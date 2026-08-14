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
* artifact anchoring: an env root that does not hold this slug's lifecycle is
  ignored (Req 7's surviving intent), and the artifact anchor differs from the
  tree-question anchor within one ``classify`` call;
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

from cortex_command.lifecycle import complete_route, log_resolver
from cortex_command.lifecycle.complete_route import classify, main

REPO_ROOT = Path(__file__).resolve().parent.parent
GH_STUB_SOURCE = REPO_ROOT / "tests" / "fixtures" / "gh-stub.sh"
VERB_SOURCE = REPO_ROOT / "cortex_command" / "lifecycle" / "complete_route.py"

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
# Branch 3 — feature/{slug} fallback probe (recovery-gap fix): the picker
# also produces feature/{slug} branches, so a zero-match interactive/{slug}
# query must fall back to feature/{slug} before concluding first_run.
# ---------------------------------------------------------------------------


def test_orphan_probe_falls_back_to_feature_pattern_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-level pin: interactive/{slug} empty -> feature/{slug} queried next."""
    from cortex_command.lifecycle import complete_route

    seen_heads: list = []

    def _fake_run(cmd, cwd=None, timeout=30):
        head = cmd[cmd.index("--head") + 1]
        seen_heads.append(head)

        class _P:
            returncode = 0
            if head == f"feature/{SLUG}":
                stdout = json.dumps([{"number": 9, "state": "OPEN", "mergedAt": None}])
            else:
                stdout = "[]"

        return _P()

    monkeypatch.setattr(complete_route.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(complete_route, "_run", _fake_run)

    probe = complete_route._orphan_probe(SLUG)

    assert seen_heads == [f"interactive/{SLUG}", f"feature/{SLUG}"]
    assert probe["error"] is False
    assert probe["head_branch"] == f"feature/{SLUG}"
    assert probe["matches"] == [{"number": 9, "state": "OPEN", "mergedAt": None}]


def test_orphan_probe_stops_at_interactive_match_without_querying_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing behavior preserved: an interactive/{slug} match short-circuits."""
    from cortex_command.lifecycle import complete_route

    seen_heads: list = []

    def _fake_run(cmd, cwd=None, timeout=30):
        seen_heads.append(cmd[cmd.index("--head") + 1])

        class _P:
            returncode = 0
            stdout = json.dumps([{"number": 3, "state": "OPEN", "mergedAt": None}])

        return _P()

    monkeypatch.setattr(complete_route.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(complete_route, "_run", _fake_run)

    probe = complete_route._orphan_probe(SLUG)

    assert seen_heads == [f"interactive/{SLUG}"], "feature/{slug} must not be queried"
    assert probe["head_branch"] == f"interactive/{SLUG}"
    assert probe["matches"] == [{"number": 3, "state": "OPEN", "mergedAt": None}]


def test_branch3_feature_head_fallback_single_match_reconstructs_pr_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: interactive/{slug} empty, feature/{slug} has one match."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "1")
    monkeypatch.setenv("GH_STUB_PR_LIST_MATCH_HEAD", f"feature/{SLUG}")
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")  # Branch 4c after recon
    monkeypatch.setenv("GH_STUB_REPO", "owner/repo")
    monkeypatch.chdir(root)

    pr_path = root / "cortex" / "lifecycle" / SLUG / "pr.json"
    assert not pr_path.exists()

    result = classify(SLUG, root)

    assert pr_path.exists(), "feature/{slug} single-match did not reconstruct pr.json"
    pr_obj = json.loads(pr_path.read_text(encoding="utf-8"))
    assert pr_obj["number"] == 1
    assert pr_obj["head_branch"] == f"feature/{SLUG}"
    assert pr_obj["repo"] == "owner/repo"

    assert result["route"] == "pr_open"
    assert result["head_branch"] == f"feature/{SLUG}"


def test_branch3_feature_head_fallback_multi_match_orphan_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: interactive/{slug} empty, feature/{slug} has multiple matches."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "2")
    monkeypatch.setenv("GH_STUB_PR_LIST_MATCH_HEAD", f"feature/{SLUG}")
    monkeypatch.chdir(root)

    pr_path = root / "cortex" / "lifecycle" / SLUG / "pr.json"
    result = classify(SLUG, root)

    assert result["route"] == "orphan_ambiguous"
    assert not pr_path.exists(), "multi-match wrongly wrote pr.json"
    candidates = result.get("candidates")
    assert candidates and len(candidates) == 2


def test_branch3_both_patterns_empty_still_routes_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero matches on both interactive/{slug} and feature/{slug} -> first_run."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert result["route"] == "first_run"


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
# Artifact anchoring: an env root that does not hold this lifecycle is ignored
# (Req 7's surviving intent), and the two anchors are distinct.
# ---------------------------------------------------------------------------


def _setup_worktree(base: Path) -> Path:
    """Worktree-shaped marker: a STALE ``.git`` FILE + its own cortex/ tree.

    The gitdir pointer names a path that does not exist, so every git call from
    this tree fails — the degradation fixture. For a resolvable worktree (one
    whose ``commondir`` reaches a real main root) use :func:`_worktree_fixture`.
    """
    worktree_root = base / "worktree"
    (worktree_root / "cortex" / "lifecycle" / SLUG).mkdir(parents=True, exist_ok=True)
    (worktree_root / ".git").write_text("gitdir: /some/main/repo/.git/worktrees/wt\n")
    return worktree_root


def _worktree_fixture(base: Path) -> tuple[Path, Path]:
    """Main repo + linked worktree, each with a co-located ``cortex/`` tree.

    Mirrors ``cortex_command/lifecycle/tests/test_worktree_log_anchor.py``'s
    fixture: the gitfile points at a real admin dir whose ``commondir`` reaches
    the main root, so ``resolve_main_repo_root`` resolves it. Hand-built for the
    same reason that module builds one — ``git rev-parse`` exits 128 against a
    synthetic worktree (#271).
    """
    base = base.resolve()
    main_root, wt = base / "main", base / "wt"

    admin = main_root / ".git" / "worktrees" / "wt1"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")
    (main_root / "cortex" / "lifecycle" / SLUG).mkdir(parents=True)

    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (wt / "cortex" / "lifecycle" / SLUG).mkdir(parents=True)
    return main_root, wt


def test_env_root_without_this_lifecycle_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A ``CORTEX_REPO_ROOT`` that does not hold this slug never anchors artifacts.

    Supersedes ``test_worktree_cwd_resolution_ignores_env``. Req 7 of
    ``cortex/lifecycle/offload-completemd-pr-state-routing-and/spec.md:35``
    justified resolving artifacts from the CWD because that matched "the
    ``_resolve_user_project_root_from_cwd`` contract ``lifecycle_event`` uses";
    #484 moved that contract to the main-root resolver, so plain CWD anchoring
    is no longer the shared one and the old assertion pinned a superseded
    choice. Req 7's *env-ignoring* intent survives via
    ``log_resolver.resolve_verdict_root``'s validation: the env value is trusted
    only when ``{root}/cortex/lifecycle/{slug}`` exists there, so an env root
    naming a different project is still ignored — asserted here.

    What this discriminates against: replacing ``resolve_verdict_root`` with the
    raw, unvalidated ``resolve_main_repo_root`` (the design fork the critical
    review raised), under which the stranger root anchors the read and the
    wontfix row is invisible. It deliberately does **not** fail against
    pre-change ``complete_route.py`` — that code never consulted the
    environment at all, so no env-based assertion can discriminate against it.
    The spec's original "fails against unmodified code" clause rested on a
    measurement of the *proposed* anchor mis-attributed to HEAD; corrected in
    ``cortex/lifecycle/complete-route-reads-a-cwd-anchored/spec.md`` Reqs 2a/5.
    """
    main_repo, worktree_root = _worktree_fixture(tmp_path)
    # The worktree's events.log routes to wontfix (a route that returns before
    # any git/gh, so the fixture need not back a real repo).
    wt_log = worktree_root / "cortex" / "lifecycle" / SLUG / "events.log"
    wt_log.write_text(
        json.dumps(
            {"ts": "2026-01-02T03:04:05Z", "event": "feature_wontfix", "feature": SLUG}
        )
        + "\n",
        encoding="utf-8",
    )
    # An unrelated cortex project (pointed to by CORTEX_REPO_ROOT) that does NOT
    # carry this slug's lifecycle: validation rejects it, so resolution falls
    # back to the CWD walk and lands in the worktree.
    stranger = tmp_path / "stranger"
    (stranger / "cortex" / "lifecycle" / "other-feature").mkdir(parents=True)

    inside = worktree_root / "subdir"
    inside.mkdir()
    monkeypatch.chdir(inside)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(stranger))

    rc = main([SLUG])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # Read the worktree's events.log (wontfix); the env root held no lifecycle
    # for this slug, so it never became the artifact anchor.
    assert payload["route"] == "wontfix"
    assert "2026-01-02T03:04:05Z" in payload["message"]
    # Neither the env root nor the main repo was written to.
    assert not (stranger / "cortex" / "lifecycle" / SLUG).exists()
    assert not (main_repo / "cortex" / "lifecycle" / SLUG / "pr.json").exists()


def test_classify_never_raises_when_the_verdict_root_cannot_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolver failure degrades to the invoking checkout, never a traceback.

    ``resolve_verdict_root`` guards only its CWD-walk branch; its step-1
    ``resolve_main_repo_root()`` can raise ``CortexProjectRootError``.
    ``record_pr_opened`` catches that; ``classify`` must too, so the never-crash
    contract does not rest on ``main()``'s root walk having already succeeded.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(
        root,
        _BENIGN_EVENT,
        json.dumps(
            {"ts": "2026-06-02T01:02:03Z", "event": "feature_wontfix", "feature": SLUG}
        ),
    )

    def _raise(slug: str) -> Path:
        raise complete_route.CortexProjectRootError("no project root above cwd")

    monkeypatch.setattr(complete_route, "resolve_verdict_root", _raise)
    monkeypatch.chdir(root)

    result = classify(SLUG, root)

    assert result["route"] == "wontfix", (
        f"the fallback anchor was not the invoking checkout: {result['route']!r}"
    )


def test_main_root_pr_json_is_found_from_the_worktree_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 2, read leg: a main-root ``pr.json`` reaches Branch 4 from a worktree.

    This is the direction that discriminates. From the *primary* the invoking
    root and the validated root are the same path, so "classify from the
    primary finds it" cannot fail whatever the anchor is; only the reverse —
    the worktree CWD reading a ``pr.json`` that sits outside its own tree —
    exercises the resolution. A CWD-anchored read finds no ``pr.json`` here,
    falls into the Branch-3 orphan probe and, with the stub reporting zero
    matches, restarts the lifecycle at ``first_run``/step1.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    main_repo, worktree_root = _worktree_fixture(tmp_path)
    _write_pr_json(main_repo, number=7, url="https://github.com/owner/repo/pull/7")
    assert not (worktree_root / "cortex" / "lifecycle" / SLUG / "pr.json").exists(), (
        "fixture invalid: the worktree must hold no pr.json of its own"
    )

    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")  # Branch 4c
    # Zero orphan matches, so a CWD-anchored read cannot re-enter Branch 4 by
    # way of the single-match reconstruction: it lands on first_run instead.
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    monkeypatch.chdir(worktree_root)

    result = classify(SLUG, worktree_root)

    assert result["route"] == "pr_open", (
        f"pr.json resolved from the CWD, not the validated root: {result['route']!r}"
    )
    assert result["pr_state"] == "OPEN"
    assert result["pr_url"] == "https://github.com/owner/repo/pull/7"
    assert result["terminal"] is True
    # The reconstruction arm must not have run: pr.json stays where it was.
    assert not (worktree_root / "cortex" / "lifecycle" / SLUG / "pr.json").exists()


def test_classify_uses_two_distinct_anchors_from_worktree_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One classify() call reads artifacts at the main root, asks git at the CWD.

    Discriminating: the main root's events.log carries a feature_complete row
    (-> already_complete) while the worktree's carries feature_wontfix
    (-> wontfix, a route that returns before any git call). A single-anchor
    classify() reads the worktree copy, routes wontfix, and records no
    ``git show HEAD:`` at all. With the split anchors the artifact read lands on
    the main root while ``_head_has_feature_complete`` still runs against the
    invoking checkout — a cwd that differs from the artifact parent.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    main_repo, worktree_root = _worktree_fixture(tmp_path)
    (main_repo / "cortex" / "lifecycle" / SLUG / "events.log").write_text(
        json.dumps(
            {
                "ts": "2026-06-30T12:00:00Z",
                "event": "feature_complete",
                "feature": SLUG,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (worktree_root / "cortex" / "lifecycle" / SLUG / "events.log").write_text(
        json.dumps(
            {"ts": "2026-01-02T03:04:05Z", "event": "feature_wontfix", "feature": SLUG}
        )
        + "\n",
        encoding="utf-8",
    )

    # Record every git invocation; the synthetic worktree backs no real repo, so
    # a stubbed "" show-prefix is what lets the `git show HEAD:` call happen.
    calls: list[tuple[list[str], Optional[str]]] = []

    def _recording_git_out(args: list[str], cwd: Optional[str] = None) -> Optional[str]:
        calls.append((list(args), cwd))
        if args[:2] == ["rev-parse", "--show-prefix"]:
            return ""
        return None

    monkeypatch.setattr(complete_route, "_git_out", _recording_git_out)
    monkeypatch.chdir(worktree_root)

    result = classify(SLUG, worktree_root)

    # Artifact anchor: the main root's log was the one read.
    assert result["route"] == "already_complete", (
        f"artifacts resolved from the CWD, not the validated root: {result['route']!r}"
    )
    artifact_root = log_resolver.resolve_verdict_root(SLUG)
    assert artifact_root.resolve() == main_repo.resolve()

    # Tree anchor: `git show HEAD:` ran against the invoking checkout.
    show_cwds = {
        cwd for args, cwd in calls if args and args[0] == "show" and "HEAD:" in args[1]
    }
    assert show_cwds == {str(worktree_root)}, (
        f"_head_has_feature_complete was re-anchored: {show_cwds!r}"
    )

    # The two anchors differ within this single classify() call.
    assert Path(next(iter(show_cwds))).resolve() != artifact_root.resolve()


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


# ---------------------------------------------------------------------------
# Branch-2 narrowing helpers
# ---------------------------------------------------------------------------


def _write_fc_event(root: Path, *, merge_anchor: Optional[str] = "merge") -> None:
    """Write a feature_complete row to events.log (with a preceding benign row).

    If *merge_anchor* is None the field is omitted, testing the legacy/missing-
    anchor behaviour — absent defaults to "review" in classify()'s scan.
    """
    row = {
        "ts": "2026-06-30T12:00:00Z",
        "event": "feature_complete",
        "feature": SLUG,
        "tasks_total": 3,
        "rework_cycles": 0,
    }
    if merge_anchor is not None:
        row["merge_anchor"] = merge_anchor
    _write_events(root, _BENIGN_EVENT, json.dumps(row))


def _write_lifecycle_config(root: Path, *, commit_artifacts: bool) -> None:
    """Write cortex/lifecycle.config.md with the given commit-artifacts setting.

    Uses _CONFIG_RELPATH = "cortex/lifecycle.config.md" (lifecycle_config.py:25).
    The cortex/ directory is guaranteed to exist after _make_root().
    """
    val = "true" if commit_artifacts else "false"
    config_path = root / "cortex" / "lifecycle.config.md"
    config_path.write_text(f"---\ncommit-artifacts: {val}\n---\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Branch-2 narrowing: per-case builder functions (all use _init_repo)
# ---------------------------------------------------------------------------


def _b2_committed_in_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Case 1: feature_complete row committed to HEAD → already_complete (H=True)."""
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor="merge")
    _git("add", "--", f"cortex/lifecycle/{SLUG}/events.log", cwd=root)
    _git("commit", "-m", "c1 feature_complete committed", cwd=root)
    return root


def _b2_uncommitted_anchor_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 2: uncommitted + merge_anchor:"review" → already_complete (anchor!=merge)."""
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor="review")
    return root


def _b2_uncommitted_no_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 3: uncommitted + no merge_anchor field → already_complete.

    Absent field defaults to "review" per the canonical convention, so the row
    is NOT a retry trigger.  Regression guard for the success-path.
    """
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor=None)  # omit the field
    return root


