"""Tests for ``overnight_schedule_run`` MCP tool.

Test coverage:
  1. ``test_happy_path`` — mocked CLI returns exit-zero with JSON success;
     delegate returns ``ScheduleRunOutput(scheduled=True, ...)`` with the
     parsed fields.
  2. ``test_nonzero_exit_returns_scheduled_false`` — mocked CLI returns
     non-zero exit; delegate returns ``scheduled=False`` without raising.
  3. ``test_timeout_propagates`` — mocked subprocess raises
     ``subprocess.TimeoutExpired``; delegate propagates the exception so
     the MCP layer surfaces it as a tool error.
  4. ``test_missing_confirm_gate`` — ``ScheduleRunInput`` with no
     ``confirm_dangerously_skip_permissions`` (or ``False``) is rejected
     by Pydantic before the delegate is reached.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_PATH = REPO_ROOT / "plugins" / "cortex-overnight" / "server.py"
PLUGIN_ROOT = SERVER_PATH.parent


def _load_server_module():
    """Import ``server.py`` as a module, setting CLAUDE_PLUGIN_ROOT first."""
    if "cortex_plugin_server_t8" in sys.modules:
        return sys.modules["cortex_plugin_server_t8"]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    spec = importlib.util.spec_from_file_location("cortex_plugin_server_t8", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_plugin_server_t8"] = module
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


def _print_root_response():
    """Return a minimal valid ``--print-root`` JSON payload."""
    return json.dumps({
        "version": "1.0",
        "root": "/fake/root",
        "remote_url": "git@github.com:user/repo.git",
        "head_sha": "0" * 40,
    })


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
# Test 1: happy path — exit-zero + JSON returns scheduled=True with fields
# ---------------------------------------------------------------------------


def test_happy_path(server_module) -> None:
    """Mocked CLI returns exit-zero with a JSON success envelope.

    Verifies that ``_delegate_overnight_schedule_run`` returns
    ``ScheduleRunOutput(scheduled=True)`` and that the ``session_id``,
    ``label``, and ``scheduled_for_iso`` fields are populated from the
    parsed JSON.
    """
    schedule_response = json.dumps({
        "version": "1.0",
        "scheduled": True,
        "session_id": "sess-abc123",
        "label": "com.cortex.overnight.sess-abc123",
        "scheduled_for_iso": "2026-05-05T02:00:00+00:00",
    })

    def _fake_run(argv, **kwargs):
        if "--print-root" in argv:
            return _completed(stdout=_print_root_response())
        return _completed(stdout=schedule_response, returncode=0)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_schedule_run(
            server_module.ScheduleRunInput(
                confirm_dangerously_skip_permissions=True,
                target_time="02:00",
            )
        )

    assert isinstance(result, server_module.ScheduleRunOutput)
    assert result.scheduled is True
    assert result.session_id == "sess-abc123"
    assert result.label == "com.cortex.overnight.sess-abc123"
    assert result.scheduled_for_iso == "2026-05-05T02:00:00+00:00"


# ---------------------------------------------------------------------------
# Test 2: non-zero exit → scheduled=False (no exception)
# ---------------------------------------------------------------------------


def test_nonzero_exit_returns_scheduled_false(server_module) -> None:
    """CLI exits with non-zero; delegate returns ``scheduled=False``.

    A non-zero exit means the schedule subcommand failed (e.g. time
    already passed, conflicting plist).  The delegate returns a
    ``ScheduleRunOutput(scheduled=False)`` rather than raising so the
    MCP caller can surface a user-friendly message.
    """

    def _fake_run(argv, **kwargs):
        if "--print-root" in argv:
            return _completed(stdout=_print_root_response())
        return _completed(
            stdout="",
            stderr="error: target time already passed",
            returncode=1,
        )

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_schedule_run(
            server_module.ScheduleRunInput(
                confirm_dangerously_skip_permissions=True,
                target_time="01:00",
            )
        )

    assert isinstance(result, server_module.ScheduleRunOutput)
    assert result.scheduled is False
    assert result.session_id is None
    assert result.label is None
    assert result.scheduled_for_iso is None


# ---------------------------------------------------------------------------
# Test 3: timeout propagates — TimeoutExpired is not swallowed
# ---------------------------------------------------------------------------


def test_timeout_propagates(server_module) -> None:
    """subprocess.TimeoutExpired propagates; no silent scheduled=False.

    When the CLI does not return within the timeout, the exception should
    propagate to the MCP layer so it can surface an explicit tool error
    rather than silently returning ``scheduled=False`` (which could mislead
    the user into thinking the schedule attempt was cleanly rejected).
    """

    def _fake_run(argv, **kwargs):
        if "--print-root" in argv:
            return _completed(stdout=_print_root_response())
        raise subprocess.TimeoutExpired(
            cmd=["cortex", "overnight", "schedule", "02:00"],
            timeout=30.0,
        )

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
            server_module._delegate_overnight_schedule_run(
                server_module.ScheduleRunInput(
                    confirm_dangerously_skip_permissions=True,
                    target_time="02:00",
                )
            )

    assert exc_info.value.timeout == 30.0


# ---------------------------------------------------------------------------
# Test 4: missing confirm_dangerously_skip_permissions → Pydantic refuses
# ---------------------------------------------------------------------------


def test_missing_confirm_gate(server_module) -> None:
    """``ScheduleRunInput`` with no confirmation literal raises ValidationError.

    The ``Literal[True]`` field ensures the MCP wrapper rejects the call
    before the delegate is invoked — the tool refuses without touching
    the subprocess layer.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        server_module.ScheduleRunInput(target_time="02:00")

    with pytest.raises(ValidationError):
        server_module.ScheduleRunInput(
            confirm_dangerously_skip_permissions=False,
            target_time="02:00",
        )
