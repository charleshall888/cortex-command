"""Tests for cortex-list-requirements — the requirements orchestrator's
`list` inventory verb (file/scope/last-gathered/requirement-count rows over
cortex/requirements/*.md, excluding glossary.md).
"""

from __future__ import annotations

import json

import pytest

from cortex_command.common import CortexProjectRootError
from cortex_command.lifecycle import list_requirements_cli as lr


def _write(root, name, body):
    d = root / "cortex" / "requirements"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_ok_lists_rows_excluding_glossary(tmp_path) -> None:
    _write(
        tmp_path,
        "project.md",
        "# Requirements: x\n\n> Last gathered: 2026-04-01\n\n## Overview\n\n- a\n- b\n",
    )
    _write(
        tmp_path,
        "multi-agent.md",
        "# Requirements: multi-agent\n\n> Last gathered: 2026-04-03\n\n"
        "## Overview\n\n- **x**: y\n  - nested\n- z\n",
    )
    _write(tmp_path, "glossary.md", "# Glossary\n\n## Language\n\n- **t**: d\n")

    r = lr.list_requirements(project_root=tmp_path)
    assert r["state"] == "ok"
    files = [row["file"] for row in r["rows"]]
    assert files == [
        "cortex/requirements/multi-agent.md",
        "cortex/requirements/project.md",
    ]

    by_file = {row["file"]: row for row in r["rows"]}
    project_row = by_file["cortex/requirements/project.md"]
    assert project_row["scope"] == "project"
    assert project_row["last_gathered"] == "2026-04-01"
    assert project_row["requirement_count"] == 2

    area_row = by_file["cortex/requirements/multi-agent.md"]
    assert area_row["scope"] == "multi-agent"
    assert area_row["last_gathered"] == "2026-04-03"
    assert area_row["requirement_count"] == 3


def test_last_gathered_ignores_updated_suffix(tmp_path) -> None:
    _write(
        tmp_path,
        "project.md",
        "# Requirements: x\n\n> Last gathered: 2026-04-01 (updated 2026-05-12)\n\n"
        "## Overview\n",
    )
    r = lr.list_requirements(project_root=tmp_path)
    assert r["rows"][0]["last_gathered"] == "2026-04-01"


def test_missing_last_gathered_line_is_null(tmp_path) -> None:
    _write(tmp_path, "project.md", "# Requirements: x\n\n## Overview\n\n- a\n")
    r = lr.list_requirements(project_root=tmp_path)
    assert r["rows"][0]["last_gathered"] is None


def test_absent_directory_returns_absent_with_empty_rows(tmp_path) -> None:
    r = lr.list_requirements(project_root=tmp_path)
    assert r == {"state": "absent", "rows": []}


def test_requirements_dir_arg_takes_precedence_over_project_root(tmp_path) -> None:
    _write(tmp_path, "project.md", "# Requirements: x\n\n## Overview\n\n- a\n")
    explicit_dir = tmp_path / "cortex" / "requirements"
    # project_root points somewhere with no cortex/requirements — proves the
    # explicit dir wins and no project-root resolution is attempted.
    r = lr.list_requirements(
        requirements_dir=explicit_dir, project_root=tmp_path / "elsewhere"
    )
    assert r["state"] == "ok"
    assert len(r["rows"]) == 1


def test_project_root_error_returns_state_not_traceback(monkeypatch) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(lr, "_resolve_user_project_root_from_cwd", _raise)
    r = lr.list_requirements()
    assert r["state"] == "project-root-error"
    assert "no cortex/ found" in r["message"]


def test_every_state_is_known(tmp_path) -> None:
    seen = set()
    seen.add(lr.list_requirements(project_root=tmp_path)["state"])  # absent
    _write(tmp_path, "project.md", "# Requirements: x\n\n## Overview\n")
    seen.add(lr.list_requirements(project_root=tmp_path)["state"])  # ok
    assert seen <= set(lr.KNOWN_STATES)
    assert seen == {"absent", "ok"}


def test_cli_emits_json(monkeypatch, tmp_path, capsys) -> None:
    _write(tmp_path, "project.md", "# Requirements: x\n\n## Overview\n\n- a\n")
    rc = lr.main(["--project-root", str(tmp_path)])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert len(obj["rows"]) == 1


def test_cli_requirements_dir_flag(tmp_path, capsys) -> None:
    _write(tmp_path, "project.md", "# Requirements: x\n\n## Overview\n\n- a\n")
    rc = lr.main(
        ["--requirements-dir", str(tmp_path / "cortex" / "requirements")]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert len(obj["rows"]) == 1


def test_cli_never_raises_and_always_exits_zero(monkeypatch, capsys) -> None:
    def _raise():
        raise CortexProjectRootError("no cortex/ found")

    monkeypatch.setattr(lr, "_resolve_user_project_root_from_cwd", _raise)
    rc = lr.main([])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "project-root-error"
