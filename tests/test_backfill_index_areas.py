"""Coverage for ``cortex-lifecycle-backfill-index-areas`` (#472).

Exercises the four load-bearing cases named in the plan task: a linked index
gaining ``areas:`` from its parent item, a second run being a byte-identical
no-op, an unlinked Shape-B index staying untouched (no ``areas:`` field at
all), and a linked index whose item declares no ``areas:`` staying untouched.
Also covers the zero-padded-id resolution edge case and the item-absent /
stale-link skip.

The date seam ``backfill_index_areas._today`` is monkeypatched to a fixed
value so the ``updated:`` bump on a real write is deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.lifecycle import backfill_index_areas as bia
from cortex_command.lifecycle.backfill_index_areas import backfill_index_areas

DATE = "2026-08-07"
DATE2 = "2026-08-08"


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_ticket(
    root: Path,
    name: str,
    *,
    areas: str | None = None,
    created: str = DATE,
) -> None:
    lines = ["---", "title: 'A ticket'", "uuid: 11111111-1111-1111-1111-111111111111"]
    if areas is not None:
        lines.append(f"areas: {areas}")
    lines += [f"created: {created}", "status: refined", "---", "", "Body.", ""]
    (root / "cortex" / "backlog" / name).write_text("\n".join(lines))


def _write_index(
    root: Path,
    slug: str,
    *,
    parent_backlog_id,
    areas_line: str | None = None,
    extra_frontmatter: str = "",
    body: str = "\nBody.\n",
) -> Path:
    lc = root / "cortex" / "lifecycle" / slug
    lc.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"feature: {slug}\n"
        "parent_backlog_uuid: 11111111-1111-1111-1111-111111111111\n"
        f"parent_backlog_id: {parent_backlog_id}\n"
        "artifacts: [research]\n"
        "tags: [lifecycle]\n"
    )
    if areas_line is not None:
        frontmatter += f"{areas_line}\n"
    frontmatter += extra_frontmatter
    frontmatter += f"created: {DATE}\nupdated: {DATE}\n---\n"
    target = lc / "index.md"
    target.write_text(frontmatter + body)
    return target


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    monkeypatch.setattr(bia, "_today", lambda: DATE2)


# ---------------------------------------------------------------------------
# (a) A linked index gains areas: from its item
# ---------------------------------------------------------------------------


def test_linked_index_gains_areas_from_item(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="['pipeline', 'lifecycle']")
    index = _write_index(root, "foo", parent_backlog_id=42)

    result = backfill_index_areas(root)

    content = index.read_text()
    assert "areas: [pipeline, lifecycle]" in content
    assert result == {
        "signal": "backfilled",
        "total": 1,
        "updated": 1,
        "unchanged": 0,
        "unlinked": 0,
        "skipped": 0,
        "malformed": [],
    }
    # created/artifacts/body preserved; updated: bumped for the real change.
    assert f"created: {DATE}\n" in content
    assert "artifacts: [research]\n" in content
    assert content.endswith("\nBody.\n")
    assert f"updated: {DATE2}\n" in content


# ---------------------------------------------------------------------------
# (b) A second run is a byte-identical no-op
# ---------------------------------------------------------------------------


def test_second_run_is_byte_identical(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="['pipeline']")
    index = _write_index(root, "foo", parent_backlog_id=42)

    first = backfill_index_areas(root)
    assert first["updated"] == 1
    after_first = index.read_text()

    second = backfill_index_areas(root)
    assert second == {
        "signal": "backfilled",
        "total": 1,
        "updated": 0,
        "unchanged": 1,
        "unlinked": 0,
        "skipped": 0,
        "malformed": [],
    }
    assert index.read_text() == after_first


# ---------------------------------------------------------------------------
# (c) An unlinked Shape-B index is left without an areas: field
# ---------------------------------------------------------------------------


def test_unlinked_shape_b_index_gains_no_areas_field(tmp_path):
    root = _repo(tmp_path)
    index = _write_index(root, "adhoc", parent_backlog_id="null")
    before = index.read_text()

    result = backfill_index_areas(root)

    assert index.read_text() == before
    assert "areas:" not in index.read_text()
    assert result["unlinked"] == 1
    assert result["updated"] == 0


# ---------------------------------------------------------------------------
# (d) An index whose item declares no areas: is left untouched
# ---------------------------------------------------------------------------


def test_item_with_no_areas_leaves_index_untouched(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md")  # no areas: on the ticket
    index = _write_index(root, "foo", parent_backlog_id=42)
    before = index.read_text()

    result = backfill_index_areas(root)

    assert index.read_text() == before
    assert "areas:" not in index.read_text()
    assert result["skipped"] == 1
    assert result["updated"] == 0


def test_item_with_empty_areas_list_leaves_index_untouched(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="[]")
    index = _write_index(root, "foo", parent_backlog_id=42)
    before = index.read_text()

    result = backfill_index_areas(root)

    assert index.read_text() == before
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# (e) Item absent / stale link — skipped, not guessed
# ---------------------------------------------------------------------------


def test_item_absent_is_skipped(tmp_path):
    root = _repo(tmp_path)
    # No 42-*.md ticket exists at all.
    index = _write_index(root, "foo", parent_backlog_id=42)
    before = index.read_text()

    result = backfill_index_areas(root)

    assert index.read_text() == before
    assert result["skipped"] == 1


def test_ambiguous_id_match_is_skipped(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="['pipeline']")
    _write_ticket(root, "042-bar.md", areas="['pipeline']")
    index = _write_index(root, "foo", parent_backlog_id=42)
    before = index.read_text()

    result = backfill_index_areas(root)

    assert index.read_text() == before
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# (f) Zero-padded backlog filename resolves against an unpadded id
# ---------------------------------------------------------------------------


def test_zero_padded_backlog_filename_resolves(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "007-foo.md", areas="['pipeline']")
    index = _write_index(root, "foo", parent_backlog_id=7)

    result = backfill_index_areas(root)

    assert "areas: [pipeline]" in index.read_text()
    assert result["updated"] == 1


# ---------------------------------------------------------------------------
# (g) A linked index that already carries no areas: line gains one inserted
# after tags:, matching create_index's field order.
# ---------------------------------------------------------------------------


def test_areas_inserted_after_tags_when_absent(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="['pipeline']")
    index = _write_index(root, "foo", parent_backlog_id=42, areas_line=None)

    backfill_index_areas(root)

    content = index.read_text()
    assert content.index("areas:") > content.index("tags:")


# ---------------------------------------------------------------------------
# (h) Multiple indexes swept in one call; counts add up
# ---------------------------------------------------------------------------


def test_sweeps_multiple_indexes_and_aggregates_counts(tmp_path):
    root = _repo(tmp_path)
    _write_ticket(root, "042-foo.md", areas="['pipeline']")
    _write_index(root, "foo", parent_backlog_id=42)
    _write_index(root, "adhoc", parent_backlog_id="null")

    result = backfill_index_areas(root)

    assert result["total"] == 2
    assert result["updated"] == 1
    assert result["unlinked"] == 1


def test_malformed_index_does_not_abort_the_sweep(tmp_path):
    """A hand-edited index must not leave a whole-tree migration half-applied.

    The malformed file sorts before the well-formed one, so an uncaught parse
    error here would abort the sweep and `later` would never be written --
    silently, with no summary emitted at all.
    """
    root = _repo(tmp_path)
    _write_ticket(root, "042-later.md", areas="['pipeline']")
    _write_index(root, "later", parent_backlog_id=42)

    broken = root / "cortex" / "lifecycle" / "aaa-broken"
    broken.mkdir(parents=True)
    (broken / "index.md").write_text(
        "---\nfeature: aaa-broken\ntags: [unclosed\n  bad: : :\n---\n\n# broken\n",
        encoding="utf-8",
    )

    result = backfill_index_areas(root)

    assert result["malformed"] == ["cortex/lifecycle/aaa-broken/index.md"]
    assert result["total"] == 2
    # The well-formed index after the broken one was still processed.
    assert result["updated"] == 1
    assert "areas: [pipeline]" in (
        root / "cortex" / "lifecycle" / "later" / "index.md"
    ).read_text(encoding="utf-8")
