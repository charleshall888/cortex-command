"""Citation-pin test — protect section designators cited normatively by overnight prompts
and lifecycle_config.

The harness-token-efficiency-trim feature trimmed skills/lifecycle/references/*.md but
was required to preserve every heading that overnight prompts or lifecycle_config cite
by designator.  This test pins those exact heading forms so a future editor knows they
cannot rename or remove the headings without updating the citing files first.

Each assertion carries a comment identifying the citing site(s) so a maintainer can
locate the callers.

Cited from:
  - cortex_command/overnight/prompts/orchestrator-round.md:242,302,413
  - cortex_command/lifecycle_config.py:8-9,162-163
  - cortex_command/overnight/report.py:965

Spec: cortex/lifecycle/harness-token-efficiency-trim/spec.md R5, R6f.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCES_DIR = REPO_ROOT / "skills" / "lifecycle" / "references"


def _read_headings(filename: str) -> set[str]:
    """Return the set of heading lines (stripped) from a reference file."""
    path = REFERENCES_DIR / filename
    text = path.read_text(encoding="utf-8")
    return {line.strip() for line in text.splitlines() if line.startswith("#")}


# ---------------------------------------------------------------------------
# skills/lifecycle/references/plan.md
# ---------------------------------------------------------------------------

def test_plan_md_has_1a_heading() -> None:
    """plan.md must contain '### 1a. Check Criticality'.

    Cited by:
      - orchestrator-round.md:242  (``plan.md`` §1a precedent)
      - lifecycle_config.py:8,95   (``skills/lifecycle/references/plan.md`` §5 and ...)
        [§1a cited in orchestrator-round.md only; lifecycle_config.py cites §5]
    """
    headings = _read_headings("plan.md")
    assert "### 1a. Check Criticality" in headings, (
        "plan.md is missing '### 1a. Check Criticality' — "
        "this designator is cited normatively at "
        "cortex_command/overnight/prompts/orchestrator-round.md:242. "
        "Rename the heading there before removing or renaming it here."
    )


def test_plan_md_has_1b_heading() -> None:
    """plan.md must contain '### 1b. Competing Plans (Critical Only)'.

    Cited by:
      - orchestrator-round.md:302  (LAST-occurrence anchor pattern as ... plan.md §1b)
    """
    headings = _read_headings("plan.md")
    assert "### 1b. Competing Plans (Critical Only)" in headings, (
        "plan.md is missing '### 1b. Competing Plans (Critical Only)' — "
        "this designator is cited normatively at "
        "cortex_command/overnight/prompts/orchestrator-round.md:302. "
        "Update the citing line before removing or renaming it here."
    )


def test_plan_md_has_5_transition_heading() -> None:
    """plan.md must contain '### 5. Transition'.

    Cited by:
      - lifecycle_config.py:8-9    (``skills/lifecycle/references/plan.md`` §5)
      - lifecycle_config.py:162-163 (same)
      - orchestrator-round.md:413 (canonical plan.md format defined in skills/lifecycle/references/plan.md)
    """
    headings = _read_headings("plan.md")
    assert "### 5. Transition" in headings, (
        "plan.md is missing '### 5. Transition' — "
        "this designator is cited normatively at "
        "cortex_command/lifecycle_config.py:8-9,162-163. "
        "Update the citing lines before removing or renaming it here."
    )


# ---------------------------------------------------------------------------
# skills/lifecycle/references/complete-first-run.md
# ---------------------------------------------------------------------------

def test_complete_first_run_md_has_step2_heading() -> None:
    """complete-first-run.md must contain '### Step 2 — Commit Lifecycle Artifacts'.

    Step 2 moved out of complete.md into the extracted first-run PR flow in the
    lifecycle-corpus-trim-wave-2 split, so the citation now targets that file.

    Cited by:
      - lifecycle_config.py:8-9     (``skills/lifecycle/references/complete-first-run.md`` Step 2)
      - lifecycle_config.py:162-163 (same)
    """
    headings = _read_headings("complete-first-run.md")
    assert "### Step 2 — Commit Lifecycle Artifacts" in headings, (
        "complete-first-run.md is missing '### Step 2 — Commit Lifecycle Artifacts' — "
        "this designator is cited normatively at "
        "cortex_command/lifecycle_config.py:8-9,162-163. "
        "Update the citing lines before removing or renaming it here."
    )


# ---------------------------------------------------------------------------
# skills/lifecycle/references/review.md
# ---------------------------------------------------------------------------

def test_review_md_has_4a_heading() -> None:
    """review.md must contain '### 4a. Auto-Apply Requirements Drift'.

    Cited by:
      - cortex_command/overnight/report.py:965
        (``skills/lifecycle/references/review.md`` §4a)
    """
    headings = _read_headings("review.md")
    assert "### 4a. Auto-Apply Requirements Drift" in headings, (
        "review.md is missing '### 4a. Auto-Apply Requirements Drift' — "
        "this designator is cited normatively at "
        "cortex_command/overnight/report.py:965. "
        "Update the citing line before removing or renaming it here."
    )
