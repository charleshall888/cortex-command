"""The A–H band partition for the navigator's board (surface A).

The board's job is to render every record in the active slice on first
paint, at correct relative weight, without a click. The band grammar is how
it does that: each band carries four channels *before colour is consulted* —
a band letter, a spelled label, a live count, and a border style — plus an
italic rationale that says why those records sit together.

The property this module exists to guarantee is **completeness**. A
read-only board that silently drops a ticket is worse than no board: the
operator cannot tell "nothing to do here" from "the partition lost it". So
the partition is not a set of buckets that happen to cover the input, it is
an ordered rule table whose **last rule is unconditional**, and ``partition``
returns its own coverage (``Bands.total`` / ``Bands.covered_ids``) as data
rather than printing a reconciliation line and hoping.

Two orderings live here and they are deliberately different:

``_RULES``
    Match precedence. First match wins. The exclusion classes are tested
    *before* the startable sub-bands, because a deferred keyholder is
    deferred first and a keyholder second — the design says deferred items
    appear only in band F and blocked items only in G/G′. The final rule is
    literally unconditional (``_always``), so a status nobody has seen yet
    lands in band H instead of falling off the page.

``_BAND_META``
    Reading order on the page: A B C D E E* E′ F G G′ H. The last *rendered*
    band is H, which is also the band the unconditional rule feeds, so
    "the last band is an unconditional catch-all" reads true from either end.

Bands with ``count == 0`` are returned anyway, with empty ``rows``. Filtering
them out is the caller's decision (a 4-item slice must not render eight empty
headers) — but they have to exist here, or the reconciliation total would be
computed over a set the caller had already pruned, which is exactly the
arithmetic that cannot be trusted to check itself.

**Who decides what is startable.** This module is the authority, and it is
deliberately stricter than :func:`score.is_contender`: that predicate reads
only ``Graph.live``, while band G also holds a record whose blocker sits
outside the slice or resolves to nothing. An unresolvable hold is still a
hold, and the readiness partition the rest of the dashboard sits behind
treats external blockers as blocking. A caller assembling the page should
therefore pass the union of bands A–E* into ``ScoreContext.contender_ids``,
which exists for exactly this handshake, so the §01 pick can never name a
ticket the board draws as blocked.

Nothing in this module renders. It returns plain dataclasses; the templates
decide what a border style looks like.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable

from cortex_command.overnight.backlog import ELIGIBLE_STATUSES

from cortex_command.dashboard.backlog.score import (
    CONTAINER_TYPES,
    DEFECT_TYPES,
    PRIORITY_W,
    TERMINAL_PHASES,
    rank_key,
    score_of,
)

# Statuses that mean the work is over. Spelled out here rather than imported
# from ``score.TERMINAL_PHASES`` for the reason that module gives for keeping
# its own copy: those are *phase* values, these are *status* values, and the
# two vocabularies are free to drift. They happen to agree today.
TERMINAL_STATUSES = frozenset({"complete", "done", "wontfix", "abandoned"})

# The statuses cortex itself recognises as workable. Imported rather than
# copied — this is the *same* question the readiness partition asks, and a
# local copy that drifted would let the board rank something
# ``partition_ready`` rejects.
#
# A status outside this set is deliberately NOT excluded from the startable
# bands. Cortex ships into consumer repos that run their own vocabularies, and
# a repo whose statuses are ``must-have``/``should-have`` is describing real
# work; sweeping every unrecognised value into "untriaged" would empty that
# repo's board. What the set is used for instead is *disclosure*: a record the
# board is ranking on a status it does not understand has to say so on the
# row, rather than presenting the claim silently.
OPEN_STATUSES = frozenset(ELIGIBLE_STATUSES)

# The edge classes ``graph.blocked_by_titles`` reports. Everything that is not
# discharged still holds the ticket — including ``external`` (a blocker
# outside the slice) and ``unresolvable`` (a ref naming no known ticket).
DISCHARGED_KIND = "discharged"


@dataclass(frozen=True)
class BlockerRef:
    """One named blocker on a row, resolved far enough to print.

    Carrying the title is the point. The complaint against today's board is
    that a blocked row says "blocked by non-terminal internal blocker" and
    makes the operator go look up which one; a band-G row names the id *and*
    the full title, on both sides of the constraint, with no hover and no
    click.
    """

    ref: str
    title: str | None
    status: str | None
    kind: str | None
    discharged: bool


@dataclass(frozen=True)
class Row:
    """One record as the board renders it.

    ``rank`` is ``None`` whenever the owning band carries ``show_rank=False``.
    That is not a rendering hint smuggled into the data — a rank number in a
    band where nine records tie on points is a claim the scores cannot
    support, so the absence is the honest value and the template has nothing
    left to decide.

    ``points`` is present in every band, including the ones removed from the
    ranking. Even where the ordering does not apply, the number is what makes
    the band placement falsifiable.

    ``status`` / ``priority`` / ``type`` are carried through verbatim, not
    normalised: all three vocabularies are documented as closed and are open
    in practice, and a row that reprints what the file actually says is the
    only way an operator can see that ``p0`` is not a priority this board
    knows.
    """

    id: str
    title: str
    points: int
    rank: int | None
    why: str
    status: str | None
    priority: str | None
    type: str | None
    blockers: tuple[BlockerRef, ...] = ()


@dataclass(frozen=True)
class Band:
    """One horizontal band on the board.

    ``key`` is the band letter as it prints. Two of them are primed (``E′``,
    ``G′``) because the design's letter run is A–H and two partitions were
    discovered after the letters were handed out: HOLD LAPSED, and the epic
    containers the ranking removes before it runs. A prime says "a sibling
    category the run did not anticipate" — renumbering instead would
    invalidate every letter the rest of the design refers to by name.

    ``border_style`` is one of ``solid`` / ``dashed`` / ``dotted`` / ``ghost``
    and is the fourth channel. It has to stay meaningful in monochrome, which
    is why it groups band *classes* — startable, not-a-task, held, lapsed,
    off-board — rather than trying to give eleven bands a distinct treatment
    that four values could not carry anyway.
    """

    key: str
    label: str
    count: int
    rationale: str
    border_style: str
    rows: list[Row] = field(default_factory=list)
    show_rank: bool = False


@dataclass(frozen=True)
class Bands(Sequence):
    """The partition, plus the coverage claim it makes about itself.

    Behaves as the ``list[Band]`` the signature names — iterate it, index it,
    take its length — while carrying the reconciliation as return values
    rather than as a printed footer. ``total`` and ``covered_ids`` are derived
    from the same assignment map that built the rows, so they cannot drift
    from what rendered; a test asserting ``total == len(slice)`` is therefore
    asserting about the page and not about a parallel count.
    """

    bands: tuple[Band, ...]
    total: int
    covered_ids: frozenset[str]

    def __len__(self) -> int:
        return len(self.bands)

    def __getitem__(self, index):  # noqa: ANN001,ANN201 - Sequence protocol
        return self.bands[index]

    def __iter__(self) -> Iterator[Band]:
        return iter(self.bands)

    def by_key(self, key: str) -> Band | None:
        """The band with this letter, or ``None``. Convenience for callers
        that need one band by name without scanning."""
        for band in self.bands:
            if band.key == key:
                return band
        return None


# ---------------------------------------------------------------------------
# Band metadata: key, label, border style, show_rank. Reading order.
# ---------------------------------------------------------------------------
#
# ``show_rank`` is True only for A, B and C. D and E are locked to False by
# operator decision: the dev corpus produces 13 distinct scores over 48
# startable rows, so a per-row rank there is decoration dressed as a
# measurement — the band label is the ordering claim and the points column is
# the evidence. The same reasoning retires the rank from the bands that were
# removed from the ranking outright (E*, E′, F, G, G′, H); numbering records
# the ranking refused to rank would be a contradiction rendered as an integer.
_BAND_META: tuple[tuple[str, str, str, bool], ...] = (
    ("A", "KEYHOLDERS", "solid", True),
    ("B", "ALREADY IN FLIGHT", "solid", True),
    ("C", "HIGH · STARTABLE", "solid", True),
    ("D", "MEDIUM · STARTABLE", "solid", False),
    ("E", "LOW · STARTABLE", "solid", False),
    ("E*", "UNKNOWN PRIORITY · STARTABLE", "solid", False),
    ("E′", "EPIC CONTAINERS", "dotted", False),
    ("F", "HELD · DEFERRED BY DECISION", "dotted", False),
    ("G", "DOWNSTREAM · NOT STARTABLE", "dashed", False),
    ("G′", "HOLD LAPSED · BLOCKER ALREADY COMPLETE", "ghost", False),
    ("H", "UNTRIAGED · CLOSED IN PLACE · OFF-BOARD", "ghost", False),
)

# The bands whose members are startable work competing for the same day. This
# is the set a caller feeds back into ``ScoreContext.contender_ids``.
STARTABLE_KEYS: tuple[str, ...] = ("A", "B", "C", "D", "E", "E*")


# ---------------------------------------------------------------------------
# Per-record facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Facts:
    """Everything the rule table needs about one record, resolved once.

    Rules are cheap predicates over this rather than repeated dictionary
    spelunking: thirteen rules across seventy-three records is a lot of
    re-derivation of the same blocker split, and a rule that recomputed it
    could disagree with the rule that ran before it.
    """

    tid: str
    status: str
    phase: str
    kind: str  # the record's `type`, case-folded; named to dodge the builtin
    priority: str
    holding: tuple[BlockerRef, ...]  # blockers that still constrain
    lapsed: tuple[BlockerRef, ...]  # blockers already closed
    hold_lapsed: bool  # graph's verdict: every incoming edge is discharged
    direct: tuple[str, ...]
    onward: tuple[str, ...]  # transitive dependents beyond the direct ones
    inflight_bits: tuple[str, ...]
    child_count: int
    on_order: bool


def _lower(value: object) -> str:
    """Case-fold a possibly-absent open-vocabulary field to a bare string.

    ``None``, ``""`` and whitespace all collapse to ``""`` so a rule can test
    truthiness. Anything else survives apart from case: this never maps an
    unrecognised value onto a recognised one, which is what would let a typo
    score as a real priority.
    """
    if value is None:
        return ""
    return str(value).strip().lower()


def _text(value: object) -> str:
    """``_lower`` without the case-fold, for values that get printed."""
    if value is None:
        return ""
    return str(value).strip()


def _id_sort_key(tid: str) -> tuple[int, int, str]:
    """Numeric ids ascending, non-numeric ones after them and lexical.

    Backlog ids are numeric by convention, but nothing in the write path
    enforces it, so every ordering here has to survive one that is not.
    """
    if tid.isdigit():
        return (0, int(tid), tid)
    return (1, 0, tid)


def _normalize_ids(records: object) -> list[str]:
    """Coerce whatever the caller passed into an ordered list of distinct ids.

    Accepts a sequence of ids (``str`` or ``int``), a sequence of record dicts
    carrying an ``id``, or an id-keyed mapping — the three shapes the snapshot
    hands around. Forcing the caller to pick one would just move this
    conversion to the call site.

    Duplicates collapse, first occurrence winning. A record cannot land in two
    bands, so a duplicated input id would make ``sum(counts)`` disagree with
    ``len(records)`` for a reason that has nothing to do with a dropped
    ticket. Folding it here keeps the reconciliation total measuring the one
    failure it exists to catch.
    """
    if isinstance(records, Mapping):
        candidates: list[object] = list(records.keys())
    else:
        candidates = list(records or [])

    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        raw = candidate.get("id") if isinstance(candidate, Mapping) else candidate
        tid = _text(raw)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def _blocker_split(
    tid: str, blocked_by_titles: Mapping[str, Any]
) -> tuple[tuple[BlockerRef, ...], tuple[BlockerRef, ...]]:
    """Split one record's incoming edges into (still holding, already lapsed).

    The graph has already classified every edge as ``live`` / ``discharged`` /
    ``external`` / ``unresolvable``; this only groups them. Everything that is
    not discharged is treated as holding — see the module docstring for why
    that is stricter than :func:`score.is_contender` on purpose.
    """
    holding: list[BlockerRef] = []
    lapsed: list[BlockerRef] = []

    for why in blocked_by_titles.get(tid, ()) or ():
        if not isinstance(why, Mapping):
            continue
        ref = _text(why.get("ref"))
        if not ref:
            continue
        kind = _text(why.get("kind")) or None
        discharged = kind == DISCHARGED_KIND
        blocker = BlockerRef(
            ref=ref,
            title=_text(why.get("title")) or None,
            status=_text(why.get("status")) or None,
            kind=kind,
            discharged=discharged,
        )
        (lapsed if discharged else holding).append(blocker)

    return tuple(holding), tuple(lapsed)


def _inflight_bits(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Name the lifecycle artefacts this record carries, in scoring order.

    Mirrors the inputs of the score model's ``inflight`` term so band B and
    the ledger cannot disagree about what "in flight" means. These strings are
    the row gloss only — the points come from ``score_of`` and never from here.
    """
    bits: list[str] = []
    phase = _lower(record.get("lifecycle_phase"))
    if phase and phase not in TERMINAL_PHASES:
        bits.append("phase %s" % phase)
    if record.get("spec"):
        bits.append("spec.md")
    if record.get("plan"):
        bits.append("plan.md")
    if record.get("research"):
        bits.append("research.md")
    return tuple(bits)


