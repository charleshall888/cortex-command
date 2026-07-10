"""Environment-fixture guard tests (arm f) for the interactive/overnight
concurrency guards.

Unlike ``test_prepare_worktree.py`` (which stubs every composed primitive on
the ``pw`` module namespace to drive the routing seam) and
``tests/test_interactive_lock.py`` (which drives the R4 liveness predicate over
in-memory lock dicts), these tests stage **real on-disk fixtures** under
``tmp_path`` and drive the real ``acquire_lock()`` / ``prepare_worktree()``
composition against them. Only the liveness seam is monkeypatched
(``os.kill`` / ``psutil.Process``); the composed primitives themselves
(``read_lock``, ``read_active_session``, ``read_runner_pid``,
``_verify_live_owner_with_reason``, ``_check_overnight_guard``) run for real.

Adversarial caution (research §Guard-verb fixtures): full end-to-end process
fixtures against real ``os.kill``/psutil risk pid-reuse races and sandbox
flakiness. So the fixtures are on-disk ``interactive.pid`` / ``runner.pid`` /
session-pointer files, but process *liveness* is decided by a seam-level
monkeypatch of ``os.kill`` / ``psutil.Process`` (except where the genuinely
live current process, ``os.getpid()``, is the safe deterministic choice — it
has no pid-reuse race).

The on-disk schemas are read from the modules under test, not invented:
  - ``interactive.pid`` schema: ``cortex_command.interactive_lock`` docstring
  - ``runner.pid`` schema:      ``cortex_command.overnight.ipc.write_runner_pid``
  - active-session pointer:     ``cortex_command.overnight.ipc.write_active_session``

NOTE ON A SEAM PATCH BEYOND os.kill/psutil: the overnight session pointer is
read from the hard-coded home-dir global ``ipc.ACTIVE_SESSION_PATH`` (there is
no env override), so the overnight tests ``monkeypatch.setattr`` that global to
point at a real ``tmp_path`` fixture file. This is a filesystem *path redirect*
that stages a real on-disk fixture — the real ``read_active_session`` still
runs and parses real JSON; no guard logic is stubbed.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import psutil
import pytest

import cortex_command.interactive_lock as il
from cortex_command.lifecycle import prepare_worktree as pw
from cortex_command.overnight import ipc


# ---------------------------------------------------------------------------
# On-disk fixture builders (real schemas, read from the modules under test)
# ---------------------------------------------------------------------------


def _scaffold(tmp_path: Path) -> Path:
    """Create the ``cortex/`` umbrella under tmp_path and return the repo root."""
    (tmp_path / "cortex").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _stage_interactive_pid(
    repo_root: Path,
    slug: str,
    *,
    session_id: str | None,
    pid: int,
    start_time: float | None,
    acquired_at: str = "2024-01-01T00:00:00+00:00",
) -> Path:
    """Write a real ``cortex/lifecycle/{slug}/interactive.pid`` fixture.

    Schema mirrors ``interactive_lock``'s docstring exactly.
    """
    lock_dir = repo_root / "cortex" / "lifecycle" / slug
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "interactive.pid"
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-interactive-lock",
                "session_id": session_id,
                "pid": pid,
                "start_time": start_time,
                "acquired_at": acquired_at,
            }
        ),
        encoding="utf-8",
    )
    return lock_path


def _stage_runner_pid(session_dir: Path, *, pid: int) -> Path:
    """Write a real ``runner.pid`` fixture (cortex-runner-v1 schema)."""
    session_dir.mkdir(parents=True, exist_ok=True)
    runner_path = session_dir / "runner.pid"
    runner_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": "2026-01-01T00:00:00+00:00",
                "session_id": "overnight-sess",
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
            }
        ),
        encoding="utf-8",
    )
    return runner_path


def _stage_active_session_pointer(
    pointer_path: Path,
    *,
    repo_path: Path,
    session_dir: Path,
) -> None:
    """Write a real active-session.json pointer (R9 shape) at *pointer_path*."""
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "session_id": "overnight-sess",
                "session_dir": str(session_dir),
                "repo_path": str(repo_path),
                "phase": "implement",
            }
        ),
        encoding="utf-8",
    )


def _read_events(repo_root: Path, slug: str) -> list[dict]:
    """Return the parsed JSON event rows for a feature slug's events.log."""
    events_log = repo_root / "cortex" / "lifecycle" / slug / "events.log"
    if not events_log.exists():
        return []
    rows: list[dict] = []
    for line in events_log.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# ===========================================================================
