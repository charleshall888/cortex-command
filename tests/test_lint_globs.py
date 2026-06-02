"""Truth-table unit test for the shared glob-membership matcher.

Locks every one of the nine Edge Case rows from
``cortex/lifecycle/pre-commit-gates-silently-skip-deep/spec.md`` so the
``**``=zero-or-more-segments semantics cannot silently regress to
``Path.match`` (``**``=exactly-one-segment) or bare ``fnmatch``.

Each row carries a ``row`` id naming the truth-table shape it asserts. On
Python 3.13+ the matcher is additionally cross-checked against
``glob.translate(pat, recursive=True, include_hidden=True)`` as a behavioral
oracle; that API is 3.13-only and is used here *only* as a test oracle — the
matcher itself stays stdlib-3.12-safe (verified by ``test_no_py313_only_api``).
"""

from __future__ import annotations

import re

import pytest

from cortex_command.lint._globs import matches_any_glob

# (row id, rel_path, glob, expected) — one or more rows per truth-table shape.
# Every one of the nine Edge Case shapes in spec.md §Edge Cases is represented.
TRUTH_TABLE = [
    # Row 1 — depth-1 against dir/**/*.ext (the bug's core miss).
    ("depth-1", "docs/agentic-layer.md", "docs/**/*.md", True),
    # Row 2 — depth-2 against dir/**/*.ext.
    ("depth-2", "docs/internals/pipeline.md", "docs/**/*.md", True),
    # Row 3 — depth-≥3 against dir/**/*.ext.
    ("depth-3", "skills/lifecycle/references/implement.md", "skills/**/*.md", True),
    # Row 4 — single-* over-scan rejection (* must not cross '/').
    ("star-overscan-reject", "cortex/backlog/sub/x.md", "cortex/backlog/*.md", False),
    # Row 5 — deep literal-prefix single-* (interior-segment anchoring).
    (
        "deep-litprefix-in",
        "cortex_command/overnight/prompts/plan-synthesizer.md",
        "cortex_command/overnight/prompts/*.md",
        True,
    ),
    (
        "deep-litprefix-reject",
        "cortex_command/overnight/prompts/sub/x.md",
        "cortex_command/overnight/prompts/*.md",
        False,
    ),
    # Row 6 — bare trailing ** matches files at depth-1 and deeper.
    ("bare-star-depth1", "hooks/cortex-cleanup-session.sh", "hooks/**", True),
    ("bare-star-deeper", "hooks/sub/cortex-x.sh", "hooks/**", True),
    # Row 7 — exact-name literal is anchored (no tail-match).
    ("exact-literal-in", "justfile", "justfile", True),
    ("exact-literal-claude", "CLAUDE.md", "CLAUDE.md", True),
    ("exact-literal-reject", "sub/CLAUDE.md", "CLAUDE.md", False),
    # Row 8 — single-* with directory prefix discriminates the prefix.
    ("dirprefix-star-in", "hooks/cortex-foo.sh", "hooks/cortex-*.sh", True),
    ("dirprefix-star-reject", "claude/hooks/cortex-x.sh", "hooks/cortex-*.sh", False),
    # Row 9 — hidden (dot) files are in-scope (include_hidden-equivalent).
    ("hidden-file-in", "tests/fixtures/.parity-exceptions.md", "tests/**/*.md", True),
]


@pytest.mark.parametrize(
    "rel_path, glob, expected",
    [(r[1], r[2], r[3]) for r in TRUTH_TABLE],
    ids=[r[0] for r in TRUTH_TABLE],
)
def test_matches_any_glob_truth_table(rel_path: str, glob: str, expected: bool) -> None:
    """Each truth-table row: matcher membership equals the spec's expected value."""
    assert matches_any_glob(rel_path, (glob,)) is expected


def test_matches_any_glob_returns_true_when_any_glob_matches() -> None:
    """A path matching the 2nd glob in a tuple is in-scope (any-semantics)."""
    globs = ("cortex/backlog/*.md", "skills/**/*.md")
    assert matches_any_glob("skills/lifecycle/references/implement.md", globs) is True


def test_matches_any_glob_false_when_no_glob_matches() -> None:
    """A path matching no glob is out of scope."""
    globs = ("docs/**/*.md", "hooks/**")
    assert matches_any_glob("cortex_command/lint/_globs.py", globs) is False


def test_matches_any_glob_empty_globs_is_false() -> None:
    """An empty glob set admits nothing."""
    assert matches_any_glob("docs/agentic-layer.md", ()) is False


@pytest.mark.skipif(
    not hasattr(__import__("glob"), "translate"),
    reason="glob.translate oracle requires Python 3.13+",
)
@pytest.mark.parametrize(
    "rel_path, glob, expected",
    [(r[1], r[2], r[3]) for r in TRUTH_TABLE],
    ids=[r[0] for r in TRUTH_TABLE],
)
def test_matcher_agrees_with_glob_translate_oracle(
    rel_path: str, glob: str, expected: bool
) -> None:
    """On 3.13+, cross-check the matcher against glob.translate (test-only oracle)."""
    import glob as _glob

    oracle = re.compile(
        _glob.translate(glob, recursive=True, include_hidden=True)
    )
    assert bool(oracle.match(rel_path)) is expected
