"""Tests for the runner clearing ``scheduled_start`` on fire (spec R13,
lifecycle task 10).

A scheduled overnight session carries a future ``scheduled_start`` ISO
timestamp in its state file. A read-time "scheduled (dormant)" predicate
(R12) infers a dormant display state from ``scheduled_start`` being in the
future AND no live ``runner.pid``. To keep that predicate from
false-positiving on a run that has already fired (live, completed, or
crashed), the runner clears ``scheduled_start`` to ``None`` as it reaches
its session-start.

This is a plain field write — NOT a phase transition — persisted via the
atomic ``save_state`` (tempfile + ``os.replace``), reading/writing the
explicit per-session state path (NOT the no-arg ``load_state``) so R13
stays decoupled from R19's top-level symlink.

The test drives the runner's real fire-time startup path
(``runner._start_session``), stubbing only the non-subject IPC/interrupt
plumbing, and asserts ``scheduled_start`` is ``None`` in the session state
file after the runner reaches its session-start.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cortex_command.overnight import runner as runner_module
from cortex_command.overnight import state as state_module
from cortex_command.overnight.runner_primitives import RunnerCoordination
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState


def _make_state(session_id: str, scheduled_start: str | None) -> OvernightState:
    return OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feat-a": OvernightFeatureStatus(status="pending")},
        scheduled_start=scheduled_start,
    )


class TestRunnerClearsScheduledStartOnFire(unittest.TestCase):
    """``_start_session`` clears ``scheduled_start`` in the state file."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._session_id = "overnight-2026-06-01-0300"
        self._session_dir = self._tmp / "sessions" / self._session_id
        self._session_dir.mkdir(parents=True)
        self._state_path = self._session_dir / "overnight-state.json"
        self._events_path = self._session_dir / "overnight-events.log"
        # Snapshot LIFECYCLE_SESSION_ID so the test never leaks env state.
        self._prior_lsid = os.environ.get("LIFECYCLE_SESSION_ID")

    def tearDown(self) -> None:
        if self._prior_lsid is None:
            os.environ.pop("LIFECYCLE_SESSION_ID", None)
        else:
            os.environ["LIFECYCLE_SESSION_ID"] = self._prior_lsid
        self._tmpdir.cleanup()

    def _run_start_session(self) -> None:
        """Drive ``_start_session`` with non-subject plumbing stubbed."""
        coord = RunnerCoordination()
        with mock.patch.object(
            runner_module.interrupt, "handle_interrupted_features"
        ), mock.patch.object(
            runner_module, "_check_concurrent_start", return_value=(None, -1)
        ), mock.patch.object(
            runner_module.ipc, "write_runner_pid"
        ), mock.patch.object(
            runner_module.ipc, "write_active_session"
        ), mock.patch.object(
            runner_module.fcntl, "flock"
        ), mock.patch.object(
            runner_module.os, "close"
        ):
            os.environ["LIFECYCLE_SESSION_ID"] = self._session_id
            state, _pid_data, _start_time = runner_module._start_session(
                state_path=self._state_path,
                session_dir=self._session_dir,
                repo_path=self._tmp,
                events_path=self._events_path,
                coord=coord,
            )
        self.assertIsNotNone(state, "fire-time startup returned a None state")

    def test_scheduled_start_cleared_in_state_file_after_fire(self) -> None:
        """A future ``scheduled_start`` is ``None`` in the file post-fire."""
        state_module.save_state(
            _make_state(self._session_id, scheduled_start="2026-12-31T22:00:00"),
            self._state_path,
        )

        self._run_start_session()

        # Read the raw on-disk state file (explicit per-session path) and
        # assert ``scheduled_start`` was cleared by the atomic write.
        raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        self.assertIn(
            "scheduled_start",
            raw,
            "scheduled_start field should still be serialized (as null)",
        )
        self.assertIsNone(
            raw["scheduled_start"],
            "runner must clear scheduled_start to None on fire so the "
            "read-time dormant predicate cannot false-positive on a fired run",
        )
        # Confirm load_state on the explicit path also reflects the clear.
        loaded = state_module.load_state(self._state_path)
        self.assertIsNone(loaded.scheduled_start)

    def test_already_null_scheduled_start_stays_null(self) -> None:
        """A run-now session (no ``scheduled_start``) is unaffected."""
        state_module.save_state(
            _make_state(self._session_id, scheduled_start=None),
            self._state_path,
        )

        self._run_start_session()

        raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        self.assertIsNone(raw["scheduled_start"])


if __name__ == "__main__":
    unittest.main()
