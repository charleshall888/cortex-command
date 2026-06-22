"""CLI integration test for ``cortex overnight recover`` (spec §R7, Task 8).

``cortex overnight recover [--session <id>]`` is the operator-facing manual
trigger for the out-of-process recovery core. It is writer-authorized and is
deliberately NOT folded into the read-only ``cortex overnight status`` verb
(``observability.md:93/99``): recovery writes originate only from this verb
and the host-level guardian.

The verb resolves the target session (explicit ``--session <id>``, else the
active-session pointer that ``status`` reads), invokes
:func:`cortex_command.overnight.recovery.recover_session` with
``trigger="manual"``, and reports cleanly when there is nothing to recover
(self-heal / no-op → exit 0, never an error).

These tests synthesize a stuck-``executing`` + dead-pid session dir on disk
(mirroring ``tests/test_recovery_core.py`` / ``tests/test_recovery_predicate.py``)
and assert:

  * ``--session`` against a stuck fixture transitions the session to
    ``paused`` (state read), exit 0;
  * the default (no ``--session``) path resolves through the active-session
    pointer and recovers the same way;
  * a missing/absent target self-heals to a "nothing to recover" exit 0;
  * an invalid session-id is rejected (exit 1).

The orphan reaper (:func:`recovery.reap_session_orphans`) is monkeypatched so
no real processes are touched, and ``SKIP_NOTIFICATIONS=1`` short-circuits the
report path's notify hook (which blocks on non-tty stdin).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command import cli
from cortex_command.overnight import ipc, recovery
from cortex_command.overnight.recovery import ReapOutcome
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)

SESSION_ID = "overnight-2026-05-01-cli-recover"


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running."""
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _dead_pid_payload(pid: int) -> dict:
    """Return a well-formed ``runner.pid`` payload whose process is gone."""
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "session_id": SESSION_ID,
    }


def _synthesize_stuck_session(root: Path) -> Path:
    """Build a stuck-``executing`` + dead-pid session dir under ``root``.

    Lays out ``{root}/cortex/lifecycle/sessions/{SESSION_ID}/`` with an
    ``overnight-state.json`` at ``phase == "executing"`` (one non-terminal
    feature) and a ``runner.pid`` whose recorded process is dead. Returns the
    session dir.
    """
    session_dir = root / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")

    (session_dir / "runner.pid").write_text(json.dumps(_dead_pid_payload(_dead_pid())))
    return session_dir


def _patch_environment(tmp_path: Path, monkeypatch) -> None:
    """Pin repo-root resolution + suppress the notify hook + stub the reaper."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    # report.notify() shells out to a notify hook that blocks on `cat` when
    # stdin is non-tty; SKIP_NOTIFICATIONS=1 short-circuits it.
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    # The recovery core resolves the repo via _resolve_repo_path() (git
    # rev-parse, falling back to cwd); pin it to the synthesized tree so the
    # --session lookup stays inside the fixture.
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler._resolve_repo_path",
        lambda *a, **k: tmp_path,
    )
    # Reaper must not touch real processes.
    monkeypatch.setattr(
        recovery,
        "reap_session_orphans",
        lambda *a, **k: ReapOutcome(matched=[111], terminated=[111]),
    )
    # Redirect the active-session pointer (a module-level constant under
    # ~/.local/share, outside the test sandbox) into the tmp tree so any
    # update_active_session_phase write lands somewhere writable and never
    # clobbers a real operator pointer.
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", tmp_path / "active-session.json")


def test_recover_with_session_flag_transitions_to_paused(tmp_path, monkeypatch):
    """``cortex overnight recover --session <id>`` recovers a stuck session.

    Spec §R7 acceptance: running it against a synthesized stuck-``executing``
    + dead-pid fixture transitions it to ``paused`` (assert via state read),
    exit 0.
    """
    _patch_environment(tmp_path, monkeypatch)
    session_dir = _synthesize_stuck_session(tmp_path)

    args = argparse.Namespace(session=SESSION_ID)
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 0

    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"
    assert not (session_dir / "runner.pid").exists()


def test_recover_default_resolves_active_session_pointer(tmp_path, monkeypatch):
    """The default (no ``--session``) path resolves via the active-session
    pointer — the same source ``status`` reads — and recovers."""
    _patch_environment(tmp_path, monkeypatch)
    session_dir = _synthesize_stuck_session(tmp_path)

    # Write a pointer at the synthesized session dir — the same source
    # ``status`` reads. ``_patch_environment`` already redirected
    # ACTIVE_SESSION_PATH into the tmp tree.
    ipc.ACTIVE_SESSION_PATH.write_text(
        json.dumps(
            {
                "session_id": SESSION_ID,
                "session_dir": str(session_dir),
                "phase": "executing",
            }
        )
    )

    args = argparse.Namespace(session=None)
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 0
    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"


def test_recover_no_active_session_is_clean_noop(tmp_path, monkeypatch):
    """With no active-session pointer, the verb self-heals to exit 0."""
    _patch_environment(tmp_path, monkeypatch)
    monkeypatch.setattr(ipc, "read_active_session", lambda: None)

    args = argparse.Namespace(session=None)
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 0


def test_recover_unknown_session_is_clean_noop(tmp_path, monkeypatch):
    """``--session`` naming a non-existent session is a clean no-op (exit 0)."""
    _patch_environment(tmp_path, monkeypatch)
    # Create the sessions root so containment resolution succeeds, but no
    # session dir for the requested id.
    (tmp_path / "cortex" / "lifecycle" / "sessions").mkdir(parents=True)

    args = argparse.Namespace(session="overnight-2026-01-01-does-not-exist")
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 0


def test_recover_invalid_session_id_is_rejected(tmp_path, monkeypatch):
    """An attacker-controlled / malformed session-id is rejected (exit 1)."""
    _patch_environment(tmp_path, monkeypatch)

    args = argparse.Namespace(session="../../../etc")
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 1


def test_recover_already_paused_is_clean_noop(tmp_path, monkeypatch):
    """Recovering an already-paused session is a no-op exit 0 (idempotent)."""
    _patch_environment(tmp_path, monkeypatch)
    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="paused",
    )
    save_state(state, session_dir / "overnight-state.json")

    args = argparse.Namespace(session=SESSION_ID)
    rc = cli._dispatch_overnight_recover(args)

    assert rc == 0
    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
