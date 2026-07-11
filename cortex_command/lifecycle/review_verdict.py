"""cortex-lifecycle-review-verdict — order-enforcing review-verdict routing verb.

Composes the truncated ``review_verdict → (drift_protocol_breach) → phase_transition``
tail the ``review.md`` §4/§4a/§5 prose used to narrate as back-to-back
``cortex-lifecycle-event`` calls. The function body IS the ordering invariant:
the exact per-invocation event sequence lives here, so the emit-before-transition
stranding, drift, and duplicate ``review→implement-rework`` rows a prose gate
invited cannot recur. Returns ONE ``{state, ...}`` JSON envelope whose ``state``
echoes the routed outcome the skill routes on.

This verb owns ONLY the tail. The §4a drift auto-apply judgment LOOP (parse the
``## Suggested Requirements Update`` section, apply it, retry-on-failure) stays
PROSE and completes BEFORE this verb is called; when that loop exhausted its
retries the prose calls this verb with the post-hoc ``--breach`` / ``--retries``
args so the verb interleaves the ``drift_protocol_breach`` row in the correct
position (between the verdict row and the transition), rather than the prose
having to re-establish the ordering itself.

Verdict × cycle routing (the single discriminant the skill routes on):

  APPROVED (any cycle)            → phase_transition review→complete   (state: approved)
  CHANGES_REQUESTED cycle == 1    → phase_transition review→implement-rework
                                                                       (state: rework)
  CHANGES_REQUESTED cycle ≥ 2     → phase_transition review→escalated  (state: escalated)
  REJECTED (any cycle)            → phase_transition review→escalated  (state: escalated)

Exact ordered emissions per invocation:

  (a) ``review_verdict`` {verdict, cycle, requirements_drift}
  (b) ``drift_protocol_breach`` {state, suggestion, retries} — ONLY when ``--breach``
  (c) the routed ``phase_transition`` {from: review, to: <target>}

This verb is the **single owner** of ``phase_transition review→implement-rework``
(the duplicate emission in ``implement.md`` §3 is removed in Task 10, ordered
before this verb is wired into the prose in Task 11). Because a feature's
``events.log`` carries MANY ``phase_transition`` rows over its life (spec→plan,
plan→implement, …), the transition presence-check matches on ``event`` PLUS
``from``/``to`` — an event-name-only guard would false-skip against an earlier
transition.

``review_verdict`` presence-checks on ``event`` PLUS ``cycle``: the same feature
legitimately carries one ``review_verdict`` row per review cycle, so a cycle-2
verdict must still emit even though a cycle-1 verdict row exists. ``drift_protocol_breach``
presence-checks on ``event`` name alone (the typed subcommand carries no cycle
field to qualify on, and the byte-identical-to-typed-subcommand invariant forbids
inventing one) — this is sound for the dominant crash-recovery case (re-running
one invocation), with the documented residual that a genuine second breach in a
later cycle would be suppressed; see the report caveat.

Each emission is parsed-field matched (never a substring) and skipped when
already present, so re-running the whole verb after a crash between emissions —
or re-invoking after the rework transition already landed — repairs rather than
duplicates. Emission goes ONLY through ``log_event`` (the flock + O_APPEND +
spaced-json writer) so each row is byte-identical to the equivalent typed
``cortex-lifecycle-event`` subcommand (``review-verdict``, ``drift-protocol-breach``,
``phase-transition``).

A slug-shape guard rejects path separators and ``..`` in ``--feature`` before any
filesystem access. ``main`` never tracebacks: any escaping exception (and the
guard) yields a ``{"state": "error", ...}`` envelope on stdout at exit 0.

Root resolution uses the cwd flavor (``_resolve_user_project_root_from_cwd``),
matching ``lifecycle_event``/``finalize``/``plan_decision``: ``log_event``
resolves its own write target from the physical CWD and cannot be handed a root,
so this verb reads the same-tree ``events.log`` for the presence checks rather
than diverging under ``CORTEX_REPO_ROOT``. Caller-passed args only (ADR-0019).
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

_VERDICTS = ("APPROVED", "CHANGES_REQUESTED", "REJECTED")
_DRIFT_VALUES = ("none", "detected")

KNOWN_STATES = (
    "approved",
    "rework",
    "escalated",
    "error",
)

# Fixed field values the §4a breach path always emits (see review.md:91): the
# breach fires only after requirements_drift == "detected" and only when the
# suggestion section is missing/unparseable, so both are invariant. Only
# ``retries`` varies (the prose's --retries N).
_BREACH_STATE = "detected"
_BREACH_SUGGESTION = "missing"


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
    ``match_fields`` refinement is load-bearing for ``phase_transition`` (the
    feature carries earlier transitions under the same event name, so only the
    ``from``/``to`` pair distinguishes the row this verb owns) and for
    ``review_verdict`` (the feature carries one verdict row per cycle, so only
    ``cycle`` distinguishes this cycle's row). Missing/unreadable log → False.
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


def _route_target(verdict: str, cycle: int) -> str:
    """Map (verdict, cycle) to the routed ``phase_transition`` target phase.

    APPROVED → complete (any cycle); CHANGES_REQUESTED cycle 1 → implement-rework;
    everything else (CHANGES_REQUESTED cycle ≥ 2, or REJECTED any cycle) →
    escalated.
    """
    if verdict == "APPROVED":
        return "complete"
    if verdict == "CHANGES_REQUESTED" and cycle == 1:
        return "implement-rework"
    return "escalated"


_TARGET_TO_STATE = {
    "complete": "approved",
    "implement-rework": "rework",
    "escalated": "escalated",
}


def review_verdict(
    *,
    feature: str,
    verdict: str,
    cycle: int,
    drift: str,
    breach: bool = False,
    retries: int = 2,
    project_root: Optional[Path] = None,
) -> dict:
    """Compose the review-verdict tail into its ordered, idempotent emissions.

    Emits (a) ``review_verdict`` → (b) ``drift_protocol_breach`` (only when
    *breach*) → (c) the routed ``phase_transition``, each presence-checked
    independently. Returns the ``{state, ...}`` envelope; ``state`` echoes the
    routed outcome (``approved`` / ``rework`` / ``escalated``), or ``"error"``
    for the slug guard or an invalid verdict/drift value.
    """
    guard = _reject_unsafe_slug(feature)
    if guard is not None:
        return guard

    if verdict not in _VERDICTS:
        return {"state": "error", "message": f"unknown verdict {verdict!r}, expected {_VERDICTS}"}
    if drift not in _DRIFT_VALUES:
        return {"state": "error", "message": f"unknown drift {drift!r}, expected {_DRIFT_VALUES}"}

    target = _route_target(verdict, cycle)
    state = _TARGET_TO_STATE[target]

    root = project_root or _resolve_user_project_root_from_cwd()
    events_log = root / "cortex" / "lifecycle" / feature / "events.log"
    emitted: List[str] = []

    # (a) review_verdict{verdict, cycle, requirements_drift} — cycle-qualified
    #     presence check so a later cycle's verdict still emits.
    if not _event_exists(events_log, "review_verdict", {"cycle": cycle}):
        log_event(
            event="review_verdict",
            feature=feature,
            fields=[
                ("str", "verdict", verdict),
                ("json", "cycle", cycle),
                ("str", "requirements_drift", drift),
            ],
        )
        emitted.append("review_verdict")

    # (b) drift_protocol_breach{state, suggestion, retries} — ONLY when the
    #     prose's §4a drift-apply loop failed and passed --breach. Event-name
    #     presence check (the typed subcommand carries no cycle field to qualify).
    if breach and not _event_exists(events_log, "drift_protocol_breach"):
        log_event(
            event="drift_protocol_breach",
            feature=feature,
            fields=[
                ("str", "state", _BREACH_STATE),
                ("str", "suggestion", _BREACH_SUGGESTION),
                ("json", "retries", retries),
            ],
        )
        emitted.append("drift_protocol_breach")

    # (c) the routed phase_transition{from: review, to: <target>} — from/to
    #     qualified so it never false-skips against an earlier transition, and
    #     re-invocation after the transition already landed emits nothing.
    if not _event_exists(
        events_log, "phase_transition", {"from": "review", "to": target}
    ):
        log_event(
            event="phase_transition",
            feature=feature,
            fields=[("str", "from", "review"), ("str", "to", target)],
        )
        emitted.append("phase_transition")

    return {
        "state": state,
        "feature": feature,
        "verdict": verdict,
        "cycle": cycle,
        "drift": drift,
        "transition_to": target,
        "emitted": emitted,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-review-verdict",
        description=(
            "Resolve the review verdict×cycle to a single {state, ...} JSON "
            "struct on stdout, emitting the invocation's exact ordered events "
            "(review_verdict → optional drift_protocol_breach → routed "
            "phase_transition), idempotently, via the shared events.log writer. "
            "Always exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--verdict",
        required=True,
        choices=list(_VERDICTS),
        help="Review verdict discriminant.",
    )
    parser.add_argument(
        "--cycle",
        required=True,
        type=int,
        metavar="N",
        help="Review cycle number (1-based).",
    )
    parser.add_argument(
        "--drift",
        required=True,
        choices=list(_DRIFT_VALUES),
        help="Requirements-drift observation (review_verdict's requirements_drift field).",
    )
    parser.add_argument(
        "--breach",
        action="store_true",
        help=(
            "Post-hoc flag: the prose's §4a drift-apply loop exhausted its "
            "retries, so emit a drift_protocol_breach row between the verdict "
            "and the transition."
        ),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        metavar="N",
        help="Retry count recorded on the drift_protocol_breach row (with --breach).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-review-verdict")
    args = _build_parser().parse_args(argv)
    try:
        result = review_verdict(
            feature=args.feature,
            verdict=args.verdict,
            cycle=args.cycle,
            drift=args.drift,
            breach=args.breach,
            retries=args.retries,
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
