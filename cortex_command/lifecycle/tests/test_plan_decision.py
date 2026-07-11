"""Tests for cortex-lifecycle-plan-decision — the plan-approval decision verb
whose function body encodes the exact per-arm ordered emission sequence.

Root resolution uses the cwd flavor, so the tests ``monkeypatch.chdir(tmp_path)``
(and ``delenv CORTEX_REPO_ROOT``) and scaffold a ``cortex/`` tree there; the real
``log_event`` then resolves and writes the same tree the verb reads for its
presence checks. Assertions parse the real appended ``events.log`` rows — the
write-side ordering invariant is the whole point of the verb.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import plan_decision as pd
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION


def _scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, feature: str = "feat") -> Path:
    """chdir into a scaffolded cortex/ project root and return the feature dir."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    return feature_dir


def _events_rows(feature_dir: Path) -> list[dict]:
    log = feature_dir / "events.log"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _event_names(feature_dir: Path) -> list[str]:
    return [r["event"] for r in _events_rows(feature_dir)]


# ---------------------------------------------------------------------------
# Per-arm ordered emission sequences
# ---------------------------------------------------------------------------


def test_branch_mode_emits_plan_approved_then_phase_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """branch-mode-approved: plan_approved{dispatch_choice} THEN
    phase_transition plan->implement, in that order."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(
        feature="feat", decision="branch-mode-approved", dispatch_choice="trunk"
    )

    assert r["state"] == "branch-mode-approved"
    assert r["emitted"] == ["plan_approved", "phase_transition"]

    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["plan_approved", "phase_transition"]
    assert rows[0]["dispatch_choice"] == "trunk"
    assert rows[1]["from"] == "plan"
    assert rows[1]["to"] == "implement"
    # phase_transition carries no tier when the typed subcommand omits it.
    assert "tier" not in rows[1]


@pytest.mark.parametrize("mode", ["trunk", "worktree-interactive", "feature-branch"])
def test_branch_mode_carries_each_valid_dispatch_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    pd.plan_decision(feature="feat", decision="branch-mode-approved", dispatch_choice=mode)
    rows = _events_rows(feature_dir)
    assert rows[0]["event"] == "plan_approved"
    assert rows[0]["dispatch_choice"] == mode


def test_wait_emits_plan_approved_wait_then_feature_paused_no_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """wait-approved: plan_approved{dispatch_choice: wait} THEN feature_paused,
    and NO phase_transition."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(feature="feat", decision="wait-approved")

    assert r["state"] == "wait-approved"
    assert r["emitted"] == ["plan_approved", "feature_paused"]

    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["plan_approved", "feature_paused"]
    assert rows[0]["dispatch_choice"] == "wait"
    assert "phase_transition" not in _event_names(feature_dir)


def test_wait_feature_paused_row_carries_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """374 R5 emission guard: the pausing arm writes a `feature_paused` row
    carrying the pause `slug` (and its `relayed-consent` kind) so the row is
    per-pause accountable — guards against a silent emitter regression that
    would drop back to a bare kind-less/slug-less row."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    pd.plan_decision(feature="feat", decision="wait-approved")

    rows = _events_rows(feature_dir)
    paused = [x for x in rows if x["event"] == "feature_paused"]
    assert len(paused) == 1
    assert paused[0]["slug"] == "plan-approval"
    assert paused[0]["kind"] == "relayed-consent"


def test_cancelled_emits_only_lifecycle_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(feature="feat", decision="cancelled")

    assert r["state"] == "cancelled"
    assert r["emitted"] == ["lifecycle_cancelled"]
    assert _event_names(feature_dir) == ["lifecycle_cancelled"]


def test_revise_emits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """revise short-circuits before any mutation — no events.log write."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(feature="feat", decision="revise")

    assert r["state"] == "revise"
    assert r["emitted"] == []
    assert not (feature_dir / "events.log").exists()


# ---------------------------------------------------------------------------
# No-duplicate + double-invocation idempotency
# ---------------------------------------------------------------------------


def test_branch_mode_no_duplicate_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single branch-mode invocation appends exactly one of each row."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    pd.plan_decision(feature="feat", decision="branch-mode-approved", dispatch_choice="trunk")
    names = _event_names(feature_dir)
    assert names.count("plan_approved") == 1
    assert names.count("phase_transition") == 1


def test_double_invocation_is_idempotent_branch_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the whole verb (crash-between-emissions repair) appends no
    duplicate — the second run reports nothing emitted."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    first = pd.plan_decision(
        feature="feat", decision="branch-mode-approved", dispatch_choice="trunk"
    )
    second = pd.plan_decision(
        feature="feat", decision="branch-mode-approved", dispatch_choice="trunk"
    )

    assert first["emitted"] == ["plan_approved", "phase_transition"]
    assert second["emitted"] == []
    names = _event_names(feature_dir)
    assert names == ["plan_approved", "phase_transition"]


