"""Unit tests for _map_results_to_state() terminal-status guards.

Verifies that features already at a terminal status (merged, failed, deferred)
are not overwritten by paused/deferred/failed result entries, and that a
successful retry (failed -> merged) still updates status correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.map_results import _map_results_to_state


_ISO_NOW = "2026-04-07T00:00:00+00:00"


def _write_state(tmp_path: Path, initial_status: str) -> Path:
    state_path = tmp_path / "overnight-state.json"
    state = {
        "session_id": "t",
        "plan_ref": "",
        "current_round": 1,
        "phase": "executing",
        "started_at": _ISO_NOW,
        "updated_at": _ISO_NOW,
        "features": {"feat": {"status": initial_status}},
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def test_paused_result_does_not_overwrite_merged(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path, "merged")
    results = {"features_paused": [{"name": "feat", "error": None}]}
    _map_results_to_state(results, state_path, batch_id=1)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["features"]["feat"]["status"] == "merged"


def test_failed_result_does_not_overwrite_merged(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path, "merged")
    results = {"features_failed": [{"name": "feat", "error": "some error"}]}
    _map_results_to_state(results, state_path, batch_id=1)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["features"]["feat"]["status"] == "merged"


def test_deferred_result_does_not_overwrite_merged(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path, "merged")
    results = {"features_deferred": [{"name": "feat", "question_count": 1}]}
    _map_results_to_state(results, state_path, batch_id=1)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["features"]["feat"]["status"] == "merged"


def test_merged_result_overwrites_failed(tmp_path: Path) -> None:
    """Retry success: failed -> merged must still work (features_merged is unguarded)."""
    state_path = _write_state(tmp_path, "failed")
    results = {"features_merged": ["feat"]}
    _map_results_to_state(results, state_path, batch_id=1)
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["features"]["feat"]["status"] == "merged"
