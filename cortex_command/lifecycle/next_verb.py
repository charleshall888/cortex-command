"""cortex-lifecycle-next — the read-only served-state verb of the lifecycle loop.

``next`` is the READ-ONLY server verb the Phase-5 prose loop calls to learn what
to do next. It composes four wheel-owned primitives and serves ONE JSON envelope:

  1. **Identity resolution** — ``resolve.resolve_invocation`` (absorbing the
     Step-1 ``$ARGUMENTS`` classification and its ``_ROUTE_NEXT`` one-hop
     lookahead). Anchored at the main repo root so a worktree session resolves
     the *same* identity the pinned log resolver does.
  2. **Log reduction via the pinned resolver** — ``log_resolver.resolve_events_log``
     locates the single main-root-anchored ``events.log`` (hazard 1 / R4) and
     ``common.reduce_lifecycle_state`` folds it to the criticality/tier/pause
     discriminants the guards read. The physical log path is recorded in the
     advance contract so ``advance`` (Task 14) can assert the caller resolved the
     same log.
  3. **Guard evaluation** — the wheel-owned transition table
     (``transition_table``) supplies the outgoing edges, their guard
     preconditions, pause specs, and emitted vocabulary for the current state.
     Guard output is labeled **advisory** (R11 / hazard 6): a guard is a hint the
     loop may render, NEVER an authorization — the authoritative gate re-runs
     inside ``advance`` at act time (ADR-0008).
  4. **Protocol handshake** — ``protocol.classify_protocol`` classifies the
     served payload's ``protocol`` integer against a CALLER-supplied expectation
     range (``--expect-min`` / ``--expect-max`` or the ``CORTEX_LIFECYCLE_PROTOCOL_*``
     env vars). When the expectation is out of range the verb short-circuits to
     ``{"state": "protocol-skew", ...}`` carrying the copy-pasteable remediation
     message (R7 substrate, loop-side halt boundary).

It NEVER writes — no ``events.log`` append, no backlog write-back. It always
exits 0: house verb style means ``main`` catches every escaping exception and
emits ``{"state": "error"}`` rather than a traceback. ``--explain`` expands the
derivation trace into the full step-by-step (operator req 1).

**Naming collision (adversarial finding 9):** the resolver's routing struct
already carries a ``next`` *directive* field for legacy consumers. This verb's
served (resume) envelope deliberately does NOT introduce a ``next`` routing key —
the served fields are ``state`` / ``fragment_ref`` / ``advance_contract`` / …. The
resolver's ``next`` field stays on the passthrough routing states (``new`` /
``empty`` / …) until the protocol-floor bump.

Envelope schema (served / resume case)::

    {
      "state": <current lifecycle state, a transition-table state name>,
      "legacy_display_phase": <the artifact-derived projection for the state>,
      "fragment_ref": {"state", "directive", "reference", "flavor": "selector"},
      "pause_spec": {"specs": [{"slug", "kind"}], "active", "active_kind"},
      "advance_contract": {"expected_from_state", "log_path", "flock_path"},
      "path_overview": {"nominal": [...], "outgoing": [...]},   # default-on at resume
      "guards": {"advisory": true, "note": ..., "edges": [ ... ]},
      "evidence_trace": [ <derivation step>, ... ],
      "protocol": <PROTOCOL_VERSION>
    }

The passthrough routing states (``derive-slug`` / ``empty`` / ``needs-feature`` /
``wontfix`` / ``no-such-lifecycle`` / ``ambiguous-backlog`` / ``new``) are
returned verbatim from the resolver (they carry the resolver's legacy ``next``
directive), stamped with ``protocol``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import LifecycleStateReduction, reduce_lifecycle_state
from cortex_command.lifecycle import resolve as resolve_mod
from cortex_command.lifecycle import transition_table as tt
from cortex_command.lifecycle.log_resolver import (
    resolve_events_log,
    resolve_flock_path,
    resolve_main_repo_root,
)
from cortex_command.lifecycle.protocol import (
    PROTOCOL_VERSION,
    classify_protocol,
    remediation_message,
)

# Passthrough routing states the resolver owns end-to-end: ``next`` returns the
# resolver's struct verbatim (stamped with ``protocol``). ``resume`` is NOT here —
# it is transformed into the served envelope keyed by the concrete table state.
_ROUTING_PASSTHROUGH = (
    "derive-slug",
    "empty",
    "needs-feature",
    "wontfix",
    "no-such-lifecycle",
    "ambiguous-backlog",
    "new",
)

# Closed set of ``state`` values ``next`` can emit (house style). The served
# subset is exactly the transition table's state names; the rest are the
# resolver's passthrough routing states plus the two verb-specific arms.
KNOWN_STATES = (
    # served transition-table states (the resume case projects one of these)
    "research",
    "specify",
    "plan",
    "implement",
    "implement-rework",
    "review",
    "complete",
    "escalated",
    "cancelled",
    # passthrough routing states (owned by resolve.resolve_invocation)
    *_ROUTING_PASSTHROUGH,
    # verb-specific arms
    "protocol-skew",
    "error",
)

# Drift tripwire: every table state MUST be a state ``next`` can serve. If the
# closed table grows a state this tuple does not list, fail loudly at import
# rather than silently serve a malformed envelope.
assert tt.STATE_NAMES <= set(KNOWN_STATES), (
    "transition_table.STATE_NAMES carries a state next.KNOWN_STATES omits: "
    f"{tt.STATE_NAMES - set(KNOWN_STATES)}"
)

_ADVISORY_NOTE = (
    "Guards are ADVISORY (ADR-0008 / hazard 6): a hint the loop may render, "
    "never an authorization. The authoritative gate re-runs inside `advance` "
    "at act time."
)


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


def _terminal_directive(state: str) -> str:
    """The fragment directive for a served state, terminal-aware.

    Reuses the resolver's ``_ROUTE_NEXT`` directives for the non-terminal
    routes (the same one-hop lookahead prose the loop already reads) and pins
    an explicit terminal directive for the event-only ``cancelled`` state,
    which the artifact reader has no route for.
    """
    if state == "cancelled":
        return "Lifecycle cancelled (terminal) — no further transitions; nothing to enter."
    return resolve_mod._ROUTE_NEXT.get(state, f"Enter the {state} phase.")


def _evaluate_guard(transition: tt.Transition, discriminants: dict) -> dict:
    """Advisory guard evaluation for one outgoing edge.

    Returns the guard's precondition + the discriminants it reads, plus an
    ADVISORY ``holds`` verdict computed ONLY from inputs cheaply available at
    read time (criticality / tier from the reduction; cycle from the artifact
    detection). ``holds`` is ``None`` when a required input is not available
    read-side (e.g. ``verdict``, which ``advance`` reads from ``review.md`` at
    act time) — never a guess. Guard-less arms report ``holds: null`` with an
    empty ``reads`` set (they are taken unconditionally on their discriminant).
    """
    guard = transition.guard
    if guard is None:
        return {
            "transition_id": transition.id,
            "to_state": transition.to_state,
            "edge_kind": transition.edge_kind,
            "emits": list(transition.emits),
            "precondition": None,
            "reads": [],
            "inputs": {},
            "holds": None,
        }

    inputs = {r: discriminants.get(r) for r in guard.reads}
    holds: Optional[bool]
    # Only the criticality/tier guards are decidable read-side; verdict-reading
    # guards defer to advance (verdict is unavailable here → holds stays None).
    if "verdict" in guard.reads:
        holds = None
    elif set(guard.reads) <= {"criticality", "tier"}:
        criticality = discriminants.get("criticality")
        tier = discriminants.get("tier")
        corrupted = bool(discriminants.get("corrupted"))
        escalate = criticality in ("high", "critical") or tier == "complex" or corrupted
        # implement.review holds on escalate; implement.complete is the else arm.
        holds = escalate if transition.to_state == "review" else not escalate
    else:
        holds = None

    return {
        "transition_id": transition.id,
        "to_state": transition.to_state,
        "edge_kind": transition.edge_kind,
        "emits": list(transition.emits),
        "precondition": guard.precondition,
        "reads": list(guard.reads),
        "inputs": inputs,
        "holds": holds,
    }


def _nominal_forward_path(state: str) -> List[str]:
    """The nominal forward state path from *state* through the STATES ordering.

    Documentation-only (the authoritative topology is the edge set); STATES is
    declared research → … → terminals so the slice from the current state reads
    as the nominal forward path. Terminal states return just themselves.
    """
    names = [s.name for s in tt.STATES]
    if state not in names:
        return [state]
    idx = names.index(state)
    # Stop at (and include) the first terminal at/after the current state so the
    # branch terminals (escalated/cancelled) do not appear on the nominal line.
    path: List[str] = []
    for s in tt.STATES[idx:]:
        path.append(s.name)
        if s.terminal:
            break
    return path


def build_served_envelope(
    *,
    state: str,
    events_log: Path,
    reduction: Optional[LifecycleStateReduction] = None,
    cycle: int = 1,
    checked: int = 0,
    total: int = 0,
    at_resume: bool = True,
    explain: bool = False,
) -> dict:
    """Build the served ``next`` envelope for a concrete transition-table *state*.

    Pure over its inputs (the only I/O is the caller's log resolution/reduction,
    passed in). *state* MUST be a ``transition_table`` state name; the per-state
    acceptance test drives this for every ``STATE_NAMES`` member, including the
    event-only ``cancelled`` the artifact reader cannot itself produce.

    ``reduction`` supplies criticality/tier/pause_kind; when ``None`` the table
    defaults stand in (a fresh lifecycle with no reduced axes). ``at_resume``
    gates the default-on ``path_overview``. ``explain`` expands the evidence
    trace with the full guard-input derivation.
    """
    states = tt.states_by_name()
    st = states[state]  # KeyError → caught by main() as an error envelope.

    reduced = reduction.state if reduction is not None else {}
    criticality = reduced.get("criticality", tt.DEFAULT_PARAMETERS["criticality"])
    tier = reduced.get("tier", tt.DEFAULT_PARAMETERS["tier"])
    pause_kind = reduced.get("pause_kind")
    corrupted = bool(reduction.corrupted) if reduction is not None else False

    discriminants = {
        "criticality": criticality,
        "tier": tier,
        "cycle": cycle,
        "corrupted": corrupted,
        # verdict is intentionally absent — read at act time by advance.
    }

    outgoing = tt.transitions_from(state)
    guard_edges = [_evaluate_guard(t, discriminants) for t in outgoing]

    # Pause specs available from this state (the pause-hold arms), plus whether a
    # pause is currently active (an event-backed feature_paused reduced above).
    pause_specs = [
        {"slug": t.pause.slug, "kind": t.pause.kind}
        for t in outgoing
        if t.pause is not None
    ]
    pause_spec = {
        "specs": pause_specs,
        "active": pause_kind is not None,
        "active_kind": pause_kind,
    }

    fragment_ref = {
        "state": state,
        "directive": _terminal_directive(state),
        "reference": None if st.terminal else f"{state}.md",
        "flavor": "selector",
    }

    advance_contract = {
        "expected_from_state": state,
        "log_path": str(events_log),
        "flock_path": str(resolve_flock_path(events_log)),
    }

    evidence_trace: List[dict] = [
        {"step": "state", "value": state, "terminal": st.terminal},
        {
            "step": "reduction",
            "criticality": criticality,
            "tier": tier,
            "pause_kind": pause_kind,
            "corrupted": corrupted,
            "skipped_lines": list(reduction.skipped_lines) if reduction is not None else [],
        },
        {"step": "cycle", "value": cycle, "checked": checked, "total": total},
        {"step": "log_resolution", "log_path": str(events_log), "anchor": "main-root"},
    ]
    if explain:
        evidence_trace.append(
            {
                "step": "guards",
                "advisory": True,
                "edges": guard_edges,
                "note": _ADVISORY_NOTE,
            }
        )

    envelope = {
        "state": state,
        "legacy_display_phase": st.legacy_display_phase,
        "fragment_ref": fragment_ref,
        "pause_spec": pause_spec,
        "advance_contract": advance_contract,
        "guards": {"advisory": True, "note": _ADVISORY_NOTE, "edges": guard_edges},
        "evidence_trace": evidence_trace,
        "protocol": PROTOCOL_VERSION,
    }
    if at_resume or explain:
        envelope["path_overview"] = {
            "nominal": _nominal_forward_path(state),
            "outgoing": [
                t.to_state for t in outgoing if t.edge_kind == tt.EDGE_KIND_PHASE_TRANSITION
            ],
        }
    if explain:
        envelope["explain"] = True
    return envelope


def _caller_expectation(
    expect_min: Optional[int], expect_max: Optional[int]
) -> Optional[tuple[int, int]]:
    """Resolve the caller-supplied protocol expectation range, argv over env.

    The CALLER (the prose loop) declares what protocol range it expects; the verb
    never reads the plugin expectation file itself (that keeps ``classify_protocol``
    a pure function). Argv ``--expect-min``/``--expect-max`` win; otherwise the
    ``CORTEX_LIFECYCLE_PROTOCOL_MIN``/``_MAX`` env vars are honored. Returns
    ``None`` when no expectation is supplied (the skew check is skipped).
    """
    lo = expect_min
    hi = expect_max
    if lo is None:
        env_lo = os.environ.get("CORTEX_LIFECYCLE_PROTOCOL_MIN")
        lo = int(env_lo) if env_lo not in (None, "") else None
    if hi is None:
        env_hi = os.environ.get("CORTEX_LIFECYCLE_PROTOCOL_MAX")
        hi = int(env_hi) if env_hi not in (None, "") else None
    if lo is None and hi is None:
        return None
    # A one-sided expectation pins the missing bound to the served value so a
    # single-ended range is still a valid inclusive interval.
    if lo is None:
        lo = PROTOCOL_VERSION
    if hi is None:
        hi = PROTOCOL_VERSION
    return lo, hi


def next_state(
    arguments: str,
    *,
    expect_min: Optional[int] = None,
    expect_max: Optional[int] = None,
    explain: bool = False,
) -> dict:
    """Resolve *arguments* to the served ``next`` envelope (or a routing struct).

    Anchors identity resolution AND log resolution at the main repo root so a
    worktree session serves the main-root log (R4). The protocol-skew check runs
    first: when the caller supplies an expectation range the served
    ``PROTOCOL_VERSION`` falls outside, the verb short-circuits to
    ``protocol-skew`` with the remediation message — the loop's halt boundary.
    """
    # (1) Protocol handshake — the caller declares its expected range; classify
    # the payload this wheel serves against it. Out-of-range (or a legacy-shaped
    # expectation, unreachable for our own always-stamped payload) → halt.
    expectation = _caller_expectation(expect_min, expect_max)
    if expectation is not None:
        lo, hi = expectation
        served_payload = {"protocol": PROTOCOL_VERSION}
        verdict = classify_protocol(served_payload, expected_min=lo, expected_max=hi)
        if verdict != "ok":
            return {
                "state": "protocol-skew",
                "classification": verdict,
                "served_protocol": PROTOCOL_VERSION,
                "expected_min": lo,
                "expected_max": hi,
                "remediation": remediation_message(
                    served=PROTOCOL_VERSION, expected_min=lo, expected_max=hi
                ),
                "protocol": PROTOCOL_VERSION,
            }

    # (2) Identity resolution — anchored at the main root (worktree-aware) so the
    # artifact-derived route and the pinned log resolver agree on one feature.
    root = resolve_main_repo_root()
    resolved = resolve_mod.resolve_invocation(arguments, project_root=root)
    state = resolved.get("state")

    # Guard-shape failures the resolver already classified propagate verbatim
    # (they carry the resolver's legacy ``next`` directive, kept for consumers).
    if state in _ROUTING_PASSTHROUGH:
        out = dict(resolved)
        out["protocol"] = PROTOCOL_VERSION
        return out
    if state == "error":
        out = dict(resolved)
        out["protocol"] = PROTOCOL_VERSION
        return out

    # (3) Resume → project the concrete table state and serve the rich envelope.
    if state == "resume":
        feature = resolved["feature"]
        guard = _reject_unsafe_slug(feature)
        if guard is not None:
            return guard
        route = resolved["route"]
        if route not in tt.STATE_NAMES:
            # A phase override the closed table has no state for — surface it as
            # an error rather than serve a malformed envelope.
            return {
                "state": "error",
                "message": f"route {route!r} is not a transition-table state",
                "feature": feature,
            }
        events_log = resolve_events_log(feature)
        reduction = reduce_lifecycle_state(events_log)
        envelope = build_served_envelope(
            state=route,
            events_log=events_log,
            reduction=reduction,
            cycle=int(resolved.get("cycle", 1)),
            checked=int(resolved.get("checked", 0)),
            total=int(resolved.get("total", 0)),
            at_resume=True,
            explain=explain,
        )
        envelope["feature"] = feature
        envelope["paused"] = bool(resolved.get("paused"))
        if resolved.get("resolved_from") is not None:
            envelope["resolved_from"] = resolved["resolved_from"]
        return envelope

    # Any other resolver state is unexpected for the served path.
    out = dict(resolved)
    out["state"] = out.get("state") or "error"
    out["protocol"] = PROTOCOL_VERSION
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-next",
        description=(
            "Serve the current lifecycle state and its advance contract for a "
            "feature as a single JSON envelope on stdout (read-only; always exit "
            "0). Guards are advisory. --explain emits the full derivation."
        ),
    )
    parser.add_argument(
        "arguments",
        nargs="?",
        default="",
        help="The raw $ARGUMENTS string (a single quoted feature/slug argument).",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Expand the evidence trace into the full step-by-step derivation.",
    )
    parser.add_argument(
        "--expect-min",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Caller-supplied lower bound of the protocol compat range (the prose "
            "loop's expectation). Out-of-range → a protocol-skew envelope."
        ),
    )
    parser.add_argument(
        "--expect-max",
        type=int,
        default=None,
        metavar="N",
        help="Caller-supplied upper bound of the protocol compat range.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-next")
    args = _build_parser().parse_args(argv)
    try:
        result = next_state(
            args.arguments or "",
            expect_min=args.expect_min,
            expect_max=args.expect_max,
            explain=args.explain,
        )
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc), "protocol": PROTOCOL_VERSION}
    result.setdefault("protocol", PROTOCOL_VERSION)
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
