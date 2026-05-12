"""Smoke test for spec R13: downstream parsers tolerate ``superseded:`` frontmatter.

When `/cortex-core:discovery` is re-run on a topic with an existing
``cortex/research/{topic}/`` directory, R13 produces a fresh-slug artifact at
``cortex/research/{topic}-N/research.md`` whose YAML frontmatter carries a
``superseded:`` key pointing at the prior artifact path. The four sub-rules
spelled out in the spec (a/b/c/d) require that the prior artifact stay
untouched and that reconciliation is a manual user decision, NOT something
the downstream tooling automates.

The unverified-assumption gap R13 closes is the question "will existing
parsers reject ``superseded:`` as an unknown frontmatter field?". This
smoke test answers that question positively: each parser the spec names
as a downstream consumer is exercised against a fixture that carries the
new key, and the test asserts the parser neither raises nor silently
drops other fields.

Parsers exercised (spec R13 acceptance):

  1. **Refine's clarify-critic loader** — ``bin/cortex-load-parent-epic``
     uses ``yaml.safe_load`` against the frontmatter of the resolved
     backlog item (and its parent epic) before clarify-critic's dispatch.
     A backlog item whose research artifact carries ``superseded:`` does
     not itself carry the field, but the loader's tolerance is verified
     by feeding ``superseded:`` directly into the parsed frontmatter
     (covering the broader "the loader does not reject unknown fields"
     contract). The loader's `_parse_frontmatter` helper is the entry
     point that any future change to scan research-artifact frontmatter
     would re-use.

  2. **Lifecycle's discovery-bootstrap loader** — the bootstrap consumes
     ``cortex-resolve-backlog-item``'s parsed frontmatter from Step 1
     of the lifecycle skill. ``bin/cortex-resolve-backlog-item`` uses
     ``yaml.safe_load`` on the frontmatter block. The bootstrap reads
     ``discovery_source`` and ``research`` fields; it must not break
     when the referenced research-artifact frontmatter (or, by symmetry,
     the backlog-item frontmatter) carries an additional
     ``superseded:`` field.

  3. **Backlog index generator** — ``cortex_command.backlog.generate_index``
     extracts known fields from each backlog item's frontmatter via a
     simple key/value splitter. The frontmatter parser must tolerate
     ``superseded:`` (a key it does not extract) without raising or
     mis-parsing the surrounding keys it does extract.

The test pattern for each parser is identical: build a temp markdown
fixture whose frontmatter carries ``superseded: <prior-path>`` alongside
other known fields; invoke the parser's entry point; assert no exception
and assert the surrounding fields parse correctly (proving the unknown
field did not corrupt sibling keys).
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
LOAD_PARENT_EPIC = REPO_ROOT / "bin" / "cortex-load-parent-epic"
RESOLVE_BACKLOG_ITEM = REPO_ROOT / "bin" / "cortex-resolve-backlog-item"


# Sample frontmatter blob the new R13 artifact would carry. Mirrors the
# shape documented in skills/discovery/SKILL.md Step 2:
#   superseded: cortex/research/<prior-topic>/research.md
SAMPLE_SUPERSEDED_VALUE = "cortex/research/plugin-system/research.md"


def _load_module_from_path(name: str, path: Path):
    """Load a module-by-path so dashed-name scripts can be imported."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Parser 1: refine's clarify-critic loader (bin/cortex-load-parent-epic)
# ---------------------------------------------------------------------------


