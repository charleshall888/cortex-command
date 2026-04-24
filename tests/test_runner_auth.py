"""Regression tests for the auth resolution that runner.py delegates to.

Replaces the legacy `tests/test_runner_auth.sh`, which extracted the auth block
verbatim from `runner.sh` and stubbed `python3` on PATH to exercise its three
exit-code branches. Post-R6/R7 the auth block lives in
`cortex_command.overnight.auth`, so these tests call the Python entry points
directly rather than spawning a subshell.

Covers the three behavioral scenarios of the original bash suite:

  1. success path — apiKeyHelper resolves a token and
     `resolve_auth_for_shell()` prints an `export ANTHROPIC_API_KEY=...`
     line on stdout, returning exit 0.
  2. no-vector path — empty home with no settings.json and no oauth file,
     `resolve_auth_for_shell()` returns exit 1 and prints nothing on stdout.
  3. helper-internal failure path — malformed `~/.claude/settings.json`
     surfaces as `_HelperInternalError`; `resolve_auth_for_shell()` returns
     exit 2 and emits the "auth helper internal failure" message on stderr.

Also asserts the ANTHROPIC_API_KEY env-var precedence short-circuit specified
in the task context (pre-existing env var wins over settings.json).

The existing `cortex_command/overnight/tests/test_auth.py` suite covers the
same exit-code table as part of the R2 contract; this file is retained in
`tests/` so the top-level runner-auth test name survives the migration and
ensures `grep -rn 'runner_auth' tests/` still returns a hit for devs auditing
the migration.
"""

from __future__ import annotations

import json
import pathlib
import stat
from pathlib import Path

import pytest

from cortex_command.overnight.auth import resolve_auth_for_shell


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip auth env vars so prior-process state cannot leak into a test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point `pathlib.Path.home()` at `home` (auth.py's only home-lookup API)."""
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)


def _write_settings_with_helper(home: Path, helper_cmd: str) -> Path:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings = claude_dir / "settings.json"
    settings.write_text(json.dumps({"apiKeyHelper": helper_cmd}), encoding="utf-8")
    return settings


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------------------------------------------------------------------------
# Scenario 1 — success path via apiKeyHelper
# ---------------------------------------------------------------------------


def test_api_key_helper_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """apiKeyHelper returning a token produces exit 0 and an `export` line on stdout."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    helper_path = tmp_path / "helper.sh"
    _write_executable(
        helper_path,
        "#!/bin/sh\nprintf 'sk-test-runner-auth-token'\n",
    )
    _write_settings_with_helper(tmp_path, str(helper_path))

    rc = resolve_auth_for_shell()

    captured = capsys.readouterr()
    assert rc == 0
    assert "export ANTHROPIC_API_KEY=" in captured.out
    assert "sk-test-runner-auth-token" in captured.out


# ---------------------------------------------------------------------------
# Scenario 2 — no-vector (missing settings.json AND missing oauth file)
# ---------------------------------------------------------------------------


def test_no_vector_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty fixture home (no settings.json, no oauth file) returns exit 1."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    rc = resolve_auth_for_shell()

    captured = capsys.readouterr()
    assert rc == 1
    # No `export` line should be printed on the no-vector branch.
    assert "export " not in captured.out
    # Stderr carries the warning message.
    assert captured.err.strip() != ""


# ---------------------------------------------------------------------------
# Scenario 3 — helper-internal failure via malformed settings.json
# ---------------------------------------------------------------------------


def test_helper_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed `~/.claude/settings.json` surfaces as exit 2 with a stderr marker."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    # Truncated JSON — json.loads raises JSONDecodeError, which auth.py wraps
    # in _HelperInternalError and maps to exit 2.
    (claude_dir / "settings.json").write_text(
        '{"apiKeyHelper": "foo"', encoding="utf-8"
    )

    rc = resolve_auth_for_shell()

    captured = capsys.readouterr()
    assert rc == 2
    assert "auth helper internal failure" in captured.err


# ---------------------------------------------------------------------------
# Precedence — pre-existing ANTHROPIC_API_KEY wins over any settings.json
# ---------------------------------------------------------------------------


def test_env_api_key_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pre-existing ANTHROPIC_API_KEY short-circuits the settings.json read."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    # Plant a helper that would succeed if reached — precedence must skip it.
    helper_path = tmp_path / "helper.sh"
    _write_executable(
        helper_path,
        "#!/bin/sh\nprintf 'sk-from-helper-not-env'\n",
    )
    _write_settings_with_helper(tmp_path, str(helper_path))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env-preexisting")

    rc = resolve_auth_for_shell()

    captured = capsys.readouterr()
    assert rc == 0
    # Pre-existing branch does not emit an `export` line — the var is already
    # set in the parent shell. Stderr carries the "Using pre-existing" notice.
    assert "export " not in captured.out
    assert "Using pre-existing ANTHROPIC_API_KEY" in captured.err
