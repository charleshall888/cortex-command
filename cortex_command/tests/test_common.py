"""Tests for cortex_command.common — focused on _resolve_user_project_root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cortex_command.common import CortexProjectRootError, _resolve_user_project_root


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
