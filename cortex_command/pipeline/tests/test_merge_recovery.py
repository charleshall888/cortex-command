"""Unit tests for merge_recovery.py post-merge test-failure recovery loop.

Tests cover:
  - TestFlakyGuard: re-merge succeeds without code changes (transient failure).
  - TestRepairSuccess: flaky guard fails, repair cycle attempt 1 fixes the issue.
  - TestCircuitBreaker: SHA unchanged after dispatch — no commits produced.
  - TestExhausted: both repair attempts produce different SHAs but merge always fails.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.pipeline.merge import MergeResult, TestResult
from cortex_command.pipeline.merge_recovery import MergeRecoveryResult, recover_test_failure


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> CompletedProcess:
    """Build a CompletedProcess suitable for use as a subprocess.run mock return value."""
    result = CompletedProcess(args=[], returncode=returncode)
    result.stdout = stdout
    result.stderr = stderr
    return result


def _merge_success(feature: str = "f") -> MergeResult:
    """Return a MergeResult representing a successful merge with passing tests."""
    return MergeResult(
        success=True,
        feature=feature,
        conflict=False,
        test_result=TestResult(passed=True, output="", return_code=0),
    )


def _merge_failure(feature: str = "f") -> MergeResult:
    """Return a MergeResult representing a failed merge (test failure)."""
    return MergeResult(
        success=False,
        feature=feature,
        conflict=False,
        test_result=TestResult(passed=False, output="FAILED test_foo", return_code=1),
        error="Tests failed (exit code 1)",
    )


def _subprocess_side_effect(cmd, **kwargs):
    """Side-effect for subprocess.run that handles dirty-base check commands.

    - git rev-parse --show-toplevel -> /fake/repo
    - git status --porcelain -> empty (clean working tree)
    - git rev-parse HEAD -> "abc123" (default SHA)
    - git diff base..HEAD -> "" (empty diff)
    """
    if isinstance(cmd, list):
        if "--show-toplevel" in cmd:
            return _make_proc(returncode=0, stdout="/fake/repo\n")
        if "--porcelain" in cmd:
            return _make_proc(returncode=0, stdout="")
        if "rev-parse" in cmd and "HEAD" in cmd:
            return _make_proc(returncode=0, stdout="abc123\n")
        if "diff" in cmd:
            return _make_proc(returncode=0, stdout="")
    return _make_proc(returncode=0)


# Common arguments for recover_test_failure
_COMMON_KWARGS = dict(
    feature="test-feat",
    base_branch="main",
    test_output="FAILED test_foo",
    branch="pipeline/test-feat",
    worktree_path=Path("/fake/worktree"),
    test_command="python -m pytest",
    pipeline_log_path=None,
)


# ---------------------------------------------------------------------------
# Class 1: Flaky guard — re-merge passes without code changes
# ---------------------------------------------------------------------------

class TestFlakyGuard(unittest.IsolatedAsyncioTestCase):
    """When the flaky guard re-merge succeeds, recovery returns flaky=True."""

    async def test_flaky_detected_success_true(self):
        """Flaky guard passes -> result.success is True."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_success(),
                ):
                    result = await recover_test_failure(
                        **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                    )
            self.assertTrue(result.success)

    async def test_flaky_detected_flaky_true(self):
        """Flaky guard passes -> result.flaky is True."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_success(),
                ):
                    result = await recover_test_failure(
                        **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                    )
            self.assertTrue(result.flaky)

    async def test_flaky_detected_zero_attempts(self):
        """Flaky guard passes -> result.attempts is 0 (no repair cycles needed)."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_success(),
                ):
                    result = await recover_test_failure(
                        **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                    )
            self.assertEqual(result.attempts, 0)


# ---------------------------------------------------------------------------
# Class 2: Repair success — flaky guard fails, first repair attempt works
# ---------------------------------------------------------------------------

class TestRepairSuccess(unittest.IsolatedAsyncioTestCase):
    """Flaky guard fails, repair cycle attempt 1 produces new SHA, re-merge succeeds."""

    async def test_repair_success_result_true(self):
        """Repair attempt 1 succeeds -> result.success is True."""
        merge_call_count = 0

        def _merge_side_effect(*args, **kwargs):
            nonlocal merge_call_count
            merge_call_count += 1
            if merge_call_count == 1:
                # Flaky guard: still fails
                return _merge_failure()
            # Re-merge after repair: passes
            return _merge_success()

        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            if sha_call_count == 1:
                return "sha_before_1"
            return "sha_after_1"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    side_effect=_merge_side_effect,
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="fixed", cost_usd=0.0,
                                error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertTrue(result.success)

    async def test_repair_success_not_flaky(self):
        """Repair attempt 1 succeeds -> result.flaky is False."""
        merge_call_count = 0

        def _merge_side_effect(*args, **kwargs):
            nonlocal merge_call_count
            merge_call_count += 1
            if merge_call_count == 1:
                return _merge_failure()
            return _merge_success()

        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            if sha_call_count == 1:
                return "sha_before_1"
            return "sha_after_1"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    side_effect=_merge_side_effect,
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="fixed", cost_usd=0.0,
                                error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertFalse(result.flaky)

    async def test_repair_success_one_attempt(self):
        """Repair attempt 1 succeeds -> result.attempts is 1."""
        merge_call_count = 0

        def _merge_side_effect(*args, **kwargs):
            nonlocal merge_call_count
            merge_call_count += 1
            if merge_call_count == 1:
                return _merge_failure()
            return _merge_success()

        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            if sha_call_count == 1:
                return "sha_before_1"
            return "sha_after_1"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    side_effect=_merge_side_effect,
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="fixed", cost_usd=0.0,
                                error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertEqual(result.attempts, 1)


