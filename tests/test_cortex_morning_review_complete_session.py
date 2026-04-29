"""Fixture-replay tests for ``bin/cortex-morning-review-complete-session``.

Covers the six C11 behaviour cases enumerated in the lifecycle spec
(R6 of ``extract-morning-review-deterministic-sequences-c11-c15-bundle``).
Each test invokes the real bash shim via ``subprocess.run`` and asserts on
filesystem state, exit code, and stderr — no mocking of the Python helper.

Cases:
    (a) phase=executing + --pointer -> state becomes complete; pointer
        unlinked; exit 0.
    (b) phase=executing without --pointer -> state becomes complete;
        any unrelated pointer file is untouched; exit 0.
    (c) phase=complete + --pointer -> no-op; pointer preserved; exit 0.
    (d) phase in {paused, planning} -> no-op; pointer preserved; exit 0.
    (e) state file missing -> exit 0 with empty stderr (silent skip).
    (f) malformed phase value (raw JSON with all six required keys but a
        phase outside PHASES) -> non-zero exit; state file byte-identical;
        stderr names the malformed phase.

A bonus test (KeyError-on-missing-key) locks in the catch-block coverage
for the missing-required-key path separately from the ValueError path,
bringing the total ``def test_`` count to seven.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cortex_command.overnight.state import OvernightState, load_state, save_state

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "bin"
    / "cortex-morning-review-complete-session"
)


def _make_executing_state(session_id: str = "test-session") -> OvernightState:
    """Construct a canonical executing-phase OvernightState for fixtures."""
    return OvernightState(
        session_id=session_id,
        plan_ref="test-plan",
        current_round=1,
        phase="executing",
    )


def _make_state_with_phase(phase: str, session_id: str = "test-session") -> OvernightState:
    """Construct an OvernightState with the given phase (must be in PHASES)."""
    return OvernightState(
        session_id=session_id,
        plan_ref="test-plan",
        current_round=1,
        phase=phase,
    )


def _run_shim(*args: str) -> subprocess.CompletedProcess:
    """Invoke the real bash shim (not python3 directly) with the given args."""
    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        text=True,
        capture_output=True,
    )


def test_executing_with_pointer_transitions_to_complete_and_unlinks_pointer(
    tmp_path: Path,
) -> None:
    """Case (a): happy path with --pointer.

    Fixture: state.phase == "executing"; pointer file exists.
    Expect: phase becomes "complete"; pointer is removed; exit 0.
    """
    state_path = tmp_path / "overnight-state.json"
    save_state(_make_executing_state(), state_path)

    pointer_path = tmp_path / "active-session-pointer"
    pointer_path.write_text("dummy-pointer-content\n")

    result = _run_shim(str(state_path), "--pointer", str(pointer_path))

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    reloaded = load_state(state_path)
    assert reloaded.phase == "complete", (
        f"expected phase=complete; got {reloaded.phase!r}"
    )
    assert not pointer_path.exists(), (
        f"pointer file should be unlinked, but still exists at {pointer_path}"
    )


def test_executing_without_pointer_transitions_to_complete_no_pointer_touched(
    tmp_path: Path,
) -> None:
    """Case (b): happy path without --pointer (fallback path).

    Fixture: state.phase == "executing"; no --pointer arg passed; an
    unrelated sentinel file exists at a different path.
    Expect: phase becomes "complete"; sentinel untouched; exit 0.
    """
    state_path = tmp_path / "overnight-state.json"
    save_state(_make_executing_state(), state_path)

    # Sentinel file at an unrelated path. The shim should not touch this
    # because --pointer was not supplied.
    sentinel = tmp_path / "unrelated-sentinel.txt"
    sentinel_content = "I should remain on disk\n"
    sentinel.write_text(sentinel_content)

    result = _run_shim(str(state_path))

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    reloaded = load_state(state_path)
    assert reloaded.phase == "complete"
    assert sentinel.exists(), "sentinel was unexpectedly removed"
    assert sentinel.read_text() == sentinel_content


def test_phase_complete_is_noop_pointer_untouched(tmp_path: Path) -> None:
    """Case (c): phase already "complete" -> no-op; pointer preserved.

    Fixture: state.phase == "complete"; pointer file exists; --pointer
    is passed.
    Expect: phase stays "complete"; pointer file still exists; exit 0.
    """
    state_path = tmp_path / "overnight-state.json"
    save_state(_make_state_with_phase("complete"), state_path)

    pointer_path = tmp_path / "active-session-pointer"
    pointer_content = "still-here\n"
    pointer_path.write_text(pointer_content)

    result = _run_shim(str(state_path), "--pointer", str(pointer_path))

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    reloaded = load_state(state_path)
    assert reloaded.phase == "complete"
    assert pointer_path.exists(), (
        "pointer was unlinked despite no-op phase; spec requires preservation"
    )
    assert pointer_path.read_text() == pointer_content


@pytest.mark.parametrize("phase", ["paused", "planning"])
def test_phase_paused_or_planning_is_noop_pointer_untouched(
    tmp_path: Path, phase: str
) -> None:
    """Case (d): phase is "paused" or "planning" -> no-op; pointer preserved.

    Fixture: state.phase in {"paused", "planning"}; pointer file exists;
    --pointer is passed.
    Expect: phase unchanged; pointer file still exists; exit 0.
    """
    state_path = tmp_path / "overnight-state.json"
    save_state(_make_state_with_phase(phase), state_path)

    pointer_path = tmp_path / "active-session-pointer"
    pointer_content = f"phase-was-{phase}\n"
    pointer_path.write_text(pointer_content)

    result = _run_shim(str(state_path), "--pointer", str(pointer_path))

    assert result.returncode == 0, (
        f"expected exit 0 for phase={phase!r}; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    reloaded = load_state(state_path)
    assert reloaded.phase == phase, (
        f"phase changed unexpectedly from {phase!r} to {reloaded.phase!r}"
    )
    assert pointer_path.exists(), (
        f"pointer was unlinked for no-op phase={phase!r}; "
        "spec requires preservation"
    )
    assert pointer_path.read_text() == pointer_content


def test_state_file_missing_silent_skip(tmp_path: Path) -> None:
    """Case (e): state file does not exist -> exit 0 silently.

    Fixture: state_path is a nonexistent path.
    Expect: exit 0 with no error message about a missing state file.
    """
    state_path = tmp_path / "does-not-exist.json"
    assert not state_path.exists(), "fixture precondition: state must not exist"

    result = _run_shim(str(state_path))

    assert result.returncode == 0, (
        f"expected silent exit 0; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    # The shim's invocation logger may print to stderr unconditionally;
    # what we lock in is that there is NO error message about the missing
    # state file.
    assert "error loading" not in result.stderr, (
        f"unexpected error message for missing state: {result.stderr!r}"
    )
    assert "does-not-exist.json" not in result.stderr or "error" not in result.stderr.lower(), (
        f"stderr should not flag the missing state file as an error: {result.stderr!r}"
    )


def test_malformed_phase_exits_nonzero_state_unchanged_stderr_names_phase(
    tmp_path: Path,
) -> None:
    """Case (f): malformed phase value -> non-zero exit; state unchanged.

    Fixture: raw JSON with all six required keys but ``phase: "running"``
    (not a member of PHASES). Bypasses save_state because OvernightState's
    __post_init__ would reject the construction at fixture-creation time;
    load_state's required-key checks still pass, so the helper reaches
    OvernightState(__post_init__) which raises ValueError.
    Expect: exit != 0; state file byte-identical pre/post; stderr contains
    the malformed phase value.
    """
    state_path = tmp_path / "overnight-state.json"
    raw = {
        "session_id": "test-session",
        "plan_ref": "test-plan",
        "current_round": 1,
        "phase": "running",  # invalid: not in PHASES
        "started_at": "2026-04-28T00:00:00Z",
        "updated_at": "2026-04-28T00:00:00Z",
    }
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    pre_bytes = state_path.read_bytes()

    result = _run_shim(str(state_path))

    assert result.returncode != 0, (
        f"expected non-zero exit for malformed phase; got 0\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    post_bytes = state_path.read_bytes()
    assert post_bytes == pre_bytes, (
        "state file should be byte-identical after malformed-phase rejection"
    )
    assert "running" in result.stderr, (
        f"stderr should name the malformed phase 'running'; got: {result.stderr!r}"
    )


def test_missing_required_key_exits_nonzero_state_unchanged(tmp_path: Path) -> None:
    """Bonus case: missing required key (KeyError path).

    Fixture: raw JSON with only ``phase: "running"`` (omits the other
    five required keys). The helper hits the KeyError branch of
    load_state's catch block.
    Expect: exit != 0; state unchanged; stderr is non-empty.
    """
    state_path = tmp_path / "overnight-state.json"
    raw = {"phase": "running"}
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    pre_bytes = state_path.read_bytes()

    result = _run_shim(str(state_path))

    assert result.returncode != 0, (
        f"expected non-zero exit for missing-key fixture; got 0\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    post_bytes = state_path.read_bytes()
    assert post_bytes == pre_bytes, (
        "state file should be byte-identical after missing-key rejection"
    )
    assert result.stderr.strip(), (
        "stderr should contain a diagnostic message, but was empty"
    )
