"""Parity test: cortex_command.commit.preflight vs captured golden fixtures.

Golden-replay fixture test that asserts the Python port
(``cortex_command.commit.preflight``) produces stdout/stderr/exit-code
matching the captured fixtures in ``tests/fixtures/cortex-commit-preflight/``.

Each fixture quintuple contains:
  <case>.argv      one argv element per line (empty for all current cases)
  <case>.stdin     literal bytes piped to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

The ``valid_git_repo`` and ``empty_repo`` cases require a controlled git
environment. The test re-creates this environment deterministically for each
run. The ``not_in_repo`` case uses a plain directory with no git ancestry.

Named-tolerance categories for this fixture set:
  stdout: ["key-reorder", "trailing-newline"]
  stderr: byte-identical (fixed strings, must match exactly)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_parity_contract import (
    assert_byte_identical,
    assert_structurally_equivalent,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-commit-preflight"

# Determinism env-var overrides mirroring the capture harness (see README).
_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
}


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    cases: list[str] = []
    for path in FIXTURE_DIR.glob("*.argv"):
        cases.append(path.stem)
    return sorted(cases)


def _read_argv(case: str) -> list[str]:
    """Parse <case>.argv: one element per line (strip trailing newlines)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    """Read <case>.stdin as raw bytes (may be empty)."""
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


# ---------------------------------------------------------------------------
# Environment construction
# ---------------------------------------------------------------------------


def _build_env() -> dict[str, str]:
    """Build a minimal environment for one fixture invocation.

    Inherits the current process environment, then applies determinism
    overrides. Inheriting the full environment is necessary so that Python
    itself (sys.executable path, LD_LIBRARY_PATH on Linux, etc.)
    remains resolvable.
    """
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    return env


# ---------------------------------------------------------------------------
# Controlled git environment setup
# ---------------------------------------------------------------------------


def _setup_valid_git_repo(tmp_path: Path) -> Path:
    """Create a deterministic git repo with one commit and return its path.

    Replicates the exact state used during fixture capture:
    - Branch: main (forced via git checkout -b main)
    - File: hello.txt with content 'hello world\\n'
    - Commit message: 'Initial commit'
    - Author/committer: Test <test@example.com>
    - Author/committer date: 2024-01-15T10:00:00+0000
    - GPG signing: disabled

    The resulting abbreviated commit hash is 2a9110f (deterministic given
    the above parameters and no parent commit).
    """
    repo = tmp_path / "valid_git_repo"
    repo.mkdir(parents=True)

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "checkout", "-q", "-b", "main")

    (repo / "hello.txt").write_text("hello world\n", encoding="utf-8")
    _git(repo, "add", "hello.txt")

    commit_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2024-01-15T10:00:00+0000",
        "GIT_COMMITTER_DATE": "2024-01-15T10:00:00+0000",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "commit", "-q", "-m", "Initial commit"],
        cwd=str(repo),
        env=commit_env,
        check=True,
        capture_output=True,
    )

    return repo


def _setup_empty_repo(tmp_path: Path) -> Path:
    """Create a fresh git repo with no commits and return its path.

    Replicates the exact state used during fixture capture:
    - Branch: main (forced via 'git checkout -b main')
    - No commits (HEAD does not exist)
    - No files staged
    """
    repo = tmp_path / "empty_repo"
    repo.mkdir(parents=True)

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    # Force branch to main. In empty repos, git checkout -b main may fail if
    # the initial branch is already 'main'. Use git symbolic-ref instead to
    # be robust across git versions and configurations.
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    return repo


def _setup_not_in_repo(tmp_path: Path) -> Path:
    """Create a plain directory with no git ancestry and return its path.

    The directory is created inside tmp_path. Pytest's tmp_path is always
    outside any git worktree, so this directory has no .git in its ancestry.
    """
    plain = tmp_path / "not_in_repo"
    plain.mkdir(parents=True)
    return plain


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in the given directory, checking for success."""
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Per-case git environment factory
# ---------------------------------------------------------------------------


def _setup_cwd_for_case(case: str, tmp_path: Path) -> Path:
    """Return the working directory to use when running the module for this case."""
    if case == "valid_git_repo":
        return _setup_valid_git_repo(tmp_path)
    if case == "empty_repo":
        return _setup_empty_repo(tmp_path)
    if case == "not_in_repo":
        return _setup_not_in_repo(tmp_path)
    pytest.fail(f"unknown fixture case: {case!r}")


# ---------------------------------------------------------------------------
# Invocation helper (shared per test function via fixture)
# ---------------------------------------------------------------------------


@pytest.fixture()
def invocation_result(request: pytest.FixtureRequest, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run cortex_command.commit.preflight for the current case and return result.

    This fixture is parametrized indirectly via the test's parametrize marker.
    It sets up the controlled git environment and invokes the module once,
    then provides the result to all three assertion tests.
    """
    case: str = request.param
    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    cwd = _setup_cwd_for_case(case, tmp_path)
    env = _build_env()

    return subprocess.run(
        [sys.executable, "-m", "cortex_command.commit.preflight"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["key-reorder", "trailing-newline"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout matches the fixture capture.

    For JSON-emitting cases (valid_git_repo, empty_repo): structural equivalence
    with key-reorder and trailing-newline tolerances.
    For non-JSON cases (not_in_repo): byte-identical (empty stdout).
    """
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _run_case(case, tmp_path).stdout

    if not expected_stdout and not actual_stdout:
        # Both empty — trivially identical.
        assert_byte_identical(actual_stdout, expected_stdout)
    elif not expected_stdout or not actual_stdout:
        # One side empty, other not — always a parity failure.
        assert_byte_identical(actual_stdout, expected_stdout)
    else:
        # Both non-empty — use structural equivalence for JSON stdout.
        assert_structurally_equivalent(
            actual_stdout,
            expected_stdout,
            stream="stdout",
            tolerances=["key-reorder", "trailing-newline"],
        )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture.

    The stderr messages are fixed strings (e.g. 'not inside a git repository').
    The Python port must reproduce these byte-for-byte.
    """
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _run_case(case, tmp_path).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _run_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )


# ---------------------------------------------------------------------------
# Per-test invocation helper (avoids id(tmp_path) cache collision)
# ---------------------------------------------------------------------------

# Module-level cache keyed on str(tmp_path) + case to avoid id() aliasing
# after garbage collection. Each parametrized test function gets a fresh
# tmp_path from pytest, so the path string uniquely identifies an invocation.
_result_cache: dict[str, subprocess.CompletedProcess] = {}


def _run_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the module for the given case, memoizing by (tmp_path, case).

    Three test functions (stdout, stderr, exitcode) share this result.
    Cache key uses the full path string to avoid id() aliasing after GC.
    """
    cache_key = f"{tmp_path!s}::{case}"
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    cwd = _setup_cwd_for_case(case, tmp_path)
    env = _build_env()

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.commit.preflight"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )

    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Import check
# ---------------------------------------------------------------------------


def test_module_importable() -> None:
    """Verify the module is importable without side effects."""
    import cortex_command.commit.preflight as m  # noqa: F401
    assert hasattr(m, "main"), "cortex_command.commit.preflight must expose main()"
