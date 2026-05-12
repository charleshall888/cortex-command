#!/usr/bin/env python3
"""One-shot historical drift remediation enumerator (R8).

This script identifies the historical `cortex/lifecycle/{,archive/}*/review.md`
artifacts where the reviewer flagged `requirements_drift: detected` but
omitted the `## Suggested Requirements Update` section that R7 now
enforces going forward. Research §2 of
`cortex/lifecycle/requirements-skill-v2/research.md` identified 8 such
artifacts at the time of the audit; the soft acceptance target for R8 is
≤1 unfixed (≥7/8 fixed).

The script is a one-shot — it lives in this lifecycle directory rather
than in `bin/`, and is not wired into the overnight runner. It is
discoverable via the `docs/internals/one-shot-scripts.md` registry.

## Usage

    # Default: print candidates + per-file dispatch prompt and operator
    # instructions. Designed to be read inside an interactive Claude Code
    # session so the operator can run the per-file dispatches as
    # sub-agent tool calls.
    python3 cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py

    # Dry-run: print only the candidate file paths, one per line.
    # The semantic verifier the operator runs before live dispatch.
    python3 cortex/lifecycle/requirements-skill-v2/scripts/remediate-historical-drift.py --dry-run

## Enumeration rules

A `review.md` is a candidate iff:

1. It contains a `## Requirements Drift` H2 section, AND
2. That section contains a `**State**: detected` line, AND
3. The file contains no `## Suggested Requirements Update` H2 section.

Note: the canonical drift-state encoding in review.md files is the
section-style `**State**: detected` inside `## Requirements Drift`. The
spec's R8 acceptance text uses `requirements_drift: detected` as
shorthand for that condition. This script implements the semantic
intent.

## Per-file dispatch failure handling

The script itself does not dispatch agents; it produces the per-file
prompts. Task 12 runs this script inside an interactive Claude Code
session where the operator dispatches a reviewer sub-agent per file.
Per-file dispatch failures (a sub-agent that errors or produces an
empty patch) are logged by the operator and the script proceeds to
the next candidate — the soft acceptance target tolerates ≤1 unfixed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
LIFECYCLE_ROOT = REPO_ROOT / "cortex" / "lifecycle"

REQUIREMENTS_DRIFT_HEADING = re.compile(r"^## Requirements Drift\b", re.MULTILINE)
STATE_DETECTED = re.compile(r"^\*\*State\*\*:\s*\"?detected\"?\b", re.MULTILINE)
NEXT_H2 = re.compile(r"^## ", re.MULTILINE)
SUGGESTED_HEADING = "## Suggested Requirements Update"


def find_candidates(lifecycle_root: Path) -> list[Path]:
    """Return review.md paths matching the R8 enumeration rules.

    Walks both `cortex/lifecycle/*/review.md` and
    `cortex/lifecycle/archive/*/review.md`. Returns absolute paths
    sorted lexicographically for stable output.
    """
    candidates: list[Path] = []
    for review_path in sorted(lifecycle_root.rglob("review.md")):
        try:
            text = review_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Unreadable file — skip silently; remediation cannot help.
            continue
        match = REQUIREMENTS_DRIFT_HEADING.search(text)
        if not match:
            continue
        section_start = match.start()
        next_h2 = NEXT_H2.search(text, section_start + 1)
        section_end = next_h2.start() if next_h2 else len(text)
        section = text[section_start:section_end]
        if not STATE_DETECTED.search(section):
            continue
        if SUGGESTED_HEADING in text:
            continue
        candidates.append(review_path)
    return candidates


def per_file_prompt(review_path: Path) -> str:
    """Build the per-file reviewer dispatch prompt.

    The prompt instructs a reviewer sub-agent to read the review.md,
    derive the suggested requirements update from the existing
    Requirements Drift section's `**Findings**` and `**Update needed**`
    lines, and append a `## Suggested Requirements Update` section
    matching the format R7 enforces going forward.
    """
    rel = review_path.relative_to(REPO_ROOT)
    return f"""Read {rel} and append a `## Suggested Requirements Update` section.

The file already has a `## Requirements Drift` section with
`**State**: detected` and `**Findings**` bullets describing the gap.
It is missing the `## Suggested Requirements Update` section that R7
now enforces.

Your task:
1. Read the existing `## Requirements Drift` section's `**Findings**`
   bullets and `**Update needed**` line (if present) for context.
2. Identify the requirements file the drift points at (e.g.,
   `cortex/requirements/pipeline.md`, `cortex/requirements/project.md`,
   `cortex/requirements/observability.md`).
3. Append a `## Suggested Requirements Update` section after the
   existing `## Requirements Drift` section (and any subsequent
   `## Verdict` block — place it before the `## Verdict` JSON if one
   exists, otherwise at the end of the file). The section should
   contain:
   - **Target file**: <requirements file>
   - **Suggested edit**: <2-4 sentences describing the concrete edit
     needed, derived from the Findings bullets>
   - **Rationale**: <1-2 sentences citing the drift finding>
4. Write the modified file back to disk.
5. Do not modify any other section of the review.md.
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Enumerate historical lifecycle review.md files with "
            "requirements_drift: detected but no Suggested Requirements "
            "Update section. R8 one-shot remediation enumerator."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print only candidate file paths, one per line. "
            "Use this to semantically verify the enumeration before "
            "running the live remediation dispatch."
        ),
    )
    args = parser.parse_args(argv)

    candidates = find_candidates(LIFECYCLE_ROOT)

    if args.dry_run:
        for path in candidates:
            print(path)
        return 0

    print(f"# R8 historical drift remediation candidates: {len(candidates)}")
    print(
        "# Research §2 identified 8 such artifacts; acceptance soft "
        "target is ≤1 unfixed (≥7/8 fixed).",
    )
    print(
        "# This script does not dispatch agents. Run it inside an "
        "interactive Claude Code session; the operator dispatches a "
        "reviewer sub-agent per file using the prompts below.",
    )
    print(
        "# Per-file dispatch failures: log the failure and continue to "
        "the next file. ≤1 unfixed is acceptable.",
    )
    print()
    for path in candidates:
        print(f"## Candidate: {path}")
        print()
        print(per_file_prompt(path))
        print("---")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