def _b2_uncommitted_ca_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 4: uncommitted + merge_anchor:"merge" + commit-artifacts:false → already_complete.

    Flag-false carve-out: deliberately-uncommitted design, not a retryable strand.
    """
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor="merge")
    _write_lifecycle_config(root, commit_artifacts=False)
    return root


def _b2_committable_on_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 5: uncommitted + merge_anchor:"merge" + committable + on main → on_main/step9.

    All retryable conditions are True: H=False (never committed), merge-anchor,
    commit-artifacts=True (default), committable=True (events.log untracked),
    current_branch="main", pr.json absent.  Falls through to Branch 3 →
    on_main/step9 (NOT already_complete).

    Pre-fix un-narrowed Branch 2 would return already_complete here — this is
    the positive discriminating case for the narrowing fix.
    """
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor="merge")
    # No lifecycle.config.md → commit-artifacts defaults to True.
    # No pr.json → Branch 3 checks current_branch ("main") → on_main.
    return root


def _b2_in_head_absent_from_wt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 6: committed-then-reverted → already_complete (H=True even though W=False).

    Branch 2 fires on (W ∨ H); H-present is sufficient to short-circuit.
    """
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_fc_event(root, merge_anchor="merge")
    _git("add", "--", f"cortex/lifecycle/{SLUG}/events.log", cwd=root)
    _git("commit", "-m", "c1 feature_complete committed", cwd=root)
    # Overwrite working-tree events.log, removing the feature_complete row.
    # W=False after this write; H remains True (HEAD is unchanged).
    _write_events(root, _BENIGN_EVENT)
    return root


def _b2_feature_branch_no_pr_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Case 7: feature branch + no pr.json → already_complete (retry-target guard).

    Without the guard (current_branch in {main,master} or pr_json.is_file()),
    retryable=True would fall through to first_run/step1 via the orphan probe
    (0 matches on a non-main branch with no PR) = lifecycle restart.  The guard
    suppresses the fall-through.  A gh stub returning 0 matches makes the
    discriminating intent explicit: without the guard, the test fails.
    """
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _git("checkout", "-b", "feature-foo", cwd=root)
    _write_fc_event(root, merge_anchor="merge")
    # gh stub returning 0 orphan matches: without the guard the code would call
    # _orphan_probe, get [], and return first_run/step1.
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    return root


