#!/usr/bin/env python3
"""Tests for lifecycle phase detection against state fixtures.

Iterates over tests/fixtures/state/ subdirectories, calls detect_phase()
from tests/lifecycle_phase.py, and asserts the result matches the directory
name.
"""

import importlib.util
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MODULE_PATH = REPO_ROOT / "tests" / "lifecycle_phase.py"

spec = importlib.util.spec_from_file_location("lifecycle_phase", MODULE_PATH)
lp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lp)


# ---------------------------------------------------------------------------
# Run fixture tests
# ---------------------------------------------------------------------------

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "state"

_fixture_dirs = [d for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir()]


@pytest.mark.parametrize("fixture_dir", _fixture_dirs, ids=[d.name for d in _fixture_dirs])
def test_lifecycle_phase(fixture_dir: Path) -> None:
    expected = fixture_dir.name
    got = lp.detect_phase(fixture_dir)
    assert got == expected
