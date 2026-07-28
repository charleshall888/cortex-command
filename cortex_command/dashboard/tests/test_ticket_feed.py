"""Unit tests for cortex_command/dashboard/ticket_feed.py.

The snapshot's schema is the deliverable — downstream views are written
against it before they can read the code that fills it — so these tests
assert the shape key-for-key rather than spot-checking values.

Tests cover:
  - the exact key set, the pinned schema version, and per-item keys
  - id-keyed items resolving by subscript, not by scan
  - the active/archive split reaching the snapshot
  - an unknown item schema version not killing the build
  - deferral exposed as two independent flags
  - blocker refs resolved to status and title across terminal items
  - every null-phase spelling collapsing to one value
  - the module importing without the optional agent SDK installed
  - stale marking that copies rather than mutates
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cortex_command.dashboard.ticket_feed import (
    build_backlog_snapshot,
    mark_snapshot_stale,
)

# The full key set a consumer may rely on. Asserted by equality, not
# containment: a silently-dropped key is exactly the regression #412 and
# #413 cannot defend themselves against.
EXPECTED_KEYS = [
    "active_ids",
    "archive_ids",
    "blocked_why",
    "counts",
    "epics",
    "ineligible",
    "item_order",
    "items",
    "polled_ts",
    "ready",
    "schema_version",
    "stale",
]

EXPECTED_ITEM_KEYS = {
    "areas",
    "blocked_by",
    "blocks",
    "created",
    "deferred_status",
    "deferred_tag",
    "discovery_source",
    "id",
    "lifecycle_phase",
    "lifecycle_slug",
    "parent",
    "phase",
    "plan",
    "priority",
    "repo",
    "research",
    "schema_version",
    "session_id",
    "spec",
    "status",
    "tags",
    "title",
    "type",
    "updated",
    "uuid",
}


def _write_item(directory: Path, filename: str, frontmatter: str) -> None:
    """Write a backlog item with the given YAML frontmatter body."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        f"---\n{frontmatter}---\n\nBody.\n", encoding="utf-8"
    )


class _CorpusTestCase(unittest.TestCase):
    """Base class supplying a throwaway corpus and a lifecycle-free root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.backlog_dir = root / "backlog"
        self.backlog_dir.mkdir()
        # Deliberately absent: with no lifecycle directory every phase comes
        # from raw frontmatter, which is the path the null spellings live on.
        self.lifecycle_dir = root / "lifecycle"

    def build(self, titles_by_id=None, polled_ts="2026-07-27T00:00:00+00:00"):
        return build_backlog_snapshot(
            self.backlog_dir, self.lifecycle_dir, titles_by_id or {}, polled_ts
        )


class TestSnapshotSchema(_CorpusTestCase):
    """The pinned envelope (R3)."""

    def test_key_set_is_exact(self):
        _write_item(self.backlog_dir, "001-alpha.md", "title: Alpha\nstatus: backlog\n")

        snapshot = self.build()

        self.assertEqual(sorted(snapshot.keys()), EXPECTED_KEYS)

    def test_schema_version_is_pinned(self):
        snapshot = self.build()

        self.assertEqual(snapshot["schema_version"], "1")

    def test_polled_ts_is_the_caller_supplied_value(self):
        """The builder never stamps its own clock, so only a real poll can."""
        snapshot = self.build(polled_ts="2026-01-01T12:00:00+00:00")

        self.assertEqual(snapshot["polled_ts"], "2026-01-01T12:00:00+00:00")
        self.assertFalse(snapshot["stale"])

    def test_item_carries_every_documented_key(self):
        _write_item(
            self.backlog_dir,
            "042-beta.md",
            "title: Beta\nstatus: backlog\npriority: high\ntype: feature\n",
        )

        snapshot = self.build()

        self.assertEqual(set(snapshot["items"]["42"]), EXPECTED_ITEM_KEYS)

    def test_items_resolve_by_subscript(self):
        """#413 resolves one ticket per request; a scan would be the wrong shape."""
        _write_item(self.backlog_dir, "007-gamma.md", "title: Gamma\nstatus: backlog\n")

        snapshot = self.build()

        self.assertEqual(snapshot["items"]["7"]["title"], "Gamma")
        self.assertIsInstance(snapshot["items"], dict)

    def test_item_order_preserves_priority_then_id(self):
        _write_item(self.backlog_dir, "001-low.md", "title: Low\nstatus: backlog\npriority: low\n")
        _write_item(self.backlog_dir, "009-high.md", "title: High\nstatus: backlog\npriority: high\n")
        _write_item(self.backlog_dir, "005-high.md", "title: Mid\nstatus: backlog\npriority: high\n")

        snapshot = self.build()

        self.assertEqual(snapshot["item_order"], ["5", "9", "1"])

    def test_absent_corpus_yields_a_complete_envelope(self):
        """An empty corpus is a populated snapshot — not None, not partial."""
        snapshot = build_backlog_snapshot(
            self.backlog_dir / "nope", self.lifecycle_dir, {}, "T"
        )

        self.assertEqual(sorted(snapshot.keys()), EXPECTED_KEYS)
        self.assertEqual(snapshot["items"], {})
        self.assertEqual(snapshot["counts"], {"active": 0, "archived": 0})