# id, builder, expected_route, expected_continue_to, forbidden_route
_BRANCH2_CASES = [
    ("committed_in_head", _b2_committed_in_head, "already_complete", "step12", None),
    ("uncommitted_anchor_review", _b2_uncommitted_anchor_review, "already_complete", "step12", None),
    ("uncommitted_no_anchor", _b2_uncommitted_no_anchor, "already_complete", "step12", None),
    ("uncommitted_ca_false", _b2_uncommitted_ca_false, "already_complete", "step12", None),
    ("committable_on_main", _b2_committable_on_main, "on_main", "step9", None),
    ("in_head_absent_from_wt", _b2_in_head_absent_from_wt, "already_complete", "step12", None),
    ("feature_branch_no_pr_json", _b2_feature_branch_no_pr_json, "already_complete", "step12", "first_run"),
]


@pytest.mark.parametrize(
    "builder,expected_route,expected_continue_to,forbidden_route",
    [row[1:] for row in _BRANCH2_CASES],
    ids=[row[0] for row in _BRANCH2_CASES],
)
def test_branch2_narrowing_carveout_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder: Callable[[Path, pytest.MonkeyPatch], Path],
    expected_route: str,
    expected_continue_to: Optional[str],
    forbidden_route: Optional[str],
) -> None:
    """Parametrized: each carve-out condition in the narrowed Branch-2 retryable check.

    Every case uses a real repo via _init_repo so assertions discriminate on
    committed-vs-uncommitted state, not on the no-repo accident (_make_root
    alone → committable=False → not retryable regardless of anchor).
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = builder(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    before = _events_line_count(root)
    result = classify(SLUG, root)
    after = _events_line_count(root)

    assert result["route"] == expected_route, (
        f"{builder.__name__}: expected {expected_route!r}, got {result['route']!r}"
    )
    assert result["continue_to"] == expected_continue_to, (
        f"{builder.__name__}: expected continue_to={expected_continue_to!r}, "
        f"got {result['continue_to']!r}"
    )
    if forbidden_route is not None:
        assert result["route"] != forbidden_route, (
            f"{builder.__name__}: route must not be {forbidden_route!r} "
            f"(retry-target guard missing?)"
        )

    # Req 1b: classify() must not write to events.log on any route.
    assert after == before, (
        f"{builder.__name__}: classify() mutated events.log ({before} → {after} lines)"
    )


# ---------------------------------------------------------------------------
# Nested-cortex-root H test: --show-prefix enables git-top-relative path
# resolution when root is a subdirectory of the git repository.
# ---------------------------------------------------------------------------


def test_branch2_nested_cortex_root_H_uses_show_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H=True via --show-prefix when root is a subdirectory of the git repo.

    Discriminating: without the --show-prefix fix, _head_has_feature_complete
    would use a root-relative path (``cortex/lifecycle/.../events.log``) for
    ``git show HEAD:``.  With ``root = gitroot/sub``, git resolves that path
    against the git top (``gitroot/``) → exit 128 → H=False.  With H=False and
    a committable backlog delta present, retryable=True and classify() falls
    through to on_main/step9 instead of already_complete.

    The --show-prefix fix prepends ``sub/`` → correct path → H=True →
    already_complete.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

    gitroot = tmp_path / "gitroot"
    root = gitroot / "sub"
    lifecycle_dir = root / "cortex" / "lifecycle" / SLUG
    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    # Git repo is at gitroot; root (sub/) is a proper subdirectory.
    _init_repo(gitroot)
    (gitroot / "README").write_text("x\n")
    _git("add", "README", cwd=gitroot)
    _git("commit", "-m", "c0", cwd=gitroot)

    # Write and commit events.log via gitroot (path relative to the git top).
    _write_fc_event(root, merge_anchor="merge")
    _git("add", "--", f"sub/cortex/lifecycle/{SLUG}/events.log", cwd=gitroot)
    _git("commit", "-m", "c1 feature_complete nested", cwd=gitroot)

    # Leave a committable backlog delta so that, without the --show-prefix fix
    # (H incorrectly False), retryable=True and classify() misroutes to on_main.
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    (backlog_dir / "index.md").write_text("# index\n", encoding="utf-8")

    monkeypatch.chdir(root)
    result = classify(SLUG, root)

    # With fix: --show-prefix → H=True → retryable=False → already_complete.
    # Without fix: root-relative path → exit 128 → H=False → retryable=True → on_main.
    assert result["route"] == "already_complete", (
        f"expected already_complete (H=True via --show-prefix), got {result['route']!r}"
    )
    assert result["continue_to"] == "step12"


# ---------------------------------------------------------------------------
# R3 same-root / no-traceback test: stale .git-file worktree marker degrades
# gracefully; no CORTEX_REPO_ROOT leakage into classify().
# ---------------------------------------------------------------------------


def test_branch2_stale_git_file_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """classify() degrades gracefully on a stale .git-file worktree marker.

    All git helpers (H, committable, current_branch) fail and return the
    safe-direction default (False / "").  W=True (working-tree row present)
    makes Branch 2 trigger; H=False and committable=False make it not retryable
    → already_complete.  A CORTEX_REPO_ROOT naming a divergent project that
    does not hold this slug's lifecycle is rejected by resolve_verdict_root's
    validation, so it never anchors the artifact read either.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

    # Stale .git-file worktree: .git is a FILE pointing to a non-existent dir.
    worktree_root = _setup_worktree(tmp_path)
    _write_fc_event(worktree_root, merge_anchor="merge")

    # Divergent CORTEX_REPO_ROOT holding a different project's lifecycles only.
    divergent = tmp_path / "divergent"
    (divergent / "cortex" / "lifecycle" / "other-feature").mkdir(parents=True)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(divergent))

    monkeypatch.chdir(worktree_root)

    # Should not raise; git helpers degrade gracefully on the stale .git file.
    result = classify(SLUG, worktree_root)

    # W=True (working-tree row), H=False (git fails gracefully),
    # committable=False (git fails gracefully) → not retryable → already_complete.
    assert result["route"] == "already_complete"
    assert result["continue_to"] == "step12"


