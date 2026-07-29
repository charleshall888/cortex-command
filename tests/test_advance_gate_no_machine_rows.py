"""The from-state gate must not refuse when the log carries no machine rows.

``resolve_lifecycle_phase`` is events-first only *where machine rows exist*;
with none it degrades to ``detect_lifecycle_phase`` — the artifact-presence
LEGACY FALLBACK the gate's own contract forbids consulting. Gating on that
derivation makes the first machine row unwritable whenever the artifacts
disagree, and the refusal is self-perpetuating: no row -> fallback -> refuse ->
still no row.

Reproduced from session ``overnight-2026-07-29-0145``, where feature #412 ran
plan -> implement -> review -> merged and emitted **zero** lifecycle rows:

    implement-transition REFUSED (gate-mismatch): detected phase 'plan'
        does not match expected from_state 'implement'
    review-verdict       REFUSED (gate-mismatch): detected phase 'complete'
        does not match expected from_state 'review'

Both against an events.log that never changed — the artifact detector simply
reported a different phase before and after ``review.md`` landed.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.lifecycle import advance as adv


def _scaffold(tmp_path: Path, *, with_review: bool = False) -> Path:
    """A lifecycle dir whose events.log holds only NON-machine rows.

    Mirrors #412's real log: a refine-era chain with no ``phase_transition`` and
    no terminal event, so ``_phase_from_machine_rows`` returns ``None`` and the
    artifact detector decides the phase.
    """
    feature_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    rows = [
        {"event": "lifecycle_start", "feature": "feat", "tier": "complex"},
        {"event": "clarify_critic", "feature": "feat", "status": "ok"},
        {"event": "complexity_override", "feature": "feat",
         "from": "simple", "to": "complex"},
        {"event": "spec_approved", "feature": "feat", "decision": "approved"},
    ]
    (feature_dir / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")
    (feature_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (feature_dir / "plan.md").write_text(
        "# Plan\n\n- [x] Task 1\n- [x] Task 2\n", encoding="utf-8"
    )
    if with_review:
        (feature_dir / "review.md").write_text("# Review\n", encoding="utf-8")
    return tmp_path


def test_implement_transition_not_refused_without_machine_rows(tmp_path: Path) -> None:
    """The implement->review entry transition fires on a machine-row-free log."""
    root = _scaffold(tmp_path)
    log_path = root / "cortex" / "lifecycle" / "feat" / "events.log"

    envelope = adv.advance(
        verb="implement-transition",
        feature="feat",
        mode="transition",
        log_path=log_path,
        project_root=root,
    )

    assert envelope.get("refusal") != "gate-mismatch", (
        f"gate refused with no events-derived evidence to gate against: "
        f"{envelope.get('reason')}"
    )
    assert envelope["state"] != "refused", envelope

    # The row it exists to write actually lands.
    written = log_path.read_text(encoding="utf-8")
    assert '"phase_transition"' in written, written


def test_gate_still_refuses_when_machine_rows_contradict(tmp_path: Path) -> None:
    """The gate is narrowed, not removed: real recorded history still binds."""
    root = _scaffold(tmp_path)
    feature_dir = root / "cortex" / "lifecycle" / "feat"
    log_path = feature_dir / "events.log"
    # A genuine machine row placing the feature at `specify` — which contradicts
    # implement-transition's expected from_state of `implement`.
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "phase_transition", "feature": "feat",
                             "from": "research", "to": "specify"}) + "\n")

    envelope = adv.advance(
        verb="implement-transition",
        feature="feat",
        mode="transition",
        log_path=log_path,
        project_root=root,
    )

    assert envelope["state"] == "refused"
    assert envelope["refusal"] == "gate-mismatch"
