"""Unit tests for cortex_command/dashboard/backlog/score.py.

Three of these tests defend properties that no rendered page can show is
broken, which is why they exist at this layer rather than in the render
suite:

* **Keystone-first ordering.** The board's whole editorial claim is that
  leverage beats declared priority. If that inverts, every page still
  renders, every other test still passes, and the operator is simply told to
  work on the wrong ticket. :meth:`KeystoneOrderingTest` pins the exact
  documented case — #331 (``priority: low``) above #147 (``priority: high``)
  — against the real dev-corpus records.
* **No wall-clock read.** ``stale`` anchors to ``max(updated)`` across the
  corpus. A wall-clock anchor would produce a different score at midnight on
  unchanged data, morphing the whole board on the 30s poll. Asserted by
  monkeypatching ``date.today`` to an absurd value and comparing the full
  term-by-term output, not just the totals.
* **Totality over open vocabularies.** ``priority``/``type``/``status`` are
  documented as enums and open in practice, so a fixture of deliberate
  garbage must score rather than raise.

Fixture provenance: the ``_DEV_SLICE`` records are verbatim frontmatter from
the wild-light corpus (the 73-item active slice the design was measured on),
narrowed to the #331 keystone subgraph plus the #139 epic that #147 sits in.
They are inlined rather than read from a file so the assertion travels with
the property it defends. ``_TINY_SLICE`` is the shape of cortex-command's own
4-item slice: no epics, no in-slice edges.

The graph is stubbed here, not built. ``score.py`` reads ``Graph`` by
attribute and never calls into it, so a stand-in carrying the documented
fields exercises exactly the surface under test and keeps these assertions
independent of ``graph.py``'s build path. One test picks up the real
``build_graph`` when it is importable and asserts totality against it.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import date

from cortex_command.dashboard.backlog.score import (
    PRIORITY_W,
    TERM_META,
    UNKNOWN_PRIORITY,
    Score,
    ScoreContext,
    contenders,
    corpus_as_of,
    counterfactual,
    is_contender,
    rank_key,
    score_of,
)

TERMINAL_STATUSES = {"complete", "done", "wontfix", "abandoned"}


# ---------------------------------------------------------------------------
# Graph stand-in
# ---------------------------------------------------------------------------


@dataclass
class _StubGraph:
    """The documented ``Graph`` read surface, and nothing else.

    Deliberately not a subclass of the real dataclass: these tests are about
    the ranking, and coupling them to ``graph.py``'s constructor would make a
    field added there fail a scoring test for no scoring reason.
    """

    edges: list[tuple[str, str]] = field(default_factory=list)
    live: list[tuple[str, str]] = field(default_factory=list)
    discharged: list[tuple[str, str]] = field(default_factory=list)
    external: list[tuple[str, str]] = field(default_factory=list)
    declared_by: dict[tuple[str, str], str] = field(default_factory=dict)
    direct: dict[str, set[str]] = field(default_factory=dict)
    downstream: dict[str, set[str]] = field(default_factory=dict)


def _stub_graph(items: dict[str, dict], edges: list[tuple[str, str]]) -> _StubGraph:
    """Derive the documented graph fields from records + a raw edge list.

    An edge is *live* unless its blocker is terminal or missing from the
    slice, mirroring ``graph.py``'s stated classification; ``direct`` and
    ``downstream`` are then closed over the live subset only. Written out
    rather than imported so the fixture's intent is readable at the call site.
    """
    graph = _StubGraph(edges=sorted(set(edges)))
    for blocker, blocked in graph.edges:
        record = items.get(blocker)
        if record is None:
            graph.external.append((blocker, blocked))
        elif str(record.get("status", "")).lower() in TERMINAL_STATUSES:
            graph.discharged.append((blocker, blocked))
        else:
            graph.live.append((blocker, blocked))

        blocked_record = items.get(blocked) or {}
        declares_blocks = blocked in _blocker_side(items, blocker)
        declares_blocked_by = blocker in {
            str(x) for x in (blocked_record.get("blocked_by") or [])
        }
        if declares_blocks and declares_blocked_by:
            graph.declared_by[(blocker, blocked)] = "both"
        elif declares_blocked_by:
            graph.declared_by[(blocker, blocked)] = "blocked_by"
        else:
            graph.declared_by[(blocker, blocked)] = "blocks"

    for blocker, blocked in graph.live:
        graph.direct.setdefault(blocker, set()).add(blocked)

    # Transitive closure over live edges, bounded by node count so a cycle in
    # a hostile fixture terminates instead of hanging.
    graph.downstream = {node: set(kids) for node, kids in graph.direct.items()}
    for _ in range(len(items) + 1):
        changed = False
        for node in list(graph.downstream):
            grown = set(graph.downstream[node])
            for reached in list(grown):
                grown |= graph.downstream.get(reached, set())
            if grown != graph.downstream[node]:
                graph.downstream[node] = grown
                changed = True
        if not changed:
            break
    return graph


def _blocker_side(items: dict[str, dict], blocker: str) -> list[str]:
    """The ``blocks:`` list the blocker itself declared (may be empty)."""
    return [str(x) for x in ((items.get(blocker) or {}).get("blocks") or [])]


def _record(**overrides) -> dict:
    """A minimally-complete record; overrides supply the fields under test."""
    base = {
        "title": "untitled",
        "status": "backlog",
        "priority": "medium",
        "type": "feature",
        "created": "2026-01-01",
        "updated": "2026-01-01",
        "blocks": [],
        "blocked_by": [],
        "parent": None,
        "spec": None,
        "plan": None,
        "research": None,
        "lifecycle_phase": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Verbatim from the wild-light active slice. #331 holds #242 and #278
# directly and #388/#417 through them; #147 is the highest-priority ticket
# that holds nothing. #265 is deliberately absent: it is complete and
# archived, so its edge into #278 is discharged and must not count as a hold.
_DEV_SLICE: dict[str, dict] = {
    "331": _record(
        title="Dungeon space: enterable interior + load path",
        priority="low",
        created="2026-07-10",
        updated="2026-07-30",
        blocks=["278"],
    ),
    "242": _record(
        title="Multi-island streaming + late-join (Stage C, needs MP design pass)",
        priority="low",
        created="2026-06-16",
        updated="2026-07-10",
        blocked_by=["331"],
        parent="344",
    ),
    "278": _record(
        title="Dungeon / interior lighting model",
        priority="low",
        created="2026-06-21",
        updated="2026-07-10",
        blocked_by=["265", "331"],
        parent="263",
    ),
    "388": _record(
        title="Crossing vista: zoom-out and real old-island submersion",
        priority="medium",
        created="2026-07-22",
        updated="2026-08-03",
        blocked_by=["242"],
        parent="344",
    ),
    "417": _record(
        title="Crossings have no camera driver",
        priority="medium",
        created="2026-07-28",
        updated="2026-08-03",
        blocked_by=["242"],
        parent="344",
    ),
    "147": _record(
        title="Tier 1: 10 Hz position + interpolation via netfox",
        priority="high",
        created="2026-05-18",
        updated="2026-05-25",
        parent="139",
    ),
    "148": _record(title="Tier 2 replication", priority="medium", parent="139"),
    "439": _record(title="Netcode smoke harness", priority="medium", parent="139"),
    "139": _record(
        title="Epic: Multiplayer infrastructure overhaul",
        priority="high",
        type="epic",
        created="2026-05-18",
        updated="2026-05-18",
    ),
    # The corpus anchor: the most recently touched record in the slice.
    "466": _record(
        title="Overlay draws under the HUD",
        priority="low",
        type="bug",
        status="should-have",
        updated="2026-08-08",
    ),
}

_DEV_EDGES = [
    ("331", "242"),
    ("331", "278"),
    ("242", "388"),
    ("242", "417"),
    ("265", "278"),  # blocker is complete and out of slice — discharged
]

_DEV_PARENTS = {
    "139": ["147", "148", "439"],   # 3 children — clears the live-epic threshold
    "344": ["242", "388", "417"],
    "263": ["278"],                 # 1 child — base credit only
}

# The degenerate shape: cortex-command's own slice. Four records, zero epics,
# and an edge list whose every endpoint is archived, so nothing is live.
_TINY_SLICE: dict[str, dict] = {
    "478": _record(title="Overhaul the dashboard", updated="2026-08-10"),
    "156": _record(title="Shelved idea", priority="low", status="deferred",
                   updated="2026-05-26"),
    "295": _record(title="Another shelved idea", priority="low", status="deferred",
                   updated="2026-06-10"),
    "466": _record(title="A defect", priority="low", type="bug",
                   status="should-have", updated="2026-08-07"),
}

_TINY_EDGES = [("113", "102"), ("118", "124"), ("370", "373")]

# Deliberate garbage across every open vocabulary, plus the two absent-field
# cases the contract names.
_GARBAGE_SLICE: dict[str, dict] = {
    "1": _record(priority="p0", type="", status="icebox", updated=None,
                 created="2026-04-01"),
    "2": _record(priority=None, type="chore", status="new", updated="",
                 created=""),
    "3": _record(priority="HIGH", type="Bug", status="backlog",
                 updated="not-a-date"),
    "4": _record(priority="medium", status="backlog", parent="9999",
                 updated="2026-06-01", lifecycle_phase="implement", spec="s.md",
                 plan="p.md", research="r.md"),
    "5": _record(priority="critical", status="backlog", updated="2026-07-01",
                 blocked_by=["3", "4"]),
    "wl-7f2": _record(priority="low", status="backlog", updated="2026-05-01"),
    "6": _record(priority="high", type="epic", status="backlog",
                 updated="2026-07-02"),
    "7": _record(priority="high", status="backlog", updated="2026-07-02",
                 lifecycle_phase="complete"),
}

_GARBAGE_EDGES = [("3", "5"), ("4", "5")]


def _ctx(items, edges, parents=None, **kwargs) -> ScoreContext:
    return ScoreContext(
        items=items, graph=_stub_graph(items, edges), parents=parents or {}, **kwargs
    )


def dev_ctx() -> ScoreContext:
    return _ctx(_DEV_SLICE, _DEV_EDGES, _DEV_PARENTS)


# ---------------------------------------------------------------------------
# The editorial position
# ---------------------------------------------------------------------------


class KeystoneOrderingTest(unittest.TestCase):
    """Leverage dominates declared priority. This is the board's whole claim."""

    def test_keystone_low_priority_outranks_high_priority(self):
        """#331 (low) must outrank #147 (high) — the locked operator decision.

        Not a tiebreak and not a nudge: #331 wins by 9 points *while carrying
        the lowest priority weight on the table*, because it holds four items
        and #147 holds none. Inverting this is a silent regression — the page
        renders identically and points at a different ticket.
        """
        ctx = dev_ctx()
        self.assertLess(
            rank_key("331", ctx),
            rank_key("147", ctx),
            "keystone-first ordering inverted: the low-priority keystone must "
            "outrank the high-priority leaf",
        )
        self.assertGreater(score_of("331", ctx).total, score_of("147", ctx).total)

    def test_keystone_is_rank_one_over_the_whole_slice(self):
        """It is not merely above #147 — it is the pick."""
        self.assertEqual(contenders(dev_ctx())[0], "331")

    def test_keystone_wins_on_leverage_not_on_priority(self):
        """The mechanism, pinned separately from the outcome.

        If #331 ever won because its *priority* term grew, the ordering test
        would still pass while the editorial claim had quietly collapsed.
        """
        ctx = dev_ctx()
        keystone = score_of("331", ctx).by_key
        leaf = score_of("147", ctx).by_key
        self.assertLess(keystone["priority"].points, leaf["priority"].points)
        self.assertEqual(keystone["priority"].points, PRIORITY_W["low"])
        self.assertGreater(keystone["leverage"].points, leaf["leverage"].points)
        # 14 x 2 direct (#242, #278) + 7 x 2 downstream (#388, #417).
        self.assertEqual(keystone["leverage"].points, 42)
        self.assertEqual(leaf["leverage"].points, 0)


