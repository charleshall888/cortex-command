"""Unit tests for cortex_command/dashboard/data.py.

Tests cover:
  - tail_jsonl: initial call returns last N lines and byte offset
  - tail_jsonl: second call with saved offset returns only new lines
  - tail_jsonl: malformed JSON lines are skipped
  - tail_jsonl: absent file returns ([], 0)
  - parse_backlog_titles: one pass yields both slug→title and id→title
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

from cortex_command.dashboard.data import (
    ARTIFACT_MAX_CHARS,
    TICKET_BODY_MAX_CHARS,
    _exit_report_sort_key,
    _lane_label_width_pct,
    _read_all_jsonl,
    build_swim_lane_data,
    load_ticket_artifact,
    load_ticket_body,
    load_ticket_page,
    parse_recent_session_events,
    compute_slow_flags,
    get_last_activity_ts,
    parse_backlog_titles,
    parse_feature_cost_delta,
    parse_feature_timestamps,
    parse_fleet_cards,
    parse_last_session,
    parse_metrics,
    parse_overnight_state,
    parse_pipeline_dispatch,
    parse_pipeline_state,
    parse_round_timestamps,
    resolve_artifact_dir,
    tail_jsonl,
)


# ---------------------------------------------------------------------------
# Tests: _exit_report_sort_key (suffix-aware exit-report ordering, #297)
# ---------------------------------------------------------------------------

class TestExitReportSortKey(unittest.TestCase):
    """#297 Req 9: exit-report stems sort by (numeric-prefix, suffix) so a
    sub-task stem sorts after its parent and before the next integer."""

    def test_suffixed_stems_sort_after_parent_before_next_integer(self):
        stems = ["10", "3b", "1", "3", "2", "3a"]
        ordered = sorted(stems, key=_exit_report_sort_key)
        self.assertEqual(ordered, ["1", "2", "3", "3a", "3b", "10"])

    def test_non_conforming_stem_buckets_to_floor(self):
        # A non-digit stem (e.g. "repair") sorts after all numeric stems.
        stems = ["repair", "2", "1"]
        ordered = sorted(stems, key=_exit_report_sort_key)
        self.assertEqual(ordered, ["1", "2", "repair"])


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
# Tests: parse_overnight_state
# ---------------------------------------------------------------------------

class TestParseBacklogTitles(unittest.TestCase):
    """Both title maps come from the function's single corpus pass (#411 R13)."""

    def _write_backlog_file(self, directory: Path, filename: str, frontmatter: str) -> None:
        content = f"---\n{frontmatter}---\n\nBody text.\n"
        (directory / filename).write_text(content, encoding="utf-8")

    def test_returns_both_slug_and_id_maps(self):
        """by_slug keeps its historical shape; by_id keys on the filename id."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "007-alpha.md", "title: Alpha Feature\n")
            self._write_backlog_file(backlog_dir, "412-beta.md", "title: Beta Board\n")

            result = parse_backlog_titles(backlog_dir)

            self.assertEqual(
                result.by_slug,
                {"alpha-feature": "Alpha Feature", "beta-board": "Beta Board"},
            )
            self.assertEqual(
                result.by_id, {"7": "Alpha Feature", "412": "Beta Board"}
            )

    def test_id_key_is_unpadded(self):
        """Keys mirror collect_items' unpadded ids so a join needs no zfill dance."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "003-gamma.md", "title: Gamma\n")

            result = parse_backlog_titles(backlog_dir)

            self.assertIn("3", result.by_id)
            self.assertNotIn("003", result.by_id)

    def test_terminal_items_are_included(self):
        """The blocked-why join resolves blockers that are already complete."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(
                backlog_dir, "228-done.md", "title: Finished Work\nstatus: complete\n"
            )

            result = parse_backlog_titles(backlog_dir)

            self.assertEqual(result.by_id["228"], "Finished Work")

    def test_archive_subdirectory_is_not_scanned(self):
        """The glob is non-recursive; archived blockers resolve with no title."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            archive = backlog_dir / "archive"
            archive.mkdir()
            self._write_backlog_file(archive, "050-archived.md", "title: Archived\n")
            self._write_backlog_file(backlog_dir, "051-active.md", "title: Active\n")

            result = parse_backlog_titles(backlog_dir)

            self.assertEqual(result.by_id, {"51": "Active"})

    def test_absent_directory_returns_two_empty_maps(self):
        """Degenerate corpora yield empty maps, never a raise."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_backlog_titles(Path(tmp) / "does-not-exist")

            self.assertEqual(result.by_slug, {})
            self.assertEqual(result.by_id, {})

    def test_untitled_item_appears_in_neither_map(self):
        """A missing title is skipped for both keys, not stored as empty."""
        with tempfile.TemporaryDirectory() as tmp:
            backlog_dir = Path(tmp)
            self._write_backlog_file(backlog_dir, "009-untitled.md", "status: backlog\n")

            result = parse_backlog_titles(backlog_dir)

            self.assertEqual(result.by_slug, {})
            self.assertEqual(result.by_id, {})


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

    def _crowded_lane(self) -> dict:
        """One lane whose events all fall inside a few seconds of each other.

        The realistic shape at a phase boundary: a feature completes and
        transitions in the same breath, so two long labels land on effectively
        the same x.
        """
        session_ts = "2026-02-26T09:00:00+00:00"
        overnight = {"features": {"feat-a": {"status": "merged"}}}
        events = [
            {"event": "session_start", "ts": session_ts},
            {"event": "feature_start", "feature": "feat-a",
             "ts": "2026-02-26T09:30:00+00:00"},
            {"event": "feature_complete", "feature": "feat-a",
             "ts": "2026-02-26T09:30:02+00:00"},
        ]
        feature_states = {
            "feat-a": {
                "phase_transitions": [
                    {"from": "specify", "to": "plan",
                     "ts": "2026-02-26T09:30:01+00:00"},
                    {"from": "plan", "to": "implement",
                     "ts": "2026-02-26T09:30:03+00:00"},
                ]
            }
        }
        end = datetime(2026, 2, 26, 10, 0, 0, tzinfo=timezone.utc)
        return build_swim_lane_data(
            overnight, events, feature_states, Path("."), end_dt=end
        )

    def test_crowded_lane_labels_do_not_overlap(self):
        """Near-simultaneous events are spread so their labels stay readable.

        Regression: labels were positioned at raw elapsed percentages with no
        collision handling, so "complete" and "specify→implement" rendered on
        top of one another as an unreadable composite — the failure DESIGN.md's
        "Operational usefulness" criterion names explicitly.
        """
        lane = self._crowded_lane()["lanes"][0]
        self.assertGreaterEqual(len(lane["events"]), 4)
        placed = sorted(
            ((e["x_pct"], _lane_label_width_pct(e["label"])) for e in lane["events"]),
            key=lambda pair: pair[0],
        )
        for (x, width), (next_x, _) in zip(placed, placed[1:]):
            self.assertLessEqual(
                x + width, next_x + 1e-9,
                f"label at {x:.2f}% (width {width:.2f}%) runs into {next_x:.2f}%",
            )

    def test_spread_labels_stay_inside_the_track(self):
        """No label extends past the right edge after the forward sweep."""
        lane = self._crowded_lane()["lanes"][0]
        for event in lane["events"]:
            right = event["x_pct"] + _lane_label_width_pct(event["label"])
            self.assertGreaterEqual(event["x_pct"], 0)
            self.assertLessEqual(right, 100.0 + 1e-9, f"{event['label']} overflows")

    def test_spread_preserves_chronological_order(self):
        """Nudging apart must not reorder events relative to their timestamps."""
        lane = self._crowded_lane()["lanes"][0]
        by_time = sorted(lane["events"], key=lambda e: e["elapsed_secs"])
        xs = [e["x_pct"] for e in by_time]
        self.assertEqual(xs, sorted(xs))


# ---------------------------------------------------------------------------
# Tests: parse_recent_session_events
# ---------------------------------------------------------------------------

class TestParseRecentSessionEvents(unittest.TestCase):
    """The activity stream is labelled 'newest first' and must actually be."""

    @staticmethod
    def _events() -> list[dict]:
        """Events whose append order is NOT their timestamp order.

        This is the real log shape, not a contrived one: the runner
        interleaves writers, so a round-level heartbeat lands after the
        per-feature checkpoints it postdates.
        """
        return [
            {"event": "feature_checkpoint", "ts": "2026-02-26T12:30:00+00:00",
             "feature": "feat-a", "note": "step 2"},
            {"event": "feature_checkpoint", "ts": "2026-02-26T13:05:00+00:00",
             "feature": "feat-a", "note": "step 12"},
            {"event": "plan_loaded", "ts": "2026-02-26T11:45:00+00:00"},
            {"event": "branch_synced", "ts": "2026-02-26T12:10:00+00:00"},
            {"event": "heartbeat", "ts": "2026-02-26T13:08:00+00:00"},
        ]

    def test_returns_events_newest_first(self):
        # Regression: the old implementation sliced the last N in FILE order
        # and reversed, so the panel rendered a 5m/1h/8m/45m jumble under a
        # heading promising descending time.
        result = parse_recent_session_events(self._events())
        stamps = [entry["ts"] for entry in result]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(result[0]["event"], "heartbeat")

    def test_keeps_the_newest_events_when_truncating(self):
        # Truncation must drop the OLDEST, which a positional tail does not:
        # here the oldest event (plan_loaded) is fourth from the end in file
        # order, so a tail of 2 would have kept it and dropped a newer one.
        result = parse_recent_session_events(self._events(), last_n=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            [entry["ts"] for entry in result],
            ["2026-02-26T13:08:00+00:00", "2026-02-26T13:05:00+00:00"],
        )

    def test_events_without_a_timestamp_do_not_raise(self):
        events = self._events() + [{"event": "heartbeat"}, {"event": "heartbeat", "ts": None}]
        result = parse_recent_session_events(events)
        self.assertEqual(len(result), len(events))
        # A missing stamp sorts last under reverse ordering — surfaced, not
        # dropped, and never crashing the comparison.
        self.assertEqual([entry["ts"] for entry in result][-2:], ["", ""])


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
        """Returns None when cortex/lifecycle/sessions/ does not exist."""
        with tempfile.TemporaryDirectory() as tmp:
            result = parse_last_session(Path(tmp))
            self.assertIsNone(result)

    def test_returns_none_when_sessions_dir_empty(self):
        """Returns None when cortex/lifecycle/sessions/ has no session subdirectories."""
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

    def test_model_arrives_from_dispatch_model_observed_mid_run(self):
        """Current event shape: the model is not known at dispatch_start.

        cortex pins no model (ADR-0032), so dispatch_start carries none and the
        badge fills in from the one-shot dispatch_model_observed event — which
        fires as soon as the agent replies, i.e. while the dispatch is still
        running. Reading only dispatch_start would leave the badge blank for
        the whole run.
        """
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            path = lifecycle_dir / "pipeline-events.log"
            content = (
                json.dumps({
                    "event": "dispatch_start",
                    "feature": "feat-a",
                    "complexity": "complex",
                }) + "\n"
                + json.dumps({
                    "event": "dispatch_model_observed",
                    "feature": "feat-a",
                    "model": "claude-opus-4-7",
                }) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            result = parse_pipeline_dispatch(lifecycle_dir)

            self.assertEqual(result, {
                "feat-a": {"model": "claude-opus-4-7", "complexity": "complex"},
            })

    def test_redispatch_clears_the_previous_attempts_model(self):
        """A retry must not display the prior attempt's model as if it were live.

        The new dispatch_start resets the badge; it refills when that attempt's
        own dispatch_model_observed arrives.
        """
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp)
            path = lifecycle_dir / "pipeline-events.log"
            content = (
                json.dumps({
                    "event": "dispatch_start", "feature": "feat-a",
                    "complexity": "complex",
                }) + "\n"
                + json.dumps({
                    "event": "dispatch_model_observed", "feature": "feat-a",
                    "model": "claude-opus-4-7",
                }) + "\n"
                + json.dumps({
                    "event": "dispatch_start", "feature": "feat-a",
                    "complexity": "complex",
                }) + "\n"
            )
            path.write_bytes(content.encode("utf-8"))

            result = parse_pipeline_dispatch(lifecycle_dir)

            self.assertEqual(result["feat-a"]["model"], "")

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

    def test_implement_rework_simple_slow_returns_true(self):
        """Feature in implement-rework + simple tier + current duration 250s > 3x median(60s) -> True."""
        ts = self._make_transition_ts(250)
        result = compute_slow_flags(
            feature_states={
                "feat-a": {
                    "current_phase": "implement-rework",
                    "phase_transitions": [{"from": "review", "to": "implement-rework", "ts": ts}],
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


class TestLoadTicketBody(unittest.TestCase):
    """The per-ticket description read behind /partials/ticket/{id}."""

    def _corpus(self, tmp: str) -> Path:
        backlog = Path(tmp) / "backlog"
        (backlog / "archive").mkdir(parents=True)
        (backlog / "042-a-real-ticket.md").write_text(
            "---\ntitle: A real ticket\nstatus: backlog\n---\n\n"
            "## Context\n\nProse with a `code span`.\n\n"
            "| Option | Cost |\n|---|---|\n| One | low |\n",
            encoding="utf-8",
        )
        (backlog / "007-frontmatter-only.md").write_text(
            "---\ntitle: Frontmatter only\n---\n", encoding="utf-8"
        )
        (backlog / "archive" / "900-closed-ticket.md").write_text(
            "---\ntitle: Closed ticket\n---\n\nStill readable.\n", encoding="utf-8"
        )
        return backlog

    def test_renders_headings_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = load_ticket_body("42", self._corpus(tmp))
            self.assertEqual(got["title"], "A real ticket")
            self.assertIn("<h2>Context</h2>", got["html"])
            self.assertIn("<table>", got["html"])
            self.assertIn("<code>code span</code>", got["html"])
            self.assertFalse(got["truncated"])

    def test_a_line_leading_ticket_ref_is_not_a_heading(self):
        """``#331`` opening a line is a cross-reference, not an ``<h1>``.

        Python-Markdown does not require a space after ``#`` for an ATX
        heading, so every line opening with a ticket id rendered as the largest
        type on the page. Measured on the wild-light corpus before the fix: 156
        such lines across 109 of 512 tickets. Cross-referencing a ticket at the
        start of a sentence is ordinary in this corpus, and the four prefixes
        below are the shapes it actually takes there.
        """
        prefixes = {
            "bare": "#331 is the prerequisite.",
            "blockquote": "> #331 is the prerequisite.",
            "bullet": "- #331 is the prerequisite.",
            "ordered": "1. #331 is the prerequisite.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            for name, line in prefixes.items():
                (backlog / ("05%d-ref.md" % len(name))).write_text(
                    "---\ntitle: Ref\n---\n\n" + line + "\n", encoding="utf-8"
                )
                got = load_ticket_body("05%d" % len(name), backlog)
                with self.subTest(prefix=name):
                    self.assertNotIn("<h1>", got["html"])
                    self.assertIn("#331", got["html"])

    def test_real_headings_still_render(self):
        # The guard against over-correcting: the fix keys on a digit directly
        # after the hash, so every heading with a space or a second hash is
        # untouched. Without this, escaping every leading hash would silently
        # flatten the Why/Role/Integration/Edges template the whole corpus uses.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "060-headings.md").write_text(
                "---\ntitle: Headings\n---\n\n# Why\n\n## Role\n\n### 1. A step\n",
                encoding="utf-8",
            )
            got = load_ticket_body("60", backlog)
            self.assertIn("<h1>Why</h1>", got["html"])
            self.assertIn("<h2>Role</h2>", got["html"])
            self.assertIn("<h3>1. A step</h3>", got["html"])

    def test_frontmatter_is_stripped_from_the_body(self):
        # The reader shows the description, not the fields the row already has.
        with tempfile.TemporaryDirectory() as tmp:
            got = load_ticket_body("42", self._corpus(tmp))
            self.assertNotIn("status: backlog", got["html"])
            self.assertNotIn("title: A real ticket", got["html"])

    def test_frontmatter_only_ticket_yields_empty_html(self):
        # Distinct from "no such ticket": the template says so differently.
        with tempfile.TemporaryDirectory() as tmp:
            got = load_ticket_body("7", self._corpus(tmp))
            self.assertIsNotNone(got)
            self.assertEqual(got["html"], "")

    def test_archived_ticket_is_still_readable(self):
        # A blocker frequently points at a closed ticket; being unable to read
        # it is the case the reader most needs to cover.
        with tempfile.TemporaryDirectory() as tmp:
            got = load_ticket_body("900", self._corpus(tmp))
            self.assertIsNotNone(got)
            self.assertIn("Still readable.", got["html"])

    def test_raw_html_in_a_body_is_stripped_not_executed(self):
        # Bodies quote material this repo did not author. Python-Markdown has
        # no safe mode, so raw HTML would otherwise reach the page verbatim.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "500-hostile.md").write_text(
                "---\ntitle: Hostile\n---\n\n"
                "<script>fetch('/exfil')</script>\n\n"
                '<img src=x onerror="alert(1)">\n\n'
                '<a href="javascript:alert(1)">click</a>\n\n'
                '<div onclick="steal()">text survives</div>\n',
                encoding="utf-8",
            )
            html = load_ticket_body("500", backlog)["html"]
            self.assertNotIn("<script", html)
            self.assertNotIn("<img", html)
            self.assertNotIn("<iframe", html)
            self.assertNotIn("onerror", html)
            self.assertNotIn("onclick", html)
            self.assertNotIn("javascript:", html)
            # Script *contents* go too — unwrapping would print the payload.
            self.assertNotIn("fetch('/exfil')", html)
            # A disallowed wrapper is unwrapped, but its prose is still shown.
            self.assertIn("text survives", html)

    def test_code_fences_are_not_double_escaped(self):
        # Regression: escaping the source before rendering double-escaped every
        # fenced block, because Markdown escapes `&` again inside code — so
        # `-> str` reached the page as the literal text `-&gt; str`.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "502-code.md").write_text(
                "---\ntitle: Code\n---\n\n"
                "```python\ndef f(x: dict) -> str:\n    return x[\"k\"] < 3 and y > 1\n```\n",
                encoding="utf-8",
            )
            html = load_ticket_body("502", backlog)["html"]
            self.assertNotIn("&amp;gt;", html)
            self.assertNotIn("&amp;lt;", html)
            self.assertNotIn("&amp;quot;", html)
            self.assertIn("-&gt; str", html)
            self.assertIn("&lt; 3", html)

    def test_unrecognized_placeholder_tag_in_prose_is_escaped_not_dropped(self):
        # Regression: a bare `<slug>`-style placeholder in prose reads as an
        # HTML tag to Python-Markdown, and the old sanitizer dropped any tag
        # outside its allowlist with no trace — turning
        # `cortex/lifecycle/<slug>/research.md` into `cortex/lifecycle//research.md`.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "504-placeholder.md").write_text(
                "---\ntitle: Placeholder\n---\n\n"
                "Path pattern: cortex/lifecycle/<slug>/research.md\n",
                encoding="utf-8",
            )
            html = load_ticket_body("504", backlog)["html"]
            self.assertIn("cortex/lifecycle/&lt;slug&gt;/research.md", html)
            self.assertNotIn("<slug>", html)

    def test_unrecognized_placeholder_tag_in_a_fence_is_not_double_escaped(self):
        # The same token inside a fenced block never reaches tag parsing —
        # Markdown escapes it as code text — so it must not be re-escaped.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "505-placeholder-fence.md").write_text(
                "---\ntitle: Placeholder fence\n---\n\n"
                "```\ncortex/lifecycle/<slug>/research.md\n```\n",
                encoding="utf-8",
            )
            html = load_ticket_body("505", backlog)["html"]
            self.assertIn("cortex/lifecycle/&lt;slug&gt;/research.md", html)
            self.assertNotIn("&amp;lt;", html)

    def test_markdown_structure_and_safe_links_survive_sanitising(self):
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "503-links.md").write_text(
                "---\ntitle: Links\n---\n\n"
                "See [the docs](https://example.com/x) and [a file](../spec.md).\n\n"
                "> a quote\n\n- one\n- two\n",
                encoding="utf-8",
            )
            html = load_ticket_body("503", backlog)["html"]
            self.assertIn('href="https://example.com/x"', html)
            self.assertIn('href="../spec.md"', html)
            self.assertIn("<blockquote>", html)
            self.assertIn("<li>one</li>", html)

    def test_oversized_body_is_truncated_and_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            (backlog / "501-huge.md").write_text(
                "---\ntitle: Huge\n---\n\n" + ("x" * (TICKET_BODY_MAX_CHARS + 500)),
                encoding="utf-8",
            )
            got = load_ticket_body("501", backlog)
            self.assertTrue(got["truncated"])
            self.assertLess(len(got["html"]), TICKET_BODY_MAX_CHARS + 200)

    def test_non_integer_ids_are_rejected_before_any_filesystem_call(self):
        # The id comes straight off the URL path.
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            for bad in ("../../etc/passwd", "42; rm -rf /", "*", "", "42a", "-1"):
                with self.subTest(item_id=bad):
                    self.assertIsNone(load_ticket_body(bad, backlog))

    def test_traversal_via_a_symlink_out_of_the_backlog_dir_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            backlog = self._corpus(tmp)
            secret = Path(tmp) / "secret.md"
            secret.write_text("---\ntitle: Secret\n---\n\ntop secret\n", encoding="utf-8")
            try:
                (backlog / "808-escape.md").symlink_to(secret)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            self.assertIsNone(load_ticket_body("808", backlog))

    def test_unknown_id_and_missing_dir_return_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_ticket_body("99999", self._corpus(tmp)))
            self.assertIsNone(load_ticket_body("42", Path(tmp) / "nope"))


class TestTicketPageDataLayer(unittest.TestCase):
    """load_ticket_page / load_ticket_artifact / resolve_artifact_dir — the
    whole read side of the ``/tickets/{id}`` page (#413 Task 5)."""

    def _write_ticket(
        self, backlog_dir: Path, item_id: int, extra_fm: str = "", body: str = "Body.\n"
    ) -> None:
        backlog_dir.mkdir(parents=True, exist_ok=True)
        (backlog_dir / f"{item_id}-ticket.md").write_text(
            f"---\ntitle: Ticket {item_id}\nstatus: backlog\npriority: medium\n"
            f"type: feature\n{extra_fm}---\n\n{body}",
            encoding="utf-8",
        )

    def _write_artifacts(self, artifact_dir: Path, *kinds: str) -> None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for kind in kinds:
            (artifact_dir / f"{kind}.md").write_text(f"# {kind.title()}\n\nContent.\n", encoding="utf-8")

    def test_spec_key_found_path(self):
        """A `spec:` value whose parent directory exists resolves directly."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 100,
                extra_fm="spec: cortex/lifecycle/direct-slug/spec.md\n",
            )
            self._write_artifacts(
                lifecycle_dir / "direct-slug", "research", "spec", "plan", "review"
            )

            page = load_ticket_page("100", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["artifacts"], ["research", "spec", "plan", "review"])

    def test_lifecycle_slug_fallback_path(self):
        """No `spec:` key: falls back to lifecycle_dir/<lifecycle_slug>."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 101, extra_fm="lifecycle_slug: plain-slug\n"
            )
            self._write_artifacts(lifecycle_dir / "plain-slug", "spec")

            page = load_ticket_page("101", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["artifacts"], ["spec"])

    def test_lifecycle_slug_archive_fallback_path(self):
        """No `spec:` key and the plain slug dir is absent: probes archive/<slug>."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 102, extra_fm="lifecycle_slug: archived-slug\n"
            )
            self._write_artifacts(lifecycle_dir / "archive" / "archived-slug", "research")

            page = load_ticket_page("102", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["artifacts"], ["research"])

    def test_neither_key_resolves_to_no_artifacts(self):
        """A ticket with neither `spec:` nor `lifecycle_slug` gets an empty artifact list."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(backlog_dir, 103)

            page = load_ticket_page("103", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["artifacts"], [])

    def test_stale_spec_falls_through_to_lifecycle_slug_probe(self):
        """A `spec:` pointing at a vanished directory falls through, not short-circuits."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 104,
                extra_fm=(
                    "spec: cortex/lifecycle/vanished-slug/spec.md\n"
                    "lifecycle_slug: real-slug\n"
                ),
            )
            self._write_artifacts(lifecycle_dir / "real-slug", "plan")
            # vanished-slug is never created on disk.

            page = load_ticket_page("104", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["artifacts"], ["plan"])

    def test_directory_holding_only_some_kinds_omits_the_rest(self):
        """Absent kinds are omitted, never rendered as empty shells."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 105, extra_fm="lifecycle_slug: partial-slug\n"
            )
            self._write_artifacts(lifecycle_dir / "partial-slug", "research", "plan")

            page = load_ticket_page("105", backlog_dir, lifecycle_dir)

            self.assertEqual(page["artifacts"], ["research", "plan"])

    def test_load_ticket_artifact_rejects_unknown_kind_before_filesystem_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 106, extra_fm="lifecycle_slug: some-slug\n"
            )
            self._write_artifacts(lifecycle_dir / "some-slug", "spec")

            self.assertIsNone(
                load_ticket_artifact("106", "notes", backlog_dir, lifecycle_dir)
            )

    def test_load_ticket_artifact_renders_the_present_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 107, extra_fm="lifecycle_slug: render-slug\n"
            )
            self._write_artifacts(lifecycle_dir / "render-slug", "spec")

            got = load_ticket_artifact("107", "spec", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(got)
            self.assertEqual(got["kind"], "spec")
            self.assertIn("<h1>Spec</h1>", got["html"])
            self.assertFalse(got["truncated"])

    def test_oversized_artifact_is_truncated_and_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(
                backlog_dir, 108, extra_fm="lifecycle_slug: huge-slug\n"
            )
            artifact_dir = lifecycle_dir / "huge-slug"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "plan.md").write_text(
                "x" * (ARTIFACT_MAX_CHARS + 500), encoding="utf-8"
            )

            got = load_ticket_artifact("108", "plan", backlog_dir, lifecycle_dir)

            self.assertTrue(got["truncated"])
            self.assertLess(len(got["html"]), ARTIFACT_MAX_CHARS + 200)

    def test_non_integer_id_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            backlog_dir.mkdir(parents=True)

            self.assertIsNone(load_ticket_page("42a", backlog_dir, lifecycle_dir))
            self.assertIsNone(
                load_ticket_artifact("42a", "spec", backlog_dir, lifecycle_dir)
            )

    def test_epic_children_resolved_for_an_epic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            (backlog_dir / "109-epic.md").parent.mkdir(parents=True, exist_ok=True)
            (backlog_dir / "109-epic.md").write_text(
                "---\ntitle: The epic\nstatus: backlog\npriority: medium\n"
                "type: epic\n---\n\nBody.\n",
                encoding="utf-8",
            )
            (backlog_dir / "110-child.md").write_text(
                "---\ntitle: Child one\nstatus: backlog\npriority: medium\n"
                "type: feature\nparent: 109\n---\n\nBody.\n",
                encoding="utf-8",
            )
            (backlog_dir / "111-child.md").write_text(
                "---\ntitle: Child two\nstatus: backlog\npriority: medium\n"
                "type: feature\nparent: 109\n---\n\nBody.\n",
                encoding="utf-8",
            )

            page = load_ticket_page("109", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["type"], "epic")
            self.assertEqual([c["id"] for c in page["children"]], [110, 111])

    def test_epic_children_absent_for_a_non_epic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog_dir = root / "cortex" / "backlog"
            lifecycle_dir = root / "cortex" / "lifecycle"
            self._write_ticket(backlog_dir, 112)

            page = load_ticket_page("112", backlog_dir, lifecycle_dir)

            self.assertIsNotNone(page)
            self.assertEqual(page["type"], "feature")
            self.assertIsNone(page["children"])


if __name__ == "__main__":
    unittest.main()