# interactive.pid variants — drive the REAL acquire_lock() against on-disk
# fixtures, monkeypatching only the liveness seam.
# ===========================================================================


def test_acquire_live_owned_by_self_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variant: live-owned-by-self. The staged lock's ``session_id`` matches
    ``CLAUDE_CODE_SESSION_ID`` (R4 Row 1, authoritative LIVE — no os.kill even
    consulted), so a fresh acquire is rejected and the file is left untouched.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-self")

    lock_path = _stage_interactive_pid(
        root, "feat", session_id="sess-self", pid=4242, start_time=None
    )
    original = lock_path.read_text(encoding="utf-8")

    # os.kill must never be consulted on Row 1; make it explode if it is.
    monkeypatch.setattr(
        os, "kill", lambda *a, **k: pytest.fail("os.kill consulted on Row 1")
    )

    assert il.acquire_lock("feat") is False
    # The live owner's lock file is left byte-for-byte untouched.
    assert lock_path.read_text(encoding="utf-8") == original

    events = _read_events(root, "feat")
    assert any(
        e.get("event") == "interactive_lock_rejected_concurrent" for e in events
    ), f"expected a rejection event, got {events}"


def test_acquire_live_owned_by_other_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variant: live-owned-by-other. No session-id match; ``os.kill`` succeeds
    and the stored ``start_time`` is null (R4 Row 4, conservative LIVE), so a
    co-passer's live lock blocks acquisition and is not clobbered.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    lock_path = _stage_interactive_pid(
        root, "feat", session_id="sess-other", pid=4242, start_time=None
    )
    original = lock_path.read_text(encoding="utf-8")

    # Seam: os.kill succeeds → process judged running.
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    assert il.acquire_lock("feat") is False
    assert lock_path.read_text(encoding="utf-8") == original

    events = _read_events(root, "feat")
    assert any(
        e.get("event") == "interactive_lock_rejected_concurrent" for e in events
    )


def test_acquire_stale_esrch_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variant: stale-ESRCH. No session-id match; ``os.kill`` raises ESRCH
    (R4 Row 2, STALE/esrch). The real ``acquire_lock`` recovers: emits
    ``interactive_lock_stale_recovered`` (reason ``esrch``), unlinks the stale
    file, and writes a fresh lock owned by the new session.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-new")

    lock_path = _stage_interactive_pid(
        root, "feat", session_id="sess-old", pid=88887, start_time=99999.0
    )

    def _kill_esrch(pid: int, sig: int) -> None:
        raise OSError(errno.ESRCH, "No such process")

    monkeypatch.setattr(os, "kill", _kill_esrch)

    assert il.acquire_lock("feat") is True

    events = _read_events(root, "feat")
    recovered = [
        e for e in events if e.get("event") == "interactive_lock_stale_recovered"
    ]
    assert len(recovered) == 1, f"expected one recovery event, got {events}"
    assert recovered[0]["recovery_reason"] == "esrch"

    # The fresh lock is now owned by the recovering session.
    fresh = json.loads(lock_path.read_text(encoding="utf-8"))
    assert fresh["session_id"] == "sess-new"
    assert fresh["magic"] == "cortex-interactive-lock"


def test_acquire_stale_start_time_mismatch_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variant: start-time-mismatch. No session-id match; ``os.kill`` succeeds
    but the psutil ``create_time`` is far outside the ±2s window (R4 Row 6,
    STALE/start_time_mismatch). The real ``acquire_lock`` recovers.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    stored_start = 10000.0
    lock_path = _stage_interactive_pid(
        root, "feat", session_id="sess-old", pid=88887, start_time=stored_start
    )

    monkeypatch.setattr(os, "kill", lambda pid, sig: None)

    # Seam: psutil reports a create_time well outside ±2s of the stored value.
    # This same fake also serves the fresh-write start_time probe on recovery.
    class _FakeProc:
        def create_time(self) -> float:
            return stored_start + 500.0

    monkeypatch.setattr(psutil, "Process", lambda pid: _FakeProc())

    assert il.acquire_lock("feat") is True

    events = _read_events(root, "feat")
    recovered = [
        e for e in events if e.get("event") == "interactive_lock_stale_recovered"
    ]
    assert len(recovered) == 1, f"expected one recovery event, got {events}"
    assert recovered[0]["recovery_reason"] == "start_time_mismatch"
    # Stale file was replaced with a fresh acquisition.
    assert json.loads(lock_path.read_text(encoding="utf-8"))["session_id"] is None


