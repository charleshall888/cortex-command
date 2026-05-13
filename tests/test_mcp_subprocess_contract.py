"""Subprocess+JSON contract tests for the plugin-bundled MCP server.

Task 5 seeded this file with the confused-deputy startup-check test
(R17). Task 6 extends it with:

- per-tool subprocess delegation tests (R2): each tool invokes the
  expected ``cortex <verb> --format json`` argv and parses the
  response correctly.
- schema-version enforcement tests (R15):
  ``test_major_version_mismatch_is_rejected``,
  ``test_minor_version_greater_skips_unknown_fields``.
- the R4 acceptance test
  ``test_overnight_start_concurrent_runner_json_shape`` exercising
  the real CLI directly with a pre-written ``runner.pid``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = (
    REPO_ROOT
    / "plugins"
    / "cortex-overnight"
    / "server.py"
)
PLUGIN_ROOT = SERVER_PATH.parent


# ---------------------------------------------------------------------------
# Module loader: import server.py as a regular module for in-process tests.
# The confused-deputy startup check in server.py exits non-zero unless
# ``CLAUDE_PLUGIN_ROOT`` matches the file's directory; we set it before
# loading so the same source the production plugin runs is exercised
# in-process.
# ---------------------------------------------------------------------------


def _load_server_module():
    """Import ``plugins/cortex-overnight/server.py`` as a module.

    Sets ``CLAUDE_PLUGIN_ROOT`` to the plugin directory so the
    confused-deputy guard at the top of the file accepts the load. The
    module is cached under its ``__name__`` so subsequent loads do not
    re-trigger the guard.
    """
    if "cortex_plugin_server" in sys.modules:
        return sys.modules["cortex_plugin_server"]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    spec = importlib.util.spec_from_file_location(
        "cortex_plugin_server", SERVER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cortex_plugin_server"] = module
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
# R17: confused-deputy mitigation (Task 5; preserved for Task 6 suite).
# ---------------------------------------------------------------------------


def test_plugin_path_mismatch_exits_nonzero(tmp_path: Path) -> None:
    """R17 — confused-deputy mitigation.

    Invoke the plugin server with ``CLAUDE_PLUGIN_ROOT`` pointed at an
    attacker-controlled directory that does NOT contain
    ``server.py``; the server must refuse to start, exit non-zero, and
    emit a stderr message containing ``"plugin path mismatch"``.
    """

    if shutil.which("uv") is None:
        pytest.skip("uv not installed; cannot resolve PEP 723 deps")

    assert SERVER_PATH.exists(), f"plugin server.py missing at {SERVER_PATH}"

    attacker_root = tmp_path / "attacker-controlled"
    attacker_root.mkdir()

    completed = subprocess.run(
        ["uv", "run", "--script", str(SERVER_PATH)],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "CLAUDE_PLUGIN_ROOT": str(attacker_root),
        },
    )

    assert completed.returncode != 0, (
        "expected non-zero exit when CLAUDE_PLUGIN_ROOT points outside "
        f"the plugin directory; got returncode={completed.returncode}, "
        f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
    )
    assert "plugin path mismatch" in completed.stderr, (
        "expected stderr to contain 'plugin path mismatch'; got "
        f"stderr={completed.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Per-tool subprocess delegation tests (R2).
# ---------------------------------------------------------------------------


@pytest.fixture
def server_module():
    """Load the plugin server.py once and reset caches per-test."""
    mod = _load_server_module()
    # Reset the discovery cache so each test starts from a clean slate.
    mod._CORTEX_ROOT_CACHE = None
    mod._STATUS_LEGACY_VERSION_WARNED = False
    return mod


def _print_root_payload(root: str = "/fake/root") -> str:
    """Return a JSON string matching ``cortex --print-root``'s contract."""
    return json.dumps(
        {
            "version": "0.1.0",
            "schema_version": "2.0",
            "root": root,
            "remote_url": "git@github.com:user/cortex-command.git",
            "head_sha": "0" * 40,
        }
    )


def test_overnight_status_invokes_expected_argv(server_module) -> None:
    """``overnight_status`` calls ``cortex overnight status --format json``."""

    status_payload = json.dumps(
        {
            "session_id": "alpha",
            "phase": "executing",
            "current_round": 4,
            "features": {},
        }
    )

    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        # First call is `cortex --print-root` for the discovery cache;
        # subsequent calls are the actual tool delegation.
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=status_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )

    # Last call is the status delegation; assert exact verb argv.
    assert calls[-1] == ["cortex", "overnight", "status", "--format", "json"]
    assert isinstance(result, server_module.StatusOutput)
    assert result.phase == "executing"
    assert result.session_id == "alpha"


