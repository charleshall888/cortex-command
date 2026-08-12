"""Dependency graph for the backlog navigator.

Turns the raw ``blocked_by`` / ``blocks`` declarations scattered across a
backlog corpus into one deduped, classified edge list plus the closures the
navigator's ranking and epic map read. Pure data in, pure data out: nothing
here touches the filesystem, renders markup, or reads wall-clock time.

Every other navigator module reads this one, so the edge semantics are the
contract and are spelled out rather than discovered:

*Declaration is two-sided.* ``blocked_by`` on the blocked ticket and
``blocks`` on the blocker describe the same edge, and the corpus uses both
spellings — sometimes for the same pair. An edge exists if **either** side
declared it, and :attr:`Graph.declared_by` records which side(s) did. That
matters downstream: the score ledger prints *why* an edge is believed to
exist, and "only the blocker claims this" is a weaker claim than "both ends
agree".

*A declared blocker is not necessarily a live one.* Three classes, disjoint:

``discharged``
    The blocker's status is terminal. The hold lapsed and nobody updated the
    field — these tickets look unavailable and are in fact the easiest picks
    on the board, which is the single error this surface exists to prevent.
``external``
    Not discharged, and an endpoint lives outside the active slice (an
    archived blocker still in flight, or a ref that resolves to no ticket at
    all). Real, but not something the board can reason about.
``live``
    Not discharged, both endpoints on the active board. Only these propagate
    through :attr:`Graph.downstream`.

*The board is the active slice.* An edge is kept only when at least one of
its endpoints is in ``items``. Two archived tickets pointing at each other
are corpus history, not board state, and folding them in would inflate every
leverage count with work that is already finished.

*Nothing here may hang.* The corpus has no cycles today, but a cycle is one
mis-typed ``blocked_by`` away. Cycles are detected explicitly (so they can be
reported rather than inferred from a relaxation that failed to converge),
their internal edges are withheld from the wave relaxation, and the
relaxation is bounded by node count regardless.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from cortex_command.backlog.readiness import _looks_like_uuid
from cortex_command.common import TERMINAL_STATUSES, normalize_status_spelling

# Every spelling of "this reference is empty" that survives the write path.
# ``null`` is what the update verb writes for a cleared field (ADR-0027), and
# a list-valued field cleared that way can read back as the literal string
# rather than an empty list. Compared case-folded after stripping.
_NULL_REF_TOKENS = frozenset({"", "null", "none", "nil", "~", "[]", "-"})

# First run of digits anywhere in the reference. The corpus spells the same
# id four ways -- bare int ``170``, quoted ``"013"``, zero-padded ``016``, and
# occasionally decorated (``#331``) -- and all four name the same ticket.
_DIGITS_RE = re.compile(r"\d+")

# The two frontmatter fields that declare an edge, mapped to the direction
# they declare it in. Named once so the scan below cannot drift from the
# ``declared_by`` vocabulary that consumers switch on.
_BLOCKED_BY = "blocked_by"
_BLOCKS = "blocks"


def normalize_ref(ref: object) -> str | None:
    """Collapse one blocker/blocks reference to a canonical ticket id.

    ``"013"`` and ``016`` and ``13`` and ``#13`` all name the same ticket; the
    corpus contains every one of those spellings because nothing validates the
    field on write. Returns the id with leading zeros stripped, or ``None``
    when the reference is one of the null spellings.

    Two decisions worth knowing about, because "digits anywhere win" is not
    the whole rule:

    * **A UUID is returned verbatim, never digit-extracted.** Backlog items
      carry UUIDs and a stale ref can name one; extracting the first digit run
      from ``b734b65c-7f1a-...`` would silently resolve it to ticket #734.
      Returned intact, it resolves to nothing and lands in
      :attr:`Graph.unresolvable`, which is the honest outcome.
    * **A digit-free reference is returned verbatim, not dropped.** Work
      tracked outside this backlog is named by string; forgetting it here
      would make it vanish from the board rather than render as external.

    ``bool`` is rejected explicitly: it is an ``int`` subclass, so ``True``
    would otherwise normalize to ticket #1.
    """
    if ref is None or isinstance(ref, bool):
        return None

    text = str(ref).strip()
    if text.casefold() in _NULL_REF_TOKENS:
        return None

    if _looks_like_uuid(text):
        return text

    match = _DIGITS_RE.search(text)
    if match:
        # int() drops the leading zeros of the zero-padded spellings without
        # assuming the whole string is numeric.
        return str(int(match.group()))

    return text


def _sort_key(ref: str) -> tuple[int, int, str]:
    """Order ids numerically where possible, lexically where not.

    Ticket ids are numeric strings, but this module deliberately admits
    non-numeric refs (UUIDs, externally-tracked names), and ``sorted(...,
    key=int)`` would raise on the first one. Numerics sort ahead of the rest so
    the common case reads as plain ascending ids.
    """
    if ref.isdigit():
        return (0, int(ref), "")
    return (1, 0, ref)


@dataclass(frozen=True)
class Graph:
    """The navigator's dependency picture over one active slice.

    Frozen so a consumer cannot rebind a field and hand a half-mutated graph
    to the next module; the collections themselves are ordinary and are not
    defensively copied.

    Attributes:
        edges: Deduped ``(blocker, blocked)`` pairs, ascending. Every edge has
            at least one endpoint in the active slice.
        declared_by: Edge → ``"blocked_by"`` | ``"blocks"`` | ``"both"``.
        live: Edges that actually constrain the board — blocker non-terminal,
            both endpoints in the active slice.
        discharged: Edges whose blocker has already reached a terminal status.
            Classified *before* ``external``, so a completed archived blocker
            reads as a lapsed hold rather than as off-board noise; that
            ordering is what makes the HOLD LAPSED partition findable.
        external: Everything else — a non-terminal blocker outside the slice,
            a blocked side outside the slice, or a ref naming no known ticket.
        downstream: Slice id → every id reachable from it over live edges.
        direct: Slice id → its immediate live dependents. Both maps carry an
            entry for every slice id, empty set included, so consumers can
            subscript rather than ``.get``.
        blocked_by_titles: Blocked slice id → one ``{ref, title, status,
            kind}`` per incoming edge, ascending by ref. Only ids that have an
            incoming edge appear. ``kind`` is the edge's class, except that a
            ref resolving to no known ticket reads ``"unresolvable"`` — a more
            useful thing to render than the ``"external"`` bucket it also
            falls into.
        unresolvable: Edges with an endpoint that names no ticket in either
            the slice or the corpus. A subset of ``external``, reported
            separately because it is a data defect rather than a boundary.
        cycles: Node lists, one per dependency cycle over live edges (a
            self-block counts). Empty on a healthy corpus.
        hold_lapsed: Slice ids whose every incoming edge is discharged — the
            tickets that are startable and do not know it. Derived here rather
            than in the band partition because this is the only module that
            knows an edge's class; a consumer re-deriving it from ``live`` and
            ``discharged`` alone would have to reconstruct the per-id grouping
            that ``blocked_by_titles`` already carries.
    """

    edges: list[tuple[str, str]]
    declared_by: dict[tuple[str, str], str]
    live: list[tuple[str, str]]
    discharged: list[tuple[str, str]]
    external: list[tuple[str, str]]
    downstream: dict[str, set[str]]
    direct: dict[str, set[str]]
    blocked_by_titles: dict[str, list[dict]]
    unresolvable: list[tuple[str, str]]
    cycles: list[list[str]]
    hold_lapsed: list[str]


def _record_id(record: dict, fallback: object = None) -> str | None:
    """Return *record*'s canonical id, preferring its own ``id`` field.

    The snapshot keys ``items`` by a stringified id already, but the corpus
    records carry theirs as an int and archived stubs carry only the id, so
    both paths route through the same normalizer.
    """
    return normalize_ref(record.get("id", fallback))


def _refs(record: dict, field: str) -> list[str]:
    """Return *record*'s normalized references from one declaration field.

    A bare scalar is accepted as a one-element list: the legacy
    ``blocked-by: 411`` spelling is still in the corpus and the index parser
    passes it through unchanged when it did not come from an inline list.
    Null-ish references drop out here and never reach the edge set.
    """
    raw = record.get(field)
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    return [ref for ref in (normalize_ref(item) for item in raw) if ref]


def _find_cycles(
    adjacency: dict[str, set[str]], nodes: list[str]
) -> list[list[str]]:
    """Return the dependency cycles in *adjacency*.

    Tarjan's strongly-connected-components, written iteratively because the
    recursive form blows the stack on a long enough chain and this runs over
    whatever a consumer repo's corpus happens to contain.

    A component is a cycle when it holds more than one node, or when a single
    node blocks itself.

    This used to also return a node → cycle index, for a wave relaxation that
    withheld the edges inside a cycle. That relaxation and the ``waves`` map it
    produced had no consumer and are gone; the reachability closure beneath is
    cycle-safe on its own. What survives is the cycle list itself, which the
    census now prints — a cycle is a corpus defect, and detecting one and
    discarding it was the one outcome worse than not looking.
    """
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []
    counter = 0

    def successors_of(node: str) -> Iterator[str]:
        # Sorted so the reported cycle membership is stable across runs; the
        # 30s poll re-renders this and an unstable order would churn the DOM.
        return iter(sorted(adjacency.get(node, ()), key=_sort_key))

    for root in nodes:
        if root in index:
            continue
        index[root] = lowlink[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[str, Iterator[str]]] = [(root, successors_of(root))]

        while work:
            node, successors = work[-1]
            descended = False
            for nxt in successors:
                if nxt not in index:
                    index[nxt] = lowlink[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, successors_of(nxt)))
                    descended = True
                    break
                if nxt in on_stack:
                    lowlink[node] = min(lowlink[node], index[nxt])
            if descended:
                continue

            work.pop()
            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.append(popped)
                    if popped == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, ()):
                    cycles.append(sorted(component, key=_sort_key))
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    cycles.sort(key=lambda component: _sort_key(component[0]))
    return cycles


def _closure(
    adjacency: dict[str, set[str]], nodes: list[str]
) -> dict[str, set[str]]:
    """Return every node reachable from each of *nodes* over *adjacency*.

    Breadth-first with a per-source visited set, which makes it cycle-safe
    without needing the cycle report: a node already seen is never expanded
    twice, so a cycle terminates on its second visit.

    The source is excluded from its own reachable set even when a cycle makes
    it reachable — leverage counts what a ticket unblocks *other than itself*.
    """
    reach: dict[str, set[str]] = {}
    for source in nodes:
        seen: set[str] = set()
        frontier = list(adjacency.get(source, ()))
        while frontier:
            current = frontier.pop()
            if current in seen or current == source:
                continue
            seen.add(current)
            frontier.extend(adjacency.get(current, ()))
        reach[source] = seen
    return reach


def build_graph(items: dict[str, dict], corpus: list[dict]) -> Graph:
    """Build the navigator's dependency graph over one active slice.

    Args:
        items: The active slice, id-keyed — the snapshot's ``items`` map. This
            is the board: slice membership is what separates a live edge from
            an external one.
        corpus: Every record the repo knows about, active and terminal and
            archived-stub alike, as a flat list. Used only to resolve a
            reference's status and title; a blocker that lives here and not in
            *items* is off-board by definition. Passing an empty list is legal
            and degrades every off-board ref to unresolvable.

    Returns:
        A schema-complete :class:`Graph`. Empty inputs yield empty
        collections, never ``None`` and never a partial structure.
    """
    # ---- Index the two populations -------------------------------------
    # Slice first, then corpus underneath it: the two describe the same
    # tickets, but the slice records are the ones the board renders and a
    # disagreement should resolve in their favour.
    slice_records: dict[str, dict] = {}
    for key, record in items.items():
        item_id = _record_id(record, key) or normalize_ref(key)
        if item_id:
            slice_records[item_id] = record

    known_records: dict[str, dict] = {}
    for record in corpus:
        record_id = _record_id(record)
        if record_id and record_id not in known_records:
            known_records[record_id] = record
    known_records.update(slice_records)

    def status_of(ref: str) -> str | None:
        record = known_records.get(ref)
        if record is None:
            return None
        return normalize_status_spelling(record.get("status")) or None

    def title_of(ref: str) -> str | None:
        record = known_records.get(ref)
        if record is None:
            return None
        title = record.get("title")
        return str(title) if title else None

    # ---- Collect declarations from both sides --------------------------
    # Scanning the corpus as well as the slice is what makes "either side
    # declared it" true in the direction that matters most: a completed
    # blocker whose own `blocks` list still names an active ticket would
    # otherwise be invisible, because the active ticket never mentioned it.
    declared: dict[tuple[str, str], set[str]] = {}
    scanned: set[int] = set()
    for record in list(slice_records.values()) + list(corpus):
        # Slice and corpus overlap; scanning one record twice would be
        # harmless (the sets dedupe) but wasteful on a 500-file corpus.
        if id(record) in scanned:
            continue
        scanned.add(id(record))

        record_id = _record_id(record)
        if not record_id:
            continue
        for ref in _refs(record, _BLOCKED_BY):
            declared.setdefault((ref, record_id), set()).add(_BLOCKED_BY)
        for ref in _refs(record, _BLOCKS):
            declared.setdefault((record_id, ref), set()).add(_BLOCKS)

    # ---- Restrict to the board and classify ----------------------------
    edges: list[tuple[str, str]] = sorted(
        (
            edge
            for edge in declared
            if edge[0] in slice_records or edge[1] in slice_records
        ),
        key=lambda edge: (_sort_key(edge[0]), _sort_key(edge[1])),
    )

    declared_by: dict[tuple[str, str], str] = {}
    live: list[tuple[str, str]] = []
    discharged: list[tuple[str, str]] = []
    external: list[tuple[str, str]] = []
    unresolvable: list[tuple[str, str]] = []
    edge_kind: dict[tuple[str, str], str] = {}

    for edge in edges:
        sides = declared[edge]
        declared_by[edge] = "both" if len(sides) > 1 else next(iter(sides))

        blocker, blocked = edge
        if blocker not in known_records or blocked not in known_records:
            unresolvable.append(edge)

        blocker_status = status_of(blocker)
        if blocker_status is not None and blocker_status in TERMINAL_STATUSES:
            # Terminal beats off-board: an archived *complete* blocker is a
            # lapsed hold, which is actionable, and calling it external would
            # bury it with the refs nobody can do anything about.
            discharged.append(edge)
            kind = "discharged"
        elif blocker not in slice_records or blocked not in slice_records:
            external.append(edge)
            kind = "external"
        else:
            live.append(edge)
            kind = "live"
        edge_kind[edge] = kind

    # ---- Closures over live edges only ---------------------------------
    forward: dict[str, set[str]] = {}
    for blocker, blocked in live:
        forward.setdefault(blocker, set()).add(blocked)

    slice_ids = sorted(slice_records, key=_sort_key)
    cycles = _find_cycles(forward, slice_ids)

    direct: dict[str, set[str]] = {
        tid: set(forward.get(tid, ())) for tid in slice_ids
    }
    downstream = _closure(forward, slice_ids)

    # ---- Per-ticket blocker rows ---------------------------------------
    # Keyed on the blocked side and restricted to the slice: this feeds the
    # board row that must name its blocker's id *and* title, and an off-board
    # blocked ticket has no row to render into. Titles resolve against the
    # whole corpus, which is what lets a terminal blocker print its title
    # instead of the bare "#id (complete)" fallback the old board showed.
    blocked_by_titles: dict[str, list[dict]] = {}
    for blocker, blocked in edges:
        if blocked not in slice_records:
            continue
        kind = edge_kind[(blocker, blocked)]
        if blocker not in known_records:
            kind = "unresolvable"
        blocked_by_titles.setdefault(blocked, []).append({
            "ref": blocker,
            "title": title_of(blocker),
            "status": status_of(blocker),
            "kind": kind,
        })
    for rows in blocked_by_titles.values():
        rows.sort(key=lambda row: _sort_key(row["ref"]))

    # A hold has lapsed only when *every* declared blocker is discharged. One
    # surviving live or external blocker still holds the ticket, and shipping
    # it as startable would be the same error in the opposite direction.
    hold_lapsed = sorted(
        (
            blocked
            for blocked, rows in blocked_by_titles.items()
            if rows and all(row["kind"] == "discharged" for row in rows)
        ),
        key=_sort_key,
    )

    return Graph(
        edges=edges,
        declared_by=declared_by,
        live=live,
        discharged=discharged,
        external=external,
        downstream=downstream,
        direct=direct,
        blocked_by_titles=blocked_by_titles,
        unresolvable=unresolvable,
        cycles=cycles,
        hold_lapsed=hold_lapsed,
    )
