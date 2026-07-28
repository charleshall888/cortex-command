"""A refused lifecycle transition must be audible, not silent.

Session ``overnight-2026-07-28-1216`` reviewed #415 and the agent wrote a
``review.md`` ending in ``{"verdict": "APPROVED", "cycle": 1, "issues": []}`` —
but no ``review_verdict`` row reached the feature's ``events.log``, so
``cortex-morning-review-advance-lifecycle`` reported ``missing-review`` for a
feature that had in fact passed review.

``_advance_review_complete`` passes ``_current_phase()`` as ``from_state``, and
that detector disagrees with ``advance``'s own gate — reproduced live:
``_current_phase()`` returned ``complete`` while ``advance`` detected
``review``. The underlying disagreement is NOT fixed here (hardcoding a state
was tried and mismatches in the other direction on different artifact sets).
What is fixed is the silence: the arms were written "envelope ignored", so the
refusal left no trace at all.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cortex_command.overnight  # noqa: F401  (settles a circular import)
from cortex_command.pipeline.review_dispatch import _advance_review_complete

_FEATURE = "regression-feature"


def _seed_feature(tmp_path: Path) -> Path:
    d = tmp_path / "cortex" / "lifecycle" / _FEATURE
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n")
    (d / "plan.md").write_text("# Plan\n- [x] done\n")
    # Present by the time the arm runs — the review agent writes it first.
    (d / "review.md").write_text(
        '```json\n{"verdict": "APPROVED", "cycle": 1, "issues": []}\n```\n'
    )
    log = d / "events.log"
    log.write_text(
        json.dumps({"ts": "2026-07-28T00:00:00Z", "event": "lifecycle_start",
                    "feature": _FEATURE}) + "\n"
        + json.dumps({"ts": "2026-07-28T00:02:00Z", "event": "phase_transition",
                      "feature": _FEATURE, "from_phase": "implement",
                      "to_phase": "review"}) + "\n"
    )
    return log


def test_a_refused_verdict_transition_is_logged(tmp_path, caplog) -> None:
    """The operator must be able to see that the row went missing.

    Without this, the only symptom surfaces days later as ``missing-review``
    from a different tool, with nothing tying it back to the refusal.
    """
    log = _seed_feature(tmp_path)
    before = len(log.read_text().splitlines())

    with caplog.at_level(logging.WARNING, logger="cortex_command.pipeline.review_dispatch"):
        _advance_review_complete(_FEATURE, 1, log)

    appended = len(log.read_text().splitlines()) > before
    if appended:
        # The gate held on this artifact set — nothing to warn about.
        assert not any("REFUSED" in r.message for r in caplog.records)
        return

    assert any("REFUSED" in r.getMessage() for r in caplog.records), (
        "the transition recorded nothing AND logged nothing — this is the "
        "silent-loss mode that hid a passing review for a full session"
    )
    warning = next(r.getMessage() for r in caplog.records if "REFUSED" in r.getMessage())
    # The warning has to name the feature and the log it failed to write, or it
    # is not actionable.
    assert _FEATURE in warning
    assert str(log) in warning


def test_advance_failure_never_raises(tmp_path) -> None:
    """Best-effort remains the contract: a refusal must not fail the run."""
    log = _seed_feature(tmp_path)
    _advance_review_complete(_FEATURE, 1, log)  # must not raise
