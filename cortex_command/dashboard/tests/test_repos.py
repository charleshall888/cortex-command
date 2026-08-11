"""The repo registry, and the routing that keeps two repos from bleeding together.

The failure this file exists to prevent is not a crash. A dashboard serving two
checkouts renders a plausible page either way; the bug is that the page is about
the wrong repository, and nothing on it says so. So the assertions here are
mostly about *identity* — which root a request resolved, which state it read,
which repo a link points back at — rather than about anything being present.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cortex_command.dashboard.backlog.view import scope_links
from cortex_command.dashboard.repos import (
    ROOTS_ENV,
    RepoRegistry,
    build_registry,
    resolve_roots,
    slugify_root,
)


class TestSlugs(unittest.TestCase):
    def test_directory_name_becomes_the_slug(self):
        self.assertEqual("wild-light", slugify_root(Path("/x/wild-light")))

    def test_punctuation_folds_to_dashes(self):
        # The slug rides in a query string, so it has to be URL-safe whatever
        # the directory is called.
        self.assertEqual("my-repo-v2", slugify_root(Path("/x/My_Repo.v2")))
        self.assertEqual("a-b", slugify_root(Path("/x/  a  b  ")))

    def test_a_nameless_root_still_gets_a_slug(self):
        # "/" has an empty name; a blank slug would produce ?repo= and resolve
        # to the default, silently making a tracked repo unreachable.
        self.assertTrue(slugify_root(Path("/")))

    def test_colliding_names_get_distinct_slugs(self):
        """Two checkouts can share a directory name.

        A worktree beside its origin, or the same project under two parents.
        A colliding slug would make the second repo's state overwrite the
        first's in the registry, so both switcher entries would show one repo.
        """
        registry = build_registry([Path("/a/proj"), Path("/b/proj")])
        slugs = [repo.slug for repo in registry.repos]
        self.assertEqual(len(set(slugs)), 2)
        self.assertEqual(["proj", "proj-2"], slugs)
        # The label stays the human name in both cases; the slug is plumbing.
        self.assertEqual(["proj", "proj"], [repo.label for repo in registry.repos])


class TestResolveRoots(unittest.TestCase):
    def test_primary_is_kept_even_without_a_cortex_directory(self):
        """A freshly-initialised repo is a legitimate thing to point at.

        Dropping it would leave the process serving nothing at all.
        """
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / "brand-new"
            primary.mkdir()
            self.assertEqual([primary.resolve()], resolve_roots(primary))

    def test_extra_roots_that_do_not_exist_are_dropped(self):
        # These are typos, not empty repos, and a switcher entry leading to a
        # permanently blank page is worse than no entry.
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp)
            roots = resolve_roots(primary, ["/nonexistent/definitely/not/here"])
            self.assertEqual([primary.resolve()], roots)

    def test_duplicates_collapse_and_order_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            roots = resolve_roots(a, [str(b), str(a)])
            self.assertEqual([a.resolve(), b.resolve()], roots)

    def test_env_roots_are_read_and_compose_with_explicit_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, c = (Path(tmp) / n for n in ("a", "b", "c"))
            for p in (a, b, c):
                p.mkdir()
            with mock.patch.dict(os.environ, {ROOTS_ENV: str(c)}):
                roots = resolve_roots(a, [str(b)])
            self.assertEqual([a.resolve(), b.resolve(), c.resolve()], roots)


class TestRegistryResolution(unittest.TestCase):
    def setUp(self):
        self.registry = build_registry([Path("/x/alpha"), Path("/x/beta")])

    def test_unknown_slug_falls_back_to_the_default(self):
        """The slug arrives from a query string, so it is typo-reachable.

        A 500 on a bad one would be a worse answer than the page the operator
        was already looking at.
        """
        self.assertEqual("alpha", self.registry.resolve("nope").slug)
        self.assertEqual("alpha", self.registry.resolve(None).slug)
        self.assertEqual("alpha", self.registry.resolve("").slug)

    def test_known_slug_resolves_to_its_own_repo(self):
        self.assertEqual(Path("/x/beta"), self.registry.resolve("beta").root)

    def test_each_repo_gets_its_own_state(self):
        a = self.registry.state_for(self.registry.resolve("alpha"))
        b = self.registry.state_for(self.registry.resolve("beta"))
        self.assertIsNot(a, b)
        a.backlog_snapshot = {"items": {}}
        self.assertIsNone(b.backlog_snapshot)

    def test_state_is_stable_across_lookups(self):
        # A fresh state per request would discard the poll on every render.
        first = self.registry.state_for(self.registry.resolve("beta"))
        second = self.registry.state_for(self.registry.resolve("beta"))
        self.assertIs(first, second)

    def test_single_repo_reports_not_multi(self):
        # The switcher is suppressed here, which is what keeps the one-repo
        # page byte-identical to what it rendered before the registry existed.
        self.assertFalse(build_registry([Path("/x/only")]).multi)
        self.assertTrue(self.registry.multi)

    def test_empty_registry_answers_without_raising(self):
        # What a template test or any importer that never ran the lifespan gets.
        empty = RepoRegistry()
        self.assertIsNone(empty.default)
        self.assertIsNone(empty.resolve("anything"))
        self.assertFalse(empty.multi)
        self.assertIsNotNone(empty.state_for(None))


class TestScopeLinks(unittest.TestCase):
    """Every href in a view-model carries the repo it belongs to.

    Done as a walk over the finished model rather than at the seven places a
    ticket URL is built, because a missed site renders a link that works and
    points at another repository's ticket. The band, pick, frame and tail
    templates are macro libraries imported without ``with context``, so they
    cannot do this job at all — a page-level variable is Undefined inside them
    and renders as the empty string.
    """

    def test_nested_hrefs_are_all_scoped(self):
        model = {
            "pick": {"id": "1", "href": "/tickets/1"},
            "bands": [
                {"rows": [{"href": "/tickets/2", "blockers": [{"href": "/tickets/3"}]}]}
            ],
        }
        got = scope_links(model, "?repo=beta")
        self.assertEqual("/tickets/1?repo=beta", got["pick"]["href"])
        self.assertEqual(
            "/tickets/2?repo=beta", got["bands"][0]["rows"][0]["href"]
        )
        self.assertEqual(
            "/tickets/3?repo=beta",
            got["bands"][0]["rows"][0]["blockers"][0]["href"],
        )

    def test_empty_suffix_returns_the_model_untouched(self):
        # The single-repo case must not rewrite anything at all.
        model = {"href": "/tickets/1"}
        self.assertIs(model, scope_links(model, ""))

    def test_non_href_keys_and_empty_hrefs_are_left_alone(self):
        model = {"href": "", "title": "/tickets/9 mentioned in prose", "id": "9"}
        got = scope_links(model, "?repo=x")
        self.assertEqual("", got["href"])
        self.assertEqual("/tickets/9 mentioned in prose", got["title"])


if __name__ == "__main__":
    unittest.main()
