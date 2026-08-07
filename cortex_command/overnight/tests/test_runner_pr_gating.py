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


def _make_worktree_recovered_state() -> OvernightState:
    """A session whose home worktree was re-created in place and merged.

    Pins the "recovered" shape from the worktree-loss fix (commits
    dac36ef8 / 01bef807): the merge-target resolver re-created the purged
    integration worktree, so the feature completed normally as ``merged``.
    """
    return OvernightState(
        session_id="overnight-test-pr-gating",
        plan_ref="cortex/lifecycle/test-plan.md",
        phase="complete",
        integration_branch="overnight/overnight-test-pr-gating",
        features={
            "feat-recovered": OvernightFeatureStatus(
                status="merged",
                repo_path=None,
            ),
        },
    )


def _make_worktree_unresolved_state() -> OvernightState:
    """A session whose every feature deferred on an unresolved worktree.

    Pins the "deferred" shape from the worktree-loss fix: when re-creation
    of the purged integration worktree is impossible, the feature is routed
    to ``deferred`` with ``error="integration worktree unresolved"`` and
    deliberately no ``recoverable_branch`` — it is neither merged nor
    recoverable, so the gate must treat it as zero progress.
    """
    return OvernightState(
        session_id="overnight-test-pr-gating",
        plan_ref="cortex/lifecycle/test-plan.md",
        phase="complete",
        integration_branch="overnight/overnight-test-pr-gating",
        features={
            "feat-unresolved": OvernightFeatureStatus(
                status="deferred",
                error="integration worktree unresolved",
                recoverable_branch=None,
                repo_path=None,
            ),
        },
    )


def _run_post_loop(
    tmp_path: Path, commit_count: int, state: OvernightState | None = None
) -> str:
    """Drive _post_loop in dry_run with externals mocked; return stdout."""
    state_path = tmp_path / "overnight-state.json"
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    events_path = tmp_path / "events.log"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    save_state(state if state is not None else _make_recoverable_state(), state_path)

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


def test_worktree_recovered_session_not_zero_progress(tmp_path: Path) -> None:
    """A session that re-created its purged home worktree and merged is real
    progress: no [ZERO PROGRESS] title (spec Requirement 12)."""
    out = _run_post_loop(
        tmp_path, commit_count=3, state=_make_worktree_recovered_state()
    )
    assert "DRY-RUN gh pr create" in out
    assert "[ZERO PROGRESS]" not in out


def test_worktree_unresolved_session_is_zero_progress(tmp_path: Path) -> None:
    """A session whose every feature deferred on an unresolved integration
    worktree carries no recoverable_branch, so it gates as [ZERO PROGRESS]
    (spec Requirement 12)."""
    out = _run_post_loop(
        tmp_path, commit_count=3, state=_make_worktree_unresolved_state()
    )
    assert "[ZERO PROGRESS]" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
