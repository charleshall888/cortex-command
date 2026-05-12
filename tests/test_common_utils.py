"""Unit tests for cortex_command.common utility functions: read_tier and requires_review.

Tests cover:
  - read_tier: existing events.log with tier field, empty file,
    missing file (default "simple"), complexity_override event.
  - requires_review: all 8 cells of the gating matrix
    (2 tiers x 4 criticalities).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cortex_command.common import (
    CortexProjectRootError,
    _resolve_user_project_root,
    mark_task_done_in_plan,
    read_criticality,
    read_tier,
    requires_review,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TIER_PARITY_ROOT = REPO_ROOT / "tests" / "fixtures" / "state" / "tier_parity"


# ---------------------------------------------------------------------------
# read_tier
# ---------------------------------------------------------------------------


class TestReadTier:
    """Tests for read_tier()."""

    def test_returns_tier_from_events_log(self, tmp_path: Path):
        """Reads the tier field from a well-formed lifecycle_start event."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text(
            json.dumps({"event": "lifecycle_start", "tier": "complex"}) + "\n",
            encoding="utf-8",
        )

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_complexity_override_supersedes_lifecycle_start_tier(
        self, tmp_path: Path
    ):
        """complexity_override.to supersedes the earlier lifecycle_start.tier."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "tier": "simple"}),
            json.dumps({"event": "something_else", "note": "no tier here"}),
            json.dumps({"event": "complexity_override", "to": "complex"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_returns_default_for_empty_file(self, tmp_path: Path):
        """Empty events.log returns the default tier 'simple'."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text("", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"

    def test_returns_default_for_missing_file(self, tmp_path: Path):
        """Missing events.log returns the default tier 'simple'."""
        feature = "test-feature"
        # Don't create the feature directory at all
        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"

    def test_complexity_override_to_field_updates_tier(self, tmp_path: Path):
        """complexity_override with `to` field overrides the baseline tier."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "tier": "simple"}),
            json.dumps({"event": "complexity_override", "to": "complex"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_skips_malformed_json_lines(self, tmp_path: Path):
        """Malformed JSON lines are skipped without error."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            "not valid json",
            json.dumps({"event": "lifecycle_start", "tier": "complex"}),
            "{bad json too",
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_returns_default_when_no_tier_field_present(self, tmp_path: Path):
        """Events without a tier field leave the default 'simple' unchanged."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "session_start"}),
            json.dumps({"event": "task_complete", "task": 1}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"


# ---------------------------------------------------------------------------
# read_criticality — canonical rule (lifecycle_start → criticality_override.to)
# ---------------------------------------------------------------------------


class TestReadCriticality:
    """Tests for read_criticality() canonical rule.

    The canonical rule reads the ``criticality`` field of the most recent
    ``lifecycle_start`` event, superseded by the ``to`` field of any later
    ``criticality_override`` event. Stray ``criticality`` fields on other
    event types (e.g. ``critical_review``) are ignored.
    """

    def test_returns_criticality_from_lifecycle_start(self, tmp_path: Path):
        """Reads criticality from a well-formed lifecycle_start event."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text(
            json.dumps({"event": "lifecycle_start", "criticality": "high"}) + "\n",
            encoding="utf-8",
        )

        assert read_criticality(feature, lifecycle_base=tmp_path) == "high"

    def test_criticality_override_supersedes_lifecycle_start(self, tmp_path: Path):
        """criticality_override.to supersedes the earlier lifecycle_start.criticality."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "criticality": "low"}),
            json.dumps({"event": "criticality_override", "to": "critical"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert read_criticality(feature, lifecycle_base=tmp_path) == "critical"

    def test_stray_criticality_field_on_other_event_ignored(self, tmp_path: Path):
        """A criticality field on a non-canonical event (e.g. critical_review)
        does NOT update the canonical value — the spec line 42 stray-tier
        sibling case for the criticality axis."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "criticality": "medium"}),
            json.dumps({"event": "critical_review", "criticality": "high"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert read_criticality(feature, lifecycle_base=tmp_path) == "medium"

    def test_returns_default_for_missing_file(self, tmp_path: Path):
        """Missing events.log returns the default criticality 'medium'."""
        feature = "test-feature"
        assert read_criticality(feature, lifecycle_base=tmp_path) == "medium"

    def test_returns_default_when_no_canonical_event(self, tmp_path: Path):
        """An events.log with no lifecycle_start/criticality_override events
        returns the default — even if other events carry criticality fields."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text(
            json.dumps({"event": "critical_review", "criticality": "high"}) + "\n",
            encoding="utf-8",
        )

        assert read_criticality(feature, lifecycle_base=tmp_path) == "medium"


# ---------------------------------------------------------------------------
# requires_review — all 8 cells of the gating matrix
# ---------------------------------------------------------------------------


class TestRequiresReview:
    """Tests for requires_review(): 2 tiers x 4 criticalities = 8 cells."""

    # simple tier: only high and critical trigger review

    def test_simple_low_skips_review(self):
        assert requires_review("simple", "low") is False

    def test_simple_medium_skips_review(self):
        assert requires_review("simple", "medium") is False

    def test_simple_high_requires_review(self):
        assert requires_review("simple", "high") is True

    def test_simple_critical_requires_review(self):
        assert requires_review("simple", "critical") is True

    # complex tier: always requires review regardless of criticality

    def test_complex_low_requires_review(self):
        assert requires_review("complex", "low") is True

    def test_complex_medium_requires_review(self):
        assert requires_review("complex", "medium") is True

    def test_complex_high_requires_review(self):
        assert requires_review("complex", "high") is True

    def test_complex_critical_requires_review(self):
        assert requires_review("complex", "critical") is True


# ---------------------------------------------------------------------------
# mark_task_done_in_plan — idempotency over already-marked Status fields (R12)
# ---------------------------------------------------------------------------


class TestMarkTaskDoneInPlanIdempotent:
    """Codify R12: mark_task_done_in_plan is a no-op on already-[X] or [x]
    Status fields (file bytes unchanged) and updates [ ] to [x].
    """

    def test_mark_task_done_in_plan_idempotent_over_existing_marks(
        self, tmp_path: Path
    ):
        """R12: calling on [X] or [x] leaves bytes unchanged; [ ] becomes [x]."""
        # Case 1: already [X] complete — file bytes must be byte-identical.
        plan_upper = tmp_path / "plan_upper.md"
        content_upper = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [X] complete\n"
        )
        plan_upper.write_text(content_upper, encoding="utf-8")
        before_upper = plan_upper.read_bytes()
        mark_task_done_in_plan(plan_upper, 1)
        after_upper = plan_upper.read_bytes()
        assert after_upper == before_upper

        # Case 2: already [x] complete — file bytes must be byte-identical.
        plan_lower = tmp_path / "plan_lower.md"
        content_lower = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [x] complete\n"
        )
        plan_lower.write_text(content_lower, encoding="utf-8")
        before_lower = plan_lower.read_bytes()
        mark_task_done_in_plan(plan_lower, 1)
        after_lower = plan_lower.read_bytes()
        assert after_lower == before_lower

        # Case 3: [ ] pending — file is updated to [x] complete.
        plan_pending = tmp_path / "plan_pending.md"
        content_pending = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [ ] pending\n"
        )
        plan_pending.write_text(content_pending, encoding="utf-8")
        mark_task_done_in_plan(plan_pending, 1)
        updated = plan_pending.read_text(encoding="utf-8")
        assert "- **Status**: [x] pending" in updated
        assert "- **Status**: [ ] pending" not in updated


# ---------------------------------------------------------------------------
# read_tier — canonical-rule cases (i)–(iii) using tier_parity fixtures
# ---------------------------------------------------------------------------

CANONICAL_CASES = [
    ("lifecycle_start_only", "simple"),
    ("start_then_override", "complex"),
    ("stray_tier_after_override", "simple"),
]


def _stage_tier_parity_fixture(tmp_path: Path, slug: str) -> None:
    """Stage ``tests/fixtures/state/tier_parity/<slug>/events.log`` under
    ``tmp_path/lifecycle/<slug>/events.log`` so read_tier can be invoked with
    an absolute lifecycle_base."""
    source = TIER_PARITY_ROOT / slug / "events.log"
    feature_dir = tmp_path / "lifecycle" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, feature_dir / "events.log")


@pytest.mark.parametrize(
    "slug,expected",
    CANONICAL_CASES,
    ids=[c[0] for c in CANONICAL_CASES],
)
def test_canonical_tier_rule(
    tmp_path: Path,
    slug: str,
    expected: str,
) -> None:
    """Cases (i)–(iii): read_tier returns the canonical tier value for each
    tier_parity fixture.

    Slugs: lifecycle_start_only, start_then_override, stray_tier_after_override.
    """
    source = TIER_PARITY_ROOT / slug / "events.log"
    assert source.exists(), f"missing fixture: {source}"
    _stage_tier_parity_fixture(tmp_path, slug)

    result = read_tier(slug, lifecycle_base=tmp_path / "lifecycle")

    assert result == expected, (
        f"read_tier({slug!r}) returned {result!r}, expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# read_tier — key-name tests: T-A and T-B (migrated from test_report.py)
# ---------------------------------------------------------------------------


def test_read_tier_ignores_complexity_field_only_returns_default(
    tmp_path: Path,
) -> None:
    """T-A: read_tier on an events.log containing only a ``complexity`` field
    (no ``tier`` field) returns ``"simple"`` — the default. The wrong key is
    silently ignored."""
    feature = "tA-complexity-only"
    feature_dir = tmp_path / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    events_log = feature_dir / "events.log"
    events_log.write_text(
        json.dumps({"event": "lifecycle_start", "feature": feature, "complexity": "complex"})
        + "\n",
        encoding="utf-8",
    )

    assert read_tier(feature, lifecycle_base=tmp_path / "lifecycle") == "simple"


def test_read_tier_canonical_tier_wins_over_stray_complexity(
    tmp_path: Path,
) -> None:
    """T-B: read_tier on an events.log containing BOTH ``tier: "complex"`` and
    a stray ``complexity: "simple"`` returns ``"complex"`` — the canonical
    ``tier`` key wins."""
    feature = "tB-both-keys"
    feature_dir = tmp_path / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    events_log = feature_dir / "events.log"
    events_log.write_text(
        json.dumps({
            "event": "lifecycle_start",
            "feature": feature,
            "tier": "complex",
            "complexity": "simple",
        })
        + "\n",
        encoding="utf-8",
    )

    assert read_tier(feature, lifecycle_base=tmp_path / "lifecycle") == "complex"


# ---------------------------------------------------------------------------
# _resolve_user_project_root — upward walk for project-root detection (#201)
# ---------------------------------------------------------------------------


def test_resolve_user_project_root_lifecycle_marker_at_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk returns the cwd itself when ``lifecycle/`` is present at cwd."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    (tmp_path / "lifecycle").mkdir()
    monkeypatch.chdir(tmp_path)

    assert _resolve_user_project_root() == tmp_path.resolve()


def test_resolve_user_project_root_backlog_only_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk returns cwd when only ``backlog/`` is present (lifecycle/ absent)."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    (tmp_path / "backlog").mkdir()
    monkeypatch.chdir(tmp_path)

    assert _resolve_user_project_root() == tmp_path.resolve()


def test_resolve_user_project_root_walks_up_from_subdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk starts deep inside the tree and returns the ancestor with markers."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    (tmp_path / "lifecycle").mkdir()
    deep = tmp_path / "lifecycle" / "feature-x" / "deferred"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)

    assert _resolve_user_project_root() == tmp_path.resolve()


def test_resolve_user_project_root_git_dir_boundary_terminates_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``.git/`` (as directory) ancestor without cortex markers terminates the walk."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    repo = tmp_path / "some-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    subdir = repo / "src" / "nested"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    with pytest.raises(CortexProjectRootError) as excinfo:
        _resolve_user_project_root()
    assert "Searched: " in str(excinfo.value)


def test_resolve_user_project_root_git_file_boundary_terminates_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``.git`` as a regular file (worktree shape) also terminates the walk."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    worktree = tmp_path / "wt-checkout"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    subdir = worktree / "src"
    subdir.mkdir()
    monkeypatch.chdir(subdir)

    with pytest.raises(CortexProjectRootError):
        _resolve_user_project_root()


def test_resolve_user_project_root_env_override_skips_walk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CORTEX_REPO_ROOT`` env var is honored verbatim and bypasses the walk."""
    # Override points to a directory that does NOT contain markers — the walk
    # would otherwise fail. The env var must win without inspecting the path.
    override = tmp_path / "explicit-root"
    override.mkdir()
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(override))
    monkeypatch.chdir(tmp_path)

    assert _resolve_user_project_root() == override


def test_resolve_user_project_root_searched_paths_in_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Error message lists each visited path so failure is self-diagnosing."""
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    repo = tmp_path / "outer"
    repo.mkdir()
    (repo / ".git").mkdir()
    leaf = repo / "a" / "b"
    leaf.mkdir(parents=True)
    monkeypatch.chdir(leaf)

    with pytest.raises(CortexProjectRootError) as excinfo:
        _resolve_user_project_root()
    msg = str(excinfo.value)
    assert "Searched: " in msg
    assert str(leaf.resolve()) in msg
    assert str(repo.resolve()) in msg