class TestActiveArchiveSplit(_CorpusTestCase):
    """The landscape strip's only source for the split (R4)."""

    def test_archive_reaches_counts_and_ids(self):
        _write_item(self.backlog_dir, "001-active.md", "title: Active\nstatus: backlog\n")
        archive = self.backlog_dir / "archive"
        _write_item(archive, "100-old.md", "title: Old\nstatus: complete\n")
        _write_item(archive, "101-older.md", "title: Older\nstatus: complete\n")

        snapshot = self.build()

        self.assertEqual(snapshot["counts"]["archived"], 2)
        self.assertEqual(snapshot["counts"]["archived"], len(snapshot["archive_ids"]))
        self.assertEqual(snapshot["archive_ids"], [100, 101])
        self.assertEqual(snapshot["active_ids"], [1])
        self.assertEqual(snapshot["counts"]["active"], 1)

    def test_absent_archive_is_zero_not_missing(self):
        _write_item(self.backlog_dir, "001-active.md", "title: Active\nstatus: backlog\n")

        snapshot = self.build()

        self.assertEqual(snapshot["archive_ids"], [])
        self.assertEqual(snapshot["counts"]["archived"], 0)


class TestUnknownItemSchemaVersion(_CorpusTestCase):
    """A future schema bump must not permanently kill the poll (R9)."""

    def test_future_schema_version_does_not_raise_or_warn(self):
        _write_item(
            self.backlog_dir,
            '001-future.md',
            'title: Future\nstatus: backlog\nschema_version: "2"\n',
        )

        with self.assertNoLogs():
            snapshot = self.build()

        self.assertIn("1", snapshot["items"])
        self.assertEqual(snapshot["items"]["1"]["schema_version"], "2")


class TestDeferralFlags(_CorpusTestCase):
    """Two flags, never one collapsed boolean (R12)."""

    def test_tag_deferred_item_is_still_ready(self):
        """The readiness partition does not read tags; a view must badge it."""
        _write_item(
            self.backlog_dir,
            "001-tagged.md",
            "title: Tagged\nstatus: backlog\ntags: [deferred]\n",
        )

        snapshot = self.build()

        self.assertTrue(snapshot["items"]["1"]["deferred_tag"])
        self.assertFalse(snapshot["items"]["1"]["deferred_status"])
        self.assertIn("1", snapshot["ready"])

    def test_status_deferred_item_is_ineligible(self):
        _write_item(self.backlog_dir, "002-status.md", "title: S\nstatus: deferred\n")

        snapshot = self.build()

        self.assertTrue(snapshot["items"]["2"]["deferred_status"])
        self.assertFalse(snapshot["items"]["2"]["deferred_tag"])
        self.assertNotIn("2", snapshot["ready"])
        reasons = {entry["id"]: entry for entry in snapshot["ineligible"]}
        self.assertEqual(reasons["2"]["kind"], "status")

    def test_tag_match_is_case_normalized_and_whole_element(self):
        _write_item(
            self.backlog_dir,
            "003-mixed.md",
            "title: M\nstatus: backlog\ntags: [Deferred]\n",
        )
        _write_item(
            self.backlog_dir,
            "004-partial.md",
            "title: P\nstatus: backlog\ntags: [deferred-later]\n",
        )

        snapshot = self.build()

        self.assertTrue(snapshot["items"]["3"]["deferred_tag"])
        self.assertFalse(snapshot["items"]["4"]["deferred_tag"])


