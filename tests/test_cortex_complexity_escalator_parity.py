"""Parity test: cortex_command.lifecycle.complexity_escalator vs captured fixtures.

Golden-replay fixture test that asserts the Python port produces byte-identical
stdout/stderr/exit-code as the captured outputs stored under
``tests/fixtures/cortex-complexity-escalator/``.

Each fixture case consists of:
  <case>.argv         one argument per line (feature slug on line 1, then
                      flag lines for --gate)
  <case>.stdin        literal bytes to pipe to stdin (empty for all cases)
  <case>.stdout       expected stdout bytes
  <case>.stderr       expected stderr bytes
  <case>.exitcode     decimal exit status + trailing newline
  <case>.research_md  (optional) content to place in research.md for the case
  <case>.spec_md      (optional) content to place in spec.md for the case
  <case>.events_log   (optional) pre-existing events.log content

The test injects ``--lifecycle-dir`` dynamically: it creates a scratch
lifecycle directory, places the sidecar input files (research_md, events_log,
etc.) in the appropriate feature subdirectory, then runs the module.

Fixture cases:

  gate1_fires        Gate 1 (research_open_questions) threshold met — 2 bullets
                     in ``## Open Questions``; ``complexity_override`` event is
                     emitted; stdout contains the escalation announcement; exit 0.

  gate1_no_fire      Gate 1 threshold NOT met — 1 bullet in ``## Open Questions``
                     (threshold is 2); no event emitted; empty stdout; exit 0.

  already_complex    Feature has a pre-existing ``complexity_override`` event in
                     events.log (tier guard fires); no second event emitted;
                     empty stdout; exit 0. Exercises the ambiguous-tier path
                     where the artifact has enough bullets to escalate but the
                     tier guard prevents re-emission.

Named-tolerance categories for this fixture set:

  stdout: byte-identical by default (the escalation message is deterministic).
  stderr: byte-identical by default (empty for all cases).
  exit-code: byte-identical (always 0 for these fixture paths).

No named tolerances are opted in: the stdout message is a plain string
(not JSON), timestamps are not present in stdout/stderr, and there are no
jq-vs-Python serialization differences to absorb.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.test_parity_contract import assert_byte_identical


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "cortex-complexity-escalator"

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
    directory name is taken from the first line of the ``.argv`` file.
    Sidecar files (``<case>.research_md``, ``<case>.spec_md``,
    ``<case>.events_log``) are copied into the feature directory with their
    canonical names (``research.md``, ``spec.md``, ``events.log``).
    """
    argv = _read_argv(case)
    # First positional arg is the feature slug.
    feature = argv[0] if argv else "test-feature"

    lifecycle_dir = base / "cortex" / "lifecycle"
    feature_dir = lifecycle_dir / feature
    feature_dir.mkdir(parents=True, exist_ok=True)

    # Sidecar: research.md
    research_sidecar = FIXTURE_DIR / f"{case}.research_md"
    if research_sidecar.exists():
        (feature_dir / "research.md").write_bytes(research_sidecar.read_bytes())

    # Sidecar: spec.md
    spec_sidecar = FIXTURE_DIR / f"{case}.spec_md"
    if spec_sidecar.exists():
        (feature_dir / "spec.md").write_bytes(spec_sidecar.read_bytes())

    # Sidecar: events.log
    events_sidecar = FIXTURE_DIR / f"{case}.events_log"
    if events_sidecar.exists():
        (feature_dir / "events.log").write_bytes(events_sidecar.read_bytes())

    return lifecycle_dir


# ---------------------------------------------------------------------------
# Invocation helper (cached per case+tmp_path)
# ---------------------------------------------------------------------------

_result_cache: dict[tuple[str, str], subprocess.CompletedProcess] = {}


def _invoke_case(case: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the Python module against the given fixture case.

    Sets up a scratch lifecycle directory under ``tmp_path``, injects
    ``--lifecycle-dir`` into the argv, and runs via
    ``python3 -m cortex_command.lifecycle.complexity_escalator``.

    Results are memoized within a single tmp_path (pytest provides a unique
    tmp_path per test function; three test functions share the same invocation
    result).
    """
    cache_key = (str(tmp_path), case)
    if cache_key in _result_cache:
        return _result_cache[cache_key]

    argv = _read_argv(case)
    stdin_bytes = _read_stdin(case)
    lifecycle_dir = _setup_lifecycle_dir(case, tmp_path)

    env = dict(os.environ)
    env.update(_DETERMINISM_ENV_OVERRIDES)

    result = subprocess.run(
        [sys.executable, "-m", "cortex_command.lifecycle.complexity_escalator"]
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


@pytest.mark.parametrize("case", _discover_cases())
def test_stdout_parity(case: str, tmp_path: Path) -> None:
    """stdout is byte-identical to the fixture capture."""
    expected_stdout = _read_expected_stdout(case)
    actual_stdout = _invoke_case(case, tmp_path).stdout
    assert_byte_identical(actual_stdout, expected_stdout)


@pytest.mark.parametrize("case", _discover_cases())
def test_stderr_parity(case: str, tmp_path: Path) -> None:
    """stderr is byte-identical to the fixture capture (empty for all current cases)."""
    expected_stderr = _read_expected_stderr(case)
    actual_stderr = _invoke_case(case, tmp_path).stderr
    assert_byte_identical(actual_stderr, expected_stderr)


@pytest.mark.parametrize("case", _discover_cases())
def test_exitcode_parity(case: str, tmp_path: Path) -> None:
    """Exit code matches the fixture capture."""
    expected_exitcode = _read_expected_exitcode(case)
    result = _invoke_case(case, tmp_path)
    assert result.returncode == expected_exitcode, (
        f"exit code mismatch for {case!r}: "
        f"got {result.returncode}, expected {expected_exitcode}"
    )
