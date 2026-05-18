"""Atomic CLI helpers for the /cortex-core:refine skill.

Scaffolds an ``emit-lifecycle-start`` subcommand that will (in subsequent
tasks) read backlog frontmatter and atomically append a ``lifecycle_start``
row to ``cortex/lifecycle/{feature}/events.log``. This module currently
exposes only the argparse surface; the handler is a stub returning 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lifecycle_start_present(events_log: Path) -> bool:
    """Return True when ``events_log`` exists and contains a ``lifecycle_start``.

    Each non-empty line is parsed as JSON; unparseable lines are skipped
    silently (mirrors the tolerant parse pattern at
    ``cortex_command/common.py:_read_criticality_inner:435-436``).
    """
    if not events_log.exists():
        return False
    for line in events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == "lifecycle_start":
            return True
    return False


def _cmd_emit_lifecycle_start(args: argparse.Namespace) -> int:
    """Atomically seed ``cortex/lifecycle/{slug}/events.log`` with a row.

    Idempotent: if a ``lifecycle_start`` row already exists in the file,
    exits 0 silently without appending. Otherwise reads backlog frontmatter
    via :func:`_read_backlog_frontmatter`, appends a row with the canonical
    key order (``schema_version, ts, event, feature, tier, criticality,
    entry_point``), and re-reads the last line to verify the write landed.
    """
    lifecycle_slug: str = args.lifecycle_slug
    backlog_slug: str | None = args.backlog_slug

    events_log = Path("cortex/lifecycle") / lifecycle_slug / "events.log"
    events_log.parent.mkdir(parents=True, exist_ok=True)

    if _lifecycle_start_present(events_log):
        return 0

    tier, criticality = _read_backlog_frontmatter(backlog_slug)

    row = {
        "schema_version": 1,
        "ts": _now_iso(),
        "event": "lifecycle_start",
        "feature": lifecycle_slug,
        "tier": tier,
        "criticality": criticality,
        "entry_point": "refine",
    }

    try:
        with open(events_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except (PermissionError, OSError) as e:
        print(
            f"cortex-refine: failed to append to {events_log}: {e}. "
            f"Ensure the cortex/ umbrella is registered for sandbox writes "
            f"(run `cortex init` to register it in "
            f"~/.claude/settings.local.json's sandbox.filesystem.allowWrite).",
            file=sys.stderr,
        )
        return 70

    # Read-after-write verify: re-read the last line and assert it matches.
    try:
        with open(events_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(
            f"cortex-refine: read_after_write_io_error reading {events_log}: {e}",
            file=sys.stderr,
        )
        return 70

    mismatch = False
    if not lines:
        mismatch = True
    else:
        last = lines[-1].strip()
        try:
            obj = json.loads(last)
        except (json.JSONDecodeError, ValueError):
            mismatch = True
        else:
            if (
                obj.get("event") != "lifecycle_start"
                or obj.get("tier") != tier
                or obj.get("criticality") != criticality
            ):
                mismatch = True

    if mismatch:
        print("read_after_write_mismatch", file=sys.stderr)
        return 70

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
