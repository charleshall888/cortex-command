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

    def _start(self, feature, complexity="complex", model="opus", skill="implement", ts="2026-04-01T00:00:00Z"):
        from cortex_command.pipeline.dispatch import resolve_effort
        criticality = "high"
        return {
            "event": "dispatch_start",
            "ts": ts,
            "feature": feature,
            "complexity": complexity,
            "criticality": criticality,
            "model": model,
            "skill": skill,
            "effort": resolve_effort(complexity, criticality, skill, model),
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        bucket = result["sonnet,simple,legacy-effort"]
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        bucket = result["sonnet,simple,legacy-effort"]
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

        # Fixture's dispatch_start carries effort="xhigh"; bucket key reflects it.
        self.assertIn("opus,complex,xhigh", result)
        bucket = result["opus,complex,xhigh"]
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        bucket = result["sonnet,simple,legacy-effort"]
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        bucket = result["sonnet,simple,legacy-effort"]
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        self.assertIn("opus,complex,legacy-effort", result)
        self.assertEqual(result["sonnet,simple,legacy-effort"]["n_completes"], 2)
        self.assertEqual(result["opus,complex,legacy-effort"]["n_completes"], 1)
        # Buckets don't bleed into each other
        self.assertNotEqual(
            result["sonnet,simple,legacy-effort"]["estimated_cost_usd_mean"],
            result["opus,complex,legacy-effort"]["estimated_cost_usd_mean"],
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

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("sonnet,simple,legacy-effort", result)
        bucket = result["sonnet,simple,legacy-effort"]
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


class TestSkillTierDispatchAggregates(unittest.TestCase):
    """Tests for compute_skill_tier_dispatch_aggregates.

    Exercises the conditional bucket-key behavior:
        * non-review-fix skills group as "<skill>,<tier>"
        * review-fix groups as "<skill>,<tier>,<cycle>" (or
          "<skill>,<tier>,legacy-cycle" when cycle is absent)
        * historical events without a skill field bucket as "legacy,<tier>"
    """

    def _paired_complete(
        self,
        skill,
        tier,
        cost_usd,
        num_turns,
        model="sonnet",
        cycle=None,
        feature="feat-x",
        ts="2026-04-01T00:01:00Z",
        include_skill=True,
    ):
        """Build one paired-dispatch record (outcome=complete) directly.

        Mirrors :class:`TestModelTierAggregates._make_complete` but adds the
        skill/cycle keys that the new aggregator reads.  When
        ``include_skill=False``, the ``skill`` key is omitted entirely so the
        legacy-bucket behavior can be exercised.
        """
        rec = {
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
        if include_skill:
            rec["skill"] = skill
        if cycle is not None:
            rec["cycle"] = cycle
        return rec

    # ------------------------------------------------------------------
    # (a) Single non-review-fix skill: bucket key is "<skill>,<tier>"
    # ------------------------------------------------------------------

    def test_single_bucket_grouping_non_review_fix(self):
        """Three implement/simple completes group into a single
        'implement,simple' bucket with n_completes=3 and correct cost mean.
        Also asserts the aggregator returns an empty dict for empty input,
        confirming there are no implicit/unconditional bucket keys.
        """
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        # Sanity: empty input → no buckets.
        self.assertEqual(compute_skill_tier_dispatch_aggregates([]), {})

        paired = [
            self._paired_complete("implement", "simple", cost_usd=1.0, num_turns=4, feature="f1"),
            self._paired_complete("implement", "simple", cost_usd=2.0, num_turns=6, feature="f2"),
            self._paired_complete("implement", "simple", cost_usd=3.0, num_turns=8, feature="f3"),
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("implement,simple,legacy-effort", result)
        # No four-dimensional cycle key for non-review-fix skill.
        self.assertNotIn("implement,simple,legacy-effort,1", result)
        bucket = result["implement,simple,legacy-effort"]
        self.assertEqual(bucket["n_completes"], 3)
        self.assertAlmostEqual(bucket["estimated_cost_usd_mean"], 2.0)
        self.assertAlmostEqual(bucket["num_turns_mean"], 6.0)

    # ------------------------------------------------------------------
    # (b) Multi-bucket grouping: distinct skills produce distinct buckets
    # ------------------------------------------------------------------

    def test_multi_bucket_grouping_across_skills(self):
        """Records spanning two non-review-fix skills produce two distinct
        buckets, each with its own n_completes."""
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        paired = [
            self._paired_complete("implement", "simple", cost_usd=1.0, num_turns=4, feature="i1"),
            self._paired_complete("implement", "simple", cost_usd=2.0, num_turns=5, feature="i2"),
            self._paired_complete("conflict-repair", "complex", cost_usd=10.0, num_turns=20,
                                  model="opus", feature="c1"),
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("implement,simple,legacy-effort", result)
        self.assertIn("conflict-repair,complex,legacy-effort", result)
        self.assertEqual(result["implement,simple,legacy-effort"]["n_completes"], 2)
        self.assertEqual(result["conflict-repair,complex,legacy-effort"]["n_completes"], 1)
        # Buckets do not bleed into each other.
        self.assertNotEqual(
            result["implement,simple,legacy-effort"]["estimated_cost_usd_mean"],
            result["conflict-repair,complex,legacy-effort"]["estimated_cost_usd_mean"],
        )

    # ------------------------------------------------------------------
    # (c) review-fix cycle disentanglement: cycle 1 vs cycle 2 → two buckets
    # ------------------------------------------------------------------

    def test_review_fix_cycle_disentanglement(self):
        """Two review-fix paired records at the SAME tier — one with cycle=1,
        one with cycle=2 — produce two distinct four-dimensional buckets
        (skill,tier,effort,cycle), not a single collapsed bucket."""
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        paired = [
            self._paired_complete("review-fix", "simple", cost_usd=1.0, num_turns=4,
                                  cycle=1, feature="rf1"),
            self._paired_complete("review-fix", "simple", cost_usd=2.0, num_turns=6,
                                  cycle=2, feature="rf2"),
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("review-fix,simple,legacy-effort,1", result)
        self.assertIn("review-fix,simple,legacy-effort,2", result)
        review_fix_keys = [k for k in result if k.startswith("review-fix,")]
        self.assertEqual(len(review_fix_keys), 2)
        # Each cycle bucket holds exactly one record.
        self.assertEqual(result["review-fix,simple,legacy-effort,1"]["n_completes"], 1)
        self.assertEqual(result["review-fix,simple,legacy-effort,2"]["n_completes"], 1)

    # ------------------------------------------------------------------
    # (d) review-fix legacy-cycle bucketing: missing cycle on review-fix
    # ------------------------------------------------------------------

    def test_review_fix_legacy_cycle_bucketing(self):
        """A review-fix record without a cycle field buckets as
        '<skill>,<tier>,<effort>,legacy-cycle' (the spec's escape hatch for
        historical review-fix events emitted before the cycle field was added).
        Records synthesized without an effort field bucket as legacy-effort."""
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        paired = [
            self._paired_complete("review-fix", "simple", cost_usd=1.5, num_turns=5,
                                  cycle=None, feature="rf-legacy"),
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        self.assertIn("review-fix,simple,legacy-effort,legacy-cycle", result)
        # Not bucketed under the cycle-1 or cycle-2 keys.
        self.assertNotIn("review-fix,simple,legacy-effort,1", result)
        self.assertNotIn("review-fix,simple,legacy-effort,2", result)
        self.assertEqual(
            result["review-fix,simple,legacy-effort,legacy-cycle"]["n_completes"], 1,
        )

    # ------------------------------------------------------------------
    # (e) Missing-skill historical event: bucketed as "legacy,<tier>"
    # ------------------------------------------------------------------

    def test_legacy_bucket_for_missing_skill(self):
        """A paired record whose start event lacked the skill field buckets
        as 'legacy,<tier>,<effort>' — NOT as 'unknown' (which would collide
        with the existing untiered sentinel) and NOT as the bare string 'legacy'.

        The fixture is constructed directly (not via :func:`_start`) so the
        ``skill`` key is genuinely absent rather than defaulting to
        ``"implement"`` — exercises the historical-event compatibility path
        that the aggregator must handle for pre-instrumentation logs.
        Records synthesized without an effort field bucket as legacy-effort.
        """
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        paired = [
            self._paired_complete(
                skill=None,  # ignored when include_skill=False
                tier="simple",
                cost_usd=0.75,
                num_turns=3,
                feature="legacy-feat",
                include_skill=False,
            ),
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        legacy_keys = [k for k in result if k.startswith("legacy,")]
        self.assertTrue(
            any(k.startswith("legacy,") for k in result),
            f"Expected a key starting with 'legacy,'; got {sorted(result.keys())}",
        )
        # Must be the bucket-key-shaped form 'legacy,<tier>,<effort>', not bare 'legacy'.
        self.assertIn("legacy,simple,legacy-effort", result)
        self.assertNotIn("legacy", result)
        self.assertEqual(len(legacy_keys), 1)
        self.assertEqual(result["legacy,simple,legacy-effort"]["n_completes"], 1)

    # ------------------------------------------------------------------
    # (f) p95 suppression below the 30-complete threshold
    # ------------------------------------------------------------------

    def test_p95_suppression_below_threshold(self):
        """A bucket with n_completes < 30 has p95_suppressed=True,
        num_turns_p95=None, and max_turns_observed set to the largest
        observed num_turns (inheriting the model-tier aggregator's rule)."""
        from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates
        paired = [
            self._paired_complete("implement", "simple",
                                  cost_usd=float(i), num_turns=i + 1,
                                  feature=f"feat-{i}")
            for i in range(5)
        ]
        result = compute_skill_tier_dispatch_aggregates(paired)

        # Records synthesized without an effort field bucket as legacy-effort.
        self.assertIn("implement,simple,legacy-effort", result)
        bucket = result["implement,simple,legacy-effort"]
        self.assertEqual(bucket["n_completes"], 5)
        self.assertTrue(bucket["p95_suppressed"])
        self.assertIsNone(bucket["num_turns_p95"])
        self.assertEqual(bucket["max_turns_observed"], 5)


class TestPairAggregatorEndToEnd(unittest.TestCase):
    """End-to-end coverage of the production data flow:
    raw events -> ``pair_dispatch_events`` -> ``compute_skill_tier_dispatch_aggregates``.

    These tests guard the integration boundary that the unit tests in
    :class:`TestSkillTierDispatchAggregates` deliberately bypass.  Those tests
    construct paired records directly with explicit ``skill``/``cycle`` keys
    to test the aggregator in isolation; this class instead synthesizes raw
    ``dispatch_start`` / ``dispatch_complete`` events and runs them through
    the real pairing layer.  Without ``skill``/``cycle`` propagation in
    :func:`pair_dispatch_events`, every paired record buckets as
    ``legacy,<tier>`` regardless of what the new instrumentation emits — this
    test class catches that regression class.
    """

    def _start(self, feature, skill="implement", complexity="simple",
               model="sonnet", cycle=None, ts="2026-04-01T00:00:00Z"):
        from cortex_command.pipeline.dispatch import resolve_effort
        criticality = "high"
        evt = {
            "event": "dispatch_start",
            "ts": ts,
            "feature": feature,
            "complexity": complexity,
            "criticality": criticality,
            "model": model,
            "skill": skill,
            "effort": resolve_effort(complexity, criticality, skill, model),
            "max_turns": 30,
            "max_budget_usd": 50.0,
        }
        if cycle is not None:
            evt["cycle"] = cycle
        return evt

    def _complete(self, feature, cost_usd=1.0, num_turns=4,
                  ts="2026-04-01T00:01:00Z"):
        return {
            "event": "dispatch_complete",
            "ts": ts,
            "feature": feature,
            "cost_usd": cost_usd,
            "duration_ms": 5000,
            "num_turns": num_turns,
        }

    def test_pair_propagates_skill_to_aggregator_non_review_fix(self):
        """A dispatch_start carrying skill="implement" + matching complete,
        run through pair_dispatch_events then compute_skill_tier_dispatch_aggregates,
        produces an "implement,simple,<effort>" bucket key — NOT a legacy-skill bucket.

        The effort axis is resolved by the start helper via resolve_effort(),
        so the bucket key picks up the matrix-derived effort suffix.
        """
        from cortex_command.pipeline.dispatch import resolve_effort
        from cortex_command.pipeline.metrics import (
            compute_skill_tier_dispatch_aggregates,
            pair_dispatch_events,
        )
        expected_effort = resolve_effort("simple", "high", "implement", "sonnet")
        expected_key = f"implement,simple,{expected_effort}"
        events = [
            self._start("feat-a", skill="implement", complexity="simple",
                        model="sonnet"),
            self._complete("feat-a", cost_usd=1.5, num_turns=5),
        ]
        paired = pair_dispatch_events(events)
        result = compute_skill_tier_dispatch_aggregates(paired)

        self.assertIn(
            expected_key, result,
            f"Expected {expected_key!r} bucket; got {sorted(result.keys())}",
        )
        self.assertNotIn(f"legacy,simple,{expected_effort}", result)
        self.assertEqual(result[expected_key]["n_completes"], 1)

    def test_pair_propagates_skill_and_cycle_to_aggregator_review_fix(self):
        """A dispatch_start with skill="review-fix", cycle=2 + matching complete
        produces a 'review-fix,simple,<effort>,2' four-dimensional bucket key
        after the full pair -> aggregate pipeline.

        The effort axis is resolved by the start helper via resolve_effort(),
        so the bucket key picks up the matrix-derived effort suffix between
        tier and cycle.
        """
        from cortex_command.pipeline.dispatch import resolve_effort
        from cortex_command.pipeline.metrics import (
            compute_skill_tier_dispatch_aggregates,
            pair_dispatch_events,
        )
        expected_effort = resolve_effort("simple", "high", "review-fix", "sonnet")
        expected_key = f"review-fix,simple,{expected_effort},2"
        events = [
            self._start("feat-rf", skill="review-fix", complexity="simple",
                        model="sonnet", cycle=2),
            self._complete("feat-rf", cost_usd=2.0, num_turns=6),
        ]
        paired = pair_dispatch_events(events)
        result = compute_skill_tier_dispatch_aggregates(paired)

        self.assertIn(
            expected_key, result,
            f"Expected {expected_key!r} bucket; got {sorted(result.keys())}",
        )
        self.assertNotIn(f"review-fix,simple,{expected_effort},1", result)
        self.assertNotIn(f"review-fix,simple,{expected_effort},legacy-cycle", result)
        self.assertNotIn(f"legacy,simple,{expected_effort}", result)
        self.assertEqual(result[expected_key]["n_completes"], 1)


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
        lifecycle_dir = tmp_path / "cortex" / "lifecycle"
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
                from cortex_command.pipeline.dispatch import resolve_effort
                start_ts = "2026-04-01T00:00:00Z"
                _complexity = rec.get("tier", "simple")
                _criticality = rec.get("criticality", "high")
                _skill = rec.get("skill", "implement")
                _model = rec.get("model", "sonnet")
                raw_events.append({
                    "event": "dispatch_start",
                    "ts": start_ts,
                    "feature": rec["feature"],
                    "complexity": _complexity,
                    "criticality": _criticality,
                    "model": _model,
                    "effort": resolve_effort(_complexity, _criticality, _skill, _model),
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
                from cortex_command.pipeline.dispatch import resolve_effort
                start_ts = "2026-04-01T00:00:00Z"
                _complexity = rec.get("tier", "simple")
                _criticality = rec.get("criticality", "high")
                _skill = rec.get("skill", "implement")
                _model = rec.get("model", "sonnet")
                raw_events.append({
                    "event": "dispatch_start",
                    "ts": start_ts,
                    "feature": rec["feature"],
                    "complexity": _complexity,
                    "criticality": _criticality,
                    "model": _model,
                    "effort": resolve_effort(_complexity, _criticality, _skill, _model),
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
            lifecycle_dir = root / "cortex" / "lifecycle"
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
            lifecycle_dir = root / "cortex" / "lifecycle"
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


def test_aggregator_buckets_by_effort():
    """Synthesizing dispatch events at multiple effort levels for the same
    (model, tier, skill) lands them in distinct aggregator buckets.

    Module-level (non-class) test per spec verification command:
    ``pytest test_metrics.py::test_aggregator_buckets_by_effort``.

    Builds three dispatch_start/dispatch_complete pairs that are identical
    except for ``effort`` (``high`` vs ``xhigh`` vs ``max``), runs them
    through the production ``pair_dispatch_events`` →
    ``compute_skill_tier_dispatch_aggregates`` (and
    ``compute_model_tier_dispatch_aggregates``) flow, and asserts that the
    three records do NOT collapse into a single bucket.  Without effort in
    the bucket key, all three would land in ``implement,complex`` /
    ``opus,complex`` and the cost regression signal post-flip would be
    invisible.
    """
    from cortex_command.pipeline.metrics import (
        compute_model_tier_dispatch_aggregates,
        compute_skill_tier_dispatch_aggregates,
        pair_dispatch_events,
    )

    def _start(feature, effort, ts):
        return {
            "event": "dispatch_start",
            "ts": ts,
            "feature": feature,
            "complexity": "complex",
            "criticality": "high",
            "model": "opus",
            "skill": "implement",
            "effort": effort,
            "max_turns": 30,
            "max_budget_usd": 50.0,
        }

    def _complete(feature, cost_usd, num_turns, ts):
        return {
            "event": "dispatch_complete",
            "ts": ts,
            "feature": feature,
            "cost_usd": cost_usd,
            "duration_ms": 5000,
            "num_turns": num_turns,
        }

    events = [
        _start("feat-high", "high", "2026-04-01T00:00:00Z"),
        _complete("feat-high", 1.0, 5, "2026-04-01T00:01:00Z"),
        _start("feat-xhigh", "xhigh", "2026-04-01T00:02:00Z"),
        _complete("feat-xhigh", 3.0, 10, "2026-04-01T00:03:00Z"),
        _start("feat-max", "max", "2026-04-01T00:04:00Z"),
        _complete("feat-max", 5.0, 15, "2026-04-01T00:05:00Z"),
    ]

    paired = pair_dispatch_events(events)
    assert len(paired) == 3
    # Paired records carry the effort field through.
    efforts_in_paired = sorted(r["effort"] for r in paired)
    assert efforts_in_paired == ["high", "max", "xhigh"]

    skill_aggs = compute_skill_tier_dispatch_aggregates(paired)
    # The three records, identical except for effort, must land in three
    # distinct buckets — not a single collapsed (skill, tier) bucket.
    assert "implement,complex,high" in skill_aggs, sorted(skill_aggs.keys())
    assert "implement,complex,xhigh" in skill_aggs, sorted(skill_aggs.keys())
    assert "implement,complex,max" in skill_aggs, sorted(skill_aggs.keys())
    # Pre-effort-axis bucket key must NOT exist (would mean effort was dropped).
    assert "implement,complex" not in skill_aggs
    # Each bucket holds exactly one complete.
    assert skill_aggs["implement,complex,high"]["n_completes"] == 1
    assert skill_aggs["implement,complex,xhigh"]["n_completes"] == 1
    assert skill_aggs["implement,complex,max"]["n_completes"] == 1
    # Cost means must differ (each bucket holds a different cost record).
    assert skill_aggs["implement,complex,high"]["estimated_cost_usd_mean"] == 1.0
    assert skill_aggs["implement,complex,xhigh"]["estimated_cost_usd_mean"] == 3.0
    assert skill_aggs["implement,complex,max"]["estimated_cost_usd_mean"] == 5.0

    model_aggs = compute_model_tier_dispatch_aggregates(paired)
    # Model-tier aggregator also splits by effort.
    assert "opus,complex,high" in model_aggs, sorted(model_aggs.keys())
    assert "opus,complex,xhigh" in model_aggs, sorted(model_aggs.keys())
    assert "opus,complex,max" in model_aggs, sorted(model_aggs.keys())
    assert "opus,complex" not in model_aggs


def test_metrics_json_exposes_effort_bucket(tmp_path):
    """A realistic mix of pre-flip and post-flip dispatch event records,
    fed through the full ``main()`` pipeline that writes ``metrics.json``,
    exposes per-effort cost means in the operator-facing slice.

    Module-level (non-class) test per spec verification command:
    ``pytest test_metrics.py::test_metrics_json_exposes_effort_bucket``.

    Pre-flip records use ``effort="high"``; post-flip records use
    ``effort="xhigh"``.  Both share ``(model="opus", tier="complex",
    skill="implement")``.  After ``main()`` writes ``cortex/lifecycle/metrics.json``,
    the JSON's ``skill_tier_dispatch_aggregates`` and
    ``model_tier_dispatch_aggregates`` slices must expose distinct
    per-effort buckets so an operator can compute the >2× cost-regression
    rollback trigger from §13.
    """
    import json as _json

    from cortex_command.pipeline.metrics import main

    lifecycle_dir = tmp_path / "cortex" / "lifecycle"
    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    def _start(feature, effort, ts):
        return {
            "event": "dispatch_start",
            "ts": ts,
            "feature": feature,
            "complexity": "complex",
            "criticality": "high",
            "model": "opus",
            "skill": "implement",
            "effort": effort,
            "max_turns": 30,
            "max_budget_usd": 50.0,
        }

    def _complete(feature, cost_usd, num_turns, ts):
        return {
            "event": "dispatch_complete",
            "ts": ts,
            "feature": feature,
            "cost_usd": cost_usd,
            "duration_ms": 5000,
            "num_turns": num_turns,
        }

    # Mix of pre-flip (high) and post-flip (xhigh) records.  Two of each so
    # the cost mean differs from any single record's cost.
    events = [
        # Pre-flip: high effort, lower costs.
        _start("pre-1", "high", "2026-04-01T00:00:00Z"),
        _complete("pre-1", 1.0, 5, "2026-04-01T00:01:00Z"),
        _start("pre-2", "high", "2026-04-01T00:02:00Z"),
        _complete("pre-2", 2.0, 7, "2026-04-01T00:03:00Z"),
        # Post-flip: xhigh effort, higher costs.
        _start("post-1", "xhigh", "2026-04-02T00:00:00Z"),
        _complete("post-1", 4.0, 10, "2026-04-02T00:01:00Z"),
        _start("post-2", "xhigh", "2026-04-02T00:02:00Z"),
        _complete("post-2", 6.0, 12, "2026-04-02T00:03:00Z"),
    ]

    log_path = lifecycle_dir / "pipeline-events.log"
    log_path.write_text(
        "\n".join(_json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )

    # Run the full metrics pipeline; main() writes metrics.json under
    # tmp_path/lifecycle/.
    main(["--root", str(tmp_path)])

    metrics_path = lifecycle_dir / "metrics.json"
    assert metrics_path.exists(), f"metrics.json not written at {metrics_path}"
    metrics_data = _json.loads(metrics_path.read_text(encoding="utf-8"))

    # The operator-facing slice must surface per-effort buckets.
    skill_aggs = metrics_data["skill_tier_dispatch_aggregates"]
    assert "implement,complex,high" in skill_aggs, sorted(skill_aggs.keys())
    assert "implement,complex,xhigh" in skill_aggs, sorted(skill_aggs.keys())
    # Per-effort cost means are distinct.
    pre_mean = skill_aggs["implement,complex,high"]["estimated_cost_usd_mean"]
    post_mean = skill_aggs["implement,complex,xhigh"]["estimated_cost_usd_mean"]
    assert pre_mean == 1.5  # mean of 1.0 and 2.0
    assert post_mean == 5.0  # mean of 4.0 and 6.0
    assert post_mean > pre_mean

    # Model-tier slice mirrors the per-effort split.
    model_aggs = metrics_data["model_tier_dispatch_aggregates"]
    assert "opus,complex,high" in model_aggs, sorted(model_aggs.keys())
    assert "opus,complex,xhigh" in model_aggs, sorted(model_aggs.keys())
    assert model_aggs["opus,complex,high"]["estimated_cost_usd_mean"] == 1.5
    assert model_aggs["opus,complex,xhigh"]["estimated_cost_usd_mean"] == 5.0


def test_plan_comparison_v2_round_trip(tmp_path):
    """A v2 ``plan_comparison`` event written to events.log and read back
    through ``parse_events`` round-trips with all five new v2 fields and
    ``schema_version: 2`` intact.

    The v2 schema is additive: it preserves all v1 fields (``ts``,
    ``event``, ``feature``, ``variants``, ``selected``) and adds five new
    fields (``selection_rationale``, ``selector_confidence``,
    ``position_swap_check_result``, ``disposition``, ``operator_choice``)
    plus ``schema_version: 2``.  ``parse_events`` is a generic JSONL
    parser — it must surface every key present on the JSON line without
    dropping or coercing the new fields.
    """
    import json as _json

    from cortex_command.pipeline.metrics import parse_events

    v2_event = {
        "ts": "2026-05-04T12:34:56Z",
        "event": "plan_comparison",
        "feature": "feat-v2",
        "variants": ["A", "B", "C"],
        "selected": "B",
        "selection_rationale": "Variant B isolates the synthesizer prompt fragment cleanly.",
        "selector_confidence": "high",
        "position_swap_check_result": "agreed",
        "disposition": "rubber_stamp",
        "operator_choice": None,
        "schema_version": 2,
    }
    log_path = tmp_path / "events.log"
    log_path.write_text(_json.dumps(v2_event) + "\n", encoding="utf-8")

    parsed = parse_events(log_path)

    assert len(parsed) == 1, f"Expected 1 parsed event; got {len(parsed)}"
    evt = parsed[0]
    # All v1 fields preserved.
    assert evt["ts"] == "2026-05-04T12:34:56Z"
    assert evt["event"] == "plan_comparison"
    assert evt["feature"] == "feat-v2"
    assert evt["variants"] == ["A", "B", "C"]
    assert evt["selected"] == "B"
    # All five new v2 fields preserved on the parsed event dict.
    assert evt["selection_rationale"] == "Variant B isolates the synthesizer prompt fragment cleanly."
    assert evt["selector_confidence"] == "high"
    assert evt["position_swap_check_result"] == "agreed"
    assert evt["disposition"] == "rubber_stamp"
    assert evt["operator_choice"] is None
    # schema_version field round-trips intact.
    assert evt["schema_version"] == 2


def test_v2_tolerance_downstream_filter_unaffected(tmp_path):
    """A mixed events.log containing one v2 ``plan_comparison`` event and
    one ``feature_complete`` event: callers that filter the parsed list
    by ``event == "feature_complete"`` get exactly the ``feature_complete``
    event back — the v2 ``plan_comparison`` event does not contaminate
    name-keyed filters.

    Adjacent readers (``cortex_command/dashboard/data.py``,
    ``claude/statusline.sh``, ``bin/cortex-archive-sample-select``,
    ``hooks/cortex-scan-lifecycle.sh``) all key on the ``event`` field
    name; this test guards that downstream filtering invariant against
    the additive v2 schema.
    """
    import json as _json

    from cortex_command.pipeline.metrics import parse_events

    v2_plan_comparison = {
        "ts": "2026-05-04T10:00:00Z",
        "event": "plan_comparison",
        "feature": "feat-mixed",
        "variants": ["A", "B"],
        "selected": "A",
        "selection_rationale": "A is simpler.",
        "selector_confidence": "medium",
        "position_swap_check_result": "agreed",
        "disposition": "auto_select",
        "operator_choice": None,
        "schema_version": 2,
    }
    feature_complete = {
        "ts": "2026-05-04T11:00:00Z",
        "event": "feature_complete",
        "feature": "feat-mixed",
    }
    log_path = tmp_path / "events.log"
    log_path.write_text(
        _json.dumps(v2_plan_comparison) + "\n" + _json.dumps(feature_complete) + "\n",
        encoding="utf-8",
    )

    parsed = parse_events(log_path)

    # Sanity: both events parsed.
    assert len(parsed) == 2

    # Downstream-filter invariant: filtering by event == "feature_complete"
    # returns exactly the feature_complete event, no v2 contamination.
    filtered = [e for e in parsed if e["event"] == "feature_complete"]
    assert len(filtered) == 1, f"Expected exactly 1 feature_complete event; got {len(filtered)}"
    assert filtered[0]["event"] == "feature_complete"
    assert filtered[0]["feature"] == "feat-mixed"
    # No v2-only field bled into the filtered slice.
    assert "selection_rationale" not in filtered[0]
    assert "schema_version" not in filtered[0]


class TestExtractVerdict(unittest.TestCase):
    """Tests for the closed-enum alias lookup helper ``_extract_verdict``.

    Locks in the four-case contract from spec R11:
      (a) canonical ``"verdict"`` is returned as-is,
      (b) alias-only events (``"review_verdict"``) resolve to that value,
      (c) events missing all aliases return ``None``,
      (d) multi-alias events (both ``"verdict"`` and ``"review_verdict"``
          present) deterministically resolve to canonical per the tuple
          ordering of ``_VERDICT_FIELD_ALIASES``.
    """

    def _fn(self, event):
        from cortex_command.pipeline.metrics import _extract_verdict
        return _extract_verdict(event)

    def test_canonical_verdict_returned(self):
        """An event with canonical ``"verdict"`` returns its value."""
        event = {"event": "review_verdict", "verdict": "APPROVED"}
        self.assertEqual(self._fn(event), "APPROVED")

    def test_alias_review_verdict_only(self):
        """An event with only the ``"review_verdict"`` alias resolves to it."""
        event = {"event": "review_verdict", "review_verdict": "CHANGES_REQUESTED"}
        self.assertEqual(self._fn(event), "CHANGES_REQUESTED")

    def test_no_alias_returns_none(self):
        """An event missing every alias returns ``None``."""
        event = {"event": "review_verdict", "feature": "feat-x"}
        self.assertIsNone(self._fn(event))

    def test_canonical_wins_over_alias(self):
        """When both ``"verdict"`` and ``"review_verdict"`` are present,
        tuple-ordering precedence resolves to the canonical field."""
        event = {
            "event": "review_verdict",
            "verdict": "APPROVED",
            "review_verdict": "CHANGES_REQUESTED",
        }
        self.assertEqual(self._fn(event), "APPROVED")


if __name__ == "__main__":
    unittest.main()