def test_overnight_status_no_active_session_legacy_shape(
    server_module,
) -> None:
    """The legacy ``{"active": false}`` shape collapses to no_active_session."""

    def _fake_run(argv, **kwargs):
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        # Legacy unversioned no-active-session sentinel.
        return _completed(stdout=json.dumps({"active": False}))

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_status(
            server_module.StatusInput(session_id=None)
        )
    assert result.phase == "no_active_session"


def test_overnight_logs_invokes_expected_argv(server_module) -> None:
    """``overnight_logs`` invokes ``cortex overnight logs --format json``."""

    logs_payload = json.dumps(
        {
            "schema_version": "2.0",
            "lines": ['{"msg":"hello"}'],
            "next_cursor": "@128",
            "files": "events",
        }
    )

    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=logs_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_logs(
            server_module.LogsInput(
                session_id="alpha",
                files=["events"],
                limit=50,
                tail=20,
            )
        )

    last_call = calls[-1]
    assert last_call[:5] == [
        "cortex",
        "overnight",
        "logs",
        "--format",
        "json",
    ]
    assert "--files" in last_call
    assert "events" in last_call
    assert "alpha" in last_call
    assert result.next_cursor == "@128"
    assert result.lines == [{"msg": "hello"}]


def test_overnight_cancel_invokes_expected_argv(server_module) -> None:
    """``overnight_cancel`` invokes ``cortex overnight cancel --format json``."""

    cancel_payload = json.dumps(
        {
            "schema_version": "2.0",
            "cancelled": True,
            "session_id": "alpha",
            "pgid": 12345,
        }
    )

    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=cancel_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_cancel(
            server_module.CancelInput(session_id="alpha")
        )

    last_call = calls[-1]
    assert last_call == [
        "cortex",
        "overnight",
        "cancel",
        "--format",
        "json",
        "alpha",
    ]
    assert result.cancelled is True
    assert result.reason == "cancelled"


def test_overnight_list_sessions_invokes_expected_argv(
    server_module,
) -> None:
    """``overnight_list_sessions`` invokes the matching CLI verb."""

    list_payload = json.dumps(
        {
            "schema_version": "2.0",
            "active": [
                {
                    "session_id": "active-1",
                    "phase": "executing",
                    "started_at": "2026-04-01T00:00:00+00:00",
                    "updated_at": "2026-04-01T00:01:00+00:00",
                    "integration_branch": "overnight/active-1",
                }
            ],
            "recent": [],
            "total_count": 1,
            "next_cursor": None,
        }
    )

    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=list_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_list_sessions(
            server_module.ListSessionsInput(limit=5)
        )

    last_call = calls[-1]
    assert last_call[:5] == [
        "cortex",
        "overnight",
        "list-sessions",
        "--format",
        "json",
    ]
    assert "--limit" in last_call
    assert "5" in last_call
    assert len(result.active) == 1
    assert result.active[0].session_id == "active-1"
    assert result.total_count == 1


def test_overnight_start_run_concurrent_refusal_via_mock(
    server_module,
) -> None:
    """Concurrent-runner refusal: CLI emits versioned error envelope."""

    refusal_payload = json.dumps(
        {
            "schema_version": "2.0",
            "error": "concurrent_runner",
            "session_id": "existing-session",
            "existing_pid": 99999,
        }
    )

    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=refusal_payload, returncode=1)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_start_run(
            server_module.StartRunInput(
                confirm_dangerously_skip_permissions=True
            )
        )

    last_call = calls[-1]
    assert last_call[:5] == [
        "cortex",
        "overnight",
        "start",
        "--format",
        "json",
    ]
    assert result.started is False
    assert result.reason == "concurrent_runner_alive"
    assert result.existing_session_id == "existing-session"
    assert result.pid == 99999


# ---------------------------------------------------------------------------
# R15: schema-version enforcement.
# ---------------------------------------------------------------------------


def test_major_version_mismatch_is_rejected(server_module) -> None:
    """A payload with a different major version raises SchemaVersionError."""

    bad_payload = json.dumps(
        {
            # Re-keyed from "version" -> "schema_version" by T9 (consumer
            # migration). Under the post-T10 floor (MCP_REQUIRED_CLI_VERSION
            # = "2.0") a forward-major value (e.g. "3.0") is the canonical
            # mismatch case: it preserves the original test intent
            # (a CLI emitting a major newer than the MCP supports must be
            # rejected) under the new floor. Task 11 follow-up.
            "schema_version": "3.0",
            "lines": [],
            "next_cursor": None,
            "files": "events",
        }
    )

    def _fake_run(argv, **kwargs):
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=bad_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        with pytest.raises(server_module.SchemaVersionError) as exc_info:
            server_module._delegate_overnight_logs(
                server_module.LogsInput(session_id="alpha", files=["events"])
            )

    msg = str(exc_info.value)
    assert "major-version mismatch" in msg
    assert "2.0" in msg


