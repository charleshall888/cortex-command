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
                            the review→complete transition is routed through the
                            ``advance`` body. ``tasks_total`` and ``rework_cycles``
                            (always 0) are set.
  advanced-crash-recovery — review required and a real (``cycle >= 1``)
                            ``review_verdict`` is present but the feature is not
                            yet machine-complete; the review→complete transition
                            is routed through the ``advance`` body.
                            ``tasks_total`` and ``rework_cycles`` are set.
  missing-review          — review required but no real review event is
                            present; nothing written (the feature was expected
                            to be reviewed overnight but wasn't).
  error                   — an unexpected exception escaped ``advance_lifecycle``
                            itself; ``main`` catches it here so the CLI always
                            emits a JSON struct and exits 0.

Every state above is reached without raising — the verb always emits a
``{"state": ..., ...}`` struct on stdout and exits 0 (see ``main``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import (
    _resolve_user_project_root_from_cwd,
    detect_lifecycle_phase,
    reduce_lifecycle_state,
)
from cortex_command.lifecycle.advance import advance
from cortex_command.lifecycle.counters import count_rework_cycles, count_tasks

KNOWN_STATES = (
    "no-lifecycle-dir",
    "already-complete",
    "advanced-complete",
    "advanced-crash-recovery",
    "missing-review",
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
    review_required = tier == "complex" or criticality in _HIGH_CRITICALITY

    plan_path = feature_dir / "plan.md"

    if review_required and not _has_real_review_verdict(events):
        return {"state": "missing-review"}

    # FOLD (374 R15): the review→complete transition is decided + emitted by the
    # shared ``advance`` body, not hand-appended here. Gather the facts it needs
    # (the current detected phase to satisfy the claim's from_state gate — which
    # is artifact-based, ``common.detect_lifecycle_phase`` — and the review cycle)
    # and pass them as arguments. ``verdict=APPROVED`` composes the review.approved
    # arm (review_verdict → phase_transition review→complete); the cycle-qualified
    # presence check inside the body suppresses a duplicate verdict on the
    # crash-recovery path where a real verdict already exists.
    tasks_total, _ = count_tasks(plan_path)
    if not review_required:
        cycle = 0
        rework_cycles = 0
        state = "advanced-complete"
    else:
        cycle = _last_real_review_cycle(events)
        rework_cycles = count_rework_cycles(events_path)
        state = "advanced-crash-recovery"

    from_state = str(detect_lifecycle_phase(feature_dir).get("phase") or "review")
    advance(
        verb="review-verdict",
        feature=feature,
        verdict="APPROVED",
        cycle=cycle,
        drift="none",
        from_state=from_state,
        project_root=root,
    )

    return {
        "state": state,
        "tasks_total": tasks_total,
        "rework_cycles": rework_cycles,
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
