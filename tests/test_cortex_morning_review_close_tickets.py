"""Tests for cortex-morning-review-close-tickets — the morning-review
walkthrough §6b per-feature backlog-ticket close-loop façade (the
cortex-read-backlog-backend 3-arm routing, given an explicit caller-passed
list of (feature, identifier) pairs).

Exercises the real resolver/updater primitives
(``cortex_command.backlog.update_item``/``resolve_item``) against real
backlog item fixtures written via ``tests.conftest.make_item`` — the same
fixture helper ``test_update_item_resolution.py`` uses — rather than
monkeypatching them, since the whole point of this verb is composing those
two already-tested primitives; only the backend-routing branches
(none/external) are pure logic and asserted directly.

That real-primitive rule is load-bearing for the ``changed_paths`` group at the
bottom of this file: what those tests pin is what ``update_item`` *actually
wrote*, which a stub returning ``None`` could not tell us. This is why they live
here rather than beside the module under ``cortex_command/overnight/tests/``,
whose ``conftest.py`` installs ``update_item = lambda *a, **kw: None``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight import close_tickets as ct
from tests.conftest import make_item


@pytest.fixture()
def backlog_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cortex" / "backlog"
    d.mkdir(parents=True)
    return d


def _status(item_path: Path) -> str:
    text = item_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def _closed_entry(tmp_path: Path, feature: str, identifier: str) -> dict:
    """Close one item against the tmp fixture root and return its result entry."""
    r = ct.close_tickets(
        [(feature, identifier)], backend="cortex-backlog", project_root=tmp_path
    )
    entry = r["results"][0]
    assert entry["state"] == "closed", entry
    return entry


def test_closed_sets_status_and_reports_id(tmp_path: Path, backlog_dir: Path) -> None:
    item = make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    r = ct.close_tickets([("auth-api", "1")], backend="cortex-backlog", project_root=tmp_path)
    assert r["state"] == "ok"
    assert r["results"] == [
        {
            "feature": "auth-api",
            "state": "closed",
            "id": "001",
            "changed_paths": ["cortex/backlog/001-auth-api.md"],
            "status_changed": True,
        }
    ]
    assert _status(item) == "complete"


def test_no_ticket_found(tmp_path: Path, backlog_dir: Path) -> None:
    make_item(backlog_dir, "001-auth-api.md", "Auth API")
    r = ct.close_tickets(
        [("data-pipeline", "999")], backend="cortex-backlog", project_root=tmp_path
    )
    assert r["results"] == [{"feature": "data-pipeline", "state": "no-ticket"}]


def test_ambiguous_reports_message(tmp_path: Path, backlog_dir: Path) -> None:
    make_item(backlog_dir, "001-fix-thing.md", "Fix the thing")
    make_item(backlog_dir, "002-fix-other.md", "Fix the other thing")
    r = ct.close_tickets([("fix", "fix")], backend="cortex-backlog", project_root=tmp_path)
    assert len(r["results"]) == 1
    entry = r["results"][0]
    assert entry["feature"] == "fix"
    assert entry["state"] == "ambiguous"
    assert "ambiguous" in entry["message"]


def test_backend_none_skips_with_advisory_and_writes_nothing(
    tmp_path: Path, backlog_dir: Path
) -> None:
    item = make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    before = item.read_text()
    r = ct.close_tickets([("auth-api", "1")], backend="none", project_root=tmp_path)
    assert r["results"] == [{"feature": "auth-api", "state": "skipped-disabled"}]
    assert item.read_text() == before


def test_backend_external_reports_external_and_writes_nothing(
    tmp_path: Path, backlog_dir: Path
) -> None:
    item = make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    before = item.read_text()
    r = ct.close_tickets([("auth-api", "1")], backend="jira", project_root=tmp_path)
    assert r["results"] == [{"feature": "auth-api", "state": "external"}]
    assert item.read_text() == before


def test_parent_epic_also_closed_flag(tmp_path: Path, backlog_dir: Path) -> None:
    make_item(backlog_dir, "010-epic.md", "The Epic", extra="status: open\n")
    make_item(
        backlog_dir,
        "011-child-a.md",
        "Child A",
        extra="status: complete\nparent: 10\n",
    )
    child_b = make_item(
        backlog_dir,
        "012-child-b.md",
        "Child B",
        extra="status: in_progress\nparent: 10\n",
    )
    r = ct.close_tickets([("child-b", "12")], backend="cortex-backlog", project_root=tmp_path)
    entry = r["results"][0]
    assert entry["state"] == "closed"
    assert entry["id"] == "012"
    assert entry.get("parent_closed") is True
    assert _status(child_b) == "complete"
    assert _status(backlog_dir / "010-epic.md") == "complete"


def test_batch_processes_multiple_items_independently(tmp_path: Path, backlog_dir: Path) -> None:
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    r = ct.close_tickets(
        [("auth-api", "1"), ("data-pipeline", "999")],
        backend="cortex-backlog",
        project_root=tmp_path,
    )
    assert [entry["feature"] for entry in r["results"]] == ["auth-api", "data-pipeline"]
    assert r["results"][0]["state"] == "closed"
    assert r["results"][1]["state"] == "no-ticket"


def test_empty_items_returns_empty_results(tmp_path: Path, backlog_dir: Path) -> None:
    r = ct.close_tickets([], backend="cortex-backlog", project_root=tmp_path)
    assert r == {"state": "ok", "results": []}


def test_every_item_state_is_known(tmp_path: Path, backlog_dir: Path) -> None:
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    make_item(backlog_dir, "002-fix-thing.md", "Fix the thing")
    make_item(backlog_dir, "003-fix-other.md", "Fix the other thing")

    seen = set()
    seen.add(
        ct.close_tickets([("auth-api", "1")], backend="cortex-backlog", project_root=tmp_path)[
            "results"
        ][0]["state"]
    )
    seen.add(
        ct.close_tickets([("ghost", "999")], backend="cortex-backlog", project_root=tmp_path)[
            "results"
        ][0]["state"]
    )
    seen.add(
        ct.close_tickets([("fix", "fix")], backend="cortex-backlog", project_root=tmp_path)[
            "results"
        ][0]["state"]
    )
    seen.add(
        ct.close_tickets([("auth-api", "1")], backend="none", project_root=tmp_path)["results"][
            0
        ]["state"]
    )
    seen.add(
        ct.close_tickets([("auth-api", "1")], backend="jira", project_root=tmp_path)["results"][
            0
        ]["state"]
    )

    assert seen <= set(ct.KNOWN_ITEM_STATES)
    assert seen == {"closed", "no-ticket", "ambiguous", "skipped-disabled", "external"}


def test_cli_item_flag_parses_repeated_pairs() -> None:
    parser = ct._build_parser()
    args = parser.parse_args(
        ["--item", "auth-api=001", "--item", "data-pipeline=002", "--backend", "cortex-backlog"]
    )
    assert args.items == [("auth-api", "001"), ("data-pipeline", "002")]
    assert args.backend == "cortex-backlog"


def test_cli_item_flag_rejects_missing_equals() -> None:
    parser = ct._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--item", "auth-api-no-identifier", "--backend", "cortex-backlog"])


def test_cli_emits_json(
    tmp_path: Path, backlog_dir: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_item(backlog_dir, "001-auth-api.md", "Auth API", extra="status: in_progress\n")
    # Route main()'s root resolution to the tmp fixture — without this the
    # CLI resolves the developer's real repo and mutates a real backlog item.
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    rc = ct.main(
        [
            "--item", "auth-api=1",
            "--backend", "cortex-backlog",
        ]
    )
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "ok"
    assert obj["results"][0]["state"] == "closed"


def test_cli_no_items_returns_empty_results(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(ct, "close_tickets", lambda items, backend: {"state": "ok", "results": []})
    rc = ct.main(["--backend", "none"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj == {"state": "ok", "results": []}


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def _boom(items, backend):
        raise RuntimeError("boom")

    monkeypatch.setattr(ct, "close_tickets", _boom)
    rc = ct.main(["--backend", "cortex-backlog"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "boom" in obj["message"]


# ---------------------------------------------------------------------------
# changed_paths / status_changed — the pushable set a close produces.
#
# A close writes more than its own item: the terminal-status cascade rewrites
# the parent epic when the last sibling closes, and strips the closed item's
# uuid from every dependent's blocked-by. The committer stages exactly what
# these entries report, so what follows pins the *completeness* of the reported
# set (both cascades appear, unrelated items do not) and its *stageability* (no
# gitignored derived state appears).
# ---------------------------------------------------------------------------


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
    item. An over-broad report would sweep concurrent edits into the commit —
    the exact failure a wholesale `cortex/backlog/*.md` glob would cause."""
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
