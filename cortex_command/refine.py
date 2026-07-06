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
from cortex_command.common import reduce_lifecycle_state


# Allowed value sets, kept in lockstep with the canonical readers at
# ``cortex_command/common.py:_read_criticality_inner`` and ``_read_tier_inner``.
_ALLOWED_CRITICALITY: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
_ALLOWED_COMPLEXITY: frozenset[str] = frozenset({"simple", "complex"})

# Legacy pre-two-tier complexity vocabulary, coerced with a stderr warning
# instead of hard-failing (readers tolerate every prior shape — see
# clarify-critic.md's event-schema rule). Mid-scale values map to "complex"
# per clarify.md §5's "when in doubt, prefer complex"; Clarify re-assesses
# and writes the reconciled value back regardless.
_LEGACY_COMPLEXITY_MAP: dict[str, str] = {
    "trivial": "simple",
    "medium": "complex",
    "moderate": "complex",
}

# The regex frontmatter reader returns YAML nulls as literal strings; treat
# them as an absent key (defaults apply) rather than an invalid value.
_YAML_NULL_LITERALS: frozenset[str] = frozenset({"null", "~", "None"})

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
    ``complexity`` against ``{simple, complex}``. Legacy pre-two-tier
    complexity values (``trivial``, ``medium``, ``moderate``) are coerced
    via :data:`_LEGACY_COMPLEXITY_MAP` with a stderr warning; YAML null
    literals are treated as absent. On any other invalid value, prints a
    stderr diagnostic naming the invalid value, file path, allowed set,
    and the ``cortex-update-item`` remediation, then exits with status 64
    (``EX_USAGE``).
    """
    if backlog_slug is None:
        return ("simple", "medium")

    backlog_path = Path("cortex/backlog") / f"{backlog_slug}.md"
    if not backlog_path.exists():
        return ("simple", "medium")

    text = backlog_path.read_text(encoding="utf-8")
    criticality = _get_frontmatter_value(text, "criticality")
    complexity = _get_frontmatter_value(text, "complexity")

    if criticality is None or criticality in _YAML_NULL_LITERALS:
        criticality = "medium"
    elif criticality not in _ALLOWED_CRITICALITY:
        allowed = ", ".join(sorted(_ALLOWED_CRITICALITY))
        print(
            f"cortex-refine: invalid criticality value {criticality!r} in "
            f"{backlog_path} (allowed: {allowed}). Fix with: "
            f"cortex-update-item {backlog_slug} --criticality <value>",
            file=sys.stderr,
        )
        sys.exit(64)

    if complexity is None or complexity in _YAML_NULL_LITERALS:
        complexity = "simple"
    elif complexity in _LEGACY_COMPLEXITY_MAP:
        coerced = _LEGACY_COMPLEXITY_MAP[complexity]
        print(
            f"cortex-refine: legacy complexity value {complexity!r} in "
            f"{backlog_path} coerced to {coerced!r} (Clarify re-assesses "
            f"and writes back the two-tier value)",
            file=sys.stderr,
        )
        complexity = coerced
    elif complexity not in _ALLOWED_COMPLEXITY:
        allowed = ", ".join(sorted(_ALLOWED_COMPLEXITY))
        print(
            f"cortex-refine: invalid complexity value {complexity!r} in "
            f"{backlog_path} (allowed: {allowed}). Fix with: "
            f"cortex-update-item {backlog_slug} --complexity <value>",
            file=sys.stderr,
        )
        sys.exit(64)

    return (complexity, criticality)


def _apply_backend_guard(backend: str, backlog_slug: str | None) -> str | None:
    """Structural guard: drop a local backlog slug on a non-local backend.

    Acts only on the caller-passed ``--backend`` value (already ``.strip()``'d
    by the caller) — it does NOT resolve the backend or read config (the skill
    resolves the backend via ``cortex-read-backlog-backend`` and passes the
    value). When the backend is not ``cortex-backlog`` AND a ``--backlog-slug``
    was passed, coerce the slug to ``None`` so no (possibly stale) local backlog
    file is read, and emit a path-accurate stderr diagnostic naming the ignored
    slug and the backend. Returns the (possibly coerced) slug.

    The diagnostic describes only the slug handling — uniform across the seed,
    idempotent short-circuit, and reconcile paths — so it stays accurate
    wherever the guard runs. Gating the message on ``backlog_slug is not None``
    keeps it silent on the common no-slug Context-B call.
    """
    if backend != "cortex-backlog" and backlog_slug is not None:
        print(
            f"cortex-refine: ignoring --backlog-slug {backlog_slug!r} on "
            f"non-local backend {backend!r}",
            file=sys.stderr,
        )
        return None
    return backlog_slug


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

    Delegates to :func:`cortex_command.common.reduce_lifecycle_state`, the single
    tolerant reducer shared by all three reader sites (``state_cli``,
    ``read_tier``/``read_criticality``, and this function), so they agree by
    construction. A single torn or out-of-vocabulary line is skipped rather than
    collapsing the reduce.

    Defaults to ``("simple", "medium")`` when ``events_log`` is absent or leaves
    a field unset, matching the canonical reader defaults.
    """
    state = reduce_lifecycle_state(events_log).state
    return (state.get("tier", "simple"), state.get("criticality", "medium"))


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
    backlog_slug = _apply_backend_guard(args.backend.strip(), backlog_slug)

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
    backlog_slug = _apply_backend_guard(args.backend.strip(), backlog_slug)

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


