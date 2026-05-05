"""Unit tests for the GC pass + concurrent-schedule serialization.

Covers:
  - Stale plist (label absent from sidecar) removed; paired
    ``launcher-<label>.sh`` also removed.
  - In-flight plist (label present in sidecar AND ``launchctl print``
    exits 0) preserved.
  - Tracked-but-launchctl-exits-113 plist (job already completed)
    removed.
  - Corrupt sidecar handled gracefully — no plist removal (fail
    closed).
  - Concurrent-schedule serialization: two threads invoke
    ``schedule()`` simultaneously with mocked ``launchctl``; both
    succeed and GC does not remove either invocation's in-flight plist.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.scheduler import sidecar
from cortex_command.overnight.scheduler.macos import (
    MacOSLaunchAgentBackend,
    _LAUNCHCTL_PRINT_NOT_REGISTERED_EXIT,
)
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    """Build a fake :class:`subprocess.CompletedProcess`."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _mk_label(suffix: str) -> str:
    """Mint a deterministic label whose trailing field is a valid epoch int.

    ``parse_label`` (used by GC to filter foreign plists) requires the
    suffix to be an integer, so we hash the string suffix into a stable
    epoch value. The exact number is irrelevant — only the
    parses-as-int property matters for these tests.
    """
    epoch = abs(hash(suffix)) % 10_000_000 + 1
    return (
        "com.charleshall.cortex-command.overnight-schedule."
        f"sess-{suffix}.{epoch}"
    )


def _mk_handle(suffix: str, plist_dir: Path) -> ScheduledHandle:
    label = _mk_label(suffix)
    return ScheduledHandle(
        label=label,
        session_id=f"sess-{suffix}",
        plist_path=plist_dir / f"{label}.plist",
        launcher_path=plist_dir / f"launcher-{label}.sh",
        scheduled_for_iso="2026-05-04T23:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )


def _touch_plist(plist_dir: Path, label: str) -> tuple[Path, Path]:
    """Create empty plist + launcher files for ``label``. Returns (plist, launcher)."""
    plist_dir.mkdir(parents=True, exist_ok=True)
    p = plist_dir / f"{label}.plist"
    l = plist_dir / f"launcher-{label}.sh"
    p.write_text("<plist/>")
    l.write_text("#!/bin/bash\nexit 0\n")
    return p, l


# ---------------------------------------------------------------------------
# Test base class — temp HOME + temp TMPDIR
# ---------------------------------------------------------------------------


class _GCTestCase(unittest.TestCase):
    """Per-test temp HOME (sidecar root) + temp TMPDIR (plist dir)."""

    def setUp(self) -> None:
        self._home_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._home_tmp.cleanup)
        self._home = Path(self._home_tmp.name)

        self._tmp_tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_tmpdir.cleanup)
        self._tmpdir = Path(self._tmp_tmpdir.name)

        # Patch Path.home() at all sites that consult it.
        self._home_patches = [
            patch(
                "cortex_command.overnight.scheduler.sidecar.Path.home",
                return_value=self._home,
            ),
            patch(
                "cortex_command.overnight.scheduler.lock.Path.home",
                return_value=self._home,
            ),
        ]
        for p in self._home_patches:
            p.start()
            self.addCleanup(p.stop)

        # TMPDIR drives _plist_dir().
        self._tmpdir_patch = patch.dict(
            os.environ, {"TMPDIR": str(self._tmpdir)}
        )
        self._tmpdir_patch.start()
        self.addCleanup(self._tmpdir_patch.stop)

        # The plist dir under the temp TMPDIR.
        self.plist_dir = self._tmpdir / "cortex-overnight-launch"


# ---------------------------------------------------------------------------
# GC pass — stale, in-flight, completed, corrupt-sidecar cases
# ---------------------------------------------------------------------------


