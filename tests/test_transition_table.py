"""Closure, completeness and reachability tests for the lifecycle transition table.

`transition_table`'s module docstring cites this file three times as the
enforcement for its two headline properties — that the table is CLOSED (consumer
config can select parameter values but never introduce a state or an edge) and
COMPLETE (every B1 verb decision arm maps to exactly one row). The file did not
exist. Nothing checked either property, which is how `review.rework` was able to
add `implement-rework` as a destination with no way back out: the table gained a
state that stranded any feature routed into it, and the defect surfaced only when
a live rework cycle hit a refusal it could not clear (#433).

The arm set here is derived by importing the real B1 verb modules and reading
their `KNOWN_STATES`, never by hand-copying them — so adding or removing a
decision arm in any B1 verb fails these tests until the table is updated in
lockstep, which is the property the docstring promises.
"""

from __future__ import annotations

import dataclasses

import pytest

from cortex_command.lifecycle import implement_transition as it
from cortex_command.lifecycle import plan_decision as pd
from cortex_command.lifecycle import review_verdict as rv
from cortex_command.lifecycle import spec_approve as sa
from cortex_command.lifecycle import transition_table as tt

# The four B1 decision verbs, keyed by the `owning_verb` string their rows carry.
B1_VERBS = {
    "plan_decision": pd,
    "review_verdict": rv,
    "spec_approve": sa,
    "implement_transition": it,
}


def _real_arms() -> set[tuple[str, str]]:
    """Every (owning_verb, decision_state) arm the real B1 modules declare.

    An "arm" is a non-`error` member of a verb's `KNOWN_STATES` — `error` is the
    never-traceback envelope, not a lifecycle decision, so it owns no edge.
    """
    return {
        (verb, state)
        for verb, module in B1_VERBS.items()
        for state in module.KNOWN_STATES
        if state != "error"
    }


# ---------------------------------------------------------------------------
# Completeness: arms <-> rows is a total bijection
# ---------------------------------------------------------------------------


def test_every_b1_arm_has_exactly_one_transition_row() -> None:
    """Each non-error decision arm maps to one row, keyed by (verb, decision)."""
    missing = sorted(
        arm for arm in _real_arms() if tt.transition_by_arm(*arm) is None
    )
    assert not missing, (
        "B1 verb decision arms with no transition row (the table is behind the "
        f"verbs): {missing}"
    )


def test_no_transition_row_without_a_real_b1_arm() -> None:
    """The table declares no edge for a decision arm no verb can produce."""
    arms = _real_arms()
    orphans = sorted(
        t.id
        for t in tt.TRANSITIONS
        if (t.owning_verb, t.decision_state) not in arms
    )
    assert not orphans, (
        f"transition rows whose (owning_verb, decision_state) no B1 verb declares: {orphans}"
    )


def test_row_identity_is_unique() -> None:
    arms = [(t.owning_verb, t.decision_state) for t in tt.TRANSITIONS]
    assert len(arms) == len(set(arms)), f"duplicate arm identity: {arms}"
    ids = [t.id for t in tt.TRANSITIONS]
    assert len(ids) == len(set(ids)), f"duplicate transition id: {ids}"


# ---------------------------------------------------------------------------
# Reachability: no state the table routes INTO is a dead end
# ---------------------------------------------------------------------------


def test_no_reachable_non_terminal_state_is_a_dead_end() -> None:
    """The guard #433 asks for: a feature can always leave where it was put.

    Scoped to states that are some row's `to_state`. A state the table never
    routes into is an entry point owned by a phase outside the four B1 verbs —
    `research` is the only one, and the refine phase (not a B1 verb) owns its
    `research -> specify` step, so it legitimately has no row here. Any state the
    table CAN transition into, though, must be terminal or have a way out;
    otherwise the machine can strand a live feature, which is exactly what
    `implement-rework` did before `implement.rework-review` existed.
    """
    reachable = {t.to_state for t in tt.TRANSITIONS}
    by_name = tt.states_by_name()
    stranded = sorted(
        name
        for name in reachable
        if not by_name[name].terminal and not tt.transitions_from(name)
    )
    assert not stranded, (
        "non-terminal states the table routes into but never out of — a feature "
        f"reaching one is stranded and needs an out-of-band event append: {stranded}"
    )


def test_entry_states_are_documented_as_such() -> None:
    """`research` is the sole state no transition routes into.

    Pinned so that a new state added without an inbound edge is noticed here
    rather than silently widening the dead-end test's exemption set.
    """
    reachable = {t.to_state for t in tt.TRANSITIONS}
    assert sorted(tt.STATE_NAMES - reachable) == ["research"]


