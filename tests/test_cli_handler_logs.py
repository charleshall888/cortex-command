"""Verification test for Task 8 of the MCP control-plane spec.

Covers R19: ``cortex overnight logs --files=escalations <session_id>``
reads ``cortex/lifecycle/sessions/{session_id}/escalations.jsonl``, not the
legacy repo-level ``cortex/lifecycle/escalations.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from cortex_command.overnight import cli_handler


def test_escalations_per_session(capsys, monkeypatch) -> None:
    """`handle_logs --files=escalations` reads the per-session file.

    Writes a fixture per-session ``escalations.jsonl`` under
    ``cortex/lifecycle/sessions/<id>/`` inside a tempdir, points the CLI handler
    at that tempdir via the repo-path resolver, invokes the handler with
    ``--files=escalations``, and asserts that the lines returned come
    from the per-session file (and that no repo-level
    ``cortex/lifecycle/escalations.jsonl`` is consulted).
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "alpha-2026-04-24"
        sessions_root = repo_path / "cortex" / "lifecycle" / "sessions"
        session_dir = sessions_root / session_id
        session_dir.mkdir(parents=True)

        # Fixture per-session escalations.
        per_session_lines = [
            json.dumps({"escalation_id": f"{session_id}-feat-1-q1", "n": 1}),
            json.dumps({"escalation_id": f"{session_id}-feat-1-q2", "n": 2}),
        ]
        (session_dir / "escalations.jsonl").write_text(
            "\n".join(per_session_lines) + "\n",
            encoding="utf-8",
        )

        # Write a legacy repo-level escalations file with distinct
        # content; if the handler still resolved to the repo-level path,
        # these would leak into stdout instead of the per-session lines.
        (repo_path / "cortex" / "lifecycle" / "escalations.jsonl").write_text(
            json.dumps({"escalation_id": "LEGACY-REPO-LEVEL"}) + "\n",
            encoding="utf-8",
        )

        # Route the handler's repo-path resolver at our tempdir.
        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        args = argparse.Namespace(
            session_id=session_id,
            session_dir=None,
            files="escalations",
            tail=20,
            since=None,
            limit=500,
        )

        rc = cli_handler.handle_logs(args)
        assert rc == 0

        captured = capsys.readouterr()
        stdout_lines = [ln for ln in captured.out.splitlines() if ln]

        # The per-session lines are returned verbatim.
        assert stdout_lines == per_session_lines

        # Legacy repo-level content must not appear in output.
        assert "LEGACY-REPO-LEVEL" not in captured.out
