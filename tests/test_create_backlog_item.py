"""Unit tests for :func:`cortex_command.backlog.create_item._get_next_id`.

Covers three cases:
  - Seed range present: IDs 990-999 exist alongside normal IDs; allocator skips
    the seed range and returns max(non-seed) + 1.
  - No seed range: allocator returns max(all) + 1 as usual.
  - Zero-padding: IDs below 1000 are zero-padded to three digits.
"""

from __future__ import annotations

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
