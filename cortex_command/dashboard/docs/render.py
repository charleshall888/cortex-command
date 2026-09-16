"""Markdown → sanitized HTML for the Docs view, with citations linkified.

Pipeline, in order:

1. Strip the frontmatter block (kept raw for display, parsed to scalars).
2. Cap the body at :data:`DOC_MAX_CHARS`, reporting truncation.
3. Render with Python-Markdown (``fenced_code``, ``tables``, ``toc``) and
   take ``toc_tokens`` for the rail.
4. Sanitize with :class:`_DocSanitizer`, the ticket-body allowlist plus ``id``
   on headings and ``class``/``data-doc`` on anchors — nothing else loosened.
   Relative hrefs are resolved here, before the safe-URL check sees them,
   because that check (``_TICKET_SAFE_URL_RE``) rejects a bare ``project.md``
   and would erase the href before any later pass could read it: a target
   the reader serves becomes ``/docs/<path>``, anything else loses its
   anchor and keeps its text.
5. Linkify with a second parser pass that touches only text outside ``<a>``
   and ``<pre>``: ``ADR-NNNN`` tokens and ``<code>`` spans naming a corpus
   doc become reader links. A link to a 404 is never emitted.

Pure functions only. Nothing here reads disk or touches dashboard state.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser

import markdown

from cortex_command.dashboard.data import (
    _TICKET_ALLOWED_TAGS,
    _TICKET_SAFE_URL_RE,
    _TicketBodySanitizer,
)
from cortex_command.dashboard.docs.model import Corpus, DocNode

#: Ceiling on rendered source, in characters, matching
#: ``data.ARTIFACT_MAX_CHARS``. Truncation is reported, never silent.
DOC_MAX_CHARS = 128_000

#: Length the plain-text summary is clipped to.
SUMMARY_CHARS = 180

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_FM_KEY_RE = re.compile(r"^[A-Za-z_][\w-]*$")
_ADR_TOKEN_RE = re.compile(r"\bADR-(\d{4})\b")
_ADR_EXACT_RE = re.compile(r"^ADR-(\d{4})$")
#: An href the browser would resolve against the page URL rather than the
#: doc's own directory: no scheme, not root-absolute, not a fragment.
_RELATIVE_HREF_RE = re.compile(r"^(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)")

#: Attributes worth preserving, per tag: the ticket-body table plus the two
#: additions the reader needs. ``id`` on headings carries the ``toc``
#: extension's anchors; ``class``/``data-doc`` on ``a`` are what the
#: linkifier emits, kept so a re-sanitize is idempotent.
_DOC_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title", "class", "data-doc"}),
    "code": frozenset({"class"}),
    "pre": frozenset({"class"}),
    "td": frozenset({"align"}),
    "th": frozenset({"align"}),
    **{f"h{n}": frozenset({"id"}) for n in range(1, 7)},
}


@dataclass(frozen=True)
class TocEntry:
    level: int
    id: str
    text: str


@dataclass
class Rendered:
    html: str
    toc: list[TocEntry] = field(default_factory=list)
    truncated: bool = False
    frontmatter: dict[str, str] = field(default_factory=dict)
    frontmatter_raw: str | None = None


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[str, dict[str, str], str | None]:
    """Return ``(body, scalars, raw_block)`` for *text*.

    ``scalars`` holds only ``key: value`` lines whose key is an identifier
    and whose value is non-empty — comment lines and nested-list members
    (``lifecycle.config.md`` has both) are skipped rather than surfacing as
    keys like ``# skip-specify``. ``raw_block`` is the block verbatim
    including its fences, or None when there is no frontmatter.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, {}, None
    scalars: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if sep and value and _FM_KEY_RE.match(key):
            scalars[key] = value
    return text[m.end():], scalars, m.group(0).rstrip("\n")


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

def _servable(node: DocNode | None) -> DocNode | None:
    """The node if the reader route would serve it (governing, on disk)."""
    if node is not None and node.governing and node.exists:
        return node
    return None


def resolve_relative(corpus: Corpus, self_path: str, target: str) -> DocNode | None:
    """Resolve *target* like corpus.py does: against the citing doc's directory,
    then as a repo-relative path. Returns a servable node or None."""
    target = target.strip()
    if not target:
        return None
    base = posixpath.dirname(self_path)
    for candidate in (posixpath.normpath(posixpath.join(base, target)), posixpath.normpath(target)):
        if candidate.startswith("../") or candidate == "..":
            continue
        node = _servable(corpus.get(candidate))
        if node is not None:
            return node
    return None


