"""Build the governing-document corpus for the Docs view.

Pure except for reading files under ``root``. Nothing here caches, polls,
or writes. The graph shape and edge forms follow ``model.py``'s docstring;
the parsers are borrowed from the modules that already own each format
(requirements map rows, ADR references, backlog frontmatter) so this module
never grows a second reading of a convention.

Three public entry points:

- :func:`build_corpus` — the whole graph for one repo root.
- :func:`load_doc_text` — the body of one corpus node, for the reader.
- :func:`backlinks` — who mentions a node: governing docs (from the corpus
  edges), backlog tickets and lifecycle artifacts (scanned on demand).
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from cortex_command.adr_citation_audit import _extract_references
from cortex_command.backlog.generate_index import _parse_frontmatter
from cortex_command.dashboard.data import read_text_lossy
from cortex_command.dashboard.docs.model import (
    EDGE_KINDS,
    Corpus,
    DocEdge,
    DocNode,
)
from cortex_command.dashboard.docs.render import first_paragraph
from cortex_command.lifecycle.load_requirements_cli import (
    _parse_conditional_loading,
    _parse_global_context,
    _split_keys,
)

# ---------------------------------------------------------------------------
# The governing set
# ---------------------------------------------------------------------------

CONSTITUTION = "CLAUDE.md"
POLICY = "docs/policies.md"
ROOT_DOC = "cortex/requirements/project.md"
CONFIG = "cortex/lifecycle.config.md"
README = "cortex/README.md"
GLOSSARY = "cortex/requirements/glossary.md"
ADR_README = "cortex/adr/README.md"
REQUIREMENTS_DIR = "cortex/requirements"
ADR_DIR = "cortex/adr"

_FIXED_KINDS = {
    CONSTITUTION: "constitution",
    POLICY: "policy",
    ROOT_DOC: "root",
    CONFIG: "config",
    README: "readme",
    GLOSSARY: "glossary",
    ADR_README: "policy",
}

_ADR_FILE_RE = re.compile(r"^(\d{4})-[A-Za-z0-9._-]+\.md$")
_ADR_STEM_RE = re.compile(r"^(\d{4})(?:-[A-Za-z0-9._-]+)?$")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n?", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_TITLE_PREFIX_RE = re.compile(r"^\s*(?:ADR[- ])?\d{4}\s*[:—–-]\s*")
_LAST_GATHERED_RE = re.compile(r"^>\s*Last gathered:(.*)$", re.MULTILINE)
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DECISION_RE = re.compile(
    r"^_Decision date:\s*(?P<date>\d{4}-\d{2}-\d{2})(?P<rest>[^\n]*)$", re.MULTILINE
)
_TICKET_NUM_RE = re.compile(r"#(\d{1,9})\b")
_PARENT_RE = re.compile(r"^\*\*Parent doc\*\*\s*:\s*\[[^\]]*\]\(([^)\s]+)\)", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_BARE_PATH_RE = re.compile(r"(?<![\w/])(?:docs|cortex)/[\w./-]+\.md\b")
_CLAUDE_MD_RE = re.compile(r"(?<![\w/.-])CLAUDE\.md\b")

# Paths a cites edge may point at without a node behind it (dangling). A cite
# to anything outside these namespaces (a ticket file, a lifecycle artifact,
# source code) is not an edge in this graph and is dropped.
_IN_SCOPE_PREFIXES = ("docs/", f"{REQUIREMENTS_DIR}/", f"{ADR_DIR}/")
_IN_SCOPE_EXACT = frozenset({CONSTITUTION, CONFIG, README})

# H2 sections whose rows are structural edges (maps-area / global), never cites.
_STRUCTURAL_SECTIONS = frozenset({"Conditional Loading", "Global Context"})

_EDGE_RANK = {k: i for i, k in enumerate(EDGE_KINDS)}


# ---------------------------------------------------------------------------
# Backlink result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TicketRef:
    id: str            # unpadded numeric id, as ``/tickets/{id}`` wants it
    title: str
    status: str
    path: str          # repo-relative posix path of the ticket file


@dataclass(frozen=True)
class LifecycleRef:
    slug: str
    kinds: tuple[str, ...]         # subset of (research, spec, plan, review), in that order
    ticket_id: str | None          # index.md's parent_backlog_id / backlog_id, if any


@dataclass
class Backlinks:
    docs: list[tuple[DocNode, str | None, int]]   # (citing governing doc, section, count)
    tickets: list[TicketRef]
    lifecycles: list[LifecycleRef]


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def _classify(path: str) -> str:
    """Node kind for a repo-relative path, by the closed rule in model.py."""
    fixed = _FIXED_KINDS.get(path)
    if fixed:
        return fixed
    head, _, name = path.rpartition("/")
    if head == REQUIREMENTS_DIR and name.endswith(".md"):
        return "area"
    if head == ADR_DIR and _ADR_FILE_RE.match(name):
        return "adr"
    return "doc"


def _adr_number(path: str) -> int | None:
    head, _, name = path.rpartition("/")
    if head != ADR_DIR:
        return None
    m = _ADR_FILE_RE.match(name)
    return int(m.group(1)) if m else None


def _in_scope(path: str) -> bool:
    return path in _IN_SCOPE_EXACT or path.startswith(_IN_SCOPE_PREFIXES)


def _title_of(body: str, path: str) -> str:
    m = _H1_RE.search(body)
    if not m:
        return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    # Backticks are markdown, not title: a chip or an SVG box shows the
    # title as plain text, where ``\`cortex init\`` reads as noise.
    title = _TITLE_PREFIX_RE.sub("", m.group(1)).replace("`", "").strip()
    return title or m.group(1).replace("`", "").strip()


def _headings_of(body: str) -> tuple[str, ...]:
    out: list[str] = []
    for line in body.splitlines():
        m = _H2_RE.match(line)
        if m:
            out.append(m.group(1))
    return tuple(out)


def _last_gathered_of(body: str) -> str | None:
    m = _LAST_GATHERED_RE.search(body)
    if not m:
        return None
    d = _ISO_DATE_RE.search(m.group(1))
    return d.group(0) if d else None


def _decision_of(body: str) -> tuple[str | None, str | None]:
    m = _DECISION_RE.search(body)
    if not m:
        return None, None
    t = _TICKET_NUM_RE.search(m.group("rest"))
    return m.group("date"), (f"#{t.group(1)}" if t else None)


def _normalise(path: str) -> str | None:
    """Repo-relative posix path with ``./`` and ``a/../`` folded, or None if it escapes."""
    path = path.replace("\\", "/")
    if path.startswith("/"):
        return None
    norm = posixpath.normpath(path)
    if norm == "." or norm.startswith("../") or norm == "..":
        return None
    return norm


def _resolve_target(root: Path, src: str, target: str, known: set[str]) -> str | None:
    """Resolve a link target written in *src*: relative to its dir first, then repo-relative.

    Strips ``#anchor`` and ``:line`` suffixes, refuses URLs and non-``.md``
    targets. Falls back to the repo-relative spelling when it names an
    in-scope path, else the dir-relative one, so a dangling target keeps a
    sensible path.
    """
    if "://" in target or target.startswith(("mailto:", "#")):
        return None
    target = target.split("#", 1)[0]
    target = re.sub(r":\d+$", "", target)
    if not target.endswith(".md"):
        return None
    rel = _normalise(posixpath.join(posixpath.dirname(src), target))
    repo = _normalise(target)
    for cand in (rel, repo):
        if cand and (cand in known or (root / cand).is_file()):
            return cand
    if repo and _in_scope(repo):
        return repo
    return rel


def _resolve_superseded_by(raw: str, by_number: dict[int, str]) -> str | None:
    """``superseded_by`` may be a full stem, a bare number, ``none``, or a placeholder."""
    value = raw.strip().strip("\"'")
    if not value or value.lower() in {"none", "null", "~"} or value.startswith("<"):
        return None
    value = value.split("#", 1)[0].strip()
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    value = value.removesuffix(".md")
    m = _ADR_STEM_RE.match(value)
    if not m:
        return None
    if "-" in value:
        return f"{ADR_DIR}/{value}.md"
    return by_number.get(int(m.group(1)))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _discover(root: Path) -> list[str]:
    """Every governing file on disk, repo-relative, in a stable order."""
    found: list[str] = []
    for fixed in (CONSTITUTION, POLICY, ROOT_DOC, CONFIG, README, GLOSSARY, ADR_README):
        if (root / fixed).is_file():
            found.append(fixed)
    req = root / REQUIREMENTS_DIR
    if req.is_dir():
        for p in sorted(req.glob("*.md")):
            rel = f"{REQUIREMENTS_DIR}/{p.name}"
            if rel not in found and p.is_file():
                found.append(rel)
    adr = root / ADR_DIR
    if adr.is_dir():
        for p in sorted(adr.glob("*.md")):
            if _ADR_FILE_RE.match(p.name) and p.is_file():
                found.append(f"{ADR_DIR}/{p.name}")
    return found


def _stat(root: Path, path: str) -> tuple[int, float]:
    try:
        st = (root / path).stat()
    except OSError:
        return 0, 0.0
    return st.st_size, st.st_mtime


# ---------------------------------------------------------------------------
# build_corpus
# ---------------------------------------------------------------------------


@dataclass
class _Raw:
    path: str
    text: str
    body: str
    fm: dict[str, str]


def build_corpus(root: Path) -> Corpus:
    """Build the governing-doc graph for *root*. Reads only files under root."""
    root = Path(root)
    corpus = Corpus(root=root)
    raws: dict[str, _Raw] = {}
    for path in _discover(root):
        text = read_text_lossy(root / path)
        if text is None:
            continue
        raws[path] = _Raw(path, text, _strip_frontmatter(text), _parse_frontmatter(text))

    by_number: dict[int, str] = {}
    for path in raws:
        n = _adr_number(path)
        if n is not None and n not in by_number:
            by_number[n] = path

    known = set(raws)
    adr_words = {
        path: _words(path.rsplit("/", 1)[-1][5:-3].replace("-", " ") + " " + _title_of(raw.body, path))
        for path, raw in raws.items() if _adr_number(path) is not None
    }
    nodes: dict[str, DocNode] = {}
    edges: dict[tuple[str, str, str], DocEdge] = {}
    map_row: dict[tuple[str, str], int] = {}

    def add_edge(edge: DocEdge) -> None:
        edges.setdefault((edge.src, edge.dst, edge.kind), edge)

    def ensure_ghost(path: str) -> None:
        if path in nodes or path in known:
            return
        nodes[path] = DocNode(
            path=path, kind=_classify(path), title=path.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            governing=False, exists=False, adr_number=_adr_number(path),
        )

    # -- governing nodes + structural edges ---------------------------------
    parents: dict[str, str | None] = {}
    supersedes: dict[str, str | None] = {}
    map_keys: dict[str, list[str]] = {}

    for path, raw in raws.items():
        m = _PARENT_RE.search(raw.body)
        parents[path] = _resolve_target(root, path, m.group(1), known) if m else None
        if _adr_number(path) is not None:
            supersedes[path] = _resolve_superseded_by(raw.fm.get("superseded_by", ""), by_number)
        else:
            supersedes[path] = None

    if ROOT_DOC in raws:
        for i, (key_text, target) in enumerate(_parse_conditional_loading(raws[ROOT_DOC].text)):
            dst = _normalise(target.strip("`"))
            if not dst or dst == ROOT_DOC:
                continue
            keys = tuple(_split_keys(key_text))
            key = (ROOT_DOC, dst)
            if key in map_row:
                prev = edges[(ROOT_DOC, dst, "maps-area")]
                edges[(ROOT_DOC, dst, "maps-area")] = DocEdge(
                    src=ROOT_DOC, dst=dst, kind="maps-area", count=prev.count + 1,
                    keys=prev.keys + keys, section="Conditional Loading", dangling=prev.dangling,
                )
            else:
                map_row[key] = i
                add_edge(DocEdge(
                    src=ROOT_DOC, dst=dst, kind="maps-area", keys=keys,
                    section="Conditional Loading",
                    dangling=dst not in known and not (root / dst).is_file(),
                ))
            map_keys.setdefault(dst, []).extend(keys)
        for target in _parse_global_context(raws[ROOT_DOC].text):
            dst = _normalise(target.strip("`"))
            if not dst or dst == ROOT_DOC:
                continue
            add_edge(DocEdge(
                src=ROOT_DOC, dst=dst, kind="global", section="Global Context",
                dangling=dst not in known and not (root / dst).is_file(),
            ))

    for path, parent in parents.items():
        if parent and parent != path:
            add_edge(DocEdge(
                src=path, dst=parent, kind="parent",
                dangling=parent not in known and not (root / parent).is_file(),
            ))
    for older, newer in supersedes.items():
        if newer and newer != older:
            add_edge(DocEdge(
                src=newer, dst=older, kind="supersedes",
                dangling=newer not in known and not (root / newer).is_file(),
            ))

    # -- cites ---------------------------------------------------------------
    for path, raw in raws.items():
        for dst, section in _cites_in(root, path, raw.text, known, adr_words):
            if dst == path:
                continue
            key = (path, dst, "cites")
            prev = edges.get(key)
            if prev is None:
                edges[key] = DocEdge(
                    src=path, dst=dst, kind="cites", count=1, section=section,
                    dangling=dst not in known and not (root / dst).is_file(),
                )
            else:
                edges[key] = DocEdge(
                    src=path, dst=dst, kind="cites", count=prev.count + 1,
                    section=prev.section, dangling=prev.dangling,
                )

    # -- nodes: governing, then cited docs/ neighbours, then ghosts ------------
    for path, raw in raws.items():
        size, mtime = _stat(root, path)
        status = raw.fm.get("status", "").strip().strip("\"'").lower() or None
        decision_date, origin_ticket = _decision_of(raw.body)
        nodes[path] = DocNode(
            path=path,
            kind=_classify(path),
            title=_title_of(raw.body, path),
            governing=True,
            exists=True,
            adr_number=_adr_number(path),
            status=status if _adr_number(path) is not None else None,
            superseded_by=supersedes.get(path),
            parent=parents.get(path),
            last_gathered=_last_gathered_of(raw.body),
            decision_date=decision_date,
            origin_ticket=origin_ticket,
            map_keys=tuple(map_keys.get(path, ())),
            summary=first_paragraph(raw.text),
            bytes=size,
            mtime=mtime,
            headings=_headings_of(raw.body),
        )

    structural = ("parent", "maps-area", "global", "supersedes")
    for edge in list(edges.values()):
        for end in (edge.src, edge.dst):
            if end in nodes:
                continue
            on_disk = (root / end).is_file()
            if on_disk and end.startswith("docs/"):
                text = read_text_lossy(root / end) or ""
                size, mtime = _stat(root, end)
                nodes[end] = DocNode(
                    path=end, kind="doc", title=_title_of(_strip_frontmatter(text), end),
                    governing=False, exists=True, summary=first_paragraph(text),
                    bytes=size, mtime=mtime, headings=_headings_of(_strip_frontmatter(text)),
                )
            elif not on_disk and edge.kind in structural:
                ensure_ghost(end)

    # Cites that resolve to neither a node nor an in-scope dangling path are
    # not part of this graph.
    kept: dict[tuple[str, str, str], DocEdge] = {}
    for key, edge in edges.items():
        if edge.kind != "cites" or edge.dst in nodes or (edge.dangling and _in_scope(edge.dst)):
            kept[key] = edge

    # -- deterministic order ---------------------------------------------------
    corpus.nodes = nodes
    corpus.edges = [e for e in kept.values() if e.kind == "maps-area"]
    corpus.edges.sort(key=lambda e: map_row.get((e.src, e.dst), 0))
    order = {n.path: i for i, n in enumerate(corpus.ordered())}
    last = len(order)

    def edge_key(e: DocEdge):
        return (
            order.get(e.src, last),
            _EDGE_RANK.get(e.kind, 99),
            map_row.get((e.src, e.dst), 0) if e.kind == "maps-area" else 0,
            e.dst,
        )

    corpus.edges = sorted(kept.values(), key=edge_key)
    corpus.nodes = {n.path: n for n in corpus.ordered()}
    return corpus


def _cites_in(
    root: Path, src: str, text: str, known: set[str],
    adr_words: dict[str, set[str]] | None = None,
) -> list[tuple[str, str | None]]:
    """Every citation in *text*, in order, as ``(dst, section)``.

    Per line, so the enclosing H2 is known. Markdown links are consumed
    first, then bare paths, then ``ADR-NNNN`` tokens on what is left — each
    scanner masks its span so one mention is counted once. The structural
    forms — the ``**Parent doc**`` line and the two map sections — already
    carry their own edge kinds and are not re-read as cites. A number two
    ADR files share resolves by the words after the token (see
    :func:`_adr_paths`), so one mention can yield more than one edge only
    when those words cannot tell the files apart.
    """
    adr_words = adr_words or {}
    out: list[tuple[str, str | None]] = []
    section: str | None = None
    for line in text.splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            section = h2.group(1)
            continue
        if section in _STRUCTURAL_SECTIONS or _PARENT_RE.match(line):
            continue
        if not line or ("(" not in line and "/" not in line and "ADR" not in line
                        and "CLAUDE.md" not in line):
            continue
        masked = line
        for m in _MD_LINK_RE.finditer(line):
            dst = _resolve_target(root, src, m.group(1), known)
            if dst:
                out.append((dst, section))
            masked = _mask(masked, m.start(), m.end())
        for m in _BARE_PATH_RE.finditer(masked):
            dst = _normalise(m.group(0))
            if dst:
                out.append((dst, section))
            masked = _mask(masked, m.start(), m.end())
        for m in _CLAUDE_MD_RE.finditer(masked):
            out.append((CONSTITUTION, section))
            masked = _mask(masked, m.start(), m.end())
        if "ADR" in masked or "adr/" in masked:
            refs = _extract_references(masked)
            starts = sorted(_token_start(masked, token, i, refs) for i, (token, _n, _s) in enumerate(refs))
            for i, (token, num, slug) in enumerate(refs):
                at = _token_start(masked, token, i, refs)
                later = [p for p in starts if p > at]
                earlier = [p for p in starts if p < at]
                after = masked[at + len(token): later[0] if later else len(masked)]
                before = masked[earlier[-1] if earlier else 0: at]
                for dst in _adr_paths(num, slug, known, adr_words, after, before):
                    out.append((dst, section))
    return out


def _token_start(line: str, token: str, index: int, refs: list[tuple[str, int, str | None]]) -> int:
    """Where the *index*-th reference's token sits: its nth occurrence on the line."""
    nth = sum(1 for t, _n, _s in refs[:index] if t == token)
    at = -1
    for _ in range(nth + 1):
        at = line.find(token, at + 1)
    return max(at, 0)


