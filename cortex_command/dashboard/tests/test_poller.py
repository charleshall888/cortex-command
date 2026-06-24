"""Unit tests for poller.py — DashboardState and run_polling.

Tests cover:
  - DashboardState can be instantiated with default fields
  - run_polling populates state.overnight from a tmp overnight-state.json within 3 seconds
  - The overnight-events.log offset advances so a second poll does not re-emit seen events
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cortex_command.dashboard.poller import DashboardState, run_polling


# Fixture: a repo with leftover backlog items whose known statuses make the
# cortex-backlog arm produce {"backlog": 2, "complete": 1} (normalize_status
# keeps both verbatim). The leftover items are load-bearing — a clean-empty
# fixture would pass even a broken gate (both dicts already default to {}).
_BACKLOG_ITEMS = [("001-a.md", "backlog"), ("002-b.md", "backlog"), ("003-c.md", "complete")]
_EXPECTED_COUNTS = {"backlog": 2, "complete": 1}


def _write_repo(root: Path, backend: str | None) -> None:
    """Build a tmp repo: optional backend config + leftover backlog items."""
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    backlog = root / "cortex" / "backlog"
    backlog.mkdir(parents=True, exist_ok=True)
    if backend is not None:
        (root / "cortex" / "lifecycle.config.md").write_text(
            f"---\nbacklog:\n  backend: {backend}\n---\n", encoding="utf-8"
        )
    for fname, status in _BACKLOG_ITEMS:
        (backlog / fname).write_text(
            f"---\nstatus: {status}\ntitle: Item {fname}\n---\n\nbody\n", encoding="utf-8"
        )


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
        self.assertEqual(state.backlog_backend, "cortex-backlog")
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
            lifecycle_dir = root / "cortex" / "lifecycle"
            lifecycle_dir.mkdir(parents=True)
            session_dir = lifecycle_dir / "sessions" / "latest-overnight"
            session_dir.mkdir(parents=True)

            overnight_data = {
                "session_id": "test-session-001",
                "plan_ref": "cortex/lifecycle/plan.md",
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
            lifecycle_dir = root / "cortex" / "lifecycle"
            lifecycle_dir.mkdir(parents=True)
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


class TestPollSlowBackendGate(unittest.IsolatedAsyncioTestCase):
    """The _poll_slow gate skips local reads under a non-cortex-backlog backend.

    Drives a real poll iteration — asserting on a freshly-constructed
    DashboardState() would be insufficient (its dicts already default to {}).
    """

    async def _run_one_cycle(self, root: Path) -> DashboardState:
        from cortex_command.dashboard.poller import _poll_slow

        state = DashboardState()
        task = asyncio.create_task(_poll_slow(state, root))
        # Let the synchronous poll body run once, up to its `await sleep(30)`.
        for _ in range(5):
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return state

    async def test_nonlocal_arm_skips_local_reads(self):
        """none AND an external backend: gate stands down, parse never called."""
        for backend in ("none", "github-issues"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_repo(root, backend)
                with mock.patch(
                    "cortex_command.dashboard.poller.parse_backlog_counts"
                ) as spy_counts, mock.patch(
                    "cortex_command.dashboard.poller.parse_backlog_titles"
                ) as spy_titles:
                    state = await self._run_one_cycle(root)
                # (a) Only passes if the poller actually ran AND wrote the
                # resolved value — fails for a never-run poller (default
                # "cortex-backlog") and for a poller that forgets the assign.
                self.assertEqual(state.backlog_backend, backend)
                # (b) Local reads skipped even with leftover items present.
                self.assertEqual(state.backlog_counts, {})
                self.assertEqual(state.backlog_titles, {})
                spy_counts.assert_not_called()
                spy_titles.assert_not_called()

    async def test_cortex_backlog_arm_reads_known_counts(self):
        """Positive control: known-value dict (NOT == parse_backlog_counts(dir))."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, "cortex-backlog")
            state = await self._run_one_cycle(root)
        self.assertEqual(state.backlog_backend, "cortex-backlog")
        self.assertEqual(state.backlog_counts, _EXPECTED_COUNTS)

    async def test_absent_config_resolves_local(self):
        """Absent lifecycle.config.md → cortex-backlog → today's behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, None)
            state = await self._run_one_cycle(root)
        self.assertEqual(state.backlog_backend, "cortex-backlog")
        self.assertEqual(state.backlog_counts, _EXPECTED_COUNTS)


class TestLifespanStartupResolution(unittest.IsolatedAsyncioTestCase):
    """The backend is resolved synchronously at lifespan startup (R1).

    Closes the first-render window: a request landing before the first 30s
    poll must already see the resolved backend, not the cortex-backlog default.
    """

    async def test_backend_resolved_before_any_poll(self):
        from cortex_command.dashboard import app as app_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_repo(root, "none")
            fresh = DashboardState()

            async def _noop_run_polling(state, r):  # no pollers spawned
                return None

            with mock.patch.object(app_mod, "_root", return_value=root), \
                 mock.patch.object(app_mod, "run_polling", _noop_run_polling), \
                 mock.patch.object(app_mod, "_pid_file", root / "dash.pid"), \
                 mock.patch.object(app_mod, "state", fresh):
                # Sanity: the singleton defaults to the local arm before startup.
                self.assertEqual(fresh.backlog_backend, "cortex-backlog")
                async with app_mod.lifespan(app_mod.app):
                    # Resolution ran synchronously before `yield` — assert here,
                    # before any poll cycle has had a chance to run.
                    self.assertEqual(fresh.backlog_backend, "none")
                    await asyncio.sleep(0)  # drain the no-op polling task


if __name__ == "__main__":
    unittest.main()
