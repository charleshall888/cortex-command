"""Session-state mutation helpers for the scan-lifecycle hook.

Pure-function helpers that mutate ``.session`` and ``.session-owner``
files within a feature's lifecycle directory. These ports the bash
hook's session-state migration and claim semantics into Python with two
durability/safety properties the bash version lacked:

* **Atomic writes** via ``tempfile.NamedTemporaryFile`` + ``os.replace``
  so partial writes cannot land on disk if the process dies mid-write
  (no zero-byte ``.session`` window).
* **Inter-process serialization** via ``fcntl.flock(LOCK_EX)`` on a
  per-feature directory-level lockfile (``{feature_dir}/.lock``), so
  two concurrent SessionStart invocations never observe each other's
  partial filesystem state.

Branches implemented (per spec req #6):

* ``migrate_session_p1`` — **(P1) Phase 1 migration**: a feature's
  ``.session`` matches the stale ``LIFECYCLE_SESSION_ID``. Overwrite
  ``.session`` with the new ``SESSION_ID`` AND write ``.session-owner``
  with the prior stale id. (bash precedent: lines 49-59)
* ``migrate_session_p2`` — **(P2) Phase 2 chain migration**: a
  feature's ``.session-owner`` matches the stale id and Phase 1 did not
  fire. Write ``.session`` with the new id; leave ``.session-owner``
  unchanged. (bash precedent: lines 61-72)
* ``claim_single_feature`` — **(SC) Single-feature crash-recovery**:
  exactly one incomplete feature with no session match. Write the new
  ``SESSION_ID`` to that feature's ``.session``. (bash precedent: lines
  343-351)
* ``skip_orphan_session_owner`` — **(OR) Orphan ``.session-owner``** —
  **DEPARTURE from bash**: bash silently resurrects ``.session`` from a
  matching ``.session-owner`` even when the feature is complete (line 69
  comment notwithstanding, the assignment fires). The Python port
  detects ``.session-owner`` present + ``.session`` absent and skips
  writing — bash's behavior is treated as a latent bug.

This module does NOT modify ``scan_lifecycle.py``; Task 8 wires these
helpers into the orchestrator.
"""

from __future__ import annotations

