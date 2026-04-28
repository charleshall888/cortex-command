"""End-to-end tests for ``bin/cortex-check-parity`` driven by mini-repo fixtures.

Each subdirectory of ``tests/fixtures/parity/`` is a self-contained mini-repo
exercising one wiring/violation scenario. The linter is invoked with that
directory as ``cwd`` (it operates on ``os.getcwd()``) and its JSON output is
asserted against expectations keyed on the fixture name's prefix:

  - ``valid-*`` → exit 0, JSON is an empty array.
  - ``invalid-*`` → exit 1, JSON contains the codes listed in
    ``expected.json`` (a JSON array of expected violation codes, e.g.
    ``["E001", "E001"]``).
  - ``exclude-*`` → exit 0, JSON is an empty array (proves R5 exclusions).

Tasks 5 and 6 add ``invalid-*`` and ``exclude-*`` fixtures into the same
directory using this harness without modification.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "cortex-check-parity"
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "parity"


def _fixture_dirs() -> list[Path]:
    if not FIXTURES_ROOT.is_dir():
        return []
    return sorted(p for p in FIXTURES_ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize(
    "fixture",
    _fixture_dirs(),
    ids=lambda p: p.name,
)
def test_parity_fixture(fixture: Path) -> None:
    """Run the linter against ``fixture`` and assert outcome by prefix."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json"],
        cwd=str(fixture),
        capture_output=True,
        text=True,
    )

    name = fixture.name
    stdout = result.stdout.strip()
    # The linter emits a single JSON array on stdout when --json is set.
    try:
        violations = json.loads(stdout) if stdout else []
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic aid
        pytest.fail(
            f"{name}: linter stdout is not JSON: {exc}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    if name.startswith("valid-") or name.startswith("exclude-"):
        assert result.returncode == 0, (
            f"{name}: expected exit 0, got {result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert violations == [], (
            f"{name}: expected empty violation array, got {violations}"
        )
        return

    if name.startswith("invalid-"):
        assert result.returncode == 1, (
            f"{name}: expected exit 1, got {result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        expected_path = fixture / "expected.json"
        assert expected_path.is_file(), (
            f"{name}: invalid-* fixtures must include expected.json "
            f"(JSON array of expected violation codes)"
        )
        expected_codes = json.loads(expected_path.read_text(encoding="utf-8"))
        actual_codes = sorted(v["code"] for v in violations)
        assert actual_codes == sorted(expected_codes), (
            f"{name}: violation codes mismatch\n"
            f"expected={sorted(expected_codes)}\nactual={actual_codes}\n"
            f"violations={violations}"
        )
        return

    pytest.fail(
        f"{name}: unrecognized fixture-name prefix; "
        f"expected one of valid-*, invalid-*, exclude-*"
    )
