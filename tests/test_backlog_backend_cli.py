"""Unit tests for ``cortex_command.lifecycle.backlog_backend_cli``.

Covers the spec R2 graceful console-script shape from
``cortex/lifecycle/config-driven-backlog-backend-resolver-local/spec.md``
(#317): the reader prints the resolved backend + newline and exits 0,
defaulting to ``cortex-backlog`` for an unconfigured repo.

The new ``cortex-read-backlog-backend`` console script is NOT on PATH
until the editable wheel is reinstalled, so these tests exercise the
module in-process via ``main()`` (passing ``repo_root`` as the optional
positional) rather than the PATH command.
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle.backlog_backend_cli import main


def _write_config(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    config_path = cortex_dir / "lifecycle.config.md"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_resolved_backend_is_printed_with_newline(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Clear any ambient CORTEX_COMMAND_ROOT so the positional path is honored.
    monkeypatch.delenv("CORTEX_COMMAND_ROOT", raising=False)
    body = "---\nbacklog:\n  backend: github-issues\n---\nbody\n"
    _write_config(tmp_path, body)

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "github-issues\n"


def test_unconfigured_dir_prints_default_and_exits_zero(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CORTEX_COMMAND_ROOT", raising=False)
    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "cortex-backlog\n"


def test_cortex_command_root_env_overrides_positional(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = "---\nbacklog:\n  backend: jira\n---\nbody\n"
    _write_config(tmp_path, body)
    monkeypatch.setenv("CORTEX_COMMAND_ROOT", str(tmp_path))

    # Positional points at an unconfigured dir; the env var must win.
    other = tmp_path / "elsewhere"
    other.mkdir()
    exit_code = main([str(other)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "jira\n"