def _doc_href(node: DocNode, repo_query: str, fragment: str = "") -> str:
    return f"/docs/{node.path}{repo_query}" + (f"#{fragment}" if fragment else "")


class _DocSanitizer(_TicketBodySanitizer):
    """The ticket-body sanitizer with the reader's two attribute additions.

    Only ``handle_starttag`` consults the attribute table, so that is the one
    method overridden for the allowlist; tag allow/deny and content
    suppression are inherited unchanged from ``data._TicketBodySanitizer``.
    Anchors get one extra step: a relative href is resolved through the
    corpus and rewritten to the reader route, or the anchor is dropped and
    its text kept — see the module docstring for why this cannot wait for
    the linkify pass.
    """

    def __init__(self, corpus: Corpus, self_path: str, repo_query: str) -> None:
        super().__init__()
        self.corpus = corpus
        self.self_path = self_path
        self.repo_query = repo_query
        # One entry per open <a>: True when emitted, False when dropped.
        self._a_stack: list[bool] = []

    def _rewrite_href(self, attrs: list) -> tuple[list, bool]:
        href = next((v for k, v in attrs if k == "href"), None)
        if href is None or not _RELATIVE_HREF_RE.match(href.strip()):
            return attrs, True
        target, _, fragment = href.strip().partition("#")
        node = resolve_relative(self.corpus, self.self_path, target)
        if node is None:
            return attrs, False
        rewritten = [(k, v) for k, v in attrs if k not in ("href", "class", "data-doc")]
        rewritten += [
            ("href", _doc_href(node, self.repo_query, fragment)),
            ("class", "doc-cite js-doc"),
            ("data-doc", node.path),
        ]
        return rewritten, True

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in _TICKET_ALLOWED_TAGS or self._suppress_depth:
            super().handle_starttag(tag, attrs)
            return
        if tag == "a":
            attrs, keep = self._rewrite_href(attrs)
            self._a_stack.append(keep)
            if not keep:
                return
        allowed = _DOC_ALLOWED_ATTRS.get(tag, frozenset())
        rendered = ""
        for name, value in attrs:
            if name not in allowed or value is None:
                continue
            if name == "href" and not _TICKET_SAFE_URL_RE.match(value.strip()):
                continue
            rendered += f' {name}="{escape(value, quote=True)}"'
        self.out.append(f"<{tag}{rendered}>")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and not self._suppress_depth and self._a_stack and not self._a_stack.pop():
            return
        super().handle_endtag(tag)


def sanitize_doc_html(html: str, corpus: Corpus, self_path: str, repo_query: str = "") -> str:
    parser = _DocSanitizer(corpus, self_path, repo_query)
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


# ---------------------------------------------------------------------------
# Linkifier
# ---------------------------------------------------------------------------

def _resolve_code_text(corpus: Corpus, self_path: str, text: str) -> DocNode | None:
    m = _ADR_EXACT_RE.match(text.strip())
    if m:
        return _servable(corpus.by_adr(int(m.group(1))))
    return resolve_relative(corpus, self_path, text)


