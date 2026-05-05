"""IPC contract layer for the overnight runner.

Provides the per-session ``runner.pid`` file (R8), the global
``active-session.json`` pointer (R9), and stale-PID verification (R18).
Both artifacts share a single ``schema_version`` axis per R8's versioning
rule; the active-session pointer additionally carries a ``phase`` field.

All on-disk writes are atomic (``tempfile.NamedTemporaryFile`` +
``os.fsync`` via ``durable_fsync`` + ``os.replace``) and never leak
partial content. The initial ``runner.pid`` claim additionally uses
``O_CREAT|O_EXCL`` so two concurrent ``cortex overnight start``
invocations cannot both win the lock (R8 / Adversarial §1).
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import psutil

from cortex_command.common import durable_fsync


class ConcurrentRunnerError(Exception):
    """Raised when another runner has already claimed ``runner.pid``.

    Signals R8's race-loser path: the caller lost the
    ``O_CREAT|O_EXCL`` claim against a live (or unverifiable-but-present)
    competitor. Carries the ``session_id`` of the contended session and
    the ``existing_pid`` recorded in the on-disk claim so the MCP layer
    can surface ``{started: false, reason: "concurrent_runner_alive",
    existing_session_id: ...}`` to the caller.
    """

    def __init__(self, session_id: str, existing_pid: int) -> None:
        self.session_id = session_id
        self.existing_pid = existing_pid
        super().__init__(
            f"runner.pid already claimed for session {session_id!r} "
            f"by pid {existing_pid}"
        )


class ConcurrentRunnerLockTimeoutError(ConcurrentRunnerError):
    """Raised when the takeover lock cannot be acquired within budget.

    Distinguishes the lock-acquisition timeout failure mode from the
    base :class:`ConcurrentRunnerError` "third party beat us on the
    recreate path" signal. Operators retrying a wedged-holder scenario
    can match on this subclass (or on the explicit timeout substring in
    the message) and escalate to ``cortex overnight cancel --force``.
    """

    def __init__(
        self,
        session_id: str = "<unknown>",
        existing_pid: int = -1,
    ) -> None:
        self.session_id = session_id
        self.existing_pid = existing_pid
        # Skip ConcurrentRunnerError.__init__ — we want a distinct
        # message that the spec requires to contain the literal
        # substring "takeover lock acquire timed out".
        Exception.__init__(
            self,
            "takeover lock acquire timed out after 5s; "
            "another starter holds .runner.pid.takeover.lock",
        )


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_RUNNER_MAGIC = "cortex-runner-v1"
_SCHEMA_VERSION = 1
MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION = 1
_START_TIME_TOLERANCE_SECONDS = 2.0

_TAKEOVER_LOCK_FILENAME = ".runner.pid.takeover.lock"
_TAKEOVER_LOCK_BUDGET_SECONDS = 5.0
_TAKEOVER_LOCK_POLL_INTERVAL_SECONDS = 0.05

ACTIVE_SESSION_PATH: Path = (
    Path.home() / ".local" / "share" / "overnight-sessions" / "active-session.json"
)


# ---------------------------------------------------------------------------
# Takeover-lock helper
# ---------------------------------------------------------------------------

def _acquire_takeover_lock(session_dir: Path) -> int:
    """Acquire the per-session takeover lock with a 5-second budget.

    Opens ``session_dir / ".runner.pid.takeover.lock"`` with
    ``O_RDWR | O_CREAT | 0o600`` and performs a polling
    ``fcntl.flock(LOCK_EX | LOCK_NB)`` acquire with a 5-second total
    budget and 50 ms sleep cadence. Returns the held file descriptor on
    success.

    Caller is responsible for releasing via the nested-finally pattern::

        fd = _acquire_takeover_lock(session_dir)
        try:
            ...work...
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    On budget exhaustion, raises
    :class:`ConcurrentRunnerLockTimeoutError` with
    ``existing_session_id="<unknown>"`` and ``existing_pid=-1`` and an
    explicit timeout message so operators can distinguish timeout from
    a genuine concurrent-runner collision. Pattern reference:
    ``cortex_command/init/settings_merge.py:_acquire_lock`` (sibling
    lockfile rationale) and
    ``plugins/cortex-overnight/server.py:_acquire_update_flock``
    (polling-with-budget shape).
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    lock_path = session_dir / _TAKEOVER_LOCK_FILENAME
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + _TAKEOVER_LOCK_BUDGET_SECONDS
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
            if time.monotonic() >= deadline:
                raise ConcurrentRunnerLockTimeoutError(
                    session_id="<unknown>",
                    existing_pid=-1,
                )
            time.sleep(_TAKEOVER_LOCK_POLL_INTERVAL_SECONDS)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, payload: dict, mode: int = 0o600) -> None:
    """Write ``payload`` as JSON to ``path`` atomically.

    Uses ``tempfile.NamedTemporaryFile`` in ``path.parent`` with
    ``delete=False``, fsyncs durably, closes, then ``os.replace`` onto
    the destination. Applies ``os.chmod(mode)`` after replace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
        tmp.flush()
        durable_fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp_path, path)
        os.chmod(path, mode)
    except BaseException:
        try:
            tmp.close()
        except OSError:
            pass
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Per-session runner.pid (R8)
# ---------------------------------------------------------------------------

def _exclusive_create_runner_pid(path: Path, payload: dict) -> None:
    """Create ``path`` exclusively and write ``payload`` as JSON.

    Uses ``os.open`` with ``O_CREAT | O_EXCL | O_WRONLY`` and mode
    ``0o600``. Raises ``FileExistsError`` if another writer already
    created the file. On any post-open failure the partially-written
    file is unlinked so a retry sees a clean slate.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")

    fd = os.open(
        str(path),
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    try:
        os.write(fd, data)
        durable_fsync(fd)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass
        raise
    else:
        os.close(fd)


def write_runner_pid(
    session_dir: Path,
    pid: int,
    pgid: int,
    start_time: str,
    session_id: str,
    repo_path: Path,
    lock_fd: int | None = None,
) -> None:
    """Atomically claim ``runner.pid`` in ``session_dir`` via O_EXCL.

    Schema matches R8 exactly: ``schema_version: 1``,
    ``magic: "cortex-runner-v1"``, plus the passed fields. File mode is
    ``0o600``.

    The initial claim uses ``os.open(O_CREAT | O_EXCL | O_WRONLY)`` so
    two concurrent starters cannot both win the lock. On
    ``FileExistsError``:

    1. Read the existing payload and run :func:`verify_runner_pid`.
    2. If verification fails (stale PID), unlink and retry the claim
       exactly once.
    3. If verification passes (the existing claim points at a live
       runner), raise :class:`ConcurrentRunnerError`.
    4. If the retry's second claim also collides — a third party beat
       us to the recreated file — re-read, run verify, and raise
       :class:`ConcurrentRunnerError` regardless of liveness. The
       retry budget is exactly one; the loop never spins.

    The full read-verify-claim sequence (initial ``O_EXCL`` AND retry
    path) is serialized under the per-session takeover lock
    (``.runner.pid.takeover.lock``). When ``lock_fd`` is ``None``, the
    function acquires its own takeover lock for the entire claim
    sequence and releases it via ``fcntl.flock(LOCK_UN)`` followed by
    ``os.close`` in nested ``finally`` blocks (so ``os.close`` runs
    unconditionally even if ``LOCK_UN`` raises). When ``lock_fd is not
    None``, the function operates inside the caller's critical section
    and does NOT acquire its own lock; the caller is responsible for
    release.
    """
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "magic": _RUNNER_MAGIC,
        "pid": pid,
        "pgid": pgid,
        "start_time": start_time,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(repo_path),
    }
    path = session_dir / "runner.pid"

    if lock_fd is None:
        owned_fd = _acquire_takeover_lock(session_dir)
        try:
            _write_runner_pid_locked(path, payload, session_id)
        finally:
            try:
                fcntl.flock(owned_fd, fcntl.LOCK_UN)
            finally:
                os.close(owned_fd)
    else:
        _write_runner_pid_locked(path, payload, session_id)


