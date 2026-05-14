"""Precedence-pin test for `auth.ensure_sdk_auth`.

Pins the existing 5-vector resolution chain in
`cortex_command.overnight.auth.ensure_sdk_auth` (documented in
`auth.py:398-468`): a configured-and-working ``apiKeyHelper`` MUST resolve
before the ``personal-oauth-token`` file. This guards against a future change
where the addition of a `cortex auth bootstrap`-minted oauth file
inadvertently flips the precedence and silently overrides per-repo
``apiKeyHelper`` configuration.

Mirrors the apiKeyHelper fixture pattern in `tests/test_runner_auth.py`:
a tiny shell script in a tmp dir that prints an API key on stdout, referenced
by the settings.local.json ``apiKeyHelper`` key.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
from pathlib import Path

import pytest

from cortex_command.overnight.auth import ensure_sdk_auth


def test_apikeyhelper_overrides_oauth_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A working ``apiKeyHelper`` wins over a present ``personal-oauth-token``.

    Both vectors are configured simultaneously:
      * ``~/.claude/settings.local.json`` references a helper script that
        prints a valid-looking API key to stdout.
      * ``~/.claude/personal-oauth-token`` contains a valid-looking OAuth
        token.

    Expectation per `auth.py:ensure_sdk_auth` precedence chain (vector 3
    ``api_key_helper`` resolves before vector 4 ``oauth_file``):
      * returned ``vector == "api_key_helper"``
      * ``ANTHROPIC_API_KEY`` is set in ``os.environ``
      * ``CLAUDE_CODE_OAUTH_TOKEN`` is NOT set by this call
    """
    # Scrub every auth env var that could short-circuit the chain ahead of
    # the apiKeyHelper branch (auth_token / env_preexisting / oauth env).
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    # Redirect Path.home() — auth.py's only home-lookup API — so both
    # settings.local.json and personal-oauth-token resolve under tmp_path.
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    # 1. Configure a working apiKeyHelper via settings.local.json.
    helper_path = tmp_path / "helper.sh"
    helper_path.write_text(
        "#!/bin/sh\nprintf 'sk-test-precedence-api-key'\n", encoding="utf-8"
    )
    helper_path.chmod(
        helper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    settings_local = claude_dir / "settings.local.json"
    settings_local.write_text(
        json.dumps({"apiKeyHelper": str(helper_path)}), encoding="utf-8"
    )

    # 2. Place a valid-looking OAuth token file alongside it.
    oauth_file = claude_dir / "personal-oauth-token"
    oauth_file.write_text(
        "sk-ant-oat01-test-precedence-oauth-token\n", encoding="utf-8"
    )

    result = ensure_sdk_auth(event_log_path=None)

    # Precedence: api_key_helper (vector 3) wins over oauth_file (vector 4).
    assert result["vector"] == "api_key_helper", (
        f"expected api_key_helper to win, got {result['vector']!r}; "
        f"message={result.get('message')!r}"
    )
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-test-precedence-api-key"
    # The oauth env var must NOT be set by this call — that would indicate
    # the oauth_file branch ran (and clobbered the api_key_helper outcome).
    assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") is None
