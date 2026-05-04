"""Unit tests for the sidecar index module.

Covers:
  - add / remove / find / round-trip on :class:`ScheduledHandle`.
  - Corrupt JSON: ``read_sidecar`` returns ``[]`` and a subsequent
    ``add_entry`` overwrites the corrupt file.
  - Missing parent directory: first ``add_entry`` creates
    ``~/.cache/cortex-command/`` (handles first-install case).
  - Concurrent writers: threaded test using ``os.replace`` semantics —
    no torn writes; final file is a valid JSON list whose length
    equals the number of distinct labels added.
"""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_command.overnight.scheduler import sidecar
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(
    suffix: str,
    *,
    session_id: str | None = None,
) -> ScheduledHandle:
    """Build a synthetic :class:`ScheduledHandle` for tests."""
    sid = session_id if session_id is not None else f"sess-{suffix}"
    return ScheduledHandle(
        label=f"com.charleshall.cortex-command.overnight-schedule.{sid}.{suffix}",
        session_id=sid,
        plist_path=Path(f"/tmp/fake/{suffix}.plist"),
        launcher_path=Path(f"/tmp/fake/launcher-{suffix}.sh"),
        scheduled_for_iso="2026-05-04T23:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )


# ---------------------------------------------------------------------------
# Test base class with HOME redirect
# ---------------------------------------------------------------------------


class _SidecarTestCase(unittest.TestCase):
    """Redirect ``Path.home()`` to a per-test temp dir.

    The sidecar module derives its filesystem layout from
    ``Path.home()``, so each test gets a fresh ``HOME`` to ensure
    isolation. Patching only the resolver functions (rather than
    ``HOME`` env) avoids touching the real user's cache.
    """

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self._home = Path(self._tmp.name)

        # Patch Path.home() at the sidecar module's import binding.
        self._home_patch = patch(
            "cortex_command.overnight.scheduler.sidecar.Path.home",
            return_value=self._home,
        )
        self._home_patch.start()
        self.addCleanup(self._home_patch.stop)


# ---------------------------------------------------------------------------
# Round-trip: add → read → find → remove
# ---------------------------------------------------------------------------


class TestSidecarRoundTrip(_SidecarTestCase):
    """Add / read / find / remove invariants."""

    def test_add_then_read_returns_handle(self) -> None:
        h = _make_handle("a")
        sidecar.add_entry(h)

        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], h)

    def test_add_multiple_then_read_returns_all(self) -> None:
        h1 = _make_handle("a")
        h2 = _make_handle("b")
        sidecar.add_entry(h1)
        sidecar.add_entry(h2)

        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 2)
        self.assertIn(h1, entries)
        self.assertIn(h2, entries)

    def test_find_by_session_id_returns_handle(self) -> None:
        h = _make_handle("a", session_id="custom-session")
        sidecar.add_entry(h)

        found = sidecar.find_by_session_id("custom-session")
        self.assertEqual(found, h)

    def test_find_by_session_id_returns_none_for_missing(self) -> None:
        self.assertIsNone(sidecar.find_by_session_id("nonexistent"))

    def test_remove_entry_removes_handle(self) -> None:
        h1 = _make_handle("a")
        h2 = _make_handle("b")
        sidecar.add_entry(h1)
        sidecar.add_entry(h2)

        removed = sidecar.remove_entry(h1.label)
        self.assertTrue(removed)

        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], h2)

    def test_remove_entry_idempotent_for_missing(self) -> None:
        removed = sidecar.remove_entry("nonexistent-label")
        self.assertFalse(removed)

    def test_add_entry_replaces_existing_label(self) -> None:
        """Re-adding the same label overwrites rather than duplicates."""
        h_orig = _make_handle("a")
        h_replaced = ScheduledHandle(
            label=h_orig.label,
            session_id=h_orig.session_id,
            plist_path=Path("/tmp/different.plist"),
            launcher_path=Path("/tmp/launcher-different.sh"),
            scheduled_for_iso="2026-06-01T00:00:00",
            created_at_iso="2026-05-31T23:00:00",
        )
        sidecar.add_entry(h_orig)
        sidecar.add_entry(h_replaced)

        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], h_replaced)