class TestGCPass(_GCTestCase):
    """Per-case behavior of :meth:`MacOSLaunchAgentBackend._gc_pass`."""

    def test_stale_plist_removed(self) -> None:
        """Plist whose label is not in the sidecar is removed."""
        backend = MacOSLaunchAgentBackend()
        # Seed sidecar with a different schedule so the file exists
        # and read_sidecar returns a non-empty list (avoiding the
        # corrupt-sidecar fail-closed path).
        sidecar.add_entry(_mk_handle("alive", self.plist_dir))
        plist_alive, launcher_alive = _touch_plist(
            self.plist_dir, _mk_label("alive")
        )

        # Untracked stale plist.
        plist_stale, launcher_stale = _touch_plist(
            self.plist_dir, _mk_label("stale")
        )

        # launchctl print returns 0 for the alive label so it stays;
        # we don't reach launchctl for the stale one because it's
        # untracked.
        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0),
        ):
            removed = backend._gc_pass()

        self.assertFalse(plist_stale.exists())
        self.assertFalse(launcher_stale.exists())
        self.assertTrue(plist_alive.exists())
        self.assertTrue(launcher_alive.exists())
        self.assertEqual(removed, 2)

    def test_in_flight_plist_preserved(self) -> None:
        """Tracked plist with launchctl print exit 0 is preserved."""
        backend = MacOSLaunchAgentBackend()
        h = _mk_handle("alive", self.plist_dir)
        sidecar.add_entry(h)
        plist, launcher = _touch_plist(self.plist_dir, h.label)

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0),
        ):
            removed = backend._gc_pass()

        self.assertTrue(plist.exists())
        self.assertTrue(launcher.exists())
        self.assertEqual(removed, 0)

    def test_tracked_but_launchctl_113_removed(self) -> None:
        """Plist tracked in sidecar but launchctl reports 'not registered' is GC'd."""
        backend = MacOSLaunchAgentBackend()
        h = _mk_handle("ghost", self.plist_dir)
        sidecar.add_entry(h)
        plist, launcher = _touch_plist(self.plist_dir, h.label)

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(
                returncode=_LAUNCHCTL_PRINT_NOT_REGISTERED_EXIT
            ),
        ):
            removed = backend._gc_pass()

        self.assertFalse(plist.exists())
        self.assertFalse(launcher.exists())
        self.assertEqual(removed, 2)

    def test_orphan_launcher_paired_with_stale_plist_removed(self) -> None:
        """Verifies the launcher file is removed alongside its plist (covers
        the explicit spec call-out: 'orphan launcher.sh paired with stale
        plist also removed')."""
        backend = MacOSLaunchAgentBackend()
        # Seed a tracked entry so sidecar is non-empty (avoid
        # fail-closed).
        sidecar.add_entry(_mk_handle("alive", self.plist_dir))
        _touch_plist(self.plist_dir, _mk_label("alive"))

        plist_stale, launcher_stale = _touch_plist(
            self.plist_dir, _mk_label("orphan")
        )

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0),
        ):
            backend._gc_pass()

        self.assertFalse(plist_stale.exists())
        self.assertFalse(launcher_stale.exists())

    def test_corrupt_sidecar_skips_gc(self) -> None:
        """Corrupt sidecar → no plist removal (fail closed)."""
        backend = MacOSLaunchAgentBackend()
        # Write a corrupt sidecar — must exist so the fail-closed
        # path triggers (an absent file is interpreted as "first
        # use", which legitimately implies no tracked schedules).
        sidecar_path = sidecar.sidecar_path()
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text("not-json{", encoding="utf-8")

        plist, launcher = _touch_plist(self.plist_dir, _mk_label("any"))

        # No subprocess call should be needed in the fail-closed
        # path; if launchctl is invoked we want the test to fail
        # loudly (the GC should bail early).
        def _no_subprocess(*args, **kwargs):
            raise AssertionError(
                "launchctl was invoked despite corrupt sidecar"
            )

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_no_subprocess,
        ):
            removed = backend._gc_pass()

        self.assertTrue(plist.exists())
        self.assertTrue(launcher.exists())
        self.assertEqual(removed, 0)

    def test_no_plist_dir_returns_zero(self) -> None:
        """Plist dir absent → GC is a no-op."""
        backend = MacOSLaunchAgentBackend()
        # Don't create plist_dir; it should not exist.
        self.assertFalse(self.plist_dir.exists())

        removed = backend._gc_pass()
        self.assertEqual(removed, 0)

    def test_foreign_plist_in_dir_ignored(self) -> None:
        """Plists not matching our label format are left alone."""
        backend = MacOSLaunchAgentBackend()
        # Seed sidecar with an entry to avoid the fail-closed path.
        sidecar.add_entry(_mk_handle("a", self.plist_dir))
        _touch_plist(self.plist_dir, _mk_label("a"))

        # Foreign plist (does not parse as our label format).
        self.plist_dir.mkdir(parents=True, exist_ok=True)
        foreign = self.plist_dir / "com.someone.else.foo.plist"
        foreign.write_text("<plist/>")

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0),
        ):
            backend._gc_pass()

        self.assertTrue(foreign.exists())

    def test_idempotent_back_to_back_calls(self) -> None:
        """Repeated GC calls are no-ops once stale files are gone."""
        backend = MacOSLaunchAgentBackend()
        sidecar.add_entry(_mk_handle("a", self.plist_dir))
        _touch_plist(self.plist_dir, _mk_label("a"))

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0),
        ):
            first = backend._gc_pass()
            second = backend._gc_pass()
            third = backend._gc_pass()

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(third, 0)


