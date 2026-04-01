"""Unit tests for claude/dashboard/data.py.

Tests cover:
  - tail_jsonl: initial call returns last N lines and byte offset
  - tail_jsonl: second call with saved offset returns only new lines
  - tail_jsonl: malformed JSON lines are skipped
  - tail_jsonl: absent file returns ([], 0)
  - parse_plan_progress: checkbox counting
  - parse_plan_progress: absent file returns None
  - parse_backlog_counts: counts by status field from YAML frontmatter
  - parse_backlog_counts: skips malformed/missing frontmatter files
  - parse_overnight_state: returns None for absent path
  - parse_overnight_state: returns None for JSON decode error
  - parse_pipeline_state: returns None for absent path
  - parse_pipeline_state: returns None for JSON decode error
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude.dashboard.data import (
    _read_all_jsonl,
    build_swim_lane_data,
    compute_slow_flags,
    get_last_activity_ts,
    parse_backlog_counts,
    parse_feature_cost_delta,
    parse_feature_timestamps,
    parse_fleet_cards,
    parse_last_session,
    parse_metrics,
    parse_overnight_state,
    parse_pipeline_dispatch,
    parse_pipeline_state,
    parse_plan_progress,
    parse_round_timestamps,
    tail_jsonl,
)


# ---------------------------------------------------------------------------
# Tests: tail_jsonl
# ---------------------------------------------------------------------------

class TestTailJsonl(unittest.TestCase):
    """Tests for tail_jsonl byte-offset tracking."""

    def test_initial_call_returns_last_n_lines_and_offset(self):
        """Initial call (offset=0) returns last N lines and the file end offset."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            lines = [json.dumps({"i": i}) for i in range(10)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            events, offset = tail_jsonl(path, last_n=3)

            self.assertEqual(len(events), 3)
            self.assertEqual(events[0]["i"], 7)
            self.assertEqual(events[1]["i"], 8)
            self.assertEqual(events[2]["i"], 9)
            self.assertGreater(offset, 0)
            self.assertEqual(offset, path.stat().st_size)

    def test_second_call_with_offset_returns_only_new_lines(self):
        """Second call with saved offset returns only bytes written since the first call."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            initial_lines = [json.dumps({"i": i}) for i in range(5)]
            path.write_text("\n".join(initial_lines) + "\n", encoding="utf-8")

            events1, offset1 = tail_jsonl(path, last_n=200)
            self.assertEqual(len(events1), 5)
            self.assertGreater(offset1, 0)

            # Append new lines
            new_lines = [json.dumps({"i": i}) for i in range(5, 8)]
            with path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(new_lines) + "\n")

            events2, offset2 = tail_jsonl(path, offset=offset1)

            self.assertEqual(len(events2), 3)
            self.assertEqual(events2[0]["i"], 5)
            self.assertEqual(events2[1]["i"], 6)
            self.assertEqual(events2[2]["i"], 7)
            self.assertGreater(offset2, offset1)
            self.assertEqual(offset2, path.stat().st_size)

    def test_byte_offset_does_not_repeat_lines(self):
        """After a second call, a third call with the new offset returns empty when no new data."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(json.dumps({"x": 1}) + "\n", encoding="utf-8")

            _, offset1 = tail_jsonl(path, last_n=200)
            events2, offset2 = tail_jsonl(path, offset=offset1)

            self.assertEqual(events2, [])
            self.assertEqual(offset2, offset1)

    def test_malformed_json_lines_are_skipped(self):
        """Lines that are not valid JSON are silently skipped; valid lines returned."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            content = (
                json.dumps({"ok": 1}) + "\n"
                + "not json at all\n"
                + json.dumps({"ok": 2}) + "\n"
                + "{broken\n"
                + json.dumps({"ok": 3}) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            events, offset = tail_jsonl(path, last_n=200)

            self.assertEqual(len(events), 3)
            self.assertEqual([e["ok"] for e in events], [1, 2, 3])
            self.assertGreater(offset, 0)

    def test_absent_file_returns_empty_list_and_zero_offset(self):
        """When the file does not exist, tail_jsonl returns ([], 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.jsonl"

            events, offset = tail_jsonl(path)

            self.assertEqual(events, [])
            self.assertEqual(offset, 0)

    def test_empty_file_returns_empty_list_and_zero_offset(self):
        """An empty file returns ([], 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_bytes(b"")

            events, offset = tail_jsonl(path)

            self.assertEqual(events, [])
            self.assertEqual(offset, 0)

    def test_initial_call_with_more_lines_than_last_n(self):
        """Initial call respects last_n limit even when file has many more lines."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            lines = [json.dumps({"i": i}) for i in range(100)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            events, offset = tail_jsonl(path, last_n=5)

            self.assertEqual(len(events), 5)
            self.assertEqual(events[0]["i"], 95)
            self.assertEqual(events[4]["i"], 99)

    def test_non_dict_json_lines_are_skipped(self):
        """JSON values that are not dicts (arrays, strings, etc.) are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            content = (
                json.dumps({"ok": 1}) + "\n"
                + json.dumps([1, 2, 3]) + "\n"
                + json.dumps("a string") + "\n"
                + json.dumps({"ok": 2}) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            events, _ = tail_jsonl(path, last_n=200)

            self.assertEqual(len(events), 2)
            self.assertEqual([e["ok"] for e in events], [1, 2])


# ---------------------------------------------------------------------------
# Tests: parse_plan_progress
# ---------------------------------------------------------------------------

class TestParsePlanProgress(unittest.TestCase):
    """Tests for parse_plan_progress checkbox counting."""

    def test_returns_completed_and_total_for_mixed_checkboxes(self):
        """3 checked + 2 unchecked boxes -> (3, 5)."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feature_dir = lifecycle_dir / "my-feature"
            feature_dir.mkdir()
            plan = feature_dir / "plan.md"
            plan.write_text(
                "# Plan\n\n"
                "- [x] Task one\n"
                "- [x] Task two\n"
                "- [x] Task three\n"
                "- [ ] Task four\n"
                "- [ ] Task five\n",
                encoding="utf-8",
            )

            result = parse_plan_progress("my-feature", lifecycle_dir)

            self.assertEqual(result, (3, 5))

    def test_returns_none_for_absent_file(self):
        """Returns None when plan.md does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            (lifecycle_dir / "no-feature").mkdir()

            result = parse_plan_progress("no-feature", lifecycle_dir)

            self.assertIsNone(result)

    def test_returns_none_for_absent_feature_directory(self):
        """Returns None when the feature directory itself does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)

            result = parse_plan_progress("missing-feature", lifecycle_dir)

            self.assertIsNone(result)

    def test_case_insensitive_checked_boxes(self):
        """[X] (uppercase) is counted as completed."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feature_dir = lifecycle_dir / "feat"
            feature_dir.mkdir()
            (feature_dir / "plan.md").write_text(
                "- [X] Done\n- [x] Also done\n- [ ] Not done\n",
                encoding="utf-8",
            )

            result = parse_plan_progress("feat", lifecycle_dir)

            self.assertEqual(result, (2, 3))

    def test_all_completed(self):
        """All tasks checked -> (n, n)."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feature_dir = lifecycle_dir / "feat"
            feature_dir.mkdir()
            (feature_dir / "plan.md").write_text(
                "- [x] A\n- [x] B\n",
                encoding="utf-8",
            )

            result = parse_plan_progress("feat", lifecycle_dir)

            self.assertEqual(result, (2, 2))

    def test_no_checkboxes(self):
        """File with no checkboxes returns (0, 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feature_dir = lifecycle_dir / "feat"
            feature_dir.mkdir()
            (feature_dir / "plan.md").write_text(
                "# No checkboxes here\n",
                encoding="utf-8",
            )

            result = parse_plan_progress("feat", lifecycle_dir)

            self.assertEqual(result, (0, 0))


# ---------------------------------------------------------------------------
# Tests: parse_backlog_counts
# ---------------------------------------------------------------------------

class TestParseBacklogCounts(unittest.TestCase):
    """Tests for parse_backlog_counts YAML status extraction."""

    def _write_backlog_file(self, directory: Path, filename: str, frontmatter: str) -> None:
        """Helper to write a backlog file with YAML frontmatter."""
        content = f"---\n{frontmatter}---\n\nBody text.\n"
        (directory / filename).write_text(content, encoding="utf-8")

    def test_counts_by_status(self):
        """Counts items grouped by status field."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "001-alpha.md", "status: open\n")
            self._write_backlog_file(backlog_dir, "002-beta.md", "status: open\n")
            self._write_backlog_file(backlog_dir, "003-gamma.md", "status: done\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"backlog": 2, "complete": 1})

    def test_missing_status_defaults_to_open(self):
        """Items without a status field default to 'open'."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "001-item.md", "title: Something\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"backlog": 1})

    def test_skips_files_without_frontmatter(self):
        """Files without --- frontmatter are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            # File with no frontmatter
            (backlog_dir / "001-no-fm.md").write_text(
                "# Just a heading\nNo frontmatter here.\n",
                encoding="utf-8",
            )
            # File with valid frontmatter
            self._write_backlog_file(backlog_dir, "002-valid.md", "status: wip\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"wip": 1})

    def test_skips_files_with_unclosed_frontmatter(self):
        """Files with opening --- but no closing --- are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            (backlog_dir / "001-broken.md").write_text(
                "---\nstatus: open\n# No closing marker\n",
                encoding="utf-8",
            )
            self._write_backlog_file(backlog_dir, "002-good.md", "status: done\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"complete": 1})

    def test_absent_directory_returns_empty_dict(self):
        """Returns {} when the backlog directory does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp) / "nonexistent"

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {})

    def test_ignores_non_matching_filenames(self):
        """Only files matching [0-9]*-*.md are processed."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            # Should be ignored
            (backlog_dir / "README.md").write_text(
                "---\nstatus: open\n---\n",
                encoding="utf-8",
            )
            (backlog_dir / "notes.md").write_text(
                "---\nstatus: open\n---\n",
                encoding="utf-8",
            )
            # Should be counted
            self._write_backlog_file(backlog_dir, "001-valid.md", "status: active\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"active": 1})

    def test_status_with_quotes_is_stripped(self):
        """Quoted status values have their quotes stripped."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "001-a.md", 'status: "open"\n')
            self._write_backlog_file(backlog_dir, "002-b.md", "status: 'done'\n")

            result = parse_backlog_counts(backlog_dir)

            self.assertEqual(result, {"backlog": 1, "complete": 1})

    def test_empty_directory_returns_empty_dict(self):
        """Returns {} when the backlog directory exists but has no matching files."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_backlog_counts(Path(tmp))

            self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Tests: parse_overnight_state
# ---------------------------------------------------------------------------

class TestParseOvernightState(unittest.TestCase):
    """Tests for parse_overnight_state."""

    def test_returns_parsed_dict_for_valid_file(self):
        """Valid JSON file returns the parsed dict."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overnight-state.json"
            data = {"status": "running", "feature": "test-feat"}
            path.write_text(json.dumps(data), encoding="utf-8")

            result = parse_overnight_state(path)

            self.assertEqual(result, data)

    def test_returns_none_for_absent_path(self):
        """Returns None when the file does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.json"

            result = parse_overnight_state(path)

            self.assertIsNone(result)

    def test_returns_none_for_json_decode_error(self):
        """Returns None when the file contains invalid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overnight-state.json"
            path.write_text("{ not valid json }", encoding="utf-8")

            result = parse_overnight_state(path)

            self.assertIsNone(result)

    def test_returns_none_for_empty_file(self):
        """Returns None for an empty file (JSON decode error)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overnight-state.json"
            path.write_bytes(b"")

            result = parse_overnight_state(path)

            self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: parse_pipeline_state
# ---------------------------------------------------------------------------

class TestParsePipelineState(unittest.TestCase):
    """Tests for parse_pipeline_state."""

    def test_returns_parsed_dict_for_valid_file(self):
        """Valid JSON file returns the parsed dict."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline-state.json"
            data = {"phase": "implement", "task": 3}
            path.write_text(json.dumps(data), encoding="utf-8")

            result = parse_pipeline_state(path)

            self.assertEqual(result, data)

    def test_returns_none_for_absent_path(self):
        """Returns None when the file does not exist (normal no-pipeline state)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.json"

            result = parse_pipeline_state(path)

            self.assertIsNone(result)

    def test_returns_none_for_json_decode_error(self):
        """Returns None when the file contains invalid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline-state.json"
            path.write_text("not json", encoding="utf-8")

            result = parse_pipeline_state(path)

            self.assertIsNone(result)

    def test_returns_none_for_empty_file(self):
        """Returns None for an empty file (JSON decode error)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline-state.json"
            path.write_bytes(b"")

            result = parse_pipeline_state(path)

            self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: parse_fleet_cards
# ---------------------------------------------------------------------------

class TestParseFleetCards(unittest.TestCase):
    """Tests for parse_fleet_cards fleet card building."""

    def _overnight(self, features: dict) -> dict:
        return {"features": features}

    def _feature_start_event(self, slug: str, ts: str) -> dict:
        return {"event": "feature_start", "feature": slug, "ts": ts, "round": 1}

    def test_returns_card_for_running_feature(self):
        """One running feature produces one fleet card."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({"feat-a": {"status": "running"}})
            ts = "2026-02-26T10:00:00+00:00"
            events = [self._feature_start_event("feat-a", ts)]
            cards, _ = parse_fleet_cards(overnight, events, {}, Path(tmp), {})
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["slug"], "feat-a")

    def test_skips_non_running_features(self):
        """Features with status != 'running' are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({
                "feat-run": {"status": "running"},
                "feat-done": {"status": "merged"},
                "feat-pend": {"status": "pending"},
            })
            ts = "2026-02-26T10:00:00+00:00"
            events = [self._feature_start_event("feat-run", ts)]
            cards, _ = parse_fleet_cards(overnight, events, {}, Path(tmp), {})
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["slug"], "feat-run")

    def test_duration_str_is_non_empty_for_feature_with_start_event(self):
        """duration_str contains 'm' when a FEATURE_START event is present."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({"feat-a": {"status": "running"}})
            ts = "2026-02-26T10:00:00+00:00"
            events = [self._feature_start_event("feat-a", ts)]
            cards, _ = parse_fleet_cards(overnight, events, {}, Path(tmp), {})
            self.assertIn("m", cards[0]["duration_str"])

    def test_last_activity_not_dispatched_when_no_activity_file(self):
        """last_activity_ts is None when agent-activity.jsonl absent."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({"feat-a": {"status": "running"}})
            events: list = []
            cards, _ = parse_fleet_cards(overnight, events, {}, Path(tmp), {})
            self.assertIsNone(cards[0]["last_activity_ts"])

    def test_last_activity_shows_ts_when_activity_file_present(self):
        """last_activity_ts shows the ts from agent-activity.jsonl when present."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feat_dir = lifecycle_dir / "feat-a"
            feat_dir.mkdir()
            activity_ts = "2026-02-26T10:30:00+00:00"
            (feat_dir / "agent-activity.jsonl").write_text(
                json.dumps({"ts": activity_ts, "tool": "Read"}) + "\n",
                encoding="utf-8",
            )
            overnight = self._overnight({"feat-a": {"status": "running"}})
            events: list = []
            cards, _ = parse_fleet_cards(overnight, events, {}, lifecycle_dir, {})
            self.assertEqual(cards[0]["last_activity_ts"], activity_ts)

    def test_returns_empty_list_for_no_running_features(self):
        """Returns empty fleet when all features are non-running."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({"feat-a": {"status": "merged"}})
            cards, _ = parse_fleet_cards(overnight, [], {}, Path(tmp), {})
            self.assertEqual(cards, [])

    def test_offsets_passthrough(self):
        """new_offsets mirrors input agent_activity_offsets."""
        with tempfile.TemporaryDirectory() as tmp:
            overnight = self._overnight({})
            input_offsets = {"feat-x": 123}
            _, new_offsets = parse_fleet_cards(overnight, [], {}, Path(tmp), input_offsets)
            self.assertEqual(new_offsets, input_offsets)


# ---------------------------------------------------------------------------
# Tests: build_swim_lane_data
# ---------------------------------------------------------------------------

class TestBuildSwimLaneData(unittest.TestCase):
    """Tests for build_swim_lane_data swim lane construction."""

    def _make_events(self, n_features: int = 1) -> tuple[dict, list]:
        """Build minimal overnight + overnight_events for N features."""
        session_ts = "2026-02-26T09:00:00+00:00"
        features = {f"feat-{i}": {"status": "merged"} for i in range(n_features)}
        overnight = {"features": features}
        events: list[dict] = [{"event": "session_start", "ts": session_ts}]
        for i in range(n_features):
            events.append({
                "event": "feature_start",
                "feature": f"feat-{i}",
                "ts": f"2026-02-26T09:0{i}:00+00:00",
            })
        return overnight, events

    def test_correct_lane_count_for_n_features(self):
        """Returns one lane per feature in overnight."""
        overnight, events = self._make_events(5)
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertEqual(len(result["lanes"]), 5)

    def test_lane_events_populated_from_feature_start(self):
        """Each lane has at least one event from FEATURE_START."""
        overnight, events = self._make_events(1)
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertGreater(len(result["lanes"][0]["events"]), 0)

    def test_summary_mode_true_when_over_200_events(self):
        """summary_mode is True when total event count exceeds 200."""
        session_ts = "2026-02-26T09:00:00+00:00"
        overnight = {"features": {"feat-a": {"status": "running"}}}
        events = [{"event": "session_start", "ts": session_ts}]
        # Add 201 more events to exceed threshold
        for i in range(201):
            events.append({"event": "TOOL_USE", "ts": session_ts, "feature": "feat-a"})
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertTrue(result["summary_mode"])

    def test_summary_mode_false_below_threshold(self):
        """summary_mode is False when total event count is <= 200."""
        overnight, events = self._make_events(1)
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertFalse(result["summary_mode"])

    def test_empty_lanes_returned_without_exception_when_no_session_start(self):
        """Returns empty lanes safely when no SESSION_START event present."""
        overnight = {"features": {"feat-a": {"status": "running"}}}
        result = build_swim_lane_data(overnight, [], {}, Path("."))
        self.assertEqual(result["lanes"], [])
        self.assertFalse(result["summary_mode"])

    def test_returns_empty_when_overnight_is_none(self):
        """Returns empty result when overnight is None."""
        result = build_swim_lane_data(None, [], {}, Path("."))
        self.assertEqual(result["lanes"], [])
        self.assertEqual(result["total_elapsed_secs"], 0)

    def test_total_elapsed_secs_is_positive(self):
        """total_elapsed_secs is > 0 for a valid session."""
        overnight, events = self._make_events(1)
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertGreater(result["total_elapsed_secs"], 0)

    def test_event_x_pct_in_range(self):
        """All event x_pct values are in [0, 100]."""
        overnight, events = self._make_events(3)
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        for lane in result["lanes"]:
            for event in lane["events"]:
                self.assertGreaterEqual(event["x_pct"], 0)
                self.assertLessEqual(event["x_pct"], 100)


# ---------------------------------------------------------------------------
# Tests: get_last_activity_ts
# ---------------------------------------------------------------------------

class TestGetLastActivityTs(unittest.TestCase):
    """Tests for get_last_activity_ts timestamp selection."""

    def test_returns_none_for_absent_files(self):
        """Returns None when neither agent-activity.jsonl nor events.log exist."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            (lifecycle_dir / "feat-a").mkdir()
            result = get_last_activity_ts("feat-a", lifecycle_dir)
            self.assertIsNone(result)

    def test_returns_ts_from_activity_file_alone(self):
        """Returns timestamp from agent-activity.jsonl when events.log absent."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feat_dir = lifecycle_dir / "feat-a"
            feat_dir.mkdir()
            ts = "2026-02-26T10:00:00+00:00"
            (feat_dir / "agent-activity.jsonl").write_text(
                json.dumps({"ts": ts, "tool": "Read"}) + "\n",
                encoding="utf-8",
            )
            result = get_last_activity_ts("feat-a", lifecycle_dir)
            from datetime import datetime, timezone
            expected = datetime.fromisoformat(ts)
            self.assertEqual(result, expected)

    def test_returns_ts_from_events_log_alone(self):
        """Returns timestamp from events.log when agent-activity.jsonl absent."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feat_dir = lifecycle_dir / "feat-a"
            feat_dir.mkdir()
            ts = "2026-02-26T10:05:00+00:00"
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": ts, "event": "phase_transition"}) + "\n",
                encoding="utf-8",
            )
            result = get_last_activity_ts("feat-a", lifecycle_dir)
            from datetime import datetime
            expected = datetime.fromisoformat(ts)
            self.assertEqual(result, expected)

    def test_returns_more_recent_of_both_files(self):
        """Returns events.log ts when it is more recent than agent-activity.jsonl."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feat_dir = lifecycle_dir / "feat-a"
            feat_dir.mkdir()
            activity_ts = "2026-02-26T10:00:00+00:00"
            events_ts = "2026-02-26T10:05:00+00:00"
            (feat_dir / "agent-activity.jsonl").write_text(
                json.dumps({"ts": activity_ts}) + "\n", encoding="utf-8"
            )
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": events_ts}) + "\n", encoding="utf-8"
            )
            result = get_last_activity_ts("feat-a", lifecycle_dir)
            from datetime import datetime
            expected = datetime.fromisoformat(events_ts)
            self.assertEqual(result, expected)

    def test_returns_activity_ts_when_it_is_more_recent(self):
        """Returns agent-activity.jsonl ts when it is more recent than events.log."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            feat_dir = lifecycle_dir / "feat-a"
            feat_dir.mkdir()
            activity_ts = "2026-02-26T10:10:00+00:00"
            events_ts = "2026-02-26T10:05:00+00:00"
            (feat_dir / "agent-activity.jsonl").write_text(
                json.dumps({"ts": activity_ts}) + "\n", encoding="utf-8"
            )
            (feat_dir / "events.log").write_text(
                json.dumps({"ts": events_ts}) + "\n", encoding="utf-8"
            )
            result = get_last_activity_ts("feat-a", lifecycle_dir)
            from datetime import datetime
            expected = datetime.fromisoformat(activity_ts)
            self.assertEqual(result, expected)


