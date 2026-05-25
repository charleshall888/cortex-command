"""Tests for ``cortex_command.worktree_precondition`` (the
``cortex-worktree-precondition`` console-script registered in
``pyproject.toml``).

The probe is the gate for the lifecycle skill's ``EnterWorktree`` call
in ``implement.md`` §1a step v; getting its two branches wrong would
either skip auto-entry when it was safe (false positive → degraded UX)
or fire ``EnterWorktree`` when already in a worktree (false negative →
schema rejection by the live tool).

Test approach: exercise against real ``git`` state via ``tmp_path``,
including a real ``git worktree add`` — the precondition probe is
itself a thin wrapper over two ``git rev-parse`` calls, so mocking
those would reduce the test to a tautology. The R9 acceptance criterion
in ``spec.md`` calls for "independent oracle, not self-sealing", which
means ground truth must come from ``git`` itself.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.worktree_precondition import is_in_worktree, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> str:
    """Initialize a git repo with a single empty commit; return branch name."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c", "commit.gpgsign=false",
            "-c", "user.email=test@test.com",
            "-c", "user.name=Test",
            "commit",
            "--allow-empty",
            "-q",
            "-m", "init",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def restore_cwd():
    """Save and restore CWD around tests that ``os.chdir`` into tmp_path."""
    original = os.getcwd()
    try:
        yield
    finally:
        os.chdir(original)


# ---------------------------------------------------------------------------
# is_in_worktree() — direct API
# ---------------------------------------------------------------------------


def test_main_checkout_returns_false(tmp_path, restore_cwd, monkeypatch):
    """Main repo CWD: probe reports NOT in worktree, exit 0."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    os.chdir(repo)
    monkeypatch.setattr("sys.argv", ["cortex-worktree-precondition"])
    assert is_in_worktree() is False
    assert main() == 0


def test_linked_worktree_returns_true(tmp_path, restore_cwd, monkeypatch):
    """Inside a `git worktree add`ed sibling: probe reports IN worktree, exit 1."""
    repo = tmp_path / "repo"
    repo.mkdir()
    branch = _init_repo(repo)

    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(wt), "-b", "feature", branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    os.chdir(wt)
    monkeypatch.setattr("sys.argv", ["cortex-worktree-precondition"])
    assert is_in_worktree() is True
    assert main() == 1


def test_outside_any_repo_returns_false(tmp_path, restore_cwd, monkeypatch):
    """Outside any git repo: probe reports NOT in worktree (safe), exit 0.

    The probe's contract is "is it safe to call EnterWorktree" — outside
    any repo, the tool will surface its own error if the path is
    invalid, so the probe should not block.
    """
    bare = tmp_path / "bare"
    bare.mkdir()

    os.chdir(bare)
    monkeypatch.setattr("sys.argv", ["cortex-worktree-precondition"])
    assert is_in_worktree() is False
    assert main() == 0


def test_subdirectory_of_main_returns_false(tmp_path, restore_cwd):
    """CWD in a subdir of the main checkout still reports NOT in worktree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    sub = repo / "subdir"
    sub.mkdir()

    os.chdir(sub)
    assert is_in_worktree() is False


def test_subdirectory_of_linked_worktree_returns_true(tmp_path, restore_cwd):
    """CWD in a subdir of a linked worktree still reports IN worktree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    branch = _init_repo(repo)

    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(wt), "-b", "feature", branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sub = wt / "subdir"
    sub.mkdir()

    os.chdir(sub)
    assert is_in_worktree() is True


# ---------------------------------------------------------------------------
# main() — usage error
# ---------------------------------------------------------------------------


def test_main_rejects_extra_args(monkeypatch, capsys):
    """Any argv beyond the program name is a usage error → exit 2."""
    monkeypatch.setattr("sys.argv", ["cortex-worktree-precondition", "extra"])
    assert main() == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()