def _write_runner_pid_locked(
    path: Path,
    payload: dict,
    session_id: str,
) -> None:
    """Run the read-verify-claim sequence under a held takeover lock.

    Caller must already hold the per-session takeover lock for
    ``path.parent``. Both the initial ``O_EXCL`` claim and the
    unlink-then-retry path execute inside the same critical section so
    the re-verify step is the load-bearing CAS detecting any
    third-party live claim that arrived between attempts.
    """
    session_dir = path.parent

    try:
        _exclusive_create_runner_pid(path, payload)
        return
    except FileExistsError:
        pass

    existing = read_runner_pid(session_dir)
    if existing is not None and verify_runner_pid(existing):
        existing_session_id = existing.get("session_id", session_id)
        existing_pid = existing.get("pid", -1)
        raise ConcurrentRunnerError(existing_session_id, existing_pid)

    # Stale claim — unlink and retry exactly once.
    try:
        path.unlink()
    except FileNotFoundError:
        pass

    try:
        _exclusive_create_runner_pid(path, payload)
        return
    except FileExistsError:
        # A third party beat us to the recreated claim. Treat as alive
        # race-loser to break the loop deterministically.
        existing = read_runner_pid(session_dir)
        if existing is not None:
            verify_runner_pid(existing)
            existing_session_id = existing.get("session_id", session_id)
            existing_pid = existing.get("pid", -1)
        else:
            existing_session_id = session_id
            existing_pid = -1
        raise ConcurrentRunnerError(existing_session_id, existing_pid)


