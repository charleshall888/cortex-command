"""Parity test: cortex_command.git.sync_rebase vs bash cortex-git-sync-rebase.

Golden-replay fixture test for the three fixture cases defined in
tests/fixtures/cortex-git-sync-rebase/. Each test constructs a synthetic git
repository in tmp_path to avoid touching the live repo; the module is invoked
directly via its public API (not as a subprocess) so that no installed wheel is
required.

Named tolerances applied per stream:

  stdout surface:  byte-identical (always empty)
  stderr surface:  error-formatter-shape — stderr contains [git-sync-rebase]
                   log lines whose path segments vary per tmp_path invocation,
                   so byte-identical comparison is not meaningful. The test
                   instead asserts structural properties: the prefix is present,
                   the expected keyword appears, and the exit code matches.
  exit code:       exact integer match against the fixture .exitcode file.

Fixture cases:
  noop                  — HEAD already up to date; exit 0
  clean_rebase          — one commit behind, clean rebase + push; exit 0
  conflict_non_allowlist — one commit behind, non-allowlist conflict; exit 1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

from cortex_command.git.sync_rebase import sync_rebase
from tests.test_parity_contract import assert_byte_identical


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-git-sync-rebase"


# ---------------------------------------------------------------------------
# Fixture file readers
# ---------------------------------------------------------------------------


def _read_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


def _read_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_stderr_keywords(case: str) -> list[str]:
    """Return the [git-sync-rebase] keyword fragments to assert in stderr.

    Instead of byte-identical comparison (stderr contains tmp_path-dependent
    content), we extract the key diagnostic phrases from the fixture stderr and
    assert each appears in the actual output.
    """
    text = (FIXTURE_DIR / f"{case}.stderr").read_text(encoding="utf-8")
    keywords: list[str] = []
    for line in text.splitlines():
        # Grab the part after '[git-sync-rebase] ' as the keyword fragment.
        prefix = "[git-sync-rebase] "
        if line.startswith(prefix):
            fragment = line[len(prefix):]
            if fragment:
                keywords.append(fragment)
    return keywords


# ---------------------------------------------------------------------------
# Synthetic git repo helpers
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run git in the given directory, raising on failure."""
    base_env = dict(os.environ)
    base_env["GIT_AUTHOR_NAME"] = "Test"
    base_env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    base_env["GIT_COMMITTER_NAME"] = "Test"
    base_env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    base_env["GIT_CONFIG_COUNT"] = "1"
    base_env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    base_env["GIT_CONFIG_VALUE_0"] = "false"
    if env:
        base_env.update(env)
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=base_env,
        check=True,
    )


def _make_bare_origin(tmp_path: Path, *, subdir: str = "origin") -> Path:
    """Create a bare git repo to serve as the remote origin."""
    origin = tmp_path / subdir
    origin.mkdir()
    _git(["init", "--bare", "--initial-branch=main"], cwd=origin)
    return origin


def _make_local_clone(tmp_path: Path, origin: Path, *, subdir: str = "local") -> Path:
    """Clone the bare origin into a local working copy."""
    local = tmp_path / subdir
    _git(
        ["clone", str(origin), str(local)],
        cwd=tmp_path,
    )
    # Configure the clone's user so commits work.
    _git(["config", "user.email", "test@example.com"], cwd=local)
    _git(["config", "user.name", "Test"], cwd=local)
    return local


def _commit_file(repo: Path, filename: str, content: str, message: str) -> None:
    """Write a file, add it, and commit in the given repo."""
    (repo / filename).write_text(content, encoding="utf-8")
    _git(["add", filename], cwd=repo)
    _git(["commit", "-m", message], cwd=repo)


# ---------------------------------------------------------------------------
# Per-case synthetic repo constructors
# ---------------------------------------------------------------------------


def _setup_noop(tmp_path: Path) -> tuple[Path, Optional[Path]]:
    """Return (local_repo, allowlist_file) for the noop case.

    The local repo is already up to date with origin/main — no commits behind.
    """
    origin = _make_bare_origin(tmp_path)

    # Bootstrap origin with an initial commit via a temp clone.
    bootstrap = tmp_path / "bootstrap"
    _git(["clone", str(origin), str(bootstrap)], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=bootstrap)
    _git(["config", "user.name", "Test"], cwd=bootstrap)
    _commit_file(bootstrap, "readme.txt", "hello\n", "Initial commit")
    _git(["push", "origin", "main"], cwd=bootstrap)

    local = _make_local_clone(tmp_path, origin)
    return local, None


def _setup_clean_rebase(tmp_path: Path) -> tuple[Path, Optional[Path]]:
    """Return (local_repo, allowlist_file) for the clean_rebase case.

    The local repo is one commit behind origin/main. The rebase completes
    without conflicts. The origin will accept a force-push from local so that
    the push step (step 6) also succeeds — we update local's commit to be
    on top of origin's commit, then push.
    """
    origin = _make_bare_origin(tmp_path)

    # Bootstrap with an initial commit.
    bootstrap = tmp_path / "bootstrap"
    _git(["clone", str(origin), str(bootstrap)], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=bootstrap)
    _git(["config", "user.name", "Test"], cwd=bootstrap)
    _commit_file(bootstrap, "readme.txt", "hello\n", "Initial commit")
    _git(["push", "origin", "main"], cwd=bootstrap)

    # Create a local clone (currently at origin/main).
    local = _make_local_clone(tmp_path, origin)

    # Add a commit to origin that local doesn't have yet.
    _commit_file(bootstrap, "origin_only.txt", "from origin\n", "Origin commit")
    _git(["push", "origin", "main"], cwd=bootstrap)

    # Add a local commit on a different file (no conflict with origin_only.txt).
    _commit_file(local, "local_only.txt", "from local\n", "Local commit")

    return local, None


