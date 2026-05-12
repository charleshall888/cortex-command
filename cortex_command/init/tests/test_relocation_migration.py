"""Unit tests for the one-time encoded-data migration script.

Tests each of the three migration branches independently and asserts
idempotency (running the script twice produces zero file changes on the
second pass).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.init._relocation_migration import (
    migrate_backlog,
    migrate_decomposed,
    migrate_residue_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backlog(root: Path, filename: str, content: str) -> Path:
    backlog_dir = root / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    p = backlog_dir / filename
    p.write_text(content, encoding="utf-8")
    return p


def _make_residue(root: Path, slug: str, artifact: str, archive: bool = False) -> Path:
    lc_dir = root / "lifecycle"
    if archive:
        lc_dir = lc_dir / "archive"
    feature_dir = lc_dir / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    p = feature_dir / "critical-review-residue.json"
    data = {
        "ts": "2026-01-01T00:00:00Z",
        "feature": slug,
        "artifact": artifact,
        "synthesis_status": "ok",
    }
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def _make_decomposed(root: Path, topic: str, content: str, archive: bool = False) -> Path:
    r_dir = root / "research"
    if archive:
        r_dir = r_dir / "archive"
    topic_dir = r_dir / topic
    topic_dir.mkdir(parents=True, exist_ok=True)
    p = topic_dir / "decomposed.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Branch 1: backlog YAML fields
# ---------------------------------------------------------------------------


BACKLOG_CONTENT_NEEDS_MIGRATION = """\
---
id: "042"
title: Example feature
discovery_source: research/some-topic/research.md
spec: lifecycle/some-slug/spec.md
plan: lifecycle/some-slug/plan.md
research: research/some-topic/research.md
---
Body text here.
"""

BACKLOG_CONTENT_ALREADY_MIGRATED = """\
---
id: "042"
title: Example feature
discovery_source: cortex/research/some-topic/research.md
spec: cortex/lifecycle/some-slug/spec.md
plan: cortex/lifecycle/some-slug/plan.md
research: cortex/research/some-topic/research.md
---
Body text here.
"""

BACKLOG_CONTENT_MIXED = """\
---
id: "099"
title: Mixed item
discovery_source: research/topic-a/research.md
spec: cortex/lifecycle/already-done/spec.md
---
"""


class TestMigrateBacklog:
    def test_bare_fields_get_cortex_prefix(self, tmp_path: Path) -> None:
        _make_backlog(tmp_path, "042-example.md", BACKLOG_CONTENT_NEEDS_MIGRATION)
        changes = migrate_backlog(tmp_path)
        result = (tmp_path / "backlog" / "042-example.md").read_text()
        assert "cortex/research/some-topic/research.md" in result
        assert "cortex/lifecycle/some-slug/spec.md" in result
        assert "cortex/lifecycle/some-slug/plan.md" in result
        assert changes == 4  # four fields updated

    def test_already_prefixed_fields_unchanged(self, tmp_path: Path) -> None:
        f = _make_backlog(tmp_path, "042-migrated.md", BACKLOG_CONTENT_ALREADY_MIGRATED)
        original = f.read_text()
        changes = migrate_backlog(tmp_path)
        assert changes == 0
        assert f.read_text() == original

    def test_idempotency(self, tmp_path: Path) -> None:
        _make_backlog(tmp_path, "042-example.md", BACKLOG_CONTENT_NEEDS_MIGRATION)
        migrate_backlog(tmp_path)
        content_after_first = (tmp_path / "backlog" / "042-example.md").read_text()
        changes_second = migrate_backlog(tmp_path)
        assert changes_second == 0
        assert (tmp_path / "backlog" / "042-example.md").read_text() == content_after_first

    def test_mixed_fields_only_updates_bare_ones(self, tmp_path: Path) -> None:
        _make_backlog(tmp_path, "099-mixed.md", BACKLOG_CONTENT_MIXED)
        changes = migrate_backlog(tmp_path)
        result = (tmp_path / "backlog" / "099-mixed.md").read_text()
        # bare discovery_source gets prefixed
        assert "cortex/research/topic-a/research.md" in result
        # already-prefixed spec stays untouched
        assert "cortex/lifecycle/already-done/spec.md" in result
        assert changes == 1

    def test_no_backlog_dir_returns_zero(self, tmp_path: Path) -> None:
        changes = migrate_backlog(tmp_path)
        assert changes == 0

    def test_body_text_not_modified(self, tmp_path: Path) -> None:
        content = (
            "---\ndiscovery_source: research/x/research.md\n---\n"
            "lifecycle/some-slug/ is referenced in prose here.\n"
        )
        f = _make_backlog(tmp_path, "001.md", content)
        migrate_backlog(tmp_path)
        result = f.read_text()
        # The YAML field gets updated
        assert "cortex/research/x/research.md" in result
        # The prose line (not a YAML field) should be left alone
        assert "lifecycle/some-slug/ is referenced in prose here." in result


# ---------------------------------------------------------------------------
# Branch 2: critical-review-residue.json artifact keys
# ---------------------------------------------------------------------------


class TestMigrateResidueJson:
    def test_bare_artifact_gets_prefix(self, tmp_path: Path) -> None:
        _make_residue(tmp_path, "some-feature", "lifecycle/some-feature/plan.md")
        changes = migrate_residue_json(tmp_path)
        data = json.loads(
            (tmp_path / "lifecycle" / "some-feature" / "critical-review-residue.json")
            .read_text()
        )
        assert data["artifact"] == "cortex/lifecycle/some-feature/plan.md"
        assert changes == 1

    def test_already_prefixed_artifact_unchanged(self, tmp_path: Path) -> None:
        f = _make_residue(
            tmp_path, "done-feature", "cortex/lifecycle/done-feature/plan.md"
        )
        original = f.read_text()
        changes = migrate_residue_json(tmp_path)
        assert changes == 0
        assert f.read_text() == original

    def test_idempotency(self, tmp_path: Path) -> None:
        _make_residue(tmp_path, "my-feat", "lifecycle/my-feat/plan.md")
        migrate_residue_json(tmp_path)
        content_after_first = (
            tmp_path / "lifecycle" / "my-feat" / "critical-review-residue.json"
        ).read_text()
        changes_second = migrate_residue_json(tmp_path)
        assert changes_second == 0

    def test_archive_residue_also_migrated(self, tmp_path: Path) -> None:
        _make_residue(
            tmp_path, "old-feature", "lifecycle/archive/old-feature/plan.md", archive=True
        )
        changes = migrate_residue_json(tmp_path)
        data = json.loads(
            (
                tmp_path
                / "lifecycle"
                / "archive"
                / "old-feature"
                / "critical-review-residue.json"
            ).read_text()
        )
        assert data["artifact"] == "cortex/lifecycle/archive/old-feature/plan.md"
        assert changes == 1

    def test_no_lifecycle_dir_returns_zero(self, tmp_path: Path) -> None:
        changes = migrate_residue_json(tmp_path)
        assert changes == 0

    def test_non_path_artifact_untouched(self, tmp_path: Path) -> None:
        """Artifact values that don't start with lifecycle/backlog/research/ stay put."""
        f = _make_residue(tmp_path, "edge-case", "some-other-value")
        original_data = json.loads(f.read_text())
        changes = migrate_residue_json(tmp_path)
        assert changes == 0
        assert json.loads(f.read_text())["artifact"] == "some-other-value"

    def test_unicode_preserved(self, tmp_path: Path) -> None:
        slug = "unicode-feat"
        lc_dir = tmp_path / "lifecycle" / slug
        lc_dir.mkdir(parents=True)
        p = lc_dir / "critical-review-residue.json"
        data = {
            "artifact": "lifecycle/unicode-feat/plan.md",
            "note": "café 中文",
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        migrate_residue_json(tmp_path)
        result = json.loads(p.read_text())
        assert result["note"] == "café 中文"
        assert result["artifact"] == "cortex/lifecycle/unicode-feat/plan.md"


# ---------------------------------------------------------------------------
# Branch 3: research/*/decomposed.md prose cross-refs
# ---------------------------------------------------------------------------


DECOMPOSED_NEEDS_MIGRATION = """\
# Tickets

- `backlog/082-some-item.md` — epic
- `backlog/083-another-item.md`
- See lifecycle/some-slug/ for context.
- lifecycle/other-slug/ has more detail.
"""

DECOMPOSED_ALREADY_MIGRATED = """\
# Tickets

- `cortex/backlog/082-some-item.md` — epic
- `cortex/backlog/083-another-item.md`
- See cortex/lifecycle/some-slug/ for context.
- cortex/lifecycle/other-slug/ has more detail.
"""


class TestMigrateDecomposed:
    def test_bare_refs_get_prefixed(self, tmp_path: Path) -> None:
        _make_decomposed(tmp_path, "some-topic", DECOMPOSED_NEEDS_MIGRATION)
        changes = migrate_decomposed(tmp_path)
        result = (tmp_path / "research" / "some-topic" / "decomposed.md").read_text()
        assert "cortex/backlog/082-some-item.md" in result
        assert "cortex/backlog/083-another-item.md" in result
        assert "cortex/lifecycle/some-slug/" in result
        assert "cortex/lifecycle/other-slug/" in result
        assert changes == 4

    def test_already_prefixed_refs_unchanged(self, tmp_path: Path) -> None:
        f = _make_decomposed(tmp_path, "done-topic", DECOMPOSED_ALREADY_MIGRATED)
        original = f.read_text()
        changes = migrate_decomposed(tmp_path)
        assert changes == 0
        assert f.read_text() == original

    def test_idempotency(self, tmp_path: Path) -> None:
        _make_decomposed(tmp_path, "my-topic", DECOMPOSED_NEEDS_MIGRATION)
        migrate_decomposed(tmp_path)
        content_after_first = (
            tmp_path / "research" / "my-topic" / "decomposed.md"
        ).read_text()
        changes_second = migrate_decomposed(tmp_path)
        assert changes_second == 0
        assert (
            tmp_path / "research" / "my-topic" / "decomposed.md"
        ).read_text() == content_after_first

    def test_archive_decomposed_also_migrated(self, tmp_path: Path) -> None:
        _make_decomposed(
            tmp_path, "old-topic", "- `backlog/001-old.md`\n", archive=True
        )
        changes = migrate_decomposed(tmp_path)
        result = (
            tmp_path / "research" / "archive" / "old-topic" / "decomposed.md"
        ).read_text()
        assert "cortex/backlog/001-old.md" in result
        assert changes == 1

    def test_no_research_dir_returns_zero(self, tmp_path: Path) -> None:
        changes = migrate_decomposed(tmp_path)
        assert changes == 0

    def test_cortex_lifecycle_prose_not_double_prefixed(self, tmp_path: Path) -> None:
        """Existing ``cortex/lifecycle/`` prose must not gain a second prefix."""
        content = "- `cortex/lifecycle/already-done/spec.md`\n"
        f = _make_decomposed(tmp_path, "safe-topic", content)
        migrate_decomposed(tmp_path)
        result = f.read_text()
        # Should still appear exactly once and not as cortex/cortex/lifecycle/...
        assert result.count("cortex/lifecycle/already-done/spec.md") == 1
        assert "cortex/cortex/" not in result
