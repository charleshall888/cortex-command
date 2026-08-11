"""Unit tests for cortex_command/dashboard/backlog/bands.py.

The completeness property is what this file exists to hold down. Everything
else the band partition does is a presentation choice that can be argued
about; "no record may ever fall off the page" is the one claim a read-only
board cannot be allowed to get wrong, because a dropped ticket looks exactly
like a ticket that has nothing to say. So the coverage assertion runs on
three deliberately different slices and is checked two ways each time —
``sum(counts) == len(slice)`` catches an arithmetic error, and
``union(row ids) == slice ids`` catches a record that was counted in one band
and rendered in another.

The three slices:

``_wild_light_slice``
    The real 73-item active slice from the dev corpus, as a compact table:
    real ids, statuses, priorities, types, parents, lifecycle artefacts,
    ``updated`` dates and dependency edges. Titles are synthetic — the tests
    assert that a blocker's title reaches the row, never what it says.
    This is the slice every band except UNKNOWN PRIORITY is exercised by, and
    its per-band counts are pinned as a regression.

``_degenerate_slice``
    cortex-command's own 4-item / 0-epic / 0-edge slice. The point of the
    fixture is that the partition on it is a *correct* page, not a broken
    one — and it already carries an out-of-vocabulary status (``should-have``)
    that the corpus it was drawn from produced without anybody trying.

``_hostile_slice``
    Open-vocabulary garbage, hand-built to attack the rules that the two real
    corpora happen not to reach: ``status: icebox``, ``priority: p0``,
    ``type: ""``, absent ``updated``, an id present in the slice but missing
    from ``item_order``, a blocker naming no known ticket, a self-block, and
    a record whose id is not numeric at all.

Tests cover:
  - full coverage and disjointness on all three slices
  - the rule table's last rule being literally unconditional
  - bands rendering in reading order and ending on the catch-all's band
  - the four non-colour channels being populated on every band
  - bands D and E hiding rank and ordering by score-then-id
  - epic containers routed out of the startable bands
  - blocked rows naming the blocker's id *and* title
  - a lapsed hold banded separately from a live one
  - unknown priority banded rather than folded into LOW
  - unknown *status* staying startable rather than being swept off-board
  - off-board only being tested when an ordering was supplied
  - zero-count bands surviving to the reconciliation
  - determinism across repeated partitions of the same fixture
"""

from __future__ import annotations

import unittest

from cortex_command.dashboard.backlog import bands as bands_mod
from cortex_command.dashboard.backlog.bands import (
    STARTABLE_KEYS,
    Bands,
    partition,
)
from cortex_command.dashboard.backlog.graph import build_graph
from cortex_command.dashboard.backlog.score import ScoreContext

BORDER_STYLES = {"solid", "dashed", "dotted", "ghost"}


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------


def _record(
    tid,
    status="backlog",
    priority="medium",
    type_="feature",
    parent="",
    artefacts="",
    phase="",
    updated="2026-08-01",
    created="",
    blocked_by=(),
    blocks=(),
    title=None,
):
    """One backlog record in the shape the snapshot's ``items`` map carries.

    ``artefacts`` is a compact spelling of the three lifecycle files —
    ``"spr"`` for spec + plan + research — because writing three keyword
    arguments seventy-three times would bury the two rows that actually have
    any.
    """
    return {
        "id": int(tid) if str(tid).isdigit() else tid,
        "title": title if title is not None else "wild-light ticket %s" % tid,
        "status": status,
        "priority": priority,
        "type": type_,
        "parent": parent or None,
        "spec": "spec.md" if "s" in artefacts else None,
        "plan": "plan.md" if "p" in artefacts else None,
        "research": "research.md" if "r" in artefacts else None,
        "lifecycle_phase": phase or None,
        "created": created or updated,
        "updated": updated,
        "blocked_by": list(blocked_by),
        "blocks": list(blocks),
        "tags": [],
    }


