"""Tests for the operator ``claude`` CLI resolver (ADR-0038, #313)."""

from __future__ import annotations

import pytest

from cortex_command import cli_resolver


@pytest.fixture(autouse=True)
def _clean_resolver_state(monkeypatch):
    """Reset the memo and clear the env override before every test."""
    monkeypatch.delenv(cli_resolver._ENV_OVERRIDE, raising=False)
    cli_resolver._reset_cli_cache()
    yield
    cli_resolver._reset_cli_cache()


def _patch_discovery(monkeypatch, system):
    """Patch the system-path finder deterministically."""
    monkeypatch.setattr(cli_resolver, "_find_system_cli_path", lambda: system)


def test_env_override_returned_verbatim(monkeypatch):
    monkeypatch.setenv(cli_resolver._ENV_OVERRIDE, "/override/claude")
    # Even with discovery that would pick something else, the override wins.
    _patch_discovery(monkeypatch, system="/sys/claude")
    assert cli_resolver.resolve_claude_cli() == "/override/claude"


def test_empty_env_override_does_not_short_circuit(monkeypatch):
    monkeypatch.setenv(cli_resolver._ENV_OVERRIDE, "")
    _patch_discovery(monkeypatch, system="/sys/claude")
    assert cli_resolver.resolve_claude_cli() == "/sys/claude"


def test_neither_found_returns_none(monkeypatch):
    _patch_discovery(monkeypatch, system=None)
    assert cli_resolver.resolve_claude_cli() is None


def test_result_is_memoized(monkeypatch):
    calls = {"system": 0}

    def _counting_system():
        calls["system"] += 1
        return "/sys/claude"

    monkeypatch.setattr(cli_resolver, "_find_system_cli_path", _counting_system)

    first = cli_resolver.resolve_claude_cli()
    second = cli_resolver.resolve_claude_cli()
    assert first == second == "/sys/claude"
    # Second call returns the cached value without recomputing.
    assert calls["system"] == 1


def test_non_path_fallback_used_when_not_on_path(monkeypatch, tmp_path):
    """#313/R19: a ``claude`` off ``PATH`` under ``~/.local/bin`` still resolves
    (e.g. a Dock-launched session that inherits launchd's minimal ``PATH``)."""
    empty_path_dir = tmp_path / "empty-path"
    empty_path_dir.mkdir()
    fake_home = tmp_path / "home"
    local_bin = fake_home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    fake_claude = local_bin / "claude"
    fake_claude.write_text("#!/bin/sh\necho fake claude\n")
    fake_claude.chmod(0o755)

    monkeypatch.setenv("PATH", str(empty_path_dir))
    monkeypatch.setenv("HOME", str(fake_home))

    assert cli_resolver.resolve_claude_cli() == str(fake_claude)


@pytest.mark.parametrize(
    "output,expected",
    [
        ("2.1.186 (Claude Code)", (2, 1, 186)),
        ("2.1.69 (Claude Code)", (2, 1, 69)),
        ("  2.1.186\n", (2, 1, 186)),
        ("2.1.186-beta (Claude Code)", (2, 1, 186)),
        ("", None),
        ("garbage", None),
        ("(Claude Code) 2.1.186", None),
    ],
)
def test_parse_cli_version(output, expected):
    assert cli_resolver._parse_cli_version(output) == expected
