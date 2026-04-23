"""CLI entry point for the overnight batch orchestrator.

Thin wrapper around :mod:`cortex_command.overnight.orchestrator`.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cortex_command.overnight.orchestrator import BatchConfig, BatchResult, run_batch  # noqa: F401


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m cortex_command.overnight.batch_runner")
    p.add_argument("--plan", required=True)
    p.add_argument("--batch-id", type=int, required=True)
    p.add_argument("--test-command", default=None)
    p.add_argument("--base-branch", default="main")
    p.add_argument("--state-path", default="lifecycle/sessions/latest-overnight/overnight-state.json")
    p.add_argument("--events-path", default="lifecycle/sessions/latest-overnight/overnight-events.log")
    p.add_argument("--tier", default=None)
    return p


def _run() -> None:
    args = build_parser().parse_args()
    result_dir = Path(args.plan).parent
    test_command = args.test_command
    if test_command and str(test_command).lower() == "none":
        test_command = None
    config = BatchConfig(
        batch_id=args.batch_id,
        plan_path=Path(args.plan),
        test_command=test_command,
        base_branch=args.base_branch,
        overnight_state_path=Path(args.state_path),
        overnight_events_path=Path(args.events_path),
        result_dir=result_dir,
        pipeline_events_path=result_dir / "pipeline-events.log",
        throttle_tier=args.tier,
    )
    asyncio.run(run_batch(config))


if __name__ == "__main__":
    _run()