# ---------------------------------------------------------------------------
# Tests: parse_last_session
# ---------------------------------------------------------------------------

class TestParseLastSession(unittest.TestCase):
    """Tests for parse_last_session archived session summary."""

    def _write_session(self, sessions_dir: Path, session_id: str, updated_at: str, features: dict) -> None:
        """Write a mock overnight-state.json under sessions/{session_id}/."""
        session_dir = sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session_id,
            "updated_at": updated_at,
            "features": features,
        }
        (session_dir / "overnight-state.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_returns_none_when_sessions_dir_absent(self):
        """Returns None when lifecycle/sessions/ does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_last_session(Path(tmp))
            self.assertIsNone(result)

    def test_returns_none_when_sessions_dir_empty(self):
        """Returns None when lifecycle/sessions/ has no session subdirectories."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            (lifecycle_dir / "sessions").mkdir()
            result = parse_last_session(lifecycle_dir)
            self.assertIsNone(result)

    def test_returns_correct_counts_for_single_session(self):
        """Correct merged/failed/total counts from a single archived session."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            self._write_session(
                sessions_dir,
                "overnight-2026-01-01-2200",
                "2026-01-01T22:00:00Z",
                {
                    "feat-a": {"status": "merged"},
                    "feat-b": {"status": "merged"},
                    "feat-c": {"status": "failed"},
                },
            )
            result = parse_last_session(lifecycle_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result["features_merged"], 2)
            self.assertEqual(result["features_failed"], 1)
            self.assertEqual(result["features_total"], 3)

    def test_returns_most_recent_session_when_multiple_exist(self):
        """Selects the session with the latest updated_at timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            self._write_session(
                sessions_dir, "overnight-2026-01-01-2200", "2026-01-01T22:00:00Z",
                {"feat-a": {"status": "merged"}},
            )
            self._write_session(
                sessions_dir, "overnight-2026-01-02-2200", "2026-01-02T22:00:00Z",
                {"feat-b": {"status": "failed"}},
            )
            result = parse_last_session(lifecycle_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result["session_id"], "overnight-2026-01-02-2200")

    def test_ended_hours_ago_is_non_negative(self):
        """ended_hours_ago is >= 0 for any past session."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            self._write_session(
                sessions_dir, "overnight-2026-01-01-2200", "2026-01-01T22:00:00Z",
                {"feat-a": {"status": "merged"}},
            )
            result = parse_last_session(lifecycle_dir)
            self.assertIsNotNone(result)
            self.assertGreaterEqual(result["ended_hours_ago"], 0)

    def test_skips_malformed_json_gracefully(self):
        """Malformed JSON files are skipped; valid sessions still returned."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            # Malformed session
            broken_dir = sessions_dir / "overnight-broken"
            broken_dir.mkdir(parents=True)
            (broken_dir / "overnight-state.json").write_text("{ not json }", encoding="utf-8")
            # Valid session
            self._write_session(
                sessions_dir, "overnight-2026-01-01-2200", "2026-01-01T22:00:00Z",
                {"feat-a": {"status": "merged"}},
            )
            result = parse_last_session(lifecycle_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result["session_id"], "overnight-2026-01-01-2200")

    def test_session_id_returned_correctly(self):
        """session_id field matches the session_id in the state file."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            sessions_dir = lifecycle_dir / "sessions"
            self._write_session(
                sessions_dir, "overnight-2026-02-15-0130", "2026-02-15T01:30:00Z",
                {},
            )
            result = parse_last_session(lifecycle_dir)
            self.assertIsNotNone(result)
            self.assertEqual(result["session_id"], "overnight-2026-02-15-0130")


# ---------------------------------------------------------------------------
# Tests: _read_all_jsonl
# ---------------------------------------------------------------------------

class TestReadAllJsonl(unittest.TestCase):
    """Tests for _read_all_jsonl byte-0 JSONL reader."""

    def test_absent_file_returns_empty_list_and_zero_offset(self):
        """When the file does not exist, returns ([], 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.jsonl"

            events, offset = _read_all_jsonl(path)

            self.assertEqual(events, [])
            self.assertEqual(offset, 0)

    def test_file_with_three_events_returns_all_and_correct_offset(self):
        """A file with 3 valid JSON events returns all 3 and offset == file size."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            lines = [json.dumps({"i": i}) for i in range(3)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            events, offset = _read_all_jsonl(path)

            self.assertEqual(len(events), 3)
            self.assertEqual([e["i"] for e in events], [0, 1, 2])
            self.assertEqual(offset, path.stat().st_size)

    def test_malformed_line_in_middle_skipped_others_returned(self):
        """A malformed JSON line in the middle is skipped; valid lines are returned."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            content = (
                json.dumps({"ok": 1}) + "\n"
                + "not valid json\n"
                + json.dumps({"ok": 2}) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            events, offset = _read_all_jsonl(path)

            self.assertEqual(len(events), 2)
            self.assertEqual([e["ok"] for e in events], [1, 2])
            self.assertGreater(offset, 0)


# ---------------------------------------------------------------------------
# Tests: parse_feature_cost_delta
# ---------------------------------------------------------------------------

class TestParseFeatureCostDelta(unittest.TestCase):
    """Tests for parse_feature_cost_delta incremental cost tracking."""

    def test_absent_path_offset_zero_returns_zero_cost_and_zero_offset(self):
        """When the file is absent and offset is 0, returns (0.0, 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-activity.jsonl"

            delta, new_offset = parse_feature_cost_delta(path, 0)

            self.assertEqual(delta, 0.0)
            self.assertEqual(new_offset, 0)

    def test_no_turn_complete_events_first_call_returns_zero_cost_and_nonzero_offset(self):
        """File with no turn_complete events, first call: delta=0.0, offset > 0."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-activity.jsonl"
            content = (
                json.dumps({"event": "tool_use", "tool": "Read"}) + "\n"
                + json.dumps({"event": "tool_use", "tool": "Bash"}) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            delta, new_offset = parse_feature_cost_delta(path, 0)

            self.assertEqual(delta, 0.0)
            self.assertGreater(new_offset, 0)

    def test_one_turn_complete_event_first_call_returns_cost(self):
        """File with one turn_complete event: first call returns cost_usd and offset."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-activity.jsonl"
            path.write_text(
                json.dumps({"event": "turn_complete", "cost_usd": 0.42}) + "\n",
                encoding="utf-8",
            )

            delta, new_offset = parse_feature_cost_delta(path, 0)

            self.assertAlmostEqual(delta, 0.42)
            self.assertGreater(new_offset, 0)

    def test_second_call_with_saved_offset_no_new_writes_returns_zero(self):
        """Second call with returned offset, no new writes: delta=0.0, offset unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-activity.jsonl"
            path.write_text(
                json.dumps({"event": "turn_complete", "cost_usd": 0.10}) + "\n",
                encoding="utf-8",
            )

            _, saved_offset = parse_feature_cost_delta(path, 0)
            delta2, new_offset2 = parse_feature_cost_delta(path, saved_offset)

            self.assertEqual(delta2, 0.0)
            self.assertEqual(new_offset2, saved_offset)

    def test_append_new_turn_complete_call_with_saved_offset_returns_new_cost(self):
        """Appending a new turn_complete then calling with saved offset returns new cost."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-activity.jsonl"
            path.write_text(
                json.dumps({"event": "turn_complete", "cost_usd": 0.10}) + "\n",
                encoding="utf-8",
            )

            _, saved_offset = parse_feature_cost_delta(path, 0)

            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"event": "turn_complete", "cost_usd": 0.55}) + "\n")

            delta2, new_offset2 = parse_feature_cost_delta(path, saved_offset)

            self.assertAlmostEqual(delta2, 0.55)
            self.assertGreater(new_offset2, saved_offset)


# ---------------------------------------------------------------------------
# Tests: parse_pipeline_dispatch
# ---------------------------------------------------------------------------

class TestParsePipelineDispatch(unittest.TestCase):
    """Tests for parse_pipeline_dispatch dispatch_start event extraction."""

    def test_absent_file_returns_empty_dict(self):
        """When pipeline-events.log is absent, returns {}."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_pipeline_dispatch(Path(tmp))

            self.assertEqual(result, {})

    def test_two_dispatch_start_events_return_correct_dict(self):
        """Two dispatch_start events produce correct {feature: {model, complexity}} dict."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            path = lifecycle_dir / "pipeline-events.log"
            content = (
                json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-a",
                    "model": "claude-opus-4-6",
                    "complexity": "complex",
                }) + "\n"
                + json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-b",
                    "model": "claude-sonnet-4-5",
                    "complexity": "simple",
                }) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            result = parse_pipeline_dispatch(lifecycle_dir)

            self.assertEqual(result, {
                "feat-a": {"model": "claude-opus-4-6", "complexity": "complex"},
                "feat-b": {"model": "claude-sonnet-4-5", "complexity": "simple"},
            })

    def test_duplicate_feature_last_entry_wins(self):
        """When a feature appears twice, the last dispatch_start entry wins."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            path = lifecycle_dir / "pipeline-events.log"
            content = (
                json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-a",
                    "model": "model-1",
                    "complexity": "simple",
                }) + "\n"
                + json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-a",
                    "model": "model-2",
                    "complexity": "complex",
                }) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            result = parse_pipeline_dispatch(lifecycle_dir)

            self.assertEqual(result["feat-a"], {"model": "model-2", "complexity": "complex"})

    def test_non_dispatch_events_are_ignored(self):
        """Events with event != dispatch_start are not included in the result."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            path = lifecycle_dir / "pipeline-events.log"
            content = (
                json.dumps({"event": "session_start", "feature": "feat-a"}) + "\n"
                + json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-b",
                    "model": "m",
                    "complexity": "simple",
                }) + "\n"
                + json.dumps({"event": "dispatch_complete", "feature": "feat-b"}) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            result = parse_pipeline_dispatch(lifecycle_dir)

            self.assertNotIn("feat-a", result)
            self.assertIn("feat-b", result)
            self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# Tests: parse_metrics
# ---------------------------------------------------------------------------

class TestParseMetrics(unittest.TestCase):
    """Tests for parse_metrics metrics.json reader."""

    def test_absent_file_returns_none(self):
        """When metrics.json is absent, returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_metrics(Path(tmp))

            self.assertIsNone(result)

    def test_malformed_json_returns_none(self):
        """When metrics.json contains invalid JSON, returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            (lifecycle_dir / "metrics.json").write_text("{ not valid json }", encoding="utf-8")

            result = parse_metrics(lifecycle_dir)

            self.assertIsNone(result)

    def test_valid_json_returns_dict_unchanged(self):
        """When metrics.json is valid, returns the parsed dict unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            data = {"features": [{"tier": "simple", "phase_durations": {"implement_to_complete": 60.0}}]}
            (lifecycle_dir / "metrics.json").write_text(json.dumps(data), encoding="utf-8")

            result = parse_metrics(lifecycle_dir)

            self.assertEqual(result, data)


