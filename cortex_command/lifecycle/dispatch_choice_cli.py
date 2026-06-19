"""cortex-lifecycle-dispatch-choice — emit a feature's recorded dispatch_choice.

Usage:
    cortex-lifecycle-dispatch-choice --feature <slug>

Prints the line-position-last ``plan_approved`` event's ``dispatch_choice``
value for the feature, or an empty string when no branch mode is recorded
(no ``plan_approved`` event, the latest one lacks the field, or the value is
``wait``), then exits 0.

Resolution mirrors ``cortex_command.lifecycle.state_cli``: the events log is
``cortex/lifecycle/{feature}/events.log`` resolved CWD-relative. The Implement
consumer gates this read on being on ``main``/``master`` (the merged Plan §4
surface writes ``plan_approved`` from the main repo), so the CWD is the main
repo and the relative path resolves to the canonical log.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle_implement import read_dispatch_choice


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-dispatch-choice",
        description=(
            "Emit a feature's recorded dispatch_choice (the line-position-last "
            "plan_approved event's dispatch_choice), or an empty string when "
            "none is recorded."
        ),
    )
    parser.add_argument(
        "--feature",
        required=True,
        help="Lifecycle feature slug (resolves cortex/lifecycle/<slug>/events.log).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-dispatch-choice")
    parser = _build_parser()
    args = parser.parse_args(argv)
    events_path = (
        pathlib.Path("cortex") / "lifecycle" / args.feature / "events.log"
    )
    choice = read_dispatch_choice(events_path)
    sys.stdout.write((choice or "") + "\n")
    return 0


if __name__ == "__main__":
    main()
