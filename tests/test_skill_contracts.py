#!/usr/bin/env python3
"""Fixture assertion runner for skill contract validation.

Iterates over tests/fixtures/contracts/ subdirectories, runs
validate-skill.py against each, and asserts the expected outcome based on
directory name prefix:
  valid-*   -> validate-skill.py must exit 0
  invalid-* -> must exit 1 OR output must contain a [WARN] line with the
               expected keyword (for warn-class invalids; see WARN_KEYWORDS)
"""

import subprocess
import sys
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "contracts"
VALIDATOR = REPO_ROOT / "scripts" / "validate-skill.py"

if not VALIDATOR.exists():
    pytest.skip("validate-skill.py not found — skill-creator scripts not present", allow_module_level=True)

# For invalid-* fixtures that exit 0 but should produce a specific [WARN],
# map fixture name -> expected substring in output.
WARN_KEYWORDS = {
    "invalid-undeclared-variable": "undeclared",
}

_fixture_dirs = [d for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir()]


@pytest.mark.parametrize("fixture_dir", _fixture_dirs, ids=[d.name for d in _fixture_dirs])
def test_skill_contract(fixture_dir: Path) -> None:
    name = fixture_dir.name

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(fixture_dir)],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    exit_code = result.returncode

    if name.startswith("valid-"):
        if exit_code != 0:
            pytest.fail(f"expected exit 0, got {exit_code}\n       output: {output.strip()}")

    elif name.startswith("invalid-"):
        if exit_code == 1:
            return
        elif name in WARN_KEYWORDS and WARN_KEYWORDS[name] in output:
            return
        else:
            pytest.fail(
                f"expected exit 1 or [WARN] containing "
                f"'{WARN_KEYWORDS.get(name, '(none)')}', got exit {exit_code}\n"
                f"       output: {output.strip()}"
            )

    else:
        pytest.fail(f"unknown prefix — must be valid-* or invalid-*")
