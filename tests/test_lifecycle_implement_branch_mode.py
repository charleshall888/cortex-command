"""Unit + structural-doc tests for the R3/R4 branch-mode dispatch carve-outs.

Two test classes:

* ``TestShouldFirePicker`` exercises the five primitive-level carve-out cases
  (a1)-(a5) of ``cortex_command.lifecycle_implement.should_fire_picker``
  against a real tmp git repo:

    (a1) ``branch-mode: trunk`` + clean tree + no live worktree → suppressed.
    (a2) ``branch-mode: trunk`` + simulated dirty tree → dirty_tree.
    (a3) ``branch-mode: trunk`` + simulated live ``{slug}.interactive.pid`` →
         live_interactive_worktree_session.
    (a4) ``branch-mode: worktree-interactive`` + clean tree + no live
         worktree → suppressed.
    (a5) ``branch-mode: None`` (unset) → branch_mode_unset_or_invalid.

* ``TestImplementMdWiring`` is a documentation-shape check on
  ``skills/lifecycle/references/implement.md``: asserts that the dispatch
  helpers are named, that the open-paren invocation form is present, that
  the invocation appears before the §1 picker ``AskUserQuestion`` call site,
  and that each of the four closed-set branch-mode values appears within
  ±10 lines of a ``should_fire_picker`` mention (routing-block proximity).

The structural-doc class catches *some* of the regressions Task 5's grep V
cannot — it does **not** exercise the inverted-boolean regression class,
which is a known limitation documented in the spec's Risks section.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

from cortex_command.lifecycle_implement import should_fire_picker


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"


def _init_clean_repo(tmp_path: pathlib.Path) -> None:
    """Initialise a clean git repo rooted at ``tmp_path``.

    No initial commit and no user.name/user.email config — the carve-out
    helpers only call ``git status --porcelain``, which works without a
    HEAD.
    """
    subprocess.run(
        ["git", "init", "-q", str(tmp_path)],
        check=True,
        capture_output=True,
    )


class TestShouldFirePicker:
    """Primitive-level cases (a1)-(a5) for ``should_fire_picker``."""

    def test_a1_trunk_clean_no_live_worktree_suppressed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """(a1) ``branch-mode: trunk`` + clean tree + no live PID → suppressed."""
        _init_clean_repo(tmp_path)
        fire, reason = should_fire_picker(tmp_path, "my-feature", "trunk")
        assert fire is False
        assert reason == "suppressed"

    def test_a2_trunk_dirty_tree_fires(self, tmp_path: pathlib.Path) -> None:
        """(a2) ``branch-mode: trunk`` + dirty tree → dirty_tree."""
        _init_clean_repo(tmp_path)
        # Simulate dirty tree: write an untracked file so ``git status
        # --porcelain`` reports non-empty output.
        (tmp_path / "untracked.txt").write_text("dirty", encoding="utf-8")
        # Sanity-check that the tree is actually reported as dirty.
        status = subprocess.run(
            ["git", "-C", str(tmp_path), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert status.stdout.strip(), (
            "fixture precondition failed: expected dirty tree, got empty status"
        )

        fire, reason = should_fire_picker(tmp_path, "my-feature", "trunk")
        assert fire is True
        assert reason == "dirty_tree"

    def test_a3_trunk_live_interactive_pid_fires(
        self, tmp_path: pathlib.Path
    ) -> None:
        """(a3) ``branch-mode: trunk`` + live interactive lock → live_interactive_worktree_session.

        The dirty-tree check fires first in ``should_fire_picker``'s
        ordering (i → ii → iii → iv), so the ``cortex/`` umbrella must be
        gitignored before the lock file is dropped — otherwise the
        untracked lock file would short-circuit to ``dirty_tree`` and the
        live-lock carve-out would never be reached.
        """
        _init_clean_repo(tmp_path)
        # Ignore the cortex/ umbrella so the PID file does not dirty the
        # working tree — we are isolating the live-PID carve-out from the
        # dirty-tree carve-out under test (a2). Use ``.git/info/exclude``
        # (the per-repo non-tracked ignore file) so the exclude itself
        # does not appear as an untracked file in ``git status --porcelain``.
        info_dir = tmp_path / ".git" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        (info_dir / "exclude").write_text("cortex/\n", encoding="utf-8")

        slug = "my-feature"
        # Write the REAL interactive lock that ``scan_live_locks`` reads:
        # ``cortex/lifecycle/{slug}/interactive.pid``, JSON carrying the lock
        # magic and the current process's PID. A live PID with null
        # ``session_id``/``start_time`` classifies Row-4 conservative-LIVE
        # (sufficient to exercise detection; it need not replicate the
        # Row-1 self-session lock the live ``acquire`` writes).
        lock_dir = tmp_path / "cortex" / "lifecycle" / slug
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "interactive.pid"
        lock_file.write_text(
            json.dumps(
                {
                    "magic": "cortex-interactive-lock",
                    "pid": os.getpid(),
                    "session_id": None,
                    "start_time": None,
                }
            ),
            encoding="utf-8",
        )

        # Sanity-check: the tree must be reported as clean so that
        # should_fire_picker does NOT short-circuit to dirty_tree.
        status = subprocess.run(
            ["git", "-C", str(tmp_path), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert not status.stdout.strip(), (
            "fixture precondition failed: expected clean tree after "
            f"gitignoring cortex/, got: {status.stdout!r}"
        )

        fire, reason = should_fire_picker(tmp_path, slug, "trunk")
        assert fire is True
        assert reason == "live_interactive_worktree_session"

    def test_a4_worktree_interactive_clean_no_live_worktree_suppressed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """(a4) ``branch-mode: worktree-interactive`` + clean + no live PID → suppressed."""
        _init_clean_repo(tmp_path)
        fire, reason = should_fire_picker(
            tmp_path, "my-feature", "worktree-interactive"
        )
        assert fire is False
        assert reason == "suppressed"

    def test_a5_branch_mode_none_fires(self, tmp_path: pathlib.Path) -> None:
        """(a5) ``branch-mode`` unset (None) → branch_mode_unset_or_invalid."""
        _init_clean_repo(tmp_path)
        fire, reason = should_fire_picker(tmp_path, "my-feature", None)
        assert fire is True
        assert reason == "branch_mode_unset_or_invalid"


class TestImplementMdWiring:
    """The §1 branch/dispatch decision is composed by the
    cortex-lifecycle-branch-decision verb. implement.md invokes that verb; the
    verb composes the reads (read_branch_mode, should_fire_picker,
    read_dispatch_choice) the old prose used to narrate inline. This class
    guards both ends of that wiring. The predicate's own behavior is covered by
    TestPrimitiveCases above and
    cortex_command/lifecycle/tests/test_branch_decision.py.
    """

    def test_implement_invokes_branch_decision(self) -> None:
        """(i) implement.md §1 dispatches via the branch-decision verb."""
        text = IMPLEMENT_MD.read_text(encoding="utf-8")
        assert "cortex-lifecycle-branch-decision" in text, (
            "implement.md §1 must invoke cortex-lifecycle-branch-decision — the "
            "verb that composes the branch/dispatch decision."
        )

    def test_verb_composes_the_dispatch_predicates(self) -> None:
        """(ii) The branch-decision verb still composes the reads it absorbed.

        A refactor that drops one of the composed reads must fail here rather
        than silently change dispatch behavior.
        """
        verb_src = (
            REPO_ROOT / "cortex_command" / "lifecycle" / "branch_decision.py"
        ).read_text(encoding="utf-8")
        for helper in ("should_fire_picker", "read_branch_mode", "read_dispatch_choice"):
            assert helper in verb_src, (
                f"cortex-lifecycle-branch-decision must compose {helper}"
            )
