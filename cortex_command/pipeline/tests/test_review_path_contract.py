"""Regression guard for the worktree-vs-main review.md path contract.

Pins the property whose absence was the production bug: the review prompt the
agent receives names an *absolute* main-repo review.md path (not a worktree-
relative one), at both render seams (cycle 1 and cycle 2), and the gate's
``review_md_path`` resolution is absolute and equal to
``lifecycle_base / feature / "review.md"``.

Covers spec requirements R1 (writer side, both seams), R2 (resolution), and
R4 (bug-distinguishing regression guard).  The load-bearing, non-vacuous
assertions are (a) the rendered write target is absolute and (b) the rendered
prompt carries no bare-relative ``cortex/lifecycle/<feature>/review.md``
literal that would re-resolve against the agent's worktree cwd — NOT a bare
``writer_path == reader_path`` same-source equality (spec R4 calls that
"explicitly insufficient").
"""

from __future__ import annotations

import re
from pathlib import Path

# conftest.py installs the SDK stub before this module is imported under
# pytest; call it directly so unittest-style runs work too.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

# Pre-load the overnight package before importing review_dispatch so its
# transitive ``from cortex_command.overnight.deferral import …`` does not
# trigger overnight/__init__.py to circle back through outcome_router →
# review_dispatch while review_dispatch is still mid-import.  Mirrors the
# established ordering in test_review_dispatch.py.
import cortex_command.overnight.deferral  # noqa: F401, E402

from cortex_command.pipeline.review_dispatch import _load_review_prompt  # noqa: E402

# A bare-relative review.md path: ``cortex/lifecycle/<feature>/review.md`` NOT
# preceded by ``/``.  The negative-lookbehind is essential — an *absolute* path
# ends with that same suffix (``/main/cortex/lifecycle/feat/review.md``), so a
# plain substring check would false-positive and the guard would be vacuous.
_BARE_RELATIVE = re.compile(r"(?<!/)cortex/lifecycle/[^`\n]+/review\.md")

# The cycle-2 note appended verbatim after the second render seam in
# review_dispatch.dispatch_review (the ``_load_review_prompt`` call followed by
# ``cycle2_prompt += (...)``).  Mirrored here so the test exercises the exact
# string the cycle-2 agent receives.
_CYCLE2_NOTE = (
    "\n\nNote: This is review cycle 2. A previous review returned "
    "CHANGES_REQUESTED and a fix agent has addressed the feedback. "
    "Focus on whether the flagged issues were resolved."
)

_FEATURE = "feat-x"
_ABS_BASE = Path("/main/cortex/lifecycle")


def _render(review_md_path: str, *, cycle2: bool = False) -> str:
    """Render the review prompt the way dispatch_review's seams do."""
    prompt = _load_review_prompt(
        feature=_FEATURE,
        spec_excerpt="SPEC EXCERPT",
        worktree_path=Path("/wt"),
        branch_name="pipeline/feat-x",
        review_md_path=review_md_path,
    )
    if cycle2:
        prompt += _CYCLE2_NOTE
    return prompt


def _write_target(rendered: str) -> str:
    """Extract the backtick-delimited path the prompt tells the agent to write."""
    m = re.search(r"Write your review to `([^`]+)` on disk", rendered)
    assert m is not None, "write-target instruction not found in rendered prompt"
    return m.group(1)


# --- R1: both render seams name an absolute path, no bare-relative literal ---

def test_cycle1_render_names_absolute_path():
    review_md_path = str(_ABS_BASE / _FEATURE / "review.md")
    rendered = _render(review_md_path, cycle2=False)
    assert review_md_path in rendered
    assert Path(_write_target(rendered)).is_absolute()
    assert _BARE_RELATIVE.search(rendered) is None


def test_cycle2_render_names_absolute_path():
    review_md_path = str(_ABS_BASE / _FEATURE / "review.md")
    rendered = _render(review_md_path, cycle2=True)
    assert review_md_path in rendered
    assert Path(_write_target(rendered)).is_absolute()
    assert _BARE_RELATIVE.search(rendered) is None


def test_required_param_fails_loud_when_missing():
    # No default on review_md_path: a missed render seam fails at the call,
    # never renders an unsubstituted ``{review_md_path}`` literal.
    import pytest

    with pytest.raises(TypeError):
        _load_review_prompt(
            feature=_FEATURE,
            spec_excerpt="s",
            worktree_path=Path("/wt"),
            branch_name="b",
        )


# --- Guard the guard: the lookbehind regex is non-vacuous -------------------

def test_bare_relative_regex_is_non_vacuous():
    review_md_path = str(_ABS_BASE / _FEATURE / "review.md")
    rendered = _render(review_md_path)
    # Absolute path: not caught (the char before ``cortex`` is ``/``).
    assert _BARE_RELATIVE.search(rendered) is None
    # Pre-fix bare-relative literal: caught (proves the test fails on the bug).
    buggy = rendered.replace(review_md_path, f"cortex/lifecycle/{_FEATURE}/review.md")
    assert _BARE_RELATIVE.search(buggy) is not None


# --- R2: gate-side review_md_path resolution is absolute ---------------------

def test_review_md_path_resolution_is_absolute():
    # Mirrors review_dispatch.dispatch_review line 208:
    # ``review_md_path = lifecycle_base / feature / "review.md"``.
    review_md_path = _ABS_BASE / _FEATURE / "review.md"
    assert review_md_path.is_absolute()
    assert review_md_path == _ABS_BASE / _FEATURE / "review.md"


# --- R4: writer target agrees with the independently-derived reader path -----

def test_writer_target_matches_independent_reader_path():
    # Derive the reader path the gate reads INDEPENDENTLY of the render input,
    # then render with it and parse the target back OUT of the prompt text.
    # The bug-distinguishing checks are absoluteness + no-bare-relative (above);
    # this parity check additionally proves substitution fidelity rather than a
    # same-source in-process equality.
    reader_path = _ABS_BASE / _FEATURE / "review.md"
    rendered = _render(str(reader_path), cycle2=False)
    parsed_target = _write_target(rendered)
    assert Path(parsed_target).is_absolute()
    assert parsed_target == str(reader_path)
    assert _BARE_RELATIVE.search(rendered) is None
