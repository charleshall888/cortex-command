"""Tests for runner.sh resume behavior: count_pending() includes paused features.

Uses subprocess to run the Python snippet from count_pending() against
controlled state files, plus a structural assertion that verifies runner.sh
itself contains 'paused' in the count_pending function body.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REAL_REPO_ROOT = Path(__file__).resolve().parent.parent

# The Python snippet extracted from count_pending() in runner.sh
_COUNT_PENDING_SNIPPET = """
import json, os
state = json.load(open(os.environ['STATE_PATH']))
features = state.get('features', {})
count = sum(1 for f in features.values() if f.get('status') in ('pending', 'running', 'paused'))
print(count)
"""

_ISO_NOW = "2026-04-07T00:00:00+00:00"


def _write_state(tmp_path: Path, features: dict) -> Path:
    state_path = tmp_path / "overnight-state.json"
    state = {
        "session_id": "t",
        "plan_ref": "",
        "current_round": 1,
        "phase": "executing",
        "started_at": _ISO_NOW,
        "updated_at": _ISO_NOW,
        "features": features,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def test_count_pending_includes_paused(tmp_path: Path) -> None:
    """count_pending() returns non-zero when only paused features remain."""
    state_path = _write_state(tmp_path, {"feat": {"status": "paused"}})
    env = {**os.environ, "STATE_PATH": str(state_path)}
    result = subprocess.run(
        ["python3", "-c", _COUNT_PENDING_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 1


def test_count_pending_zero_for_merged(tmp_path: Path) -> None:
    """count_pending() returns 0 when all features are merged."""
    state_path = _write_state(tmp_path, {"feat": {"status": "merged"}})
    env = {**os.environ, "STATE_PATH": str(state_path)}
    result = subprocess.run(
        ["python3", "-c", _COUNT_PENDING_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) == 0


def test_runner_sh_count_pending_contains_paused() -> None:
    """Structural assertion: runner.sh count_pending() body includes 'paused'.

    This guards against the test logic passing while the production code was
    not actually updated — without this check, the snippet tests above would
    validate only the test author's Python, not the live runner.sh.
    """
    result = subprocess.run(
        ["bash", "-c", "grep -A10 'count_pending()' cortex_command/overnight/runner.sh | grep -c 'paused'"],
        capture_output=True,
        text=True,
        cwd=str(REAL_REPO_ROOT),
    )
    count = int(result.stdout.strip())
    assert count >= 1, (
        "runner.sh count_pending() function body does not contain 'paused' — "
        "the production fix may not have been applied"
    )
