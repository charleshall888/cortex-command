"""Shared dataclasses for the Docs view.

This is the contract between ``corpus`` (producer), ``layout`` and ``render``
(consumers) and the templates (which read fields, never compute). Keep it
free of I/O and of imports from the sibling modules.

Node kinds, in index order (the order ``Corpus.ordered()`` returns):

    constitution   CLAUDE.md
    policy         docs/policies.md
    root           cortex/requirements/project.md
    config         cortex/lifecycle.config.md
    readme         cortex/README.md
    area           cortex/requirements/<area>.md (any file that is not
                   project.md or glossary.md), in Conditional Loading row
                   order, then any unmapped ones alphabetically
    glossary       cortex/requirements/glossary.md
    adr            cortex/adr/NNNN-*.md by number
    doc            any other docs/*.md a governing doc cites — a greyed
                   neighbour, never listed on its own

Edge kinds:

    parent      child → parent, from a ``**Parent doc**:`` line
    maps-area   project.md → area doc, from a ``## Conditional Loading`` row
                (``keys`` carries the area keys of that row)
    global      project.md → doc, from a ``## Global Context`` bullet
    supersedes  newer ADR → older ADR, from the older one's ``superseded_by``
    cites       any doc → any doc, from ``ADR-NNNN`` / ``→ ADR-NNNN`` tokens,
                markdown links to a .md file, and bare repo-relative paths in
                backticks. One edge per (src, dst) with ``count`` mentions.
                Self-cites are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

NODE_KINDS = (
    "constitution", "policy", "root", "config", "readme",
    "area", "glossary", "adr", "doc",
)
EDGE_KINDS = ("parent", "maps-area", "global", "supersedes", "cites")
ADR_STATUSES = ("proposed", "accepted", "deprecated", "superseded")


@dataclass(frozen=True)
class DocNode:
    path: str                      # repo-relative posix path; the identity
    kind: str                      # one of NODE_KINDS
    title: str                     # first H1 with any ``ADR-NNNN:`` / ``NNNN —`` prefix stripped; filename stem if none
    governing: bool                # False only for kind == "doc" and for ghosts
    exists: bool = True            # False for a ghost: a target some edge names that is not on disk
    adr_number: int | None = None
    status: str | None = None      # ADR frontmatter status, lowercased, or None
    superseded_by: str | None = None   # resolved path of the successor, or None
    parent: str | None = None      # resolved path from the Parent doc line, or None
    last_gathered: str | None = None   # first ISO date in a ``> Last gathered:`` line, or None
    decision_date: str | None = None   # ADR ``_Decision date: YYYY-MM-DD`` if present
    origin_ticket: str | None = None   # ``#NNN`` from the decision-date line if present
    map_keys: tuple[str, ...] = ()     # area keys whose Conditional Loading row maps here
    summary: str = ""              # first body paragraph, plain text, clipped to ~180 chars
    bytes: int = 0
    mtime: float = 0.0
    headings: tuple[str, ...] = () # H2 texts in order

    @property
    def short(self) -> str:
        """The compact label a map node or chip shows: ``ADR-0012`` or the filename."""
        if self.adr_number is not None:
            return f"ADR-{self.adr_number:04d}"
        parts = self.path.rsplit("/", 2)
        # A bare ``README.md`` names nothing: two of them exist here
        # (``cortex/README.md``, ``cortex/adr/README.md``), so the label
        # carries its directory.
        if parts[-1].lower() == "readme.md" and len(parts) > 1:
            return "/".join(parts[-2:])
        return parts[-1]

    @property
    def href(self) -> str:
        return f"/docs/{self.path}"


@dataclass(frozen=True)
class DocEdge:
    src: str
    dst: str
    kind: str                      # one of EDGE_KINDS
    count: int = 1                 # mentions folded into this edge (cites only)
    keys: tuple[str, ...] = ()     # maps-area only
    section: str | None = None     # H2 heading the first mention sits under, if known
    dangling: bool = False         # dst names no file on disk


@dataclass
class Corpus:
    root: Path
    nodes: dict[str, DocNode] = field(default_factory=dict)
    edges: list[DocEdge] = field(default_factory=list)

    # ---- lookups the consumers rely on -----------------------------------
    def get(self, path: str) -> DocNode | None:
        return self.nodes.get(path)

    def by_adr(self, number: int) -> DocNode | None:
        for n in self.nodes.values():
            if n.adr_number == number and n.exists:
                return n
        return None

    def governing(self) -> list[DocNode]:
        return [n for n in self.ordered() if n.governing and n.exists]

    def ordered(self) -> list[DocNode]:
        """Every node in index order (see module docstring)."""
        rank = {k: i for i, k in enumerate(NODE_KINDS)}
        mapped = self.map_order()
        def key(n: DocNode):
            if n.kind == "area":
                pos = mapped.index(n.path) if n.path in mapped else len(mapped)
                return (rank["area"], pos, n.path)
            if n.kind == "adr":
                return (rank["adr"], n.adr_number or 0, n.path)
            return (rank.get(n.kind, 99), 0, n.path)
        return sorted(self.nodes.values(), key=key)

    def map_order(self) -> list[str]:
        """Area-doc paths in Conditional Loading row order (first appearance)."""
        seen: list[str] = []
        for e in self.edges:
            if e.kind == "maps-area" and e.dst not in seen:
                seen.append(e.dst)
        return seen

    def out_edges(self, path: str, kinds: tuple[str, ...] | None = None) -> list[DocEdge]:
        return [e for e in self.edges if e.src == path and (kinds is None or e.kind in kinds)]

    def in_edges(self, path: str, kinds: tuple[str, ...] | None = None) -> list[DocEdge]:
        return [e for e in self.edges if e.dst == path and (kinds is None or e.kind in kinds)]

    def children(self, path: str) -> list[DocNode]:
        """Docs whose parent line or map row points at *path*, deduped, index order."""
        found = {e.src for e in self.in_edges(path, ("parent",))}
        found |= {e.dst for e in self.out_edges(path, ("maps-area", "global"))}
        return [n for n in self.ordered() if n.path in found and n.path != path]

    def neighbours(self, path: str) -> set[str]:
        """Every node within one hop of *path*, either direction, any edge kind."""
        out = {e.dst for e in self.out_edges(path)} | {e.src for e in self.in_edges(path)}
        out.discard(path)
        return out


# ---------------------------------------------------------------------------
# Map geometry. Produced by ``layout``, drawn verbatim by _doc_map.svg.html.
# Every coordinate is an int. The template does no arithmetic.
# ---------------------------------------------------------------------------

#: Node box size, shared by the ladder and the neighbourhood strip.
MAP_NW, MAP_NH = 220, 56


@dataclass(frozen=True)
class MapNode:
    path: str
    x: int
    y: int
    short: str                     # ``ADR-0012`` / ``project.md``
    title: str
    kind: str                      # node kind, drives border colour
    status: str | None             # ADR status, drives border style; None otherwise
    state: str                     # small-caps word at the right of the head: kind for docs, status for ADRs, ``missing`` for ghosts
    href: str
    focus: str                     # ``here`` | ``in`` | ``out`` | ``both`` | ``far`` | ``none`` (no focus set)
    in_count: int
    out_count: int
    ghost: bool = False


@dataclass(frozen=True)
class MapEdge:
    src: str
    dst: str
    kind: str                      # edge kind, drives stroke
    d: str                         # SVG path data
    focus: str                     # ``in`` | ``out`` | ``far`` | ``none``


@dataclass(frozen=True)
class MapLabel:
    x: int
    y: int
    text: str
    role: str                      # ``column`` | ``shelf`` | ``pool`` | ``more``
    href: str | None = None        # ``more`` labels link to the expanded view


@dataclass(frozen=True)
class MapBox:
    x: int
    y: int
    w: int
    h: int
    role: str                      # ``pool``


@dataclass
class MapLayout:
    width: int
    height: int
    nodes: list[MapNode] = field(default_factory=list)
    edges: list[MapEdge] = field(default_factory=list)
    labels: list[MapLabel] = field(default_factory=list)
    boxes: list[MapBox] = field(default_factory=list)
    marker_id: str = "arw-docs"
    verdict: str = ""              # one sentence above the frame, always set
    drawn: int = 0                 # nodes drawn
    total: int = 0                 # governing nodes in the corpus
    empty: bool = False            # True when there is nothing worth drawing; verdict says why
