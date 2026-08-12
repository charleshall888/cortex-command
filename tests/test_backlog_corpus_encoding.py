"""One non-UTF-8 file under cortex/backlog/ must not take down the scan.

``collect_items`` read every item with a bare ``path.read_text(encoding="utf-8")``
and no guard, so a single file that is not valid UTF-8 raised
``UnicodeDecodeError`` out of the scan and took every caller with it:

  - ``cortex-backlog-index`` / ``cortex-backlog-ready`` fail outright.
  - The dashboard's ``_poll_slow`` raised on its first sweep and kept raising.
    Because the failure came *before* any snapshot had ever been committed,
    the fault path's "retain the last-good snapshot" behaviour had nothing to
    retain, and the whole backlog navigator read "awaiting first poll" for the
    life of the process — a broken surface wearing a loading state.

``common.py`` had already ratified the fix for the same hazard on
``events.log`` (spec R5: reads flow through ``errors="replace"`` so a corrupt
byte cannot crash a reader). These tests pin that the corpus scan is held to
the same rule, and — the half that matters — that a stray byte costs the
board one item's legibility rather than every item's visibility.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.backlog.generate_index import collect_items


def _write_item(backlog_dir: Path, item_id: int, slug: str, *, status: str = "backlog") -> None:
    (backlog_dir / f"{item_id:03d}-{slug}.md").write_text(
        "---\n"
        'schema_version: "1"\n'
        f"uuid: 00000000-0000-0000-0000-{item_id:012d}\n"
        f"id: {item_id}\n"
        f'title: "{slug.replace("-", " ")}"\n'
        f"status: {status}\n"
        "priority: medium\n"
        "type: feature\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )


@pytest.fixture
def corpus(tmp_path):
    """Three readable items plus one file that is not valid UTF-8."""
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    for i, slug in enumerate(("first", "second", "third"), start=1):
        _write_item(backlog, i, slug)
    # A latin-1 encoded title: the realistic shape of this, not a random blob.
    # 0xb1 is not a valid UTF-8 start byte.
    (backlog / "004-latin1-title.md").write_bytes(
        "---\nid: 4\ntitle: \"caf\N{PLUS-MINUS SIGN}\"\nstatus: backlog\n"
        "priority: medium\ntype: feature\n---\n\nBody.\n".encode("latin-1")
    )
    return backlog


def test_the_scan_does_not_raise(corpus):
    collect_items(corpus, corpus.parent / "lifecycle")


def test_every_readable_item_still_reaches_the_caller(corpus):
    """The blast radius is the one bad file, not the corpus.

    This is the assertion that distinguishes the fix from `except: continue`
    applied one level too high — a guard around the loop would also stop the
    raise, and would also drop the three good items on the floor.
    """
    active_items, active_ids, _archive_ids, _all_items = collect_items(corpus, corpus.parent / "lifecycle")

    assert {1, 2, 3} <= active_ids
    assert {"first second", "second", "third"} & {
        str(item.get("title", "")) for item in active_items
    }


def test_the_undecodable_item_is_kept_rather_than_dropped(corpus):
    """Lossy decode, not skip: an item invisible to the board is worse.

    A dropped record is one an operator cannot see is missing; a replacement
    character in one title is visibly wrong exactly where it is wrong.
    """
    _active_items, active_ids, _archive_ids, _all_items = collect_items(corpus, corpus.parent / "lifecycle")

    assert 4 in active_ids


def test_a_genuinely_binary_file_is_dropped_by_frontmatter_parsing(tmp_path):
    """Tolerating the bytes must not admit a non-item to the board.

    "This is not a ticket" is the frontmatter parser's call, and it still
    makes it — a lossy decode of random bytes yields no ``---`` fence.
    """
    backlog = tmp_path / "cortex" / "backlog"
    backlog.mkdir(parents=True)
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    _write_item(backlog, 1, "real")
    (backlog / "002-binary.md").write_bytes(bytes(range(256)) * 4)
    _active_items, active_ids, _archive_ids, _all_items = collect_items(backlog, backlog.parent / "lifecycle")

    assert 1 in active_ids
    assert 2 not in active_ids