# ---------------------------------------------------------------------------
# R3 grep guards: porcelain-not-diff-head and no-collect-paths-import.
# ---------------------------------------------------------------------------


def test_classify_uses_porcelain_not_git_diff_head() -> None:
    """complete_route.py must not use 'git diff HEAD' (blind to untracked files).

    The committability probe must use 'git status --porcelain' so that
    first-commit untracked artifacts report committable=True (Req 3).
    """
    source = VERB_SOURCE.read_text(encoding="utf-8")
    assert "git diff HEAD" not in source, (
        "complete_route.py uses 'git diff HEAD'; the committability probe must "
        "use 'git status --porcelain' to detect untracked files (Req 3)."
    )


def test_classify_does_not_import_collect_paths() -> None:
    """complete_route.py must not import stage_artifacts or collect_paths.

    The drift read is inlined in _drift_files_from_review; importing
    stage_artifacts (backlog-glob + YAML-parse) is a weight regression on
    the routing path (Req 3 Technical Constraints).
    """
    source = VERB_SOURCE.read_text(encoding="utf-8")
    assert "collect_paths" not in source, (
        "complete_route.py references 'collect_paths'; the drift read must be "
        "inlined (Req 3 — no stage_artifacts import on the routing path)."
    )
    assert "stage_artifacts" not in source, (
        "complete_route.py imports 'stage_artifacts'; the drift read must be "
        "inlined in _drift_files_from_review (Req 3 Technical Constraints)."
    )