# ---------------------------------------------------------------------------
# Row glosses — the "why it sits here" column
# ---------------------------------------------------------------------------


def _fmt_ids(ids: Sequence[str], limit: int = 3) -> str:
    """Render an id list as ``#1, #2, #3 +4 more``.

    The remainder is counted rather than elided into an ellipsis, so the row
    still states the true size of the set it is summarising.
    """
    shown = ", ".join("#" + i for i in ids[:limit])
    extra = len(ids) - limit
    if extra > 0:
        return "%s +%d more" % (shown, extra)
    return shown or "none"


def _fmt_blocker(blocker: BlockerRef) -> str:
    if blocker.title:
        return "#%s %s" % (blocker.ref, blocker.title)
    if blocker.kind == "unresolvable":
        return "#%s (names no known ticket)" % blocker.ref
    if blocker.status:
        return "#%s (%s)" % (blocker.ref, blocker.status)
    return "#%s (outside the active slice)" % blocker.ref


def _why_closed(facts: _Facts) -> str:
    return "%s / %s — closed in place, shown so the arithmetic closes" % (
        facts.status or "unset",
        facts.phase or "—",
    )


def _why_off_board(_facts: _Facts) -> str:
    return "present in the slice but absent from the board's own ordering"


def _why_untriaged(_facts: _Facts) -> str:
    return "status: new — needs triage, not work"


