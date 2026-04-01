"""Lifecycle metrics pipeline: event parsing, per-feature extraction,
aggregate computation, calibration insights, and JSON output.

Discovers all ``lifecycle/*/events.log`` files, parses JSONL events, and
computes per-feature metric records.  Handles edge cases: malformed lines
(skip with warning), minimal-event features (partial records with nulls),
in-progress features (excluded), duplicate ``feature_complete`` events
(use last per feature), and backfilled timestamps (phase durations between
backfilled events marked as null).

Usage::

    python3 -m claude.pipeline.metrics [--root /path/to/repo]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# Per-feature metric extraction
# ---------------------------------------------------------------------------

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
            dt = _parse_ts(nxt["ts"]) - _parse_ts(curr["ts"])
            secs = dt.total_seconds()

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
        [e["verdict"] for e in review_events] if review_events else None
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

def main(argv: list[str] | None = None) -> None:
    """Run the full metrics pipeline: discover, parse, extract, aggregate,
    calibrate, and write ``lifecycle/metrics.json``.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).
    """
    parser = argparse.ArgumentParser(
        prog="python3 -m claude.pipeline.metrics",
        description="Compute lifecycle metrics from event logs.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current working directory)",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    lifecycle_dir = root / "lifecycle"
    output_path = root / "lifecycle" / "metrics.json"

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

    # ---- Assemble and write output ----
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": features_out,
        "aggregates": aggregates,
        "calibration": calibration,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  Wrote {output_path}")


if __name__ == "__main__":
    main()
