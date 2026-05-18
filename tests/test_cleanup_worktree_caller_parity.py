"""Parity test: cleanup_worktree() raises TypeError when branch= is omitted.

Verifies that the ``branch`` parameter is keyword-only and required, so
callers that forget to pass it get an immediate TypeError rather than
silently deleting the wrong branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_cleanup_worktree_raises_typeerror_when_branch_omitted(tmp_path):
    """cleanup_worktree() without branch= raises TypeError."""
    import cortex_command.pipeline.worktree as wt_mod

    # Initialise a minimal git repo so _main_worktree_root() has something to
    # query if the function somehow reaches subprocess calls (it should not).
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
        },
    )

    with pytest.raises(TypeError):
        wt_mod.cleanup_worktree("test-fixture", repo_path=repo)