_WORD_RE = re.compile(r"[a-z0-9]+")
_COMMON_WORDS = frozenset({
    "acros", "after", "also", "been", "before", "both", "does", "each", "from",
    "have", "into", "just", "more", "most", "must", "never", "only", "other",
    "over", "rather", "same", "should", "some", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "under", "what", "when",
    "where", "which", "while", "will", "with", "without", "would",
})


def _words(text: str) -> set[str]:
    """Lower-case telling words: four letters or more, a trailing ``s``
    folded, common words dropped so they cannot decide a duplicate."""
    out = set()
    for w in _WORD_RE.findall(text.lower()):
        if len(w) < 4:
            continue
        if w.endswith("s") and len(w) > 4:
            w = w[:-1]
        if w not in _COMMON_WORDS:
            out.add(w)
    return out


def _mask(text: str, a: int, b: int) -> str:
    """Blank ``text[a:b]`` in place so a later scanner cannot re-match it."""
    return text[:a] + " " * (b - a) + text[b:]


def _adr_paths(
    num: int, slug: str | None, known: set[str],
    adr_words: dict[str, set[str]], after: str, before: str = "",
) -> list[str]:
    """The corpus path(s) an ADR reference names, or a dangling stand-in.

    One file with the number: that file. Two or more — a number reused by
    parallel branches — the slug picks when the reference spells one;
    otherwise the words written after the token (``ADR-0093 — terrain is a
    live consumer…``), then the words before it (``a mesh mount landing
    (ADR-0093)``), pick the file whose slug and title share the most of
    them, counting only words the candidates do not share. A reference that
    names no telling word cites every candidate: the text really is
    ambiguous, and choosing one silently hid the other.
    """
    prefix = f"{ADR_DIR}/{num:04d}-"
    found = sorted(p for p in known if p.startswith(prefix))
    if slug and f"{prefix}{slug}.md" in found:
        return [f"{prefix}{slug}.md"]
    if len(found) == 1:
        return found
    if found:
        shared = set.intersection(*(adr_words.get(p, set()) for p in found))
        for context in (after, before):
            said = _words(context)
            score = {p: len((adr_words.get(p, set()) - shared) & said) for p in found}
            best = max(score.values())
            winners = [p for p in found if score[p] == best]
            if best and len(winners) == 1:
                return winners
        return found
    if slug:
        return [f"{prefix}{slug}.md"]
    return [f"{ADR_DIR}/{num:04d}.md"]


