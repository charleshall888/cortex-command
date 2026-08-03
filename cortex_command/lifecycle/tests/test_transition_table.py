"""Tests for the wheel-owned lifecycle transition table.

Two acceptance obligations (spec R10):

  * **Completeness** — every B1 verb decision arm maps to exactly one table row.
    The arm set is derived from the *real* B1 modules' ``KNOWN_STATES`` tuples
    (imported here, never hand-copied), so a decision arm added to or removed
    from any B1 verb fails the completeness test until the table is updated.
  * **Closure** — consumer config can select enum-validated parameters only; it
    can never introduce a state or reorder an edge.

Plus real-code cross-checks that the table's edge targets agree with the B1
routing functions (``review_verdict._route_target`` / ``_TARGET_TO_STATE``) and
that the states generalize the resolver's one-hop lookahead
(``resolve._ROUTE_NEXT``) — so the table stays a faithful centralization of the
logic it absorbs rather than a parallel invention.
"""

from __future__ import annotations

import dataclasses

import pytest

from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle import (
    implement_transition,
    plan_decision,
    resolve,
    review_verdict,
    spec_approve,
)
from cortex_command.lifecycle import transition_table as tt

# The four B1 decision verbs, keyed by the owning_verb identifier the table uses
# (their module basename). This is the single source the completeness test reads
# the real decision arms from.
B1_MODULES = {
    "plan_decision": plan_decision,
    "review_verdict": review_verdict,
    "spec_approve": spec_approve,
    "implement_transition": implement_transition,
}


def _real_decision_arms() -> set[tuple[str, str]]:
    """Derive the decision-arm set from the real B1 modules' KNOWN_STATES.

    An arm is a non-``error`` member of a verb's ``KNOWN_STATES`` closed tuple —
    the verb's own declaration of the decision outcomes it routes on. Reading
    the live tuple (not a copy) is what makes the completeness test a genuine
    cross-check against the verbs rather than against the table's own data.
    """
    arms: set[tuple[str, str]] = set()
    for verb_name, module in B1_MODULES.items():
        for state in module.KNOWN_STATES:
            if state == "error":
                continue
            arms.add((verb_name, state))
    return arms


def _table_arms() -> set[tuple[str, str]]:
    return {(t.owning_verb, t.decision_state) for t in tt.TRANSITIONS}


# ---------------------------------------------------------------------------
# Completeness — every B1 verb decision arm maps to a row
# ---------------------------------------------------------------------------


def test_every_b1_decision_arm_maps_to_a_row() -> None:
    """The set of (owning_verb, decision_state) rows equals the set of real B1
    decision arms — no arm unmapped, no phantom row for a non-existent arm."""
    real = _real_decision_arms()
    table = _table_arms()
    assert table == real, (
        f"unmapped B1 arms: {real - table}; phantom table rows: {table - real}"
    )


def test_each_arm_resolves_to_exactly_one_row() -> None:
    """``transition_by_arm`` is a total, unique lookup over the real arm set."""
    for verb_name, state in _real_decision_arms():
        row = tt.transition_by_arm(verb_name, state)
        assert row is not None, f"no table row for arm ({verb_name}, {state})"
        assert row.owning_verb == verb_name and row.decision_state == state


def test_artifact_only_states_are_covered() -> None:
    """The states the events back only after B1 — implement-rework and escalated
    (review_verdict routing) — are declared states and are edge targets."""
    for name in ("implement-rework", "escalated"):
        assert name in tt.STATE_NAMES
    targets = {t.to_state for t in tt.TRANSITIONS}
    assert {"implement-rework", "escalated"} <= targets


def test_review_edge_targets_match_route_target_function() -> None:
    """The review rows' to_states agree with the real ``_route_target`` /
    ``_TARGET_TO_STATE`` mapping — a cross-check of the *edges*, not just the
    arm names. Derived by calling the live routing function over verdict×cycle.
    """
    state_to_target = {v: k for k, v in review_verdict._TARGET_TO_STATE.items()}
    for verdict in review_verdict._VERDICTS:
        for cycle in (1, 2):
            target = review_verdict._route_target(verdict, cycle)
            state = review_verdict._TARGET_TO_STATE[target]
            row = tt.transition_by_arm("review_verdict", state)
            assert row is not None
            # to_state is the routed phase target for this decision state.
            assert row.to_state == state_to_target[state] == target


