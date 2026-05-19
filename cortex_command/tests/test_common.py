"""Tests for cortex_command.common — focused on _resolve_user_project_root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
    _resolve_user_project_root_from_cwd,
)


# ---------------------------------------------------------------------------
# _resolve_user_project_root
# ---------------------------------------------------------------------------

class TestResolveUserProjectRoot:
    """Tests for the upward-walking cortex project root resolver."""

    def test_detects_cortex_subdir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the directory that contains a ``cortex/`` subdirectory."""
        cortex_dir = tmp_path / "cortex"
        cortex_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        result = _resolve_user_project_root()

        assert result == tmp_path.resolve()

    def test_detects_cortex_subdir_from_child(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the ancestor that contains ``cortex/`` when invoked from a subdirectory."""
        cortex_dir = tmp_path / "cortex"
        cortex_dir.mkdir()
        child = tmp_path / "subdir" / "nested"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        result = _resolve_user_project_root()

        assert result == tmp_path.resolve()

    def test_raises_when_no_cortex_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises CortexProjectRootError when no ancestor has a ``cortex/`` subdir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
        # Terminate the walk at tmp_path by placing a .git marker there.
        (tmp_path / ".git").mkdir()

        with pytest.raises(CortexProjectRootError):
            _resolve_user_project_root()

    def test_env_override_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns Path(CORTEX_REPO_ROOT) verbatim when that env var is set."""
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        result = _resolve_user_project_root()

        assert result == tmp_path


# ---------------------------------------------------------------------------
# _resolve_user_project_root_from_cwd
# ---------------------------------------------------------------------------

class TestResolveUserProjectRootFromCwd:
    """Tests for the cwd-only cortex project root resolver."""

    def test_from_cwd_returns_worktree_root_ignoring_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the worktree root from CWD even when CORTEX_REPO_ROOT points elsewhere.

        Simulates a git worktree: the worktree directory has a ``.git`` file
        (not a directory) which is the worktree-shaped marker, and a ``cortex/``
        subdirectory. CWD is set to a subdirectory inside the worktree.
        CORTEX_REPO_ROOT is set to the main repo path (a different directory),
        which the cwd-based resolver must ignore.
        """
        # Build a fake worktree: root contains cortex/ and a .git *file*
        worktree_root = tmp_path / "worktree"
        worktree_root.mkdir()
        (worktree_root / "cortex").mkdir()
        (worktree_root / ".git").write_text("gitdir: /some/main/repo/.git/worktrees/wt\n")

        # CWD is inside the worktree (a subdirectory)
        inside = worktree_root / "subdir"
        inside.mkdir()
        monkeypatch.chdir(inside)

        # CORTEX_REPO_ROOT points to the main repo (a separate directory)
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(main_repo))

        result = _resolve_user_project_root_from_cwd()

        assert result == worktree_root.resolve()

    def test_from_cwd_raises_from_non_cortex_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises CortexProjectRootError when CWD has no cortex/ ancestor.

        Places a ``.git`` file (worktree-shaped boundary) at tmp_path so the
        walk terminates without finding a ``cortex/`` directory.
        """
        (tmp_path / ".git").write_text("gitdir: /some/other/repo/.git/worktrees/wt\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(CortexProjectRootError):
            _resolve_user_project_root_from_cwd()
