"""Unit tests for dispatch.py budget-exhausted path, rate-limit classification,
stderr accumulator integration, and per-spawn sandbox-settings tempfile wiring
(spec Reqs 5, 6, 15).

These tests use asyncio.run() inside synchronous test methods because
pytest-asyncio is not a project dependency.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Install the SDK stub before importing dispatch.
from cortex_command.tests._stubs import _install_sdk_stub
_install_sdk_stub()

import cortex_command.pipeline.dispatch as _dispatch_module  # noqa: E402

_sdk = sys.modules["claude_agent_sdk"]
ResultMessage = _sdk.ResultMessage
ProcessError = _sdk.ProcessError
ClaudeAgentOptions = _sdk.ClaudeAgentOptions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_gen(*items):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Test 1: budget-exhausted dispatch path
# ---------------------------------------------------------------------------

class TestBudgetExhaustedDispatchPath(unittest.TestCase):
    """dispatch_task returns success=False / error_type=budget_exhausted when
    ResultMessage.is_error is True with subtype error_max_budget_usd."""

    def test_budget_exhausted_returns_failure_result(self):
        async def _run():
            async def mock_query(**kwargs):
                msg = ResultMessage(
                    subtype="error_max_budget_usd",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=1,
                    session_id="sess-budget-test",
                    total_cost_usd=0.01,
                )
                async for m in _async_gen(msg):
                    yield m

            with patch("cortex_command.pipeline.dispatch.query", new=mock_query):
                return await _dispatch_module.dispatch_task(
                    feature="budget-test",
                    task="do something",
                    worktree_path=Path("/tmp"),
                    complexity="simple",
                    system_prompt="test",
                    skill="implement",
                )

        result = asyncio.run(_run())
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "budget_exhausted")


# ---------------------------------------------------------------------------
# Test 2: rate-limit classify_error
# ---------------------------------------------------------------------------

class TestRateLimitClassifyError(unittest.TestCase):
    """classify_error returns api_rate_limit when the ProcessError message
    contains a rate-limit keyword pattern."""

    def test_rate_limit_error_in_output_returns_api_rate_limit(self):
        err = ProcessError("Command failed")
        result = _dispatch_module.classify_error(err, "rate_limit_error in response")
        self.assertEqual(result, "api_rate_limit")


# ---------------------------------------------------------------------------
# Test 3: stderr accumulator integration
# ---------------------------------------------------------------------------

class TestStderrAccumulatorIntegration(unittest.TestCase):
    """dispatch_task classifies error as api_rate_limit when stderr lines
    contain a rate-limit keyword and query raises ProcessError."""

    def test_stderr_rate_limit_line_yields_api_rate_limit_error_type(self):
        async def _run():
            captured_options = {}

            # Wrap ClaudeAgentOptions to intercept the stderr callback.
            _original_cls = ClaudeAgentOptions

            class _CapturingOptions(_original_cls):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    captured_options["stderr"] = kwargs.get("stderr")

            async def mock_query(**kwargs):
                # Call the stderr callback with a rate-limit line before raising.
                stderr_cb = captured_options.get("stderr")
                if stderr_cb is not None:
                    stderr_cb("rate limit error received from API")
                raise ProcessError("Command failed")
                # Make this an async generator (required yield for the type).
                yield  # pragma: no cover  -- never reached

            with patch("cortex_command.pipeline.dispatch.ClaudeAgentOptions", new=_CapturingOptions):
                with patch("cortex_command.pipeline.dispatch.query", new=mock_query):
                    return await _dispatch_module.dispatch_task(
                        feature="stderr-test",
                        task="do something",
                        worktree_path=Path("/tmp"),
                        complexity="simple",
                        system_prompt="test",
                        skill="implement",
                    )

        result = asyncio.run(_run())
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "api_rate_limit")


# ---------------------------------------------------------------------------
# Helpers for sandbox-settings dispatch tests (Req 5, 6, 15)
# ---------------------------------------------------------------------------


def _capture_dispatch_options(monkeypatch_env: dict, repo_root: Path | None = None) -> dict:
    """Run ``dispatch_task`` with mocks, return the captured ClaudeAgentOptions kwargs.

    Patches the SDK ``query`` to immediately yield a ResultMessage so the
    dispatch returns success. Captures the kwargs passed to
    ``ClaudeAgentOptions`` for assertion.

    Args:
        monkeypatch_env: Mapping of env vars to set for the duration of the call.
        repo_root: Optional cortex repo root used to write a fixture
            ``.claude/settings.local.json`` for the no-blob-injection test.

    Returns:
        Dict with at least ``options_kwargs`` and ``settings_path_contents`` keys.
    """
    captured: dict = {}
    _original_cls = ClaudeAgentOptions

    class _CapturingOptions(_original_cls):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured["options_kwargs"] = kwargs

    async def mock_query(**kwargs):
        msg = ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=8,
            is_error=False,
            num_turns=1,
            session_id="sess-test",
            total_cost_usd=0.0,
        )
        async for m in _async_gen(msg):
            yield m

    async def _run():
        return await _dispatch_module.dispatch_task(
            feature="sandbox-test",
            task="do something",
            worktree_path=Path(tempfile.gettempdir()),
            complexity="simple",
            system_prompt="test",
            skill="implement",
        )

    # Apply env overrides.
    saved_env: dict[str, str | None] = {}
    for k, v in monkeypatch_env.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        with patch("cortex_command.pipeline.dispatch.ClaudeAgentOptions", new=_CapturingOptions):
            with patch("cortex_command.pipeline.dispatch.query", new=mock_query):
                asyncio.run(_run())
    finally:
        for k, prev in saved_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev

    settings_path = captured["options_kwargs"].get("settings")
    if settings_path is not None and Path(settings_path).exists():
        captured["settings_path_contents"] = json.loads(
            Path(settings_path).read_text(encoding="utf-8")
        )
    else:
        captured["settings_path_contents"] = None
    return captured


# ---------------------------------------------------------------------------
# Test 4 (spec Req 5): settings tempfile is used and has correct shape
# ---------------------------------------------------------------------------


def test_settings_tempfile_used(tmp_path):
    """Mock the SDK call, dispatch a feature, assert the captured
    ClaudeAgentOptions.settings is a filepath that exists, and its JSON contents
    contain the documented sandbox shape (spec Req 5)."""
    captured = _capture_dispatch_options({"LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}"})

    settings_path = captured["options_kwargs"].get("settings")
    assert settings_path is not None, "ClaudeAgentOptions.settings must be set"
    assert Path(settings_path).exists(), (
        f"Settings tempfile must exist on disk: {settings_path}"
    )

    contents = captured["settings_path_contents"]
    assert contents is not None
    sandbox = contents.get("sandbox")
    assert isinstance(sandbox, dict), f"Expected sandbox dict, got {type(sandbox)}"

    # Required keys per spec Req 2/Req 5.
    assert sandbox.get("enabled") is True
    assert "failIfUnavailable" in sandbox
    assert sandbox.get("allowUnsandboxedCommands") is False
    assert sandbox.get("enableWeakerNestedSandbox") is False
    assert sandbox.get("enableWeakerNetworkIsolation") is False

    fs = sandbox.get("filesystem")
    assert isinstance(fs, dict), f"Expected filesystem dict, got {type(fs)}"
    assert "denyWrite" in fs, "filesystem.denyWrite key required"
    assert "allowWrite" in fs, "filesystem.allowWrite key required"


# ---------------------------------------------------------------------------
# Test 5 (spec Req 5): dispatched env locks TMPDIR
# ---------------------------------------------------------------------------


def test_dispatched_env_locks_tmpdir(tmp_path):
    """Mock the SDK call; assert the captured env dict contains TMPDIR with a
    non-empty value (spec Req 5/Req 10 — locked into dispatched-agent env to
    prevent unset-fallback to /tmp/)."""
    captured = _capture_dispatch_options({"LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}"})

    env = captured["options_kwargs"].get("env")
    assert isinstance(env, dict), f"Expected env dict, got {type(env)}"
    assert "TMPDIR" in env, f"env must contain TMPDIR; got keys: {list(env)}"
    tmpdir_value = env["TMPDIR"]
    assert tmpdir_value, f"TMPDIR must be non-empty; got {tmpdir_value!r}"


# ---------------------------------------------------------------------------
# Test 6 (spec Req 6): no project-settings blob injection
# ---------------------------------------------------------------------------


def test_no_blob_injection(tmp_path):
    """Write a fixture .claude/settings.local.json containing hooks/env,
    dispatch a feature, assert the captured options.settings JSON does NOT
    contain "hooks" or "env" keys after json.loads (spec Req 6)."""
    # Create a fixture .claude/settings.local.json in tmp_path.
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_local = claude_dir / "settings.local.json"
    settings_local.write_text(
        json.dumps({"hooks": {"PostToolUse": []}, "env": {"FOO": "BAR"}}),
        encoding="utf-8",
    )

    # Run dispatch from tmp_path so _load_project_settings would naturally pick
    # up this fixture if it were still being force-injected.
    captured = _capture_dispatch_options(
        {
            "LIFECYCLE_SESSION_ID": f"test-{tmp_path.name}",
            "CORTEX_REPO_ROOT": str(tmp_path),
        }
    )

    contents = captured["settings_path_contents"]
    # Settings file is used (per Req 5); it must NOT contain hooks or env keys
    # at top level.
    assert contents is not None, "settings tempfile contents missing"
    assert "hooks" not in contents, (
        f"settings tempfile must NOT contain 'hooks' key; got: {sorted(contents)}"
    )
    assert "env" not in contents, (
        f"settings tempfile must NOT contain 'env' key; got: {sorted(contents)}"
    )


# ---------------------------------------------------------------------------
# Test 7 (spec Req 15): no typed sandbox field attempted
#
# NOTE: spec Req 15 originally named ``test_sdk_typed_sandbox_symbols_present``
# but that test cannot exist because the symbols (``SandboxSettings``,
# ``SandboxFilesystemSettings``) do NOT exist in claude_agent_sdk@0.1.46.
# The substitution ``test_no_typed_sandbox_field_attempted`` is documented
# in Task 10 spec as the inverse-assertion guard against accidental
# re-introduction of the broken typed-field path.
# ---------------------------------------------------------------------------


def test_no_typed_sandbox_field_attempted():
    """Assert ``cortex_command/pipeline/dispatch.py`` does NOT import
    ``SandboxSettings`` or ``SandboxFilesystemSettings`` from
    ``claude_agent_sdk``. Drift detector that guards against accidental
    re-introduction of the broken typed-field path (spec Req 15, REVISED
    2026-05-05)."""
    dispatch_path = Path(_dispatch_module.__file__)
    source = dispatch_path.read_text(encoding="utf-8")
    assert "SandboxSettings" not in source, (
        "cortex_command/pipeline/dispatch.py must not reference SandboxSettings "
        "(symbol does not exist in claude_agent_sdk@0.1.46; spec Req 15 REVISED)."
    )
    assert "SandboxFilesystemSettings" not in source, (
        "cortex_command/pipeline/dispatch.py must not reference "
        "SandboxFilesystemSettings (symbol does not exist in "
        "claude_agent_sdk@0.1.46; spec Req 15 REVISED)."
    )


if __name__ == "__main__":
    unittest.main()
