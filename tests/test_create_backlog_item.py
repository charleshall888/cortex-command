"""Unit tests for :func:`cortex_command.backlog.create_item._get_next_id`.

Covers:
  - No reserved band: 990-999 are ordinary IDs, allocated like any other.
  - Stale pre-containment seed fixtures are ignored, so a contaminated repo's
    ID sequence is not jumped past them.
  - Archived IDs participate in allocation, so an archived ID is never reused.
  - Plain max(all) + 1, and zero-padding of IDs below 1000.
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


def test_allocates_into_the_former_reserved_band(tmp_path: Path) -> None:
    """990-999 carry no reservation: they allocate like any other IDs.

    A corpus topping out at 989 gets "990"; once that item exists, the next
    allocation is "991". The old exclusion made 990 a permanent ceiling.
    """
    _stub(tmp_path, "989-foo.md")

    assert _get_next_id(tmp_path) == "990"

    _stub(tmp_path, "990-bar.md")

    assert _get_next_id(tmp_path) == "991"


def test_ignores_stale_pre_containment_seed_fixtures(tmp_path: Path) -> None:
    """Stray ``99[0-9]-seed-*.md`` files never advance the ID sequence.

    A repo that ran the pre-containment dashboard seeder and never cleaned up
    carries 990-994; the next real ticket must still be "230", not "995".
    """
    _stub(tmp_path, "229-foo.md")
    _stub(tmp_path, "990-seed-feature-alpha.md")
    _stub(tmp_path, "991-seed-feature-beta.md")
    _stub(tmp_path, "992-seed-feature-gamma.md")
    _stub(tmp_path, "993-seed-feature-delta.md")
    _stub(tmp_path, "994-seed-feature-epsilon.md")

    assert _get_next_id(tmp_path) == "230"


def test_includes_archived_ids(tmp_path: Path) -> None:
    """Archived IDs participate in allocation, so they are never reallocated.

    An archived 500 above the main directory's max 010 yields "501".
    """
    _stub(tmp_path, "010-y.md")
    (tmp_path / "archive").mkdir()
    _stub(tmp_path / "archive", "500-x.md")

    assert _get_next_id(tmp_path) == "501"


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


# ---------------------------------------------------------------------------
# #422: the emitted file ends with exactly one newline, so the standard
# pre-commit-hooks `end-of-file-fixer` never modifies it. A modified file
# aborts the caller's commit, and the abort is buried under passing-hook
# output — a deterministic first-attempt failure that self-heals on retry.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        pytest.param("Some body text", id="no-trailing-newline"),
        pytest.param("Some body text\n", id="one-trailing-newline"),
        pytest.param("Some body text\n\n", id="several-trailing-newlines"),
        pytest.param("", id="empty-body"),
        pytest.param(None, id="no-body"),
    ],
)
def test_create_item_emits_exactly_one_trailing_newline(
    body: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The written file ends in exactly one ``\\n`` for every ``body`` shape.

    Both directions abort a commit under ``end-of-file-fixer``: a missing
    trailing newline gets one added, and a surplus one gets truncated.
    ``--body ""`` is included because normalizing the body alone would leave a
    blank line after the frontmatter and fail the same way.
    """
    from cortex_command.backlog import create_item

    monkeypatch.setattr(create_item.subprocess, "run", lambda *a, **k: None)

    item_path = create_item.create_item(
        title="trailing newline probe",
        status="backlog",
        item_type="chore",
        backlog_dir=tmp_path,
        body=body,
    )

    raw = item_path.read_bytes()
    assert raw.endswith(b"\n"), "file must end with a newline"
    assert not raw.endswith(b"\n\n"), "file must not end with a blank line"


def test_create_item_preserves_body_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Newline normalization is confined to the end of the file.

    Interior blank lines are part of the markdown the caller asked for and
    must survive; only the trailing run is collapsed.
    """
    from cortex_command.backlog import create_item

    monkeypatch.setattr(create_item.subprocess, "run", lambda *a, **k: None)

    item_path = create_item.create_item(
        title="body content probe",
        status="backlog",
        item_type="chore",
        backlog_dir=tmp_path,
        body="## Why\n\nFirst para.\n\nSecond para.\n",
    )

    text = item_path.read_text(encoding="utf-8")
    assert text.endswith("## Why\n\nFirst para.\n\nSecond para.\n")


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
