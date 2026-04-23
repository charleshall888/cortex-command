"""End-to-end regression tests for PR-gating behavior in runner.sh.

Covers spec Req 8 of `lifecycle/gate-overnight-pr-creation-on-merged-over-zero/`:
eleven subprocess-capture tests that invoke
`bash cortex_command/overnight/runner.sh --dry-run --state-path <tmp>` and assert
substring patterns on stdout.

Test isolation (mandatory per spec Req 8):
- The source state fixtures in `tests/fixtures/` are NEVER written to by the
  runner. Each test copies the fixture into `tmp_path` and passes the copy
  as `--state-path`. `LOCK_FILE`, `session_start` event appends, and
  `interrupt.py` state mutations all land in `tmp_path`.
- A per-test bare-repo fake remote + `GIT_CONFIG_GLOBAL` `insteadOf` redirect
  ensures `git push -u origin <branch>` never reaches the real GitHub remote.
- A per-test PATH-injected `gh` stub (copied from `tests/fixtures/gh-stub.sh`)
  intercepts `gh pr view` so the resume-recovery path sees canned responses.
- Each test sets `TMPDIR=<tmp_path>` so the runner's `$TMPDIR/overnight-pr-body.txt`
  and other scratch files land in tmp_path, not the host temp dir.

Every test asserts three things:
  (i)  returncode == 0
  (ii) "Traceback" not in stderr (catches Python crashes that would otherwise
       look like "PR gate emitted wrong output")
  (iii) the requirement-specific substring pattern on stdout

Rationale: grep-only assertions cannot distinguish "PR gate misbehavior" from
"runner crashed at state-load"; the return-code and traceback checks fail
loudly on non-PR-gate faults.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REAL_REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REAL_REPO_ROOT / "tests" / "fixtures"
GH_STUB_SOURCE = FIXTURE_DIR / "gh-stub.sh"


def _copy_state_fixture(source_name: str, tmp_path: Path) -> Path:
    """Copy a source fixture into tmp_path; return the destination path."""
    src = FIXTURE_DIR / source_name
    dst = tmp_path / "overnight-state.json"
    shutil.copy(src, dst)
    return dst


def _patch_state(state_path: Path, patch: dict[str, Any]) -> None:
    """Merge `patch` into the JSON state file at state_path."""
    data = json.loads(state_path.read_text())
    data.update(patch)
    state_path.write_text(json.dumps(data))


def _make_fake_remote(tmp_path: Path) -> Path:
    """Create a bare-repo fake remote so `git push` never reaches GitHub."""
    bare = tmp_path / "fake-remote.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", str(bare)],
        check=True,
        capture_output=True,
    )
    return bare


def _make_git_config(tmp_path: Path, fake_remote: Path) -> Path:
    """Write a git config that redirects the real origin URL to the fake remote."""
    cfg = tmp_path / "test-git-config"
    cfg.write_text(
        f'[url "{fake_remote}"]\n'
        f'\tinsteadOf = https://github.com/charleshall888/cortex-command.git\n'
    )
    return cfg


def _install_gh_stub(tmp_path: Path) -> Path:
    """Copy the gh stub into a bin/ dir inside tmp_path and mark it executable."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    dst = bin_dir / "gh"
    shutil.copy(GH_STUB_SOURCE, dst)
    dst.chmod(0o755)
    return bin_dir


