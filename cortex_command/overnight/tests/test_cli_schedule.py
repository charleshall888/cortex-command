"""Smoke tests for ``cortex overnight schedule`` (Task 5).

Covers the three high-value branches of :func:`handle_schedule`:

  - ``--dry-run`` exits 0 and prints session_id / label / scheduled_for_iso
    (human format) or a versioned envelope (json format).
  - Non-darwin platforms exit non-zero with the spec-exact macOS-only
    error message.
  - Invalid target-time inputs exit non-zero with the spec-mandated
    error phrasings (Feb-29 in non-leap year, in-the-past, malformed).

The tests construct a synthetic session directory under ``tmp_path`` and
monkeypatch :func:`cli_handler._resolve_repo_path` so the auto-discover
path locates the synthesized state file. The real macOS backend's
``schedule()`` is never invoked — dry-run and platform-gate cases both
short-circuit before reaching it, and the test suite must remain
hermetic regardless of host platform.
"""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler.dispatch import _UnsupportedScheduler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state_file(session_dir: Path, session_id: str) -> Path:
    """Create a minimal valid overnight-state.json under ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    state_payload = {
        "session_id": session_id,
        "plan_ref": "cortex/lifecycle/test/plan.md",
        "current_round": 1,
        "phase": "planning",
        "features": {},
        "round_history": [],
        "started_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:00:00",
        "schema_version": 1,
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def _future_hhmm(minutes_from_now: int = 60) -> str:
    """Return an HH:MM string in the future, well within the 7-day horizon.

    Defaults to one hour from now so the test is robust against
    cross-midnight drift if invoked at 23:59:59.
    """
    target = datetime.now() + timedelta(minutes=minutes_from_now)
    return target.strftime("%H:%M")


def _make_args(
    *,
    target_time: str,
    state: str | None = None,
    dry_run: bool = False,
    fmt: str = "human",
) -> argparse.Namespace:
    """Build an argparse.Namespace shaped like the schedule subparser produces."""
    return argparse.Namespace(
        target_time=target_time,
        state=state,
        dry_run=dry_run,
        format=fmt,
    )


# ---------------------------------------------------------------------------
# (a) --dry-run smoke
# ---------------------------------------------------------------------------


def test_schedule_dry_run_human_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--dry-run`` succeeds and prints session_id/label/target ISO."""
    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=True,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r} stdout={captured.out!r}"
    assert f"session_id: {session_id}" in captured.out
    assert "label:" in captured.out
    assert "scheduled_for_iso:" in captured.out
    assert "dry-run" in captured.out


def test_schedule_dry_run_json_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--dry-run --format json`` emits a versioned JSON envelope."""
    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=True,
        fmt="json",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert payload["schema_version"] == "2.0"
    assert payload["dry_run"] is True
    assert payload["session_id"] == session_id
    assert payload["label"].startswith(
        "com.charleshall.cortex-command.overnight-schedule."
    )
    assert payload["scheduled_for_iso"]


# ---------------------------------------------------------------------------
# (b) macOS-only gate
# ---------------------------------------------------------------------------


def test_schedule_non_darwin_exits_with_macos_only_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Non-macOS platforms get the spec-exact error message and non-zero exit."""
    session_id = "overnight-2026-05-04-0100"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    # Force the dispatch.get_backend() call inside handle_schedule to
    # return the unsupported stub regardless of host platform.
    from cortex_command.overnight import scheduler as _scheduler_pkg

    monkeypatch.setattr(
        _scheduler_pkg,
        "get_backend",
        lambda: _UnsupportedScheduler(),
    )

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=False,  # platform gate fires before dry-run short-circuit
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "cortex overnight scheduling requires macOS" in captured.err


# ---------------------------------------------------------------------------
# (c) invalid target time
# ---------------------------------------------------------------------------


