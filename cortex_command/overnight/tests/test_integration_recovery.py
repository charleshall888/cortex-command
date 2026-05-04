"""Integration-style tests for cortex_command.overnight.integration_recovery.

Verifies the dispatch-site fix from spec Req #3a: the production caller at
integration_recovery.py:215-225 must pass model_override="opus" to
dispatch_task so the skill-based effort override (integration-recovery -> max,
gated on resolved model == "opus") fires reliably for every dispatch.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from cortex_command.overnight import integration_recovery


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> CompletedProcess:
    """Build a CompletedProcess suitable for use as a subprocess.run mock return value."""
    result = CompletedProcess(args=[], returncode=returncode)
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestIntegrationRecoveryForcesOpus(unittest.TestCase):
    """Spec Req #3a: dispatch_task must receive model_override="opus"."""

    def test_integration_recovery_forces_opus(self):
        """Integration-recovery dispatch passes model_override="opus"."""
        recorded: dict = {}

        async def _spy_dispatch(*args, **kwargs):
            # Record the call args/kwargs so we can assert on them after main() returns.
            recorded["args"] = args
            recorded["kwargs"] = kwargs

            # Return a minimal object; main() does not inspect the return value.
            class _Result:
                success = True
                output = ""
                cost_usd = 0.0
                error_type = None
                error_detail = None

            return _Result()

        def _subprocess_side_effect(cmd, **kwargs):
            # Flaky guard: simulate a non-flaky failure (returncode != 0) so the
            # dispatch path is exercised. The SHA / re-test paths after dispatch
            # are not under test here — we short-circuit by leaving the SHA
            # equal across calls (caught by the circuit breaker, but only AFTER
            # dispatch_task is called, which is what we are asserting).
            if isinstance(cmd, list):
                if "rev-parse" in cmd and "HEAD" in cmd:
                    return _make_proc(returncode=0, stdout="abc123\n")
                if "diff" in cmd:
                    return _make_proc(returncode=0, stdout="")
            # bash -c "<test_command>" -> returncode 1 means tests failed (not flaky).
            return _make_proc(returncode=1)

        with tempfile.TemporaryDirectory() as tmp:
            worktree_path = Path(tmp)
            argv = [
                "integration_recovery",
                "--worktree", str(worktree_path),
                "--test-command", "false",
                "--test-output", "FAILED test_foo",
            ]
            with patch.object(sys, "argv", argv):
                with patch(
                    "cortex_command.overnight.integration_recovery.subprocess.run",
                    side_effect=_subprocess_side_effect,
                ):
                    with patch(
                        "cortex_command.overnight.integration_recovery.dispatch_task",
                        new=_spy_dispatch,
                    ):
                        # Ensure the dispatch path is taken (not the
                        # _DISPATCH_AVAILABLE early return).
                        with patch.object(
                            integration_recovery, "_DISPATCH_AVAILABLE", True,
                        ):
                            integration_recovery.main()

        # Verify dispatch_task was actually invoked.
        self.assertIn("kwargs", recorded, "dispatch_task was not called")

        # Spec Req #3a: model_override must be "opus" so the skill override
        # (integration-recovery -> max effort) fires reliably.
        self.assertEqual(
            recorded["kwargs"].get("model_override"),
            "opus",
            "dispatch_task must be called with model_override='opus' "
            "(spec Req #3a) so the integration-recovery skill effort "
            "override fires reliably.",
        )


if __name__ == "__main__":
    unittest.main()
