"""cortex-lifecycle-branch-mode — emit the active branch mode for a lifecycle path.

Stub created by Task 4 of the convert-bin-cortex-and-skill-embedded feature.
Real logic is filled in by Task 5.

Usage:
    cortex-lifecycle-branch-mode <path>

Prints the branch-mode token (closed set) or an empty string when no branch
mode is recorded, then exits 0.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle_config import read_branch_mode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-branch-mode",
        description=(
            "Emit the active branch mode for a lifecycle path. Calls "
            "cortex_command.lifecycle_config.read_branch_mode and prints "
            "the result, or an empty string when no branch mode is set."
        ),
    )
    parser.add_argument(
        "path",
        help="Path to inspect (typically '.' from the lifecycle root).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-branch-mode")
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = pathlib.Path(args.path)
    mode = read_branch_mode(path)
    sys.stdout.write((mode or "") + "\n")
    return 0


if __name__ == "__main__":
    main()
