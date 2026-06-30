"""Golden-route-table test for ``cortex-lifecycle-complete-route`` (#331 Task 3).

Pins the exact ``{route, terminal, continue_to, pr_state}`` tuple (and the
terminal-route ``message`` substrings) that
``cortex_command.lifecycle.complete_route.classify`` produces for each of the
12 Complete-phase routes, so the Task-5 prose collapse cannot drift the
contract.

Coverage (Reqs 1, 1b, 2, 4, 5, 6, 7, 7a):
* the 12-route golden table (one parametrized case per branch);
* 4a/4b discrimination via the Task-2 ``$GH_STUB_VIEW_FAIL`` dimension
  (``network`` -> ``pr_unknown`` / ``notfound`` -> ``pr_not_found``);
* gh-absent -> ``pr_state == "unknown"`` / exit 0 (through ``main``);
* ``already_complete`` asserts ``continue_to == "step12"`` (idempotent
  short-circuit);
* zero new ``events.log`` lines written on every route (Req 1b);
* Branch-3 single-match real-fs ``pr.json`` reconstruction (written-then-routed)
  and ``orphan_ambiguous`` multi-match (no write, non-empty ``candidates``);
* the feature-branch (no interactive worktree) 4d path resolving ``<path>`` to
  the checkout root and still routing ``merged_dirty`` on a dirty tree;
* worktree-CWD resolution ignoring ``CORTEX_REPO_ROOT`` (Req 7);
* the Req-7a speculative-caller grep guard.

Fixture idiom mirrors ``cortex_command/tests/test_lifecycle_event.py``
(``tmp_path`` + ``monkeypatch.chdir(root)`` + ``monkeypatch.delenv``) and the
PATH-injected gh stub from ``tests/test_runner_pr_gating.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

import pytest

from cortex_command.lifecycle.complete_route import classify, main

REPO_ROOT = Path(__file__).resolve().parent.parent
GH_STUB_SOURCE = REPO_ROOT / "tests" / "fixtures" / "gh-stub.sh"

SLUG = "feat"

# A benign, non-routing events.log line so the zero-events count assertion has a
# real baseline (neither feature_wontfix nor feature_complete, so it never
# drives Branch 1/2).
_BENIGN_EVENT = json.dumps(
    {"ts": "2026-06-01T00:00:00Z", "event": "research_started", "feature": SLUG}
)


# ---------------------------------------------------------------------------
# Fixture plumbing
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run git with a hermetic identity (mirrors the real-git harness)."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(root: Path) -> None:
    """Initialize an isolated git repo on ``main`` with hooks/gpg disabled."""
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.test", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    _git("config", "commit.gpgsign", "false", cwd=root)
    _git("config", "core.hooksPath", os.devnull, cwd=root)


def _make_root(tmp_path: Path) -> Path:
    """Create ``<tmp>/proj/cortex/lifecycle/<slug>/`` and return the project root."""
    root = tmp_path / "proj"
    (root / "cortex" / "lifecycle" / SLUG).mkdir(parents=True, exist_ok=True)
    return root


def _write_events(root: Path, *rows: str) -> None:
    log = root / "cortex" / "lifecycle" / SLUG / "events.log"
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_pr_json(
    root: Path,
    *,
    number: int = 1,
    url: str = "https://github.com/owner/repo/pull/1",
    head_branch: str = "featbranch",
    repo: str = "owner/repo",
) -> None:
    pr = root / "cortex" / "lifecycle" / SLUG / "pr.json"
    pr.write_text(
        json.dumps(
            {
                "number": number,
                "url": url,
                "head_branch": head_branch,
                "opened_at": "",
                "repo": repo,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _install_gh_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Prepend a PATH dir holding the gh stub as ``gh`` (git stays resolvable)."""
    bin_dir = tmp_path / "ghbin"
    bin_dir.mkdir(exist_ok=True)
    dst = bin_dir / "gh"
    shutil.copy(GH_STUB_SOURCE, dst)
    dst.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _gh_absent_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point PATH at an empty dir so ``shutil.which('gh')`` returns None."""
    empty = tmp_path / "emptybin"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))


def _events_line_count(root: Path) -> int:
    log = root / "cortex" / "lifecycle" / SLUG / "events.log"
    if not log.is_file():
        return 0
    return len([ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()])


# ---------------------------------------------------------------------------
# Per-route builders. Each returns the project root; classify() is invoked by
# the table test with cwd == root.
# ---------------------------------------------------------------------------


def _build_wontfix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(
        root,
        _BENIGN_EVENT,
        json.dumps(
            {"ts": "2026-06-02T01:02:03Z", "event": "feature_wontfix", "feature": SLUG}
        ),
    )
    return root


def _build_already_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(
        root,
        _BENIGN_EVENT,
        json.dumps(
            {
                "ts": "2026-06-02T01:02:03Z",
                "event": "feature_complete",
                "feature": SLUG,
                "tasks_total": 3,
                "rework_cycles": 0,
                "merge_anchor": "merge",
            }
        ),
    )
    return root


def _build_on_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Real repo on main, pr.json absent. A negative control: a stub that WOULD
    # report 5 orphan PRs is on PATH, so a route of on_main (not orphan_ambiguous)
    # proves the orphan probe was bypassed (Req 5).
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "5")
    return root


def _build_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # pr.json absent, not on main (no git -> empty branch), probe returns [].
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    return root


def _build_orphan_ambiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "2")
    return root


def _build_pr_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=5)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_VIEW_FAIL", "network")  # -> Branch 4a
    return root


def _build_pr_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=42)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_VIEW_FAIL", "notfound")  # -> Branch 4b
    return root


def _build_pr_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=7, url="https://github.com/owner/repo/pull/7")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")  # -> Branch 4c
    return root


def _build_merged_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Feature-branch checkout (no interactive worktree). MERGED + dirty tree.
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    # cortex/ artifacts are untracked -> dirty working tree.
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=12, head_branch="featbranch")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "merged-anchored")  # MERGED; git decides
    return root


def _build_merged_clean_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    # MERGED + clean tree + head IS an ancestor of origin/main.
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=10, head_branch="featbranch")
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "c1 fixtures", cwd=root)  # pr.json/events committed -> clean
    _git("branch", "featbranch", cwd=root)  # featbranch == C1
    (root / "other.txt").write_text("y\n")
    _git("add", "other.txt", cwd=root)
    _git("commit", "-m", "c2", cwd=root)  # main advances to C2 (descendant of C1)
    _git("update-ref", "refs/remotes/origin/main", "main", cwd=root)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "merged-anchored")
    return root


def _build_merged_not_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    # MERGED + clean tree + head is NOT an ancestor of origin/main.
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=11, head_branch="divergent")
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "c1 fixtures", cwd=root)  # main == C1, clean
    _git("update-ref", "refs/remotes/origin/main", "main", cwd=root)  # origin/main==C1
    _git("checkout", "-b", "divergent", cwd=root)
    (root / "divfile.txt").write_text("z\n")
    _git("add", "divfile.txt", cwd=root)
    _git("commit", "-m", "c2 divergent", cwd=root)  # divergent == C2 (not in origin/main)
    _git("checkout", "main", cwd=root)  # back on main, clean tree
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "merged-anchored")
    return root


def _build_pr_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=9, url="https://github.com/owner/repo/pull/9")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "closed-unmerged")  # -> Branch 4g
    return root


# ---------------------------------------------------------------------------
# Golden route table. Each row pins the exact 4-tuple plus a message check:
#   msg_mode "empty" -> message must be exactly ""
#   msg_mode "subs"  -> every listed substring must be present in message
# ---------------------------------------------------------------------------

_GOLDEN = [
    # id, builder, route, terminal, continue_to, pr_state, msg_mode, msg_subs
    (
        "wontfix",
        _build_wontfix,
        "wontfix",
        True,
        None,
        "",
        "subs",
        ["lifecycle was wontfix'd at", "nothing to complete (worktree cleanup skipped)."],
    ),
    (
        "already_complete",
        _build_already_complete,
        "already_complete",
        False,
        "step12",
        "",
        "empty",
        [],
    ),
    ("on_main", _build_on_main, "on_main", False, "step9", "", "empty", []),
    ("first_run", _build_first_run, "first_run", False, "step1", "", "empty", []),
    (
        "orphan_ambiguous",
        _build_orphan_ambiguous,
        "orphan_ambiguous",
        False,
        None,
        "",
        "empty",
        [],
    ),
    (
        "pr_unknown",
        _build_pr_unknown,
        "pr_unknown",
        True,
        None,
        "unknown",
        "subs",
        ["PR state unknown; gh unauthenticated or network error; retry later. (Worktree retained.)"],
    ),
    (
        "pr_not_found",
        _build_pr_not_found,
        "pr_not_found",
        True,
        None,
        "",
        "subs",
        ["PR 42 referenced in pr.json was not found on GitHub.", "The PR may have been deleted."],
    ),
    (
        "pr_open",
        _build_pr_open,
        "pr_open",
        True,
        None,
        "OPEN",
        "subs",
        ["PR open at https://github.com/owner/repo/pull/7; merge first."],
    ),
    (
        "merged_dirty",
        _build_merged_dirty,
        "merged_dirty",
        True,
        None,
        "MERGED",
        "subs",
        ["uncommitted changes at", "resolve first."],
    ),
    (
        "merged_clean_ancestor",
        _build_merged_clean_ancestor,
        "merged_clean_ancestor",
        False,
        "step8",
        "MERGED",
        "empty",
        [],
    ),
    (
        "merged_not_ancestor",
        _build_merged_not_ancestor,
        "merged_not_ancestor",
        True,
        None,
        "MERGED",
        "subs",
        ["branch head is not in origin/main", "refusing cleanup until verified."],
    ),
    (
        "pr_closed",
        _build_pr_closed,
        "pr_closed",
        True,
        None,
        "CLOSED",
        "subs",
        ["PR https://github.com/owner/repo/pull/9 was closed without merging.", "(Worktree retained.)"],
    ),
]


@pytest.mark.parametrize(
    "builder,route,terminal,continue_to,pr_state,msg_mode,msg_subs",
    [row[1:] for row in _GOLDEN],
    ids=[row[0] for row in _GOLDEN],
)
def test_golden_route_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder: Callable[[Path, pytest.MonkeyPatch], Path],
    route: str,
    terminal: bool,
    continue_to: Optional[str],
    pr_state: str,
    msg_mode: str,
    msg_subs: list[str],
) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = builder(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    before = _events_line_count(root)
    result = classify(SLUG, root)
    after = _events_line_count(root)

    # The full 4-tuple is pinned exactly.
    assert result["route"] == route
    assert result["terminal"] is terminal
    assert result["continue_to"] == continue_to
    assert result["pr_state"] == pr_state

    # Terminal-message contract.
    if msg_mode == "empty":
        assert result["message"] == "", result["message"]
    else:
        for sub in msg_subs:
            assert sub in result["message"], (route, sub, result["message"])

    # Req 1b: the verb never appends to events.log on any route.
    assert after == before, f"{route} mutated events.log ({before} -> {after})"


# ---------------------------------------------------------------------------
# 4d path resolution: <path> resolves to the checkout root (Req 1/2).
# ---------------------------------------------------------------------------


def test_merged_dirty_path_is_checkout_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_merged_dirty(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    toplevel = _git("rev-parse", "--show-toplevel", cwd=root).stdout.strip()
    result = classify(SLUG, root)

    assert result["route"] == "merged_dirty"
    # The verb resolved <path> to the checkout root (git toplevel), not a
    # phantom interactive worktree, and embeds it verbatim in the message.
    assert result["message"] == f"uncommitted changes at {toplevel}; resolve first."


# ---------------------------------------------------------------------------
# Branch 3 — single-match reconstruction (Req 6).
# ---------------------------------------------------------------------------


def test_branch3_single_match_reconstructs_pr_json_then_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "1")  # exactly one orphan match
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")  # Branch 4c after recon
    monkeypatch.setenv("GH_STUB_REPO", "owner/repo")
    monkeypatch.chdir(root)

    pr_path = root / "cortex" / "lifecycle" / SLUG / "pr.json"
    assert not pr_path.exists()

    result = classify(SLUG, root)

    # Reconstruction happened: pr.json written with the probe-derived fields.
    assert pr_path.exists(), "single-match did not reconstruct pr.json"
    pr_obj = json.loads(pr_path.read_text(encoding="utf-8"))
    assert pr_obj["number"] == 1
    assert pr_obj["head_branch"] == f"interactive/{SLUG}"
    assert pr_obj["repo"] == "owner/repo"
    # url/opened_at are not in the probe response -> left empty (per Task 1 note).
    assert pr_obj["url"] == ""

    # Then fell through to Branch 4 (the stubbed OPEN state -> pr_open).
    assert result["route"] == "pr_open"
    assert result["pr_state"] == "OPEN"
    assert result["pr_number"] == 1
    assert result["head_branch"] == f"interactive/{SLUG}"
    assert "merge first." in result["message"]


# ---------------------------------------------------------------------------
# Branch 3 — multi-match orphan_ambiguous (Req 6): no write, candidates present.
# ---------------------------------------------------------------------------


def test_branch3_multi_match_no_write_with_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "2")  # multiple orphan matches
    monkeypatch.chdir(root)

    pr_path = root / "cortex" / "lifecycle" / SLUG / "pr.json"
    result = classify(SLUG, root)

    assert result["route"] == "orphan_ambiguous"
    assert result["terminal"] is False
    assert result["continue_to"] is None
    # Negative control: multi-match must NOT auto-select / write pr.json.
    assert not pr_path.exists(), "multi-match wrongly wrote pr.json"
    candidates = result.get("candidates")
    assert candidates, "orphan_ambiguous payload missing candidates"
    assert len(candidates) == 2
    assert {c["number"] for c in candidates} == {1, 2}


# ---------------------------------------------------------------------------
# gh-absent -> Branch 4a unknown / exit 0 through the CLI main() (Req 1a, 4).
# ---------------------------------------------------------------------------


def test_gh_absent_routes_unknown_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=3)
    _gh_absent_path(monkeypatch, tmp_path)  # PATH has no gh (nor git)
    monkeypatch.chdir(root)

    rc = main([SLUG])
    assert rc == 0  # never a non-zero exit / traceback

    out = capsys.readouterr().out.strip()
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one JSON line, got {lines!r}"
    payload = json.loads(lines[0])
    # Req 1a: keys present and valid JSON.
    assert {"route", "terminal", "message", "pr_state"} <= set(payload)
    assert payload["pr_state"] == "unknown"
    assert payload["route"] == "pr_unknown"


def test_auth_failure_routes_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # gh present but `gh auth status` non-zero -> Branch 4a (the third failure
    # band: present-but-unauthenticated).
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=4)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_AUTH", "fail")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert result["route"] == "pr_unknown"
    assert result["pr_state"] == "unknown"


# ---------------------------------------------------------------------------
# Worktree-CWD resolution ignoring CORTEX_REPO_ROOT (Req 7).
# ---------------------------------------------------------------------------


def _setup_worktree(base: Path) -> Path:
    """Worktree-shaped marker: a ``.git`` FILE + its own cortex/ tree."""
    worktree_root = base / "worktree"
    (worktree_root / "cortex" / "lifecycle" / SLUG).mkdir(parents=True, exist_ok=True)
    (worktree_root / ".git").write_text("gitdir: /some/main/repo/.git/worktrees/wt\n")
    return worktree_root


def test_worktree_cwd_resolution_ignores_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    worktree_root = _setup_worktree(tmp_path)
    # The worktree's events.log routes to wontfix (a route that returns before
    # any git/gh, so the .git-file marker need not back a real repo).
    wt_log = worktree_root / "cortex" / "lifecycle" / SLUG / "events.log"
    wt_log.write_text(
        json.dumps(
            {"ts": "2026-01-02T03:04:05Z", "event": "feature_wontfix", "feature": SLUG}
        )
        + "\n",
        encoding="utf-8",
    )
    # A divergent main repo (pointed to by CORTEX_REPO_ROOT) whose events.log
    # would instead route to already_complete -> a clean discriminator.
    main_repo = tmp_path / "main-repo"
    (main_repo / "cortex" / "lifecycle" / SLUG).mkdir(parents=True, exist_ok=True)
    main_log = main_repo / "cortex" / "lifecycle" / SLUG / "events.log"
    main_log.write_text(
        json.dumps(
            {"ts": "2026-01-02T03:04:05Z", "event": "feature_complete", "feature": SLUG}
        )
        + "\n",
        encoding="utf-8",
    )
    main_before = main_log.read_text(encoding="utf-8")

    inside = worktree_root / "subdir"
    inside.mkdir()
    monkeypatch.chdir(inside)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(main_repo))

    rc = main([SLUG])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # Read the worktree's events.log (wontfix), NOT the CORTEX_REPO_ROOT main
    # repo's (which would have routed already_complete).
    assert payload["route"] == "wontfix"
    assert "2026-01-02T03:04:05Z" in payload["message"]
    # The main-repo artifacts were never touched.
    assert main_log.read_text(encoding="utf-8") == main_before
    assert not (main_repo / "cortex" / "lifecycle" / SLUG / "pr.json").exists()


# ---------------------------------------------------------------------------
# Req 7a — speculative-caller boundary: no render/observability surface
# references the verb.
# ---------------------------------------------------------------------------


def test_no_speculative_callers_grep_guard() -> None:
    paths = ["claude/statusline.sh", "cortex_command/dashboard/", "hooks/"]
    proc = subprocess.run(
        ["grep", "-rEc", "cortex-lifecycle-complete-route|complete_route", *paths],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    total = 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        tail = line.rsplit(":", 1)[-1] if ":" in line else line
        try:
            total += int(tail)
        except ValueError:
            continue
    assert total == 0, f"speculative caller(s) reference the verb:\n{proc.stdout}"
