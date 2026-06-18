"""Tests for the pid-death recovery predicate (spec §R1, Phase 1).

:func:`cortex_command.overnight.recovery.needs_recovery_pid_death` is the
false-positive-free, read-only detection predicate: a session needs
recovery iff its on-disk ``phase`` is ``"executing"`` AND its recorded
session-leader ``runner.pid`` is no longer alive. These tests assert the
three discriminating cases from the spec's acceptance criterion:

  (a) executing + dead-pid -> True
  (b) executing + live-pid (this process's payload) -> False
  (c) paused / complete -> False (regardless of pid liveness)

The pid fixtures mirror the ``_alive_pid_payload``/``_write_runner_pid``
helpers from ``tests/test_ipc_verify_runner_pid.py``; the state writer
mirrors the ``_write_state`` helper from ``tests/test_runner_resume.py``,
extended to set the session ``phase`` the predicate keys on.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight.recovery import needs_recovery_pid_death
from cortex_command.overnight.state import OvernightState, save_state


def _alive_pid_payload(pid: int) -> dict:
    """Return a well-formed ``runner.pid`` payload for a live ``pid``.

    Mirrors ``tests/test_ipc_verify_runner_pid.py``: a payload with the
    correct magic, an in-range schema version, and a ``start_time``
    matching ``pid``'s ``create_time`` verifies as live.
    """
    epoch = psutil.Process(pid).create_time()
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
        "session_id": "2026-04-24-12-00-00",
    }


def _dead_pid_payload(pid: int) -> dict:
    """Return a well-formed ``runner.pid`` payload for a dead ``pid``.

    The schema is valid (correct magic, in-range version) but the recorded
    process is gone, so :func:`ipc.verify_runner_pid` reads it as dead via
    ``psutil.NoSuchProcess``. ``start_time`` is a placeholder — it is never
    matched, because the process no longer exists.
    """
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "session_id": "2026-04-24-12-00-00",
    }


def _write_runner_pid(session_dir: Path, payload: dict) -> None:
    """Write a ``runner.pid`` JSON file into ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload))


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running.

    Spawns a trivial child, waits for it to exit, and returns its pid so
    ``verify_runner_pid`` reads it as dead.
    """
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _write_state(session_dir: Path, phase: str) -> None:
    """Write a minimal overnight state at ``phase`` into ``session_dir``.

    Mirrors ``tests/test_runner_resume.py``'s ``_write_state`` helper,
    extended to set the session ``phase`` that the predicate reads. A
    ``paused`` state additionally needs ``paused_from`` to be valid per
    ``OvernightState`` invariants.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {
        "session_id": "overnight-2026-04-24-recovery",
        "plan_ref": "cortex/lifecycle/overnight-plan.md",
        "phase": phase,
    }
    if phase == "paused":
        kwargs["paused_from"] = "executing"
    state = OvernightState(**kwargs)
    save_state(state, session_dir / "overnight-state.json")


def test_executing_dead_pid_needs_recovery(tmp_path: Path) -> None:
    """executing + dead runner pid -> needs recovery (spec §R1 case a)."""
    _write_state(tmp_path, "executing")
    _write_runner_pid(tmp_path, _dead_pid_payload(_dead_pid()))

    assert needs_recovery_pid_death(tmp_path) is True


def test_executing_live_pid_no_recovery(tmp_path: Path) -> None:
    """executing + live runner pid -> no recovery (spec §R1 case b).

    A live runner's pid is always alive, so the predicate must never
    false-positive on healthy work.
    """
    _write_state(tmp_path, "executing")
    _write_runner_pid(tmp_path, _alive_pid_payload(os.getpid()))

    assert needs_recovery_pid_death(tmp_path) is False


def test_paused_phase_no_recovery(tmp_path: Path) -> None:
    """paused -> no recovery even with a dead pid (spec §R1 case c)."""
    _write_state(tmp_path, "paused")
    _write_runner_pid(tmp_path, _dead_pid_payload(_dead_pid()))

    assert needs_recovery_pid_death(tmp_path) is False


def test_complete_phase_no_recovery(tmp_path: Path) -> None:
    """complete -> no recovery even with a dead pid (spec §R1 case c)."""
    _write_state(tmp_path, "complete")
    _write_runner_pid(tmp_path, _dead_pid_payload(_dead_pid()))

    assert needs_recovery_pid_death(tmp_path) is False
