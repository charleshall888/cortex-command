"""Unit tests for compute_eligible_features — R10 convergence semantics.

Covers:
- Test A: owner-acquires-mid-overnight
    Round N includes X in eligible (scan returns empty); round N+1 excludes X
    (scan returns {"X"}) and produces a skip-event with the expected shape.
- Test B: owner-exits-mid-overnight (mirror of A)
    Round N excludes X (scan returns {"X"}); round N+1 re-includes X
    (scan returns empty, no skip-events).

Mock target: ``cortex_command.interactive_lock.scan_live_locks`` via
``monkeypatch.setattr``.

Synthetic lock-data fixture: a real lock file is written under
``tmp_path / "cortex/lifecycle/X/interactive.pid"`` so that
``compute_eligible_features`` can do its ``read_lock("X")`` call and
populate ``interactive_session_id`` / ``interactive_acquired_at`` in the
skip-event payload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.orchestrator import compute_eligible_features


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LOCK_MAGIC = "cortex-interactive-lock"
_ACQUIRED_AT = "2024-06-01T12:00:00+00:00"
_SESSION_ID = "test-session-abc123"


def _write_lock_file(tmp_path: Path, feature: str) -> Path:
    """Write a synthetic interactive.pid lock file for *feature* under tmp_path.

    Path: ``tmp_path/cortex/lifecycle/{feature}/interactive.pid``.
    Uses a real PID (os.getpid()) with no start_time so the live-check path
    does not matter — the mocked scan_live_locks decides liveness, not the
    real file content.  The lock fields used by the skip-event payload
    (``session_id`` and ``acquired_at``) are set to known test values.
    """
    import os

    lock_dir = tmp_path / "cortex" / "lifecycle" / feature
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "interactive.pid"
    payload = {
        "schema_version": 1,
        "magic": _LOCK_MAGIC,
        "session_id": _SESSION_ID,
        "pid": os.getpid(),
        "start_time": None,
        "acquired_at": _ACQUIRED_AT,
    }
    lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return lock_path


def _make_scan_side_effect(*successive_sets: set[str]):
    """Return a callable that returns each set in sequence on successive calls."""
    calls = list(successive_sets)
    idx = {"n": 0}

    def _scan(_project_root: Path) -> set[str]:
        result = calls[idx["n"]]
        if idx["n"] < len(calls) - 1:
            idx["n"] += 1
        return result

    return _scan


# ---------------------------------------------------------------------------
# Test A: owner-acquires-mid-overnight
#
# Round N: scan returns {} → X is eligible (no skip-events).
# Round N+1: scan returns {"X"} → X is excluded; skip-event is emitted.
# ---------------------------------------------------------------------------

def test_owner_acquires_mid_overnight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R10 convergence: feature excluded at round N+1 when interactive owner appears.

    Simulates an owner that acquires the interactive lock between round N and
    round N+1.  Round N should see X as eligible; round N+1 should exclude X
    with a correctly-shaped skip-event.
    """
    feature = "X"
    other = "Y"
    _write_lock_file(tmp_path, feature)

    # Route read_lock to tmp_path rather than the real project root.
    # compute_eligible_features reads the lock file via a path derived from
    # project_root, so we pass tmp_path as project_root — no monkeypatching
    # of read_lock itself is needed.

    # Two successive scans: first empty (round N), then {"X"} (round N+1).
    side_effect = _make_scan_side_effect(set(), {feature})

    import cortex_command.interactive_lock as il
    monkeypatch.setattr(il, "scan_live_locks", side_effect)

    # Round N — no live owners yet
    eligible_n, skip_events_n = compute_eligible_features(
        [feature, other], tmp_path
    )

    assert feature in eligible_n, "round N: X should be eligible when no live owner"
    assert other in eligible_n, "round N: Y should be eligible"
    assert skip_events_n == [], "round N: no skip-events expected"

    # Round N+1 — X now has a live owner
    eligible_n1, skip_events_n1 = compute_eligible_features(
        [feature, other], tmp_path
    )

    assert feature not in eligible_n1, "round N+1: X should be excluded"
    assert other in eligible_n1, "round N+1: Y still eligible"
    assert len(skip_events_n1) == 1, "round N+1: exactly one skip-event"

    evt = skip_events_n1[0]
    assert evt["event"] == "feature_skipped_interactive_active"
    assert evt["feature"] == feature
    assert "live interactive owner" in evt["rationale"], (
        "rationale should mention 'live interactive owner'"
    )
    # Lock payload fields populated from the synthetic lock file
    assert evt["interactive_session_id"] == _SESSION_ID
    assert evt["interactive_acquired_at"] == _ACQUIRED_AT


# ---------------------------------------------------------------------------
# Test B: owner-exits-mid-overnight (mirror of A)
#
# Round N: scan returns {"X"} → X is excluded; skip-event emitted.
# Round N+1: scan returns {} → X is re-included; no skip-events.
# ---------------------------------------------------------------------------

def test_owner_exits_mid_overnight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R10 convergence: feature re-included at round N+1 when interactive owner exits.

    Simulates an owner that releases the interactive lock between round N and
    round N+1.  Round N should exclude X with a skip-event; round N+1 should
    re-include X with no skip-events.
    """
    feature = "X"
    other = "Y"
    _write_lock_file(tmp_path, feature)

    # Two successive scans: first {"X"} (round N), then empty (round N+1).
    side_effect = _make_scan_side_effect({feature}, set())

    import cortex_command.interactive_lock as il
    monkeypatch.setattr(il, "scan_live_locks", side_effect)

    # Round N — X has a live owner
    eligible_n, skip_events_n = compute_eligible_features(
        [feature, other], tmp_path
    )

    assert feature not in eligible_n, "round N: X should be excluded"
    assert other in eligible_n, "round N: Y should be eligible"
    assert len(skip_events_n) == 1, "round N: exactly one skip-event for X"

    evt_n = skip_events_n[0]
    assert evt_n["event"] == "feature_skipped_interactive_active"
    assert evt_n["feature"] == feature
    assert evt_n["interactive_session_id"] == _SESSION_ID
    assert evt_n["interactive_acquired_at"] == _ACQUIRED_AT

    # Round N+1 — owner has exited; X re-included
    eligible_n1, skip_events_n1 = compute_eligible_features(
        [feature, other], tmp_path
    )

    assert feature in eligible_n1, "round N+1: X should be re-included after owner exits"
    assert other in eligible_n1, "round N+1: Y still eligible"
    assert skip_events_n1 == [], "round N+1: no skip-events after owner releases lock"