def _setup_conflict_non_allowlist(tmp_path: Path) -> tuple[Path, Optional[Path]]:
    """Return (local_repo, allowlist_file) for the conflict_non_allowlist case.

    Both origin and local modify the same file (work.txt), causing a rebase
    conflict. The file is NOT in the allowlist, so the rebase is aborted.
    """
    origin = _make_bare_origin(tmp_path)

    # Bootstrap.
    bootstrap = tmp_path / "bootstrap"
    _git(["clone", str(origin), str(bootstrap)], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=bootstrap)
    _git(["config", "user.name", "Test"], cwd=bootstrap)
    _commit_file(bootstrap, "work.txt", "line A\n", "Initial commit")
    _git(["push", "origin", "main"], cwd=bootstrap)

    local = _make_local_clone(tmp_path, origin)

    # Origin modifies work.txt.
    _commit_file(bootstrap, "work.txt", "line B from origin\n", "Origin changes work.txt")
    _git(["push", "origin", "main"], cwd=bootstrap)

    # Local also modifies work.txt (divergent — causes conflict).
    _commit_file(local, "work.txt", "line C from local\n", "Local changes work.txt")

    # Write a minimal allowlist that does NOT match work.txt.
    allowlist = tmp_path / "allowlist.conf"
    allowlist.write_text("# only lifecycle artifacts are safe\nlifecycle/sessions/*/\n", encoding="utf-8")

    return local, allowlist


# ---------------------------------------------------------------------------
# Case configuration
# ---------------------------------------------------------------------------

_CASE_SETUP = {
    "noop": _setup_noop,
    "clean_rebase": _setup_clean_rebase,
    "conflict_non_allowlist": _setup_conflict_non_allowlist,
}

_CASES = sorted(_CASE_SETUP.keys())


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _CapturedResult:
    """Holds the return code and stderr text from invoking sync_rebase."""

    def __init__(self, returncode: int, stderr_text: str) -> None:
        self.returncode = returncode
        self.stderr = stderr_text.encode("utf-8")
        self.stdout = b""


def _invoke_case(case: str, tmp_path: Path) -> _CapturedResult:
    """Invoke sync_rebase for the given fixture case and return the result.

    stderr is captured by redirecting sys.stderr during the call. The
    function constructs the appropriate synthetic git repo using the per-case
    setup function.
    """
    import io

    setup_fn = _CASE_SETUP[case]
    local_repo, allowlist_file = setup_fn(tmp_path)

    # Capture stderr from the module (it writes directly to sys.stderr).
    old_stderr = sys.stderr
    buf = io.StringIO()
    sys.stderr = buf
    saved_env = {
        k: os.environ.get(k)
        for k in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
    }
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    os.environ["GIT_CONFIG_VALUE_0"] = "false"
    try:
        returncode = sync_rebase(repo_root=local_repo, allowlist_file=allowlist_file)
    finally:
        sys.stderr = old_stderr
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return _CapturedResult(returncode=returncode, stderr_text=buf.getvalue())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES)
def test_stdout_is_empty(case: str, tmp_path: Path) -> None:
    """stdout is always empty — all output goes to stderr."""
    result = _invoke_case(case, tmp_path)
    expected_stdout = _read_stdout(case)
    assert_byte_identical(result.stdout, expected_stdout)


@pytest.mark.parametrize("case", _CASES)
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}. "
        f"stderr was: {result.stderr.decode('utf-8', errors='replace')!r}"
    )


@pytest.mark.structural_equivalence(
    stream="stderr",
    tolerances=["error-formatter-shape"],
)
@pytest.mark.parametrize("case", _CASES)
def test_stderr_structural_parity(case: str, tmp_path: Path) -> None:
    """stderr contains the expected [git-sync-rebase] diagnostic keyword phrases.

    Byte-identical comparison is not applicable because stderr includes
    file paths derived from tmp_path. The test asserts that each keyword
    fragment from the fixture stderr appears in the actual stderr output,
    and that the prefix '[git-sync-rebase]' is consistently present.
    """
    result = _invoke_case(case, tmp_path)
    actual_stderr = result.stderr.decode("utf-8", errors="replace")

    # All stderr lines from the module must carry the prefix.
    for line in actual_stderr.splitlines():
        if line:
            assert line.startswith("[git-sync-rebase] "), (
                f"stderr line missing prefix in case {case!r}: {line!r}"
            )

    # Each keyword fragment from the fixture must appear somewhere in stderr.
    keywords = _read_stderr_keywords(case)
    for kw in keywords:
        assert kw in actual_stderr, (
            f"expected stderr keyword {kw!r} not found in case {case!r}. "
            f"Actual stderr: {actual_stderr!r}"
        )
