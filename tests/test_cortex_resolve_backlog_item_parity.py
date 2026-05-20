"""Parity test: cortex_command.backlog.resolve_item vs bash cortex-resolve-backlog-item.

Golden-replay fixture test asserting that the Python wheel-tier port produces
byte-identical (or structurally-equivalent under declared tolerances) stdout,
stderr, and exit-code output compared to the captured bash/PEP-723 original.

Each fixture quintuple in tests/fixtures/cortex-resolve-backlog-item/ contains:
  <case>.argv      one argv element per line (line 1 is sys.argv[1])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

Three golden-replay cases are defined (exit codes 0/2/3):
  numeric_unambiguous     — numeric ID resolves to one match (exit 0, JSON stdout)
  title_phrase_ambiguous  — title phrase resolves to >1 matches (exit 2, candidates stderr)
  no_match                — input matches nothing (exit 3, stderr message)

Named-tolerance categories per the fixture README:
  numeric_unambiguous stdout:  ["key-reorder", "unicode-escape", "trailing-newline"]
  all other streams:           byte-identical (no tolerance opted in)

error-formatter-shape is NOT opted in: the script's stderr messages in cases
2 and 3 are fixed-format strings that the port must reproduce byte-for-byte
(subject to trailing-newline tolerance which is stdout-only per contract).
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
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-resolve-backlog-item"
BACKLOG_DIR = REPO_ROOT / "cortex" / "backlog"

# Determinism env-var overrides mirroring the capture harness (see README).
_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
    "CORTEX_BACKLOG_DIR": str(BACKLOG_DIR),
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
    """Build a deterministic environment for fixture invocations.

    Inherits the current process environment (so Python itself is reachable),
    then applies determinism overrides and the CORTEX_BACKLOG_DIR pointing to
    the repo's committed backlog state at fixture-capture time.
    """
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    return env


# ---------------------------------------------------------------------------
# Invocation helper (cached per case)
# ---------------------------------------------------------------------------

_result_cache: dict[str, subprocess.CompletedProcess] = {}


def _invoke_case(case: str) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.backlog.resolve_item for the given fixture case.

    Results are memoized per case because stdout, stderr, and exitcode tests
    all share the same invocation.
    """
    if case in _result_cache:
        return _result_cache[case]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    env = _build_env()

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.resolve_item"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    _result_cache[case] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str) -> None:
    """stderr is byte-identical to the fixture capture.

    The script's stderr messages (ambiguous-candidate list and no-match
    diagnostic) are fixed-format strings the port must reproduce exactly.
    No tolerance is opted in for stderr.
    """
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str) -> None:
    """stdout is byte-identical or structurally equivalent per declared tolerances.

    For ``numeric_unambiguous`` (exit 0, JSON output): structural equivalence
    under key-reorder, unicode-escape, and trailing-newline tolerances.

    For all other cases (no stdout): byte-identical (trivially empty).
    """
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case).stdout

    if case == "numeric_unambiguous":
        # JSON stdout: apply structural-equivalence tolerances per fixture README.
        assert_structurally_equivalent(
            actual_stdout,
            expected_stdout,
            stream="stdout",
            tolerances=["key-reorder", "unicode-escape", "trailing-newline"],
        )
    else:
        # Empty stdout cases: byte-identical.
        assert_byte_identical(actual_stdout, expected_stdout)


# ---------------------------------------------------------------------------
# Edge-case suite — exercises exit codes 64 and 70 (not in golden-replay
# fixtures per the README, but covered here to complete the contract).
# ---------------------------------------------------------------------------


def _invoke_with_argv(argv: list[str], env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the module directly with the given argv list."""
    env = _build_env()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "cortex_command.backlog.resolve_item"] + argv,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_exit_64_empty_input() -> None:
    """Empty string input produces exit code 64 (usage error)."""
    result = _invoke_with_argv([""])
    assert result.returncode == 64, (
        f"expected exit 64 for empty input, got {result.returncode}"
    )
    assert result.stderr, "expected non-empty stderr for usage error"


def test_exit_64_whitespace_input() -> None:
    """Whitespace-only input produces exit code 64 (usage error)."""
    result = _invoke_with_argv(["   "])
    assert result.returncode == 64, (
        f"expected exit 64 for whitespace input, got {result.returncode}"
    )


def test_exit_70_missing_backlog_dir() -> None:
    """Missing backlog directory produces exit code 70 (software/IO error)."""
    result = _invoke_with_argv(
        ["some-item"],
        env_overrides={"CORTEX_BACKLOG_DIR": "/nonexistent/backlog/dir/xyz"},
    )
    assert result.returncode == 70, (
        f"expected exit 70 for missing backlog dir, got {result.returncode}"
    )
    assert result.stderr, "expected non-empty stderr for missing backlog dir"
