"""R26 sync-rebase coverage for post-merge sync semantics.

Closes the R16 [M]-tagged pipeline.md gap: "Post-session sync via
``bin/cortex-git-sync-rebase`` + ``sync-allowlist.conf`` — script-level; no
pytest today".

The test creates a fixture git repo with a bare ``origin`` remote, then
invokes the real ``cortex-git-sync-rebase`` to exercise the rebase pipeline.
Verification asserts the script exits 0 and the local branch is rebased
correctly on top of origin/main.

The "clean rebase" path uses a ``git pull --rebase`` that should succeed
without conflicts; this is the happy-path sync that pipeline.md R26
requires to keep the ``--merge`` PR strategy load-bearing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import cortex_command.git.sync_rebase as sync_rebase_mod
from cortex_command.git.sync_rebase import (
    _load_allowlist,
    _matches_allowlist,
    _stale_rebase_in_progress,
    sync_rebase,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC_REBASE_SH = REPO_ROOT / "bin" / "cortex-git-sync-rebase"
SYNC_ALLOWLIST = REPO_ROOT / "cortex_command" / "overnight" / "sync-allowlist.conf"

# Representative repo-relative paths, in the same shape git reports conflict
# paths: rooted at the repo, carrying the `cortex/` umbrella prefix. Every
# pattern in sync-allowlist.conf must match at least one of these.
REPRESENTATIVE_PATHS = (
    "cortex/backlog/346-x.md",
    "cortex/backlog/index.md",
    "cortex/backlog/archive/300-done.md",
    "cortex/lifecycle/pipeline-events.log",
    "cortex/lifecycle/foo/research.md",
    "cortex/lifecycle/foo/spec.md",
    "cortex/lifecycle/foo/plan.md",
    "cortex/lifecycle/foo/agent-activity.jsonl",
    "cortex/lifecycle/sessions/s1/",
    "cortex/lifecycle/sessions/s1/batch-results.md",
)


def _allowlist_patterns() -> list[str]:
    """Load the live conf, failing loudly if it has gone empty."""
    patterns = _load_allowlist(SYNC_ALLOWLIST)
    assert patterns, f"no patterns loaded from {SYNC_ALLOWLIST}"
    return patterns


@pytest.mark.parametrize("pattern", _allowlist_patterns())
def test_every_allowlist_pattern_matches_a_real_path(pattern: str) -> None:
    """Each conf pattern must match at least one representative real path.

    Asserted per-pattern (not in aggregate) so one live pattern cannot mask
    dead siblings — the exact failure that let the `cortex/` umbrella
    relocation (c8110de5) strand all nine patterns for two months, silently
    disabling the §6a auto-resolution the morning-review sync advertises.
    """
    matched = [p for p in REPRESENTATIVE_PATHS if _matches_allowlist(p, [pattern])]
    assert matched, (
        f"allowlist pattern {pattern!r} matches none of the representative "
        f"paths — it is dead and can never auto-resolve a conflict. Check the "
        f"`cortex/` umbrella prefix, and note that patterns ending in '/' are "
        f"matched as literal prefixes (a '*' inside one never matches)."
    )


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command with repeatable author/committer identity."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        # Defeat any global gpg-sign / editor config that would block
        # interactive rebase or signed commits inside the fixture.
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "core.editor",
        "GIT_CONFIG_VALUE_2": "true",
    }
    # Strip any GIT_DIR override from the outer environment so tests are
    # isolated from the surrounding repo.
    env.pop("GIT_DIR", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash required for shell test"
)
def test_git_sync_rebase_noop_when_up_to_date(tmp_path: Path) -> None:
    """git-sync-rebase.sh exits 0 with a ``nothing to rebase`` message when
    the local branch is already at origin/main — the noop success path.

    This path validates the script's fetch-and-check wiring (read the
    allowlist location, identify origin/main, short-circuit when behind-
    count is zero).  It runs on all bash versions including macOS 3.2.
    """
    # ---- Bare remote ----
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    # ---- Local clone with an initial commit on main ----
    local = tmp_path / "local"
    _git("clone", str(remote), str(local), cwd=tmp_path)

    (local / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=local)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Initial commit",
        cwd=local,
    )
    _git("push", "origin", "main", cwd=local)

    # Copy the real sync-allowlist and commit it so the working tree is
    # clean for any rebase the script attempts.
    allowlist_dir = local / "cortex_command" / "overnight"
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SYNC_ALLOWLIST, allowlist_dir / "sync-allowlist.conf")
    _git("add", "cortex_command/overnight/sync-allowlist.conf", cwd=local)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Add sync allowlist",
        cwd=local,
    )
    _git("push", "origin", "main", cwd=local)

    # ---- Invoke the sync-rebase script from the local repo root ----
    result = subprocess.run(
        ["bash", str(SYNC_REBASE_SH)],
        cwd=str(local),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sync-rebase should succeed on up-to-date branch:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (
        "up to date" in result.stderr.lower()
        or "nothing to rebase" in result.stderr.lower()
    ), (
        f"expected noop message; got stderr: {result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash required for shell test"
)
def test_git_sync_rebase_clean_rebase_succeeds(tmp_path: Path) -> None:
    """git-sync-rebase.sh rebases cleanly when local is behind origin/main
    by a non-conflicting commit, and the push to origin lands.

    R26 ``--merge`` semantics check: after rebase, the local commit sits
    on top of the upstream history.  This exercises the primary success
    path through ``git pull --rebase`` (no conflicts, no allowlist work).
    """
    # ---- Bare remote ----
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    # ---- Seed remote via a scratch clone ----
    seed = tmp_path / "seed"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    (seed / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=seed)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Initial commit",
        cwd=seed,
    )
    _git("push", "origin", "main", cwd=seed)

    # ---- Local clone (starts at initial commit) ----
    local = tmp_path / "local"
    _git("clone", str(remote), str(local), cwd=tmp_path)

    # Copy the sync-allowlist inside the fixture and commit it so the
    # working tree is clean before the rebase runs.
    allowlist_dir = local / "cortex_command" / "overnight"
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SYNC_ALLOWLIST, allowlist_dir / "sync-allowlist.conf")
    _git("add", "cortex_command/overnight/sync-allowlist.conf", cwd=local)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Add sync allowlist",
        cwd=local,
    )
    _git("push", "origin", "main", cwd=local)

    # ---- Upstream clone advances origin/main with a non-conflicting commit.
    upstream = tmp_path / "upstream"
    _git("clone", str(remote), str(upstream), cwd=tmp_path)
    (upstream / "upstream.txt").write_text("from upstream\n")
    _git("add", "upstream.txt", cwd=upstream)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Upstream commit",
        cwd=upstream,
    )
    _git("push", "origin", "main", cwd=upstream)

    # ---- Local commits a different, non-conflicting file ----
    (local / "local.txt").write_text("from local\n")
    _git("add", "local.txt", cwd=local)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "-m", "Local commit",
        cwd=local,
    )

    # ---- Invoke the sync-rebase script ----
    # Use the same config-suppression env as _git() so rebases are not
    # derailed by a global commit.gpgsign or core.editor setting.
    script_env = {
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
    script_env.pop("GIT_DIR", None)
    result = subprocess.run(
        ["bash", str(SYNC_REBASE_SH)],
        cwd=str(local),
        capture_output=True,
        text=True,
        env=script_env,
    )
    # The script should exit 0 on clean rebase + push.  On older bashes
    # (macOS 3.2) the ``mapfile`` builtin used in the conflict-resolution
    # branch is missing; the clean-rebase path avoids that branch by
    # taking the happy-path ``git pull --rebase`` short-circuit.  If we
    # nevertheless land in the conflict branch, surface the diagnostic
    # rather than silently masking the failure.
    if result.returncode != 0:
        if "mapfile: command not found" in result.stderr:
            pytest.skip(
                "system bash lacks mapfile (bash 4+); clean-rebase path "
                "fell into conflict branch due to environment — script "
                "semantics are covered by test_git_sync_rebase_noop_when_up_to_date"
            )
        pytest.fail(
            f"git-sync-rebase.sh failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # ---- Assert local history includes both commits post-rebase ----
    log = _git("log", "--oneline", "main", cwd=local).stdout
    assert "Local commit" in log, f"local commit missing: {log}"
    assert "Upstream commit" in log, f"upstream commit missing: {log}"

    # ---- Assert the push to origin/main landed (the rebased local tip) ----
    remote_log = _git("log", "--oneline", "main", cwd=remote).stdout
    assert "Local commit" in remote_log, (
        f"push did not land on origin: {remote_log}"
    )


def _make_conflict_fixture(tmp_path: Path, conflict_path: str) -> tuple[Path, Path]:
    """Build an origin + local clone staged for a guaranteed rebase conflict.

    ``conflict_path`` is written with three different bodies: a base revision
    on origin/main, a remote revision pushed by a second clone, and a local
    revision committed but not pushed.  Rebasing local onto origin/main is
    then forced through the conflict-resolution loop for exactly that path,
    which lets a caller choose whether the conflict lands on an allowlisted
    path or a non-allowlisted one.

    :returns: ``(local, remote)`` paths.
    """
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    # ---- Seed origin/main with the base revision + the live allowlist ----
    seed = tmp_path / "seed"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    seed_file = seed / conflict_path
    seed_file.parent.mkdir(parents=True, exist_ok=True)
    seed_file.write_text("base\n")
    allowlist_dir = seed / "cortex_command" / "overnight"
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SYNC_ALLOWLIST, allowlist_dir / "sync-allowlist.conf")
    _git("add", "-A", cwd=seed)
    _git("-c", "commit.gpgsign=false", "commit", "-m", "Initial commit", cwd=seed)
    _git("push", "origin", "main", cwd=seed)

    # ---- Local clone, pinned to a repo-local identity ----
    # sync_rebase() shells out to git without injecting author env, so the
    # rebase it drives must find an identity in the fixture's own config.
    local = tmp_path / "local"
    _git("clone", str(remote), str(local), cwd=tmp_path)
    _git("config", "user.name", "Test", cwd=local)
    _git("config", "user.email", "test@example.com", cwd=local)
    _git("config", "commit.gpgsign", "false", cwd=local)

    # ---- Upstream advances origin/main, touching the same lines ----
    upstream = tmp_path / "upstream"
    _git("clone", str(remote), str(upstream), cwd=tmp_path)
    (upstream / conflict_path).write_text("remote revision\n")
    _git("add", "-A", cwd=upstream)
    _git("-c", "commit.gpgsign=false", "commit", "-m", "Upstream commit", cwd=upstream)
    _git("push", "origin", "main", cwd=upstream)

    # ---- Local commits a competing revision of the same file ----
    (local / conflict_path).write_text("local revision\n")
    _git("add", "-A", cwd=local)
    _git("-c", "commit.gpgsign=false", "commit", "-m", "Local commit", cwd=local)

    return local, remote


def test_sync_rebase_auto_resolves_allowlisted_conflict(tmp_path: Path) -> None:
    """A conflict on an allowlisted path is auto-resolved and the rebase lands.

    ``cortex/backlog/index.md`` is one of the paths the conf claims to cover.
    This is the §6a auto-resolution the morning-review sync advertises, and
    the arm that stays green only while the conf's patterns actually match
    git's repo-relative conflict paths.
    """
    local, remote = _make_conflict_fixture(tmp_path, "cortex/backlog/index.md")

    rc = sync_rebase(repo_root=local)

    assert rc == 0, "an allowlisted conflict should auto-resolve, rebase, and push"

    # Which side survives is deliberately unasserted: git inverts ours/theirs
    # during a rebase, so `checkout --theirs` keeps the LOCAL revision, not the
    # remote one the module docstring and the conf header both promise. Pinning
    # either side here would certify a semantic nobody has ruled on yet.
    assert not _stale_rebase_in_progress(local), "rebase state left behind"
    assert _git("status", "--porcelain", cwd=local).stdout == "", "tree not clean"

    log = _git("log", "--oneline", "main", cwd=local).stdout
    assert "Local commit" in log and "Upstream commit" in log, (
        f"expected both commits in rebased history: {log}"
    )
    remote_log = _git("log", "--oneline", "main", cwd=remote).stdout
    assert "Local commit" in remote_log, f"push did not land on origin: {remote_log}"


def _make_up_to_date_fixture(tmp_path: Path) -> Path:
    """Build a local clone sitting exactly at origin/main.

    The behind-count here is a *legitimate* zero, which is what makes this
    fixture the right control for the failing-rev-list test: the two tests
    differ only by the stub, so a stub that still exits 0 is provably
    collapsing the error path into the real "up to date" answer.

    :returns: the ``local`` clone path.
    """
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    local = tmp_path / "local"
    _git("clone", str(remote), str(local), cwd=tmp_path)
    _git("config", "user.name", "Test", cwd=local)
    _git("config", "user.email", "test@example.com", cwd=local)
    _git("config", "commit.gpgsign", "false", cwd=local)

    (local / "README.md").write_text("hello\n")
    allowlist_dir = local / "cortex_command" / "overnight"
    allowlist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(SYNC_ALLOWLIST, allowlist_dir / "sync-allowlist.conf")
    _git("add", "-A", cwd=local)
    _git("-c", "commit.gpgsign=false", "commit", "-m", "Initial commit", cwd=local)
    _git("push", "origin", "main", cwd=local)

    return local


def test_sync_rebase_reports_failure_when_behind_count_cannot_be_determined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A failing ``git rev-list`` must not render as "already up to date".

    A missing origin/main, a shallow clone, an auth failure or a dropped
    network all make the behind-count unanswerable. Returning 0 for those --
    as the pre-fix code did for both the non-zero rc and the ValueError --
    reports success while pushing nothing: a silent false success that tells
    the morning review the sync landed when no sync occurred.

    The exit code must therefore fall outside the three codes a caller can
    already interpret (0 success, 1 conflict, 2 push failure).
    """
    local = _make_up_to_date_fixture(tmp_path)

    real_git = sync_rebase_mod._git

    def fake_git(args: list[str], **kwargs):
        if args[:1] == ["rev-list"]:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=128,
                stdout="",
                stderr="fatal: ambiguous argument 'HEAD..origin/main': "
                "unknown revision or path not in the working tree.\n",
            )
        return real_git(args, **kwargs)

    monkeypatch.setattr(sync_rebase_mod, "_git", fake_git)

    rc = sync_rebase(repo_root=local)

    assert rc not in (0, 1, 2), (
        "a failed behind-count must not reuse success (0), conflict (1) or "
        f"push-failure (2) — a caller cannot tell them apart; got {rc}"
    )
    assert rc == 3, f"expected the documented behind-count exit code 3, got {rc}"

    stderr = capsys.readouterr().err
    assert "behind-count" in stderr, (
        f"the diagnostic must name the behind-count step so an operator can "
        f"tell this from a conflict or a push failure; got: {stderr!r}"
    )
    assert "up to date" not in stderr.lower(), (
        f"a failed check must never claim the branch is up to date: {stderr!r}"
    )


