"""Unit tests for cortex_command/dashboard/seed.py.

The seeder is a shipped console script that used to write fixtures into the
operator's own repository, so the properties under test here are containment
properties first:

  - ``write_all`` writes under the root it is handed and nowhere else — no
    writer resolves the project root on its own any more (R3)
  - a seed-then-clean cycle returns a fresh root to its exact prior listing,
    directories included, so no orphaned ``exit-reports/``, ``learnings/``,
    feature or session directory survives (R5)
  - the one-time legacy sweep removes the five backlog fixture files a
    pre-containment seed run left in a project repository, leaves real tickets
    alone, and refuses to delete a git-tracked match (R7)

…and then corpus properties, read back through the real feed layer rather
than off the fixture table (R11, R17): ``build_backlog_snapshot`` computes
``phase``, ``deferred_status``, ``deferred_tag``, and the blocker kind/title
joins that nothing in ``collect_items`` produces, so a corpus that diverges
from what the feed expects is only visible from this side of the call.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from cortex_command.dashboard import seed as seed_module
from cortex_command.dashboard.poller import _resolve_session_path
from cortex_command.dashboard.seed import (
    SEED_PREFIX,
    clean_all,
    sweep_legacy_backlog,
    write_all,
    write_seed_marker,
)
from cortex_command.dashboard.ticket_feed import build_backlog_snapshot

# Imported rather than re-derived: the pinned R3 key set has exactly one
# definition, so #411 changing its snapshot surfaces here as a failure of
# this corpus instead of as two lists drifting quietly apart.
from cortex_command.dashboard.tests.test_ticket_feed import EXPECTED_KEYS

#: Deterministic stand-in for the module's wall-clock ``SESSION_ID``. It must
#: carry ``SEED_PREFIX`` because that prefix is how ``clean_all`` recognises a
#: session directory as its own.
SESSION_ID = f"{SEED_PREFIX}-2026-01-01-0000"

#: The five filenames the pre-containment seeder wrote into a real
#: ``cortex/backlog/`` (this repository carried exactly these until they were
#: untracked by hand in ``0040d55c``).
LEGACY_FIXTURES = [
    "990-seed-feature-alpha.md",
    "991-seed-feature-beta.md",
    "992-seed-feature-gamma.md",
    "993-seed-feature-delta.md",
    "994-seed-feature-epsilon.md",
]


def _listing(root: Path) -> list[str]:
    """Return every path under ``root`` — files *and* directories — sorted."""
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


class _RootTestCase(unittest.TestCase):
    """Base class supplying a fresh, empty fixture root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "fixture-root"
        self.root.mkdir()

    def seed(self, root: Path) -> None:
        """Run the writers against ``root``, swallowing their progress output."""
        with redirect_stdout(io.StringIO()):
            write_seed_marker(root)
            write_all(root, SESSION_ID)


class TestContainment(_RootTestCase):
    """Everything the writers write lands under the root they were handed (R3)."""

    def test_write_all_creates_no_path_outside_its_root(self):
        # Two decoys, each on a funnel a writer could reach the real repository
        # through: XDG_STATE_HOME feeds _resolve_fixture_root, CORTEX_REPO_ROOT
        # feeds _resolve_user_project_root. Both must stay untouched.
        xdg_home = self.tmp / "xdg-state"
        project_root = self.tmp / "project-root"
        xdg_home.mkdir()
        project_root.mkdir()

        with mock.patch.dict(
            os.environ,
            {"XDG_STATE_HOME": str(xdg_home), "CORTEX_REPO_ROOT": str(project_root)},
        ):
            self.seed(self.root)

        self.assertEqual(_listing(xdg_home), [])
        self.assertEqual(_listing(project_root), [])
        # …and the fixtures really were written, so the emptiness above is not
        # the vacuous result of the writers doing nothing at all.
        self.assertTrue(
            (self.root / "cortex" / "lifecycle" / "overnight-state.json").is_file()
        )
        self.assertTrue(
            (self.root / "cortex" / "lifecycle" / "sessions" / SESSION_ID).is_dir()
        )
        self.assertTrue(any((self.root / "cortex" / "backlog").glob("*.md")))

    def test_only_the_cli_entry_resolves_the_project_root(self):
        # The decoy above only proves containment for the funnel it patches; a
        # writer that resolved the project root some other way would slip past
        # it. Pin the count instead: one reference, in the --sweep-legacy path.
        source = Path(seed_module.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count("_resolve_user_project_root"), 1)


