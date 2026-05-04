"""Cross-process schedule lock for the overnight scheduler.

Exposes :func:`schedule_lock`, an exclusive ``fcntl.flock`` context
manager around ``~/.cache/cortex-command/scheduled-launches.lock``. The
schedule path acquires this lock BEFORE running the GC pass and holds
it continuously through launcher install, plist write,
``launchctl bootstrap`` + verify, and the sidecar entry write. Holding
the lock across the entire critical section prevents the race where
Process B's GC observes Process A's just-written plist as orphan
(label not yet in sidecar) and removes it before A's sidecar entry
lands.

Pattern mirrors the existing ``fcntl.flock`` usage at
:mod:`cortex_command.overnight.ipc` and :mod:`cortex_command.overnight.runner`
— open a sidecar lockfile in append mode (auto-creates the file),
``flock(LOCK_EX)`` it, yield, then release in a ``finally``. The lock
is process-scoped: one acquire per ``schedule()`` call; it does NOT
span the entire CLI session.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from collections.abc import Iterator
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cache directory containing the sidecar index and its lockfile.
_CACHE_DIR_RELATIVE = Path(".cache") / "cortex-command"

# Lockfile filename. Distinct from the sidecar index filename so a
# concurrent reader of the index never accidentally truncates the lock.
_LOCK_FILENAME = "scheduled-launches.lock"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """Resolve ``~/.cache/cortex-command/``.

    Pure path resolution — does not create the directory. Callers that
    need the directory to exist should call ``mkdir(parents=True,
    exist_ok=True)``.
    """
    return Path.home() / _CACHE_DIR_RELATIVE


def _lock_path() -> Path:
    """Absolute path to the schedule-lock file."""
    return _cache_dir() / _LOCK_FILENAME


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def schedule_lock() -> Iterator[None]:
    """Acquire an exclusive ``fcntl.flock`` on the schedule lockfile.

    Creates ``~/.cache/cortex-command/`` if it does not yet exist
    (handles the first-install case). Opens the lockfile in append
    mode so the file auto-creates on first use without truncating
    pre-existing content. Acquires :data:`fcntl.LOCK_EX` (blocking)
    and yields control to the caller. Releases the lock and closes the
    file descriptor in a ``finally`` block so a raised exception in
    the protected block does not leak the lock.

    The lock serializes the schedule critical section across processes:
    GC + launcher install + plist write + bootstrap + verify + sidecar
    write. It does NOT serialize cancel, list, or status reads — those
    paths read the sidecar without holding the lock per the task
    contract ("the lock is process-scoped (one acquire per
    ``schedule()`` call); it does NOT span the entire CLI session").

    Yields:
        None. The caller runs its critical section inside the
        ``with`` block.
    """
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path()

    # 'a' mode (text-append) — auto-creates the file, never truncates,
    # leaves a usable file descriptor we can flock on. Mirrors the
    # existing ``open(... "a")`` + flock pattern used elsewhere in
    # cortex-command lock helpers.
    fp = open(lock_path, "a")
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        try:
            yield None
        finally:
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
            except OSError:
                # Best effort — even if unlock raises (e.g. process
                # going down), the close below releases the underlying
                # OS lock.
                pass
    finally:
        try:
            fp.close()
        except OSError:
            pass


__all__ = ["schedule_lock"]