def _why_deferred(_facts: _Facts) -> str:
    return "deferred — a decision that was made, not an obstacle that appeared"


def _why_blocked(facts: _Facts) -> str:
    return "waits on " + "; ".join(_fmt_blocker(b) for b in facts.holding)


def _fmt_lapsed_blocker(blocker: BlockerRef) -> str:
    """Name a discharged blocker the way a live one is named — id *and* title.

    The status stays because it is what says "discharged", but it is no longer
    the only thing said. Rendering these as a bare ``#90 (complete)`` made the
    one band that tells the operator to go ahead the one band that made them
    look up which ticket had been holding them.
    """
    status = blocker.status or "closed"
    if blocker.title:
        return "#%s %s (%s)" % (blocker.ref, blocker.title, status)
    return "#%s (%s)" % (blocker.ref, status)


def _why_lapsed(facts: _Facts) -> str:
    return "%s — constraint discharged, startable today" % "; ".join(
        _fmt_lapsed_blocker(b) for b in facts.lapsed
    )


def _why_container(facts: _Facts) -> str:
    return "container: %d active %s" % (
        facts.child_count,
        "child" if facts.child_count == 1 else "children",
    )


def _why_keyholder(facts: _Facts) -> str:
    held = "holds %s directly" % _fmt_ids(facts.direct)
    if facts.onward:
        return "%s, %d further downstream" % (held, len(facts.onward))
    return held


