"""View-models for the backlog navigator's two surfaces.

This is the only module in the package that knows what a *section* is. The four
helpers beneath it answer separate questions — what depends on what
(:mod:`.graph`), what is it worth (:mod:`.score`), where does it sit
(:mod:`.bands`), where is it drawn (:mod:`.epic_layout`) — and none of them
knows that the answers get arranged into "§ 01 THE PICK" and "§ 03 THE BOARD".
Keeping that knowledge here is what lets a template be a template: every
sentence, count and coordinate a template prints is computed below and handed
over as a plain dict, so the Jinja layer has no arithmetic and no vocabulary
decisions left to make.

Two properties are load-bearing and are the reason several things below look
more careful than they need to:

**Nothing is read from disk.** Both builders take the 30s poll's snapshot and
nothing else. A route that hit the filesystem would do it once per viewer per
poll for data the poller already holds, and the corpus argument
:func:`~.graph.build_graph` wants is reconstructible from the snapshot: the
slice records *are* the corpus for every id on the board, and the snapshot's
``blocked_why`` already carries the resolved status and title of every ref
pointing off it. ``root`` is therefore accepted (the routes resolve it anyway,
and both builders sit beside the ``data.py`` builders that do take it) and
deliberately unread.

**The same snapshot renders byte-identically.** Every collection built here is
either sorted or built in a sorted iteration order, and no value anywhere reads
the wall clock — the ``stale`` term is anchored to ``max(updated)`` inside
:mod:`.score` for exactly this reason. An htmx morph-swap of an unchanged
snapshot must produce the same bytes, or the operator's cursor moves under
their hand every thirty seconds.

An absent snapshot (never polled, or a non-``cortex-backlog`` backend, which
clears it to ``None``) returns a schema-complete empty view-model. Templates
render an empty state from a *present* key rather than guarding every access,
which is the difference between a page that says "awaiting first poll" and one
that renders blanks because a dotted lookup found an ``Undefined``.
"""

from __future__ import annotations

from typing import Any

from cortex_command.dashboard.backlog import bands as bands_mod
from cortex_command.dashboard.backlog.bands import OPEN_STATUSES
from cortex_command.dashboard.backlog.epic_layout import (
    POOL_INSET,
    LayoutContext,
    layout_epic,
)
from cortex_command.dashboard.backlog.graph import build_graph, normalize_ref
from cortex_command.dashboard.backlog.score import (
    TERM_META,
    ScoreContext,
    contenders,
    counterfactual,
    score_of,
)

# How many ranked entries § 02 ALTERNATES shows. Three total picks (rank 1 in
# § 01 plus two here) is the number the corpus supports: the dev slice produces
# roughly thirteen distinct scores over forty-eight startable rows, so a fourth
# ranked entry would be asserting a difference the scores cannot carry.
ALTERNATE_COUNT = 2

# Below this, an epic collapses to a row in THE TAIL rather than getting a
# frame. A diagram of one node is a box with nothing to say about ordering.
FRAME_MIN_CHILDREN = 2

# Band letter → the one- or two-word state label a node box may carry in SVG.
# Two words is the ceiling because the contract caps SVG text at three-word
# labels, and it is a *label* rather than a truncated title: a shortened title
# would be a width guess against an unbundled font, which is the specific
# defect the whole no-text-metrics rule exists to prevent. Full titles are
# rendered as HTML, in the table beneath each frame.
_NODE_STATE = {
    "A": "ready",
    "B": "in flight",
    "C": "ready",
    "D": "ready",
    "E": "ready",
    "E*": "ready",
    "E′": "epic",
    "F": "deferred",
    "G": "held",
    "G′": "lapsed",
    "H": "off board",
}

# Band letter → border style, so a node in a frame carries the same channel the
# same record carries in its band row on surface A. Mirrors ``bands._BAND_META``
# by key rather than importing the tuple, because the frame needs a *default*
# for an id the partition never saw (an external blocker off the slice) and a
# lookup with a default is the honest expression of that.
_BORDER_OF_BAND = {
    "A": "solid",
    "B": "solid",
    "C": "solid",
    "D": "solid",
    "E": "solid",
    "E*": "solid",
    "E′": "dotted",
    "F": "dotted",
    "G": "dashed",
    "G′": "ghost",
    "H": "ghost",
}

# Term key → the noun phrase that term becomes inside the swap sentence. The
# ledger's own labels are column headings ("Is a defect", "Sat untouched") and
# lowercasing one into a clause produces "if is a defect matters more to you".
# One sentence deserves one extra vocabulary; the two stay keyed to the same
# term list so a new term cannot arrive with only half of it.
_SWAP_CLAUSE = {
    "priority": "declared priority",
    "leverage": "unblocking others",
    "inflight": "work already under way",
    "epic": "advancing a live epic",
    "defect": "being a defect",
    "stale": "how long it has sat",
}

