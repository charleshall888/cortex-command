"""Tests for claude/pipeline/metrics.py.

Covers: discover_pipeline_event_logs, pair_dispatch_events, filter_events_since
"""

from __future__ import annotations

import argparse
import unittest
import warnings
from datetime import datetime, timezone
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
PIPELINE_LOGS_FIXTURE = FIXTURES_DIR / "pipeline_logs"
DISPATCH_SINCE_BOUNDARY_FIXTURE = FIXTURES_DIR / "dispatch_since_boundary.jsonl"

UTC = timezone.utc


class TestDiscoverPipelineEventLogs(unittest.TestCase):
    """Tests for discover_pipeline_event_logs."""

    def _fn(self, lifecycle_dir: Path):
        from claude.pipeline.metrics import discover_pipeline_event_logs
        return discover_pipeline_event_logs(lifecycle_dir)

    def test_pipeline_events_sources(self):
        """Returns all three pipeline-events.log paths in sorted order."""
        result = self._fn(PIPELINE_LOGS_FIXTURE)

        expected = sorted([
            PIPELINE_LOGS_FIXTURE / "pipeline-events.log",
            PIPELINE_LOGS_FIXTURE / "sessions" / "s1" / "pipeline-events.log",
            PIPELINE_LOGS_FIXTURE / "sessions" / "s2" / "pipeline-events.log",
        ])

        self.assertEqual(result, expected)

    def test_empty_dir_returns_empty_list(self, tmp_path=None):
        """Returns [] when no pipeline-events.log files exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._fn(Path(tmpdir))
            self.assertEqual(result, [])

    def test_nonexistent_dir_returns_empty_list(self):
        """Returns [] when the directory does not exist."""
        result = self._fn(Path("/nonexistent/path/that/does/not/exist"))
        self.assertEqual(result, [])


class TestPairDispatchEvents(unittest.TestCase):
    """Tests for pair_dispatch_events."""

    def _fn(self, events):
        from claude.pipeline.metrics import pair_dispatch_events
        return pair_dispatch_events(events)

    # ------------------------------------------------------------------
    # Helpers for building synthetic events
    # ------------------------------------------------------------------

    def _start(self, feature, complexity="complex", model="opus", ts="2026-04-01T00:00:00Z"):
        return {
            "event": "dispatch_start",
            "ts": ts,
            "feature": feature,
            "complexity": complexity,
            "criticality": "high",
            "model": model,
            "effort": "high",
            "max_turns": 30,
            "max_budget_usd": 50.0,
        }

    def _complete(self, feature, cost_usd=1.23, num_turns=5, ts="2026-04-01T00:01:00Z"):
        return {
            "event": "dispatch_complete",
            "ts": ts,
            "feature": feature,
            "cost_usd": cost_usd,
            "duration_ms": 5000,
            "num_turns": num_turns,
        }

    def _error(self, feature, error_type="timeout", ts="2026-04-01T00:01:00Z"):
        return {
            "event": "dispatch_error",
            "ts": ts,
            "feature": feature,
            "error_type": error_type,
            "error_detail": "ProcessError: timed out",
        }

    def _progress(self, feature, ts="2026-04-01T00:00:30Z"):
        return {
            "event": "dispatch_progress",
            "ts": ts,
            "feature": feature,
            "message_type": "assistant",
        }

    # ------------------------------------------------------------------
    # (a) Basic pair: one start + one complete
    # ------------------------------------------------------------------

    def test_basic_pair_complete(self):
        """One start + one complete pairs correctly with all fields populated."""
        events = [
            self._start("feat-a", complexity="complex", model="opus"),
            self._complete("feat-a", cost_usd=2.50, num_turns=7),
        ]
        result = self._fn(events)

        self.assertEqual(len(result), 1)
        rec = result[0]
        self.assertEqual(rec["feature"], "feat-a")
        self.assertEqual(rec["model"], "opus")
        self.assertEqual(rec["tier"], "complex")
        self.assertEqual(rec["outcome"], "complete")
        self.assertAlmostEqual(rec["cost_usd"], 2.50)
        self.assertEqual(rec["num_turns"], 7)
        self.assertIsNone(rec["error_type"])
        self.assertFalse(rec["untiered"])

    # ------------------------------------------------------------------
    # (b) Interleaved different features
    # ------------------------------------------------------------------

    def test_interleaved_different_features(self):
        """Feature A start, feature B start, feature A complete, feature B
        complete: each complete pairs to its own feature's start."""
        events = [
            self._start("feat-a", complexity="simple", model="sonnet", ts="2026-04-01T00:00:01Z"),
            self._start("feat-b", complexity="trivial", model="haiku", ts="2026-04-01T00:00:02Z"),
            self._complete("feat-a", cost_usd=0.50, num_turns=3, ts="2026-04-01T00:01:00Z"),
            self._complete("feat-b", cost_usd=0.10, num_turns=2, ts="2026-04-01T00:01:01Z"),
        ]
        result = self._fn(events)

        self.assertEqual(len(result), 2)
        by_feature = {r["feature"]: r for r in result}

        self.assertEqual(by_feature["feat-a"]["tier"], "simple")
        self.assertEqual(by_feature["feat-a"]["model"], "sonnet")
        self.assertFalse(by_feature["feat-a"]["untiered"])

        self.assertEqual(by_feature["feat-b"]["tier"], "trivial")
        self.assertEqual(by_feature["feat-b"]["model"], "haiku")
        self.assertFalse(by_feature["feat-b"]["untiered"])

    # ------------------------------------------------------------------
    # (c) Same-feature retry storm
    # ------------------------------------------------------------------

    def test_same_feature_retry_storm(self):
        """3 starts for same feature, then 2 completes: first complete pairs
        to start[0], second complete pairs to start[1], start[2] remains
        unmatched (no orphan emitted for unmatched starts)."""
        events = [
            self._start("feat-a", complexity="complex", model="opus", ts="2026-04-01T00:00:01Z"),
            self._start("feat-a", complexity="complex", model="opus", ts="2026-04-01T00:00:02Z"),
            self._start("feat-a", complexity="complex", model="opus", ts="2026-04-01T00:00:03Z"),
            self._complete("feat-a", cost_usd=1.0, num_turns=5, ts="2026-04-01T00:01:00Z"),
            self._complete("feat-a", cost_usd=2.0, num_turns=8, ts="2026-04-01T00:01:01Z"),
        ]
        result = self._fn(events)

        # Only 2 paired records (no orphan for the unmatched start[2])
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0]["cost_usd"], 1.0)
        self.assertEqual(result[0]["num_turns"], 5)
        self.assertAlmostEqual(result[1]["cost_usd"], 2.0)
        self.assertEqual(result[1]["num_turns"], 8)
        for r in result:
            self.assertFalse(r["untiered"])
            self.assertEqual(r["tier"], "complex")

    # ------------------------------------------------------------------
    # (d) Orphan dispatch_complete → untiered
    # ------------------------------------------------------------------

    def test_orphan_dispatch_complete_untiered(self):
        """A lone complete with no preceding start emits an untiered record
        and raises a UserWarning."""
        events = [
            self._complete("feat-orphan", cost_usd=0.77, num_turns=4),
        ]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self._fn(events)

        self.assertEqual(len(result), 1)
        rec = result[0]
        self.assertTrue(rec["untiered"])
        self.assertIsNone(rec["tier"])
        self.assertIsNone(rec["model"])
        self.assertEqual(rec["outcome"], "complete")

        # A UserWarning must have been emitted
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertTrue(
            len(user_warnings) >= 1,
            "Expected at least one UserWarning for orphan dispatch_complete",
        )

    # ------------------------------------------------------------------
    # (e) Daytime-schema dispatch_complete is skipped entirely
    # ------------------------------------------------------------------

    def test_daytime_schema_skipped(self):
        """A dispatch_complete with 'mode', 'outcome', or 'pr_url' fields is
        omitted from output entirely — not treated as untiered."""
        daytime_complete_mode = {
            "event": "dispatch_complete",
            "ts": "2026-04-01T00:01:00Z",
            "feature": "feat-daytime",
            "mode": "lifecycle",
            "cost_usd": 1.0,
        }
        daytime_complete_outcome = {
            "event": "dispatch_complete",
            "ts": "2026-04-01T00:01:01Z",
            "feature": "feat-daytime2",
            "outcome": "approved",
        }
        daytime_complete_pr_url = {
            "event": "dispatch_complete",
            "ts": "2026-04-01T00:01:02Z",
            "feature": "feat-daytime3",
            "pr_url": "https://github.com/example/pr/1",
        }
        events = [daytime_complete_mode, daytime_complete_outcome, daytime_complete_pr_url]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = self._fn(events)

        # Nothing in output — skipped, not untiered
        self.assertEqual(result, [])
        # No warnings for daytime skips
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        self.assertEqual(len(user_warnings), 0)

    # ------------------------------------------------------------------
    # (f) dispatch_progress noise is silently ignored
    # ------------------------------------------------------------------

    def test_dispatch_progress_noise_ignored(self):
        """Start, 5 dispatch_progress events, complete: one paired record
        emitted, progress events silently skipped."""
        ts_start = "2026-04-01T00:00:00Z"
        ts_end = "2026-04-01T00:01:00Z"
        events = [self._start("feat-a", ts=ts_start)]
        for i in range(5):
            events.append(self._progress("feat-a", ts=f"2026-04-01T00:00:{10 + i:02d}Z"))
        events.append(self._complete("feat-a", ts=ts_end))

        result = self._fn(events)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["feature"], "feat-a")
        self.assertFalse(result[0]["untiered"])

    # ------------------------------------------------------------------
    # (g) Timestamp tie-break: start and complete at same ts
    # ------------------------------------------------------------------

    def test_timestamp_tie_deterministic(self):
        """A start and complete sharing the exact same ts are paired correctly
        due to the (ts, event_priority) sort tie-break."""
        same_ts = "2026-04-01T00:00:00Z"
        events = [
            self._complete("feat-a", cost_usd=1.0, num_turns=3, ts=same_ts),
            self._start("feat-a", complexity="simple", model="sonnet", ts=same_ts),
        ]
        # Even though complete is listed first, the tie-break should sort
        # start before complete at the same timestamp.
        result = self._fn(events)

        self.assertEqual(len(result), 1)
        rec = result[0]
        self.assertEqual(rec["tier"], "simple")
        self.assertEqual(rec["model"], "sonnet")
        self.assertFalse(rec["untiered"])


