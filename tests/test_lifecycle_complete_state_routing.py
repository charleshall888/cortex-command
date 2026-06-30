"""Routing tests for the Complete phase, migrated to target the verb (#331 T4).

Historically this file grepped ``skills/lifecycle/references/complete.md``
prose for the Step-7 routing table's exit-message substrings and command/order
tokens. Step 7's PR-state router has been extracted into the
``cortex-lifecycle-complete-route <slug>`` classifier verb
(``cortex_command/lifecycle/complete_route.py``), and the prose collapses to
"run it, act on ``route``/``continue_to``". So every assertion that previously
read complete.md text now targets the VERB instead (spec #331 Req 3):

* message/branch assertions assert the verb's ``{route, message, pr_state}``
  output, driving the ``gh`` states through the Task-2 stub
  (``tests/fixtures/gh-stub.sh``) and its ``$GH_STUB_*`` env vars;
* command/order/precedence assertions assert the verb's module source (the
  ``gh``/``git`` invocations it now owns) or its observable routing behavior,
  not the prose;
* the three assertion shapes that resist a 1:1 swap are re-expressed
  behaviorally (the ``Worktree retained`` cross-message repetition → three
  per-route message checks; the orphan-probe prose descriptions → route
  assertions; the structural Step-7 heading guard is kept).

Two structural guards still read complete.md by design and are the only
intentional residual ``complete.md`` references:

* ``test_step_7_heading_present`` — the Step-7 heading must survive the
  collapse (Req 3's "intentional residual");
* ``test_step7_invokes_verb_and_drops_terminal_messages`` — the persisted
  narration-removal wiring guard: the Step-7 region must invoke
  ``cortex-lifecycle-complete-route`` AND no longer carry the Branch 4a-4g
  terminal-message strings (so the prose collapse is regression-guarded by a
  durable test, not only Task 5's one-shot grep). This is the routing-side
  counterpart to the positive ``stage-artifacts``-invocation token that
  ``test_complete_md_finalization_commit.py`` keeps on the Phase-2 side.

The verb's full golden route table lives in ``tests/test_complete_route.py``;
this file stands alone with self-contained fixtures so the migrated routing
contract is exercised independently of that golden table.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

import pytest

from cortex_command.lifecycle.complete_route import classify, main

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLETE_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "complete.md"
VERB_SOURCE = REPO_ROOT / "cortex_command" / "lifecycle" / "complete_route.py"
GH_STUB_SOURCE = REPO_ROOT / "tests" / "fixtures" / "gh-stub.sh"

SLUG = "feat"

# A benign, non-routing events.log line so events.log is never empty (and so a
# precedence fixture has a real baseline). Neither feature_wontfix nor
# feature_complete, so it never drives Branch 1/2 on its own.
_BENIGN_EVENT = json.dumps(
    {"ts": "2026-06-01T00:00:00Z", "event": "research_started", "feature": SLUG}
)


def _complete_text() -> str:
    """Return the contents of complete.md (structural guards only)."""
    return COMPLETE_MD.read_text(encoding="utf-8")


def _verb_source() -> str:
    """Return the complete-route verb's module source."""
    return VERB_SOURCE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture plumbing (self-contained; idiom mirrors tests/test_complete_route.py
# and the PATH-injected gh stub from tests/test_runner_pr_gating.py).
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run git with a hermetic identity and hooks/gpg disabled."""
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
    """Create ``<tmp>/proj/cortex/lifecycle/<slug>/`` and return the root."""
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


def _pr_json_path(root: Path) -> Path:
    return root / "cortex" / "lifecycle" / SLUG / "pr.json"


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


def _build_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # pr.json absent, not on main (no git -> empty branch), probe returns [].
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "0")
    return root


def _build_one_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # pr.json absent, exactly one orphan -> reconstruct pr.json, then Branch 4
    # (OPEN via open-anchored) -> pr_open.
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_PR_LIST_COUNT", "1")
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")
    monkeypatch.setenv("GH_STUB_REPO", "owner/repo")
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
    # Feature-branch checkout (no interactive worktree). MERGED + dirty tree
    # (untracked cortex/ artifacts).
    root = _make_root(tmp_path)
    _init_repo(root)
    (root / "README").write_text("x\n")
    _git("add", "README", cwd=root)
    _git("commit", "-m", "c0", cwd=root)
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
    _git("commit", "-m", "c1 fixtures", cwd=root)  # artifacts committed -> clean
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
# Migrated routing table. Each row replaces one of the 12 original
# ROUTING_BRANCHES prose-grep cases with a verb-output assertion. The 4-tuple
# {route, terminal, continue_to, pr_state} is pinned; message handling:
#   msg_mode "empty" -> message must be exactly ""  (non-terminal/continue routes)
#   msg_mode "subs"  -> every listed substring must appear in message
# ---------------------------------------------------------------------------

_ROUTE_CASES = [
    # id, builder, route, terminal, continue_to, pr_state, msg_mode, msg_subs
    (
        "feature_wontfix",  # was ROUTING_BRANCHES "lifecycle was wontfix'd at"
        _build_wontfix,
        "wontfix",
        True,
        None,
        "",
        "subs",
        ["lifecycle was wontfix'd at", "nothing to complete (worktree cleanup skipped)."],
    ),
    (
        "feature_complete_already",  # was "feature_complete" (empty msg now)
        _build_already_complete,
        "already_complete",
        False,
        "step12",
        "",
        "empty",
        [],
    ),
    (
        "pr_json_absent_zero_orphan",  # was "Zero matches" (prose) -> first_run route
        _build_first_run,
        "first_run",
        False,
        "step1",
        "",
        "empty",
        [],
    ),
    (
        "pr_json_absent_one_orphan",  # was "Exactly one match" -> reconstruct then Branch 4
        _build_one_match,
        "pr_open",
        True,
        None,
        "OPEN",
        "subs",
        ["merge first."],
    ),
    (
        "pr_json_absent_multi_orphan",  # was "Multiple matches" -> orphan_ambiguous
        _build_orphan_ambiguous,
        "orphan_ambiguous",
        False,
        None,
        "",
        "empty",
        [],
    ),
    (
        "auth_error",  # was "gh unauthenticated or network error"
        _build_pr_unknown,
        "pr_unknown",
        True,
        None,
        "unknown",
        "subs",
        ["gh unauthenticated or network error", "Worktree retained"],
    ),
    (
        "pr_not_found",  # was "referenced in pr.json was not found on GitHub"
        _build_pr_not_found,
        "pr_not_found",
        True,
        None,
        "",
        "subs",
        ["referenced in pr.json was not found on GitHub", "The PR may have been deleted"],
    ),
    (
        "open",  # was "merge first"
        _build_pr_open,
        "pr_open",
        True,
        None,
        "OPEN",
        "subs",
        ["merge first."],
    ),
    (
        "merged_dirty",  # was "uncommitted changes at"
        _build_merged_dirty,
        "merged_dirty",
        True,
        None,
        "MERGED",
        "subs",
        ["uncommitted changes at", "resolve first."],
    ),
    (
        "merged_clean_ancestor",  # was "Continue to Steps 8" (empty msg now)
        _build_merged_clean_ancestor,
        "merged_clean_ancestor",
        False,
        "step8",
        "MERGED",
        "empty",
        [],
    ),
    (
        "merged_not_ancestor",  # was "refusing cleanup until verified"
        _build_merged_not_ancestor,
        "merged_not_ancestor",
        True,
        None,
        "MERGED",
        "subs",
        ["refusing cleanup until verified"],
    ),
    (
        "closed_unmerged",  # was "closed without merging"
        _build_pr_closed,
        "pr_closed",
        True,
        None,
        "CLOSED",
        "subs",
        ["closed without merging"],
    ),
]


@pytest.mark.parametrize(
    "builder,route,terminal,continue_to,pr_state,msg_mode,msg_subs",
    [row[1:] for row in _ROUTE_CASES],
    ids=[row[0] for row in _ROUTE_CASES],
)
def test_routing_branch_targets_verb_output(
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
    """Each routing branch asserts the verb's {route, message, pr_state} output.

    Migrated from the original prose-grep ``test_routing_branch_exit_message
    _present`` (12 cases): instead of checking that complete.md contains a
    terminal-message substring, we drive the verb to each branch via the
    gh-stub + on-disk fixtures and assert its real output.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = builder(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    result = classify(SLUG, root)

    assert result["route"] == route
    assert result["terminal"] is terminal
    assert result["continue_to"] == continue_to
    assert result["pr_state"] == pr_state

    if msg_mode == "empty":
        assert result["message"] == "", result["message"]
    else:
        for sub in msg_subs:
            assert sub in result["message"], (route, sub, result["message"])


# ---------------------------------------------------------------------------
# Resistant shape 1: the original cross-message repetition invariant
# (text.count("Worktree retained") >= 3) is re-expressed as three separate
# per-route message-contains checks — one verb invocation emits ONE message.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [_build_pr_unknown, _build_pr_not_found, _build_pr_closed],
    ids=["pr_unknown", "pr_not_found", "pr_closed"],
)
def test_worktree_retained_in_each_retaining_terminal_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder: Callable[[Path, pytest.MonkeyPatch], Path],
) -> None:
    """Each worktree-retaining terminal route's message says 'Worktree retained'.

    Migrated from ``test_worktree_retained_language_in_terminal_branches``
    (which counted >= 3 occurrences across complete.md prose): the three
    routes that retain the worktree (4a pr_unknown, 4b pr_not_found, 4g
    pr_closed) each emit the phrase in their own ``message``.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = builder(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert "Worktree retained" in result["message"], result


# ---------------------------------------------------------------------------
# Verbatim terminal-message intents, asserted against verb output.
# ---------------------------------------------------------------------------


def test_closed_unmerged_message_offers_three_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 4g (pr_closed) message offers three recovery paths.

    Migrated from ``test_closed_unmerged_exit_offers_three_paths`` — reopen+
    merge, manual ``git worktree remove``, or wontfix.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_pr_closed(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    msg = classify(SLUG, root)["message"]
    assert "reopen and merge" in msg, msg
    assert "git worktree remove" in msg, msg
    assert "wontfix" in msg, msg


def test_non_ancestor_message_offers_manual_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 4f (merged_not_ancestor) message offers a manual override.

    Migrated from ``test_non_ancestor_exit_offers_manual_override``.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_merged_not_ancestor(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert result["route"] == "merged_not_ancestor"
    assert "git worktree remove" in result["message"], result["message"]


# ---------------------------------------------------------------------------
# Strict-order / precedence — behavioral (first match wins), not prose strings.
# ---------------------------------------------------------------------------


def test_wontfix_precedes_complete_and_open_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 1 (wontfix) wins even when feature_complete AND an OPEN PR coexist.

    Migrated from ``test_feature_wontfix_takes_precedence`` (which grepped
    'Takes precedence'): a fixture carrying a feature_wontfix row, a
    feature_complete row, and a present pr.json (which a stubbed gh would
    report OPEN) must still route ``wontfix`` — proving Branch 1 precedes both
    Branch 2 and Branch 4.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
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
        json.dumps(
            {"ts": "2026-06-02T02:00:00Z", "event": "feature_wontfix", "feature": SLUG}
        ),
    )
    _write_pr_json(root, number=7, url="https://github.com/owner/repo/pull/7")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert result["route"] == "wontfix"
    assert result["terminal"] is True


def test_feature_complete_precedes_pr_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 2 (feature_complete) short-circuits ahead of the Branch-4 PR query.

    Migrated from ``test_evaluation_order_documented`` (which grepped 'strict
    order'/'Evaluation order'): with a feature_complete row AND a present
    pr.json that a stubbed gh reports OPEN, the verb must route
    ``already_complete`` (continue_to step12), not ``pr_open`` — proving the
    strict-order short-circuit fires before Branch 4.
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
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
    _write_pr_json(root, number=7, url="https://github.com/owner/repo/pull/7")
    _install_gh_stub(monkeypatch, tmp_path)
    monkeypatch.setenv("GH_STUB_SCENARIO", "open-anchored")
    monkeypatch.chdir(root)

    result = classify(SLUG, root)
    assert result["route"] == "already_complete"
    assert result["continue_to"] == "step12"


# ---------------------------------------------------------------------------
# Resistant shape 2: the orphan-probe prose descriptions (Zero/Exactly one/
# Multiple matches, "first-run path", "retroactively") become behavioral route
# assertions. The zero/multi cases ride the table above; the single-match
# reconstruction side-effect gets its own dedicated assertion here.
# ---------------------------------------------------------------------------


def test_one_match_reconstructs_pr_json_then_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 3 single-match retroactively reconstructs pr.json, then routes.

    Migrated from ``test_pr_json_absent_one_match_reconstructs_pr_json``
    (grepped 'retroactively'): a single orphan match writes pr.json from the
    probe response, then falls through to Branch 4 (OPEN -> pr_open).
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_one_match(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    pr_path = _pr_json_path(root)
    assert not pr_path.exists()

    result = classify(SLUG, root)

    # Reconstruction happened with the probe-derived fields.
    assert pr_path.exists(), "single-match did not reconstruct pr.json"
    pr_obj = json.loads(pr_path.read_text(encoding="utf-8"))
    assert pr_obj["number"] == 1
    assert pr_obj["head_branch"] == f"interactive/{SLUG}"
    assert pr_obj["repo"] == "owner/repo"

    # Then fell through to Branch 4 (stubbed OPEN -> pr_open).
    assert result["route"] == "pr_open"
    assert result["pr_state"] == "OPEN"
    assert "merge first." in result["message"]


def test_multi_match_orphan_ambiguous_no_write_with_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch 3 multi-match returns orphan_ambiguous with candidates, no write.

    Migrated from the 'Multiple matches' prose entry: the verb does NOT
    auto-select; it surfaces candidates and leaves pr.json unwritten (the user
    pick stays in prose — Req 6 kept affordance).
    """
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _build_orphan_ambiguous(tmp_path, monkeypatch)
    monkeypatch.chdir(root)

    pr_path = _pr_json_path(root)
    result = classify(SLUG, root)

    assert result["route"] == "orphan_ambiguous"
    assert result["terminal"] is False
    assert result["continue_to"] is None
    assert not pr_path.exists(), "multi-match wrongly wrote pr.json"
    candidates = result.get("candidates")
    assert candidates and len(candidates) == 2, result
    assert {c["number"] for c in candidates} == {1, 2}