def _why_inflight(facts: _Facts) -> str:
    return "carries " + " · ".join(facts.inflight_bits)


def _why_priority(facts: _Facts) -> str:
    kind = facts.kind or "unset"
    if facts.kind in DEFECT_TYPES:
        kind += " (defect)"
    return "%s · %s" % (facts.priority or "unset", kind)


def _why_unknown_priority(facts: _Facts) -> str:
    return "priority: %s — outside the known set, banded rather than dropped" % (
        facts.priority or "unset"
    )


def _status_note(facts: _Facts) -> str:
    """The disclosure a startable row owes when its status is unrecognised.

    Empty for every status cortex knows, so it costs nothing on the ordinary
    board. When it fires, the row states the raw value and that the board took
    it at face value — because the alternative found in review was a record
    with ``status: icebox`` being presented as rank 1 of the startable field
    with nothing anywhere on the page disclosing that the ranking rested on a
    word the board does not understand.
    """
    if facts.status in OPEN_STATUSES:
        return ""
    return " · status: %s — outside cortex's vocabulary, taken at face value" % (
        facts.status or "unset"
    )


def _startable(reason: _Reason) -> _Reason:
    """Wrap a startable band's gloss so it discloses an unrecognised status."""

    def with_note(facts: _Facts) -> str:
        return reason(facts) + _status_note(facts)

    return with_note


def _why_catch_all(facts: _Facts) -> str:
    return "status: %s — matched no rule; banded so nothing is dropped" % (
        facts.status or "unset"
    )


# ---------------------------------------------------------------------------
# The rule table
# ---------------------------------------------------------------------------

_Predicate = Callable[[_Facts], bool]
_Reason = Callable[[_Facts], str]


def _always(_facts: _Facts) -> bool:
    """The unconditional catch-all predicate.

    Its identity is asserted by the test suite: whatever else changes about
    the rule table, the final rule must still be this function, because it is
    the only structural reason no record can fall off the page. A predicate
    that grew a condition would break the completeness property silently — the
    coverage total would still add up on every corpus that happened not to
    exercise the gap.
    """
    return True


# (band key, predicate, gloss builder). Order is **match precedence**, not the
# order bands render in. Three rules feed band H on purpose: its three named
# members have to outrank F and G, and the catch-all has to stay last, which
# is only possible if the band can be reached from more than one rule.
_RULES: tuple[tuple[str, _Predicate, _Reason], ...] = (
    # --- H's three named members, tested first ------------------------------
    # These outrank F and G deliberately. An abandoned ticket that also names
    # a live blocker is closed, not blocked; drawing it in band G would invite
    # somebody to go unblock work nobody intends to do.
    (
        "H",
        lambda f: f.status in TERMINAL_STATUSES or f.phase in TERMINAL_PHASES,
        _why_closed,
    ),
    ("H", lambda f: not f.on_order, _why_off_board),
    ("H", lambda f: f.status == "new", _why_untriaged),
    # --- held by decision, then held by dependency --------------------------
    # Deferral outranks a blocker: a deferred ticket that is also blocked is
    # not getting picked either way, and band F states the fact the operator
    # can actually act on — somebody chose this.
    ("F", lambda f: f.status == "deferred", _why_deferred),
    ("G", lambda f: bool(f.holding), _why_blocked),
    ("G′", lambda f: f.hold_lapsed or bool(f.lapsed), _why_lapsed),
    # --- containers, which the ranking removes before it runs ---------------
    ("E′", lambda f: f.kind in CONTAINER_TYPES, _why_container),
    # --- the startable sub-bands -------------------------------------------
    # Everything reaching here cleared every exclusion above, so "startable" is
    # true by construction and no rule below re-tests it.
    ("A", lambda f: bool(f.direct or f.onward), _startable(_why_keyholder)),
    ("B", lambda f: bool(f.inflight_bits), _startable(_why_inflight)),
    ("C", lambda f: f.priority in ("high", "critical"), _startable(_why_priority)),
    ("D", lambda f: f.priority == "medium", _startable(_why_priority)),
    ("E", lambda f: f.priority == "low", _startable(_why_priority)),
    ("E*", lambda f: f.priority not in PRIORITY_W, _startable(_why_unknown_priority)),
    # --- the unconditional catch-all. Must stay last. -----------------------
    ("H", _always, _why_catch_all),
)


# ---------------------------------------------------------------------------
# Rationales — the italic right-aligned gloss under each band label
# ---------------------------------------------------------------------------
#
# Static wherever the claim is static. The one that quotes a count takes it
# from the partition, because no corpus number may be baked into shipped copy.
_RATIONALE: dict[str, str] = {
    "B": "carries a spec, plan or research artefact — cheapest to resume",
    "C": "declared high or critical, with no live blocker",
    "D": "the bulk of the front; the band is the ordering claim, not the row order",
    "E": "startable, but nothing argues for them",
    "E*": "priority outside the known vocabulary — banded, never dropped",
    "E′": "a container is not a day's work; its children are ranked above",
    "F": "deferral is a decision that was made, not an obstacle that appeared",
    "G": "waiting on a live blocker; every row names the blocker and its title",
    "G′": "the declared blocker is already closed — free today, and the old "
    "board still called them blocked",
    "H": "shown so the arithmetic closes, not because you should act on them",
}