# ---------------------------------------------------------------------------
# No wall-clock
# ---------------------------------------------------------------------------


class _AbsurdDate(date):
    """A ``date`` whose ``today()`` is nowhere near the fixture's dates."""

    @classmethod
    def today(cls):
        return cls(2317, 12, 31)


def _full_dump(ctx: ScoreContext) -> dict:
    """Every id's total and every term, for equality comparison."""
    return {
        tid: (
            score_of(tid, ctx).total,
            [(t.key, t.points, t.raw, t.note) for t in score_of(tid, ctx).terms],
        )
        for tid in sorted(ctx.items)
    }


class WallClockIndependenceTest(unittest.TestCase):
    """The stale term measures against the corpus, never against today."""

    def test_scores_are_identical_under_an_absurd_today(self):
        """Monkeypatch ``date.today`` three centuries out; nothing may move.

        The comparison is term-by-term rather than total-only: a wall-clock
        leak that happened to cancel out in the sum would still change the
        printed raw string, and the raw string is what the operator checks.
        """
        import cortex_command.dashboard.backlog.score as score_mod

        before = _full_dump(_ctx(_DEV_SLICE, _DEV_EDGES, _DEV_PARENTS))

        original = score_mod.date
        score_mod.date = _AbsurdDate
        try:
            self.assertEqual(score_mod.date.today().year, 2317)
            after = _full_dump(_ctx(_DEV_SLICE, _DEV_EDGES, _DEV_PARENTS))
        finally:
            score_mod.date = original

        self.assertEqual(before, after)

    def test_anchor_is_the_corpus_maximum_updated(self):
        ctx = dev_ctx()
        self.assertEqual(ctx.as_of, "2026-08-08")
        self.assertEqual(corpus_as_of(_DEV_SLICE), "2026-08-08")
        # The raw string names the anchor so the reader can check the sum.
        raw = score_of("331", ctx).by_key["stale"].raw
        self.assertIn("2026-08-08", raw)
        self.assertIn("2026-07-30", raw)

    def test_moving_the_corpus_forward_is_what_moves_the_term(self):
        """The term is not frozen — it tracks the data, and only the data."""
        base = score_of("147", dev_ctx()).by_key["stale"].points
        later = dict(_DEV_SLICE)
        later["466"] = {**_DEV_SLICE["466"], "updated": "2026-12-31"}
        moved = score_of("147", _ctx(later, _DEV_EDGES, _DEV_PARENTS))
        self.assertEqual(base, 6)  # already capped on the real corpus
        self.assertEqual(moved.by_key["stale"].points, 6)
        self.assertIn("2026-12-31", moved.by_key["stale"].raw)

    def test_one_unparseable_date_cannot_poison_the_anchor(self):
        """These are ISO strings compared as strings.

        ``updated: soon`` sorts above every real date, so an anchor picked
        without a parse filter becomes unparseable and zeroes the ``stale``
        term for every ticket on the board — one typo, whole column dead.
        Found by the open-vocab fixture, not by review.
        """
        poisoned = {
            "1": _record(updated="soon"),
            "2": _record(updated="2026-08-08"),
            "3": _record(updated="2026-01-01"),
        }
        ctx = _ctx(poisoned, [])
        self.assertEqual(ctx.as_of, "2026-08-08")
        self.assertEqual(score_of("3", ctx).by_key["stale"].points, 6)

    def test_corpus_with_no_dates_scores_zero_rather_than_raising(self):
        undated = {"1": _record(updated=None, created=None)}
        ctx = _ctx(undated, [])
        self.assertEqual(ctx.as_of, "")
        self.assertEqual(score_of("1", ctx).by_key["stale"].points, 0)