def test_minor_version_greater_skips_unknown_fields(server_module) -> None:
    """A minor-greater payload is accepted; unknown fields are dropped."""

    forward_compat_payload = json.dumps(
        {
            # Re-keyed from "1.99" -> "2.99" by T11 follow-up. Under
            # the post-T10 floor (MCP_REQUIRED_CLI_VERSION = "2.0") a
            # minor-greater value within the same major is the canonical
            # forward-compat case: it preserves the original test intent
            # (minor-greater within the same major is accepted; unknown
            # fields silently dropped by Pydantic's extra="ignore") under
            # the new floor.
            "schema_version": "2.99",
            "lines": ['{"msg":"hi"}'],
            "next_cursor": "@1",
            "files": "events",
            # Unknown future-minor field — must be silently ignored.
            "future_field": {"nested": [1, 2, 3]},
        }
    )

    def _fake_run(argv, **kwargs):
        if argv[1:] == ["--print-root"]:
            return _completed(stdout=_print_root_payload())
        return _completed(stdout=forward_compat_payload)

    with patch.object(server_module.subprocess, "run", side_effect=_fake_run):
        result = server_module._delegate_overnight_logs(
            server_module.LogsInput(session_id="alpha", files=["events"])
        )

    # Unknown fields were dropped silently; known fields parsed.
    assert result.next_cursor == "@1"
    assert result.lines == [{"msg": "hi"}]
    # The result model is the canonical shape — no future_field
    # leakage.
    dumped = result.model_dump()
    assert "future_field" not in dumped


# ---------------------------------------------------------------------------
# R4: end-to-end concurrent-runner JSON-shape acceptance test.
# ---------------------------------------------------------------------------


def _live_start_time_iso() -> str:
    """Return the test process's create_time as an ISO-8601 string."""
    import psutil

    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _alive_runner_pid_payload(
    session_dir: Path, session_id: str, repo_path: Path
) -> dict:
    """Return a runner.pid payload pointing at *this* live test process."""
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "start_time": _live_start_time_iso(),
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(repo_path),
    }


def test_overnight_start_concurrent_runner_json_shape() -> None:
    """R4 acceptance: real CLI emits structured concurrent_runner JSON.

    Pre-writes a ``runner.pid`` pointing at the test process, then
    invokes ``cortex overnight start --format json --state <path>``
    against a temp session directory. The CLI must:

      * exit non-zero
      * emit a parseable JSON envelope on stdout containing
        ``"schema_version": "2.0"`` and ``"error": "concurrent_runner"``
      * include the existing session's id
    """

    cortex = shutil.which("cortex")
    if cortex is None:
        # Fall back to ``python -m cortex_command.cli`` so the test
        # works in CI/sandbox environments where the console script is
        # not on PATH.
        argv_prefix = [sys.executable, "-m", "cortex_command.cli"]
    else:
        argv_prefix = [cortex]

    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "concurrent-test-session"
        session_dir = repo_path / "lifecycle" / "sessions" / session_id
        session_dir.mkdir(parents=True)

        state_path = session_dir / "overnight-state.json"
        state_path.write_text(
            json.dumps({"session_id": session_id, "phase": "executing"}),
            encoding="utf-8",
        )

        pid_payload = _alive_runner_pid_payload(
            session_dir, session_id, repo_path
        )
        (session_dir / "runner.pid").write_text(
            json.dumps(pid_payload), encoding="utf-8"
        )

        completed = subprocess.run(
            argv_prefix
            + [
                "overnight",
                "start",
                "--format",
                "json",
                "--state",
                str(state_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo_path),
        )

    assert completed.returncode != 0, (
        f"concurrent runner refusal must exit non-zero; "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )

    payload = json.loads(completed.stdout)
    # Re-keyed from "version" -> "schema_version" by T9 (consumer
    # migration) and bumped 1.x -> 2.x by T10 (schema-major bump).
    # Under the post-T10 envelope, the concurrent_runner refusal
    # carries ``"schema_version": "2.0"`` (M.m form per Terraform's
    # ``format_version`` precedent); ``version`` is now the package
    # version which the CLI emits only on ``--print-root``, not on
    # error refusal envelopes.
    assert isinstance(payload.get("schema_version"), str)
    assert payload["schema_version"].startswith("2.")
    assert payload.get("error") == "concurrent_runner"
    assert payload.get("session_id") == session_id
