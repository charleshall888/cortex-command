"""Tests for the ``changed_paths``/``status_changed`` reporting that
cortex-morning-review-close-tickets adds to each ``closed`` entry.

A close writes more than its own item: the terminal-status cascade rewrites the
parent epic when the last sibling closes, and strips the closed item's uuid from
every dependent's ``blocked-by``. Task 10's committer stages exactly what this
reports, so what these tests pin is the *completeness* of the reported set (both
cascades appear) and its *stageability* (no gitignored derived state appears).

The backend-routing arms and the resolver branches are covered in
``tests/test_cortex_morning_review_close_tickets.py``; this file does not repeat
them. Both files drive the real ``update_item``/``resolve_item`` primitives
against real fixtures rather than monkeypatching, since the reported set is
produced by those primitives' actual writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.overnight import close_tickets as ct
from tests.conftest import make_item


@pytest.fixture()
def backlog_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cortex" / "backlog"
    d.mkdir(parents=True)
    return d


def _closed_entry(tmp_path: Path, feature: str, identifier: str) -> dict:
    """Close one item against the tmp fixture root and return its result entry."""
    r = ct.close_tickets(
        [(feature, identifier)], backend="cortex-backlog", project_root=tmp_path
    )
    entry = r["results"][0]
    assert entry["state"] == "closed", entry
    return entry


def test_cascaded_parent_epic_path_is_reported(tmp_path: Path, backlog_dir: Path) -> None:
    """Closing the last open child closes the parent epic — both files were
    written, so both must appear in changed_paths. Reporting only the child
    would strand the epic's close as an uncommitted local edit."""
    make_item(backlog_dir, "010-epic.md", "The Epic", extra="status: open\n")
    make_item(
        backlog_dir, "011-child-a.md", "Child A", extra="status: complete\nparent: 10\n"
    )
    make_item(
        backlog_dir, "012-child-b.md", "Child B", extra="status: in_progress\nparent: 10\n"
    )

    entry = _closed_entry(tmp_path, "child-b", "12")

    assert entry["parent_closed"] is True
    assert set(entry["changed_paths"]) == {
        "cortex/backlog/012-child-b.md",
        "cortex/backlog/010-epic.md",
    }


def test_blocked_by_dependent_path_is_reported(tmp_path: Path, backlog_dir: Path) -> None:
    """The cascade strips the closed item's uuid from every dependent's
    blocked-by. That is a real rewrite of another file and must be reported."""
    uuid = "dadaf6b6-431d-4c5a-92b5-6226be90d26b"
    make_item(
        backlog_dir,
        "020-blocker.md",
        "The Blocker",
        extra=f"status: in_progress\nuuid: {uuid}\n",
    )
    dependent = make_item(
        backlog_dir,
        "021-dependent.md",
        "The Dependent",
        extra=f"status: open\nblocked-by: [{uuid}]\n",
    )

    entry = _closed_entry(tmp_path, "blocker", "20")

    assert "cortex/backlog/021-dependent.md" in entry["changed_paths"]
    # The dependent was really rewritten, not merely named.
    assert "blocked-by: []" in dependent.read_text(encoding="utf-8")


def test_unrelated_item_is_not_reported(tmp_path: Path, backlog_dir: Path) -> None:
    """The cascade skips items whose blocked-by never referenced the closed
    item. An over-broad report would sweep concurrent edits into Task 10's
    commit — the exact failure a `cortex/backlog/*.md` glob would cause."""
    uuid = "dadaf6b6-431d-4c5a-92b5-6226be90d26b"
    make_item(
        backlog_dir,
        "030-blocker.md",
        "The Blocker",
        extra=f"status: in_progress\nuuid: {uuid}\n",
    )
    make_item(
        backlog_dir,
        "031-unrelated.md",
        "Unrelated",
        extra="status: open\nblocked-by: [99999999-0000-0000-0000-000000000000]\n",
    )

    entry = _closed_entry(tmp_path, "blocker", "30")

    assert entry["changed_paths"] == ["cortex/backlog/030-blocker.md"]


def test_no_gitignored_artifact_is_reported(tmp_path: Path, backlog_dir: Path) -> None:
    """The index and the events sidecars are gitignored (cortex/.gitignore).
    Staging one would fail, so neither may appear — even though the close
    really does write the sidecar."""
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")

    entry = _closed_entry(tmp_path, "auth-api", "1")

    # Non-vacuous: the sidecar really was written by this close...
    sidecar = backlog_dir / "001-auth-api.events.jsonl"
    assert sidecar.is_file()
    # ...and is still absent from the reported set, as are the index files.
    names = [Path(p).name for p in entry["changed_paths"]]
    assert "001-auth-api.events.jsonl" not in names
    assert not [n for n in names if n.startswith("index.")]
    assert entry["changed_paths"] == ["cortex/backlog/001-auth-api.md"]


def test_reclose_of_complete_ticket_reports_status_unchanged(
    tmp_path: Path, backlog_dir: Path
) -> None:
    """The overnight success path already sets status:complete before §6b runs,
    so §6b's close is normally a re-close. It still rewrites the file (the
    `updated` bump), so changed_paths stays non-empty — status_changed is the
    only signal that distinguishes a real close from a redundant one."""
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: complete\n")

    entry = _closed_entry(tmp_path, "auth-api", "1")

    assert entry["status_changed"] is False
    assert entry["changed_paths"] == ["cortex/backlog/001-auth-api.md"]


def test_first_close_reports_status_changed(tmp_path: Path, backlog_dir: Path) -> None:
    """Counterpart to the re-close: a genuine open→complete transition reports
    status_changed true, so the flag tracks the transition and is not constant."""
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")

    entry = _closed_entry(tmp_path, "auth-api", "1")

    assert entry["status_changed"] is True
