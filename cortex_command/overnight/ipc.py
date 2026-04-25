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

import json
import os
import tempfile
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


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

_RUNNER_MAGIC = "cortex-runner-v1"
_SCHEMA_VERSION = 1
MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION = 1
_START_TIME_TOLERANCE_SECONDS = 2.0

ACTIVE_SESSION_PATH: Path = (
    Path.home() / ".local" / "share" / "overnight-sessions" / "active-session.json"
)


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


def clear_runner_pid(session_dir: Path) -> None:
    """Remove ``runner.pid`` from ``session_dir`` if present."""
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
