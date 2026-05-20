"""Parity test: cortex_command.parity_check vs bash cortex-check-parity.

Golden-replay fixture test asserting that the Python port produces
byte-identical stdout/stderr/exit-code as the captured pre-deletion bash
original.

Each fixture quintuple in tests/fixtures/cortex-check-parity/ contains:
  <case>.argv      one argv element per line (line 1 is sys.argv[1])
  <case>.stdin     literal bytes to pipe to stdin (empty for all current cases)
  <case>.stdout    captured stdout bytes
  <case>.stderr    captured stderr bytes
  <case>.exitcode  decimal exit status + trailing newline

## Cases

| Case        | Scenario                                            | cwd         | exit |
|-------------|-----------------------------------------------------|-------------|------|
| self_test   | --self-test; all inline self-test cases pass        | repo root   | 0    |
| all_green   | --json; mini-repo with one wired bin script         | mini-repo   | 0    |
| orphan_bin  | --json; mini-repo with one un-wired bin script      | mini-repo   | 1    |

The `self_test` case runs in the real repo root so the plugin-list-matches-
justfile self-test case can locate the justfile. The `all_green` and
`orphan_bin` cases use tmp_path mini-repos whose structure matches what
was set up during fixture capture (see README.md).

## Named-tolerance categories opted in

stdout/stderr surface: ["trailing-newline"]
No structural_equivalence is needed: the JSON output from --json is produced
via Python's json.dumps and is deterministic in key order and whitespace.
"""

from __future__ import annotations

import json
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
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-check-parity"

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
# Per-case cwd configuration
# ---------------------------------------------------------------------------

# Maps case name → callable(tmp_path) -> Path that constructs the cwd.
# self_test runs in the actual repo root (needs justfile for plugin-list check).
# all_green and orphan_bin run in mini-repos built in tmp_path.

def _cwd_self_test(tmp_path: Path) -> Path:
    """self_test runs in the real repo root."""
    return REPO_ROOT


def _cwd_all_green(tmp_path: Path) -> Path:
    """all_green: one wired script in bin/, referenced in CLAUDE.md."""
    # Script name uses a variable to avoid the parity scanner picking up the
    # name as a wired cortex-* reference in *this* Python source file.
    _script = "cortex-" + "foo"
    root = tmp_path / "all_green"
    root.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    script = bin_dir / _script
    script.write_text("#!/usr/bin/env bash\necho foo\n", encoding="utf-8")
    script.chmod(0o755)
    tick = "`"
    (root / "CLAUDE.md").write_text(
        f"# Docs\n\nRun {tick}{_script}{tick} to use it.\n",
        encoding="utf-8",
    )
    return root


def _cwd_orphan_bin(tmp_path: Path) -> Path:
    """orphan_bin: script in bin/ but NOT referenced anywhere (W003)."""
    # Script name uses a variable to avoid the parity scanner picking up the
    # name as a wired cortex-* reference in *this* Python source file.
    _script = "cortex-" + "bar"
    root = tmp_path / "orphan_bin"
    root.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    script = bin_dir / _script
    script.write_text("#!/usr/bin/env bash\necho bar\n", encoding="utf-8")
    script.chmod(0o755)
    (root / "CLAUDE.md").write_text(
        "# Docs\n\nNothing relevant here.\n",
        encoding="utf-8",
    )
    return root


def _cwd_wired_allowlisted(tmp_path: Path) -> Path:
    """wired_allowlisted: script is referenced in CLAUDE.md AND in
    .parity-exceptions.md, triggering W005 allowlist-superfluous."""
    # Script name uses a variable to avoid the parity scanner picking up the
    # name as a wired cortex-* reference in *this* Python source file.
    _script = "cortex-" + "baz"
    root = tmp_path / "wired_allowlisted"
    root.mkdir()
    bin_dir = root / "bin"
    bin_dir.mkdir()
    script = bin_dir / _script
    script.write_text("#!/usr/bin/env bash\necho baz\n", encoding="utf-8")
    script.chmod(0o755)
    tick = "`"
    (root / "CLAUDE.md").write_text(
        f"# Docs\n\nRun {tick}{_script}{tick} to use it.\n",
        encoding="utf-8",
    )
    # .parity-exceptions.md allowlists the script even though it is wired.
    (bin_dir / ".parity-exceptions.md").write_text(
        "# Parity Exceptions\n\n"
        "| script | category | rationale | lifecycle_id | added_date |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| {tick}{_script}{tick} | {tick}maintainer-only-tool{tick} | "
        "This script is allowlisted even though it has a wiring signal for "
        f"testing W005 behavior. | {tick}test-123{tick} | {tick}2026-01-01{tick} |\n",
        encoding="utf-8",
    )
    return root


_CASE_CWD: dict[str, object] = {
    "self_test": _cwd_self_test,
    "all_green": _cwd_all_green,
    "orphan_bin": _cwd_orphan_bin,
    "wired_allowlisted": _cwd_wired_allowlisted,
}


# ---------------------------------------------------------------------------
# Invocation helper
# ---------------------------------------------------------------------------


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run python3 -m cortex_command.parity_check for the given fixture case.

    Each test function gets its own tmp_path from pytest. The mini-repo for
    cwd-dependent cases is created under tmp_path / case. This function is
    called once per test function; no cross-function caching is used to avoid
    id-reuse hazards with pytest's tmp_path fixture.
    """
    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)

    cwd_factory = _CASE_CWD.get(case)
    if cwd_factory is None:
        pytest.skip(f"no cwd configuration for case {case!r}")
    cwd = cwd_factory(tmp_path)  # type: ignore[call-arg]

    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    # Prepend the repo root to PYTHONPATH so the subprocess always sees
    # the working-tree cortex_command package, not a stale installed version.
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{REPO_ROOT}:{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = str(REPO_ROOT)

    return subprocess.run(
        [sys.executable, "-m", "cortex_command.parity_check"] + argv,
        input=stdin_bytes,
        capture_output=True,
        cwd=str(cwd),
        env=env,
    )


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is byte-identical to the fixture capture.

    For JSON-producing cases (--json), the output is deterministic:
    Python's json.dumps produces consistent key order and whitespace.
    For self_test, the output is the fixed string 'self-test passed\\n'.
    """
    expected_stdout = _read_expected_stdout(case)
    result = _invoke_case(case, tmp_path)
    assert_byte_identical(result.stdout, expected_stdout)


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture (empty for all cases)."""
    expected_stderr = _read_expected_stderr(case)
    result = _invoke_case(case, tmp_path)
    assert_byte_identical(result.stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
