"""Tests for cortex init worktree-root registration (R7).

Covers three acceptance criteria:
    (a) same-repo path is registered in sandbox.filesystem.allowWrite.
    (b) cross-repo $TMPDIR path is NOT registered (already sandbox-writable
        per convention).
    (c) cortex init is idempotent — re-run does not duplicate the worktree
        entry.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.init.handler import main as init_main


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _git_init(path: Path) -> None:
    """Initialize ``path`` as a bare-enough git repo for cortex init."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point HOME at a fresh temp directory so settings.local.json is isolated."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def _make_args(
    path: Path,
    *,
    update: bool = False,
    force: bool = False,
    unregister: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        path=str(path),
        update=update,
        force=force,
        unregister=unregister,
    )


def _settings_path(home: Path) -> Path:
    return home / ".claude" / "settings.local.json"


def _allow_write(home: Path) -> list:
    """Read allowWrite entries from settings.local.json."""
    settings = _settings_path(home)
    if not settings.exists():
        return []
    data = json.loads(settings.read_text(encoding="utf-8"))
    return (
        data.get("sandbox", {}).get("filesystem", {}).get("allowWrite", [])
    )


# ---------------------------------------------------------------------------
# (a) Same-repo path is registered
# ---------------------------------------------------------------------------


def test_same_repo_worktree_root_is_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7(a): cortex init registers the worktree root for a same-repo path.

    The resolver returns a path under the repo root (not under $TMPDIR),
    so the worktree target must appear in sandbox.filesystem.allowWrite.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    expected_worktree_root = repo / ".claude" / "worktrees"
    expected_worktree_target = str(expected_worktree_root) + "/"

    with patch(
        "cortex_command.init.handler.resolve_worktree_root",
        return_value=expected_worktree_root,
    ):
        rc = init_main(_make_args(repo))

    assert rc == 0, "cortex init should succeed"
    allow = _allow_write(fake_home)
    assert expected_worktree_target in allow, (
        f"Expected {expected_worktree_target!r} in allowWrite, got: {allow}"
    )


# ---------------------------------------------------------------------------
# (b) Cross-repo $TMPDIR path is NOT registered
# ---------------------------------------------------------------------------


def test_cross_repo_tmpdir_path_is_not_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7(b): cortex init skips registration when the worktree root is under $TMPDIR.

    Paths under $TMPDIR are already sandbox-writable per convention; adding
    them to allowWrite would be redundant (and could reveal the session tmpdir
    to unrelated sandbox checks).
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    # Build a TMPDIR-based path the resolver would return for cross-repo usage.
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    cross_repo_root = Path(tmpdir) / "overnight-worktrees" / "sess-abc" / "feat"
    cross_repo_target = str(cross_repo_root) + "/"

    with patch(
        "cortex_command.init.handler.resolve_worktree_root",
        return_value=cross_repo_root,
    ):
        rc = init_main(_make_args(repo))

    assert rc == 0, "cortex init should succeed"
    allow = _allow_write(fake_home)
    assert cross_repo_target not in allow, (
        f"Cross-repo TMPDIR path {cross_repo_target!r} should NOT be in allowWrite, "
        f"got: {allow}"
    )


# ---------------------------------------------------------------------------
# (c) Idempotent — re-run does not duplicate the worktree entry
# ---------------------------------------------------------------------------


def test_cortex_init_worktree_registration_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R7(c): re-running cortex init does not duplicate the worktree entry.

    Running ``cortex init --update`` a second time (idiomatic re-init path)
    must not create a second copy of the worktree-root allowWrite entry.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    expected_worktree_root = repo / ".claude" / "worktrees"
    expected_worktree_target = str(expected_worktree_root) + "/"

    with patch(
        "cortex_command.init.handler.resolve_worktree_root",
        return_value=expected_worktree_root,
    ):
        rc1 = init_main(_make_args(repo))
        assert rc1 == 0, "first cortex init should succeed"

        rc2 = init_main(_make_args(repo, update=True))
        assert rc2 == 0, "second cortex init --update should succeed"

    allow = _allow_write(fake_home)
    count = allow.count(expected_worktree_target)
    assert count == 1, (
        f"Expected exactly one occurrence of {expected_worktree_target!r} "
        f"in allowWrite, got {count}: {allow}"
    )
