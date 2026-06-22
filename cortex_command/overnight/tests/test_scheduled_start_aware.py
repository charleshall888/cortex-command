"""Regression guard for the tz-aware ``scheduled_start`` writer (Task 10 / R7).

Task 8 made the *reader* (``status._parse_iso``) normalize naive→local→UTC so
``cortex overnight status`` stops crashing on legacy naive ``scheduled_start``
values. Task 10 (R7, "Should") fixes the *writer* too: the scheduler now emits
``scheduled_start``/``scheduled_for_iso`` tz-aware with the local offset
(``resolved_target.astimezone().isoformat()``), so new sessions are
unambiguous and no longer depend on the reader's normalization backstop.

These tests are a **regression guard**, not a fix for an open defect:

  1. A newly written ``scheduled_for_iso`` (from the real ``backend.schedule``
     write site, ``macos.py``) parses to a tz-aware datetime
     (``.tzinfo is not None``).
  2. The spent-fire GC ``_is_spent`` loop still reaps a **past aware**
     ``scheduled_for`` when called with a **naive** ``now = datetime.now()``
     (``macos.py``) — confirming the existing
     ``scheduled_for.tzinfo is not None and now.tzinfo is None`` normalization
     handles the aware values the writer now emits, without crashing on a
     naive-vs-aware compare. Asserted both at the ``_is_spent`` unit level and
     end-to-end through ``_gc_pass`` reaping an aware spent entry.
  3. The Task 9 legacy-naive **reader** path still parses a naive
     ``scheduled_start`` without raising (the backstop is intact).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.scheduler import sidecar
from cortex_command.overnight.scheduler.labels import mint_label
from cortex_command.overnight.scheduler.macos import (
    MacOSLaunchAgentBackend,
    _is_spent,
)
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    """Build a fake :class:`subprocess.CompletedProcess`."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _touch_plist(plist_dir: Path, label: str) -> tuple[Path, Path]:
    """Create a plist + paired launcher under ``plist_dir`` for ``label``."""
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / f"{label}.plist"
    launcher = plist_dir / f"launcher-{label}.sh"
    plist.write_text("<plist/>\n", encoding="utf-8")
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    return plist, launcher


# ---------------------------------------------------------------------------
# Test base — temp HOME (sidecar/lock root) + temp TMPDIR (plist dir)
# ---------------------------------------------------------------------------


class _SchedulerTempEnv(unittest.TestCase):
    """Per-test temp HOME (sidecar root) + temp TMPDIR (plist dir).

    Mirrors ``test_plist_gc._GCTestCase`` so the real ``backend.schedule`` /
    ``_gc_pass`` paths operate on isolated scratch dirs, never the user's
    LaunchAgents.
    """

    def setUp(self) -> None:
        self._home_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._home_tmp.cleanup)
        self._home = Path(self._home_tmp.name)

        self._tmp_tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_tmpdir.cleanup)
        self._tmpdir = Path(self._tmp_tmpdir.name)

        for target in (
            "cortex_command.overnight.scheduler.sidecar.Path.home",
            "cortex_command.overnight.scheduler.lock.Path.home",
        ):
            p = patch(target, return_value=self._home)
            p.start()
            self.addCleanup(p.stop)

        tmpdir_patch = patch.dict(os.environ, {"TMPDIR": str(self._tmpdir)})
        tmpdir_patch.start()
        self.addCleanup(tmpdir_patch.stop)

        self.plist_dir = self._tmpdir / "cortex-overnight-launch"
        self._sessions_root = self._home / "sessions"

    def _fake_session_dir(self, session_id: str) -> Path:
        d = self._sessions_root / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _schedule(self, *, target: datetime, session_id: str) -> ScheduledHandle:
        """Drive the real ``backend.schedule`` with mocked launchctl.

        Exercises the production write site (``macos.py`` ``schedule()``)
        that emits ``scheduled_for_iso`` — no monkeypatch of the writer
        expression itself, so the test verifies real behavior.
        """
        backend = MacOSLaunchAgentBackend()

        def _fake_run(argv, *args, **kwargs):
            verb = argv[1]
            if verb == "bootstrap":
                return _make_completed(returncode=0)
            if verb == "print":
                return _make_completed(returncode=0, stdout=b"state = waiting\n")
            raise AssertionError(f"unexpected argv: {argv!r}")

        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            side_effect=_fake_run,
        ), patch(
            "cortex_command.overnight.state.session_dir",
            side_effect=self._fake_session_dir,
        ):
            return backend.schedule(
                target=target,
                session_id=session_id,
                env={},
                repo_root=Path("/repo"),
            )


# ---------------------------------------------------------------------------
# (1) Writer emits a tz-aware scheduled_for_iso
# ---------------------------------------------------------------------------