class TestLatestOvernightPointer(_RootTestCase):
    """The seeded session is reachable through the pointer the poller reads."""

    def _pointer(self, root: Path) -> Path:
        return root / "cortex" / "lifecycle" / "sessions" / "latest-overnight"

    def test_seed_publishes_a_pointer_the_poller_resolves(self):
        # The regression: the seeder wrote overnight-state.json to the session
        # directory and to cortex/lifecycle/, but _resolve_session_path reads
        # neither — absent the ~/.local/share pointer it falls back to
        # sessions/latest-overnight/ and nothing else. So `just dashboard-demo`
        # rendered an idle, sessionless dashboard over a full fixture corpus.
        self.seed(self.root)
        pointer = self._pointer(self.root)
        self.assertTrue(pointer.is_symlink(), "seeder published no pointer")
        # Relative, so the fixture root stays movable.
        self.assertEqual(os.readlink(pointer), SESSION_ID)
        self.assertTrue((pointer / "overnight-state.json").is_file())
        self.assertTrue((pointer / "overnight-events.log").is_file())

    def test_the_pointer_resolves_the_same_state_the_dashboard_renders(self):
        # Pin the actual consumer, not just the link's existence: the poller's
        # resolver must land on the seeded session's real state file.
        self.seed(self.root)
        # _resolve_session_path prefers ~/.local/share/overnight-sessions's
        # pointer when it names an executing session. Redirect HOME at a bare
        # tmp dir so this asserts the fallback arm on every machine, including
        # a developer's with a live overnight session running.
        fake_home = self.tmp / "home"
        fake_home.mkdir()
        with mock.patch("pathlib.Path.home", return_value=fake_home):
            state_path, events_path = _resolve_session_path(self.root)
        self.assertTrue(state_path.is_file())
        self.assertTrue(events_path.is_file())
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["session_id"], SESSION_ID)
        self.assertTrue(payload["features"], "resolved state names no features")

    def test_clean_removes_a_seed_pointer(self):
        self.seed(self.root)
        with redirect_stdout(io.StringIO()):
            clean_all(self.root)
        self.assertFalse(self._pointer(self.root).is_symlink())
        self.assertFalse(self._pointer(self.root).exists())

    def test_clean_leaves_a_pointer_into_a_real_session_alone(self):
        # --clean runs against whatever root it is handed, and a real repo
        # keeps the runner's own latest-overnight link at exactly this path.
        # Unlinking it would blind every reader that resolves through it.
        sessions = self.root / "cortex" / "lifecycle" / "sessions"
        real_session = sessions / "2026-07-29-real-work"
        real_session.mkdir(parents=True)
        (real_session / "overnight-state.json").write_text("{}", encoding="utf-8")
        pointer = self._pointer(self.root)
        pointer.symlink_to(real_session.name, target_is_directory=True)

        with redirect_stdout(io.StringIO()):
            clean_all(self.root)

        self.assertTrue(pointer.is_symlink())
        self.assertEqual(os.readlink(pointer), real_session.name)


class TestWriterCleanerSymmetry(_RootTestCase):
    """A seed/clean cycle is a round trip, asserted rather than assumed (R5)."""

    def test_clean_all_restores_the_prior_listing(self):
        before = _listing(self.root)
        self.assertEqual(before, [])

        self.seed(self.root)
        self.assertNotEqual(_listing(self.root), before)

        with redirect_stdout(io.StringIO()):
            clean_all(self.root)

        # Files *and* directories: an orphaned empty exit-reports/, learnings/,
        # feature or session directory — none of which written_paths records —
        # fails this equality.
        self.assertEqual(_listing(self.root), before)

    def test_clean_all_leaves_a_foreign_file_and_its_parents_alone(self):
        foreign = self.root / "cortex" / "lifecycle" / "real-work" / "spec.md"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("Not the seeder's.\n", encoding="utf-8")
        before = _listing(self.root)

        self.seed(self.root)
        with redirect_stdout(io.StringIO()):
            clean_all(self.root)

        self.assertEqual(_listing(self.root), before)
        self.assertTrue(foreign.is_file())