# ---------------------------------------------------------------------------
# Command/order assertions — migrated from prose-command greps to the verb's
# module source (the gh/git invocations the verb now owns).
# ---------------------------------------------------------------------------


def test_orphan_probe_command_in_verb_source() -> None:
    """The verb owns the Branch-3 'gh pr list --head' orphan probe.

    Migrated from ``test_pr_json_absent_probe_command_present`` (grepped 'gh
    pr list' + '--head' in complete.md).
    """
    src = _verb_source()
    assert '"list"' in src and '"--head"' in src and '"--state"' in src, (
        "complete_route.py must own the 'gh pr list --head --state all' orphan probe"
    )


def test_pr_view_command_in_verb_source() -> None:
    """The verb owns the Branch-4 'gh pr view <number> --json state,mergedAt'.

    Migrated from ``test_gh_pr_view_command_present``.
    """
    src = _verb_source()
    assert '"view"' in src and '"state,mergedAt"' in src, (
        "complete_route.py must own the 'gh pr view --json state,mergedAt' query"
    )


def test_merge_base_is_ancestor_in_verb_source() -> None:
    """The verb owns the 4e/4f 'git merge-base --is-ancestor' check.

    Migrated from ``test_merge_base_is_ancestor_command_present``.
    """
    src = _verb_source()
    assert '"merge-base"' in src and '"--is-ancestor"' in src, (
        "complete_route.py must own the 'git merge-base --is-ancestor' ancestor check"
    )


