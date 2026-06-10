"""cortex-lifecycle-counters — emit a feature's plan/events counters as JSON.

Reads ``cortex/lifecycle/<feature>/plan.md`` and ``events.log`` and emits:

    {"tasks_total": <int>, "tasks_checked": <int>, "rework_cycles": <int>}

Counter rules:

- ``tasks_total``   — count of ``**Status**: [ ]`` or ``**Status**: [x]``
  lines in ``plan.md`` (``\\*\\*Status\\*\\*:.*\\[[ x]\\]``).
- ``tasks_checked`` — count of ``**Status**: [x]`` lines
  (``\\*\\*Status\\*\\*:.*\\[x\\]``).
- ``rework_cycles`` — count of ``review_verdict`` events with
  ``verdict == "CHANGES_REQUESTED"`` in ``events.log``. Each line is parsed
  defensively (non-JSON / malformed lines are skipped, not raised on),
  mirroring the events.log tolerant-reader convention in
  ``common.py``'s ``_detect_lifecycle_phase_inner``. A clean first-pass
  approval (a synthetic ``APPROVED`` verdict, or no review at all) reports 0.

Missing/empty files default to 0 for all three fields.
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


def count_rework_cycles(events_log_path: Path) -> int:
    """Return rework_cycles from events.log.

    Counts ``review_verdict`` events whose ``verdict`` is
    ``"CHANGES_REQUESTED"``. Each line is parsed defensively: non-JSON /
    malformed lines are skipped rather than raised on (the events.log
    tolerant-reader convention, mirroring ``common.py``'s
    ``_detect_lifecycle_phase_inner``).

    Returns 0 when the file does not exist, is empty, or cannot be read.
    """
    if not events_log_path.exists():
        return 0
    try:
        text = events_log_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "review_verdict" and (
            event.get("verdict") == "CHANGES_REQUESTED"
        ):
            count += 1
    return count


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
    events_log_path = feature_dir / "events.log"

    tasks_total, tasks_checked = count_tasks(plan_path)
    rework_cycles = count_rework_cycles(events_log_path)

    result = {
        "tasks_total": tasks_total,
        "tasks_checked": tasks_checked,
        "rework_cycles": rework_cycles,
    }
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
