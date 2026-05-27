"""Unit tests for ``cortex_command.lifecycle_config.read_commit_artifacts``.

Covers the three required branches from spec R1 of
``cortex/lifecycle/refine-commits-lifecycle-artifacts/spec.md``:

  1. Missing file → ``True`` (preserve default).
  2. Field absent → ``True`` (preserve default).
  3. Field present with ``false`` → ``False``.

Plus default-safety branches the implementation also handles:

  4. Field present with ``true`` → ``True``.
  5. Malformed YAML frontmatter → ``True`` + stderr warning.
  6. Field present non-boolean → ``True`` + stderr warning.
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle_config import read_commit_artifacts


def _write_config(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    config_path = cortex_dir / "lifecycle.config.md"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_missing_file_returns_true(tmp_path: pathlib.Path) -> None:
    assert read_commit_artifacts(tmp_path) is True


def test_field_absent_returns_true(tmp_path: pathlib.Path) -> None:
    body = "---\nbranch-mode: prompt\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_commit_artifacts(tmp_path) is True


def test_field_false_returns_false(tmp_path: pathlib.Path) -> None:
    body = "---\ncommit-artifacts: false\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_commit_artifacts(tmp_path) is False


def test_field_true_returns_true(tmp_path: pathlib.Path) -> None:
    body = "---\ncommit-artifacts: true\n---\nbody\n"
    _write_config(tmp_path, body)
    assert read_commit_artifacts(tmp_path) is True


def test_malformed_yaml_returns_true_and_warns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "---\n: : :\n---\nbody\n"
    config_path = _write_config(tmp_path, body)
    result = read_commit_artifacts(tmp_path)
    assert result is True
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert str(config_path) in captured.err


def test_non_boolean_value_returns_true_and_warns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "---\ncommit-artifacts: maybe\n---\nbody\n"
    _write_config(tmp_path, body)
    result = read_commit_artifacts(tmp_path)
    assert result is True
    captured = capsys.readouterr()
    assert "commit-artifacts" in captured.err
    assert "not a boolean" in captured.err