# ---------------------------------------------------------------------------
# gh-absent degradation through the CLI main() — exit 0, pr_state unknown.
# ---------------------------------------------------------------------------


def test_gh_absent_degrades_to_unknown_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Missing gh -> Branch 4a pr_unknown via main(), exit 0 (never a traceback)."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    root = _make_root(tmp_path)
    _write_events(root, _BENIGN_EVENT)
    _write_pr_json(root, number=3)
    empty = tmp_path / "emptybin"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))  # no gh (nor git) on PATH
    monkeypatch.chdir(root)

    rc = main([SLUG])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["route"] == "pr_unknown"
    assert payload["pr_state"] == "unknown"


# ---------------------------------------------------------------------------
# Coverage meta-assertion — the migrated table covers all 12 routing branches.
# ---------------------------------------------------------------------------


def test_twelve_routing_branches_covered() -> None:
    """The migrated route table covers exactly 12 branches (spec #331 Req 2/3)."""
    assert len(_ROUTE_CASES) == 12, (
        f"Expected 12 migrated routing branches, got {len(_ROUTE_CASES)}"
    )
    # Each row drives a distinct verb route (the 4e/4f MERGED split + the two
    # pr_open paths — 3b reconstruct vs 4c direct — are the only intentional
    # route repeats), so the 12 builders span the full Step-7 branch matrix.
    assert len({row[0] for row in _ROUTE_CASES}) == 12


