"""cortex-lifecycle-picker-decision — emit the picker decision as JSON.

Stub created by Task 4 of the convert-bin-cortex-and-skill-embedded feature.
Real logic is filled in by Task 5.

Usage:
    cortex-lifecycle-picker-decision <path> <slug> [<mode>]

Calls cortex_command.lifecycle_implement.should_fire_picker(path, slug, mode)
and serializes the (fire, reason) tuple as a single JSON object on stdout:
``{"fire": <bool>, "reason": "<closed-set-token>"}``. The closed-set ``reason``
vocabulary is the verbatim ``cortex_command.lifecycle_implement.REASONS`` set.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle_implement import should_fire_picker


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-picker-decision",
        description=(
            "Emit the picker decision for a lifecycle slug as JSON. Calls "
            "cortex_command.lifecycle_implement.should_fire_picker and "
            "serializes the result as "
            '{"fire": <bool>, "reason": "<closed-set-token>"}.'
        ),
    )
    parser.add_argument(
        "path",
        help="Path to inspect (typically '.' from the lifecycle root).",
    )
    parser.add_argument(
        "slug",
        help="Lifecycle feature slug to evaluate.",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default=None,
        help="Optional branch mode token (closed set); omit when unknown.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-picker-decision")
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = pathlib.Path(args.path)
    # Treat empty string as None — the legacy snippet substituted
    # '{branch_mode}' or None which produced an empty string when
    # read_branch_mode returned None.
    mode = args.mode if args.mode else None
    fire, reason = should_fire_picker(path, args.slug, mode)
    sys.stdout.write(json.dumps({"fire": fire, "reason": reason}) + "\n")
    return 0


if __name__ == "__main__":
    main()