def _context(items, extra_corpus=(), parents=None):
    """Build the ``(ScoreContext, item_order)`` pair a partition runs against.

    ``extra_corpus`` carries the off-slice records a blocker ref has to
    resolve against — a discharged edge is only discoverable if the graph can
    see that the blocker reached a terminal status, and those tickets are by
    definition not in the active slice.

    ``parents`` is derived from the records' own ``parent`` field when not
    supplied, which is what makes an epic container's child count real rather
    than fixture-authored.
    """
    if parents is None:
        parents = {}
        for tid, record in items.items():
            parent = record.get("parent")
            if parent:
                parents.setdefault(str(parent), []).append(str(tid))

    corpus = list(items.values()) + list(extra_corpus)
    graph = build_graph(items, corpus)
    return ScoreContext(items=items, graph=graph, parents=parents)


# The dev corpus's active slice, as (id, status, priority, type, parent,
# artefacts, phase, updated, blocked_by, blocks). Real values throughout
# except the titles.
_WILD_LIGHT_ROWS = (
    ("103", "abandoned", "high", "epic", "", "", "wontfix", "2026-07-27", (), ()),
    ("138", "deferred", "low", "chore", "126", "", "", "2026-07-20", (), ()),
    ("139", "backlog", "high", "epic", "", "", "", "2026-05-18", (), ()),
    ("147", "backlog", "high", "feature", "139", "", "", "2026-05-25", (), ()),
    ("148", "backlog", "medium", "feature", "139", "", "", "2026-05-26", (), ()),
    ("226", "backlog", "low", "feature", "", "", "", "2026-06-18", (), ()),
    ("236", "backlog", "low", "epic", "", "", "", "2026-07-27", (), ()),
    ("242", "backlog", "low", "feature", "344", "", "", "2026-07-10", ("331",), ()),
    ("247", "deferred", "low", "feature", "236", "", "", "2026-08-05", (), ()),
    ("257", "deferred", "low", "feature", "236", "", "", "2026-07-27", (), ()),
    ("263", "backlog", "medium", "epic", "", "", "", "2026-07-06", (), ()),
    ("276", "backlog", "low", "feature", "263", "", "", "2026-07-13", ("265",), ()),
    ("278", "backlog", "low", "feature", "263", "", "", "2026-07-10", ("265", "331"), ()),
    ("281", "backlog", "low", "chore", "", "s", "", "2026-08-04", (), ()),
    ("284", "backlog", "low", "epic", "", "", "", "2026-07-27", (), ()),
    ("286", "deferred", "medium", "feature", "284", "", "", "2026-07-27", (), ()),
    ("287", "deferred", "low", "spike", "284", "s", "plan", "2026-07-27", (), ()),
    ("290", "backlog", "low", "feature", "", "", "", "2026-06-22", (), ()),
    ("328", "backlog", "medium", "chore", "", "", "", "2026-07-10", (), ()),
    ("329", "deferred", "low", "chore", "", "", "", "2026-07-13", (), ()),
    ("330", "deferred", "low", "chore", "", "", "", "2026-07-13", (), ()),
    ("331", "backlog", "low", "feature", "", "", "", "2026-07-30", (), ("278",)),
    ("334", "backlog", "medium", "bug", "", "", "", "2026-07-10", (), ()),
    ("344", "backlog", "high", "epic", "", "", "", "2026-07-14", (), ()),
    ("364", "backlog", "medium", "feature", "344", "", "", "2026-07-27", (), ()),
    ("381", "backlog", "low", "feature", "344", "", "", "2026-08-07", (), ()),
    ("384", "backlog", "medium", "feature", "263", "", "", "2026-07-22", (), ()),
    ("388", "backlog", "medium", "feature", "344", "", "", "2026-08-03", ("242",), ()),
    ("395", "backlog", "medium", "feature", "344", "", "", "2026-07-27", (), ()),
    ("407", "backlog", "high", "chore", "", "", "", "2026-08-05", (), ()),
    ("417", "backlog", "medium", "feature", "344", "", "", "2026-08-03", ("242",), ()),
    ("419", "deferred", "low", "chore", "344", "", "", "2026-08-07", (), ()),
    ("424", "backlog", "medium", "bug", "", "", "", "2026-07-29", (), ()),
    ("425", "backlog", "low", "chore", "103", "", "", "2026-07-29", (), ()),
    ("430", "backlog", "low", "chore", "344", "", "", "2026-08-05", ("424",), ()),
    ("433", "backlog", "medium", "chore", "333", "", "", "2026-07-30", (), ()),
    ("434", "backlog", "medium", "chore", "333", "", "", "2026-07-30", (), ()),
    ("439", "backlog", "medium", "chore", "139", "", "", "2026-08-03", ("432",), ()),
    ("447", "backlog", "medium", "chore", "432", "", "", "2026-08-03", (), ()),
    ("466", "backlog", "medium", "chore", "", "", "", "2026-08-04", (), ()),
    ("471", "backlog", "medium", "chore", "446", "", "", "2026-08-04", (), ()),
    ("475", "backlog", "medium", "feature", "", "", "", "2026-08-05", (), ()),
    ("478", "backlog", "low", "feature", "344", "", "", "2026-08-05", (), ()),
    ("483", "backlog", "medium", "bug", "455", "", "", "2026-08-06", (), ()),
    ("484", "backlog", "medium", "chore", "455", "", "", "2026-08-06", (), ()),
    ("485", "backlog", "low", "bug", "455", "", "", "2026-08-06", (), ()),
    ("486", "backlog", "medium", "bug", "455", "", "", "2026-08-06", (), ()),
    # `updated` is empty on this one in the real corpus; the score model falls
    # back to `created`, so the fixture keeps the gap rather than filling it.
    ("487", "backlog", "medium", "bug", "455", "", "", "", (), ()),
    ("488", "backlog", "medium", "bug", "", "", "", "2026-08-06", (), ()),
    ("489", "backlog", "medium", "chore", "", "", "", "2026-08-06", (), ()),
    ("490", "backlog", "medium", "chore", "", "", "", "2026-08-06", (), ()),
    ("491", "backlog", "low", "chore", "", "", "", "2026-08-06", (), ()),
    ("492", "backlog", "medium", "bug", "", "", "", "2026-08-06", (), ()),
    ("493", "backlog", "medium", "bug", "", "", "", "2026-08-07", (), ()),
    ("494", "backlog", "low", "bug", "", "", "", "2026-08-07", (), ()),
    ("495", "backlog", "medium", "chore", "", "", "", "2026-08-07", (), ()),
    ("496", "backlog", "medium", "bug", "", "", "", "2026-08-07", (), ()),
    ("497", "backlog", "low", "chore", "", "", "", "2026-08-07", (), ()),
    ("498", "backlog", "medium", "bug", "", "", "", "2026-08-07", (), ()),
    ("499", "backlog", "low", "bug", "", "", "", "2026-08-07", (), ()),
    ("500", "backlog", "low", "chore", "", "", "", "2026-08-07", (), ()),
    ("501", "backlog", "low", "feature", "", "", "", "2026-08-07", (), ()),
    ("502", "backlog", "medium", "bug", "", "", "", "2026-08-07", (), ()),
    ("503", "backlog", "medium", "spike", "", "", "", "2026-08-08", (), ()),
    ("507", "backlog", "low", "bug", "", "", "", "2026-08-07", (), ()),
    ("508", "backlog", "low", "bug", "", "", "", "2026-08-07", (), ()),
    ("509", "backlog", "low", "chore", "", "", "", "2026-08-07", (), ()),
    ("510", "backlog", "medium", "chore", "", "", "", "2026-08-07", (), ()),
    ("511", "backlog", "low", "chore", "", "", "", "2026-08-07", (), ()),
    ("512", "backlog", "medium", "feature", "", "", "", "2026-08-07", (), ()),
    ("513", "new", "medium", "bug", "", "", "", "2026-08-07", (), ()),
    ("514", "new", "medium", "feature", "", "", "", "2026-08-07", (), ()),
    ("515", "new", "medium", "bug", "", "", "", "2026-08-07", (), ()),
)