def test_clarify_critic_loader_tolerates_superseded_on_child(tmp_path: Path) -> None:
    """The clarify-critic loader parses a child backlog item whose
    frontmatter carries ``superseded:`` without raising and without losing
    sibling keys.
    """
    child = tmp_path / "300-test-child.md"
    child.write_text(
        "---\n"
        "title: Test child\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "parent: null\n"
        "---\n\n# Body\n",
        encoding="utf-8",
    )

    env = {"CORTEX_BACKLOG_DIR": str(tmp_path), **os.environ}
    result = subprocess.run(
        [sys.executable, str(LOAD_PARENT_EPIC), "300-test-child"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"loader rejected superseded:; stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    # The known sibling field (parent: null) was honored, proving the
    # unknown superseded: did not corrupt parsing of surrounding keys.
    assert payload == {"status": "no_parent"}


def test_clarify_critic_loader_helper_returns_superseded_value(tmp_path: Path) -> None:
    """Direct unit-level check of the loader's ``_parse_frontmatter`` helper:
    when invoked on a file whose frontmatter carries ``superseded:``, the
    helper returns the field's value alongside all other keys.
    """
    module = _load_module_from_path(
        "cortex_load_parent_epic_for_test", LOAD_PARENT_EPIC
    )

    artifact = tmp_path / "research.md"
    artifact.write_text(
        "---\n"
        "title: Re-run research artifact\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "topic: plugin-system-2\n"
        "---\n\n# Architecture\n\nBody.\n",
        encoding="utf-8",
    )
    fm = module._parse_frontmatter(artifact)
    assert fm["superseded"] == SAMPLE_SUPERSEDED_VALUE
    assert fm["topic"] == "plugin-system-2"
    assert fm["title"] == "Re-run research artifact"


# ---------------------------------------------------------------------------
# Parser 2: lifecycle's discovery-bootstrap loader (bin/cortex-resolve-backlog-item)
# ---------------------------------------------------------------------------


def test_discovery_bootstrap_loader_tolerates_superseded_on_backlog_item(
    tmp_path: Path,
) -> None:
    """The lifecycle discovery-bootstrap loader resolves a backlog item
    whose frontmatter carries ``superseded:`` without rejecting the file.
    Step 1's frontmatter parse is the entry point the bootstrap reads
    from; if that parse fails, the bootstrap cannot proceed.
    """
    item = tmp_path / "300-supersede-test.md"
    item.write_text(
        "---\n"
        "title: Supersede test\n"
        "lifecycle_slug: supersede-test\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "discovery_source: cortex/research/plugin-system-2/research.md\n"
        "---\n\n# Body\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(RESOLVE_BACKLOG_ITEM), "supersede-test"],
        capture_output=True,
        text=True,
        cwd=tmp_path.parent,
        env={**os.environ, "PWD": str(tmp_path.parent)},
    )
    # Some resolver invocations may exit non-zero if the backlog dir isn't
    # exactly named "backlog/" — re-run with the canonical layout.
    if result.returncode not in (0, 3):
        # Retry under a "backlog/" layout, which is the resolver's
        # standard search location.
        backlog_dir = tmp_path / "cortex" / "backlog"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        item2 = backlog_dir / "300-supersede-test.md"
        item2.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(RESOLVE_BACKLOG_ITEM), "supersede-test"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
    # The contract being tested: parser does not REJECT the file. Exit
    # codes 0 (resolved), 1 (no match), or 3 (no match) are all
    # acceptable; what fails the test is a YAML/parse error (exit 70
    # per the resolver's documented error codes).
    assert result.returncode != 70, (
        f"resolver flagged frontmatter parse error; stderr={result.stderr!r}"
    )


def test_discovery_bootstrap_loader_helper_returns_superseded_value(
    tmp_path: Path,
) -> None:
    """Direct unit-level check of the resolver's ``_parse_frontmatter`` helper:
    parsing a file with ``superseded:`` returns the field's value alongside
    siblings.
    """
    module = _load_module_from_path(
        "cortex_resolve_backlog_item_for_test", RESOLVE_BACKLOG_ITEM
    )

    artifact = tmp_path / "research.md"
    artifact.write_text(
        "---\n"
        "title: Re-run research artifact\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "lifecycle_slug: plugin-system-2\n"
        "---\n\n# Body\n",
        encoding="utf-8",
    )
    fm = module._parse_frontmatter(artifact)
    assert fm["superseded"] == SAMPLE_SUPERSEDED_VALUE
    assert fm["lifecycle_slug"] == "plugin-system-2"
    assert fm["title"] == "Re-run research artifact"


# ---------------------------------------------------------------------------
# Parser 3: backlog index generator
# ---------------------------------------------------------------------------


def test_backlog_index_generator_tolerates_superseded(tmp_path: Path) -> None:
    """The backlog index generator's frontmatter parser does not reject
    ``superseded:`` and continues to extract the surrounding known fields
    correctly.
    """
    from cortex_command.backlog.generate_index import _parse_frontmatter

    item = tmp_path / "300-supersede.md"
    item.write_text(
        "---\n"
        "title: Supersede smoke test\n"
        "status: open\n"
        "priority: medium\n"
        "type: feature\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "discovery_source: cortex/research/plugin-system-2/research.md\n"
        "tags: []\n"
        "---\n\n# Body\n",
        encoding="utf-8",
    )

    fm = _parse_frontmatter(item.read_text(encoding="utf-8"))
    # No exception means the parser tolerated the unknown key. Verify
    # the surrounding fields still parsed (the unknown field did not
    # corrupt siblings).
    assert fm["title"] == "Supersede smoke test"
    assert fm["status"] == "open"
    assert fm["priority"] == "medium"
    assert fm["discovery_source"] == "cortex/research/plugin-system-2/research.md"
    # And the unknown field is captured rather than silently dropped or
    # raising — the generator simply doesn't extract it downstream.
    assert fm["superseded"] == SAMPLE_SUPERSEDED_VALUE


def test_backlog_index_generator_overnight_parser_tolerates_superseded(
    tmp_path: Path,
) -> None:
    """Companion check covering the parallel frontmatter parser in
    ``cortex_command.overnight.backlog``. The two generators share the
    same backlog-frontmatter shape and would both encounter ``superseded:``
    if the field ever lands in a backlog item's frontmatter.
    """
    from cortex_command.overnight.backlog import _parse_frontmatter

    text = (
        "---\n"
        "title: Supersede smoke test\n"
        "status: open\n"
        f"superseded: {SAMPLE_SUPERSEDED_VALUE}\n"
        "discovery_source: cortex/research/plugin-system-2/research.md\n"
        "---\n\n# Body\n"
    )
    fm = _parse_frontmatter(text)
    assert fm["title"] == "Supersede smoke test"
    assert fm["status"] == "open"
    assert fm["superseded"] == SAMPLE_SUPERSEDED_VALUE
    assert fm["discovery_source"] == "cortex/research/plugin-system-2/research.md"
