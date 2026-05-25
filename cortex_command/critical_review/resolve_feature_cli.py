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
import sys
from pathlib import Path
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
    args = parser.parse_args(argv)
    session_id = args.session_id

    matches: List[Path] = []
    for session_file in Path("cortex/lifecycle").glob("*/.session"):
        try:
            contents = session_file.read_text().strip()
        except OSError:
            continue
        if contents == session_id:
            matches.append(session_file)

    if len(matches) == 0:
        print(f"no session matching {session_id}", file=sys.stderr)
        return 1
    if len(matches) > 1:
        slugs = ", ".join(sorted(p.parent.name for p in matches))
        print(
            f"multiple sessions matching {session_id}: {slugs}",
            file=sys.stderr,
        )
        return 1

    print(matches[0].parent.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
