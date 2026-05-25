"""cortex-critical-review-resolve-feature — resolve a session id to a feature slug.

Stub created by Task 4 of the convert-bin-cortex-and-skill-embedded feature.
Real logic is filled in by Task 6.

Usage:
    cortex-critical-review-resolve-feature <session-id>

Globs ``cortex/lifecycle/*/.session`` files; when exactly one file's contents
match the given session id, prints the parent directory name (the feature
slug) to stdout and exits 0. When no session matches (or multiple match),
exits non-zero with a clear stderr message.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from cortex_command.backlog import _telemetry


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-critical-review-resolve-feature",
        description=(
            "Resolve a lifecycle session id to its feature slug by globbing "
            "cortex/lifecycle/*/.session files. Prints the matching feature "
            "slug to stdout, or exits non-zero with a stderr message when "
            "no session matches."
        ),
    )
    parser.add_argument(
        "session_id",
        metavar="session-id",
        help="Lifecycle session id (typically $LIFECYCLE_SESSION_ID).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-critical-review-resolve-feature")
    parser = _build_parser()
    parser.parse_args(argv)
    raise NotImplementedError("filled in by T6")


if __name__ == "__main__":
    main()