# The two blockers that live outside the active slice. Both already complete,
# which is the whole reason band G′ exists: #276 and #439 are startable today
# and the old board still drew them as blocked.
_WILD_LIGHT_OFF_SLICE = (
    _record("265", status="complete", title="palette pipeline landed"),
    _record("432", status="complete", title="migration coordinator landed"),
)


def _wild_light_slice():
    items = {}
    for tid, status, priority, type_, parent, art, phase, upd, bby, blk in (
        _WILD_LIGHT_ROWS
    ):
        items[tid] = _record(
            tid,
            status=status,
            priority=priority,
            type_=type_,
            parent=parent,
            artefacts=art,
            phase=phase,
            updated=upd,
            created=upd or "2026-08-06",
            blocked_by=bby,
            blocks=blk,
        )
    ctx = _context(items, extra_corpus=_WILD_LIGHT_OFF_SLICE)
    return items, ctx, list(items)


def _degenerate_slice():
    """cortex-command's own slice: 4 items, 0 epics, 0 edges.

    ``should-have`` is a real status from that corpus and is outside every
    vocabulary the navigator knows. It must not disqualify the ticket.
    """
    items = {
        "478": _record("478", priority="medium", type_="feature", updated="2026-08-10"),
        "156": _record(
            "156", status="deferred", priority="low", type_="feature",
            updated="2026-05-26",
        ),
        "295": _record(
            "295", status="deferred", priority="low", type_="feature",
            updated="2026-06-10",
        ),
        "466": _record(
            "466", status="should-have", priority="low", type_="bug",
            updated="2026-08-07",
        ),
    }
    ctx = _context(items)
    return items, ctx, ["478", "156", "295", "466"]