def test_sync_rebase_still_exits_zero_when_genuinely_up_to_date(
    tmp_path: Path,
) -> None:
    """A real behind-count of zero remains an exit-0 noop.

    The control for the test above: same fixture, no stub. Distinguishing the
    error path must not disturb the legitimate "nothing to rebase" answer.
    """
    local = _make_up_to_date_fixture(tmp_path)

    assert sync_rebase(repo_root=local) == 0, (
        "an up-to-date branch is a legitimate zero and must still exit 0"
    )


def test_sync_rebase_aborts_on_non_allowlisted_conflict(tmp_path: Path) -> None:
    """A conflict outside the allowlist aborts the rebase and exits 1.

    ``README.md`` matches no conf pattern, so the loop must refuse to guess,
    abort, and leave the repo back on the un-rebased local tip with no
    half-finished rebase for the next session to trip over.
    """
    local, remote = _make_conflict_fixture(tmp_path, "README.md")

    head_before = _git("rev-parse", "HEAD", cwd=local).stdout.strip()

    rc = sync_rebase(repo_root=local)

    assert rc == 1, "a non-allowlisted conflict must report the conflict exit code"

    # The abort must be complete: no rebase-merge/rebase-apply directory, a
    # clean tree, and HEAD back where it started.
    assert not _stale_rebase_in_progress(local), (
        "aborted rebase left a rebase-merge/rebase-apply directory behind"
    )
    status = _git("status", "--porcelain", cwd=local).stdout
    assert status == "", f"aborted rebase left a dirty tree: {status!r}"
    assert _git("rev-parse", "HEAD", cwd=local).stdout.strip() == head_before, (
        "abort should restore the pre-rebase local tip"
    )

    # Nothing was pushed — origin still lacks the local commit.
    remote_log = _git("log", "--oneline", "main", cwd=remote).stdout
    assert "Local commit" not in remote_log, (
        f"a failed sync must not push: {remote_log}"
    )
