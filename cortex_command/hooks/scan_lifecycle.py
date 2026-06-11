"""SessionStart lifecycle scanner.

Implements the ``cortex hooks scan-lifecycle`` subcommand. Reads a Claude
Code SessionStart hook JSON payload on stdin (containing ``session_id``
and ``cwd``), then performs lifecycle-state detection, session-state
mutation, phase encoding, and ``hookSpecificOutput`` emission to inject
lifecycle context into the session.

This module is the Python port of ``hooks/cortex-scan-lifecycle.sh`` per
the resolve-cortex-interpreter-via-cli feature. The skeleton currently
parses input and exits 0 with no output; subsequent tasks fill in the
behavior progressively.

Imports of ``cortex_command.common`` and other intra-package modules are
kept inside the functions that need them (lazy-load discipline per the
overnight precedent at ``cortex_command/cli.py:48-66``), so ``--help``
and trivial dispatch paths do not pay the cost of the full package graph.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cortex_command.hooks._pipeline_state import PipelineState


def _encode_phase(phase: str, checked: int, total: int, cycle: int) -> str:
    """Encode (phase, checked, total, cycle) into the wire-format string.

    Mirrors the bash ``encode_phase`` helper at
    ``hooks/cortex-scan-lifecycle.sh`` lines 184-200. Pure function: no
    I/O, no side effects. Downstream code consumes the encoded string to
    produce phase labels like ``"Phase: Implement (3/5 tasks done)"``.

    Encoding rules per R3:

    * ``phase == "implement"`` and ``total > 0``  -> ``"implement:<checked>/<total>"``
    * ``phase == "implement"`` and ``total == 0`` -> ``"implement:0/0"``
    * ``phase == "implement-rework"``             -> ``"implement-rework:<cycle>"``
    * any other phase                             -> bare ``phase`` string

    Parameters
    ----------
    phase:
        Lifecycle phase identifier (e.g. ``"research"``, ``"implement"``,
        ``"implement-rework"``).
    checked:
        Number of completed implementation tasks.
    total:
        Total implementation tasks.
    cycle:
        Implement-rework cycle index.

    Returns
    -------
    str
        The wire-format encoded phase string.
    """

    paused_suffix = "-paused" if phase.endswith("-paused") else ""
    base_phase = phase.removesuffix("-paused")
    if base_phase == "implement":
        payload = f"{checked}/{total}" if total > 0 else "0/0"
        return f"implement{paused_suffix}:{payload}"
    if base_phase == "implement-rework":
        return f"implement-rework{paused_suffix}:{cycle}"
    return f"{base_phase}{paused_suffix}"


def _phase_label(encoded_phase: str) -> str:
    """Translate an encoded phase string into a human-readable label.

    Thin delegating wrapper around :func:`cortex_command.phase_labels.phase_label`,
    the canonical mapping shared with the dashboard (registered as a
    Jinja filter). Pure function: no I/O, no side effects. The bash
    mirror lives at ``hooks/cortex-scan-lifecycle.sh`` and is covered by
    ``tests/test_lifecycle_phase_parity.py``.
    """

    from cortex_command.phase_labels import phase_label

    return phase_label(encoded_phase)


def _interrupted_hint(encoded_phase: str, active_feature: str) -> str:
    """Return a one-line interrupted-state hint, or empty when not applicable.

    Mirrors the bash interrupted-state hint emission at
    ``hooks/cortex-scan-lifecycle.sh`` lines 378-398. Pure function: no
    I/O, no side effects. The caller appends the returned hint to the
    ``additionalContext`` block on its own line; an empty string signals
    "no hint applicable" (no extra line should be emitted).

    Hint rules:

    * ``"implement:<checked>/<total>"`` with ``0 < checked < total``
      -> "Interrupted: implementation in progress ..." hint.
    * ``"implement:<checked>/<total>"`` with ``checked == 0`` or
      ``checked >= total`` -> empty (not-started or fully-done).
    * ``"implement-rework:<cycle>"`` -> "Interrupted: review cycle ..." hint.
    * ``"escalated"`` -> "Action needed: review returned REJECTED ..." hint.
    * any other phase -> empty.

    Parameters
    ----------
    encoded_phase:
        Wire-format phase string as produced by :func:`_encode_phase`.
    active_feature:
        Feature slug of the active lifecycle, used to render the
        ``/cortex-core:lifecycle <feature>`` resume command and the
        ``cortex/lifecycle/<feature>/review.md`` artifact path.

    Returns
    -------
    str
        The hint line (no trailing newline), or an empty string when no
        interrupted-state hint applies.
    """

    # Strip the -paused marker so the existing startswith() prefix checks
    # match paused features. The resume hint text is identical for active
    # vs paused implement features (R10: operator action is the same).
    if "-paused" in encoded_phase:
        encoded_phase = encoded_phase.replace("-paused", "", 1)

    if encoded_phase.startswith("implement:"):
        progress = encoded_phase[len("implement:") :]
        if "/" not in progress:
            return ""
        checked_str, _, total_str = progress.partition("/")
        try:
            checked = int(checked_str)
            total = int(total_str)
        except ValueError:
            return ""
        if checked > 0 and checked < total:
            return (
                f"Interrupted: implementation in progress "
                f"({checked} of {total} tasks done). "
                f"Resume with /cortex-core:lifecycle {active_feature}."
            )
        return ""
    if encoded_phase.startswith("implement-rework:"):
        cycle = encoded_phase[len("implement-rework:") :]
        return (
            f"Interrupted: review cycle {cycle} returned CHANGES_REQUESTED. "
            f"Re-enter implementation to address feedback. "
            f"Resume with /cortex-core:lifecycle {active_feature}."
        )
    if encoded_phase == "escalated":
        return (
            f"Action needed: review returned REJECTED. See "
            f"cortex/lifecycle/{active_feature}/review.md for analysis."
        )
    return ""


def _is_terminal_mismatch(
    events_phase: str,
    backlog_status: str | None,
) -> bool:
    """Return True when the events-derived phase and backlog status disagree
    on whether the feature is terminally complete.

    The two sources of truth — ``events.log`` (via ``detect_lifecycle_phase``)
    and ``cortex/backlog/index.json``'s ``status:`` — should agree on
    whether a feature is "done". A mismatch surfaces the cases that bit
    us in the past:

    - #075-shape: backlog ``status: complete`` but events.log still
      pointing at ``implement`` (someone closed the ticket without
      finishing the lifecycle).
    - inverse #209-shape (pre-fix): events show ``feature_paused`` (now
      "implement-paused" after T2) while backlog reads ``in_progress``,
      and the SessionStart enumeration silently hides the divergence.

    The predicate is symmetric: ``events_terminal != backlog_terminal``
    fires in both directions. Pass ``backlog_status=None`` (no backlog
    row) and the predicate returns False — no mismatch claim without
    evidence.
    """

    events_terminal = (
        events_phase in ("complete", "escalated")
        or events_phase.startswith("complete:")
    )
    if backlog_status is None:
        return False
    from cortex_command.common import TERMINAL_STATUSES
    backlog_terminal = backlog_status in TERMINAL_STATUSES
    return events_terminal != backlog_terminal


def _load_backlog_status_map(
    repo_root: Path,
) -> tuple[dict[str, str], list[str]]:
    """Load ``cortex/backlog/index.json`` once and return a slug→status map.

    Returns
    -------
    tuple[dict[str, str], list[str]]
        The first element is the slug→status mapping (keys are
        ``lifecycle_slug`` values from the index; null/absent slugs are
        skipped). The second element lists ``lifecycle_slug`` values
        that appeared more than once — for the duplicate slugs the
        first-encountered status wins.

    Fail-open: returns ``({}, [])`` when ``index.json`` is absent,
    unreadable, malformed, or shaped unexpectedly. This is intentional
    — the SessionStart hook treats the index as best-effort enrichment
    and must never abort on its absence.
    """

    index_path = repo_root / "cortex" / "backlog" / "index.json"
    try:
        raw = index_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {}, []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}, []
    if not isinstance(data, list):
        return {}, []

    result: dict[str, str] = {}
    duplicates: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("lifecycle_slug")
        if not isinstance(slug, str) or not slug:
            continue
        status = entry.get("status")
        if not isinstance(status, str):
            continue
        if slug in result:
            duplicates.append(slug)
            continue
        result[slug] = status
    return result, duplicates


def _events_log_has_event(events_log: Path, event_name: str) -> bool:
    """Return ``True`` if ``events_log`` contains ``"event": "<event_name>"``.

    Mirrors the bash hook's ``grep -q '"event"[[:space:]]*:[[:space:]]*"X"'``
    test used to detect the ``pr_opened`` / ``feature_complete`` /
    ``feature_wontfix`` events when promoting ``complete`` to
    ``complete:awaiting-merge`` (bash precedent lines 311-321). Returns
    ``False`` for missing/unreadable files (bash ``2>/dev/null`` swallow).
    """

    try:
        content = events_log.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    # Match ``"event"`` followed by any whitespace, colon, any whitespace,
    # then the quoted event name. We don't need a regex here: the bash
    # hook's grep uses ``[[:space:]]*`` which is permissive — we look for
    # the simplest canonical form first and then the spaced variants.
    # In practice events.log is JSONL with no extra whitespace, so the
    # tight form covers production.
    needle_tight = f'"event": "{event_name}"'
    if needle_tight in content:
        return True
    needle_no_space = f'"event":"{event_name}"'
    return needle_no_space in content


def _events_log_meta(feature_dir: Path) -> dict[str, str | None]:
    """Return ``{"latest_ts": str|None, "last_event": str|None}`` for the
    feature's ``events.log``.

    ``latest_ts`` is the maximum ``ts`` field across parseable JSON
    lines (ISO 8601, Z-suffix accepted). ``last_event`` is the
    ``event`` field of the line-position-last JSON event (used by the
    diagnostic, distinct from :func:`_is_stale`'s ts-based staleness).
    Missing / unreadable / unparseable events.log returns
    ``{"latest_ts": None, "last_event": None}`` — fail-open so the
    caller can render a partial diagnostic.
    """

    events_log = feature_dir / "events.log"
    try:
        content = events_log.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {"latest_ts": None, "last_event": None}

    latest_ts: str | None = None
    last_event: str | None = None
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        ts_str = event.get("ts")
        if isinstance(ts_str, str) and ts_str:
            if latest_ts is None or ts_str > latest_ts:
                latest_ts = ts_str
        event_type = event.get("event")
        if isinstance(event_type, str) and event_type:
            last_event = event_type
    return {"latest_ts": latest_ts, "last_event": last_event}


def _emit_diag(record: dict) -> None:
    """Append a single-line JSON record to the session-bound diagnostic.

    Destination: ``cortex/lifecycle/sessions/${LIFECYCLE_SESSION_ID}/scan-lifecycle-diag.jsonl``
    (relative to the current working directory). Fail-open: never raises.
    Silent no-op when ``LIFECYCLE_SESSION_ID`` is unset or empty — the
    diagnostic is best-effort observability, not load-bearing.
    """

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")
    if not session_id:
        return
    try:
        diag_dir = (
            Path(os.getcwd())
            / "cortex"
            / "lifecycle"
            / "sessions"
            / session_id
        )
        diag_dir.mkdir(parents=True, exist_ok=True)
        diag_path = diag_dir / "scan-lifecycle-diag.jsonl"
        with diag_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except (OSError, ValueError, TypeError):
        # Best-effort: diagnostics must never break the hook.
        pass


def _emit_candidate_diag(
    feature_dir: Path,
    feature: str,
    decision: str,
    exclude_reason: str | None,
    encoded_phase: str | None,
    backlog_status_map: dict[str, str],
    stale_days: int,
) -> None:
    """Construct and emit one per-candidate JSONL diagnostic record.

    R14 schema: ``ts``, ``feature``, ``decision`` ("included"/"excluded"),
    ``exclude_reason`` (when excluded — "stale"/"morning_review"/
    "complete_no_pr"), ``latest_event_ts``, ``threshold_days``,
    ``last_event``, ``events_phase``, ``backlog_status``,
    ``index_json_resolved``, ``mismatch``.

    For excluded candidates that haven't reached phase detection (stale,
    morning_review), ``encoded_phase`` is ``None`` and ``mismatch`` is
    ``False``. For complete-no-PR exclusions, ``encoded_phase`` is the
    detected ``complete`` value so the mismatch predicate can still
    surface backlog disagreements (e.g., events=complete but
    backlog=in_progress — the inverse of #075).
    """

    import datetime as _dt

    meta = _events_log_meta(feature_dir)
    backlog_status = backlog_status_map.get(feature)
    has_mismatch = (
        _is_terminal_mismatch(encoded_phase, backlog_status)
        if encoded_phase is not None
        else False
    )
    _emit_diag({
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature": feature,
        "decision": decision,
        "exclude_reason": exclude_reason,
        "latest_event_ts": meta.get("latest_ts"),
        "threshold_days": stale_days,
        "last_event": meta.get("last_event"),
        "events_phase": encoded_phase,
        "backlog_status": backlog_status,
        "index_json_resolved": feature in backlog_status_map,
        "mismatch": has_mismatch,
    })


def _is_stale(feature_dir: Path, threshold_days: int) -> bool:
    """Return True if the latest events.log event is older than threshold_days.

    Uses the max ``ts`` field across parseable JSON lines in
    ``events.log`` — content-based, not mtime — because mtimes get
    falsely reset by ``git mv`` bulk operations (e.g. umbrella
    relocations) and filesystem maintenance. Parses ISO 8601 with
    trailing ``Z`` support; lines without a parseable ts are skipped.
    A lifecycle whose ``events.log`` is missing/unreadable or has no
    parseable ts is treated as stale — covers the skill-test debris
    case (dirs with only ``learnings/`` and no events.log).

    ``threshold_days <= 0`` disables the filter (returns False) for
    users who want bash-equivalent unfiltered behavior.
    """

    if threshold_days <= 0:
        return False
    events_log = feature_dir / "events.log"
    try:
        content = events_log.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return True
    import datetime  # local: only needed when filter is active
    latest: datetime.datetime | None = None
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_str = event.get("ts") if isinstance(event, dict) else None
        if not isinstance(ts_str, str) or not ts_str:
            continue
        normalized = (
            ts_str.replace("Z", "+00:00") if ts_str.endswith("Z") else ts_str
        )
        try:
            ts = datetime.datetime.fromisoformat(normalized)
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return True
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=threshold_days
    )
    return latest < cutoff


def _metrics_summary_line(metrics_file: Path) -> str | None:
    """Build the metrics-summary line from ``metrics.json``.

    Mirrors bash precedent lines 443-469. Returns ``None`` when the
    metrics file is absent or unparseable; otherwise returns the
    single-line summary string the orchestrator appends to the context.

    The shape is:
    ``"Metrics: N completed features | Simple: avg X tasks, Y rework | Complex: avg X tasks, Y rework"``

    where ``N`` is ``len(features)`` and the avg fields default to ``0``
    when missing (bash ``// 0`` fallback). Integers keep their natural
    JSON form (``"0"`` — golden fixtures pin this); floats are rounded
    to 2 decimals so the line doesn't carry full-repr noise like
    ``9.885714285714286``. (The old no-rounding rule mirrored the bash
    hook for parity, but that script is now a thin wrapper delegating
    here, so the constraint is dead.)
    """

    if not metrics_file.is_file():
        return None
    try:
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    features = data.get("features")
    completed = len(features) if isinstance(features, dict) else 0

    aggregates = data.get("aggregates") or {}
    if not isinstance(aggregates, dict):
        aggregates = {}
    simple = aggregates.get("simple") or {}
    if not isinstance(simple, dict):
        simple = {}
    complex_ = aggregates.get("complex") or {}
    if not isinstance(complex_, dict):
        complex_ = {}

    def _fmt(val: object) -> str:
        # ``json.dumps`` of an int gives "3" (the bash hook's `// 0`
        # fallback emits "0" for missing — golden fixtures pin that form).
        if val is None:
            return "0"
        if isinstance(val, bool):
            # Defensive: bools are ints in Python; bash never emits bool here.
            return "0"
        if isinstance(val, float):
            # Floats are means from compute_aggregates; round to 2 decimals
            # so the context line stays readable. Ints must pass through
            # unrounded to keep the golden fixtures byte-identical.
            return json.dumps(round(val, 2))
        if isinstance(val, int):
            return json.dumps(val)
        return str(val)

    m_simple_tasks = _fmt(simple.get("avg_task_count", 0))
    m_simple_rework = _fmt(simple.get("avg_rework_cycles", 0))
    m_complex_tasks = _fmt(complex_.get("avg_task_count", 0))
    m_complex_rework = _fmt(complex_.get("avg_rework_cycles", 0))

    return (
        f"Metrics: {completed} completed features | "
        f"Simple: avg {m_simple_tasks} tasks, {m_simple_rework} rework | "
        f"Complex: avg {m_complex_tasks} tasks, {m_complex_rework} rework"
    )


def _build_additional_context(
    pipeline_state: "PipelineState",
    active_feature: str,
    active_phase: str,
    incomplete: list[tuple[str, str, bool, str | None]],
    lifecycle_dir: Path,
    metrics_summary: str | None = None,
) -> str:
    """Assemble the SessionStart ``additionalContext`` payload.

    Mirrors the bash precedent at lines 368-435 (active-feature header,
    phase line, interrupted hints, other-incomplete enumeration,
    multi-incomplete prompt fallback) and 426-435 (pipeline-context
    prepend) and 471-476 (metrics-summary append). Pure-ish: only the
    interrupted-hint helpers and the phase-label helper are called; no
    I/O beyond what those helpers perform (none).

    Parameters
    ----------
    pipeline_state:
        Pipeline state produced by
        :func:`cortex_command.hooks._pipeline_state.PipelineState.from_path`.
        Its ``context_string`` is prepended when non-empty.
    active_feature:
        Slug of the active feature (empty string when no active feature
        was determined — caller falls through to the multi-incomplete
        prompt branch when ``len(incomplete) > 1``).
    active_phase:
        Encoded phase string for the active feature (empty when no
        active feature). Consumed by :func:`_phase_label` and
        :func:`_interrupted_hint`.
    incomplete:
        Ordered list of ``(feature_slug, encoded_phase)`` pairs for
        every incomplete feature. The active feature is included here
        too; the helper skips it when enumerating "other incomplete
        lifecycles."
    lifecycle_dir:
        ``cortex/lifecycle/`` path. Currently unused by the assembler
        itself (path-derived artifact lines are constant text), but
        exposed for forward compatibility with the orchestrator's
        verification harness.
    metrics_summary:
        Optional metrics-summary line (already built by
        :func:`_metrics_summary_line`). Appended on its own line when
        non-``None`` AND an ``active_feature`` was determined (bash
        gates the metrics append on ``active_feature`` at line 439).

    Returns
    -------
    str
        The complete ``additionalContext`` string ready for the
        ``hookSpecificOutput`` envelope. Empty string signals "no
        context to inject" (caller suppresses the JSON output).
    """

    del lifecycle_dir  # Reserved for future use; bash uses constant text.

    context = ""

    # Look up the active feature's mismatch state from the widened
    # tuple so the active-feature header can carry its own annotation.
    active_has_mismatch = False
    active_backlog_status: str | None = None
    if active_feature:
        for slug, _phase, has_mismatch, backlog_status in incomplete:
            if slug == active_feature:
                active_has_mismatch = has_mismatch
                active_backlog_status = backlog_status
                break

    # T13 helper: mismatch-first sort + soft-budget truncation for the
    # enumerated lifecycle entries. Mismatches are never dropped; only
    # non-mismatch entries get truncated from the end when the assembled
    # context exceeds the 9,000-char soft budget.
    def _sort_and_truncate(
        entries: list[tuple[str, str, bool, str | None]],
        overhead_chars: int,
        budget: int = 9000,
    ) -> tuple[list[str], int, int]:
        # Stable mismatch-first sort (key: 0 if mismatch else 1, then
        # original index).
        indexed = list(enumerate(entries))
        indexed.sort(key=lambda x: (0 if x[1][2] else 1, x[0]))
        sorted_entries = [item for _, item in indexed]
        mismatch_count = sum(1 for e in entries if e[2])

        def _render(entry: tuple[str, str, bool, str | None]) -> str:
            slug, phase, has_mismatch, backlog_status = entry
            annot = (
                f" [mismatch: backlog={backlog_status}]"
                if has_mismatch
                else ""
            )
            return f"  - {slug} ({_phase_label(phase)}){annot}"

        full_lines = [_render(e) for e in sorted_entries]
        max_droppable = len(sorted_entries) - mismatch_count
        dropped = 0
        while True:
            kept = full_lines[: len(full_lines) - dropped] if dropped else list(full_lines)
            tail = [f"  … +{dropped} more"] if dropped else []
            block_size = overhead_chars + sum(len(l) + 1 for l in kept + tail)
            if block_size <= budget or dropped >= max_droppable:
                return kept + tail, mismatch_count, dropped
            dropped += 1

    if active_feature:
        label = _phase_label(active_phase)
        active_annot = (
            f" [mismatch: backlog={active_backlog_status}]"
            if active_has_mismatch
            else ""
        )
        context = (
            f"Active lifecycle: {active_feature} | Phase: {label}{active_annot}\n"
            f"Artifacts: cortex/lifecycle/{active_feature}/"
        )

        hint = _interrupted_hint(active_phase, active_feature)
        if hint:
            context = f"{context}\n{hint}"

        # Note other incomplete features if any (bash lines 401-412).
        others = [
            (slug, phase, has_mismatch, backlog_status)
            for slug, phase, has_mismatch, backlog_status in incomplete
            if slug != active_feature
        ]
        if others:
            # Provisional header — extended with mismatch fragment below.
            mismatch_count = sum(1 for e in others if e[2])
            header_line = "Other incomplete lifecycles:"
            if mismatch_count >= 1:
                header_line = (
                    f"{header_line} — mismatches: {mismatch_count} total"
                )
            footer_line = (
                "Switch with /cortex-core:lifecycle resume <feature>."
            )
            # Overhead = current context + header + footer + 3 separators.
            overhead = (
                len(context) + len(header_line) + len(footer_line) + 3
            )
            entry_lines, _, _ = _sort_and_truncate(others, overhead)
            context = f"{context}\n{header_line}"
            for line in entry_lines:
                context = f"{context}\n{line}"
            context = f"{context}\n{footer_line}"

    elif len(incomplete) > 1:
        # Multiple incomplete, no session match (bash lines 414-424).
        mismatch_count = sum(1 for e in incomplete if e[2])
        header_line = "Multiple incomplete lifecycles — select one to resume:"
        if mismatch_count >= 1:
            header_line = (
                f"{header_line} — mismatches: {mismatch_count} total"
            )
        footer_line = "Resume with /cortex-core:lifecycle resume <feature>."
        overhead = len(header_line) + len(footer_line) + 2
        entry_lines, _, _ = _sort_and_truncate(incomplete, overhead)
        context = header_line
        for line in entry_lines:
            context = f"{context}\n{line}"
        context = f"{context}\n{footer_line}"

    # Prepend pipeline context (bash lines 428-435).
    pipeline_ctx = pipeline_state.context_string
    if pipeline_ctx:
        if context:
            context = f"{pipeline_ctx}\n{context}"
        else:
            context = pipeline_ctx

    # Append metrics summary (bash lines 471-476). Bash gates on
    # ``active_feature`` being non-empty.
    if metrics_summary and active_feature:
        if context:
            context = f"{context}\n{metrics_summary}"
        else:
            context = metrics_summary

    return context


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``cortex hooks scan-lifecycle``.

    Reads a SessionStart hook JSON payload on stdin, parses
    ``session_id`` and ``cwd``, and (in the completed implementation)
    emits a ``hookSpecificOutput`` block on stdout that injects
    lifecycle context for the active feature.

    Parameters
    ----------
    argv:
        Optional command-line argument list. Reserved for future use;
        the skeleton currently ignores it.

    Returns
    -------
    int
        Process exit code. ``0`` indicates the hook ran successfully
        (whether or not it emitted context); nonzero is reserved for
        genuine internal errors per the spec.
    """

    del argv  # Reserved for future use.

    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return 0

    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    if not isinstance(payload, dict):
        return 0

    session_id_raw = payload.get("session_id") or ""
    if not isinstance(session_id_raw, str):
        session_id_raw = ""
    session_id = session_id_raw

    cwd_raw = payload.get("cwd")
    if not isinstance(cwd_raw, str) or not cwd_raw:
        cwd_raw = os.getcwd()
    cwd = Path(cwd_raw)

    # --- Session identity injection (bash precedent lines 7-13) ---
    # Emit before the cwd/lifecycle early-exit so non-cortex sessions still
    # propagate LIFECYCLE_SESSION_ID for downstream hook invocations.
    if session_id:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            export_line = (
                f"export LIFECYCLE_SESSION_ID={shlex.quote(session_id)}\n"
            )
            try:
                with open(env_file, "a", encoding="utf-8") as fh:
                    fh.write(export_line)
            except OSError:
                # Best-effort: parity with bash, which would surface a
                # redirection failure but not abort the hook chain.
                pass
        else:
            print(
                "[scan-lifecycle] CLAUDE_ENV_FILE not set; "
                "cannot inject LIFECYCLE_SESSION_ID",
                file=sys.stderr,
            )

    # --- cwd/lifecycle early-exit (bash precedent lines 26-29) ---
    # Non-cortex repos: silently exit 0 with no stdout. The wrapper at
    # hooks/cortex-scan-lifecycle.sh does its own pre-check; this is
    # defense-in-depth for the direct-invocation path.
    lifecycle_dir = cwd / "cortex" / "lifecycle"
    if not lifecycle_dir.is_dir():
        return 0

    # Lazy-imports per the module docstring's discipline. Keeping these
    # inside ``main`` means ``cortex hooks scan-lifecycle --help`` and
    # the cwd-early-exit path do not pay the package-import cost.
    from cortex_command.common import (
        detect_lifecycle_phase,
        is_phantom_lifecycle_dir,
    )
    from cortex_command.hooks._pipeline_state import PipelineState
    from cortex_command.hooks._session_state import (
        claim_single_feature,
        migrate_session_p1,
        migrate_session_p2,
        skip_orphan_session_owner,
    )

    # --- Session migration (bash precedent lines 39-73) ---
    # Survives /clear: when SESSION_ID (fresh) != LIFECYCLE_SESSION_ID
    # (stale) and both are non-empty, migrate .session files so the
    # active feature is still matched after /clear.
    lifecycle_session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")
    if (
        session_id
        and lifecycle_session_id
        and session_id != lifecycle_session_id
    ):
        # Phase 1: scan .session files for the stale id.
        migration_done = False
        try:
            children = sorted(lifecycle_dir.iterdir())
        except OSError:
            children = []
        for child in children:
            if not child.is_dir():
                continue
            if (child / ".session").is_file():
                if migrate_session_p1(
                    child, session_id, lifecycle_session_id
                ):
                    migration_done = True

        # Phase 2: chain migration via .session-owner. Skip features
        # whose ``.session-owner`` is orphaned (no ``.session`` AND no
        # incomplete-phase indicator i.e. complete) — bash resurrects
        # those; the Python port intentionally diverges.
        if not migration_done:
            # Pre-filter: don't enter P2 for orphan features that are
            # complete. The orchestrator inspects each feature's phase
            # AFTER candidate-collection below, but the orphan check
            # here is cheap (file presence) — let _session_state do the
            # heavy lifting via its own loop, and we filter post-hoc by
            # phase detection.
            written = migrate_session_p2(
                lifecycle_dir, session_id, lifecycle_session_id
            )
            # OR-branch enforcement: if a feature directory had only
            # ``.session-owner`` (no ``.session``) AND its detected
            # phase is "complete", undo any write the P2 helper made.
            # (The helper writes unconditionally; bash's OR-resurrection
            # is the bug we're avoiding — see spec req #6 branch OR.)
            for feature_dir in written:
                phase_info = detect_lifecycle_phase(feature_dir)
                phase_name = phase_info.get("phase")
                if phase_name == "complete":
                    # The feature was complete and only had an orphan
                    # .session-owner; bash would have resurrected
                    # .session here, but we treat that as a latent bug.
                    # Remove the .session we just wrote.
                    try:
                        (feature_dir / ".session").unlink()
                    except OSError:
                        pass
            # Belt-and-suspenders: also expose the orphan detector for
            # any future P2 caller that wants pre-write gating.
            _ = skip_orphan_session_owner  # Symbol kept reachable.

    # --- Pipeline-state detection (bash precedent lines 75-171) ---
    pipeline_state = PipelineState.from_path(
        lifecycle_dir / "overnight-state.json"
    )

    # --- Scan candidate feature directories (bash precedent lines 220-244) ---
    # Python port diverges from bash with two additional filters that
    # suppress non-lifecycle clutter the bash hook used to inject into
    # SessionStart additionalContext:
    #   (1) ``sessions`` is the per-session registry, not a feature dir
    #       (its UUID-keyed children made ``detect_lifecycle_phase``
    #       falsely return ``research``).
    #   (2) Lifecycles with an unreadable/missing events.log OR whose
    #       last logged event is older than the staleness threshold
    #       (default 30 days, env override
    #       ``CORTEX_SCAN_LIFECYCLE_STALE_DAYS``; <=0 disables) are
    #       suppressed. ``_is_stale`` treats unreadable events.log as
    #       stale, so the skill-test debris case (just ``learnings/``,
    #       no events.log) is covered by the same filter.
    try:
        stale_days = int(os.environ.get("CORTEX_SCAN_LIFECYCLE_STALE_DAYS", "30"))
    except (TypeError, ValueError):
        stale_days = 30

    # --- Load backlog status map once (T11) ---
    # Single read of cortex/backlog/index.json keyed by lifecycle_slug,
    # consumed below by both candidate loops (for the included-feature
    # mismatch annotation AND for the per-candidate JSONL diagnostic
    # records). Fail-open on missing / unparseable index — reconciliation
    # degrades silently rather than blocking the hook.
    backlog_status_map, _ = _load_backlog_status_map(cwd)

    candidate_dirs: list[Path] = []
    candidate_features: list[str] = []
    try:
        children = sorted(lifecycle_dir.iterdir())
    except OSError:
        children = []
    for child in children:
        if not child.is_dir():
            continue
        feature = child.name
        # Non-lifecycle structural exclusions (archive, sessions registry,
        # non-dir entries) are pre-candidate — no diagnostic emitted.
        if feature in ("archive", "sessions"):
            continue
        if _is_stale(child, stale_days):
            _emit_candidate_diag(
                child, feature, "excluded", "stale", None,
                backlog_status_map, stale_days,
            )
            continue
        # Phantom guard (runs AFTER _is_stale, so the empty/absent/unparseable
        # case is already excluded). Closes the recent-ts gap _is_stale leaves
        # open: a telemetry-only dir whose events carry a recent ts would
        # otherwise default to "research" and surface as an incomplete
        # lifecycle. is_phantom_lifecycle_dir classifies it as a phantom and
        # we suppress it here before it is ever surfaced.
        if is_phantom_lifecycle_dir(child):
            _emit_candidate_diag(
                child, feature, "excluded", "phantom", None,
                backlog_status_map, stale_days,
            )
            continue
        # Suppress Morning Review batch features.
        if pipeline_state.morning_review_active and (
            feature in pipeline_state.morning_review_features
        ):
            _emit_candidate_diag(
                child, feature, "excluded", "morning_review", None,
                backlog_status_map, stale_days,
            )
            continue
        candidate_dirs.append(child)
        candidate_features.append(feature)

    # --- Phase detection per candidate (bash precedent lines 249-326) ---
    incomplete: list[tuple[str, str, bool, str | None]] = []
    for feature_dir, feature in zip(candidate_dirs, candidate_features):
        try:
            r = detect_lifecycle_phase(feature_dir)
        except Exception:
            continue
        phase = str(r.get("phase", "") or "")
        if not phase:
            continue
        try:
            checked = int(r.get("checked", 0) or 0)
        except (TypeError, ValueError):
            checked = 0
        try:
            total = int(r.get("total", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        try:
            cycle = int(r.get("cycle", 1) or 1)
        except (TypeError, ValueError):
            cycle = 1

        encoded = _encode_phase(phase, checked, total, cycle)

        # Promote "complete" to "complete:awaiting-merge" when
        # ``pr_opened`` event is present and neither ``feature_complete``
        # nor ``feature_wontfix`` are. Otherwise filter complete features
        # out of the incomplete list. (Bash precedent lines 311-321.)
        if encoded == "complete":
            events_log = feature_dir / "events.log"
            if (
                _events_log_has_event(events_log, "pr_opened")
                and not _events_log_has_event(
                    events_log, "feature_complete"
                )
                and not _events_log_has_event(
                    events_log, "feature_wontfix"
                )
            ):
                encoded = "complete:awaiting-merge"
            else:
                # Complete-no-PR exclusion: feature is suppressed from the
                # incomplete enumeration, but the diagnostic still emits so
                # an inverse-#075 case (events=complete + backlog non-terminal)
                # surfaces in the JSONL for post-mortem review.
                _emit_candidate_diag(
                    feature_dir, feature, "excluded", "complete_no_pr",
                    encoded, backlog_status_map, stale_days,
                )
                continue

        backlog_status = backlog_status_map.get(feature)
        has_mismatch = _is_terminal_mismatch(encoded, backlog_status)
        incomplete.append((feature, encoded, has_mismatch, backlog_status))

        # T14 diagnostic: one record per included candidate. Excluded
        # candidates (stale / morning_review / complete_no_pr) emit from
        # their respective continue branches above.
        _emit_candidate_diag(
            feature_dir, feature, "included", None, encoded,
            backlog_status_map, stale_days,
        )

    # No incomplete features and no pipeline context — nothing to inject.
    if not incomplete and not pipeline_state.context_string:
        return 0

    # --- Determine active feature (bash precedent lines 333-366) ---
    # Order:
    #   (1) session-id match against ``.session`` files,
    #   (2) crash-recovery claim if exactly one incomplete,
    #   (3) no match → multi-incomplete prompt (handled in builder).
    active_feature = ""
    active_phase = ""

    if session_id:
        for feature, encoded, _has_mismatch, _backlog_status in incomplete:
            session_file = lifecycle_dir / feature / ".session"
            if not session_file.is_file():
                continue
            try:
                file_id = "".join(
                    session_file.read_text(encoding="utf-8").split()
                )
            except (OSError, ValueError):
                continue
            if file_id == session_id:
                active_feature = feature
                active_phase = encoded
                break

    if not active_feature and len(incomplete) == 1:
        active_feature, active_phase, _has_mismatch, _backlog_status = incomplete[0]
        if session_id:
            # Crash-recovery claim under flock (bash precedent line 364
            # was a bare ``echo``; the Python port serializes via
            # _session_state.claim_single_feature).
            try:
                claim_single_feature(
                    lifecycle_dir / active_feature, session_id
                )
            except OSError:
                # Best-effort: parity with bash's redirect, which
                # would surface stderr but not abort.
                pass

    # --- Regenerate metrics (bash precedent lines 437-440) ---
    # Replace the bash subprocess call to ``cortex-pipeline-metrics``
    # with a direct module-function call. Suppress stdout (which the
    # bash hook discards via ``>/dev/null 2>&1``) so the SessionStart
    # JSON envelope stays the only thing on our stdout.
    metrics_summary: str | None = None
    if active_feature:
        try:
            from cortex_command.pipeline import metrics as metrics_mod
        except ImportError:
            metrics_mod = None  # type: ignore[assignment]
        if metrics_mod is not None:
            try:
                with contextlib.redirect_stdout(
                    io.StringIO()
                ), contextlib.redirect_stderr(io.StringIO()):
                    metrics_mod.main(["--root", str(cwd)])
            except SystemExit:
                # argparse may raise SystemExit on --help; we don't pass
                # --help, but defensive.
                pass
            except Exception:
                # Bash uses ``|| true`` after the metrics regen — never
                # fail the hook because the metrics pass had a problem.
                pass
        metrics_file = lifecycle_dir / "metrics.json"
        metrics_summary = _metrics_summary_line(metrics_file)

    # --- Build final additionalContext ---
    context = _build_additional_context(
        pipeline_state,
        active_feature,
        active_phase,
        incomplete,
        lifecycle_dir,
        metrics_summary=metrics_summary,
    )

    if context:
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }
        # ``ensure_ascii=False`` preserves emoji-bearing context strings
        # byte-for-byte against bash output (jq -n --arg ctx ... at bash
        # precedent lines 482-489 emits UTF-8 verbatim; the Python port
        # must match for parity with golden-file fixtures and downstream
        # statusline/PipelineState pause/fail glyphs).
        json.dump(envelope, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI entry shim
    sys.exit(main(sys.argv[1:]))