def test_schedule_feb_29_in_non_leap_year_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Feb 29 in a non-leap year exits non-zero with the spec phrasing."""
    session_id = "overnight-2026-05-04-0200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    args = _make_args(
        target_time="2026-02-29T23:00",
        state=str(state_path),
        dry_run=True,  # would otherwise short-circuit, but validation runs first
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "Feb 29 not in 2026" in captured.err


def test_schedule_malformed_target_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Unparseable target time exits non-zero before any backend work."""
    session_id = "overnight-2026-05-04-0300"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)

    args = _make_args(
        target_time="not-a-time",
        state=str(state_path),
        dry_run=True,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "invalid format" in captured.err


# ---------------------------------------------------------------------------
# (d) advisory liveness probe — bookkeeping completes (Task 8 / R10)
# ---------------------------------------------------------------------------


def _make_completed(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Minimal stand-in for ``subprocess.CompletedProcess`` shaped for the
    macos backend's ``returncode``/``stdout``/``stderr`` reads.
    """
    return SimpleNamespace(
        returncode=returncode, stdout=stdout, stderr=stderr
    )


def _install_inconclusive_probe_backend(
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
) -> "object":
    """Wire ``handle_schedule`` to a real macOS backend whose post-bootstrap
    liveness probe is inconclusive.

    Isolates the sidecar/lock (``HOME``) and plist dir (``TMPDIR``) under
    ``home`` and forces ``launchctl bootstrap`` to succeed while
    ``launchctl print`` never confirms the armed-state line within the
    verify budget — driving the advisory ``LaunchctlVerifyError`` path
    inside ``_bootstrap_and_verify`` (now caught by ``_mint_and_install``).
    Returns the backend instance so callers can inspect
    ``last_verify_inconclusive``.
    """
    from cortex_command.overnight import scheduler as _scheduler_pkg
    from cortex_command.overnight.scheduler import macos as _macos

    # Isolate sidecar + lock (Path.home()) and the plist dir ($TMPDIR).
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(home / "tmp"))
    (home / "tmp").mkdir(parents=True, exist_ok=True)

    backend = _macos.MacOSLaunchAgentBackend()
    # Force the macOS-only gate true on any host so handle_schedule reaches
    # the real schedule() body.
    monkeypatch.setattr(backend, "is_supported", lambda: True)
    monkeypatch.setattr(_scheduler_pkg, "get_backend", lambda: backend)

    def _fake_run(argv, *args, **kwargs):
        verb = argv[1] if len(argv) > 1 else ""
        if verb == "bootstrap":
            # Bootstrap succeeds — the job IS armed.
            return _make_completed(returncode=0)
        if verb == "print":
            # Probe is inconclusive: clean exit but no armed-state line and
            # no calendar block, so _print_confirms_armed() is False.
            return _make_completed(returncode=0, stdout=b"state = running\n")
        return _make_completed(returncode=0)

    # Collapse the verify poll: monotonic jumps past the deadline so the
    # loop raises LaunchctlVerifyError on the first failed probe.
    monotonic_values = iter([0.0, 5.0, 10.0])

    def _fake_monotonic() -> float:
        try:
            return next(monotonic_values)
        except StopIteration:
            return 999.0

    monkeypatch.setattr(_macos.subprocess, "run", _fake_run)
    monkeypatch.setattr(_macos.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(_macos.time, "monotonic", _fake_monotonic)

    return backend


def test_schedule_inconclusive_probe_completes_bookkeeping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An inconclusive liveness probe is advisory: bookkeeping completes.

    Drives the real ``schedule()`` body with ``launchctl bootstrap``
    succeeding but ``launchctl print`` never confirming the armed-state
    line. Asserts (R10) that:

      - ``handle_schedule`` returns exit 0 (advisory, not fatal),
      - the ``scheduled_start`` state-file write completed (non-null),
      - a sidecar entry for the session exists,
      - the inconclusive probe surfaced as a non-fatal stderr warning.
    """
    from cortex_command.overnight import state as state_module
    from cortex_command.overnight.scheduler import sidecar as sidecar_module

    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda *a, **k: tmp_path)
    backend = _install_inconclusive_probe_backend(monkeypatch, tmp_path / "home")

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=False,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    # Exit 0 even though the probe was inconclusive.
    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"

    # The probe was recorded as inconclusive (advisory, not fatal).
    assert backend.last_verify_inconclusive is True
    assert "inconclusive" in captured.err

    # scheduled_start bookkeeping completed (cli_handler.py write).
    reloaded = state_module.load_state(state_path)
    assert reloaded.scheduled_start is not None

    # Sidecar bookkeeping completed (macos.py _write_sidecar_entry).
    entries = sidecar_module.read_sidecar()
    assert any(h.session_id == session_id for h in entries), (
        f"expected a sidecar entry for {session_id}; got {entries!r}"
    )


def test_schedule_inconclusive_probe_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``backend.schedule()`` itself does not raise on an inconclusive probe.

    Calls the backend directly (bypassing the CLI handler) to pin the
    contract that ``LaunchctlVerifyError`` no longer propagates out of
    ``schedule()`` — the sidecar entry lands and the advisory flag is set.
    """
    from cortex_command.overnight.scheduler import sidecar as sidecar_module

    session_id = "overnight-2026-05-04-2300"
    backend = _install_inconclusive_probe_backend(monkeypatch, tmp_path / "home2")

    target = datetime.now() + timedelta(hours=1)

    # Must not raise.
    handle = backend.schedule(
        target=target,
        session_id=session_id,
        env={"PATH": "/usr/bin"},
        repo_root=tmp_path,
    )

    assert handle.session_id == session_id
    assert backend.last_verify_inconclusive is True

    entries = sidecar_module.read_sidecar()
    assert any(h.label == handle.label for h in entries)
