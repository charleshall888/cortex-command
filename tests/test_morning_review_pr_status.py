"""Tests for cortex-morning-review-pr-status — the verb that finds and
classifies the overnight integration PR for walkthrough Section 6.

``gh`` is replaced by a PATH-injected stub that prints ``$PR_STUB_JSON`` and
exits ``$PR_STUB_EXIT``, so every state the verb can emit is driven by data.
Each state is asserted against the verb's real output, and the ``several`` /
``merged`` cases pin the two rules the prose used to carry: never pick a PR
on the reader's behalf, and never treat a merged same-named branch as proof
this session's work landed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cortex_command.overnight import pr_status as prs

STUB = """#!/usr/bin/env bash
if [ -n "${PR_STUB_EXIT:-}" ] && [ "${PR_STUB_EXIT}" != "0" ]; then
  echo "stub failure" >&2
  exit "${PR_STUB_EXIT}"
fi
printf '%s\\n' "${PR_STUB_JSON:-[]}"
"""


@pytest.fixture
def gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Install the gh stub on PATH and return a setter for its response."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(STUB)
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("PR_STUB_EXIT", raising=False)

    def _set(payload=None, exit_code: int = 0) -> None:
        monkeypatch.setenv("PR_STUB_JSON", json.dumps(payload if payload is not None else []))
        monkeypatch.setenv("PR_STUB_EXIT", str(exit_code))

    return _set


def _state(tmp_path: Path, **fields) -> Path:
    p = tmp_path / "overnight-state.json"
    p.write_text(json.dumps({"integration_branch": "overnight/s1", "worktree_path": "/tmp/wt", **fields}))
    return p


def _pr(number: int, state: str, draft: bool = False) -> dict:
    return {"number": number, "url": f"https://example.test/pr/{number}",
            "state": state, "title": f"PR {number}", "isDraft": draft}


def test_missing_state_file_is_no_branch(tmp_path: Path, gh) -> None:
    r = prs.pr_status(state_path=tmp_path / "absent.json", project_root=tmp_path)
    assert r["state"] == "no-branch"
    assert "No integration branch" in r["message"]


def test_empty_branch_is_no_branch(tmp_path: Path, gh) -> None:
    r = prs.pr_status(state_path=_state(tmp_path, integration_branch=""), project_root=tmp_path)
    assert r["state"] == "no-branch"


def test_gh_failure_is_gh_error(tmp_path: Path, gh) -> None:
    gh([], exit_code=4)
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "gh-error"
    assert "exited 4" in r["message"]


def test_gh_missing_is_gh_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "gh-error"


def test_no_pr(tmp_path: Path, gh) -> None:
    gh([])
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "no-pr"
    assert "overnight/s1" in r["message"] and "/pr" in r["message"]


def test_several_lists_candidates_and_picks_none(tmp_path: Path, gh) -> None:
    gh([_pr(1, "MERGED"), _pr(2, "OPEN")])
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "several"
    assert r["pr"] is None
    assert [c["number"] for c in r["candidates"]] == [1, 2]


def test_merged_reports_only(tmp_path: Path, gh) -> None:
    gh([_pr(7, "MERGED")])
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "merged"
    assert r["pr"]["number"] == 7
    assert "does not establish" in r["message"]


def test_closed(tmp_path: Path, gh) -> None:
    gh([_pr(3, "CLOSED")])
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "closed"


def test_open_carries_draft_flag_and_worktree(tmp_path: Path, gh) -> None:
    gh([_pr(5, "OPEN", draft=True)])
    r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
    assert r["state"] == "open"
    assert r["pr"]["draft"] is True
    assert r["worktree_path"] == "/tmp/wt"
    assert r["integration_branch"] == "overnight/s1"


def test_every_state_is_known(tmp_path: Path, gh) -> None:
    gh([_pr(5, "OPEN")])
    for payload in ([], [_pr(1, "OPEN"), _pr(2, "OPEN")], [_pr(1, "MERGED")], [_pr(1, "CLOSED")], [_pr(1, "OPEN")]):
        gh(payload)
        r = prs.pr_status(state_path=_state(tmp_path), project_root=tmp_path)
        assert r["state"] in prs.KNOWN_STATES


def test_main_emits_json_and_exits_zero(tmp_path: Path, gh, capsys, monkeypatch) -> None:
    gh([_pr(9, "OPEN")])
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    rc = prs.main(["--state", str(_state(tmp_path))])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "open" and out["pr"]["number"] == 9