# The census groups the eleven bands into the five dispositions an operator
# distinguishes when they ask "what is on this board". The grouping is here and
# not in bands.py because it is a *legend*, and a legend is a section.
_CENSUS_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("startable", "startable today", ("A", "B", "C", "D", "E", "E*")),
    ("lapsed", "hold lapsed — startable and looks blocked", ("G′",)),
    ("blocked", "behind a live blocker", ("G",)),
    ("deferred", "held by decision", ("F",)),
    ("container", "epic containers", ("E′",)),
    ("offboard", "untriaged · closed in place · off-board", ("H",)),
)

# What each border style claims, printed beside its live count. The style is
# the channel that survives monochrome and colour-blindness, so the key states
# it in words rather than relying on the reader inferring it from the swatch.
_BORDER_GLOSS = {
    "solid": "startable — nothing external holds it",
    "dotted": "held by a decision, or not a task at all",
    "dashed": "held by a live dependency",
    "ghost": "not competing for today — closed, off-board, or already free",
}


# ---------------------------------------------------------------------------
# Snapshot → context
# ---------------------------------------------------------------------------


def _snapshot(state: object) -> dict | None:
    """The poll's snapshot, or ``None`` when there has not been one."""
    snap = getattr(state, "backlog_snapshot", None)
    return snap if isinstance(snap, dict) else None


def _backend(state: object) -> str:
    """The resolved backlog backend, for the gate every backlog read sits behind."""
    return str(getattr(state, "backlog_backend", "cortex-backlog") or "")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _id_key(tid: str) -> tuple[int, int, str]:
    """Numeric ids ascending, non-numeric after them — the package's ordering."""
    return (0, int(tid), "") if tid.isdigit() else (1, 0, tid)


def _items_of(snapshot: dict) -> dict[str, dict]:
    """The active slice, id-keyed with string keys.

    The snapshot already stringifies its keys; re-normalising costs one pass
    and removes the whole class of silent miss where an int key looks up as
    absent and every record scores as unknown.
    """
    raw = snapshot.get("items") or {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def _corpus_of(snapshot: dict, items: dict[str, dict]) -> list[dict]:
    """Reconstruct :func:`~.graph.build_graph`'s corpus argument.

    The graph reads the corpus for exactly two things — a ref's status and its
    title — and the snapshot already carries both for every ref that points off
    the slice, in ``blocked_why``. So the corpus is the slice records plus one
    stub per off-slice ref, and no file is opened.

    The status is what makes this more than a nicety: it is the sole input to
    the discharged/live classification, and therefore the sole reason the HOLD
    LAPSED band can exist. A stub without it would redraw two startable tickets
    as blocked.
    """
    corpus: list[dict] = list(items.values())
    seen = set(items)
    for rows in (snapshot.get("blocked_why") or {}).values():
        for row in rows or []:
            ref = normalize_ref(row.get("ref"))
            if not ref or ref in seen:
                continue
            seen.add(ref)
            stub: dict[str, Any] = {"id": ref, "status": row.get("status")}
            # Only when the feed actually resolved one. An invented placeholder
            # title would print on a band-G row as though it were the blocker's
            # real name; absent, the row falls back to naming the status.
            if row.get("title"):
                stub["title"] = row["title"]
            corpus.append(stub)
    return corpus


def _parents_of(items: dict[str, dict]) -> dict[str, list[str]]:
    """Epic id → its active children, from each record's own ``parent`` field.

    Derived from ``parent`` rather than from the snapshot's ``epics`` envelope
    because the envelope is pruned for the old board's grouping rules (a closed
    epic is kept only while it still has children) while this map has to answer
    a different question: which container does the ``epic`` score term credit,
    and whose children does a frame draw. A parent id that is not itself on the
    board is kept — those groups are real, and § 5.4 routes them to the tail
    with their membership stated rather than dropping them.
    """
    parents: dict[str, list[str]] = {}
    for tid in sorted(items, key=_id_key):
        parent = normalize_ref(items[tid].get("parent"))
        if parent:
            parents.setdefault(parent, []).append(tid)
    return parents


def _context(snapshot: dict) -> tuple[dict[str, dict], Any, ScoreContext, dict[str, list[str]]]:
    """Assemble the slice, its graph, its score context and its parent map."""
    items = _items_of(snapshot)
    graph = build_graph(items, _corpus_of(snapshot, items))
    parents = _parents_of(items)
    ctx = ScoreContext(items=items, graph=graph, parents=parents)
    return items, graph, ctx, parents


# ---------------------------------------------------------------------------
# § 01 / § 02 — the pick and its alternates
# ---------------------------------------------------------------------------


def _title_of(tid: str, items: dict[str, dict]) -> str:
    """A ticket's title, or a statement that it is not on this board.

    Never the empty string: every place this feeds is a link's accessible name
    or a sentence, and a blank there reads as a rendering failure rather than
    as missing data.
    """
    record = items.get(tid)
    if record is None:
        return "not on this board"
    return _text(record.get("title")) or "untitled"


def _ref(tid: str, items: dict[str, dict]) -> dict:
    """One id as every cross-reference on these surfaces renders it."""
    return {"id": tid, "title": _title_of(tid, items), "href": "/tickets/%s" % tid}


def _join(parts: list[str]) -> str:
    """``a, b and c`` — a list read as a sentence clause rather than as data.

    Every prose string on these surfaces is assembled from live values, so the
    conjunctions have to be assembled too; a comma-joined run reads as a
    rendering artefact exactly where the copy is trying to make an argument.
    """
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _fmt_refs(ids: list[str]) -> str:
    """``#242, #278 and #388`` — an id list inside a sentence."""
    return _join(["#" + tid for tid in ids])


def _ledger(tid: str, ctx: ScoreContext) -> list[dict]:
    """The six ledger rows, in ``TERM_META`` order, zeros included.

    A zero row is not noise: the ledger's claim is that the total is the sum of
    six named terms, and a ledger that dropped the zeros would be showing a
    different arithmetic from the one that ranked the row. ``zero`` travels as
    data so the template dims rather than decides.
    """
    swatch = {key: css for key, _label, css in TERM_META}
    return [
        {
            "key": term.key,
            "label": term.label,
            "points": term.points,
            "raw": term.raw,
            "note": term.note,
            "swatch": swatch.get(term.key, ""),
            "zero": term.points == 0,
        }
        for term in score_of(tid, ctx).terms
    ]


def _argument(tid: str, ctx: ScoreContext, items: dict[str, dict]) -> str:
    """The prose argument for a pick, naming the mechanism that produced it.

    Assembled from the ledger rather than written: the dominant term picks the
    sentence, and its own raw input fills it. That is what keeps the paragraph
    honest when the data changes — no id, count or priority word below is a
    literal, so the copy cannot go on asserting a ranking reason that stopped
    being true.
    """
    score = score_of(tid, ctx)
    by_key = score.by_key
    record = items.get(tid) or {}
    priority = _text(record.get("priority")) or "unset"
    direct = ctx.direct_of(tid)
    onward = ctx.downstream_of(tid)

    # Ties resolve to TERM_META order, which is the order the ledger prints:
    # the reader's eye lands on the first row that carries the winning number.
    order = {key: i for i, (key, _l, _c) in enumerate(TERM_META)}
    top = min(score.terms, key=lambda t: (-t.points, order[t.key]))

    if top.key == "leverage" and (direct or onward):
        wins = "It wins because it is the keystone: it directly holds %s" % _fmt_refs(
            direct
        )
        if onward:
            wins += ", and through them %s" % _fmt_refs(onward)
        wins += "."
    elif top.key == "priority":
        wins = "It wins on declared priority — %s." % priority
    elif top.key == "inflight":
        wins = "It wins because the work is already under way: it carries %s." % top.raw
    elif top.key == "epic":
        wins = "It wins because it advances a live epic — %s." % top.raw
    elif top.key == "defect":
        wins = "It wins because it is a defect, and a defect is already-declared work."
    elif top.key == "stale" and top.points:
        wins = "It wins on neglect: %s." % top.raw
    else:
        # Every term scored zero except the unknown-priority floor, which is
        # the shape a slice of untyped, unprioritised, unconnected tickets
        # takes. Say so rather than inventing a reason.
        wins = (
            "It wins by default: no term on this board separates it from the rest, "
            "so the tiebreak is its id."
        )

    parts: list[str] = []
    if top.key != "priority" and by_key["priority"].points:
        parts.append("It is %s priority, which is not why it wins." % priority)
    parts.append(wins)
    if top.key != "leverage" and (direct or onward):
        parts.append(
            "It also unblocks %s." % _fmt_refs(direct or onward)
        )
    elif not direct and not onward:
        parts.append("Nothing on this board waits on it, so finishing it frees nobody.")
    return " ".join(parts)


def _counterfactual(tid: str, ctx: ScoreContext, items: dict[str, dict]) -> dict:
    """The two-way counterfactual, both halves rendered as data.

    "If you skip it" is not decoration. A pick whose leverage is the reason it
    leads has to be able to say what stays frozen when it does not land, or the
    leverage claim is unfalsifiable from the page.
    """
    result = counterfactual(tid, ctx)
    return {
        "freed": [_ref(other, items) for other in result.freed],
        "still_held": [_ref(other, items) for other in result.still_held],
        "new_top3": [
            {**_ref(other, items), "points": points}
            for other, points in result.new_top3
        ],
    }


def _swap(tid: str, pick: str, ctx: ScoreContext) -> dict:
    """Why you would take this alternate over the pick, from the term deltas.

    The sentence is derived, never authored: whichever terms this row wins on
    are the "if", whichever it loses on are the "than". An alternate whose
    every term is worse gets told so, which is a more useful thing to read than
    a manufactured argument for it.
    """
    mine = score_of(tid, ctx).by_key
    theirs = score_of(pick, ctx).by_key

    deltas = []
    for key, label, _css in TERM_META:
        delta = mine[key].points - theirs[key].points
        if delta:
            deltas.append({"key": key, "label": label, "delta": delta})

    up = [_SWAP_CLAUSE[d["key"]] for d in deltas if d["delta"] > 0]
    down = [_SWAP_CLAUSE[d["key"]] for d in deltas if d["delta"] < 0]
    verb = "matters" if len(up) == 1 else "matter"

    if up and down:
        sentence = "Take this over #%s if %s %s more to you today than %s." % (
            pick,
            _join(up),
            verb,
            _join(down),
        )
    elif up:
        sentence = "Take this over #%s if %s is what you want today." % (
            pick,
            _join(up),
        )
    else:
        sentence = (
            "There is no term on which this beats #%s — it is here because it is "
            "next, not because a case can be made for it." % pick
        )
    return {"deltas": deltas, "sentence": sentence}


def _entry(
    tid: str,
    rank: int,
    ctx: ScoreContext,
    items: dict[str, dict],
    *,
    pick: str | None = None,
) -> dict:
    """One ranked entry — the hero at rank 1 and each alternate below it.

    Same shape either way. § 02 differs from § 01 by carrying a swap condition
    and by putting its ledger behind a disclosure; neither is a difference in
    what is computed, so neither is a difference in the view-model.
    """
    record = items.get(tid) or {}
    direct = ctx.direct_of(tid)
    onward = ctx.downstream_of(tid)
    entry = {
        "id": tid,
        "rank": rank,
        "title": _title_of(tid, items),
        "href": "/tickets/%s" % tid,
        "points": score_of(tid, ctx).total,
        "status": _text(record.get("status")) or "unset",
        # Empty for every status cortex recognises, so the ordinary board is
        # unchanged. When it fires, the hero states that its own rank-1 claim
        # rests on a word the board does not understand — the band row already
        # discloses this, but the pick is where the claim is actually made, and
        # a disclosure the operator has to scroll to find is not one.
        "status_note": _unrecognised_status_note(record),
        "priority": _text(record.get("priority")) or "unset",
        "type": _text(record.get("type")) or "unset",
        "phase": _text(record.get("phase")),
        "direct": [_ref(other, items) for other in direct],
        "downstream": [_ref(other, items) for other in onward],
        "unblocks": "%d direct / %d downstream" % (len(direct), len(onward)),
        "argument": _argument(tid, ctx, items),
        "ledger": _ledger(tid, ctx),
        # Id-stable, and stable across a re-rank: keyed on the ticket, not on
        # its position. A positional id would reopen a different ticket's
        # ledger the moment one score moved.
        "details_id": "nav-alt-%s" % tid,
        "counterfactual": _counterfactual(tid, ctx, items),
        "swap": _swap(tid, pick, ctx) if pick else None,
    }
    return entry


def _unrecognised_status_note(record: dict) -> str:
    """Name a status cortex does not know, or return the empty string.

    Unrecognised statuses are deliberately still ranked — cortex installs into
    repos that run their own vocabularies, and a board that swept ``must-have``
    into "untriaged" would be empty in such a repo. The obligation that comes
    with ranking them is to say so.
    """
    status = _text(record.get("status"))
    if not status or status.lower() in OPEN_STATUSES:
        return ""
    return "status · %s — outside cortex's vocabulary" % status


# ---------------------------------------------------------------------------
# § 03 / § 04 — the board and its census
# ---------------------------------------------------------------------------


def _band_slug(key: str) -> str:
    """A band letter as an HTML id fragment, injectively.

    Band keys are ``A``–``H`` plus a star (``E*``) and two primes (``E′``,
    ``G′``), none of which is usable in an id. The obvious transform — fold
    every non-alphanumeric to ``-`` and strip — is *not* injective over that
    set: ``E``, ``E*`` and ``E′`` all collapse to ``e``, which is a duplicate
    ``id`` on the page and therefore a live idiomorph keying bug rather than a
    cosmetic one. Each punctuation mark gets a name instead, and anything
    unforeseen gets its codepoint, so a band key that has not been invented yet
    still cannot collide with one that has.
    """
    names = {"*": "-star", "′": "-prime", "'": "-prime"}
    out = []
    for char in str(key):
        if char.isalnum():
            out.append(char.lower())
        else:
            out.append(names.get(char, "-u%x" % ord(char)))
    return "".join(out) or "x"


def _row(row: bands_mod.Row, items: dict[str, dict]) -> dict:
    """One band row, with its blockers resolved to printable references."""
    return {
        "id": row.id,
        "title": row.title,
        "href": "/tickets/%s" % row.id,
        "points": row.points,
        "rank": row.rank,
        "why": row.why,
        "status": row.status or "unset",
        "priority": row.priority or "unset",
        "type": row.type or "unset",
        "blockers": [
            {
                "id": blocker.ref,
                "title": blocker.title or "",
                "status": blocker.status or "",
                "discharged": blocker.discharged,
                "href": "/tickets/%s" % blocker.ref,
            }
            for blocker in row.blockers
        ],
    }


def _band(band: bands_mod.Band, items: dict[str, dict]) -> dict:
    """One band, ready to render. Empty bands are filtered by the caller."""
    return {
        "key": band.key,
        "slug": _band_slug(band.key),
        "label": band.label,
        "count": band.count,
        "rationale": band.rationale,
        "border_style": band.border_style,
        "show_rank": band.show_rank,
        "rows": [_row(row, items) for row in band.rows],
    }


def _census(banded: bands_mod.Bands) -> dict:
    """The legend that *is* the distribution readout.

    Replaces the stacked bar outright rather than restyling it: the counts sit
    against the glyph and border style they explain, and the accessibility
    contract that colour is never the only channel is printed in the gloss
    instead of being an unwritten rule someone has to remember.
    """
    by_key = {band.key: band for band in banded}
    groups = []
    for key, gloss, members in _CENSUS_GROUPS:
        present = [by_key[m] for m in members if m in by_key]
        count = sum(band.count for band in present)
        if not count:
            continue
        groups.append(
            {
                "key": key,
                "gloss": gloss,
                "count": count,
                "bands": [band.key for band in present if band.count],
                "border_style": present[0].border_style if present else "solid",
            }
        )

    borders = []
    for style, gloss in _BORDER_GLOSS.items():
        count = sum(band.count for band in banded if band.border_style == style)
        if count:
            borders.append({"style": style, "gloss": gloss, "count": count})

    parts = [band for band in banded if band.count]
    return {
        "groups": groups,
        "borders": borders,
        # Filled by the caller: the corpus-wide counts the retired ledger bar
        # used to carry. They are not derivable from the partition — the
        # partition only ever sees the active slice — so they travel beside it
        # rather than pretending to be one of its groups.
        "corpus": None,
        "reconciliation": {
            "parts": [{"key": band.key, "count": band.count} for band in parts],
            "sum": " + ".join(str(band.count) for band in parts),
            "total": sum(band.count for band in parts),
            "slice_total": banded.total,
            "ok": sum(band.count for band in parts) == banded.total,
        },
    }


# ---------------------------------------------------------------------------
# Surface A
# ---------------------------------------------------------------------------


def _empty_navigator(state: object) -> dict:
    """A schema-complete view-model with nothing in it.

    Every key the template touches is present and falsy. The alternative —
    letting the template guard each access — is how a surface ends up rendering
    a blank page instead of saying which of "never polled" and "empty corpus"
    it is looking at.
    """
    return {
        "available": False,
        "backend": _backend(state),
        "stale": False,
        "polled_ts": "",
        "as_of": "",
        "slice_total": 0,
        "contender_count": 0,
        "pick": None,
        "alternates": [],
        "bands": [],
        "census": {
            "groups": [],
            "borders": [],
            "reconciliation": None,
            "corpus": None,
        },
    }


def _navigator_model(state: object) -> dict:
    """Build surface A — "what should I work on next?".

    Args:
        state: The dashboard state. Only ``backlog_snapshot`` and
            ``backlog_backend`` are read.
        root: Accepted and deliberately unread — see the module docstring.

    Returns:
        A view-model whose every key is present whether or not there is a
        snapshot. ``available`` is the single flag a template branches on.
    """
    snapshot = _snapshot(state)
    if snapshot is None:
        return _empty_navigator(state)

    items, _graph, ctx, _parents = _context(snapshot)
    banded = bands_mod.partition(items, ctx, item_order=snapshot.get("item_order"))

    # The handshake bands.py asks for, and the reason § 01 can never name a
    # ticket § 03 draws as blocked. ``score.is_contender`` reads only
    # ``Graph.live``, so a record whose blocker sits outside the slice — or
    # resolves to no known ticket — passes it while the partition puts that
    # record in band G. Unwired, a high-priority ticket held by an off-slice
    # blocker becomes the hero pick above its own "NOT STARTABLE" row.
    #
    # The population is the startable bands PLUS band G′: a hold whose blocker
    # already completed is discharged, and graft G3 exists precisely because
    # those are the cheapest picks on the board, not to hide them from it.
    ctx.contender_ids = frozenset(
        row.id
        for band in banded
        if band.key in bands_mod.STARTABLE_KEYS or band.key == "G′"
        for row in band.rows
    )
    ranked = contenders(ctx)

    census = _census(banded)
    # The half of the retired ledger bar the board itself cannot see: what
    # sits outside the active slice these eleven bands describe.
    #
    # Deliberately NOT summed into a repo total. The snapshot counts active
    # files and archived files and nothing else — a ticket closed in place is
    # in neither, and on the dev corpus that is several hundred of them. Adding
    # the two would print a "the repo tracks N" that is wrong by an order of
    # magnitude, which is precisely the sort of confidently-false number this
    # surface exists to stop producing.
    counts = snapshot.get("counts") or {}
    census["corpus"] = {
        "active": int(counts.get("active") or 0),
        "archived": int(counts.get("archived") or 0),
    }

    pick = _entry(ranked[0], 1, ctx, items) if ranked else None
    alternates = [
        _entry(tid, i + 2, ctx, items, pick=ranked[0])
        for i, tid in enumerate(ranked[1 : 1 + ALTERNATE_COUNT])
    ]

    return {
        "available": True,
        "backend": _backend(state),
        "stale": bool(snapshot.get("stale")),
        "polled_ts": _text(snapshot.get("polled_ts")),
        # The corpus's own "today". Printed because the staleness term is
        # measured against it rather than against the wall clock, and a reader
        # comparing a "3 weeks untouched" row to the actual date would
        # otherwise conclude the board was wrong.
        "as_of": ctx.as_of,
        "slice_total": banded.total,
        "contender_count": len(ranked),
        "pick": pick,
        "alternates": alternates,
        # Zero-count bands are dropped here, not in the template: the
        # reconciliation above still counted them, so the arithmetic in § 04
        # closes over the same partition the board rendered.
        "bands": [_band(band, items) for band in banded if band.count],
        "census": census,
    }


# ---------------------------------------------------------------------------
# Surface B
# ---------------------------------------------------------------------------


def _preview(
    tid: str,
    ctx: ScoreContext,
    items: dict[str, dict],
    why_of: dict[str, str],
) -> dict:
    """The facts a hover card shows, resolved from data already computed.

    Deliberately carries no ticket *body*. The body is a per-request read
    (``load_ticket_body``'s docstring gives the size argument — folding bodies
    into a polled fragment would morph hundreds of KB into the DOM twice a
    minute), so hover shows the classification, which is free, and the modal
    fetches the prose, which is not. Hover therefore costs no request and
    cannot lag behind the pointer.

    ``why`` is the band's own gloss for this record — the same sentence the
    board prints under "why it sits here", so the two surfaces cannot drift
    into telling the operator different stories about one ticket.
    """
    record = items.get(tid) or {}
    on_slice = tid in items
    direct = ctx.direct_of(tid) if on_slice else ()
    onward = ctx.downstream_of(tid) if on_slice else ()
    return {
        "status": _text(record.get("status")) or "unset",
        "priority": _text(record.get("priority")) or "unset",
        "type": _text(record.get("type")) or "unset",
        "points": score_of(tid, ctx).total if on_slice else None,
        "why": why_of.get(tid, ""),
        "unblocks": "%d direct / %d downstream" % (len(direct), len(onward)),
    }


def _node(
    tid: str,
    xy: tuple[int, int],
    items: dict[str, dict],
    band_of: dict[str, str],
    *,
    external: bool = False,
    preview: dict | None = None,
) -> dict:
    """One node box: a coordinate, a link, and a label of at most two words.

    The full title travels as ``title`` for the SVG ``<title>`` child (the
    accessible name) and for the HTML table beneath the frame. It is never
    drawn as SVG text — the fonts are not bundled, Georgia is what renders,
    and a box sized to a guessed advance is the defect this rule exists to
    prevent.

    ``preview`` is the same facts again in a form the hover card reads off
    ``data-`` attributes. It is not a second source: both come from the one
    band partition this frame was built against.
    """
    key = band_of.get(tid, "")
    return {
        "id": tid,
        "x": xy[0],
        "y": xy[1],
        "title": _title_of(tid, items),
        "state": "external" if external else _NODE_STATE.get(key, "on board"),
        "border_style": "ghost" if external else _BORDER_OF_BAND.get(key, "solid"),
        "href": "/tickets/%s" % tid,
        "external": external,
        "preview": preview or {},
    }


def _frame(
    epic_id: str,
    children: list[str],
    ctx: ScoreContext,
    items: dict[str, dict],
    band_of: dict[str, str],
    layout_ctx: LayoutContext,
    why_of: dict[str, str],
) -> dict:
    """One epic frame: the geometry, plus the table that carries the names."""
    layout = layout_epic(epic_id, layout_ctx)
    external_set = set(layout.externals)

    nodes = [
        _node(
            tid,
            layout.pos[tid],
            items,
            band_of,
            external=tid in external_set,
            preview=_preview(tid, ctx, items, why_of),
        )
        for tid in sorted(layout.pos, key=_id_key)
    ]
    record = items.get(epic_id) or {}

    return {
        "id": epic_id,
        "title": _title_of(epic_id, items),
        "href": "/tickets/%s" % epic_id,
        "status": _text(record.get("status")) or "unset",
        "on_board": epic_id in items,
        "verdict": layout.verdict,
        "constrained": layout.constrained,
        "total": layout.total,
        "width": layout.width,
        "height": layout.height,
        "wrapped": layout.wrapped,
        "ncols": layout.ncols,
        "marker_id": layout.marker_id,
        # Per-epic, so two frames on one page cannot collide, and stable, so
        # the pan container's scrollLeft survives an idiomorph swap.
        "pan_id": "epic-pan-%s" % epic_id,
        "pool_box": layout.pool_box,
        # Where the enclosure's own two-word label sits. Computed here because
        # it is geometry, and because the inset it depends on is a layout
        # constant the template has no business knowing. The enclosure reserves
        # a 30px caption band above its first node row, so the label clears the
        # box edge and the nodes by well over the 8px the SVG-text rule
        # requires — it is the only string on this surface drawn as SVG text
        # that is not inside a node box, and it is inside this one.
        "pool_label": (
            {"x": layout.pool_box[0] + POOL_INSET, "y": layout.pool_box[1] + 20}
            if layout.pool_box
            else None
        ),
        "spine": layout.spine,
        "pool": layout.pool,
        "externals": layout.externals,
        "elbows": layout.elbows,
        "nodes": nodes,
        # The names, as HTML. Ordered spine-then-pool-then-external so the
        # table reads in the same order the frame does.
        "roster": [
            {
                **_ref(tid, items),
                "points": score_of(tid, ctx).total if tid in items else 0,
                "state": _NODE_STATE.get(band_of.get(tid, ""), "off board"),
                "external": tid in external_set,
                # The roster row is the same ticket as the node above it, so it
                # opens the same hover card and the same modal. Carrying the
                # payload twice keeps the two affordances from disagreeing.
                "preview": _preview(tid, ctx, items, why_of),
            }
            for tid in list(layout.spine) + list(layout.pool) + list(layout.externals)
        ],
    }


def _tail_row(
    epic_id: str,
    children: list[str],
    items: dict[str, dict],
    band_of: dict[str, str],
) -> dict:
    """One THE TAIL row — a group too small, or too off-board, for a frame.

    ``note`` states *why* it is in the tail. A group that appears here without
    saying which rule sent it looks dropped, and "never silently dropped" is
    the whole reason the tail exists.
    """
    on_board = epic_id in items
    if not on_board:
        note = "parent is not on this board"
    elif len(children) < FRAME_MIN_CHILDREN:
        note = "one child — a frame for one node states nothing"
    else:
        note = "small group"
    return {
        "id": epic_id,
        "title": _title_of(epic_id, items),
        "href": "/tickets/%s" % epic_id,
        "on_board": on_board,
        "status": _text((items.get(epic_id) or {}).get("status")) or "unset",
        "count": len(children),
        "note": note,
        "children": [
            {
                **_ref(tid, items),
                "state": _NODE_STATE.get(band_of.get(tid, ""), "off board"),
            }
            for tid in children
        ],
    }


def scope_links(model: object, suffix: str) -> object:
    """Append *suffix* to every ``href`` in a view-model, recursively.

    Applied as a final pass over the assembled model rather than threaded
    through the seven places that build a ticket URL, because the failure mode
    of threading is silent: a missed site still renders a working-looking link,
    it just points at the wrong repository's ticket. One walk cannot miss a
    site, and a new href added later is covered without anyone remembering to.

    Templates cannot do this job at all. The band, pick, frame and tail
    templates are macro libraries imported without ``with context``, so a
    page-level ``repo_query`` is Undefined inside them and renders as the empty
    string — the same wrong link, with no error anywhere.

    Every href in these models is an internal ticket or epic route, so there is
    nothing here that a repo scope would be wrong for. A no-op for the empty
    suffix, which is the single-repo case.
    """
    if not suffix:
        return model
    if isinstance(model, dict):
        return {
            key: (
                value + suffix
                if key == "href" and isinstance(value, str) and value
                else scope_links(value, suffix)
            )
            for key, value in model.items()
        }
    if isinstance(model, list):
        return [scope_links(item, suffix) for item in model]
    return model


def _empty_epic_map(state: object) -> dict:
    """A schema-complete epic view-model with nothing in it."""
    return {
        "available": False,
        "backend": _backend(state),
        "stale": False,
        "polled_ts": "",
        "frames": [],
        "tail": [],
        "frame_min": FRAME_MIN_CHILDREN,
        "group_total": 0,
        "child_total": 0,
        "declared": 0,
    }


def _epic_map_model(state: object) -> dict:
    """Build surface B — the epic map.

    Args:
        state: The dashboard state. Only ``backlog_snapshot`` and
            ``backlog_backend`` are read.
        root: Accepted and deliberately unread — see the module docstring.

    Returns:
        A view-model carrying one frame per epic with at least
        :data:`FRAME_MIN_CHILDREN` children on the board, and one tail row for
        every other group. Every group in the parent map reaches exactly one of
        the two.
    """
    snapshot = _snapshot(state)
    if snapshot is None:
        return _empty_epic_map(state)

    items, graph, ctx, parents = _context(snapshot)
    banded = bands_mod.partition(items, ctx, item_order=snapshot.get("item_order"))
    band_of = {row.id: band.key for band in banded for row in band.rows}
    # The board's own "why it sits here" sentence, keyed by ticket, so a hover
    # card on this surface repeats surface A's reason rather than inventing a
    # second one.
    why_of = {row.id: row.why for band in banded for row in band.rows}

    layout_ctx = LayoutContext(
        children=parents,
        live_edges=graph.live,
        discharged_edges=graph.discharged,
    )

    frames: list[dict] = []
    tail: list[dict] = []
    for epic_id in sorted(parents, key=_id_key):
        children = parents[epic_id]
        # A group whose container is off the slice cannot render a frame
        # header — there is no title, status or link to head it with — and the
        # design routes it to the tail with its membership stated instead of
        # drawing a frame titled after a ticket nobody can open.
        if len(children) < FRAME_MIN_CHILDREN or epic_id not in items:
            tail.append(_tail_row(epic_id, children, items, band_of))
        else:
            frames.append(
                _frame(epic_id, children, ctx, items, band_of, layout_ctx, why_of)
            )

    # Frames read largest first: the epic holding nine children is the one an
    # operator opens this page for, and burying it under a two-child frame
    # because its id sorts later is an ordering with no claim behind it.
    frames.sort(key=lambda frame: (-frame["total"], _id_key(frame["id"])))

    return {
        "available": True,
        "backend": _backend(state),
        "stale": bool(snapshot.get("stale")),
        "polled_ts": _text(snapshot.get("polled_ts")),
        "frames": frames,
        "tail": tail,
        # The frame/tail threshold, so the empty arm can state the rule it just
        # applied without the template hard-coding the number.
        "frame_min": FRAME_MIN_CHILDREN,
        "group_total": len(parents),
        "child_total": sum(len(kids) for kids in parents.values()),
        # How many groups declare any internal ordering at all. Printed once in
        # the section lede so the per-epic verdict lines do not each have to
        # carry the explanation — the defect that made the losing prototype's
        # densest copy its least informative.
        "declared": sum(1 for frame in frames if frame["constrained"]),
    }


def build_navigator(
    state: object, root: object = None, *, link_suffix: str = ""
) -> dict:
    """Surface A's view-model, with every href scoped to the caller's repo.

    ``link_suffix`` is the query string identifying which tracked repository
    this render belongs to (empty when the process serves one, which is the
    common case and leaves every URL byte-identical). Applied by
    :func:`scope_links` as a single pass over the finished model — see there
    for why this is not threaded through the builders.
    """
    return scope_links(_navigator_model(state), link_suffix)


def build_epic_map(
    state: object, root: object = None, *, link_suffix: str = ""
) -> dict:
    """Surface B's view-model, with every href scoped to the caller's repo."""
    return scope_links(_epic_map_model(state), link_suffix)