def _hostile_slice():
    """Open-vocabulary garbage aimed at the rules the real corpora miss."""
    items = {
        # Unknown status, unknown priority, empty type, no `updated` at all.
        "900": {
            "id": 900,
            "title": "icebox item with a priority nobody defined",
            "status": "icebox",
            "priority": "p0",
            "type": "",
            "blocked_by": [],
            "blocks": [],
        },
        # Unknown status but a known priority: must stay startable and band
        # on the priority, not get swept off the board for the status.
        "901": _record("901", status="should-have", priority="high", updated="2026-08-02"),
        # Present in the slice, absent from item_order.
        "902": _record("902", priority="low", updated="2026-08-02"),
        # Blocked by a ref that names no known ticket anywhere.
        "903": _record("903", blocked_by=("nope-9999",), updated="2026-08-02"),
        # Blocked by a ticket that is already complete: a lapsed hold.
        "904": _record("904", blocked_by=("910",), updated="2026-08-02"),
        # Self-block. The graph reports the cycle; the band must still place it.
        "905": _record("905", blocked_by=("905",), updated="2026-08-02"),
        # A container with no children at all.
        "906": _record("906", type_="epic", priority="critical", updated="2026-08-02"),
        # Terminal status still sitting in the slice.
        "907": _record("907", status="wontfix", priority="high", updated="2026-08-02"),
        # No priority key whatsoever.
        "908": {
            "id": 908,
            "title": "no priority key at all",
            "status": "backlog",
            "blocked_by": [],
            "blocks": [],
        },
        # A non-numeric id, which the write path does not forbid.
        "spike-a": _record(
            "spike-a", priority="critical", type_="spike", updated="2026-08-02",
        ),
    }
    off_slice = (_record("910", status="complete", title="already landed"),)
    ctx = _context(items, extra_corpus=off_slice)
    # #902 is deliberately missing from the ordering.
    order = [tid for tid in items if tid != "902"]
    return items, ctx, order


# ---------------------------------------------------------------------------
# The completeness property
# ---------------------------------------------------------------------------