class TestWriterEmitsAware(_SchedulerTempEnv):
    def test_scheduled_for_iso_is_tz_aware(self) -> None:
        """A newly scheduled fire writes a tz-aware ``scheduled_for_iso``.

        ``backend.schedule`` is given a naive-local ``target`` (the shape
        ``parse_target_time`` produces). Post-R7 the writer attaches the
        local offset via ``.astimezone()``, so the persisted string parses
        back to ``.tzinfo is not None`` — unambiguous for the status reader.
        """
        target = datetime.now() + timedelta(hours=1)  # naive-local
        handle = self._schedule(target=target, session_id="fresh")

        parsed = datetime.fromisoformat(handle.scheduled_for_iso)
        self.assertIsNotNone(
            parsed.tzinfo,
            f"scheduled_for_iso must be tz-aware, got {handle.scheduled_for_iso!r}",
        )
        # The sidecar entry persists the same aware string.
        sidecar_handles = sidecar.read_sidecar()
        self.assertTrue(sidecar_handles)
        for h in sidecar_handles:
            self.assertIsNotNone(
                datetime.fromisoformat(h.scheduled_for_iso).tzinfo,
                f"sidecar scheduled_for_iso must be aware, got "
                f"{h.scheduled_for_iso!r}",
            )


# ---------------------------------------------------------------------------
# (2) GC _is_spent still reaps an aware scheduled_for against a naive now
# ---------------------------------------------------------------------------


class TestIsSpentReapsAware(unittest.TestCase):
    def test_is_spent_reaps_past_aware_against_naive_now(self) -> None:
        """A past **aware** ``scheduled_for`` is spent vs a **naive** ``now``.

        The GC loop calls ``_is_spent`` with ``now = datetime.now()`` (naive).
        After R7 the stored value is aware; the
        ``scheduled_for.tzinfo is not None and now.tzinfo is None`` branch
        must normalize ``now`` to the stored offset and report the past fire
        as spent — without raising a naive-vs-aware ``TypeError``.
        """
        past_aware = (
            datetime.now().astimezone() - timedelta(hours=2)
        ).isoformat()
        naive_now = datetime.now()  # the production GC ``now``

        self.assertTrue(
            _is_spent(past_aware, naive_now),
            "past aware scheduled_for must be reaped against a naive now",
        )

    def test_is_spent_preserves_future_aware_against_naive_now(self) -> None:
        """A future aware ``scheduled_for`` is NOT spent (still pending)."""
        future_aware = (
            datetime.now().astimezone() + timedelta(hours=2)
        ).isoformat()
        self.assertFalse(_is_spent(future_aware, datetime.now()))


class TestGCReapsAwareSpentEntry(_SchedulerTempEnv):
    def test_gc_pass_reaps_aware_spent_entry(self) -> None:
        """End-to-end: ``_gc_pass`` reaps an aware spent sidecar entry.

        Confirms the writer change (aware ``scheduled_for_iso``) does not
        break the spent-fire GC loop's naive-``now`` reaping path.
        """
        backend = MacOSLaunchAgentBackend()

        past_aware = (
            datetime.now().astimezone() - timedelta(hours=2)
        ).isoformat()
        label = mint_label("fresh")
        spent = ScheduledHandle(
            label=label,
            session_id="fresh",
            plist_path=self.plist_dir / f"{label}.plist",
            launcher_path=self.plist_dir / f"launcher-{label}.sh",
            scheduled_for_iso=past_aware,
            created_at_iso=datetime.now().isoformat(),
        )
        sidecar.add_entry(spent)
        plist, launcher = _touch_plist(self.plist_dir, label)

        # launchctl reports REGISTERED — the spent-by-timestamp reap must
        # win regardless, proving the aware compare drove the decision.
        with patch(
            "cortex_command.overnight.scheduler.macos.subprocess.run",
            return_value=_make_completed(returncode=0, stdout=b"state = waiting\n"),
        ):
            backend._gc_pass()

        self.assertFalse(plist.exists(), "spent plist not reaped")
        self.assertFalse(launcher.exists(), "spent launcher not reaped")
        self.assertNotIn(
            spent.label,
            {h.label for h in sidecar.read_sidecar()},
            "spent sidecar entry not reaped",
        )


# ---------------------------------------------------------------------------
# (3) Task 9 legacy-naive reader backstop still parses without raising
# ---------------------------------------------------------------------------


class TestLegacyNaiveReaderBackstop(unittest.TestCase):
    def test_parse_iso_normalizes_legacy_naive_scheduled_start(self) -> None:
        """The Task 9 reader still normalizes a legacy naive ``scheduled_start``.

        Pre-R7 sessions persist naive-local strings. ``status._parse_iso``
        must still interpret them (naive→system-local→UTC) and yield a
        tz-aware UTC datetime so downstream compares never raise — the
        backstop R7 leaves in place for already-scheduled sessions.
        """
        from cortex_command.overnight import status as status_module

        naive_legacy = (
            datetime.now() + timedelta(hours=1)
        ).replace(microsecond=0).isoformat()
        self.assertIsNone(
            datetime.fromisoformat(naive_legacy).tzinfo,
            "fixture must be naive to exercise the legacy backstop",
        )

        parsed = status_module._parse_iso(naive_legacy)
        self.assertIsNotNone(
            parsed.tzinfo, "reader must normalize naive input to tz-aware"
        )
        self.assertEqual(
            parsed.utcoffset(),
            timedelta(0),
            "reader normalizes to UTC-aware",
        )


if __name__ == "__main__":
    unittest.main()