def _rationale_for(key: str, count: int, startable: int) -> str:
    """One band's gloss, with the counted one filled from live data."""
    if key == "A":
        return "startable AND unlock something downstream — %d of %d startable" % (
            count,
            startable,
        )
    return _RATIONALE.get(key, "")


# ---------------------------------------------------------------------------
# Ordering and points
# ---------------------------------------------------------------------------


def _ordering_key(tid: str, ctx: object) -> tuple:
    """Score-then-id, for every band.

    Bands D and E are locked to this ordering by operator decision — not to
    ``updated``, which was the alternative — and every other band uses it too.
    One ordering rule across the whole board is what stops the reconciliation
    and the rendering disagreeing about which row is which.

    ``rank_key`` casts through ``int``. It is wrapped because a record can
    reach the board without being resolvable by the score model at all (an id
    that arrived from ``item_order`` and nowhere else), and a board that
    raised on one bad row would render none of the good ones.
    """
    try:
        return rank_key(tid, ctx)
    except (TypeError, ValueError, KeyError, AttributeError):
        return (0,) + _id_sort_key(tid)


def _points(tid: str, ctx: object) -> int:
    """The record's total score, or 0 when the score model cannot place it.

    Zero is the honest value in that case: no term could be evaluated. It is
    not a claim that the ticket is worthless, which is why the row still
    prints its own "why it sits here" gloss beside it.
    """
    try:
        return int(score_of(tid, ctx).total)
    except (TypeError, ValueError, KeyError, AttributeError):
        return 0