def _cmd_resume_point(args: argparse.Namespace) -> int:
    """Classify the refine resume state from lifecycle artifact-stat.

    Read-only: stats ``cortex/lifecycle/{slug}/{spec,research}.md`` and prints a
    single-line JSON object to stdout — no writes, no backend, no events. The
    resume value is the load-bearing field; the two booleans are a convenience
    for a data-driven warn message and a cleaner test surface.

    Existence is ``is_file()`` (NOT ``exists()``): a directory named
    ``spec.md``/``research.md`` does not count, while an empty-but-present
    ``spec.md`` does (the non-empty check is a separate post-research gate).

    Determination: ``spec ∧ research`` → ``complete``; ``spec ∧ ¬research`` →
    ``research``; ``research ∧ ¬spec`` → ``spec``; else (incl. a missing
    lifecycle dir) → ``clarify``. Always exits 0 — every state is a successful
    determination, and there is no write path that could fail.
    """
    lifecycle_slug: str = args.lifecycle_slug

    base = Path("cortex/lifecycle") / lifecycle_slug
    spec_exists = (base / "spec.md").is_file()
    research_exists = (base / "research.md").is_file()

    if spec_exists and research_exists:
        resume = "complete"
    elif spec_exists:
        resume = "research"
    elif research_exists:
        resume = "spec"
    else:
        resume = "clarify"

    print(
        json.dumps(
            {
                "resume": resume,
                "spec_exists": spec_exists,
                "research_exists": research_exists,
            },
            separators=(",", ":"),
        )
    )
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
    el.add_argument(
        "--backend",
        default="cortex-backlog",
        help=(
            "Caller-resolved backlog backend (the skill resolves it via "
            "cortex-read-backlog-backend). Structural guard only: when not "
            "'cortex-backlog', --backlog-slug is ignored (no local file is "
            "read) and a stderr diagnostic is emitted. This verb does NOT "
            "resolve the backend itself. Default: cortex-backlog."
        ),
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
    rc.add_argument(
        "--backend",
        default="cortex-backlog",
        help=(
            "Caller-resolved backlog backend (the skill resolves it via "
            "cortex-read-backlog-backend). Structural guard only: when not "
            "'cortex-backlog', --backlog-slug is ignored (no local file is "
            "read) and a stderr diagnostic is emitted. The explicit "
            "--complexity/--criticality flags still drive. This verb does NOT "
            "resolve the backend itself. Default: cortex-backlog."
        ),
    )
    rc.set_defaults(func=_cmd_reconcile_clarify)

    # resume-point
    rp = sub.add_parser(
        "resume-point",
        help=(
            "Classify the refine resume state from lifecycle artifact-stat. "
            "Read-only: prints a single-line JSON object "
            '{"resume":...,"spec_exists":...,"research_exists":...} to stdout '
            "and exits 0 for every state."
        ),
    )
    rp.add_argument(
        "--lifecycle-slug",
        required=True,
        help="Lifecycle feature slug under cortex/lifecycle/.",
    )
    rp.set_defaults(func=_cmd_resume_point)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
