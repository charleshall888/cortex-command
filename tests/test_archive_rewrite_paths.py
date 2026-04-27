"""Unit tests for ``bin/cortex-archive-rewrite-paths``.

Covers the path-rewriting helper invoked by the lifecycle-archive recipe
(N6.3). The helper must rewrite three citation forms across ``*.md`` files
without colliding on substring slugs and without touching the four excluded
directories. See spec.md §N6.3 and plan.md Task 12 for the contract.

Cases covered:
  - Slash form (``lifecycle/<slug>/...``) is rewritten.
  - Wikilink form is rewritten across all four terminator variants
    (``]``, ``/``, ``|``, ``/index``).
  - Bare form (``lifecycle/<slug>`` with no trailing slash) is rewritten when
    bordered by non-word characters.
  - Substring collision: ``lifecycle/add-foo`` does NOT match inside
    ``lifecycle/add-foo-bar`` (boundary char class treats ``-`` as
    word-equivalent).
  - Slug containing regex metacharacters is escaped via ``re.escape()``.
  - Atomic-write side effect: no leftover ``.tmp-archive-rewrite`` files.
  - Excluded directories (``.git/``, ``lifecycle/archive/``,
    ``lifecycle/sessions/``, ``retros/``) are not walked.
  - ``--dry-run`` does not modify files.
  - JSON-on-stdout protocol: one object per slug with the right shape.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-archive-rewrite-paths"


def _load_module():
    """Load the helper script as an importable module for in-process tests.

    The script has no ``.py`` suffix (it ships as a CLI tool) so we must
    pass an explicit ``SourceFileLoader`` to ``spec_from_file_location``.
    """
    loader = importlib.machinery.SourceFileLoader(
        "cortex_archive_rewrite_paths", str(SCRIPT_PATH)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def helper():
    return _load_module()


# ---------------------------------------------------------------------------
# Pure-function tests on rewrite_text — fast, no filesystem
# ---------------------------------------------------------------------------


def test_slash_form_rewritten(helper):
    src = "see lifecycle/add-foo/research.md for context"
    out = helper.rewrite_text(src, "add-foo")
    assert out == "see lifecycle/archive/add-foo/research.md for context"


def test_slash_form_at_line_start(helper):
    src = "lifecycle/add-foo/spec.md"
    out = helper.rewrite_text(src, "add-foo")
    assert out == "lifecycle/archive/add-foo/spec.md"


def test_wikilink_terminator_close_bracket(helper):
    src = "[[lifecycle/foo]]"
    out = helper.rewrite_text(src, "foo")
    assert out == "[[lifecycle/archive/foo]]"


def test_wikilink_terminator_trailing_slash(helper):
    src = "[[lifecycle/foo/]]"
    out = helper.rewrite_text(src, "foo")
    assert out == "[[lifecycle/archive/foo/]]"


def test_wikilink_terminator_pipe_display(helper):
    src = "[[lifecycle/foo|display text]]"
    out = helper.rewrite_text(src, "foo")
    assert out == "[[lifecycle/archive/foo|display text]]"


def test_wikilink_terminator_slash_path(helper):
    src = "[[lifecycle/foo/index]]"
    out = helper.rewrite_text(src, "foo")
    assert out == "[[lifecycle/archive/foo/index]]"


def test_bare_form_with_trailing_punctuation(helper):
    src = "see lifecycle/foo. The end."
    out = helper.rewrite_text(src, "foo")
    assert out == "see lifecycle/archive/foo. The end."


def test_bare_form_at_end_of_line(helper):
    src = "ref: lifecycle/foo"
    out = helper.rewrite_text(src, "foo")
    assert out == "ref: lifecycle/archive/foo"


def test_substring_collision_add_foo_does_not_match_in_add_foo_bar(helper):
    """The boundary char class treats ``-`` as word-equivalent so
    ``add-foo`` must NOT match inside ``add-foo-bar``."""
    src = "see lifecycle/add-foo-bar/research.md and lifecycle/add-foo/spec.md"
    out = helper.rewrite_text(src, "add-foo")
    # The longer slug stays untouched; the exact slug rewrites.
    assert "lifecycle/add-foo-bar/research.md" in out
    assert "lifecycle/archive/add-foo/spec.md" in out
    # And the wrong rewrite never happens:
    assert "lifecycle/archive/add-foo-bar" not in out


def test_substring_collision_in_wikilink(helper):
    src = "[[lifecycle/add-foo-bar]] and [[lifecycle/add-foo]]"
    out = helper.rewrite_text(src, "add-foo")
    assert "[[lifecycle/add-foo-bar]]" in out
    assert "[[lifecycle/archive/add-foo]]" in out


def test_substring_collision_bare_form(helper):
    src = "lifecycle/add-foo-bar lifecycle/add-foo"
    out = helper.rewrite_text(src, "add-foo")
    assert "lifecycle/add-foo-bar" in out
    assert "lifecycle/archive/add-foo" in out
    assert "lifecycle/archive/add-foo-bar" not in out


def test_already_archived_path_not_rewritten_twice(helper):
    """The boundary class treats ``/`` as word-equivalent so
    ``lifecycle/archive/foo`` must NOT match the bare or slash patterns
    (the leading boundary fails on the ``/`` after ``lifecycle``)."""
    src = "see lifecycle/archive/foo/research.md"
    out = helper.rewrite_text(src, "foo")
    assert out == "see lifecycle/archive/foo/research.md"


def test_slug_with_regex_metacharacters_is_escaped(helper):
    """``re.escape()`` must protect slug values containing regex specials.
    Use a contrived slug containing ``.`` and ``+`` so we exercise the
    escape path without relying on a real-world filename."""
    slug = "weird.name+v2"
    src = f"see lifecycle/{slug}/research.md"
    out = helper.rewrite_text(src, slug)
    assert out == f"see lifecycle/archive/{slug}/research.md"
    # The unescaped form would also match a non-literal alternative; verify
    # the regex is treating ``.`` and ``+`` as literal by feeding a near-miss
    # that should NOT match.
    near = "see lifecycle/weirdXnameXv2/research.md"
    out2 = helper.rewrite_text(near, slug)
    assert out2 == near


def test_pattern_order_slash_before_bare(helper):
    """Slash must run before bare so ``lifecycle/foo/`` is not stolen
    by the bare pattern (which matches ``lifecycle/foo`` followed by ``/``,
    treated as a word-equivalent boundary, so it would NOT match anyway —
    but verify by construction that slash form rewrites the path correctly
    in a single pass)."""
    src = "lifecycle/foo/ and lifecycle/foo and lifecycle/foo."
    out = helper.rewrite_text(src, "foo")
    assert out == (
        "lifecycle/archive/foo/ and lifecycle/archive/foo and "
        "lifecycle/archive/foo."
    )


def test_multiple_occurrences_in_one_string(helper):
    src = "lifecycle/foo/a and lifecycle/foo/b and [[lifecycle/foo]]"
    out = helper.rewrite_text(src, "foo")
    assert out == (
        "lifecycle/archive/foo/a and lifecycle/archive/foo/b "
        "and [[lifecycle/archive/foo]]"
    )


def test_no_match_returns_input_unchanged(helper):
    src = "no references here"
    assert helper.rewrite_text(src, "foo") == src


# ---------------------------------------------------------------------------
# Filesystem tests on rewrite_for_slug — atomic write, exclusions, --dry-run
# ---------------------------------------------------------------------------


def _setup_repo(tmp_path: Path) -> Path:
    """Create a small repo-like tree with .md files in various locations."""
    root = tmp_path / "repo"
    root.mkdir()
    # Citer in a regular doc
    (root / "docs").mkdir()
    (root / "docs" / "ops.md").write_text(
        "see lifecycle/foo/research.md for details\n", encoding="utf-8"
    )
    # Citer in a top-level README
    (root / "README.md").write_text(
        "[[lifecycle/foo|the foo feature]]\n", encoding="utf-8"
    )
    # Excluded: lifecycle/archive
    (root / "lifecycle" / "archive" / "old").mkdir(parents=True)
    (root / "lifecycle" / "archive" / "old" / "notes.md").write_text(
        "lifecycle/foo/research.md (must NOT be rewritten — excluded)\n",
        encoding="utf-8",
    )
    # Excluded: lifecycle/sessions
    (root / "lifecycle" / "sessions" / "20250101").mkdir(parents=True)
    (root / "lifecycle" / "sessions" / "20250101" / "log.md").write_text(
        "lifecycle/foo (excluded session log)\n", encoding="utf-8"
    )
    # Excluded: retros
    (root / "retros").mkdir()
    (root / "retros" / "2025-01-01.md").write_text(
        "lifecycle/foo (excluded retro)\n", encoding="utf-8"
    )
    # Excluded: .git
    (root / ".git").mkdir()
    (root / ".git" / "COMMIT_EDITMSG.md").write_text(
        "lifecycle/foo (excluded git internal)\n", encoding="utf-8"
    )
    # Non-md file: should not be touched even if it cites
    (root / "scripts").mkdir()
    (root / "scripts" / "tool.py").write_text(
        "# lifecycle/foo (non-md, out of scope)\n", encoding="utf-8"
    )
    return root


def test_rewrite_for_slug_writes_in_place_and_skips_excluded(helper, tmp_path):
    root = _setup_repo(tmp_path)
    rewritten = helper.rewrite_for_slug(root, "foo", dry_run=False)
    # Both citers in scope were rewritten
    assert sorted(rewritten) == ["README.md", "docs/ops.md"]
    assert (root / "docs" / "ops.md").read_text(encoding="utf-8") == (
        "see lifecycle/archive/foo/research.md for details\n"
    )
    assert (root / "README.md").read_text(encoding="utf-8") == (
        "[[lifecycle/archive/foo|the foo feature]]\n"
    )
    # Excluded files are untouched
    assert "lifecycle/foo" in (
        root / "lifecycle" / "archive" / "old" / "notes.md"
    ).read_text(encoding="utf-8")
    assert "lifecycle/foo" in (
        root / "lifecycle" / "sessions" / "20250101" / "log.md"
    ).read_text(encoding="utf-8")
    assert "lifecycle/foo" in (
        root / "retros" / "2025-01-01.md"
    ).read_text(encoding="utf-8")
    assert "lifecycle/foo" in (
        root / ".git" / "COMMIT_EDITMSG.md"
    ).read_text(encoding="utf-8")
    # Non-md file untouched (out of scope)
    assert "lifecycle/foo" in (
        root / "scripts" / "tool.py"
    ).read_text(encoding="utf-8")


def test_dry_run_does_not_modify_files(helper, tmp_path):
    root = _setup_repo(tmp_path)
    before_ops = (root / "docs" / "ops.md").read_text(encoding="utf-8")
    before_readme = (root / "README.md").read_text(encoding="utf-8")
    rewritten = helper.rewrite_for_slug(root, "foo", dry_run=True)
    # Returned list still reports what WOULD have been rewritten
    assert sorted(rewritten) == ["README.md", "docs/ops.md"]
    # But the files are unchanged on disk
    assert (root / "docs" / "ops.md").read_text(encoding="utf-8") == before_ops
    assert (root / "README.md").read_text(encoding="utf-8") == before_readme


def test_no_temp_files_left_behind(helper, tmp_path):
    root = _setup_repo(tmp_path)
    helper.rewrite_for_slug(root, "foo", dry_run=False)
    leftovers = list(root.rglob("*.tmp-archive-rewrite"))
    assert leftovers == []


def test_rewrite_for_slug_no_match_returns_empty(helper, tmp_path):
    root = tmp_path / "empty-repo"
    root.mkdir()
    (root / "doc.md").write_text("nothing to see here\n", encoding="utf-8")
    rewritten = helper.rewrite_for_slug(root, "nonexistent", dry_run=False)
    assert rewritten == []
    assert (root / "doc.md").read_text(encoding="utf-8") == "nothing to see here\n"


# ---------------------------------------------------------------------------
# CLI / subprocess tests — argparse, JSON stdout protocol
# ---------------------------------------------------------------------------


def test_cli_emits_one_json_object_per_slug(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "doc.md").write_text(
        "see lifecycle/alpha/spec.md and lifecycle/beta/research.md\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--slug",
            "alpha",
            "--slug",
            "beta",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["slug"] == "alpha"
    assert parsed[0]["rewritten_files"] == ["doc.md"]
    assert parsed[1]["slug"] == "beta"
    assert parsed[1]["rewritten_files"] == ["doc.md"]
    # And the file itself was rewritten in place
    assert (root / "doc.md").read_text(encoding="utf-8") == (
        "see lifecycle/archive/alpha/spec.md and "
        "lifecycle/archive/beta/research.md\n"
    )


def test_cli_dry_run_does_not_modify_files(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "doc.md").write_text(
        "see lifecycle/alpha/spec.md\n", encoding="utf-8"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--slug",
            "alpha",
            "--dry-run",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed = json.loads(result.stdout.strip())
    assert parsed == {"slug": "alpha", "rewritten_files": ["doc.md"]}
    # File untouched
    assert (root / "doc.md").read_text(encoding="utf-8") == (
        "see lifecycle/alpha/spec.md\n"
    )


def test_cli_requires_slug_argument():
    """``--slug`` is required; missing it must exit non-zero."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--slug" in result.stderr


def test_cli_rejects_nonexistent_root(tmp_path):
    missing = tmp_path / "does-not-exist"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--slug",
            "foo",
            "--root",
            str(missing),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not a directory" in result.stderr
