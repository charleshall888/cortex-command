#!/usr/bin/env python3
"""`phase_label` must tolerate a null phase (#411 R1).

`collect_items` emits ``lifecycle_phase=None`` for every backlog item with
no on-disk lifecycle directory — the majority of any real corpus. A caller
rendering whole-corpus item records therefore feeds `phase_label` ``None``
routinely, and the pre-#411 signature (`encoded_phase: str`, with an
unguarded `.endswith()` on the first line) raised `AttributeError` on it.

This lives apart from `test_lifecycle_phase_parity.py` because `None` has
no bash counterpart: the parity suite asserts Python/bash agreement on the
wire-format mapping table, and a null phase never reaches the wire format.
"""

import unittest

from cortex_command.phase_labels import phase_label


class TestPhaseLabelNone(unittest.TestCase):
    def test_none_returns_empty_string(self):
        """The R1 contract: `None` renders as `""`, not a crash."""
        self.assertEqual(phase_label(None), "")

    def test_none_is_distinct_from_empty_string_input(self):
        """`""` already fell through verbatim; `None` joins it, unchanged."""
        self.assertEqual(phase_label(""), "")

    def test_known_mappings_unchanged(self):
        """The null guard must not shadow any existing branch."""
        for encoded, expected in (
            ("research", "Research"),
            ("specify", "Specify"),
            ("plan", "Plan"),
            ("implement:3/7", "Implement (3/7 tasks done)"),
            ("implement-rework:2", "Implement — rework (review cycle 2)"),
            ("review", "Review"),
            ("escalated", "Escalated (REJECTED — needs user direction)"),
            ("complete:awaiting-merge", "Complete (awaiting merge)"),
            ("complete", "Complete"),
            ("plan-paused", "Plan — paused"),
        ):
            with self.subTest(encoded=encoded):
                self.assertEqual(phase_label(encoded), expected)

    def test_unrecognized_phase_still_falls_through_verbatim(self):
        """Open-vocabulary passthrough is load-bearing for #411's feed."""
        for encoded in ("wontfix", "closed", "none"):
            with self.subTest(encoded=encoded):
                self.assertEqual(phase_label(encoded), encoded)


if __name__ == "__main__":
    unittest.main()
