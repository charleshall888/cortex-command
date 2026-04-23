"""Data model contract tests for escalations.jsonl.

TestEscalationsDataModel — 8 tests covering the JSONL schema contracts that
the orchestrator prompt logic relies on:
  Req 1: set-difference unresolved computation
  Req 2: promoted-as-tombstone removes from unresolved
  Req 3: cycle-breaking resolution count
  Req 4: escalation cap timestamp sorting (5 oldest)
  Req 5: escalation entry field presence (all 7 required fields)
  Req 6: resolution entry field presence
  Req 7: promoted entry field presence
  Req 8: escalation_id consistency across entries
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.deferral import EscalationEntry, _now_iso, write_escalation
from cortex_command.overnight.tests.conftest import _parse_jsonl


class TestEscalationsDataModel(unittest.TestCase):
    """JSONL data model contracts for escalations.jsonl."""

    # ------------------------------------------------------------------
    # Req 1: set-difference unresolved computation
    # ------------------------------------------------------------------

    def test_unresolved_is_set_difference_of_escalation_minus_resolved(self):
        """Unresolved = escalation IDs not in resolution or promoted IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            # Write 3 escalations
            for i in range(1, 4):
                write_escalation(
                    EscalationEntry(
                        escalation_id=f"feat-1-q{i}",
                        feature="feat", round=1,
                        question=f"Q{i}?", context="ctx",
                    ),
                    escalations_path=path,
                )
            # Resolve escalation 1
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "resolution",
                    "escalation_id": "feat-1-q1",
                    "feature": "feat",
                    "answer": "yes",
                    "resolved_by": "orchestrator",
                    "ts": _now_iso(),
                }) + "\n")

            entries = _parse_jsonl(path)
            escalated = {e["escalation_id"] for e in entries if e["type"] == "escalation"}
            resolved = {e["escalation_id"] for e in entries
                        if e["type"] in ("resolution", "promoted")}
            unresolved = escalated - resolved

            self.assertEqual(unresolved, {"feat-1-q2", "feat-1-q3"})

    # ------------------------------------------------------------------
    # Req 2: promoted-as-tombstone
    # ------------------------------------------------------------------

    def test_promoted_entry_removes_from_unresolved(self):
        """A 'promoted' entry acts as a tombstone, removing ID from unresolved."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            write_escalation(
                EscalationEntry(
                    escalation_id="feat-1-q1",
                    feature="feat", round=1,
                    question="Q?", context="ctx",
                ),
                escalations_path=path,
            )
            # Promote (tombstone) it
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "promoted",
                    "escalation_id": "feat-1-q1",
                    "feature": "feat",
                    "promoted_by": "orchestrator",
                    "ts": _now_iso(),
                }) + "\n")

            entries = _parse_jsonl(path)
            escalated = {e["escalation_id"] for e in entries if e["type"] == "escalation"}
            tombstoned = {e["escalation_id"] for e in entries
                          if e["type"] in ("resolution", "promoted")}
            unresolved = escalated - tombstoned

            self.assertEqual(unresolved, set())

    # ------------------------------------------------------------------
    # Req 3: cycle-breaking resolution count
    # ------------------------------------------------------------------

    def test_cycle_breaking_resolution_count_is_one(self):
        """Exactly one resolution entry exists for the feature after one resolution write."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            write_escalation(
                EscalationEntry(
                    escalation_id="feat-1-q1",
                    feature="cycle-feat", round=1,
                    question="Q?", context="ctx",
                ),
                escalations_path=path,
            )
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "resolution",
                    "escalation_id": "feat-1-q1",
                    "feature": "cycle-feat",
                    "answer": "resolved",
                    "resolved_by": "orchestrator",
                    "ts": _now_iso(),
                }) + "\n")

            entries = _parse_jsonl(path)
            resolutions = [
                e for e in entries
                if e["type"] == "resolution" and e["feature"] == "cycle-feat"
            ]
            self.assertEqual(len(resolutions), 1)

    # ------------------------------------------------------------------
    # Req 4: cap timestamp sorting (5 oldest)
    # ------------------------------------------------------------------

    def test_cap_logic_selects_five_oldest_by_timestamp(self):
        """Cap logic: sort by ts, take first 5 → these are the 5 oldest entries."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            # Write 7 escalations with controlled timestamps
            iso_ts = [f"2026-01-0{i}T00:00:00+00:00" for i in range(1, 8)]
            ids_in_order = [f"feat-1-q{i}" for i in range(1, 8)]

            with patch(
                "cortex_command.overnight.deferral._now_iso",
                side_effect=iso_ts,
            ):
                for i, eid in enumerate(ids_in_order):
                    write_escalation(
                        EscalationEntry(
                            escalation_id=eid,
                            feature="feat", round=1,
                            question=f"Q{i+1}?", context="ctx",
                        ),
                        escalations_path=path,
                    )

            entries = _parse_jsonl(path)
            esc_entries = [e for e in entries if e["type"] == "escalation"]
            oldest_five_ids = [
                e["escalation_id"]
                for e in sorted(esc_entries, key=lambda e: e["ts"])[:5]
            ]
            self.assertEqual(oldest_five_ids, ids_in_order[:5])

    # ------------------------------------------------------------------
    # Req 5: escalation entry field presence
    # ------------------------------------------------------------------

    def test_escalation_entry_has_all_required_fields(self):
        """write_escalation() produces a record with all 7 required fields."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            write_escalation(
                EscalationEntry(
                    escalation_id="feat-1-q1",
                    feature="feat", round=1,
                    question="Q?", context="ctx",
                ),
                escalations_path=path,
            )
            data = _parse_jsonl(path)[0]
            for field in ("type", "escalation_id", "feature", "round",
                          "question", "context", "ts"):
                self.assertIn(field, data, msg=f"Missing field: {field}")
                self.assertIsNotNone(data[field])
            self.assertEqual(data["type"], "escalation")

    # ------------------------------------------------------------------
    # Req 6: resolution entry field presence
    # ------------------------------------------------------------------

    def test_resolution_entry_has_required_fields(self):
        """Manually appended resolution entry has all expected fields."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            record = {
                "type": "resolution",
                "escalation_id": "feat-1-q1",
                "feature": "feat",
                "answer": "yes",
                "resolved_by": "orchestrator",
                "ts": _now_iso(),
            }
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            data = _parse_jsonl(path)[0]
            for field in ("type", "escalation_id", "feature",
                          "answer", "resolved_by", "ts"):
                self.assertIn(field, data, msg=f"Missing field: {field}")

    # ------------------------------------------------------------------
    # Req 7: promoted entry field presence
    # ------------------------------------------------------------------

    def test_promoted_entry_has_required_fields(self):
        """Manually appended promoted entry has all expected fields."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            record = {
                "type": "promoted",
                "escalation_id": "feat-1-q1",
                "feature": "feat",
                "promoted_by": "orchestrator",
                "ts": _now_iso(),
            }
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            data = _parse_jsonl(path)[0]
            for field in ("type", "escalation_id", "feature", "promoted_by", "ts"):
                self.assertIn(field, data, msg=f"Missing field: {field}")

    # ------------------------------------------------------------------
    # Req 8: escalation_id consistency
    # ------------------------------------------------------------------

    def test_escalation_id_consistent_across_escalation_and_resolution(self):
        """The escalation_id in a resolution entry matches the original escalation."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escalations.jsonl"
            eid = "feat-1-q1"
            write_escalation(
                EscalationEntry(
                    escalation_id=eid,
                    feature="feat", round=1,
                    question="Q?", context="ctx",
                ),
                escalations_path=path,
            )
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "resolution",
                    "escalation_id": eid,
                    "feature": "feat",
                    "answer": "done",
                    "resolved_by": "orchestrator",
                    "ts": _now_iso(),
                }) + "\n")

            entries = _parse_jsonl(path)
            esc_ids = {e["escalation_id"] for e in entries if e["type"] == "escalation"}
            res_ids = {e["escalation_id"] for e in entries if e["type"] == "resolution"}
            self.assertEqual(esc_ids, res_ids)


if __name__ == "__main__":
    unittest.main()
