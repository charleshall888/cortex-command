"""Three-way SERVED-pause-spec parity: TOML registry ↔ table ↔ envelope (R17).

This is the *parity half* of spec R17 (the routing half landed with the loop
rewiring). ``skills/lifecycle/references/kept-pauses-data.toml`` is, as of Phase C,
the SERVED pause-spec registry: a row carrying ``served_from_state`` declares that
the served ``cortex-lifecycle-next`` envelope for that lifecycle state renders the
pause from the wheel-owned transition table's ``PauseSpec``.

The three layers live in three independent homes and must agree exactly, so no
layer can silently drift:

  * **Home 1 — the TOML registry** (``kept-pauses-data.toml``): the rows carrying
    ``served_from_state``. Read here directly via ``tomllib`` (NOT through the
    transition table or the envelope), so this home is genuinely independent.
  * **Home 2 — the closed transition table**
    (``cortex_command.lifecycle.transition_table``): the ``TRANSITIONS`` rows that
    carry a ``PauseSpec``. The pair asserted is ``(pause.slug, pause.kind,
    from_state)`` — a pause HOLDS at its ``from_state``.
  * **Home 3 — the served envelope** (``cortex_command.lifecycle.next_verb``): the
    ``pause_spec.specs`` entries the served ``next`` envelope carries for each
    table state. Built by calling the real ``build_served_envelope`` per state and
    reading its output (NOT by re-deriving from the table by hand).

**The exact parity relation asserted** — a THREE-way set-equality over
``(slug, kind, state)`` triples:

    {(id, kind, served_from_state) : TOML rows with served_from_state}
      == {(pause.slug, pause.kind, from_state) : table transitions with a pause}
      == {(spec.slug, spec.kind, state) : served envelope pause_spec.specs, per state}

**Honest subset relation (why this is NOT 18-way equality).** The TOML enumerates
all 18 kept-pause SITES; the closed table encodes a ``PauseSpec`` only for
event-backed pause-gated STATES — today exactly one, ``plan-approval`` (the
``plan.wait-approved`` hold at state ``plan``). The other 17 rows are prose
affordances / judgment- or config-conditional pauses the served path does not
structurally enforce (C+1 boundary, spec R12), so they carry no
``served_from_state`` and are deliberately OUTSIDE this equality. A test that
forced all 18 rows into the table/envelope would be dishonest. Instead we assert:
(1) the three SERVED layers are set-equal, and (2) every ``served_from_state`` row
is a genuine subset of the full TOML inventory (i.e. it did not invent an id that
the marker/inventory parity test — ``test_lifecycle_kept_pauses_parity.py`` — does
not also cover).

"Freshness" for the served registry IS this set-equality: it fails in both
directions — a ``served_from_state`` row with no table/envelope pause, and a table
pause with no registry row — so neither the registry, the table, nor the envelope
can drift out of lockstep with the other two.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from cortex_command.lifecycle import next_verb
from cortex_command.lifecycle import transition_table as tt

REPO_ROOT = Path(__file__).resolve().parent.parent
KEPT_PAUSES_DATA = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "kept-pauses-data.toml"
)

# A dummy log path: build_served_envelope does no I/O on it (it is stringified for
# the advance contract and passed to the pure resolve_flock_path), so any path
# value produces the same pause_spec, which is all this test reads.
_DUMMY_LOG = Path("/dev/null")


# ---------------------------------------------------------------------------
# Independent readers — one per home
# ---------------------------------------------------------------------------


def _toml_served_triples() -> set[tuple[str, str, str]]:
    """Home 1: (id, kind, served_from_state) for TOML rows that are served."""
    with KEPT_PAUSES_DATA.open("rb") as fh:
        rows = tomllib.load(fh).get("pause", [])
    return {
        (row["id"], row["kind"], row["served_from_state"])
        for row in rows
        if row.get("served_from_state") is not None
    }


def _toml_all_ids() -> set[str]:
    """Every TOML id (the full kept-pause inventory) — for the subset check."""
    with KEPT_PAUSES_DATA.open("rb") as fh:
        rows = tomllib.load(fh).get("pause", [])
    return {row["id"] for row in rows}


def _table_pause_triples() -> set[tuple[str, str, str]]:
    """Home 2: (pause.slug, pause.kind, from_state) for table transitions with a
    pause. A pause HOLDS at its from_state, so from_state is the served state."""
    return {
        (t.pause.slug, t.pause.kind, t.from_state)
        for t in tt.TRANSITIONS
        if t.pause is not None
    }


def _envelope_pause_triples() -> set[tuple[str, str, str]]:
    """Home 3: (slug, kind, state) from the served envelope's pause_spec.specs,
    built by calling the real build_served_envelope for every table state."""
    triples: set[tuple[str, str, str]] = set()
    for state in sorted(tt.STATE_NAMES):
        envelope = next_verb.build_served_envelope(
            state=state, events_log=_DUMMY_LOG, reduction=None
        )
        for spec in envelope["pause_spec"]["specs"]:
            triples.add((spec["slug"], spec["kind"], state))
    return triples


# ---------------------------------------------------------------------------
# The three-way parity
# ---------------------------------------------------------------------------


def test_served_registry_equals_table_pause_specs() -> None:
    """TOML served rows == table PauseSpec rows (keyed on slug/kind/state)."""
    toml = _toml_served_triples()
    table = _table_pause_triples()
    assert toml, (
        "no served_from_state rows in kept-pauses-data.toml — the served "
        "pause-spec registry is empty; expected at least plan-approval"
    )
    assert toml == table, (
        f"registry-vs-table drift: only in TOML registry {sorted(toml - table)}; "
        f"only in transition table {sorted(table - toml)}"
    )


def test_table_pause_specs_equal_served_envelopes() -> None:
    """Table PauseSpec rows == served envelope pause specs (per pause-gated state)."""
    table = _table_pause_triples()
    envelope = _envelope_pause_triples()
    assert table == envelope, (
        f"table-vs-envelope drift: only in table {sorted(table - envelope)}; "
        f"only in served envelopes {sorted(envelope - table)}"
    )


def test_three_way_served_parity() -> None:
    """All three served layers agree exactly — the closing invariant."""
    toml = _toml_served_triples()
    table = _table_pause_triples()
    envelope = _envelope_pause_triples()
    assert toml == table == envelope, (
        "three-way served pause-spec parity broken:\n"
        f"  TOML registry: {sorted(toml)}\n"
        f"  transition table: {sorted(table)}\n"
        f"  served envelopes: {sorted(envelope)}"
    )


def test_served_rows_are_subset_of_full_inventory() -> None:
    """Every served_from_state row is a real kept-pause id (no invented registry
    entry that the marker/inventory parity test does not also cover)."""
    served_ids = {sid for sid, _kind, _state in _toml_served_triples()}
    all_ids = _toml_all_ids()
    orphans = served_ids - all_ids
    assert not orphans, (
        f"served_from_state rows name ids absent from the kept-pause inventory: "
        f"{sorted(orphans)}"
    )
    # This IS a strict subset today (17 unserved prose/judgment/config pauses):
    # guards against a future collapse that would silently make the served
    # registry the whole inventory without a deliberate decision.
    assert served_ids < all_ids, (
        "every kept-pause is marked served_from_state — the honest subset "
        "relation (only event-backed pause-gated states are served) has been "
        "collapsed; if intentional, update this test and the R17 rationale"
    )


def test_served_states_are_real_table_states() -> None:
    """Every served_from_state names a real, non-terminal transition-table state
    that actually renders the pause in its served envelope."""
    states_by_name = tt.states_by_name()
    problems: list[str] = []
    for slug, _kind, state in _toml_served_triples():
        st = states_by_name.get(state)
        if st is None:
            problems.append(f"{slug}: served_from_state {state!r} is not a table state")
            continue
        if st.terminal:
            problems.append(f"{slug}: served_from_state {state!r} is terminal")
        envelope = next_verb.build_served_envelope(
            state=state, events_log=_DUMMY_LOG, reduction=None
        )
        served_slugs = {s["slug"] for s in envelope["pause_spec"]["specs"]}
        if slug not in served_slugs:
            problems.append(
                f"{slug}: not rendered in the served envelope for state {state!r}"
            )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Negative controls — assert the parity actually catches drift on bad input.
# These operate on synthetic in-memory sets; they never touch the tree.
# ---------------------------------------------------------------------------


def test_negative_registry_row_without_table_pause() -> None:
    """A served registry row with no matching table pause is a detectable drift."""
    toml = {("plan-approval", "relayed-consent", "plan"), ("ghost", "question", "review")}
    table = {("plan-approval", "relayed-consent", "plan")}
    assert toml != table
    assert toml - table == {("ghost", "question", "review")}


def test_negative_table_pause_without_registry_row() -> None:
    """A table pause with no served registry row is a detectable drift."""
    toml = {("plan-approval", "relayed-consent", "plan")}
    table = {
        ("plan-approval", "relayed-consent", "plan"),
        ("spec-approval", "relayed-consent", "specify"),
    }
    assert toml != table
    assert table - toml == {("spec-approval", "relayed-consent", "specify")}


def test_negative_kind_mismatch_is_detected() -> None:
    """A slug/state match whose kind drifted is NOT set-equal (triple includes kind)."""
    toml = {("plan-approval", "relayed-consent", "plan")}
    table = {("plan-approval", "question", "plan")}
    assert toml != table
