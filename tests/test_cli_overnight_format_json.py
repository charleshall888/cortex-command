"""Tests for ``--format json`` on overnight start, logs, and cancel (R4, R5, R15).

Verifies:

(a) ``cortex overnight logs --format json <session-id>`` produces
    versioned JSON parseable by :func:`json.loads` on stdout.
(b) ``cortex overnight cancel --format json <session-id>`` likewise
    (success path emits versioned JSON to stdout; failures use the
    JSON error envelope).
(c) ``cortex overnight start --format json`` against a pre-existing
    live ``runner.pid`` produces ``{"version": "1.0", "error":
    "concurrent_runner", ...}`` on stdout with non-zero exit.

Each handler is exercised through :mod:`cortex_command.overnight.cli_handler`
directly; the dispatch shim in :mod:`cortex_command.cli` is a thin
forwarder so an in-process call covers the contract without paying
subprocess startup costs.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import cli_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _live_start_time_iso() -> str:
    """Return the current process's ``create_time`` as an ISO-8601 string.

    Mirrors the helper in ``test_runner_concurrent_start_race.py`` so the
    fabricated ``runner.pid`` payload passes
    :func:`ipc.verify_runner_pid` (which compares
    ``psutil.Process(pid).create_time()`` to the recorded start_time
    within ±2s).
    """
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


def _make_session(tmp_path: Path, session_id: str) -> Path:
    """Create a session directory under ``tmp_path/cortex/lifecycle/sessions/`` and return it."""
    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    return session_dir


# ---------------------------------------------------------------------------
# (a) overnight logs --format json
# ---------------------------------------------------------------------------

def test_overnight_logs_format_json_emits_versioned_json(
    capsys, monkeypatch
) -> None:
    """``logs --format json <session-id>`` writes parseable versioned JSON to stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "alpha-2026-04-26"
        session_dir = _make_session(repo_path, session_id)

        # Fixture: a tiny events log with two lines.
        events_path = session_dir / "overnight-events.log"
        events_path.write_text(
            '{"ts":"2026-04-26T00:00:00+00:00","msg":"line-1"}\n'
            '{"ts":"2026-04-26T00:00:01+00:00","msg":"line-2"}\n',
            encoding="utf-8",
        )

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        args = argparse.Namespace(
            session_id=session_id,
            session_dir=None,
            files="events",
            tail=20,
            since=None,
            limit=500,
            format="json",
        )

        rc = cli_handler.handle_logs(args)
        assert rc == 0

        captured = capsys.readouterr()

        # Stdout is a single JSON object parseable in one shot.
        payload = json.loads(captured.out)

        # R15 schema-floor: version field present and major == 1.
        assert isinstance(payload.get("version"), str)
        assert payload["version"].startswith("1.")

        # Lines from the fixture flow through verbatim.
        assert "lines" in payload
        assert isinstance(payload["lines"], list)
        assert len(payload["lines"]) == 2
        assert payload["lines"][0].endswith("line-1\"}")
        assert payload["lines"][1].endswith("line-2\"}")

        # next_cursor stamped per R11 (now in JSON, not stderr).
        assert isinstance(payload.get("next_cursor"), str)
        assert payload["next_cursor"].startswith("@")
        assert int(payload["next_cursor"][1:]) > 0

        # files echoes the requested stream.
        assert payload["files"] == "events"


# ---------------------------------------------------------------------------
# (b) overnight cancel --format json
# ---------------------------------------------------------------------------

def test_overnight_cancel_format_json_emits_versioned_json(
    capsys, monkeypatch
) -> None:
    """``cancel --format json <session-id>`` emits parseable versioned JSON to stdout.

    No live runner is spawned in tests — exercises the
    ``no_active_session`` failure path, which (per the contract change)
    emits its error envelope to stdout when ``--format json`` is set
    rather than stderr text. The JSON parse-ability + ``version`` field
    are the load-bearing assertions; verifying spec acceptance criterion
    (b) without spawning a real runner.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "beta-2026-04-26"
        _make_session(repo_path, session_id)

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        args = argparse.Namespace(
            session_id=session_id,
            session_dir=None,
            format="json",
        )

        rc = cli_handler.handle_cancel(args)
        # No runner.pid present → error envelope, non-zero exit.
        assert rc == 1

        captured = capsys.readouterr()

        # Spec acceptance (b): stdout is parseable JSON.
        payload = json.loads(captured.out)

        # R15 schema-floor.
        assert isinstance(payload.get("version"), str)
        assert payload["version"].startswith("1.")

        # Error envelope shape.
        assert payload.get("error") == "no_active_session"
        assert isinstance(payload.get("message"), str)


# ---------------------------------------------------------------------------
# (c) overnight start --format json against pre-existing alive runner.pid
# ---------------------------------------------------------------------------

def test_overnight_start_format_json_concurrent_runner(
    capsys, monkeypatch
) -> None:
    """Pre-existing live ``runner.pid`` triggers ``concurrent_runner`` JSON shape.

    Pre-writes a runner.pid pointing at the current test process (which
    :func:`ipc.verify_runner_pid` accepts as alive within the ±2s
    create_time tolerance). Invokes ``handle_start`` with
    ``--format json`` and asserts:

      - non-zero exit code
      - stdout parses as JSON
      - ``version`` major == 1
      - ``error`` is exactly ``"concurrent_runner"``
      - ``session_id`` is the pre-existing claim's session id

    The state file under the session directory is intentionally minimal
    (the JSON refusal fires before runner.run is invoked, so loadable
    state is not required).
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "gamma-2026-04-26"
        session_dir = _make_session(repo_path, session_id)

        # Minimal state file + plan + events; the JSON refusal path
        # short-circuits before any of these are read, but state_path
        # existence is checked first by handle_start.
        state_path = session_dir / "overnight-state.json"
        state_path.write_text(
            json.dumps({"session_id": session_id, "phase": "executing"}),
            encoding="utf-8",
        )

        # Pre-write a live runner.pid claim.
        pid_payload = _alive_runner_pid_payload(
            session_dir, session_id, repo_path
        )
        (session_dir / "runner.pid").write_text(
            json.dumps(pid_payload), encoding="utf-8"
        )

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        args = argparse.Namespace(
            state=str(state_path),
            time_limit=None,
            max_rounds=None,
            tier="simple",
            dry_run=False,
            format="json",
        )

        rc = cli_handler.handle_start(args)
        assert rc != 0, "concurrent runner refusal must exit non-zero"

        captured = capsys.readouterr()

        # Spec acceptance (c): stdout parses as JSON.
        payload = json.loads(captured.out)

        assert isinstance(payload.get("version"), str)
        assert payload["version"].startswith("1.")
        assert payload.get("error") == "concurrent_runner"
        assert payload.get("session_id") == session_id
