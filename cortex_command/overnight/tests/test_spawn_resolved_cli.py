"""#313 Task 3: the orchestrator spawn uses the resolved best-available CLI.

Asserts ``_spawn_orchestrator`` builds its ``subprocess.Popen`` argv with
``resolve_claude_cli()`` as ``argv[0]`` (not the bare literal ``"claude"``), and
falls back to ``"claude"`` when resolution returns ``None``.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cortex_command import cli_resolver
from cortex_command.overnight import runner as runner_module


def _invoke_spawn(tmp_path: Path, monkeypatch, resolved):
    """Drive _spawn_orchestrator with all heavy plumbing mocked; return argv."""
    monkeypatch.setattr(cli_resolver, "resolve_claude_cli", lambda: resolved)

    sb = runner_module.sandbox_settings
    monkeypatch.setattr(sb, "emit_linux_warning_if_needed", lambda: None)
    monkeypatch.setattr(sb, "build_orchestrator_deny_paths", lambda **kw: [])
    monkeypatch.setattr(sb, "read_soft_fail_env", lambda: False)
    monkeypatch.setattr(sb, "build_sandbox_settings_dict", lambda **kw: {})
    monkeypatch.setattr(
        sb, "write_settings_tempfile", lambda *a, **k: tmp_path / "settings.json"
    )
    monkeypatch.setattr(sb, "register_atexit_cleanup", lambda *a, **k: None)
    monkeypatch.setattr(
        runner_module, "_write_sandbox_deny_list_sidecar", lambda **kw: None
    )
    monkeypatch.setattr(runner_module, "WatchdogThread", MagicMock())

    captured: dict = {}

    def _fake_popen(argv, *a, **k):
        captured["argv"] = argv
        return MagicMock()

    monkeypatch.setattr(runner_module.subprocess, "Popen", _fake_popen)

    state = types.SimpleNamespace(
        project_root=str(tmp_path), integration_worktrees=[]
    )
    runner_module._spawn_orchestrator(
        filled_prompt="do the thing",
        coord=MagicMock(),
        spawned_procs=[],
        stdout_path=tmp_path / "out.ndjson",
        state=state,
        session_dir=tmp_path,
        round_num=1,
    )
    return captured["argv"]


def test_spawn_uses_resolved_cli(tmp_path, monkeypatch):
    argv = _invoke_spawn(tmp_path, monkeypatch, resolved="/best/claude")
    assert argv[0] == "/best/claude"
    # Sanity: the rest of the argv is the orchestrator invocation.
    assert "-p" in argv


def test_spawn_falls_back_to_bare_claude_when_unresolved(tmp_path, monkeypatch):
    argv = _invoke_spawn(tmp_path, monkeypatch, resolved=None)
    assert argv[0] == "claude"
