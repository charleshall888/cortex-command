"""Unit tests for :func:`cortex_command.overnight.scheduler.macos.parse_target_time`.

Covers the spec R16 contract:
  - HH:MM today (future): resolved against today, returned unchanged.
  - HH:MM past: rolled forward 24 h to tomorrow.
  - YYYY-MM-DDTHH:MM ISO 8601: parsed via datetime.fromisoformat.
  - ISO 8601 in the past: rejected with the spec's exact phrasing.
  - ISO 8601 Feb 29 in a non-leap year: rejected with R16 phrasing.
  - ISO 8601 > 7 days out: rejected with the 7-day-ceiling phrasing.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cortex_command.overnight.scheduler.macos import parse_target_time


class TestHHMM(unittest.TestCase):
    """HH:MM short-form parsing rolls past times to tomorrow."""

    def test_hhmm_future_today(self) -> None:
        # Anchor "now" at 10:00 today and ask for 23:30 — should resolve
        # to today 23:30.
        now = datetime(2026, 5, 4, 10, 0, 0)
        resolved = parse_target_time("23:30", now=now)
        self.assertEqual(
            resolved,
            datetime(2026, 5, 4, 23, 30, 0),
        )

    def test_hhmm_past_rolls_to_tomorrow(self) -> None:
        # Anchor "now" at 23:00 today and ask for 06:00 — should resolve
        # to tomorrow 06:00.
        now = datetime(2026, 5, 4, 23, 0, 0)
        resolved = parse_target_time("06:00", now=now)
        self.assertEqual(
            resolved,
            datetime(2026, 5, 5, 6, 0, 0),
        )

    def test_hhmm_invalid_format_rejected(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, 0)
        with self.assertRaises(ValueError) as cm:
            parse_target_time("not-a-time", now=now)
        self.assertIn("invalid format", str(cm.exception))


class TestISO8601(unittest.TestCase):
    """YYYY-MM-DDTHH:MM ISO 8601 parsing."""

    def test_iso_future_valid(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, 0)
        resolved = parse_target_time("2026-05-05T22:00", now=now)
        self.assertEqual(
            resolved,
            datetime(2026, 5, 5, 22, 0, 0),
        )

    def test_iso_past_rejected(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, 0)
        with self.assertRaises(ValueError) as cm:
            parse_target_time("2026-05-03T22:00", now=now)
        self.assertEqual(str(cm.exception), "target time is in the past")

    def test_iso_feb_29_non_leap_year(self) -> None:
        # 2026 is not a leap year (divisible by 2 but not 4 — 2024 was).
        now = datetime(2026, 1, 1, 10, 0, 0)
        with self.assertRaises(ValueError) as cm:
            parse_target_time("2026-02-29T23:00", now=now)
        # Spec-mandated exact phrasing.
        self.assertEqual(
            str(cm.exception),
            "target time invalid: Feb 29 not in 2026",
        )

    def test_iso_feb_29_leap_year_accepted(self) -> None:
        # 2024 IS a leap year — should parse.
        now = datetime(2024, 1, 1, 10, 0, 0)
        # 2024-02-29 is more than 7 days out from 2024-01-01, so this
        # would trip the 7-day ceiling. Anchor "now" 2 days before.
        now = datetime(2024, 2, 27, 10, 0, 0)
        resolved = parse_target_time("2024-02-29T23:00", now=now)
        self.assertEqual(
            resolved,
            datetime(2024, 2, 29, 23, 0, 0),
        )

    def test_iso_more_than_7_days_out_rejected(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, 0)
        too_far = now + timedelta(days=8)
        target = too_far.strftime("%Y-%m-%dT%H:%M")
        with self.assertRaises(ValueError) as cm:
            parse_target_time(target, now=now)
        self.assertEqual(
            str(cm.exception),
            "target time is more than 7 days in the future",
        )

    def test_iso_exactly_at_7_days_accepted(self) -> None:
        # Exactly 7 days out should be allowed (ceiling is "more than").
        now = datetime(2026, 5, 4, 10, 0, 0)
        on_limit = now + timedelta(days=7)
        target = on_limit.strftime("%Y-%m-%dT%H:%M")
        resolved = parse_target_time(target, now=now)
        # Strip seconds since on_limit may carry them.
        self.assertEqual(
            resolved.replace(second=0, microsecond=0),
            on_limit.replace(second=0, microsecond=0),
        )


if __name__ == "__main__":
    unittest.main()
