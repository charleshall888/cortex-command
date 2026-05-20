"""cortex-lifecycle-counters — emit a feature's plan/review counters as JSON.

Port of ``bin/cortex-lifecycle-counters`` (bash+jq). Reads
``cortex/lifecycle/<feature>/plan.md`` and ``review.md`` and emits:

    {"tasks_total": <int>, "tasks_checked": <int>, "rework_cycles": <int>}

Counter rules (pinned to the same regexes as ``common.py:182-183``):

- ``tasks_total``   — count of ``**Status**: [ ]`` or ``**Status**: [x]``
  lines in ``plan.md`` (``\\*\\*Status\\*\\*:.*\\[[ x]\\]``).
- ``tasks_checked`` — count of ``**Status**: [x]`` lines
  (``\\*\\*Status\\*\\*:.*\\[x\\]``).
- ``rework_cycles`` — count of ``"verdict": "<UPPER_SNAKE>"`` matches in
  ``review.md`` (``"verdict"\\s*:\\s*"[A-Z_]+"``).

Missing files default to 0 for all three fields — identical to the bash
behavior.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional


RE_TASKS_TOTAL = re.compile(r"\*\*Status\*\*:.*\[[ x]\]")
RE_TASKS_CHECKED = re.compile(r"\*\*Status\*\*:.*\[x\]")
RE_VERDICT = re.compile(r'"verdict"\s*:\s*"[A-Z_]+"')


def count_tasks(plan_path: Path) -> tuple[int, int]:
    """Return (tasks_total, tasks_checked) from plan.md.

    Returns (0, 0) when the file does not exist or cannot be read.
    """
    if not plan_path.exists():
        return 0, 0
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return 0, 0
    total = len(RE_TASKS_TOTAL.findall(text))
    checked = len(RE_TASKS_CHECKED.findall(text))
    return total, checked


def count_rework_cycles(review_path: Path) -> int:
    """Return rework_cycles from review.md.

    Returns 0 when the file does not exist or cannot be read.
    """
    if not review_path.exists():
        return 0
    try:
        text = review_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(RE_VERDICT.findall(text))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-counters",
        description=(
            "Emit a feature's plan/review counters as JSON. "
            "Output: {\"tasks_total\": <int>, \"tasks_checked\": <int>, "
            "\"rework_cycles\": <int>}"
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        metavar="SLUG",
        help="Feature slug under cortex/lifecycle/ (e.g., my-feature-name).",
    )
    parser.add_argument(
        "--lifecycle-dir",
        default="cortex/lifecycle",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for cortex-lifecycle-counters."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    feature = args.feature
    lifecycle_dir = Path(args.lifecycle_dir)
    feature_dir = lifecycle_dir / feature

    plan_path = feature_dir / "plan.md"
    review_path = feature_dir / "review.md"

    tasks_total, tasks_checked = count_tasks(plan_path)
    rework_cycles = count_rework_cycles(review_path)

    result = {
        "tasks_total": tasks_total,
        "tasks_checked": tasks_checked,
        "rework_cycles": rework_cycles,
    }
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
