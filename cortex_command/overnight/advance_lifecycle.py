"""cortex-morning-review-advance-lifecycle — composes morning-review
walkthrough §2b's mechanical per-feature lifecycle advancement into one
call: checkbox counting, the tier/criticality review gate, and the
transition emission.

Before this consolidation, §2b narrated five to six steps of prose per
completed feature: check ``events.log`` existence and prior completion,
read tier/criticality via ``cortex-lifecycle-state``'s underlying reducer,
apply the review-required gate, count ``plan.md`` checkboxes, and hand-write
either four events (no review required), two events (crash recovery), or
none (missing review / already handled) to ``events.log``.

**374 Phase-4 fold (R15 write path):** this module no longer DECIDES or
appends transition rows itself. Its artifact reads (``events.log``,
``plan.md``) are demoted to *input-gathering*; the transition
decision + emission is owned by the shared ``advance`` verb body
(``cortex_command.lifecycle.advance.advance``), which composes the B1 verb
cores inside one gate-checked body and emits the legacy vocabulary
(``review_verdict`` → ``phase_transition`` review→complete) idempotently
(#397 retired the claim/commit machine rows). This module gathers the facts the overnight
gate needs (tier/criticality, whether a real review ran, the current detected
phase) and passes them as arguments; it emits NO transition-vocabulary rows of
its own (the positive fold-completion discriminator in
``tests/test_fold_completion.py`` fails if a ``log_event``/``log_event_at``
call re-introduces one).

Completion is signalled by the ``phase_transition`` review→complete row the
``advance`` body emits — the events-first authority (ADR-0025). The legacy
``feature_complete`` telemetry row this path used to hand-append is NOT emitted
by the ``advance``/B1 bodies (the served transition table does not list it);
``tasks_total``/``rework_cycles`` are still computed for the returned envelope
but no longer land on an events.log row. Downstream metrics
(``cortex_command/pipeline/metrics.py:extract_feature_metrics``) therefore
detect completion events-first — off the ``phase_transition→complete`` row
rather than ``feature_complete`` — and default a fold-completed feature's
``merge_anchor`` to ``"review"``.

States:
  no-lifecycle-dir        — ``cortex/lifecycle/{feature}/events.log`` doesn't
                            exist; nothing written.
  already-complete        — the events.log already carries a machine-complete
                            row (``phase_transition`` review→complete, or a
                            terminal ``feature_complete``/``feature_wontfix``/
                            ``lifecycle_cancelled``); nothing written.
  advanced-complete       — review not required (simple/low or simple/medium);
                            the implement→complete transition is routed through
                            the ``advance`` body's implement-transition arm.
                            ``tasks_total`` and ``rework_cycles`` (always 0) are
                            set.
  advanced-crash-recovery — review required and a real (``cycle >= 1``)
                            ``review_verdict`` is present but the feature is not
                            yet machine-complete; the review→complete transition
                            is routed through the ``advance`` body.
                            ``tasks_total`` and ``rework_cycles`` are set.
  missing-review          — review required but no real review event is
                            present; nothing written (the feature was expected
                            to be reviewed overnight but wasn't). Also returned
                            when the reduction is corrupted (tier/criticality
                            unknowable, so review is the cautious default), and
                            when the implement-exit arm routes somewhere other
                            than ``complete`` — its own verdict is that this
                            feature needs review, so reporting completion would
                            be a lie.
  advance-refused         — the ``advance`` body refused the transition (an
                            unsatisfied gate: wrong departure phase, an active
                            enforcement-bearing pause, or an unmerged recorded
                            PR). NO completion row was written, so the feature is
                            NOT complete. A warning naming the feature and its
                            events log is logged. Best-effort still holds: a
                            refusal returns a state, it never raises or fails the
                            run — it just stops being silent, which is what let a
                            passing review read as ``missing-review`` for a whole
                            session.
  error                   — an unexpected exception escaped ``advance_lifecycle``
                            itself; ``main`` catches it here so the CLI always
                            emits a JSON struct and exits 0.

Every state above is reached without raising — the verb always emits a
``{"state": ..., ...}`` struct on stdout and exits 0 (see ``main``).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    _resolve_user_project_root_from_cwd,
    reduce_lifecycle_state,
)
from cortex_command.lifecycle.advance import advance
from cortex_command.lifecycle.counters import count_rework_cycles, count_tasks

logger = logging.getLogger(__name__)

KNOWN_STATES = (
    "no-lifecycle-dir",
    "already-complete",
    "advanced-complete",
    "advanced-crash-recovery",
    "missing-review",
    "advance-refused",
    "error",
)

_HIGH_CRITICALITY = {"high", "critical"}


def _read_events(events_path: Path) -> list[dict]:
    """Tolerantly parse *events_path* into a list of dicts.

    A torn or non-JSON line is skipped rather than raising, mirroring the
    events.log tolerant-reader convention shared by
    ``cortex_command.lifecycle.counters.count_rework_cycles`` and
    ``cortex_command.common.reduce_lifecycle_state``.
    """
    try:
        text = events_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _has_real_review_verdict(events: list[dict]) -> bool:
    """True iff a ``review_verdict`` event with an integer ``cycle >= 1`` is present.

    ``cycle >= 1`` distinguishes a real batch-runner review from a synthetic
    ``cycle: 0`` APPROVED row. ``bool`` is excluded even though it subclasses
    ``int`` in Python — a JSON boolean is never a valid cycle.
    """
    for event in events:
        if event.get("event") != "review_verdict":
            continue
        cycle = event.get("cycle")
        if isinstance(cycle, bool) or not isinstance(cycle, int):
            continue
        if cycle >= 1:
            return True
    return False


def _last_real_review_cycle(events: list[dict]) -> int:
    """Return the last real (``cycle >= 1``) ``review_verdict`` cycle, or 0.

    Used as the ``cycle`` argument threaded into the ``advance`` review-verdict
    body on the crash-recovery path so the shared body's cycle-qualified
    presence check recognises the already-present real verdict row and emits
    only the missing ``phase_transition`` review→complete (never a duplicate
    verdict).
    """
    last = 0
    for event in events:
        if event.get("event") != "review_verdict":
            continue
        cycle = event.get("cycle")
        if isinstance(cycle, bool) or not isinstance(cycle, int):
            continue
        if cycle >= 1:
            last = cycle
    return last


# Events whose presence means the feature is already MACHINE-complete: a
# ``phase_transition`` landing on ``complete`` (the events-first completion
# signal, ADR-0025) or any terminal row. Mirrors ``common._phase_from_machine_rows``'
# terminal handling so the already-complete short-circuit keys on the same
# events-authority the shared resolver uses — a hand-edited plan.md never
# flips it.
_TERMINAL_EVENTS = frozenset({"feature_complete", "feature_wontfix", "lifecycle_cancelled"})


def _is_machine_complete(events: list[dict]) -> bool:
    """True when *events* already establishes a complete/terminal machine state."""
    for event in events:
        etype = event.get("event")
        if etype in _TERMINAL_EVENTS:
            return True
        if etype == "phase_transition" and event.get("to") == "complete":
            return True
    return False


def _refusal_state(envelope: object, feature: str, events_path: Path) -> Optional[dict]:
    """Return the ``advance-refused`` state when *envelope* is a refusal, else None.

    This call site used to set its ``state`` BEFORE calling ``advance`` and return
    it unconditionally, so a refusal was reported to the CLI as success with no
    events written and no warning — a worse failure surface than a loud one,
    since the operator had nothing to act on. ``review_dispatch._advance_or_warn``
    is the sibling shape; best-effort still holds, so this returns a state rather
    than raising.
    """
    if not isinstance(envelope, dict) or envelope.get("state") != "refused":
        return None
    logger.warning(
        "lifecycle advance REFUSED for %s (%s): %s — %s carries no completion "
        "row, so the feature is NOT complete",
        feature,
        envelope.get("refusal"),
        envelope.get("reason"),
        events_path,
    )
    return {"state": "advance-refused"}


def _envelope_route(envelope: object) -> Optional[str]:
    """Return the destination state *envelope* actually moved to, or None.

    The implement-transition arm's ``state`` IS its resolved route
    (``"review"``/``"complete"``); ``to_state`` carries the same fact from the
    table row and survives the replay short-circuit.
    """
    if not isinstance(envelope, dict):
        return None
    to_state = envelope.get("to_state")
    return str(to_state) if to_state is not None else None


def advance_lifecycle(feature: str, project_root: Optional[Path] = None) -> dict:
    """Advance one completed feature's lifecycle per walkthrough §2b.

    Never raises — every failure/skip mode returns a distinct ``state``
    (see the module docstring), so the CLI's exit-0 contract holds by
    construction rather than relying on a try/except in ``main``.
    """
    root = project_root or _resolve_user_project_root_from_cwd()
    feature_dir = root / "cortex" / "lifecycle" / feature
    events_path = feature_dir / "events.log"

    if not events_path.exists():
        return {"state": "no-lifecycle-dir"}

    events = _read_events(events_path)
    if _is_machine_complete(events):
        return {"state": "already-complete"}

    reduction = reduce_lifecycle_state(events_path)
    tier = reduction.state.get("tier", "simple")
    criticality = reduction.state.get("criticality", "medium")
    # ``corrupted`` must be review-required, matching what the arm itself will
    # decide: ``implement_transition._resolve_route`` treats a corrupted
    # reduction as ("review", "complex"). When the two rules disagree, this
    # caller takes the no-review branch, the arm routes to ``review``, and the
    # feature lands ``phase_transition{to: "review"}`` under an
    # ``advanced-complete`` report — and since ``_is_machine_complete`` matches
    # only ``to: "complete"``, every later run replays and reports completion
    # forever. Any future edit to either rule must change both.
    review_required = (
        tier == "complex" or criticality in _HIGH_CRITICALITY or reduction.corrupted
    )

    plan_path = feature_dir / "plan.md"

    if review_required and not _has_real_review_verdict(events):
        return {"state": "missing-review"}

    # FOLD (374 R15): the transition is decided + emitted by the shared ``advance``
    # body, not hand-appended here. Neither branch supplies ``from_state``: a verb
    # has exactly one departure state across the closed table, so the composed arm
    # already carries the correct expected phase, and the gate then compares two
    # readings of the same events-first oracle. Deriving one from artifacts here is
    # what silently refused every transition on a log carrying real machine rows.
    tasks_total, _ = count_tasks(plan_path)

    if not review_required:
        # The feature never entered review, so the review-verdict arm is the
        # wrong arm — it departs from ``review`` and would fabricate a synthetic
        # APPROVED verdict for something nobody reviewed. The implement-exit arm
        # resolves its own route from the same reduction and emits
        # phase_transition implement→<route>.
        envelope = advance(
            verb="implement-transition",
            feature=feature,
            mode="transition",
            project_root=root,
        )
        refused = _refusal_state(envelope, feature, events_path)
        if refused is not None:
            return refused
        # Assert the route we actually got. Requirement 5 should make a non-complete
        # route unreachable, but reporting completion on the arm's say-so without
        # checking is precisely how the divergence above stayed invisible.
        if _envelope_route(envelope) != "complete":
            return {"state": "missing-review"}
        return {"state": "advanced-complete", "tasks_total": tasks_total, "rework_cycles": 0}

    # Crash recovery: a real verdict exists but the completion row is missing.
    # ``verdict=APPROVED`` composes the review.approved arm (review_verdict →
    # phase_transition review→complete); the cycle-qualified presence check inside
    # the body suppresses a duplicate verdict against the already-present one.
    envelope = advance(
        verb="review-verdict",
        feature=feature,
        verdict="APPROVED",
        cycle=_last_real_review_cycle(events),
        drift="none",
        project_root=root,
    )
    refused = _refusal_state(envelope, feature, events_path)
    if refused is not None:
        return refused

    return {
        "state": "advanced-crash-recovery",
        "tasks_total": tasks_total,
        "rework_cycles": count_rework_cycles(events_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-morning-review-advance-lifecycle",
        description=(
            "Advance one completed feature's lifecycle per morning-review "
            "walkthrough §2b: checkbox counting, the tier/criticality review "
            "gate, and the synthetic events.log appends. Emits a single "
            "{state, ...} struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, help="Lifecycle feature slug.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-morning-review-advance-lifecycle")
    args = _build_parser().parse_args(argv)
    try:
        result = advance_lifecycle(args.feature)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
