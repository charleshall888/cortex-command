"""Tests for cortex-morning-review-resolve-demo-config — the morning-review
walkthrough §2a Guard 1 demo-config parsing façade (demo-commands list vs.
demo-command single-string fallback, entry validation).

``resolve_demo_config()`` is a pure function of a file path — no composed
primitives to monkeypatch, so these tests drive it directly against
synthetic ``lifecycle.config.md``-shaped fixtures in ``tmp_path``, following
the ``test_prepare_worktree.py``/``test_record_pr_opened.py`` precedent of
pinning the discriminated ``state`` + payload for every branch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight import resolve_demo_config as rdc


def _write_config(tmp_path: Path, frontmatter_body: str) -> Path:
    path = tmp_path / "lifecycle.config.md"
    path.write_text(f"---\n{frontmatter_body}\n---\n\n# Lifecycle Configuration\n")
    return path


def test_missing_file_is_none(tmp_path: Path) -> None:
    r = rdc.resolve_demo_config(tmp_path / "does-not-exist.md")
    assert r == {"state": "none", "entries": []}


def test_no_frontmatter_delimiters_is_none(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.config.md"
    path.write_text("# Lifecycle Configuration\n\nNo frontmatter here.\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"


def test_frontmatter_with_neither_key_is_none(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "type: other\ntest-command: just test")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"


def test_demo_commands_list_single_valid_entry(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        'demo-commands:\n  - label: "Dashboard"\n    command: "just dashboard"',
    )
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "list"
    assert r["entries"] == [
        {"path": "list", "label": "Dashboard", "command": "just dashboard"}
    ]


def test_demo_commands_list_multiple_valid_entries_preserve_order(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        "demo-commands:\n"
        '  - label: "Dashboard"\n'
        '    command: "just dashboard"\n'
        '  - label: "Godot"\n'
        '    command: "godot res://main.tscn"',
    )
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "list"
    assert [e["command"] for e in r["entries"]] == ["just dashboard", "godot res://main.tscn"]


def test_demo_commands_list_discards_empty_command(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        "demo-commands:\n"
        '  - label: "Empty"\n'
        '    command: ""\n'
        '  - label: "Dashboard"\n'
        '    command: "just dashboard"',
    )
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "list"
    assert len(r["entries"]) == 1
    assert r["entries"][0]["label"] == "Dashboard"


def test_demo_commands_list_discards_whitespace_only_command(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        "demo-commands:\n"
        '  - label: "Blank"\n'
        '    command: "   "\n'
        '  - label: "Dashboard"\n'
        '    command: "just dashboard"',
    )
    r = rdc.resolve_demo_config(path)
    assert len(r["entries"]) == 1
    assert r["entries"][0]["label"] == "Dashboard"


def test_demo_commands_list_discards_control_character_command(tmp_path: Path) -> None:
    """A raw control byte (e.g. NUL) inside command: must reject the entry."""
    entries = [
        {"label": "Bad", "command": "just\x07dashboard"},
        {"label": "Dashboard", "command": "just dashboard"},
    ]
    # Build the file directly via yaml.dump to avoid hand-quoting control bytes.
    import yaml as _yaml

    path = tmp_path / "lifecycle.config.md"
    body = _yaml.safe_dump({"demo-commands": entries})
    path.write_text(f"---\n{body}---\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "list"
    assert len(r["entries"]) == 1
    assert r["entries"][0]["label"] == "Dashboard"


def test_demo_commands_list_allows_tab_in_command(tmp_path: Path) -> None:
    """Tab (0x09) is the one allowed control character."""
    import yaml as _yaml

    entries = [{"label": "Tabbed", "command": "just\tdashboard"}]
    path = tmp_path / "lifecycle.config.md"
    body = _yaml.safe_dump({"demo-commands": entries})
    path.write_text(f"---\n{body}---\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "list"
    assert r["entries"] == [{"path": "list", "label": "Tabbed", "command": "just\tdashboard"}]


def test_demo_commands_list_zero_valid_entries_falls_back_to_single(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        "demo-commands:\n"
        '  - label: "Empty"\n'
        '    command: ""\n'
        'demo-command: "just dashboard"',
    )
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "single"
    assert r["entries"] == [{"path": "single", "command": "just dashboard"}]


def test_demo_command_single_string_only(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'demo-command: "just dashboard"')
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "single"
    assert r["entries"] == [{"path": "single", "command": "just dashboard"}]


def test_demo_command_trims_whitespace(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'demo-command: "  just dashboard  "')
    r = rdc.resolve_demo_config(path)
    assert r["entries"][0]["command"] == "just dashboard"


def test_demo_command_empty_is_none(tmp_path: Path) -> None:
    path = _write_config(tmp_path, 'demo-command: ""')
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"


def test_demo_command_control_character_is_none(tmp_path: Path) -> None:
    import yaml as _yaml

    body = _yaml.safe_dump({"demo-command": "just\x07dashboard"})
    path = tmp_path / "lifecycle.config.md"
    path.write_text(f"---\n{body}---\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"


def test_malformed_yaml_is_none_with_stderr_warning(tmp_path: Path, capsys) -> None:
    path = tmp_path / "lifecycle.config.md"
    path.write_text("---\ndemo-commands: [unclosed\n---\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"
    err = capsys.readouterr().err
    assert "failed to parse YAML frontmatter" in err


def test_frontmatter_not_a_mapping_is_none(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.config.md"
    path.write_text("---\n- just\n- a\n- list\n---\n")
    r = rdc.resolve_demo_config(path)
    assert r["state"] == "none"


def test_every_state_is_known(tmp_path: Path) -> None:
    seen = set()
    seen.add(rdc.resolve_demo_config(tmp_path / "missing.md")["state"])
    seen.add(
        rdc.resolve_demo_config(_write_config(tmp_path, 'demo-command: "just dashboard"'))[
            "state"
        ]
    )
    seen.add(
        rdc.resolve_demo_config(
            _write_config(
                tmp_path,
                'demo-commands:\n  - label: "D"\n    command: "just dashboard"',
            )
        )["state"]
    )
    assert seen <= set(rdc.KNOWN_STATES)
    assert seen == {"none", "single", "list"}


def test_cli_emits_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    cortex_dir = tmp_path / "cortex"
    cortex_dir.mkdir()
    _write_config(cortex_dir, 'demo-command: "just dashboard"')
    monkeypatch.setattr(rdc, "_resolve_user_project_root_from_cwd", lambda: tmp_path)
    rc = rdc.main([])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "single"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def _boom():
        raise RuntimeError("no project root")

    monkeypatch.setattr(rdc, "_resolve_user_project_root_from_cwd", _boom)
    rc = rdc.main([])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "no project root" in obj["message"]
