"""Unit tests for dispatch_repair_agent() in claude.pipeline.conflict.

Six scenarios covering the full dispatch contract: Sonnet success, Sonnet
quality failure with Opus escalation, Opus quality failure, agent deferral,
test failure after clean resolution, and SDK exception (no Opus escalation).

Uses unittest.mock.patch — no real git operations or SDK calls.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude.pipeline.conflict import (
    ConflictClassification,
    RepairResult,
    dispatch_repair_agent,
)
from claude.overnight.feature_executor import execute_feature


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _FakeBatchConfig:
    """Minimal BatchConfig substitute for unit tests."""

    def __init__(self) -> None:
        self.batch_id: int = 1
        self.base_branch: str = "main"
        self.test_command: Optional[str] = None
        self.pipeline_events_path: Path = Path("/dev/null")
        self.overnight_state_path: Path = Path("/dev/null")
        self.overnight_events_path: Path = Path("/dev/null")


def _make_dispatch_result(
    *, success: bool = True, cost: float = 1.0, error_detail: Optional[str] = None
) -> MagicMock:
    r = MagicMock()
    r.success = success
    r.cost_usd = cost
    r.error_detail = error_detail
    return r


def _make_test_result(*, passed: bool = True, output: str = "") -> MagicMock:
    r = MagicMock()
    r.passed = passed
    r.output = output
    return r


def _write_exit_report(worktree: Path, feature: str, report: dict) -> None:
    path = worktree / "lifecycle" / feature / "exit-reports" / "repair.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")


def _base_cc() -> ConflictClassification:
    return ConflictClassification(
        conflicted_files=["foo.py"], conflict_summary="1 file conflicted"
    )


# ---------------------------------------------------------------------------
# (a) Sonnet success
# ---------------------------------------------------------------------------

def test_sonnet_success(tmp_path: Path) -> None:
    """Sonnet resolves on first attempt → success=True, model_used='sonnet'."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()

    def dispatch_side_effect(*args, **kwargs):
        # Write exit report as the agent would (after stale report is removed).
        _write_exit_report(worktree, feature, {
            "action": "complete",
            "resolved_files": ["foo.py"],
            "rationale": {"foo.py": "kept both"},
        })
        return _make_dispatch_result()

    dispatch_mock = AsyncMock(side_effect=dispatch_side_effect)
    run_tests_mock = MagicMock(return_value=_make_test_result(passed=True))

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, [])),
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.merge.run_tests", run_tests_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path="lifecycle/my-feature/spec.md",
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is True
    assert result.model_used == "sonnet"
    assert result.resolved_files == ["foo.py"]
    dispatch_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# (b) Sonnet quality failure → Opus escalation → success
# ---------------------------------------------------------------------------

def test_sonnet_quality_failure_opus_succeeds(tmp_path: Path) -> None:
    """Sonnet writes deferral question → Opus resolves cleanly → success, model_used='opus'."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()
    call_count = [0]

    def dispatch_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Sonnet: deferral question → agent quality failure
            _write_exit_report(worktree, feature, {
                "action": "question",
                "question": "Which foo() wins?",
                "context": "foo.py line 42",
            })
        else:
            # Opus: clean resolution
            _write_exit_report(worktree, feature, {
                "action": "complete",
                "resolved_files": ["foo.py"],
                "rationale": {"foo.py": "kept opus side"},
            })
        return _make_dispatch_result()

    dispatch_mock = AsyncMock(side_effect=dispatch_side_effect)
    run_tests_mock = MagicMock(return_value=_make_test_result(passed=True))

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, [])),
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.merge.run_tests", run_tests_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path=None,
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is True
    assert result.model_used == "opus"
    assert dispatch_mock.await_count == 2


# ---------------------------------------------------------------------------
# (c) Both Sonnet and Opus produce quality failures (no deferral question)
# ---------------------------------------------------------------------------

def test_opus_quality_failure(tmp_path: Path) -> None:
    """Both dispatches produce quality failures (missing exit report) → success=False."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()
    # Write conflict markers so _has_remaining_markers also returns True
    (worktree / "foo.py").write_text(
        "<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> branch\n", encoding="utf-8"
    )
    # No exit report written — _read_exit_report returns None → quality failure

    dispatch_mock = AsyncMock(return_value=_make_dispatch_result())

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, ["foo.py"])),
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path=None,
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is False
    assert dispatch_mock.await_count == 2


# ---------------------------------------------------------------------------
# (d) Agent deferral: both models write action="question"
# ---------------------------------------------------------------------------

