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


# ---------------------------------------------------------------------------
# _resolve_main_repo_root — lock-scoped main-repo resolver (#271)
#
# All fixtures are HAND-BUILT (no `git worktree add`) to avoid the
# editable-`.pth` rewrite hazard.  The skeleton mirrors a real
# `git worktree add` pointer shape: the worktree's `.git` is a *file*
# (`gitdir: <main>/.git/worktrees/<id>`) and `<id>` carries a `commondir`
# file holding the RELATIVE `../..` pointer git actually emits.
# ---------------------------------------------------------------------------


def _build_worktree_skeleton(tmp_path: Path, *, with_worktree_cortex: bool) -> dict:
    """Hand-build a main repo + linked worktree (no ``git worktree add``).

    Layout::

        <main>/.git/                              (dir)
        <main>/.git/HEAD
        <main>/cortex/                            (dir)
        <main>/.git/worktrees/wt-id/commondir     -> "../.." (relative, real shape)
        <wt>/.git                                 (file) -> "gitdir: <main>/.git/worktrees/wt-id"
        <wt>/cortex/                              (dir, optional collision)

    Returns the key paths so callers can mutate the fixture for variants.
    """
    main = tmp_path / "main"
    main_git = main / ".git"
    wt_admin = main_git / "worktrees" / "wt-id"
    wt_admin.mkdir(parents=True)
    (main_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (main / "cortex").mkdir()
    # Real git emits a RELATIVE commondir pointer (../..), not an absolute path.
    (wt_admin / "commondir").write_text("../..\n", encoding="utf-8")
    wt = tmp_path / "worktree" / "probe"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {wt_admin}\n", encoding="utf-8")
    if with_worktree_cortex:
        (wt / "cortex").mkdir()
    return {"main": main, "main_git": main_git, "wt_admin": wt_admin, "wt": wt}


def test_resolve_main_repo_root_worktree_with_cortex_resolves_to_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 7 structural guard: a worktree carrying its OWN co-located cortex/
    (the production bug's exact shape) must still resolve to the MAIN repo,
    and the lock's writer and reader both converge on the main-repo path.

    Fails against any walk-first implementation (which returns the worktree)
    and against a future revert of the _lock_path/_events_log_path wiring.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    fx = _build_worktree_skeleton(tmp_path, with_worktree_cortex=True)
    main, wt = fx["main"], fx["wt"]
    monkeypatch.chdir(wt)

    # (1) Resolver returns MAIN, not the co-located worktree root.
    assert il._resolve_main_repo_root() == main.resolve()

    # (2) _lock_path lands under <main>/cortex/lifecycle/probe/interactive.pid.
    expected_lock = (
        main.resolve() / "cortex" / "lifecycle" / "probe" / "interactive.pid"
    )
    assert il._lock_path("probe") == expected_lock

    # (3) Writer/reader convergence from the worktree CWD — the production bug:
    #     acquire writes to <main>, and read_lock from the SAME worktree CWD
    #     reads it back (NOT None).  This directly exercises complete.md Step 3's
    #     read_lock-from-worktree Variant-A detection path.
    assert il.acquire_lock("probe") is True
    assert expected_lock.exists()
    lock = il.read_lock("probe")
    assert lock is not None
    assert lock.get("magic") == "cortex-interactive-lock"


def test_resolve_main_repo_root_env_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5: CORTEX_REPO_ROOT short-circuits before any .git parse, even from
    a worktree CWD (no regression to the overnight env-pin)."""
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    fx = _build_worktree_skeleton(tmp_path, with_worktree_cortex=True)
    monkeypatch.chdir(fx["wt"])
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    # Prove the .git parse path is never reached when the env var is set.
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("env-first short-circuit failed: .git was parsed")

    monkeypatch.setattr(il, "_main_root_from_gitfile", _boom)

    assert il._resolve_main_repo_root() == tmp_path.resolve()


def test_resolve_main_repo_root_no_git_cortex_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6: a non-git cortex/ project (no .git anywhere, no env var) resolves
    via the step-(c) fallback rather than raising."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    proj = tmp_path / "proj"
    (proj / "cortex").mkdir(parents=True)
    monkeypatch.chdir(proj)

    assert il._resolve_main_repo_root() == proj.resolve()


def test_resolve_main_repo_root_synthetic_direct_gitdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 8a: synthetic direct ``gitdir: <main>/.git`` (no commondir, no
    worktree-local cortex/) → <main>.  Matches the existing CI fixture shape."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    (main / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (main / "cortex").mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git'}\n", encoding="utf-8")
    monkeypatch.chdir(wt)

    assert il._resolve_main_repo_root() == main.resolve()


def test_resolve_main_repo_root_malformed_gitdir_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 8e: a malformed/empty ``gitdir:`` line falls back via step (c) to a
    reachable cortex/ ancestor — no raise, no non-cortex path returned."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    fx = _build_worktree_skeleton(tmp_path, with_worktree_cortex=True)
    wt = fx["wt"]
    # Overwrite the .git file with an empty gitdir target (malformed).
    (wt / ".git").write_text("gitdir:\n", encoding="utf-8")
    monkeypatch.chdir(wt)

    result = il._resolve_main_repo_root()
    # (b) parse returns None → (b-guard) fails → (c) finds the worktree's cortex/.
    assert result == wt.resolve()
    assert (result / "cortex").is_dir()


def test_resolve_main_repo_root_worktree_pointer_no_cortex_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 8e: a well-formed worktree pointer whose resolved main root has NO
    cortex/, and no cortex/ ancestor anywhere → (b-guard) fails and step (c)
    raises CortexProjectRootError (never returns a non-cortex path)."""
    from cortex_command.common import CortexProjectRootError

    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    main = tmp_path / "main"
    main_git = main / ".git"
    wt_admin = main_git / "worktrees" / "wt-id"
    wt_admin.mkdir(parents=True)
    (main_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (wt_admin / "commondir").write_text("../..\n", encoding="utf-8")
    # NO <main>/cortex and NO worktree cortex — nothing cortex-bearing anywhere.
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wt_admin}\n", encoding="utf-8")
    monkeypatch.chdir(wt)

    with pytest.raises(CortexProjectRootError):
        il._resolve_main_repo_root()


def test_resolve_main_repo_root_bfail_inside_worktree_degrades_to_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documented limitation (critical-review Objection 1): a (b)-failure from
    INSIDE a worktree that carries its own cortex/ degrades to worktree-local
    resolution (pre-fix behavior) — unreachable for well-formed
    ``git worktree add`` output, but pinned here so it cannot change silently.

    The pointer is well-formed but its resolved main root has no cortex/, so
    the (b-guard) fails; the worktree's own cortex/ then wins via step (c)."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    main = tmp_path / "main"
    main_git = main / ".git"
    wt_admin = main_git / "worktrees" / "wt-id"
    wt_admin.mkdir(parents=True)
    (main_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (wt_admin / "commondir").write_text("../..\n", encoding="utf-8")
    # NO <main>/cortex → the parsed candidate fails the (b-guard).
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {wt_admin}\n", encoding="utf-8")
    (wt / "cortex").mkdir()  # the worktree's OWN cortex/ (the collision)
    monkeypatch.chdir(wt)

    # (b-guard) fails on the no-cortex main → step (c) returns the worktree root.
    assert il._resolve_main_repo_root() == wt.resolve()


# ---------------------------------------------------------------------------
# release_lock_if_owner — owner-checked release for the §1a.iii abort
# ---------------------------------------------------------------------------


def test_release_if_owner_unlinks_when_session_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner match (lock session_id == CLAUDE_CODE_SESSION_ID) → unlink + True."""
    project_root = _setup_repo_root(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "owner-session")

    lock_dir = project_root / "cortex" / "lifecycle" / "feat"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "interactive.pid"
    lock_path.write_text(json.dumps(_make_lock(session_id="owner-session")))

    result = il.release_lock_if_owner("feat")

    assert result is True
    assert not lock_path.exists()


def test_release_if_owner_leaves_lock_when_session_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Session mismatch (a co-passer's live lock) → leave the file, return False."""
    project_root = _setup_repo_root(tmp_path)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project_root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "loser-session")

    lock_dir = project_root / "cortex" / "lifecycle" / "feat"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "interactive.pid"
    lock_path.write_text(json.dumps(_make_lock(session_id="winner-session")))

    result = il.release_lock_if_owner("feat")

    assert result is False
    assert lock_path.exists(), "must not delete a co-passer's live lock"
