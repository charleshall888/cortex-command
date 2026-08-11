"""The six-term ranking behind "what should I work on next?", and its counterfactual.

This module is the whole editorial position of the navigator board, and the
position is **keystone-first**: leverage dominates declared priority. A ticket
that holds four others outranks every ``priority: high`` ticket that holds
nothing. On the dev corpus that puts #331 (``priority: low``, +42 leverage)
above #147 (``priority: high``, +36) — a deliberate disagreement with the
priority-sorted board this one replaces, confirmed as an operator decision and
not open for softening into a tiebreak. ``test_navigator_score.py`` pins it,
because a regression there changes what the operator is told to do next while
every other test still passes.

Two properties are load-bearing and easy to break by accident:

* **Every term prints its raw input.** ``Term.raw`` is operator-facing prose,
  not a debug repr — the ledger's entire value is that a rank is falsifiable
  line by line, so a reader can check "holds #242, #278" against the tickets
  themselves and reject the rank if it is wrong. A term that scores 0 still
  emits a row saying what it looked at; six rows, always, in ``TERM_META``
  order.
* **Nothing here reads the wall clock.** The ``stale`` term measures against
  ``max(updated)`` across the corpus, never ``date.today()``. The page
  re-renders every 30 seconds through an htmx morph-swap, and a wall-clock
  anchor would tick a score over a day boundary with no data change, producing
  a diff the operator did not cause. Byte-stability is a property of the
  formula, not of the template.

Vocabularies are open in practice — the item-creation verb applies no
restriction to ``priority``, ``type``, or ``status`` — so every lookup here
has a default branch and an unknown value scores rather than raises. That
tolerance lives in this module and nowhere else; ``bands.py`` and ``view.py``
are entitled to assume a score exists for every record they are handed.

The graph is *read*, never rebuilt. ``graph.py`` owns edge normalisation,
live/discharged classification, and the transitive closure; this module only
counts what that module already decided. The import is deferred to
``TYPE_CHECKING`` so the two can be developed independently — nothing here
calls a graph function, it only reads documented attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from .graph import Graph


# --------------------------------------------------------------------------
# Vocabulary constants
# --------------------------------------------------------------------------

PRIORITY_W = {"critical": 40, "high": 30, "medium": 18, "low": 8}

# An unrecognised priority scores between "medium" and "low" rather than at
# zero. Scoring it zero would quietly bury a ticket whose author simply typed
# a word this table has not heard of; scoring it high would reward the typo.
UNKNOWN_PRIORITY = 12

# A lifecycle phase in this set is finished work, so it earns no in-flight
# credit. Shared with the graph's discharged-edge rule by coincidence of
# meaning, not by import: these are *phase* values, those are *status* values,
# and the two vocabularies drift independently.
TERMINAL_PHASES = frozenset({"complete", "done", "wontfix", "abandoned"})

DEFECT_TYPES = frozenset({"bug", "fix", "regression"})

# Epic containers are removed from `contenders` before the ranking runs. A
# container is not a day's work, and on the dev corpus 5 of 56 ready items are
# containers including two of the five `high`-priority tickets — a
# priority-sorted board floats all of them to the very top and tells the
# operator to go "work on" a grouping.
CONTAINER_TYPES = frozenset({"epic"})

# Statuses that take a record out of the ranking. `deferred` and `new` are
# excluded because they are decisions and non-decisions respectively, not
# candidates; the terminal set is excluded because the work is over. Anything
# NOT in this set is a candidate — the check is a denylist precisely because
# the status vocabulary is open and an unrecognised status must still be able
# to reach the board.
NON_CONTENDER_STATUSES = frozenset(
    {"deferred", "new", "complete", "done", "wontfix", "abandoned"}
)

# (key, operator-facing label, css swatch class). This list is the ledger's
# row order and its length: six rows, every time, including zeros. Templates
# read the labels from here so the ledger and any legend cannot disagree.
TERM_META: list[tuple[str, str, str]] = [
    ("priority", "Declared priority", "t-pri"),
    ("leverage", "Unblocks others", "t-lev"),
    ("inflight", "Already in flight", "t-fly"),
    ("epic", "Advances a live epic", "t-epi"),
    ("defect", "Is a defect", "t-def"),
    ("stale", "Sat untouched", "t-stl"),
]

_TERM_LABELS = {key: label for key, label, _ in TERM_META}
_TERM_ORDER = [key for key, _, _ in TERM_META]


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Term:
    """One line of the ledger.

    ``raw`` is the input this term looked at, written for a human: it is what
    lets a reader disagree with the rank without reading this file. ``note``
    is the second line — an arithmetic breakdown or a caveat — and is ``None``
    when the raw input speaks for itself.
    """

    key: str
    label: str
    points: int
    raw: str
    note: str | None = None


@dataclass(frozen=True)
class Score:
    """A total and the six terms that produced it, in ``TERM_META`` order."""

    total: int
    terms: list[Term]

    @property
    def by_key(self) -> dict[str, Term]:
        """Terms keyed for direct lookup, for callers computing swap deltas."""
        return {term.key: term for term in self.terms}


@dataclass(frozen=True)
class Counterfactual:
    """What changes on this board if ``pick`` lands.

    ``freed`` are the ids whose *only* live blocker was the pick — they become
    startable the moment it closes. ``still_held`` are the ones the pick also
    blocks but which stay held by something else, which is the honest other
    half: a pick that frees nothing is a pick whose leverage is speculative.
    ``new_top3`` is the resulting board's top three, re-ranked over
    ``contenders - {pick} | freed`` so the argument for the pick is the
    already-written argument for what comes after it.
    """

    pick: str
    freed: list[str]
    still_held: list[str]
    new_top3: list[tuple[str, int]]


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


@dataclass
class ScoreContext:
    """Everything the six terms and the counterfactual read.

    Held as one object rather than five parameters because ``bands.py``,
    ``epic_layout.py`` and ``view.py`` all take the same context, and a
    ranking that silently disagreed with the band partition about which
    records exist would be undetectable from the rendered page.

    Args:
        items: Active-slice records, id-keyed with **string** keys. This is
            the snapshot's ``items``, so ids arrive stringified; anything
            passed with int keys is normalised on construction.
        graph: The :class:`~.graph.Graph` for this slice. Read-only, and read
            by attribute — ``direct``, ``downstream``, ``live``,
            ``declared_by``. Never rebuilt here.
        parents: Epic id → active child ids. Supplies the ``epic`` term's
            child count; an empty mapping is legitimate (cortex-command's own
            slice has zero epics) and every ticket then scores the
            has-a-parent value or nothing.
        as_of: The corpus anchor for the ``stale`` term, ``YYYY-MM-DD``.
            Derived from ``items`` when left empty. Passing it explicitly is
            for tests that need a fixed anchor; production leaves it derived
            so it moves only when the data does.
        contender_ids: Optional override of the ranked population. ``None``
            means "derive it here", which is what production does. The
            override exists so a caller that has already partitioned records
            can guarantee the ranking and the bands see the same set.
    """

    items: dict[str, dict]
    graph: Graph
    parents: dict[str, list[str]] = field(default_factory=dict)
    as_of: str = ""
    contender_ids: frozenset[str] | None = None

    # Derived on construction. Excluded from equality and repr: they are
    # caches of the fields above, so including them would make two contexts
    # over identical data compare unequal on memo-population order alone.
    _score_memo: dict[str, Score] = field(
        default_factory=dict, repr=False, compare=False
    )
    _live_blockers: dict[str, set[str]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # Ids are string keys everywhere they are used as keys (the snapshot's
        # own rule). A context built from a hand-written int-keyed dict would
        # otherwise miss every lookup and score every ticket as unknown, which
        # is a silent wrong answer rather than an error.
        if any(not isinstance(key, str) for key in self.items):
            self.items = {str(key): value for key, value in self.items.items()}
        if any(not isinstance(key, str) for key in self.parents):
            self.parents = {
                str(key): [str(child) for child in value]
                for key, value in self.parents.items()
            }

        if not self.as_of:
            self.as_of = corpus_as_of(self.items)

        # Reverse the graph's live edge list once. Every term and the whole
        # counterfactual asks "what still holds X", and scanning the edge list
        # per question is O(edges) inside an O(items) loop.
        for blocker, blocked in getattr(self.graph, "live", ()):
            self._live_blockers.setdefault(str(blocked), set()).add(str(blocker))

    # -- graph reads ------------------------------------------------------

    def live_blockers_of(self, tid: str) -> set[str]:
        """Ids that still hold *tid*. Empty means startable."""
        return self._live_blockers.get(tid, set())

    def direct_of(self, tid: str) -> list[str]:
        """Immediate live dependents of *tid*, restricted to the active slice.

        The intersection with ``items`` is deliberate and is the difference
        between an honest count and an inflated one: the graph may legitimately
        carry an edge whose blocked side sits outside the slice, but the claim
        this term makes is "this unblocks N tickets **on this board**", and the
        operator can only check the ones that are on it.
        """
        return _sorted_ids(getattr(self.graph, "direct", {}).get(tid, ()), self.items)

    def downstream_of(self, tid: str) -> list[str]:
        """Transitive live dependents of *tid* beyond the direct ones."""
        direct = set(self.direct_of(tid))
        closure = getattr(self.graph, "downstream", {}).get(tid, ())
        return [x for x in _sorted_ids(closure, self.items) if x not in direct]

    def declared_by(self, blocker: str, blocked: str) -> str:
        """Which side of the edge declared it: ``blocks``/``blocked_by``/``both``."""
        table = getattr(self.graph, "declared_by", {})
        return table.get((blocker, blocked), "blocks")


def corpus_as_of(items: dict[str, dict]) -> str:
    """The corpus's own "today": the latest ``updated`` anywhere in the slice.

    Returns ``""`` when no record carries a *parseable* date, which the
    ``stale`` term reads as "no anchor" and scores zero rather than guessing.
    ``max`` takes a ``default`` here for the same reason it does everywhere in
    this package — the 4-item cortex-command slice is a real input, not a
    pathological one.

    The parse filter is load-bearing, not defensive tidiness: these are
    ISO strings compared as strings, so a single ticket with
    ``updated: soon`` sorts above every real date and would become the anchor,
    silently zeroing the ``stale`` term for the entire board.
    """
    return max(
        (
            stamp
            for stamp in (
                _text(record.get("updated")) for record in items.values()
            )
            if _parse_date(stamp) is not None
        ),
        default="",
    )


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _text(value: object) -> str:
    """Coerce a frontmatter value to a stripped string. ``None`` becomes ``""``."""
    if value is None:
        return ""
    return str(value).strip()


def _lower(value: object) -> str:
    return _text(value).lower()


def _sorted_ids(ids, known: dict[str, dict]) -> list[str]:
    """Stringify, keep only ids present in *known*, and sort numerically."""
    kept = {str(x) for x in ids} & set(known)
    return sorted(kept, key=_id_sort_key)


def _id_sort_key(tid: str) -> tuple[int, int, str]:
    """Numeric-first ordering that survives a non-numeric id.

    Ids are integers throughout both corpora and the contract specifies
    ``int(tid)``, but nothing in the item-creation path *enforces* that, and a
    ``ValueError`` raised out of a sort key would take down the whole board
    rather than misplace one row. Numeric ids keep exactly the documented
    order among themselves; anything else sorts after them, alphabetically.
    """
    try:
        return (0, int(tid), "")
    except (TypeError, ValueError):
        return (1, 0, str(tid))


def _parse_date(value: str) -> date | None:
    """Parse ``YYYY-MM-DD``, returning ``None`` for anything else.

    Deliberately narrow. A half-parsed date would produce a plausible-looking
    staleness number from a value the operator never wrote, and the ledger's
    whole promise is that its inputs are checkable.
    """
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _id_list(ids) -> str:
    return ", ".join("#" + str(x) for x in ids)


# --------------------------------------------------------------------------
# The six terms
# --------------------------------------------------------------------------


def _term_priority(record: dict, ctx: ScoreContext) -> Term:
    declared = _lower(record.get("priority"))
    known = declared in PRIORITY_W
    points = PRIORITY_W[declared] if known else UNKNOWN_PRIORITY

    if known:
        note = None
        raw = "priority: %s" % declared
    elif declared:
        raw = "priority: %s" % declared
        note = "not in the known set — scored at the %d default" % UNKNOWN_PRIORITY
    else:
        raw = "priority: none declared"
        note = "nothing declared — scored at the %d default" % UNKNOWN_PRIORITY

    return Term("priority", _TERM_LABELS["priority"], points, raw, note)


def _term_leverage(tid: str, record: dict, ctx: ScoreContext) -> Term:
    """14 per direct dependent, 7 per further-downstream one.

    This is the term that makes the board disagree with a priority sort, so it
    is also the term most likely to be challenged — which is why the raw string
    names every id *and which side of the edge declared it*. An edge counts if
    either side declared it, so a ticket routinely holds something its own
    ``blocks:`` list never mentions; without the provenance the reader would
    check the pick's frontmatter, find nothing, and conclude the board lied.
    """
    direct = ctx.direct_of(tid)
    further = ctx.downstream_of(tid)
    points = 14 * len(direct) + 7 * len(further)

    if direct:
        held = []
        for other in direct:
            side = ctx.declared_by(tid, other)
            if side == "both":
                where = "declared on both sides"
            elif side == "blocked_by":
                where = "via #%s's blocked_by:" % other
            else:
                where = "via this ticket's blocks:"
            held.append("#%s (%s)" % (other, where))
        parts = ["directly holds " + ", ".join(held)]
        if further:
            parts.append("and through them " + _id_list(further))
        raw = " · ".join(parts)
        note = "14 × %d direct + 7 × %d downstream" % (len(direct), len(further))
    else:
        # Downstream-without-direct is unreachable through live edges, but the
        # closure is another module's output and this term does not get to
        # assume it. Print whatever arrived.
        raw = (
            "holds nothing on this board"
            if not further
            else "downstream only: " + _id_list(further)
        )
        note = None if not further else "7 × %d downstream" % len(further)

    return Term("leverage", _TERM_LABELS["leverage"], points, raw, note)


def _term_inflight(record: dict, ctx: ScoreContext) -> Term:
    """Credit for work already started, so the board does not scatter attention.

    ``lifecycle_phase`` is the authoritative field; ``phase`` (the snapshot's
    normalised copy) is read only when the raw key is absent entirely, so a
    record built by either path scores the same.
    """
    points = 0
    seen: list[str] = []

    if "lifecycle_phase" in record:
        phase = _lower(record.get("lifecycle_phase"))
    else:
        phase = _lower(record.get("phase"))

    if phase and phase not in TERMINAL_PHASES:
        points += 20
        seen.append("lifecycle_phase: %s (+20)" % phase)
    elif phase:
        seen.append("lifecycle_phase: %s — terminal, no credit" % phase)

    for key, weight, label in (
        ("spec", 10, "spec.md"),
        ("plan", 5, "plan.md"),
        ("research", 3, "research.md"),
    ):
        if record.get(key):
            points += weight
            seen.append("%s recorded (+%d)" % (label, weight))

    raw = " · ".join(seen) if seen else "no lifecycle phase or artefacts recorded"
    return Term("inflight", _TERM_LABELS["inflight"], points, raw, None)


def _term_epic(record: dict, ctx: ScoreContext) -> Term:
    """+6 inside a live epic (3+ active children), +3 inside any epic.

    The 3-child threshold is what separates "this advances something with
    momentum" from "this happens to have a parent". Both are worth something;
    only the first is worth interrupting the priority order for.
    """
    parent = _text(record.get("parent"))
    if not parent:
        return Term("epic", _TERM_LABELS["epic"], 0, "no parent epic", None)

    children = ctx.parents.get(parent)
    if children is None:
        # The parent is not a group on this board — it may be closed, or live
        # outside the active slice. The ticket still belongs to something, so
        # it keeps the base credit; the count it would have earned is unknown
        # rather than zero, and the raw says so instead of printing "0".
        return Term(
            "epic",
            _TERM_LABELS["epic"],
            3,
            "child of #%s — parent is not an active group on this board" % parent,
            None,
        )

    count = len(children)
    points = 6 if count >= 3 else 3
    raw = "child of #%s — %d active child%s on this board" % (
        parent,
        count,
        "" if count == 1 else "ren",
    )
    note = None if count >= 3 else "fewer than 3 active children — base credit only"
    return Term("epic", _TERM_LABELS["epic"], points, raw, note)


def _term_defect(record: dict, ctx: ScoreContext) -> Term:
    declared = _lower(record.get("type"))
    points = 6 if declared in DEFECT_TYPES else 0
    raw = "type: %s" % (declared or "none declared")
    return Term("defect", _TERM_LABELS["defect"], points, raw, None)


def _term_stale(record: dict, ctx: ScoreContext) -> Term:
    """One point per week untouched, capped at 6 — measured against the corpus.

    The anchor is ``max(updated)`` across the slice, never ``date.today()``.
    Two reasons, and the second is the one that bites: a corpus anchor makes
    the term a statement about *this backlog's* internal age rather than about
    how long the dashboard has been running, and it makes an unchanged 30s
    poll re-render byte-identically. With a wall-clock anchor every ticket's
    score would step at midnight, morphing the whole board on no new data.
    """
    key = "stale"
    label = _TERM_LABELS[key]

    anchor = _parse_date(ctx.as_of)
    if anchor is None:
        return Term(key, label, 0, "no dated record in this slice to measure against")

    stamp = _text(record.get("updated"))
    fell_back = False
    if not stamp:
        stamp = _text(record.get("created"))
        fell_back = True

    if not stamp:
        return Term(key, label, 0, "no updated: or created: date on this ticket")

    when = _parse_date(stamp)
    if when is None:
        return Term(
            key,
            label,
            0,
            "%s: %s" % ("created" if fell_back else "updated", stamp),
            "not a YYYY-MM-DD date — scored at 0 rather than guessed",
        )

    # Clamped at zero: a `created` fallback can post-date the corpus anchor
    # when the newest ticket is also the one missing `updated`, and a negative
    # week count would read as "touched in the future".
    days = max((anchor - when).days, 0)
    points = min(days // 7, 6)

    # "0 days before the corpus's latest change" is technically true and reads
    # like a bug. The ticket that sets the anchor gets said so plainly.
    field_name = "created" if fell_back else "updated"
    if days == 0:
        raw = "%s: %s — the corpus's most recent change" % (field_name, stamp)
    else:
        raw = "%s: %s — %d day%s before the corpus's latest change (%s)" % (
            field_name,
            stamp,
            days,
            "" if days == 1 else "s",
            ctx.as_of,
        )
    notes = []
    if fell_back:
        notes.append("no updated: date — fell back to created:")
    if days // 7 > 6:
        notes.append("capped at 6 (%d weeks untouched)" % (days // 7))
    return Term(key, label, points, raw, " · ".join(notes) or None)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def score_of(tid: str, ctx: ScoreContext) -> Score:
    """Score one ticket, emitting all six terms whether or not they contribute.

    Total in the sense that matters: any id, any vocabulary, any missing
    field. An id absent from ``ctx.items`` scores against an empty record
    rather than raising — a board that drops a row it cannot explain is worse
    than one that shows a row scoring 12 and says why.
    """
    tid = str(tid)
    memo = ctx._score_memo.get(tid)
    if memo is not None:
        return memo

    record = ctx.items.get(tid) or {}
    terms = [
        _term_priority(record, ctx),
        _term_leverage(tid, record, ctx),
        _term_inflight(record, ctx),
        _term_epic(record, ctx),
        _term_defect(record, ctx),
        _term_stale(record, ctx),
    ]
    # Guards the ledger against a future term being added to one place and not
    # the other: the row order is TERM_META's, and callers index by position.
    assert [t.key for t in terms] == _TERM_ORDER, "ledger row order drifted"

    result = Score(total=sum(t.points for t in terms), terms=terms)
    ctx._score_memo[tid] = result
    return result


def rank_key(tid: str, ctx: ScoreContext) -> tuple:
    """Sort key: score descending, then id ascending.

    Ties break on id and nothing else. There are only ~13 distinct scores over
    48 startable rows on the dev corpus, so a tiebreak that read a mutable
    field — ``updated``, say — would reshuffle most of the board on a poll
    that changed one ticket.
    """
    return (-score_of(tid, ctx).total,) + _id_sort_key(str(tid))


def is_contender(tid: str, ctx: ScoreContext) -> bool:
    """Is this record eligible for the ranked top-of-board?

    Four exclusions, each for a different reason: epic containers are not a
    day's work; deferred and new are decisions and non-decisions rather than
    candidates; a terminal status is finished; and a live blocker means the
    ticket cannot be started today no matter what it scores. Everything else
    is a contender — an unrecognised status must still reach the board.
    """
    tid = str(tid)
    record = ctx.items.get(tid)
    if record is None:
        return False
    if _lower(record.get("type")) in CONTAINER_TYPES:
        return False
    if _lower(record.get("status")) in NON_CONTENDER_STATUSES:
        return False
    # A finished lifecycle phase on an otherwise-open status is how a ticket
    # says "the work landed, the row has not been closed yet". The empty
    # string is not in the set, so an unset phase falls through.
    if _lower(record.get("lifecycle_phase")) in TERMINAL_PHASES:
        return False
    if ctx.live_blockers_of(tid):
        return False
    return True


def contenders(ctx: ScoreContext) -> list[str]:
    """The ranked contender list — rank 1 first.

    Honours ``ctx.contender_ids`` when the caller supplied one, so the
    ranking and the band partition cannot disagree about the population.
    """
    if ctx.contender_ids is not None:
        pool = [tid for tid in ctx.contender_ids if tid in ctx.items]
    else:
        pool = [tid for tid in ctx.items if is_contender(tid, ctx)]
    return sorted(pool, key=lambda tid: rank_key(tid, ctx))


def counterfactual(pick: str, ctx: ScoreContext) -> Counterfactual:
    """What the board looks like once *pick* lands.

    The re-ranked board is computed by running the *same* ``rank_key`` over a
    changed population — ``contenders - {pick} | freed`` — rather than by
    adjusting scores. That is the honest simulation: closing a ticket does not
    make the survivors more valuable, it makes previously-held work reachable.

    A ticket is ``freed`` only when *every* live blocker it has is the pick.
    The dev corpus has a case each way (#278 is held by the pick and by an
    already-complete ticket, so it frees; a ticket held by two live blockers
    does not), and reporting the second group as freed would be the single
    most misleading thing this surface could say.
    """
    pick = str(pick)
    held_by_pick = ctx.direct_of(pick)

    freed: list[str] = []
    still_held: list[str] = []
    for other in held_by_pick:
        if ctx.live_blockers_of(other) <= {pick}:
            freed.append(other)
        else:
            still_held.append(other)

    remaining = [tid for tid in contenders(ctx) if tid != pick]
    reranked = sorted(
        dict.fromkeys(remaining + freed), key=lambda tid: rank_key(tid, ctx)
    )
    top3 = [(tid, score_of(tid, ctx).total) for tid in reranked[:3]]

    return Counterfactual(
        pick=pick, freed=freed, still_held=still_held, new_top3=top3
    )
