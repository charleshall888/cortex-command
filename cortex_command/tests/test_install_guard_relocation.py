"""Regression tests for the install_guard relocation (Spec R6, ticket 151).

Asserts the post-relocation contract:

* ``import cortex_command`` does NOT fire the guard, even when an
  active overnight session pointer is present.
* ``cortex_command.cli.main(["upgrade"])`` DOES fire the guard, since
  the call now lives inside ``_dispatch_upgrade``.
* ``cortex_command.cli.main(["overnight", "status"])`` does NOT fire
  the guard — the latent-bug fix that was previously masked by the
  package-import-time call.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import psutil
import pytest

from cortex_command import install_guard
from cortex_command.install_guard import InstallInFlightError
from cortex_command.overnight import ipc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _live_start_time_iso() -> str:
    return datetime.fromtimestamp(
        psutil.Process(os.getpid()).create_time(), tz=timezone.utc
    ).isoformat()


def _setup_live_inflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_id: str = "session-relocation-test",
) -> Path:
    """Stage a live in-flight pointer pointing at THIS process pid.

    Both ``ipc.ACTIVE_SESSION_PATH`` and
    ``install_guard._ACTIVE_SESSION_PATH`` are redirected into ``tmp_path``
    so the guard reads from the staged fixture instead of the real
    user-home location.
    """
    fake_active = (
        tmp_path
        / ".local"
        / "share"
        / "overnight-sessions"
        / "active-session.json"
    )
    fake_active.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", fake_active)
    monkeypatch.setattr(install_guard, "_ACTIVE_SESSION_PATH", fake_active)

    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    start_time = _live_start_time_iso()
    pid = os.getpid()

    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": pid,
        "start_time": start_time,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(session_dir),
        "phase": "executing",
    }
    fake_active.write_text(json.dumps(payload), encoding="utf-8")
    (session_dir / "runner.pid").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
            }
        ),
        encoding="utf-8",
    )
    return session_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_import_does_not_fire_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``import cortex_command`` must succeed even with a live pointer.

    Pre-relocation, ``cortex_command/__init__.py`` called the guard
    unconditionally — only the carve-outs prevented misfiring during
    pytest collection. Post-relocation, the call is gone from the
    package init, so a clean import always succeeds.
    """
    _setup_live_inflight(tmp_path, monkeypatch)

    # Force a fresh import so the test exercises the package init path.
    for mod in list(sys.modules):
        if mod == "cortex_command" or mod.startswith("cortex_command."):
            # Don't actually evict; we just want to verify the
            # invariant by re-running __init__ logic. Instead, scan
            # cortex_command/__init__.py for a check_in_flight_install
            # call site; if absent, the import-time-fire is structurally
            # impossible.
            pass

    init_path = Path(__import__("cortex_command").__file__)
    init_text = init_path.read_text(encoding="utf-8")
    assert "check_in_flight_install" not in init_text, (
        "cortex_command/__init__.py still references check_in_flight_install — "
        "the guard call must live in _dispatch_upgrade, not at package import."
    )


def test_upgrade_fires_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cortex upgrade`` must fire the guard on a live in-flight pointer.

    The call to ``check_in_flight_install`` now lives inside
    ``_dispatch_upgrade``; verify it raises ``InstallInFlightError``
    before any subprocess work runs.
    """
    _setup_live_inflight(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    from cortex_command import cli

    # Stub subprocess.run so even if the guard fails to fire, the test
    # does not trigger a real `git pull` / `uv tool install --force`.
    with patch("subprocess.run") as mock_run:
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["upgrade"])
        assert excinfo.value.code == 1
        # Guard should fire BEFORE any subprocess call.
        assert mock_run.call_count == 0, (
            "guard did not fire — subprocess.run was called "
            f"{mock_run.call_count} times before guard could abort"
        )


def test_overnight_status_does_not_fire_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cortex overnight status`` must NOT fire the guard (latent-bug fix).

    Pre-relocation, importing ``cortex_command`` fired the guard via
    ``__init__.py``. The pytest carve-out hid this from the test suite,
    but a real ``cortex overnight status`` invocation under an active
    session would abort with ``InstallInFlightError`` — even though
    status is read-only and never mutates the install. Post-relocation,
    only ``_dispatch_upgrade`` calls the guard, so other subcommands
    are unaffected.
    """
    _setup_live_inflight(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cortex", "overnight", "status"])

    from cortex_command import cli

    # Stub the dispatch handler so the test doesn't actually probe a
    # session — we only care that the guard does NOT fire.
    def _stub_status(_args):
        return 0

    with patch.object(cli, "_dispatch_overnight_status", _stub_status):
        # Must not raise InstallInFlightError.
        rc = cli.main(["overnight", "status"])
        assert rc == 0, f"expected status to succeed, got rc={rc!r}"
