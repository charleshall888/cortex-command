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
        """(a3) ``branch-mode: trunk`` + live interactive PID → live_interactive_worktree_session.

        The dirty-tree check fires first in ``should_fire_picker``'s
        ordering (i → ii → iii → iv), so the sessions directory must be
        gitignored before the PID file is dropped — otherwise the
        untracked PID file would short-circuit to ``dirty_tree`` and the
        live-PID carve-out would never be reached.
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
        sessions_dir = tmp_path / "cortex" / "lifecycle" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # Use the current process's PID — ``os.kill(os.getpid(), 0)`` always
        # succeeds, so the liveness check inside ``should_fire_picker`` will
        # treat the session as live.
        pid_file = sessions_dir / f"{slug}.interactive.pid"
        pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")

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
    """Structural-doc check that implement.md wires the dispatch helpers correctly.

    Reads ``skills/lifecycle/references/implement.md`` directly, splits into
    lines, and applies regex/proximity checks. Documentation-shape testing;
    does not exercise the inverted-boolean regression class.
    """

    @pytest.fixture(scope="class")
    def implement_lines(self) -> list[str]:
        """Cache the implement.md content as a list of lines for the class."""
        return IMPLEMENT_MD.read_text(encoding="utf-8").splitlines()

    def test_helpers_named(self, implement_lines: list[str]) -> None:
        """(i) Both ``read_branch_mode`` and ``should_fire_picker`` are named."""
        text = "\n".join(implement_lines)
        assert "read_branch_mode" in text, (
            "implement.md must name the read_branch_mode helper"
        )
        assert "should_fire_picker" in text, (
            "implement.md must name the should_fire_picker helper"
        )

    def test_should_fire_picker_invocation_present(
        self, implement_lines: list[str]
    ) -> None:
        """(ii) An invocation form of ``should_fire_picker`` appears at least once.

        Historically the implement.md dispatch used the Python open-paren
        form ``should_fire_picker(...)``. After the convert-bin migration
        (see the spec under "Changes to Existing Behavior" line 109; the
        lifecycle slug is mentioned without code formatting here to keep
        the parity-check from flagging a substring as drift), the Python
        ``python3 -c`` snippet was replaced with the
        ``cortex-lifecycle-picker-decision`` console-script. Either form
        satisfies the "dispatch must actually call the predicate" intent
        — the console-script's ``main()`` calls ``should_fire_picker``
        directly.
        """
        invocations = [
            idx
            for idx, line in enumerate(implement_lines)
            if "should_fire_picker(" in line
            or "cortex-lifecycle-picker-decision" in line
        ]
        assert invocations, (
            "implement.md must invoke should_fire_picker(...) — either via "
            "the open-paren Python form or via the "
            "cortex-lifecycle-picker-decision CLI (which calls the predicate "
            "in its main()). Citation of the helper name alone is insufficient."
        )

    def test_invocation_before_picker_askuserquestion(
        self, implement_lines: list[str]
    ) -> None:
        """(iii) The picker invocation precedes the §1 picker AskUserQuestion anchor.

        The picker call site is the AskUserQuestion mention that the
        dispatch routes to — i.e. the first AskUserQuestion occurrence
        located at or after the §1 ``Branch-mode dispatch preflight``
        block (anchored on the dispatch-helper invocation line). The
        descriptive prose at the top of §1 ("prompt the user via
        AskUserQuestion with three options:") is the section heading
        rather than the call site the dispatch gates.

        Accepts either the legacy ``should_fire_picker(`` Python form or
        the new ``cortex-lifecycle-picker-decision`` CLI form (post the
        convert-bin migration, spec line 109). For the dispatch anchor,
        accepts either ``read_branch_mode`` (Python form) or
        ``cortex-lifecycle-branch-mode`` (CLI form).
        """
        # Locate the dispatch preflight anchor — prefer the open-paren
        # Python form, then fall back to the CLI form, then to any
        # mention of the dispatch helper.
        dispatch_anchor: int | None = None
        for idx, line in enumerate(implement_lines):
            if "read_branch_mode" in line and "(" in line:
                dispatch_anchor = idx
                break
        if dispatch_anchor is None:
            for idx, line in enumerate(implement_lines):
                if "cortex-lifecycle-branch-mode" in line:
                    dispatch_anchor = idx
                    break
        if dispatch_anchor is None:
            for idx, line in enumerate(implement_lines):
                if "read_branch_mode" in line:
                    dispatch_anchor = idx
                    break
        assert dispatch_anchor is not None, (
            "could not locate read_branch_mode / "
            "cortex-lifecycle-branch-mode anchor in implement.md"
        )

        # Find the first picker invocation line — either Python or CLI form.
        invocation_idx: int | None = None
        for idx, line in enumerate(implement_lines):
            if (
                "should_fire_picker(" in line
                or "cortex-lifecycle-picker-decision" in line
            ):
                invocation_idx = idx
                break
        assert invocation_idx is not None, (
            "picker invocation not found in implement.md — neither "
            "should_fire_picker( nor cortex-lifecycle-picker-decision present"
        )

        # Find the picker AskUserQuestion call-site anchor: first
        # AskUserQuestion mention at or after the dispatch preflight block.
        # This is the call site the dispatch gates — the prose-only mention
        # at the top of §1 (the section heading) precedes the dispatch.
        picker_anchor: int | None = None
        for idx, line in enumerate(
            implement_lines[dispatch_anchor:], start=dispatch_anchor
        ):
            if "AskUserQuestion" in line:
                picker_anchor = idx
                break
        assert picker_anchor is not None, (
            "could not locate §1 picker AskUserQuestion anchor in implement.md "
            f"(searched from line {dispatch_anchor + 1} onward)"
        )

        assert invocation_idx < picker_anchor, (
            f"should_fire_picker( invocation at line {invocation_idx + 1} "
            f"must appear before §1 picker AskUserQuestion anchor at line "
            f"{picker_anchor + 1}"
        )

    def test_four_branch_modes_within_proximity(
        self, implement_lines: list[str]
    ) -> None:
        """(iv) Each closed-set value appears within ±10 lines of a should_fire_picker mention.

        The routing block must name each of the four branch-mode values
        (``worktree-interactive``, ``trunk``, ``feature-branch``,
        ``prompt``) near a ``should_fire_picker`` mention so that each
        closed-set value has a documented routing destination adjacent to
        the dispatch invocation.
        """
        mention_indices = [
            idx
            for idx, line in enumerate(implement_lines)
            if "should_fire_picker" in line
        ]
        assert mention_indices, (
            "no should_fire_picker mentions found — proximity check cannot run"
        )

        values = ("worktree-interactive", "trunk", "feature-branch", "prompt")
        for value in values:
            found_near_mention = False
            for mention_idx in mention_indices:
                lo = max(0, mention_idx - 10)
                hi = min(len(implement_lines), mention_idx + 11)
                window = implement_lines[lo:hi]
                if any(value in line for line in window):
                    found_near_mention = True
                    break
            assert found_near_mention, (
                f"closed-set value {value!r} not found within ±10 lines of "
                f"any should_fire_picker mention in implement.md "
                f"(mentions at lines: {[i + 1 for i in mention_indices]})"
            )
