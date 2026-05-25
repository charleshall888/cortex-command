"""Parity test: cortex_command.log_invocation vs bash cortex-log-invocation.

Golden-replay fixture test that asserts the Python port produces
byte-identical stdout/stderr/exit-code as the captured bash original, and
that the JSONL side-effect written to the scratch session dir is structurally
equivalent under the named tolerances declared in the fixture README.

Each fixture quintuple in tests/fixtures/cortex-log-invocation/ contains:
  <case>.argv      one argv element per line (line 1 is sys.argv[1])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

The bash script is fail-open by contract: every invocation exits 0 with
empty stdout and stderr.  The named tolerances apply when comparing the
JSONL side-effect emitted by the Python port's json.dumps path against the
bash-captured shape (which was built via printf).

Named-tolerance categories opted in for this fixture set (per README):
  stdout/stderr surface:  ["unicode-escape", "trailing-newline"]
  JSONL side-effect:      ["unicode-escape", "trailing-newline",
                           "number-format", "key-reorder"]

error-formatter-shape is NOT opted in: the bash script never emits
diagnostic stderr on its happy or fail-open paths.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

from tests.test_parity_contract import (
    assert_byte_identical,
    assert_structurally_equivalent,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-log-invocation"

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


def _build_env(
    *,
    session_id: str | None,
    repo_root: str | None,
    home: str,
) -> dict[str, str]:
    """Build a minimal environment for one fixture invocation.

    Inherits the current process environment, then applies determinism
    overrides and sets LIFECYCLE_SESSION_ID / CORTEX_REPO_ROOT / HOME as
    directed by the caller.  Inheriting the full environment is necessary so
    that Python itself (sys.executable path, LD_LIBRARY_PATH on Linux, etc.)
    remains resolvable.
    """
    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    env["HOME"] = home
    # Remove LIFECYCLE_SESSION_ID and CORTEX_REPO_ROOT unconditionally first,
    # then set them only when the caller provides a value.
    env.pop("LIFECYCLE_SESSION_ID", None)
    env.pop("CORTEX_REPO_ROOT", None)
    if session_id is not None:
        env["LIFECYCLE_SESSION_ID"] = session_id
    if repo_root is not None:
        env["CORTEX_REPO_ROOT"] = repo_root
    return env


# ---------------------------------------------------------------------------
# Per-case env configuration
# ---------------------------------------------------------------------------

# Maps case name → (session_id, repo_root_is_valid, cwd_has_git)
# session_id=None means LIFECYCLE_SESSION_ID is unset (no_session_id case).
# repo_root_is_valid=True means CORTEX_REPO_ROOT is set to a valid git repo.
# repo_root_is_valid=False means CORTEX_REPO_ROOT is unset.
_CASE_CONFIG: dict[str, dict] = {
    "happy_path":    {"session_id": "test-session-01", "repo_root_valid": True,  "cwd_git": True,  "jsonl_expected": True},
    "no_session_id": {"session_id": None,              "repo_root_valid": True,  "cwd_git": True,  "jsonl_expected": False},
    "multi_argv":    {"session_id": "test-session-02", "repo_root_valid": True,  "cwd_git": True,  "jsonl_expected": True},
    "no_repo_root":  {"session_id": "test-session-03", "repo_root_valid": False, "cwd_git": False, "jsonl_expected": False},
}


# ---------------------------------------------------------------------------
# JSONL side-effect comparison helpers
# ---------------------------------------------------------------------------


_TS_PATTERN = re.compile(r'"ts"\s*:\s*"[^"]*"')


def _freeze_ts(jsonl_line: str) -> str:
    """Replace the 'ts' field value with a stable placeholder."""
    return _TS_PATTERN.sub('"ts":"<FROZEN>"', jsonl_line)


def _read_jsonl_side_effect(session_dir: Path) -> list[dict]:
    """Read bin-invocations.jsonl from session_dir and return parsed records."""
    log_file = session_dir / "bin-invocations.jsonl"
    if not log_file.exists():
        return []
    records = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _assert_jsonl_structurally_equivalent(
    actual_records: list[dict],
    expected_script: str,
    expected_argv_count: int,
    expected_session_id: str,
) -> None:
    """Assert the JSONL side-effect contains exactly one record with the right shape.

    The 'ts' field is excluded from comparison (clock-dependent).
    Named tolerances applied: key-reorder, unicode-escape, number-format.
    All are absorbed by json.loads + Python dict equality + int normalization.
    """
    assert len(actual_records) == 1, (
        f"expected exactly 1 JSONL record, got {len(actual_records)}: "
        f"{actual_records!r}"
    )
    record = actual_records[0]
    # ts must be present and non-empty (format validated, not value-compared).
    assert "ts" in record, f"JSONL record missing 'ts' field: {record!r}"
    assert isinstance(record["ts"], str) and record["ts"], (
        f"JSONL 'ts' field is not a non-empty string: {record!r}"
    )
    assert record.get("script") == expected_script, (
        f"JSONL 'script' mismatch: got {record.get('script')!r}, "
        f"expected {expected_script!r}"
    )
    # number-format tolerance: accept int or integer-valued float.
    actual_count = record.get("argv_count")
    if isinstance(actual_count, float) and actual_count.is_integer():
        actual_count = int(actual_count)
    assert actual_count == expected_argv_count, (
        f"JSONL 'argv_count' mismatch: got {record.get('argv_count')!r}, "
        f"expected {expected_argv_count!r}"
    )
    assert record.get("session_id") == expected_session_id, (
        f"JSONL 'session_id' mismatch: got {record.get('session_id')!r}, "
        f"expected {expected_session_id!r}"
    )


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["unicode-escape", "trailing-newline"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is byte-identical to the fixture capture (both empty by contract)."""
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case, tmp_path).stdout

    # All fixtures have empty stdout — use byte-identical comparison since
    # the named tolerances are declared for decorator documentation only;
    # when both sides are empty they agree trivially.
    if not expected_stdout and not actual_stdout:
        assert_byte_identical(actual_stdout, expected_stdout)
    else:
        assert_structurally_equivalent(
            actual_stdout,
            expected_stdout,
            stream="stdout",
            tolerances=["unicode-escape", "trailing-newline"],
        )


