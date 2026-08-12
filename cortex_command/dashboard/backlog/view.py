"""View-models for the backlog navigator.

This is the only module in the package that knows what a *section* is. The four
helpers beneath it answer separate questions — what depends on what
(:mod:`.graph`), what is it worth (:mod:`.score`), where does it sit
(:mod:`.bands`) — and none of them knows that the answers get arranged into
"§ 01 THE PICK" and "§ 03 THE FIELD".
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
pointing off it. ``root`` is therefore accepted (the route resolves it anyway,
and this builder sits beside the ``data.py`` builders that do take it) and
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

# The eleven bands, grouped into the dispositions an operator distinguishes
# when they ask "what is on this board". One constant, read twice: § 03 splits
# the field table on it and § 06 counts the census against it, so the two
# cannot disagree about which records are startable.
#
# Band G′ sits inside "startable today" and not in a group of its own. A hold
# whose blocker already completed IS startable — that is the entire finding the
# band exists to report — and giving it a separate census line is what made
# § 01 print "51 startable" over a census reading 49, with nothing on the page
# reconciling them. The lapsed nuance survives where it belongs: on the row,
# in the band letter and its "why" sentence.
_FIELD_SEGMENTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("startable", "startable today", ("A", "B", "C", "D", "E", "E*", "G′")),
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


def _offslice_of(snapshot: dict) -> dict[str, dict]:
    """The snapshot's corpus resolution for ids the board points at but lacks.

    Absent on a snapshot written before the key existed, which is a live case:
    the poller retains the last good snapshot across a failed poll, so a
    process can serve one shape while running the code for another. An empty
    map degrades to the old placeholder rather than raising.
    """
    raw = snapshot.get("offslice") or {}
    return {
        str(key): value for key, value in raw.items() if isinstance(value, dict)
    }


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


def _title_of(tid: str, items: dict[str, dict], offslice: dict | None = None) -> str:
    """A ticket's title, from the board or from the corpus behind it.

    The fallback used to be the literal "not on this board", and that was the
    wrong sentence for the population that actually reaches it. Nearly every
    off-board reference on these surfaces is a **completed** ticket — a
    blocker whose closing is precisely what discharged the hold being drawn.
    Telling the operator it is not on the board describes the board rather
    than the ticket, and reads like a lookup that failed.

    ``offslice`` carries the snapshot's corpus resolution for exactly these
    ids. When it names one, the real title is used and the caller states the
    disposition separately (see :func:`_state_of`); the placeholder survives
    only for a reference the corpus cannot name at all, where it is true.

    Never the empty string: every place this feeds is a link's accessible name
    or a sentence, and a blank there reads as a rendering failure rather than
    as missing data.
    """
    record = items.get(tid)
    if record is not None:
        return _text(record.get("title")) or "untitled"
    known = (offslice or {}).get(tid)
    if known:
        return _text(known.get("title")) or "untitled"
    return "names no known ticket"


def _offslice_state(tid: str, offslice: dict | None) -> str:
    """The one- or two-word disposition of an id that is not on the board.

    Fits the SVG-text rule's label budget, so a node box can carry it, and it
    is the ticket's own status rather than a statement about the board. A
    corpus status is a single word for every spelling cortex writes; an
    unrecognised one is passed through rather than bucketed, because consumer
    repos run their own vocabularies.
    """
    known = (offslice or {}).get(tid) or {}
    return _text(known.get("status")) or "off board"


def _ref(tid: str, items: dict[str, dict], offslice: dict | None = None) -> dict:
    """One id as every cross-reference on these surfaces renders it."""
    return {
        "id": tid,
        "title": _title_of(tid, items, offslice),
        "href": "/tickets/%s" % tid,
    }


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
    # Only the branch that ADDS ids. The "frees nobody" arm used to fire here
    # too, forty pixels above a counterfactual whose whole job is to say what
    # changes — "Nothing on this board waits on it, so finishing it frees
    # nobody." sitting directly over "nothing becomes startable — no ticket on
    # this board names it as its only live blocker." The counterfactual keeps
    # it, because that is the section a reader goes to for the consequence.
    if top.key != "leverage" and (direct or onward):
        parts.append("It also unblocks %s." % _fmt_refs(direct or onward))
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


def _row(
    row: bands_mod.Row,
    items: dict[str, dict],
    band_key: str = "",
    show_why: bool = True,
) -> dict:
    """One field row, with its blockers resolved to printable references.

    ``band`` and ``epic`` are columns rather than section headers. § 03 was ten
    separate tables, each with its own head and its own ``<thead>``; the band
    is one letter and repeating it down a column costs less than nine extra
    table heads, and it leaves the reader one scan direction instead of ten.
    """
    parent = normalize_ref((items.get(row.id) or {}).get("parent"))
    return {
        "id": row.id,
        "title": row.title,
        "href": "/tickets/%s" % row.id,
        "points": row.points,
        "rank": row.rank,
        # Blanked where the band label IS the reason. Under MEDIUM · STARTABLE
        # a per-row "medium · chore" restated the run heading and called it a
        # reason; band F's rows each repeated the band's own rationale verbatim.
        # The band is a column now, so the suppression has to travel per row —
        # a single run mixes bands that explain themselves with bands that do
        # not, and printing the run's widest answer for all of them is how the
        # restatement came back.
        "why": row.why if show_why else "",
        "band": band_key,
        # The parent id only. The title lives once, in § 05, because a title
        # repeated on each of nine children is the duplication the two-page
        # split was made of.
        "epic": parent or "",
        "epic_href": "/tickets/%s" % parent if parent else "",
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


def _field(banded: bands_mod.Bands, items: dict[str, dict]) -> list[dict]:
    """§ 03 THE FIELD — every record, one table, split into disposition runs.

    This replaced ten band blocks, each a header plus its own ``<table>`` with
    its own ``<thead>``. The bands are not gone: the band letter is a column
    and the ordering within a run is still the partition's. What is gone is
    nine table heads, nine repeated column rows and ten section headers, for a
    reader who now learns one row grammar instead of scanning ten.

    The per-band rationale moves to the § 06 legend, printed once each, which
    is where a legend belongs — it was never a property of the rows beneath it.
    """
    by_key = {band.key: band for band in banded if band.count}
    segments = []
    for key, label, members in _FIELD_SEGMENTS:
        present = [by_key[m] for m in members if m in by_key]
        if not present:
            continue
        segments.append(
            {
                "key": key,
                "label": label,
                "slug": "nav-seg-%s" % key,
                "count": sum(band.count for band in present),
                "border_style": present[0].border_style,
                # Any band in the run wanting a rank column gives the whole run
                # one: a column that appears and disappears mid-table is a
                # different table, and the reader is promised one grammar. The
                # "why" is the opposite case and is decided per row — see
                # :func:`_row`.
                "show_rank": any(band.show_rank for band in present),
                "rows": [
                    _row(row, items, band_key=band.key, show_why=band.show_why)
                    for band in present
                    for row in band.rows
                ],
            }
        )
    return segments


def _census(banded: bands_mod.Bands) -> dict:
    """The legend that *is* the distribution readout.

    Replaces the stacked bar outright rather than restyling it: the counts sit
    against the glyph and border style they explain, and the accessibility
    contract that colour is never the only channel is printed in the gloss
    instead of being an unwritten rule someone has to remember.
    """
    by_key = {band.key: band for band in banded}
    groups = []
    for key, gloss, members in _FIELD_SEGMENTS:
        present = [by_key[m] for m in members if m in by_key]
        count = sum(band.count for band in present)
        if not count:
            continue
        groups.append(
            {
                "key": key,
                "gloss": gloss,
                "count": count,
                # The letters jump to the run they name in § 03.
                "slug": "nav-seg-%s" % key,
                "bands": [
                    {"key": band.key, "slug": _band_slug(band.key)}
                    for band in present
                    if band.count
                ],
                "border_style": present[0].border_style if present else "solid",
            }
        )

    # What each band letter claims. This is the copy that used to head each of
    # the ten band blocks in § 03; the letters now live in a column there, and
    # a rationale repeated above every table was a legend pretending to be a
    # section heading. Printed once each, only for bands that have rows.
    legend = [
        {
            "key": band.key,
            "label": band.label,
            "rationale": band.rationale,
            "count": band.count,
            "border_style": band.border_style,
        }
        for band in banded
        if band.count
    ]

    borders = []
    for style, gloss in _BORDER_GLOSS.items():
        count = sum(band.count for band in banded if band.border_style == style)
        if count:
            borders.append({"style": style, "gloss": gloss, "count": count})

    parts = [band for band in banded if band.count]
    return {
        "groups": groups,
        "legend": legend,
        "borders": borders,
        # Filled by the caller: the corpus-wide counts the retired ledger bar
        # used to carry. They are not derivable from the partition — the
        # partition only ever sees the active slice — so they travel beside it
        # rather than pretending to be one of its groups.
        "corpus": None,
        "reconciliation": {
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
        "field": [],
        "groups": [],
        "group_children": 0,
        "ordered_groups": 0,
        "census": {
            "groups": [],
            "legend": [],
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

    items, graph, ctx, parents = _context(snapshot)
    offslice = _offslice_of(snapshot)
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

    # § 05. Every group the parent map knows, largest first: the epic holding
    # nine children is the one a reader came for, and burying it under a
    # two-child group because its id sorts earlier is an ordering with no claim
    # behind it. Groups whose container is off the slice are included rather
    # than routed to a separate table — see :func:`_group`.
    band_of = {row.id: band.key for band in banded for row in band.rows}
    groups = [
        _group(epic_id, parents[epic_id], items, band_of, offslice, graph.live)
        for epic_id in sorted(parents, key=_id_key)
    ]
    groups.sort(key=lambda group: (-group["count"], _id_key(group["id"])))

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
        # Zero-count bands are dropped inside _field, not in the template: the
        # reconciliation still counted them, so the arithmetic in § 06 closes
        # over the same partition the field rendered.
        "field": _field(banded, items),
        "groups": groups,
        "group_children": sum(group["count"] for group in groups),
        # How many groups declare any internal ordering at all. Printed once in
        # the section lede so no group has to carry the explanation itself.
        "ordered_groups": sum(1 for group in groups if group["order"]),
        "census": census,
    }


# ---------------------------------------------------------------------------
# § 05 EPIC GROUPS
# ---------------------------------------------------------------------------

# Band letter → the one- or two-word state a child chip carries. A *label*
# rather than a truncated title: a shortened title would be a width guess
# against an unbundled font. Full titles are in the field table above.
_CHILD_STATE = {
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

# Band letter → border style, so a child chip carries the same channel the
# same record carries in its field row. Mirrors ``bands._BAND_META`` by key
# rather than importing the tuple, because a chip needs a *default* for an id
# the partition never saw (a child off the slice) and a lookup with a default
# is the honest expression of that.
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


def _group_order(children: list[str], live: list[tuple[str, str]]) -> list[dict]:
    """Intra-group ordering as printable ``blocker → blocked`` statements.

    This replaced a per-epic SVG frame that solved longest-path waves, routed
    right-angled elbows through reserved lanes and namespaced an arrowhead
    marker per epic. What it drew, on the whole dev slice, was two arrows: ten
    of eleven groups declare no intra-group edge at all, so ten frames were a
    dashed box round an unordered list. Two relations are a sentence.

    Grouped by blocker rather than emitted per edge, so one ticket holding two
    siblings reads ``#242 → #388, #417`` and not as two near-identical lines.
    """
    member = set(children)
    holds: dict[str, list[str]] = {}
    for blocker, blocked in live:
        if blocker in member and blocked in member:
            holds.setdefault(blocker, []).append(blocked)
    return [
        {
            "blocker": blocker,
            "blocked": sorted(holds[blocker], key=_id_key),
        }
        for blocker in sorted(holds, key=_id_key)
    ]


def _group(
    epic_id: str,
    children: list[str],
    items: dict[str, dict],
    band_of: dict[str, str],
    offslice: dict | None,
    live: list[tuple[str, str]],
) -> dict:
    """One epic group: who it is, what is in it, and any declared order.

    Renders whether or not the container is on the board. A group whose parent
    sits off the slice used to be routed to a separate tail table with a
    different state vocabulary, which is how the same off-slice ticket came to
    read ``complete`` in a frame and ``off board`` in the tail. One builder,
    one vocabulary, no drift.
    """
    on_board = epic_id in items
    return {
        "id": epic_id,
        "title": _title_of(epic_id, items, offslice),
        "href": "/tickets/%s" % epic_id,
        "on_board": on_board,
        "status": (
            _text(items[epic_id].get("status")) or "unset"
            if on_board
            else _offslice_state(epic_id, offslice)
        ),
        "count": len(children),
        "children": [
            {
                "id": tid,
                "title": _title_of(tid, items, offslice),
                "href": "/tickets/%s" % tid,
                "state": (
                    _CHILD_STATE.get(band_of[tid], "ready")
                    if tid in band_of
                    else _offslice_state(tid, offslice)
                ),
                "border_style": _BORDER_OF_BAND.get(band_of.get(tid, ""), "ghost"),
            }
            for tid in sorted(children, key=_id_key)
        ],
        "order": _group_order(children, live),
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
