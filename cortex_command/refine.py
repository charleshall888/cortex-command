"""Atomic CLI helpers for the /cortex-core:refine skill.

Scaffolds an ``emit-lifecycle-start`` subcommand that will (in subsequent
tasks) read backlog frontmatter and atomically append a ``lifecycle_start``
row to ``cortex/lifecycle/{feature}/events.log``. This module currently
exposes only the argparse surface; the handler is a stub returning 0.
"""

from __future__ import annotations

import argparse
import sys


def _cmd_emit_lifecycle_start(args: argparse.Namespace) -> int:
    """Stub handler for the emit-lifecycle-start subcommand.

    Subsequent tasks fill in the frontmatter reader, idempotency scan, and
    atomic append + read-after-write verify logic.
    """
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cortex-refine",
        description=(
            "Atomic CLI helpers for the /cortex-core:refine skill. "
            "Currently exposes emit-lifecycle-start, which seeds "
            "cortex/lifecycle/{feature}/events.log with a lifecycle_start "
            "row derived from backlog frontmatter."
        ),
    )
    sub = p.add_subparsers(dest="command")
    sub.required = True

    # emit-lifecycle-start
    el = sub.add_parser(
        "emit-lifecycle-start",
        help=(
            "Read backlog frontmatter and atomically append a "
            "lifecycle_start row to the lifecycle's events.log. "
            "Idempotent: no-op when a lifecycle_start row already exists."
        ),
    )
    el.add_argument(
        "--backlog-slug",
        default=None,
        help=(
            "Backlog filename slug (without .md). Omit for Context B "
            "(ad-hoc refine with no backlog item); defaults will apply."
        ),
    )
    el.add_argument(
        "--lifecycle-slug",
        required=True,
        help="Lifecycle feature slug under cortex/lifecycle/.",
    )
    el.set_defaults(func=_cmd_emit_lifecycle_start)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
