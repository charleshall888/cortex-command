"""Tests for fire-time ``session_start`` authorship (spec R11, lifecycle
task 9).

The ``/overnight`` flow used to log ``session_start`` unconditionally at
prep time (``new-session-flow.md`` step 5 / ``SKILL.md`` step 7.5), BEFORE
the run-now/schedule branch. On the schedule branch the fire happens hours
later, so the prep log landed early — and because ``LIFECYCLE_SESSION_ID``
is unset in the prep context, it was tagged ``session_id:"manual"``. The
runner then re-logged the real ``session_start`` at fire, producing a
duplicate.

This task gates the prep-time log to the run-now branch only and makes the
runner the sole fire-time author of exactly one ``session_start`` (with the
real session id) on the schedule path.

Two checkable halves, mirroring the spec's R11 acceptance:

  TestSkillFlowGating
      (a) The skill-flow prose gates the step-5 prep-time ``session_start``
      log to the run-now branch only — the schedule branch reaches the
      launch without it. Asserted against ``new-session-flow.md``, the sole
      file carrying the launch sub-steps (SKILL.md's New Session Flow
      section is a pointer into it, not a duplicate step list, so it's
      asserted only to confirm it doesn't reintroduce an unconditional
      ``session_start`` call). Canonical ``skills/overnight/`` files; the
      plugin mirror is byte-identical via ``just build-plugin``.

  TestRunnerSessionStartSingle
      (b) After a (simulated) fire, the session's ``events.log`` contains
      exactly one ``session_start`` whose ``session_id`` is the real session
      id (not ``manual``). Drives the runner's real fire-time logging path
      (``runner._start_session``) with ``LIFECYCLE_SESSION_ID`` exported as
      ``runner.run`` does, stubbing only the non-subject IPC/interrupt
      plumbing.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cortex_command.overnight import events as events_module
from cortex_command.overnight import runner as runner_module
from cortex_command.overnight import state as state_module
from cortex_command.overnight.runner_primitives import RunnerCoordination
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState


# ---------------------------------------------------------------------------
# Repo-root resolution for the skill-flow prose assertions.
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Walk up from this file to the repository root (contains ``skills/``)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skills" / "overnight" / "SKILL.md").is_file():
            return parent
    raise RuntimeError("could not locate repo root from test file location")


# ---------------------------------------------------------------------------
# Half (a): skill-flow gating
# ---------------------------------------------------------------------------


class TestSkillFlowGating(unittest.TestCase):
    """The prep-time ``session_start`` log is gated to the run-now branch."""

    def setUp(self) -> None:
        root = _repo_root()
        self._flow = (
            root / "skills" / "overnight" / "references" / "new-session-flow.md"
        ).read_text(encoding="utf-8")
        self._skill = (
            root / "skills" / "overnight" / "SKILL.md"
        ).read_text(encoding="utf-8")

    def _step5_block(self) -> str:
        """Return the step-5 block text from ``new-session-flow.md``."""
        # Step 5 starts at the numbered "5." heading and runs up to the
        # step-6 heading.
        m = re.search(
            r"\n5\.\s.*?(?=\n6\.\s)", self._flow, flags=re.DOTALL
        )
        self.assertIsNotNone(m, "could not locate step-5 block in new-session-flow.md")
        return m.group(0)

    def _runnow_block(self) -> str:
        """Return the run-now (option 1) block text from ``new-session-flow.md``."""
        m = re.search(
            r"\*\*Run now \(option 1\)\*\*.*?(?=\*\*Schedule for specific time)",
            self._flow,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(m, "could not locate run-now block in new-session-flow.md")
        return m.group(0)

    def _schedule_block(self) -> str:
        """Return the schedule (option 2) block from ``new-session-flow.md``."""
        m = re.search(
            r"\*\*Schedule for specific time \(option 2\)\*\*.*?(?=\n8\.\s)",
            self._flow,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(m, "could not locate schedule block in new-session-flow.md")
        return m.group(0)

    def test_step5_does_not_invoke_prep_session_start_log(self) -> None:
        """Step 5 no longer issues the prep-time ``session_start`` log call.

        The step-5 block must not contain a ``log_event(... 'session_start')``
        invocation directive — it is deferred to the run-now branch.
        """
        block = self._step5_block()
        # No active "log_event(...session_start...)" call directive remains in
        # step 5. The block may *mention* session_start while explaining the
        # deferral, but must not pair it with a log_event call.
        self.assertNotRegex(
            block,
            r"Call `log_event\(\)`[^\n]*session_start",
            "step 5 still issues a prep-time session_start log; it must be "
            "gated to the run-now branch",
        )
        # And it must explicitly defer / gate the log to the run-now branch.
        self.assertRegex(
            block.lower(),
            r"run-now|run now",
            "step 5 must reference the run-now branch as the gated location",
        )

    def test_runnow_branch_invokes_prep_session_start_log(self) -> None:
        """The run-now branch carries the gated prep-time ``session_start`` log."""
        block = self._runnow_block()
        self.assertRegex(
            block,
            r"log_event\(\)`?[^\n]*session_start|session_start[^\n]*log_event",
            "run-now branch must issue the gated prep-time session_start log",
        )

    def test_schedule_branch_has_no_prep_session_start_log(self) -> None:
        """The schedule branch reaches the launch WITHOUT pre-logging."""
        block = self._schedule_block()
        self.assertNotRegex(
            block,
            r"log_event\([^\n]*session_start",
            "schedule branch must not pre-log session_start; the runner is "
            "the sole fire-time author",
        )

    def test_skill_new_session_flow_does_not_duplicate_prep_session_start_log(
        self,
    ) -> None:
        """SKILL.md's New Session Flow section must not reintroduce the bug.

        The launch sub-steps (formerly duplicated in SKILL.md as 7.1-7.8)
        now live solely in new-session-flow.md, which the section above
        asserts is gated correctly. This guards against a regression where
        SKILL.md's pointer text grows back into a step list carrying its own
        unconditional ``session_start`` log call.
        """
        m = re.search(r"## New Session Flow.*?(?=\n## )", self._skill, flags=re.DOTALL)
        self.assertIsNotNone(
            m, "could not locate New Session Flow section in SKILL.md"
        )
        section = m.group(0)
        self.assertNotRegex(
            section,
            r"log_event\([^\n]*session_start",
            "SKILL.md must not duplicate the session_start log directive; "
            "gating lives solely in new-session-flow.md",
        )
        self.assertRegex(
            section.lower(),
            r"run-now|run now",
            "SKILL.md's New Session Flow pointer should still note the "
            "run-now gating for a reader who doesn't open the reference",
        )


# ---------------------------------------------------------------------------
# Half (b): runner is the sole fire-time author of one real session_start
# ---------------------------------------------------------------------------


def _make_state(session_id: str) -> OvernightState:
    return OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feat-a": OvernightFeatureStatus(status="pending")},
    )


class TestRunnerSessionStartSingle(unittest.TestCase):
    """Post-fire events.log holds exactly one real-id ``session_start``."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._session_id = "overnight-2026-06-01-0300"
        self._session_dir = self._tmp / "sessions" / self._session_id
        self._session_dir.mkdir(parents=True)
        self._state_path = self._session_dir / "overnight-state.json"
        self._events_path = self._session_dir / "overnight-events.log"
        state_module.save_state(_make_state(self._session_id), self._state_path)
        # Snapshot LIFECYCLE_SESSION_ID so the test never leaks env state.
        self._prior_lsid = os.environ.get("LIFECYCLE_SESSION_ID")

    def tearDown(self) -> None:
        if self._prior_lsid is None:
            os.environ.pop("LIFECYCLE_SESSION_ID", None)
        else:
            os.environ["LIFECYCLE_SESSION_ID"] = self._prior_lsid
        self._tmpdir.cleanup()

    def test_runner_logs_exactly_one_real_id_session_start(self) -> None:
        """``_start_session`` is the sole author of one real-id session_start.

        Exports ``LIFECYCLE_SESSION_ID`` exactly as ``runner.run`` does
        (runner.py: ``os.environ["LIFECYCLE_SESSION_ID"] = session_id``)
        before invoking the fire-time startup path. Non-subject IPC and
        interrupt-recovery plumbing is stubbed so the test exercises only the
        fire-time ``events.log_event(events.SESSION_START, ...)`` authorship.
        """
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
            # Mirror runner.run's export so log_event reads the real id.
            os.environ["LIFECYCLE_SESSION_ID"] = self._session_id
            state, pid_data, start_time = runner_module._start_session(
                state_path=self._state_path,
                session_dir=self._session_dir,
                repo_path=self._tmp,
                events_path=self._events_path,
                coord=coord,
            )

        self.assertIsNotNone(state, "fire-time startup returned a None state")

        records = events_module.read_events(self._events_path)
        starts = [r for r in records if r.get("event") == "session_start"]
        self.assertEqual(
            len(starts),
            1,
            f"expected exactly one session_start at fire, got {len(starts)}: "
            f"{starts}",
        )
        self.assertEqual(
            starts[0].get("session_id"),
            self._session_id,
            "the fire-time session_start must carry the real session id, "
            "not 'manual'",
        )
        self.assertNotEqual(
            starts[0].get("session_id"),
            "manual",
            "fire-time session_start must not be tagged session_id:'manual'",
        )

    def test_unset_lifecycle_session_id_yields_manual(self) -> None:
        """Guard: with LIFECYCLE_SESSION_ID unset, log_event tags 'manual'.

        This pins the failure mode the gating fixes — the prep-time log (no
        ``LIFECYCLE_SESSION_ID``) would land as ``manual``. The runner path
        sets the env var, which is why its fire-time log carries the real id.
        """
        os.environ.pop("LIFECYCLE_SESSION_ID", None)
        events_module.log_event(
            events_module.SESSION_START,
            round=1,
            details={"session_id": self._session_id},
            log_path=self._events_path,
        )
        records = events_module.read_events(self._events_path)
        starts = [r for r in records if r.get("event") == "session_start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].get("session_id"), "manual")


if __name__ == "__main__":
    unittest.main()