# ---------------------------------------------------------------------------
# Task 4 / R5: commit-failure routing-recovery test
# ---------------------------------------------------------------------------


def test_classify_recovery_commit_failed_then_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5: commit-failed → on_main/step9 retry → committed → already_complete.

    Stage 1 (commit failed): feature_complete row in working tree, not in HEAD.
    A committable backlog delta is also present so retryable=True (all five
    conditions satisfied).  The Stage-1 on_main assertion is the discriminator:
    the pre-fix un-narrowed classify() returns already_complete here (short-
    circuits on W=True), so this assertion fails against the old code.

    Stage 2 (successful retry): commit the finalization set.  H is now True →
    already_complete.  The cycle ends done.

    Convergence-state check: exactly one feature_complete row in HEAD's
    events.log confirms classify() (read-only) did not duplicate during the
    round-trip.

    Scope note: this tests routing (Task 1 fix), not R4's Step-11 prose dedup —
    classify() never runs Step 11, so the prose emit guard is not exercisable
    by any unit test; that is acknowledged here rather than claimed.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    monkeypatch.chdir(root)

    # Stage 1: simulate a failed Step-11a commit.
    # feature_complete row is in the working tree (W=True) but NOT in HEAD (H=False).
    # A committable backlog delta ensures committable=True so the retryable=True
    # path triggers (not the committable=False carve-out).
    _write_fc_event(root, merge_anchor="merge")
    backlog_dir = root / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True, exist_ok=True)
    (backlog_dir / "index.md").write_text("# index\n", encoding="utf-8")

    result = classify(SLUG, root)
    # Discriminator: pre-fix classify() returns already_complete; post-fix
    # (narrowed Branch 2) detects retryable=True and falls through to on_main.
    assert result["route"] == "on_main", (
        f"Stage 1: expected on_main (commit-failed retry), got {result['route']!r}"
    )
    assert result["continue_to"] == "step9"

    # Stage 2: successful retry — commit the finalization set.
    _git(
        "add", "--",
        f"cortex/lifecycle/{SLUG}/events.log",
        "cortex/backlog/index.md",
        cwd=root,
    )
    _git("commit", "-m", "c1 finalization", cwd=root)

    result2 = classify(SLUG, root)
    # H is now True (feature_complete row committed to HEAD) → already_complete.
    assert result2["route"] == "already_complete", (
        f"Stage 2: expected already_complete (committed), got {result2['route']!r}"
    )
    assert result2["continue_to"] == "step12"

    # Convergence-state check: exactly one feature_complete row in HEAD's events.log.
    # classify() is read-only and never appends; the single row is fixture-written.
    # (Does not exercise R4's prose emit guard — scope note above.)
    prefix_proc = _git("rev-parse", "--show-prefix", cwd=root)
    prefix = prefix_proc.stdout.strip()
    path_in_git = f"{prefix}cortex/lifecycle/{SLUG}/events.log"
    show_proc = _git("show", f"HEAD:{path_in_git}", cwd=root)
    committed_content = show_proc.stdout
    fc_count = committed_content.count('"event": "feature_complete"')
    assert fc_count == 1, (
        f"expected exactly 1 feature_complete row in HEAD's events.log, got {fc_count}"
    )


