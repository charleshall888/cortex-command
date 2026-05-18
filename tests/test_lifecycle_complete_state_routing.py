"""Structural tests for Complete phase step 7 routing table.

Exercises all 12 routing branches documented in
``skills/lifecycle/references/complete.md`` Step 7:

  1.  feature_wontfix present in events.log
  2.  feature_complete already in events.log
  3a. pr.json absent, zero orphan PRs  (first-run path)
  3b. pr.json absent, exactly one orphan PR (retroactive reconstruction)
  3c. pr.json absent, multiple orphan PRs (slug-reuse / interactive)
  4a. Auth/network error
  4b. PR not found on GitHub
  4c. state=OPEN
  4d. state=MERGED + dirty worktree
  4e. state=MERGED + clean worktree + branch IS ancestor of origin/main
  4f. state=MERGED + clean worktree + branch NOT ancestor of origin/main
  4g. state=CLOSED without merge

Each test asserts that the canonical exit-message substring for that branch
appears verbatim in ``complete.md``.  This is strategy (a) from T13's context
note: structural assertions on the skill prose rather than extracted Python
logic.  The tests do NOT invoke the skill at runtime — they verify that the
skill document encodes the correct routing protocol so a model executing it
has the right instructions.

The 12 test count in the parametrize list maps to the acceptance-criterion
wording of spec §12 (which names 12 branches including the three pr.json-absent
sub-cases).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
COMPLETE_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "complete.md"


def _complete_text() -> str:
    """Return the contents of complete.md."""
    return COMPLETE_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Parametrized routing-branch tests
# Each tuple: (branch_id, exit_message_substring)
# Substrings are taken verbatim from the canonical prose in complete.md.
# ---------------------------------------------------------------------------

ROUTING_BRANCHES = [
    (
        "feature_wontfix",
        "lifecycle was wontfix'd at",
    ),
    (
        "feature_complete-already",
        "feature_complete",
    ),
    (
        "pr.json-absent-no-orphan",
        "Zero matches",
    ),
    (
        "pr.json-absent-one-orphan",
        "Exactly one match",
    ),
    (
        "pr.json-absent-multi-orphan",
        "Multiple matches",
    ),
    (
        "auth-error",
        "gh unauthenticated or network error",
    ),
    (
        "PR-not-found",
        "referenced in pr.json was not found on GitHub",
    ),
    (
        "OPEN",
        "merge first",
    ),
    (
        "MERGED+dirty",
        "uncommitted changes at",
    ),
    (
        "MERGED+clean+ancestor",
        "Continue to Steps 8",
    ),
    (
        "MERGED+clean+non-ancestor",
        "refusing cleanup until verified",
    ),
    (
        "CLOSED-unmerged",
        "closed without merging",
    ),
]


@pytest.mark.parametrize("branch_id,expected_substring", ROUTING_BRANCHES)
def test_routing_branch_exit_message_present(branch_id: str, expected_substring: str) -> None:
    """Each routing branch's exit message substring appears in complete.md.

    This verifies the skill document encodes the correct exit text for each
    branch so a model executing the skill has the right instructions.
    """
    text = _complete_text()
    assert expected_substring in text, (
        f"Branch '{branch_id}': expected exit-message substring "
        f"{expected_substring!r} not found in {COMPLETE_MD.relative_to(REPO_ROOT)}"
    )


# ---------------------------------------------------------------------------
# Structural invariants (not parametrized)
# ---------------------------------------------------------------------------


def test_complete_md_exists() -> None:
    """complete.md must exist at the expected canonical path."""
    assert COMPLETE_MD.is_file(), (
        f"complete.md not found at {COMPLETE_MD.relative_to(REPO_ROOT)}"
    )


def test_step_7_heading_present() -> None:
    """complete.md must contain a Step 7 heading (state-aware routing step)."""
    text = _complete_text()
    assert re.search(r"^#{1,4}\s+Step\s+7\b", text, re.MULTILINE), (
        "complete.md missing '### Step 7' (or similar) heading"
    )


def test_evaluation_order_documented() -> None:
    """Step 7 must declare 'strict order' or 'Evaluation order'."""
    text = _complete_text()
    assert "strict order" in text or "Evaluation order" in text, (
        "complete.md Step 7 must document evaluation order as strict"
    )


def test_feature_wontfix_takes_precedence() -> None:
    """Branch 1 (wontfix) must assert precedence over pr.json state checks."""
    text = _complete_text()
    assert "Takes precedence" in text or "takes precedence" in text, (
        "complete.md must state that feature_wontfix takes precedence over all pr.json checks"
    )


def test_worktree_retained_language_in_terminal_branches() -> None:
    """Branches that retain the worktree must say '(Worktree retained.)' explicitly."""
    text = _complete_text()
    count = text.count("Worktree retained")
    assert count >= 3, (
        f"Expected at least 3 occurrences of 'Worktree retained' (auth-error, PR-not-found, "
        f"CLOSED-unmerged branches), found {count}"
    )


def test_pr_json_absent_probe_command_present() -> None:
    """Branch 3 must document the orphan-PR probe command using 'gh pr list'."""
    text = _complete_text()
    assert "gh pr list" in text and "--head" in text, (
        "complete.md Branch 3 (pr.json absent) must document 'gh pr list --head' orphan-PR probe"
    )


def test_gh_pr_view_command_present() -> None:
    """Branch 4 must document 'gh pr view <number> --json state,mergedAt'."""
    text = _complete_text()
    assert "gh pr view" in text and "--json state,mergedAt" in text, (
        "complete.md Branch 4 must document 'gh pr view <number> --json state,mergedAt'"
    )


def test_merge_base_is_ancestor_command_present() -> None:
    """Branches 4e/4f must document 'git merge-base --is-ancestor'."""
    text = _complete_text()
    assert "git merge-base --is-ancestor" in text, (
        "complete.md must document 'git merge-base --is-ancestor' check for ancestor branch"
    )


def test_twelve_routing_branches_covered() -> None:
    """The parametrized list covers exactly 12 routing branches as required by spec §12."""
    assert len(ROUTING_BRANCHES) == 12, (
        f"Expected 12 routing branches in the test matrix, got {len(ROUTING_BRANCHES)}"
    )


def test_wontfix_exit_message_verbatim() -> None:
    """Branch 1 exit message matches verbatim spec text."""
    text = _complete_text()
    assert "nothing to complete (worktree cleanup skipped)" in text, (
        "complete.md Branch 1 wontfix exit message must contain "
        "'nothing to complete (worktree cleanup skipped)'"
    )


def test_pr_not_found_exit_message_verbatim() -> None:
    """Branch 4b exit message includes 'The PR may have been deleted' clause."""
    text = _complete_text()
    assert "The PR may have been deleted" in text, (
        "complete.md Branch 4b (PR-not-found) exit message must include "
        "'The PR may have been deleted'"
    )


def test_closed_unmerged_exit_offers_three_paths() -> None:
    """Branch 4g (CLOSED-unmerged) exit must offer three recovery paths."""
    text = _complete_text()
    # The spec requires: reopen+merge, manual git worktree remove, or wontfix
    assert "reopen and merge" in text, (
        "Branch 4g must offer 'reopen and merge' recovery path"
    )
    assert "git worktree remove" in text, (
        "Branch 4g must offer 'git worktree remove' recovery path"
    )
    assert "wontfix" in text, (
        "Branch 4g must offer wontfix recovery path"
    )


def test_non_ancestor_exit_offers_manual_override() -> None:
    """Branch 4f (non-ancestor) exit must offer 'git worktree remove' manual override."""
    text = _complete_text()
    assert "git worktree remove" in text, (
        "Branch 4f must offer 'git worktree remove <path> manually to override'"
    )


def test_pr_json_absent_zero_match_runs_first_run_path() -> None:
    """Branch 3a (zero orphan matches) routes to first-run path (Steps 1–6)."""
    text = _complete_text()
    # The spec says "run first-run path (Steps 1–6)" for zero matches
    assert "first-run path" in text, (
        "complete.md Branch 3a must say 'run first-run path' for zero orphan matches"
    )


def test_pr_json_absent_one_match_reconstructs_pr_json() -> None:
    """Branch 3b (one orphan match) retroactively reconstructs pr.json."""
    text = _complete_text()
    assert "retroactively" in text, (
        "complete.md Branch 3b must say 'retroactively reconstruct' pr.json for single orphan match"
    )
