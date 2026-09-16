"""Tests for cortex_command/dashboard/docs/render.py.

The corpus is built by hand from model.py dataclasses — no disk. Each test
names the behaviour it pins in its docstring; none pins prose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.dashboard.docs.model import Corpus, DocNode
from cortex_command.dashboard.docs.render import (
    DOC_MAX_CHARS,
    first_paragraph,
    render_doc,
    split_frontmatter,
)


def _node(path: str, kind: str, **kw) -> DocNode:
    return DocNode(path=path, kind=kind, title=path, governing=kw.pop("governing", True), **kw)


@pytest.fixture
def corpus() -> Corpus:
    c = Corpus(root=Path("/nowhere"))
    for n in (
        _node("CLAUDE.md", "constitution"),
        _node("docs/policies.md", "policy"),
        _node("cortex/requirements/project.md", "root"),
        _node("cortex/requirements/lifecycle.md", "area"),
        _node("cortex/adr/0001-first.md", "adr", adr_number=1, status="accepted"),
        _node("cortex/adr/0002-second.md", "adr", adr_number=2, status="proposed"),
        _node("cortex/adr/0009-ghost.md", "adr", adr_number=9, governing=False, exists=False),
        _node("docs/setup.md", "doc", governing=False),
    ):
        c.nodes[n.path] = n
    return c


def test_toc_ids_present(corpus):
    """Headings carry ids and the TOC lists levels 1–3 in order, plain text."""
    r = render_doc("# Top &amp; more\n\n## Sub `code`\n\n### Third\n\n#### Fourth\n", corpus, "CLAUDE.md")
    assert 'id="top-more"' in r.html
    assert 'id="fourth"' in r.html
    assert [(t.level, t.id) for t in r.toc] == [(1, "top-more"), (2, "sub-code"), (3, "third")]
    assert r.toc[0].text == "Top & more"


def test_adr_token_linked(corpus):
    """A bare ADR-NNNN in prose becomes a reader link carrying the repo query."""
    r = render_doc("See ADR-0001 and → ADR-0002.", corpus, "docs/policies.md", "?repo=x")
    assert '<a class="doc-cite js-doc" href="/docs/cortex/adr/0001-first.md?repo=x" data-doc="cortex/adr/0001-first.md">ADR-0001</a>' in r.html
    assert 'href="/docs/cortex/adr/0002-second.md?repo=x"' in r.html


def test_unknown_and_ghost_adr_not_linked(corpus):
    """Numbers with no on-disk ADR stay plain text — ADR-0009 is a ghost node."""
    r = render_doc("ADR-0042 and ADR-0009 and ADR-00011.", corpus, "CLAUDE.md")
    assert "<a" not in r.html
    assert "ADR-0042" in r.html and "ADR-0009" in r.html


def test_code_span_path_linked(corpus):
    """An inline code span naming a corpus path wraps in the same anchor; unknown paths do not."""
    r = render_doc("Read `docs/policies.md`, `project.md` and `bin/nope.md`.", corpus, "cortex/requirements/lifecycle.md")
    assert '<a class="doc-cite js-doc" href="/docs/docs/policies.md" data-doc="docs/policies.md"><code>docs/policies.md</code></a>' in r.html
    assert 'data-doc="cortex/requirements/project.md"><code>project.md</code></a>' in r.html
    assert "<code>bin/nope.md</code>" in r.html
    assert r.html.count("<a ") == 2


def test_relative_link_rewritten(corpus):
    """A relative .md href resolves against the citing doc's directory; the fragment survives."""
    r = render_doc("[parent](project.md#scope) and [adr](../adr/0001-first.md)", corpus, "cortex/requirements/lifecycle.md", "?repo=y")
    assert 'href="/docs/cortex/requirements/project.md?repo=y#scope"' in r.html
    assert 'href="/docs/cortex/adr/0001-first.md?repo=y"' in r.html
    assert 'data-doc="cortex/adr/0001-first.md"' in r.html