# ---------------------------------------------------------------------------
# Reqs 6/7 — worktree-existence predicate and the on_main worktree gate.
#
# Between EnterWorktree and `gh pr create` no pr.json exists anywhere, so from
# the primary on main the short-circuit routed on_main -> step9 (the finalize
# leg) for a feature that has no PR at all. The gate makes that arm require
# worktree *absence*.
# ---------------------------------------------------------------------------


_PORCELAIN_NO_MATCH = (
    "worktree /repos/main\n"
    "HEAD 0000000000000000000000000000000000000000\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /repos/wt-other\n"
    "HEAD 1111111111111111111111111111111111111111\n"
    "branch refs/heads/interactive/other-slug\n"
    "\n"
)

_PORCELAIN_MATCH = (
    "worktree /repos/main\n"
    "HEAD 0000000000000000000000000000000000000000\n"
    "branch refs/heads/main\n"
    "\n"
    f"worktree /repos/wt-{SLUG}\n"
    "HEAD 2222222222222222222222222222222222222222\n"
    f"branch refs/heads/interactive/{SLUG}\n"
    "\n"
)


def _stub_git_out(monkeypatch: pytest.MonkeyPatch, porcelain: Optional[str]) -> None:
    """Answer only ``worktree list`` / ``--show-toplevel``; None elsewhere."""

    def _fake(args: list[str], cwd: Optional[str] = None) -> Optional[str]:
        if args[:3] == ["worktree", "list", "--porcelain"]:
            return porcelain
        if args[:2] == ["rev-parse", "--show-toplevel"]:
            return "/repos/main\n"
        return None

    monkeypatch.setattr(complete_route, "_git_out", _fake)


