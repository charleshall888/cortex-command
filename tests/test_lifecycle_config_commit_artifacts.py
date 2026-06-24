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

The closing section pins the ``cortex-read-commit-artifacts`` CLI
(``_main``): the #317/#321 wrong-env-var fix means it resolves the project
via ``_resolve_user_project_root()`` (CORTEX_REPO_ROOT, else a cortex/ walk
from cwd) and never consults CORTEX_COMMAND_ROOT (the package location).
"""

from __future__ import annotations

import pathlib

import pytest

from cortex_command.lifecycle_config import _main, read_commit_artifacts


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


# ---------------------------------------------------------------------------
# cortex-read-commit-artifacts CLI (_main) — project-root resolution
# ---------------------------------------------------------------------------


def _clear_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORTEX_COMMAND_ROOT", raising=False)
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)


def test_main_cortex_command_root_is_ignored_for_project_root(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    # Unrelated package-location repo declares the OPPOSITE flag value.
    command_root = tmp_path / "cortex-command-checkout"
    _write_config(command_root, "---\ncommit-artifacts: true\n---\nbody\n")
    monkeypatch.setenv("CORTEX_COMMAND_ROOT", str(command_root))

    # The user's project (cwd) disables commit-artifacts.
    project = tmp_path / "user-project"
    _write_config(project, "---\ncommit-artifacts: false\n---\nbody\n")
    monkeypatch.chdir(project)

    exit_code = _main()

    assert exit_code == 0
    # Must reflect the project, not the CORTEX_COMMAND_ROOT repo's "true".
    assert capsys.readouterr().out == "false\n"


def test_main_cortex_repo_root_override_is_honored(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    project = tmp_path / "user-project"
    _write_config(project, "---\ncommit-artifacts: false\n---\nbody\n")
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(project))
    monkeypatch.setenv("CORTEX_COMMAND_ROOT", str(tmp_path / "elsewhere"))

    exit_code = _main()

    assert exit_code == 0
    assert capsys.readouterr().out == "false\n"


def test_main_cwd_walk_resolves_from_subdirectory(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    project = tmp_path / "user-project"
    _write_config(project, "---\ncommit-artifacts: false\n---\nbody\n")
    subdir = project / "a" / "b"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    exit_code = _main()

    assert exit_code == 0
    assert capsys.readouterr().out == "false\n"


def test_main_fail_open_when_no_project_anywhere(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_roots(monkeypatch)

    bare = tmp_path / "bare"
    (bare / ".git").mkdir(parents=True)
    monkeypatch.chdir(bare)

    exit_code = _main()

    assert exit_code == 0
    # Default-true preserved when resolution raises and falls open to cwd.
    assert capsys.readouterr().out == "true\n"
