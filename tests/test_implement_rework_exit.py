"""The rework cycle must be representable in the verb layer (#433).

`review.rework` moves a feature `review -> implement-rework`. Until
`implement.rework-review` existed, nothing departed that state: all three
`implement_transition` arms left from `implement`, so recording the cycle-2
verdict refused with `gate-mismatch` and the only way forward was hand-appending
a `phase_transition` row via `cortex-lifecycle-event log` — the exact
hand-written-emission failure mode the served-loop work was built to remove.

Fixtures here carry REAL `phase_transition` rows all the way into
`implement-rework`. That is load-bearing: a fixture without machine rows sends
`resolve_lifecycle_phase` down its artifact-derived LEGACY FALLBACK, which
reports `review` off ticked plan.md checkboxes and would collapse the two
detectors into one — hiding whether the departure is genuinely events-derived.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle import implement_transition as it

_BASE_ROWS = [
    {"event": "lifecycle_start", "feature": "feat", "tier": "complex"},
    {"event": "spec_approved", "feature": "feat", "decision": "approved"},
    {"event": "phase_transition", "feature": "feat", "from": "specify", "to": "plan"},
    {"event": "plan_approved", "feature": "feat", "decision": "branch-mode-approved"},
    {"event": "phase_transition", "feature": "feat", "from": "plan", "to": "implement"},
    {"event": "batch_dispatch", "feature": "feat", "batch": 1, "tasks": ["T1"]},
    {"event": "phase_transition", "feature": "feat", "from": "implement", "to": "review"},
]

_REWORK_ROWS = [
    {"event": "review_verdict", "feature": "feat", "verdict": "CHANGES_REQUESTED",
     "cycle": 1},
    {"event": "phase_transition", "feature": "feat", "from": "review",
     "to": "implement-rework"},
]


def _scaffold(
    tmp_path: Path,
    rows: list[dict],
    *,
    tier: str = "complex",
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> Path:
    """A lifecycle dir whose events.log carries genuine machine rows.

    `monkeypatch` is required for any test that lets the verb WRITE: `log_event`
    resolves its target from the physical CWD (never from `project_root`), so
    without the chdir the emission lands in the developer's own checkout instead
    of the fixture.
    """
    feature_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    if monkeypatch is not None:
        monkeypatch.chdir(tmp_path)
    stamped = [dict(r) for r in rows]
    stamped[0]["tier"] = tier
    (feature_dir / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in stamped), encoding="utf-8"
    )
    for name in ("research.md", "spec.md", "review.md"):
        (feature_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    (feature_dir / "plan.md").write_text("# Plan\n\n- [x] T1\n", encoding="utf-8")
    return tmp_path


def test_fixture_actually_reaches_implement_rework(tmp_path: Path) -> None:
    """Guard the guard: the fixture's departure is events-derived, not artifact.

    `implement-rework` is an events-only state — the artifact detector has no
    route that can produce it. So if `resolve_lifecycle_phase` reports it, the
    machine rows genuinely decided, and the rest of this file is asserting
    against the state it thinks it is. Pinning the two detectors as *different*
    (rather than pinning the artifact detector's exact value, which is incidental
    here) is what keeps a fixture regression from silently collapsing them.
    """
    from cortex_command.common import detect_lifecycle_phase, resolve_lifecycle_phase

    feature_dir = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS) / "cortex" / "lifecycle" / "feat"
    assert resolve_lifecycle_phase(feature_dir)["route"] == "implement-rework"
    assert detect_lifecycle_phase(feature_dir)["phase"] != "implement-rework", (
        "fixture no longer distinguishes the two detectors — the artifact "
        "derivation should have no route to implement-rework at all"
    )


def test_rework_exits_to_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS, monkeypatch=monkeypatch)

    envelope = it.implement_transition(
        feature="feat", mode="transition", project_root=root
    )

    assert envelope["state"] == "rework-review", envelope
    assert envelope["transition_from"] == "implement-rework"
    assert envelope["transition_to"] == "review"
    assert "phase_transition" in envelope["emitted"]


def test_rework_exit_row_names_implement_rework_as_its_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The emitted row must depart `implement-rework`, not `implement`.

    A row claiming `from: implement` would leave the reducer's view of the rework
    cycle wrong and would false-match the earlier implement->review row.
    """
    root = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS, monkeypatch=monkeypatch)
    log_path = root / "cortex" / "lifecycle" / "feat" / "events.log"

    it.implement_transition(feature="feat", mode="transition", project_root=root)

    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    transitions = [(r.get("from"), r.get("to")) for r in rows if r.get("event") == "phase_transition"]
    assert ("implement-rework", "review") in transitions, transitions
    # The pre-existing implement->review row is untouched and unduplicated.
    assert transitions.count(("implement", "review")) == 1, transitions


def test_rework_exit_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running after the row landed writes nothing — the crash-repair property.

    The second call reports `review`, not `rework-review`, and that is correct
    rather than a leak: the departure is recomputed from the log each time, and
    by then the feature really has moved to `review`. It matches what the plain
    `implement` departure already does when re-run after its own exit row landed.
    What must hold — and what this pins — is that the log does not grow.
    """
    root = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS, monkeypatch=monkeypatch)
    log_path = root / "cortex" / "lifecycle" / "feat" / "events.log"

    first = it.implement_transition(feature="feat", mode="transition", project_root=root)
    after_first = log_path.read_text()
    second = it.implement_transition(feature="feat", mode="transition", project_root=root)

    assert first["emitted"] == ["phase_transition"]
    assert second["emitted"] == []
    assert log_path.read_text() == after_first


@pytest.mark.parametrize("tier", ["simple", "complex"])
def test_rework_never_routes_to_complete(
    tmp_path: Path, tier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The §4 criticality/tier rule is NOT re-run from implement-rework.

    A simple/low feature departing `implement` routes to `complete`. Departing
    `implement-rework` it must still route to `review`: the rework exists because
    a reviewer asked for changes, and skipping straight to complete would ship
    them unread.
    """
    root = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS, tier=tier, monkeypatch=monkeypatch)

    envelope = it.implement_transition(
        feature="feat", mode="transition", project_root=root
    )

    assert envelope["transition_to"] == "review", (
        f"tier={tier} rework routed to {envelope['transition_to']}"
    )


def test_plain_implement_departure_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-existing implement->{review,complete} behavior is untouched."""
    rows = _BASE_ROWS[:-1]  # stop at implement, no exit yet
    root = _scaffold(tmp_path, rows, tier="simple", monkeypatch=monkeypatch)

    envelope = it.implement_transition(
        feature="feat", mode="transition", project_root=root
    )

    assert envelope["transition_from"] == "implement"
    assert envelope["state"] == envelope["transition_to"] == "complete"


def test_advance_composes_the_rework_arm_without_refusing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The served loop can record the cycle: no gate-mismatch, no --from-state.

    This is the end the ticket reports as broken — `cortex-lifecycle-next` served
    `implement-rework` with `outgoing: []`, and threading its
    `expected_from_state` just returned a state no verb accepted as a departure.
    """
    root = _scaffold(tmp_path, _BASE_ROWS + _REWORK_ROWS, monkeypatch=monkeypatch)
    log_path = root / "cortex" / "lifecycle" / "feat" / "events.log"

    envelope = adv.advance(
        verb="implement-transition",
        feature="feat",
        mode="transition",
        log_path=log_path,
        project_root=root,
    )

    assert envelope.get("refusal") != "gate-mismatch", envelope.get("reason")
    assert envelope["state"] != "refused", envelope