# ---------------------------------------------------------------------------
# Tests: compute_slow_flags
# ---------------------------------------------------------------------------

class TestComputeSlowFlags(unittest.TestCase):
    """Tests for compute_slow_flags slow-feature detection."""

    def _make_transition_ts(self, seconds_ago: float) -> str:
        """Return an ISO-8601 timestamp for `seconds_ago` seconds before now."""
        dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        return dt.isoformat()

    def test_metrics_none_returns_empty_dict(self):
        """When metrics is None, returns {}."""
        result = compute_slow_flags(
            feature_states={},
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics=None,
            pipeline_dispatch={},
        )
        self.assertEqual(result, {})

    def test_overnight_none_returns_empty_dict(self):
        """When overnight is None, returns {}."""
        result = compute_slow_flags(
            feature_states={},
            overnight=None,
            metrics={"features": []},
            pipeline_dispatch={},
        )
        self.assertEqual(result, {})

    def test_feature_with_current_phase_none_not_in_result(self):
        """A feature with current_phase=None is not included in result."""
        result = compute_slow_flags(
            feature_states={"feat-a": {"current_phase": None, "phase_transitions": []}},
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics={"features": [{"tier": "simple", "phase_durations": {"implement_to_complete": 10.0}}]},
            pipeline_dispatch={"feat-a": {"model": "m", "complexity": "simple"}},
        )
        self.assertNotIn("feat-a", result)

    def test_implement_complex_slow_returns_true(self):
        """Feature in implement + complex tier + current duration 250s > 3x median(60s) -> True."""
        ts = self._make_transition_ts(250)
        result = compute_slow_flags(
            feature_states={
                "feat-a": {
                    "current_phase": "implement",
                    "phase_transitions": [{"from": "plan", "to": "implement", "ts": ts}],
                }
            },
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics={
                "features": [
                    {"tier": "complex", "phase_durations": {"implement_to_review": 60.0}},
                ]
            },
            pipeline_dispatch={"feat-a": {"model": "m", "complexity": "complex"}},
        )
        self.assertIn("feat-a", result)
        self.assertTrue(result["feat-a"])

    def test_implement_simple_slow_returns_true(self):
        """Feature in implement + simple tier + current duration 250s > 3x median(60s) -> True."""
        ts = self._make_transition_ts(250)
        result = compute_slow_flags(
            feature_states={
                "feat-a": {
                    "current_phase": "implement",
                    "phase_transitions": [{"from": "plan", "to": "implement", "ts": ts}],
                }
            },
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics={
                "features": [
                    {"tier": "simple", "phase_durations": {"implement_to_complete": 60.0}},
                ]
            },
            pipeline_dispatch={"feat-a": {"model": "m", "complexity": "simple"}},
        )
        self.assertIn("feat-a", result)
        self.assertTrue(result["feat-a"])

    def test_research_phase_not_in_result(self):
        """A feature in research phase has no phase key mapping and is excluded."""
        ts = self._make_transition_ts(250)
        result = compute_slow_flags(
            feature_states={
                "feat-a": {
                    "current_phase": "research",
                    "phase_transitions": [{"from": "plan", "to": "research", "ts": ts}],
                }
            },
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics={
                "features": [
                    {"tier": "simple", "phase_durations": {"implement_to_complete": 60.0}},
                ]
            },
            pipeline_dispatch={"feat-a": {"model": "m", "complexity": "simple"}},
        )
        self.assertNotIn("feat-a", result)

    def test_zero_historical_values_for_phase_key_not_in_result(self):
        """When there are no historical values for the relevant phase key, feature excluded."""
        ts = self._make_transition_ts(250)
        result = compute_slow_flags(
            feature_states={
                "feat-a": {
                    "current_phase": "implement",
                    "phase_transitions": [{"from": "plan", "to": "implement", "ts": ts}],
                }
            },
            overnight={"features": {"feat-a": {"status": "running"}}},
            metrics={
                "features": [
                    # Has tier=simple but phase_durations doesn't include implement_to_complete
                    {"tier": "simple", "phase_durations": {"review_to_complete": 30.0}},
                ]
            },
            pipeline_dispatch={"feat-a": {"model": "m", "complexity": "simple"}},
        )
        self.assertNotIn("feat-a", result)