def test_worktree_predicate_is_distinct_from_path_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 6: the predicate answers None where path resolution still answers.

    Same ``git worktree list --porcelain`` input, two different jobs: the
    ``on_main`` gate needs "is there a worktree for this slug" (None), while
    the 4d/4f guards need a real path to run ``git status`` / ``merge-base``
    against, which the ``--show-toplevel`` fallback keeps supplying.
    """
    _stub_git_out(monkeypatch, _PORCELAIN_NO_MATCH)

    assert complete_route._find_slug_worktree(SLUG) is None
    resolved = complete_route._resolve_worktree_path(SLUG, Path("/fallback-root"))
    assert resolved == "/repos/main"
    assert resolved, "_resolve_worktree_path must never return empty"


def test_worktree_predicate_returns_the_matched_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching block yields the path, and path resolution agrees with it."""
    _stub_git_out(monkeypatch, _PORCELAIN_MATCH)

    assert complete_route._find_slug_worktree(SLUG) == f"/repos/wt-{SLUG}"
    assert (
        complete_route._resolve_worktree_path(SLUG, Path("/fallback-root"))
        == f"/repos/wt-{SLUG}"
    )


def test_worktree_predicate_fails_open_when_git_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``git worktree list`` failing yields None (== "no worktree"), not a raise.

    Failing open keeps the never-crash contract and keeps ``on_main`` firing
    exactly as it did before the gate; ``_resolve_worktree_path`` still lands
    on a non-empty fallback.
    """
    _stub_git_out(monkeypatch, None)

    assert complete_route._find_slug_worktree(SLUG) is None
    assert complete_route._resolve_worktree_path(SLUG, Path("/fallback-root")) == (
        "/repos/main"
    )


def _build_main_checkout_no_pr_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Real repo on ``main``, events.log benign, no pr.json."""
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_events(root, _BENIGN_EVENT)
    return root


def _add_interactive_worktree(root: Path, wt_path: Path) -> None:
    """Create a real ``interactive/{slug}`` worktree linked to *root*."""
    _git("worktree", "add", "-b", f"interactive/{SLUG}", str(wt_path), cwd=root)


def test_on_main_does_not_fire_while_a_worktree_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 7: on main, no pr.json, worktree present -> not the finalize leg.

    The pre-PR window. With gh reachable the fall-through lands on the
    Branch-3 orphan probe's zero-match arm (``first_run`` -> step1),
    converging on "go create the PR" instead of finalizing unmerged work.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_main_checkout_no_pr_json(tmp_path, monkeypatch)
    _add_interactive_worktree(root, tmp_path / "wt")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    monkeypatch.chdir(root)

    assert complete_route._current_branch() == "main"
    result = classify(SLUG, root)

    assert result["route"] != "on_main", (
        "on_main fired with a worktree present — the finalize leg would "
        "complete a feature that has no PR"
    )
    assert result["route"] == "first_run"
    assert result["continue_to"] == "step1"


