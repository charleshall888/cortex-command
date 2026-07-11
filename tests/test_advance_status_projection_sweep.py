"""Arm-g: status-projection differential sweep across the 374 Phase-4 cutover.

Spec R15 acceptance (b): the events-first status projection
(``common.resolve_lifecycle_phase`` — the ADR-0025 authority every migrated
read-path caller funnels through) must be **byte-identical pre/post cutover**
for the transitions the fold rewrites. Before the fold, the two overnight/pipeline
modules hand-appended the transition rows; after, they route the decision +
emission through the shared ``advance`` body. This sweep pins the exact pre-fold
row sequences as fixtures, runs the REAL post-fold code paths, and asserts the
resolved projection dict is equal for every scenario.

The projection is preserved because completion rides on ``phase_transition``
review→complete (which ``_phase_from_machine_rows`` maps to ``complete`` exactly
as the pre-fold ``feature_complete`` terminal did), and the advance-authored
additive fields (``invocation_id``) and machine rows
(``advance_started``/``advance_committed``) are invisible to the resolver (not in
its phase-significant / terminal sets).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import order matters: importing the overnight package first fully initialises
# the overnight <-> pipeline import cycle so review_dispatch is importable
# (a pre-existing standalone-import cycle, unrelated to the fold).
from cortex_command.overnight import advance_lifecycle as al  # noqa: E402
from cortex_command.pipeline import review_dispatch as rd  # noqa: E402
from cortex_command.common import resolve_lifecycle_phase  # noqa: E402

FEATURE = "feat"


def _feature_dir(root: Path) -> Path:
    d = root / "cortex" / "lifecycle" / FEATURE
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_events(feature_dir: Path, rows: list[dict]) -> None:
    (feature_dir / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


# Plan bodies (checked/total feed the projection's checked/total fields, which
# must also match — they are read-side artifact facts, identical pre/post).
_PLAN_MIXED = "- **Status**: [x] a\n- **Status**: [ ] b\n- **Status**: [x] c\n"
_PLAN_DONE = "- **Status**: [x] a\n- **Status**: [x] b\n"

_LS_SIMPLE = {"event": "lifecycle_start", "feature": FEATURE, "tier": "simple", "criticality": "medium"}
_LS_COMPLEX = {"event": "lifecycle_start", "feature": FEATURE, "tier": "complex", "criticality": "medium"}


# ---------------------------------------------------------------------------
# Scenarios: (id, plan_md, pre_rows, seed_rows, post_producer)
#   pre_rows       — the exact pre-fold events.log the hand-appended code produced.
#   seed_rows      — the pre-transition seed the post-fold path starts from.
#   post_producer  — runs the REAL folded code against a seeded feature dir.
# ---------------------------------------------------------------------------


def _post_al(feature_dir: Path) -> None:
    """advance_lifecycle folds its completion through the advance body."""
    al.advance_lifecycle(FEATURE, project_root=feature_dir.parents[2])


def _post_rd_approved(feature_dir: Path) -> None:
    """review_dispatch's APPROVED path: entry implement→review then review→complete,
    both via the folded advance helpers (the exact calls dispatch_review makes)."""
    log = feature_dir / "events.log"
    rd._advance_to_review(FEATURE, log)
    rd._advance_review_complete(FEATURE, 1, log)


def _post_rd_rejected(feature_dir: Path) -> None:
    """review_dispatch's REJECTED path: only the entry implement→review transition
    is recorded (the informational verdict row is dropped by the fold)."""
    rd._advance_to_review(FEATURE, feature_dir / "events.log")


SCENARIOS = [
    pytest.param(
        _PLAN_MIXED,
        # pre-fold no-review completion: 4 hand-appended rows.
        [
            _LS_SIMPLE,
            {"event": "phase_transition", "feature": FEATURE, "from": "implement", "to": "review"},
            {"event": "review_verdict", "feature": FEATURE, "verdict": "APPROVED", "cycle": 0},
            {"event": "phase_transition", "feature": FEATURE, "from": "review", "to": "complete"},
            {"event": "feature_complete", "feature": FEATURE, "tasks_total": 2, "rework_cycles": 0},
        ],
        [_LS_SIMPLE],
        _post_al,
        id="advance_lifecycle-no-review-complete",
    ),
    pytest.param(
        _PLAN_DONE,
        # pre-fold crash-recovery: 2 hand-appended rows over a real-review seed.
        [
            _LS_COMPLEX,
            {"event": "review_verdict", "feature": FEATURE, "verdict": "CHANGES_REQUESTED", "cycle": 1},
            {"event": "review_verdict", "feature": FEATURE, "verdict": "APPROVED", "cycle": 2},
            {"event": "phase_transition", "feature": FEATURE, "from": "review", "to": "complete"},
            {"event": "feature_complete", "feature": FEATURE, "tasks_total": 2, "rework_cycles": 1},
        ],
        [
            _LS_COMPLEX,
            {"event": "review_verdict", "feature": FEATURE, "verdict": "CHANGES_REQUESTED", "cycle": 1},
            {"event": "review_verdict", "feature": FEATURE, "verdict": "APPROVED", "cycle": 2},
        ],
        _post_al,
        id="advance_lifecycle-crash-recovery-complete",
    ),
    pytest.param(
        _PLAN_DONE,
        # pre-fold review_dispatch APPROVED: entry + verdict + transition + complete.
        [
            _LS_COMPLEX,
            {"event": "plan_approved", "feature": FEATURE, "dispatch_choice": "trunk"},
            {"event": "phase_transition", "feature": FEATURE, "from": "implement", "to": "review"},
            {"event": "review_verdict", "feature": FEATURE, "verdict": "APPROVED", "cycle": 1},
            {"event": "phase_transition", "feature": FEATURE, "from": "review", "to": "complete"},
            {"event": "feature_complete", "feature": FEATURE, "merge_anchor": "review"},
        ],
        [
            _LS_COMPLEX,
            {"event": "plan_approved", "feature": FEATURE, "dispatch_choice": "trunk"},
        ],
        _post_rd_approved,
        id="review_dispatch-approved-complete",
    ),
    pytest.param(
        _PLAN_DONE,
        # pre-fold review_dispatch REJECTED: entry + informational verdict (no transition).
        [
            _LS_COMPLEX,
            {"event": "plan_approved", "feature": FEATURE, "dispatch_choice": "trunk"},
            {"event": "phase_transition", "feature": FEATURE, "from": "implement", "to": "review"},
            {"event": "review_verdict", "feature": FEATURE, "verdict": "REJECTED", "cycle": 1},
        ],
        [
            _LS_COMPLEX,
            {"event": "plan_approved", "feature": FEATURE, "dispatch_choice": "trunk"},
        ],
        _post_rd_rejected,
        id="review_dispatch-rejected-stays-review",
    ),
]


@pytest.mark.parametrize("plan_md, pre_rows, seed_rows, post_producer", SCENARIOS)
def test_status_projection_byte_identical_pre_post_cutover(
    tmp_path: Path, plan_md: str, pre_rows, seed_rows, post_producer
) -> None:
    # PRE: the pinned hand-appended pre-fold events.log.
    pre_root = tmp_path / "pre"
    pre_dir = _feature_dir(pre_root)
    (pre_dir / "plan.md").write_text(plan_md, encoding="utf-8")
    _write_events(pre_dir, pre_rows)
    pre_proj = resolve_lifecycle_phase(pre_dir)

    # POST: the same seed, advanced through the REAL folded code path.
    post_root = tmp_path / "post"
    post_dir = _feature_dir(post_root)
    (post_dir / "plan.md").write_text(plan_md, encoding="utf-8")
    _write_events(post_dir, seed_rows)
    post_producer(post_dir)
    post_proj = resolve_lifecycle_phase(post_dir)

    assert post_proj == pre_proj, (
        "status projection diverged across the cutover:\n"
        f"  pre  = {pre_proj}\n  post = {post_proj}"
    )
