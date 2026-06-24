"""Unit tests for ``cortex_command.lifecycle_config.resolve_backlog_backend``.

Covers the spec R1 acceptance branches from
``cortex/lifecycle/config-driven-backlog-backend-resolver-local/spec.md``
(#317). Every degenerate input must resolve to ``"cortex-backlog"`` without
raising; an explicit value returns the raw string:

  1. Absent file → ``"cortex-backlog"``.
  2. Absent ``backlog:`` block → ``"cortex-backlog"``.
  3. Scalar ``backlog:`` value (not a mapping) → ``"cortex-backlog"``
     (the ``isinstance`` guard prevents an ``AttributeError``).
  4. ``backend`` null/empty → ``"cortex-backlog"``.
  5. Malformed YAML frontmatter → ``"cortex-backlog"`` + stderr warning.
  6. Valid explicit value → the raw string.
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle_config import resolve_backlog_backend


def _write_config(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    config_path = cortex_dir / "lifecycle.config.md"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_absent_file_returns_default(tmp_path: pathlib.Path) -> None:
    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"


def test_absent_block_returns_default(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: prompt\n---\nbody\n"
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"


def test_scalar_block_returns_default(tmp_path: pathlib.Path) -> None:
    body = "---\nbacklog: cortex-backlog\n---\nbody\n"
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"


def test_null_backend_returns_default(tmp_path: pathlib.Path) -> None:
    body = "---\nbacklog:\n  backend:\n---\nbody\n"
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"


def test_empty_backend_returns_default(tmp_path: pathlib.Path) -> None:
    body = '---\nbacklog:\n  backend: ""\n---\nbody\n'
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "cortex-backlog"


def test_malformed_yaml_returns_default_and_warns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "---\n: : :\n---\nbody\n"
    config_path = _write_config(tmp_path, body)
    result = resolve_backlog_backend(tmp_path)
    assert result == "cortex-backlog"
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert str(config_path) in captured.err


def test_valid_value_returns_raw_string(tmp_path: pathlib.Path) -> None:
    body = "---\nbacklog:\n  backend: github-issues\n---\nbody\n"
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "github-issues"


def test_valid_value_is_whitespace_stripped(tmp_path: pathlib.Path) -> None:
    body = "---\nbacklog:\n  backend: '  none  '\n---\nbody\n"
    _write_config(tmp_path, body)
    assert resolve_backlog_backend(tmp_path) == "none"