class TestLegacySweep(unittest.TestCase):
    """The one-time migration off the pre-containment seeder (R7)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self.backlog_dir = self.project_root / "cortex" / "backlog"
        self.backlog_dir.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "-q", str(self.project_root)],
            check=True,
            capture_output=True,
        )

    def write(self, name: str) -> Path:
        path = self.backlog_dir / name
        path.write_text(f"---\ntitle: {name}\n---\n\nBody.\n", encoding="utf-8")
        return path

    def track(self, path: Path) -> None:
        """Add ``path`` to the index, which is what ``git ls-files`` reports."""
        subprocess.run(
            ["git", "-C", str(self.project_root), "add", str(path)],
            check=True,
            capture_output=True,
        )

    def test_sweep_removes_untracked_fixtures_and_spares_the_tracked_one(self):
        real_ticket = self.write("229-foo.md")
        # A real ticket whose name merely starts with the same token as the
        # fixtures: the anchored pattern must not eat it.
        near_miss = self.write("230-seed-feature-flags.md")
        fixtures = [self.write(name) for name in LEGACY_FIXTURES]
        tracked = fixtures[0]
        self.track(tracked)

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            removed = sweep_legacy_backlog(self.project_root)

        self.assertEqual(
            removed,
            [f"cortex/backlog/{name}" for name in LEGACY_FIXTURES[1:]],
        )
        for path in fixtures[1:]:
            self.assertFalse(path.exists())
        self.assertTrue(tracked.exists())
        self.assertIn(tracked.name, stdout.getvalue())
        self.assertIn("git-tracked", stdout.getvalue())
        self.assertTrue(real_ticket.exists())
        self.assertTrue(near_miss.exists())

    def test_sweep_of_a_clean_repository_removes_nothing(self):
        self.write("229-foo.md")

        with redirect_stdout(io.StringIO()):
            removed = sweep_legacy_backlog(self.project_root)

        self.assertEqual(removed, [])
        self.assertTrue((self.backlog_dir / "229-foo.md").exists())


class TestFeedSnapshot(_RootTestCase):
    """The enriched corpus, read back through #411's snapshot builder (R11, R17).

    Every assertion here goes through ``build_backlog_snapshot`` with the
    signature the poller uses, because the states this corpus exists to cover
    are computed in that builder and appear nowhere in ``collect_items``.
    """

    #: The poller supplies the timestamp; the builder never stamps its own.
    POLLED_TS = "2026-01-01T00:00:00+00:00"

    def setUp(self):
        super().setUp()
        self.seed(self.root)
        self.snapshot = build_backlog_snapshot(
            self.root / "cortex" / "backlog",
            self.root / "cortex" / "lifecycle",
            titles_by_id={},
            polled_ts=self.POLLED_TS,
        )

    def blockers(self, item_id: str) -> list[dict]:
        """Return the ``blocked_why`` entries for ``item_id``.

        Blocker coverage is asserted from here rather than from readiness
        reason strings: a terminal internal blocker leaves the item ready with
        no reason at all, which is indistinguishable from a fixture that
        declares no blockers.
        """
        return self.snapshot["blocked_why"].get(item_id, [])

    def test_snapshot_over_the_seeded_root_carries_the_pinned_schema(self):
        # Equality, not containment: a key the corpus stops populating is the
        # regression the consuming views cannot defend themselves against.
        self.assertEqual(sorted(self.snapshot.keys()), EXPECTED_KEYS)
        self.assertEqual(self.snapshot["schema_version"], "1")
        self.assertEqual(self.snapshot["polled_ts"], self.POLLED_TS)
        self.assertFalse(self.snapshot["stale"])

    def test_snapshot_carries_an_epic_with_both_its_children(self):
        epics = self.snapshot["epics"]["epics"]

        self.assertIn("6", epics)
        self.assertEqual(
            sorted(child["id"] for child in epics["6"]["children"]), [7, 8]
        )

    def test_closed_epic_still_heads_a_group_for_its_live_child(self):
        """#458: an epic that closed before its last child must still group it.

        ``build_epic_map`` detects an epic by scanning the list it is handed for
        ``type: epic``. Handing it the *active* slice made 015 invisible as an
        epic, so 016's ``parent`` matched nothing and it fell into the flat
        Standalone list — asserting it had no parent when it plainly does.
        """
        epics = self.snapshot["epics"]["epics"]

        self.assertIn("15", epics)
        self.assertEqual([child["id"] for child in epics["15"]["children"]], [16])
        self.assertEqual(self.snapshot["items"]["15"]["status"], "complete")

    def test_closed_epic_heading_a_group_is_renderable_but_not_active(self):
        """It reaches ``items`` so the heading row renders, and stops there.

        The board's group heading *is* the epic's own ticket row, so a group
        with no record behind it renders blank rather than raising. But
        ``item_order`` is the board's active set — ``backlog_panel.html`` reads
        its length as the active count and the Standalone list is its
        complement — so a closed epic in there would both inflate the count and
        reappear as a standalone row.
        """
        self.assertIn("15", self.snapshot["items"])
        self.assertNotIn("15", self.snapshot["item_order"])
        self.assertNotIn(15, self.snapshot["active_ids"])
        self.assertEqual(
            self.snapshot["counts"]["active"], len(self.snapshot["item_order"])
        )

    def test_every_epic_key_and_child_id_resolves_in_items(self):
        """The map may name only ids the board can actually render.

        This is the invariant that makes full-corpus *detection* safe. A closed
        child, or an epic key with no record, subscripts to a Jinja
        ``Undefined`` and renders as a blank row instead of raising — the silent
        failure ``triage_board.html``'s docstring exists to prevent.
        """
        items = self.snapshot["items"]
        for epic_id, epic in self.snapshot["epics"]["epics"].items():
            self.assertIn(epic_id, items, f"epic {epic_id} has no record")
            for child in epic["children"]:
                self.assertIn(
                    str(child["id"]), items, f"child {child['id']} has no record"
                )

    def test_no_epic_carries_a_terminal_child(self):
        """Children are filtered to the active set, closed epics included.

        Terminal item 003 and archived 014 exist in the corpus; neither may
        reach a children list, or the board would render a blank row for it.
        """
        terminal_ids = {3, 14, 15}
        for epic in self.snapshot["epics"]["epics"].values():
            for child in epic["children"]:
                self.assertNotIn(child["id"], terminal_ids)

    def test_childless_closed_epics_do_not_seed_empty_groups(self):
        """Detection widened to the full corpus; the rendered set did not.

        Every finished epic in a mature repo would otherwise open a "no active
        children" group — 34 of them on cortex-command. Only a closed epic with
        live work in it earns a group; an *active* epic keeps its empty one,
        which is how the board says a live epic has nothing left in flight.
        """
        items = self.snapshot["items"]
        for epic_id, epic in self.snapshot["epics"]["epics"].items():
            if epic["children"]:
                continue
            self.assertIn(
                int(epic_id), self.snapshot["active_ids"],
                f"closed epic {epic_id} ({items[epic_id]['title']}) opened an "
                "empty group",
            )

    def test_snapshot_drops_a_child_whose_parent_is_not_an_epic(self):
        # 009 names 001 — a feature — as its parent, so the epic map drops the
        # relationship silently while the raw frontmatter keeps it.
        self.assertEqual(self.snapshot["items"]["9"]["parent"], "001")
        for epic in self.snapshot["epics"]["epics"].values():
            self.assertNotIn(9, [child["id"] for child in epic["children"]])

    def test_snapshot_reports_all_four_blocker_outcomes(self):
        # Internal, non-terminal: blocks 007 and is why it is ineligible.
        self.assertEqual(
            self.blockers("7"),
            [{
                "ref": "002",
                "kind": "internal",
                "status": "in_progress",
                "title": None,
            }],
        )
        # Internal, terminal: 008 is ready anyway, and the blocker is still
        # listed — the state that has no readiness-side signal at all.
        self.assertEqual(
            self.blockers("8"),
            [{"ref": "005", "kind": "internal", "status": "complete", "title": None}],
        )
        self.assertIn("8", self.snapshot["ready"])
        # External: a reference to work outside this backlog entirely.
        self.assertEqual(
            self.blockers("9"),
            [{
                "ref": "anthropics/claude-code#34243",
                "kind": "external",
                "status": None,
                "title": None,
            }],
        )
        # not_found: a well-formed UUID matching no item, which renders
        # differently from an external reference.
        self.assertEqual(
            self.blockers("10"),
            [{
                "ref": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "kind": "not_found",
                "status": None,
                "title": None,
            }],
        )

    def test_snapshot_reports_an_ineligible_item_of_kind_status(self):
        status_ineligible = [
            entry for entry in self.snapshot["ineligible"]
            if entry["kind"] == "status"
        ]

        self.assertEqual([entry["id"] for entry in status_ineligible], ["11"])

    def test_snapshot_carries_both_deferral_forms_independently(self):
        # A deferred *status*, which is also what makes 011 ineligible.
        deferred_status = self.snapshot["items"]["11"]
        self.assertTrue(deferred_status["deferred_status"])
        self.assertFalse(deferred_status["deferred_tag"])
        self.assertNotIn("11", self.snapshot["ready"])

        # A deferred *tag* at an eligible status: legitimately ready and
        # deferred at once, which a view must be able to badge distinctly.
        deferred_tag = self.snapshot["items"]["12"]
        self.assertFalse(deferred_tag["deferred_status"])
        self.assertTrue(deferred_tag["deferred_tag"])
        self.assertIn("12", self.snapshot["ready"])

    def test_snapshot_reports_a_non_null_phase_for_the_artifact_fixture(self):
        # 004 is the fixture whose lifecycle_slug resolves to a directory the
        # seeder really writes; phase exists only on the snapshot.
        self.assertEqual(self.snapshot["items"]["4"]["lifecycle_slug"],
                         "seed-feature-delta")
        self.assertIsNotNone(self.snapshot["items"]["4"]["phase"])
        # …and the dangling-artifact fixture is the counterexample: it names a
        # lifecycle slug the seeder deliberately never creates.
        self.assertIsNone(self.snapshot["items"]["13"]["phase"])

    def test_snapshot_carries_archive_ids_outside_the_active_set(self):
        self.assertTrue(self.snapshot["archive_ids"])
        self.assertEqual(
            self.snapshot["counts"]["archived"], len(self.snapshot["archive_ids"])
        )
        for archived_id in self.snapshot["archive_ids"]:
            self.assertNotIn(archived_id, self.snapshot["active_ids"])


if __name__ == "__main__":
    unittest.main()