def test_states_generalize_resolver_one_hop_lookahead() -> None:
    """Every route the resolver's one-hop lookahead (_ROUTE_NEXT) knows is a
    state in the table — the table generalizes that precedent, not a subset."""
    for route in resolve._ROUTE_NEXT:
        assert route in tt.STATE_NAMES, f"_ROUTE_NEXT route {route!r} missing from STATES"


def test_plan_branch_mode_selects_valid_modes() -> None:
    """The branch_mode parameter enum matches plan_decision._VALID_MODES — the
    table draws its dispatch-mode selection from the same closed set the verb
    validates against."""
    assert tt.PARAMETERS["branch_mode"] == frozenset(plan_decision._VALID_MODES)


# ---------------------------------------------------------------------------
# Closure — config selects parameters only; never states or edges
# ---------------------------------------------------------------------------


def test_config_cannot_introduce_a_state() -> None:
    """A config key that names something state-shaped has zero effect: it is not
    a parameter selector, so resolve_parameters ignores it and STATES is
    untouched. The bogus value never becomes a state or a parameter value."""
    before = set(tt.STATE_NAMES)
    resolved = tt.resolve_parameters(
        {"phase": "banana", "new-state": "quux", "workflow": "custom"}
    )
    assert set(tt.STATE_NAMES) == before
    assert "banana" not in tt.STATE_NAMES
    assert set(resolved) == set(tt.DEFAULT_PARAMETERS)  # only known parameters
    assert "banana" not in resolved.values() and "quux" not in resolved.values()


def test_config_cannot_reorder_or_add_edges() -> None:
    """The edge topology is invariant across arbitrary configs — including ones
    setting the dormant skip-specify / skip-review keys that, if honored, would
    reorder the phase graph. Config selects parameter values, never topology."""
    baseline = tt.edge_topology()
    aggressive = {
        "branch-mode": "feature-branch",
        "commit-artifacts": False,
        "backend": "none",
        "default-tier": "complex",
        "default-criticality": "critical",
        "skip-specify": True,
        "skip-review": True,
        "phase": "banana",
    }
    # Selecting parameters does not touch the topology accessor at all.
    tt.resolve_parameters(aggressive)
    assert tt.edge_topology() == baseline


def test_out_of_enum_parameter_value_is_refused() -> None:
    """A recognized parameter key with a value outside its enum raises — a value
    the closed table does not admit is refused, not coerced."""
    with pytest.raises(tt.ClosedTableError):
        tt.resolve_parameters({"default-tier": "gigantic"})
    with pytest.raises(tt.ClosedTableError):
        tt.resolve_parameters({"branch-mode": "rebase-everything"})


def test_in_enum_parameter_value_is_selected() -> None:
    """A recognized parameter key with an in-enum value selects it; defaults
    hold for everything else."""
    resolved = tt.resolve_parameters({"branch-mode": "worktree-interactive"})
    assert resolved["branch_mode"] == "worktree-interactive"
    assert resolved["tier"] == tt.DEFAULT_PARAMETERS["tier"]  # unchanged default


def test_defaults_preserve_todays_local_behavior() -> None:
    """No config → the documented local defaults (byte-identical-to-today)."""
    resolved = tt.resolve_parameters(None)
    assert resolved == tt.DEFAULT_PARAMETERS
    assert resolved is not tt.DEFAULT_PARAMETERS  # fresh dict, defaults not mutated


def test_every_default_is_in_its_enum() -> None:
    for param, value in tt.DEFAULT_PARAMETERS.items():
        assert value in tt.PARAMETERS[param]


# ---------------------------------------------------------------------------
# Structural / R10 append-only invariants
# ---------------------------------------------------------------------------


def test_transition_ids_and_arms_are_unique() -> None:
    ids = [t.id for t in tt.TRANSITIONS]
    arms = [(t.owning_verb, t.decision_state) for t in tt.TRANSITIONS]
    assert len(ids) == len(set(ids))
    assert len(arms) == len(set(arms))


def test_active_ids_never_reuse_reserved_ids() -> None:
    """Reserve-on-deprecate (R10): active identifiers never collide with the
    reserved (retired) sets."""
    assert not (tt.STATE_NAMES & tt.RESERVED_STATE_NAMES)
    assert not ({t.id for t in tt.TRANSITIONS} & tt.RESERVED_TRANSITION_IDS)


def test_all_edge_endpoints_are_declared_states() -> None:
    for t in tt.TRANSITIONS:
        assert t.from_state in tt.STATE_NAMES
        assert t.to_state in tt.STATE_NAMES