# ---------------------------------------------------------------------------
# Retained structural guards on complete.md — the ONLY intentional residual
# complete.md references (spec #331 Req 3).
# ---------------------------------------------------------------------------


def test_step_7_heading_present() -> None:
    """complete.md must retain the Step 7 heading after the prose collapse.

    Resistant shape 3: a structural heading guard with no verb equivalent —
    kept as the 'intentional residual' Req 3 allows.
    """
    text = _complete_text()
    assert re.search(r"^#{1,4}\s+Step\s+7\b", text, re.MULTILINE), (
        "complete.md missing '### Step 7' (or similar) heading"
    )


# The Branch-1 / 4a-4g terminal-message strings the verb now owns; the Step-7
# region must no longer carry any of them after the prose collapse.
_VERB_OWNED_TERMINAL_STRINGS = [
    "lifecycle was wontfix'd at",          # Branch 1
    "gh unauthenticated or network error",  # 4a
    "The PR may have been deleted",         # 4b
    "was not found on GitHub",              # 4b
    "merge first",                          # 4c
    "uncommitted changes at",               # 4d
    "refusing cleanup until verified",      # 4f
    "closed without merging",               # 4g
    "Worktree retained",                    # 4a / 4b / 4g
]


def _step7_region(text: str) -> str:
    """Return the Step-7 region: '### Step 7' up to (not incl.) '### Step 8'.

    Mirrors the Task-5 verification ``awk '/^### Step 7/,/^### Step 8/'`` slice.
    """
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if re.match(r"^#{1,4}\s+Step\s+7\b", ln)),
        None,
    )
    assert start is not None, "complete.md missing a Step 7 heading"
    end = next(
        (
            i
            for i, ln in enumerate(lines)
            if i > start and re.match(r"^#{1,4}\s+Step\s+8\b", ln)
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_step7_invokes_verb_and_drops_terminal_messages() -> None:
    """Persisted narration-removal wiring guard for the Step-7 prose collapse.

    The Step-7 region must invoke ``cortex-lifecycle-complete-route`` AND must
    no longer carry any Branch 1 / 4a-4g terminal-message string (those moved
    into the verb). This makes the collapse a durable regression guard — not
    only Task 5's one-shot grep — and is the routing-side counterpart to the
    positive stage-artifacts-invocation token kept by
    test_complete_md_finalization_commit.py on the Phase-2 side.
    """
    region = _step7_region(_complete_text())
    assert "cortex-lifecycle-complete-route" in region, (
        "Step 7 must invoke the cortex-lifecycle-complete-route verb"
    )
    leaked = [s for s in _VERB_OWNED_TERMINAL_STRINGS if s in region]
    assert not leaked, (
        "Step 7 still carries verb-owned terminal-message string(s) that the "
        f"prose collapse should have removed: {leaked}"
    )
