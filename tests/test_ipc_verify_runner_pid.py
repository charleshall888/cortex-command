"""Tests for :func:`cortex_command.overnight.ipc.verify_runner_pid`'s
schema-version range check.

The bounded schema-version window prevents an older ``cortex`` from
silently mis-decoding a future runner's ``runner.pid`` (Adversarial
§10). The current accepted range is ``1 <=
schema_version <= MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import ipc


def _live_start_time_iso() -> str:
    """Return the current process's ``create_time`` as an ISO-8601 string."""
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_runner_pid(session_dir: Path, payload: dict) -> None:
    """Write a ``runner.pid`` JSON file into ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload))


def test_rejects_future_schema_version(tmp_path: Path) -> None:
    """A ``runner.pid`` with ``schema_version`` above the known maximum
    must be rejected, even when the PID is live and the ``start_time``
    matches — preventing silent mis-decoding of a newer-format payload.
    """
    payload = {
        "schema_version": ipc.MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION + 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "start_time": _live_start_time_iso(),
        "session_id": "2026-04-24-12-00-00",
        "session_dir": str(tmp_path),
        "repo_path": str(tmp_path),
    }
    _write_runner_pid(tmp_path, payload)

    data = ipc.read_runner_pid(tmp_path)
    assert data is not None
    assert ipc.verify_runner_pid(data) is False
