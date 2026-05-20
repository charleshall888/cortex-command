"""Concurrency invariant parity test for ``cortex_command.clean``.

Task 9 / Phase 2 of ticket-255 (gate-policy-taxonomy-and-critical-review).
This file is the dedicated parity-style sibling of
``tests/test_clean_adhoc.py``. It exists in its own file (mirroring the
precedent set by ``tests/test_critical_review_gate_class_parity.py``
in Phase 1 / Task 1) so a future refactor of the scenario suite cannot
silently delete the invariant: the file name itself telegraphs the
contract, and the named-failure diagnostic
``Concurrency invariant violated — tombstone-rename atomicity broken``
is grep-discoverable from both source and CI output.

The invariant being enforced:

  Deletion of a snapshot directory under ``cortex/_adhoc/`` uses a
  two-pass tombstone-rename pattern:

    Pass 1: ``os.rename(<sha[2:]>/, .tombstone-<sha[2:]>/)`` — atomic
            within a filesystem.
    Pass 2: ``shutil.rmtree(.tombstone-<sha[2:]>/)`` — operates on a
            name owned by this invocation.

  Concurrent invocations of ``cortex clean --adhoc``:
    - cannot half-delete a snapshot (atomicity from ``os.rename``)
    - cannot error if a peer already tombstoned the same snapshot
      (the collision is caught and treated as benign)
    - skip ``.tombstone-*`` directories at enumeration time (a peer
      owns the cleanup of that tombstone)

  Tests in this file:

    test_tombstone_rename_atomic_against_concurrent_cleaner
      Simulates two concurrent invocations via a fixture that
      pre-places a ``.tombstone-<sha[2:]>/`` directory in the
      ``<sha[:2]>/`` fanout BEFORE invoking ``run_adhoc``. The
      invocation must not error, must not half-delete the snapshot
      itself (it would have been queued for deletion by an old peer
      cleaner), and must end with exactly one final state — the
      tombstone is gone (the surviving invocation rm -rf'd it) and the
      original snapshot is either gone (deleted in a single pass after
      reclaiming the orphan) or absent because it was never created in
      the first place. The assertion focuses on "no error, no
      half-delete, exactly one final ``rm -rf``" — the named-failure
      diagnostic fires if the tombstone-rename pattern is removed.

    test_concurrent_cleaner_skips_tombstoned_directory
      Pre-places a ``.tombstone-<sha[2:]>/`` at the leaf level under a
      valid fanout dir, then invokes ``run_adhoc`` and asserts the
      tombstone is NOT touched by enumeration (the skip-on-tombstone
      branch of ``_enumerate_snapshot_dirs`` skips ``.tombstone-*``
      prefixes). The second invocation observes the tombstone and
      defers ownership of cleanup to the first invocation.

Both tests fail with the named diagnostic
``Concurrency invariant violated — tombstone-rename atomicity broken``
if any of the following regressions occur:
  - ``os.rename`` is removed from ``_delete_snapshot`` (the deletion
    becomes direct ``shutil.rmtree`` and the atomicity claim is lost).
  - The skip-on-tombstone branch in ``_enumerate_snapshot_dirs`` is
    deleted (a concurrent invocation would re-tombstone or re-delete a
    directory another invocation owns).
  - The collision-handling branch (``EEXIST`` / ``ENOTEMPTY``) is
    removed from ``_delete_snapshot`` (the second invocation raises
    instead of skipping).
"""

from __future__ import annotations

import hashlib
import inspect
import io
import os
import re
import time
from pathlib import Path

from cortex_command import clean
from cortex_command.clean import RETENTION_SECONDS, run_adhoc


# ---------------------------------------------------------------------------
# Named-failure diagnostic substring (matches the spec verbatim)
# ---------------------------------------------------------------------------

