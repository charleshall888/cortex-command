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

from cortex_command.backlog.resolve_item import ResolutionError
from cortex_command.backlog.resolve_item import _build_json as _build_item_json
from cortex_command.backlog.resolve_item import _parse_frontmatter as _parse_item_frontmatter
from cortex_command.backlog.resolve_item import resolve as _resolve_backlog
from cortex_command.backlog.update_item import _get_frontmatter_value
from cortex_command.common import (
    _resolve_user_project_root_from_cwd as _project_root,
    reduce_lifecycle_state,
)
from cortex_command.lifecycle import session_marker
from cortex_command.lifecycle.create_index import create_index
from cortex_command.lifecycle_config import resolve_backlog_backend
from cortex_command.lifecycle_event import log_event_at


# Every subcommand below builds a filesystem path from --lifecycle-slug, which
# arrives either from the flag or from a backlog item's `lifecycle_slug:`
# frontmatter. Refine was the one lifecycle-writing surface with no slug guard,
# so a `..` slug wrote events.log and the session marker outside
# cortex/lifecycle/ entirely. Message shared so all three arms read alike.
_UNSAFE_SLUG_MSG = (
    "cortex-refine: unsafe lifecycle slug {slug!r}: no path separators or '..'"
)

# Allowed value sets, kept in lockstep with the canonical readers at
# ``cortex_command/common.py:_read_criticality_inner`` and ``_read_tier_inner``.
_ALLOWED_CRITICALITY: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
_ALLOWED_COMPLEXITY: frozenset[str] = frozenset({"simple", "moderate", "complex"})

# Legacy complexity vocabulary, coerced with a stderr warning instead of
# hard-failing (readers tolerate every prior shape — see clarify-critic.md's
# event-schema rule). Clarify re-assesses and writes the reconciled value back
# regardless.
#
# The two-tier era wrote ``simple`` for what the three-tier vocabulary calls
# ``moderate`` — a feature that enters the lifecycle and takes the short road.
# That value is NOT remapped: both lower tiers satisfy the short road's
# ``tier != complex`` predicate, so a historical ``simple`` replays identically
# either way, and rewriting it would falsify what the run actually recorded.
# ``trivial`` was the old name for the new lightest tier.
_LEGACY_COMPLEXITY_MAP: dict[str, str] = {
    "trivial": "simple",
    "medium": "moderate",
}

# The regex frontmatter reader returns YAML nulls as literal strings; treat
# them as an absent key (defaults apply) rather than an invalid value.
_YAML_NULL_LITERALS: frozenset[str] = frozenset({"null", "~", "None"})