# ---------------------------------------------------------------------------
# Tests: parse_feature_timestamps
# ---------------------------------------------------------------------------

class TestParseFeatureTimestamps(unittest.TestCase):
    """Tests for parse_feature_timestamps per-feature start/complete extraction."""

    def test_empty_input_returns_empty_dict(self):
        """Empty event list returns {}."""
        result = parse_feature_timestamps([])
        self.assertEqual(result, {})

    def test_single_feature_with_both_start_and_complete(self):
        """Feature with start + complete events: all three keys populated."""
        events = [
            {"event": "feature_start", "feature": "feat-a", "ts": "2026-03-01T09:00:00+00:00"},
            {"event": "feature_complete", "feature": "feat-a", "ts": "2026-03-01T10:00:00+00:00"},
        ]
        result = parse_feature_timestamps(events)
        self.assertIn("feat-a", result)
        entry = result["feat-a"]
        self.assertEqual(entry["started_at"], "2026-03-01T09:00:00+00:00")
        self.assertEqual(entry["completed_at"], "2026-03-01T10:00:00+00:00")
        self.assertEqual(entry["duration_secs"], 3600)

    def test_feature_start_only_completed_at_is_none(self):
        """Feature with feature_start but no feature_complete: completed_at and duration_secs are None."""
        events = [
            {"event": "feature_start", "feature": "feat-b", "ts": "2026-03-01T09:00:00+00:00"},
        ]
        result = parse_feature_timestamps(events)
        self.assertIn("feat-b", result)
        entry = result["feat-b"]
        self.assertEqual(entry["started_at"], "2026-03-01T09:00:00+00:00")
        self.assertIsNone(entry["completed_at"])
        self.assertIsNone(entry["duration_secs"])

    def test_events_missing_feature_key_are_skipped(self):
        """Events without a 'feature' key are silently skipped; no KeyError raised."""
        events = [
            {"event": "feature_start", "ts": "2026-03-01T09:00:00+00:00"},  # no 'feature' key
            {"event": "feature_complete", "ts": "2026-03-01T10:00:00+00:00"},  # no 'feature' key
        ]
        result = parse_feature_timestamps(events)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Tests: parse_round_timestamps
