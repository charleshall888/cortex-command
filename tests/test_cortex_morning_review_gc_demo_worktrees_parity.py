"""Parity test: cortex_command.overnight.gc_demo_worktrees vs bash original.

Golden-replay fixture test for the Python port of
``bin/cortex-morning-review-gc-demo-worktrees``. Each fixture in
``tests/fixtures/cortex-morning-review-gc-demo-worktrees/`` describes a
scenario (session-id argv, expected exit code, expected tagged stderr pattern).

Because ``gc_demo_worktrees`` operates on real git worktrees rather than
reading from stdin, the parity test synthesizes git state in ``tmp_path``
per fixture and runs the Python module via ``python3 -m`` against that
synthetic state. This avoids flakiness from ambient ``$TMPDIR`` state.

Comparison strategy per stream:

* **stdout**: byte-identical (always empty).
* **stderr**: tagged-line pattern comparison. The parity test filters stderr
  to ``[gc-demo-worktrees]`` prefixed lines, substitutes the synthetic
  worktree path with the ``<WT_PATH>`` placeholder, then compares against
  the fixture's ``.stderr`` content (which also uses ``<WT_PATH>``).
* **exit code**: exact integer match against ``.exitcode``.

This is one of the four high-risk parity tests for genuinely-bash scripts
(per spec requirement 7 and task context).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest

from tests.test_parity_contract import assert_byte_identical

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "cortex-morning-review-gc-demo-worktrees"
)

_DETERMINISM_ENV: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
}

# Placeholder token used in .stderr fixtures for dynamic worktree paths.
_WT_PATH_TOKEN = "<WT_PATH>"

# Tagged log prefix emitted by both the bash original and the Python port.
_TAG_PREFIX = "[gc-demo-worktrees]"


# ---------------------------------------------------------------------------
# Fixture file helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    return sorted(p.stem for p in FIXTURE_DIR.glob("*.argv"))


def _read_argv(case: str) -> list[str]:
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr_pattern(case: str) -> str:
    """Read .stderr fixture as str; contains <WT_PATH> placeholders."""
    return (FIXTURE_DIR / f"{case}.stderr").read_text(encoding="utf-8")


def _read_expected_exitcode(case: str) -> int:
    return int((FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip())


# ---------------------------------------------------------------------------
# Git helpers for synthetic state construction
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a git command with deterministic identity and signing disabled."""
    base_env = dict(os.environ)
    base_env.update({
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
    })
    base_env.pop("GIT_DIR", None)
    if env:
        base_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env=base_env,
    )


def _make_parent_repo(tmp_path: Path) -> Path:
    """Initialize a bare parent git repo with an empty initial commit."""
    parent = tmp_path / "parent_repo"
    _git("init", "-b", "main", str(parent), cwd=tmp_path)
    _git(
        "-c", "commit.gpgsign=false",
        "commit", "--allow-empty", "-m", "initial",
        cwd=parent,
    )
    return parent


def _add_worktree(parent_repo: Path, synthetic_tmpdir: Path, name: str) -> Path:
    """Add a git worktree under synthetic_tmpdir and return its path."""
    wt_path = synthetic_tmpdir / name
    _git("worktree", "add", str(wt_path), cwd=parent_repo)
    return wt_path


def _cleanup_worktrees(parent_repo: Path, worktrees: List[Path]) -> None:
    """Force-remove worktrees and prune (teardown helper)."""
    for wt in worktrees:
        subprocess.run(
            ["git", "-C", str(parent_repo), "worktree", "remove", "--force", str(wt)],
            capture_output=True, check=False,
        )
    subprocess.run(
        ["git", "-C", str(parent_repo), "worktree", "prune"],
        capture_output=True, check=False,
    )


# ---------------------------------------------------------------------------
# State builders per fixture case
# ---------------------------------------------------------------------------

# Maps case name → callable(tmp_path) → (parent_repo, synthetic_tmpdir, created_worktrees, wt_path_for_substitution)
# The callable builds the git state and returns the runtime context.


def _build_clean_worktree_removed(tmp_path: Path):
    """One clean demo-overnight- worktree that should be removed."""
    synthetic_tmpdir = tmp_path / "tmpdir"
    synthetic_tmpdir.mkdir()
    parent_repo = _make_parent_repo(tmp_path)
    wt_name = "demo-overnight-2026-04-28-0900-20260428T130000Z"
    wt = _add_worktree(parent_repo, synthetic_tmpdir, wt_name)
    return parent_repo, synthetic_tmpdir, [wt], wt


def _build_dirty_worktree_skipped(tmp_path: Path):
    """One demo-overnight- worktree with an untracked file; should be skipped."""
    synthetic_tmpdir = tmp_path / "tmpdir"
    synthetic_tmpdir.mkdir()
    parent_repo = _make_parent_repo(tmp_path)
    wt_name = "demo-overnight-2026-04-28-0900-20260428T130000Z"
    wt = _add_worktree(parent_repo, synthetic_tmpdir, wt_name)
    # Add untracked file to make it dirty.
    (wt / "scratch.txt").write_text("untracked\n")
    return parent_repo, synthetic_tmpdir, [wt], wt


