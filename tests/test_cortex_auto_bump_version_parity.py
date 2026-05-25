"""Parity test: cortex_command.auto_bump_version vs captured bin/ fixtures.

Golden-replay fixture test that asserts the Python module produces
byte-identical stdout/stderr/exit-code as the captured original script,
when replayed against synthetic git repositories matching each fixture's
setup.

Each fixture quintuple in tests/fixtures/cortex-auto-bump-version/ contains:
  <case>.argv      one argv element per line (line 1 is sys.argv[0])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

The script exits 0 for all cases; stdout is a plain-text tag or 'no-bump'.
stderr is always empty.

Named-tolerance categories opted in for this fixture set (per README):
  stdout surface: ["trailing-newline"]
  stderr surface: byte-identical (always empty)

'unicode-escape', 'error-formatter-shape', 'number-format', and 'key-reorder'
are NOT opted into: the script emits plain text, not JSON. 'unicode-escape'
requires JSON-parseable content and is not applicable here.

Fixture-to-repo mapping (each case requires a specific git repo state):
  no_bump             — HEAD == latest tag (v1.2.3, no commits after)
  patch_bump          — two plain commits after tag v1.2.3
  minor_bump          — one commit with [release-type: minor] after v1.2.3
  major_bump_breaking — one commit with BREAKING: footer after v1.2.3
  no_tags_default     — no tags, one commit
  patch_bump_dry_run  — one plain commit after v2.0.0, --dry-run flag
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
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-auto-bump-version"


# ---------------------------------------------------------------------------
# Git repo helpers
# ---------------------------------------------------------------------------

_GIT_ENV_BASE = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git_env() -> dict[str, str]:
    """Build a minimal git environment, inheriting PATH and PYTHONPATH."""
    env = dict(os.environ)
    env.update(_GIT_ENV_BASE)
    env.pop("LIFECYCLE_SESSION_ID", None)
    return env


def _init_repo(tmp_path: Path) -> None:
    """Init a minimal git repo at ``tmp_path``."""
    env = _git_env()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "commit.gpgsign", "false"],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "tag.gpgsign", "false"],
        check=True, env=env,
    )


def _commit(tmp_path: Path, filename: str, message: str) -> None:
    """Make a commit with ``message`` in ``tmp_path``."""
    env = _git_env()
    (tmp_path / filename).write_text(filename, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", filename],
        check=True, env=env,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", message],
        check=True, env=env,
    )


def _tag(tmp_path: Path, tag: str) -> None:
    env = _git_env()
    subprocess.run(
        ["git", "-C", str(tmp_path), "tag", tag],
        check=True, env=env,
    )


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names present in the fixture directory."""
    cases: list[str] = []
    for path in FIXTURE_DIR.glob("*.argv"):
        cases.append(path.stem)
    return sorted(cases)


def _read_argv_extra(case: str) -> list[str]:
    """Parse <case>.argv and return args after line 1 (the script path)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line]
    # Line 0 is the script path; remaining lines are extra args.
    return lines[1:]


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


# ---------------------------------------------------------------------------
# Per-case repo setup
# ---------------------------------------------------------------------------

# Maps case name → callable that receives tmp_path and sets up the git repo.
# Each callable populates the repo to match the state at capture time.


def _setup_no_bump(tmp_path: Path) -> None:
    """HEAD == latest tag → no-bump."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.2.3")


def _setup_patch_bump(tmp_path: Path) -> None:
    """Two plain commits after tag v1.2.3 → patch bump."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.2.3")
    _commit(tmp_path, "b.txt", "fix: small bug")
    _commit(tmp_path, "c.txt", "docs: update readme")


def _setup_minor_bump(tmp_path: Path) -> None:
    """Commit with [release-type: minor] body → minor bump."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.2.3")
    _commit(tmp_path, "b.txt", "feat: new feature\n\n[release-type: minor]")


def _setup_major_bump_breaking(tmp_path: Path) -> None:
    """Commit with BREAKING: footer → major bump via fallback."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v1.2.3")
    _commit(tmp_path, "b.txt", "refactor: restructure API\n\nBREAKING: removes old interface")


def _setup_no_tags_default(tmp_path: Path) -> None:
    """No tags in repo, one commit → DEFAULT_TAG (v0.1.0)."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")


def _setup_patch_bump_dry_run(tmp_path: Path) -> None:
    """One plain commit after v2.0.0 → patch bump (dry-run flag same output)."""
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt", "initial commit")
    _tag(tmp_path, "v2.0.0")
    _commit(tmp_path, "b.txt", "fix: typo")


_CASE_SETUP: dict[str, object] = {
    "no_bump": _setup_no_bump,
    "patch_bump": _setup_patch_bump,
    "minor_bump": _setup_minor_bump,
    "major_bump_breaking": _setup_major_bump_breaking,
    "no_tags_default": _setup_no_tags_default,
    "patch_bump_dry_run": _setup_patch_bump_dry_run,
}


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------

_result_cache: dict[tuple[str, str], subprocess.CompletedProcess] = {}


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.auto_bump_version for the given fixture case.

    Results are memoized within a single tmp_path because multiple test
    functions (stdout, stderr, exitcode) share the same invocation.
    """
    cache_key = (str(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    # Set up the repo for this case.
    setup_fn = _CASE_SETUP.get(case)
    if setup_fn is None:
        pytest.skip(f"no setup function for case {case!r}")

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    setup_fn(repo_dir)  # type: ignore[operator]

    # Parse extra args from the .argv fixture.
    extra_args = _read_argv_extra(case)

    env = _git_env()

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.auto_bump_version"] + extra_args,
        cwd=str(repo_dir),
        capture_output=True,
        text=False,
        env=env,
    )

    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["trailing-newline"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout matches the fixture capture under trailing-newline tolerance.

    The module emits plain text ('no-bump\\n' or 'vX.Y.Z\\n') via
    sys.stdout.write. Only trailing-newline tolerance is needed; the output
    contains only ASCII and is not JSON.
    """
    expected_stdout = _read_expected_stdout(case)
    result = _invoke_case(case, tmp_path)
    actual_stdout = result.stdout

    assert_structurally_equivalent(
        actual_stdout,
        expected_stdout,
        stream="stdout",
        tolerances=["trailing-newline"],
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is empty for all cases (byte-identical comparison)."""
    expected_stderr = _read_expected_stderr(case)
    result = _invoke_case(case, tmp_path)
    actual_stderr = result.stderr

    # All fixtures have empty stderr — strict byte-identical comparison.
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture (always 0 for all cases)."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )
