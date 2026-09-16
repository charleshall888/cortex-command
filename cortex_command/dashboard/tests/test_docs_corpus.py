"""Tests for ``cortex_command.dashboard.docs.corpus``.

Builds a small governing set in ``tmp_path`` — constitution, project.md
with a Conditional Loading map and a Global Context bullet, two area docs
with Parent lines, a glossary, three ADRs (one superseded), a policy doc, a
cited non-governing ``docs/`` neighbour, one dangling cite and one ghost
map target — and asserts the graph the builder derives from it. One test
runs the builder against this repository itself.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cortex_command.dashboard.docs.corpus import (
    Backlinks,
    LifecycleRef,
    TicketRef,
    backlinks,
    build_corpus,
    load_doc_text,
)
from cortex_command.dashboard.docs.model import Corpus

REPO_ROOT = Path(__file__).resolve().parents[3]

PROJECT = "cortex/requirements/project.md"
ALPHA = "cortex/requirements/alpha.md"
ZETA = "cortex/requirements/zeta.md"
GHOST = "cortex/requirements/ghost.md"
GLOSSARY = "cortex/requirements/glossary.md"
ADR1 = "cortex/adr/0001-first-decision.md"
ADR2 = "cortex/adr/0002-second-decision.md"
ADR3 = "cortex/adr/0003-third-decision.md"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    _write(tmp_path, "CLAUDE.md", (
        "# Project instructions\n\n"
        "Read `cortex/requirements/project.md` first, then docs/policies.md.\n\n"
        "## Conventions\n\n"
        "Path resolution follows ADR-0001.\n"
    ))
    _write(tmp_path, "docs/policies.md", (
        "# Policies\n\n"
        "Governance for the harness, see CLAUDE.md.\n\n"
        "## Escalation\n\n"
        "Decided in ADR-0001 and [the guide](guide.md).\n"
    ))
    _write(tmp_path, "docs/guide.md", "# The guide\n\nA tutorial, not governing.\n")
    _write(tmp_path, "cortex/README.md", "# cortex/\n\nUmbrella. See cortex/lifecycle.config.md.\n")
    _write(tmp_path, "cortex/lifecycle.config.md", "---\ntype: other\n---\n\n# Config\n\nBody.\n")
    _write(tmp_path, PROJECT, (
        "# Requirements: project\n\n"
        "> Last gathered: 2026-01-02 (updated 2026-03-04)\n\n"
        "The vision paragraph, which is the summary.\n\n"
        "## Conditional Loading\n\n"
        "- alpha, beta → cortex/requirements/alpha.md\n"
        "- zeta → cortex/requirements/zeta.md\n"
        "- ghost → cortex/requirements/ghost.md\n\n"
        "## Global Context\n\n"
        "- cortex/requirements/glossary.md\n\n"
        "## Optional\n\n"
        "See docs/guide.md and docs/missing.md; also ADR-0002.\n"
    ))
    _write(tmp_path, ALPHA, (
        "# Requirements: alpha\n\n"
        "> Last gathered: 2026-02-02\n\n"
        "**Parent doc**: [requirements/project.md](project.md)\n\n"
        "## Overview\n\n"
        "Follows ADR-0001, and ADR-0099 which does not exist.\n\n"
        "## Related\n\n"
        "Sibling: [zeta](zeta.md).\n"
    ))
    _write(tmp_path, ZETA, (
        "# Requirements: zeta\n\n"
        "**Parent doc**: [requirements/project.md](project.md)\n\n"
        "## Constraints\n\n"
        "Bound by ADR-0002 (see → ADR-0002 again).\n"
    ))
    _write(tmp_path, GLOSSARY, "# Glossary\n\n- **term** — meaning.\n")
    _write(tmp_path, "cortex/adr/README.md", "# ADRs\n\nHow to write one. Template: `status: proposed`.\n")
    _write(tmp_path, ADR1, (
        "---\nstatus: accepted\n---\n\n"
        "# ADR-0001: First decision\n\n"
        "_Decision date: 2026-01-10 (#12 — some-slug)._\n\n"
        "## Context\n\nWe needed one. CLAUDE.md agrees.\n"
    ))
    _write(tmp_path, ADR2, (
        "---\nstatus: superseded\nsuperseded_by: 0003-third-decision\n---\n\n"
        "# 0002 — Second decision\n\n## Context\n\nOld.\n"
    ))
    _write(tmp_path, ADR3, (
        "---\nstatus: proposed\n---\n\n"
        "# Third decision\n\n## Context\n\nReplaces ADR-0002; this is ADR-0003.\n"
    ))
    # Tickets: one live, one archived.
    _write(tmp_path, "cortex/backlog/012-do-the-thing.md", (
        "---\ntitle: \"Do the thing\"\nstatus: complete\n---\n\n"
        "Touches requirements/zeta.md and [ADR-0001].\n"
    ))
    _write(tmp_path, "cortex/backlog/archive/003-old-thing.md", (
        "---\ntitle: Old thing\nstatus: archived\n---\n\nAbout ADR-0002.\n"
    ))
    _write(tmp_path, "cortex/backlog/004-unrelated.md", "---\ntitle: Nope\nstatus: backlog\n---\n\nNothing.\n")
    # Lifecycles: one live with an index, one archived without a ticket.
    _write(tmp_path, "cortex/lifecycle/some-slug/index.md", (
        "---\nfeature: some-slug\nparent_backlog_id: 12\nareas: [zeta]\n---\n\n# some-slug\n"
    ))
    _write(tmp_path, "cortex/lifecycle/some-slug/research.md", "# Research\n\ncortex/requirements/zeta.md\n")
    _write(tmp_path, "cortex/lifecycle/some-slug/spec.md", "# Spec\n\nSee requirements/zeta.md.\n")
    _write(tmp_path, "cortex/lifecycle/some-slug/plan.md", "# Plan\n\nNo doc named.\n")
    _write(tmp_path, "cortex/lifecycle/archive/old-slug/index.md", (
        "---\nfeature: old-slug\nparent_backlog_id: null\n---\n"
    ))
    _write(tmp_path, "cortex/lifecycle/archive/old-slug/review.md", "# Review\n\nADR-0002 drifted.\n")
    return tmp_path


@pytest.fixture
def corpus(fixture_root: Path) -> Corpus:
    return build_corpus(fixture_root)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def test_node_kinds(corpus: Corpus) -> None:
    kinds = {p: n.kind for p, n in corpus.nodes.items()}
    assert kinds["CLAUDE.md"] == "constitution"
    assert kinds["docs/policies.md"] == "policy"
    assert kinds["cortex/adr/README.md"] == "policy"
    assert kinds[PROJECT] == "root"
    assert kinds["cortex/lifecycle.config.md"] == "config"
    assert kinds["cortex/README.md"] == "readme"
    assert kinds[ALPHA] == "area"
    assert kinds[ZETA] == "area"
    assert kinds[GLOSSARY] == "glossary"
    assert kinds[ADR1] == kinds[ADR2] == kinds[ADR3] == "adr"
    assert kinds["docs/guide.md"] == "doc"
    assert not corpus.nodes["docs/guide.md"].governing
    assert "docs/missing.md" not in corpus.nodes
    assert "cortex/adr/README.md" in {n.path for n in corpus.governing()}


def test_index_order(corpus: Corpus) -> None:
    assert [n.path for n in corpus.ordered()] == [
        "CLAUDE.md",
        "cortex/adr/README.md",
        "docs/policies.md",
        PROJECT,
        "cortex/lifecycle.config.md",
        "cortex/README.md",
        ALPHA,
        ZETA,
        GHOST,
        GLOSSARY,
        ADR1,
        ADR2,
        ADR3,
        "docs/guide.md",
    ]
    # nodes dict iterates in the same order
    assert list(corpus.nodes) == [n.path for n in corpus.ordered()]


def test_node_fields(corpus: Corpus) -> None:
    project = corpus.nodes[PROJECT]
    assert project.title == "Requirements: project"
    assert project.last_gathered == "2026-01-02"
    assert project.summary == "The vision paragraph, which is the summary."
    assert project.headings == ("Conditional Loading", "Global Context", "Optional")
    assert project.bytes > 0 and project.mtime > 0

    alpha = corpus.nodes[ALPHA]
    assert alpha.parent == PROJECT
    assert alpha.map_keys == ("alpha", "beta")
    assert corpus.nodes[ZETA].map_keys == ("zeta",)

    adr1 = corpus.nodes[ADR1]
    assert adr1.adr_number == 1
    assert adr1.status == "accepted"
    assert adr1.title == "First decision"
    assert adr1.short == "ADR-0001"
    assert adr1.decision_date == "2026-01-10"
    assert adr1.origin_ticket == "#12"

    adr2 = corpus.nodes[ADR2]
    assert adr2.title == "Second decision"
    assert adr2.status == "superseded"
    assert adr2.superseded_by == ADR3
    assert corpus.nodes[ADR3].superseded_by is None
    assert corpus.by_adr(2) is adr2
    assert corpus.by_adr(99) is None


def test_ghost_map_target(corpus: Corpus) -> None:
    ghost = corpus.nodes[GHOST]
    assert ghost.exists is False
    assert ghost.governing is False
    assert ghost.kind == "area"
    edge = [e for e in corpus.edges if e.kind == "maps-area" and e.dst == GHOST]
    assert len(edge) == 1 and edge[0].dangling and edge[0].keys == ("ghost",)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def _edges(corpus: Corpus, kind: str) -> list[tuple[str, str]]:
    return [(e.src, e.dst) for e in corpus.edges if e.kind == kind]


def test_structural_edges(corpus: Corpus) -> None:
    assert _edges(corpus, "maps-area") == [(PROJECT, ALPHA), (PROJECT, ZETA), (PROJECT, GHOST)]
    assert corpus.map_order() == [ALPHA, ZETA, GHOST]
    assert _edges(corpus, "global") == [(PROJECT, GLOSSARY)]
    assert _edges(corpus, "parent") == [(ALPHA, PROJECT), (ZETA, PROJECT)]
    assert _edges(corpus, "supersedes") == [(ADR3, ADR2)]
    for e in corpus.edges:
        if e.kind != "maps-area" or e.dst != GHOST:
            assert not e.dangling or e.kind == "cites", e


def test_cites_fold_and_section(corpus: Corpus) -> None:
    zeta_cites = corpus.out_edges(ZETA, ("cites",))
    assert len(zeta_cites) == 1
    e = zeta_cites[0]
    assert (e.dst, e.count, e.section, e.dangling) == (ADR2, 2, "Constraints", False)

    claude = {e.dst: e for e in corpus.out_edges("CLAUDE.md", ("cites",))}
    assert set(claude) == {PROJECT, "docs/policies.md", ADR1}
    assert claude[PROJECT].section is None          # above any H2
    assert claude[ADR1].section == "Conventions"

    # relative markdown link resolved against the citing file's dir
    assert (ALPHA, ZETA) in _edges(corpus, "cites")
    # a governing doc citing a docs/ file makes it a grey neighbour
    assert (PROJECT, "docs/guide.md") in _edges(corpus, "cites")
    assert ("docs/policies.md", "docs/guide.md") in _edges(corpus, "cites")


def test_dangling_cites_get_no_node(corpus: Corpus) -> None:
    dangling = {(e.src, e.dst) for e in corpus.edges if e.kind == "cites" and e.dangling}
    assert dangling == {(PROJECT, "docs/missing.md"), (ALPHA, "cortex/adr/0099.md")}
    assert "docs/missing.md" not in corpus.nodes
    assert "cortex/adr/0099.md" not in corpus.nodes


def test_self_cites_dropped(corpus: Corpus) -> None:
    assert all(e.src != e.dst for e in corpus.edges)
    assert _edges(corpus, "cites").count((ADR3, ADR2)) == 1


def test_edge_order_is_src_index_order(corpus: Corpus) -> None:
    pos = {n.path: i for i, n in enumerate(corpus.ordered())}
    srcs = [pos[e.src] for e in corpus.edges]
    assert srcs == sorted(srcs)
    # deterministic: a rebuild yields identical edges
    assert build_corpus(corpus.root).edges == corpus.edges


def test_children_and_neighbours(corpus: Corpus) -> None:
    assert [n.path for n in corpus.children(PROJECT)] == [ALPHA, ZETA, GHOST, GLOSSARY]
    assert corpus.neighbours(ZETA) == {PROJECT, ADR2, ALPHA}
    assert corpus.neighbours(ADR2) == {ZETA, ADR3, PROJECT}


# ---------------------------------------------------------------------------
# load_doc_text / backlinks
# ---------------------------------------------------------------------------


def test_load_doc_text(fixture_root: Path, corpus: Corpus) -> None:
    text = load_doc_text(fixture_root, ZETA)
    assert text is not None and text.startswith("# Requirements: zeta")
    assert load_doc_text(fixture_root, "../etc/passwd") is None
    assert load_doc_text(fixture_root, "/etc/passwd") is None
    assert load_doc_text(fixture_root, "cortex/requirements/nope.md") is None


def test_backlinks_area_doc(fixture_root: Path, corpus: Corpus) -> None:
    bl = backlinks(fixture_root, corpus, ZETA)
    assert isinstance(bl, Backlinks)
    assert [(n.path, sec, cnt) for n, sec, cnt in bl.docs] == [(ALPHA, "Related", 1)]
    assert bl.tickets == [
        TicketRef(id="12", title="Do the thing", status="complete",
                  path="cortex/backlog/012-do-the-thing.md"),
    ]
    assert bl.lifecycles == [
        LifecycleRef(slug="some-slug", kinds=("research", "spec"), ticket_id="12"),
    ]


def test_backlinks_adr_by_token(fixture_root: Path, corpus: Corpus) -> None:
    bl = backlinks(fixture_root, corpus, ADR2)
    assert [(n.path, cnt) for n, _, cnt in bl.docs] == [(PROJECT, 1), (ZETA, 2), (ADR3, 1)]
    assert [t.id for t in bl.tickets] == ["3"]
    assert bl.tickets[0].path == "cortex/backlog/archive/003-old-thing.md"
    assert bl.lifecycles == [LifecycleRef(slug="old-slug", kinds=("review",), ticket_id=None)]


def test_backlinks_unknown_path(fixture_root: Path, corpus: Corpus) -> None:
    bl = backlinks(fixture_root, corpus, "docs/missing.md")
    assert bl.docs == [] and bl.tickets == [] and bl.lifecycles == []


# ---------------------------------------------------------------------------
# This repository
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not (REPO_ROOT / "cortex" / "adr").is_dir(), reason="no cortex/adr here")
def test_real_repo_corpus() -> None:
    corpus = build_corpus(REPO_ROOT)
    assert len(corpus.governing()) >= 40
    assert len(_edges(corpus, "maps-area")) >= 7
    assert all(e.src != e.dst for e in corpus.edges)
    assert all(corpus.get(e.src) is not None for e in corpus.edges)
    for e in corpus.edges:
        if not e.dangling:
            assert corpus.get(e.dst) is not None, e
    started = time.perf_counter()
    bl = backlinks(REPO_ROOT, corpus, "cortex/requirements/project.md")
    elapsed = time.perf_counter() - started
    assert bl.tickets and bl.lifecycles
    assert elapsed < 2.0, f"backlinks took {elapsed:.3f}s"
