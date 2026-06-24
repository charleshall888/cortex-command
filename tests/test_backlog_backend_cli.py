"""Unit tests for ``cortex_command.lifecycle.backlog_backend_cli``.

Covers the spec R2 graceful console-script shape from
``cortex/lifecycle/config-driven-backlog-backend-resolver-local/spec.md``
(#317): the reader prints the resolved backend + newline and exits 0,
defaulting to ``cortex-backlog`` for an unconfigured repo.

Also pins the #317/#321 wrong-env-var fix: the reader resolves the
*project* to inspect via ``_resolve_user_project_root()`` (CORTEX_REPO_ROOT
override, else an upward cortex/ walk from cwd), with an explicit positional
winning verbatim and a cwd fall-open. It does NOT read CORTEX_COMMAND_ROOT —
that variable locates the cortex-command package, not the user's project.

The ``cortex-read-backlog-backend`` console script is exercised in-process
via ``main()`` (passing argv) rather than the PATH command, which is not
installed until the editable wheel is reinstalled.
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle.backlog_backend_cli import main


def _write_config(repo_root: pathlib.Path, body: str) -> pathlib.Path:
    cortex_dir = repo_root / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    config_path = cortex_dir / "lifecycle.config.md"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _clear_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip both root env vars so a test controls resolution explicitly."""
    monkeypatch.delenv("CORTEX_COMMAND_ROOT", raising=False)
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)


_GITHUB_BODY = "---\nbacklog:\n  backend: github-issues\n---\nbody\n"
_JIRA_BODY = "---\nbacklog:\n  backend: jira\n---\nbody\n"


# ---------------------------------------------------------------------------
# Explicit positional repo_root — highest precedence, used verbatim
# ---------------------------------------------------------------------------


def test_explicit_positional_repo_root_is_honored(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)
    _write_config(tmp_path, _GITHUB_BODY)

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == "github-issues\n"


def test_unconfigured_positional_prints_default_and_exits_zero(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == "cortex-backlog\n"


# ---------------------------------------------------------------------------
# Regression (the bug this change fixes): CORTEX_COMMAND_ROOT must NOT steer
# project resolution. With it pointed at an unrelated jira repo and cwd inside
# a github-issues project, the reader returns the project's backend.
# ---------------------------------------------------------------------------


def test_cortex_command_root_is_ignored_for_project_root(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    # The cortex-command *package* location — a wholly unrelated repo.
    command_root = tmp_path / "cortex-command-checkout"
    _write_config(command_root, _JIRA_BODY)
    monkeypatch.setenv("CORTEX_COMMAND_ROOT", str(command_root))

    # The user's actual project — cwd lives here.
    project = tmp_path / "user-project"
    _write_config(project, _GITHUB_BODY)
    monkeypatch.chdir(project)

    exit_code = main([])

    assert exit_code == 0
    # Must be the project's backend, NOT the CORTEX_COMMAND_ROOT repo's "jira".
    assert capsys.readouterr().out == "github-issues\n"


# ---------------------------------------------------------------------------
# CORTEX_REPO_ROOT override is honored (and beats a stray CORTEX_COMMAND_ROOT)
# ---------------------------------------------------------------------------


def test_cortex_repo_root_override_is_honored(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    project = tmp_path / "user-project"
    _write_config(project, _GITHUB_BODY)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project))
    # A stray package-location var must not change the answer.
    monkeypatch.setenv("CORTEX_COMMAND_ROOT", str(tmp_path / "elsewhere"))

    exit_code = main([])

    assert exit_code == 0
    assert capsys.readouterr().out == "github-issues\n"


# ---------------------------------------------------------------------------
# cwd-walk resolves from a subdirectory of the project
# ---------------------------------------------------------------------------


def test_cwd_walk_resolves_from_subdirectory(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    project = tmp_path / "user-project"
    _write_config(project, _GITHUB_BODY)
    subdir = project / "a" / "b"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    exit_code = main([])

    assert exit_code == 0
    assert capsys.readouterr().out == "github-issues\n"


# ---------------------------------------------------------------------------
# Fail-open: no project anywhere → cortex-backlog, exit 0, never raises
# ---------------------------------------------------------------------------


def test_fail_open_when_no_project_anywhere(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    # A .git boundary with no cortex/ ancestor bounds the upward walk so it
    # raises CortexProjectRootError, which the reader must swallow.
    bare = tmp_path / "bare"
    (bare / ".git").mkdir(parents=True)
    monkeypatch.chdir(bare)

    exit_code = main([])

    assert exit_code == 0
    assert capsys.readouterr().out == "cortex-backlog\n"
