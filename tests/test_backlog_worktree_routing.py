"""Integration tests: Python-layer backlog writes route through worktree.

Covers lifecycle 130:
  - Task 1 / Task 6: outcome_router._write_back_to_backlog writes to the
    configured worktree backlog dir, never to the home repo's backlog/.
  - Task 3: create_followup_backlog_items writes to the provided backlog_dir
    and stamps session_id from LIFECYCLE_SESSION_ID (not 'null').
  - Task 1: update_item.update_item raises TypeError when backlog_dir=None.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cortex_command.backlog.update_item import update_item
from cortex_command.overnight.report import (
    NewBacklogItem,
    ReportData,
    create_followup_backlog_items,
)
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState


REPO_ROOT = Path(__file__).resolve().parent.parent
HOME_BACKLOG = REPO_ROOT / "backlog"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _mk_item(path: Path, slug: str, *, status: str = "refined",
             session_id: str = "null", uuid: str = "00000000") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    p = path / f"{slug}.md"
    p.write_text(
        "---\n"
        f'schema_version: "1"\n'
        f"uuid: {uuid}\n"
        f'title: "test"\n'
        f"status: {status}\n"
        f"session_id: {session_id}\n"
        "---\n"
    )
    return p


def _frontmatter(p: Path, key: str) -> str | None:
    for line in p.read_text().splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return None


def test_update_item_raises_on_none_backlog_dir(tmp_path: Path):
    """Internal API must raise TypeError rather than silently fall back to cwd."""
    item = _mk_item(tmp_path / "backlog", "001-foo")
    with pytest.raises(TypeError, match="backlog_dir is required"):
        update_item(item, {"status": "complete"}, None)  # type: ignore[arg-type]


def test_update_item_writes_to_passed_backlog_dir(tmp_path: Path):
    """update_item must mutate the item in the passed backlog_dir only."""
    worktree_backlog = tmp_path / "worktree" / "backlog"
    item = _mk_item(worktree_backlog, "001-x", status="refined",
                    session_id="null", uuid="11111111")

    update_item(item, {"status": "in_progress"}, worktree_backlog,
                session_id="sess-abc")

    assert _frontmatter(item, "status") == "in_progress"
    # Home repo backlog untouched.
    assert not (HOME_BACKLOG / "001-x.md").exists()


def test_write_back_to_backlog_routes_to_worktree(tmp_path: Path, monkeypatch):
    """outcome_router._write_back_to_backlog writes to worktree, not home."""
    from cortex_command.overnight import outcome_router

    worktree_backlog = tmp_path / "worktree" / "backlog"
    _mk_item(worktree_backlog, "001-test-feature", status="refined",
             session_id="null", uuid="22222222")

    # Set the router's worktree binding (set by orchestrator.py:143).
    outcome_router.set_backlog_dir(worktree_backlog)
    try:
        monkeypatch.setenv("LIFECYCLE_SESSION_ID", "overnight-route-test")
        outcome_router._write_back_to_backlog(
            feature="test-feature",
            overnight_status="failed",
            round_number=1,
            log_path=tmp_path / "events.log",
        )
    finally:
        outcome_router.set_backlog_dir(None)  # type: ignore[arg-type]

    # Item was rewritten in the worktree.
    worktree_item = worktree_backlog / "001-test-feature.md"
    assert _frontmatter(worktree_item, "status") == "refined"

    # No collateral write in the home-repo backlog.
    home_copy = HOME_BACKLOG / "001-test-feature.md"
    assert not home_copy.exists()


def test_create_followup_backlog_items_writes_to_passed_dir(
    tmp_path: Path, monkeypatch
):
    """Followups land in the passed backlog_dir with session_id from env."""
    worktree_backlog = tmp_path / "worktree" / "backlog"
    worktree_backlog.mkdir(parents=True)

    state = OvernightState(
        session_id="overnight-route-followup",
        phase="executing",
        current_round=1,
        features={
            "broken-feature": OvernightFeatureStatus(
                status="failed",
                error="boom",
            ),
        },
    )
    data = ReportData(
        session_id=state.session_id,
        state=state,
    )

    monkeypatch.setenv("LIFECYCLE_SESSION_ID", "overnight-route-followup")
    items = create_followup_backlog_items(data, backlog_dir=worktree_backlog)

    assert len(items) == 1
    [new_item] = items
    followup = worktree_backlog / new_item.filename
    assert followup.exists()
    # session_id must NOT be null — spec R5.
    sid = _frontmatter(followup, "session_id")
    assert sid == "overnight-route-followup", (
        f"expected session_id from env, got {sid!r}"
    )
    # Home repo backlog untouched.
    assert not (HOME_BACKLOG / new_item.filename).exists()


def test_create_followup_session_id_defaults_to_manual(
    tmp_path: Path, monkeypatch
):
    """When LIFECYCLE_SESSION_ID is unset, session_id is 'manual' (not null)."""
    worktree_backlog = tmp_path / "worktree" / "backlog"
    worktree_backlog.mkdir(parents=True)

    state = OvernightState(
        session_id="s",
        phase="executing",
        current_round=1,
        features={
            "deferred-feature": OvernightFeatureStatus(status="deferred"),
        },
    )
    data = ReportData(session_id=state.session_id, state=state)

    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    items = create_followup_backlog_items(data, backlog_dir=worktree_backlog)
    assert len(items) == 1
    followup = worktree_backlog / items[0].filename
    assert _frontmatter(followup, "session_id") == "manual"