class CoverageTests(unittest.TestCase):
    """``sum(counts) == len(slice)`` and ``union(row ids) == slice ids``.

    Both directions, on all three slices. Either one alone can pass while the
    partition is broken: a count can be right while the rows are wrong, and
    the rows can cover the slice while a band reports a stale count.
    """

    def _assert_covers(self, result: Bands, slice_ids):
        expected = set(slice_ids)

        self.assertEqual(
            result.total,
            len(expected),
            "band counts do not sum to the slice size",
        )
        self.assertEqual(
            sum(band.count for band in result),
            len(expected),
            "the reported total disagrees with the bands it was derived from",
        )
        self.assertEqual(result.covered_ids, expected)

        rendered = [row.id for band in result for row in band.rows]
        self.assertEqual(set(rendered), expected)
        self.assertEqual(
            len(rendered), len(expected), "a record was rendered in two bands"
        )

        for band in result:
            self.assertEqual(
                band.count, len(band.rows), "band %s miscounts its rows" % band.key
            )

    def test_wild_light_slice_is_fully_covered(self):
        items, ctx, order = _wild_light_slice()
        self._assert_covers(partition(items, ctx, item_order=order), items)

    def test_degenerate_slice_is_fully_covered(self):
        items, ctx, order = _degenerate_slice()
        self._assert_covers(partition(items, ctx, item_order=order), items)

    def test_hostile_open_vocabulary_slice_is_fully_covered(self):
        items, ctx, order = _hostile_slice()
        self._assert_covers(partition(items, ctx, item_order=order), items)

    def test_coverage_holds_when_records_arrive_as_a_list_of_ids(self):
        """The three accepted input shapes must agree on the partition."""
        items, ctx, order = _wild_light_slice()
        as_mapping = partition(items, ctx, item_order=order)
        as_ids = partition(list(items), ctx, item_order=order)
        as_records = partition(list(items.values()), ctx, item_order=order)
        self.assertEqual(as_mapping, as_ids)
        self.assertEqual(as_mapping, as_records)

    def test_duplicate_ids_collapse_rather_than_double_counting(self):
        """A duplicated input id must not inflate the reconciliation total.

        A record cannot be in two bands, so a duplicate would make the total
        disagree with ``len(records)`` for a reason that has nothing to do
        with a dropped ticket — which is the one failure the total exists to
        detect.
        """
        items, ctx, order = _degenerate_slice()
        doubled = list(items) + list(items)
        result = partition(doubled, ctx, item_order=order)
        self.assertEqual(result.total, len(items))
        self.assertEqual(result.covered_ids, set(items))

    def test_empty_slice_returns_every_band_at_zero(self):
        items, ctx, order = _degenerate_slice()
        result = partition([], ctx, item_order=order)
        self.assertEqual(result.total, 0)
        self.assertEqual(result.covered_ids, frozenset())
        self.assertTrue(len(result) > 0, "bands must survive an empty slice")
        self.assertTrue(all(band.count == 0 for band in result))

    def test_zero_count_bands_are_returned_not_dropped(self):
        """Filtering empty bands is the caller's job, not this module's.

        If ``partition`` pruned them, the reconciliation total would be a sum
        over a set that had already been edited — arithmetic that cannot catch
        its own error.
        """
        items, ctx, order = _degenerate_slice()
        result = partition(items, ctx, item_order=order)
        self.assertTrue(
            any(band.count == 0 for band in result),
            "the 4-item slice should leave several bands empty",
        )
        self.assertEqual(len(result), len(bands_mod._BAND_META))


# ---------------------------------------------------------------------------
# The structural guarantees behind the property
# ---------------------------------------------------------------------------


class RuleTableTests(unittest.TestCase):
    def test_final_rule_is_literally_unconditional(self):
        """The catch-all is the only structural reason nothing falls off.

        Asserted by identity rather than by behaviour: a predicate that grew a
        condition would still pass every coverage test on every corpus that
        happened not to exercise the gap it opened.
        """
        _key, predicate, _reason = bands_mod._RULES[-1]
        self.assertIs(predicate, bands_mod._always)
        self.assertTrue(predicate(None))

    def test_catch_all_feeds_the_last_rendered_band(self):
        """Reading order must end on the band the catch-all routes to, so
        "the last band is a catch-all" is true from either direction."""
        self.assertEqual(bands_mod._RULES[-1][0], bands_mod._BAND_META[-1][0])

    def test_every_rule_targets_a_declared_band(self):
        declared = {key for key, _l, _b, _r in bands_mod._BAND_META}
        for key, _predicate, _reason in bands_mod._RULES:
            self.assertIn(key, declared)

    def test_band_keys_are_unique(self):
        keys = [key for key, _l, _b, _r in bands_mod._BAND_META]
        self.assertEqual(len(keys), len(set(keys)))


