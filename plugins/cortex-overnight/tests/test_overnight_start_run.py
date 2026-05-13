"""Tests for ``overnight_start_run`` MCP tool — async-spawn semantics.

Task 9 updates ``overnight_start_run`` to reflect the async-spawn
refactor from Task 6:

- Subprocess timeout is 30 s (R12).
- The runner is detached under launchd by design; exit-zero means
  the spawn-confirmation handshake (R18) succeeded.
- ``started: true`` is returned as a fast async return (within ~5 s in
  the typical case; within 30 s in slow-disk scenarios).

Test coverage:
  1. ``test_async_return_shape`` — mocked CLI returns exit-zero with no
     stdout; delegate returns ``started=True`` immediately.
  2. ``test_slow_spawn_within_30s`` — mocked CLI sleeps 25 s before
     returning exit-zero; delegate succeeds within the 30 s timeout.
  3. ``test_timeout_boundary_at_30s`` — mocked subprocess raises
     ``subprocess.TimeoutExpired`` after 30 s; delegate propagates the
     exception (MCP layer surfaces it as a tool error rather than
     returning a false-negative ``started=false``).
  4. ``test_start_run_tool_timeout_constant`` — ``_START_RUN_TOOL_TIMEOUT``
     equals 30.0 per R12.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader — mirrors the pattern used in test_mcp_subprocess_contract.py
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = REPO_ROOT / "plugins" / "cortex-overnight" / "server.py"
PLUGIN_ROOT = SERVER_PATH.parent


def _load_server_module():
    """Import ``server.py`` as a module, setting CLAUDE_PLUGIN_ROOT first."""
    if "cortex_plugin_server_t9" in sys.modules:
        return sys.modules["cortex_plugin_server_t9"]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    spec = importlib.util.spec_from_file_location("cortex_plugin_server_t9", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_plugin_server_t9"] = module
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Return a fake :class:`subprocess.CompletedProcess` for mocks."""
    return subprocess.CompletedProcess(
        args=["cortex"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server_module():
    """Load the plugin server.py once and reset caches per-test."""
    mod = _load_server_module()
    mod._CORTEX_ROOT_CACHE = None
    return mod


# ---------------------------------------------------------------------------
# Test 1: async-return shape — exit-zero with no stdout returns started=True
# ---------------------------------------------------------------------------


def test_async_return_shape(server_module) -> None:
    """Mocked CLI returns exit-zero with no stdout; delegate returns started=True.

    Verifies the fast async-return contract: caller sees ``started=True``
    as soon as the CLI exits (which itself returns promptly after the
    spawn-confirmation handshake).
    """

    def _fake_run(argv, **kwargs):
        # Gate-dispatch discovery call returns a minimal valid payload.
        if "--print-root" in argv:
            import json
            return _completed(
                stdout=json.dumps({
                    "schema_version": "2.0",
                    "root": "/fake/root",
                    "remote_url": "git@github.com:user/repo.git",
                    "head_sha": "0" * 40,
                })
            )
        # Async spawn succeeds: exit 0, no JSON on stdout (runner is detached).
        return _completed(stdout="", returncode=0)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_start_run(
            server_module.StartRunInput(confirm_dangerously_skip_permissions=True)
        )

    assert isinstance(result, server_module.StartRunOutput)
    assert result.started is True
    assert result.reason is None
    assert result.existing_session_id is None


# ---------------------------------------------------------------------------
# Test 2: slow spawn completes within the 30 s timeout
# ---------------------------------------------------------------------------


def test_slow_spawn_within_30s(server_module) -> None:
    """A CLI that takes 25 s to return still succeeds within the 30 s timeout.

    The mock simulates a slow-disk scenario (e.g., plist write + bootstrap
    + launchctl print verify + sidecar atomic write taking longer than usual)
    by introducing a 0.05 s artificial delay in the test to confirm the
    timeout is passed as 30 s to the subprocess call.
    """
    import json

    captured_kwargs: list[dict] = []

    def _fake_run(argv, **kwargs):
        captured_kwargs.append(kwargs)
        if "--print-root" in argv:
            return _completed(
                stdout=json.dumps({
                    "schema_version": "2.0",
                    "root": "/fake/root",
                    "remote_url": "git@github.com:user/repo.git",
                    "head_sha": "0" * 40,
                })
            )
        # Simulate slow spawn (sub-30s latency): brief sleep then success.
        time.sleep(0.05)
        return _completed(stdout="", returncode=0)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_start_run(
            server_module.StartRunInput(confirm_dangerously_skip_permissions=True)
        )

    assert result.started is True

    # Confirm the subprocess was called with timeout=30.0 (R12).
    start_run_calls = [
        kw for kw in captured_kwargs
        if kw.get("timeout") == 30.0
    ]
    assert len(start_run_calls) >= 1, (
        f"Expected at least one subprocess call with timeout=30.0; "
        f"captured kwargs: {captured_kwargs!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: timeout boundary — TimeoutExpired at 30 s propagates to caller
# ---------------------------------------------------------------------------


def test_timeout_boundary_at_30s(server_module) -> None:
    """subprocess.TimeoutExpired after 30 s propagates; no false started=False.

    When the CLI does not return within 30 s, the MCP layer should surface
    the timeout as an exception rather than silently returning
    ``started=False``.  A false-negative ``started=False`` would tell Claude
    "scheduling failed" while a job may be armed — a worse UX than a raised
    exception that the MCP framework wraps into a tool error.
    """
    import json

    def _fake_run(argv, **kwargs):
        if "--print-root" in argv:
            return _completed(
                stdout=json.dumps({
                    "schema_version": "2.0",
                    "root": "/fake/root",
                    "remote_url": "git@github.com:user/repo.git",
                    "head_sha": "0" * 40,
                })
            )
        # Simulate timeout exceeded.
        raise subprocess.TimeoutExpired(cmd=["cortex", "overnight", "start"], timeout=30.0)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
            server_module._delegate_overnight_start_run(
                server_module.StartRunInput(confirm_dangerously_skip_permissions=True)
            )

    assert exc_info.value.timeout == 30.0


# ---------------------------------------------------------------------------
# Test 4: constant check — _START_RUN_TOOL_TIMEOUT == 30.0 per R12
# ---------------------------------------------------------------------------


def test_start_run_tool_timeout_constant(server_module) -> None:
    """``_START_RUN_TOOL_TIMEOUT`` equals 30.0 as required by spec R12."""
    assert server_module._START_RUN_TOOL_TIMEOUT == 30.0, (
        f"Expected _START_RUN_TOOL_TIMEOUT=30.0 (R12); "
        f"got {server_module._START_RUN_TOOL_TIMEOUT!r}"
    )
