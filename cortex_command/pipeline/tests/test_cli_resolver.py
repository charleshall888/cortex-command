"""Tests for the best-available ``claude`` CLI resolver (ADR-0014, #313)."""

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


def _patch_discovery(monkeypatch, system, bundled, versions):
    """Patch the path finders and the version probe deterministically.

    ``versions`` maps a path -> version tuple (or ``None`` to simulate a probe
    flake). A path absent from ``versions`` probes as ``None``.
    """
    monkeypatch.setattr(cli_resolver, "_find_system_cli_path", lambda: system)
    monkeypatch.setattr(cli_resolver, "_find_bundled_cli_path", lambda: bundled)
    monkeypatch.setattr(
        cli_resolver, "_probe_version", lambda path: versions.get(path)
    )


def test_system_newer_than_bundled_returns_system(monkeypatch):
    _patch_discovery(
        monkeypatch,
        system="/sys/claude",
        bundled="/bun/claude",
        versions={"/sys/claude": (2, 1, 186), "/bun/claude": (2, 1, 69)},
    )
    assert cli_resolver.resolve_claude_cli() == "/sys/claude"


def test_system_older_than_bundled_returns_bundled(monkeypatch):
    _patch_discovery(
        monkeypatch,
        system="/sys/claude",
        bundled="/bun/claude",
        versions={"/sys/claude": (2, 1, 50), "/bun/claude": (2, 1, 69)},
    )
    assert cli_resolver.resolve_claude_cli() == "/bun/claude"


def test_system_absent_returns_bundled(monkeypatch):
    _patch_discovery(
        monkeypatch,
        system=None,
        bundled="/bun/claude",
        versions={},
    )
    assert cli_resolver.resolve_claude_cli() == "/bun/claude"


def test_env_override_returned_verbatim(monkeypatch):
    monkeypatch.setenv(cli_resolver._ENV_OVERRIDE, "/override/claude")
    # Even with discovery that would pick something else, the override wins.
    _patch_discovery(
        monkeypatch,
        system="/sys/claude",
        bundled="/bun/claude",
        versions={"/sys/claude": (2, 1, 186), "/bun/claude": (2, 1, 69)},
    )
    assert cli_resolver.resolve_claude_cli() == "/override/claude"


def test_empty_env_override_does_not_short_circuit(monkeypatch):
    monkeypatch.setenv(cli_resolver._ENV_OVERRIDE, "")
    _patch_discovery(
        monkeypatch,
        system="/sys/claude",
        bundled=None,
        versions={},
    )
    assert cli_resolver.resolve_claude_cli() == "/sys/claude"


def test_neither_found_returns_none(monkeypatch):
    _patch_discovery(monkeypatch, system=None, bundled=None, versions={})
    assert cli_resolver.resolve_claude_cli() is None


def test_result_is_memoized(monkeypatch):
    calls = {"system": 0}

    def _counting_system():
        calls["system"] += 1
        return "/sys/claude"

    monkeypatch.setattr(cli_resolver, "_find_system_cli_path", _counting_system)
    monkeypatch.setattr(cli_resolver, "_find_bundled_cli_path", lambda: None)
    monkeypatch.setattr(cli_resolver, "_probe_version", lambda path: (2, 1, 186))

    first = cli_resolver.resolve_claude_cli()
    second = cli_resolver.resolve_claude_cli()
    assert first == second == "/sys/claude"
    # Second call returns the cached value without recomputing.
    assert calls["system"] == 1


def test_probe_flake_prefers_system_and_does_not_memoize(monkeypatch):
    """#313-regression guard: a system-CLI probe flake must NOT fall back to the
    stale bundle, and the indeterminate result must not be memoized."""
    calls = {"compute": 0}
    real_compute = cli_resolver._compute_best_cli

    def _counting_compute():
        calls["compute"] += 1
        return real_compute()

    monkeypatch.setattr(cli_resolver, "_compute_best_cli", _counting_compute)
    _patch_discovery(
        monkeypatch,
        system="/sys/claude",
        bundled="/bun/claude",
        # System version unparseable (None) — a timeout/parse flake.
        versions={"/sys/claude": None, "/bun/claude": (2, 1, 69)},
    )

    first = cli_resolver.resolve_claude_cli()
    second = cli_resolver.resolve_claude_cli()
    # Prefers the present system CLI, never the stale bundle.
    assert first == "/sys/claude"
    assert second == "/sys/claude"
    # Not memoized: a transient flake must not pin the choice — recomputed.
    assert calls["compute"] == 2


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
