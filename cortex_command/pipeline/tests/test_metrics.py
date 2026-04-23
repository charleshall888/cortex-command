"""Tests for cortex_command/pipeline/metrics.py.

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
        from cortex_command.pipeline.metrics import discover_pipeline_event_logs
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
        from cortex_command.pipeline.metrics import pair_dispatch_events
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
        from cortex_command.pipeline.metrics import filter_events_since
        return filter_events_since(events, since)

    def _parse_since(self, s):
        from cortex_command.pipeline.metrics import _parse_since
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


DISPATCH_OVER_CAP_FIXTURE = FIXTURES_DIR / "dispatch_over_cap.jsonl"


class TestModelTierAggregates(unittest.TestCase):
    """Tests for compute_model_tier_dispatch_aggregates."""

    def _fn(self, paired):
        from cortex_command.pipeline.metrics import compute_model_tier_dispatch_aggregates
        return compute_model_tier_dispatch_aggregates(paired)

    def _make_complete(self, model, tier, cost_usd, num_turns, feature="feat-x", ts="2026-04-01T00:01:00Z"):
        return {
            "ts": ts,
            "feature": feature,
            "model": model,
            "tier": tier,
            "outcome": "complete",
            "cost_usd": cost_usd,
            "num_turns": num_turns,
            "error_type": None,
            "untiered": False,
        }

    def _make_error(self, model, tier, error_type, feature="feat-x", ts="2026-04-01T00:01:00Z"):
        return {
            "ts": ts,
            "feature": feature,
            "model": model,
            "tier": tier,
            "outcome": "error",
            "cost_usd": None,
            "num_turns": None,
            "error_type": error_type,
            "untiered": False,
        }

    # ------------------------------------------------------------------
    # (a) n=3 bucket: p95_suppressed=True, max_turns_observed set,
    #     num_turns_p95=None
    # ------------------------------------------------------------------

    def test_small_bucket_p95_suppressed(self):
        """n=3 complete bucket: p95_suppressed=True, max_turns_observed
        equals the maximum num_turns, num_turns_p95=None."""
        paired = [
            self._make_complete("sonnet", "simple", cost_usd=1.0, num_turns=5),
            self._make_complete("sonnet", "simple", cost_usd=2.0, num_turns=10),
            self._make_complete("sonnet", "simple", cost_usd=3.0, num_turns=15),
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        bucket = result["sonnet,simple"]
        self.assertEqual(bucket["n_completes"], 3)
        self.assertTrue(bucket["p95_suppressed"])
        self.assertEqual(bucket["max_turns_observed"], 15)
        self.assertIsNone(bucket["num_turns_p95"])

    # ------------------------------------------------------------------
    # (b) n=100 bucket: num_turns_p95 computed, p95_suppressed=False
    # ------------------------------------------------------------------

    def test_large_bucket_p95_computed(self):
        """n=100 complete bucket: num_turns_p95 equals the 95th percentile
        via statistics.quantiles, p95_suppressed=False."""
        import statistics as _stats
        paired = [
            self._make_complete("sonnet", "simple", cost_usd=i * 0.5, num_turns=i,
                                feature=f"feat-{i}", ts="2026-04-01T00:01:00Z")
            for i in range(100)
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        bucket = result["sonnet,simple"]
        self.assertEqual(bucket["n_completes"], 100)
        self.assertFalse(bucket["p95_suppressed"])
        self.assertIsNone(bucket["max_turns_observed"])

        turns = list(range(100))
        expected_p95 = _stats.quantiles(turns, n=100, method="inclusive")[94]
        self.assertAlmostEqual(bucket["num_turns_p95"], expected_p95)

    # ------------------------------------------------------------------
    # (c) over_cap_rate: fixture with 4 opus/complex dispatches, 2 over cap
    # ------------------------------------------------------------------

    def test_over_cap_rate_from_fixture(self):
        """dispatch_over_cap.jsonl: 4 opus/complex dispatches where 2 exceed
        the $50 cap → over_cap_rate == 0.5."""
        import json
        events = []
        for line in DISPATCH_OVER_CAP_FIXTURE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))

        from cortex_command.pipeline.metrics import pair_dispatch_events
        paired = pair_dispatch_events(events)
        result = self._fn(paired)

        self.assertIn("opus,complex", result)
        bucket = result["opus,complex"]
        self.assertEqual(bucket["n_completes"], 4)
        self.assertAlmostEqual(bucket["over_cap_rate"], 0.5)

    # ------------------------------------------------------------------
    # (d) Mixed complete + error records in same bucket
    # ------------------------------------------------------------------

    def test_mixed_complete_and_errors(self):
        """2 complete + 3 error records (mix of agent_timeout and
        api_rate_limit): n_completes=2, n_errors=3,
        error_counts={agent_timeout: 2, api_rate_limit: 1},
        num_turns_mean computed from the 2 completes."""
        paired = [
            self._make_complete("sonnet", "simple", cost_usd=1.0, num_turns=4, feature="f1"),
            self._make_complete("sonnet", "simple", cost_usd=2.0, num_turns=6, feature="f2"),
            self._make_error("sonnet", "simple", "agent_timeout", feature="f3"),
            self._make_error("sonnet", "simple", "agent_timeout", feature="f4"),
            self._make_error("sonnet", "simple", "api_rate_limit", feature="f5"),
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        bucket = result["sonnet,simple"]
        self.assertEqual(bucket["n_completes"], 2)
        self.assertEqual(bucket["n_errors"], 3)
        self.assertEqual(bucket["error_counts"], {"agent_timeout": 2, "api_rate_limit": 1})
        self.assertAlmostEqual(bucket["num_turns_mean"], 5.0)

    # ------------------------------------------------------------------
    # (e) All-error bucket: 0 complete + 2 errors
    # ------------------------------------------------------------------

    def test_all_errors_no_completes(self):
        """0 complete + 2 error records: n_completes=0,
        error_counts={agent_timeout: 2}, all cost/turn stats None."""
        paired = [
            self._make_error("sonnet", "simple", "agent_timeout", feature="f1"),
            self._make_error("sonnet", "simple", "agent_timeout", feature="f2"),
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        bucket = result["sonnet,simple"]
        self.assertEqual(bucket["n_completes"], 0)
        self.assertEqual(bucket["error_counts"], {"agent_timeout": 2})
        self.assertIsNone(bucket["num_turns_mean"])
        self.assertIsNone(bucket["num_turns_median"])
        self.assertIsNone(bucket["num_turns_p95"])
        self.assertIsNone(bucket["max_turns_observed"])
        self.assertIsNone(bucket["estimated_cost_usd_mean"])
        self.assertIsNone(bucket["estimated_cost_usd_median"])
        self.assertIsNone(bucket["estimated_cost_usd_max"])

    # ------------------------------------------------------------------
    # (f) Two distinct buckets are independent
    # ------------------------------------------------------------------

    def test_distinct_bucket_independence(self):
        """(sonnet, simple) and (opus, complex) buckets are computed
        independently; each has correct n_completes."""
        paired = [
            self._make_complete("sonnet", "simple", cost_usd=1.0, num_turns=5, feature="s1"),
            self._make_complete("sonnet", "simple", cost_usd=2.0, num_turns=8, feature="s2"),
            self._make_complete("opus", "complex", cost_usd=40.0, num_turns=20, feature="o1"),
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        self.assertIn("opus,complex", result)
        self.assertEqual(result["sonnet,simple"]["n_completes"], 2)
        self.assertEqual(result["opus,complex"]["n_completes"], 1)
        # Buckets don't bleed into each other
        self.assertNotEqual(
            result["sonnet,simple"]["estimated_cost_usd_mean"],
            result["opus,complex"]["estimated_cost_usd_mean"],
        )

    # ------------------------------------------------------------------
    # (g) Untiered bucket
    # ------------------------------------------------------------------

    def test_error_type_frequency_novel_strings_passthrough(self):
        """Novel error_type strings pass through under their raw value
        without erroring. error_counts is keyed by the raw error_type string
        — no enum whitelist, no case-folding — so an aggregator run over
        logs containing never-before-seen error types produces correct
        frequency counts rather than dropping or coercing them.
        """
        paired = [
            self._make_error("sonnet", "simple", "cosmic_ray_flip", feature="f1"),
            self._make_error("sonnet", "simple", "cosmic_ray_flip", feature="f2"),
            self._make_error("sonnet", "simple", "quantum_tunneling", feature="f3"),
            self._make_error("sonnet", "simple", "API-Misuse", feature="f4"),
        ]
        result = self._fn(paired)

        self.assertIn("sonnet,simple", result)
        bucket = result["sonnet,simple"]
        self.assertEqual(bucket["n_errors"], 4)
        self.assertEqual(
            bucket["error_counts"],
            {"cosmic_ray_flip": 2, "quantum_tunneling": 1, "API-Misuse": 1},
        )

    def test_untiered_bucket(self):
        """Untiered records bucket under 'untiered,untiered' with
        is_untiered=True, budget_cap_usd=None, over_cap_rate=None."""
        paired = [
            {
                "ts": "2026-04-01T00:01:00Z",
                "feature": "feat-orphan",
                "model": None,
                "tier": None,
                "outcome": "complete",
                "cost_usd": 5.0,
                "num_turns": 3,
                "error_type": None,
                "untiered": True,
            }
        ]
        result = self._fn(paired)

        self.assertIn("untiered,untiered", result)
        bucket = result["untiered,untiered"]
        self.assertTrue(bucket["is_untiered"])
        self.assertIsNone(bucket["budget_cap_usd"])
        self.assertIsNone(bucket["over_cap_rate"])
        self.assertIsNone(bucket["turn_cap_observed_rate"])
        self.assertEqual(bucket["n_completes"], 1)


class TestReportTierDispatch(unittest.TestCase):
    """Tests for the --report tier-dispatch CLI output."""

    def _run_report(self, argv: list[str], root: "Path | None" = None):
        """Run main() with the given argv, capturing stdout.

        Returns the captured stdout string.
        """
        import io
        import sys
        from cortex_command.pipeline.metrics import main

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            main(argv)
        finally:
            sys.stdout = old_stdout
        return captured.getvalue()

    def _make_root_with_aggregates(
        self,
        tmp_path: Path,
        paired_records: list[dict],
        since: "datetime | None" = None,
    ) -> tuple[Path, str]:
        """Write a minimal lifecycle dir with pipeline-events.log for the given
        paired records.

        The paired records are converted back to raw dispatch_start /
        dispatch_complete events so the main pipeline can parse them.

        Returns ``(root, lifecycle_dir_as_str)``.
        """
        lifecycle_dir = tmp_path / "lifecycle"
        lifecycle_dir.mkdir(parents=True, exist_ok=True)

        # Write raw events from paired records so main() can pair them.
        import json as _json
        raw_events = []
        for rec in paired_records:
            if rec.get("untiered"):
                # orphan: write only a dispatch_complete (no matching start)
                raw_events.append({
                    "event": "dispatch_complete",
                    "ts": rec.get("ts", "2026-04-01T00:01:00Z"),
                    "feature": rec["feature"],
                    "cost_usd": rec.get("cost_usd"),
                    "num_turns": rec.get("num_turns"),
                    "duration_ms": 1000,
                })
            elif rec.get("outcome") == "error":
                start_ts = "2026-04-01T00:00:00Z"
                raw_events.append({
                    "event": "dispatch_start",
                    "ts": start_ts,
                    "feature": rec["feature"],
                    "complexity": rec.get("tier", "simple"),
                    "criticality": "high",
                    "model": rec.get("model", "sonnet"),
                    "effort": "high",
                    "max_turns": 20,
                    "max_budget_usd": 10.0,
                })
                raw_events.append({
                    "event": "dispatch_error",
                    "ts": rec.get("ts", "2026-04-01T00:01:00Z"),
                    "feature": rec["feature"],
                    "error_type": rec.get("error_type", "unknown"),
                    "error_detail": "test error",
                })
            else:
                start_ts = "2026-04-01T00:00:00Z"
                raw_events.append({
                    "event": "dispatch_start",
                    "ts": start_ts,
                    "feature": rec["feature"],
                    "complexity": rec.get("tier", "simple"),
                    "criticality": "high",
                    "model": rec.get("model", "sonnet"),
                    "effort": "high",
                    "max_turns": 20,
                    "max_budget_usd": 10.0,
                })
                raw_events.append({
                    "event": "dispatch_complete",
                    "ts": rec.get("ts", "2026-04-01T00:01:00Z"),
                    "feature": rec["feature"],
                    "cost_usd": rec.get("cost_usd"),
                    "num_turns": rec.get("num_turns"),
                    "duration_ms": 1000,
                })

        log_path = lifecycle_dir / "pipeline-events.log"
        log_path.write_text(
            "\n".join(_json.dumps(e) for e in raw_events) + "\n",
            encoding="utf-8",
        )
        return tmp_path

    # ------------------------------------------------------------------
    # (a) Populated aggregates → stdout contains "(estimated)" and each
    #     bucket key
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_populated_aggregates(self):
        """Populated aggregates: stdout contains '(estimated)' header and
        each bucket key in some form."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._make_root_with_aggregates(
                Path(tmpdir),
                [
                    {
                        "feature": "feat-a",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "complete",
                        "cost_usd": 1.5,
                        "num_turns": 5,
                        "ts": "2026-04-01T00:01:00Z",
                    },
                ],
            )
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch"]
            )
        self.assertIn("(estimated)", output)
        self.assertIn("sonnet", output)
        self.assertIn("simple", output)

    # ------------------------------------------------------------------
    # (b) Empty aggregates → stdout contains "No dispatch data found"
    #     and exit 0
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_empty_aggregates(self):
        """Empty aggregates (no pipeline-events.log): stdout contains
        'No dispatch data found'."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lifecycle_dir = root / "lifecycle"
            lifecycle_dir.mkdir(parents=True, exist_ok=True)
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch"]
            )
        self.assertIn("No dispatch data found", output)

    # ------------------------------------------------------------------
    # (c) --since 2099-01-01 → stdout contains "No dispatch data found
    #     after 2099-01-01"
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_future_since(self):
        """--since 2099-01-01 (far future): stdout contains
        'No dispatch data found after 2099-01-01'."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lifecycle_dir = root / "lifecycle"
            lifecycle_dir.mkdir(parents=True, exist_ok=True)
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch", "--since", "2099-01-01"]
            )
        self.assertIn("No dispatch data found after 2099-01-01", output)

    # ------------------------------------------------------------------
    # (d) Populated + --since 2026-04-18 → stdout contains the window
    #     header line
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_since_window_header(self):
        """--since 2026-04-18 with populated aggregates: stdout contains
        the window header."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._make_root_with_aggregates(
                Path(tmpdir),
                [
                    {
                        "feature": "feat-a",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "complete",
                        "cost_usd": 1.0,
                        "num_turns": 4,
                        "ts": "2026-04-18T01:00:00Z",
                    },
                ],
            )
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch", "--since", "2026-04-18"]
            )
        self.assertIn("Window: since 2026-04-18", output)
        self.assertIn("per-dispatch aggregates only; per-feature metrics are all-time", output)

    # ------------------------------------------------------------------
    # (e) Aggregates with 2 untiered records → stdout contains
    #     "⚠ 2 dispatches had no matching dispatch_start"
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_untiered_orphan_banner(self):
        """2 untiered records: stdout contains the orphan banner with
        the correct count."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._make_root_with_aggregates(
                Path(tmpdir),
                [
                    {
                        "feature": "feat-orphan-1",
                        "model": None,
                        "tier": None,
                        "outcome": "complete",
                        "cost_usd": 1.0,
                        "num_turns": 3,
                        "ts": "2026-04-01T00:01:00Z",
                        "untiered": True,
                    },
                    {
                        "feature": "feat-orphan-2",
                        "model": None,
                        "tier": None,
                        "outcome": "complete",
                        "cost_usd": 2.0,
                        "num_turns": 5,
                        "ts": "2026-04-01T00:02:00Z",
                        "untiered": True,
                    },
                ],
            )
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch"]
            )
        self.assertIn("2 dispatches had no matching dispatch_start", output)

    # ------------------------------------------------------------------
    # (f) Bucket with errors → error_counts_summary column renders
    #     the condensed string
    # ------------------------------------------------------------------

    def test_report_tier_dispatch_error_counts_summary(self):
        """Bucket with errors: error_counts_summary column shows condensed
        string like 'timeout:3,rate_limit:1'."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._make_root_with_aggregates(
                Path(tmpdir),
                [
                    {
                        "feature": "feat-e1",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "error",
                        "error_type": "timeout",
                        "ts": "2026-04-01T00:01:00Z",
                    },
                    {
                        "feature": "feat-e2",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "error",
                        "error_type": "timeout",
                        "ts": "2026-04-01T00:01:01Z",
                    },
                    {
                        "feature": "feat-e3",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "error",
                        "error_type": "timeout",
                        "ts": "2026-04-01T00:01:02Z",
                    },
                    {
                        "feature": "feat-e4",
                        "model": "sonnet",
                        "tier": "simple",
                        "outcome": "error",
                        "error_type": "rate_limit",
                        "ts": "2026-04-01T00:01:03Z",
                    },
                ],
            )
            output = self._run_report(
                ["--root", str(root), "--report", "tier-dispatch"]
            )
        self.assertIn("timeout:3", output)
        self.assertIn("rate_limit:1", output)


if __name__ == "__main__":
    unittest.main()
