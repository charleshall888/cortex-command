"""Parity test: cortex_command.lifecycle.state_cli vs bash cortex-lifecycle-state.

Golden-replay fixture test that asserts the Python port produces
byte-identical (or structurally equivalent under named tolerances) stdout,
stderr, and exit-code as the captured bash+jq original.

Fixtures live in tests/fixtures/cortex-lifecycle-state/. Each case is stored
as five sibling files:
  <case>.argv        one argv element per line (line 1 is argv[1] of the script)
  <case>.stdin       literal bytes piped to stdin (empty for all cases)
  <case>.stdout      literal bytes captured from stdout
  <case>.stderr      literal bytes captured from stderr
  <case>.exitcode    decimal exit status + trailing newline
  <case>.events.log  events.log content staged in cortex/lifecycle/<feature>/
                     (absent for missing-events-log, which tests the no-file path)

Named-tolerance categories per fixture (from tests/fixtures/cortex-lifecycle-state/README.md):

  basic-ok:              key-reorder  (stdout)
  complexity-override:   key-reorder  (stdout)
  criticality-override:  key-reorder  (stdout)
  field-criticality:     none         (single-key object; key-reorder is vacuous)
  field-tier:            none         (single-key object; key-reorder is vacuous)
  missing-events-log:    none         (output is {} — trivially byte-identical)
  no-start-event:        none         (output is {} — trivially byte-identical)
  torn-line:             error-formatter-shape (stderr), key-reorder (stdout)

The torn-line case applies the error-formatter-shape tolerance to stderr only;
stdout must still match the fixture (null).

Determinism harness: LC_ALL=C, TZ=UTC as set during fixture capture.
LIFECYCLE_SESSION_ID is unset and CORTEX_REPO_ROOT is set to the scratch
directory to prevent telemetry side-effects from polluting the comparison.
"""

from __future__ import annotations

import os
import shutil
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
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-lifecycle-state"

# Determinism env-var overrides mirroring the capture harness (per README).
_DETERMINISM_ENV_OVERRIDES: dict[str, str] = {
    "LC_ALL": "C",
    "TZ": "UTC",
}

# Per-fixture tolerance declarations (from README.md tolerance table).
# Key: case name. Value: dict with "stdout_tolerances" and "stderr_tolerances".
_CASE_TOLERANCES: dict[str, dict[str, list[str]]] = {
    "basic-ok":            {"stdout": ["key-reorder"], "stderr": []},
    "complexity-override": {"stdout": ["key-reorder"], "stderr": []},
    "criticality-override":{"stdout": ["key-reorder"], "stderr": []},
    "field-criticality":   {"stdout": [],              "stderr": []},
    "field-tier":          {"stdout": [],              "stderr": []},
    "missing-events-log":  {"stdout": [],              "stderr": []},
    "no-start-event":      {"stdout": [],              "stderr": []},
    "torn-line":           {"stdout": ["key-reorder"], "stderr": ["error-formatter-shape"]},
}


# ---------------------------------------------------------------------------
# Fixture discovery helpers
# ---------------------------------------------------------------------------


def _discover_cases() -> list[str]:
    """Return sorted list of case names in the fixture directory."""
    return sorted(p.stem for p in FIXTURE_DIR.glob("*.argv"))


def _read_argv(case: str) -> list[str]:
    """Parse <case>.argv: one element per line (skip blanks)."""
    text = (FIXTURE_DIR / f"{case}.argv").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _read_stdin(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    return int((FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip())


# ---------------------------------------------------------------------------
# Staging helper
# ---------------------------------------------------------------------------


def _stage_fixture(case: str, tmp_path: Path, feature: str) -> Path:
    """Stage <case>.events.log into tmp_path/cortex/lifecycle/<feature>/events.log.

    Returns tmp_path (the cwd to use for the subprocess invocation).
    The events.log file is absent for missing-events-log — the directory is
    created but no file is written.
    """
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)

    events_log_src = FIXTURE_DIR / f"{case}.events.log"
    if events_log_src.is_file():
        shutil.copy2(events_log_src, feature_dir / "events.log")

    return tmp_path


def _extract_feature(argv: list[str]) -> str:
    """Extract the --feature value from an argv list."""
    for i, arg in enumerate(argv):
        if arg == "--feature" and i + 1 < len(argv):
            return argv[i + 1]
    raise ValueError(f"--feature not found in argv: {argv!r}")


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------

# Cache subprocess results per (case, tmp_path) to share across test functions.
_result_cache: dict[tuple[str, str], subprocess.CompletedProcess] = {}


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.lifecycle.state_cli for the given case.

    Stages the fixture's events.log into a scratch cortex/lifecycle/<feature>/
    directory and invokes the module with the captured argv. Results are cached
    per (case, tmp_path) so that stdout/stderr/exitcode tests share one run.
    """
    cache_key = (str(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    feature = _extract_feature(argv)

    cwd = _stage_fixture(case, tmp_path, feature)

    # Build environment: inherit current env, apply determinism overrides,
    # remove LIFECYCLE_SESSION_ID to suppress telemetry side-effects,
    # set CORTEX_REPO_ROOT to the scratch directory.
    # PYTHONPATH is prepended with REPO_ROOT so the subprocess loads the
    # local worktree's cortex_command package rather than any editable
    # install that may point to a different worktree.
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    env.pop("LIFECYCLE_SESSION_ID", None)
    env["CORTEX_REPO_ROOT"] = str(cwd)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + os.pathsep + existing_pythonpath
        if existing_pythonpath
        else str(REPO_ROOT)
    )

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.state_cli"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )

    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------

_CASES = _discover_cases()


@pytest.mark.parametrize("case", _CASES)
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected}"
    )


@pytest.mark.parametrize("case", _CASES)
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout matches the fixture capture under declared tolerances."""
    expected_bytes = _read_expected_stdout(case)
    result = _invoke_case(case, tmp_path)
    actual_bytes = result.stdout

    tolerances = _CASE_TOLERANCES.get(case, {}).get("stdout", [])

    if not tolerances:
        assert_byte_identical(actual_bytes, expected_bytes)
    else:
        assert_structurally_equivalent(
            actual_bytes,
            expected_bytes,
            stream="stdout",
            tolerances=tolerances,
        )


@pytest.mark.parametrize("case", _CASES)
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr matches the fixture capture under declared tolerances.

    For the torn-line case, the error-formatter-shape tolerance is applied:
    both actual and expected are empty with exit 0 — the Python port must
    also produce empty stderr with exit 0.
    """
    expected_bytes = _read_expected_stderr(case)
    result = _invoke_case(case, tmp_path)
    actual_bytes = result.stderr

    tolerances = _CASE_TOLERANCES.get(case, {}).get("stderr", [])

    if not tolerances:
        assert_byte_identical(actual_bytes, expected_bytes)
    else:
        assert_structurally_equivalent(
            actual_bytes,
            expected_bytes,
            stream="stderr",
            tolerances=tolerances,
            exit_code_actual=result.returncode,
            exit_code_expected=_read_expected_exitcode(case),
        )
