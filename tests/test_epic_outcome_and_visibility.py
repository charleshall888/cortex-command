"""Tests for #438 — an epic's recorded outcome, membership, and visibility.

Three defects, one ticket:

  1. The epic map read the active-only index, so an epic became invisible the
     moment it closed — 2 of 35 epics were visible in this repo.
  2. A parent epic was closed with a hardcoded ``complete`` regardless of how
     its children actually ended, so an epic whose scope was dropped read as
     delivered.
  3. A closed epic absorbed later children with no signal and no timestamp
     change (one absorbed a child 39 days after closing).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from cortex_command.backlog.build_epic_map import build_epic_map
from cortex_command.backlog.generate_index import collect_items, full_corpus
from cortex_command.backlog.update_item import _derive_parent_outcome


def _write(backlog_dir, item_id, title, *, status, item_type="feature",
           parent=None, uuid=None):
    fm = [
        "---",
        'schema_version: "1"',
        f"uuid: {uuid or f'0000000-{item_id}'}",
        f"title: {title}",
        f"status: {status}",
        "priority: medium",
        f"type: {item_type}",
        "created: 2026-01-01",
        "updated: 2026-01-01",
    ]
    if parent is not None:
        fm.append(f'parent: "{parent}"')
    fm += ["---", "", "## Why", "", "Body.", ""]
    p = backlog_dir / f"{item_id:03d}-{title.lower().replace(' ', '-')}.md"
    p.write_text("\n".join(fm), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Arm 1 — a closed epic is still visible to the epic map
# ---------------------------------------------------------------------------

class TestClosedEpicsAreVisible:

    def test_terminal_epic_reaches_the_epic_map(self, tmp_path):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        _write(backlog, 100, "Closed Epic", status="complete", item_type="epic")
        _write(backlog, 101, "Done Child", status="complete", parent=100)

        items, _active, _arc, all_items = collect_items(backlog, tmp_path / "lc")

        assert items == [], "a closed epic must not widen the active list"
        epics = build_epic_map(full_corpus(all_items))["epics"]
        assert "100" in epics, "the epic map must see the epic even once closed"
        assert [c["id"] for c in epics["100"]["children"]] == [101]

    def test_active_index_is_unchanged_by_the_wider_corpus(self, tmp_path):
        """The ready list must not widen with the map."""
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        _write(backlog, 100, "Closed Epic", status="complete", item_type="epic")
        _write(backlog, 102, "Open Item", status="backlog")

        items, active_ids, _arc, all_items = collect_items(backlog, tmp_path / "lc")

        assert [i["id"] for i in items] == [102]
        assert active_ids == {102}
        assert {r["id"] for r in full_corpus(all_items)} == {100, 102}

    def test_full_corpus_excludes_archive_stubs(self, tmp_path):
        """Archived entries are id/status/uuid stubs and cannot be epics."""
        backlog = tmp_path / "cortex" / "backlog"
        (backlog / "archive").mkdir(parents=True)
        _write(backlog / "archive", 200, "Archived", status="complete")
        _write(backlog, 100, "Closed Epic", status="complete", item_type="epic")

        _items, _active, _arc, all_items = collect_items(backlog, tmp_path / "lc")

        assert {r["id"] for r in full_corpus(all_items)} == {100}

    def test_index_full_json_is_written(self, tmp_path, monkeypatch):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
        _write(backlog, 100, "Closed Epic", status="complete", item_type="epic")
        _write(backlog, 102, "Open Item", status="backlog")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        from cortex_command.backlog import generate_index
        generate_index.main()

        active = json.loads((backlog / "index.json").read_text())
        full = json.loads((backlog / "index-full.json").read_text())
        assert [i["id"] for i in active] == [102]
        assert sorted(i["id"] for i in full) == [100, 102]


# ---------------------------------------------------------------------------
# Arm 2 — the parent's outcome follows its children's
# ---------------------------------------------------------------------------

class TestParentOutcomeDerivation:

    def test_all_complete_closes_complete(self):
        assert _derive_parent_outcome(["complete", "complete"]) == "complete"

    def test_all_abandoned_closes_abandoned(self):
        """An epic whose whole scope was dropped must not read as delivered."""
        assert _derive_parent_outcome(["abandoned", "abandoned"]) == "abandoned"

    def test_spellings_of_one_outcome_still_agree(self):
        """`wontfix` normalizes to `abandoned`, so these agree."""
        assert _derive_parent_outcome(["wontfix", "abandoned"]) == "abandoned"

    def test_done_and_complete_agree(self):
        assert _derive_parent_outcome(["done", "complete"]) == "complete"

    def test_mixed_outcomes_stay_complete(self):
        """No vocabulary exists for a mixed epic — explicitly out of scope."""
        assert _derive_parent_outcome(["complete", "abandoned"]) == "complete"

    def test_single_child_carries_its_outcome(self):
        assert _derive_parent_outcome(["superseded"]) == "superseded"


class TestCascadeUsesDerivedOutcome:

    def test_parent_of_all_abandoned_children_closes_abandoned(self, tmp_path, monkeypatch):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
        epic = _write(backlog, 300, "Dropped Epic", status="backlog", item_type="epic")
        _write(backlog, 301, "Child A", status="abandoned", parent=300)
        child_b = _write(backlog, 302, "Child B", status="backlog", parent=300)
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        from cortex_command.backlog.update_item import _check_and_close_parent
        _write(backlog, 302, "Child B", status="abandoned", parent=300)
        closed = _check_and_close_parent(child_b, "2026-08-03", backlog_dir=backlog)

        assert closed is not None
        assert "status: abandoned" in epic.read_text()
        assert "status: complete" not in epic.read_text()


# ---------------------------------------------------------------------------
# Arm 3 — a late-arriving child is audible
# ---------------------------------------------------------------------------

class TestLateArrivingChildIsSurfaced:

    def test_child_finishing_under_closed_parent_says_so(self, tmp_path, capsys):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        _write(backlog, 400, "Closed Epic", status="complete", item_type="epic")
        child = _write(backlog, 401, "Late Child", status="complete", parent=400)

        from cortex_command.backlog.update_item import _check_and_close_parent
        result = _check_and_close_parent(child, "2026-08-03", backlog_dir=backlog)

        assert result is None, "must not reopen — the race would undo a human close"
        err = capsys.readouterr().err
        assert "already" in err and "400" in err

    def test_creating_under_a_closed_epic_warns(self, tmp_path, monkeypatch):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
        _write(backlog, 500, "Closed Epic", status="complete", item_type="epic")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        proc = subprocess.run(
            [sys.executable, "-m", "cortex_command.backlog.create_item",
             "--title", "Late Arrival", "--status", "backlog",
             "--type", "feature", "--parent", "500"],
            capture_output=True, text=True, cwd=tmp_path,
        )

        assert proc.returncode == 0, proc.stderr
        assert "already" in proc.stderr
        assert "500" in proc.stderr

    def test_creating_under_an_open_epic_is_silent(self, tmp_path, monkeypatch):
        backlog = tmp_path / "cortex" / "backlog"
        backlog.mkdir(parents=True)
        (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
        _write(backlog, 501, "Open Epic", status="backlog", item_type="epic")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        proc = subprocess.run(
            [sys.executable, "-m", "cortex_command.backlog.create_item",
             "--title", "Normal Child", "--status", "backlog",
             "--type", "feature", "--parent", "501"],
            capture_output=True, text=True, cwd=tmp_path,
        )

        assert proc.returncode == 0, proc.stderr
        assert "Warning" not in proc.stderr
