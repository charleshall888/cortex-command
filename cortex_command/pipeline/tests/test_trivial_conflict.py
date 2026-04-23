"""Unit tests for resolve_trivial_conflict() and execute_feature() routing.

Four scenarios for resolve_trivial_conflict():
  a. Success: clean merge + passing tests → ConflictResolutionResult(success=True)
  b. Worktree creation failure: _create_repair_worktree raises → success=False
  c. merge --continue failure: non-zero returncode → success=False
  d. Test gate failure: run_tests returns passed=False → success=False, error starts with "test_failure:"

Four scenarios for execute_feature() routing:
  e. Trivial eligible (1 file, no hot files) → resolve_trivial_conflict called, repair agent not called
  f. Hot file overlap → trivial skipped, repair agent dispatched
  g. Budget exhausted (recovery_attempts=1, non-trivial conflict) → deferred, no agent called
  h. Trivial fails → falls through to repair agent

Uses unittest.mock.patch — no real git operations or SDK calls.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from cortex_command.pipeline.conflict import (
    ConflictResolutionResult,
    resolve_trivial_conflict,
)
from cortex_command.overnight.feature_executor import execute_feature


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _FakeBatchConfig:
    """Minimal BatchConfig substitute for unit tests."""

    def __init__(self, tmp_path: Optional[Path] = None) -> None:
        self.batch_id: int = 1
        self.base_branch: str = "main"
        self.test_command: Optional[str] = None
        self.pipeline_events_path: Path = Path("/dev/null")
        if tmp_path is not None:
            self.overnight_state_path: Path = tmp_path / "overnight-state.json"
            self.overnight_events_path: Path = tmp_path / "overnight-events.jsonl"
        else:
            self.overnight_state_path = Path("/dev/null")
            self.overnight_events_path = Path("/dev/null")


def _make_test_result(*, passed: bool = True, output: str = "") -> MagicMock:
    r = MagicMock()
    r.passed = passed
    r.output = output
    return r


def _make_subprocess_result(returncode: int = 0, stderr: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stderr = stderr
    r.stdout = ""
    return r


def _write_conflict_event(
    events_file: Path, feature: str, conflicted_files: list[str]
) -> None:
    events_file.write_text(
        json.dumps({
            "event": "merge_conflict_classified",
            "feature": feature,
            "details": {
                "conflicted_files": conflicted_files,
                "conflict_summary": f"{len(conflicted_files)} file(s) conflicted",
            },
        }) + "\n",
        encoding="utf-8",
    )


def _make_mock_state(feature: str, recovery_attempts: int, recovery_depth: int) -> MagicMock:
    mock_fs = MagicMock()
    mock_fs.recovery_attempts = recovery_attempts
    mock_fs.recovery_depth = recovery_depth
    mock_state = MagicMock()
    mock_state.features = {feature: mock_fs}
    return mock_state


# ---------------------------------------------------------------------------
# (a) resolve_trivial_conflict: success
# ---------------------------------------------------------------------------


def test_resolve_trivial_conflict_success(tmp_path: Path) -> None:
    """Clean merge + passing tests → success=True, resolved_files populated, repair_branch set."""
    feature = "feat"
    round_number = 1
    worktree = tmp_path / f"repair-{feature}-{round_number}"
    worktree.mkdir()

    cleanup_mock = MagicMock()
    run_tests_mock = MagicMock(return_value=_make_test_result(passed=True))

    with (
        patch("cortex_command.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, ["file.py"])),
        patch("cortex_command.pipeline.conflict._cleanup_repair_worktree", cleanup_mock),
        patch("subprocess.run", return_value=_make_subprocess_result(returncode=0)),
        patch("cortex_command.pipeline.merge.run_tests", run_tests_mock),
    ):
        result = asyncio.run(resolve_trivial_conflict(
            feature=feature,
            branch=f"pipeline/{feature}",
            base_branch="main",
            conflicted_files=["file.py"],
            config=_FakeBatchConfig(),
            round_number=round_number,
        ))

    assert result.success is True
    assert result.strategy == "trivial_fast_path"
    assert result.resolved_files == ["file.py"]
    assert result.repair_branch == f"repair/{feature}-{round_number}"
    assert result.error is None
    # Cleanup called with delete_branch=False (keep branch for ff-merge)
    cleanup_mock.assert_called_once_with(
        worktree,
        f"repair/{feature}-{round_number}",
        Path.cwd(),
        delete_branch=False,
    )


# ---------------------------------------------------------------------------
# (b) resolve_trivial_conflict: worktree creation failure
# ---------------------------------------------------------------------------


def test_resolve_trivial_conflict_worktree_failure() -> None:
    """_create_repair_worktree raises ValueError → success=False, error carries message."""
    feature = "feat"

    with (
        patch("cortex_command.pipeline.conflict._create_repair_worktree",
              side_effect=ValueError("feature_branch_missing: pipeline/feat")),
        patch("subprocess.run", return_value=_make_subprocess_result(returncode=0)),
    ):
        result = asyncio.run(resolve_trivial_conflict(
            feature=feature,
            branch=f"pipeline/{feature}",
            base_branch="main",
            conflicted_files=["file.py"],
            config=_FakeBatchConfig(),
            round_number=1,
        ))

    assert result.success is False
    assert result.error is not None
    assert "feature_branch_missing" in result.error


# ---------------------------------------------------------------------------
# (c) resolve_trivial_conflict: merge --continue failure
# ---------------------------------------------------------------------------


def test_resolve_trivial_conflict_continue_failure(tmp_path: Path) -> None:
    """git merge --continue returns non-zero → success=False, error starts with 'merge_continue_failed:'."""
    feature = "feat"
    round_number = 1
    worktree = tmp_path / f"repair-{feature}-{round_number}"
    worktree.mkdir()

    cleanup_mock = MagicMock()

    # Call sequence: branch -d, checkout --theirs, git add, merge --continue
    subprocess_side_effects = [
        _make_subprocess_result(returncode=0),  # git branch -d (pre-clean)
        _make_subprocess_result(returncode=0),  # git checkout --theirs file.py
        _make_subprocess_result(returncode=0),  # git add file.py
        _make_subprocess_result(returncode=1, stderr="conflict remains"),  # merge --continue
    ]

    with (
        patch("cortex_command.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, ["file.py"])),
        patch("cortex_command.pipeline.conflict._cleanup_repair_worktree", cleanup_mock),
        patch("subprocess.run", side_effect=subprocess_side_effects),
    ):
        result = asyncio.run(resolve_trivial_conflict(
            feature=feature,
            branch=f"pipeline/{feature}",
            base_branch="main",
            conflicted_files=["file.py"],
            config=_FakeBatchConfig(),
            round_number=round_number,
        ))

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("merge_continue_failed:")
    cleanup_mock.assert_called_once_with(
        worktree,
        f"repair/{feature}-{round_number}",
        Path.cwd(),
        delete_branch=True,
    )


# ---------------------------------------------------------------------------
# (d) resolve_trivial_conflict: test gate failure
# ---------------------------------------------------------------------------


def test_resolve_trivial_conflict_test_failure(tmp_path: Path) -> None:
    """run_tests returns passed=False → success=False, error starts with 'test_failure:'."""
    feature = "feat"
    round_number = 1
    worktree = tmp_path / f"repair-{feature}-{round_number}"
    worktree.mkdir()

    cleanup_mock = MagicMock()
    run_tests_mock = MagicMock(
        return_value=_make_test_result(passed=False, output="FAILED test_foo")
    )

    with (
        patch("cortex_command.pipeline.conflict._create_repair_worktree",
              return_value=(worktree, ["file.py"])),
        patch("cortex_command.pipeline.conflict._cleanup_repair_worktree", cleanup_mock),
        patch("subprocess.run", return_value=_make_subprocess_result(returncode=0)),
        patch("cortex_command.pipeline.merge.run_tests", run_tests_mock),
    ):
        result = asyncio.run(resolve_trivial_conflict(
            feature=feature,
            branch=f"pipeline/{feature}",
            base_branch="main",
            conflicted_files=["file.py"],
            config=_FakeBatchConfig(),
            round_number=round_number,
        ))

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("test_failure:")
    cleanup_mock.assert_called_once_with(
        worktree,
        f"repair/{feature}-{round_number}",
        Path.cwd(),
        delete_branch=True,
    )


# ---------------------------------------------------------------------------
# (e) execute_feature: routes to trivial fast-path when eligible
# ---------------------------------------------------------------------------


def test_execute_feature_routes_trivial_when_eligible(tmp_path: Path) -> None:
    """1 conflicted file, no hot_files → resolve_trivial_conflict called, repair agent NOT called."""
    feature = "feat"
    config = _FakeBatchConfig(tmp_path)
    _write_conflict_event(config.overnight_events_path, feature, ["x.py"])

    mock_state = _make_mock_state(feature, recovery_attempts=0, recovery_depth=0)

    trivial_result = ConflictResolutionResult(
        success=True,
        strategy="trivial_fast_path",
        resolved_files=["x.py"],
        repair_branch=f"repair/{feature}-1",
        error=None,
    )

    resolve_mock = AsyncMock(return_value=trivial_result)
    repair_mock = AsyncMock()

    with (
        patch("cortex_command.overnight.feature_executor.load_state", return_value=mock_state),
        patch("cortex_command.overnight.feature_executor.save_state"),
        patch("cortex_command.overnight.feature_executor.resolve_trivial_conflict", resolve_mock),
        patch("cortex_command.overnight.feature_executor.dispatch_repair_agent", repair_mock),
    ):
        result = asyncio.run(execute_feature(
            feature=feature,
            worktree_path=tmp_path,
            config=config,
        ))

    assert result.status == "repair_completed"
    assert result.trivial_resolved is True
    assert result.resolved_files == ["x.py"]
    resolve_mock.assert_awaited_once()
    repair_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# (f) execute_feature: hot file overlap → repair agent dispatched, trivial skipped
# ---------------------------------------------------------------------------


def test_execute_feature_routes_repair_agent_when_hot_file(tmp_path: Path) -> None:
    """hot.py in hot_files → trivial path skipped, repair agent dispatched."""
    from cortex_command.pipeline.conflict import RepairResult

    feature = "feat"
    config = _FakeBatchConfig(tmp_path)
    _write_conflict_event(config.overnight_events_path, feature, ["hot.py"])

    # Write overnight-strategy.json with hot_files
    strategy_path = tmp_path / "overnight-strategy.json"
    strategy_path.write_text(
        json.dumps({"hot_files": ["hot.py"]}), encoding="utf-8"
    )

    mock_state = _make_mock_state(feature, recovery_attempts=0, recovery_depth=0)
    mock_state.features[feature].recovery_depth = 0

    repair_result = RepairResult(
        success=True,
        feature=feature,
        repair_branch=f"repair/{feature}-1",
    )

    resolve_mock = AsyncMock()
    repair_mock = AsyncMock(return_value=repair_result)

    with (
        patch("cortex_command.overnight.feature_executor.load_state", return_value=mock_state),
        patch("cortex_command.overnight.feature_executor.save_state"),
        patch("cortex_command.overnight.feature_executor.resolve_trivial_conflict", resolve_mock),
        patch("cortex_command.overnight.feature_executor.dispatch_repair_agent", repair_mock),
    ):
        result = asyncio.run(execute_feature(
            feature=feature,
            worktree_path=tmp_path,
            config=config,
        ))

    assert result.repair_agent_used is True
    assert result.trivial_resolved is False
    resolve_mock.assert_not_awaited()
    repair_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# (g) execute_feature: budget exhausted → deferral
# ---------------------------------------------------------------------------


def test_execute_feature_budget_exhausted_deferral(tmp_path: Path) -> None:
    """Non-trivial conflict + recovery_attempts=1 → FeatureResult(status='deferred')."""
    feature = "feat"
    config = _FakeBatchConfig(tmp_path)
    # 4 files = non-trivial (> 3)
    _write_conflict_event(
        config.overnight_events_path, feature,
        ["a.py", "b.py", "c.py", "d.py"],
    )

    mock_state = _make_mock_state(feature, recovery_attempts=1, recovery_depth=0)

    resolve_mock = AsyncMock()
    repair_mock = AsyncMock()
    deferral_mock = MagicMock()

    with (
        patch("cortex_command.overnight.feature_executor.load_state", return_value=mock_state),
        patch("cortex_command.overnight.feature_executor.resolve_trivial_conflict", resolve_mock),
        patch("cortex_command.overnight.feature_executor.dispatch_repair_agent", repair_mock),
        patch("cortex_command.overnight.feature_executor.write_deferral", deferral_mock),
        patch("cortex_command.overnight.feature_executor._next_escalation_n", return_value=1),
    ):
        result = asyncio.run(execute_feature(
            feature=feature,
            worktree_path=tmp_path,
            config=config,
        ))

    assert result.status == "deferred"
    deferral_mock.assert_called_once()
    resolve_mock.assert_not_awaited()
    repair_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# (h) execute_feature: trivial fast-path fails → falls through to repair agent
# ---------------------------------------------------------------------------


def test_execute_feature_trivial_fallthrough_to_repair_agent(tmp_path: Path) -> None:
    """Trivial path fails → repair agent dispatched, repair_agent_used=True."""
    from cortex_command.pipeline.conflict import RepairResult

    feature = "feat"
    config = _FakeBatchConfig(tmp_path)
    _write_conflict_event(config.overnight_events_path, feature, ["f.py"])

    mock_state = _make_mock_state(feature, recovery_attempts=0, recovery_depth=0)

    trivial_result = ConflictResolutionResult(
        success=False,
        strategy="trivial_fast_path",
        resolved_files=[],
        repair_branch=None,
        error="test_failure: assertion error",
    )
    repair_result = RepairResult(
        success=True,
        feature=feature,
        repair_branch=f"repair/{feature}-1",
    )

    resolve_mock = AsyncMock(return_value=trivial_result)
    repair_mock = AsyncMock(return_value=repair_result)

    with (
        patch("cortex_command.overnight.feature_executor.load_state", return_value=mock_state),
        patch("cortex_command.overnight.feature_executor.save_state"),
        patch("cortex_command.overnight.feature_executor.resolve_trivial_conflict", resolve_mock),
        patch("cortex_command.overnight.feature_executor.dispatch_repair_agent", repair_mock),
    ):
        result = asyncio.run(execute_feature(
            feature=feature,
            worktree_path=tmp_path,
            config=config,
        ))

    assert result.repair_agent_used is True
    assert result.trivial_resolved is False
    resolve_mock.assert_awaited_once()
    repair_mock.assert_awaited_once()