# ---------------------------------------------------------------------------
# load_doc_text
# ---------------------------------------------------------------------------


def load_doc_text(root: Path, path: str) -> str | None:
    """Body of one corpus node. *path* must be a key in ``corpus.nodes``.

    Defends against a stray caller anyway: refuses anything that is not a
    normalised repo-relative path resolving under *root*.
    """
    norm = _normalise(path)
    if norm is None or norm != path:
        return None
    root = Path(root)
    target = root / norm
    try:
        if not target.resolve().is_relative_to(root.resolve()):
            return None
    except OSError:
        return None
    if not target.is_file():
        return None
    return read_text_lossy(target)


# ---------------------------------------------------------------------------
# backlinks
# ---------------------------------------------------------------------------

_ARTIFACT_KINDS = ("research", "spec", "plan", "review")


def _needles(node: DocNode) -> list[str]:
    """Literal strings whose presence in a file counts as a mention of *node*."""
    out = [node.path]
    parts = node.path.split("/")
    if len(parts) >= 2:
        out.append("/".join(parts[-2:]))
    return out


def _mentions(
    text: str, needles: list[str], adr_re: re.Pattern[str] | None, adr_digits: str | None
) -> bool:
    if any(n in text for n in needles):
        return True
    # The regex is the slow path; the four digits are a cheap substring gate
    # that every form it accepts must contain (measured: 400ms -> 100ms on
    # this repo's 25 MB of lifecycle artifacts).
    return bool(adr_re and adr_digits and adr_digits in text and adr_re.search(text))


