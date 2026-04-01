"""Unit tests for poller.py — DashboardState and run_polling.

Tests cover:
  - DashboardState can be instantiated with default fields
  - run_polling populates state.overnight from a tmp overnight-state.json within 3 seconds
  - The overnight-events.log offset advances so a second poll does not re-emit seen events
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from claude.dashboard.poller import DashboardState, run_polling


class TestDashboardStateDefaults(unittest.TestCase):
    """DashboardState instantiates correctly with all default fields."""

    def test_defaults(self):
        state = DashboardState()
        self.assertIsNone(state.overnight)
        self.assertIsNone(state.pipeline)
        self.assertIsInstance(state.overnight_events, list)
        self.assertEqual(state.overnight_events_offset, 0)
        self.assertIsInstance(state.feature_states, dict)
        self.assertIsInstance(state.backlog_counts, dict)
        self.assertEqual(state.last_updated, "")

    def test_independent_mutable_defaults(self):
        """Each DashboardState instance gets its own mutable containers."""
        s1 = DashboardState()
        s2 = DashboardState()
        s1.overnight_events.append({"x": 1})
        self.assertEqual(s2.overnight_events, [])


class TestRunPolling(unittest.IsolatedAsyncioTestCase):
    """Tests for run_polling integration with real tmp files."""

    async def test_overnight_state_populated(self):
        """state.overnight is populated from overnight-state.json within 3 seconds."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle_dir = root / "lifecycle"
            lifecycle_dir.mkdir()
            session_dir = lifecycle_dir / "sessions" / "latest-overnight"
            session_dir.mkdir(parents=True)

            overnight_data = {
                "session_id": "test-session-001",
                "plan_ref": "lifecycle/plan.md",
                "current_round": 1,
                "phase": "executing",
                "features": {},
                "round_history": [],
                "started_at": "2026-02-26T00:00:00+00:00",
                "updated_at": "2026-02-26T00:00:00+00:00",
                "paused_from": None,
                "integration_branch": None,
            }
            overnight_path = session_dir / "overnight-state.json"
            overnight_path.write_text(json.dumps(overnight_data), encoding="utf-8")

            state = DashboardState()
            await run_polling(state, root)

            # Let the event loop run long enough for at least one 2-second poll cycle.
            await asyncio.sleep(3)

            self.assertIsNotNone(state.overnight, "state.overnight should be populated")
            self.assertEqual(state.overnight["session_id"], "test-session-001")
            self.assertEqual(state.overnight["phase"], "executing")

    async def test_overnight_events_offset_advances(self):
        """A second poll of overnight-events.log does not re-emit already-seen events."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle_dir = root / "lifecycle"
            lifecycle_dir.mkdir()
            session_dir = lifecycle_dir / "sessions" / "latest-overnight"
            session_dir.mkdir(parents=True)

            # Write initial overnight-state.json so _poll_state_files doesn't error.
            overnight_path = session_dir / "overnight-state.json"
            overnight_path.write_text(
                json.dumps({
                    "session_id": "sess-offset-test",
                    "plan_ref": "",
                    "current_round": 1,
                    "phase": "executing",
                    "features": {},
                    "round_history": [],
                    "started_at": "2026-02-26T00:00:00+00:00",
                    "updated_at": "2026-02-26T00:00:00+00:00",
                    "paused_from": None,
                    "integration_branch": None,
                }),
                encoding="utf-8",
            )

            # Write two initial events to overnight-events.log.
            events_path = session_dir / "overnight-events.log"
            initial_lines = (
                '{"event": "FEATURE_START", "feature": "feat-a"}\n'
                '{"event": "FEATURE_START", "feature": "feat-b"}\n'
            )
            events_path.write_text(initial_lines, encoding="utf-8")

            state = DashboardState()
            await run_polling(state, root)

            # Let the polling loop run for a couple of seconds so it reads
            # the initial two events and advances the offset.
            await asyncio.sleep(2.5)

            events_after_first_poll = list(state.overnight_events)
            offset_after_first_poll = state.overnight_events_offset

            # The offset must have advanced past zero (the file had content).
            self.assertGreater(
                offset_after_first_poll,
                0,
                "Offset should have advanced after reading the initial events",
            )
            # We should have seen both initial events.
            event_names = [e.get("feature") for e in events_after_first_poll]
            self.assertIn("feat-a", event_names)
            self.assertIn("feat-b", event_names)

            # Append a third event to the log.
            with events_path.open("a", encoding="utf-8") as fh:
                fh.write('{"event": "FEATURE_COMPLETE", "feature": "feat-a"}\n')

            # Wait for another poll cycle (1 second interval).
            await asyncio.sleep(1.5)

            events_after_second_poll = list(state.overnight_events)

            # The total number of events should be exactly 3 (no duplicates).
            self.assertEqual(
                len(events_after_second_poll),
                3,
                f"Expected exactly 3 events (no re-emission), got {len(events_after_second_poll)}: "
                f"{events_after_second_poll}",
            )

            # The third event should be the FEATURE_COMPLETE one.
            last_event = events_after_second_poll[-1]
            self.assertEqual(last_event.get("event"), "feature_complete")
            self.assertEqual(last_event.get("feature"), "feat-a")

    async def test_missing_files_do_not_crash(self):
        """run_polling tolerates absent state files without raising."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Do not create lifecycle/ or any files — everything is absent.
            state = DashboardState()
            await run_polling(state, root)

            # Let a full 2-second poll cycle complete.
            await asyncio.sleep(2.5)

            # State should remain at safe defaults — no exception was raised.
            self.assertIsNone(state.overnight)
            self.assertIsNone(state.pipeline)
            self.assertEqual(state.overnight_events, [])


if __name__ == "__main__":
    unittest.main()
