#!/usr/bin/env python3
"""Transition failure matrix script.

Parses all cortex/lifecycle/*/events.log files, builds a table of state transition
frequencies and rework cycle counts, and prints a markdown report.

Standalone -- no arguments required.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def main():
    log_files = sorted(REPO_ROOT.glob("cortex/lifecycle/*/events.log"))

    if not log_files:
        print("No lifecycle event logs found. Run some lifecycle features first.")
        sys.exit(0)

    transition_counts = defaultdict(int)
    rework_cycles = []

    for log_file in log_files:
        try:
            content = log_file.read_text(errors="replace")
        except OSError:
            continue

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = entry.get("event")

            if event == "phase_transition":
                from_phase = entry.get("from")
                to_phase = entry.get("to")
                if from_phase is not None and to_phase is not None:
                    transition_counts[(from_phase, to_phase)] += 1

            elif event == "feature_complete":
                cycles = entry.get("rework_cycles")
                if cycles is not None:
                    rework_cycles.append(cycles)

    # Print transition frequency table
    print("## State Transition Frequencies\n")
    print("| Transition | Count |")
    print("| --- | --- |")

    if transition_counts:
        for (from_phase, to_phase), count in sorted(
            transition_counts.items(), key=lambda x: (-x[1], x[0])
        ):
            print(f"| {from_phase} -> {to_phase} | {count} |")
    else:
        print("| (no transitions recorded) | 0 |")

    # Print rework cycle summary
    print()
    print("## Rework Cycle Summary\n")

    zero = sum(1 for c in rework_cycles if c == 0)
    one = sum(1 for c in rework_cycles if c == 1)
    two_plus = sum(1 for c in rework_cycles if c >= 2)

    print(f"- Features with 0 rework cycles: {zero}")
    print(f"- Features with 1 rework cycle: {one}")
    print(f"- Features with 2+ rework cycles: {two_plus}")


if __name__ == "__main__":
    main()
