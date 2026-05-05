"""Tests for cortex_command.overnight.report soft-fail header (spec Req 20).

Covers the unconditional ``CORTEX_SANDBOX_SOFT_FAIL`` header line that the
morning-report builder emits when at least one ``sandbox_soft_fail_active``
event is present in the session's events.log. The event is recorded by the
per-spawn settings builder at the first orchestrator-spawn or per-dispatch
invocation that observed ``CORTEX_SANDBOX_SOFT_FAIL=1``.

Tests construct a fixture ``ReportData`` directly (with and without the
event) so the assertion focuses on the rendering boundary rather than on
the upstream collection plumbing.
"""

from __future__ import annotations

import unittest

from cortex_command.overnight.report import (
    ReportData,
    generate_report,
    render_soft_fail_header,
)


_EXPECTED_HEADER = (
    "CORTEX_SANDBOX_SOFT_FAIL=1 was active for this session; "
    "sandbox.failIfUnavailable was downgraded to false."
)


class TestSoftFailHeader(unittest.TestCase):
    """Spec Req 20: morning-report builder emits an unconditional header line
    when ``sandbox_soft_fail_active`` was recorded in events.log."""

    def test_soft_fail_header_emitted(self) -> None:
        """ReportData containing a ``sandbox_soft_fail_active`` event causes
        the morning-report builder to emit the documented header string."""
        data = ReportData(
            session_id="overnight-test",
            date="2026-05-05",
            events=[
                {
                    "v": 1,
                    "ts": "2026-05-05T00:00:00+00:00",
                    "event": "sandbox_soft_fail_active",
                    "session_id": "overnight-test",
                }
            ],
        )

        # Direct render assertion: helper must return the exact header string.
        rendered = render_soft_fail_header(data)
        self.assertEqual(rendered, _EXPECTED_HEADER)

        # Top-level builder must include the header in its assembled output.
        report = generate_report(data)
        self.assertIn(_EXPECTED_HEADER, report)

    def test_no_soft_fail_no_header(self) -> None:
        """ReportData WITHOUT a ``sandbox_soft_fail_active`` event causes the
        morning-report builder to NOT emit the header string."""
        data = ReportData(
            session_id="overnight-test",
            date="2026-05-05",
            events=[
                # An unrelated event — should not trigger the header.
                {
                    "v": 1,
                    "ts": "2026-05-05T00:00:00+00:00",
                    "event": "round_started",
                    "session_id": "overnight-test",
                }
            ],
        )

        rendered = render_soft_fail_header(data)
        self.assertEqual(rendered, "")

        report = generate_report(data)
        self.assertNotIn(_EXPECTED_HEADER, report)


if __name__ == "__main__":
    unittest.main()
