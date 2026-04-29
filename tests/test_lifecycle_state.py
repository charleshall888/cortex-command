#!/usr/bin/env python3
"""Tests for lifecycle phase detection against state fixtures.

Iterates over tests/fixtures/state/ subdirectories, calls
detect_lifecycle_phase() from cortex_command.common, and asserts the
phase field of the returned dict matches the directory name.
"""

import pytest
from pathlib import Path

from cortex_command.common import detect_lifecycle_phase


# ---------------------------------------------------------------------------
# Run fixture tests
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "state"

_fixture_dirs = [d for d in sorted(FIXTURES_DIR.iterdir()) if d.is_dir()]


@pytest.mark.parametrize("fixture_dir", _fixture_dirs, ids=[d.name for d in _fixture_dirs])
def test_lifecycle_phase(fixture_dir: Path) -> None:
    expected = fixture_dir.name
    result = detect_lifecycle_phase(fixture_dir)
    assert result["phase"] == expected
