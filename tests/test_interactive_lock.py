"""Unit tests for cortex_command.interactive_lock.

Covers:
- R4 eight-row branch table (test_verify_live_owner_row_1 through _row_8)
- R3 schema shape on a fresh acquire
- R6 stale-recovery negative test: merge --abort / worktree remove are never invoked

Test isolation uses monkeypatch + tmp_path; CORTEX_REPO_ROOT is set to tmp_path
so _resolve_user_project_root() returns an isolated directory rather than the
real repo root.
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import psutil
import pytest

import cortex_command.interactive_lock as il


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_lock(
    *,
    session_id: str | None = "stored-session",
    pid: int = 99999,
    start_time: float | None = 12345.0,
    acquired_at: str = "2024-01-01T00:00:00+00:00",
) -> dict:
    """Build a minimal valid lock dict for testing."""
    return {
        "schema_version": 1,
        "magic": "cortex-interactive-lock",
        "session_id": session_id,
        "pid": pid,
        "start_time": start_time,
        "acquired_at": acquired_at,
    }


def _setup_repo_root(tmp_path: Path) -> Path:
    """Create the cortex/ umbrella under tmp_path and return tmp_path."""
    (tmp_path / "cortex").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# R4 row tests — verify_live_owner / _verify_live_owner_with_reason
#
# Each test constructs exactly the (env-var, os.kill, start_time, psutil)
# combination specified by the R4 branch table and asserts the expected
# (LIVE/STALE, recovery_reason) tuple.
# ---------------------------------------------------------------------------


def test_verify_live_owner_row_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 1: env-var matches stored session_id → LIVE (authoritative)."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "my-session-abc")
    lock = _make_lock(session_id="my-session-abc", pid=12345)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is True
    assert reason is None


def test_verify_live_owner_row_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 2: env-var absent/mismatch, os.kill raises ESRCH → STALE (esrch)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    lock = _make_lock(session_id="some-other-session", pid=99998)

    def _kill_esrch(pid: int, sig: int) -> None:
        raise OSError(errno.ESRCH, "No such process")

    monkeypatch.setattr(os, "kill", _kill_esrch)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is False
    assert reason == "esrch"


def test_verify_live_owner_row_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 3: env-var absent/mismatch, os.kill raises EPERM → LIVE (conservative)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    lock = _make_lock(session_id="some-other-session", pid=99998)

    def _kill_eperm(pid: int, sig: int) -> None:
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "kill", _kill_eperm)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is True
    assert reason is None


def test_verify_live_owner_row_4(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 4: env-var absent/mismatch, os.kill succeeds, start_time=null → LIVE (conservative)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    lock = _make_lock(session_id="some-other-session", pid=99998, start_time=None)

    # os.kill succeeds (returns None) — no exception
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is True
    assert reason is None


def test_verify_live_owner_row_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 5: env-var absent/mismatch, os.kill succeeds, start_time non-null, matches within ±2s → LIVE."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    stored_start = 10000.0
    lock = _make_lock(session_id="some-other-session", pid=99998, start_time=stored_start)

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    # psutil.Process(pid).create_time() returns a value within ±2s
    actual_start = stored_start + 1.5  # within ±2s tolerance

    fake_process = MagicMock()
    fake_process.create_time.return_value = actual_start
    monkeypatch.setattr(psutil, "Process", lambda pid: fake_process)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is True
    assert reason is None


def test_verify_live_owner_row_6(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 6: env-var absent/mismatch, os.kill succeeds, start_time non-null, mismatches → STALE (start_time_mismatch)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    stored_start = 10000.0
    lock = _make_lock(session_id="some-other-session", pid=99998, start_time=stored_start)

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    # psutil.Process(pid).create_time() returns a value outside ±2s
    actual_start = stored_start + 100.0  # clearly outside ±2s

    fake_process = MagicMock()
    fake_process.create_time.return_value = actual_start
    monkeypatch.setattr(psutil, "Process", lambda pid: fake_process)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is False
    assert reason == "start_time_mismatch"


def test_verify_live_owner_row_7(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 7: env-var absent/mismatch, os.kill succeeds, start_time non-null, psutil.NoSuchProcess → STALE (nosuchprocess)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    lock = _make_lock(session_id="some-other-session", pid=99998, start_time=10000.0)

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    def _raise_nosuch(pid: int):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(psutil, "Process", _raise_nosuch)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is False
    assert reason == "nosuchprocess"


def test_verify_live_owner_row_8(monkeypatch: pytest.MonkeyPatch) -> None:
    """Row 8: env-var absent/mismatch, os.kill succeeds, start_time non-null, any other psutil exception → LIVE (conservative)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    lock = _make_lock(session_id="some-other-session", pid=99998, start_time=10000.0)

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    def _raise_access_denied(pid: int):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(psutil, "Process", _raise_access_denied)

    is_live, reason = il._verify_live_owner_with_reason(lock)

    assert is_live is True
    assert reason is None