def _create_integration_branch(branch: str, ensure: bool = True) -> str | None:
    """Create (or remove) a lightweight integration branch via git update-ref.

    Uses `git commit-tree` on the current tree to produce a fresh commit whose
    parent is HEAD, then points `refs/heads/<branch>` at it. This is
    non-invasive (no working-tree change) and satisfies
    `git rev-list --count main..<branch>` > 0 provided HEAD is at main OR
    the fresh commit is a descendant of main — which it is, because
    commit-tree uses `-p HEAD` and the fresh commit is not yet reachable
    from main.

    Returns the SHA of the created branch tip so the caller can clean up,
    or None when ensure=False (branch deleted).
    """
    if not ensure:
        subprocess.run(
            ["git", "update-ref", "-d", f"refs/heads/{branch}"],
            capture_output=True,
        )
        return None
    tree = subprocess.run(
        ["git", "write-tree"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "commit-tree", tree, "-p", "HEAD", "-m", "Dummy commit for PR gating test"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", f"refs/heads/{branch}", commit],
        check=True,
        capture_output=True,
    )
    return commit


def _build_env(
    tmp_path: Path,
    bin_dir: Path,
    git_config: Path,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assemble the subprocess environment for a runner invocation."""
    env = dict(os.environ)
    # PATH-injected gh stub takes precedence over real gh
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    # Redirect git origin URL to the per-test fake remote
    env["GIT_CONFIG_GLOBAL"] = str(git_config)
    # Route the runner's $TMPDIR/* scratch files into tmp_path
    env["TMPDIR"] = str(tmp_path)
    # Don't inherit prior GH_STUB_* unless tests set them
    env.pop("GH_STUB_SCENARIO", None)
    env.pop("GH_STUB_READY_MODE", None)
    # notify.sh reads stdin via `cat` when stdin isn't a TTY (see ~/.claude/notify.sh).
    # subprocess.run's default stdin is a pipe that never closes, causing a hang.
    # SKIP_NOTIFICATIONS=1 short-circuits notify.sh before the cat call.
    env["SKIP_NOTIFICATIONS"] = "1"
    if extra:
        env.update(extra)
    return env


def _run_runner(state_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke runner.sh --dry-run against a state file copy."""
    return subprocess.run(
        ["bash", "cortex_command/overnight/runner.sh", "--dry-run", "--state-path", str(state_path)],
        cwd=str(REAL_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _read_pr_body(tmp_path: Path) -> str:
    """Read the runner's PR body file written to $TMPDIR."""
    body = tmp_path / "overnight-pr-body.txt"
    if not body.exists():
        return ""
    return body.read_text()


@pytest.fixture
def env_setup(tmp_path: Path):
    """Per-test setup: fake remote + git config + gh stub.

    Yields a dict of (tmp_path, bin_dir, git_config, fake_remote) for tests
    that need to customize the env (e.g. add GH_STUB_SCENARIO).
    """
    fake_remote = _make_fake_remote(tmp_path)
    git_config = _make_git_config(tmp_path, fake_remote)
    bin_dir = _install_gh_stub(tmp_path)
    return {
        "tmp_path": tmp_path,
        "bin_dir": bin_dir,
        "git_config": git_config,
        "fake_remote": fake_remote,
    }


def _assert_clean_run(result: subprocess.CompletedProcess[str]) -> None:
    """Fail loudly on non-PR-gate faults (crash, traceback)."""
    assert result.returncode == 0, (
        f"runner exited {result.returncode}\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, (
        f"Python traceback in stderr (non-PR-gate fault):\n{result.stderr}"
    )


# --- Req 1 --------------------------------------------------------------


def test_zero_merge_produces_draft(env_setup) -> None:
    """Zero-merge fixture -> PR created with --draft and [ZERO PROGRESS] title."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(tp, env_setup["bin_dir"], env_setup["git_config"])
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    pr_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("DRY-RUN gh pr create")]
    assert pr_lines, f"expected 'DRY-RUN gh pr create' line, got stdout:\n{result.stdout}"
    pr_line = pr_lines[0]
    assert "--draft" in pr_line, f"expected --draft in PR line, got:\n{pr_line}"
    assert "[ZERO PROGRESS] Overnight session:" in pr_line, (
        f"expected '[ZERO PROGRESS] Overnight session:' in title, got:\n{pr_line}"
    )
    body = _read_pr_body(tp)
    assert "**ZERO PROGRESS**" in body, f"expected '**ZERO PROGRESS**' in body, got:\n{body}"


# --- Req 1/2 ------------------------------------------------------------


def test_nonzero_merge_produces_nondraft(env_setup) -> None:
    """Nonzero-merge fixture -> PR created without --draft, plain title, no ZERO PROGRESS body."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-nonzero-merge.json", tp)
    branch = "overnight/test-nonzero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(tp, env_setup["bin_dir"], env_setup["git_config"])
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    pr_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("DRY-RUN gh pr create")]
    assert pr_lines, f"expected 'DRY-RUN gh pr create' line, got stdout:\n{result.stdout}"
    pr_line = pr_lines[0]
    assert "--draft" not in pr_line, f"did NOT expect --draft, got:\n{pr_line}"
    assert "--title Overnight session:" in pr_line, (
        f"expected title '--title Overnight session:' (no bracket prefix), got:\n{pr_line}"
    )
    assert "[ZERO PROGRESS]" not in pr_line, f"did NOT expect '[ZERO PROGRESS]', got:\n{pr_line}"
    body = _read_pr_body(tp)
    assert "**ZERO PROGRESS**" not in body, (
        f"did NOT expect '**ZERO PROGRESS**' in body, got:\n{body}"
    )


# --- Req 3 (nonzero + degraded: title plain, body has warning) ----------


def test_nonzero_merge_degraded(env_setup) -> None:
    """Nonzero merge + degraded flag -> plain title (no bracket), body has warning."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-nonzero-merge-degraded.json", tp)
    branch = "overnight/test-nonzero-merge-degraded"
    _create_integration_branch(branch, ensure=True)
    # Seed the integration warning file at the runner's expected location
    # ($TMPDIR/overnight-integration-warning.txt). The runner rebuilds the
    # path from $TMPDIR at startup; it does not inherit INTEGRATION_WARNING_FILE
    # from env. TMPDIR is set to tp in _build_env so this path resolves.
    warning_text = "INTEGRATION GATE FAILED — test scenario warning.\n"
    warning_file = tp / "overnight-integration-warning.txt"
    warning_file.write_text(warning_text)
    try:
        # The fixture's `integration_degraded: true` is preserved across
        # save_state (see cortex_command/overnight/state.py dataclass). No env-var
        # override needed.
        env = _build_env(tp, env_setup["bin_dir"], env_setup["git_config"])
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    pr_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("DRY-RUN gh pr create")]
    assert pr_lines, f"expected 'DRY-RUN gh pr create' line, got stdout:\n{result.stdout}"
    pr_line = pr_lines[0]
    assert "--draft" not in pr_line, f"did NOT expect --draft, got:\n{pr_line}"
    assert "--title Overnight session:" in pr_line, (
        f"expected plain 'Overnight session:' title, got:\n{pr_line}"
    )
    assert "[ZERO PROGRESS]" not in pr_line, f"did NOT expect bracket prefix, got:\n{pr_line}"
    body = _read_pr_body(tp)
    assert body.startswith("INTEGRATION GATE FAILED"), (
        f"expected body to begin with warning content, got:\n{body!r}"
    )


# --- Req 4 --------------------------------------------------------------


def test_zero_commits_skips_pr(env_setup) -> None:
    """Zero-commit fixture (no integration branch) -> pre-check skips PR, emits notify."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge-zero-commits.json", tp)
    # Intentionally do NOT create the integration branch: missing ref -> count 0 -> skip.
    env = _build_env(tp, env_setup["bin_dir"], env_setup["git_config"])
    result = _run_runner(state, env)

    _assert_clean_run(result)
    assert "DRY-RUN gh pr create" not in result.stdout, (
        f"expected NO 'gh pr create' under zero-commit skip, got:\n{result.stdout}"
    )
    notify_lines = [
        ln for ln in result.stdout.splitlines()
        if "DRY-RUN notify.sh" in ln and "Zero-progress session with no branch commits" in ln
    ]
    assert notify_lines, (
        f"expected 'DRY-RUN notify.sh ... Zero-progress session with no branch commits' line, "
        f"got stdout:\n{result.stdout}"
    )


# --- Req 3 (zero + degraded: title is [ZERO PROGRESS], no combined marker) ---


def test_degraded_plus_zero_title(env_setup) -> None:
    """Zero merge + degraded flag -> title is [ZERO PROGRESS] only; body has warning first."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    # Patch the state to add `integration_degraded: true` — the field is now
    # preserved across save_state (see cortex_command/overnight/state.py).
    _patch_state(state, {"integration_degraded": True})
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    warning_text = "INTEGRATION GATE FAILED — test zero+degraded warning.\n"
    warning_file = tp / "overnight-integration-warning.txt"
    warning_file.write_text(warning_text)
    try:
        env = _build_env(tp, env_setup["bin_dir"], env_setup["git_config"])
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    pr_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("DRY-RUN gh pr create")]
    assert pr_lines, f"expected 'DRY-RUN gh pr create' line, got stdout:\n{result.stdout}"
    pr_line = pr_lines[0]
    assert "[ZERO PROGRESS] Overnight session:" in pr_line, (
        f"expected '[ZERO PROGRESS] Overnight session:' title, got:\n{pr_line}"
    )
    # Must NOT be a combined/merged prefix
    assert "[ZERO PROGRESS + GATE FAILED]" not in pr_line
    assert "[GATE FAILED]" not in pr_line
    assert "--draft" in pr_line, f"expected --draft, got:\n{pr_line}"
    body = _read_pr_body(tp)
    assert body.startswith("INTEGRATION GATE FAILED"), (
        f"expected body to begin with warning content, got:\n{body!r}"
    )
    assert "**ZERO PROGRESS**" in body, f"expected '**ZERO PROGRESS**' in body, got:\n{body}"


# --- Req 5: resume flow happy-path state flip, both directions ----------


def test_resume_flips_draft_state(env_setup) -> None:
    """Happy-path: resume flow flips PR's isDraft to intended, both directions.

    Forward subtest: OPEN + isDraft=false + MC_MERGED_COUNT=0 (intended=true) ->
        DRY-RUN gh pr ready --undo <url>  (ready -> draft)
        DRY-RUN state-write integration_pr_flipped_once: true

    Reverse subtest: OPEN + isDraft=true + MC_MERGED_COUNT>0 (intended=false) ->
        DRY-RUN gh pr ready <url>  (draft -> ready)
        DRY-RUN state-write integration_pr_flipped_once: true
    """
    tp = env_setup["tmp_path"]

    # --- Forward: zero-merge, PR currently ready (not draft), should flip to draft
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={"GH_STUB_SCENARIO": "open-ready-mismatch", "GH_STUB_READY_MODE": "ok"},
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    # dry_run_echo prints "DRY-RUN <label> <args...>"; label="gh pr ready --undo"
    # and args start with "gh pr ready --undo <url>", so the URL appears once
    # after the doubled prefix. Assert the trailing portion including the URL.
    assert "gh pr ready --undo https://example.test/pr/1" in result.stdout, (
        f"expected 'gh pr ready --undo https://example.test/pr/1' in stdout, "
        f"got:\n{result.stdout}"
    )
    # Double-check we hit the dry-run echo (not a real invocation that somehow
    # got past the stub): the DRY-RUN prefix must appear on the same line.
    flip_lines = [ln for ln in result.stdout.splitlines() if "DRY-RUN gh pr ready --undo" in ln]
    assert flip_lines, f"expected DRY-RUN marker on gh pr ready --undo line, got:\n{result.stdout}"
    assert "DRY-RUN state-write integration_pr_flipped_once: true" in result.stdout, (
        f"expected marker write after successful flip, got:\n{result.stdout}"
    )

    # --- Reverse: non-zero merge, PR currently draft, should flip to ready
    # Use a new per-test tmp layout nested under tp so test-hygiene stays clean.
    tp2 = tp / "reverse"
    tp2.mkdir()
    fake_remote2 = _make_fake_remote(tp2)
    git_config2 = _make_git_config(tp2, fake_remote2)
    bin_dir2 = _install_gh_stub(tp2)

    state2 = _copy_state_fixture("state-nonzero-merge.json", tp2)
    branch2 = "overnight/test-nonzero-merge"
    _create_integration_branch(branch2, ensure=True)
    try:
        env2 = _build_env(
            tp2,
            bin_dir2,
            git_config2,
            extra={"GH_STUB_SCENARIO": "open-draft-mismatch", "GH_STUB_READY_MODE": "ok"},
        )
        result2 = _run_runner(state2, env2)
    finally:
        _create_integration_branch(branch2, ensure=False)

    _assert_clean_run(result2)
    # Reverse direction: the `--undo` variant must NOT appear.
    assert "--undo" not in result2.stdout, (
        f"did NOT expect '--undo' in reverse case, got:\n{result2.stdout}"
    )
    flip_lines_rev = [
        ln for ln in result2.stdout.splitlines()
        if ln.startswith("DRY-RUN gh pr ready ") and "--undo" not in ln
    ]
    assert flip_lines_rev, (
        f"expected DRY-RUN gh pr ready <url> (no --undo) line, got:\n{result2.stdout}"
    )
    assert "gh pr ready https://example.test/pr/1" in result2.stdout, (
        f"expected 'gh pr ready https://example.test/pr/1' in stdout, got:\n{result2.stdout}"
    )
    assert "DRY-RUN state-write integration_pr_flipped_once: true" in result2.stdout, (
        f"expected marker write after successful flip, got:\n{result2.stdout}"
    )


# --- Req 5: marker=true short-circuits flip -----------------------------


def test_marker_true_skips_flip(env_setup) -> None:
    """integration_pr_flipped_once=true -> no flip even when isDraft is mismatched."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    _patch_state(state, {"integration_pr_flipped_once": True})
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={"GH_STUB_SCENARIO": "open-ready-mismatch", "GH_STUB_READY_MODE": "ok"},
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    assert "DRY-RUN gh pr ready" not in result.stdout, (
        f"did NOT expect gh pr ready invocation (marker=true), got:\n{result.stdout}"
    )
    assert "PR previously handled by runner — deferring to human state" in result.stdout, (
        f"expected 'PR previously handled by runner — deferring to human state', "
        f"got:\n{result.stdout}"
    )


# --- Req 5: MERGED PR short-circuits flip -------------------------------


def test_merged_pr_skips_flip(env_setup) -> None:
    """PR state=MERGED -> no flip, log 'runner yielding to human action', marker unchanged."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={"GH_STUB_SCENARIO": "merged", "GH_STUB_READY_MODE": "ok"},
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    assert "DRY-RUN gh pr ready" not in result.stdout, (
        f"did NOT expect gh pr ready invocation (PR is MERGED), got:\n{result.stdout}"
    )
    assert "PR already MERGED — runner yielding to human action" in result.stdout, (
        f"expected 'PR already MERGED — runner yielding to human action', got:\n{result.stdout}"
    )
    # Marker must remain unchanged (still false) — no marker-write echo
    assert "DRY-RUN state-write integration_pr_flipped_once: true" not in result.stdout, (
        f"did NOT expect marker write (no flip attempted on MERGED PR), got:\n{result.stdout}"
    )


# --- Req 5: CLOSED PR short-circuits flip -------------------------------


def test_closed_pr_skips_flip(env_setup) -> None:
    """PR state=CLOSED -> no flip, log 'runner yielding to human action', marker unchanged."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={"GH_STUB_SCENARIO": "closed", "GH_STUB_READY_MODE": "ok"},
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    assert "DRY-RUN gh pr ready" not in result.stdout, (
        f"did NOT expect gh pr ready invocation (PR is CLOSED), got:\n{result.stdout}"
    )
    assert "PR already CLOSED — runner yielding to human action" in result.stdout, (
        f"expected 'PR already CLOSED — runner yielding to human action', got:\n{result.stdout}"
    )
    assert "DRY-RUN state-write integration_pr_flipped_once: true" not in result.stdout, (
        f"did NOT expect marker write (no flip attempted on CLOSED PR), got:\n{result.stdout}"
    )


# --- Req 5: transient gh pr ready failure does NOT set marker -----------


def test_pr_ready_transient_does_not_set_marker(env_setup) -> None:
    """gh pr ready returns HTTP 429 -> pr_ready_failed reason=transient, marker stays false."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        # dry_run_echo short-circuits the gh pr ready invocation in dry-run,
        # so the gh stub's exit code cannot drive the failure branch. Use the
        # runner's dry-run-only simulation hook (DRY_RUN_GH_READY_SIMULATE)
        # to force non-zero exit with a canned 429 stderr payload.
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={
                "GH_STUB_SCENARIO": "open-ready-mismatch",
                "DRY_RUN_GH_READY_SIMULATE": "transient",
            },
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    assert "DRY-RUN event pr_ready_failed reason=transient" in result.stdout, (
        f"expected 'DRY-RUN event pr_ready_failed reason=transient', got:\n{result.stdout}"
    )
    # Transient -> marker must NOT be set (next resume retries naturally)
    assert "DRY-RUN state-write integration_pr_flipped_once: true" not in result.stdout, (
        f"did NOT expect marker write on transient failure, got:\n{result.stdout}"
    )


# --- Req 5: persistent gh pr ready failure sets marker ------------------


def test_pr_ready_persistent_sets_marker(env_setup) -> None:
    """gh pr ready returns HTTP 401 -> pr_ready_failed reason=persistent, marker set."""
    tp = env_setup["tmp_path"]
    state = _copy_state_fixture("state-zero-merge.json", tp)
    branch = "overnight/test-zero-merge"
    _create_integration_branch(branch, ensure=True)
    try:
        # See comment in test_pr_ready_transient_does_not_set_marker for why
        # DRY_RUN_GH_READY_SIMULATE is used instead of the gh stub's exit code.
        env = _build_env(
            tp,
            env_setup["bin_dir"],
            env_setup["git_config"],
            extra={
                "GH_STUB_SCENARIO": "open-ready-mismatch",
                "DRY_RUN_GH_READY_SIMULATE": "persistent",
            },
        )
        result = _run_runner(state, env)
    finally:
        _create_integration_branch(branch, ensure=False)

    _assert_clean_run(result)
    assert "DRY-RUN event pr_ready_failed reason=persistent" in result.stdout, (
        f"expected 'DRY-RUN event pr_ready_failed reason=persistent', got:\n{result.stdout}"
    )
    # Persistent -> marker IS set (retry is pointless)
    assert "DRY-RUN state-write integration_pr_flipped_once: true" in result.stdout, (
        f"expected marker write on persistent failure, got:\n{result.stdout}"
    )