def test_repo_relative_link_rewritten(corpus):
    """A link written repo-relative (as CLAUDE.md does) also resolves."""
    r = render_doc("[p](docs/policies.md)", corpus, "cortex/requirements/project.md")
    assert 'href="/docs/docs/policies.md"' in r.html


def test_dangling_link_unwrapped(corpus):
    """A relative link to nothing servable loses its anchor but keeps its text; ADR tokens inside it still link."""
    r = render_doc("[missing](../requirements/spec.md) and [grey](../../docs/setup.md) and [t ADR-0001](nope.md)", corpus, "cortex/requirements/lifecycle.md")
    assert "missing" in r.html and "grey" in r.html
    assert "spec.md" not in r.html and "setup.md" not in r.html
    assert r.html.count("<a ") == 1
    assert 'href="/docs/cortex/adr/0001-first.md"' in r.html


def test_absolute_and_external_links_untouched(corpus):
    """Root-absolute, scheme and fragment hrefs pass through; text inside a kept anchor is not re-linked."""
    r = render_doc("[a](/tickets/1) [b](https://x.y/z.md) [c](#top) [ADR-0001](https://x.y/)", corpus, "CLAUDE.md")
    assert 'href="/tickets/1"' in r.html
    assert 'href="https://x.y/z.md"' in r.html
    assert 'href="#top"' in r.html
    assert r.html.count("<a ") == 4


def test_script_dropped(corpus):
    """Raw HTML is sanitized: script content vanishes, unknown attributes are stripped."""
    r = render_doc('hi <script>alert(1)</script> <a href="javascript:x" onclick="y">z</a> <h2 id="ok" style="x">t</h2>', corpus, "CLAUDE.md")
    assert "script" not in r.html and "alert" not in r.html
    assert "onclick" not in r.html and "javascript:" not in r.html and "style=" not in r.html


def test_code_blocks_untouched(corpus):
    """Fenced code is never linkified and is not re-escaped twice."""
    r = render_doc("```py\nx -> ADR-0001 & `docs/policies.md`\n```\n", corpus, "CLAUDE.md")
    assert "<a" not in r.html
    assert "-&gt; ADR-0001 &amp; `docs/policies.md`" in r.html


def test_cap_reported(corpus):
    """Bodies over the cap are truncated and say so; short ones are not."""
    long = "x" * (DOC_MAX_CHARS + 10)
    assert render_doc(long, corpus, "CLAUDE.md").truncated is True
    assert render_doc("short", corpus, "CLAUDE.md").truncated is False


def test_frontmatter_split():
    """Frontmatter is stripped from the body, kept raw, and parsed to clean scalars only."""
    text = "---\nstatus: accepted\n# a comment\nsuperseded_by:\nlist:\n  - a\n---\n# T\n\nbody\n"
    body, scalars, raw = split_frontmatter(text)
    assert body == "# T\n\nbody\n"
    assert scalars == {"status": "accepted"}
    assert raw == "---\nstatus: accepted\n# a comment\nsuperseded_by:\nlist:\n  - a\n---"
    r = render_doc(text, Corpus(root=Path("/nowhere")), "cortex/adr/0001-x.md")
    assert r.frontmatter == {"status": "accepted"} and r.frontmatter_raw == raw
    assert "status: accepted" not in r.html
    assert split_frontmatter("no fm\n") == ("no fm\n", {}, None)


def test_first_paragraph():
    """Skips frontmatter, headings, gathered lines, metadata lines and fences; strips inline marks; clips."""
    text = (
        "---\nstatus: accepted\n---\n# ADR-0001: Title\n\n> Last gathered: 2026-01-01\n\n"
        "**Parent doc**: [p](project.md)\n\n_Decision date: 2026-01-02 (#12)_\n\n```\ncode\n```\n\n"
        "The **first** real `para` with [a link](x.md)\ncontinues here.\n\nSecond para.\n"
    )
    assert first_paragraph(text) == "The first real para with a link continues here."
    assert first_paragraph("# only heading\n") == ""
    clipped = first_paragraph("word " * 100)
    assert clipped.endswith("…") and len(clipped) <= 181
