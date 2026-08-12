"""Tests for the backlog navigator's dependency graph.

Three populations, deliberately:

* **Synthetic fixtures** for the edge semantics that the real corpora do not
  happen to contain — a cycle, a self-block, an unresolvable ref, an edge
  declared only by the blocker.
* **Frozen slices of the two real corpora**, transcribed from the snapshots
  taken on 2026-08-11. These pin the exact numbers (8 board edges, 3
  discharged edges, 2 lapsed holds) that a moving corpus cannot be asked to
  hold still for.
* **The live corpora**, when they are on this machine. These assert the
  durable claims only — every reference normalizes to a known ticket, the
  three edge classes partition the edge list — so adding a ticket to either
  repo cannot turn the suite red.

The frozen slices carry ids, statuses and declarations verbatim. Titles are
carried only for the tickets that participate in an edge, because those are
the only ones the graph reads a title for; the rest would be transcription
noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.dashboard.backlog.graph import Graph, build_graph, normalize_ref

# ---------------------------------------------------------------------------
# Frozen slice: wild-light, 2026-08-11 (73 board records, 44 corpus refs)
# ---------------------------------------------------------------------------

_WL_STATUS: dict[str, str] = {
    "abandoned": "103",
    "backlog": (
        "139 147 148 226 236 242 263 276 278 281 284 290 328 331 334 344 364 "
        "381 384 388 395 407 417 424 425 430 433 434 439 447 466 471 475 478 "
        "483 484 485 486 487 488 489 490 491 492 493 494 495 496 497 498 499 "
        "500 501 502 503 507 508 509 510 511 512"
    ),
    "deferred": "138 247 257 286 287 329 330 419",
    "new": "513 514 515",
}

# id -> (blocked_by, blocks), verbatim from the snapshot. Note #331/#278: the
# blocker declares `blocks` and the blocked declares `blocked_by`, which is
# the corpus' only two-sided declaration inside the active slice.
_WL_REFS: dict[str, tuple[list[str], list[str]]] = {
    "242": (["331"], []),
    "276": (["265"], []),
    "278": (["265", "331"], []),
    "331": ([], ["278"]),
    "388": (["242"], []),
    "417": (["242"], []),
    "430": (["424"], []),
    "439": (["432"], []),
}

_WL_TITLES: dict[str, str] = {
    "242": "Multi-island streaming + late-join (Stage C, needs MP design pass)",
    "276": "Darkness-danger contract (no direct damage; splash-out douse)",
    "278": "Dungeon / interior lighting model",
    "331": "Dungeon space: enterable interior + load path",
    "388": "Crossing vista: zoom-out and real old-island submersion on the drawbridge",
    "417": "Crossings have no camera driver: crossing_dolly.gd was deleted with no 3D successor",
    "424": "Enemy presence tell renders as a solid red blob instead of eye-pair + weapon-tip glow points",
    "430": "Measure the emissive_enemy fixture-vs-production over-weighting magnitude on a real wave enemy",
    "439": "Express MigrationCoordinator's lifecycle as an explicit phase enum (retaining the one-shot guards)",
}

# Both blockers live outside the active slice and both are already finished.
# They are the whole reason `corpus` is a separate argument from `items`.
_WL_OFF_BOARD: dict[str, tuple[str, str]] = {
    "265": ("complete", "Replicated day/night clock + light state"),
    "432": (
        "complete",
        "Survivor ENet detection skew (up to ~18s) exceeds the 5s finalize "
        "watchdog — late-detecting survivors miss the migration",
    ),
}

# ---------------------------------------------------------------------------
# Frozen slice: cortex-command, 2026-08-11 (4 board records, 0 edges, 0 epics)
# ---------------------------------------------------------------------------

_CC_SLICE: list[tuple[str, str]] = [
    ("156", "deferred"),
    ("295", "deferred"),
    ("466", "should-have"),
    ("478", "backlog"),
]


def _record(item_id: str, status: str, **extra) -> dict:
    """Build one backlog-shaped record with only the fields the graph reads."""
    return {"id": item_id, "status": status, "title": None, **extra}


def wild_light_slice() -> dict[str, dict]:
    """Return the frozen wild-light active slice, id-keyed as the snapshot is."""
    items: dict[str, dict] = {}
    for status, ids in _WL_STATUS.items():
        for item_id in ids.split():
            blocked_by, blocks = _WL_REFS.get(item_id, ([], []))
            items[item_id] = _record(
                item_id,
                status,
                title=_WL_TITLES.get(item_id),
                blocked_by=list(blocked_by),
                blocks=list(blocks),
            )
    return items


def wild_light_corpus() -> list[dict]:
    """Return the frozen slice plus the two finished off-board blockers."""
    corpus = list(wild_light_slice().values())
    corpus += [
        _record(item_id, status, title=title)
        for item_id, (status, title) in _WL_OFF_BOARD.items()
    ]
    return corpus


def cortex_command_slice() -> dict[str, dict]:
    """Return the frozen cortex-command slice: four items, no declarations."""
    return {
        item_id: _record(item_id, status, blocked_by=[], blocks=[])
        for item_id, status in _CC_SLICE
    }


def _live_corpus(root: Path) -> tuple[dict[str, dict], list[dict]] | None:
    """Load a real repo's slice and corpus, or None when it is not present."""
    if not (root / "cortex" / "backlog").is_dir():
        return None
    from cortex_command.backlog.generate_index import collect_items

    active, _active_ids, _archive_ids, all_items = collect_items(
        root / "cortex" / "backlog", root / "cortex" / "lifecycle"
    )
    return {str(rec["id"]): rec for rec in active}, all_items