def _ticket_dirs(root: Path) -> list[Path]:
    base = root / "cortex" / "backlog"
    return [d for d in (base, base / "archive") if d.is_dir()]


def _lifecycle_dirs(root: Path) -> list[Path]:
    base = root / "cortex" / "lifecycle"
    out: list[Path] = []
    for parent in (base, base / "archive"):
        if not parent.is_dir():
            continue
        try:
            for d in sorted(parent.iterdir()):
                if d.is_dir() and d.name != "archive":
                    out.append(d)
        except OSError:
            continue
    return out


def backlinks(root: Path, corpus: Corpus, path: str) -> Backlinks:
    """Who mentions *path*: citing governing docs, tickets, lifecycle artifacts.

    Lazy — only the cited-by partial calls it — and read-only. Tickets and
    lifecycles are matched by literal mention of the path, its last two
    components (``requirements/project.md``) or, for an ADR, its
    ``ADR-NNNN`` token.
    """
    root = Path(root)
    node = corpus.get(path)
    if node is None:
        return Backlinks(docs=[], tickets=[], lifecycles=[])

    order = {n.path: i for i, n in enumerate(corpus.ordered())}
    docs: list[tuple[DocNode, str | None, int]] = []
    for e in corpus.in_edges(path, ("cites",)):
        src = corpus.get(e.src)
        if src is not None and src.governing:
            docs.append((src, e.section, e.count))
    docs.sort(key=lambda t: order.get(t[0].path, len(order)))

    needles = _needles(node)
    adr_re = None
    adr_digits = None
    if node.adr_number is not None:
        adr_digits = f"{node.adr_number:04d}"
        adr_re = re.compile(rf"(?<![0-9A-Za-z])\[?ADR[- ]{adr_digits}\]?(?![0-9A-Za-z])")

    tickets: list[TicketRef] = []
    seen_ids: set[str] = set()
    for d in _ticket_dirs(root):
        try:
            files = sorted(d.glob("[0-9]*-*.md"))
        except OSError:
            continue
        for f in files:
            text = read_text_lossy(f)
            if text is None or not _mentions(text, needles, adr_re, adr_digits):
                continue
            head = re.match(r"^(\d+)-", f.name)
            if not head:
                continue
            tid = str(int(head.group(1)))
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            fm = _parse_frontmatter(text)
            tickets.append(TicketRef(
                id=tid,
                title=fm.get("title", "").strip().strip("\"'") or f.stem,
                status=fm.get("status", "").strip().strip("\"'"),
                path=f.relative_to(root).as_posix(),
            ))
    tickets.sort(key=lambda t: int(t.id))

    lifecycles: list[LifecycleRef] = []
    for d in _lifecycle_dirs(root):
        kinds: list[str] = []
        for kind in _ARTIFACT_KINDS:
            f = d / f"{kind}.md"
            if not f.is_file():
                continue
            text = read_text_lossy(f)
            if text is not None and _mentions(text, needles, adr_re, adr_digits):
                kinds.append(kind)
        if not kinds:
            continue
        ticket_id: str | None = None
        index_text = read_text_lossy(d / "index.md") if (d / "index.md").is_file() else None
        if index_text:
            fm = _parse_frontmatter(index_text)
            raw = (fm.get("parent_backlog_id") or fm.get("backlog_id") or "").strip().strip("\"'")
            if raw.isdigit():
                ticket_id = str(int(raw))
        lifecycles.append(LifecycleRef(slug=d.name, kinds=tuple(kinds), ticket_id=ticket_id))
    lifecycles.sort(key=lambda lc: lc.slug)

    return Backlinks(docs=docs, tickets=tickets, lifecycles=lifecycles)