import errno
import fcntl
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically.

    Uses ``tempfile.NamedTemporaryFile(delete=False)`` in the same
    directory as ``path`` so the subsequent ``os.replace`` is an atomic
    same-filesystem rename. On any exception the temp file is unlinked
    so no abandoned ``.tmp`` files accumulate.

    Parameters
    ----------
    path:
        Destination file path. Parent directory must exist (the caller
        owns directory creation — these helpers operate on feature
        directories that are guaranteed to exist).
    content:
        UTF-8 text payload. The trailing newline policy matches the
        bash hook: written verbatim with no implicit newline appended.
    """

    parent = path.parent
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp.close()
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@contextmanager
def feature_lock(feature_dir: Path) -> Iterator[None]:
    """Hold an exclusive advisory flock on the feature directory.

    Lockfile path: ``{feature_dir}/.lock``. The lockfile is created
    with mode ``0o600`` if absent; its content is never written to.
    The lock is released on exit (normal or exceptional).

    Parameters
    ----------
    feature_dir:
        Directory containing the ``.session`` / ``.session-owner``
        files for a single feature. Must exist on entry.

    Notes
    -----
    Lock is on the lockfile *inode*, not the data files — this matches
    the precedent in ``cortex_command/init/settings_merge.py`` where
    ``atomic_write``'s ``os.replace`` swaps the data-file inode and
    would otherwise defeat a lock held on the data file directly.
    """

    feature_dir.mkdir(parents=True, exist_ok=True)
    lock_path = feature_dir / ".lock"
    fd = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC,
        0o600,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _read_id(path: Path) -> str | None:
    """Read a ``.session`` / ``.session-owner`` payload, stripped.

    Returns ``None`` if the file is absent or unreadable. Mirrors the
    bash ``cat ... | tr -d '[:space:]'`` form: whitespace stripped from
    both ends and from within (matching ``tr -d``).
    """

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EISDIR):
            return None
        raise
    # bash uses `tr -d '[:space:]'` which removes ALL whitespace, not
    # just leading/trailing. Match that for parity.
    return "".join(raw.split())


def migrate_session_p1(
    feature_dir: Path, new_id: str, stale_id: str
) -> bool:
    """**(P1) Phase 1 migration**.

    If ``feature_dir/.session`` exists and its content matches
    ``stale_id``, overwrite it with ``new_id`` AND write
    ``feature_dir/.session-owner`` with the prior ``stale_id``.

    Returns ``True`` when the migration fired (both files written),
    ``False`` otherwise (no ``.session`` file, or content does not
    match ``stale_id``). The caller drives the per-directory loop
    that the bash hook expresses as a glob; this helper handles a
    single feature directory under its own flock.

    bash precedent: lines 49-59 of ``hooks/cortex-scan-lifecycle.sh``.
    """

    session_path = feature_dir / ".session"
    owner_path = feature_dir / ".session-owner"

    with feature_lock(feature_dir):
        current = _read_id(session_path)
        if current is None or current != stale_id:
            return False
        _atomic_write(session_path, new_id)
        _atomic_write(owner_path, stale_id)
        return True


def migrate_session_p2(
    lifecycle_dir: Path, new_id: str, stale_id: str
) -> list[Path]:
    """**(P2) Phase 2 chain migration**.

    Iterate features under ``lifecycle_dir`` and, for each feature
    whose ``.session-owner`` matches ``stale_id``, write ``new_id``
    into ``.session`` (leaving ``.session-owner`` unchanged).

    Returns the list of feature directories that received a write.
    The bash hook only enters this loop when Phase 1 produced no
    matches; that ordering belongs to Task 8's orchestrator, not to
    this helper — callers must gate the invocation themselves.

    bash precedent: lines 61-72 of ``hooks/cortex-scan-lifecycle.sh``.
    """

    written: list[Path] = []
    if not lifecycle_dir.is_dir():
        return written

    for child in sorted(lifecycle_dir.iterdir()):
        if not child.is_dir():
            continue
        owner_path = child / ".session-owner"
        if not owner_path.is_file():
            continue
        with feature_lock(child):
            owner_id = _read_id(owner_path)
            if owner_id != stale_id:
                continue
            # .session-owner stays unchanged — it holds the original
            # stale id so chained /clear events keep migrating.
            _atomic_write(child / ".session", new_id)
            written.append(child)
    return written


def claim_single_feature(feature_dir: Path, new_id: str) -> None:
    """**(SC) Single-feature crash-recovery claim**.

    The orchestrator has determined there is exactly one incomplete
    feature and no ``.session`` matched the current ``SESSION_ID``.
    Write ``new_id`` to ``feature_dir/.session`` so the feature is
    claimed by this session.

    The caller owns the "exactly one incomplete feature" decision;
    this helper unconditionally writes ``.session``. It does NOT
    touch ``.session-owner``.

    bash precedent: lines 343-351 of ``hooks/cortex-scan-lifecycle.sh``.
    """

    with feature_lock(feature_dir):
        _atomic_write(feature_dir / ".session", new_id)


def skip_orphan_session_owner(feature_dir: Path) -> bool:
    """**(OR) Orphan ``.session-owner`` detection — DEPARTURE from bash**.

    Returns ``True`` if ``feature_dir`` has a ``.session-owner`` but
    no ``.session``, signalling that the caller should NOT write a
    new ``.session`` (the bash hook's chain-migration would resurrect
    one; this is intentionally not reproduced).

    Returns ``False`` when both files coexist or when both are absent
    — those cases fall through to the normal P1/P2/SC flow.

    This helper is read-only; it acquires no lock and writes nothing.
    The caller is responsible for using the return value to skip the
    P2 write path for this feature.
    """

    session_path = feature_dir / ".session"
    owner_path = feature_dir / ".session-owner"
    return owner_path.is_file() and not session_path.is_file()
