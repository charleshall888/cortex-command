"""Tests for generate_index.py deferred-tag rendering and suppression.

Covers Reqs 1–5 from spec backlog-index-surface-deferred-parked-state:

  (a) deferred-tagged status:backlog item — annotated + suppressed
  (b) non-deferred status:backlog control — no annotation, present in grouping
  (c) deferred-tagged status:refined item — suppressed from ## Refined
  (d) Deferred-cased item — annotated + suppressed identically to lowercase
  (e) deferred-feature-work-tagged status:backlog item — NOT annotated, NOT
      suppressed (pins whole-element == match so substring regression fails)
"""

from __future__ import annotations

import json

import pytest

from cortex_command.backlog import generate_index as _gen_index


# ---------------------------------------------------------------------------
# Minimal item dict factory
# ---------------------------------------------------------------------------

def _make_item(**kwargs) -> dict:
    """Return an item dict with sensible defaults, overridden by kwargs.

    Keys mirror the record shape that generate_md and generate_json consume
    (see generate_index.py:186–209).
    """
    defaults: dict = {
        "id": 1,
        "title": "Default Item",
        "status": "backlog",
        "priority": "medium",
        "type": "feature",
        "tags": [],
        "areas": [],
        "created": "",
        "updated": "",
        "blocks": [],
        "blocked_by": [],
        "parent": None,
        "research": None,
        "spec": None,
        "discovery_source": None,
        "plan": None,
        "uuid": None,
        "lifecycle_slug": None,
        "session_id": None,
        "lifecycle_phase": None,
        "schema_version": None,
        "repo": None,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Fixtures shared across tests
# ---------------------------------------------------------------------------

#: (a) deferred-tagged status:backlog item
ITEM_A = _make_item(id=1, title="Parked Feature", status="backlog", tags=["deferred"])

#: (b) non-deferred status:backlog control
ITEM_B = _make_item(id=2, title="Active Feature", status="backlog", tags=[])

#: (c) deferred-tagged status:refined item
ITEM_C = _make_item(id=3, title="Deferred Refined", status="refined", tags=["deferred"])

#: (d) Deferred-cased item (case-insensitive variant)
ITEM_D = _make_item(id=4, title="Capital Deferred", status="backlog", tags=["Deferred"])

#: (e) deferred-feature-work-tagged — whole-element negative control
ITEM_E = _make_item(id=5, title="Work Feature", status="backlog", tags=["deferred-feature-work"])


def _md_for(items: list[dict]) -> str:
    """Call generate_md with the given items as both active and all_items."""
    active_ids = {item["id"] for item in items}
    return _gen_index.generate_md(
        items,
        active_ids=active_ids,
        archive_ids=set(),
        all_items=items,
    )


# ---------------------------------------------------------------------------
# Req 2: Status-cell annotation
# ---------------------------------------------------------------------------

class TestStatusCellAnnotation:
    """generate_md renders '<status> (deferred)' for deferred items and
    '<status>' (no suffix) for non-deferred controls."""

    def test_deferred_item_row_contains_annotation(self):
        """(a) deferred-tagged status:backlog item — full row equality on Status cell."""
        md = _md_for([ITEM_A, ITEM_B])
        # Full rendered table row for item (a)
        expected_row = (
            "| 1 | Parked Feature | backlog (deferred) | medium | feature | — | — | — |"
        )
        assert expected_row in md, (
            f"Expected full row:\n  {expected_row!r}\nnot found in output:\n{md}"
        )

    def test_control_item_row_has_no_deferred_suffix(self):
        """(b) non-deferred status:backlog control — no (deferred) suffix in Status cell."""
        md = _md_for([ITEM_A, ITEM_B])
        expected_row = (
            "| 2 | Active Feature | backlog | medium | feature | — | — | — |"
        )
        assert expected_row in md, (
            f"Expected full row:\n  {expected_row!r}\nnot found in output:\n{md}"
        )

    def test_control_row_does_not_contain_deferred_suffix(self):
        """(b) Confirm the control row contains '| backlog |' not '| backlog (deferred) |'."""
        md = _md_for([ITEM_A, ITEM_B])
        # The control row must NOT carry (deferred)
        assert "| 2 | Active Feature | backlog (deferred) |" not in md


# ---------------------------------------------------------------------------
# Req 4 + Req 5: Actionable suppression and table-row preservation
# ---------------------------------------------------------------------------

class TestGroupingSuppression:
    """Deferred items are absent from ## Backlog / ## Refined bullets but
    their table row is preserved in the master table (Req 5)."""

    def test_deferred_backlog_absent_from_backlog_section(self):
        """(a) deferred-tagged status:backlog — NOT a bullet under ## Backlog."""
        md = _md_for([ITEM_A, ITEM_B])
        backlog_section = md.split("## Backlog", 1)[1] if "## Backlog" in md else ""
        assert "- **1**" not in backlog_section, (
            "Deferred item (id=1) should not appear as a bullet under ## Backlog"
        )

    def test_control_backlog_present_in_backlog_section(self):
        """(b) non-deferred status:backlog control — IS a bullet under ## Backlog."""
        md = _md_for([ITEM_A, ITEM_B])
        backlog_section = md.split("## Backlog", 1)[1] if "## Backlog" in md else ""
        assert "- **2**" in backlog_section, (
            "Control item (id=2) should appear as a bullet under ## Backlog"
        )

    def test_deferred_refined_absent_from_refined_section(self):
        """(c) deferred-tagged status:refined — NOT a bullet under ## Refined."""
        md = _md_for([ITEM_C])
        refined_section = md.split("## Refined", 1)[1] if "## Refined" in md else ""
        # Trim to just the ## Refined section content (stop at next ##)
        refined_section = refined_section.split("##")[0]
        assert "- **3**" not in refined_section, (
            "Deferred refined item (id=3) should not appear as a bullet under ## Refined"
        )

    def test_deferred_item_row_present_in_table(self):
        """(a/Req 5) deferred item id appears in the table region of generate_md output."""
        md = _md_for([ITEM_A, ITEM_B])
        # Table region is before the first ## section header
        table_region = md.split("## ")[0] if "## " in md else md
        assert "| 1 |" in table_region, (
            "Deferred item (id=1) must have a row in the master table even when suppressed"
        )


# ---------------------------------------------------------------------------
# Req 1 (case-variant): Deferred-cased tag fires identically
# ---------------------------------------------------------------------------

class TestCaseInsensitiveDeferred:
    """(d) A 'Deferred'-cased tag is annotated and suppressed identically
    to a lowercase 'deferred' tag (Req 1 case-insensitive match)."""

    def test_capital_deferred_tag_annotates_status_cell(self):
        """(d) 'Deferred'-tagged item row has '| backlog (deferred) |'."""
        md = _md_for([ITEM_D])
        expected_row = (
            "| 4 | Capital Deferred | backlog (deferred) | medium | feature | — | — | — |"
        )
        assert expected_row in md, (
            f"Expected full row:\n  {expected_row!r}\nnot found in output:\n{md}"
        )

    def test_capital_deferred_tag_suppresses_from_backlog_section(self):
        """(d) 'Deferred'-tagged item NOT a bullet under ## Backlog."""
        md = _md_for([ITEM_D])
        backlog_section = md.split("## Backlog", 1)[1] if "## Backlog" in md else ""
        assert "- **4**" not in backlog_section, (
            "Deferred-cased item (id=4) should not appear under ## Backlog"
        )


# ---------------------------------------------------------------------------
# Req 1 (whole-element negative control)
# ---------------------------------------------------------------------------

class TestDeferredFeatureWorkTagIsNotDeferred:
    """(e) 'deferred-feature-work' tag does NOT trigger the deferred signal.

    This pins Req 1's whole-element == match so a substring ('deferred' in
    tag) regression causes this test to fail.
    """

    def test_deferred_feature_work_row_has_no_annotation(self):
        """(e) 'deferred-feature-work'-tagged item row contains '| backlog |' (no suffix)."""
        md = _md_for([ITEM_E])
        expected_row = (
            "| 5 | Work Feature | backlog | medium | feature | — | — | — |"
        )
        assert expected_row in md, (
            f"Expected full row:\n  {expected_row!r}\nnot found in output:\n{md}"
        )

    def test_deferred_feature_work_row_has_no_deferred_suffix(self):
        """(e) Confirm 'deferred-feature-work'-tagged row does NOT have '(deferred)' suffix."""
        md = _md_for([ITEM_E])
        assert "| 5 | Work Feature | backlog (deferred) |" not in md

    def test_deferred_feature_work_present_in_backlog_section(self):
        """(e) 'deferred-feature-work'-tagged item IS a bullet under ## Backlog."""
        md = _md_for([ITEM_E])
        backlog_section = md.split("## Backlog", 1)[1] if "## Backlog" in md else ""
        assert "- **5**" in backlog_section, (
            "deferred-feature-work item (id=5) should appear under ## Backlog"
        )


# ---------------------------------------------------------------------------
# Req 3: index.json record is unchanged
# ---------------------------------------------------------------------------

class TestGenerateJsonUnchanged:
    """(a/Req 3) generate_json for a deferred-tagged item keeps raw status
    and emits the tags array including 'deferred'."""

    def test_json_record_status_is_raw(self):
        """Status field in JSON is the raw 'backlog', not 'backlog (deferred)'."""
        json_str = _gen_index.generate_json([ITEM_A])
        records = json.loads(json_str)
        assert len(records) == 1
        assert records[0]["status"] == "backlog"

    def test_json_record_tags_contains_deferred(self):
        """tags array in JSON includes 'deferred'."""
        json_str = _gen_index.generate_json([ITEM_A])
        records = json.loads(json_str)
        assert "deferred" in records[0]["tags"]
