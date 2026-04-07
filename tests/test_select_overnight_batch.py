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
    Batch,
    _parse_inline_id_list,
    _parse_inline_str_list,
    filter_ready,
    group_into_batches,
    select_overnight_batch,
)
from claude.overnight.plan import _detect_risks


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


# ---------------------------------------------------------------------------
# (g) Area-separation behavior in group_into_batches
# ---------------------------------------------------------------------------

class TestAreaSeparation:
    """Verify that items sharing an area are forced into separate batches."""

    def test_overlap_forced_separation(self):
        """Two items with the same area AND same tags must land in different batches."""
        item_a = _make_item(
            id=1, title="Item A", areas=["overnight-runner"], tags=["auth"],
        )
        item_b = _make_item(
            id=2, title="Item B", areas=["overnight-runner"], tags=["auth"],
        )
        scored = [(item_a, 10.0), (item_b, 9.0)]
        batches = group_into_batches(scored)

        # Each item should be in a different batch
        batch_ids_a = [b.batch_id for b in batches if item_a in b.items]
        batch_ids_b = [b.batch_id for b in batches if item_b in b.items]
        assert len(batch_ids_a) == 1
        assert len(batch_ids_b) == 1
        assert batch_ids_a[0] != batch_ids_b[0]

    def test_silent_absence_allows_same_batch(self):
        """Item with areas and item with empty areas may share a batch (silent absence)."""
        item_a = _make_item(
            id=1, title="Item A", areas=["overnight-runner"], tags=["auth"],
        )
        item_b = _make_item(
            id=2, title="Item B", areas=[], tags=["auth"],
        )
        scored = [(item_a, 10.0), (item_b, 9.0)]
        batches = group_into_batches(scored)

        # They may land in the same batch because item_b has no areas
        batch_ids_a = [b.batch_id for b in batches if item_a in b.items]
        batch_ids_b = [b.batch_id for b in batches if item_b in b.items]
        assert len(batch_ids_a) == 1
        assert len(batch_ids_b) == 1
        assert batch_ids_a[0] == batch_ids_b[0]

    def test_no_overlap_tags_preserved(self):
        """Items with different areas but same tags may share a batch."""
        item_a = _make_item(
            id=1, title="Item A", areas=["overnight-runner"], tags=["auth"],
        )
        item_b = _make_item(
            id=2, title="Item B", areas=["skills"], tags=["auth"],
        )
        scored = [(item_a, 10.0), (item_b, 9.0)]
        batches = group_into_batches(scored)

        # No area overlap, so tag grouping can place them together
        batch_ids_a = [b.batch_id for b in batches if item_a in b.items]
        batch_ids_b = [b.batch_id for b in batches if item_b in b.items]
        assert len(batch_ids_a) == 1
        assert len(batch_ids_b) == 1
        assert batch_ids_a[0] == batch_ids_b[0]

    def test_full_serialization(self):
        """4 items all sharing the same area produce 4 batches of 1 item each."""
        items = [
            _make_item(id=i, title=f"Item {i}", areas=["overnight-runner"], tags=["auth"])
            for i in range(1, 5)
        ]
        scored = [(item, 10.0 - i) for i, item in enumerate(items)]
        batches = group_into_batches(scored)

        # Each item must be in its own batch
        assert len(batches) >= 4
        for item in items:
            containing = [b for b in batches if item in b.items]
            assert len(containing) == 1
            assert len(containing[0].items) == 1


# ---------------------------------------------------------------------------
# (h) _detect_risks replacement: area-overlap-within-batch detection
# ---------------------------------------------------------------------------

class TestDetectRisks:
    """Verify _detect_risks checks area overlap within batches."""

    def test_no_areas_no_risks(self):
        """Batches with items having no areas produce no risks."""
        batch_1 = Batch(
            items=[
                _make_item(id=1, title="A", areas=[]),
                _make_item(id=2, title="B", areas=[]),
            ],
            batch_context="no areas",
            batch_id=1,
        )
        batch_2 = Batch(
            items=[
                _make_item(id=3, title="C", areas=[]),
            ],
            batch_context="no areas",
            batch_id=2,
        )
        risks = _detect_risks([batch_1, batch_2])
        assert risks == []

    def test_area_overlap_within_batch_detected(self):
        """A batch containing two items with the same area triggers a risk."""
        batch = Batch(
            items=[
                _make_item(id=1, title="Item X", areas=["overnight-runner"]),
                _make_item(id=2, title="Item Y", areas=["overnight-runner"]),
            ],
            batch_context="area overlap",
            batch_id=1,
        )
        risks = _detect_risks([batch])
        assert len(risks) > 0
        assert any("overnight-runner" in r for r in risks)


# ---------------------------------------------------------------------------
# (i) BacklogItem.resolve_slug fallback chain
# ---------------------------------------------------------------------------

class TestResolveSlug:
    """Verify resolve_slug priority: lifecycle_slug > spec/research path > slugify(title)."""

    def test_lifecycle_slug_wins(self):
        item = _make_item(
            lifecycle_slug="explicit-slug",
            spec="lifecycle/different-slug/spec.md",
            title="Yet Another Title",
        )
        assert item.resolve_slug() == "explicit-slug"

    def test_spec_path_extraction(self):
        item = _make_item(
            lifecycle_slug=None,
            spec="lifecycle/from-spec-path/spec.md",
            title="Ignored Title",
        )
        assert item.resolve_slug() == "from-spec-path"

    def test_research_path_extraction(self):
        item = _make_item(
            lifecycle_slug=None,
            spec=None,
            research="lifecycle/from-research/research.md",
            title="Ignored Title",
        )
        assert item.resolve_slug() == "from-research"

    def test_falls_through_to_slugify(self):
        item = _make_item(
            lifecycle_slug=None,
            spec=None,
            research=None,
            title="My Feature with_underscores",
        )
        assert item.resolve_slug() == "my-feature-with-underscores"

    def test_spec_preferred_over_research(self):
        item = _make_item(
            lifecycle_slug=None,
            spec="lifecycle/spec-wins/spec.md",
            research="lifecycle/research-loses/research.md",
            title="Ignored",
        )
        assert item.resolve_slug() == "spec-wins"

    def test_bare_filename_spec_falls_through(self):
        """spec: spec.md (no directory) should fall through to slugify."""
        item = _make_item(
            lifecycle_slug=None,
            spec="spec.md",
            title="Bare Filename Feature",
        )
        assert item.resolve_slug() == "bare-filename-feature"

    def test_underscores_become_hyphens_in_slugify_fallback(self):
        """The bug that started it all: session_panel must become session-panel."""
        item = _make_item(
            lifecycle_slug=None,
            spec=None,
            title="Fix inline style violations in session_panel and feature_cards templates",
        )
        assert item.resolve_slug() == "fix-inline-style-violations-in-session-panel-and-feature-cards-templates"
