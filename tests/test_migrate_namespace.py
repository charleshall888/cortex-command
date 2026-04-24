"""Tests for ``scripts/migrate-namespace.py`` — the scoped namespace rewrite tool.

Covers:
  - Positive prose rewrite (bare ``/commit``, ``/lifecycle`` -> ``/cortex:*``)
  - Positive YAML frontmatter quoted form (``"/commit"`` -> ``"/cortex:commit"``)
  - Positive sentence-terminating period (``/commit.`` -> ``/cortex:commit.``)
  - Skip: top-level ``research/`` (epic-research artifacts, NOT the shipped skill)
  - Positive: nested ``skills/research/`` IS rewritten (component-anchor
    does not collide with substring)
  - Skip: ``retros/`` (historical session logs)
  - Skip: URLs (``https://github.com/foo/commit/abc123``)
  - Skip: relative-path segments (``./commit/hook.sh``, ``src/pr/util.py``)
  - Idempotence: second ``--mode apply`` produces zero rewrites
    (``--verify`` exits 0)
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate-namespace.py"
FIXTURE_SRC = REPO_ROOT / "tests" / "fixtures" / "migrate_namespace"


def _load_module():
    """Load migrate-namespace.py as an importable module for in-process tests."""
    spec = importlib.util.spec_from_file_location(
        "migrate_namespace", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    """Copy the seeded fixture directory into a writable tmp_path and return it."""
    dest = tmp_path / "migrate_namespace"
    shutil.copytree(FIXTURE_SRC, dest)
    return dest


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke migrate-namespace.py as a subprocess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_exits_zero():
    """``--help`` must exit 0 (smoke test for CLI wiring)."""
    result = _run_cli(["--help"])
    assert result.returncode == 0
    assert "migrate-namespace" in result.stdout


def test_positive_prose_rewrite(fixture_tree: Path):
    """Bare ``/commit`` and ``/lifecycle`` in prose are rewritten to ``/cortex:*``."""
    target = fixture_tree / "docs" / "sample.md"
    result = _run_cli(["--include", str(target), "--mode", "apply"])
    assert result.returncode == 0
    content = target.read_text(encoding="utf-8")
    assert "/cortex:commit" in content
    assert "/cortex:lifecycle" in content
    # Ensure the plain form no longer appears as a standalone token.
    # A negative space+slash lookaround is sufficient because the fixture has
    # no other legitimate uses.
    assert " /commit " not in content
    assert " /lifecycle " not in content


def test_positive_yaml_quoted_frontmatter(fixture_tree: Path):
    """The quoted form ``"/commit"`` inside YAML frontmatter is rewritten."""
    target = fixture_tree / "docs" / "frontmatter.md"
    result = _run_cli(["--include", str(target), "--mode", "apply"])
    assert result.returncode == 0
    content = target.read_text(encoding="utf-8")
    assert '"/cortex:commit"' in content
    assert '"/commit"' not in content


def test_positive_sentence_terminating_period(fixture_tree: Path):
    """``/commit.`` (sentence-end) is rewritten to ``/cortex:commit.``."""
    target = fixture_tree / "docs" / "period.md"
    result = _run_cli(["--include", str(target), "--mode", "apply"])
    assert result.returncode == 0
    content = target.read_text(encoding="utf-8")
    assert "/cortex:commit." in content
    # Bare form must not remain.
    assert " /commit." not in content
    assert content.startswith("Use /cortex:commit.") or "Use /cortex:commit." in content


def test_skip_top_level_research_dir(fixture_tree: Path):
    """Files under the top-level ``research/`` tree are NOT rewritten.

    Uses a directory include so path components are evaluated relative to
    the include root (matching production use, where callers pass the repo
    root to ``--include``).
    """
    target = fixture_tree / "research" / "seed.md"
    original = target.read_bytes()
    result = _run_cli(["--include", str(fixture_tree), "--mode", "apply"])
    assert result.returncode == 0
    assert target.read_bytes() == original, (
        "research/ fixture contents must be byte-identical after apply; "
        "top-level research/ is a skip-list root."
    )


def test_nested_skills_research_is_rewritten(fixture_tree: Path):
    """``skills/research/`` IS rewritten — only top-level ``research/`` is skipped.

    Guards against a naive ``'research' in str(path)`` substring check that
    would also exclude the shipped ``research`` skill under ``skills/``.
    Uses a directory include so the ``research`` component appears at
    ``parts[1]`` (not ``parts[0]``) and therefore is NOT treated as the
    top-level skip anchor.
    """
    target = fixture_tree / "skills" / "research" / "seed.md"
    result = _run_cli(["--include", str(fixture_tree), "--mode", "apply"])
    assert result.returncode == 0
    content = target.read_text(encoding="utf-8")
    assert "/cortex:research" in content


def test_skip_retros(fixture_tree: Path):
    """Files under ``retros/`` are NOT rewritten (historical session logs).

    Uses a directory include so ``retros`` appears as a path component
    during skip-rule evaluation (matches production usage).
    """
    target = fixture_tree / "retros" / "seed.md"
    original = target.read_bytes()
    result = _run_cli(["--include", str(fixture_tree), "--mode", "apply"])
    assert result.returncode == 0
    assert target.read_bytes() == original


def test_skip_url_substring(fixture_tree: Path):
    """URL paths like ``https://github.com/foo/commit/abc123`` are untouched."""
    target = fixture_tree / "docs" / "url.md"
    original = target.read_bytes()
    result = _run_cli(["--include", str(target), "--mode", "apply"])
    assert result.returncode == 0
    assert target.read_bytes() == original


def test_skip_relative_path_segment(fixture_tree: Path):
    """Relative paths like ``./commit/hook.sh`` and ``src/pr/util.py`` are untouched."""
    target = fixture_tree / "docs" / "relpath.md"
    original = target.read_bytes()
    result = _run_cli(["--include", str(target), "--mode", "apply"])
    assert result.returncode == 0
    assert target.read_bytes() == original


def test_idempotence_via_verify(fixture_tree: Path):
    """Running ``--mode apply`` twice produces zero changes on the second run.

    ``--verify`` after a first apply exits 0 (no further changes queued).
    """
    # First apply — mutates files where rewrites are warranted.
    first = _run_cli(["--include", str(fixture_tree), "--mode", "apply"])
    assert first.returncode == 0

    # Second apply — should produce zero rewrites across the entire fixture tree.
    second = _run_cli(["--include", str(fixture_tree), "--mode", "apply"])
    assert second.returncode == 0
    assert "Rewrote 0 references" in second.stdout

    # --verify must exit 0 when no further changes would occur.
    verify = _run_cli(["--include", str(fixture_tree), "--verify"])
    assert verify.returncode == 0, (
        f"--verify after double-apply must exit 0; got {verify.returncode}. "
        f"stdout={verify.stdout!r} stderr={verify.stderr!r}"
    )


def test_verify_exits_one_when_changes_pending(fixture_tree: Path):
    """``--verify`` on a fresh (un-migrated) tree exits 1."""
    # Target a single prose fixture known to contain rewritable content.
    target = fixture_tree / "docs" / "sample.md"
    result = _run_cli(["--include", str(target), "--verify"])
    assert result.returncode == 1


def test_dry_run_does_not_mutate(fixture_tree: Path):
    """Default ``dry-run`` mode reports changes but leaves files unchanged."""
    target = fixture_tree / "docs" / "sample.md"
    original = target.read_bytes()
    result = _run_cli(["--include", str(target)])  # default mode=dry-run
    assert result.returncode == 0
    assert target.read_bytes() == original
    assert "/commit" in result.stdout  # rewrite was reported


def test_critical_review_not_partial_matched_as_critical(tmp_path: Path):
    """Allowlist alternation sorts longest-first; ``critical-review`` must match whole."""
    module = _load_module()
    line = "Invoke /critical-review after plan approval."
    new, rewrites = module.rewrite_line(line)
    assert "/cortex:critical-review" in new
    assert rewrites == ["critical-review"]