def clear_runner_pid(
    session_dir: Path,
    expected_session_id: str | None = None,
) -> None:
    """Remove ``runner.pid`` from ``session_dir`` if present.

    When ``expected_session_id`` is ``None`` (the default), the unlink is
    unconditional — appropriate for lock-covered call sites that have
    already verified ownership under the takeover lock.

    When ``expected_session_id`` is provided, perform a compare-and-swap
    by reading the on-disk ``runner.pid`` first and only unlinking if
    the JSON's ``session_id`` field equals ``expected_session_id``.
    Otherwise no-op silently. This closes the residual race where a
    displaced owner's unlocked clear could clobber a new owner's
    just-written claim during a takeover transition. If the file is
    absent or its payload is unreadable, the read returns ``None`` and
    this function no-ops (mirroring :func:`read_runner_pid`'s
    semantics).
    """
    if expected_session_id is None:
        (session_dir / "runner.pid").unlink(missing_ok=True)
        return

    pid_data = read_runner_pid(session_dir)
    if pid_data is None:
        return
    if pid_data.get("session_id") != expected_session_id:
        return
    (session_dir / "runner.pid").unlink(missing_ok=True)


def read_runner_pid(session_dir: Path) -> dict | None:
    """Return the parsed ``runner.pid`` dict, or ``None`` if absent."""
    path = session_dir / "runner.pid"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify_runner_pid(pid_data: dict) -> bool:
    """Verify a ``runner.pid`` payload matches a running process.

    Checks ``magic == "cortex-runner-v1"``, ``1 <= schema_version <=
    MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION``, and
    ``psutil.Process(pid).create_time()`` within ±2s of the
    recorded ``start_time``. Returns ``False`` on any mismatch,
    ``psutil.NoSuchProcess``, or ``psutil.AccessDenied``. Never signals;
    never raises to the caller. A future ``schema_version`` exceeding the
    known maximum is rejected to prevent silent mis-decoding when an
    older ``cortex`` reads a newer runner's PID file.
    """
    if not isinstance(pid_data, dict):
        return False

    if pid_data.get("magic") != _RUNNER_MAGIC:
        return False

    schema_version = pid_data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or schema_version < 1
        or schema_version > MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION
    ):
        return False

    pid = pid_data.get("pid")
    start_time_str = pid_data.get("start_time")
    if not isinstance(pid, int) or not isinstance(start_time_str, str):
        return False

    try:
        recorded_epoch = datetime.fromisoformat(
            start_time_str.replace("Z", "+00:00")
        ).timestamp()
    except (ValueError, TypeError):
        return False

    try:
        actual_epoch = psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False

    return abs(actual_epoch - recorded_epoch) <= _START_TIME_TOLERANCE_SECONDS


# ---------------------------------------------------------------------------
# Active-session pointer (R9)
# ---------------------------------------------------------------------------

def write_active_session(pid_data: dict, phase: str) -> None:
    """Write the active-session pointer atomically.

    Merges ``pid_data`` with ``{"phase": phase}`` and writes to
    :data:`ACTIVE_SESSION_PATH`. Creates the parent directory if needed.
    """
    payload = dict(pid_data)
    payload["phase"] = phase
    _atomic_write_json(ACTIVE_SESSION_PATH, payload, mode=0o600)


def read_active_session() -> dict | None:
    """Return the parsed active-session pointer, or ``None`` if absent."""
    if not ACTIVE_SESSION_PATH.exists():
        return None
    try:
        return json.loads(ACTIVE_SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def update_active_session_phase(session_id: str, new_phase: str) -> None:
    """Update the active-session pointer's phase.

    Reads the pointer, verifies the ``session_id`` matches, then
    atomically rewrites with the updated phase. Used for ``paused`` and
    pre-``complete`` transitions; ``complete`` should use
    :func:`clear_active_session` instead.
    """
    current = read_active_session()
    if current is None:
        return
    if current.get("session_id") != session_id:
        return
    current["phase"] = new_phase
    _atomic_write_json(ACTIVE_SESSION_PATH, current, mode=0o600)


def clear_active_session() -> None:
    """Remove the active-session pointer file if present."""
    ACTIVE_SESSION_PATH.unlink(missing_ok=True)