class TestSinceFlag(unittest.TestCase):
    """Tests for filter_events_since and _parse_since."""

    def _filter(self, events, since):
        from claude.pipeline.metrics import filter_events_since
        return filter_events_since(events, since)

    def _parse_since(self, s):
        from claude.pipeline.metrics import _parse_since
        return _parse_since(s)

    def _load_boundary_events(self):
        """Load events from dispatch_since_boundary.jsonl fixture."""
        import json
        events = []
        for line in DISPATCH_SINCE_BOUNDARY_FIXTURE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    # ------------------------------------------------------------------
    # (a) Boundary: since=2026-04-18 filters out the 23:59:59 event,
    #     keeps 00:00:00 and 00:00:01 events.
    # ------------------------------------------------------------------

    def test_since_flag_boundary(self):
        """since=2026-04-18 UTC: event at 23:59:59 filtered out, 00:00:00
        and 00:00:01 events retained."""
        events = self._load_boundary_events()
        since = datetime(2026, 4, 18, tzinfo=UTC)

        result = self._filter(events, since)

        # The 23:59:59 pair (2 events) should be excluded; 4 events remain.
        self.assertEqual(len(result), 4)
        ts_values = [e["ts"] for e in result]
        self.assertNotIn("2026-04-17T23:59:59Z", ts_values)
        self.assertIn("2026-04-18T00:00:00Z", ts_values)
        self.assertIn("2026-04-18T00:00:01Z", ts_values)

    # ------------------------------------------------------------------
    # (b) None passthrough: all events returned unchanged.
    # ------------------------------------------------------------------

    def test_since_flag_none_passthrough(self):
        """since=None returns all events unchanged."""
        events = self._load_boundary_events()

        result = self._filter(events, None)

        self.assertEqual(result, events)

    # ------------------------------------------------------------------
    # (c) Unparseable ts raises ValueError.
    # ------------------------------------------------------------------

    def test_since_flag_unparseable_ts_raises_value_error(self):
        """An event with an unparseable ts raises ValueError."""
        events = [{"ts": "not-a-timestamp", "event": "dispatch_start", "feature": "feat-x"}]
        since = datetime(2026, 4, 18, tzinfo=UTC)

        with self.assertRaises(ValueError):
            self._filter(events, since)

    # ------------------------------------------------------------------
    # (d) _parse_since("yesterday") raises ArgumentTypeError.
    # ------------------------------------------------------------------

    def test_parse_since_invalid_format_raises_argument_type_error(self):
        """_parse_since with a non-YYYY-MM-DD string raises ArgumentTypeError."""
        with self.assertRaises(argparse.ArgumentTypeError):
            self._parse_since("yesterday")


if __name__ == "__main__":
    unittest.main()