class ChannelTests(unittest.TestCase):
    """Four channels before colour is consulted: letter, label, count, border."""

    def test_every_band_populates_all_four_channels(self):
        items, ctx, order = _wild_light_slice()
        for band in partition(items, ctx, item_order=order):
            self.assertTrue(band.key.strip())
            self.assertTrue(band.label.strip())
            self.assertIsInstance(band.count, int)
            self.assertIn(band.border_style, BORDER_STYLES)

    def test_every_band_carries_a_rationale(self):
        items, ctx, order = _wild_light_slice()
        for band in partition(items, ctx, item_order=order):
            self.assertTrue(band.rationale.strip(), band.key)

    def test_band_labels_are_distinct(self):
        items, ctx, order = _wild_light_slice()
        labels = [band.label for band in partition(items, ctx, item_order=order)]
        self.assertEqual(len(labels), len(set(labels)))

    def test_every_row_carries_a_reason_and_a_title(self):
        items, ctx, order = _wild_light_slice()
        for band in partition(items, ctx, item_order=order):
            for row in band.rows:
                self.assertTrue(row.why.strip(), row.id)
                self.assertTrue(row.title.strip(), row.id)
                self.assertIsInstance(row.points, int)


# ---------------------------------------------------------------------------
# Band membership
# ---------------------------------------------------------------------------


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.items, self.ctx, self.order = _wild_light_slice()
        self.result = partition(self.items, self.ctx, item_order=self.order)
        self.by_key = {band.key: band for band in self.result}

    def _ids(self, key):
        return {row.id for row in self.by_key[key].rows}

    def test_measured_partition_of_the_dev_slice(self):
        """Pin the per-band counts on the real slice.

        Not a taste assertion: these numbers are the ones the design was
        argued from — two keyholders, five genuinely blocked items, two lapsed
        holds, five epic containers — and a rule reorder that silently moved
        thirty records between D and E would otherwise pass every other test
        in this file.
        """
        counts = {band.key: band.count for band in self.result}
        self.assertEqual(
            counts,
            {
                "A": 2,
                "B": 1,
                "C": 2,
                "D": 28,
                "E": 16,
                "E*": 0,
                "E′": 5,
                "F": 8,
                "G": 5,
                "G′": 2,
                "H": 4,
            },
        )
        self.assertEqual(sum(counts.values()), 73)

    def test_keyholders_are_the_records_that_unlock_something(self):
        # #331 holds #242 and #278 directly and reaches #388/#417 through
        # them; #424 holds #430. Nothing else in the slice unlocks anything.
        self.assertEqual(self._ids("A"), {"331", "424"})
        for row in self.by_key["A"].rows:
            direct, onward = bands_mod._dependents(row.id, self.ctx, self.ctx.graph)
            self.assertTrue(direct or onward)

    def test_epic_containers_are_routed_out_of_the_startable_bands(self):
        containers = self._ids("E′")
        self.assertEqual(containers, {"139", "236", "263", "284", "344"})
        startable = {
            row.id
            for key in STARTABLE_KEYS
            for row in self.by_key[key].rows
        }
        self.assertFalse(containers & startable)
        # The abandoned epic is closed first — a terminal status outranks the
        # container rule, or the board would invite work on a dead grouping.
        self.assertIn("103", self._ids("H"))

    def test_blocked_rows_name_the_blockers_id_and_title(self):
        blocked = self.by_key["G"]
        self.assertEqual({row.id for row in blocked.rows},
                         {"242", "278", "388", "417", "430"})
        for row in blocked.rows:
            self.assertTrue(row.blockers, row.id)
            for blocker in row.blockers:
                self.assertTrue(blocker.ref)
                self.assertTrue(blocker.title, "%s -> %s" % (row.id, blocker.ref))
                self.assertFalse(blocker.discharged)

    def test_a_lapsed_hold_is_banded_apart_from_a_live_one(self):
        """#276 and #439 name a blocker that is already complete."""
        self.assertEqual(self._ids("G′"), {"276", "439"})
        for row in self.by_key["G′"].rows:
            self.assertTrue(row.blockers)
            self.assertTrue(all(b.discharged for b in row.blockers))
        # #278 names one complete blocker and one live one, so it is still
        # held. Reporting it as lapsed would be the same error inverted.
        self.assertIn("278", self._ids("G"))

    def test_deferral_outranks_a_dependency(self):
        deferred = self._ids("F")
        self.assertEqual(
            deferred, {"138", "247", "257", "286", "287", "329", "330", "419"}
        )
        self.assertFalse(deferred & self._ids("G"))
        # #287 carries a spec and a plan, so it would have matched band B had
        # the exclusion bands not been tested first.
        self.assertIn("287", deferred)

    def test_in_flight_beats_declared_priority(self):
        self.assertEqual(self._ids("B"), {"281"})
        self.assertEqual(self._ids("C"), {"147", "407"})

    def test_untriaged_and_closed_share_the_catch_all_band(self):
        self.assertEqual(self._ids("H"), {"103", "513", "514", "515"})


