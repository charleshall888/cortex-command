"""Tests for cortex_command/dashboard/docs/edit.py.

A tmp_path root with a couple of files and a hand-built Corpus whose nodes
point at them. Each test names the rail it pins.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from cortex_command.dashboard.docs.edit import (
    content_hash,
    read_for_edit,
    save_doc,
)
from cortex_command.dashboard.docs.model import Corpus, DocNode


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "CLAUDE.md").write_text("# Claude\n\nrules\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "setup.md").write_text("# Setup\n", encoding="utf-8")
    (tmp_path / "docs" / "link.md").symlink_to(tmp_path / "CLAUDE.md")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (tmp_path / "docs" / "escape.md").symlink_to(outside)
    return tmp_path


@pytest.fixture
def corpus(root: Path) -> Corpus:
    c = Corpus(root=root)
    for n in (
        DocNode(path="CLAUDE.md", kind="constitution", title="Claude", governing=True),
        DocNode(path="docs/setup.md", kind="doc", title="Setup", governing=False),
        DocNode(path="docs/link.md", kind="policy", title="Link", governing=True),
        DocNode(path="docs/escape.md", kind="policy", title="Escape", governing=True),
        DocNode(path="docs/ghost.md", kind="policy", title="Ghost", governing=False, exists=False),
    ):
        c.nodes[n.path] = n
    return c


def test_happy_path(root, corpus):
    """A save with the current sha writes the new text and returns its hash."""
    view = read_for_edit(root, corpus, "CLAUDE.md")
    assert view is not None and view.text == "# Claude\n\nrules\n"
    assert view.sha == content_hash(view.text)
    res = save_doc(root, corpus, "CLAUDE.md", "# Claude\n\nnew rules\n", view.sha)
    assert res.ok and res.reason is None and res.disk_text is None
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "# Claude\n\nnew rules\n"
    assert res.sha == content_hash("# Claude\n\nnew rules\n")
    assert not [p for p in (root).iterdir() if p.name.endswith(".tmp")]


def test_conflict(root, corpus):
    """A stale sha is refused, the disk is untouched, and the disk text comes back."""
    view = read_for_edit(root, corpus, "CLAUDE.md")
    (root / "CLAUDE.md").write_text("# Claude\n\nsomeone else\n", encoding="utf-8")
    res = save_doc(root, corpus, "CLAUDE.md", "# Claude\n\nmine\n", view.sha)
    assert not res.ok and res.reason == "conflict"
    assert res.disk_text == "# Claude\n\nsomeone else\n"
    assert res.sha == content_hash(res.disk_text)
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "# Claude\n\nsomeone else\n"


def test_non_governing_refused(root, corpus):
    """Non-governing, ghost and unknown paths are not readable or writable."""
    for path in ("docs/setup.md", "docs/ghost.md", "nope.md", "../etc/passwd"):
        assert read_for_edit(root, corpus, path) is None
        res = save_doc(root, corpus, path, "x\n", content_hash("# Setup\n"))
        assert not res.ok and res.reason == "not-governing"
    assert (root / "docs" / "setup.md").read_text(encoding="utf-8") == "# Setup\n"


def test_symlink_refused(root, corpus):
    """A symlinked node is refused even when listed as governing, whether it points inside or outside the root."""
    for path in ("docs/link.md", "docs/escape.md"):
        assert read_for_edit(root, corpus, path) is None
        res = save_doc(root, corpus, path, "x\n", content_hash("# Claude\n\nrules\n"))
        assert not res.ok and res.reason == "symlink"
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "# Claude\n\nrules\n"


def test_unchanged(root, corpus):
    """Identical bytes are reported as unchanged (ok) without rewriting the file."""
    view = read_for_edit(root, corpus, "CLAUDE.md")
    before = (root / "CLAUDE.md").stat().st_mtime_ns
    res = save_doc(root, corpus, "CLAUDE.md", view.text, view.sha)
    assert res.ok and res.reason == "unchanged" and res.sha == view.sha
    assert (root / "CLAUDE.md").stat().st_mtime_ns == before


def test_crlf_normalised(root, corpus):
    """Browser CRLF submissions land as LF with exactly one trailing newline."""
    view = read_for_edit(root, corpus, "CLAUDE.md")
    res = save_doc(root, corpus, "CLAUDE.md", "# Claude\r\n\r\nrules\r\nmore\r\n\r\n\r\n", view.sha)
    assert res.ok and res.reason is None
    assert (root / "CLAUDE.md").read_bytes() == b"# Claude\n\nrules\nmore\n"
    # And CRLF that normalises to the disk bytes is 'unchanged', not a rewrite.
    res2 = save_doc(root, corpus, "CLAUDE.md", "# Claude\r\n\r\nrules\r\nmore", res.sha)
    assert res2.ok and res2.reason == "unchanged"


def test_mode_preserved(root, corpus):
    """The replaced file keeps the original permission bits."""
    target = root / "CLAUDE.md"
    os.chmod(target, 0o640)
    view = read_for_edit(root, corpus, "CLAUDE.md")
    res = save_doc(root, corpus, "CLAUDE.md", "# changed\n", view.sha)
    assert res.ok
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