# ---------------------------------------------------------------------------

class TestParseRoundTimestamps(unittest.TestCase):
    """Tests for parse_round_timestamps per-round start/complete extraction."""

    def test_empty_input_returns_empty_dict(self):
        """Empty event list returns {}."""
        result = parse_round_timestamps([])
        self.assertEqual(result, {})

    def test_round_with_both_start_and_complete(self):
        """Round with round_start + round_complete: both timestamps populated."""
        events = [
            {"event": "round_start", "round": 1, "ts": "2026-03-01T09:00:00+00:00"},
            {"event": "round_complete", "round": 1, "ts": "2026-03-01T09:30:00+00:00"},
        ]
        result = parse_round_timestamps(events)
        self.assertIn(1, result)
        entry = result[1]
        self.assertEqual(entry["started_at"], "2026-03-01T09:00:00+00:00")
        self.assertEqual(entry["completed_at"], "2026-03-01T09:30:00+00:00")

    def test_round_with_only_start_completed_at_is_none(self):
        """Round with only round_start: completed_at is None."""
        events = [
            {"event": "round_start", "round": 2, "ts": "2026-03-01T10:00:00+00:00"},
        ]
        result = parse_round_timestamps(events)
        self.assertIn(2, result)
        self.assertIsNone(result[2]["completed_at"])

    def test_round_number_is_stored_as_int(self):
        """Round number key is an int, not a string."""
        events = [
            {"event": "round_start", "round": 3, "ts": "2026-03-01T11:00:00+00:00"},
        ]
        result = parse_round_timestamps(events)
        keys = list(result.keys())
        self.assertEqual(len(keys), 1)
        self.assertIsInstance(keys[0], int)
        self.assertEqual(keys[0], 3)


