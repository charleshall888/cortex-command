"""Per-batch master plan generation and pipeline result mapping.

Generates temporary master plan files for individual overnight rounds.
Maps pipeline results back to overnight state terminology after each round.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from claude.pipeline.parser import parse_feature_plan, parse_master_plan


def generate_batch_plan(
    features: list[str],
    test_command: str | None,
    output_path: Path,
    base_branch: str = "main",
    feature_plan_paths: dict[str, str] | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    """Generate a master plan markdown file for a single batch of features.

    Creates a plan compatible with the pipeline parser at
    ``claude.pipeline.parser.parse_master_plan()``. The generated plan
    covers only the features in this batch, with parallel execution mode.

    Args:
        features: List of feature names.
        test_command: Shell command for integration tests, or None.
        output_path: Where to write the generated plan.
        base_branch: Branch to merge into. Defaults to "main".
        feature_plan_paths: Optional mapping of feature name to plan.md path.
            When provided, overrides the default ``lifecycle/{name}/plan.md``
            derivation. Use this when feature slugs in the overnight state
            differ from the actual lifecycle directory names.

    Returns:
        A tuple of (output_path, excluded) where excluded is a list of
        dicts with "name" and "error" keys for features whose plans
        could not be parsed.
    """
    if not output_path.is_absolute():
        raise ValueError(f"output_path must be absolute, got: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read per-feature plans to extract task count and complexity
    rows: list[str] = []
    excluded: list[dict[str, str]] = []
    for priority, name in enumerate(features, start=1):
        if feature_plan_paths and name in feature_plan_paths:
            plan_path = Path(feature_plan_paths[name])
        else:
            plan_path = Path(f"lifecycle/{name}/plan.md")
        if plan_path.exists():
            try:
                fp = parse_feature_plan(plan_path)
                task_count = len(fp.tasks)
                # Derive overall complexity: highest tier among tasks
                complexities = {t.complexity for t in fp.tasks}
                if "complex" in complexities:
                    complexity = "complex"
                elif "simple" in complexities:
                    complexity = "simple"
                else:
                    complexity = "trivial"
                summary = fp.overview.split("\n")[0][:80] if fp.overview else name
            except FileNotFoundError:
                reason = "plan file not found"
                logging.warning(f"Pre-flight: excluding {name}: {reason}")
                excluded.append({"name": name, "error": reason})
                continue
            except ValueError as exc:
                reason = f"plan not parseable: {exc}"
                logging.warning(f"Pre-flight: excluding {name}: {reason}")
                excluded.append({"name": name, "error": reason})
                continue
        else:
            task_count = 0
            complexity = "simple"
            summary = name

        rows.append(
            f"| {priority} | {name} | {complexity} | {task_count} | {summary} |"
        )

    test_value = test_command if test_command else "none"

    lines = [
        f"# Master Plan: overnight-batch",
        "",
        "## Features",
        "",
        "| Priority | Feature | Complexity | Tasks | Summary |",
        "|----------|---------|------------|-------|---------|",
        *rows,
        "",
        "## Configuration",
        "",
        "| Key | Value |",
        "|-----|-------|",
        f"| test_command | {test_value} |",
        f"| base_branch | {base_branch} |",
        "",
        "## Cross-Feature Risks",
        "",
        "- Batch plan generated for overnight round; features pre-grouped for independence",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return (output_path, excluded)


def map_pipeline_results(
    pipeline_state_path: Path,
    round_number: int,
) -> dict[str, tuple[str, Optional[str]]]:
    """Map pipeline feature statuses to overnight state terminology.

    Reads the pipeline state file after a round completes and translates
    each feature's status:

    - ``merged`` -> ``merged``
    - ``paused`` (error contains "deferred") -> ``deferred``
    - ``paused`` (other) -> ``paused``
    - ``failed`` -> ``failed``
    - ``pending`` / ``executing`` -> ``running`` (pipeline didn't finish)

    After reading, archives the pipeline state file to
    ``lifecycle/pipeline-state-round-{N}.json`` so the next round starts
    clean.

    Args:
        pipeline_state_path: Path to ``lifecycle/pipeline-state.json``.
        round_number: Current round number (used for archive filename).

    Returns:
        Mapping of feature_name -> (overnight_status, error_detail).
        error_detail is None when there is no error.

    Raises:
        FileNotFoundError: If the pipeline state file does not exist.
    """
    raw = json.loads(pipeline_state_path.read_text(encoding="utf-8"))

    results: dict[str, tuple[str, Optional[str]]] = {}

    features = raw.get("features", {})
    for name, status_dict in features.items():
        pipeline_status = status_dict.get("status", "pending")
        error = status_dict.get("error")

        if pipeline_status == "merged":
            overnight_status = "merged"
        elif pipeline_status == "paused":
            if error and "deferred" in error.lower():
                overnight_status = "deferred"
            else:
                overnight_status = "paused"
        elif pipeline_status == "failed":
            overnight_status = "failed"
        else:
            # pending, executing, reviewing, merging — pipeline didn't finish
            overnight_status = "running"

        results[name] = (overnight_status, error)

    # Archive the pipeline state for this round
    archive_path = pipeline_state_path.parent / f"pipeline-state-round-{round_number}.json"
    shutil.move(str(pipeline_state_path), str(archive_path))

    return results
