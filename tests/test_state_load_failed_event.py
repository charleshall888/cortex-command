"""Integration test: orchestrator emits state_load_failed on corrupt state.

Covers lifecycle 130 Task 5 — when ``load_state`` raises while reading
overnight-state.json, the orchestrator writes a ``state_load_failed`` event
to pipeline-events.log carrying exception_type, exception_message, the
state_path, and the ``subsequent_writes_target`` operator signal (the home
repo backlog path that writes will silently fall back to per spec R6).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.overnight import orchestrator
from cortex_command.overnight.orchestrator import BatchConfig, run_batch
from cortex_command.pipeline.parser import MasterPlan, MasterPlanConfig


def _read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def test_state_load_failed_event_emitted_on_corrupt_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Corrupted overnight-state.json → state_load_failed event in pipeline log.

    The event must include:
      - exception_type, exception_message: concrete diagnostics
      - state_path: which file we tried to load
      - subsequent_writes_target: operator signal pointing at the home-repo
        backlog where silent-misdirection writes will land per spec R6.
    """
    # Pin user project root to tmp_path so BatchConfig defaults that resolve
    # `_resolve_user_project_root()` and the orchestrator's
    # `subsequent_writes_target` lookup both land inside tmp_path.
    # CORTEX_REPO_ROOT is set below so the resolver bypasses the walk;
    # lifecycle/ and backlog/ are created for orchestrator path resolution.
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    (tmp_path / "cortex" / "backlog").mkdir()
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    # Corrupted state — invalid JSON so json.load raises.
    state_path = tmp_path / "overnight-state.json"
    state_path.write_text("{not valid json")

    # Empty plan file; mocked parser returns an empty MasterPlan so run_batch
    # is a no-op past the state-load try/except we're exercising.
    plan_path = tmp_path / "master-plan.md"
    plan_path.write_text("# Master Plan: test\n")

    pipeline_log = tmp_path / "pipeline-events.log"
    overnight_log = tmp_path / "overnight-events.log"

    config = BatchConfig(
        batch_id=1,
        plan_path=plan_path,
        overnight_state_path=state_path,
        overnight_events_path=overnight_log,
        result_dir=tmp_path,
        pipeline_events_path=pipeline_log,
    )

    empty_plan = MasterPlan(name="test", features=[], config=MasterPlanConfig())

    with patch.object(
        orchestrator, "parse_master_plan", return_value=empty_plan
    ):
        asyncio.run(run_batch(config))

    events = _read_events(pipeline_log)
    slf = [e for e in events if e.get("event") == "state_load_failed"]
    assert slf, (
        f"no state_load_failed event found in {pipeline_log}; "
        f"got events: {[e.get('event') for e in events]}"
    )
    assert len(slf) == 1, f"expected exactly one state_load_failed event, got {len(slf)}"
    evt = slf[0]

    # Schema assertions
    assert evt.get("ts"), "event must include ts field (added by pipeline_log_event)"
    assert evt["exception_type"], "exception_type must be non-empty"
    assert isinstance(evt["exception_message"], str) and evt["exception_message"]
    assert evt["state_path"] == str(state_path)

    # subsequent_writes_target is the key operator signal from spec R6 —
    # points at the home-repo backlog fallback the silent-misdirection path
    # uses. Resolved at call time from CORTEX_REPO_ROOT (set above to tmp_path).
    expected_target = str(tmp_path / "cortex" / "backlog")
    assert evt["subsequent_writes_target"] == expected_target, (
        f"expected subsequent_writes_target={expected_target!r}, "
        f"got {evt.get('subsequent_writes_target')!r}"
    )
