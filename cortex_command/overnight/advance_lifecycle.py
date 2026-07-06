"""cortex-morning-review-advance-lifecycle — composes morning-review
walkthrough §2b's mechanical per-feature lifecycle advancement into one
call: checkbox counting, the tier/criticality review gate, and the
synthetic ``events.log`` appends.

Before this consolidation, §2b narrated five to six steps of prose per
completed feature: check ``events.log`` existence and prior completion,
read tier/criticality via ``cortex-lifecycle-state``'s underlying reducer,
apply the review-required gate, count ``plan.md`` checkboxes, and hand-write
either four events (no review required), two events (crash recovery), or
none (missing review / already handled) to ``events.log``.

This verb reuses the SAME machinery ``cortex-lifecycle-state`` and
``cortex-lifecycle-counters`` already expose as library functions —
``cortex_command.common.reduce_lifecycle_state`` for the tier/criticality
fold and ``cortex_command.lifecycle.counters.count_tasks`` /
``count_rework_cycles`` for the two counters — rather than re-deriving
either. Event rows are appended via ``cortex_command.lifecycle_event.log_event``
(the same writer ``cortex-lifecycle-event``'s high-level subcommands funnel
through), never hand-assembled, so each row's ``ts``/``event``/``feature``
prefix and append-atomicity match every other lifecycle event in the repo.
``log_event`` resolves the project root from the physical CWD (ADR-independent
of ``CORTEX_REPO_ROOT``) exactly as it always has; this verb's own reads
(``events.log``, ``plan.md``) resolve the same root once via
``project_root`` (defaulting to the same CWD-based resolver) so a single
invocation's reads and writes agree by construction.

The four/two-event field shapes are intentionally NOT the ``review-verdict``/
``feature-complete`` HIGH-LEVEL subcommands in ``cortex_command.lifecycle_event``
(those require a ``--drift`` / support a ``--merge-anchor`` this walkthrough's
synthetic rows never carried) — calling ``log_event`` directly with exactly
the field list the prose specifies keeps the row shape byte-for-byte
unchanged from what the hand-written prose produced.

States:
  no-lifecycle-dir        — ``cortex/lifecycle/{feature}/events.log`` doesn't
                            exist; nothing written.
  already-complete        — a ``feature_complete`` event is already present;
                            nothing written.
  advanced-complete       — review not required (simple/low or simple/medium);
                            four synthetic events appended. ``tasks_total`` and
                            ``rework_cycles`` (always 0) are set.
  advanced-crash-recovery — review required and a real (``cycle >= 1``)
                            ``review_verdict`` is present but ``feature_complete``
                            is missing; two synthetic events appended.
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
from cortex_command.common import _resolve_user_project_root_from_cwd, reduce_lifecycle_state
from cortex_command.lifecycle.counters import count_rework_cycles, count_tasks
from cortex_command.lifecycle_event import log_event

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

    ``cycle >= 1`` distinguishes a real batch-runner review from this verb's
    own synthetic ``cycle: 0`` APPROVED row. ``bool`` is excluded even though
    it subclasses ``int`` in Python — a JSON boolean is never a valid cycle.
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
    if any(event.get("event") == "feature_complete" for event in events):
        return {"state": "already-complete"}

    reduction = reduce_lifecycle_state(events_path)
    tier = reduction.state.get("tier", "simple")
    criticality = reduction.state.get("criticality", "medium")
    review_required = tier == "complex" or criticality in _HIGH_CRITICALITY

    plan_path = feature_dir / "plan.md"

    if not review_required:
        tasks_total, _ = count_tasks(plan_path)
        log_event(
            event="phase_transition",
            feature=feature,
            fields=[("str", "from", "implement"), ("str", "to", "review")],
        )
        log_event(
            event="review_verdict",
            feature=feature,
            fields=[("str", "verdict", "APPROVED"), ("json", "cycle", 0)],
        )
        log_event(
            event="phase_transition",
            feature=feature,
            fields=[("str", "from", "review"), ("str", "to", "complete")],
        )
        log_event(
            event="feature_complete",
            feature=feature,
            fields=[
                ("json", "tasks_total", tasks_total),
                ("json", "rework_cycles", 0),
            ],
        )
        return {
            "state": "advanced-complete",
            "tasks_total": tasks_total,
            "rework_cycles": 0,
        }

    if not _has_real_review_verdict(events):
        return {"state": "missing-review"}

    # review required, a real review_verdict is present, feature_complete is
    # absent (the early "already-complete" check above already handles the
    # case where it IS present) — crash recovery.
    tasks_total, _ = count_tasks(plan_path)
    rework_cycles = count_rework_cycles(events_path)
    log_event(
        event="phase_transition",
        feature=feature,
        fields=[("str", "from", "review"), ("str", "to", "complete")],
    )
    log_event(
        event="feature_complete",
        feature=feature,
        fields=[
            ("json", "tasks_total", tasks_total),
            ("json", "rework_cycles", rework_cycles),
        ],
    )
    return {
        "state": "advanced-crash-recovery",
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
