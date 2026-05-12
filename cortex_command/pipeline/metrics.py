"""Lifecycle metrics pipeline: event parsing, per-feature extraction,
aggregate computation, calibration insights, and JSON output.

Discovers all ``lifecycle/*/events.log`` files, parses JSONL events, and
computes per-feature metric records.  Handles edge cases: malformed lines
(skip with warning), minimal-event features (partial records with nulls),
in-progress features (excluded), duplicate ``feature_complete`` events
(use last per feature), and backfilled timestamps (phase durations between
backfilled events marked as null).

Usage::

    python3 -m cortex_command.pipeline.metrics [--root /path/to/repo]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import statistics
import sys
import tempfile
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

assert sys.version_info >= (3, 11), (
    "cortex_command/pipeline/metrics.py requires Python 3.11+ for datetime.fromisoformat offset handling"
)

# ---------------------------------------------------------------------------
# Backfill detection
# ---------------------------------------------------------------------------

# Synthetic timestamps sit at exact-minute intervals from midnight:
# T00:00:00Z, T00:01:00Z, ... T00:09:00Z.  Hour 0, minute 0-9, second 0.
_BACKFILL_RE = re.compile(r"T00:0\d:00Z$")


def is_backfilled(ts_str: str) -> bool:
    """Return True if *ts_str* looks like a backfilled synthetic timestamp.

    Detection heuristic: the time component matches ``T00:0X:00Z`` where
    X is a single digit — i.e., exact-minute intervals in the first ten
    minutes after midnight UTC.

    Args:
        ts_str: An ISO 8601 timestamp string ending in ``Z``.
    """
    return bool(_BACKFILL_RE.search(ts_str))


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO 8601 UTC timestamp string into a datetime.

    Args:
        ts_str: Timestamp like ``2026-02-16T16:21:45Z``.

    Returns:
        A timezone-aware datetime in UTC.
    """
    # Strip trailing Z and attach UTC tzinfo.
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def parse_events(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL events file and return parsed event dicts.

    Malformed lines are skipped with a warning.

    Args:
        path: Path to a ``events.log`` file.

    Returns:
        List of event dicts, each with at least ``ts``, ``event``, and
        ``feature`` keys.
    """
    events: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            warnings.warn(f"{path}:{lineno}: skipping malformed JSON line")
            continue
        if not isinstance(evt, dict) or "event" not in evt or "ts" not in evt:
            warnings.warn(f"{path}:{lineno}: skipping line missing required fields")
            continue
        events.append(evt)
    return events


def filter_events_since(
    events: list[dict[str, Any]],
    since: datetime | None,
) -> list[dict[str, Any]]:
    """Filter events to those with timestamp >= *since*.

    Args:
        events: List of event dicts, each containing a ``ts`` field.
        since: UTC datetime lower bound (inclusive).  When ``None``, all
            events are returned unchanged.

    Returns:
        Filtered list of event dicts.

    Raises:
        ValueError: If an event's ``ts`` field cannot be parsed as ISO 8601.
    """
    if since is None:
        return events
    result: list[dict[str, Any]] = []
    for evt in events:
        ts = _parse_ts(evt["ts"])
        if ts >= since:
            result.append(evt)
    return result


# ---------------------------------------------------------------------------
# Per-feature metric extraction
# ---------------------------------------------------------------------------

#: Closed enum of field aliases recognized when reading a verdict value from a
#: ``review_verdict`` event.  Tuple ordering is the precedence contract:
#: canonical ``"verdict"`` first; multi-alias events resolve to canonical.
#: Scope is deliberately narrow — do not generalize this helper across other
#: field accesses in this module (per R11 / FM-6).
_VERDICT_FIELD_ALIASES: tuple[str, ...] = ("verdict", "review_verdict", "decision")


def _extract_verdict(event: dict) -> str | None:
    """Return the verdict value from *event* using closed-enum alias lookup.

    Iterates :data:`_VERDICT_FIELD_ALIASES` in order and returns the first
    present field's value.  Returns ``None`` when no alias is present.

    Args:
        event: A ``review_verdict`` event dict.

    Returns:
        The verdict string, or ``None`` if no alias field is present.
    """
    for alias in _VERDICT_FIELD_ALIASES:
        if alias in event:
            return event[alias]
    return None


def _phase_durations(
    transitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive phase durations from consecutive phase_transition events.

    A duration is ``null`` when either the start or end timestamp is
    backfilled (synthetic).

    Args:
        transitions: Sorted list of ``phase_transition`` event dicts.

    Returns:
        List of dicts with ``from``, ``to``, and ``duration_seconds``
        (float or None) keys.
    """
    durations: list[dict[str, Any]] = []
    for i in range(len(transitions) - 1):
        curr = transitions[i]
        nxt = transitions[i + 1]

        if is_backfilled(curr["ts"]) or is_backfilled(nxt["ts"]):
            secs: float | None = None
        else:
            try:
                dt = _parse_ts(nxt["ts"]) - _parse_ts(curr["ts"])
                secs = dt.total_seconds()
            except ValueError:
                secs = None

        durations.append({
            "from": curr.get("to", curr.get("from")),
            "to": nxt.get("to", nxt.get("from")),
            "duration_seconds": secs,
        })
    return durations


def extract_feature_metrics(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute per-feature metrics from a list of events for one feature.

    Returns ``None`` for in-progress features (no ``feature_complete``
    event).

    Args:
        events: All parsed events for a single feature, in file order.

    Returns:
        A dict of per-feature metrics, or ``None`` if the feature is
        still in progress.
    """
    # ---- Check for completion ----
    complete_events = [e for e in events if e["event"] == "feature_complete"]
    if not complete_events:
        return None

    # Use the *last* feature_complete event (handles duplicates).
    final_complete = complete_events[-1]

    feature_name = final_complete["feature"]

    # ---- Tier (from lifecycle_start, if present) ----
    start_events = [e for e in events if e["event"] == "lifecycle_start"]
    tier: str | None = start_events[0]["tier"] if start_events else None

    # ---- Task count ----
    task_count: int | None = final_complete.get("tasks_total")

    # ---- Rework cycles ----
    rework_cycles: int | None = final_complete.get("rework_cycles")

    # ---- Batch metrics ----
    batch_events = [e for e in events if e["event"] == "batch_dispatch"]
    batch_events.sort(key=lambda e: e.get("batch", 0))
    batch_count: int | None = len(batch_events) if batch_events else None
    batch_sizes: list[int] | None = (
        [len(e["tasks"]) for e in batch_events] if batch_events else None
    )

    # ---- Phase transitions & durations ----
    transitions = [e for e in events if e["event"] == "phase_transition"]
    # Sort by timestamp to be safe, though file order should already be
    # chronological.
    transitions.sort(key=lambda e: e["ts"])
    phase_durations = _phase_durations(transitions) if transitions else None

    # ---- Review verdicts ----
    review_events = [e for e in events if e["event"] == "review_verdict"]
    review_verdicts: list[str] | None = (
        [v for v in (_extract_verdict(e) for e in review_events) if v is not None]
        if review_events
        else None
    )

    # ---- Total duration ----
    # From first event to feature_complete — only if neither endpoint is
    # backfilled.
    first_ts_str = events[0]["ts"]
    last_ts_str = final_complete["ts"]
    if is_backfilled(first_ts_str) or is_backfilled(last_ts_str):
        total_duration_seconds: float | None = None
    else:
        total_duration_seconds = (
            _parse_ts(last_ts_str) - _parse_ts(first_ts_str)
        ).total_seconds()

    return {
        "feature": feature_name,
        "tier": tier,
        "task_count": task_count,
        "batch_count": batch_count,
        "batch_sizes": batch_sizes,
        "rework_cycles": rework_cycles,
        "review_verdicts": review_verdicts,
        "phase_durations": phase_durations,
        "total_duration_seconds": total_duration_seconds,
    }


# ---------------------------------------------------------------------------
# Discovery and batch extraction
# ---------------------------------------------------------------------------

def discover_event_logs(lifecycle_dir: Path) -> list[Path]:
    """Find all ``events.log`` files under *lifecycle_dir*.

    Args:
        lifecycle_dir: The ``lifecycle/`` directory at the repo root.

    Returns:
        Sorted list of paths to ``events.log`` files.
    """
    if not lifecycle_dir.is_dir():
        return []
    logs = sorted(lifecycle_dir.glob("*/events.log"))
    return logs


def discover_pipeline_event_logs(lifecycle_dir: Path) -> list[Path]:
    """Find all ``pipeline-events.log`` files under *lifecycle_dir*.

    Returns the root-level ``pipeline-events.log`` (if present) plus all
    ``sessions/*/pipeline-events.log`` files, in sorted order.

    Args:
        lifecycle_dir: The ``lifecycle/`` directory at the repo root.

    Returns:
        Sorted list of paths to ``pipeline-events.log`` files.
    """
    if not lifecycle_dir.is_dir():
        return []
    logs: list[Path] = []
    root_log = lifecycle_dir / "pipeline-events.log"
    if root_log.exists():
        logs.append(root_log)
    logs.extend(sorted(lifecycle_dir.glob("sessions/*/pipeline-events.log")))
    return sorted(logs)


# ---------------------------------------------------------------------------
# Dispatch event pairing
# ---------------------------------------------------------------------------

#: Fields whose presence identifies a daytime-schema ``dispatch_complete``
#: event (lifecycle-skill dispatches, not overnight pipeline dispatches).
#: These records must be skipped entirely — not treated as untiered.
_DAYTIME_DISPATCH_FIELDS = frozenset({"mode", "outcome", "pr_url"})

#: Event types processed by the pairing walker.
_DISPATCH_PAIRABLE = frozenset({"dispatch_start", "dispatch_complete", "dispatch_error"})

#: Sort priority within a single timestamp: starts before completes/errors.
_DISPATCH_PRIORITY: dict[str, int] = {
    "dispatch_start": 0,
    "dispatch_complete": 1,
    "dispatch_error": 1,
}


def pair_dispatch_events(events: list[dict]) -> list[dict]:
    """Pair ``dispatch_start`` events to their matching ``dispatch_complete``
    or ``dispatch_error`` events within a single pipeline log's event list.

    Pairing is FIFO per feature: each completion/error is matched to the
    *oldest* unmatched preceding ``dispatch_start`` for the same feature.
    This handles same-feature concurrent retry storms correctly.

    Events are sorted by ``(ts, event_priority)`` before processing so that
    two events sharing the same timestamp are processed in start-before-
    complete order.

    Daytime-schema ``dispatch_complete`` events (identified by the presence of
    ``mode``, ``outcome``, or ``pr_url`` fields) are skipped entirely.
    ``dispatch_progress``, ``dispatch_retry``, and any other ``dispatch_*``
    event types not in ``{dispatch_start, dispatch_complete, dispatch_error}``
    are also silently skipped.

    Orphan completions/errors (no preceding unmatched start for the feature)
    emit a record with ``tier=None``, ``model=None``, and ``untiered=True``,
    and raise a ``UserWarning`` via ``warnings.warn``.

    Args:
        events: All parsed events from **one** pipeline log file, in any order.

    Returns:
        List of paired dispatch records.  Each record has the shape::

            {
                "ts": str,
                "feature": str,
                "model": str | None,
                "tier": str | None,
                "outcome": "complete" | "error",
                "cost_usd": float | None,
                "num_turns": int | None,
                "error_type": str | None,
                "untiered": bool,
                "skill": str | None,    # propagated from the matched start event;
                                        # absent on orphan completion/error records
                                        # (no start to read from).
                "cycle": int | None,    # propagated from the matched start event;
                                        # absent on orphan completion/error records.
                "effort": str | None,   # propagated from the matched start event;
                                        # absent on orphan completion/error records.
            }

        The ``skill``, ``cycle``, and ``effort`` keys are populated only on the
        matched-start branches.  Orphan completions/errors (no preceding
        unmatched start) omit these keys entirely so downstream aggregators
        bucket them as ``skill="legacy"`` via the
        ``rec.get("skill") or "legacy"`` fallback.
    """
    # Filter to the three pairable event types then sort deterministically.
    pairable = [
        e for e in events
        if e.get("event") in _DISPATCH_PAIRABLE
    ]
    pairable.sort(key=lambda e: (e.get("ts", ""), _DISPATCH_PRIORITY.get(e.get("event", ""), 1)))

    # Per-feature FIFO queue of unmatched dispatch_start events.
    unmatched_starts: dict[str, collections.deque[dict]] = defaultdict(collections.deque)

    results: list[dict] = []

    for evt in pairable:
        event_type = evt.get("event")
        feature = evt.get("feature", "")

        if event_type == "dispatch_start":
            unmatched_starts[feature].append(evt)

        elif event_type == "dispatch_complete":
            # Skip daytime-schema completions (positive field check).
            if _DAYTIME_DISPATCH_FIELDS & evt.keys():
                continue

            queue = unmatched_starts.get(feature)
            if queue:
                start = queue.popleft()
                results.append({
                    "ts": evt.get("ts", ""),
                    "feature": feature,
                    "model": start.get("model"),
                    "tier": start.get("complexity"),
                    "outcome": "complete",
                    "cost_usd": evt.get("cost_usd"),
                    "num_turns": evt.get("num_turns"),
                    "error_type": None,
                    "untiered": False,
                    "skill": start.get("skill"),
                    "cycle": start.get("cycle"),
                    "effort": start.get("effort"),
                })
            else:
                warnings.warn(
                    f"pair_dispatch_events: orphan dispatch_complete for feature "
                    f"{feature!r} at ts={evt.get('ts')!r} — no matching start"
                )
                results.append({
                    "ts": evt.get("ts", ""),
                    "feature": feature,
                    "model": None,
                    "tier": None,
                    "outcome": "complete",
                    "cost_usd": evt.get("cost_usd"),
                    "num_turns": evt.get("num_turns"),
                    "error_type": None,
                    "untiered": True,
                })

        elif event_type == "dispatch_error":
            queue = unmatched_starts.get(feature)
            if queue:
                start = queue.popleft()
                results.append({
                    "ts": evt.get("ts", ""),
                    "feature": feature,
                    "model": start.get("model"),
                    "tier": start.get("complexity"),
                    "outcome": "error",
                    "cost_usd": None,
                    "num_turns": None,
                    "error_type": evt.get("error_type"),
                    "untiered": False,
                    "skill": start.get("skill"),
                    "cycle": start.get("cycle"),
                    "effort": start.get("effort"),
                })
            else:
                warnings.warn(
                    f"pair_dispatch_events: orphan dispatch_error for feature "
                    f"{feature!r} at ts={evt.get('ts')!r} — no matching start"
                )
                results.append({
                    "ts": evt.get("ts", ""),
                    "feature": feature,
                    "model": None,
                    "tier": None,
                    "outcome": "error",
                    "cost_usd": None,
                    "num_turns": None,
                    "error_type": evt.get("error_type"),
                    "untiered": True,
                })

    return results


def compute_model_tier_dispatch_aggregates(paired: list[dict]) -> dict[str, dict]:
    """Group paired dispatch records by (model, tier, effort) and compute per-bucket aggregates.

    Paired records are the output of :func:`pair_dispatch_events`.  Each bucket
    accumulates ``outcome="complete"`` records for cost/turn statistics and
    ``outcome="error"`` records for error counts.

    Bucket keys are formatted as ``"<model>,<tier>,<effort>"`` strings for JSON
    compatibility.  ``effort`` is propagated from the ``dispatch_start``
    event; records whose start event lacked the ``effort`` field (legacy
    pre-instrumentation logs) bucket as ``effort="legacy-effort"``.  Records
    with ``untiered=True`` (orphaned dispatches with unknown model/tier) are
    grouped under the literal key ``"untiered,untiered"`` with
    ``is_untiered=True``.

    Statistical rules:

    * When ``n_completes >= 30``: ``num_turns_p95`` is the 95th percentile
      (``statistics.quantiles`` with ``n=100, method='inclusive'``),
      ``p95_suppressed=False``, ``max_turns_observed=None``.
    * When ``0 < n_completes < 30``: ``num_turns_p95=None``,
      ``p95_suppressed=True``, ``max_turns_observed=max(turns)``.
    * When ``n_completes == 0``: all cost/turn stats are ``None``,
      ``p95_suppressed=False``.

    ``budget_cap_usd`` and ``turn_cap_observed_rate`` are looked up from
    :data:`TIER_CONFIG` via the tier key.  The ``"untiered,untiered"`` bucket
    emits ``None`` for those fields.

    ``over_cap_rate`` is computed when ``n_completes > 0`` and ``budget_cap_usd``
    is not ``None``.

    Args:
        paired: List of paired dispatch records from :func:`pair_dispatch_events`.

    Returns:
        Dict mapping ``"<model>,<tier>"`` string keys to per-bucket aggregate
        dicts.  Each bucket contains:

        ``n_completes``, ``n_errors``, ``num_turns_mean``, ``num_turns_median``,
        ``num_turns_p95``, ``max_turns_observed``, ``p95_suppressed``,
        ``estimated_cost_usd_mean``, ``estimated_cost_usd_median``,
        ``estimated_cost_usd_max``, ``budget_cap_usd``, ``over_cap_rate``,
        ``turn_cap_observed_rate``, ``error_counts``, ``is_untiered``.
    """
    from cortex_command.pipeline.dispatch import TIER_CONFIG

    # Group records by bucket key.
    completes_by_bucket: dict[str, list[dict]] = defaultdict(list)
    errors_by_bucket: dict[str, list[dict]] = defaultdict(list)
    is_untiered_bucket: set[str] = set()

    for rec in paired:
        if rec.get("untiered"):
            key = "untiered,untiered"
            is_untiered_bucket.add(key)
        else:
            model = rec.get("model") or "unknown"
            tier = rec.get("tier") or "unknown"
            effort = rec.get("effort") or "legacy-effort"
            key = f"{model},{tier},{effort}"

        outcome = rec.get("outcome")
        if outcome == "complete":
            completes_by_bucket[key].append(rec)
        elif outcome == "error":
            errors_by_bucket[key].append(rec)

    # Collect all bucket keys seen across both sides.
    all_keys = set(completes_by_bucket.keys()) | set(errors_by_bucket.keys())

    result: dict[str, dict] = {}

    for key in sorted(all_keys):
        completes = completes_by_bucket.get(key, [])
        errors = errors_by_bucket.get(key, [])
        n_completes = len(completes)
        n_errors = len(errors)
        is_untiered = key in is_untiered_bucket

        # -- Cost / turn stats from completes --
        turns = [r["num_turns"] for r in completes if r.get("num_turns") is not None]
        costs = [r["cost_usd"] for r in completes if r.get("cost_usd") is not None]

        if n_completes == 0:
            num_turns_mean: float | None = None
            num_turns_median: float | None = None
            num_turns_p95: float | None = None
            max_turns_observed: int | None = None
            p95_suppressed = False
            estimated_cost_usd_mean: float | None = None
            estimated_cost_usd_median: float | None = None
            estimated_cost_usd_max: float | None = None
        else:
            num_turns_mean = statistics.fmean(turns) if turns else None
            num_turns_median = statistics.median(turns) if turns else None
            if n_completes >= 30:
                num_turns_p95 = statistics.quantiles(turns, n=100, method="inclusive")[94] if turns else None
                p95_suppressed = False
                max_turns_observed = None
            else:
                num_turns_p95 = None
                p95_suppressed = True
                max_turns_observed = max(turns) if turns else None
            estimated_cost_usd_mean = statistics.fmean(costs) if costs else None
            estimated_cost_usd_median = statistics.median(costs) if costs else None
            estimated_cost_usd_max = max(costs) if costs else None

        # -- Tier config lookup --
        if is_untiered:
            budget_cap_usd: float | None = None
            over_cap_rate: float | None = None
            turn_cap_observed_rate: float | None = None
        else:
            # Extract the tier portion of the key (second comma-separated element).
            key_parts = key.split(",")
            tier_part = key_parts[1] if len(key_parts) >= 2 else key
            tier_cfg = TIER_CONFIG.get(tier_part)
            if tier_cfg is not None:
                budget_cap_usd = tier_cfg.get("max_budget_usd")
                max_turns_cfg = tier_cfg.get("max_turns")
            else:
                budget_cap_usd = None
                max_turns_cfg = None

            # over_cap_rate: fraction of completes whose cost exceeds the cap.
            if n_completes > 0 and budget_cap_usd is not None:
                over_cap_count = sum(
                    1 for r in completes
                    if r.get("cost_usd") is not None and r["cost_usd"] > budget_cap_usd
                )
                over_cap_rate = over_cap_count / n_completes
            else:
                over_cap_rate = None

            # turn_cap_observed_rate: fraction of completes that hit the turn cap.
            if n_completes > 0 and max_turns_cfg is not None:
                at_cap_count = sum(
                    1 for r in completes
                    if r.get("num_turns") is not None and r["num_turns"] >= max_turns_cfg
                )
                turn_cap_observed_rate = at_cap_count / n_completes
            else:
                turn_cap_observed_rate = None

        # -- Error counts --
        error_counts: dict[str, int] = {}
        for err_rec in errors:
            etype = err_rec.get("error_type") or "unknown"
            error_counts[etype] = error_counts.get(etype, 0) + 1

        result[key] = {
            "n_completes": n_completes,
            "n_errors": n_errors,
            "num_turns_mean": num_turns_mean,
            "num_turns_median": num_turns_median,
            "num_turns_p95": num_turns_p95,
            "max_turns_observed": max_turns_observed,
            "p95_suppressed": p95_suppressed,
            "estimated_cost_usd_mean": estimated_cost_usd_mean,
            "estimated_cost_usd_median": estimated_cost_usd_median,
            "estimated_cost_usd_max": estimated_cost_usd_max,
            "budget_cap_usd": budget_cap_usd,
            "over_cap_rate": over_cap_rate,
            "turn_cap_observed_rate": turn_cap_observed_rate,
            "error_counts": error_counts,
            "is_untiered": is_untiered,
        }

    return result


def compute_skill_tier_dispatch_aggregates(paired: list[dict]) -> dict[str, dict]:
    """Group paired dispatch records by (skill, tier, effort[, cycle]) and compute per-bucket aggregates.

    Parallel to :func:`compute_model_tier_dispatch_aggregates` but bucketed by
    the dispatching skill rather than the model.  The bucket key shape is
    conditional:

    * For ``skill != "review-fix"``: bucket key is ``"<skill>,<tier>,<effort>"``
      (three-dimensional, mirrors the model-tier aggregator after the effort
      axis was added).
    * For ``skill == "review-fix"``: bucket key is
      ``"<skill>,<tier>,<effort>,<cycle>"`` (four-dimensional, surfacing the
      cycle distinction).  When a review-fix dispatch lacks ``cycle`` (legacy
      data), the substring ``"legacy-cycle"`` is used in place of the cycle
      number.

    ``effort`` is propagated from the ``dispatch_start`` event; records whose
    start event lacked the ``effort`` field (legacy pre-instrumentation logs)
    bucket as ``effort="legacy-effort"``.

    Records with the ``skill`` field absent from the start event (historical
    events emitted before this instrumentation landed) are bucketed as
    ``skill="legacy"`` — NOT ``"unknown"``, which collides with the existing
    untiered sentinel used by :func:`compute_model_tier_dispatch_aggregates`.

    Statistical rules and per-bucket output shape mirror
    :func:`compute_model_tier_dispatch_aggregates` exactly, including the
    ``n_completes < 30`` p95 suppression.

    Args:
        paired: List of paired dispatch records from :func:`pair_dispatch_events`.

    Returns:
        Dict mapping conditional bucket-key strings to per-bucket aggregate
        dicts.  Each bucket contains the same keys as the model-tier
        aggregator output.
    """
    from cortex_command.pipeline.dispatch import TIER_CONFIG

    # Group records by bucket key.
    completes_by_bucket: dict[str, list[dict]] = defaultdict(list)
    errors_by_bucket: dict[str, list[dict]] = defaultdict(list)
    is_untiered_bucket: set[str] = set()

    for rec in paired:
        if rec.get("untiered"):
            key = "untiered,untiered"
            is_untiered_bucket.add(key)
        else:
            skill = rec.get("skill") or "legacy"
            tier = rec.get("tier") or "unknown"
            effort = rec.get("effort") or "legacy-effort"
            cycle = rec.get("cycle")
            if skill == "review-fix":
                cycle_part = cycle if cycle is not None else "legacy-cycle"
                key = f"{skill},{tier},{effort},{cycle_part}"
            else:
                key = f"{skill},{tier},{effort}"

        outcome = rec.get("outcome")
        if outcome == "complete":
            completes_by_bucket[key].append(rec)
        elif outcome == "error":
            errors_by_bucket[key].append(rec)

    # Collect all bucket keys seen across both sides.
    all_keys = set(completes_by_bucket.keys()) | set(errors_by_bucket.keys())

    result: dict[str, dict] = {}

    for key in sorted(all_keys):
        completes = completes_by_bucket.get(key, [])
        errors = errors_by_bucket.get(key, [])
        n_completes = len(completes)
        n_errors = len(errors)
        is_untiered = key in is_untiered_bucket

        # -- Cost / turn stats from completes --
        turns = [r["num_turns"] for r in completes if r.get("num_turns") is not None]
        costs = [r["cost_usd"] for r in completes if r.get("cost_usd") is not None]

        if n_completes == 0:
            num_turns_mean: float | None = None
            num_turns_median: float | None = None
            num_turns_p95: float | None = None
            max_turns_observed: int | None = None
            p95_suppressed = False
            estimated_cost_usd_mean: float | None = None
            estimated_cost_usd_median: float | None = None
            estimated_cost_usd_max: float | None = None
        else:
            num_turns_mean = statistics.fmean(turns) if turns else None
            num_turns_median = statistics.median(turns) if turns else None
            if n_completes >= 30:
                num_turns_p95 = statistics.quantiles(turns, n=100, method="inclusive")[94] if turns else None
                p95_suppressed = False
                max_turns_observed = None
            else:
                num_turns_p95 = None
                p95_suppressed = True
                max_turns_observed = max(turns) if turns else None
            estimated_cost_usd_mean = statistics.fmean(costs) if costs else None
            estimated_cost_usd_median = statistics.median(costs) if costs else None
            estimated_cost_usd_max = max(costs) if costs else None

        # -- Tier config lookup --
        if is_untiered:
            budget_cap_usd: float | None = None
            over_cap_rate: float | None = None
            turn_cap_observed_rate: float | None = None
        else:
            # Extract the tier portion of the key (second comma-separated element).
            key_parts = key.split(",")
            tier_part = key_parts[1] if len(key_parts) >= 2 else key
            tier_cfg = TIER_CONFIG.get(tier_part)
            if tier_cfg is not None:
                budget_cap_usd = tier_cfg.get("max_budget_usd")
                max_turns_cfg = tier_cfg.get("max_turns")
            else:
                budget_cap_usd = None
                max_turns_cfg = None

            # over_cap_rate: fraction of completes whose cost exceeds the cap.
            if n_completes > 0 and budget_cap_usd is not None:
                over_cap_count = sum(
                    1 for r in completes
                    if r.get("cost_usd") is not None and r["cost_usd"] > budget_cap_usd
                )
                over_cap_rate = over_cap_count / n_completes
            else:
                over_cap_rate = None

            # turn_cap_observed_rate: fraction of completes that hit the turn cap.
            if n_completes > 0 and max_turns_cfg is not None:
                at_cap_count = sum(
                    1 for r in completes
                    if r.get("num_turns") is not None and r["num_turns"] >= max_turns_cfg
                )
                turn_cap_observed_rate = at_cap_count / n_completes
            else:
                turn_cap_observed_rate = None

        # -- Error counts --
        error_counts: dict[str, int] = {}
        for err_rec in errors:
            etype = err_rec.get("error_type") or "unknown"
            error_counts[etype] = error_counts.get(etype, 0) + 1

        result[key] = {
            "n_completes": n_completes,
            "n_errors": n_errors,
            "num_turns_mean": num_turns_mean,
            "num_turns_median": num_turns_median,
            "num_turns_p95": num_turns_p95,
            "max_turns_observed": max_turns_observed,
            "p95_suppressed": p95_suppressed,
            "estimated_cost_usd_mean": estimated_cost_usd_mean,
            "estimated_cost_usd_median": estimated_cost_usd_median,
            "estimated_cost_usd_max": estimated_cost_usd_max,
            "budget_cap_usd": budget_cap_usd,
            "over_cap_rate": over_cap_rate,
            "turn_cap_observed_rate": turn_cap_observed_rate,
            "error_counts": error_counts,
            "is_untiered": is_untiered,
        }

    return result


def extract_all_feature_metrics(
    lifecycle_dir: Path,
) -> list[dict[str, Any]]:
    """Parse all event logs and return per-feature metric records.

    In-progress features (those without a ``feature_complete`` event) are
    excluded from the results.

    Args:
        lifecycle_dir: The ``lifecycle/`` directory at the repo root.

    Returns:
        List of per-feature metric dicts, sorted by feature name.
    """
    results: list[dict[str, Any]] = []

    for log_path in discover_event_logs(lifecycle_dir):
        events = parse_events(log_path)
        if not events:
            continue

        metrics = extract_feature_metrics(events)
        if metrics is not None:
            results.append(metrics)

    results.sort(key=lambda m: m["feature"])
    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _phase_durations_as_dict(
    phase_list: list[dict[str, Any]] | None,
) -> dict[str, float | None]:
    """Convert the internal phase-durations list to a ``{label: seconds}`` dict.

    Keys are formatted as ``"<from>_to_<to>"`` (e.g. ``"research_to_specify"``).

    Args:
        phase_list: Output of :func:`_phase_durations`, or ``None``.

    Returns:
        Ordered dict of phase labels to durations (float or None).
    """
    if not phase_list:
        return {}
    result: dict[str, float | None] = {}
    for entry in phase_list:
        label = f"{entry['from']}_to_{entry['to']}"
        result[label] = entry["duration_seconds"]
    return result


def _first_pass_approved(review_verdicts: list[str] | None) -> bool | None:
    """Determine whether the first review verdict was ``APPROVED``.

    Args:
        review_verdicts: Ordered list of verdict strings, or ``None``.

    Returns:
        ``True`` if the first verdict is ``"APPROVED"``, ``False`` if a
        different verdict, or ``None`` if no verdicts are recorded.
    """
    if not review_verdicts:
        return None
    return review_verdicts[0] == "APPROVED"


def format_feature_record(metrics: dict[str, Any]) -> dict[str, Any]:
    """Transform internal per-feature metrics into the output JSON schema.

    Renames keys, converts phase durations from list to dict, and adds
    derived fields (``status``, ``first_pass_approved``).

    Args:
        metrics: A single record from :func:`extract_feature_metrics`.

    Returns:
        Dict matching the ``features.<name>`` schema in ``metrics.json``.
    """
    return {
        "tier": metrics["tier"],
        "status": "complete",
        "total_duration_s": metrics["total_duration_seconds"],
        "phase_durations": _phase_durations_as_dict(metrics["phase_durations"]),
        "task_count": metrics["task_count"],
        "batch_count": metrics["batch_count"],
        "batch_sizes": metrics["batch_sizes"],
        "rework_cycles": metrics["rework_cycles"],
        "review_verdicts": metrics["review_verdicts"],
        "first_pass_approved": _first_pass_approved(metrics["review_verdicts"]),
    }


# ---------------------------------------------------------------------------
# Aggregate computation
# ---------------------------------------------------------------------------

def _safe_mean(values: list[float | None]) -> float | None:
    """Compute the mean of *values*, ignoring ``None`` entries.

    Returns ``None`` if no non-None values exist.
    """
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def compute_aggregates(
    feature_metrics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group completed features by tier and compute aggregate statistics.

    Features with ``tier is None`` are excluded (pre-observability data
    that cannot be grouped).

    Args:
        feature_metrics: List of per-feature metric dicts from
            :func:`extract_feature_metrics`.

    Returns:
        Dict keyed by tier name, each containing ``n``,
        ``avg_total_duration_s``, ``avg_phase_durations``,
        ``avg_task_count``, ``avg_batch_count``, ``avg_rework_cycles``,
        and ``first_pass_approval_rate``.
    """
    # Group by tier, excluding null-tier features.
    by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in feature_metrics:
        if m["tier"] is not None:
            by_tier[m["tier"]].append(m)

    aggregates: dict[str, dict[str, Any]] = {}
    for tier, members in sorted(by_tier.items()):
        n = len(members)

        # Average total duration (skip None values from backfilled features).
        avg_total = _safe_mean([m["total_duration_seconds"] for m in members])

        # Average phase durations: collect all phase labels, average each.
        phase_dicts = [
            _phase_durations_as_dict(m["phase_durations"]) for m in members
        ]
        all_labels: list[str] = []
        for pd in phase_dicts:
            for label in pd:
                if label not in all_labels:
                    all_labels.append(label)

        avg_phases: dict[str, float | None] = {}
        for label in all_labels:
            vals = [pd.get(label) for pd in phase_dicts]
            avg_phases[label] = _safe_mean(vals)

        # Average numeric fields (skip None).
        avg_task = _safe_mean(
            [float(m["task_count"]) for m in members if m["task_count"] is not None]
        )
        avg_batch = _safe_mean(
            [float(m["batch_count"]) for m in members if m["batch_count"] is not None]
        )
        avg_rework = _safe_mean(
            [float(m["rework_cycles"]) for m in members if m["rework_cycles"] is not None]
        )

        # First-pass approval rate.
        verdicts = [m["review_verdicts"] for m in members]
        first_pass_results = [
            _first_pass_approved(v) for v in verdicts
        ]
        approved_count = sum(1 for r in first_pass_results if r is True)
        total_with_verdicts = sum(1 for r in first_pass_results if r is not None)
        approval_rate: float | None = (
            approved_count / total_with_verdicts if total_with_verdicts > 0 else None
        )

        aggregates[tier] = {
            "n": n,
            "avg_total_duration_s": avg_total,
            "avg_phase_durations": avg_phases,
            "avg_task_count": avg_task,
            "avg_batch_count": avg_batch,
            "avg_rework_cycles": avg_rework,
            "first_pass_approval_rate": approval_rate,
        }

    return aggregates


# ---------------------------------------------------------------------------
# Calibration insights
# ---------------------------------------------------------------------------

def compute_calibration(
    aggregates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Generate human-readable calibration insights per tier.

    Each tier gets a ``sample_count`` and a list of ``insights`` strings
    summarizing the aggregate data.

    Args:
        aggregates: Output of :func:`compute_aggregates`.

    Returns:
        Dict keyed by tier, each with ``sample_count`` and ``insights``.
    """
    tier_labels = {"simple": "Simple", "complex": "Complex"}
    calibration: dict[str, dict[str, Any]] = {}

    for tier, agg in sorted(aggregates.items()):
        n = agg["n"]
        label = tier_labels.get(tier, tier.capitalize())
        insights: list[str] = []

        # Task and batch insight.
        if agg["avg_task_count"] is not None and agg["avg_batch_count"] is not None:
            insights.append(
                f"{label} features averaged "
                f"{agg['avg_task_count']:.0f} tasks across "
                f"{agg['avg_batch_count']:.0f} batches (n={n})"
            )

        # Rework insight.
        if agg["avg_rework_cycles"] is not None:
            insights.append(
                f"{label} features averaged "
                f"{agg['avg_rework_cycles']:.1f} rework cycles (n={n})"
            )

        # Duration insight.
        if agg["avg_total_duration_s"] is not None:
            minutes = agg["avg_total_duration_s"] / 60
            insights.append(
                f"{label} features averaged "
                f"{minutes:.0f} min total duration (n={n})"
            )

        # Approval rate insight.
        if agg["first_pass_approval_rate"] is not None:
            pct = agg["first_pass_approval_rate"] * 100
            insights.append(
                f"{label} features had "
                f"{pct:.0f}% first-pass approval rate (n={n})"
            )

        calibration[tier] = {
            "sample_count": n,
            "insights": insights,
        }

    return calibration


# ---------------------------------------------------------------------------
# Pipeline orchestration and CLI
# ---------------------------------------------------------------------------

def _parse_since(s: str) -> datetime:
    """Argparse type callable: parse *s* as ``YYYY-MM-DD`` → UTC midnight.

    Args:
        s: Date string in ``YYYY-MM-DD`` format.

    Returns:
        A timezone-aware datetime at midnight UTC on that date.

    Raises:
        argparse.ArgumentTypeError: If *s* does not match ``YYYY-MM-DD``.
    """
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format {s!r}: expected YYYY-MM-DD"
        )


def _format_tier_dispatch_report(metrics_data: dict[str, Any], since: datetime | None) -> str:
    """Format the tier-dispatch report as a human-readable fixed-width table.

    Args:
        metrics_data: The parsed contents of ``metrics.json``.
        since: The ``--since`` datetime if provided, else ``None``.

    Returns:
        A multi-line string containing headers, optional window/orphan banners,
        and the formatted table.
    """
    aggregates: dict[str, dict] = metrics_data.get("model_tier_dispatch_aggregates", {})
    lines: list[str] = []

    # Window header (when --since was supplied).
    if since is not None:
        since_str = since.strftime("%Y-%m-%d")
        lines.append(
            f"Window: since {since_str} (per-dispatch aggregates only; per-feature metrics are all-time)"
        )

    # Orphan banner (when untiered records exist).
    untiered_count: int = metrics_data.get("untiered_count", 0)
    if untiered_count > 0:
        lines.append(
            f"\u26a0 {untiered_count} dispatches had no matching dispatch_start (bucketed as untiered)"
        )

    # Empty aggregates case.
    if not aggregates:
        if since is not None:
            since_str = since.strftime("%Y-%m-%d")
            lines.append(f"No dispatch data found after {since_str}")
        else:
            lines.append("No dispatch data found")
        return "\n".join(lines)

    # Column headers — cost columns include "(estimated)" suffix per spec.
    col_headers = [
        "(model, tier)",
        "n_completes",
        "n_errors",
        "mean_turns",
        "p95_turns",
        "mean_cost_usd (estimated)",
        "median_cost_usd (estimated)",
        "max_cost_usd (estimated)",
        "budget_cap_usd",
        "over_cap_rate",
        "error_counts_summary",
    ]

    def _fmt_float(v: float | None, decimals: int = 2) -> str:
        if v is None:
            return "—"
        return f"{v:.{decimals}f}"

    def _fmt_rate(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:.2%}"

    def _fmt_p95_turns(bucket: dict) -> str:
        if bucket.get("p95_suppressed"):
            max_obs = bucket.get("max_turns_observed")
            if max_obs is None:
                return "— [n<30]"
            return f"{max_obs} [n<30]"
        p95 = bucket.get("num_turns_p95")
        if p95 is None:
            return "—"
        return f"{p95:.1f}"

    def _fmt_error_counts(error_counts: dict) -> str:
        if not error_counts:
            return "-"
        return ",".join(f"{k}:{v}" for k, v in sorted(error_counts.items()))

    # Build rows: sorted keys, with untiered bucket last.
    sorted_keys = sorted(k for k in aggregates if k != "untiered,untiered")
    if "untiered,untiered" in aggregates:
        sorted_keys.append("untiered,untiered")

    rows: list[list[str]] = []
    for key in sorted_keys:
        bucket = aggregates[key]
        is_untiered = bucket.get("is_untiered", False)

        # Format the (model, tier) display key.
        if "," in key:
            model_part, tier_part = key.split(",", 1)
        else:
            model_part, tier_part = key, key
        display_key = f"({model_part}, {tier_part})"

        row = [
            display_key,
            str(bucket.get("n_completes", 0)),
            str(bucket.get("n_errors", 0)),
            _fmt_float(bucket.get("num_turns_mean"), 1),
            _fmt_p95_turns(bucket),
            _fmt_float(bucket.get("estimated_cost_usd_mean")),
            _fmt_float(bucket.get("estimated_cost_usd_median")),
            _fmt_float(bucket.get("estimated_cost_usd_max")),
            "—" if is_untiered else _fmt_float(bucket.get("budget_cap_usd")),
            "—" if is_untiered else _fmt_rate(bucket.get("over_cap_rate")),
            _fmt_error_counts(bucket.get("error_counts", {})),
        ]
        rows.append(row)

    # Compute column widths.
    col_widths = [len(h) for h in col_headers]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > col_widths[i]:
                col_widths[i] = len(cell)

    def _fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))

    lines.append(_fmt_row(col_headers))
    lines.append("  ".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(_fmt_row(row))

    return "\n".join(lines)


def _format_skill_tier_dispatch_report(metrics_data: dict[str, Any], since: datetime | None) -> str:
    """Format the skill-tier-dispatch report as a human-readable fixed-width table.

    Mirrors :func:`_format_tier_dispatch_report` but reads from
    ``skill_tier_dispatch_aggregates`` and prepends a 2-3 line header
    documenting two known data-quality caveats: idempotency-skipped tasks
    under-count per-skill dispatch totals, and orphan dispatches (crashed
    with no terminal event) are silently dropped.

    Args:
        metrics_data: The parsed contents of ``metrics.json``.
        since: The ``--since`` datetime if provided, else ``None``.

    Returns:
        A multi-line string containing the caveat header, optional
        window/orphan banners, and the formatted table.
    """
    aggregates: dict[str, dict] = metrics_data.get("skill_tier_dispatch_aggregates", {})
    lines: list[str] = []

    # Caveat header — always emitted, regardless of bucket count.  Must
    # contain both substrings ``idempot`` and ``orphan`` for R11 grep.
    lines.append(
        "Note: idempotency-skipped tasks emit no dispatch_start, so per-skill "
        "counts may under-count vs task_* events."
    )
    lines.append(
        "Crashed dispatches with no terminal event are silently dropped "
        "(orphan-handling carve-out, separate ticket)."
    )

    # Window header (when --since was supplied).
    if since is not None:
        since_str = since.strftime("%Y-%m-%d")
        lines.append(
            f"Window: since {since_str} (per-dispatch aggregates only; per-feature metrics are all-time)"
        )

    # Orphan banner (when untiered records exist).
    untiered_count: int = metrics_data.get("untiered_count", 0)
    if untiered_count > 0:
        lines.append(
            f"⚠ {untiered_count} dispatches had no matching dispatch_start (bucketed as untiered)"
        )

    # Empty aggregates case.
    if not aggregates:
        if since is not None:
            since_str = since.strftime("%Y-%m-%d")
            lines.append(f"No dispatch data found after {since_str}")
        else:
            lines.append("No dispatch data found")
        return "\n".join(lines)

    # Column headers — cost columns include "(estimated)" suffix per spec.
    col_headers = [
        "(skill, tier[, cycle])",
        "n_completes",
        "n_errors",
        "mean_turns",
        "p95_turns",
        "mean_cost_usd (estimated)",
        "median_cost_usd (estimated)",
        "max_cost_usd (estimated)",
        "budget_cap_usd",
        "over_cap_rate",
        "error_counts_summary",
    ]

    def _fmt_float(v: float | None, decimals: int = 2) -> str:
        if v is None:
            return "—"
        return f"{v:.{decimals}f}"

    def _fmt_rate(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:.2%}"

    def _fmt_p95_turns(bucket: dict) -> str:
        if bucket.get("p95_suppressed"):
            max_obs = bucket.get("max_turns_observed")
            if max_obs is None:
                return "— [n<30]"
            return f"{max_obs} [n<30]"
        p95 = bucket.get("num_turns_p95")
        if p95 is None:
            return "—"
        return f"{p95:.1f}"

    def _fmt_error_counts(error_counts: dict) -> str:
        if not error_counts:
            return "-"
        return ",".join(f"{k}:{v}" for k, v in sorted(error_counts.items()))

    # Build rows: lexicographic sort, with untiered bucket last.
    sorted_keys = sorted(k for k in aggregates if k != "untiered,untiered")
    if "untiered,untiered" in aggregates:
        sorted_keys.append("untiered,untiered")

    rows: list[list[str]] = []
    for key in sorted_keys:
        bucket = aggregates[key]
        is_untiered = bucket.get("is_untiered", False)

        # Format the (skill, tier[, cycle]) display key.
        parts = key.split(",")
        if len(parts) == 3:
            display_key = f"({parts[0]}, {parts[1]}, {parts[2]})"
        elif len(parts) == 2:
            display_key = f"({parts[0]}, {parts[1]})"
        else:
            display_key = f"({key})"

        row = [
            display_key,
            str(bucket.get("n_completes", 0)),
            str(bucket.get("n_errors", 0)),
            _fmt_float(bucket.get("num_turns_mean"), 1),
            _fmt_p95_turns(bucket),
            _fmt_float(bucket.get("estimated_cost_usd_mean")),
            _fmt_float(bucket.get("estimated_cost_usd_median")),
            _fmt_float(bucket.get("estimated_cost_usd_max")),
            "—" if is_untiered else _fmt_float(bucket.get("budget_cap_usd")),
            "—" if is_untiered else _fmt_rate(bucket.get("over_cap_rate")),
            _fmt_error_counts(bucket.get("error_counts", {})),
        ]
        rows.append(row)

    # Compute column widths.
    col_widths = [len(h) for h in col_headers]
    for row in rows:
        for i, cell in enumerate(row):
            if len(cell) > col_widths[i]:
                col_widths[i] = len(cell)

    def _fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))

    lines.append(_fmt_row(col_headers))
    lines.append("  ".join("-" * w for w in col_widths))
    for row in rows:
        lines.append(_fmt_row(row))

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Run the full metrics pipeline: discover, parse, extract, aggregate,
    calibrate, and write ``lifecycle/metrics.json``.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).
    """
    parser = argparse.ArgumentParser(
        prog="python3 -m cortex_command.pipeline.metrics",
        description="Compute lifecycle metrics from event logs.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        help="Filter dispatch events to those on or after YYYY-MM-DD (UTC midnight). Does not affect per-feature metrics.",
    )
    parser.add_argument(
        "--report",
        choices=["tier-dispatch", "skill-tier-dispatch"],
        default=None,
        help="After writing metrics.json, print a human-readable report to stdout.",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    lifecycle_dir = root / "cortex" / "lifecycle"
    output_path = root / "cortex" / "lifecycle" / "metrics.json"

    # ---- Discover and extract per-feature metrics ----
    print(f"Scanning {lifecycle_dir} for event logs...")
    feature_metrics = extract_all_feature_metrics(lifecycle_dir)
    print(f"  Found {len(feature_metrics)} completed feature(s)")

    # ---- Build features dict for output ----
    features_out: dict[str, Any] = {}
    for m in feature_metrics:
        features_out[m["feature"]] = format_feature_record(m)

    # ---- Compute aggregates (exclude null-tier features) ----
    aggregates = compute_aggregates(feature_metrics)
    tier_names = list(aggregates.keys())
    print(f"  Aggregated tiers: {tier_names}")

    # ---- Compute calibration insights ----
    calibration = compute_calibration(aggregates)

    # ---- Dispatch aggregation pipeline (file-local pairing) ----
    all_paired: list[dict] = []
    for log_path in discover_pipeline_event_logs(lifecycle_dir):
        events = parse_events(log_path)
        if not events:
            continue
        filtered = filter_events_since(events, args.since)
        paired = pair_dispatch_events(filtered)
        all_paired.extend(paired)

    model_tier_dispatch_aggregates = compute_model_tier_dispatch_aggregates(all_paired)
    skill_tier_dispatch_aggregates = compute_skill_tier_dispatch_aggregates(all_paired)
    print(f"  Dispatch aggregation: {len(all_paired)} paired record(s), {len(model_tier_dispatch_aggregates)} bucket(s)")

    # ---- Assemble and write output ----
    output: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": features_out,
        "aggregates": aggregates,
        "calibration": calibration,
        "model_tier_dispatch_aggregates": model_tier_dispatch_aggregates,
        "skill_tier_dispatch_aggregates": skill_tier_dispatch_aggregates,
    }

    if args.since is not None:
        output["model_tier_dispatch_aggregates_window"] = {
            "since": args.since.strftime("%Y-%m-%d"),
            "note": "per-dispatch aggregates only; per-feature metrics are all-time",
        }

    untiered_count = sum(1 for r in all_paired if r.get("untiered"))
    if untiered_count > 0:
        output["untiered_count"] = untiered_count

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tf:
        tf.write(json.dumps(output, indent=2) + "\n")
        tmp_path = tf.name
    os.replace(tmp_path, output_path)
    print(f"  Wrote {output_path}")

    # ---- Optional human-readable report ----
    if args.report == "tier-dispatch":
        metrics_data = json.loads(output_path.read_text(encoding="utf-8"))
        report_str = _format_tier_dispatch_report(metrics_data, args.since)
        print(report_str)
    elif args.report == "skill-tier-dispatch":
        metrics_data = json.loads(output_path.read_text(encoding="utf-8"))
        report_str = _format_skill_tier_dispatch_report(metrics_data, args.since)
        print(report_str)


if __name__ == "__main__":
    main()
