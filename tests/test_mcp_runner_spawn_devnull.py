"""Verification tests for Task 15 — runner spawn FD plumbing (R16).

Covers the ``overnight_start_run`` tool's spawn invariants:

* ``stdin=subprocess.DEVNULL`` so the runner never inherits the MCP
  server's stdio channel (which carries the JSON-RPC stream).
* ``stdout`` / ``stderr`` redirected to a ``runner-bootstrap.log``
  file descriptor opened *before* the spawn, so any pre-events.log
  failure (import errors, missing deps, early uncaught exceptions) is
  captured to disk rather than lost.
* ``start_new_session=True`` so the runner runs in a detached PG that
  ``overnight_cancel`` can ``os.killpg`` without flowing back into the
  MCP server.
* A deliberate import failure inside the spawned runner surfaces a
  Python traceback in ``runner-bootstrap.log``.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Optional

import pytest

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import StartRunInput, StartRunOutput
from cortex_command.overnight import cli_handler


def _write_state_file(session_dir: Path, session_id: str) -> Path:
    """Write a minimal ``overnight-state.json`` and return its path."""
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "phase": "executing",
                "current_round": 1,
                "features": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return state_path


class _FakePopen:
    """Minimal stand-in for :class:`subprocess.Popen` that records kwargs.

    The real ``subprocess.Popen`` would fork-exec a child; we monkeypatch
    it so the test never actually launches a runner subprocess. The
    captured kwargs are then asserted against the R16 contract.
    """

    captured: list[dict] = []

    def __init__(self, argv, **kwargs) -> None:  # noqa: D401 - signature mirror
        # Record everything so the test can assert on stdin/stdout/stderr,
        # start_new_session, and the argv prefix.
        recorded = {"argv": list(argv), **kwargs}
        type(self).captured.append(recorded)
        self.pid = 424242
        self.returncode: Optional[int] = None

    def wait(self, timeout: Optional[float] = None) -> int:  # pragma: no cover
        return 0

    def poll(self) -> Optional[int]:  # pragma: no cover
        return None


@pytest.fixture(autouse=True)
def _reset_fake_popen_log() -> None:
    """Clear ``_FakePopen.captured`` between tests so assertions are clean."""
    _FakePopen.captured.clear()
    yield
    _FakePopen.captured.clear()


def test_runner_spawn_uses_devnull_stdin_and_bootstrap_log(
    monkeypatch, tmp_path
) -> None:
    """R16: ``stdin=DEVNULL``, ``stdout``/``stderr`` → bootstrap log FDs."""
    repo_path = tmp_path
    session_id = "overnight-2026-04-24-spawn"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    # Fake out subprocess.Popen so no real runner is spawned. The
    # ``_subprocess`` module reference inside tools.py points at the
    # real ``subprocess`` module — patching the attribute on that
    # reference catches the actual call site.
    monkeypatch.setattr(tools._subprocess, "Popen", _FakePopen)

    payload = StartRunInput(
        confirm_dangerously_skip_permissions=True,
        state_path=str(state_path),
    )
    result = asyncio.run(tools.overnight_start_run(payload))

    assert isinstance(result, StartRunOutput)
    assert result.started is True
    assert result.session_id == session_id
    assert result.pid == 424242
    assert result.started_at is not None  # ISO-8601 timestamp string

    # Exactly one Popen call was made by the spawn path.
    assert len(_FakePopen.captured) == 1
    call = _FakePopen.captured[0]

    # (a) stdin=DEVNULL — the runner never inherits the MCP server's
    # stdio channel.
    assert call["stdin"] == subprocess.DEVNULL

    # (c) start_new_session=True — runner runs in a detached PG so
    # ``overnight_cancel``'s ``os.killpg`` reaches the full PG without
    # flowing back into the MCP server.
    assert call["start_new_session"] is True

    # (b) stdout / stderr are file descriptors pointing to the bootstrap
    # log under the session_dir. Both should be valid integer FDs (the
    # tool opens one fd and reuses it for both).
    bootstrap_log_path = session_dir / "runner-bootstrap.log"
    assert bootstrap_log_path.exists(), (
        "runner-bootstrap.log must be created by the spawn path before "
        "the subprocess is launched (R16)"
    )

    stdout_fd = call["stdout"]
    stderr_fd = call["stderr"]
    assert isinstance(stdout_fd, int)
    assert isinstance(stderr_fd, int)
    # The MCP layer opens a single fd and reuses it for both stdout and
    # stderr — they should be the same integer.
    assert stdout_fd == stderr_fd

    # The argv invokes ``overnight start --state <state_path>`` against
    # either the ``cortex`` console script or ``python -m cortex_command``.
    argv = call["argv"]
    assert "overnight" in argv
    assert "start" in argv
    assert "--state" in argv
    assert str(state_path) in argv


def test_bootstrap_log_captures_runner_import_failure(tmp_path) -> None:
    """A spawn whose runner fails on import writes its traceback to disk.

    Spawn-level smoke test: we use a real ``subprocess.Popen`` against a
    deliberately-broken Python command line whose ``stdout`` and
    ``stderr`` are redirected to a ``runner-bootstrap.log`` file
    descriptor opened by the parent before the spawn — exactly the same
    plumbing the MCP tool uses (R16). The traceback from the broken
    import must land in the log file, proving the FD-redirection path
    is wired correctly.
    """
    session_id = "overnight-2026-04-24-importfail"
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "runner-bootstrap.log"

    # Open the bootstrap log fd with the same flags the MCP tool uses.
    fd = os.open(
        str(log_path),
        os.O_CREAT | os.O_APPEND | os.O_WRONLY,
        0o600,
    )
    try:
        # Deliberately broken script: importing a module that does not
        # exist raises ``ModuleNotFoundError`` at import time, before
        # any other runner setup. The traceback lands on stderr — which
        # is wired to the bootstrap log fd.
        broken_code = textwrap.dedent(
            """
            import this_module_definitely_does_not_exist_xyz_424242
            """
        ).strip()
        proc = subprocess.Popen(
            [sys.executable, "-c", broken_code],
            stdin=subprocess.DEVNULL,
            stdout=fd,
            stderr=fd,
            start_new_session=True,
        )
        # The child should exit nonzero quickly — the ImportError fires
        # immediately at startup.
        deadline = time.monotonic() + 5.0
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proc.returncode is not None, (
            "broken subprocess did not exit within 5 s — ImportError "
            "should fire at startup"
        )
        assert proc.returncode != 0, (
            f"broken subprocess exited 0 unexpectedly "
            f"(returncode={proc.returncode!r})"
        )
    finally:
        os.close(fd)

    # The bootstrap log must contain the traceback from the failed
    # import — this is the whole point of R16 (capture pre-events.log
    # init failures).
    log_contents = log_path.read_text(encoding="utf-8")
    assert "Traceback" in log_contents, (
        f"runner-bootstrap.log must contain the traceback from the "
        f"import failure; got: {log_contents!r}"
    )
    assert (
        "this_module_definitely_does_not_exist_xyz_424242" in log_contents
        or "ModuleNotFoundError" in log_contents
    ), (
        f"runner-bootstrap.log must mention the failed module or its "
        f"error class; got: {log_contents!r}"
    )