# This literal substring is the grep-discoverable signal. The spec's
# Requirement 9 acceptance criterion names this exact phrase; future
# CI grep against test output (or a maintainer running ``rg
# 'Concurrency invariant violated'``) lands on the failing assertion
# message in one shot.
_NAMED_DIAGNOSTIC = (
    "Concurrency invariant violated — tombstone-rename atomicity broken"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Build a minimal repo scaffold under ``tmp_path`` and return the root."""
    repo = tmp_path / "repo"
    (repo / "cortex" / "lifecycle").mkdir(parents=True)
    (repo / "cortex" / "_adhoc").mkdir(parents=True)
    return repo


def _make_snapshot(
    repo: Path, content: bytes, *, age_seconds: float | None = None
) -> tuple[Path, str]:
    """Create a snapshot directory under ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/``."""
    full_sha = hashlib.sha256(content).hexdigest()
    leaf = repo / "cortex" / "_adhoc" / full_sha[:2] / full_sha[2:]
    leaf.mkdir(parents=True)
    (leaf / "snapshot.md").write_bytes(content)
    if age_seconds is not None:
        target_mtime = time.time() - age_seconds
        os.utime(leaf, (target_mtime, target_mtime))
    return leaf, full_sha


def _strip_docstring_and_comments(source: str) -> str:
    """Return ``source`` with the leading docstring and ``#`` comments removed.

    Mirrors the helper of the same name in
    ``tests/test_critical_review_gate_class_parity.py``. The structural
    guard regexes below must match executable code, not archaeological
    prose inside the docstring (which legitimately mentions
    ``os.rename``, ``.tombstone-``, ``errno.EEXIST``/``errno.ENOTEMPTY``
    as part of the narrative explanation of the pattern). Without this
    stripping pass, a regression that removed the executable
    ``os.rename`` call but left the docstring intact would fool the
    structural check.
    """
    # Remove the first triple-quoted block (the function docstring).
    no_docstring = re.sub(
        r'""".*?"""', "", source, count=1, flags=re.DOTALL,
    )
    # Strip inline ``# ...`` comments line-by-line.
    out_lines: list[str] = []
    for line in no_docstring.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _assert_tombstone_rename_pattern_intact() -> None:
    """Source-level guard: fail with the named diagnostic if the pattern is broken.

    This pre-flight check confirms that ``_delete_snapshot`` and
    ``_enumerate_snapshot_dirs`` still implement the tombstone-rename
    pattern in *executable code* (docstring and comments stripped).
    Without this guard, a regression that replaced ``os.rename`` with
    direct ``shutil.rmtree`` would only show up indirectly as the
    runtime behavioral assertions failing; the structural guard makes
    the named diagnostic fire immediately on pattern removal, even
    before the runtime behavior is exercised.

    The diagnostic substring matches the spec's Requirement 9
    acceptance criterion verbatim.
    """
    delete_src = _strip_docstring_and_comments(
        inspect.getsource(clean._delete_snapshot)
    )
    enumerate_src = _strip_docstring_and_comments(
        inspect.getsource(clean._enumerate_snapshot_dirs)
    )

    # Structural check 1: _delete_snapshot must call os.rename in
    # executable code (not just narrate it in the docstring).
    if not re.search(r"\bos\.rename\s*\(", delete_src):
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + ": _delete_snapshot no longer contains an `os.rename(...)` "
            + "call in executable code. The tombstone-rename two-pass "
            + "pattern requires the first pass to be "
            + "`os.rename(leaf_dir, tombstone)`; replacing it with "
            + "direct `shutil.rmtree` loses atomicity against concurrent "
            + "cleaners."
        )

    # Structural check 2: _delete_snapshot must reference .tombstone- as
    # the rename target prefix in executable code.
    if ".tombstone-" not in delete_src:
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + ": _delete_snapshot no longer references the "
            + "`.tombstone-` name prefix in executable code. The "
            + "tombstone-rename pattern renames `<sha[2:]>/` to "
            + "`.tombstone-<sha[2:]>/` before `rm -rf`'ing; removing the "
            + "prefix removes the pattern."
        )

    # Structural check 3: _delete_snapshot must catch the collision
    # errnos (EEXIST / ENOTEMPTY) in executable code so concurrent
    # cleaners do not raise.
    if not (
        re.search(r"\berrno\.EEXIST\b", delete_src)
        or re.search(r"\berrno\.ENOTEMPTY\b", delete_src)
    ):
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + ": _delete_snapshot no longer handles the rename-collision "
            + "errnos (EEXIST/ENOTEMPTY) in executable code. A peer "
            + "cleaner that tombstoned the same snapshot first must "
            + "cause the current cleaner to skip silently, not raise."
        )

    # Structural check 4: _enumerate_snapshot_dirs must filter
    # `.tombstone-` in executable code so a second invocation skips the
    # tombstoned dir.
    if ".tombstone-" not in enumerate_src:
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + ": _enumerate_snapshot_dirs no longer filters `.tombstone-` "
            + "directories in executable code. A concurrent invocation "
            + "that does not skip tombstones would re-tombstone or "
            + "re-delete a directory the peer cleaner owns."
        )


# ---------------------------------------------------------------------------
# Test 1: tombstone-rename atomicity against a concurrent cleaner
# ---------------------------------------------------------------------------


def test_tombstone_rename_atomic_against_concurrent_cleaner(tmp_path: Path) -> None:
    """Atomicity invariant: tombstone-rename two-pass survives a peer cleaner.

    Simulates the scenario in which a peer cleaner has already completed
    Pass 1 (the atomic rename to ``.tombstone-<sha[2:]>``) and is in
    the middle of Pass 2 (``shutil.rmtree``). The current invocation
    must not error and must end in a coherent final state: no
    half-deleted snapshot, no orphaned tombstone, no exception
    propagated to the caller.

    Fixture setup (pre-placed before ``run_adhoc`` runs):
      - A fanout directory ``<sha[:2]>/``.
      - A pre-existing tombstone ``<sha[:2]>/.tombstone-<sha[2:]>/``
        with marker contents (simulates a peer cleaner mid-Pass-2).
      - NO live snapshot at ``<sha[:2]>/<sha[2:]>/`` — the peer already
        renamed it. The current invocation's enumeration finds nothing
        to delete; the tombstone is filtered by the
        ``.tombstone-`` prefix.

    Asserts:
      - No exception raised by ``run_adhoc``.
      - Exit code 0 (clean parse, deletions completed — even if the
        only "deletion" was conceptually owned by the peer).
      - The tombstone directory is untouched by the current invocation
        (the peer owns it). Future scans will continue to ignore it
        until the peer finishes its second pass.
      - The named diagnostic fires if the tombstone-rename pattern is
        absent at the source level (the structural guard runs first).
    """
    _assert_tombstone_rename_pattern_intact()

    repo = _make_repo(tmp_path)

    # Compose a fake SHA-shape and pre-place a tombstone directly under
    # the fanout dir. No live snapshot exists at this SHA — the peer
    # cleaner already renamed it. Use 62 hex chars for the suffix so
    # the tombstone name (`.tombstone-<62 hex>`) is realistic.
    full_sha = "ab" + ("c" * 62)
    fanout = repo / "cortex" / "_adhoc" / full_sha[:2]
    fanout.mkdir()
    tombstone = fanout / (".tombstone-" + full_sha[2:])
    tombstone.mkdir()
    (tombstone / "marker").write_text("peer-mid-pass-2", encoding="utf-8")

    # Back-date the tombstone so age alone would qualify it for
    # deletion — the cleaner must still skip because of the prefix.
    target_mtime = time.time() - (RETENTION_SECONDS + 60)
    os.utime(tombstone, (target_mtime, target_mtime))

    # Also pre-place a real old-and-unpinned snapshot in a separate
    # fanout dir, so the cleaner has actual work to do alongside the
    # tombstone. This proves the cleaner is functioning and confirms
    # that the tombstone-rename pattern is exercised on the real
    # deletion target (not bypassed by an empty work list).
    real_snapshot_leaf, _real_sha = _make_snapshot(
        repo,
        b"real concurrent-cleanup target\n",
        age_seconds=RETENTION_SECONDS + 60,
    )

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        exit_code = run_adhoc(repo, stdout=stdout_buf, stderr=stderr_buf)
    except Exception as exc:  # noqa: BLE001 — pin failure to the named diagnostic.
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + f": run_adhoc raised {type(exc).__name__}: {exc!r} when a peer "
            + f"cleaner had already pre-placed a `.tombstone-*` directory. "
            + f"A concurrent invocation must skip tombstones silently, "
            + f"not raise."
        ) from exc

    assert exit_code == 0, (
        _NAMED_DIAGNOSTIC
        + f": run_adhoc returned exit code {exit_code} with a pre-placed "
        + f".tombstone-* peer; expected 0 (peer's tombstone is benign)."
    )

    # The tombstone is owned by the peer; the current invocation must
    # not have touched it (no delete, no rename, no rm -rf).
    assert tombstone.exists(), (
        _NAMED_DIAGNOSTIC
        + ": the pre-placed peer tombstone vanished — the current "
        + "invocation should leave `.tombstone-*` directories alone "
        + "(the peer owns the cleanup)."
    )
    assert (tombstone / "marker").read_text(encoding="utf-8") == "peer-mid-pass-2", (
        _NAMED_DIAGNOSTIC
        + ": the pre-placed peer tombstone's contents were modified — "
        + "the current invocation should treat `.tombstone-*` as opaque "
        + "and untouched."
    )

    # The real snapshot was a legitimate deletion target. After the
    # cleaner runs, the leaf directory should be gone AND the tombstone
    # name corresponding to it should ALSO be gone (Pass 2 completed
    # within the same invocation). Exactly one final rm -rf occurred —
    # no half-delete (leaf still present), no orphan (tombstone left
    # behind).
    assert not real_snapshot_leaf.exists(), (
        _NAMED_DIAGNOSTIC
        + ": the real old-and-unpinned snapshot was not deleted — the "
        + "tombstone-rename pattern's Pass 1 (rename) did not run."
    )
    real_tombstone = real_snapshot_leaf.parent / (
        ".tombstone-" + real_snapshot_leaf.name
    )
    assert not real_tombstone.exists(), (
        _NAMED_DIAGNOSTIC
        + ": the real deletion target left an orphaned tombstone behind "
        + "— Pass 2 (rm -rf the tombstone) did not run after Pass 1."
    )


# ---------------------------------------------------------------------------
# Test 2: concurrent cleaner skips a tombstoned directory at enumeration
# ---------------------------------------------------------------------------


def test_concurrent_cleaner_skips_tombstoned_directory(tmp_path: Path) -> None:
    """Skip-on-tombstone invariant: enumeration filters ``.tombstone-*`` leaves.

    A peer cleaner has tombstoned ``<sha[:2]>/<sha[2:]>/`` to
    ``<sha[:2]>/.tombstone-<sha[2:]>/`` and is in Pass 2. The current
    invocation enumerates ``<sha[:2]>/`` and must skip the
    ``.tombstone-*`` leaf — re-tombstoning or re-deleting would race
    with the peer's ``rm -rf``.

    Fixture setup:
      - A fanout directory ``<sha[:2]>/``.
      - A pre-existing ``.tombstone-<sha[2:]>/`` leaf with backdated
        mtime and marker contents.
      - NO live leaf at ``<sha[:2]>/<sha[2:]>/``.

    Asserts:
      - Exit code 0.
      - The tombstone is untouched.
      - No new tombstone-of-a-tombstone is created (a sign the
        enumeration filter is intact).
      - The named diagnostic fires if the skip-on-tombstone branch is
        removed from ``_enumerate_snapshot_dirs``.
    """
    _assert_tombstone_rename_pattern_intact()

    repo = _make_repo(tmp_path)

    full_sha = "fe" + ("d" * 62)
    fanout = repo / "cortex" / "_adhoc" / full_sha[:2]
    fanout.mkdir()
    tombstone_leaf = fanout / (".tombstone-" + full_sha[2:])
    tombstone_leaf.mkdir()
    (tombstone_leaf / "marker").write_text("peer-mid-pass-2", encoding="utf-8")
    target_mtime = time.time() - (RETENTION_SECONDS + 60)
    os.utime(tombstone_leaf, (target_mtime, target_mtime))

    # Pre-snapshot the fanout's children so we can assert no new
    # directories were created (no tombstone-of-a-tombstone).
    children_before = sorted(p.name for p in fanout.iterdir())

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        exit_code = run_adhoc(repo, stdout=stdout_buf, stderr=stderr_buf)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            _NAMED_DIAGNOSTIC
            + f": run_adhoc raised {type(exc).__name__}: {exc!r} when "
            + f"enumerating a fanout containing a pre-placed `.tombstone-*` "
            + f"leaf. The enumeration must skip the tombstone silently."
        ) from exc

    assert exit_code == 0, (
        _NAMED_DIAGNOSTIC
        + f": run_adhoc returned exit code {exit_code} with a tombstoned "
        + f"leaf in the fanout; expected 0."
    )

    # Tombstone is the peer's; must remain untouched.
    assert tombstone_leaf.exists(), (
        _NAMED_DIAGNOSTIC
        + ": the pre-placed `.tombstone-*` leaf vanished — enumeration "
        + "must skip tombstones and leave them for their owning "
        + "invocation to clean up."
    )
    assert (tombstone_leaf / "marker").read_text(encoding="utf-8") == "peer-mid-pass-2", (
        _NAMED_DIAGNOSTIC
        + ": the pre-placed tombstone's contents were modified."
    )

    # No new directories should have been created (no
    # tombstone-of-a-tombstone, no accidental re-rename).
    children_after = sorted(p.name for p in fanout.iterdir())
    assert children_after == children_before, (
        _NAMED_DIAGNOSTIC
        + f": the fanout directory's children changed during the "
        + f"second invocation. Before: {children_before!r}; after: "
        + f"{children_after!r}. The enumeration must skip "
        + f"`.tombstone-*` prefixes and not generate nested tombstones."
    )
