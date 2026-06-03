"""Regression test for ready.py regenerate-on-miss (untrack-backlog-index-cache).

When ``cortex/backlog/index.json`` is absent, ``cortex-backlog-ready`` must
treat it as a cache miss — regenerate the records in-memory from the backlog
``.md`` files (no disk write) and exit 0 — rather than hard-failing with
``backlog/index.json not found``. This pins the contract that lets the index
be an untracked, regenerated local cache.

Runs in-process against the working-tree ``ready.main()`` (with
``BACKLOG_DIR`` monkeypatched to a tmp fixture) so it exercises the source
tree, not the installed wheel/binstub.
"""

from __future__ import annotations

import json
from pathlib import Path

import cortex_command.backlog.ready as ready_mod


def _write_item(
    backlog_dir: Path,
    item_id: int,
    slug: str,
    *,
    status: str = "refined",
    priority: str = "medium",
    item_type: str = "feature",
) -> None:
    """Write a minimal ``NNN-slug.md`` frontmatter file the index reads."""
    title = slug.replace("-", " ")
    fm_lines = [
        "---",
        'schema_version: "1"',
        f"uuid: 00000000-0000-0000-0000-{item_id:012d}",
        f"id: {item_id}",
        f'title: "{title}"',
        f"status: {status}",
        f"priority: {priority}",
        f"type: {item_type}",
        "blocked_by: []",
        "parent: null",
        "---",
        "",
    ]
    (backlog_dir / f"{item_id:03d}-{slug}.md").write_text(
        "\n".join(fm_lines), encoding="utf-8"
    )


def test_ready_regenerates_on_missing_index(tmp_path, monkeypatch, capsys):
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)
    # lifecycle dir is resolved as BACKLOG_DIR.parent / "lifecycle" by the
    # regenerate-on-miss path; create it empty so collect_items has a dir.
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    _write_item(backlog_dir, 1, "alpha", priority="high")
    _write_item(backlog_dir, 2, "beta", priority="low")

    # The cache-miss path: no index.json exists.
    assert not (backlog_dir / "index.json").exists()

    monkeypatch.setattr(ready_mod, "BACKLOG_DIR", backlog_dir)
    rc = ready_mod.main([])

    assert rc == 0, "ready.py must regenerate on a missing index, not hard-fail"

    out = capsys.readouterr().out
    data = json.loads(out)
    assert "groups" in data, "output must carry the wire-contract 'groups' key"

    # Regeneration is in-memory: nothing is written to disk.
    assert not (backlog_dir / "index.json").exists(), (
        "regenerate-on-miss must not write index.json to disk"
    )

    # Both active, unblocked items surface in the priority groups.
    ids = {item["id"] for group in data["groups"] for item in group["items"]}
    assert {1, 2} <= ids, f"expected items 1 and 2 in groups, got {ids}"
