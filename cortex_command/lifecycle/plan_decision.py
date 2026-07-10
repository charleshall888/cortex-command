"""cortex-lifecycle-plan-decision — order-enforcing plan-approval decision verb.

Composes the four multi-emission plan-approval arms the ``plan.md`` §4/§5 prose
used to narrate as back-to-back ``cortex-lifecycle-event`` calls. The function
body IS the ordering invariant: the exact per-arm event sequence lives here, so
the emit-before-commit stranding, drift, and buggy re-implementations that a
prose gate invited cannot recur. Returns ONE ``{state, ...}`` JSON envelope whose
``state`` echoes the decision discriminant the skill routes on.

The four decision arms and their EXACT ordered emissions:

  branch-mode-approved → (a) ``plan_approved`` with the caller's ``dispatch_choice``
                             (∈ {trunk, worktree-interactive, feature-branch})
                         (b) ``phase_transition`` from=plan to=implement
  wait-approved        → (a) ``plan_approved`` with ``dispatch_choice: wait``
                         (b) ``feature_paused`` — NO phase transition
  cancelled            → (a) ``lifecycle_cancelled`` — nothing else
  revise               → nothing (short-circuit return before any mutation)

Each emission independently presence-checks ``events.log`` first — a **parsed**
``event``-field match (plus the discriminating ``from``/``to`` fields for
``phase_transition``, which shares its event name with the feature's earlier
lifecycle transitions), never a substring — so re-running the whole verb after a
crash between emissions repairs rather than duplicates. The short-circuit arms
(``revise``, and the guarded error returns) return before the first mutating
step.

Emission goes ONLY through ``log_event`` (the flock + O_APPEND + spaced-json
writer) so each row is byte-identical to what the equivalent typed
``cortex-lifecycle-event`` subcommand (``plan-approved``, ``phase-transition``,
``feature-paused``, ``lifecycle-cancelled``) would produce — scan_lifecycle
substring-matches exact spacing, so a hand-rolled ``json.dumps`` would drift.

A slug-shape guard rejects path separators and ``..`` in ``--feature`` before any
filesystem access. ``main`` never tracebacks: any escaping exception (and the
guard) yields a ``{"state": "error", ...}`` envelope on stdout at exit 0.

Root resolution uses the cwd flavor (``_resolve_user_project_root_from_cwd``),
matching ``lifecycle_event``/``finalize``: ``log_event`` resolves its own write
target from the physical CWD and cannot be handed a root, so this verb reads the
same-tree ``events.log`` for the presence checks rather than diverging under
``CORTEX_REPO_ROOT``. Caller-passed args only (ADR-0019).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root_from_cwd
from cortex_command.lifecycle_event import log_event

_DECISIONS = ("branch-mode-approved", "wait-approved", "cancelled", "revise")

KNOWN_STATES = (
    "branch-mode-approved",
    "wait-approved",
    "cancelled",
    "revise",
    "error",
)

_VALID_MODES = ("trunk", "worktree-interactive", "feature-branch")


def _reject_unsafe_slug(feature: str) -> Optional[dict]:
    """Return an error envelope when *feature* is empty or carries a path
    separator / ``..`` — a path-traversal guard applied BEFORE any filesystem
    access. Returns None when the slug is safe to use as a directory component.
    """
    if not feature or "/" in feature or "\\" in feature or ".." in feature:
        return {
            "state": "error",
            "message": f"unsafe feature slug {feature!r}: no path separators or '..'",
        }
    return None


def _event_exists(
    events_log_path: Path, event_name: str, match_fields: Optional[dict] = None
) -> bool:
    """Return True when ``events.log`` already carries a row whose parsed
    ``event`` field equals *event_name* (and, when *match_fields* is given, whose
    every listed key equals the given value).

    Each line is parsed defensively (non-JSON / malformed lines skipped, never
    raised on) and matched on parsed fields — never a substring — so the guard
    never false-matches a body that merely mentions the event string. The
    ``match_fields`` refinement is load-bearing for ``phase_transition``: the
    feature's ``events.log`` already carries the earlier lifecycle transitions
    under the same event name, so only the ``from``/``to`` pair distinguishes the
    plan→implement row this verb owns. Missing/unreadable log → False.
    """
    if not events_log_path.exists():
        return False
    try:
        text = events_log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict) or event.get("event") != event_name:
            continue
        if match_fields and any(event.get(k) != v for k, v in match_fields.items()):
            continue
        return True
    return False


def _emit_plan_approved(events_log: Path, feature: str, dispatch_choice: str) -> bool:
    """Idempotent ``plan_approved`` emission. Re-asserts its postcondition via
    the presence check first; emits (and returns True) only when absent."""
    if _event_exists(events_log, "plan_approved"):
        return False
    log_event(
        event="plan_approved",
        feature=feature,
        fields=[("str", "dispatch_choice", dispatch_choice)],
    )
    return True


def plan_decision(
    *,
    feature: str,
    decision: str,
    dispatch_choice: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Compose the plan-approval decision into its ordered, idempotent emissions.

    Returns the ``{state, ...}`` envelope. ``state`` echoes *decision* on a
    handled arm, or ``"error"`` for the slug guard / an invalid ``dispatch_choice``
    on the branch-mode arm.
    """
    guard = _reject_unsafe_slug(feature)
    if guard is not None:
        return guard

    # revise: short-circuit before root resolution / any filesystem access.
    if decision == "revise":
        return {"state": "revise", "feature": feature, "emitted": []}

    if decision == "branch-mode-approved" and dispatch_choice not in _VALID_MODES:
        return {
            "state": "error",
            "message": (
                f"branch-mode-approved requires --dispatch-choice ∈ {_VALID_MODES}, "
                f"got {dispatch_choice!r}"
            ),
        }

    root = project_root or _resolve_user_project_root_from_cwd()
    events_log = root / "cortex" / "lifecycle" / feature / "events.log"
    emitted: List[str] = []

    if decision == "branch-mode-approved":
        # (a) plan_approved{dispatch_choice} — record the approved dispatch mode.
        if _emit_plan_approved(events_log, feature, dispatch_choice):
            emitted.append("plan_approved")
        # (b) phase_transition plan->implement — advance the lifecycle phase.
        if not _event_exists(
            events_log, "phase_transition", {"from": "plan", "to": "implement"}
        ):
            log_event(
                event="phase_transition",
                feature=feature,
                fields=[("str", "from", "plan"), ("str", "to", "implement")],
            )
            emitted.append("phase_transition")
        return {
            "state": "branch-mode-approved",
            "feature": feature,
            "dispatch_choice": dispatch_choice,
            "emitted": emitted,
        }

    if decision == "wait-approved":
        # (a) plan_approved{dispatch_choice: wait} — approval recorded, paused.
        if _emit_plan_approved(events_log, feature, "wait"):
            emitted.append("plan_approved")
        # (b) feature_paused — NO phase transition; the feature holds at plan.
        if not _event_exists(events_log, "feature_paused"):
            log_event(event="feature_paused", feature=feature)
            emitted.append("feature_paused")
        return {
            "state": "wait-approved",
            "feature": feature,
            "dispatch_choice": "wait",
            "emitted": emitted,
        }

    if decision == "cancelled":
        # (a) lifecycle_cancelled — nothing else.
        if not _event_exists(events_log, "lifecycle_cancelled"):
            log_event(event="lifecycle_cancelled", feature=feature)
            emitted.append("lifecycle_cancelled")
        return {"state": "cancelled", "feature": feature, "emitted": emitted}

    # Unreachable via the CLI (argparse pins --decision to _DECISIONS); a direct
    # caller passing an unknown decision gets an error envelope, never a crash.
    return {"state": "error", "message": f"unknown decision {decision!r}"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-plan-decision",
        description=(
            "Resolve the plan-approval decision to a single {state, ...} JSON "
            "struct on stdout, emitting the arm's exact ordered events "
            "(idempotently) via the shared events.log writer. Always exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--decision",
        required=True,
        choices=list(_DECISIONS),
        help="Plan-approval decision discriminant.",
    )
    parser.add_argument(
        "--dispatch-choice",
        choices=list(_VALID_MODES),
        default=None,
        help="Approved dispatch mode (required for the branch-mode-approved arm).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-plan-decision")
    args = _build_parser().parse_args(argv)
    try:
        result = plan_decision(
            feature=args.feature,
            decision=args.decision,
            dispatch_choice=args.dispatch_choice,
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
