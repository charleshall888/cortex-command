"""Parity test: cortex_command.lifecycle.counters vs captured fixtures.

Golden-replay fixture test that asserts the Python port of
``bin/cortex-lifecycle-counters`` produces byte-identical (modulo key-reorder
tolerance) stdout/stderr/exit-code as the outputs stored under
``tests/fixtures/cortex-lifecycle-counters/``.

Each fixture case consists of:
  <case>.argv        one argument per line (argv[1] of the script on line 1)
  <case>.stdin       literal bytes to pipe to stdin (empty for all cases)
  <case>.stdout      expected stdout bytes
  <case>.stderr      expected stderr bytes
  <case>.exitcode    decimal exit status + trailing newline
  <case>.plan_md     (optional) content to place in plan.md
  <case>.review_md   (optional) content to place in review.md
  <case>.events_log  (optional) content to place in events.log (ignored by counters)

The test injects ``--lifecycle-dir`` dynamically: it creates a scratch
lifecycle directory, places the sidecar input files in the appropriate feature
subdirectory, then runs the module via ``python3 -m cortex_command.lifecycle.counters``.

Fixture cases:

  zero-lifecycle        No plan.md or review.md; all three counters default to 0.

  multiple-phases       plan.md with 5 tasks (3 checked, 2 pending) and review.md
                        with 2 verdict entries; exercises all three counter fields.

  malformed-events-log  plan.md with 2 tasks (1 checked), no review.md, and a
                        malformed events.log line (ignored by counters); verifies
                        that the Python port does not read events.log.

Named-tolerance categories for this fixture set:

  stdout: ``key-reorder`` — jq emits keys in insertion order; Python dict and
          json.dumps also preserve insertion order, but the tolerance is declared
          defensively to absorb any future Python version behavioural drift.
  stderr: byte-identical (empty for all cases).
  exit-code: byte-identical (always 0 for these fixture paths).
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
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-lifecycle-counters"

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
    return (FIXTURE_DIR / f"{case}.stdin").read_bytes()


def _read_expected_stdout(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stdout").read_bytes()


def _read_expected_stderr(case: str) -> bytes:
    return (FIXTURE_DIR / f"{case}.stderr").read_bytes()


def _read_expected_exitcode(case: str) -> int:
    text = (FIXTURE_DIR / f"{case}.exitcode").read_text(encoding="utf-8").strip()
    return int(text)


# ---------------------------------------------------------------------------
# Scratch lifecycle directory setup
# ---------------------------------------------------------------------------


def _setup_lifecycle_dir(case: str, base: Path) -> Path:
    """Create a scratch lifecycle dir for this case and populate it.

    Returns the lifecycle dir path (``base/cortex/lifecycle``). The feature
    directory name is taken from the ``--feature`` argument in the ``.argv``
    file. Sidecar files (``<case>.plan_md``, ``<case>.review_md``,
    ``<case>.events_log``) are copied into the feature directory with their
    canonical names (``plan.md``, ``review.md``, ``events.log``).
    """
    argv = _read_argv(case)
    # Find --feature value: it follows the --feature flag in argv.
    feature = "test-feature"
    for i, arg in enumerate(argv):
        if arg == "--feature" and i + 1 < len(argv):
            feature = argv[i + 1]
            break

    lifecycle_dir = base / "cortex" / "lifecycle"
    feature_dir = lifecycle_dir / feature
    feature_dir.mkdir(parents=True, exist_ok=True)

    # Sidecar: plan.md
    plan_sidecar = FIXTURE_DIR / f"{case}.plan_md"
    if plan_sidecar.exists():
        (feature_dir / "plan.md").write_bytes(plan_sidecar.read_bytes())

    # Sidecar: review.md
    review_sidecar = FIXTURE_DIR / f"{case}.review_md"
    if review_sidecar.exists():
        (feature_dir / "review.md").write_bytes(review_sidecar.read_bytes())

    # Sidecar: events.log (present in malformed-events-log to verify it is ignored)
    events_sidecar = FIXTURE_DIR / f"{case}.events_log"
    if events_sidecar.exists():
        (feature_dir / "events.log").write_bytes(events_sidecar.read_bytes())

    return lifecycle_dir


# ---------------------------------------------------------------------------
# Invocation helper (cached per case+tmp_path)
# ---------------------------------------------------------------------------

_result_cache: dict[tuple, subprocess.CompletedProcess] = {}


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the Python module against the given fixture case.

    Sets up a scratch lifecycle directory under ``tmp_path``, injects
    ``--lifecycle-dir`` into the argv, and runs via
    ``python3 -m cortex_command.lifecycle.counters``.

    Results are memoized within a single tmp_path (pytest provides a unique
    tmp_path per test function; three test functions share the same invocation
    result for a given case).
    """
    cache_key = (id(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    lifecycle_dir = _setup_lifecycle_dir(case, tmp_path)

    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)
    # Keep telemetry side-effect out of the parity comparison.
    env.pop("LIFECYCLE_SESSION_ID", None)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.counters"]
        + argv
        + ["--lifecycle-dir", str(lifecycle_dir)],
        input=stdin_bytes,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    _result_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------


@pytest.mark.structural_equivalence(stream="stdout", tolerances=["key-reorder"])
@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is structurally equivalent to the fixture capture (key-reorder tolerance)."""
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case, tmp_path).stdout
    assert_structurally_equivalent(
        actual_stdout,
        expected_stdout,
        stream="stdout",
        tolerances=["key-reorder"],
    )


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture (empty for all cases)."""
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case, tmp_path).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture (always 0 for these fixture paths)."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )
