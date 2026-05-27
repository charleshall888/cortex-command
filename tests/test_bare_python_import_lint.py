"""Tests for cortex_command.lint.bare_python_import (L201).

Coverage:
  - test_positive_fixture_yields_eight_violations: ≥8 violations from positive.md
  - test_negative_fixture_yields_zero_violations: 0 violations from negative.md
  - test_live_skills_corpus_clean: post-Task-1 implement.md has no L201 violations
  - test_find_spec_regression_caught: the §1 probe text verbatim yields ≥1 violation
  - Individual positive cases (Rules 1-4 + dynamic imports)
  - Individual negative cases (stdlib-only, prose-only, inline-code-span, sentinel forms)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.lint.bare_python_import import scan_text, Violation

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "bare_python_import"
POSITIVE_MD = FIXTURES / "positive.md"
NEGATIVE_MD = FIXTURES / "negative.md"


# ---------------------------------------------------------------------------
# Fixture-based tests
# ---------------------------------------------------------------------------


def test_positive_fixture_yields_eight_violations() -> None:
    """positive.md should yield ≥8 L201 violations — one per positive case."""
    text = POSITIVE_MD.read_text(encoding="utf-8")
    violations = scan_text(text, POSITIVE_MD)
    assert len(violations) >= 8, (
        f"Expected ≥8 violations from positive.md, got {len(violations)}: "
        + "\n".join(v.format_text() for v in violations)
    )
    # All violations should carry the L201 code.
    for v in violations:
        assert v.code == "L201", f"Unexpected code {v.code!r}: {v}"


def test_negative_fixture_yields_zero_violations() -> None:
    """negative.md should yield 0 L201 violations."""
    text = NEGATIVE_MD.read_text(encoding="utf-8")
    violations = scan_text(text, NEGATIVE_MD)
    assert violations == [], (
        f"Expected 0 violations from negative.md, got {len(violations)}:\n"
        + "\n".join(v.format_text() for v in violations)
    )


def test_live_skills_corpus_clean() -> None:
    """Post-Task-1 implement.md must contain zero L201 violations."""
    impl_md = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"
    assert impl_md.exists(), f"Expected file: {impl_md}"
    text = impl_md.read_text(encoding="utf-8")
    violations = scan_text(text, impl_md)
    assert violations == [], (
        f"skills/lifecycle/references/implement.md has bare-Python cortex_command "
        f"imports that should have been removed in Task 1:\n"
        + "\n".join(v.format_text() for v in violations)
    )


def test_find_spec_regression_caught() -> None:
    """The §1 probe text verbatim (find_spec form) must yield ≥1 violation.

    This pins the regression-prevention contract: the dynamic-import family
    in the regex catches the exact probe that was removed in Task 1, so a
    verbatim reintroduction would fail the lint.
    """
    probe_text = (
        "```python\n"
        "import sys\n"
        "import importlib.util\n"
        "sys.exit(0 if importlib.util.find_spec('cortex_command') is not None else 1)\n"
        "```\n"
    )
    violations = scan_text(probe_text, Path("regression-probe.md"))
    assert len(violations) >= 1, (
        "Expected ≥1 violation for the §1 find_spec probe text, got 0. "
        "The dynamic-import regex is not covering find_spec('cortex_command')."
    )


# ---------------------------------------------------------------------------
# Individual positive cases (one test per rule)
# ---------------------------------------------------------------------------


def test_rule1_labeled_fence_python() -> None:
    """Rule 1: labeled ```python fence with import cortex_command."""
    text = "```python\nimport cortex_command\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 1 (labeled python fence) should flag"


def test_rule1_labeled_fence_py_variant() -> None:
    """Rule 1: labeled ```py fence with from cortex_command... import."""
    text = "```py\nfrom cortex_command.pipeline import create_worktree\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 1 (labeled py fence) should flag"


def test_rule1_labeled_fence_python3_variant() -> None:
    """Rule 1: labeled ```python3 fence."""
    text = "```python3\nimport cortex_command\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 1 (labeled python3 fence) should flag"


def test_rule2_python3_c_single_line_in_prose() -> None:
    """Rule 2: python3 -c single-line in prose (unfenced)."""
    text = 'Run: python3 -c "import cortex_command"\n'
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 2 (python3 -c in prose) should flag"


def test_rule2_python3_c_multiline() -> None:
    """Rule 2: multi-line python3 -c with embedded newline in double-quotes."""
    text = 'python3 -c "\nimport cortex_command\nprint(\'done\')\n"\n'
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 2 (multi-line python3 -c) should flag"


def test_rule3_heredoc() -> None:
    """Rule 3: python3 - <<EOF heredoc with import cortex_command."""
    text = "python3 - <<EOF\nimport cortex_command\nEOF\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 3 (heredoc) should flag"


def test_rule4_python3_c_inside_unlabeled_fence() -> None:
    """Rule 4: python3 -c invocation inside an unlabeled fence."""
    text = "```\npython3 -c \"import cortex_command\"\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Rule 4 (python3 -c inside unlabeled fence) should flag"


def test_dynamic_import_find_spec() -> None:
    """Dynamic-import: find_spec('cortex_command') inside labeled fence."""
    text = "```bash\npython3 -c \"import importlib.util; importlib.util.find_spec('cortex_command')\"\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Dynamic find_spec should flag"


def test_dynamic_import_import_module() -> None:
    """Dynamic-import: import_module('cortex_command') inside labeled fence."""
    text = "```bash\npython3 -c \"import importlib; importlib.import_module('cortex_command')\"\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "Dynamic import_module should flag"


def test_dynamic_import_dunder_import() -> None:
    """Dynamic-import: __import__('cortex_command')."""
    text = "```python\n__import__('cortex_command')\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert len(violations) >= 1, "__import__ should flag"


# ---------------------------------------------------------------------------
# Individual negative cases
# ---------------------------------------------------------------------------


def test_negative_stdlib_only_python3_c() -> None:
    """Stdlib-only python3 -c invocation should not flag."""
    text = 'python3 -c "import json,sys; print(json.loads(sys.stdin.read()))"\n'
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Stdlib-only python3 -c should not flag, got: {violations}"


def test_negative_narrative_prose_mention() -> None:
    """Plain narrative prose mentioning cortex_command module path should not flag."""
    text = (
        "The module cortex_command.pipeline.worktree provides worktree creation.\n"
        "Read about it in the docs.\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Narrative prose should not flag, got: {violations}"


def test_negative_inline_code_span() -> None:
    """Inline-code span `python3 -c "import cortex_command"` should not flag (Rule 5)."""
    text = '`python3 -c "import cortex_command"` — this is a code-span, not live code.\n'
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Inline-code span should not flag, got: {violations}"


def test_negative_sentinel_immediate() -> None:
    """Sentinel immediately before a labeled fence suppresses the violation."""
    text = (
        "<!-- bare-python-lint:ignore-next -->\n"
        "```python\n"
        "import cortex_command\n"
        "```\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Sentinel-immediate should suppress, got: {violations}"


def test_negative_sentinel_with_blank_line() -> None:
    """Sentinel with an intervening blank line still suppresses (prev_nonblank pattern)."""
    text = (
        "<!-- bare-python-lint:ignore-next -->\n"
        "\n"
        "```python\n"
        "import cortex_command\n"
        "```\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert violations == [], (
        f"Sentinel-with-blank-line should suppress via prev_nonblank, got: {violations}"
    )


def test_negative_two_sentinels_before_two_regions() -> None:
    """Two consecutive sentinel+region pairs — both regions suppressed (N-to-N positional)."""
    text = (
        "<!-- bare-python-lint:ignore-next -->\n"
        "\n"
        "```python\n"
        "import cortex_command\n"
        "```\n"
        "\n"
        "<!-- bare-python-lint:ignore-next -->\n"
        "\n"
        "```python\n"
        "from cortex_command.pipeline import create_worktree\n"
        "```\n"
    )
    violations = scan_text(text, Path("test.md"))
    assert violations == [], (
        f"Two-sentinels-before-two-regions should suppress both, got: {violations}"
    )


def test_negative_from_import_no_cortex() -> None:
    """from cortex_not_command import x should not flag."""
    text = "```python\nfrom cortex_not_command import foo\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Non-cortex_command import should not flag, got: {violations}"


def test_negative_import_stdlib_in_labeled_fence() -> None:
    """Pure stdlib import in a labeled fence should not flag."""
    text = "```python\nimport sys\nimport os\n```\n"
    violations = scan_text(text, Path("test.md"))
    assert violations == [], f"Stdlib imports in labeled fence should not flag, got: {violations}"


def test_staged_glob_matches_deep_skills_path() -> None:
    """Regression: --staged mode must recognize deep skills/ paths via ** recursion.

    Path.match("skills/**/*.md") treats ** as a single component and returns False
    for skills/lifecycle/references/implement.md — silently skipping the actual
    scan corpus during pre-commit. _matches_scan_glob must use full_match.
    """
    from cortex_command.lint.bare_python_import import _matches_scan_glob

    assert _matches_scan_glob("skills/lifecycle/references/implement.md"), (
        "deep skills/ path must match skills/**/*.md glob — pre-commit hook depends on it"
    )
    assert _matches_scan_glob("docs/internals/pipeline.md"), (
        "deep docs/ path must match docs/**/*.md glob"
    )
    assert _matches_scan_glob("CLAUDE.md"), "root CLAUDE.md must match"
    assert not _matches_scan_glob("cortex_command/lint/bare_python_import.py"), (
        "python source files outside the corpus must not match"
    )
