"""Tests for cortex-lifecycle-review-verdict — the review verdict×cycle routing
verb whose function body encodes the exact per-invocation ordered emission
sequence (review_verdict → optional drift_protocol_breach → routed
phase_transition).

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

from cortex_command.lifecycle import review_verdict as rv
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
# Per-route ordered emission sequences
# ---------------------------------------------------------------------------


def test_approved_routes_to_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """APPROVED (any cycle): review_verdict THEN phase_transition review->complete."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="none")

    assert r["state"] == "approved"
    assert r["transition_to"] == "complete"
    assert r["emitted"] == ["review_verdict", "phase_transition"]

    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["review_verdict", "phase_transition"]
    assert rows[0]["verdict"] == "APPROVED"
    assert rows[0]["cycle"] == 1
    assert rows[0]["requirements_drift"] == "none"
    assert rows[1]["from"] == "review"
    assert rows[1]["to"] == "complete"


def test_changes_requested_cycle1_routes_to_implement_rework(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHANGES_REQUESTED cycle 1: review_verdict THEN phase_transition
    review->implement-rework — the transition this verb solely owns."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=1, drift="none"
    )

    assert r["state"] == "rework"
    assert r["transition_to"] == "implement-rework"
    assert r["emitted"] == ["review_verdict", "phase_transition"]

    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["review_verdict", "phase_transition"]
    assert rows[1]["from"] == "review"
    assert rows[1]["to"] == "implement-rework"


def test_changes_requested_cycle2_routes_to_escalated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CHANGES_REQUESTED cycle ≥ 2: escalated, not rework."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=2, drift="none"
    )

    assert r["state"] == "escalated"
    assert r["transition_to"] == "escalated"
    assert r["emitted"] == ["review_verdict", "phase_transition"]

    rows = _events_rows(feature_dir)
    assert rows[1]["from"] == "review"
    assert rows[1]["to"] == "escalated"


def test_rejected_any_cycle_routes_to_escalated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REJECTED escalates even at cycle 1."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(feature="feat", verdict="REJECTED", cycle=1, drift="none")

    assert r["state"] == "escalated"
    assert r["transition_to"] == "escalated"
    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == ["review_verdict", "phase_transition"]
    assert rows[1]["to"] == "escalated"


# ---------------------------------------------------------------------------
# Breach arm insertion (between verdict and transition)
# ---------------------------------------------------------------------------


def test_breach_inserts_drift_protocol_breach_between_verdict_and_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--breach interleaves drift_protocol_breach in position (b): the ordered
    sequence is review_verdict → drift_protocol_breach → phase_transition."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(
        feature="feat",
        verdict="CHANGES_REQUESTED",
        cycle=1,
        drift="detected",
        breach=True,
        retries=2,
    )

    assert r["emitted"] == [
        "review_verdict",
        "drift_protocol_breach",
        "phase_transition",
    ]
    rows = _events_rows(feature_dir)
    assert [x["event"] for x in rows] == [
        "review_verdict",
        "drift_protocol_breach",
        "phase_transition",
    ]
    assert rows[0]["requirements_drift"] == "detected"
    assert rows[1]["state"] == "detected"
    assert rows[1]["suggestion"] == "missing"
    assert rows[1]["retries"] == 2
    assert rows[1]["cycle"] == 1
    assert rows[2]["to"] == "implement-rework"


def test_no_breach_omits_the_breach_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --breach, no drift_protocol_breach row even when drift detected."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="detected")
    assert "drift_protocol_breach" not in _event_names(feature_dir)


# ---------------------------------------------------------------------------
# No-duplicate re-invocation (crash-recovery / re-run idempotency)
# ---------------------------------------------------------------------------


def test_reinvocation_after_rework_transition_emits_no_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the whole verb after the rework transition already landed
    appends no duplicate row — the second run reports nothing emitted."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    first = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=1, drift="none"
    )
    second = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=1, drift="none"
    )

    assert first["emitted"] == ["review_verdict", "phase_transition"]
    assert second["emitted"] == []
    assert _event_names(feature_dir) == ["review_verdict", "phase_transition"]


def test_resume_after_partial_emits_only_the_missing_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after review_verdict but before the transition is repaired: the
    re-run emits ONLY the missing phase_transition, never a second verdict."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps(
            {
                "event": "review_verdict",
                "feature": "feat",
                "verdict": "APPROVED",
                "cycle": 1,
                "requirements_drift": "none",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    r = rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="none")
    assert r["emitted"] == ["phase_transition"]
    assert _event_names(feature_dir) == ["review_verdict", "phase_transition"]


def test_breach_reinvocation_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The breach arm is also idempotent across a full re-invocation (same cycle)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rv.review_verdict(
        feature="feat", verdict="REJECTED", cycle=1, drift="detected", breach=True
    )
    rv.review_verdict(
        feature="feat", verdict="REJECTED", cycle=1, drift="detected", breach=True
    )
    assert _event_names(feature_dir) == [
        "review_verdict",
        "drift_protocol_breach",
        "phase_transition",
    ]


