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


class TestSingleVocabularyDeclaration:
    """The status vocabulary is declared in exactly two places (#437).

    Three constants in `cortex_command/overnight/backlog.py` — STATUSES,
    PRIORITIES and TYPES — sat under a comment claiming they were "for
    validation" with no reader anywhere, and `docs/backlog.md` named STATUSES
    as the canonical list. A reader could not tell which declaration was
    authoritative. These pin the consolidation so they cannot creep back.
    """

    def test_overnight_backlog_declares_no_status_vocabulary(self):
        from cortex_command.overnight import backlog as ob
        for dead in ("STATUSES", "PRIORITIES", "TYPES"):
            assert not hasattr(ob, dead), (
                f"{dead} was removed as unread in #437; a re-added copy is a "
                "second vocabulary declaration competing with common.py"
            )

    def test_overnight_backlog_reuses_the_canonical_terminal_set(self):
        """It must import TERMINAL_STATUSES, not define a divergent tuple."""
        from cortex_command.overnight import backlog as ob
        from cortex_command.common import TERMINAL_STATUSES as canonical
        assert ob.TERMINAL_STATUSES is canonical

    def test_eligible_statuses_survives_as_a_selection_gate(self):
        """ELIGIBLE_STATUSES is read by the dashboard and filter_ready — keep it."""
        from cortex_command.overnight.backlog import ELIGIBLE_STATUSES
        assert "backlog" in ELIGIBLE_STATUSES

    def test_eligible_statuses_is_narrower_than_the_vocabulary(self):
        """The pickup gate is a subset, not a competing vocabulary: no
        terminal status may be overnight-eligible."""
        from cortex_command.overnight.backlog import ELIGIBLE_STATUSES
        from cortex_command.common import TERMINAL_STATUSES
        assert not (set(ELIGIBLE_STATUSES) & set(TERMINAL_STATUSES))

    def test_ready_eligible_set_mirrors_the_overnight_gate(self):
        """`ready.py` mirrors the gate; drift between them is the bug #437 closes."""
        from cortex_command.backlog.ready import _ELIGIBLE_STATUSES
        from cortex_command.overnight.backlog import ELIGIBLE_STATUSES
        assert set(_ELIGIBLE_STATUSES) == set(ELIGIBLE_STATUSES)
