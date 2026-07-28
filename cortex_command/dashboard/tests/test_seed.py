"""Unit tests for cortex_command/dashboard/seed.py.

The seeder is a shipped console script that used to write fixtures into the
operator's own repository, so the properties under test here are containment
properties first and fixture-content properties not at all:

  - ``write_all`` writes under the root it is handed and nowhere else — no
    writer resolves the project root on its own any more (R3)
  - a seed-then-clean cycle returns a fresh root to its exact prior listing,
    directories included, so no orphaned ``exit-reports/``, ``learnings/``,
    feature or session directory survives (R5)
  - the one-time legacy sweep removes the five backlog fixture files a
    pre-containment seed run left in a project repository, leaves real tickets
    alone, and refuses to delete a git-tracked match (R7)
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from cortex_command.dashboard import seed as seed_module
from cortex_command.dashboard.seed import (
    SEED_PREFIX,
    clean_all,
    sweep_legacy_backlog,
    write_all,
    write_seed_marker,
)

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


if __name__ == "__main__":
    unittest.main()
