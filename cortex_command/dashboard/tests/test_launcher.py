"""The machine-wide project list, the macOS app, and stale-server replacement.

Together these make a clicked app a whole launch: it finds every project
without a shell environment, and it never hands back a board served by an
older install or missing a newly registered project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command import cli
from cortex_command.dashboard import macapp, projects


def _make_project(path: Path, *, worktree: bool = False) -> Path:
    (path / ".claude").mkdir(parents=True)
    (path / "cortex").mkdir()
    if worktree:
        (path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    else:
        (path / ".git").mkdir()
    return path.resolve()


@pytest.fixture
def home(tmp_path, monkeypatch):
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return fake


class TestProjectList:
    def test_worktrees_and_bare_cortex_dirs_are_not_projects(self, tmp_path):
        assert projects.is_project(_make_project(tmp_path / "repo"))
        assert not projects.is_project(_make_project(tmp_path / "wt", worktree=True))
        bare = tmp_path / "bare"
        (bare / "cortex").mkdir(parents=True)
        (bare / ".git").mkdir()
        assert not projects.is_project(bare)

    def test_first_read_seeds_from_claude_code_and_then_the_file_rules(
        self, tmp_path, home
    ):
        zeta = _make_project(tmp_path / "zeta")
        alpha = _make_project(tmp_path / "alpha")
        worktree = _make_project(tmp_path / "wt", worktree=True)
        (home / ".claude.json").write_text(
            json.dumps(
                {"projects": {str(zeta): {}, str(alpha): {}, str(worktree): {}}}
            ),
            encoding="utf-8",
        )

        assert projects.load_projects() == [alpha, zeta]

        # An operator removing a line is honoured: the seed never re-runs.
        projects.registry_path().write_text("%s\n" % zeta, encoding="utf-8")
        assert projects.load_projects() == [zeta]

    def test_registering_keeps_seeded_projects_and_is_idempotent(
        self, tmp_path, home
    ):
        seeded = _make_project(tmp_path / "seeded")
        (home / ".claude.json").write_text(
            json.dumps({"projects": {str(seeded): {}}}), encoding="utf-8"
        )
        new = _make_project(tmp_path / "new")

        projects.register_project(new)
        projects.register_project(new)

        assert projects.load_projects() == [seeded, new]

    def test_deleted_projects_drop_out(self, tmp_path, home):
        gone = _make_project(tmp_path / "gone")
        projects.register_project(gone)
        shutil.rmtree(gone)
        assert projects.load_projects() == []


@pytest.fixture
def fake_osacompile(home, monkeypatch):
    """Stand in for osacompile so app lifecycle tests run anywhere."""
    compiled: list[str] = []

    def _build(out, source, scratch):
        (out / "Contents").mkdir(parents=True)
        compiled.append(source)

    cortex = home / "bin" / "cortex"
    cortex.parent.mkdir()
    cortex.write_text("#!/bin/sh\n", encoding="utf-8")
    cortex.chmod(0o755)

    monkeypatch.delenv(macapp.OPT_OUT_ENV, raising=False)
    monkeypatch.setattr(macapp.sys, "platform", "darwin")
    monkeypatch.setattr(macapp, "_OSACOMPILE", sys.executable)
    monkeypatch.setattr(macapp, "build_app", _build)
    monkeypatch.setattr(macapp.shutil, "which", lambda name: str(cortex))
    return compiled


class TestMacApp:
    def test_created_once_then_left_alone(self, fake_osacompile):
        assert macapp.ensure_app() == "created"
        assert macapp.app_path().is_dir()
        assert macapp.ensure_app() is None
        assert len(fake_osacompile) == 1

    def test_an_app_the_operator_deleted_stays_deleted(self, fake_osacompile):
        macapp.ensure_app()
        shutil.rmtree(macapp.app_path())
        assert macapp.ensure_app() is None
        assert not macapp.app_path().exists()

    def test_rebuilt_when_its_cortex_is_gone(self, fake_osacompile, home, monkeypatch):
        macapp.ensure_app()
        moved = home / "elsewhere" / "cortex"
        moved.parent.mkdir()
        (home / "bin" / "cortex").rename(moved)
        monkeypatch.setattr(macapp.shutil, "which", lambda name: str(moved))

        assert macapp.ensure_app() == "updated"
        assert str(moved) in fake_osacompile[-1]

    def test_opt_out_builds_nothing(self, fake_osacompile, monkeypatch):
        monkeypatch.setenv(macapp.OPT_OUT_ENV, "0")
        assert macapp.ensure_app() is None
        assert not macapp.app_path().exists()

    @pytest.mark.skipif(
        not Path("/usr/bin/osacompile").exists(), reason="needs macOS osacompile"
    )
    def test_the_real_build_compiles_and_stays_signed(self, tmp_path):
        """Both failures show only when someone clicks the app.

        A syntax error in the applet source fails the compile. A broken seal
        after the icon swap leaves an app that Apple silicon refuses to run.
        """
        source = macapp.applet_source('/odd "path"/cortex', "/usr/bin:/bin")
        out = tmp_path / "t.app"
        macapp.build_app(out, source, tmp_path)

        assert (out / "Contents" / "Resources" / "applet.icns").stat().st_size
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", str(out)],
            check=True,
            capture_output=True,
        )


class TestStaleServer:
    def test_same_version_and_a_superset_of_roots_is_reused(self, tmp_path):
        a = _make_project(tmp_path / "a")
        b = _make_project(tmp_path / "b")
        running = {"version": cli._installed_version(), "roots": [str(a), str(b)]}
        assert cli._serves_what_was_asked(running, [str(b)])

    def test_an_older_install_or_a_missing_root_is_replaced(self, tmp_path):
        a = _make_project(tmp_path / "a")
        b = _make_project(tmp_path / "b")
        current = cli._installed_version()
        assert not cli._serves_what_was_asked(
            {"version": "0.0.1", "roots": [str(a)]}, [str(a)]
        )
        assert not cli._serves_what_was_asked(
            {"version": current, "roots": [str(a)]}, [str(a), str(b)]
        )
        # A server predating the version field is stale by definition.
        assert not cli._serves_what_was_asked({"status": "ok"}, [str(a)])

    def test_a_port_held_by_something_else_fails_without_starting(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(cli, "_port_is_serving", lambda *a, **k: True)
        monkeypatch.setattr(cli, "_running_dashboard_identity", lambda port: None)
        monkeypatch.setattr(cli, "_stop_running_dashboard", lambda port: False)
        monkeypatch.setattr(
            subprocess, "Popen", lambda *a, **k: pytest.fail("must not start")
        )

        code = cli._dispatch_dashboard_background(
            port=8099, url="http://127.0.0.1:8099", roots=[], as_json=True
        )

        assert code == 1
        assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_open_forces_a_browser_for_a_non_tty_caller(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    args = cli._build_parser().parse_args(["dashboard", "--open"])
    assert cli._should_open_browser(args)
    with pytest.raises(SystemExit):
        cli._build_parser().parse_args(["dashboard", "--open", "--no-open"])
