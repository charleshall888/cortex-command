"""Unit tests for cortex_command.overnight.auth.

Exercises the Task 1 contract:
  * R1 — vector resolution across all four branches.
  * R2 — three exit codes for the shell entry point.
  * R3 — stdlib-only regression guard via an isolated subprocess.
  * R7 — ``sk-ant-*`` redaction and byte-equivalence with ``log_event``.
  * R8 — ``os.environ`` write on resolution.
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.overnight import auth
from cortex_command.overnight.auth import ensure_sdk_auth, resolve_auth_for_shell
from cortex_command.pipeline import state as pipeline_state


REPO_ROOT = str(Path(__file__).resolve().parents[3])


# ---------------------------------------------------------------------------
# Shared helper: wipe auth env vars so prior-test state cannot leak.
# ---------------------------------------------------------------------------


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)


def _redirect_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Redirect ``pathlib.Path.home()`` to ``home`` for the duration of a test.

    Task 1 pins ``pathlib.Path.home()`` as the only home-lookup API in auth.py,
    so this monkeypatch is sufficient to sandbox filesystem reads into tmp_path.
    """
    monkeypatch.setattr(pathlib.Path, "home", lambda: home)


def _write_settings_with_helper(home: Path, helper_cmd: str) -> Path:
    """Drop a ``~/.claude/settings.json`` with an apiKeyHelper pointing at ``helper_cmd``."""
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings = claude_dir / "settings.json"
    settings.write_text(json.dumps({"apiKeyHelper": helper_cmd}), encoding="utf-8")
    return settings


def _write_executable(path: Path, body: str) -> Path:
    """Write an executable script at ``path`` containing ``body`` (chmod +x)."""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _write_oauth_file(home: Path, token: str) -> Path:
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    oauth = claude_dir / "personal-oauth-token"
    oauth.write_text(token + "\n", encoding="utf-8")
    return oauth