def test_resume_after_partial_branch_mode_emits_only_the_missing_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after plan_approved but before phase_transition is repaired: the
    re-run emits ONLY the missing phase_transition, never a second plan_approved."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    # Simulate the partial state: plan_approved present, transition absent.
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "plan_approved", "feature": "feat", "dispatch_choice": "trunk"})
        + "\n",
        encoding="utf-8",
    )
    r = pd.plan_decision(
        feature="feat", decision="branch-mode-approved", dispatch_choice="trunk"
    )
    assert r["emitted"] == ["phase_transition"]
    names = _event_names(feature_dir)
    assert names == ["plan_approved", "phase_transition"]


def test_double_invocation_is_idempotent_wait_and_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    pd.plan_decision(feature="feat", decision="wait-approved")
    pd.plan_decision(feature="feat", decision="wait-approved")
    assert _event_names(feature_dir) == ["plan_approved", "feature_paused"]

    other = _scaffold(tmp_path, monkeypatch, feature="feat2")
    pd.plan_decision(feature="feat2", decision="cancelled")
    pd.plan_decision(feature="feat2", decision="cancelled")
    assert _event_names(other) == ["lifecycle_cancelled"]


# ---------------------------------------------------------------------------
# phase_transition guard must discriminate on from/to, not just event name
# ---------------------------------------------------------------------------


def test_phase_transition_guard_ignores_earlier_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The feature's log already carries earlier lifecycle transitions under the
    same ``phase_transition`` event name; the plan->implement emission must still
    fire (the guard matches on from/to, not the bare event name)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "phase_transition", "feature": "feat", "from": "spec", "to": "plan"})
        + "\n",
        encoding="utf-8",
    )
    r = pd.plan_decision(
        feature="feat", decision="branch-mode-approved", dispatch_choice="trunk"
    )
    assert "phase_transition" in r["emitted"]
    transitions = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"]
    assert {"from": "spec", "to": "plan"}.items() <= transitions[0].items()
    assert {"from": "plan", "to": "implement"}.items() <= transitions[1].items()


# ---------------------------------------------------------------------------
# Substring false-positive negative control for the presence check
# ---------------------------------------------------------------------------


def test_presence_check_is_not_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that merely mentions ``lifecycle_cancelled`` in another field does
    not suppress emission — only a parsed ``event`` match does."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "note", "text": "lifecycle_cancelled pending"}) + "\n",
        encoding="utf-8",
    )
    r = pd.plan_decision(feature="feat", decision="cancelled")
    assert r["emitted"] == ["lifecycle_cancelled"]
    assert _event_names(feature_dir) == ["note", "lifecycle_cancelled"]


# ---------------------------------------------------------------------------
# Slug guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ""])
def test_unsafe_slug_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(feature=bad, decision="cancelled")
    assert r["state"] == "error"
    # No events.log created anywhere under the scaffolded tree.
    assert list((tmp_path / "cortex" / "lifecycle").rglob("events.log")) == []


def test_branch_mode_without_dispatch_choice_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = pd.plan_decision(feature="feat", decision="branch-mode-approved")
    assert r["state"] == "error"
    assert not (feature_dir / "events.log").exists()


# ---------------------------------------------------------------------------
# KNOWN_STATES exhaustiveness + never-crash CLI
# ---------------------------------------------------------------------------


def test_every_state_is_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = set()
    for feat, kwargs in [
        ("f1", {"decision": "branch-mode-approved", "dispatch_choice": "trunk"}),
        ("f2", {"decision": "wait-approved"}),
        ("f3", {"decision": "cancelled"}),
        ("f4", {"decision": "revise"}),
    ]:
        _scaffold(tmp_path, monkeypatch, feature=feat)
        seen.add(pd.plan_decision(feature=feat, **kwargs)["state"])

    # error is reachable via the slug guard.
    _scaffold(tmp_path, monkeypatch, feature="f5")
    seen.add(pd.plan_decision(feature="../x", decision="cancelled")["state"])

    assert seen == set(pd.KNOWN_STATES)


def test_cli_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _scaffold(tmp_path, monkeypatch)
    rc = pd.main(["--feature", "feat", "--decision", "revise"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "revise"


def test_cli_never_crashes_and_writes_nothing_on_revise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Driving main(argv) in-process: revise exits 0 with a JSON envelope and no
    events.log write."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rc = pd.main(["--feature", "feat", "--decision", "revise"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["state"] == "revise"
    assert not (feature_dir / "events.log").exists()


def test_cli_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Any exception escaping plan_decision emits a {"state": "error", ...} struct
    and exits 0 — never a traceback."""
    _scaffold(tmp_path, monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(pd, "plan_decision", _boom)
    rc = pd.main(["--feature", "feat", "--decision", "cancelled"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "kaboom" in obj["message"]


def test_cli_payload_carries_protocol_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The emitted payload carries the additive ``protocol`` field (two-sided
    handshake substrate)."""
    _scaffold(tmp_path, monkeypatch)
    rc = pd.main(["--feature", "feat", "--decision", "revise"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION
