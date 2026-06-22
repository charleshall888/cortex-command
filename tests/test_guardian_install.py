"""Tests for the persistent guardian launchd install/remove (spec §R6, Task 10).

``cortex overnight guardian install`` renders and bootstraps a SINGLE
host-level launchd LaunchAgent on a ``StartInterval`` poll cadence whose
``ProgramArguments`` invoke ``cortex overnight guardian scan`` each tick —
one agent for the whole host (NOT per-session, NOT ``StartCalendarInterval``).
``cortex overnight guardian remove`` boots it out and unlinks its plist.

The load-bearing regression guard here is the launchd-incoherence finding:
the guardian plist must carry a ``StartInterval`` integer cadence and a fixed
host-level label, and must NOT carry a bare-true ``KeepAlive`` (which would
relaunch a run-to-completion ``StartInterval`` job the instant it exits,
collapsing the poll interval into a near-continuous busy-loop). These tests
render the plist to a temp dir and assert its structure, and exercise the
install/remove CLI verbs against a temp plist dir with ``launchctl`` mocked —
no real LaunchAgent is ever bootstrapped.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command import cli
from cortex_command.overnight import guardian
from cortex_command.overnight.scheduler import macos
from cortex_command.overnight.scheduler.macos import (
    GUARDIAN_LABEL,
    GUARDIAN_START_INTERVAL_SECONDS,
    GUARDIAN_THROTTLE_INTERVAL_SECONDS,
    build_guardian_plist_dict,
    install_guardian,
    remove_guardian,
)


# ---------------------------------------------------------------------------
# Plist structure (cross-platform — pure render, no launchctl)
# ---------------------------------------------------------------------------


def _rendered_guardian_plist(repo_root: Path = Path("/repo")) -> dict:
    """Build + round-trip the guardian plist dict via plistlib."""
    plist_dict = build_guardian_plist_dict(
        cortex_bin="/usr/local/bin/cortex",
        repo_root=repo_root,
    )
    return plistlib.loads(plistlib.dumps(plist_dict))


def test_guardian_plist_has_startinterval_integer():
    """(a) The plist carries a ``StartInterval`` integer cadence — NOT a
    one-shot ``StartCalendarInterval`` calendar block."""
    plist = _rendered_guardian_plist()

    assert "StartInterval" in plist
    assert isinstance(plist["StartInterval"], int)
    assert plist["StartInterval"] == GUARDIAN_START_INTERVAL_SECONDS
    # Explicitly NOT the per-session one-shot calendar form.
    assert "StartCalendarInterval" not in plist


def test_guardian_plist_has_single_fixed_host_level_label():
    """(b) A single fixed host-level label — no per-session minting."""
    plist = _rendered_guardian_plist()

    assert plist["Label"] == GUARDIAN_LABEL
    # The label is a fixed constant, not a per-session minted string: it must
    # not carry a session-id segment (per-session labels embed the session id).
    assert ".overnight-schedule." not in plist["Label"]


def test_guardian_plist_has_no_bare_true_keepalive():
    """(c) Regression guard: NO bare-true ``KeepAlive`` key.

    A bare-true ``KeepAlive`` on a ``StartInterval`` run-to-completion job
    relaunches it the instant it exits each tick (throttled only to
    ``ThrottleInterval``), collapsing the poll interval into a near-continuous
    busy-loop. The coherent design omits ``KeepAlive`` entirely and relies on
    ``StartInterval``'s own re-fire as the restart-on-crash supervision.
    """
    plist = _rendered_guardian_plist()

    # No bare-true KeepAlive. (If a KeepAlive key were ever present at all it
    # would have to be the conditional dict form {"SuccessfulExit": False} —
    # never the bare-true form — but the default omits it entirely.)
    assert plist.get("KeepAlive") is not True
    assert "KeepAlive" not in plist


def test_guardian_plist_program_arguments_invoke_scan():
    """ProgramArguments invoke ``cortex overnight guardian scan`` directly."""
    plist = _rendered_guardian_plist()

    assert plist["ProgramArguments"] == [
        "/usr/local/bin/cortex",
        "overnight",
        "guardian",
        "scan",
    ]


def test_guardian_plist_has_throttle_interval_crash_floor():
    """The only coherent crash-handling addition is ``ThrottleInterval``."""
    plist = _rendered_guardian_plist()

    assert plist["ThrottleInterval"] == GUARDIAN_THROTTLE_INTERVAL_SECONDS


def test_guardian_plist_threads_repo_root_for_scan():
    """``CORTEX_REPO_ROOT`` is threaded so the scan resolves the user repo
    under launchd (where cwd is not the user's repo)."""
    plist = _rendered_guardian_plist(repo_root=Path("/Users/x/proj"))

    assert plist["EnvironmentVariables"]["CORTEX_REPO_ROOT"] == "/Users/x/proj"


# ---------------------------------------------------------------------------
# install / remove (macOS backend + CLI verbs, launchctl mocked)
# ---------------------------------------------------------------------------


def _fake_launchctl(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub ``subprocess.run`` at the macOS-backend boundary.

    bootstrap → exit 0; print → exit 0 with an armed-state line; bootout →
    exit 0. Returns the captured call list so tests can assert the sequence.
    """
    calls: list[list[str]] = []

    def _run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        subverb = cmd[1] if len(cmd) > 1 else ""
        if subverb == "print":
            return subprocess.CompletedProcess(cmd, 0, b"state = waiting\n", b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.subprocess.run", _run
    )
    return calls


pytestmark_darwin = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only launchd backend; install/remove require darwin",
)


@pytestmark_darwin
def test_install_guardian_writes_plist_and_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``install_guardian`` writes the plist to the target dir and bootstraps."""
    calls = _fake_launchctl(monkeypatch)
    plist_dir = tmp_path / "launch"

    plist_path = install_guardian(repo_root=tmp_path, plist_dir=plist_dir)

    assert plist_path.exists()
    assert plist_path.name == f"{GUARDIAN_LABEL}.plist"
    # The written plist round-trips to the guardian shape.
    written = plistlib.loads(plist_path.read_bytes())
    assert written["StartInterval"] == GUARDIAN_START_INTERVAL_SECONDS
    assert written["Label"] == GUARDIAN_LABEL
    # bootstrap was invoked (after a pre-install bootout for idempotency).
    assert any(c[1] == "bootstrap" for c in calls)


@pytestmark_darwin
def test_remove_guardian_boots_out_and_unlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``remove_guardian`` boots out the label and unlinks its plist."""
    calls = _fake_launchctl(monkeypatch)
    plist_dir = tmp_path / "launch"
    plist_dir.mkdir(parents=True)
    plist_path = plist_dir / f"{GUARDIAN_LABEL}.plist"
    plist_path.write_bytes(plistlib.dumps(build_guardian_plist_dict(repo_root=tmp_path)))

    removed = remove_guardian(plist_dir=plist_dir)

    assert removed is True
    assert not plist_path.exists()
    assert any(c[1] == "bootout" for c in calls)


@pytestmark_darwin
def test_remove_guardian_is_clean_noop_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Removing a guardian that was never installed is a clean no-op."""
    _fake_launchctl(monkeypatch)
    plist_dir = tmp_path / "launch"
    plist_dir.mkdir(parents=True)

    removed = remove_guardian(plist_dir=plist_dir)

    assert removed is False


@pytestmark_darwin
def test_cli_guardian_install_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``cortex overnight guardian install`` exits 0 (temp plist dir, mocked
    launchctl)."""
    _fake_launchctl(monkeypatch)
    plist_dir = tmp_path / "launch"
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler._resolve_repo_path",
        lambda *a, **k: tmp_path,
    )
    # Pin the backend's plist dir into the temp tree so the real
    # $TMPDIR/cortex-overnight-launch/ is never touched.
    monkeypatch.setattr(macos.MacOSLaunchAgentBackend, "_plist_dir", staticmethod(lambda: plist_dir))

    rc = cli._dispatch_overnight_guardian_install(argparse.Namespace())

    assert rc == 0
    assert (plist_dir / f"{GUARDIAN_LABEL}.plist").exists()


@pytestmark_darwin
def test_cli_guardian_remove_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``cortex overnight guardian remove`` exits 0 (clean no-op path)."""
    _fake_launchctl(monkeypatch)
    plist_dir = tmp_path / "launch"
    monkeypatch.setattr(macos.MacOSLaunchAgentBackend, "_plist_dir", staticmethod(lambda: plist_dir))

    rc = cli._dispatch_overnight_guardian_remove(argparse.Namespace())

    assert rc == 0


# ---------------------------------------------------------------------------
# Off-macOS gating (runs everywhere; simulates the non-darwin platform)
# ---------------------------------------------------------------------------


def test_guardian_install_raises_unsupported_off_macos(monkeypatch: pytest.MonkeyPatch):
    """Off macOS, the persistent installer raises ``GuardianUnsupportedError``."""
    monkeypatch.setattr(guardian.sys, "platform", "linux")

    with pytest.raises(guardian.GuardianUnsupportedError):
        guardian.install_guardian(Path("/repo"))


def test_cli_guardian_install_off_macos_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """The CLI verb surfaces the unsupported case as a clean exit 1."""
    monkeypatch.setattr(guardian.sys, "platform", "linux")
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler._resolve_repo_path",
        lambda *a, **k: Path("/repo"),
    )

    rc = cli._dispatch_overnight_guardian_install(argparse.Namespace())

    assert rc == 1
    assert "cannot install guardian" in capsys.readouterr().err


def test_cli_guardian_remove_off_macos_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """The remove verb surfaces the unsupported case as a clean exit 1."""
    monkeypatch.setattr(guardian.sys, "platform", "linux")

    rc = cli._dispatch_overnight_guardian_remove(argparse.Namespace())

    assert rc == 1
    assert "cannot remove guardian" in capsys.readouterr().err