def test_terminal_states_have_no_outgoing_edges() -> None:
    leaking = sorted(
        s.name for s in tt.STATES if s.terminal and tt.transitions_from(s.name)
    )
    assert not leaking, f"terminal states with outgoing edges: {leaking}"


# ---------------------------------------------------------------------------
# Closure: config selects parameter values, never topology
# ---------------------------------------------------------------------------


def test_config_cannot_introduce_a_state_or_an_edge() -> None:
    """A config naming a novel state/edge has zero effect on the topology."""
    before_states = set(tt.STATE_NAMES)
    before_edges = tt.edge_topology()
    tt.resolve_parameters(
        {
            "states": ["a-brand-new-state"],
            "transitions": [{"from_state": "review", "to_state": "research"}],
            "implement-rework": "complete",
            "branch-mode": "feature-branch",  # a *recognized* key, still topology-inert
        }
    )
    assert set(tt.STATE_NAMES) == before_states
    assert tt.edge_topology() == before_edges


@pytest.mark.parametrize("config_key,param", sorted(tt.CONFIG_KEY_TO_PARAM.items()))
def test_out_of_enum_parameter_value_is_refused(config_key: str, param: str) -> None:
    """Every selector key refuses a value outside its enum, for every key."""
    bogus = "definitely-not-in-" + param
    assert bogus not in tt.PARAMETERS[param]
    with pytest.raises(tt.ClosedTableError):
        tt.resolve_parameters({config_key: bogus})


def test_unrecognized_config_key_is_inert() -> None:
    """A key naming no parameter — including a bare parameter name.

    The config surface is keyed by `lifecycle.config.md` frontmatter keys, so
    even a valid parameter's own name (`branch_mode`) selects nothing; only the
    mapped key (`branch-mode`) does.
    """
    for key in ("no-such-parameter", "type", "skip-review", "branch_mode"):
        assert tt.resolve_parameters({key: "whatever"}) == tt.resolve_parameters(None), (
            f"config key {key!r} should have had no effect"
        )


def test_in_enum_parameter_value_is_selected() -> None:
    for config_key, param in tt.CONFIG_KEY_TO_PARAM.items():
        for value in tt.PARAMETERS[param]:
            assert tt.resolve_parameters({config_key: value})[param] == value


def test_defaults_are_never_mutated_by_a_selection() -> None:
    snapshot = dict(tt.DEFAULT_PARAMETERS)
    tt.resolve_parameters({"branch-mode": "feature-branch"})
    assert tt.DEFAULT_PARAMETERS == snapshot
    assert tt.resolve_parameters(None) == snapshot


def test_rows_are_structurally_immutable() -> None:
    """Frozen dataclasses: a stray in-place mutation raises, per the docstring."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        tt.TRANSITIONS[0].to_state = "cancelled"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Append-only / reserve-on-deprecate (R10)
# ---------------------------------------------------------------------------


def test_active_identifiers_never_reuse_reserved_ones() -> None:
    assert not (tt.STATE_NAMES & tt.RESERVED_STATE_NAMES)
    assert not ({t.id for t in tt.TRANSITIONS} & tt.RESERVED_TRANSITION_IDS)


def test_every_edge_endpoint_kind_and_selector_is_declared() -> None:
    for t in tt.TRANSITIONS:
        assert t.from_state in tt.STATE_NAMES, f"{t.id}: unknown from_state"
        assert t.to_state in tt.STATE_NAMES, f"{t.id}: unknown to_state"
        assert t.edge_kind in tt.EDGE_KINDS, f"{t.id}: unknown edge_kind"
        if t.pause is not None:
            assert t.pause.kind in tt.PAUSE_KINDS, f"{t.id}: unknown pause kind"
        for selector in t.param_selectors:
            assert selector in tt.PARAMETERS, f"{t.id}: unknown selector {selector!r}"


# ---------------------------------------------------------------------------
# The #433 edge specifically
# ---------------------------------------------------------------------------


def test_implement_rework_exits_to_review_unconditionally() -> None:
    """Rework re-enters review, never `complete`.

    A feature only reaches `implement-rework` via `review.rework`, which fires
    solely on CHANGES_REQUESTED at cycle 1. Routing its exit through the §4
    criticality/tier rule would let a low-criticality simple feature skip
    straight to `complete` without anyone re-reading the requested changes.
    """
    edges = tt.transitions_from("implement-rework")
    assert [t.to_state for t in edges] == ["review"], (
        f"implement-rework must exit only to review, got {[t.to_state for t in edges]}"
    )
    assert edges[0].owning_verb == "implement_transition"
    assert edges[0].id == "implement.rework-review"
