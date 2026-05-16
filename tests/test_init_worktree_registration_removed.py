"""Regression test: ``cortex init`` no longer registers a worktree-root entry.

The legacy ``cortex init`` Step 8 (R7 of
``harden-autonomous-dispatch-path-for-interactive``) registered the
default worktree root in ``~/.claude/settings.local.json``'s
``sandbox.filesystem.allowWrite``. The
``restore-worktree-root-env-prefix`` lifecycle retires Step 8: the
new same-repo default lives at ``$TMPDIR/cortex-worktrees/<feature>``,
which is already sandbox-writable per convention, and the user-level
``allowWrite`` registration was structurally unable to relieve
Seatbelt's mandatory deny on ``.mcp.json`` anyway.

This test asserts the structural property: after ``cortex init`` runs
on a fresh repo, no ``allowWrite`` entry matches a worktree-shaped path
(``.../worktrees`` / ``.../worktrees/``) or carries the new sentinel
suffix ``#cortex-worktree-root``. It replaces the deleted
``tests/test_init_worktree_registration.py`` (R7 acceptance tests, all
three of which were structurally tied to Step 8).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import pytest

from cortex_command.init.handler import main as init_main


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


def _make_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        path=str(path),
        update=False,
        force=False,
        unregister=False,
    )


def _allow_write(home: Path) -> list:
    settings = home / ".claude" / "settings.local.json"
    if not settings.exists():
        return []
    data = json.loads(settings.read_text(encoding="utf-8"))
    return data.get("sandbox", {}).get("filesystem", {}).get("allowWrite", [])


def test_cortex_init_does_not_register_worktrees_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After Step 8 removal, ``cortex init`` writes no worktree-root entry.

    Asserts the ``allowWrite`` array contains no entry that:
        (a) matches the regex ``r"worktrees/?$"`` (a path ending in
            ``worktrees`` or ``worktrees/``), nor
        (b) contains the new sentinel suffix ``#cortex-worktree-root``.
    """
    fake_home = _isolate_home(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    rc = init_main(_make_args(repo))
    assert rc == 0, "cortex init should succeed on a fresh repo"

    allow = _allow_write(fake_home)
    assert isinstance(allow, list), f"allowWrite should be a list, got {type(allow)}"

    worktrees_re = re.compile(r"worktrees/?$")
    offending = [
        entry
        for entry in allow
        if isinstance(entry, str)
        and (worktrees_re.search(entry) or "#cortex-worktree-root" in entry)
    ]
    assert offending == [], (
        "cortex init must not register any worktree-root entry; "
        f"found offending entries: {offending!r}"
    )