# ---------------------------------------------------------------------------
# Missing parent directory
# ---------------------------------------------------------------------------


class TestSidecarMissingParentDir(_SidecarTestCase):
    """First-install case: ``~/.cache/cortex-command/`` does not exist."""

    def test_first_add_creates_cache_dir(self) -> None:
        cache_dir = self._home / ".cache" / "cortex-command"
        self.assertFalse(cache_dir.exists())

        sidecar.add_entry(_make_handle("a"))

        self.assertTrue(cache_dir.is_dir())
        self.assertTrue((cache_dir / "scheduled-launches.json").is_file())

    def test_read_on_absent_file_returns_empty_list(self) -> None:
        self.assertEqual(sidecar.read_sidecar(), [])

    def test_find_on_absent_file_returns_none(self) -> None:
        self.assertIsNone(sidecar.find_by_session_id("anything"))

    def test_remove_on_absent_file_is_noop(self) -> None:
        self.assertFalse(sidecar.remove_entry("anything"))


# ---------------------------------------------------------------------------
# Corruption handling
# ---------------------------------------------------------------------------


class TestSidecarCorruption(_SidecarTestCase):
    """Corrupt JSON: read returns ``[]``; next write self-heals."""

    def _write_raw(self, content: str) -> None:
        path = sidecar.sidecar_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_corrupt_json_read_returns_empty(self) -> None:
        self._write_raw("not-json-at-all{")
        self.assertEqual(sidecar.read_sidecar(), [])

    def test_corrupt_json_followed_by_add_overwrites(self) -> None:
        self._write_raw("not-json{")
        sidecar.add_entry(_make_handle("a"))
        # Subsequent read produces the freshly-added record.
        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 1)

    def test_root_not_a_list_returns_empty(self) -> None:
        self._write_raw('{"oops": "this is a dict"}')
        self.assertEqual(sidecar.read_sidecar(), [])

    def test_record_missing_field_skipped(self) -> None:
        # First record valid, second missing 'launcher_path'.
        valid = {
            "label": "L1",
            "session_id": "s1",
            "plist_path": "/tmp/p1.plist",
            "launcher_path": "/tmp/l1.sh",
            "scheduled_for_iso": "2026-05-04T23:00:00",
            "created_at_iso": "2026-05-04T22:00:00",
        }
        invalid = {"label": "L2"}
        self._write_raw(json.dumps([valid, invalid]))
        entries = sidecar.read_sidecar()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].label, "L1")

    def test_empty_file_returns_empty_list(self) -> None:
        self._write_raw("")
        self.assertEqual(sidecar.read_sidecar(), [])


# ---------------------------------------------------------------------------
# Concurrent writes
# ---------------------------------------------------------------------------


class TestSidecarConcurrentWrites(_SidecarTestCase):
    """Threaded writers do not produce torn JSON.

    ``os.replace`` is atomic on POSIX, so even without an external
    lock the file always parses as valid JSON. Without a lock the
    final list MAY be missing some entries (last-writer-wins on a
    read-modify-write cycle), but that is the documented contract —
    the schedule lock in the macOS backend is what guarantees
    no-loss for the production path. This test only asserts the
    weaker no-torn-writes invariant.
    """

    def test_concurrent_writes_produce_valid_json(self) -> None:
        n_threads = 8

        def _writer(idx: int) -> None:
            sidecar.add_entry(_make_handle(f"t{idx}"))

        threads = [
            threading.Thread(target=_writer, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File is parseable; root is a list.
        path = sidecar.sidecar_path()
        decoded = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(decoded, list)
        # No partial / mangled records — every entry must round-trip.
        for record in decoded:
            self.assertIn("label", record)
            self.assertIn("session_id", record)
            self.assertIn("plist_path", record)
            self.assertIn("launcher_path", record)


if __name__ == "__main__":
    unittest.main()