def test_on_main_still_fires_with_no_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is worktree-absence only: direct-to-main work is untouched.

    Same fixture as above minus the worktree, and with a stub that WOULD
    report 5 orphan PRs — so ``on_main`` here also proves the orphan probe was
    still bypassed (no network call added to this path).
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_main_checkout_no_pr_json(tmp_path, monkeypatch)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "5")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)

    assert result["route"] == "on_main"
    assert result["continue_to"] == "step9"


def test_retryable_finalization_on_main_with_a_worktree_restarts_at_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 7's gate crossed with Branch 2's retryable fall-through.

    Branch 2 deliberately does not return for a retryable interactive
    finalization (¬H, a ``merge_anchor: "merge"`` working-tree row,
    commit-artifacts true, a committable set, on ``main``), expecting to land on
    ``on_main``/step9 and retry the finalization commit — the shape
    ``_b2_committable_on_main`` pins. Add a live ``interactive/{slug}``
    worktree and the Req-7 gate now sends that same state to the orphan probe,
    which on zero matches yields ``first_run``/step1, restarting the lifecycle —
    the outcome Branch 2's own comment calls strictly worse than
    ``already_complete``. Pre-#487 it was ``on_main``/step9.

    Characterization, not endorsement: the gate is unconditional by Req 7 and
    the crossing is narrow (it needs a *failed* finalization commit with the
    worktree still un-cleaned), but it is a behavior change that reading either
    branch alone does not reveal. Pinned so a future change to either side has
    to face it. Discriminates against dropping the gate (route becomes
    ``on_main``).
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    # Retryable: row in the working tree only, merge-anchored, untracked (so
    # the finalization set is committable), no lifecycle.config.md (commit-
    # artifacts defaults True), no pr.json.
    _write_fc_event(root, merge_anchor="merge")
    _add_interactive_worktree(root, tmp_path / "wt")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    monkeypatch.chdir(root)

    assert complete_route._current_branch() == "main"
    assert complete_route._find_slug_worktree(SLUG) is not None

    result = classify(SLUG, root)

    assert result["route"] == "first_run", (
        "the retryable-finalization crossing changed shape: expected the "
        f"documented first_run restart, got {result['route']!r}"
    )
    assert result["continue_to"] == "step1"


def test_accepted_edge_worktree_present_gh_absent_is_terminal_pr_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accepted edge (i): the pre-PR window with gh unavailable.

    Worktree present, no pr.json, ``shutil.which("gh")`` -> None (git stays
    resolvable, so ``_current_branch`` really is ``main`` and the gate is what
    moves the route). ``_orphan_probe`` sets ``error`` and classify returns
    Branch 4a — terminal ``pr_unknown``, "retry later". This is the cost of
    the guard, not a defect: a retryable refusal beats silently finalizing
    unmerged work, and it fires only when a worktree for the slug exists.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_main_checkout_no_pr_json(tmp_path, monkeypatch)
    _add_interactive_worktree(root, tmp_path / "wt")
    monkeypatch.chdir(root)

    real_which = shutil.which
    monkeypatch.setattr(
        complete_route.shutil,
        "which",
        lambda name, *a, **kw: None if name == "gh" else real_which(name, *a, **kw),
    )

    assert complete_route._current_branch() == "main"
    result = classify(SLUG, root)

    assert result["route"] == "pr_unknown"
    assert result["terminal"] is True
    assert result["continue_to"] is None
    assert result["pr_state"] == "unknown"
    assert "retry later" in result["message"]


def test_accepted_edge_foreign_head_branch_cannot_reach_step8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accepted edge (ii): a head_branch absent from the local tree stops at 4f.

    The destructive arm's authorization and its target resolve in different
    trees — ``pr.json`` supplies ``head_branch`` from the artifact root while
    Step 8 deletes ``f"interactive/{slug}"``, a name derived from the slug and
    never from the verified ``head_branch`` (``complete.md:27``). The local
    ``merge-base --is-ancestor`` probe is the only thing keeping those two
    consistent: an unknown ref exits non-zero, so the route is the safe
    terminal ``merged_not_ancestor`` and ``step8`` is unreachable. Pinned so
    the property is designed rather than accidental.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
    _write_events(root, _BENIGN_EVENT)
    # A head_branch that exists on the remote/PR but not in this local tree.
    _write_pr_json(root, number=13, head_branch="interactive/absent-from-this-tree")
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "c1 fixtures", cwd=root)  # clean tree -> past the 4d guard
    _git("update-ref", "refs/remotes/origin/main", "main", cwd=root)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "merged-anchored")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)

    assert result["pr_state"] == "MERGED"
    assert result["route"] == "merged_not_ancestor"
    assert result["continue_to"] is None, "a foreign head_branch reached step8"
    assert result["terminal"] is True