def test_prepare_worktree_lock_held_against_live_pid_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: ``prepare_worktree`` driven against a real, live (self-owned)
    ``interactive.pid`` reaches the ``lock-held`` state — proving the composed
    verb's lock-acquire branch classifies a real on-disk live lock without any
    primitive stubbing. ``base_branch`` is passed so git auto-detection is
    skipped and no real worktree is created.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-self")
    # No overnight session pointer staged → guard is clear.
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", tmp_path / "no-such-session.json")

    _stage_interactive_pid(
        root, "feat", session_id="sess-self", pid=4242, start_time=None
    )

    result = pw.prepare_worktree("feat", project_root=root, base_branch="main")

    assert result["state"] == "lock-held"
    assert "sess-self" in result["message"]
    assert "already active on this feature" in result["message"]


# ===========================================================================
# overnight runner.pid / session-pointer pair — drive the REAL
# prepare_worktree() overnight guard against on-disk fixtures.
# ===========================================================================


def test_prepare_worktree_overnight_active_against_live_runner_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real active-session pointer + a real ``runner.pid`` whose pid is the
    genuinely-live current process → ``overnight-active`` rejection, reached
    before any lock or worktree work. Uses ``os.getpid()`` (no pid-reuse race)
    as the safe live pid rather than a patched ``os.kill``.
    """
    root = _scaffold(tmp_path)
    session_dir = tmp_path / "session"
    pointer = tmp_path / "active-session.json"

    _stage_runner_pid(session_dir, pid=os.getpid())
    _stage_active_session_pointer(pointer, repo_path=root, session_dir=session_dir)
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", pointer)

    result = pw.prepare_worktree("feat", project_root=root, base_branch="main")

    assert result["state"] == "overnight-active"
    assert "wait for it to complete" in result["message"]


def test_prepare_worktree_stale_runner_pid_absent_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real session pointer present but its ``runner.pid`` absent (the stale
    pair) must NOT reject as ``overnight-active`` — the guard warns-and-continues
    into the lock path. We stage a live self-owned interactive lock so the
    continuation lands deterministically on ``lock-held`` (never touching
    ``create_worktree``), proving the guard did not fail closed on a stale pair.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-self")

    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)  # present, but NO runner.pid
    pointer = tmp_path / "active-session.json"
    _stage_active_session_pointer(pointer, repo_path=root, session_dir=session_dir)
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", pointer)

    _stage_interactive_pid(
        root, "feat", session_id="sess-self", pid=4242, start_time=None
    )

    result = pw.prepare_worktree("feat", project_root=root, base_branch="main")

    # Not rejected as overnight-active → guard continued past the stale pair.
    assert result["state"] == "lock-held"
    assert "sess-self" in result["message"]


def test_prepare_worktree_dead_runner_pid_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real session pointer + a real ``runner.pid`` whose recorded process is
    dead (``os.kill`` → ESRCH via the liveness seam) is a stale pair — the guard
    warns-and-continues rather than rejecting. As above we pin the continuation
    on a live self-owned interactive lock (``lock-held``), avoiding
    ``create_worktree``.
    """
    root = _scaffold(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-self")

    session_dir = tmp_path / "session"
    pointer = tmp_path / "active-session.json"
    _stage_runner_pid(session_dir, pid=88887)
    _stage_active_session_pointer(pointer, repo_path=root, session_dir=session_dir)
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", pointer)

    _stage_interactive_pid(
        root, "feat", session_id="sess-self", pid=4242, start_time=None
    )

    # Seam: the recorded runner pid is dead. (The self-owned interactive lock
    # matches on session-id at R4 Row 1, so os.kill is only ever consulted for
    # the overnight runner pid here.)
    def _kill_esrch(pid: int, sig: int) -> None:
        raise OSError(errno.ESRCH, "No such process")

    monkeypatch.setattr(os, "kill", _kill_esrch)

    result = pw.prepare_worktree("feat", project_root=root, base_branch="main")

    assert result["state"] == "lock-held"
    assert "sess-self" in result["message"]
