"""Parity test: cortex_command.lint.prescriptive_prose vs original bin/cortex-check-prescriptive-prose.

Golden-replay fixture test that asserts the Python port produces stdout/stderr/
exit-code matching the captured originals. The original script was a 409-line
stdlib-only Python file (``#!/usr/bin/env python3``); the port moves it into
``cortex_command/lint/prescriptive_prose.py`` with the ``main()`` entry point.

Each fixture quintuple in tests/fixtures/cortex-check-prescriptive-prose/:
  <case>.argv      one argv element per line (line 1 is argv[1])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline
  <case>.md        the markdown file to scan (passed as the positional file arg)

The .argv files contain repo-relative paths to the companion .md files. The
parity test invokes the module with cwd=REPO_ROOT so the paths resolve correctly
and the output paths in stderr are stable repo-relative strings.

Cases:
  clean               No violations; exit 0; empty stderr.
  with_violations     path:line and section-index hits in Why/Role/Edges; exit 1.
  with_fenced_block   Multi-line fenced block in ## Why; exit 1.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_parity_contract import assert_byte_identical


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-check-prescriptive-prose"

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
# Invocation helper
# ---------------------------------------------------------------------------


# Cache: case → CompletedProcess to avoid running the subprocess multiple times.
_result_cache: dict[str, subprocess.CompletedProcess] = {}


def _invoke_case(case: str) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.lint.prescriptive_prose for the given fixture case.

    Invokes with cwd=REPO_ROOT so that repo-relative paths in .argv files resolve
    correctly and output paths in stderr are stable repo-relative strings.
    Results are memoized per case name since stdout/stderr/exitcode tests share
    the same invocation.
    """
    if case in _result_cache:
        return _result_cache[case]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)

    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lint.prescriptive_prose"] + argv,
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
def test_stdout_parity(case: str) -> None:
    """stdout is byte-identical to the fixture capture (always empty by contract)."""
    result = _invoke_case(case)
    expected_stdout = _read_expected_stdout(case)
    assert_byte_identical(result.stdout, expected_stdout)


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str) -> None:
    """stderr is byte-identical to the fixture capture.

    The fixture .stderr files contain repo-relative paths. The test invokes
    the module with cwd=REPO_ROOT so that output paths are stable repo-relative
    strings matching the fixtures.
    """
    result = _invoke_case(case)
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = result.stderr

    assert actual_stderr == expected_stderr, (
        f"stderr mismatch for case {case!r}:\n"
        f"  expected: {expected_stderr!r}\n"
        f"  actual:   {actual_stderr!r}"
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str) -> None:
    """Exit code matches the fixture capture."""
    result = _invoke_case(case)
    expected_exitcode = _read_expected_exitcode(case)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for case {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )
