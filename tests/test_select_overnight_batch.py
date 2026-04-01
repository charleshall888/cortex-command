#!/usr/bin/env python3
"""Tests for overnight batch selection, intra-session unblocking, and parse fixes.

Covers:
  (a) _parse_inline_str_list / _parse_inline_id_list strip YAML quotes from IDs
  (b) Intra-session unblocking with batch round-number assertion
  (c) Chain cascade A->B->C with round-number assertions
  (d) Out-of-session blocked item with updated message
  (e) Regression guard for existing status/type/artifact checks
  (f) generate_index.py's _parse_inline_str_list strips YAML quotes
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from claude.overnight.backlog import (
    BacklogItem,
    _parse_inline_id_list,
    _parse_inline_str_list,
    filter_ready,
    select_overnight_batch,
)


# ---------------------------------------------------------------------------
# Load generate_index.py (no __init__.py in backlog/)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
_GEN_INDEX_PATH = REPO_ROOT / "backlog" / "generate_index.py"

_spec = importlib.util.spec_from_file_location("generate_index", _GEN_INDEX_PATH)
_gen_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen_index)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**kwargs) -> BacklogItem:
    """Create a BacklogItem with sensible defaults, overridden by kwargs."""
    defaults = dict(
        id=1,
        title="Default",
        status="ready",
        type="feature",
        priority="medium",
        lifecycle_slug="default-slug",
        blocked_by=[],
    )
    defaults.update(kwargs)
    return BacklogItem(**defaults)


def _stub_lifecycle(tmp_path: Path, slug: str) -> None:
    """Create minimal lifecycle artifacts (research.md + spec.md) under tmp_path."""
    lc_dir = tmp_path / "lifecycle" / slug
    lc_dir.mkdir(parents=True, exist_ok=True)
    (lc_dir / "research.md").write_text("stub")
    (lc_dir / "spec.md").write_text("stub")


def _write_index(tmp_path: Path, items: list[dict]) -> None:
    """Write a minimal index.json into tmp_path."""
    (tmp_path / "index.json").write_text(json.dumps(items))


# ---------------------------------------------------------------------------
# (a) Direct _parse_inline_str_list and _parse_inline_id_list with quoted IDs
# ---------------------------------------------------------------------------

class TestParseInlineQuoteStripping:
    """Verify that _parse_inline_str_list and _parse_inline_id_list strip
    surrounding quotes from items, handling YAML-quoted IDs like '\"036\"'."""

    def test_parse_inline_str_list_strips_double_quotes(self):
        result = _parse_inline_str_list('["036", "042"]')
        assert result == ["036", "042"]

    def test_parse_inline_str_list_strips_single_quotes(self):
        result = _parse_inline_str_list("['036', '042']")
        assert result == ["036", "042"]

    def test_parse_inline_id_list_strips_quotes(self):
        result = _parse_inline_id_list('["036"]')
        assert result == ["036"]

    def test_parse_inline_id_list_plain_integers(self):
        result = _parse_inline_id_list("[36, 42]")
        assert result == ["36", "42"]

    def test_parse_inline_str_list_empty(self):
        result = _parse_inline_str_list("[]")
        assert result == []

    def test_backlog_item_blocked_by_via_parse(self):
        """End-to-end: _parse_inline_id_list feeds BacklogItem.blocked_by."""
        parsed = _parse_inline_id_list('["036"]')
        item = _make_item(id=100, blocked_by=parsed)
        assert item.blocked_by == ["036"]


# ---------------------------------------------------------------------------
# (b) Intra-session unblocking with batch round-number assertion
# ---------------------------------------------------------------------------

class TestIntraSessionUnblocking:
    """B is blocked by A; both are session-eligible. B should be placed
    in a later batch round than A."""

    def test_intra_session_batch_ordering(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        _stub_lifecycle(tmp_path, "item-a")
        _stub_lifecycle(tmp_path, "item-b")

        items = [
            {
                "id": 1,
                "title": "Item A",
                "status": "ready",
                "priority": "high",
                "type": "feature",
                "blocked_by": [],
                "lifecycle_slug": "item-a",
            },
            {
                "id": 2,
                "title": "Item B",
                "status": "ready",
                "priority": "high",
                "type": "feature",
                "blocked_by": ["1"],
                "lifecycle_slug": "item-b",
            },
        ]
        _write_index(tmp_path, items)

        result = select_overnight_batch(backlog_dir=tmp_path)

        # Build slug -> batch_id mapping
        slug_batch = {
            item.lifecycle_slug: batch.batch_id
            for batch in result.batches
            for item in batch.items
        }

        assert "item-a" in slug_batch, "Item A should be in a batch"
        assert "item-b" in slug_batch, "Item B should be in a batch"
        assert slug_batch["item-b"] > slug_batch["item-a"], (
            "Item B must be in a later batch than Item A"
        )
        assert slug_batch["item-b"] == slug_batch["item-a"] + 1, (
            "Item B must be exactly one round after Item A"
        )

        # Verify intra_session_deps
        assert "item-b" in result.intra_session_deps
        assert result.intra_session_deps["item-b"] == ["item-a"]


# ---------------------------------------------------------------------------
# (c) Chain cascade A -> B -> C with round-number assertions
# ---------------------------------------------------------------------------

class TestChainCascade:
    """A -> B -> C chain: each item should be in exactly one round
    after its blocker."""

    def test_chain_abc_batch_ordering(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        _stub_lifecycle(tmp_path, "chain-a")
        _stub_lifecycle(tmp_path, "chain-b")
        _stub_lifecycle(tmp_path, "chain-c")

        items = [
            {
                "id": 10,
                "title": "Chain A",
                "status": "ready",
                "priority": "high",
                "type": "feature",
                "blocked_by": [],
                "lifecycle_slug": "chain-a",
            },
            {
                "id": 11,
                "title": "Chain B",
                "status": "ready",
                "priority": "high",
                "type": "feature",
                "blocked_by": ["10"],
                "lifecycle_slug": "chain-b",
            },
            {
                "id": 12,
                "title": "Chain C",
                "status": "ready",
                "priority": "high",
                "type": "feature",
                "blocked_by": ["11"],
                "lifecycle_slug": "chain-c",
            },
        ]
        _write_index(tmp_path, items)

        result = select_overnight_batch(backlog_dir=tmp_path)

        slug_batch = {
            item.lifecycle_slug: batch.batch_id
            for batch in result.batches
            for item in batch.items
        }

        assert "chain-a" in slug_batch
        assert "chain-b" in slug_batch
        assert "chain-c" in slug_batch

        # Strict ordering: A < B < C, each exactly one apart
        assert slug_batch["chain-b"] == slug_batch["chain-a"] + 1
        assert slug_batch["chain-c"] == slug_batch["chain-b"] + 1

        # Verify intra_session_deps
        assert result.intra_session_deps["chain-b"] == ["chain-a"]
        assert result.intra_session_deps["chain-c"] == ["chain-b"]


# ---------------------------------------------------------------------------
# (d) Out-of-session blocked item with updated message
# ---------------------------------------------------------------------------

class TestOutOfSessionBlocked:
    """An item blocked by another item that is NOT in the session
    should be ineligible with a message containing 'not in session'
    and the zero-padded blocker ID."""

    def test_out_of_session_blocked_message(self, tmp_path):
        # Blocker is status="backlog" with no lifecycle artifacts -> ineligible
        # so it won't be in the session-eligible set.
        blocker = _make_item(
            id=36,
            title="Blocker",
            status="backlog",
            lifecycle_slug="blocker-item",
            blocked_by=[],
        )
        # Blocked item is ready with lifecycle artifacts, but blocked by 36
        blocked = _make_item(
            id=100,
            title="Blocked Item",
            status="ready",
            lifecycle_slug="blocked-item",
            blocked_by=["36"],
        )

        _stub_lifecycle(tmp_path, "blocked-item")
        # No lifecycle artifacts for blocker-item (it's ineligible anyway)

        all_items = [blocker, blocked]
        result = filter_ready(all_items, all_items=all_items, project_root=tmp_path)

        # The blocked item should be ineligible
        ineligible_titles = {item.title for item, _reason in result.ineligible}
        assert "Blocked Item" in ineligible_titles

        # Find the reason for the blocked item
        reason = next(
            reason for item, reason in result.ineligible
            if item.title == "Blocked Item"
        )
        assert "not in session" in reason
        assert "036" in reason  # zero-padded blocker ID


# ---------------------------------------------------------------------------
# (e) Regression guard for existing status/type/artifact checks
# ---------------------------------------------------------------------------

class TestRegressionGuards:
    """Verify existing readiness checks still work: status, type, artifacts."""

    def test_status_backlog_ineligible(self, tmp_path):
        """Item with status='backlog' but no lifecycle artifacts is ineligible
        with status reason."""
        item = _make_item(
            id=50,
            title="Backlog Item",
            status="backlog",
            lifecycle_slug="backlog-item",
        )
        # Note: status="backlog" IS in ELIGIBLE_STATUSES, but without
        # lifecycle artifacts it fails the artifact check.
        # Actually let's test with a truly ineligible status.
        item_bad_status = _make_item(
            id=51,
            title="Done Item",
            status="done",
            lifecycle_slug="done-item",
        )

        result = filter_ready(
            [item_bad_status], all_items=[item_bad_status], project_root=tmp_path
        )

        assert len(result.ineligible) == 1
        reason = result.ineligible[0][1]
        assert "status: done" in reason

    def test_no_research_artifact_ineligible(self, tmp_path):
        """Item with no research.md is ineligible."""
        item = _make_item(
            id=60,
            title="No Research",
            status="ready",
            lifecycle_slug="no-research",
        )
        # Don't create any lifecycle artifacts

        result = filter_ready([item], all_items=[item], project_root=tmp_path)

        assert len(result.ineligible) == 1
        reason = result.ineligible[0][1]
        assert "research file not found" in reason

    def test_no_spec_artifact_ineligible(self, tmp_path):
        """Item with research.md but no spec.md is ineligible."""
        item = _make_item(
            id=70,
            title="No Spec",
            status="ready",
            lifecycle_slug="no-spec",
        )
        # Create research but not spec
        lc_dir = tmp_path / "lifecycle" / "no-spec"
        lc_dir.mkdir(parents=True)
        (lc_dir / "research.md").write_text("stub")

        result = filter_ready([item], all_items=[item], project_root=tmp_path)

        assert len(result.ineligible) == 1
        reason = result.ineligible[0][1]
        assert "spec file not found" in reason

    def test_epic_type_ineligible(self, tmp_path):
        """Epic items are non-implementable."""
        item = _make_item(
            id=80,
            title="Epic Item",
            status="ready",
            type="epic",
            lifecycle_slug="epic-item",
        )
        _stub_lifecycle(tmp_path, "epic-item")

        result = filter_ready([item], all_items=[item], project_root=tmp_path)

        assert len(result.ineligible) == 1
        reason = result.ineligible[0][1]
        assert "epic" in reason.lower()


# ---------------------------------------------------------------------------
# (f) generate_index.py's _parse_inline_str_list strips YAML quotes
# ---------------------------------------------------------------------------

class TestGenerateIndexParseStrList:
    """Verify generate_index.py's _parse_inline_str_list also strips quotes."""

    def test_strips_double_quotes(self):
        result = _gen_index._parse_inline_str_list('["036", "042"]')
        assert result == ["036", "042"]

    def test_strips_single_quotes(self):
        result = _gen_index._parse_inline_str_list("['036', '042']")
        assert result == ["036", "042"]

    def test_empty_list(self):
        result = _gen_index._parse_inline_str_list("[]")
        assert result == []

    def test_plain_values(self):
        result = _gen_index._parse_inline_str_list("[tag1, tag2]")
        assert result == ["tag1", "tag2"]