@pytest.mark.structural_equivalence(
    stream="stderr",
    tolerances=["unicode-escape"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture (both empty by contract)."""
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case, tmp_path).stderr

    if not expected_stderr and not actual_stderr:
        assert_byte_identical(actual_stderr, expected_stderr)
    else:
        assert_structurally_equivalent(
            actual_stderr,
            expected_stderr,
            stream="stderr",
            tolerances=["unicode-escape"],
        )


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture (always 0 by fail-open contract)."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )


@pytest.mark.structural_equivalence(
    stream="stdout",
    tolerances=["unicode-escape", "trailing-newline", "number-format", "key-reorder"],
)
@pytest.mark.parametrize("case", _discover_cases())
def test_jsonl_side_effect_parity(case: str, tmp_path: Path) -> None:
    """JSONL side-effect in the scratch session dir is structurally equivalent.

    For fail-open cases (no_session_id, no_repo_root) no JSONL is written.
    For happy-path cases exactly one record is written with the correct shape.
    The 'ts' field is validated as present+non-empty but not value-compared.
    """
    config = _CASE_CONFIG.get(case)
    if config is None:
        pytest.skip(f"no config entry for case {case!r}")

    # Run the invocation first, then inspect the session dir.
    _invoke_case(case, tmp_path)
    scratch_session_dir = _get_scratch_session_dir(case, tmp_path)

    jsonl_expected = config["jsonl_expected"]

    if not jsonl_expected:
        # Fail-open path: no JSONL should be written.
        # For no_session_id there is no session dir at all; verify it doesn't
        # exist or is empty.  For no_repo_root the dir also cannot be created
        # since there's no known repo root.
        if scratch_session_dir is None:
            # session_id is None — no session dir path can exist; pass.
            pass
        else:
            records = _read_jsonl_side_effect(scratch_session_dir)
            assert records == [], (
                f"expected no JSONL for case {case!r}, "
                f"but found records: {records!r}"
            )
    else:
        # Happy path: one JSONL record with the expected shape.
        records = _read_jsonl_side_effect(scratch_session_dir)
        argv = _read_argv(case)
        script_path = argv[0] if argv else ""
        expected_script = script_path.rsplit("/", 1)[-1] if script_path else ""
        expected_argv_count = max(len(argv) - 1, 0)
        expected_session_id = config["session_id"]
        _assert_jsonl_structurally_equivalent(
            records,
            expected_script=expected_script,
            expected_argv_count=expected_argv_count,
            expected_session_id=expected_session_id,
        )


# ---------------------------------------------------------------------------
# Invocation helper (cached per case+tmp_path via module-level dict)
# ---------------------------------------------------------------------------

# We need to run the subprocess once per case but three test functions consume
# the result.  Rather than a complex fixture chain, we keep a simple per-
# (tmp_path, case) cache in a module-level dict.  tmp_path is unique per test
# function in pytest; a helper that returns deterministic results can be called
# multiple times safely since all four fixture cases are independent.

_result_cache: dict[tuple[str, str], subprocess.CompletedProcess] = {}


def _get_scratch_home(case: str, tmp_path: Path) -> Path:
    """Return the scratch HOME directory for this case."""
    return tmp_path / "scratch-home"


def _get_scratch_repo(case: str, tmp_path: Path) -> Path:
    """Return the scratch git repo root for this case."""
    return tmp_path / "scratch-repo"


def _get_scratch_session_dir(case: str, tmp_path: Path) -> Path | None:
    """Return the expected session dir for this case, or None if no session_id.

    Returns None for fail-open cases where LIFECYCLE_SESSION_ID is unset,
    since no session dir can be constructed without a session id.
    """
    config = _CASE_CONFIG.get(case, {})
    session_id = config.get("session_id")
    if session_id is None:
        return None
    scratch_repo = _get_scratch_repo(case, tmp_path)
    return scratch_repo / "cortex" / "lifecycle" / "sessions" / session_id


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.log_invocation for the given fixture case.

    Results are memoized within a single tmp_path because three test functions
    (stdout, stderr, exitcode) share the same invocation.  The session dir and
    scratch home are set up fresh each time (tmp_path is unique per test fn).
    """
    cache_key = (str(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    config = _CASE_CONFIG.get(case, {})
    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)

    # Prepare scratch home (breadcrumb writes land here).
    scratch_home = _get_scratch_home(case, tmp_path)
    scratch_home.mkdir(parents=True, exist_ok=True)

    # Prepare scratch repo root with a .git directory so it looks like a git
    # repo to the port's _resolve_repo_root() check.
    scratch_repo = _get_scratch_repo(case, tmp_path)
    scratch_repo.mkdir(parents=True, exist_ok=True)
    if config.get("cwd_git", False):
        (scratch_repo / ".git").mkdir(exist_ok=True)

    # Determine env var values for this case.
    session_id: str | None = config.get("session_id")
    repo_root_valid: bool = config.get("repo_root_valid", False)
    repo_root_str: str | None = str(scratch_repo) if repo_root_valid else None

    # cwd: use scratch_repo when it has a .git, otherwise a bare tmp subdir
    # (no .git present) to simulate the no_repo_root scenario.
    if config.get("cwd_git", False):
        cwd = scratch_repo
    else:
        bare_dir = tmp_path / "bare-cwd"
        bare_dir.mkdir(parents=True, exist_ok=True)
        cwd = bare_dir

    env = _build_env(
        session_id=session_id,
        repo_root=repo_root_str,
        home=str(scratch_home),
    )

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.log_invocation"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )

    _result_cache[cache_key] = result
    return result
