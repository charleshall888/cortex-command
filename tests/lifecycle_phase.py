#!/usr/bin/env python3
"""Lifecycle phase detection module.

Implements detect_phase(lifecycle_dir: Path) -> str using the same logic as
determine_phase() in hooks/scan-lifecycle.sh (lines 139-176).

Phase precedence (highest priority first):
  1. events.log contains "feature_complete" -> "complete"
  2. review.md exists and has a verdict:
       APPROVED          -> "complete"
       CHANGES_REQUESTED -> "implement"
       REJECTED          -> "escalated"
  3. plan.md exists:
       all **Status**: [x] (and at least one) -> "review"
       otherwise                              -> "implement"
  4. spec.md exists    -> "plan"
  5. research.md exists -> "specify"
  6. (default)          -> "research"

Usage as CLI tool:
  python3 tests/lifecycle_phase.py <lifecycle_dir>
"""

import re
import sys
from pathlib import Path


def detect_phase(lifecycle_dir: Path) -> str:
    """Detect the current lifecycle phase for a feature directory.

    Args:
        lifecycle_dir: Path to the lifecycle feature directory
                       (e.g. lifecycle/my-feature/ or a fixture dir).

    Returns:
        One of: "complete", "escalated", "review", "implement",
                "plan", "specify", "research".
    """
    # Step 1: event-based completion check (covers all tiers)
    events_log = lifecycle_dir / "events.log"
    if events_log.is_file():
        content = events_log.read_text(errors="replace")
        if '"feature_complete"' in content:
            return "complete"

    # Step 2: review.md verdict
    review_md = lifecycle_dir / "review.md"
    if review_md.is_file():
        content = review_md.read_text(errors="replace")
        # Mirror: sed -n 's/.*"verdict"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p' | tail -1
        matches = re.findall(r'"verdict"\s*:\s*"([A-Z_]+)"', content)
        if matches:
            verdict = matches[-1]  # tail -1 equivalent
            if verdict == "APPROVED":
                return "complete"
            elif verdict == "CHANGES_REQUESTED":
                return "implement"
            elif verdict == "REJECTED":
                return "escalated"

    # Step 3: plan.md task completion
    plan_md = lifecycle_dir / "plan.md"
    if plan_md.is_file():
        content = plan_md.read_text(errors="replace")
        # Mirror: grep -cE '\*\*Status\*\*:.*\[[ x]\]'
        total_matches = re.findall(r'\*\*Status\*\*:.*\[[ x]\]', content)
        total = len(total_matches)
        # Mirror: grep -cE '\*\*Status\*\*:.*\[x\]'
        checked_matches = re.findall(r'\*\*Status\*\*:.*\[x\]', content)
        checked = len(checked_matches)

        if total > 0 and checked == total:
            return "review"
        else:
            return "implement"

    # Step 4: spec.md exists -> plan phase
    if (lifecycle_dir / "spec.md").is_file():
        return "plan"

    # Step 5: research.md exists -> specify phase
    if (lifecycle_dir / "research.md").is_file():
        return "specify"

    # Step 6: default -> research phase
    return "research"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <lifecycle_dir>", file=sys.stderr)
        sys.exit(1)
    print(detect_phase(Path(sys.argv[1])))