def test_breach_guard_discriminates_on_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine second-cycle breach is NOT suppressed by a cycle-1 breach row.

    A review can breach at cycle 1 (drift detected + suggestion missing → rework)
    and again at a later cycle; the cycle-qualified guard emits both rows, each
    carrying its own cycle. (Regression guard for the closed event-name-only
    residual.)"""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=1, drift="detected", breach=True
    )
    second = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=2, drift="detected", breach=True
    )

    # The cycle-2 run emits its own breach (not suppressed by the cycle-1 row).
    assert "drift_protocol_breach" in second["emitted"]
    breach_cycles = sorted(
        row["cycle"] for row in _events_rows(feature_dir)
        if row["event"] == "drift_protocol_breach"
    )
    assert breach_cycles == [1, 2]


# ---------------------------------------------------------------------------
# review_verdict presence check discriminates on cycle, not just event name
# ---------------------------------------------------------------------------


def test_review_verdict_guard_discriminates_on_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle-2 verdict must still emit even though a cycle-1 verdict row exists
    under the same event name — the guard matches on event+cycle."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps(
            {
                "event": "review_verdict",
                "feature": "feat",
                "verdict": "CHANGES_REQUESTED",
                "cycle": 1,
                "requirements_drift": "none",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    r = rv.review_verdict(
        feature="feat", verdict="CHANGES_REQUESTED", cycle=2, drift="none"
    )
    assert "review_verdict" in r["emitted"]
    verdicts = [x for x in _events_rows(feature_dir) if x["event"] == "review_verdict"]
    assert [v["cycle"] for v in verdicts] == [1, 2]


# ---------------------------------------------------------------------------
# phase_transition guard must discriminate on from/to, not just event name
# ---------------------------------------------------------------------------


def test_phase_transition_guard_ignores_earlier_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The feature's log already carries earlier lifecycle transitions under the
    same ``phase_transition`` event name; the review->complete emission must
    still fire (the guard matches on from/to, not the bare event name)."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps(
            {"event": "phase_transition", "feature": "feat", "from": "plan", "to": "implement"}
        )
        + "\n",
        encoding="utf-8",
    )
    r = rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="none")
    assert "phase_transition" in r["emitted"]
    transitions = [x for x in _events_rows(feature_dir) if x["event"] == "phase_transition"]
    assert {"from": "plan", "to": "implement"}.items() <= transitions[0].items()
    assert {"from": "review", "to": "complete"}.items() <= transitions[1].items()


# ---------------------------------------------------------------------------
# Substring false-positive negative control for the presence check
# ---------------------------------------------------------------------------


def test_presence_check_is_not_substring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that merely mentions ``review_verdict`` in another field does not
    suppress emission — only a parsed ``event`` match does."""
    feature_dir = _scaffold(tmp_path, monkeypatch)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "note", "text": "review_verdict pending for cycle 1"}) + "\n",
        encoding="utf-8",
    )
    r = rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="none")
    assert "review_verdict" in r["emitted"]
    assert _event_names(feature_dir) == ["note", "review_verdict", "phase_transition"]


# ---------------------------------------------------------------------------
# Slug guard + invalid inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ""])
def test_unsafe_slug_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(feature=bad, verdict="APPROVED", cycle=1, drift="none")
    assert r["state"] == "error"
    assert list((tmp_path / "cortex" / "lifecycle").rglob("events.log")) == []


def test_invalid_verdict_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(feature="feat", verdict="MAYBE", cycle=1, drift="none")
    assert r["state"] == "error"
    assert not (feature_dir / "events.log").exists()


def test_invalid_drift_errors_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    r = rv.review_verdict(feature="feat", verdict="APPROVED", cycle=1, drift="maybe")
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
        ("f1", {"verdict": "APPROVED", "cycle": 1, "drift": "none"}),
        ("f2", {"verdict": "CHANGES_REQUESTED", "cycle": 1, "drift": "none"}),
        ("f3", {"verdict": "CHANGES_REQUESTED", "cycle": 2, "drift": "none"}),
        ("f4", {"verdict": "REJECTED", "cycle": 1, "drift": "none"}),
    ]:
        _scaffold(tmp_path, monkeypatch, feature=feat)
        seen.add(rv.review_verdict(feature=feat, **kwargs)["state"])

    # error is reachable via the slug guard.
    _scaffold(tmp_path, monkeypatch, feature="f5")
    seen.add(
        rv.review_verdict(feature="../x", verdict="APPROVED", cycle=1, drift="none")["state"]
    )

    assert seen == set(rv.KNOWN_STATES)


def test_cli_emits_json_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _scaffold(tmp_path, monkeypatch)
    rc = rv.main(["--feature", "feat", "--verdict", "APPROVED", "--cycle", "1", "--drift", "none"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "approved"
    assert obj["transition_to"] == "complete"


def test_cli_breach_flag_emits_the_breach_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    feature_dir = _scaffold(tmp_path, monkeypatch)
    rc = rv.main(
        [
            "--feature", "feat",
            "--verdict", "CHANGES_REQUESTED",
            "--cycle", "1",
            "--drift", "detected",
            "--breach",
            "--retries", "2",
        ]
    )
    assert rc == 0
    assert _event_names(feature_dir) == [
        "review_verdict",
        "drift_protocol_breach",
        "phase_transition",
    ]


def test_cli_error_state_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Any exception escaping review_verdict emits a {"state": "error", ...}
    struct and exits 0 — never a traceback."""
    _scaffold(tmp_path, monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(rv, "review_verdict", _boom)
    rc = rv.main(["--feature", "feat", "--verdict", "APPROVED", "--cycle", "1", "--drift", "none"])
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
    rc = rv.main(["--feature", "feat", "--verdict", "APPROVED", "--cycle", "1", "--drift", "none"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["protocol"] == PROTOCOL_VERSION