def _departure_states_by_verb(transitions) -> dict[str, set[str]]:
    """Group *transitions* by ``owning_verb`` into the set of states each departs from."""
    by_verb: dict[str, set[str]] = {}
    for t in transitions:
        by_verb.setdefault(t.owning_verb, set()).add(t.from_state)
    return by_verb


# The one verb allowed more than one departure, and the exact set it may use.
# Sourced from advance's own declaration rather than restated, so the table and
# the resolver cannot drift apart.
_MULTI_DEPARTURE_VERBS = {"implement_transition": set(adv._IMPLEMENT_DEPARTURE_STATES)}


def test_each_verb_declares_exactly_one_from_state() -> None:
    """A verb IS the gate for the state it fires from, so it cannot have two.

    Programmatic callers rely on this: they omit ``--from-state`` and let the
    composed arm's table ``from_state`` stand as the expected departure phase.
    That is only safe while every arm of a verb agrees. ``_check_invariants``
    does NOT enforce it — it asserts only that ``(owning_verb, decision_state)``
    keys are unique, so a row giving an existing verb a divergent ``from_state``
    passes it cleanly and would silently break those callers.

    ``implement_transition`` is the one sanctioned exception, because a feature
    leaves the implement cluster from either ``implement`` or ``implement-rework``
    and only the log knows which. It is safe there precisely because the verb does
    NOT fall back to the table's ``from_state``: advance resolves the departure
    events-first and passes it to the B1 body, which owns the routing for both.
    The exception is bounded to advance's declared departure set, so a third
    departure still fails here.
    """
    divergent = {
        verb: sorted(states)
        for verb, states in _departure_states_by_verb(tt.TRANSITIONS).items()
        if len(states) != 1 and states != _MULTI_DEPARTURE_VERBS.get(verb)
    }
    assert not divergent, f"verbs with more than one departure state: {divergent}"


def test_the_multi_departure_exception_is_bounded() -> None:
    """A departure outside advance's declared set is still a failure.

    Guards the carve-out above from degenerating into "implement_transition may
    depart anything".
    """
    rogue = dataclasses.replace(
        tt.transition_by_arm("implement_transition", "review"),
        id="implement.rogue",
        decision_state="rogue",
        from_state="specify",
    )
    divergent = {
        verb: states
        for verb, states in _departure_states_by_verb([*tt.TRANSITIONS, rogue]).items()
        if len(states) != 1 and states != _MULTI_DEPARTURE_VERBS.get(verb)
    }
    assert "implement_transition" in divergent


def test_the_from_state_invariant_check_catches_a_divergent_row() -> None:
    """The grouping above must be able to fail — pinned against a synthetic row.

    Without this the invariant test is indistinguishable from one that asserts
    nothing, since today's table satisfies it.
    """
    rogue = dataclasses.replace(
        tt.transition_by_arm("review_verdict", "approved"),
        id="review.rogue",
        decision_state="rogue",
        from_state="implement",
    )
    divergent = {
        verb: states
        for verb, states in _departure_states_by_verb([*tt.TRANSITIONS, rogue]).items()
        if len(states) != 1
    }
    assert "review_verdict" in divergent


def test_frozen_rows_are_immutable() -> None:
    """The rows are structurally immutable (frozen dataclasses) — the encoding
    that enforces the append-only source-of-truth discipline."""
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        tt.TRANSITIONS[0].to_state = "hacked"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        tt.STATES[0].name = "hacked"  # type: ignore[misc]


def test_pause_spec_only_on_pause_holds_and_uses_known_kind() -> None:
    """The one B1 pause arm (plan wait-approved) carries the accountable pause
    slug + a known kind; no other arm carries a pause spec."""
    paused = [t for t in tt.TRANSITIONS if t.pause is not None]
    assert [t.id for t in paused] == ["plan.wait-approved"]
    spec = paused[0].pause
    assert spec.slug == "plan-approval"
    assert spec.kind in tt.PAUSE_KINDS
    assert paused[0].edge_kind == tt.EDGE_KIND_PAUSE_HOLD


def test_legacy_display_phase_matches_state_name_except_cancelled() -> None:
    """Every state the legacy artifact reader can itself produce projects to its
    own name; only the event-only terminal cancelled projects to complete."""
    for s in tt.STATES:
        if s.name == "cancelled":
            assert s.legacy_display_phase == "complete"
        else:
            assert s.legacy_display_phase == s.name