def test_agent_deferral(tmp_path: Path) -> None:
    """Both Sonnet and Opus write deferral questions → error starts with 'deferral:'."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()

    def dispatch_side_effect(*args, **kwargs):
        _write_exit_report(worktree, feature, {
            "action": "question",
            "question": "Cannot determine which foo() is correct",
            "context": "foo.py line 42",
        })
        return _make_dispatch_result()

    dispatch_mock = AsyncMock(side_effect=dispatch_side_effect)

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, [])),  # no marker files — deferral is the signal
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path=None,
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("deferral:")


# ---------------------------------------------------------------------------
# (e) Test failure after clean resolution — no Opus escalation
# ---------------------------------------------------------------------------

def test_test_failure_after_clean_resolution(tmp_path: Path) -> None:
    """Clean resolution but tests fail → error starts with 'test_failure:', dispatch called once."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()

    def dispatch_side_effect(*args, **kwargs):
        _write_exit_report(worktree, feature, {
            "action": "complete",
            "resolved_files": ["foo.py"],
            "rationale": {"foo.py": "kept both"},
        })
        return _make_dispatch_result()

    dispatch_mock = AsyncMock(side_effect=dispatch_side_effect)
    run_tests_mock = MagicMock(
        return_value=_make_test_result(passed=False, output="assertion error in test_foo")
    )

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, [])),  # no remaining markers
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.merge.run_tests", run_tests_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path=None,
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("test_failure:")
    dispatch_mock.assert_awaited_once()  # no Opus escalation on test failure


# ---------------------------------------------------------------------------
# (f) SDK exception — no Opus escalation
# ---------------------------------------------------------------------------

def test_sdk_exception_no_opus_escalation(tmp_path: Path) -> None:
    """Sonnet SDK dispatch fails (success=False) → failure returned, dispatch called exactly once."""
    feature = "my-feature"
    worktree = tmp_path / f"repair-{feature}-1"
    worktree.mkdir()

    dispatch_mock = AsyncMock(return_value=_make_dispatch_result(
        success=False, cost=0.0, error_detail="ProcessError: connection refused"
    ))

    with (
        patch("claude.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, ["foo.py"])),
        patch("claude.pipeline.conflict._cleanup_repair_worktree"),
        patch("claude.pipeline.conflict.dispatch_task", dispatch_mock),
        patch("claude.pipeline.conflict.pipeline_log_event"),
    ):
        result = asyncio.run(dispatch_repair_agent(
            feature=feature,
            conflict_classification=_base_cc(),
            base_branch="main",
            spec_path=None,
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is False
    dispatch_mock.assert_awaited_once()  # no Opus retry on infrastructure failure


# ---------------------------------------------------------------------------
# (g) execute_feature: repair detection fires when conflict event + budget available
# ---------------------------------------------------------------------------

def test_execute_feature_dispatches_repair_on_conflict_event(tmp_path: Path) -> None:
    """Given a conflict event and available budget, execute_feature dispatches repair
    instead of running plan tasks and returns FeatureResult(status='repair_completed')."""
    feature = "my-feature"

    events_file = tmp_path / "overnight-events.jsonl"
    events_file.write_text(
        json.dumps({
            "event": "merge_conflict_classified",
            "feature": feature,
            "details": {
                # 4 files = non-trivial (> 3) → skips trivial path, goes straight to repair agent
                "conflicted_files": ["foo.py", "bar.py", "baz.py", "qux.py"],
                "conflict_summary": "4 files conflicted",
            },
        }) + "\n",
        encoding="utf-8",
    )

    config = _FakeBatchConfig()
    config.overnight_events_path = events_file

    mock_fs = MagicMock()
    mock_fs.recovery_attempts = 0
    mock_fs.recovery_depth = 0
    mock_state = MagicMock()
    mock_state.features = {feature: mock_fs}

    repair_result = RepairResult(
        success=True,
        feature=feature,
        repair_branch=f"repair/{feature}-1",
    )

    with (
        patch("claude.overnight.feature_executor.load_state", return_value=mock_state),
        patch("claude.overnight.feature_executor.save_state"),
        patch(
            "claude.overnight.feature_executor.dispatch_repair_agent",
            new=AsyncMock(return_value=repair_result),
        ),
    ):
        result = asyncio.run(execute_feature(
            feature=feature,
            worktree_path=tmp_path,
            config=config,
        ))

    assert result.status == "repair_completed"
    assert result.repair_branch == f"repair/{feature}-1"