_WILD_LIGHT_ROOT = Path.home() / "Workspaces" / "wild-light"
_CORTEX_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# normalize_ref — the four spellings the real corpus actually contains
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The four spellings measured across wild-light's 44 references.
        ("013", "13"),          # quoted, zero-padded
        (16, "16"),             # bare int, as a YAML loader would hand it over
        ("016", "16"),          # the octal-looking spelling, read as a string
        (170, "170"),           # bare int, no padding
        ("88", "88"),           # unpadded string (cortex-command's corpus)
        # Null spellings, all of which must erase the reference entirely.
        (None, None),
        ("", None),
        ("   ", None),
        ("null", None),
        ("NULL", None),
        ("None", None),
        ("~", None),
        ("[]", None),
        # Decoration around a real id.
        ("#331", "331"),
        (" 242 ", "242"),
        ("0", "0"),
    ],
)
def test_normalize_ref_spellings(raw, expected):
    assert normalize_ref(raw) == expected


def test_normalize_ref_rejects_bool():
    """``True`` is an int subclass and would otherwise resolve to ticket #1."""
    assert normalize_ref(True) is None
    assert normalize_ref(False) is None


def test_normalize_ref_keeps_uuid_intact():
    """A UUID must not be digit-extracted into whatever ticket it happens to hit."""
    uuid = "b734b65c-7f1a-43ac-8796-15d17277d06c"
    assert normalize_ref(uuid) == uuid


def test_normalize_ref_keeps_digit_free_reference():
    """Work tracked outside this backlog stays visible rather than vanishing."""
    assert normalize_ref("upstream-godot-issue") == "upstream-godot-issue"


# ---------------------------------------------------------------------------
# Edge semantics: either side may declare, and the graph records which did
# ---------------------------------------------------------------------------


