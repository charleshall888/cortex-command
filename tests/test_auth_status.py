"""Unit tests for ``cortex_command.auth.status.run``.

Covers the four sub-cases documented in
``cortex/lifecycle/restore-subscription-auth-for-autonomous-worktree/spec.md``
Requirement 8 plus a fifth test pinning ``_HelperInternalError`` propagation
(Edge Cases entry):

  (a) ``test_status_oauth_file_only`` — only ``~/.claude/personal-oauth-token``
      present; ``vector: oauth_file`` + matching source label, no
      ``shadowed:`` line.
  (b) ``test_status_env_shadows_file`` — ``CLAUDE_CODE_OAUTH_TOKEN``
      exported AND token file present; ``vector: env_preexisting`` AND a
      ``shadowed: personal-oauth-token file`` line.
  (c) ``test_status_vector_none_remediation`` — nothing set; ``vector: none``
      AND a remediation line containing ``cortex auth bootstrap``.
  (d) ``test_status_no_secrets_in_output`` — any non-none vector with a real
      token value; ``"sk-ant-"`` substring is NOT in captured stdout.
  (e) ``test_status_malformed_apikeyhelper_propagates`` — malformed
      ``settings.json`` triggers ``_HelperInternalError``; the handler does
      not swallow the exception (status surfaces a non-zero exit, with the
      error visible).

Each test follows the same harness pattern as ``tests/test_runner_auth.py``
and ``tests/test_auth_precedence.py``: ``monkeypatch.setattr(pathlib.Path,
"home", lambda: tmp_path)`` redirects the home lookup, and
``monkeypatch.delenv`` scrubs auth env vars that could short-circuit the
chain.
"""

from __future__ import annotations

import argparse
import pathlib
from pathlib import Path

import pytest

from cortex_command.auth import status as status_mod
from cortex_command.overnight.auth import _HelperInternalError


# ---------------------------------------------------------------------------
# Fixture helpers (mirror tests/test_runner_auth.py / test_auth_precedence.py)
# ---------------------------------------------------------------------------


def _scrub_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip all auth env vars that could short-circuit ``ensure_sdk_auth``."""
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point ``pathlib.Path.home()`` at ``home`` (auth.py's only home API)."""
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)


def _write_oauth_file(home: Path, token: str) -> Path:
    """Create ``~/.claude/personal-oauth-token`` containing ``token``."""
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    token_file = claude_dir / "personal-oauth-token"
    token_file.write_text(f"{token}\n", encoding="utf-8")
    return token_file


def _empty_namespace() -> argparse.Namespace:
    """Minimal argparse.Namespace — status.run() ignores its args."""
    return argparse.Namespace()


# ---------------------------------------------------------------------------
# (a) Only ``~/.claude/personal-oauth-token`` present
# ---------------------------------------------------------------------------


def test_status_oauth_file_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """vector=oauth_file, source points at the token path, no shadowing."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _write_oauth_file(tmp_path, "sk-ant-oat01-only-oauth-file-fixture-token")

    rc = status_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    assert "vector: oauth_file" in captured.out
    assert "source: ~/.claude/personal-oauth-token" in captured.out
    # No higher-precedence source is present, so nothing can shadow oauth_file.
    assert "shadowed:" not in captured.out


# ---------------------------------------------------------------------------
# (b) CLAUDE_CODE_OAUTH_TOKEN env shadows the personal-oauth-token file
# ---------------------------------------------------------------------------


def test_status_env_shadows_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """env CLAUDE_CODE_OAUTH_TOKEN wins; file is reported as shadowed."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _write_oauth_file(tmp_path, "sk-ant-oat01-shadowed-file-fixture-token")
    monkeypatch.setenv(
        "CLAUDE_CODE_OAUTH_TOKEN",
        "sk-ant-oat01-env-preexisting-fixture-token",
    )

    rc = status_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    assert "vector: env_preexisting" in captured.out
    assert "shadowed: personal-oauth-token file" in captured.out


# ---------------------------------------------------------------------------
# (c) Nothing set — vector: none + remediation line
# ---------------------------------------------------------------------------


def test_status_vector_none_remediation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No env vars, no settings, no oauth file — vector=none, remediation shown."""
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    # Intentionally no settings.json, no personal-oauth-token file.

    rc = status_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    assert "vector: none" in captured.out
    assert "cortex auth bootstrap" in captured.out


# ---------------------------------------------------------------------------
# (d) No secrets in output — token never appears in stdout
# ---------------------------------------------------------------------------


def test_status_no_secrets_in_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A real ``sk-ant-`` token resolved as oauth_file MUST NOT leak to stdout.

    Mirrors the spec acceptance check ``! cortex auth status | grep -q sk-ant``.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)
    _write_oauth_file(
        tmp_path,
        "sk-ant-oat01-must-not-appear-in-stdout-fixture-token",
    )

    rc = status_mod.run(_empty_namespace())
    captured = capsys.readouterr()

    assert rc == 0
    # Sanity: vector resolved to a non-none vector.
    assert "vector: oauth_file" in captured.out
    # Critical: the actual token (or any sk-ant- substring) is absent.
    assert "sk-ant-" not in captured.out


# ---------------------------------------------------------------------------
# (e) Malformed apiKeyHelper — _HelperInternalError must propagate
# ---------------------------------------------------------------------------


def test_status_malformed_apikeyhelper_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The status handler MUST NOT swallow ``_HelperInternalError``.

    A malformed ``~/.claude/settings.json`` causes ``_read_api_key_helper``
    to raise ``_HelperInternalError`` (see
    ``cortex_command/overnight/auth.py:_read_api_key_helper``). The status
    handler invokes ``ensure_sdk_auth`` directly, so the exception MUST
    propagate out of ``status.run`` — the CLI dispatcher then translates it
    into a non-zero exit. We assert on the raised exception here (the
    immediate, observable error surface) rather than going through the CLI
    layer.
    """
    _scrub_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    # Truncated JSON — json.loads raises JSONDecodeError, which auth.py wraps
    # in _HelperInternalError per the spec's Edge Cases table.
    (claude_dir / "settings.json").write_text(
        '{"apiKeyHelper": "foo"', encoding="utf-8"
    )

    with pytest.raises(_HelperInternalError):
        status_mod.run(_empty_namespace())