class _Linkifier(HTMLParser):
    """Rebuild sanitized HTML with citations turned into reader links.

    Runs *after* sanitizing, so every tag seen here is allowlisted and every
    anchor already points somewhere servable; text inside ``<a>`` and
    ``<pre>`` passes through untouched. Output is re-escaped the same way the
    sanitizer does, so the pass is byte-stable on input it does not change.
    """

    def __init__(self, corpus: Corpus, self_path: str, repo_query: str) -> None:
        super().__init__(convert_charrefs=False)
        self.corpus = corpus
        self.self_path = self_path
        self.repo_query = repo_query
        self.out: list[str] = []
        self._pre_depth = 0
        self._a_depth = 0
        # While inside an inline <code> outside <pre>/<a>: the emitted pieces
        # and the plain text, decided on at </code>.
        self._code_buf: list[str] | None = None
        self._code_text: list[str] = []

    # -- helpers ---------------------------------------------------------

    def _anchor_open(self, node: DocNode) -> str:
        href = escape(_doc_href(node, self.repo_query), quote=True)
        return f'<a class="doc-cite js-doc" href="{href}" data-doc="{escape(node.path, quote=True)}">'

    def _emit(self, s: str) -> None:
        if self._code_buf is not None:
            self._code_buf.append(s)
        else:
            self.out.append(s)

    def _linkify_text(self, data: str) -> str:
        pieces: list[str] = []
        pos = 0
        for m in _ADR_TOKEN_RE.finditer(data):
            pieces.append(escape(data[pos:m.start()], quote=False))
            token = escape(m.group(0), quote=False)
            node = _servable(self.corpus.by_adr(int(m.group(1))))
            pieces.append(f"{self._anchor_open(node)}{token}</a>" if node else token)
            pos = m.end()
        pieces.append(escape(data[pos:], quote=False))
        return "".join(pieces)

    @staticmethod
    def _render_tag(tag: str, attrs: list, self_closing: bool = False) -> str:
        rendered = "".join(
            f' {k}="{escape(v, quote=True)}"' for k, v in attrs if v is not None
        )
        return f"<{tag}{rendered}{' /' if self_closing else ''}>"

    # -- parser callbacks ------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "pre":
            self._pre_depth += 1
        elif tag == "a":
            self._a_depth += 1
        elif tag == "code" and not self._pre_depth and not self._a_depth and self._code_buf is None:
            self._code_buf = [self._render_tag(tag, attrs)]
            self._code_text = []
            return
        self._emit(self._render_tag(tag, attrs))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self._emit(self._render_tag(tag, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
        elif tag == "a":
            self._a_depth = max(0, self._a_depth - 1)
        elif tag == "code" and self._code_buf is not None:
            buf, self._code_buf = self._code_buf, None
            buf.append("</code>")
            node = _resolve_code_text(self.corpus, self.self_path, "".join(self._code_text))
            if node is not None:
                self.out.append(self._anchor_open(node))
                self.out.extend(buf)
                self.out.append("</a>")
            else:
                self.out.extend(buf)
            return
        self._emit(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._code_buf is not None:
            self._code_text.append(data)
            self._emit(escape(data, quote=False))
        elif self._pre_depth or self._a_depth:
            self._emit(escape(data, quote=False))
        else:
            self._emit(self._linkify_text(data))

    def handle_entityref(self, name: str) -> None:
        if self._code_buf is not None:
            self._code_text.append(unescape(f"&{name};"))
        self._emit(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._code_buf is not None:
            self._code_text.append(unescape(f"&#{name};"))
        self._emit(f"&#{name};")


def linkify(html: str, corpus: Corpus, self_path: str, repo_query: str = "") -> str:
    parser = _Linkifier(corpus, self_path, repo_query)
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _flatten_toc(tokens: list[dict], out: list[TocEntry]) -> None:
    for tok in tokens:
        out.append(TocEntry(int(tok["level"]), str(tok["id"]), unescape(str(tok["name"]))))
        _flatten_toc(tok.get("children", []), out)


def render_doc(text: str, corpus: Corpus, self_path: str, repo_query: str = "") -> Rendered:
    """Render one governing doc's markdown for the reader page."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    body, scalars, raw = split_frontmatter(text)
    body = body.strip("\n")
    truncated = len(body) > DOC_MAX_CHARS
    if truncated:
        body = body[:DOC_MAX_CHARS]
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        extension_configs={"toc": {"toc_depth": "1-3"}},
    )
    html = sanitize_doc_html(md.convert(body), corpus, self_path, repo_query)
    html = linkify(html, corpus, self_path, repo_query)
    toc: list[TocEntry] = []
    _flatten_toc(getattr(md, "toc_tokens", []) or [], toc)
    return Rendered(html=html, toc=toc, truncated=truncated, frontmatter=scalars, frontmatter_raw=raw)


_SKIP_BLOCK_RE = re.compile(r"^(?:#|>|```|~~~|---|\||<!--|\*\*Parent doc\*\*|_Decision date)")
_INLINE_STRIP = (
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"),   # links → text
    (re.compile(r"<[^>]+>"), ""),                      # inline tags
    (re.compile(r"[`*_]{1,3}"), ""),                   # emphasis / code marks
    (re.compile(r"\s+"), " "),
)


def first_paragraph(text: str, limit: int = SUMMARY_CHARS) -> str:
    """The first body paragraph of *text* as plain text, clipped to *limit*.

    Skips frontmatter, headings, blockquotes (``> Last gathered:``), fenced
    code, tables, comments, and the ``**Parent doc**`` / ``_Decision date``
    metadata lines, since those are already fields on the node.
    """
    body, _, _ = split_frontmatter(text.replace("\r\n", "\n"))
    in_fence = False
    block: list[str] = []
    for line in body.splitlines() + [""]:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            if block:
                break
            continue
        if not block and _SKIP_BLOCK_RE.match(stripped):
            continue
        block.append(stripped)
    para = " ".join(block)
    for rx, repl in _INLINE_STRIP:
        para = rx.sub(repl, para)
    para = para.strip()
    if len(para) > limit:
        cut = para[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
        para = (cut or para[:limit]) + "…"
    return para