class DegenerateSliceTests(unittest.TestCase):
    """A 4-item, 0-epic, 0-edge slice is a correct page, not a broken one."""

    def setUp(self):
        self.items, self.ctx, self.order = _degenerate_slice()
        self.result = partition(self.items, self.ctx, item_order=self.order)
        self.by_key = {band.key: band for band in self.result}

    def test_only_the_bands_with_members_have_rows(self):
        populated = {band.key for band in self.result if band.count}
        self.assertEqual(populated, {"D", "E", "F"})

    def test_an_unknown_status_stays_startable(self):
        """``should-have`` is outside every vocabulary and is still work.

        Sweeping it into the off-board band would make the navigator quieter
        than the corpus, which is the failure the open-vocabulary rule exists
        to prevent.
        """
        low = {row.id for row in self.by_key["E"].rows}
        self.assertIn("466", low)

    def test_no_epic_band_members_when_the_corpus_has_no_epics(self):
        self.assertEqual(self.by_key["E′"].count, 0)
        self.assertEqual(self.by_key["A"].count, 0)


class HostileSliceTests(unittest.TestCase):
    def setUp(self):
        self.items, self.ctx, self.order = _hostile_slice()
        self.result = partition(self.items, self.ctx, item_order=self.order)
        self.by_key = {band.key: band for band in self.result}

    def _ids(self, key):
        return {row.id for row in self.by_key[key].rows}

    def test_unknown_priority_gets_its_own_band_rather_than_low(self):
        """``p0`` is not ``low``, and folding it there would be an invention.

        Both the value the author typed and the fact that this board does not
        recognise it have to survive to the page.
        """
        unknown = self._ids("E*")
        self.assertEqual(unknown, {"900", "908"})
        self.assertFalse(unknown & self._ids("E"))
        row = next(row for row in self.by_key["E*"].rows if row.id == "900")
        self.assertEqual(row.priority, "p0")

    def test_unknown_status_bands_on_priority(self):
        self.assertIn("901", self._ids("C"))

    def test_an_id_missing_from_the_ordering_lands_off_board(self):
        self.assertIn("902", self._ids("H"))

    def test_off_board_is_not_tested_without_an_ordering(self):
        """No ordering means no off-board claim can be made.

        An absent or empty ``item_order`` would otherwise sweep the whole
        slice into band H — the exact failure the completeness property is
        meant to surface, dressed up as a pass.
        """
        without = partition(self.items, self.ctx)
        by_key = {band.key: band for band in without}
        self.assertNotIn("902", {row.id for row in by_key["H"].rows})
        self.assertEqual(without.total, len(self.items))

    def test_an_unresolvable_blocker_still_holds_the_ticket(self):
        """A ref naming no known ticket is a hold nobody can discharge.

        Treating it as startable would put an unstartable ticket into the
        bands the pick is drawn from.
        """
        self.assertIn("903", self._ids("G"))

    def test_a_complete_blocker_lapses_even_in_garbage_data(self):
        self.assertIn("904", self._ids("G′"))

    def test_a_self_block_is_placed_rather_than_dropped(self):
        self.assertIn("905", self.result.covered_ids)

    def test_a_childless_container_still_bands_as_a_container(self):
        self.assertIn("906", self._ids("E′"))

    def test_a_terminal_status_in_the_slice_is_closed_in_place(self):
        self.assertIn("907", self._ids("H"))

    def test_a_non_numeric_id_survives_the_ordering(self):
        self.assertIn("spike-a", self.result.covered_ids)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


