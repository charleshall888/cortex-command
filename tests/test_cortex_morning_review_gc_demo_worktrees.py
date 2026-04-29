"""Fixture-replay tests for ``bin/cortex-morning-review-gc-demo-worktrees``.

Covers the six C12 behavior cases from spec R11 of
``lifecycle/extract-morning-review-deterministic-sequences-c11-c15-bundle/spec.md``.

Each test builds a real parent git repo + real worktrees in a pytest tmpdir
(since the script invokes real ``git worktree``), invokes the script via
``subprocess.run``, and asserts on worktree presence/absence + stderr line
ordering. Stderr is filtered to lines starting with ``[gc-demo-worktrees]``
before assertions because git itself emits untagged stderr (warnings,
"Removing worktrees/...") that interleaves with the script's tagged log
lines and is not stable across git versions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "bin"
    / "cortex-morning-review-gc-demo-worktrees"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command with deterministic identity + signing disabled."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.editor",
        "GIT_CONFIG_VALUE_2": "true",
    }
    env.pop("GIT_DIR", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _tagged(stderr: str) -> List[str]:
    """Return only the lines emitted by the script itself.

    ``git worktree remove`` and ``git worktree prune`` emit untagged stderr
    that interleaves with the script's tagged log lines and is not stable
    across git versions. Filter to the tagged stream before asserting on
    substring presence or line order.
    """
    return [
        line
        for line in stderr.splitlines()
        if line.startswith("[gc-demo-worktrees]")
    ]


@pytest.fixture
def gc_fixture(tmp_path: Path):
    """Build a parent repo + a per-test ``$TMPDIR``-rooted worktree area.

    Yields a callable ``add_worktree(name)`` that materializes a worktree
    under ``tmp_tmpdir`` and registers it for teardown, plus the parent
    repo path and the synthetic ``$TMPDIR`` path. Teardown force-removes
    every registered worktree and prunes the admin entries so subsequent
    test runs don't trip ``already registered`` errors when a test crashes
    mid-fixture or leaves a worktree in a state ``git worktree remove``
    refused to clean up.
    """
    parent_repo = tmp_path / "parent_repo"
    _git("init", "-b", "main", str(parent_repo), cwd=tmp_path)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "--allow-empty", "-m", "initial",
        cwd=parent_repo,
    )

    tmp_tmpdir = tmp_path / "tmpdir"
    tmp_tmpdir.mkdir()

    created: List[Path] = []

    def add_worktree(name: str) -> Path:
        wt_path = tmp_tmpdir / name
        _git("worktree", "add", str(wt_path), cwd=parent_repo)
        created.append(wt_path)
        return wt_path

    try:
        yield {
            "parent_repo": parent_repo,
            "tmp_tmpdir": tmp_tmpdir,
            "add_worktree": add_worktree,
        }
    finally:
        for wt in created:
            subprocess.run(
                ["git", "-C", str(parent_repo),
                 "worktree", "remove", "--force", str(wt)],
                capture_output=True,
                text=True,
                check=False,
            )
        subprocess.run(
            ["git", "-C", str(parent_repo), "worktree", "prune"],
            capture_output=True,
            text=True,
            check=False,
        )


def _run_script(
    parent_repo: Path,
    tmp_tmpdir: Path,
    active_session_id: str,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT_PATH), active_session_id],
        cwd=str(parent_repo),
        env={"TMPDIR": str(tmp_tmpdir), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_clean_matching_worktree_is_removed(gc_fixture) -> None:
    """A matching worktree with a clean working tree is removed; stderr
    contains a tagged ``removing`` line; exit 0 (spec R11.a)."""
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    wt = add_worktree("demo-overnight-2026-04-28-0900-20260428T130000Z")
    assert wt.exists()

    result = _run_script(parent_repo, tmp_tmpdir, "other-session")

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert not wt.exists(), (
        f"clean matching worktree should have been removed: {wt}\n"
        f"stderr: {result.stderr}"
    )
    tagged = _tagged(result.stderr)
    assert any(
        line.startswith("[gc-demo-worktrees] removing") for line in tagged
    ), f"expected a tagged 'removing' line in stderr; got tagged={tagged!r}"


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_path_under_tmpdir_not_matching_prefix_is_left_alone(gc_fixture) -> None:
    """A worktree under ``$TMPDIR`` whose basename does NOT match
    ``demo-overnight-`` is left alone — no remove, no skip log
    (spec R11.b)."""
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    wt = add_worktree("feature-something-20260428T130000Z")
    assert wt.exists()

    result = _run_script(parent_repo, tmp_tmpdir, "other-session")

    assert result.returncode == 0
    assert wt.exists(), (
        f"non-matching worktree should NOT have been removed: {wt}\n"
        f"stderr: {result.stderr}"
    )
    tagged = _tagged(result.stderr)
    for line in tagged:
        assert str(wt) not in line, (
            f"non-matching worktree path should not appear in any tagged "
            f"log line; found: {line!r}"
        )


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_uncommitted_untracked_file_skips_with_stderr_log(gc_fixture) -> None:
    """A matching worktree containing an untracked file is SKIPPED
    with a tagged ``skipping ...: uncommitted state`` stderr log; the
    worktree directory is unchanged (spec R11.c, R9)."""
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    wt = add_worktree("demo-overnight-2026-04-28-0900-20260428T130000Z")
    (wt / "scratch.txt").write_text("untracked user work\n")

    result = _run_script(parent_repo, tmp_tmpdir, "other-session")

    assert result.returncode == 0
    assert wt.exists(), (
        f"worktree with untracked file should have been preserved: {wt}\n"
        f"stderr: {result.stderr}"
    )
    assert (wt / "scratch.txt").exists(), "untracked file should be preserved"

    tagged = _tagged(result.stderr)
    expected = f"[gc-demo-worktrees] skipping {wt}: uncommitted state"
    # Match by resolved-path prefix because the script's stderr uses the
    # path string emitted by ``git worktree list --porcelain``, which on
    # macOS resolves /tmp -> /private/tmp; the test's ``wt`` may use
    # either form depending on tmp_path resolution.
    assert any(
        line.endswith(": uncommitted state")
        and line.startswith("[gc-demo-worktrees] skipping ")
        for line in tagged
    ), (
        f"expected a tagged uncommitted-state skip log; got tagged={tagged!r}\n"
        f"expected something like: {expected!r}"
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_tracked_dirty_worktree_is_skipped_or_remove_failure_logged(
    gc_fixture,
) -> None:
    """A matching worktree with a modified tracked file is SKIPPED via
    the uncommitted-state precondition OR ``git worktree remove`` refuses
    and the failure is logged; either branch is acceptable per spec
    edge-case bullet (line 93). The worktree dir must still exist.
    """
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    wt = add_worktree("demo-overnight-2026-04-28-0900-20260428T130000Z")
    # Seed a tracked file, commit it, then modify it so `git status` reports
    # a tracked dirty change.
    tracked = wt / "tracked.txt"
    tracked.write_text("v1\n")
    _git("add", "tracked.txt", cwd=wt)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "add tracked",
        cwd=wt,
    )
    tracked.write_text("v2 — dirty\n")

    result = _run_script(parent_repo, tmp_tmpdir, "other-session")

    assert result.returncode == 0
    assert wt.exists(), (
        f"tracked-dirty worktree should be preserved: {wt}\n"
        f"stderr: {result.stderr}"
    )
    tagged = _tagged(result.stderr)
    skipped = any(
        line.startswith("[gc-demo-worktrees] skipping ")
        and line.endswith(": uncommitted state")
        for line in tagged
    )
    remove_failed = any(
        line.startswith("[gc-demo-worktrees] removal failed for ")
        for line in tagged
    )
    assert skipped or remove_failed, (
        "expected either a tagged uncommitted-state skip log OR a tagged "
        f"'removal failed' log; got tagged={tagged!r}"
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_active_session_worktree_is_excluded_before_state_check(
    gc_fixture,
) -> None:
    """The active-session exclusion fires BEFORE the uncommitted-state
    check — so for a worktree named ``demo-<active_id>-...``, no
    ``removing`` or ``skipping`` line appears for that path even if
    state is clean (spec R11.e)."""
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    active_id = "overnight-2026-04-28-0900"
    wt = add_worktree(f"demo-{active_id}-20260428T130000Z")
    assert wt.exists()

    result = _run_script(parent_repo, tmp_tmpdir, active_id)

    assert result.returncode == 0
    assert wt.exists(), (
        f"active-session worktree should NOT be removed: {wt}\n"
        f"stderr: {result.stderr}"
    )

    tagged = _tagged(result.stderr)
    for line in tagged:
        if line.startswith(("[gc-demo-worktrees] removing ",
                            "[gc-demo-worktrees] skipping ")):
            assert str(wt) not in line, (
                f"active-session exclusion should fire before any per-path "
                f"log; found tagged line referencing the active worktree: "
                f"{line!r}"
            )


@pytest.mark.skipif(
    sys.platform == "win32", reason="bash-only script; not supported on Windows"
)
def test_prune_runs_once_after_all_remove_calls_ordering_invariant(
    gc_fixture,
) -> None:
    """The script runs ``git worktree remove`` per candidate first and
    ``git worktree prune`` ONCE at the end. Filter stderr to the tagged
    stream before computing line indices — git itself emits untagged
    stderr that interleaves and would make a raw-line comparison flaky
    (spec R11.f, R10)."""
    add_worktree = gc_fixture["add_worktree"]
    parent_repo = gc_fixture["parent_repo"]
    tmp_tmpdir = gc_fixture["tmp_tmpdir"]

    wts = [
        add_worktree(f"demo-overnight-2026-04-28-0900-2026042{i}T130000Z")
        for i in range(3)
    ]
    for wt in wts:
        assert wt.exists()

    result = _run_script(parent_repo, tmp_tmpdir, "other-session")

    assert result.returncode == 0
    for wt in wts:
        assert not wt.exists(), (
            f"clean matching worktree should have been removed: {wt}\n"
            f"stderr: {result.stderr}"
        )

    tagged = _tagged(result.stderr)
    prune_indices = [
        i for i, line in enumerate(tagged)
        if line == "[gc-demo-worktrees] pruning"
    ]
    remove_indices = [
        i for i, line in enumerate(tagged)
        if line.startswith("[gc-demo-worktrees] removing ")
    ]

    assert len(prune_indices) == 1, (
        f"expected exactly one 'pruning' tagged line; got tagged={tagged!r}"
    )
    assert len(remove_indices) == 3, (
        f"expected three 'removing' tagged lines (one per worktree); got "
        f"tagged={tagged!r}"
    )
    prune_idx = prune_indices[0]
    for r_idx in remove_indices:
        assert r_idx < prune_idx, (
            f"each 'removing' must precede the single 'pruning' line; "
            f"removing at {r_idx} not before pruning at {prune_idx}; "
            f"tagged={tagged!r}"
        )
