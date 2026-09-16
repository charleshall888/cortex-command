"""Regression test for Task 11: ``cortex init`` must never create the macOS app.

``ensure_app()`` used to be called from ``init/handler.py``'s post-dispatch
step (7a); it is now created lazily by the first ``cortex dashboard`` run
(``cli.py``) instead. This pins the removal: even under conditions where
``ensure_app()`` would successfully build a bundle (darwin, ``osacompile``
present, ``cortex`` on ``PATH``, no opt-out), running ``cortex init`` must
leave ``macapp.app_path()`` untouched.

Mutation check: temporarily restoring the deleted ``macapp.ensure_app()``
call in ``handler.py``'s ``_run`` must make ``test_init_creates_no_macos_app``
fail.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.dashboard import macapp
from cortex_command.init.handler import main as init_main


def _git_init(path: Path) -> None:
    """Initialize ``path`` as a git repo."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)


def _make_update_args(path: Path) -> argparse.Namespace:
    """Build a Namespace for the terminal ``cortex init --update`` path.

    Mirrors ``test_handler_ensure.py``'s ``_make_update_args`` — the terminal
    path that used to reach the now-removed macapp step (7a) after
    ``settings_merge.register``.
    """
    return argparse.Namespace(
        path=str(path),
        update=True,
        force=False,
        unregister=False,
        ensure=False,
    )


@pytest.fixture
def fake_osacompile(tmp_path, monkeypatch):
    """Stand in for osacompile so ``ensure_app()`` would succeed if called.

    Mirrors ``dashboard/tests/test_launcher.py``'s fixture of the same name:
    HOME is redirected under ``tmp_path``, a fake executable ``cortex`` is
    put on the (faked) resolution path, and the actual compile/codesign
    subprocess calls are stubbed out. Everything ``ensure_app()`` needs to
    actually build a bundle is faked, so a reintroduced call to it from init
    would produce a real (fake-built) app directory — proving the absence
    isn't just an artifact of a hostile test environment (no macOS, no
    ``osacompile``) short-circuiting ``ensure_app()`` before it ever runs.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    (fake_home / ".claude").mkdir()
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv(macapp.OPT_OUT_ENV, raising=False)

    cortex = fake_home / "bin" / "cortex"
    cortex.parent.mkdir(parents=True)
    cortex.write_text("#!/bin/sh\n", encoding="utf-8")
    cortex.chmod(0o755)

    def _build(out, source, scratch):
        (out / "Contents").mkdir(parents=True)

    monkeypatch.setattr(macapp.sys, "platform", "darwin")
    monkeypatch.setattr(macapp, "_OSACOMPILE", sys.executable)
    monkeypatch.setattr(macapp, "build_app", _build)
    monkeypatch.setattr(macapp.shutil, "which", lambda name: str(cortex))
    return fake_home


def test_init_creates_no_macos_app(tmp_path: Path, fake_osacompile: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)

    rc = init_main(_make_update_args(repo))

    assert rc == 0
    assert not macapp.app_path().exists()
