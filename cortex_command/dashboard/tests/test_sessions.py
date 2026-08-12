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

    def test_latest_overnight_pointer_is_not_listed_as_its_own_session(self):
        """A session reached through the pointer symlink is not listed twice.

        Regression: ``sessions/latest-overnight`` is a symlink the runner
        repoints at every start, and a ``*/overnight-state.json`` glob matches
        straight through it — so the newest run appeared twice on /sessions,
        under the same id both times. Every repo that has run overnight since
        the pointer shipped has the link, so this was live, not hypothetical.
        """
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            _write_session(
                sessions_dir,
                "overnight-2026-01-02-2200",
                "2026-01-02T22:00:00Z",
                "2026-01-02T23:00:00Z",
                {"feat-b": {"status": "merged"}},
            )
            (sessions_dir / "latest-overnight").symlink_to(
                "overnight-2026-01-02-2200", target_is_directory=True
            )

            result = parse_session_list(lifecycle_dir)

            self.assertEqual([row["session_id"] for row in result],
                             ["overnight-2026-01-02-2200"])

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

    def test_duration_str_is_rendered_at_session_scale(self):
        """The span reads 'Xh Ym', the same shape the history list prints."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            _write_session(
                lifecycle_dir / "sessions",
                "overnight-2026-02-26-2200",
                "2026-02-26T22:00:00Z",
                "2026-02-27T04:51:00Z",
                {"feat-a": {"status": "merged"}},
            )

            result = parse_session_detail("overnight-2026-02-26-2200", lifecycle_dir)

            self.assertEqual("6h 51m", result["duration_str"])


class TestMorningReportSanitization(unittest.TestCase):
    """The morning report goes through the same allowlist as a ticket body.

    ``markdown.markdown`` passes raw HTML in its source straight through, and
    ``morning_report_html`` reaches ``session_detail.html`` under ``| safe`` —
    so before this it was the one ``| safe`` value on the dashboard a
    ``<script>`` could reach. The report is agent-written and quotes material
    the agent read, and ``DASHBOARD_HOST`` makes a non-loopback bind a
    documented option.
    """

    def _report(self, body: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            _write_session(
                lifecycle_dir / "sessions", "overnight-2026-02-26-2200",
                "2026-02-26T22:00:00Z", "2026-02-26T23:00:00Z",
                {"feat-a": {"status": "merged"}},
            )
            (lifecycle_dir / "sessions" / "overnight-2026-02-26-2200"
             / "morning-report.md").write_text(body, encoding="utf-8")
            detail = parse_session_detail("overnight-2026-02-26-2200", lifecycle_dir)
            return detail["morning_report_html"]

    def test_a_script_tag_does_not_survive(self):
        html = self._report("Summary.\n\n<script>alert(1)</script>\n")
        self.assertNotIn("<script", html)
        # Dropped with its contents, not unwrapped — unwrapping would print the
        # script source as prose.
        self.assertNotIn("alert(1)", html)

    def test_an_event_handler_attribute_does_not_survive(self):
        html = self._report('Summary.\n\n<p onclick="alert(1)">click</p>\n')
        self.assertNotIn("onclick", html)

    def test_a_javascript_href_does_not_survive(self):
        html = self._report('<a href="javascript:alert(1)">link</a>\n')
        self.assertNotIn("javascript:", html)

    def test_real_report_structure_still_renders(self):
        # The allowlist must not cost the report what it is for: headings,
        # tables and fenced code are what a morning report is made of.
        html = self._report(
            "# Overnight\n\n## Merged\n\n| feature | outcome |\n| --- | --- |\n"
            "| alpha | merged |\n\n```python\nprint('x')\n```\n\n- one\n- two\n"
        )
        for tag in ("<h1>", "<h2>", "<table>", "<td>", "<pre>", "<code", "<li>"):
            self.assertIn(tag, html)


if __name__ == "__main__":
    unittest.main()
