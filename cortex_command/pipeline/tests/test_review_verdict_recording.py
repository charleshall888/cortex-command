"""An APPROVED overnight review must durably record its verdict and transition.

Session ``overnight-2026-07-28-1216`` reviewed #415 and the agent wrote a
``review.md`` ending in ``{"verdict": "APPROVED", "cycle": 1, "issues": []}`` —
but no ``review_verdict`` row reached the feature's ``events.log``, so
``cortex-morning-review-advance-lifecycle`` reported ``missing-review`` for a
feature that had in fact passed review.

The cause: ``_advance_review_complete`` derived ``from_state`` from
``detect_lifecycle_phase`` (the artifact-presence LEGACY FALLBACK) while
``advance``'s gate resolves phase events-first, so the gate refused and both
required rows — which share one gated emission list — were lost together. The
arm now supplies no ``from_state``, letting the closed transition table's own
``review`` stand.

The fixture below seeds the machine rows a real overnight run emits, keyed
``"from"``/``"to"``. The previous one used a misspelled key pair no producer
writes and ``common.py`` cannot read, so its row was invisible to the
events-first resolver and BOTH detectors fell back to artifacts — they could not
disagree by construction, and the regression this file exists to catch was
unobservable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cortex_command.overnight  # noqa: F401  (settles a circular import)
from cortex_command.common import resolve_lifecycle_phase
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
    # The machine rows a real run emits, in order, with the "from"/"to" keys
    # every producer actually writes. Without these the events-first resolver
    # falls back to the artifact detector and the gate becomes a tautology.
    rows = [
        {"ts": "2026-07-28T00:00:00Z", "event": "lifecycle_start", "feature": _FEATURE,
         "tier": "complex", "criticality": "medium"},
        {"ts": "2026-07-28T00:01:00Z", "event": "phase_transition", "feature": _FEATURE,
         "from": "specify", "to": "plan"},
        {"ts": "2026-07-28T00:02:00Z", "event": "plan_approved", "feature": _FEATURE,
         "dispatch_choice": "trunk"},
        {"ts": "2026-07-28T00:03:00Z", "event": "phase_transition", "feature": _FEATURE,
         "from": "plan", "to": "implement"},
        {"ts": "2026-07-28T00:04:00Z", "event": "phase_transition", "feature": _FEATURE,
         "from": "implement", "to": "review"},
    ]
    log = d / "events.log"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return log


def _appended(log: Path, event: str, **fields) -> dict | None:
    """Return the last row of type *event* matching *fields*, or None."""
    found = None
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("event") != event:
            continue
        if any(row.get(k) != v for k, v in fields.items()):
            continue
        found = row
    return found


def test_the_approved_verdict_and_transition_are_recorded(tmp_path) -> None:
    """Both rows must land. This pins ONE outcome deliberately.

    The previous version of this test branched on whether anything was appended
    and asserted-and-passed either way, so it protected nothing: the bug it was
    written for passed it cleanly.
    """
    log = _seed_feature(tmp_path)
    # The gate's own oracle sees the feature at review before the call.
    assert resolve_lifecycle_phase(log.parent)["phase"] == "review"

    _advance_review_complete(_FEATURE, 1, log)

    verdict_row = _appended(log, "review_verdict", verdict="APPROVED", cycle=1)
    assert verdict_row is not None, (
        "the APPROVED review recorded no review_verdict row — this is the "
        "silent-loss mode that hid a passing review for a full session"
    )
    complete_row = _appended(log, "phase_transition", **{"from": "review", "to": "complete"})
    assert complete_row is not None, (
        "the APPROVED review recorded no phase_transition review→complete row; "
        "downstream completion detection reads exactly this row"
    )


def test_a_refused_verdict_transition_is_logged(tmp_path, caplog) -> None:
    """A genuine refusal must be audible, not silent.

    Best-effort stays the contract, so a refusal cannot fail the run — which is
    precisely why it has to leave a trace. Here the log never reached ``review``
    (no implement→review row), so the gate is right to refuse.
    """
    log = _seed_feature(tmp_path)
    rows = [
        line for line in log.read_text().splitlines()
        if '"to": "review"' not in line
    ]
    log.write_text("".join(line + "\n" for line in rows))
    before = len(log.read_text().splitlines())

    with caplog.at_level(logging.WARNING, logger="cortex_command.pipeline.review_dispatch"):
        _advance_review_complete(_FEATURE, 1, log)

    assert len(log.read_text().splitlines()) == before, "refused, so nothing may be appended"
    warning = next(r.getMessage() for r in caplog.records if "REFUSED" in r.getMessage())
    # The warning has to name the feature and the log it failed to write, or it
    # is not actionable.
    assert _FEATURE in warning
    assert str(log) in warning


def test_advance_failure_never_raises(tmp_path) -> None:
    """Best-effort remains the contract: a refusal must not fail the run."""
    log = _seed_feature(tmp_path)
    _advance_review_complete(_FEATURE, 1, log)  # must not raise
