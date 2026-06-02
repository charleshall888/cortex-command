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

# Monotonic ordering for the no-downgrade guard (R4). An override is appended
# only when the desired value ranks strictly above the current reduced value.
# Unknown values rank below every canonical value (-1) so a non-canonical
# current state reconciles up toward a canonical desired value rather than
# raising a KeyError.
_TIER_RANK: dict[str, int] = {"simple": 0, "complex": 1}
_CRITICALITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


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


def _reduce_current_state(events_log: Path) -> tuple[str, str]:
    """Return the current reduced ``(tier, criticality)`` from ``events_log``.

    Replays ``lifecycle_start.tier``/``.criticality`` then the ``to`` field of
    any later ``complexity_override``/``criticality_override`` row — mirroring
    the canonical readers ``cortex_command/common.py:_read_tier_inner`` and
    ``_read_criticality_inner`` (both read ``.to`` only on override rows).

    Deliberately *tolerant* (R5): malformed lines are skipped via the same
    ``json.loads`` + ``JSONDecodeError`` pattern as :func:`_lifecycle_start_present`,
    so a single torn line never collapses the reduce. This diverges from
    ``state_cli._reduce_events``, which nulls on any malformed line — using
    that here would let a torn log read as unset and emit a futile override.

    Defaults to ``("simple", "medium")`` when ``events_log`` is absent or
    leaves a field unset, matching the canonical reader defaults.
    """
    tier = "simple"
    criticality = "medium"
    if not events_log.exists():
        return (tier, criticality)
    for line in events_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        event = record.get("event")
        if event == "lifecycle_start":
            t = record.get("tier")
            if isinstance(t, str) and t:
                tier = t
            c = record.get("criticality")
            if isinstance(c, str) and c:
                criticality = c
        elif event == "complexity_override":
            t = record.get("to")
            if isinstance(t, str) and t:
                tier = t
        elif event == "criticality_override":
            c = record.get("to")
            if isinstance(c, str) and c:
                criticality = c
    return (tier, criticality)


def _cmd_reconcile_clarify(args: argparse.Namespace) -> int:
    """Reconcile ``events.log`` to the Clarify-determined tier/criticality.

    Appends ``to``-keyed ``complexity_override``/``criticality_override`` rows
    (gate ``clarify_reconcile``) to bring the lifecycle state into agreement
    with the values Clarify assessed, under four guards:

    - **State-based no-op (R3):** emit nothing for a field already at the
      desired value — makes the command idempotent and safe on resume.
    - **Monotonic no-downgrade (R4):** emit only when the desired value ranks
      strictly above the current reduced value; never lower it.
    - **Tolerant read (R5):** :func:`_reduce_current_state` skips malformed
      lines rather than collapsing to null.
    - **Append-only (R6):** never rewrites existing rows, including the
      ``lifecycle_start`` seed.

    Desired-value resolution: explicit ``--complexity``/``--criticality``
    flags (Context B) win per-field over the values read from backlog
    frontmatter (Context A); absent both, the canonical defaults apply.
    """
    lifecycle_slug: str = args.lifecycle_slug
    backlog_slug: str | None = args.backlog_slug

    events_log = Path("cortex/lifecycle") / lifecycle_slug / "events.log"
    events_log.parent.mkdir(parents=True, exist_ok=True)

    # Desired values: explicit flags take precedence over backlog frontmatter.
    base_tier, base_criticality = _read_backlog_frontmatter(backlog_slug)
    desired_tier = args.complexity if args.complexity is not None else base_tier
    desired_criticality = (
        args.criticality if args.criticality is not None else base_criticality
    )

    current_tier, current_criticality = _reduce_current_state(events_log)

    ts = _now_iso()
    rows: list[dict] = []
    if _TIER_RANK.get(desired_tier, -1) > _TIER_RANK.get(current_tier, -1):
        rows.append(
            {
                "ts": ts,
                "event": "complexity_override",
                "feature": lifecycle_slug,
                "from": current_tier,
                "to": desired_tier,
                "gate": "clarify_reconcile",
            }
        )
    if _CRITICALITY_RANK.get(desired_criticality, -1) > _CRITICALITY_RANK.get(
        current_criticality, -1
    ):
        rows.append(
            {
                "ts": ts,
                "event": "criticality_override",
                "feature": lifecycle_slug,
                "from": current_criticality,
                "to": desired_criticality,
                "gate": "clarify_reconcile",
            }
        )

    # State-based no-op: already reconciled (or a downgrade was suppressed).
    if not rows:
        return 0

    try:
        with open(events_log, "a", encoding="utf-8") as f:
            for row in rows:
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

    return 0


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

    # reconcile-clarify
    rc = sub.add_parser(
        "reconcile-clarify",
        help=(
            "Append complexity_override/criticality_override rows to reconcile "
            "events.log to the Clarify-determined tier/criticality. Idempotent "
            "(state-based no-op) and monotonic (never downgrades)."
        ),
    )
    rc.add_argument(
        "--lifecycle-slug",
        required=True,
        help="Lifecycle feature slug under cortex/lifecycle/.",
    )
    rc.add_argument(
        "--backlog-slug",
        default=None,
        help=(
            "Backlog filename slug (without .md). Sources the desired tier/"
            "criticality from frontmatter (Context A). Omit for Context B."
        ),
    )
    rc.add_argument(
        "--complexity",
        default=None,
        choices=sorted(_ALLOWED_COMPLEXITY),
        help=(
            "Explicit desired tier (Context B). Takes precedence over the "
            "backlog-derived value when both are supplied."
        ),
    )
    rc.add_argument(
        "--criticality",
        default=None,
        choices=sorted(_ALLOWED_CRITICALITY),
        help=(
            "Explicit desired criticality (Context B). Takes precedence over "
            "the backlog-derived value when both are supplied."
        ),
    )
    rc.set_defaults(func=_cmd_reconcile_clarify)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
