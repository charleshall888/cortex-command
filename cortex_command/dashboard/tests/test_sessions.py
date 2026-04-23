"""Unit tests for parse_session_list and parse_session_detail in data.py.

Tests cover:
  - parse_session_list: returns sorted list for multiple sessions
  - parse_session_list: returns [] when sessions directory is absent
  - parse_session_detail: returns None for an unknown session ID
  - parse_session_detail: happy path with morning-report.md rendered as HTML
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortex_command.dashboard.data import parse_session_detail, parse_session_list


def _write_session(
    sessions_dir: Path,
    session_id: str,
    started_at: str,
    updated_at: str,
    features: dict,
) -> None:
    """Write a minimal overnight-state.json and overnight-events.log fixture."""
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "session_id": session_id,
        "started_at": started_at,
        "updated_at": updated_at,
        "features": features,
    }
    (session_dir / "overnight-state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    # overnight-events.log: one SESSION_START event as a JSONL line
    event = {"event": "SESSION_START", "ts": started_at}
    (session_dir / "overnight-events.log").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )


class TestSessionList(unittest.TestCase):
    """Tests for parse_session_list."""

    def test_session_list_returns_sorted_list(self):
        """Two session dirs are returned with the later-timestamp session first."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"

            _write_session(
                sessions_dir,
                "overnight-2026-01-01-2200",
                "2026-01-01T22:00:00Z",
                "2026-01-01T23:00:00Z",
                {"feat-a": {"status": "merged"}},
            )
            _write_session(
                sessions_dir,
                "overnight-2026-01-02-2200",
                "2026-01-02T22:00:00Z",
                "2026-01-02T23:00:00Z",
                {"feat-b": {"status": "merged"}},
            )

            result = parse_session_list(lifecycle_dir)

            self.assertEqual(len(result), 2)
            # Most recent session (Jan 2) should come first
            self.assertEqual(result[0]["session_id"], "overnight-2026-01-02-2200")

    def test_session_list_empty_dir(self):
        """Returns [] when the sessions directory is absent."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            # Do NOT create lifecycle_dir/sessions — it should be absent

            result = parse_session_list(lifecycle_dir)

            self.assertEqual(result, [])


class TestSessionDetail(unittest.TestCase):
    """Tests for parse_session_detail."""

    def test_session_detail_returns_none_for_unknown(self):
        """Returns None when the session ID does not exist on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)

            result = parse_session_detail("overnight-does-not-exist", lifecycle_dir)

            self.assertIsNone(result)

    def test_session_detail_happy_path(self):
        """Returns a dict with morning_report_html containing <h1> for '# Test' markdown."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"

            session_id = "overnight-2026-02-26-2200"
            _write_session(
                sessions_dir,
                session_id,
                "2026-02-26T22:00:00Z",
                "2026-02-26T23:00:00Z",
                {"feat-a": {"status": "merged"}},
            )

            # Add morning-report.md with a top-level heading
            session_dir = sessions_dir / session_id
            (session_dir / "morning-report.md").write_text(
                "# Test\n", encoding="utf-8"
            )

            result = parse_session_detail(session_id, lifecycle_dir)

            self.assertIsNotNone(result)
            self.assertEqual(result["session_id"], session_id)
            self.assertIsNotNone(result["morning_report_html"])
            self.assertIn("<h1>", result["morning_report_html"])


if __name__ == "__main__":
    unittest.main()