# Monotonic ordering for the no-downgrade guard (R4). An override is appended
# only when the desired value ranks strictly above the current reduced value.
# Unknown values rank below every canonical value (-1) so a non-canonical
# current state reconciles up toward a canonical desired value rather than
# raising a KeyError.
_TIER_RANK: dict[str, int] = {"simple": 0, "moderate": 1, "complex": 2}
_CRITICALITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _read_backlog_frontmatter(
    backlog_slug: str | None,
) -> tuple[str, str, frozenset[str]]:
    """Return ``(tier, criticality, seeded)`` from a backlog item's frontmatter.

    ``seeded`` names the fields that fell back to a default rather than
    carrying an assessed value — a subset of ``{"tier", "criticality"}``. The
    defaults below are placeholders, not judgments, but nothing downstream
    could tell the difference: every escalation from the floor reads
    ``simple -> complex`` whether or not ``moderate`` was ever weighed. The
    set makes the placeholder legible without changing its *value*, which
    must stay at the rank floor for the reason given below.

    When ``backlog_slug`` is ``None`` or the backlog file does not exist,
    returns ``("simple", "medium")`` — the *rank floor*, deliberately NOT the
    reader default of ``"moderate"``. This value feeds the monotonic-up
    reconcile: an absent backlog value is not an authoritative assessment, so
    it must be inert for the ratchet. Defaulting to ``"moderate"`` here would
    ratchet every legitimately ``simple`` feature up one tier the first time
    reconcile ran without a backlog file. Reader defaults live in
    ``_read_tier_inner`` and are a separate question — matching the
    behavior of ``_read_tier_inner`` / ``_read_criticality_inner`` when no
    ``lifecycle_start`` event has been emitted.

    When the file exists, reads ``cortex/backlog/{backlog_slug}.md`` and
    extracts ``complexity:`` (mapped to ``tier``) and ``criticality:`` via
    :func:`_get_frontmatter_value`. Absent keys fall back to defaults.

    Validates ``criticality`` against ``{low, medium, high, critical}`` and
    ``complexity`` against ``{simple, moderate, complex}``. Legacy
    complexity values (``trivial``, ``medium``) are coerced
    via :data:`_LEGACY_COMPLEXITY_MAP` with a stderr warning; YAML null
    literals are treated as absent. On any other invalid value, prints a
    stderr diagnostic naming the invalid value, file path, allowed set,
    and the ``cortex-update-item`` remediation, then exits with status 64
    (``EX_USAGE``).
    """
    _BOTH_SEEDED = frozenset({"tier", "criticality"})
    if backlog_slug is None:
        return ("simple", "medium", _BOTH_SEEDED)

    backlog_path = Path("cortex/backlog") / f"{backlog_slug}.md"
    if not backlog_path.exists():
        return ("simple", "medium", _BOTH_SEEDED)

    text = backlog_path.read_text(encoding="utf-8")
    criticality = _get_frontmatter_value(text, "criticality")
    complexity = _get_frontmatter_value(text, "complexity")

    seeded: set[str] = set()

    if criticality is None or criticality in _YAML_NULL_LITERALS:
        criticality = "medium"
        seeded.add("criticality")
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
        seeded.add("tier")
    elif complexity in _LEGACY_COMPLEXITY_MAP:
        coerced = _LEGACY_COMPLEXITY_MAP[complexity]
        print(
            f"cortex-refine: legacy complexity value {complexity!r} in "
            f"{backlog_path} coerced to {coerced!r} (Clarify re-assesses "
            f"and writes back the canonical value)",
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

    return (complexity, criticality, frozenset(seeded))


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
    return (state.get("tier", "moderate"), state.get("criticality", "medium"))


def _seeded_fields_at_start(events_log: Path) -> frozenset[str]:
    """Return the fields ``lifecycle_start`` recorded as rank-floor placeholders.

    Reads the ``seeded`` key this module writes in
    :func:`_cmd_emit_lifecycle_start`. Empty when the row predates that key or
    carried two assessed values — both mean "nothing known to be a placeholder",
    which is the safe reading: a marker is only ever added, never assumed.
    """
    if not events_log.exists():
        return frozenset()
    try:
        for line in events_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if row.get("event") == "lifecycle_start":
                seeded = row.get("seeded")
                if isinstance(seeded, list):
                    return frozenset(s for s in seeded if isinstance(s, str))
                return frozenset()
    except OSError:
        pass
    return frozenset()


def _fields_already_overridden(events_log: Path) -> frozenset[str]:
    """Return which of ``tier``/``criticality`` an override has already moved.

    Once a field carries an override its current value is an assessment, so the
    seed marker no longer describes it.
    """
    if not events_log.exists():
        return frozenset()
    found: set[str] = set()
    try:
        for line in events_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if row.get("event") == "complexity_override":
                found.add("tier")
            elif row.get("event") == "criticality_override":
                found.add("criticality")
    except OSError:
        pass
    return frozenset(found)


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
    if session_marker.is_unsafe_slug(lifecycle_slug):
        print(_UNSAFE_SLUG_MSG.format(slug=lifecycle_slug), file=sys.stderr)
        return 2
    backlog_slug: str | None = args.backlog_slug
    backlog_slug = _apply_backend_guard(args.backend.strip(), backlog_slug)

    events_log = Path("cortex/lifecycle") / lifecycle_slug / "events.log"
    events_log.parent.mkdir(parents=True, exist_ok=True)

    # Desired values: explicit flags take precedence over backlog frontmatter.
    base_tier, base_criticality, _seeded = _read_backlog_frontmatter(backlog_slug)
    desired_tier = args.complexity if args.complexity is not None else base_tier
    desired_criticality = (
        args.criticality if args.criticality is not None else base_criticality
    )

    current_tier, current_criticality = _reduce_current_state(events_log)

    # Which of the values we are about to move *from* are rank-floor
    # placeholders rather than assessments. Without this an override row reads
    # `simple -> complex` identically whether `moderate` was weighed and
    # rejected or never considered at all — and the override row is what every
    # corpus count reads, so the marker on lifecycle_start alone forces a join
    # that no reader performs. Only meaningful before the first override moves
    # a field; after that the current value is an assessment, not the seed.
    seeded_at_start = _seeded_fields_at_start(events_log)
    moved = _fields_already_overridden(events_log)
    tier_from_seed = "tier" in seeded_at_start and "tier" not in moved
    crit_from_seed = "criticality" in seeded_at_start and "criticality" not in moved

    ts = _now_iso()
    rows: list[dict] = []
    # The values the log will hold once these rows land — reported back so the
    # caller can route on the reconciled state without a second round-trip.
    new_tier, new_criticality = current_tier, current_criticality
    if _TIER_RANK.get(desired_tier, -1) > _TIER_RANK.get(current_tier, -1):
        new_tier = desired_tier
        rows.append(
            {
                "ts": ts,
                "event": "complexity_override",
                "feature": lifecycle_slug,
                "from": current_tier,
                "to": desired_tier,
                "gate": "clarify_reconcile",
                **({"from_seeded": True} if tier_from_seed else {}),
            }
        )
    if _CRITICALITY_RANK.get(desired_criticality, -1) > _CRITICALITY_RANK.get(
        current_criticality, -1
    ):
        new_criticality = desired_criticality
        rows.append(
            {
                "ts": ts,
                "event": "criticality_override",
                "feature": lifecycle_slug,
                "from": current_criticality,
                "to": desired_criticality,
                "gate": "clarify_reconcile",
                **({"from_seeded": True} if crit_from_seed else {}),
            }
        )

    # State-based no-op: already reconciled (or a downgrade was suppressed).
    # Reported rather than silent — the call is a state ratchet whose result a
    # later gate reads (specify.md decides whether to run critical-review from
    # the tier/criticality reconciled here), and an empty stdout left the caller
    # unable to tell "ratcheted" from "already reconciled" from "suppressed a
    # downgrade" without a second cortex-lifecycle-state round-trip.
    # `noop` is the common, legitimate result on resume — not an error.
    if not rows:
        print(
            json.dumps(
                {
                    "state": "noop",
                    "rows": 0,
                    "tier": current_tier,
                    "criticality": current_criticality,
                },
                separators=(",", ":"),
            )
        )
        return 0

    # Route every append through the shared locked primitive (flock + O_APPEND)
    # rather than a bare unlocked open("a") — R1. ``log_event_at`` takes the
    # explicit path refine already resolved (preserving the CWD-relative write
    # target the writer-site baseline pins) and preserves the extra ``gate``
    # field that the typed criticality-override subcommand cannot carry.
    try:
        for row in rows:
            log_event_at(events_log, row)
    except (PermissionError, OSError) as e:
        print(
            f"cortex-refine: failed to append to {events_log}: {e}. "
            f"Ensure the cortex/ umbrella is registered for sandbox writes "
            f"(run `cortex init` to register it in "
            f"~/.claude/settings.local.json's sandbox.filesystem.allowWrite).",
            file=sys.stderr,
        )
        return 70

    print(
        json.dumps(
            {
                "state": "ratcheted",
                "rows": len(rows),
                "tier": new_tier,
                "criticality": new_criticality,
                "overrides": [
                    {"field": r["event"], "from": r["from"], "to": r["to"]}
                    for r in rows
                ],
            },
            separators=(",", ":"),
        )
    )
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
    if session_marker.is_unsafe_slug(lifecycle_slug):
        print(_UNSAFE_SLUG_MSG.format(slug=lifecycle_slug), file=sys.stderr)
        return 2
    backlog_slug: str | None = args.backlog_slug
    backlog_slug = _apply_backend_guard(args.backend.strip(), backlog_slug)

    events_log = Path("cortex/lifecycle") / lifecycle_slug / "events.log"
    events_log.parent.mkdir(parents=True, exist_ok=True)

    if _lifecycle_start_present(events_log):
        return 0

    tier, criticality, seeded = _read_backlog_frontmatter(backlog_slug)

    row = {
        "schema_version": 1,
        "ts": _now_iso(),
        "event": "lifecycle_start",
        "feature": lifecycle_slug,
        "tier": tier,
        "criticality": criticality,
        "entry_point": "refine",
    }
    # Field-additive marker: names any value in this row that is a rank-floor
    # placeholder rather than an assessment. Emitted only when something was
    # actually seeded, so rows carrying two real values keep their existing
    # shape and no reader has to learn a new key to stay correct.
    if seeded:
        row["seeded"] = sorted(seeded)

    # Route the seed append through the shared locked primitive (flock +
    # O_APPEND) rather than a bare unlocked open("a") — R1. ``log_event_at``
    # takes the explicit CWD-relative path refine resolved and preserves the
    # extra ``schema_version``/``entry_point`` fields the typed lifecycle-start
    # subcommand cannot carry.
    try:
        log_event_at(events_log, row)
    except (PermissionError, OSError) as e:
        print(
            f"cortex-refine: failed to append to {events_log}: {e}. "
            f"Ensure the cortex/ umbrella is registered for sandbox writes "
            f"(run `cortex init` to register it in "
            f"~/.claude/settings.local.json's sandbox.filesystem.allowWrite).",
            file=sys.stderr,
        )
        return 70

    # Read-after-write verify: match our row by parsed fields ANYWHERE in the
    # log rather than by file tail (R2). A concurrent append landing between the
    # write above and this read would otherwise displace our row from the tail
    # and produce a false mismatch. The idempotency guard guarantees at most one
    # lifecycle_start row, so an event+feature match uniquely identifies ours.
    try:
        with open(events_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(
            f"cortex-refine: read_after_write_io_error reading {events_log}: {e}",
            file=sys.stderr,
        )
        return 70

    found = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(obj, dict)
            and obj.get("event") == "lifecycle_start"
            and obj.get("feature") == lifecycle_slug
        ):
            found = True
            break

    if not found:
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


def _epic_context(backlog_path: Path | None) -> dict:
    """Resolve the item's epic-research and epic-spec paths, existence-checked.

    ``discovery_source`` wins over ``research``; the spec path is recorded only
    alongside a recorded, existing research path. A referenced-but-absent file
    yields ``epic_research: null`` plus a ``warning`` the caller relays, so the
    skill never has to stat these itself.
    """
    out: dict = {"epic_research": None, "epic_spec": None, "warning": None}
    if backlog_path is None or not backlog_path.is_file():
        return out
    text = backlog_path.read_text(encoding="utf-8")
    raw = _get_frontmatter_value(text, "discovery_source") or _get_frontmatter_value(
        text, "research"
    )
    if raw is None or raw in _YAML_NULL_LITERALS:
        return out
    if not Path(raw).is_file():
        out["warning"] = f"epic research path {raw!r} referenced but missing — treating as unset"
        return out
    out["epic_research"] = raw
    spec = _get_frontmatter_value(text, "spec")
    if spec is not None and spec not in _YAML_NULL_LITERALS and Path(spec).is_file():
        out["epic_spec"] = spec
    return out


def _cmd_start(args: argparse.Namespace) -> int:
    """Compose refine's entry: resolve, backend, epic context, resume, seed.

    Replaces the four-round-trip opening sequence (``cortex-resolve-backlog-item``
    → ``cortex-read-backlog-backend`` → ``cortex-refine resume-point`` →
    ``cortex-refine emit-lifecycle-start``) with one call.

    Exit codes mirror the verbs it absorbs: ``2`` on an ambiguous reference
    (candidates on stderr, nothing seeded), ``70`` on a seed write failure.
    Otherwise ``0`` with a ``context``-tagged envelope. A reference that
    matches nothing is Context B: without ``--lifecycle-slug`` the verb
    returns ``state: "needs-slug"`` and seeds nothing, because deriving the
    kebab slug from prose is the caller's judgment.
    """
    backlog_dir = Path("cortex/backlog")
    resolution = None
    if not args.no_resolve:
        try:
            resolution = _resolve_backlog(args.reference, backlog_dir)
        except ResolutionError as exc:
            print(f"cortex-refine: {exc}", file=sys.stderr)
            return 70
        if resolution.status == "ambiguous":
            print(
                f"cortex-refine: ambiguous reference {args.reference!r}; "
                f"re-invoke with one of:",
                file=sys.stderr,
            )
            for candidate in resolution.candidates:
                print(f"  {candidate.stem}", file=sys.stderr)
            return 2

    backend = resolve_backlog_backend(_project_root())

    item = None
    backlog_path = None
    if resolution is not None and resolution.status == "ok":
        backlog_path = resolution.item
        item = _build_item_json(backlog_path, _parse_item_frontmatter(backlog_path))

    context = "A" if item is not None else "B"
    lifecycle_slug = args.lifecycle_slug or (
        item["lifecycle_slug"] if item is not None else None
    )
    if lifecycle_slug is None:
        print(
            json.dumps(
                {
                    "state": "needs-slug",
                    "context": "B",
                    "backend": backend,
                    "message": (
                        f"No backlog item matches {args.reference!r}. Derive a "
                        f"3-6 word kebab-case lifecycle slug, announce it, and "
                        f"re-run with --lifecycle-slug."
                    ),
                },
                separators=(",", ":"),
            )
        )
        return 0

    # Slug guard BEFORE any write. The slug reaches here from --lifecycle-slug
    # or from a backlog item's `lifecycle_slug:` frontmatter, and every path
    # below builds a filesystem location from it; a `..` slug wrote events.log
    # and the session marker outside cortex/lifecycle/ entirely. The sibling
    # lifecycle verbs all carry this blacklist predicate — refine did not.
    if session_marker.is_unsafe_slug(lifecycle_slug):
        print(_UNSAFE_SLUG_MSG.format(slug=lifecycle_slug), file=sys.stderr)
        return 2

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

    seed_args = argparse.Namespace(
        lifecycle_slug=lifecycle_slug,
        backlog_slug=(item["backlog_filename_slug"] if context == "A" else None),
        backend=backend,
    )
    rc = _cmd_emit_lifecycle_start(seed_args)
    if rc != 0:
        return rc

    # Refine is a first-class session owner, not just a build-phase concern.
    # Nothing else writes the marker before Clarify, so every verb that resolves
    # a feature *by session id* used to come up empty during refine — most
    # damagingly the critical-review residue writer, which returned
    # {"state": "no-context"} at exit 0 and silently discarded the findings of a
    # review that specify.md had mandated.
    root = _project_root()
    session_id = args.session_id or session_marker.session_id_from_env()
    session_recorded = False
    if session_id:
        try:
            session_marker.write_session(root, lifecycle_slug, session_id)
            session_recorded = True
        except OSError:
            # The marker is a local convenience; failing to write it must not
            # fail refine's entry. The envelope reports the miss instead.
            session_recorded = False

    # Create index.md here rather than leaving it to the build phase. It is the
    # tag source cortex-load-requirements reads, and before this the file could
    # not exist until `enter`, so Clarify's requirements-alignment rating -- which
    # feeds the critical-review gate -- was made against project.md alone even
    # for a ticket carrying area tags.
    index_signal = None
    if context == "A" and item is not None:
        try:
            index_signal = create_index(
                lifecycle_slug, item["filename"], root
            ).get("signal")
        except OSError:
            # A resolvable item whose file vanished between resolve and here.
            index_signal = "error"

    envelope = {
        "state": "ready",
        "context": context,
        "backend": backend,
        "lifecycle_slug": lifecycle_slug,
        "resume": resume,
        "spec_exists": spec_exists,
        "research_exists": research_exists,
        "session_recorded": session_recorded,
    }
    if index_signal is not None:
        envelope["index"] = index_signal
    if item is not None:
        envelope["filename"] = item["filename"]
        envelope["backlog_filename_slug"] = item["backlog_filename_slug"]
        envelope["title"] = item["title"]
    envelope.update(
        {k: v for k, v in _epic_context(backlog_path).items() if v is not None}
    )
    print(json.dumps(envelope, separators=(",", ":")))
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

    # start
    st = sub.add_parser(
        "start",
        help=(
            "Compose refine's entry in one call: resolve the reference, read "
            "the backlog backend, existence-check epic context, classify the "
            "resume point, and idempotently seed lifecycle_start. Prints one "
            "JSON envelope. Exit 2 = ambiguous reference (candidates on "
            "stderr); 70 = seed write failure."
        ),
    )
    st.add_argument(
        "reference",
        help="Any backlog reference — numeric ID, slug, UUID prefix, or title phrase.",
    )
    st.add_argument(
        "--lifecycle-slug",
        default=None,
        help=(
            "Override the resolved lifecycle slug. Required on the Context-B "
            "path, where the caller derives the kebab slug from prose."
        ),
    )
    st.add_argument(
        "--no-resolve",
        action="store_true",
        help="Skip backlog resolution and treat the run as Context B (ad-hoc).",
    )
    st.add_argument(
        "--session-id",
        default=None,
        help=(
            "Session id to record as the lifecycle's owner; defaults to "
            "$LIFECYCLE_SESSION_ID. The marker is what lets later verbs resolve "
            "this feature by session (e.g. the critical-review residue writer). "
            "Local and gitignored — never committed."
        ),
    )
    st.set_defaults(func=_cmd_start)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
