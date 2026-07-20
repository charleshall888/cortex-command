"""R11 — advance's gate-mismatch refusal carries an additive ``preferred_remedy``.

The from-state gate refuses when the events-first resolved phase does not match
the arm's expected from_state (ADR-0025). This test pins the refusal envelope's
additive ``preferred_remedy`` field: it recommends re-sync — re-run
``cortex-lifecycle-next`` and thread its ``advance_contract.expected_from_state``
through ``--from-state`` — and never echoes the detected phase back as a fix.

The field is purely additive: the existing refusal contract (``refusal ==
"gate-mismatch"``, ``sanctioned_override``, the ``{state, ...}`` envelope) is
retained verbatim.

Fixture pattern mirrors ``tests/test_advance_spec_approve_writeback.py``: a
throwaway lifecycle dir under ``tmp_path`` whose events.log resolves the phase to
``specify`` (a ``research -> specify`` transition), while the invoked
``plan-decision`` arm expects from_state ``plan`` — a guaranteed gate mismatch.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.lifecycle import advance as adv


def _scaffold(tmp_path: Path) -> Path:
    """Build a lifecycle dir whose events.log resolves the phase to ``specify``
    (a single ``research -> specify`` phase_transition). Returns *tmp_path* — the
    project root advance anchors its same-tree events.log resolution to."""
    feature_dir = tmp_path / "cortex" / "lifecycle" / "feat"
    feature_dir.mkdir(parents=True)
    (feature_dir / "events.log").write_text(
        json.dumps({"event": "phase_transition", "feature": "feat",
                    "from": "research", "to": "specify"}) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_gate_mismatch_refusal_carries_preferred_remedy(tmp_path: Path) -> None:
    """The resolved phase is ``specify``; ``plan-decision branch-mode-approved``
    expects from_state ``plan`` — so the from-state gate refuses. The refusal
    envelope keeps every existing field AND gains ``preferred_remedy``."""
    root = _scaffold(tmp_path)

    envelope = adv.advance(
        verb="plan-decision",
        feature="feat",
        decision="branch-mode-approved",
        dispatch_choice="trunk",
        project_root=root,
    )

    # Existing gate-mismatch contract is retained verbatim.
    assert envelope["state"] == "refused"
    assert envelope["refusal"] == "gate-mismatch"
    assert envelope["sanctioned_override"] == adv._SANCTIONED_OVERRIDE

    # The additive field: names the re-sync surface and its contract field, and
    # never suggests echoing the detected phase back as the fix.
    remedy = envelope["preferred_remedy"]
    assert isinstance(remedy, str) and remedy
    assert "cortex-lifecycle-next" in remedy
    assert "advance_contract.expected_from_state" in remedy
    assert "--from-state" in remedy
    # Must not train the operator to feed the detected phase (`specify`) back in.
    assert "specify" not in remedy
