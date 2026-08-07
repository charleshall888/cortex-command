"""Tests for cortex_command.common — focused on _resolve_user_project_root."""

from __future__ import annotations

import inspect
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

import pytest

from cortex_command.common import (
    MOST_RESTRICTIVE_PAUSE_KIND,
    CortexProjectRootError,
    _resolve_user_project_root,
    _resolve_user_project_root_from_cwd,
    compute_dependency_batches,
    detect_lifecycle_phase,
    mark_task_done_in_plan,
    reduce_lifecycle_events,
)
from cortex_command.pipeline.parser import FeatureTask


# ---------------------------------------------------------------------------
# _resolve_user_project_root
# ---------------------------------------------------------------------------

class TestResolveUserProjectRoot:
    """Tests for the upward-walking cortex project root resolver."""

    def test_detects_cortex_subdir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the directory that contains a ``cortex/`` subdirectory."""
        cortex_dir = tmp_path / "cortex"
        cortex_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        result = _resolve_user_project_root()

        assert result == tmp_path.resolve()

    def test_detects_cortex_subdir_from_child(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the ancestor that contains ``cortex/`` when invoked from a subdirectory."""
        cortex_dir = tmp_path / "cortex"
        cortex_dir.mkdir()
        child = tmp_path / "subdir" / "nested"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        result = _resolve_user_project_root()

        assert result == tmp_path.resolve()

    def test_raises_when_no_cortex_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises CortexProjectRootError when no ancestor has a ``cortex/`` subdir."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
        # Terminate the walk at tmp_path by placing a .git marker there.
        (tmp_path / ".git").mkdir()

        with pytest.raises(CortexProjectRootError):
            _resolve_user_project_root()

    def test_env_override_takes_precedence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns Path(CORTEX_REPO_ROOT) verbatim when that env var is set."""
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        result = _resolve_user_project_root()

        assert result == tmp_path


# ---------------------------------------------------------------------------
# _resolve_user_project_root_from_cwd
# ---------------------------------------------------------------------------

class TestResolveUserProjectRootFromCwd:
    """Tests for the cwd-only cortex project root resolver."""

    def test_from_cwd_returns_worktree_root_ignoring_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the worktree root from CWD even when CORTEX_REPO_ROOT points elsewhere.

        Simulates a git worktree: the worktree directory has a ``.git`` file
        (not a directory) which is the worktree-shaped marker, and a ``cortex/``
        subdirectory. CWD is set to a subdirectory inside the worktree.
        CORTEX_REPO_ROOT is set to the main repo path (a different directory),
        which the cwd-based resolver must ignore.
        """
        # Build a fake worktree: root contains cortex/ and a .git *file*
        worktree_root = tmp_path / "worktree"
        worktree_root.mkdir()
        (worktree_root / "cortex").mkdir()
        (worktree_root / ".git").write_text("gitdir: /some/main/repo/.git/worktrees/wt\n")

        # CWD is inside the worktree (a subdirectory)
        inside = worktree_root / "subdir"
        inside.mkdir()
        monkeypatch.chdir(inside)

        # CORTEX_REPO_ROOT points to the main repo (a separate directory)
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(main_repo))

        result = _resolve_user_project_root_from_cwd()

        assert result == worktree_root.resolve()

    def test_from_cwd_raises_from_non_cortex_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raises CortexProjectRootError when CWD has no cortex/ ancestor.

        Places a ``.git`` file (worktree-shaped boundary) at tmp_path so the
        walk terminates without finding a ``cortex/`` directory.
        """
        (tmp_path / ".git").write_text("gitdir: /some/other/repo/.git/worktrees/wt\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)

        with pytest.raises(CortexProjectRootError):
            _resolve_user_project_root_from_cwd()


# ---------------------------------------------------------------------------
# compute_dependency_batches
# ---------------------------------------------------------------------------

class TestComputeDependencyBatches(unittest.TestCase):
    """Tests for the topological dependency-batching of feature tasks.

    ``compute_dependency_batches`` feeds the overnight runner's intra-feature
    task ordering; the per-task ``Depends on`` metadata the plan parser
    extracts flows directly into this function. These are the first direct
    tests of that batching mechanism.
    """

    def test_dependency_chain_yields_ordered_single_task_batches(self) -> None:
        """A 1->2->3 chain produces three ordered batches, each a single task."""
        t1 = FeatureTask(number=1, description="t1", depends_on=[])
        t2 = FeatureTask(number=2, description="t2", depends_on=["1"])
        t3 = FeatureTask(number=3, description="t3", depends_on=["2"])

        batches = compute_dependency_batches([t1, t2, t3])

        self.assertEqual([[t.number for t in batch] for batch in batches], [[1], [2], [3]])

    def test_all_empty_depends_on_collapse_to_single_batch(self) -> None:
        """All-empty ``depends_on`` tasks collapse into one concurrent batch.

        This documents the vacuous-true collapse (``common.py``: every task's
        empty ``depends_on`` satisfies ``all(...)`` against the empty assigned
        set, so all tasks land in batch 0). For label-present plans this case
        is now unreachable because R2/R4 raise upstream in the parser; it
        remains reachable only for legitimately-fully-parallel plans.
        """
        t1 = FeatureTask(number=1, description="t1", depends_on=[])
        t2 = FeatureTask(number=2, description="t2", depends_on=[])
        t3 = FeatureTask(number=3, description="t3", depends_on=[])

        batches = compute_dependency_batches([t1, t2, t3])

        self.assertEqual(len(batches), 1)
        self.assertEqual([t.number for t in batches[0]], [1, 2, 3])

    def test_dependency_cycle_raises_value_error(self) -> None:
        """A mutual 1<->2 dependency cycle cannot be batched and raises."""
        t1 = FeatureTask(number=1, description="t1", depends_on=["2"])
        t2 = FeatureTask(number=2, description="t2", depends_on=["1"])

        with self.assertRaises(ValueError):
            compute_dependency_batches([t1, t2])


class TestSubTaskBatching(unittest.TestCase):
    """#297: dependency batching keys on task_id (str), so letter-suffixed
    sub-tasks form distinct nodes whose membership cannot collide."""

    def test_subtask_serial_chain_3a_3b(self) -> None:
        """3a (no deps) then 3b (deps [3a]) yields two ordered batches."""
        t3a = FeatureTask(number=3, suffix="a", description="3a", depends_on=[])
        t3b = FeatureTask(number=3, suffix="b", description="3b", depends_on=["3a"])

        batches = compute_dependency_batches([t3a, t3b])

        self.assertEqual(
            [[t.task_id for t in batch] for batch in batches], [["3a"], ["3b"]]
        )

    def test_parallel_subtask_siblings_coschedule(self) -> None:
        """13a/13b/13c all dep [10] co-schedule in one batch after [10]."""
        t10 = FeatureTask(number=10, description="10", depends_on=[])
        t13a = FeatureTask(number=13, suffix="a", description="13a", depends_on=["10"])
        t13b = FeatureTask(number=13, suffix="b", description="13b", depends_on=["10"])
        t13c = FeatureTask(number=13, suffix="c", description="13c", depends_on=["10"])

        batches = compute_dependency_batches([t10, t13a, t13b, t13c])

        self.assertEqual([t.task_id for t in batches[0]], ["10"])
        self.assertEqual(
            sorted(t.task_id for t in batches[1]), ["13a", "13b", "13c"]
        )

    def test_done_sibling_does_not_drop_pending_sibling(self) -> None:
        """Merge guard: a status:done 3a must NOT drop a pending 3b from
        scheduling — the done/assigned sets key on task_id, so "3a" in assigned
        does not imply "3b" in assigned (the silent-merge path #297 must close)."""
        t3a = FeatureTask(
            number=3, suffix="a", description="3a", depends_on=[], status="done"
        )
        t3b = FeatureTask(number=3, suffix="b", description="3b", depends_on=[])

        batches = compute_dependency_batches([t3a, t3b])

        scheduled = [t.task_id for batch in batches for t in batch]
        self.assertIn("3b", scheduled)
        self.assertNotIn("3a", scheduled)  # already done, excluded from pending

    def test_dangling_subtask_reference_raises_naming_offender(self) -> None:
        """A [3] reference when only 3a/3b exist is unresolvable and raises with
        a message naming the offending id `3` specifically (#297 Req 5) — not a
        bare cycle dump. `3` must be identified distinctly from the present 3a."""
        t3a = FeatureTask(number=3, suffix="a", description="3a", depends_on=[])
        t4 = FeatureTask(number=4, description="4", depends_on=["3"])

        with self.assertRaises(ValueError) as cm:
            compute_dependency_batches([t3a, t4])
        msg = str(cm.exception)
        self.assertIn("Unresolvable dependency reference", msg)
        self.assertIn("'3'", msg)

    def test_self_referential_dependency_raises_naming_offender(self) -> None:
        """A task that lists its own id in depends_on raises naming it (#297 Req 5)."""
        t3a = FeatureTask(
            number=3, suffix="a", description="3a", depends_on=["3a"]
        )
        with self.assertRaises(ValueError) as cm:
            compute_dependency_batches([t3a])
        msg = str(cm.exception)
        self.assertIn("Self-referential", msg)
        self.assertIn("3a", msg)


class TestMarkTaskDoneInPlan(unittest.TestCase):
    """#297 Req 6: mark_task_done_in_plan matches the full task_id and the
    body scan cannot bleed its [ ]->[x] flip across the next ### heading."""

    def _plan(self, body: str) -> Path:
        d = tempfile.mkdtemp()
        p = Path(d) / "plan.md"
        p.write_text(body, encoding="utf-8")
        return p

    def test_marks_target_task_status(self) -> None:
        p = self._plan(
            "## Tasks\n\n"
            "### Task 1: First\n- **Status**: [ ] pending\n\n"
            "### Task 2: Second\n- **Status**: [ ] pending\n"
        )
        mark_task_done_in_plan(p, "1")
        text = p.read_text(encoding="utf-8")
        self.assertIn("### Task 1: First\n- **Status**: [x]", text)
        self.assertIn("### Task 2: Second\n- **Status**: [ ]", text)

    def test_already_done_parent_does_not_flip_next_task(self) -> None:
        """Marking an already-[x] task does NOT bleed into the next task's [ ]
        (the pre-existing DOTALL cross-task bleed, fixed by the tempered dot)."""
        p = self._plan(
            "## Tasks\n\n"
            "### Task 1: First\n- **Status**: [x] done\n\n"
            "### Task 2: Second\n- **Status**: [ ] pending\n"
        )
        mark_task_done_in_plan(p, "1")
        text = p.read_text(encoding="utf-8")
        # Task 2 must remain unchecked — the scan must not cross into it.
        self.assertIn("### Task 2: Second\n- **Status**: [ ]", text)

    def test_marks_subtask_by_task_id_not_sibling(self) -> None:
        """Marking 3a checks 3a's status, not 3b's."""
        p = self._plan(
            "## Tasks\n\n"
            "### Task 3a: Sub A\n- **Status**: [ ] pending\n\n"
            "### Task 3b: Sub B\n- **Status**: [ ] pending\n"
        )
        mark_task_done_in_plan(p, "3a")
        text = p.read_text(encoding="utf-8")
        self.assertIn("### Task 3a: Sub A\n- **Status**: [x]", text)
        self.assertIn("### Task 3b: Sub B\n- **Status**: [ ]", text)


# ---------------------------------------------------------------------------
# reduce_lifecycle_events — feature_paused pause_kind (374 R5 / hazard 3)
# ---------------------------------------------------------------------------


class TestReduceFeaturePausedKind(unittest.TestCase):
    """The reducer reports a paused feature's resume-authority kind, failing
    closed to the most-restrictive kind for a legacy under-specified row."""

    def test_legacy_kindless_slugless_row_defaults_most_restrictive(self) -> None:
        """A legacy `feature_paused` row with neither slug nor kind reduces to
        the most-restrictive kind (relayed-consent, operator-resume-only) so an
        under-specified pause never silently auto-resumes (hazard 3)."""
        state, rejected = reduce_lifecycle_events([{"event": "feature_paused"}])
        self.assertEqual(state["pause_kind"], MOST_RESTRICTIVE_PAUSE_KIND)
        self.assertEqual(MOST_RESTRICTIVE_PAUSE_KIND, "relayed-consent")
        # Fail-closed defaulting is NOT a vocab rejection — the line is not flagged.
        self.assertEqual(rejected, [])

    def test_out_of_vocab_kind_also_defaults_most_restrictive(self) -> None:
        """An out-of-vocab `kind` is under-specified too → fail closed."""
        state, rejected = reduce_lifecycle_events(
            [{"event": "feature_paused", "slug": "plan-approval", "kind": "bogus"}]
        )
        self.assertEqual(state["pause_kind"], MOST_RESTRICTIVE_PAUSE_KIND)
        self.assertEqual(rejected, [])

    def test_valid_kind_is_reported_verbatim(self) -> None:
        """A row carrying a valid in-vocab `kind` reports that kind, not the
        default."""
        state, _ = reduce_lifecycle_events(
            [{"event": "feature_paused", "slug": "empty-lifecycle-offer",
              "kind": "question"}]
        )
        self.assertEqual(state["pause_kind"], "question")

    def test_no_paused_row_leaves_pause_kind_absent(self) -> None:
        """Without a `feature_paused` row, the reduced state carries no
        `pause_kind` key (additive, present only when a pause row exists)."""
        state, _ = reduce_lifecycle_events(
            [{"event": "lifecycle_start", "tier": "simple", "criticality": "medium"}]
        )
        self.assertNotIn("pause_kind", state)


# ---------------------------------------------------------------------------
# detect_lifecycle_phase — the `cycle` key counts review_verdict EVENTS (#455 R17)
#
# review.md is overwritten every cycle, so regex-counting its verdicts stuck at
# 1 forever; the count moved to the append-only events.log. The pair of classes
# below guards both halves of that end state — the behaviour, and the docstring
# that documents it — so a rewrite reintroducing the review.md-regex description
# fails rather than silently rotting the contract.
# ---------------------------------------------------------------------------


_CYCLE_DOC_BULLET = re.compile(
    r"^[ \t]*-\s*cycle:(?P<body>.*?)(?=^[ \t]*-\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _cycle_doc_bullet() -> str | None:
    """Return the `cycle:` bullet of detect_lifecycle_phase's Returns section.

    Scoped to that one bullet rather than the whole docstring: the docstring
    legitimately names review.md elsewhere (the verdict-extraction step), so a
    whole-docstring search could neither confirm nor refute what `cycle` counts.
    """
    doc = inspect.getdoc(detect_lifecycle_phase) or ""
    match = _CYCLE_DOC_BULLET.search(doc)
    return match.group("body") if match else None


def _feature_dir(*, verdict_events: int, review_md_verdicts: int) -> Path:
    """Build a lifecycle feature dir with independently-varied verdict counts.

    ``verdict_events`` review_verdict rows land in events.log; a *different*
    number of `"verdict"` matches land in review.md. The two counts disagree on
    purpose — that is what separates counting events from regexing review.md.
    """
    d = Path(tempfile.mkdtemp())
    rows = [{"event": "lifecycle_start", "tier": "simple"}]
    rows += [{"event": "review_verdict", "verdict": "CHANGES_REQUESTED"}] * verdict_events
    rows.append({"event": "plan_approved"})
    (d / "events.log").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    (d / "review.md").write_text(
        "".join('{"verdict": "CHANGES_REQUESTED"}\n' for _ in range(review_md_verdicts)),
        encoding="utf-8",
    )
    return d


class TestCycleCountsReviewVerdictEvents(unittest.TestCase):
    """The observable half: `cycle` tracks events.log's review_verdict rows and
    is unmoved by how many verdicts review.md happens to contain."""

    def test_cycle_follows_events_log_not_review_md(self) -> None:
        """Three review_verdict rows against a single-verdict review.md yields
        cycle 3 — the old review.md regex count would have said 1."""
        result = detect_lifecycle_phase(
            _feature_dir(verdict_events=3, review_md_verdicts=1)
        )
        self.assertEqual(result["cycle"], 3)
        # cycle is load-bearing, not decorative: it discriminates the phase.
        self.assertEqual(result["phase"], "escalated:rework-cap:3")

    def test_extra_review_md_verdicts_do_not_inflate_cycle(self) -> None:
        """The converse: a review.md stuffed with verdicts cannot push cycle
        past the single review_verdict row in events.log."""
        result = detect_lifecycle_phase(
            _feature_dir(verdict_events=1, review_md_verdicts=5)
        )
        self.assertEqual(result["cycle"], 1)
        self.assertEqual(result["phase"], "implement-rework")

    def test_cycle_floors_at_one_without_verdict_events(self) -> None:
        """No review_verdict rows -> cycle is floored at 1, never 0, even with
        verdicts present in review.md."""
        result = detect_lifecycle_phase(
            _feature_dir(verdict_events=0, review_md_verdicts=2)
        )
        self.assertEqual(result["cycle"], 1)


class TestCycleDocstringDescribesEventCount(unittest.TestCase):
    """The documented half: detect_lifecycle_phase's `cycle` bullet must
    describe the behaviour the class above proves."""

    def test_cycle_bullet_exists(self) -> None:
        """A rewrite that drops the bullet entirely must fail here rather than
        vacuously pass the content assertions below."""
        self.assertIsNotNone(
            _cycle_doc_bullet(),
            "detect_lifecycle_phase's docstring no longer documents a `cycle:` "
            "key in its Returns section",
        )

    def test_cycle_bullet_names_review_verdict_events(self) -> None:
        """The bullet must name review_verdict as what cycle counts."""
        bullet = _cycle_doc_bullet() or ""
        self.assertIn("review_verdict", bullet)

    def test_cycle_bullet_does_not_describe_a_review_md_regex_count(self) -> None:
        """The stale description ("the number of regex matches in review.md")
        must not come back — it documents a behaviour the code does not have."""
        bullet = (_cycle_doc_bullet() or "").lower()
        self.assertNotIn("review.md", bullet)
        self.assertNotIn("regex", bullet)

    def test_documented_source_matches_observed_behaviour(self) -> None:
        """Couple the two halves: the bullet claims events.log/review_verdict,
        and on a fixture where the two candidate sources disagree the observed
        cycle equals the events.log count, not review.md's."""
        bullet = (_cycle_doc_bullet() or "").lower()
        self.assertIn("review_verdict", bullet)
        self.assertIn("events.log", bullet)
        result = detect_lifecycle_phase(
            _feature_dir(verdict_events=4, review_md_verdicts=2)
        )
        self.assertEqual(result["cycle"], 4)
