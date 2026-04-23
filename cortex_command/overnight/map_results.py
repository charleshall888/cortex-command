"""Map batch runner results to overnight state and strategy.

Reads batch-{N}-results.json (produced by batch_runner.py) and updates
overnight-state.json with per-feature statuses. Also updates
overnight-strategy.json with hot file accumulation and a round history note.

Invoked by runner.sh after batch_runner exits:
    python3 -m cortex_command.overnight.map_results \
        --batch-id N --plan <path> --state-path <path> \
        --events-path <path> --strategy-path <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    RoundSummary,
    load_state,
    save_state,
)
from cortex_command.overnight.strategy import load_strategy, save_strategy
from cortex_command.pipeline.parser import parse_master_plan


# Terminal statuses that the missing-results fallback will not overwrite.
_TERMINAL_STATUSES = frozenset({"merged", "failed", "deferred"})


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for map_results."""
    parser = argparse.ArgumentParser(
        prog="python3 -m cortex_command.overnight.map_results",
        description="Map batch runner results to overnight state and strategy.",
    )
    parser.add_argument(
        "--batch-id",
        type=int,
        required=True,
        help="Batch/round number (used to derive results filename).",
    )
    parser.add_argument(
        "--plan",
        type=str,
        required=True,
        help="Path to batch-plan-round-N.md; results path is derived as "
        "Path(plan).parent / f'batch-{batch_id}-results.json'.",
    )
    parser.add_argument(
        "--state-path",
        type=str,
        required=True,
        help="Path to overnight-state.json.",
    )
    parser.add_argument(
        "--events-path",
        type=str,
        required=True,
        help="Path to overnight events log.",
    )
    parser.add_argument(
        "--strategy-path",
        type=str,
        required=True,
        help="Path to overnight-strategy.json.",
    )
    return parser


def _map_results_to_state(
    results: dict,
    state_path: Path,
    batch_id: int,
) -> None:
    """Update overnight-state.json from batch results.

    Args:
        results: Parsed batch results JSON dict.
        state_path: Path to overnight-state.json.
        batch_id: Round/batch number used to upsert into round_history.
    """
    state = load_state(state_path)

    # Merged features — no error field
    for name in results.get("features_merged", []):
        if name not in state.features:
            state.features[name] = OvernightFeatureStatus()
        fs = state.features[name]
        fs.status = "merged"
        fs.error = None

    # Paused features — has "name" and "error"
    for entry in results.get("features_paused", []):
        name = entry["name"]
        if name not in state.features:
            state.features[name] = OvernightFeatureStatus()
        fs = state.features[name]
        if fs.status in _TERMINAL_STATUSES:
            continue
        fs.status = "paused"
        fs.error = entry.get("error")

    # Deferred features — has "name" and "question_count"
    for entry in results.get("features_deferred", []):
        name = entry["name"]
        if name not in state.features:
            state.features[name] = OvernightFeatureStatus()
        fs = state.features[name]
        if fs.status in _TERMINAL_STATUSES:
            continue
        fs.status = "deferred"
        fs.deferred_questions = entry.get("question_count", 0)

    # Failed features — has "name" and "error"
    for entry in results.get("features_failed", []):
        name = entry["name"]
        if name not in state.features:
            state.features[name] = OvernightFeatureStatus()
        fs = state.features[name]
        if fs.status in _TERMINAL_STATUSES:
            continue
        fs.status = "failed"
        fs.error = entry.get("error")

    # Upsert RoundSummary into round_history
    features_merged = list(results.get("features_merged", []))
    existing = next(
        (rs for rs in state.round_history if rs.round_number == batch_id), None
    )
    if existing is not None:
        if not existing.features_merged:
            existing.features_merged = features_merged
        # else: already populated — skip
    else:
        state.round_history.append(
            RoundSummary(round_number=batch_id, features_merged=features_merged)
        )

    save_state(state, state_path)


def _handle_missing_results(
    plan_path: Path,
    state_path: Path,
) -> None:
    """Fallback when batch results file is missing.

    Reads the batch plan to identify assigned features and marks each as
    "failed" unless already at a terminal status.

    Args:
        plan_path: Path to batch-plan-round-N.md.
        state_path: Path to overnight-state.json.
    """
    master_plan = parse_master_plan(plan_path)
    state = load_state(state_path)

    for feature in master_plan.features:
        name = feature.name
        if name not in state.features:
            state.features[name] = OvernightFeatureStatus()
        fs = state.features[name]
        # Do not overwrite features already at a terminal status
        if fs.status in _TERMINAL_STATUSES:
            continue
        fs.status = "failed"
        fs.error = "batch_runner.py did not produce results file"

    save_state(state, state_path)


def _update_strategy(
    results: dict,
    batch_id: int,
    strategy_path: Path,
) -> None:
    """Update overnight-strategy.json with hot files and round history.

    Args:
        results: Parsed batch results JSON dict.
        batch_id: Round/batch number.
        strategy_path: Path to overnight-strategy.json.
    """
    strategy = load_strategy(strategy_path)

    # Build file_touch_counts: mapping of filepath -> set of feature names
    # Seed existing hot_files with two synthetic names so they start at count 2
    file_touch_counts: dict[str, set[str]] = defaultdict(set)
    for filepath in strategy.hot_files:
        file_touch_counts[filepath].add("__prev_round_a__")
        file_touch_counts[filepath].add("__prev_round_b__")

    # For each merged feature, add its changed files
    merged_names = results.get("features_merged", [])
    key_files_changed: dict[str, list[str]] = results.get(
        "key_files_changed", {}
    )
    for feat_name in merged_names:
        changed_files = key_files_changed.get(feat_name, [])
        for filepath in changed_files:
            file_touch_counts[filepath].add(feat_name)

    # Update hot_files: filepaths with >= 2 distinct feature entries
    strategy.hot_files = sorted(
        fp for fp, features in file_touch_counts.items() if len(features) >= 2
    )

    # Build round history note
    paused_names = [
        entry.get("name", "?") for entry in results.get("features_paused", [])
    ]
    note = (
        f"Round {batch_id}: merged {len(merged_names)} features "
        f"({', '.join(merged_names)}), {len(paused_names)} paused."
    )
    strategy.round_history_notes.append(note)

    try:
        save_strategy(strategy, strategy_path)
    except Exception as exc:
        print(
            f"WARNING: failed to save strategy to {strategy_path}: {exc}",
            file=sys.stderr,
        )


def _run() -> None:
    """Entry point for python3 -m cortex_command.overnight.map_results."""
    args = _build_parser().parse_args()

    plan_path = Path(args.plan)
    state_path = Path(args.state_path)
    strategy_path = Path(args.strategy_path)
    results_path = plan_path.parent / f"batch-{args.batch_id}-results.json"

    if results_path.exists():
        # Normal path: results file exists
        results = json.loads(results_path.read_text(encoding="utf-8"))
        _map_results_to_state(results, state_path, args.batch_id)
        _update_strategy(results, args.batch_id, strategy_path)
    else:
        # Fallback: batch_runner did not produce a results file
        print(
            f"WARNING: results file not found at {results_path}; "
            f"marking batch plan features as failed.",
            file=sys.stderr,
        )
        _handle_missing_results(plan_path, state_path)


if __name__ == "__main__":
    _run()
