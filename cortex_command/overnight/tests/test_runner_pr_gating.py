"""Tests for the [ZERO PROGRESS] inner PR-title gate (Task 8 / R9).

A home session whose only non-merged outcome is a built-but-merge-blocked
recoverable feature is real progress: it must NOT receive the [ZERO PROGRESS]
draft-PR title even though it merged zero features. The outer empty-integration
(commit_count == 0) gate that skips PR creation entirely is unchanged.

The tests drive ``_post_loop`` in dry_run mode (where ``gh pr create`` is echoed
via ``dry_run_echo`` rather than invoked) so the title flows through the real
gate, and assert on captured stdout.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex_command.overnight import runner
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    save_state,
)


def _make_recoverable_state() -> OvernightState:
    """A completed home session: zero merges, one recoverable home feature."""
    return OvernightState(
        session_id="overnight-test-pr-gating",
        plan_ref="cortex/lifecycle/test-plan.md",
        phase="complete",
        integration_branch="overnight/overnight-test-pr-gating",
        features={
            "feat-recoverable": OvernightFeatureStatus(
                status="deferred",
                recoverable_branch="pipeline/feat-recoverable-2",
                repo_path=None,
            ),
        },
    )


def _run_post_loop(tmp_path: Path, commit_count: int) -> str:
    """Drive _post_loop in dry_run with externals mocked; return stdout."""
    state_path = tmp_path / "overnight-state.json"
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    events_path = tmp_path / "events.log"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    save_state(_make_recoverable_state(), state_path)

    buf = io.StringIO()
    fake_proc = MagicMock(returncode=1, stdout="", stderr="")
    with patch.object(runner.subprocess, "run", return_value=fake_proc), patch.object(
        runner, "ipc", MagicMock()
    ), patch.object(
        runner, "_integration_commit_count", return_value=commit_count
    ):
        with redirect_stdout(buf):
            runner._post_loop(
                state=runner.state_module.load_state(state_path),
                state_path=state_path,
                session_dir=session_dir,
                repo_path=repo_path,
                events_path=events_path,
                round_num=2,
                session_id="overnight-test-pr-gating",
                dry_run=True,
                coord=MagicMock(),
            )
    return buf.getvalue()


def test_recoverable_not_zero_progress(tmp_path: Path) -> None:
    """A recoverable-only home session with commits gets no [ZERO PROGRESS] title."""
    out = _run_post_loop(tmp_path, commit_count=5)
    # The gh pr create line was emitted (commits > 0 → PR path runs)...
    assert "DRY-RUN gh pr create" in out
    # ...and it is NOT the zero-progress draft title.
    assert "[ZERO PROGRESS]" not in out
    assert "Overnight session: overnight/overnight-test-pr-gating" in out


def test_zero_commits_still_skips_pr(tmp_path: Path) -> None:
    """The outer commit_count == 0 gate is unchanged: no PR is created."""
    out = _run_post_loop(tmp_path, commit_count=0)
    # No PR is created at all when the integration branch has no commits.
    assert "DRY-RUN gh pr create" not in out
    assert "no branch commits" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
