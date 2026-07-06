"""Unit tests for :func:`cortex_command.backlog.create_item._get_next_id`.

Covers three cases:
  - Seed range present: IDs 990-999 exist alongside normal IDs; allocator skips
    the seed range and returns max(non-seed) + 1.
  - No seed range: allocator returns max(all) + 1 as usual.
  - Zero-padding: IDs below 1000 are zero-padded to three digits.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command.backlog.create_item import _get_next_id


def _stub(backlog_dir: Path, filename: str) -> None:
    """Write a minimal stub file under backlog_dir."""
    (backlog_dir / filename).write_text("# stub", encoding="utf-8")


def test_skips_seed_range_when_seeds_present(tmp_path: Path) -> None:
    """Allocator skips 990-999 seed range and returns max(non-seed) + 1.

    Backlog contains item 229-foo.md plus seed fixtures 990-994.
    Expected next ID is "230" (229 + 1), not 995.
    """
    _stub(tmp_path, "229-foo.md")
    _stub(tmp_path, "990-seed-alpha.md")
    _stub(tmp_path, "991-seed-beta.md")
    _stub(tmp_path, "992-seed-gamma.md")
    _stub(tmp_path, "993-seed-delta.md")
    _stub(tmp_path, "994-seed-epsilon.md")

    assert _get_next_id(tmp_path) == "230"


def test_falls_back_to_max_plus_one_without_seeds(tmp_path: Path) -> None:
    """Without seed fixtures, allocator returns max(all IDs) + 1.

    Backlog contains 001-foo.md and 229-bar.md; expected next ID is "230".
    """
    _stub(tmp_path, "001-foo.md")
    _stub(tmp_path, "229-bar.md")

    assert _get_next_id(tmp_path) == "230"


def test_zero_pads_small_ids(tmp_path: Path) -> None:
    """IDs below 1000 are zero-padded to three digits.

    Backlog contains only 001-foo.md; expected next ID is "002".
    """
    _stub(tmp_path, "001-foo.md")

    assert _get_next_id(tmp_path) == "002"


# ---------------------------------------------------------------------------
# R2: create_item serializes the title as a YAML-safe single-line scalar so
# embedded quotes/colons round-trip through the strict backlog parser.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "title",
    [
        'Weird: a "quoted" thing',   # embedded double-quote + colon
        "Fix: it's broken",          # embedded apostrophe + colon
    ],
)
def test_create_item_title_round_trips_strict(
    title: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: a created item's title round-trips exactly through the REAL strict
    parser (yaml.safe_load) without raising, even with embedded quote + colon."""
    from cortex_command.backlog import create_item, resolve_item

    # Neutralize the post-write index regeneration so the test stays hermetic
    # (it would otherwise regenerate the real repo's backlog index).
    monkeypatch.setattr(create_item.subprocess, "run", lambda *a, **k: None)

    item_path = create_item.create_item(
        title=title,
        status="backlog",
        item_type="chore",
        backlog_dir=tmp_path,
    )

    fm = resolve_item._parse_frontmatter(item_path)
    assert fm["title"] == title


# ---------------------------------------------------------------------------
# --tags / --areas: writes valid inline-YAML frontmatter, omitted when unset.
# ---------------------------------------------------------------------------

def test_create_item_writes_tags_and_areas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``tags``/``areas`` lists round-trip through the strict parser as
    inline YAML sequences when passed to :func:`create_item.create_item`."""
    from cortex_command.backlog import create_item, resolve_item

    monkeypatch.setattr(create_item.subprocess, "run", lambda *a, **k: None)

    item_path = create_item.create_item(
        title="tags and areas",
        status="backlog",
        item_type="chore",
        backlog_dir=tmp_path,
        tags=["foo", "bar"],
        areas=["skills", "docs"],
    )

    fm = resolve_item._parse_frontmatter(item_path)
    assert fm["tags"] == ["foo", "bar"]
    assert fm["areas"] == ["skills", "docs"]


def test_create_item_omits_tags_and_areas_when_not_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``tags``/``areas`` frontmatter lines are written when the
    corresponding arguments are left at their ``None`` default."""
    from cortex_command.backlog import create_item

    monkeypatch.setattr(create_item.subprocess, "run", lambda *a, **k: None)

    item_path = create_item.create_item(
        title="no tags or areas",
        status="backlog",
        item_type="chore",
        backlog_dir=tmp_path,
    )

    text = item_path.read_text(encoding="utf-8")
    assert "tags:" not in text
    assert "areas:" not in text


def test_create_item_cli_accepts_tags_and_areas_flags(tmp_path: Path) -> None:
    """``cortex-create-backlog-item --tags ... --areas ...`` (space-separated,
    matching ``cortex-update-item``'s ``nargs="*"`` convention) writes valid
    inline-YAML frontmatter."""
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)

    env = {**os.environ, "CORTEX_REPO_ROOT": str(tmp_path)}

    result = subprocess.run(
        [
            sys.executable, "-m", "cortex_command.backlog.create_item",
            "--title", "cli-tags-areas-test",
            "--status", "backlog",
            "--type", "chore",
            "--tags", "foo", "bar",
            "--areas", "skills", "docs",
        ],
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, (
        f"cortex-create-backlog-item exited {result.returncode}: "
        f"{result.stderr.decode(errors='replace')}"
    )

    created_files = [p for p in backlog_dir.glob("*.md") if p.name != "index.md"]
    assert len(created_files) == 1

    from cortex_command.backlog import resolve_item

    fm = resolve_item._parse_frontmatter(created_files[0])
    assert fm["tags"] == ["foo", "bar"]
    assert fm["areas"] == ["skills", "docs"]