class OrderingTests(unittest.TestCase):
    def setUp(self):
        self.items, self.ctx, self.order = _wild_light_slice()
        self.result = partition(self.items, self.ctx, item_order=self.order)
        self.by_key = {band.key: band for band in self.result}

    def test_bands_d_and_e_hide_the_rank_number(self):
        """Locked decision: with 13 distinct scores over 48 rows a per-row
        rank in the bulk bands is decoration dressed as a measurement."""
        for key in ("D", "E"):
            band = self.by_key[key]
            self.assertFalse(band.show_rank)
            self.assertTrue(band.rows)
            self.assertTrue(all(row.rank is None for row in band.rows))

    def test_bands_d_and_e_order_by_score_then_id(self):
        """Locked decision: score-then-id, not ``updated``."""
        for key in ("D", "E"):
            rows = self.by_key[key].rows
            observed = [(row.id, row.points) for row in rows]
            expected = sorted(
                observed,
                key=lambda pair: (-pair[1], int(pair[0])),
            )
            self.assertEqual(observed, expected)

    def test_ranked_bands_number_from_one_without_gaps(self):
        for key in ("A", "B", "C"):
            band = self.by_key[key]
            self.assertTrue(band.show_rank)
            self.assertEqual(
                [row.rank for row in band.rows],
                list(range(1, band.count + 1)),
            )

    def test_every_band_is_ordered_by_score_then_id(self):
        """One ordering rule across the whole board, including the bands the
        ranking excluded — so the reconciliation and the rendering cannot
        disagree about which row is which."""
        for band in self.result:
            observed = [(row.id, row.points) for row in band.rows]
            expected = sorted(observed, key=lambda pair: (-pair[1], int(pair[0])))
            self.assertEqual(observed, expected, band.key)

    def test_partition_is_deterministic(self):
        again = partition(self.items, self.ctx, item_order=self.order)
        self.assertEqual(self.result, again)
        self.assertEqual(
            [(band.key, [row.id for row in band.rows]) for band in self.result],
            [(band.key, [row.id for row in band.rows]) for band in again],
        )

    def test_partition_does_not_depend_on_input_order(self):
        shuffled = list(reversed(list(self.items)))
        self.assertEqual(
            self.result,
            partition(shuffled, self.ctx, item_order=self.order),
        )


class SequenceProtocolTests(unittest.TestCase):
    """``Bands`` has to behave as the ``list[Band]`` the signature names."""

    def setUp(self):
        self.items, self.ctx, self.order = _degenerate_slice()
        self.result = partition(self.items, self.ctx, item_order=self.order)

    def test_indexing_iteration_and_length(self):
        self.assertEqual(len(self.result), len(list(self.result)))
        self.assertIs(self.result[0], self.result.bands[0])
        self.assertEqual([band.key for band in self.result],
                         [key for key, _l, _b, _r in bands_mod._BAND_META])

    def test_by_key_lookup(self):
        self.assertIsNotNone(self.result.by_key("H"))
        self.assertIsNone(self.result.by_key("not-a-band"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