def test_edge_declared_by_blocked_side_only():
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=[]),
        "2": _record("2", "backlog", blocked_by=["1"], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == [("1", "2")]
    assert graph.declared_by[("1", "2")] == "blocked_by"


def test_edge_declared_by_blocker_side_only():
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=["2"]),
        "2": _record("2", "backlog", blocked_by=[], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == [("1", "2")]
    assert graph.declared_by[("1", "2")] == "blocks"


def test_edge_declared_by_both_sides_is_deduped_once():
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=["2"]),
        "2": _record("2", "backlog", blocked_by=["1"], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == [("1", "2")]
    assert graph.declared_by[("1", "2")] == "both"


def test_declaration_reached_only_through_the_corpus_still_makes_an_edge():
    """A finished blocker whose own `blocks` list names an active ticket.

    The active ticket never mentions it, so scanning the slice alone would
    lose the edge — and with it the fact that the hold has lapsed.
    """
    items = {"2": _record("2", "backlog", blocked_by=[], blocks=[])}
    corpus = [
        _record("1", "complete", blocked_by=[], blocks=["2"]),
        *items.values(),
    ]
    graph = build_graph(items, corpus)
    assert graph.edges == [("1", "2")]
    assert graph.discharged == [("1", "2")]


def test_edge_between_two_off_board_tickets_is_dropped():
    """Corpus history is not board state."""
    items = {"9": _record("9", "backlog", blocked_by=[], blocks=[])}
    corpus = [
        _record("1", "complete", blocked_by=[], blocks=["2"]),
        _record("2", "complete", blocked_by=["1"], blocks=[]),
        *items.values(),
    ]
    graph = build_graph(items, corpus)
    assert graph.edges == []


def test_zero_padded_and_bare_declarations_collapse_to_one_edge():
    """`blocked-by: ["013"]` and `blocks: [13]` name the same edge."""
    items = {
        "13": _record("13", "backlog", blocked_by=[], blocks=[14]),
        "14": _record("14", "backlog", blocked_by=["013"], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == [("13", "14")]
    assert graph.declared_by[("13", "14")] == "both"


def test_null_declarations_produce_no_edges():
    items = {
        "1": _record("1", "backlog", blocked_by=None, blocks=[]),
        "2": _record("2", "backlog", blocked_by=["null"], blocks=None),
        "3": _record("3", "backlog"),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == []
    assert graph.blocked_by_titles == {}


def test_scalar_declaration_reads_as_a_one_element_list():
    """The legacy `blocked-by: 411` spelling is still in the corpus."""
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=[]),
        "2": _record("2", "backlog", blocked_by=1, blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.edges == [("1", "2")]


# ---------------------------------------------------------------------------
# The three classes are distinct, and they partition the edge list
# ---------------------------------------------------------------------------


def test_live_discharged_external_partition_the_edges():
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=[]),
        "2": _record("2", "backlog", blocked_by=["1"], blocks=[]),
        "3": _record("3", "backlog", blocked_by=["50"], blocks=[]),   # finished, off-board
        "4": _record("4", "backlog", blocked_by=["60"], blocks=[]),   # open, off-board
        "5": _record("5", "backlog", blocked_by=["999"], blocks=[]),  # no such ticket
    }
    corpus = [
        *items.values(),
        _record("50", "complete"),
        _record("60", "backlog"),
    ]
    graph = build_graph(items, corpus)

    assert graph.live == [("1", "2")]
    assert graph.discharged == [("50", "3")]
    assert graph.external == [("60", "4"), ("999", "5")]
    assert graph.unresolvable == [("999", "5")]

    classes = [set(graph.live), set(graph.discharged), set(graph.external)]
    assert sum(len(bucket) for bucket in classes) == len(graph.edges)
    assert set().union(*classes) == set(graph.edges)
    assert set(graph.unresolvable) <= set(graph.external)


@pytest.mark.parametrize("terminal", ["complete", "done", "wontfix", "abandoned"])
def test_terminal_blocker_discharges_the_edge(terminal):
    items = {"2": _record("2", "backlog", blocked_by=["1"], blocks=[])}
    corpus = [*items.values(), _record("1", terminal)]
    graph = build_graph(items, corpus)
    assert graph.discharged == [("1", "2")]
    assert graph.live == []


def test_terminal_status_beats_off_board_membership():
    """A finished archived blocker is a lapsed hold, not off-board noise."""
    items = {"2": _record("2", "backlog", blocked_by=["1"], blocks=[])}
    graph = build_graph(items, [*items.values(), _record("1", "complete")])
    assert graph.discharged == [("1", "2")]
    assert graph.external == []


def test_terminal_blocker_inside_the_slice_also_discharges():
    """The slice carries closed epics; a closed one still holds nothing."""
    items = {
        "1": _record("1", "complete", blocked_by=[], blocks=[]),
        "2": _record("2", "backlog", blocked_by=["1"], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.discharged == [("1", "2")]
    assert graph.live == []


def test_hold_lapses_only_when_every_blocker_is_discharged():
    items = {
        "3": _record("3", "backlog", blocked_by=["1"], blocks=[]),
        "4": _record("4", "backlog", blocked_by=["1", "2"], blocks=[]),
        "2": _record("2", "backlog", blocked_by=[], blocks=[]),
    }
    corpus = [*items.values(), _record("1", "complete")]
    graph = build_graph(items, corpus)
    # #4 keeps a live blocker in #2, so its hold has not lapsed even though
    # one of its two declared blockers is finished.
    assert graph.hold_lapsed == ["3"]


def test_blocked_by_titles_resolve_off_board_titles():
    items = {"2": _record("2", "backlog", blocked_by=["1"], blocks=[])}
    corpus = [*items.values(), _record("1", "complete", title="Finished work")]
    graph = build_graph(items, corpus)
    assert graph.blocked_by_titles == {
        "2": [
            {
                "ref": "1",
                "title": "Finished work",
                "status": "complete",
                "kind": "discharged",
            }
        ]
    }


def test_blocked_by_titles_flag_an_unresolvable_ref():
    items = {"2": _record("2", "backlog", blocked_by=["999"], blocks=[])}
    graph = build_graph(items, list(items.values()))
    assert graph.blocked_by_titles["2"] == [
        {"ref": "999", "title": None, "status": None, "kind": "unresolvable"}
    ]


def test_status_spelling_variants_still_discharge():
    """Raw frontmatter spellings reach this module unnormalized."""
    items = {"2": _record("2", "backlog", blocked_by=["1"], blocks=[])}
    corpus = [*items.values(), _record("1", "  WONT_DO ")]
    graph = build_graph(items, corpus)
    assert graph.discharged == [("1", "2")]


# ---------------------------------------------------------------------------
# Closures: live edges only, every slice id present, cycle-safe
# ---------------------------------------------------------------------------


def test_closure_runs_over_live_edges_only():
    """A discharged edge must not carry leverage across it."""
    items = {
        "2": _record("2", "backlog", blocked_by=["1"], blocks=["3"]),
        "3": _record("3", "backlog", blocked_by=[], blocks=["4"]),
        "4": _record("4", "backlog", blocked_by=[], blocks=[]),
    }
    corpus = [*items.values(), _record("1", "complete")]
    graph = build_graph(items, corpus)
    assert graph.direct["2"] == {"3"}
    assert graph.downstream["2"] == {"3", "4"}
    assert graph.downstream["3"] == {"4"}
    assert graph.downstream["4"] == set()


def test_direct_and_downstream_cover_every_slice_id():
    """Consumers subscript these maps; a missing key would be a KeyError."""
    items = wild_light_slice()
    graph = build_graph(items, wild_light_corpus())
    assert set(graph.direct) == set(items)
    assert set(graph.downstream) == set(items)


def test_closure_never_leaves_the_slice():
    items = {"1": _record("1", "backlog", blocked_by=[], blocks=["77"])}
    corpus = [*items.values(), _record("77", "backlog")]
    graph = build_graph(items, corpus)
    # The blocked side is off-board, so the edge is external, not live.
    assert graph.external == [("1", "77")]
    assert graph.direct["1"] == set()


def test_cycle_terminates_and_is_reported():
    items = {
        "1": _record("1", "backlog", blocked_by=["3"], blocks=["2"]),
        "2": _record("2", "backlog", blocked_by=[], blocks=["3"]),
        "3": _record("3", "backlog", blocked_by=[], blocks=[]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.cycles == [["1", "2", "3"]]
    # Terminates. `_closure` is cycle-safe on its own — a node already seen is
    # never expanded twice — which is why the wave relaxation that used to
    # consume the cycle index could go without taking this guarantee with it.
    assert graph.downstream["1"] == {"2", "3"}


def test_self_block_is_a_cycle_and_does_not_hang():
    items = {"1": _record("1", "backlog", blocked_by=["1"], blocks=[])}
    graph = build_graph(items, list(items.values()))
    assert graph.cycles == [["1"]]
    # Excluded from its own reachable set even though the cycle reaches it.
    assert graph.downstream["1"] == set()


def test_two_disjoint_cycles_are_reported_separately():
    items = {
        "1": _record("1", "backlog", blocked_by=[], blocks=["2"]),
        "2": _record("2", "backlog", blocked_by=[], blocks=["1"]),
        "8": _record("8", "backlog", blocked_by=[], blocks=["9"]),
        "9": _record("9", "backlog", blocked_by=[], blocks=["8"]),
    }
    graph = build_graph(items, list(items.values()))
    assert graph.cycles == [["1", "2"], ["8", "9"]]


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------


def test_empty_inputs_yield_a_schema_complete_graph():
    graph = build_graph({}, [])
    assert isinstance(graph, Graph)
    assert graph.edges == []
    assert graph.declared_by == {}
    assert graph.live == graph.discharged == graph.external == []
    assert graph.downstream == graph.direct == {}
    assert graph.blocked_by_titles == {}
    assert graph.unresolvable == []
    assert graph.cycles == []
    assert graph.hold_lapsed == []


def test_empty_corpus_degrades_every_blocker_to_unresolvable():
    items = {"2": _record("2", "backlog", blocked_by=["1"], blocks=[])}
    graph = build_graph(items, [])
    assert graph.unresolvable == [("1", "2")]
    assert graph.live == []


def test_build_is_deterministic():
    """The 30s poll re-renders this; an unstable order would churn the DOM."""
    first = build_graph(wild_light_slice(), wild_light_corpus())
    second = build_graph(wild_light_slice(), wild_light_corpus())
    assert first == second


# ---------------------------------------------------------------------------
# Frozen real corpora
# ---------------------------------------------------------------------------


def test_wild_light_frozen_slice_edges():
    graph = build_graph(wild_light_slice(), wild_light_corpus())
    assert graph.edges == [
        ("242", "388"),
        ("242", "417"),
        ("265", "276"),
        ("265", "278"),
        ("331", "242"),
        ("331", "278"),
        ("424", "430"),
        ("432", "439"),
    ]
    # The slice's only two-sided declaration.
    assert graph.declared_by[("331", "278")] == "both"
    assert [
        edge for edge, side in graph.declared_by.items() if side == "both"
    ] == [("331", "278")]
    assert graph.unresolvable == []
    assert graph.cycles == []


def test_wild_light_frozen_slice_edge_classes():
    graph = build_graph(wild_light_slice(), wild_light_corpus())
    assert graph.live == [
        ("242", "388"),
        ("242", "417"),
        ("331", "242"),
        ("331", "278"),
        ("424", "430"),
    ]
    # Three discharged *edges*: both of #265's dependents plus #439's.
    assert graph.discharged == [("265", "276"), ("265", "278"), ("432", "439")]
    assert graph.external == []


def test_wild_light_frozen_slice_has_exactly_two_lapsed_holds():
    """#276→#265 and #439→#432 — startable and don't know it.

    #278 also names the finished #265, but #331 still holds it, so its hold
    has not lapsed. That is why the lapsed-hold count (2) is one lower than
    the discharged-edge count (3).
    """
    graph = build_graph(wild_light_slice(), wild_light_corpus())
    assert graph.hold_lapsed == ["276", "439"]
    assert [row["ref"] for row in graph.blocked_by_titles["276"]] == ["265"]
    assert [row["ref"] for row in graph.blocked_by_titles["439"]] == ["432"]


def test_wild_light_frozen_slice_keystone_leverage():
    """#331 holds four of the five genuinely blocked tickets, through two hops."""
    graph = build_graph(wild_light_slice(), wild_light_corpus())
    assert graph.direct["331"] == {"242", "278"}
    assert graph.downstream["331"] == {"242", "278", "388", "417"}
    live_blocked = {blocked for _blocker, blocked in graph.live}
    assert live_blocked == {"242", "278", "388", "417", "430"}


def test_wild_light_frozen_slice_names_its_blockers():
    """The blocked row must be able to print the blocker's id *and* title."""
    graph = build_graph(wild_light_slice(), wild_light_corpus())
    rows = graph.blocked_by_titles["278"]
    assert [(row["ref"], row["kind"]) for row in rows] == [
        ("265", "discharged"),
        ("331", "live"),
    ]
    # #265 lives outside the slice; its title resolves through the corpus.
    assert rows[0]["title"] == _WL_OFF_BOARD["265"][1]
    assert rows[1]["title"] == _WL_TITLES["331"]


def test_cortex_command_frozen_slice_is_degenerate_but_complete():
    items = cortex_command_slice()
    graph = build_graph(items, list(items.values()))
    assert graph.edges == []
    assert graph.live == graph.discharged == graph.external == []
    assert graph.hold_lapsed == []
    assert graph.blocked_by_titles == {}
    assert set(graph.direct) == set(items)
    assert all(not dependents for dependents in graph.direct.values())
    # `should-have` is outside the documented status vocabulary and must not
    # be mistaken for terminal, so every record still reaches the closure maps.
    assert set(graph.downstream) == set(items)


# ---------------------------------------------------------------------------
# Live corpora — durable claims only, so a new ticket cannot turn these red
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "root", [_WILD_LIGHT_ROOT, _CORTEX_ROOT], ids=["wild-light", "cortex-command"]
)
def test_live_corpus_references_all_normalize_to_known_tickets(root):
    """Every declared reference in the corpus resolves once normalized.

    Measured 2026-08-11: wild-light 44 references, cortex-command 15, zero
    unresolvable on either. The counts are pinned on the frozen slices above;
    here only the zero is asserted, because both corpora are still moving.
    """
    loaded = _live_corpus(root)
    if loaded is None:
        pytest.skip(f"corpus not present: {root}")
    _items, all_items = loaded

    known = {normalize_ref(rec.get("id")) for rec in all_items}
    seen = 0
    unresolved = []
    for record in all_items:
        for field in ("blocked_by", "blocks"):
            raw = record.get(field) or []
            if not isinstance(raw, list):
                raw = [raw]
            for ref in raw:
                normalized = normalize_ref(ref)
                if normalized is None:
                    continue
                seen += 1
                if normalized not in known:
                    unresolved.append((record.get("id"), field, ref, normalized))

    assert seen > 0
    assert unresolved == []


@pytest.mark.parametrize(
    "root", [_WILD_LIGHT_ROOT, _CORTEX_ROOT], ids=["wild-light", "cortex-command"]
)
def test_live_corpus_graph_invariants(root):
    loaded = _live_corpus(root)
    if loaded is None:
        pytest.skip(f"corpus not present: {root}")
    items, all_items = loaded
    graph = build_graph(items, all_items)

    classes = [set(graph.live), set(graph.discharged), set(graph.external)]
    assert sum(len(bucket) for bucket in classes) == len(graph.edges)
    assert set().union(*classes, set()) == set(graph.edges)
    assert set(graph.unresolvable) <= set(graph.external)
    assert graph.cycles == []
    assert set(graph.direct) == set(items)
    assert set(graph.hold_lapsed) <= set(graph.blocked_by_titles)
    # Every live edge stays on the board, which is what makes the closure safe.
    assert all(a in items and b in items for a, b in graph.live)
    assert build_graph(items, all_items) == graph
