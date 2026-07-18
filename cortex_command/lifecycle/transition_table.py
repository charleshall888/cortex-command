"""The single wheel-owned source of truth for the lifecycle state machine.

This module centralizes what the four B1 decision verbs
(``plan_decision``/``review_verdict``/``spec_approve``/``implement_transition``)
and the resolver's one-hop lookahead (``resolve._ROUTE_NEXT``) each encode
locally today: the set of lifecycle **states**, the **transitions** (edges)
between them, each edge's **guard preconditions** (advisory — the real
gate re-evaluates at ``advance`` act-time, ADR-0008), its **pause spec** when
the edge holds for a user pause, and the **parameters** (criticality × tier ×
backend × config overrides) a transition draws enum-validated values from.

CLOSED and wheel-owned (coherence req 5 / spec R10). "Closed" is a hard
property, not a convention:

  * The set of states (``STATES``) and the edge topology (``TRANSITIONS``) are
    module constants. No consumer config can add a state or reorder an edge.
  * Consumer config (from ``cortex_command.lifecycle_config``) may only
    **select** among the enum-validated ``PARAMETERS`` via
    :func:`resolve_parameters`. A config key that names no parameter has zero
    effect on the table; an out-of-enum value for a recognized parameter is
    refused (``ClosedTableError``) — never silently accepted, and never able
    to introduce a novel state or value. This is enforced by the closure tests
    in ``tests/test_transition_table.py``.

Identifiers are **append-only, reserve-on-deprecate** (spec R10 / protobuf
schema-evolution discipline): a retired state name or transition id is moved
into ``RESERVED_STATE_NAMES`` / ``RESERVED_TRANSITION_IDS`` and never reused.
Import-time invariant checks (see the bottom of the module) fail loudly if an
active id collides with a reserved one, if an edge names an unknown state, or
if a pause spec carries an unknown kind — so drift cannot land silently.

**Completeness (spec R10 acceptance):** every B1 verb decision arm maps to
exactly one transition row. An "arm" is a non-``error`` member of a B1 verb's
``KNOWN_STATES`` tuple; a row is keyed by ``(owning_verb, decision_state)``.
The completeness test in ``tests/test_transition_table.py`` derives the arm set
by importing the real B1 modules and reading their ``KNOWN_STATES`` (not a
hand-copy), so adding or removing a decision arm in any B1 verb fails the test
until this table is updated in lockstep.

This module is data + pure accessors only — no I/O, no events.log reads, no
config file reads. The ``next``/``advance``/``describe`` verbs (later tasks)
consume it; they own resolution, reduction, and emission.

Encoding choice: frozen dataclasses (not typed dicts). The table is an
immutable source of truth whose append-only / reserve-on-deprecate discipline
is best served by structurally-immutable rows with typed, named fields; frozen
dataclasses give that (a stray in-place mutation raises), read cleanly in the
``describe`` renderer, and match the lifecycle package's use of structured
records (``common.LifecycleStateReduction``). Enum *domains* stay as plain
frozensets/tuples of strings so config selection is a trivial membership test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class ClosedTableError(ValueError):
    """A consumer tried to select a parameter value outside its enum, i.e. to
    smuggle a value the closed table does not admit. Raised by
    :func:`resolve_parameters`. Naming a novel state or edge is impossible by
    construction (config never reaches the topology); this is the guard for the
    one thing config *can* touch — parameter values."""


# ---------------------------------------------------------------------------
# States (nodes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class State:
    """One lifecycle state (node).

    ``name`` is the canonical, append-only identifier. ``terminal`` marks a
    state the machine does not transition out of. ``legacy_display_phase`` is
    the phase string a legacy artifact-derived reader
    (``common.detect_lifecycle_phase``'s ``route``) projects for this state —
    the compatibility surface the served envelope will carry as its legacy
    display-phase projection field (coherence req 1). For every state the
    legacy reader can itself produce, this equals ``name``; only the
    event-only terminal ``cancelled`` (which the artifact reader has no route
    for) projects to the nearest legacy terminal, ``complete``.
    """

    name: str
    terminal: bool
    legacy_display_phase: str


# The closed set of lifecycle states. Ordered research → … → terminals to read
# as the nominal forward path; order is documentation only (topology lives in
# TRANSITIONS). Append-only: add at the end, never renumber, never reuse a
# retired name (move retired names to RESERVED_STATE_NAMES).
STATES: tuple[State, ...] = (
    State("research", terminal=False, legacy_display_phase="research"),
    State("specify", terminal=False, legacy_display_phase="specify"),
    State("plan", terminal=False, legacy_display_phase="plan"),
    State("implement", terminal=False, legacy_display_phase="implement"),
    State("implement-rework", terminal=False, legacy_display_phase="implement-rework"),
    State("review", terminal=False, legacy_display_phase="review"),
    State("complete", terminal=True, legacy_display_phase="complete"),
    State("escalated", terminal=True, legacy_display_phase="escalated"),
    State("cancelled", terminal=True, legacy_display_phase="complete"),
)

STATE_NAMES: frozenset[str] = frozenset(s.name for s in STATES)

# Reserved (retired-but-never-reused) state names. Empty today; the append-only
# / reserve-on-deprecate mechanism (R10) — a retired state name moves here and
# the import-time check refuses to let an active State reuse it.
RESERVED_STATE_NAMES: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Parameters (the ONLY thing consumer config may select)
# ---------------------------------------------------------------------------

# Each parameter's enum domain — the closed set of values config may select
# among. Membership is the whole validation surface.
PARAMETERS: dict[str, frozenset] = {
    # dispatch mode approved on the plan gate (plan_decision._VALID_MODES).
    "branch_mode": frozenset({"trunk", "worktree-interactive", "feature-branch"}),
    # whether the lifecycle commits its own artifacts (lifecycle_config bool).
    "commit_artifacts": frozenset({True, False}),
    # backlog backend that gates spec_approve's write-back (ADR-0016).
    "backend": frozenset({"cortex-backlog", "none", "external"}),
    # implement-exit routing axes (implement_transition §4 rule inputs).
    "criticality": frozenset({"low", "medium", "high", "critical"}),
    "tier": frozenset({"simple", "complex"}),
}

# The default parameter selection — the byte-identical-to-today local behavior a
# repo gets with no config overrides (mirrors the verbs' documented defaults:
# implement_transition._DEFAULT_CRITICALITY / _DEFAULT_TIER,
# lifecycle_config._BACKLOG_BACKEND_DEFAULT / _COMMIT_ARTIFACTS_DEFAULT).
DEFAULT_PARAMETERS: dict[str, object] = {
    "branch_mode": "trunk",
    "commit_artifacts": True,
    "backend": "cortex-backlog",
    "criticality": "medium",
    "tier": "simple",
}

# Translation from a ``lifecycle.config.md`` frontmatter key to the table
# parameter it selects. A config key absent from this map (``type``,
# ``test-command``, ``skip-specify``, ``skip-review``, …) selects NO parameter
# and therefore has zero effect on the closed table — it can neither introduce a
# state nor reorder an edge. ``default-criticality`` / ``default-tier`` are the
# DORMANT config keys (lifecycle_config._DORMANT_KEYS); mapping them here does
# not activate them (nothing calls resolve_parameters with them today), it
# records where they WOULD land the day activation is made loud and deliberate —
# and, crucially, confines even an activated value to selecting an enum member.
CONFIG_KEY_TO_PARAM: dict[str, str] = {
    "branch-mode": "branch_mode",
    "commit-artifacts": "commit_artifacts",
    "backend": "backend",
    "default-criticality": "criticality",
    "default-tier": "tier",
}


def resolve_parameters(config: Optional[dict] = None) -> dict[str, object]:
    """Select the table's parameter values from a consumer *config* dict.

    Starts from :data:`DEFAULT_PARAMETERS` and applies only the config keys that
    :data:`CONFIG_KEY_TO_PARAM` recognizes as parameter selectors. This is the
    closed door (coherence req 5):

      * A config key naming no parameter is ignored — it cannot introduce a
        state or edge.
      * A recognized parameter key whose value is outside the parameter's enum
        raises :class:`ClosedTableError` — a value the table does not admit is
        refused, never coerced into a novel state or silently honored.

    Returns a fresh dict (the defaults are never mutated). Never reads a file
    and never touches ``STATES`` / ``TRANSITIONS`` — topology is not selectable.
    """
    resolved = dict(DEFAULT_PARAMETERS)
    if not config:
        return resolved
    for key, value in config.items():
        param = CONFIG_KEY_TO_PARAM.get(key)
        if param is None:
            # Non-parameter key: no effect on the closed table.
            continue
        if value not in PARAMETERS[param]:
            raise ClosedTableError(
                f"config key {key!r} may only select parameter {param!r} from "
                f"{sorted(PARAMETERS[param], key=str)}, got {value!r}"
            )
        resolved[param] = value
    return resolved


# ---------------------------------------------------------------------------
# Guards and pause specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Guard:
    """A transition's guard precondition. **Advisory** by contract (ADR-0008 /
    hazard 6): the table records the precondition and which inputs decide it so
    ``next`` can serve it and ``describe`` can render it, but the authoritative
    check re-runs inside ``advance`` at act time. ``precondition`` is the
    human-readable rule; ``reads`` names the parameters and/or event-derived
    discriminants it evaluates."""

    precondition: str
    reads: tuple[str, ...]


# Kept-pause kinds (skills/lifecycle/references/kept-pauses-data.toml's
# four-kind discriminant). Enumerated here so a PauseSpec cannot carry an
# unknown kind (import-time check).
PAUSE_KINDS: frozenset[str] = frozenset(
    {"question", "phase-exit-wait", "config-conditional", "relayed-consent"}
)


@dataclass(frozen=True)
class PauseSpec:
    """A user pause a transition arm holds for. ``slug`` is the per-pause
    accountable identifier written on the ``feature_paused`` row (spec R5);
    ``kind`` is one of :data:`PAUSE_KINDS`. Event-backed pauses (this table's
    scope) are the ones ``advance`` may structurally enforce; judgment /
    config-conditional kinds are describe-only metadata (C+1 boundary, R12)."""

    slug: str
    kind: str


# ---------------------------------------------------------------------------
# Transitions (edges) — every B1 verb decision arm is one row
# ---------------------------------------------------------------------------

# Edge kinds — how a transition moves (or holds) the machine.
EDGE_KIND_PHASE_TRANSITION = "phase-transition"  # from_state != to_state, phase advances
EDGE_KIND_PAUSE_HOLD = "pause-hold"  # holds at from_state on a user pause
EDGE_KIND_IN_STATE_ACTION = "in-state-action"  # records work without changing phase
EDGE_KIND_CANCEL = "cancel"  # lifecycle_cancelled — terminal
EDGE_KIND_NO_OP = "no-op"  # short-circuit; emits nothing, no state change

EDGE_KINDS: frozenset[str] = frozenset(
    {
        EDGE_KIND_PHASE_TRANSITION,
        EDGE_KIND_PAUSE_HOLD,
        EDGE_KIND_IN_STATE_ACTION,
        EDGE_KIND_CANCEL,
        EDGE_KIND_NO_OP,
    }
)


@dataclass(frozen=True)
class Transition:
    """One decision arm of the lifecycle state machine.

    Identity is ``(owning_verb, decision_state)`` — the B1 verb module that owns
    the arm and the ``state`` value that verb returns for it (its non-``error``
    ``KNOWN_STATES`` member). ``id`` is the stable, append-only transition
    identifier (reserve-on-deprecate via :data:`RESERVED_TRANSITION_IDS`).

    ``from_state`` / ``to_state`` are the edge endpoints (equal when the arm
    holds or records in-state). ``edge_kind`` classifies the move. ``emits`` is
    the ordered legacy event vocabulary the owning verb writes for this arm — the
    reference for ``advance``'s dual-emission (it is NOT re-derived here; the verb
    bodies remain the emission authority). ``guard`` is the advisory precondition
    (``None`` when the arm is taken unconditionally on its discriminant).
    ``pause`` is the pause spec when ``edge_kind`` is a hold. ``param_selectors``
    names the :data:`PARAMETERS` this arm draws an enum-validated value from.
    ``notes`` carries any arm-specific nuance (e.g. the standalone-vs-wrapped
    transition suppression on spec approval).
    """

    id: str
    owning_verb: str
    decision_state: str
    from_state: str
    to_state: str
    edge_kind: str
    emits: tuple[str, ...]
    guard: Optional[Guard] = None
    pause: Optional[PauseSpec] = None
    param_selectors: tuple[str, ...] = ()
    notes: str = ""


TRANSITIONS: tuple[Transition, ...] = (
    # -- plan_decision (plan gate) ------------------------------------------
    Transition(
        id="plan.branch-mode-approved",
        owning_verb="plan_decision",
        decision_state="branch-mode-approved",
        from_state="plan",
        to_state="implement",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("plan_approved", "phase_transition"),
        param_selectors=("branch_mode",),
        notes="dispatch_choice ∈ branch_mode selects the approved dispatch mode.",
    ),
    Transition(
        id="plan.wait-approved",
        owning_verb="plan_decision",
        decision_state="wait-approved",
        from_state="plan",
        to_state="plan",
        edge_kind=EDGE_KIND_PAUSE_HOLD,
        emits=("plan_approved", "feature_paused"),
        pause=PauseSpec(slug="plan-approval", kind="relayed-consent"),
        notes="Approval recorded (dispatch_choice: wait); holds at plan, no transition.",
    ),
    Transition(
        id="plan.cancelled",
        owning_verb="plan_decision",
        decision_state="cancelled",
        from_state="plan",
        to_state="cancelled",
        edge_kind=EDGE_KIND_CANCEL,
        emits=("lifecycle_cancelled",),
    ),
    Transition(
        id="plan.revise",
        owning_verb="plan_decision",
        decision_state="revise",
        from_state="plan",
        to_state="plan",
        edge_kind=EDGE_KIND_NO_OP,
        emits=(),
        notes="Short-circuit before any mutation; the plan is revised out-of-band.",
    ),
    # -- review_verdict (review gate) — verdict × cycle routing -------------
    Transition(
        id="review.approved",
        owning_verb="review_verdict",
        decision_state="approved",
        from_state="review",
        to_state="complete",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("review_verdict", "phase_transition"),
        guard=Guard(
            precondition="verdict == APPROVED (any cycle)",
            reads=("verdict",),
        ),
    ),
    Transition(
        id="review.rework",
        owning_verb="review_verdict",
        decision_state="rework",
        from_state="review",
        to_state="implement-rework",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("review_verdict", "phase_transition"),
        guard=Guard(
            precondition="verdict == CHANGES_REQUESTED and cycle == 1",
            reads=("verdict", "cycle"),
        ),
    ),
    Transition(
        id="review.escalated",
        owning_verb="review_verdict",
        decision_state="escalated",
        from_state="review",
        to_state="escalated",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("review_verdict", "phase_transition"),
        guard=Guard(
            precondition="verdict == REJECTED (any cycle), or CHANGES_REQUESTED and cycle >= 2",
            reads=("verdict", "cycle"),
        ),
    ),
    # -- spec_approve (spec gate) -------------------------------------------
    Transition(
        id="spec.approved",
        owning_verb="spec_approve",
        decision_state="approved",
        from_state="specify",
        to_state="plan",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("spec_approved", "phase_transition"),
        guard=Guard(
            precondition=(
                "criticality in {high, critical} OR tier == complex "
                "(or corrupted reduction — cautious default to plan), "
                "or standalone refine (--no-emit-transition, no edge emitted)"
            ),
            reads=("criticality", "tier"),
        ),
        param_selectors=("backend", "criticality", "tier"),
        notes=(
            "phase_transition specify->plan emits ONLY when the caller wraps refine "
            "in the lifecycle (--emit-transition); standalone refine records "
            "spec_approved and the backend-gated write-back but suppresses the edge. "
            "The long road of the spec-exit fork; the short road is spec.approved-direct."
        ),
    ),
    Transition(
        id="spec.approved-direct",
        owning_verb="spec_approve",
        decision_state="approved-direct",
        from_state="specify",
        to_state="implement",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("spec_approved", "phase_transition"),
        guard=Guard(
            precondition=(
                "criticality not in {high, critical} AND tier != complex "
                "(the short road: simple/low-medium skips Plan; only taken "
                "under --emit-transition — standalone refine emits no edge)"
            ),
            reads=("criticality", "tier"),
        ),
        param_selectors=("backend", "criticality", "tier"),
        notes=(
            "Short road of the spec-exit fork: same predicate as the implement-exit "
            "rule, so a simple/low-medium feature runs specify->implement->complete "
            "and never enters plan or review. Implement derives its task list from "
            "spec.md acceptance criteria (no plan.md exists on this road)."
        ),
    ),
    Transition(
        id="spec.cancelled",
        owning_verb="spec_approve",
        decision_state="cancelled",
        from_state="specify",
        to_state="cancelled",
        edge_kind=EDGE_KIND_CANCEL,
        emits=("lifecycle_cancelled",),
    ),
    Transition(
        id="spec.revise",
        owning_verb="spec_approve",
        decision_state="revise",
        from_state="specify",
        to_state="specify",
        edge_kind=EDGE_KIND_NO_OP,
        emits=(),
        notes="Short-circuit before any mutation; the spec is revised out-of-band.",
    ),
    # -- implement_transition (implement work + exit) -----------------------
    Transition(
        id="implement.dispatched",
        owning_verb="implement_transition",
        decision_state="dispatched",
        from_state="implement",
        to_state="implement",
        edge_kind=EDGE_KIND_IN_STATE_ACTION,
        emits=("batch_dispatch",),
        notes="Records one implementation batch; does not change phase.",
    ),
    Transition(
        id="implement.review",
        owning_verb="implement_transition",
        decision_state="review",
        from_state="implement",
        to_state="review",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("phase_transition",),
        guard=Guard(
            precondition=(
                "criticality in {high, critical} OR tier == complex "
                "(or corrupted reduction — cautious default to review)"
            ),
            reads=("criticality", "tier"),
        ),
        param_selectors=("criticality", "tier"),
    ),
    Transition(
        id="implement.complete",
        owning_verb="implement_transition",
        decision_state="complete",
        from_state="implement",
        to_state="complete",
        edge_kind=EDGE_KIND_PHASE_TRANSITION,
        emits=("phase_transition",),
        guard=Guard(
            precondition=(
                "criticality not in {high, critical} AND tier != complex "
                "(the else arm of the implement-exit rule)"
            ),
            reads=("criticality", "tier"),
        ),
        param_selectors=("criticality", "tier"),
    ),
)

# Reserved (retired-but-never-reused) transition ids. Empty today; the R10
# append-only / reserve-on-deprecate mechanism — a retired transition's id moves
# here and the import-time check refuses to let an active Transition reuse it.
RESERVED_TRANSITION_IDS: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Pure accessors (consumed by next / advance / describe)
# ---------------------------------------------------------------------------


def states_by_name() -> dict[str, State]:
    """Return a ``{name: State}`` view of the closed state set."""
    return {s.name: s for s in STATES}


def transition_by_arm(owning_verb: str, decision_state: str) -> Optional[Transition]:
    """Return the transition row for a B1 verb decision arm, or ``None``.

    The ``(owning_verb, decision_state)`` pair is a row's identity, so this is a
    unique lookup — the mapping the completeness test asserts is total over the
    real B1 ``KNOWN_STATES`` arms.
    """
    for t in TRANSITIONS:
        if t.owning_verb == owning_verb and t.decision_state == decision_state:
            return t
    return None


def transition_by_id(transition_id: str) -> Optional[Transition]:
    """Return the transition row with the given stable ``id``, or ``None``."""
    for t in TRANSITIONS:
        if t.id == transition_id:
            return t
    return None


def transitions_from(from_state: str) -> tuple[Transition, ...]:
    """Return every transition departing *from_state* (in declaration order)."""
    return tuple(t for t in TRANSITIONS if t.from_state == from_state)


def edge_topology() -> frozenset[tuple[str, str, str]]:
    """Return the closed edge topology as ``{(from_state, to_state, id)}``.

    Independent of any config by construction (it reads only :data:`TRANSITIONS`)
    — the closure test asserts this frozenset is invariant across arbitrary
    consumer configs: config selects parameter *values*, never topology.
    """
    return frozenset((t.from_state, t.to_state, t.id) for t in TRANSITIONS)


# ---------------------------------------------------------------------------
# Import-time invariants — fail loudly, never let drift land silently
# ---------------------------------------------------------------------------


def _check_invariants() -> None:
    """Validate the table's internal consistency and the R10 discipline.

    Runs once at import. Cheap, and it turns a mis-authored edit (duplicate id,
    dangling state reference, reused-reserved identifier, unknown pause kind or
    edge kind) into an immediate ImportError rather than a subtle runtime bug in
    a downstream verb.
    """
    # Unique, non-reserved state names.
    names = [s.name for s in STATES]
    assert len(names) == len(set(names)), f"duplicate state name in STATES: {names}"
    reused = STATE_NAMES & RESERVED_STATE_NAMES
    assert not reused, f"active state names reuse reserved ids (R10 violation): {reused}"

    # Unique transition ids and unique arm identities.
    ids = [t.id for t in TRANSITIONS]
    assert len(ids) == len(set(ids)), f"duplicate transition id: {ids}"
    reused_ids = set(ids) & RESERVED_TRANSITION_IDS
    assert not reused_ids, f"active transition ids reuse reserved ids (R10): {reused_ids}"
    arms = [(t.owning_verb, t.decision_state) for t in TRANSITIONS]
    assert len(arms) == len(set(arms)), f"duplicate (owning_verb, decision_state) arm: {arms}"

    # Every edge endpoint is a declared state; every pause/edge kind is known;
    # every param selector names a real parameter.
    for t in TRANSITIONS:
        assert t.from_state in STATE_NAMES, f"{t.id}: unknown from_state {t.from_state!r}"
        assert t.to_state in STATE_NAMES, f"{t.id}: unknown to_state {t.to_state!r}"
        assert t.edge_kind in EDGE_KINDS, f"{t.id}: unknown edge_kind {t.edge_kind!r}"
        if t.pause is not None:
            assert t.pause.kind in PAUSE_KINDS, f"{t.id}: unknown pause kind {t.pause.kind!r}"
        for p in t.param_selectors:
            assert p in PARAMETERS, f"{t.id}: unknown param selector {p!r}"

    # DEFAULT_PARAMETERS is itself a valid selection (every default in its enum).
    for param, value in DEFAULT_PARAMETERS.items():
        assert param in PARAMETERS, f"DEFAULT_PARAMETERS has unknown parameter {param!r}"
        assert value in PARAMETERS[param], f"default {value!r} not in {param!r} enum"


_check_invariants()