def _dependents(tid: str, ctx: object, graph: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(direct dependents, further-downstream dependents) over live edges.

    Prefers the score context's own accessors, which restrict the answer to
    the active slice — the claim band A makes is "this unblocks N tickets *on
    this board*", and an operator can only check the ones that are on it. The
    raw graph maps are the fallback for a context that predates those helpers.
    """
    if hasattr(ctx, "direct_of") and hasattr(ctx, "downstream_of"):
        return tuple(ctx.direct_of(tid)), tuple(ctx.downstream_of(tid))

    direct_map = getattr(graph, "direct", {}) or {}
    downstream_map = getattr(graph, "downstream", {}) or {}
    direct = sorted((_text(x) for x in direct_map.get(tid, ())), key=_id_sort_key)
    onward = sorted(
        (
            _text(x)
            for x in downstream_map.get(tid, ())
            if _text(x) not in set(direct)
        ),
        key=_id_sort_key,
    )
    return tuple(direct), tuple(onward)


# ---------------------------------------------------------------------------
# The partition
# ---------------------------------------------------------------------------


def partition(records: object, ctx: object, *, item_order: object = None) -> Bands:
    """Partition *records* into the A–H bands.

    Args:
        records: The slice to band — a sequence of ids, a sequence of record
            dicts, or an id-keyed mapping. Duplicates collapse.
        ctx: The score context (:class:`score.ScoreContext`). Read for
            ``items``, ``graph`` and ``parents``.
        item_order: The board's own ordering, i.e. the snapshot's
            ``item_order``. Supplied separately because the score context does
            not carry it and has no reason to — the ranking never asks whether
            a record is on the board, only what it is worth. Left ``None``,
            the OFF-BOARD member of band H is not tested at all: an empty or
            missing ordering would otherwise sweep the entire slice into H,
            which is the exact failure the completeness property exists to
            surface, dressed up as a pass.

    Returns:
        A :class:`Bands` sequence carrying every band in reading order —
        including the empty ones, which the caller filters — plus ``total``
        and ``covered_ids``. ``total`` equals the number of distinct input ids
        and ``covered_ids`` equals the set of them, by construction.
    """
    ids = _normalize_ids(records)

    items: Mapping[str, Any] = getattr(ctx, "items", None) or {}
    graph = getattr(ctx, "graph", None)
    blocked_by_titles: Mapping[str, Any] = getattr(graph, "blocked_by_titles", None) or {}
    hold_lapsed: frozenset[str] = frozenset(
        _text(x) for x in (getattr(graph, "hold_lapsed", None) or ())
    )

    order_ids = frozenset(_text(i) for i in item_order) if item_order else None

    parents: Mapping[str, Any] = getattr(ctx, "parents", None) or {}
    if not parents:
        # Derive the child index from the records themselves. The context is
        # not required to carry one — cortex-command's own slice has zero
        # epics and legitimately supplies an empty mapping — and a container's
        # row gloss ("N active children") is worth more than the coupling.
        derived: dict[str, list[str]] = {}
        for tid, record in items.items():
            if not isinstance(record, Mapping):
                continue
            parent = _text(record.get("parent"))
            if parent:
                derived.setdefault(parent, []).append(_text(tid))
        parents = derived

    # id -> (band key, gloss). Built in one pass so the coverage numbers below
    # are read off the same structure the rows are.
    assignment: dict[str, tuple[str, str]] = {}

    for tid in ids:
        record = items.get(tid)
        if not isinstance(record, Mapping):
            record = {}

        holding, lapsed = _blocker_split(tid, blocked_by_titles)
        direct, onward = _dependents(tid, ctx, graph)
        facts = _Facts(
            tid=tid,
            status=_lower(record.get("status")),
            phase=_lower(record.get("lifecycle_phase")),
            kind=_lower(record.get("type")),
            priority=_lower(record.get("priority")),
            holding=holding,
            lapsed=lapsed,
            hold_lapsed=tid in hold_lapsed,
            direct=direct,
            onward=onward,
            inflight_bits=_inflight_bits(record),
            child_count=len(parents.get(tid, ()) or ()),
            on_order=True if order_ids is None else tid in order_ids,
        )

        for key, predicate, reason in _RULES:
            if predicate(facts):
                assignment[tid] = (key, reason(facts))
                break
        else:  # pragma: no cover - the last rule is unconditional
            raise AssertionError(
                "rule table fell through for #%s: the final rule is no longer "
                "unconditional, and the board can now drop records" % tid
            )

    members: dict[str, list[str]] = {key: [] for key, _l, _b, _r in _BAND_META}
    for tid in ids:
        members[assignment[tid][0]].append(tid)

    startable = sum(len(members[key]) for key in STARTABLE_KEYS)

    bands: list[Band] = []
    covered: set[str] = set()
    for key, label, border, show_rank in _BAND_META:
        ordered = sorted(members[key], key=lambda t: _ordering_key(t, ctx))

        rows: list[Row] = []
        for position, tid in enumerate(ordered, start=1):
            record = items.get(tid)
            if not isinstance(record, Mapping):
                record = {}
            holding, lapsed = _blocker_split(tid, blocked_by_titles)
            rows.append(
                Row(
                    id=tid,
                    title=_title_of(tid, record),
                    points=_points(tid, ctx),
                    rank=position if show_rank else None,
                    why=assignment[tid][1],
                    status=_text(record.get("status")) or None,
                    priority=_text(record.get("priority")) or None,
                    type=_text(record.get("type")) or None,
                    # Band G′ prints the discharged edge, because that is the
                    # whole claim it makes. Band G prints what still holds.
                    # No other band has an undischarged edge to print, by
                    # construction of the rule order.
                    blockers=lapsed if key == "G′" else holding,
                )
            )
            covered.add(tid)

        bands.append(
            Band(
                key=key,
                label=label,
                count=len(rows),
                rationale=_rationale_for(key, len(rows), startable),
                border_style=border,
                rows=rows,
                show_rank=show_rank,
            )
        )

    return Bands(
        bands=tuple(bands),
        total=sum(band.count for band in bands),
        covered_ids=frozenset(covered),
    )


def _title_of(tid: str, record: Mapping[str, Any]) -> str:
    """The record's full title, never truncated and never blank.

    A record can legitimately reach the board without a title — an id carried
    by ``item_order`` whose file the poll could not parse. Saying so is more
    useful than an empty cell, and it keeps the row clickable rather than
    dropping it to keep the table tidy.
    """
    title = record.get("title")
    if title:
        return str(title)
    return "#%s (title unavailable — not in the active slice)" % tid
