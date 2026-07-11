"""cortex-lifecycle-implement-transition — order-enforcing implement-cluster verb.

Composes the two mechanical emissions the ``implement.md`` §2/§4 prose used to
narrate as bare ``cortex-lifecycle-event`` calls: the per-batch ``batch_dispatch``
and the §4 phase-exit transition. The function body IS the ordering/routing
invariant, so the §4 routing rule ("Review when criticality ∈ {high, critical} OR
tier = complex, else Complete") lives HERE rather than in prose — a prose gate
invited drift and buggy re-implementations of that rule. Returns ONE
``{state, ...}`` JSON envelope whose ``state`` echoes the routed outcome.

Two independently-invocable modes (the caller picks via ``--mode`` / the args):

  * **batch** (``--batch N --tasks '[...]'``) — emit ``batch_dispatch{batch, tasks}``
    for one implementation batch. A feature runs MANY batches over its life, so the
    presence check matches on ``event`` PLUS the ``batch`` number — an event-name-only
    guard would false-skip batch 2 against batch 1's row (the 7a/7b lesson).
  * **transition** (``--mode transition``) — read the feature's canonical lifecycle
    state via the shared ``common.reduce_lifecycle_state`` reducer (NEVER raw
    events.log parsing — the SAME reducer ``cortex-lifecycle-state`` wraps), route to
    ``review`` or ``complete`` per the §4 rule, and emit
    ``phase_transition{from: implement, to: <review|complete>, tier: <simple|complex>}``.
    The presence check matches on ``event`` PLUS ``from``/``to`` — the feature's log
    already carries earlier ``phase_transition`` rows (spec→plan, plan→implement, …),
    so only the from/to pair distinguishes the row this verb owns.

§4 routing, read through the reducer's ``.state`` dict (keys ``"criticality"`` /
``"tier"``) and its computed ``.corrupted`` property:

  * ``corrupted`` (a torn/out-of-vocab line left tier OR criticality unknowable) →
    route ``review``, emit ``tier: complex`` — the cautious criticality-matrix.md:26
    default (treat as review-requiring rather than trusting a skip rule on unknowable
    input).
  * otherwise, apply the reducer's documented defaults for an absent axis yourself
    (``criticality=medium`` / ``tier=simple``), then route ``review`` when
    ``criticality ∈ {high, critical}`` OR ``tier == complex``, else ``complete``. The
    emitted ``tier`` is the resolved tier (``simple``/``complex``).

Emission goes ONLY through ``log_event`` (the flock + O_APPEND + spaced-json writer)
so each row is byte-identical to the equivalent typed ``cortex-lifecycle-event``
subcommand (``batch-dispatch``, ``phase-transition``) — scan_lifecycle
substring-matches exact spacing, so a hand-rolled ``json.dumps`` would drift. Each
emission is parsed-field matched (never a substring) and skipped when already
present, so re-running the whole verb after a crash repairs rather than duplicates.

A slug-shape guard rejects path separators and ``..`` in ``--feature`` before any
filesystem access. ``main`` never tracebacks: any escaping exception (and the guard)
yields a ``{"state": "error", ...}`` envelope on stdout at exit 0.

Root resolution uses the cwd flavor (``_resolve_user_project_root_from_cwd``),
matching ``lifecycle_event``/``finalize``/``plan_decision``/``review_verdict``/
``spec_approve``: ``log_event`` resolves its own write target from the physical CWD
and cannot be handed a root, so this verb reads the same-tree ``events.log`` for the
presence checks and the reducer. Caller-passed args only (ADR-0019).
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
    reduce_lifecycle_state,
)
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION
from cortex_command.lifecycle_event import log_event

_MODES = ("batch", "transition")

KNOWN_STATES = (
    "dispatched",
    "review",
    "complete",
    "error",
)

# The reducer's documented defaults for an absent (but not corruption-unknowable)
# axis — the same defaults criticality-matrix.md:24 tells the prose to apply.
_DEFAULT_CRITICALITY = "medium"
_DEFAULT_TIER = "simple"
_REVIEW_CRITICALITIES = frozenset({"high", "critical"})


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
    ``match_fields`` refinement is load-bearing for both this verb's emissions:
    ``batch_dispatch`` qualifies on ``batch`` (a feature runs many batches, so a
    bare event-name guard would false-skip a later batch against an earlier row),
    and ``phase_transition`` qualifies on ``from``/``to`` (the feature carries
    earlier transitions under the same event name). Missing/unreadable log → False.
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


def _resolve_route(events_log: Path) -> tuple[str, str]:
    """Resolve the §4 exit route and the tier to stamp on the transition row.

    Reads the feature's canonical lifecycle state through the shared
    ``reduce_lifecycle_state`` reducer (never raw events.log parsing) and applies
    the routing rule:

      * ``corrupted`` → ``("review", "complex")`` — the cautious
        criticality-matrix.md:26 default when tier/criticality are unknowable.
      * otherwise, default an absent axis (criticality=medium / tier=simple) then
        route ``review`` when criticality ∈ {high, critical} OR tier == complex,
        else ``complete``; the emitted tier is the resolved tier.

    Returns ``(route, tier)`` where ``route`` ∈ {"review", "complete"} and ``tier``
    ∈ {"simple", "complex"}.
    """
    reduction = reduce_lifecycle_state(events_log)
    if reduction.corrupted:
        return "review", "complex"
    criticality = reduction.state.get("criticality", _DEFAULT_CRITICALITY)
    tier = reduction.state.get("tier", _DEFAULT_TIER)
    if criticality in _REVIEW_CRITICALITIES or tier == "complex":
        return "review", tier
    return "complete", tier


def implement_transition(
    *,
    feature: str,
    mode: str,
    batch: Optional[int] = None,
    tasks: Optional[list] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Compose one of the implement cluster's mechanical emissions.

    ``mode == "batch"``: emit ``batch_dispatch{batch, tasks}`` (batch-qualified
    presence check). ``mode == "transition"``: read the reducer, route via the §4
    rule, and emit ``phase_transition{from: implement, to: <route>, tier}``
    (from/to-qualified presence check). Returns the ``{state, ...}`` envelope;
    ``state`` is ``"dispatched"`` (batch) / the route (``"review"``/``"complete"``,
    transition) / ``"error"`` (slug guard or bad args).
    """
    guard = _reject_unsafe_slug(feature)
    if guard is not None:
        return guard

    root = project_root or _resolve_user_project_root_from_cwd()
    events_log = root / "cortex" / "lifecycle" / feature / "events.log"
    emitted: List[str] = []

    if mode == "batch":
        if batch is None or tasks is None:
            return {
                "state": "error",
                "message": "batch mode requires --batch and --tasks",
            }
        # batch_dispatch{batch, tasks} — batch-qualified so a later batch never
        # false-skips against an earlier batch's row.
        if not _event_exists(events_log, "batch_dispatch", {"batch": batch}):
            log_event(
                event="batch_dispatch",
                feature=feature,
                fields=[("json", "batch", batch), ("json", "tasks", tasks)],
            )
            emitted.append("batch_dispatch")
        return {
            "state": "dispatched",
            "feature": feature,
            "batch": batch,
            "tasks": tasks,
            "emitted": emitted,
        }

    if mode == "transition":
        route, tier = _resolve_route(events_log)
        # phase_transition{from: implement, to: <route>, tier} — from/to qualified
        # so it never false-skips against an earlier transition, and re-invocation
        # after the transition already landed emits nothing.
        if not _event_exists(
            events_log, "phase_transition", {"from": "implement", "to": route}
        ):
            log_event(
                event="phase_transition",
                feature=feature,
                fields=[
                    ("str", "from", "implement"),
                    ("str", "to", route),
                    ("str", "tier", tier),
                ],
            )
            emitted.append("phase_transition")
        return {
            "state": route,
            "feature": feature,
            "transition_to": route,
            "tier": tier,
            "emitted": emitted,
        }

    # Unreachable via the CLI (argparse pins --mode to _MODES); a direct caller
    # passing an unknown mode gets an error envelope, never a crash.
    return {"state": "error", "message": f"unknown mode {mode!r}, expected {_MODES}"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-implement-transition",
        description=(
            "Resolve one implement-cluster emission to a single {state, ...} JSON "
            "struct on stdout: batch mode emits batch_dispatch{batch, tasks}; "
            "transition mode reads the shared lifecycle-state reducer, routes "
            "implement->{review|complete} per the §4 rule, and emits the "
            "phase_transition (idempotently) via the shared events.log writer. "
            "Always exit 0."
        ),
    )
    parser.add_argument("--feature", required=True, metavar="SLUG", help="Lifecycle feature slug.")
    parser.add_argument(
        "--mode",
        choices=list(_MODES),
        default=None,
        help=(
            "Emission mode. Omitted, it is inferred: 'batch' when --batch is "
            "given, else 'transition'."
        ),
    )
    parser.add_argument(
        "--batch",
        type=_json_int,
        default=None,
        metavar="N",
        help="Batch number (batch mode; presence-check qualifier).",
    )
    parser.add_argument(
        "--tasks",
        type=_json_arg,
        default=None,
        metavar="JSON",
        help="JSON list of task IDs in the batch (batch mode), e.g. '[1,2]'.",
    )
    return parser


def _json_arg(value: str) -> object:
    """argparse ``type=`` for the JSON-typed ``--tasks`` field."""
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON value {value!r}: {exc}")


def _json_int(value: str) -> int:
    """argparse ``type=`` for ``--batch`` — a JSON-parsed integer (matches the
    ``batch-dispatch`` subcommand's ``_JSON`` batch field)."""
    parsed = _json_arg(value)
    if not isinstance(parsed, int) or isinstance(parsed, bool):
        raise argparse.ArgumentTypeError(f"--batch must be an integer, got {value!r}")
    return parsed


def _resolve_mode(args: argparse.Namespace) -> str:
    """Pick the mode: the explicit ``--mode``, else infer 'batch' when ``--batch``
    was supplied, else 'transition'."""
    if args.mode is not None:
        return args.mode
    return "batch" if args.batch is not None else "transition"


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-implement-transition")
    args = _build_parser().parse_args(argv)
    try:
        result = implement_transition(
            feature=args.feature,
            mode=_resolve_mode(args),
            batch=args.batch,
            tasks=args.tasks,
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    result["protocol"] = PROTOCOL_VERSION
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