class TestBlockedWhy(_CorpusTestCase):
    """Blockers resolved to status and title, three ways (R13)."""

    def test_terminal_blocker_resolves_to_status_and_title(self):
        _write_item(
            self.backlog_dir,
            "001-blocked.md",
            "title: Blocked\nstatus: backlog\nblocked-by: [228]\n",
        )
        _write_item(self.backlog_dir, "228-done.md", "title: Done Work\nstatus: complete\n")

        snapshot = self.build(titles_by_id={"228": "Done Work"})

        self.assertEqual(
            snapshot["blocked_why"]["1"],
            [{"ref": "228", "kind": "internal", "status": "complete", "title": "Done Work"}],
        )

    def test_unknown_title_is_null_not_blank(self):
        """An archived blocker has no title; a view renders id and status."""
        _write_item(
            self.backlog_dir,
            "001-blocked.md",
            "title: Blocked\nstatus: backlog\nblocked-by: [100]\n",
        )
        _write_item(self.backlog_dir / "archive", "100-gone.md", "title: Gone\nstatus: complete\n")

        snapshot = self.build()

        entry = snapshot["blocked_why"]["1"][0]
        self.assertEqual(entry["kind"], "internal")
        self.assertEqual(entry["status"], "complete")
        self.assertIsNone(entry["title"])

    def test_three_way_split_is_preserved(self):
        _write_item(
            self.backlog_dir,
            "001-multi.md",
            "title: Multi\nstatus: backlog\n"
            "blocked-by: [002, 11111111-2222-3333-4444-555555555555, some-external-thing]\n",
        )
        _write_item(self.backlog_dir, "002-real.md", "title: Real\nstatus: backlog\n")

        snapshot = self.build(titles_by_id={"2": "Real"})

        kinds = {entry["ref"]: entry["kind"] for entry in snapshot["blocked_why"]["1"]}
        self.assertEqual(kinds["002"], "internal")
        self.assertEqual(kinds["11111111-2222-3333-4444-555555555555"], "not_found")
        self.assertEqual(kinds["some-external-thing"], "external")

    def test_unblocked_items_are_absent_from_the_map(self):
        _write_item(self.backlog_dir, "001-free.md", "title: Free\nstatus: backlog\n")

        snapshot = self.build()

        self.assertEqual(snapshot["blocked_why"], {})


class TestPhaseNormalization(_CorpusTestCase):
    """Every null spelling collapses; everything else passes through (R14)."""

    def test_all_null_spellings_collapse_to_one_value(self):
        spellings = {
            "001": "lifecycle_phase: none\n",
            "002": "lifecycle_phase: None\n",
            "003": "lifecycle_phase: NONE\n",
            "004": "lifecycle_phase: null\n",
            "005": "lifecycle_phase: nil\n",
            "006": "lifecycle_phase: ~\n",
            "007": "lifecycle_phase:\n",
            "008": "",  # key absent entirely
        }
        for num, line in spellings.items():
            _write_item(
                self.backlog_dir, f"{num}-item.md", f"title: Item {num}\nstatus: backlog\n{line}"
            )

        snapshot = self.build()

        phases = {
            item_id: snapshot["items"][item_id]["phase"] for item_id in snapshot["items"]
        }
        self.assertEqual(set(phases.values()), {None}, phases)

    def test_out_of_vocabulary_phase_passes_through_verbatim(self):
        """The phase vocabulary is open on the raw-frontmatter path."""
        _write_item(
            self.backlog_dir,
            "001-odd.md",
            "title: Odd\nstatus: backlog\nlifecycle_phase: wontfix\n",
        )

        snapshot = self.build()

        self.assertEqual(snapshot["items"]["1"]["phase"], "wontfix")


class TestMarkSnapshotStale(unittest.TestCase):
    """Retention on fault is a copy, and it never advances the timestamp."""

    def test_none_stays_none(self):
        self.assertIsNone(mark_snapshot_stale(None))

    def test_prior_is_copied_not_mutated(self):
        prior = {"stale": False, "polled_ts": "T0", "items": {}}

        marked = mark_snapshot_stale(prior)

        self.assertTrue(marked["stale"])
        self.assertEqual(marked["polled_ts"], "T0")
        self.assertFalse(prior["stale"], "the original must be left untouched")
        self.assertIsNot(marked, prior)

    def test_marking_twice_is_idempotent(self):
        once = mark_snapshot_stale({"stale": False, "polled_ts": "T0"})

        twice = mark_snapshot_stale(once)

        self.assertTrue(twice["stale"])
        self.assertEqual(twice["polled_ts"], "T0")


class TestImportSurface(unittest.TestCase):
    """This module is the dashboard's first dependency on the overnight package.

    That package's __init__ eagerly imports its orchestrator chain, so this
    module's import graph now spans code whose own dependencies live behind
    an optional extra. A dashboard-only install must still be able to import
    it; this test fails the moment that stops being true.
    """

    def test_imports_without_the_optional_agent_sdk(self):
        probe = (
            "import builtins\n"
            "_real = builtins.__import__\n"
            "def _guard(name, *args, **kwargs):\n"
            "    if name.split('.')[0] == 'claude_agent_sdk':\n"
            "        raise ModuleNotFoundError(\"No module named 'claude_agent_sdk'\")\n"
            "    return _real(name, *args, **kwargs)\n"
            "builtins.__import__ = _guard\n"
            "from cortex_command.dashboard.ticket_feed import build_backlog_snapshot\n"
            "print('ok')\n"
        )

        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True
        )

        self.assertEqual(
            result.returncode, 0,
            f"dashboard-only install can no longer import the feed:\n{result.stderr}",
        )
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