# ---------------------------------------------------------------------------
# Tests: build_swim_lane_data — ticks key
# ---------------------------------------------------------------------------

class TestBuildSwimLaneDataTicks(unittest.TestCase):
    """Tests for the 'ticks' key in build_swim_lane_data output."""

    def test_result_contains_ticks_key_as_list(self):
        """Return dict always contains a 'ticks' key that is a list."""
        session_ts = "2026-03-01T09:00:00+00:00"
        overnight = {"features": {}}
        events = [{"event": "session_start", "ts": session_ts}]
        result = build_swim_lane_data(overnight, events, {}, Path("."))
        self.assertIn("ticks", result)
        self.assertIsInstance(result["ticks"], list)

    def test_ticks_key_present_when_overnight_is_none(self):
        """'ticks' key is present (empty list) when overnight is None."""
        result = build_swim_lane_data(None, [], {}, Path("."))
        self.assertIn("ticks", result)
        self.assertIsInstance(result["ticks"], list)

    def test_90_minute_session_produces_3_ticks(self):
        """A 90-minute session produces exactly 3 ticks (max(3, min(8, 5400//1800)) = 3)."""
        session_ts = "2026-03-01T09:00:00+00:00"
        end_ts = "2026-03-01T10:30:00+00:00"
        session_dt = datetime.fromisoformat(session_ts)
        end_dt = datetime.fromisoformat(end_ts)

        overnight = {"features": {}}
        events = [{"event": "session_start", "ts": session_ts}]
        result = build_swim_lane_data(overnight, events, {}, Path("."), end_dt=end_dt)

        ticks = result["ticks"]
        self.assertEqual(len(ticks), 3)

    def test_90_minute_session_tick_labels_include_0m_and_1h30m(self):
        """A 90-minute session: first tick label is '0m' and last is '1h 30m'."""
        session_ts = "2026-03-01T09:00:00+00:00"
        end_ts = "2026-03-01T10:30:00+00:00"
        session_dt = datetime.fromisoformat(session_ts)
        end_dt = datetime.fromisoformat(end_ts)

        overnight = {"features": {}}
        events = [{"event": "session_start", "ts": session_ts}]
        result = build_swim_lane_data(overnight, events, {}, Path("."), end_dt=end_dt)

        ticks = result["ticks"]
        labels = [t["label"] for t in ticks]
        self.assertIn("0m", labels)
        self.assertIn("1h 30m", labels)


if __name__ == "__main__":
    unittest.main()
