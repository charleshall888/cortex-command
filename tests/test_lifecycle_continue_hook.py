"""Tests for hooks/cortex-lifecycle-continue.sh — the Stop hook that resumes
the build loop when it ends a turn mid-lifecycle at a non-pausing phase.

The hook is unmatched, so it fires on every turn end in every repo the
cortex-core plugin is installed into. Two properties matter most and both are
pinned here: it must cost nothing (no verb spawn) when there is no lifecycle
bound to *this* session, and it must never block forever.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "cortex-lifecycle-continue.sh"

SESSION_ID = "session-under-test"


def _stub_verb(bindir: Path, envelope: dict, *, marker: Path) -> None:
    """Put a fake `cortex-lifecycle-next` on PATH that records each call."""
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "cortex-lifecycle-next"
    stub.write_text(
        "#!/bin/bash\n"
        f'echo called >> "{marker}"\n'
        f"cat <<'JSON'\n{json.dumps(envelope)}\nJSON\n"
    )
    stub.chmod(0o755)


def _run(cwd: Path, bindir: Path, *, session_id: str = SESSION_ID, env=None):
    payload = json.dumps(
        {
            "session_id": session_id,
            "cwd": str(cwd),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
        }
    )
    full_env = dict(os.environ)
    full_env["PATH"] = f"{bindir}:{full_env['PATH']}"
    full_env.pop("CORTEX_NO_AUTOCONTINUE", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=full_env,
    )


@pytest.fixture
def repo(tmp_path):
    """A staged repo with one lifecycle bound to SESSION_ID."""
    feature_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    (feature_dir / ".session").write_text(SESSION_ID)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "phase_transition", "from": "implement", "to": "review"})
        + "\n"
    )
    return tmp_path


@pytest.fixture
def bindir(tmp_path):
    return tmp_path / "stubbin"


@pytest.fixture
def marker(tmp_path):
    return tmp_path / "verb-calls"


def test_blocks_at_review(repo, bindir, marker):
    """The observed stall: a non-pausing phase must be resumed, not handed back."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    r = _run(repo, bindir)
    assert r.returncode == 2, r.stderr
    assert "feat" in r.stderr and "review" in r.stderr
    # The reason must forbid the question outright — a neutral nudge is exactly
    # the prose lever that already failed twice (#423, #445).
    assert "Do not ask whether to proceed" in r.stderr


def test_no_lifecycle_dir_never_spawns_the_verb(tmp_path, bindir, marker):
    """The universal-cost path: a repo with no cortex/lifecycle pays one stat."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    r = _run(tmp_path, bindir)
    assert r.returncode == 0
    assert not marker.exists(), "spawned cortex-lifecycle-next with no lifecycle present"


def test_other_sessions_lifecycle_is_untouched(repo, bindir, marker):
    """In-flight work in another session is indistinguishable from a stall —
    so the hook only ever acts on the lifecycle bound to its own session."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    r = _run(repo, bindir, session_id="a-different-session")
    assert r.returncode == 0
    assert not marker.exists(), "consulted state for another session's lifecycle"


def test_completed_feature_is_not_re_entered(repo, bindir, marker):
    """A finished feature also serves state 'complete', so the terminal event
    has to be checked directly."""
    (repo / "cortex/lifecycle/feat/events.log").write_text(
        json.dumps({"event": "feature_complete", "feature": "feat"}) + "\n"
    )
    _stub_verb(bindir, {"state": "complete", "pause_spec": {"active": False}}, marker=marker)
    r = _run(repo, bindir)
    assert r.returncode == 0
    assert not marker.exists()


@pytest.mark.parametrize("state", ["plan", "implement", "specify", "research"])
def test_pausing_phases_are_left_alone(repo, bindir, marker, state):
    """Plan gates on approval and implement owns batch-failure triage."""
    _stub_verb(bindir, {"state": state, "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 0


def test_active_pause_spec_wins(repo, bindir, marker):
    """A sanctioned pause is the state machine's own answer to 'is a surface
    owed here' and outranks auto-continue."""
    _stub_verb(
        bindir,
        {"state": "review", "pause_spec": {"active": True, "active_kind": "question"}},
        marker=marker,
    )
    assert _run(repo, bindir).returncode == 0


def _append_event(repo, event="phase_transition"):
    with (repo / "cortex/lifecycle/feat/events.log").open("a") as fh:
        fh.write(json.dumps({"event": event, "feature": "feat"}) + "\n")


def test_conversation_is_not_hijacked(repo, bindir, marker):
    """The motivating hazard: the hook fires on EVERY turn end while a
    lifecycle is bound, including turns where the operator broke off to ask
    something unrelated. Those turns move neither state nor event count, so
    after the one legitimate nudge the hook must go silent — not keep
    dragging the operator back into the lifecycle."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 2, "the boundary stall itself must be nudged"
    codes = [_run(repo, bindir).returncode for _ in range(4)]
    assert codes == [0, 0, 0, 0], f"hijacked {codes.count(2)} conversational turns"


def test_each_boundary_crossing_gets_its_own_nudge(repo, bindir, marker):
    """Real progress re-arms the hook: review -> complete is a second stall
    opportunity and must be covered."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 2
    _append_event(repo)
    _stub_verb(bindir, {"state": "complete", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 2


def test_rework_round_trip_re_arms_the_same_phase(repo, bindir, marker):
    """review -> implement-rework -> review is the same implement->review
    stall a second time. Keying on state alone would miss it; the event count
    is what catches it."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 2
    _stub_verb(bindir, {"state": "implement-rework", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 0
    _append_event(repo)
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    assert _run(repo, bindir).returncode == 2, "second review crossing left unguarded"


def test_total_cap_bounds_a_pathological_loop(repo, bindir, marker):
    """Backstop. The progress key cannot bound a loop that writes an event
    every turn, and the Stop contract offers no platform-level protection
    against a hook that always blocks."""
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    codes = []
    for _ in range(13):
        codes.append(_run(repo, bindir).returncode)
        _append_event(repo)
    assert codes.count(2) == 10, codes
    assert codes[-1] == 0, "cap never engaged"


def test_operator_hand_back_marker(repo, bindir, marker):
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    (repo / "cortex/lifecycle/feat/.autocontinue-off").touch()
    r = _run(repo, bindir)
    assert r.returncode == 0
    assert not marker.exists()


def test_env_escape_hatch(repo, bindir, marker):
    _stub_verb(bindir, {"state": "review", "pause_spec": {"active": False}}, marker=marker)
    r = _run(repo, bindir, env={"CORTEX_NO_AUTOCONTINUE": "1"})
    assert r.returncode == 0
    assert not marker.exists()


def test_hook_is_registered_and_executable():
    assert os.access(HOOK, os.X_OK), "hook must be executable"
    manifest = json.loads(
        (REPO_ROOT / "plugins/cortex-core/hooks/hooks.json").read_text()
    )
    commands = [
        h["command"]
        for entry in manifest["hooks"].get("Stop", [])
        for h in entry["hooks"]
    ]
    assert any(HOOK.name in c for c in commands), "Stop hook not registered"