# ---------------------------------------------------------------------------
# Totality over open vocabularies
# ---------------------------------------------------------------------------


class OpenVocabularyTest(unittest.TestCase):
    """Unknown values score and print verbatim; nothing raises."""

    def test_every_garbage_record_scores(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        for tid in _GARBAGE_SLICE:
            with self.subTest(tid=tid):
                result = score_of(tid, ctx)
                self.assertIsInstance(result, Score)
                self.assertIsInstance(result.total, int)
                self.assertEqual(len(result.terms), len(TERM_META))

    def test_scoring_is_deterministic_across_fresh_contexts(self):
        """Two independently-built contexts over the same data agree exactly."""
        first = _full_dump(_ctx(_GARBAGE_SLICE, _GARBAGE_EDGES))
        second = _full_dump(_ctx(_GARBAGE_SLICE, _GARBAGE_EDGES))
        self.assertEqual(first, second)

    def test_unknown_priority_scores_the_default_and_says_so(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        term = score_of("1", ctx).by_key["priority"]
        self.assertEqual(term.points, UNKNOWN_PRIORITY)
        self.assertIn("p0", term.raw)
        self.assertIsNotNone(term.note)

    def test_absent_priority_scores_the_default_with_its_own_note(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        term = score_of("2", ctx).by_key["priority"]
        self.assertEqual(term.points, UNKNOWN_PRIORITY)
        self.assertIsNotNone(term.note)

    def test_vocabulary_matching_is_case_folded(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        terms = score_of("3", ctx).by_key
        self.assertEqual(terms["priority"].points, PRIORITY_W["high"])
        self.assertEqual(terms["defect"].points, 6)

    def test_unparseable_date_scores_zero_and_prints_the_raw_value(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        term = score_of("3", ctx).by_key["stale"]
        self.assertEqual(term.points, 0)
        self.assertIn("not-a-date", term.raw)

    def test_missing_updated_falls_back_to_created(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        term = score_of("1", ctx).by_key["stale"]
        self.assertIn("2026-04-01", term.raw)
        self.assertIsNotNone(term.note)

    def test_parent_outside_the_board_still_earns_base_credit(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        self.assertEqual(score_of("4", ctx).by_key["epic"].points, 3)

    def test_non_numeric_id_neither_raises_nor_breaks_the_sort(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        score_of("wl-7f2", ctx)
        ranked = contenders(ctx)
        self.assertIn("wl-7f2", ranked)
        self.assertEqual(ranked, sorted(ranked, key=lambda t: rank_key(t, ctx)))

    def test_unknown_id_scores_against_an_empty_record(self):
        """A row the board cannot explain still gets a row, not an exception."""
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        result = score_of("does-not-exist", ctx)
        self.assertEqual(len(result.terms), len(TERM_META))
        self.assertEqual(result.by_key["priority"].points, UNKNOWN_PRIORITY)


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


class LedgerShapeTest(unittest.TestCase):
    """Six rows, fixed order, every one printing its own raw input."""

    def test_all_six_terms_emit_in_term_meta_order(self):
        ctx = dev_ctx()
        for tid in _DEV_SLICE:
            with self.subTest(tid=tid):
                keys = [t.key for t in score_of(tid, ctx).terms]
                self.assertEqual(keys, [key for key, _, _ in TERM_META])

    def test_zero_scoring_terms_still_print_a_raw_input(self):
        """A dimmed row still has to say what it looked at."""
        ctx = dev_ctx()
        for tid in _DEV_SLICE:
            for term in score_of(tid, ctx).terms:
                with self.subTest(tid=tid, term=term.key):
                    self.assertTrue(term.raw.strip())
                    self.assertTrue(term.label.strip())

    def test_total_is_the_sum_of_its_printed_terms(self):
        """The ledger has to add up, or it is not a ledger."""
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        for tid in _GARBAGE_SLICE:
            with self.subTest(tid=tid):
                result = score_of(tid, ctx)
                self.assertEqual(result.total, sum(t.points for t in result.terms))

    def test_leverage_raw_names_every_held_id_and_which_side_declared_it(self):
        """The provenance is the point: #242 declared the edge, #331 did not.

        #331's own ``blocks:`` names #278 only. Without the per-edge
        provenance a reader checking #331's frontmatter for #242 would find
        nothing and conclude the ranking invented the hold.
        """
        raw = score_of("331", dev_ctx()).by_key["leverage"].raw
        for held in ("#242", "#278", "#388", "#417"):
            self.assertIn(held, raw)
        # #242 declared the edge alone; #278 is declared on both sides.
        self.assertIn("#242's blocked_by:", raw)
        self.assertIn("both sides", raw)

    def test_leverage_raw_credits_a_hold_only_the_blocker_declared(self):
        """The other provenance case: the held ticket's frontmatter is silent."""
        one_sided = {
            "10": _record(blocks=["11"], updated="2026-01-01"),
            "11": _record(updated="2026-01-01"),
        }
        ctx = _ctx(one_sided, [("10", "11")])
        raw = score_of("10", ctx).by_key["leverage"].raw
        self.assertIn("#11", raw)
        self.assertIn("this ticket's blocks:", raw)

    def test_inflight_raw_lists_the_artefacts_it_counted(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        term = score_of("4", ctx).by_key["inflight"]
        self.assertEqual(term.points, 20 + 10 + 5 + 3)
        for token in ("implement", "spec.md", "plan.md", "research.md"):
            self.assertIn(token, term.raw)

    def test_terminal_phase_earns_no_inflight_credit(self):
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        self.assertEqual(score_of("7", ctx).by_key["inflight"].points, 0)

    def test_epic_term_thresholds_on_active_child_count(self):
        ctx = dev_ctx()
        # #139 has three active children; #263 has one.
        self.assertEqual(score_of("147", ctx).by_key["epic"].points, 6)
        self.assertEqual(score_of("278", ctx).by_key["epic"].points, 3)
        self.assertEqual(score_of("331", ctx).by_key["epic"].points, 0)

    def test_stale_caps_at_six_weeks(self):
        ctx = dev_ctx()
        term = score_of("147", ctx).by_key["stale"]
        self.assertEqual(term.points, 6)
        self.assertIsNotNone(term.note)


# ---------------------------------------------------------------------------
# Contenders and ranking
# ---------------------------------------------------------------------------


class ContenderPartitionTest(unittest.TestCase):
    def test_epic_containers_are_removed_before_ranking(self):
        ctx = dev_ctx()
        self.assertFalse(is_contender("139", ctx))
        self.assertNotIn("139", contenders(ctx))

    def test_live_blocked_items_are_not_contenders(self):
        ctx = dev_ctx()
        for held in ("242", "278", "388", "417"):
            with self.subTest(tid=held):
                self.assertFalse(is_contender(held, ctx))

    def test_discharged_blocker_does_not_hold_a_ticket(self):
        """#278's #265 edge is complete; only the live #331 edge holds it.

        Drop #331 and #278 must become a contender — a ticket whose only
        remaining blocker is already finished is one of the easiest picks on
        the board, and drawing it as blocked is the error the surface exists
        to prevent.
        """
        without_keystone = {k: v for k, v in _DEV_SLICE.items() if k != "331"}
        ctx = _ctx(without_keystone, _DEV_EDGES, _DEV_PARENTS)
        self.assertTrue(is_contender("278", ctx))

    def test_deferred_and_new_are_not_contenders(self):
        ctx = _ctx(_TINY_SLICE, _TINY_EDGES)
        self.assertFalse(is_contender("156", ctx))
        self.assertFalse(is_contender("295", ctx))
        self.assertFalse(is_contender("2", _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)))

    def test_unrecognised_status_still_reaches_the_board(self):
        """``should-have`` and ``icebox`` are not in any enum, and must rank."""
        self.assertTrue(is_contender("466", _ctx(_TINY_SLICE, _TINY_EDGES)))
        self.assertTrue(is_contender("1", _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)))

    def test_explicit_contender_override_is_honoured(self):
        ctx = _ctx(_DEV_SLICE, _DEV_EDGES, _DEV_PARENTS,
                   contender_ids=frozenset({"147", "148"}))
        self.assertEqual(contenders(ctx), ["147", "148"])

    def test_ties_break_on_numeric_id_ascending(self):
        tied = {
            "20": _record(priority="medium", updated="2026-01-01"),
            "3": _record(priority="medium", updated="2026-01-01"),
            "100": _record(priority="medium", updated="2026-01-01"),
        }
        ctx = _ctx(tied, [])
        totals = {score_of(t, ctx).total for t in tied}
        self.assertEqual(len(totals), 1, "fixture must actually tie")
        # Numeric, not lexicographic: "100" sorting before "20" would be the
        # string order and would reorder the board on every id past 99.
        self.assertEqual(contenders(ctx), ["3", "20", "100"])


# ---------------------------------------------------------------------------
# The counterfactual
# ---------------------------------------------------------------------------


class CounterfactualTest(unittest.TestCase):
    def test_pick_is_absent_from_the_resulting_board(self):
        ctx = dev_ctx()
        result = counterfactual("331", ctx)
        self.assertNotIn("331", [tid for tid, _ in result.new_top3])
        self.assertNotIn("331", result.freed)
        self.assertNotIn("331", result.still_held)

    def test_every_freed_id_had_the_pick_as_its_sole_live_blocker(self):
        ctx = dev_ctx()
        result = counterfactual("331", ctx)
        self.assertTrue(result.freed)
        for tid in result.freed:
            with self.subTest(tid=tid):
                self.assertEqual(ctx.live_blockers_of(tid), {"331"})

    def test_freed_includes_a_ticket_whose_other_blocker_is_discharged(self):
        """#278 names two blockers; one is complete, so the pick frees it."""
        result = counterfactual("331", dev_ctx())
        self.assertEqual(sorted(result.freed), ["242", "278"])
        self.assertEqual(result.still_held, [])

    def test_still_held_names_what_the_pick_does_not_free(self):
        """A ticket with two live blockers is not freed by closing one.

        Reporting it as freed would be the most misleading thing this surface
        could say — it is the one claim the operator will act on immediately.
        """
        ctx = _ctx(_GARBAGE_SLICE, _GARBAGE_EDGES)
        result = counterfactual("3", ctx)
        self.assertEqual(result.freed, [])
        self.assertEqual(result.still_held, ["5"])
        self.assertEqual(ctx.live_blockers_of("5"), {"3", "4"})

    def test_freed_items_enter_the_reranked_board(self):
        """The freed set is added to the population, not merely reported."""
        ctx = dev_ctx()
        result = counterfactual("331", ctx)
        top_ids = [tid for tid, _ in result.new_top3]
        self.assertTrue(set(result.freed) & set(top_ids))

    def test_new_top3_carries_the_scores_it_ranked_on(self):
        ctx = dev_ctx()
        for tid, total in counterfactual("331", ctx).new_top3:
            with self.subTest(tid=tid):
                self.assertEqual(total, score_of(tid, ctx).total)

    def test_new_top3_is_at_most_three_and_ordered(self):
        ctx = dev_ctx()
        top = counterfactual("331", ctx).new_top3
        self.assertLessEqual(len(top), 3)
        self.assertEqual([t for _, t in top], sorted([t for _, t in top], reverse=True))

    def test_counterfactual_on_a_pick_that_frees_nothing(self):
        ctx = _ctx(_TINY_SLICE, _TINY_EDGES)
        result = counterfactual("478", ctx)
        self.assertEqual(result.freed, [])
        self.assertEqual(result.still_held, [])
        self.assertNotIn("478", [tid for tid, _ in result.new_top3])

    def test_counterfactual_on_an_unknown_pick_does_not_raise(self):
        result = counterfactual("does-not-exist", dev_ctx())
        self.assertEqual(result.freed, [])
        self.assertEqual(len(result.new_top3), 3)


# ---------------------------------------------------------------------------
# Degenerate corpora
# ---------------------------------------------------------------------------


class DegenerateCorpusTest(unittest.TestCase):
    """cortex-command's own slice: 4 items, 0 epics, 0 live edges."""

    def test_tiny_slice_scores_and_ranks(self):
        ctx = _ctx(_TINY_SLICE, _TINY_EDGES)
        ranked = contenders(ctx)
        self.assertEqual(ranked, ["478", "466"])
        for tid in _TINY_SLICE:
            self.assertEqual(len(score_of(tid, ctx).terms), len(TERM_META))

    def test_edges_whose_endpoints_are_off_the_board_grant_no_leverage(self):
        """Every edge in this slice points at an archived ticket."""
        ctx = _ctx(_TINY_SLICE, _TINY_EDGES)
        for tid in _TINY_SLICE:
            with self.subTest(tid=tid):
                self.assertEqual(score_of(tid, ctx).by_key["leverage"].points, 0)

    def test_empty_slice_yields_an_empty_board_without_raising(self):
        ctx = _ctx({}, [])
        self.assertEqual(contenders(ctx), [])
        self.assertEqual(ctx.as_of, "")

    def test_int_keyed_items_are_normalised_rather_than_missed(self):
        """A caller handing int keys must not silently score every row as unknown."""
        ctx = ScoreContext(
            items={331: _record(priority="low", updated="2026-07-30")},
            graph=_stub_graph({}, []),
            parents={139: ["147"]},
        )
        self.assertEqual(score_of("331", ctx).by_key["priority"].points,
                         PRIORITY_W["low"])
        self.assertIn("139", ctx.parents)


# ---------------------------------------------------------------------------
# Integration with the real graph builder, when it is available
# ---------------------------------------------------------------------------


class RealGraphTotalityTest(unittest.TestCase):
    """Score against ``graph.build_graph`` output when that module is on disk.

    Asserts totality and determinism only, never specific totals: the numbers
    are pinned above against a stand-in whose classification rules are written
    out in this file, and duplicating them here would just assert that two
    implementations of the same rule agree.
    """

    def test_scores_every_record_of_a_real_graph(self):
        try:
            from cortex_command.dashboard.backlog.graph import build_graph
        except ImportError:  # pragma: no cover - graph.py lands separately
            self.skipTest("graph.py not present yet")

        corpus = [{"id": tid, **rec} for tid, rec in _DEV_SLICE.items()]
        graph = build_graph(_DEV_SLICE, corpus)
        ctx = ScoreContext(items=_DEV_SLICE, graph=graph, parents=_DEV_PARENTS)

        for tid in _DEV_SLICE:
            with self.subTest(tid=tid):
                result = score_of(tid, ctx)
                self.assertEqual(len(result.terms), len(TERM_META))
                self.assertEqual(result.total, sum(t.points for t in result.terms))

        self.assertEqual(contenders(ctx), contenders(
            ScoreContext(items=_DEV_SLICE, graph=graph, parents=_DEV_PARENTS)
        ))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