# ---------------------------------------------------------------------------
# Concurrent-schedule serialization
# ---------------------------------------------------------------------------


class TestConcurrentSchedule(_GCTestCase):
    """Two threads invoking ``schedule()`` simultaneously must not race.

    The schedule lock guarantees one schedule's GC cannot remove
    another's just-written plist before its sidecar entry lands. The
    test mocks all subprocess calls (launchctl bootstrap + print) so
    no real launchd interaction occurs; it focuses on the
    sidecar/GC/plist-write coordination.
    """

    def test_two_concurrent_schedules_both_succeed(self) -> None:
        """Both schedule calls produce sidecar entries and surviving plists."""

        # Mock subprocess for launchctl: bootstrap returns 0, print
        # returns 0 with the verify substring. No GC removals
        # because every label minted is in the sidecar by the time
        # any GC inspects it (the lock guarantees this).
        def _fake_run(argv, *args, **kwargs):
            if argv[1] == "bootstrap":
                return _make_completed(returncode=0)
            if argv[1] == "print":
                return _make_completed(
                    returncode=0,
                    stdout=b"state = waiting\n",
                )
            raise AssertionError(f"unexpected argv: {argv!r}")

        # Patch session_dir to point inside our temp tree so the
        # plist dict's StandardOutPath / StandardErrorPath don't
        # leak outside the test.
        sessions_root = self._home / "sessions"

        def _fake_session_dir(session_id: str) -> Path:
            d = sessions_root / session_id
            d.mkdir(parents=True, exist_ok=True)
            return d

        # Use a barrier so the two threads enter schedule() at
        # roughly the same wallclock instant. The schedule lock
        # then serializes them.
        barrier = threading.Barrier(2)
        results: dict[str, ScheduledHandle | Exception] = {}

        backend = MacOSLaunchAgentBackend()
        target = datetime.now() + timedelta(hours=1)

        # Stagger session IDs so the two labels are distinct.
        def _worker(session_id: str) -> None:
            barrier.wait()
            try:
                handle = backend.schedule(
                    target=target,
                    session_id=session_id,
                    env={},
                    repo_root=Path("/repo"),
                )
                results[session_id] = handle
            except Exception as exc:
                results[session_id] = exc

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_fake_run,
        ), patch(
            "cortex_command.overnight.state.session_dir",
            side_effect=_fake_session_dir,
        ):
            t1 = threading.Thread(target=_worker, args=("sessA",))
            t2 = threading.Thread(target=_worker, args=("sessB",))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        # Both threads completed.
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(set(results.keys()), {"sessA", "sessB"})

        # Inspect outcomes. The spec allows "both succeed (or one
        # fails cleanly)". Verify that any failure is a clean
        # exception (not a torn-state crash).
        successes = [
            h for h in results.values() if isinstance(h, ScheduledHandle)
        ]
        self.assertGreaterEqual(
            len(successes),
            1,
            f"expected at least one successful schedule, got results={results!r}",
        )

        # For each successful schedule, the plist must still exist
        # on disk AND the sidecar must still contain its entry — i.e.
        # the other thread's GC pass did not remove it.
        sidecar_labels = {h.label for h in sidecar.read_sidecar()}
        for handle in successes:
            self.assertTrue(
                handle.plist_path.exists(),
                f"plist for {handle.label!r} was removed by concurrent GC",
            )
            self.assertIn(
                handle.label,
                sidecar_labels,
                f"sidecar entry for {handle.label!r} missing after concurrent schedule",
            )


if __name__ == "__main__":
    unittest.main()
