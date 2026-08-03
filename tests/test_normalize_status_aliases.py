"""Tests for `normalize_status`'s recognition of finished-work synonyms (#435).

A finished item must read as finished regardless of which synonym its author
wrote. The offending values arrive by direct frontmatter edit rather than
through the item-creation verb, so the correction has to be read-time: it then
reaches every consumer repo retroactively without touching a stored file.

Observed damage: `pixel-art-generator` carries 33 `complete` and 6 `completed`
items; `completed` was in neither the alias map nor the terminal set, so those
six sat permanently in that repo's active index — its entire active list.
"""

from __future__ import annotations

import pytest

from cortex_command.common import TERMINAL_STATUSES, normalize_status


class TestFinishedSynonymsNormalize:
    """Every recognized finished-work synonym resolves to a terminal status."""

    @pytest.mark.parametrize(
        "raw",
        ["done", "resolved", "closed", "completed"],
    )
    def test_synonym_maps_to_complete(self, raw):
        assert normalize_status(raw) == "complete"

    @pytest.mark.parametrize(
        "raw",
        ["done", "resolved", "closed", "completed", "wontfix", "complete", "abandoned"],
    )
    def test_normalized_synonym_reads_as_terminal(self, raw):
        """The point of the alias: the index's terminal check must accept it."""
        assert normalize_status(raw) in TERMINAL_STATUSES


class TestVocabularyNotNarrowed:
    """#435 must not narrow the terminal set in the same change.

    The parent-closing cascade in `update_item` reads *raw* status against
    `TERMINAL_STATUSES`, so removing a raw value here would make finished work
    read as active. Narrowing is #437's job, after the corpus normalizes.
    """

    @pytest.mark.parametrize(
        "raw",
        ["complete", "abandoned", "done", "resolved", "wontfix", "superseded"],
    )
    def test_raw_terminal_value_still_recognized(self, raw):
        assert raw in TERMINAL_STATUSES


class TestNonFinishedValuesUnaffected:
    """Parked and in-flight values must not be swept into a terminal reading."""

    @pytest.mark.parametrize("raw", ["deferred", "backlog", "refined", "in_progress"])
    def test_unfinished_status_is_not_terminal(self, raw):
        assert normalize_status(raw) not in TERMINAL_STATUSES

    def test_unknown_value_passes_through(self):
        assert normalize_status("some-invented-status") == "some-invented-status"
