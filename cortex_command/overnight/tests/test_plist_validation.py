"""Unit tests for plist round-trip validation and bootstrap-and-verify
in :class:`MacOSLaunchAgentBackend` (R6 / R7).

Covers:
  - Happy round-trip: a well-formed plist dict survives
    ``plistlib.dumps`` then ``plistlib.loads`` without divergence.
  - Typo'd top-level key (``LabeI`` instead of ``Label``) rejected via
    :class:`PlistValidationError`.
  - Bootstrap + verify ``state = waiting`` substring path: success
    returns cleanly.
  - Bootstrap success but ``state = waiting`` absent in print output:
    raises :class:`LaunchctlVerifyError`.
"""

from __future__ import annotations

import plistlib
import subprocess
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.scheduler.macos import (
    LaunchctlBootstrapError,
    LaunchctlVerifyError,
    MacOSLaunchAgentBackend,
    PlistValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_target(now: datetime | None = None) -> datetime:
    """Build a target time 1 hour from ``now`` (or wallclock now)."""
    base = now or datetime.now()
    return base + timedelta(hours=1)


def _make_completed(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    """Build a fake :class:`subprocess.CompletedProcess`."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Round-trip validation
# ---------------------------------------------------------------------------


class TestPlistRoundTrip(unittest.TestCase):
    """Round-trip ``plistlib.dumps``/``plistlib.loads`` invariants."""

    def test_happy_round_trip(self) -> None:
        backend = MacOSLaunchAgentBackend()
        target = _make_target()
        rendered = backend._render_and_validate_plist(
            label="com.charleshall.cortex-command.overnight-schedule.s1.1",
            target=target,
            env_snapshot={"PATH": "/usr/bin"},
            launcher_path=Path("/tmp/launcher.sh"),
            repo_root=Path("/repo"),
            session_dir_=Path("/sessions/s1"),
        )
        # Must be parseable back into the same structure.
        roundtrip = plistlib.loads(rendered)
        self.assertEqual(roundtrip["Label"], "com.charleshall.cortex-command.overnight-schedule.s1.1")
        self.assertIn("StartCalendarInterval", roundtrip)
        self.assertIn("EnvironmentVariables", roundtrip)
        self.assertEqual(roundtrip["EnvironmentVariables"]["PATH"], "/usr/bin")
        self.assertEqual(roundtrip["RunAtLoad"], False)

    def test_round_trip_validation_detects_corruption(self) -> None:
        """If we hand-craft a plist dict whose round-trip diverges
        (simulated by patching ``plistlib.loads`` to return a typo'd
        copy), :class:`PlistValidationError` fires and names the
        divergent key.
        """
        backend = MacOSLaunchAgentBackend()
        target = _make_target()

        original_loads = plistlib.loads

        def _corrupting_loads(data: bytes) -> dict:
            parsed = original_loads(data)
            # Simulate a round-trip that drops the Label key (e.g. as
            # might happen if the plist serializer emitted "LabeI" by
            # mistake — the round-trip would then have no "Label").
            corrupted = dict(parsed)
            del corrupted["Label"]
            corrupted["LabeI"] = parsed["Label"]
            return corrupted

        with patch(
            "cortex_command.overnight.scheduler.macos.plistlib.loads",
            side_effect=_corrupting_loads,
        ):
            with self.assertRaises(PlistValidationError) as cm:
                backend._render_and_validate_plist(
                    label="com.charleshall.cortex-command.overnight-schedule.s1.1",
                    target=target,
                    env_snapshot={"PATH": "/usr/bin"},
                    launcher_path=Path("/tmp/launcher.sh"),
                    repo_root=Path("/repo"),
                    session_dir_=Path("/sessions/s1"),
                )
        self.assertEqual(cm.exception.label, "com.charleshall.cortex-command.overnight-schedule.s1.1")
        self.assertEqual(cm.exception.key, "Label")


# ---------------------------------------------------------------------------
# Bootstrap + verify
# ---------------------------------------------------------------------------


class TestBootstrapAndVerify(unittest.TestCase):
    """Subprocess fakes drive the bootstrap/verify branches."""

    def test_bootstrap_then_verify_succeeds(self) -> None:
        backend = MacOSLaunchAgentBackend()
        plist_path = Path("/tmp/fake.plist")
        label = "com.charleshall.cortex-command.overnight-schedule.s1.1"

        calls: list[list[str]] = []

        def _fake_run(argv, *args, **kwargs):
            calls.append(list(argv))
            if argv[1] == "bootstrap":
                return _make_completed(returncode=0)
            if argv[1] == "print":
                return _make_completed(
                    returncode=0,
                    stdout=b"foo bar\nstate = waiting\nbaz",
                )
            raise AssertionError(f"unexpected argv: {argv!r}")

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_fake_run,
        ):
            backend._bootstrap_and_verify(plist_path, label)

        # We expect at least one bootstrap and one print call.
        self.assertTrue(any(c[1] == "bootstrap" for c in calls))
        self.assertTrue(any(c[1] == "print" for c in calls))

    def test_bootstrap_nonzero_raises(self) -> None:
        backend = MacOSLaunchAgentBackend()

        def _fake_run(argv, *args, **kwargs):
            return _make_completed(
                returncode=5,
                stderr=b"bootstrap: domain inaccessible",
            )

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_fake_run,
        ):
            with self.assertRaises(LaunchctlBootstrapError) as cm:
                backend._bootstrap_and_verify(
                    Path("/tmp/fake.plist"),
                    "com.charleshall.cortex-command.overnight-schedule.s1.1",
                )
        self.assertEqual(cm.exception.exit_code, 5)
        self.assertIn("domain inaccessible", cm.exception.stderr)

    def test_verify_state_waiting_absent_raises(self) -> None:
        """Bootstrap succeeds but the ``state = waiting`` substring is
        never emitted by ``launchctl print`` within the verify budget.
        """
        backend = MacOSLaunchAgentBackend()

        def _fake_run(argv, *args, **kwargs):
            if argv[1] == "bootstrap":
                return _make_completed(returncode=0)
            if argv[1] == "print":
                # Print returns 0 but lacks the substring.
                return _make_completed(
                    returncode=0,
                    stdout=b"state = running\n",
                )
            raise AssertionError(argv)

        # Patch time.sleep so the poll loop spins quickly to deadline,
        # and patch time.monotonic to produce a tight deadline.
        time_values = iter([0.0, 0.1, 0.2, 1.5, 2.0, 3.0])

        def _fake_monotonic() -> float:
            try:
                return next(time_values)
            except StopIteration:
                return 999.0

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_fake_run,
        ), patch(
            "cortex_command.overnight.scheduler.macos.time.sleep",
            return_value=None,
        ), patch(
            "cortex_command.overnight.scheduler.macos.time.monotonic",
            side_effect=_fake_monotonic,
        ):
            with self.assertRaises(LaunchctlVerifyError) as cm:
                backend._bootstrap_and_verify(
                    Path("/tmp/fake.plist"),
                    "com.charleshall.cortex-command.overnight-schedule.s1.1",
                )
        self.assertEqual(
            cm.exception.label,
            "com.charleshall.cortex-command.overnight-schedule.s1.1",
        )


if __name__ == "__main__":
    unittest.main()