# ---------------------------------------------------------------------------
# R1 — vector resolution across all four branches.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    ["env_preexisting", "api_key_helper", "oauth_file", "none"],
)
def test_vector_resolution(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ensure_sdk_auth resolves the correct vector for each of the four branches."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    if case == "env_preexisting":
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-preexisting-abc123")
        expected_vector = "env_preexisting"
    elif case == "api_key_helper":
        helper_path = tmp_path / "fake-helper.sh"
        _write_executable(
            helper_path,
            "#!/bin/sh\nprintf 'sk-ant-helper-token-xyz'\n",
        )
        _write_settings_with_helper(tmp_path, str(helper_path))
        expected_vector = "api_key_helper"
    elif case == "oauth_file":
        _write_oauth_file(tmp_path, "oauth-token-fixture-value")
        expected_vector = "oauth_file"
    elif case == "none":
        # No env vars, no settings.json, no oauth file — tmp_path HOME is empty.
        expected_vector = "none"
    else:  # pragma: no cover — parametrize guards this.
        raise AssertionError(f"unknown case: {case}")

    result = ensure_sdk_auth(event_log_path=tmp_path / "events.log")

    assert result["vector"] == expected_vector


# ---------------------------------------------------------------------------
# R1 (auth_token extension) — ANTHROPIC_AUTH_TOKEN vector env-shape and
# resolution-precedence cases.
# ---------------------------------------------------------------------------


def test_auth_token_vector(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ANTHROPIC_AUTH_TOKEN resolves to vector='auth_token' and takes priority over ANTHROPIC_API_KEY."""
    _clear_auth_env(monkeypatch)
    _redirect_home(monkeypatch, tmp_path)

    # --- Case 1: env-shape — ANTHROPIC_AUTH_TOKEN set alone resolves to auth_token.
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "some-auth-token-value")
    result = ensure_sdk_auth(event_log_path=tmp_path / "events-auth-token.log")
    assert result["vector"] == "auth_token", (
        f"expected vector='auth_token', got {result['vector']!r}"
    )

    # --- Case 2: resolution-precedence — ANTHROPIC_AUTH_TOKEN beats ANTHROPIC_API_KEY.
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "auth-token-should-win")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key-should-lose")
    result = ensure_sdk_auth(event_log_path=tmp_path / "events-precedence.log")
    assert result["vector"] == "auth_token", (
        f"expected ANTHROPIC_AUTH_TOKEN to take precedence, got vector={result['vector']!r}"
    )


# ---------------------------------------------------------------------------
# R2 — three exit codes for the shell entry point.
# ---------------------------------------------------------------------------


def test_shell_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """resolve_auth_for_shell returns 0 (resolved), 1 (no-vector), 2 (helper-internal)."""
    # --- Case 1: resolved (exit 0) via an oauth-file fixture. -----------------
    _clear_auth_env(monkeypatch)
    home_resolved = tmp_path / "home-resolved"
    home_resolved.mkdir()
    _write_oauth_file(home_resolved, "resolved-oauth-token")
    _redirect_home(monkeypatch, home_resolved)
    assert resolve_auth_for_shell() == 0

    # --- Case 2: no-vector (exit 1) with an empty fixture home. --------------
    _clear_auth_env(monkeypatch)
    home_empty = tmp_path / "home-empty"
    home_empty.mkdir()
    _redirect_home(monkeypatch, home_empty)
    assert resolve_auth_for_shell() == 1

    # --- Case 3: helper-internal failure (exit 2) via malformed settings.json.
    _clear_auth_env(monkeypatch)
    home_broken = tmp_path / "home-broken"
    (home_broken / ".claude").mkdir(parents=True)
    (home_broken / ".claude" / "settings.json").write_text(
        '{"apiKeyHelper": "foo"',  # truncated — JSONDecodeError on read
        encoding="utf-8",
    )
    _redirect_home(monkeypatch, home_broken)
    # Extra belt-and-braces: monkey-patch json.loads to raise JSONDecodeError
    # on any settings.json read path so the test is robust to read_text quirks.
    # monkeypatch auto-reverts at teardown; no try/finally needed.
    def _fake_loads(s, *args, **kwargs):  # noqa: ANN001
        raise json.JSONDecodeError("forced", s if isinstance(s, str) else "", 0)

    monkeypatch.setattr("cortex_command.overnight.auth.json.loads", _fake_loads)
    assert resolve_auth_for_shell() == 2


# ---------------------------------------------------------------------------
# R3 — stdlib-only regression guard.
# ---------------------------------------------------------------------------


def test_stdlib_only(tmp_path: Path) -> None:
    """Importing and invoking auth in Python isolated mode must not crash on non-stdlib imports.

    Runs ``python3 -I`` with ``PYTHONPATH=REPO_ROOT`` and a ``HOME`` that contains
    neither ``.claude/settings.json`` nor ``.claude/personal-oauth-token``.
    Deterministically hits the no-vector branch → exit 1. Exit 1 from an
    ImportError also exists, so we additionally assert stderr contains no
    ``ImportError`` / ``ModuleNotFoundError`` markers.
    """
    # python3 -I scrubs PYTHONPATH, so the subprocess must inject REPO_ROOT
    # onto sys.path itself. This matches the spec's R3 command shape:
    #   python3 -I -c "import sys; sys.path.insert(0, REPO_ROOT); ..."
    code = (
        f"import sys\n"
        f"sys.path.insert(0, {REPO_ROOT!r})\n"
        f"from cortex_command.overnight import auth\n"
        f"raise SystemExit(auth.resolve_auth_for_shell())\n"
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "PYTHONPATH": REPO_ROOT,
    }
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        env=env,
        capture_output=True,
    )
    assert proc.returncode == 1, (
        f"expected rc=1 from no-vector resolution, got {proc.returncode}; "
        f"stderr={proc.stderr!r}"
    )
    assert b"ImportError" not in proc.stderr
    assert b"ModuleNotFoundError" not in proc.stderr


# ---------------------------------------------------------------------------
# R7 — sk-ant-* redaction and byte-equivalence with log_event.
# ---------------------------------------------------------------------------


def test_redaction_and_byte_equivalence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Helper output containing ``sk-ant-*`` is redacted; event bytes match log_event."""
    # --- (i) Redaction of sk-ant-* via the sanitizer the helper passes through.
    # ensure_sdk_auth sanitizes every user-facing message through _sanitize
    # before emission. The api_key_helper and env_preexisting branches use
    # canned messages that don't include the raw token, so we verify the
    # contract two ways: (a) a direct _sanitize unit check for the stderr-leak
    # path the spec calls out, and (b) an end-to-end invocation proving no
    # sk-ant-* substring survives in the event log.
    _clear_auth_env(monkeypatch)
    home = tmp_path / "home-redaction"
    home.mkdir()
    _redirect_home(monkeypatch, home)

    # Helper that emits a fake sk-ant key on stdout. This exercises the
    # api_key_helper branch end-to-end.
    helper_path = tmp_path / "leaky-helper.sh"
    _write_executable(
        helper_path,
        "#!/bin/sh\nprintf 'sk-ant-secret123-leaked-key'\n",
    )
    _write_settings_with_helper(home, str(helper_path))

    event_log = tmp_path / "redaction-events.log"
    result = ensure_sdk_auth(event_log_path=event_log)

    event_line = event_log.read_text(encoding="utf-8")
    # Raw sk-ant-* token must not survive into the event log.
    assert "sk-ant-secret123" not in event_line
    # The raw key is written to os.environ (unredacted) so subprocesses inherit it.
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-secret123-leaked-key"
    assert result["vector"] == "api_key_helper"

    # Direct sanitizer check for the stderr-leak path the spec's
    # R7 acceptance (i) describes ("feed a synthetic helper emitting
    # sk-ant-secret123 on stderr"):
    leaked = "helper stderr: sk-ant-secret123 crashed"
    sanitized = auth._sanitize(leaked)
    assert "sk-ant-secret123" not in sanitized
    assert "sk-ant-<redacted>" in sanitized

    # --- (ii) Byte-equivalence with log_event under a frozen clock. ----------
    _clear_auth_env(monkeypatch)

    FROZEN = "2026-04-23T12:00:00+00:00"
    monkeypatch.setattr("cortex_command.pipeline.state._now_iso", lambda: FROZEN)
    # auth.py re-exports _now_iso from cortex_command.pipeline.state at import time;
    # patch the rebound name too so _build_event uses the frozen value.
    monkeypatch.setattr("cortex_command.overnight.auth._now_iso", lambda: FROZEN)

    # Set up a minimal home where env_preexisting resolves deterministically,
    # producing a known message we can replay through log_event verbatim.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-preexisting-frozen")
    _redirect_home(monkeypatch, tmp_path / "home-frozen")

    a_log = tmp_path / "a.log"
    b_log = tmp_path / "b.log"

    res = ensure_sdk_auth(event_log_path=a_log)

    # Mirror the same payload fields through log_event. _build_event places
    # keys in order: ts, event, vector, message. log_event adds ts first then
    # updates with the rest, so we pass event/vector/message in the matching
    # order.
    synthetic_payload = {
        "event": "auth_bootstrap",
        "vector": res["vector"],
        "message": res["message"],
    }
    pipeline_state.log_event(b_log, synthetic_payload)

    assert a_log.read_bytes() == b_log.read_bytes()


# ---------------------------------------------------------------------------
# R8 — os.environ write on resolution (oauth-file branch).
# ---------------------------------------------------------------------------


def test_environ_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ensure_sdk_auth writes the resolved oauth token into os.environ."""
    _clear_auth_env(monkeypatch)
    home = tmp_path / "home-environ"
    home.mkdir()
    _redirect_home(monkeypatch, home)

    fixture_value = "oauth-fixture-token-value-xyz"
    _write_oauth_file(home, fixture_value)

    result = ensure_sdk_auth(event_log_path=tmp_path / "events.log")

    assert result["vector"] == "oauth_file"
    assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == fixture_value
