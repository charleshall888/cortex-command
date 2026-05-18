"""Atomic CLI helpers for the /cortex-core:refine skill.

Scaffolds an ``emit-lifecycle-start`` subcommand that will (in subsequent
tasks) read backlog frontmatter and atomically append a ``lifecycle_start``
row to ``cortex/lifecycle/{feature}/events.log``. This module currently
exposes only the argparse surface; the handler is a stub returning 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cortex_command.backlog.update_item import _get_frontmatter_value


# Allowed value sets, kept in lockstep with the canonical readers at
# ``cortex_command/common.py:_read_criticality_inner`` and ``_read_tier_inner``.
_ALLOWED_CRITICALITY: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
_ALLOWED_COMPLEXITY: frozenset[str] = frozenset({"simple", "complex"})


def _read_backlog_frontmatter(backlog_slug: str | None) -> tuple[str, str]:
    """Return ``(tier, criticality)`` from a backlog item's frontmatter.

    When ``backlog_slug`` is ``None`` or the backlog file does not exist,
    returns the canonical defaults ``("simple", "medium")`` — matching the
    behavior of ``_read_tier_inner`` / ``_read_criticality_inner`` when no
    ``lifecycle_start`` event has been emitted.

    When the file exists, reads ``cortex/backlog/{backlog_slug}.md`` and
    extracts ``complexity:`` (mapped to ``tier``) and ``criticality:`` via
    :func:`_get_frontmatter_value`. Absent keys fall back to defaults.

    Validates ``criticality`` against ``{low, medium, high, critical}`` and
    ``complexity`` against ``{simple, complex}``. On an invalid value,
    prints a stderr diagnostic naming the invalid value, file path, and
    allowed set, then exits with status 64 (``EX_USAGE``).
    """
    if backlog_slug is None:
        return ("simple", "medium")

    backlog_path = Path("cortex/backlog") / f"{backlog_slug}.md"
    if not backlog_path.exists():
        return ("simple", "medium")

    text = backlog_path.read_text(encoding="utf-8")
    criticality = _get_frontmatter_value(text, "criticality")
    complexity = _get_frontmatter_value(text, "complexity")

    if criticality is None:
        criticality = "medium"
    elif criticality not in _ALLOWED_CRITICALITY:
        allowed = ", ".join(sorted(_ALLOWED_CRITICALITY))
        print(
            f"cortex-refine: invalid criticality value {criticality!r} in "
            f"{backlog_path} (allowed: {allowed})",
            file=sys.stderr,
        )
        sys.exit(64)

    if complexity is None:
        complexity = "simple"
    elif complexity not in _ALLOWED_COMPLEXITY:
        allowed = ", ".join(sorted(_ALLOWED_COMPLEXITY))
        print(
            f"cortex-refine: invalid complexity value {complexity!r} in "
            f"{backlog_path} (allowed: {allowed})",
            file=sys.stderr,
        )
        sys.exit(64)

    return (complexity, criticality)


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