# ---------------------------------------------------------------------------
# R3 schema test — fresh acquire produces a correctly shaped lock file
# ---------------------------------------------------------------------------


def test_r3_schema_fresh_acquire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R3: acquire_lock writes a JSON lock with the required schema keys,
    magic value, and mode 0o600.
    """
    project_root = _setup_repo_root(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-r3")

    result = il.acquire_lock("probe")

    assert result is True

    lock_path = project_root / "cortex" / "lifecycle" / "probe" / "interactive.pid"
    assert lock_path.exists(), f"Lock file not created at {lock_path}"

    with lock_path.open() as fh:
        d = json.load(fh)

    required_keys = {"schema_version", "magic", "session_id", "pid", "start_time", "acquired_at"}
    assert set(d.keys()) >= required_keys, (
        f"Lock file missing keys. Present: {set(d.keys())}, required: {required_keys}"
    )
    assert d["magic"] == "cortex-interactive-lock", (
        f"Expected magic='cortex-interactive-lock', got {d['magic']!r}"
    )
    assert d["schema_version"] == 1, f"Expected schema_version=1, got {d['schema_version']}"

    # File mode must be 0o600
    mode_str = oct(os.stat(lock_path).st_mode)[-3:]
    assert mode_str == "600", (
        f"Expected file mode 600, got {mode_str} for {lock_path}"
    )


# ---------------------------------------------------------------------------
# R6 stale-recovery negative test — no destructive subprocess calls
# ---------------------------------------------------------------------------


def test_r6_stale_recovery_no_destructive_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R6: stale recovery must NOT invoke subprocess.run with git merge --abort
    or git worktree remove under any STALE code path.
    """
    project_root = _setup_repo_root(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "new-session-xyz")

    # Pre-write a stale lock (env-var mismatch + ESRCH → STALE)
    stale_pid = 88887
    lock_dir = project_root / "cortex" / "lifecycle" / "stale-feature"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "interactive.pid"
    stale_payload = {
        "schema_version": 1,
        "magic": "cortex-interactive-lock",
        "session_id": "old-dead-session",
        "pid": stale_pid,
        "start_time": 99999.0,
        "acquired_at": "2024-01-01T00:00:00+00:00",
    }
    lock_path.write_text(json.dumps(stale_payload))

    # Force ESRCH for the stale PID so verify_live_owner returns STALE
    def _kill_esrch(pid: int, sig: int) -> None:
        raise OSError(errno.ESRCH, "No such process")

    monkeypatch.setattr(os, "kill", _kill_esrch)

    # Track all subprocess.run invocations
    recorded_calls: list[Any] = []

    def _fake_subprocess_run(args: Any, **kwargs: Any) -> Any:
        recorded_calls.append(args)
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr(subprocess, "run", _fake_subprocess_run)

    # Trigger stale recovery by acquiring with a new session
    result = il.acquire_lock("stale-feature")

    # Acquisition should succeed (stale lock was recovered)
    assert result is True, "Expected acquire to succeed after stale recovery"

    # Assert no destructive git commands were invoked
    destructive_patterns = [
        ("git", "merge", "--abort"),
        ("git", "worktree", "remove"),
    ]

    for call_args in recorded_calls:
        if not isinstance(call_args, (list, tuple)):
            continue
        call_tuple = tuple(str(a) for a in call_args)
        for pattern in destructive_patterns:
            if all(tok in call_tuple for tok in pattern):
                pytest.fail(
                    f"Stale recovery invoked destructive subprocess call: {call_args!r}. "
                    f"Matched pattern: {pattern}"
                )

    # Verify the stale-recovery event was emitted with a recovery_reason
    events_log = lock_dir / "events.log"
    assert events_log.exists(), f"events.log not created at {events_log}"

    recovery_events = []
    for line in events_log.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "interactive_lock_stale_recovered":
            recovery_events.append(row)

    assert len(recovery_events) >= 1, "Expected at least one interactive_lock_stale_recovered event"
    recovery_event = recovery_events[0]
    assert "recovery_reason" in recovery_event, (
        f"recovery_reason field missing from stale recovery event: {recovery_event}"
    )
    valid_reasons = {"esrch", "start_time_mismatch", "nosuchprocess"}
    assert recovery_event["recovery_reason"] in valid_reasons, (
        f"recovery_reason {recovery_event['recovery_reason']!r} not in {valid_reasons}"
    )