# ---------------------------------------------------------------------------
# Class 3: Circuit breaker — same SHA before and after dispatch
# ---------------------------------------------------------------------------

class TestCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    """SHA unchanged after dispatch triggers circuit breaker pause."""

    async def test_circuit_breaker_paused(self):
        """Same SHA before and after dispatch -> result.paused is True."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        return_value="same_sha",
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="tried but no changes",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertTrue(result.paused)

    async def test_circuit_breaker_in_error(self):
        """Same SHA before and after dispatch -> 'circuit_breaker' in result.error."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        return_value="same_sha",
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="tried but no changes",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertIn("circuit_breaker", result.error)


# ---------------------------------------------------------------------------
# Class 4: Exhausted — both repair attempts fail despite new SHAs
# ---------------------------------------------------------------------------

class TestExhausted(unittest.IsolatedAsyncioTestCase):
    """Both repair attempts produce new SHAs but merge always fails -> exhausted."""

    async def test_exhausted_not_success(self):
        """All attempts fail -> result.success is False."""
        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            return f"sha_{sha_call_count}"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="attempted fix",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertFalse(result.success)

    async def test_exhausted_paused(self):
        """All attempts fail -> result.paused is True."""
        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            return f"sha_{sha_call_count}"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="attempted fix",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertTrue(result.paused)

    async def test_exhausted_two_attempts(self):
        """All attempts fail -> result.attempts is 2."""
        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            return f"sha_{sha_call_count}"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="attempted fix",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertEqual(result.attempts, 2)

    async def test_exhausted_in_error(self):
        """All attempts fail -> 'exhausted' in result.error."""
        sha_call_count = 0

        def _sha_side_effect(worktree_path):
            nonlocal sha_call_count
            sha_call_count += 1
            return f"sha_{sha_call_count}"

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_subprocess_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_failure(),
                ):
                    with patch(
                        "cortex_command.pipeline.merge_recovery._get_branch_sha",
                        side_effect=_sha_side_effect,
                    ):
                        with patch(
                            "cortex_command.pipeline.dispatch.dispatch_task",
                            new_callable=AsyncMock,
                        ) as mock_dispatch:
                            mock_dispatch.return_value = MagicMock(
                                success=True, output="attempted fix",
                                cost_usd=0.0, error_type=None, error_detail=None,
                            )
                            result = await recover_test_failure(
                                **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                            )
            self.assertIn("exhausted", result.error)


class TestDirtyBaseCheck(unittest.IsolatedAsyncioTestCase):
    """Dirty-base check uses --untracked-files=no so lifecycle artifacts don't block recovery."""

    async def test_dirty_base_check_ignores_untracked_files(self):
        """git status call must include --untracked-files=no."""
        captured_cmds = []

        def _capturing_side_effect(cmd, **kwargs):
            if isinstance(cmd, list):
                captured_cmds.append(cmd)
            return _subprocess_side_effect(cmd, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_capturing_side_effect,
            ):
                with patch(
                    "cortex_command.pipeline.merge.merge_feature",
                    return_value=_merge_success(),
                ):
                    await recover_test_failure(
                        **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                    )

        status_calls = [c for c in captured_cmds if "--porcelain" in c]
        self.assertTrue(status_calls, "Expected at least one git status --porcelain call")
        for cmd in status_calls:
            self.assertIn("--untracked-files=no", cmd,
                          f"git status call missing --untracked-files=no: {cmd}")

    async def test_dirty_base_check_blocked_by_tracked_changes(self):
        """Tracked file changes (not untracked) must still block recovery."""
        def _dirty_tracked_side_effect(cmd, **kwargs):
            if isinstance(cmd, list) and "--porcelain" in cmd:
                return _make_proc(returncode=0, stdout=" M some-file.py\n")
            return _subprocess_side_effect(cmd, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_dirty_tracked_side_effect,
            ):
                result = await recover_test_failure(
                    **{**_COMMON_KWARGS, "learnings_dir": Path(tmp)},
                )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "dirty base branch after revert")


if __name__ == "__main__":
    unittest.main()
