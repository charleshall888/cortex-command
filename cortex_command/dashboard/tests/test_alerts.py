"""Unit tests for cortex_command/dashboard/alerts.py.

Tests cover:
  - evaluate_alerts: stall triggers on >5min inactivity
  - evaluate_alerts: stall clears when activity is recent
  - evaluate_alerts: stall absent when last_activity_ts is None
  - evaluate_alerts: circuit breaker detection from overnight_events
  - evaluate_alerts: deferred detection
  - evaluate_alerts: high-rework detection (>= 2 cycles)
  - evaluate_alerts: high-rework clears when cycles drop below threshold
  - fire_notifications: marks unnotified alerts as notified
  - fire_notifications: does not re-mark when notified == True
  - fire_notifications: circuit breaker notified flag fires once
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cortex_command.dashboard.alerts import evaluate_alerts, fire_notifications
from cortex_command.dashboard.poller import DashboardState


def _make_state(**kwargs) -> DashboardState:
    s = DashboardState()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def _running_feature(slug: str = "feat-a") -> tuple[dict, dict]:
    """Return (overnight, feature_states) for one running feature."""
    overnight = {"features": {slug: {"status": "running"}}}
    feature_states = {slug: {"rework_cycles": 0, "phase_transitions": []}}
    return overnight, feature_states


class TestEvaluateAlerts(unittest.TestCase):
    """Tests for evaluate_alerts synchronous detection logic."""

    def _root_and_lifecycle(self) -> tuple[Path, Path]:
        import tempfile
        tmp = tempfile.mkdtemp()
        root = Path(tmp)
        lifecycle_dir = root / "lifecycle"
        lifecycle_dir.mkdir()
        return root, lifecycle_dir

    def test_stall_added_when_last_activity_over_threshold(self):
        """Stall alert inserted when last activity > 5 minutes ago."""
        overnight, feature_states = _running_feature("feat-a")
        state = _make_state(overnight=overnight, feature_states=feature_states)
        root, lifecycle_dir = self._root_and_lifecycle()

        stale_ts = datetime.now(timezone.utc) - timedelta(minutes=6)
        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=stale_ts):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertIn(("feat-a", "stall"), state.alerts)

    def test_stall_cleared_when_activity_is_recent(self):
        """Stall alert removed when last activity < 5 minutes ago."""
        overnight, feature_states = _running_feature("feat-a")
        state = _make_state(overnight=overnight, feature_states=feature_states)
        state.alerts[("feat-a", "stall")] = {"first_seen": datetime.now(timezone.utc), "notified": False}
        root, lifecycle_dir = self._root_and_lifecycle()

        recent_ts = datetime.now(timezone.utc) - timedelta(minutes=1)
        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=recent_ts):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertNotIn(("feat-a", "stall"), state.alerts)

    def test_stall_absent_when_last_activity_ts_is_none(self):
        """No stall when get_last_activity_ts returns None (no log data)."""
        overnight, feature_states = _running_feature("feat-a")
        state = _make_state(overnight=overnight, feature_states=feature_states)
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertNotIn(("feat-a", "stall"), state.alerts)

    def test_circuit_breaker_detected_from_overnight_events(self):
        """circuit_breaker_active set True when CIRCUIT_BREAKER event found."""
        overnight, feature_states = _running_feature("feat-a")
        state = _make_state(
            overnight=overnight,
            feature_states=feature_states,
            overnight_events=[{"event": "CIRCUIT_BREAKER", "ts": "2026-02-26T10:00:00+00:00"}],
        )
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertTrue(state.circuit_breaker_active)

    def test_circuit_breaker_not_set_without_event(self):
        """circuit_breaker_active remains False when no CIRCUIT_BREAKER event."""
        overnight, feature_states = _running_feature("feat-a")
        state = _make_state(overnight=overnight, feature_states=feature_states, overnight_events=[])
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertFalse(state.circuit_breaker_active)

    def test_deferred_alert_added_for_deferred_feature(self):
        """Deferred alert inserted when feature status is 'deferred'."""
        overnight = {"features": {"feat-a": {"status": "deferred"}}}
        feature_states = {"feat-a": {"rework_cycles": 0}}
        state = _make_state(overnight=overnight, feature_states=feature_states)
        root, lifecycle_dir = self._root_and_lifecycle()

        evaluate_alerts(state, root, lifecycle_dir)

        self.assertIn(("feat-a", "deferred"), state.alerts)

    def test_deferred_alert_cleared_when_status_changes(self):
        """Deferred alert removed when feature is no longer deferred."""
        overnight = {"features": {"feat-a": {"status": "running"}}}
        feature_states = {"feat-a": {"rework_cycles": 0}}
        state = _make_state(overnight=overnight, feature_states=feature_states)
        state.alerts[("feat-a", "deferred")] = {"first_seen": datetime.now(timezone.utc), "notified": True}
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertNotIn(("feat-a", "deferred"), state.alerts)

    def test_high_rework_alert_added_at_threshold(self):
        """high_rework alert inserted when rework_cycles >= 2."""
        overnight = {"features": {"feat-a": {"status": "running"}}}
        feature_states = {"feat-a": {"rework_cycles": 2}}
        state = _make_state(overnight=overnight, feature_states=feature_states)
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertIn(("feat-a", "high_rework"), state.alerts)

    def test_high_rework_not_added_below_threshold(self):
        """high_rework alert absent when rework_cycles < 2."""
        overnight = {"features": {"feat-a": {"status": "running"}}}
        feature_states = {"feat-a": {"rework_cycles": 1}}
        state = _make_state(overnight=overnight, feature_states=feature_states)
        root, lifecycle_dir = self._root_and_lifecycle()

        with patch("cortex_command.dashboard.alerts.get_last_activity_ts", return_value=None):
            evaluate_alerts(state, root, lifecycle_dir)

        self.assertNotIn(("feat-a", "high_rework"), state.alerts)

    def test_no_crash_when_overnight_is_none(self):
        """evaluate_alerts returns cleanly when state.overnight is None."""
        state = _make_state()
        root, lifecycle_dir = self._root_and_lifecycle()
        evaluate_alerts(state, root, lifecycle_dir)  # must not raise


class TestFireNotifications(unittest.IsolatedAsyncioTestCase):
    """Tests for fire_notifications notified-flag bookkeeping.

    The shell-subprocess dispatch path was retired with the shareable-install
    scaffolding; fire_notifications now logs and updates the notified flag
    only. These tests guard the dedup contract.
    """

    async def test_notified_flag_set_to_true_after_fire(self):
        """notified flips to True after fire_notifications runs for a new alert."""
        state = _make_state()
        state.alerts[("feat-a", "stall")] = {
            "first_seen": datetime.now(timezone.utc),
            "notified": False,
        }
        root = Path("/tmp/test-root")

        await fire_notifications(state, root)

        self.assertTrue(state.alerts[("feat-a", "stall")]["notified"])

    async def test_does_not_remark_when_already_notified(self):
        """notified stays True across consecutive fire_notifications calls."""
        state = _make_state()
        state.alerts[("feat-a", "stall")] = {
            "first_seen": datetime.now(timezone.utc),
            "notified": True,
        }
        root = Path("/tmp/test-root")

        await fire_notifications(state, root)

        # Entry remains notified; no mutation expected.
        self.assertTrue(state.alerts[("feat-a", "stall")]["notified"])

    async def test_deferred_alert_notified_flag_set(self):
        """notified flips to True for a deferred alert entry."""
        state = _make_state()
        state.alerts[("feat-a", "deferred")] = {
            "first_seen": datetime.now(timezone.utc),
            "notified": False,
        }
        root = Path("/tmp/test-root")

        await fire_notifications(state, root)

        self.assertTrue(state.alerts[("feat-a", "deferred")]["notified"])

    async def test_circuit_breaker_notified_once(self):
        """circuit_breaker_notified flips True on first call and stays True."""
        state = _make_state()
        state.circuit_breaker_active = True
        state.circuit_breaker_notified = False
        root = Path("/tmp/test-root")

        await fire_notifications(state, root)
        self.assertTrue(state.circuit_breaker_notified)

        # Second call is a no-op for the circuit-breaker flag.
        await fire_notifications(state, root)
        self.assertTrue(state.circuit_breaker_notified)


if __name__ == "__main__":
    unittest.main()