def _build_active_session_excluded(tmp_path: Path):
    """Worktree named demo-<active_id>-... should be silently excluded."""
    synthetic_tmpdir = tmp_path / "tmpdir"
    synthetic_tmpdir.mkdir()
    parent_repo = _make_parent_repo(tmp_path)
    active_id = "overnight-2026-04-28-0900"
    wt_name = f"demo-{active_id}-20260428T130000Z"
    wt = _add_worktree(parent_repo, synthetic_tmpdir, wt_name)
    return parent_repo, synthetic_tmpdir, [wt], wt


def _build_no_tmpdir(tmp_path: Path):
    """No TMPDIR set; silent early exit."""
    # No git state needed; just a directory to serve as cwd.
    parent_repo = _make_parent_repo(tmp_path)
    return parent_repo, None, [], None


_STATE_BUILDERS = {
    "clean_worktree_removed": _build_clean_worktree_removed,
    "dirty_worktree_skipped": _build_dirty_worktree_skipped,
    "active_session_excluded": _build_active_session_excluded,
    "no_tmpdir": _build_no_tmpdir,
}


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------


def _invoke_module(
    argv: List[str],
    stdin_bytes: bytes,
    cwd: Path,
    tmpdir: Optional[Path],
) -> subprocess.CompletedProcess:
    """Invoke the Python module via ``python3 -m``."""
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV)
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    else:
        env.pop("TMPDIR", None)

    return subprocess.run(
        [sys.executable, "-m", "cortex_command.overnight.gc_demo_worktrees"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )


# ---------------------------------------------------------------------------
# Tagged-line helpers
# ---------------------------------------------------------------------------


def _tagged_lines(stderr_bytes: bytes) -> List[str]:
    """Return only the tagged log lines from stderr."""
    text = stderr_bytes.decode("utf-8", errors="replace")
    return [
        line for line in text.splitlines()
        if line.startswith(_TAG_PREFIX)
    ]


def _substitute_wt_path(lines: List[str], wt_path: Optional[Path]) -> List[str]:
    """Replace the synthetic worktree path with <WT_PATH> in tagged lines.

    Also handles macOS /tmp -> /private/tmp resolution differences by
    substituting both the raw and resolved forms.
    """
    if wt_path is None:
        return lines
    wt_str = str(wt_path)
    try:
        wt_resolved = str(wt_path.resolve())
    except OSError:
        wt_resolved = wt_str

    result = []
    for line in lines:
        substituted = line
        if wt_resolved and wt_resolved != wt_str:
            substituted = substituted.replace(wt_resolved, _WT_PATH_TOKEN)
        substituted = substituted.replace(wt_str, _WT_PATH_TOKEN)
        result.append(substituted)
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="git worktrees not supported on Windows")
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is empty for all cases — byte-identical comparison."""
    expected_stdout = _read_expected_stdout(case)
    result, _wt = _run_case(case, tmp_path)
    assert_byte_identical(result.stdout, expected_stdout)


@pytest.mark.skipif(sys.platform == "win32", reason="git worktrees not supported on Windows")
@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result, _wt = _run_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}\n"
        f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="git worktrees not supported on Windows")
@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_tagged_lines_parity(case: str, tmp_path: Path) -> None:
    """Tagged stderr lines match the fixture pattern after path substitution.

    The fixture's .stderr uses the <WT_PATH> placeholder for dynamic paths.
    The actual stderr is filtered to tagged lines, path-substituted, then
    compared against the fixture content.
    """
    expected_pattern = _read_expected_stderr_pattern(case)
    result, wt_path = _run_case(case, tmp_path)

    tagged = _tagged_lines(result.stderr)
    normalized = _substitute_wt_path(tagged, wt_path)
    actual_normalized = "\n".join(normalized)
    if normalized:
        actual_normalized += "\n"

    assert actual_normalized == expected_pattern, (
        f"tagged stderr pattern mismatch for {case!r}:\n"
        f"  actual (normalized):   {actual_normalized!r}\n"
        f"  expected (fixture):    {expected_pattern!r}\n"
        f"  raw stderr:            "
        f"{result.stderr.decode('utf-8', errors='replace')!r}"
    )


# ---------------------------------------------------------------------------
# Shared invocation + state-building helper
# ---------------------------------------------------------------------------


def _run_case(
    case: str, tmp_path: Path
) -> tuple[subprocess.CompletedProcess, Optional[Path]]:
    """Build synthetic git state, invoke the module, and return (result, wt_path).

    Each test function receives a unique tmp_path from pytest, so each call
    to this helper builds fresh state and runs the module independently.
    """
    builder = _STATE_BUILDERS.get(case)
    if builder is None:
        pytest.skip(f"no state builder for case {case!r}")

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)

    parent_repo, synthetic_tmpdir, created_worktrees, wt_path = builder(tmp_path)

    try:
        result = _invoke_module(argv, stdin_bytes, parent_repo, synthetic_tmpdir)
    finally:
        # Always clean up worktrees to avoid leaking git admin state.
        if created_worktrees:
            _cleanup_worktrees(parent_repo, created_worktrees)

    return result, wt_path
