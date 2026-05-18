"""Behavior tests for the ``--tag`` filter on ``cortex/backlog/ready.py``.

Covers Reqs 2–7 from spec ``add-tag-filter-to-backlog-query``:

  - Req 2: single ``--tag`` filters to matching items only
  - Req 3: multiple ``--tag`` flags use AND semantics
  - Req 4: tag matching is case-sensitive and exact
  - Req 5: zero matches exits 0 with empty groups (not exit 1)
  - Req 6: ``--tag`` composes with ``--include-blocked``
  - Req 7: existing behavior preserved (snapshot test stays green; also
    catches KeyError regression if ``record["tags"]`` would be read from
    tagless records)

Each test builds its own lean fixture (3–6 records) directly as
``index.json`` dicts plus minimal ``.md`` files. Fixtures are
intentionally separate from ``test_backlog_ready_render.py``'s
``_FIXTURE_RECORDS`` to keep behavior tests decoupled from the wire-
contract snapshot.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_READY_PY = REPO_ROOT / "cortex" / "backlog" / "ready.py"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_record(
    item_id: int,
    *,
    status: str = "backlog",
    priority: str = "medium",
    tags: list[str] | None = None,
    blocked_by: list[str] | None = None,
    uuid: str | None = None,
) -> dict:
    """Build a minimal index.json record dict with a ``tags`` key."""
    return {
        "id": item_id,
        "title": f"item-{item_id}",
        "status": status,
        "priority": priority,
        "type": "feature",
        "blocked_by": blocked_by or [],
        "parent": None,
        "uuid": uuid or f"00000000-0000-0000-0000-{item_id:012d}",
        "tags": tags or [],
    }


def _write_md(backlog_dir: Path, record: dict) -> None:
    """Write a minimal frontmatter ``.md`` file for *record*.

    The stale-index check in ``_check_stale_index`` globs
    ``backlog/[0-9]*-*.md``; without these files the mtime comparison
    never fires but — more importantly — ``_load_full_corpus`` reads
    these files to resolve blocker status for cross-corpus lookups.
    Each file must have a valid ``status:`` line so the blocker resolver
    can determine whether a blocker is terminal or still active.
    """
    slug = record["title"].replace(" ", "-")
    md_path = backlog_dir / f"{record['id']:03d}-{slug}.md"
    tags_yaml = json.dumps(record.get("tags") or [])
    fm_lines = [
        "---",
        'schema_version: "1"',
        f"uuid: {record['uuid']}",
        f"id: {record['id']}",
        f'title: "{record["title"]}"',
        f"status: {record['status']}",
        f"priority: {record['priority']}",
        f"type: {record['type']}",
        f"blocked_by: {json.dumps(record['blocked_by'])}",
        f"parent: {json.dumps(record['parent'])}",
        f"tags: {tags_yaml}",
        "---",
        "",
    ]
    md_path.write_text("\n".join(fm_lines), encoding="utf-8")


def _build_backlog(tmp_path: Path, records: list[dict]) -> Path:
    """Materialize *records* under ``tmp_path/cortex/backlog/``.

    ``index.json`` includes only non-terminal records (mirroring
    ``collect_items()`` which filters terminal statuses out). All
    records are written as ``.md`` so ``_load_full_corpus`` can resolve
    blocker references to terminal items.
    """
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    for r in records:
        _write_md(backlog_dir, r)

    terminal = {"complete", "cancelled", "abandoned", "archived"}
    active = [r for r in records if r["status"] not in terminal]
    (backlog_dir / "index.json").write_text(
        json.dumps(active, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return backlog_dir


def _run(tmp_path: Path, *cli_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_READY_PY), *cli_args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )


def _all_ids(output_json: dict) -> list[int]:
    """Collect item IDs across all ``groups[*].items``."""
    return [
        item["id"]
        for group in output_json.get("groups", [])
        for item in group.get("items", [])
    ]


def _all_ineligible_ids(output_json: dict) -> list[int]:
    """Collect item IDs across all ``ineligible[*].items``."""
    return [
        item["id"]
        for group in output_json.get("ineligible", [])
        for item in group.get("items", [])
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_tag_match(tmp_path: Path) -> None:
    """Req 2: single ``--tag`` returns only items whose ``tags`` list contains it."""
    records = [
        _make_record(1, tags=["phase2-trigger"]),
        _make_record(2, tags=["other"]),
        _make_record(3, tags=[]),
    ]
    _build_backlog(tmp_path, records)

    result = _run(tmp_path, "--tag", "phase2-trigger")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    ids = _all_ids(data)
    assert ids == [1], f"expected [1], got {ids}"


def test_multi_tag_and_semantics(tmp_path: Path) -> None:
    """Req 3: multiple ``--tag`` flags require ALL tags present (AND semantics)."""
    records = [
        _make_record(1, tags=["tooling-gap"]),
        _make_record(2, tags=["X"]),
        _make_record(3, tags=["tooling-gap", "X"]),
        _make_record(4, tags=[]),
    ]
    _build_backlog(tmp_path, records)

    result = _run(tmp_path, "--tag", "tooling-gap", "--tag", "X")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    ids = _all_ids(data)
    assert ids == [3], f"expected [3] (only item with both tags), got {ids}"


def test_case_sensitive_match(tmp_path: Path) -> None:
    """Req 4: tag matching is case-sensitive; uppercase and lowercase are distinct."""
    records = [
        _make_record(1, tags=["phase2-trigger"]),
        _make_record(2, tags=["PHASE2-TRIGGER"]),
    ]
    _build_backlog(tmp_path, records)

    result_upper = _run(tmp_path, "--tag", "PHASE2-TRIGGER")
    assert result_upper.returncode == 0, result_upper.stderr
    data_upper = json.loads(result_upper.stdout)
    assert _all_ids(data_upper) == [2], (
        "PHASE2-TRIGGER should match only the uppercase-tagged record"
    )

    result_lower = _run(tmp_path, "--tag", "phase2-trigger")
    assert result_lower.returncode == 0, result_lower.stderr
    data_lower = json.loads(result_lower.stdout)
    assert _all_ids(data_lower) == [1], (
        "phase2-trigger should match only the lowercase-tagged record"
    )


def test_zero_match_exits_zero_with_empty_groups(tmp_path: Path) -> None:
    """Req 5: no matching items → exit 0, stdout is valid JSON, every group empty."""
    records = [
        _make_record(1, tags=["phase2-trigger"]),
        _make_record(2, tags=["other"]),
        _make_record(3, tags=[]),
    ]
    _build_backlog(tmp_path, records)

    result = _run(tmp_path, "--tag", "nonexistent-tag-xyz")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)  # must parse without raising
    assert "groups" in data
    for group in data["groups"]:
        assert group["items"] == [], (
            f"Expected empty items for priority {group['priority']!r}, "
            f"got {group['items']}"
        )


def test_filter_applies_to_ineligible(tmp_path: Path) -> None:
    """Req 6: ``--tag`` combined with ``--include-blocked`` filters both arrays."""
    records = [
        # ready (no blocker) with the target tag
        _make_record(1, tags=["phase2-trigger"]),
        # ready (no blocker) WITHOUT the target tag
        _make_record(2, tags=["other"]),
        # blocked (has an ineligible blocker) WITH the target tag
        _make_record(3, tags=["phase2-trigger"], blocked_by=["4"]),
        # the blocker itself (active, non-terminal) — makes item 3 ineligible
        _make_record(4, tags=["other"]),
    ]
    _build_backlog(tmp_path, records)

    result = _run(tmp_path, "--tag", "phase2-trigger", "--include-blocked")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    ready_ids = _all_ids(data)
    assert ready_ids == [1], f"groups should contain only item 1; got {ready_ids}"

    ineligible_ids = _all_ineligible_ids(data)
    assert ineligible_ids == [3], (
        f"ineligible should contain only item 3; got {ineligible_ids}"
    )


def test_blocker_resolution_uses_unfiltered_corpus(tmp_path: Path) -> None:
    """``all_items_ns`` is not filtered by ``--tag`` — blocker status resolves correctly.

    Record A is tagged ``phase2-trigger`` and is blocked by B.
    Record B is tagged ``other`` (NOT matching the filter).
    When running ``--tag phase2-trigger --include-blocked``, B is absent
    from ``records`` (filtered out) but must still be visible to the
    blocker resolver via ``all_items_ns`` so the reason string correctly
    shows B's actual status rather than "blocker not found" or
    "external blocker".
    """
    records = [
        _make_record(
            1,
            status="backlog",
            tags=["phase2-trigger"],
            blocked_by=["2"],
            uuid="00000000-0000-0000-0000-000000000001",
        ),
        _make_record(
            2,
            status="backlog",
            tags=["other"],
            uuid="00000000-0000-0000-0000-000000000002",
        ),
    ]
    _build_backlog(tmp_path, records)

    result = _run(tmp_path, "--tag", "phase2-trigger", "--include-blocked")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    ineligible_items = [
        item
        for group in data.get("ineligible", [])
        for item in group.get("items", [])
    ]
    assert len(ineligible_items) == 1, (
        f"Expected exactly 1 ineligible item (A); got {ineligible_items}"
    )
    item_a = ineligible_items[0]
    assert item_a["id"] == 1

    reason = item_a.get("reason", "")
    # ``partition_ready`` materializes the non-terminal-internal-blocker sentinel
    # as the literal string "blocked by non-terminal internal blocker" when the
    # blocker (B) is found in ``all_items_ns`` and its status is non-terminal.
    # If ``all_items_ns`` is incorrectly narrowed by the tag filter, B becomes
    # invisible to the resolver, which would produce "blocker not found: 2" or
    # classify it as an external reference instead.
    assert reason == "blocked by non-terminal internal blocker", (
        f"Expected 'blocked by non-terminal internal blocker' (proving B was found "
        f"in all_items_ns despite being tag-filtered out of records); got {reason!r}. "
        "If reason is 'blocker not found: 2' the filter incorrectly narrowed "
        "all_items_ns."
    )
