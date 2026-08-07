#!/usr/bin/env python3
"""Tests for render_completed_features grouping by repo."""

import pytest
from pathlib import Path

from cortex_command.overnight.report import ReportData, render_complexity_normalized, render_completed_features, render_effort_degradation, render_executive_summary, render_failed_features
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState
from cortex_command.common import read_tier


# ---------------------------------------------------------------------------
# pytest helpers
# ---------------------------------------------------------------------------

def _pytest_make_state(features: dict, integration_branches: dict | None = None) -> "OvernightState":
    return OvernightState(
        session_id="test-session",
        features=features,
        integration_branches=integration_branches or {},
    )


def _pytest_make_data(features: dict, integration_branches: dict | None = None, pr_urls: dict | None = None) -> "ReportData":
    data = ReportData()
    data.state = _pytest_make_state(features, integration_branches=integration_branches)
    data.pr_urls = pr_urls or {}
    return data


# ---------------------------------------------------------------------------
# Test 1: Two features — home repo and cross-repo — group headers present
# ---------------------------------------------------------------------------

def test_two_features_group_headers() -> None:
    """Two features (home repo + cross-repo) produce correct group headers."""
    from cortex_command.overnight import report as _report_module
    home_repo_name = Path(_report_module.__file__).resolve().parent.parent.parent.name
    features = {
        "feature-alpha": OvernightFeatureStatus(status="merged", repo_path=None),
        "feature-beta": OvernightFeatureStatus(status="merged", repo_path="/some/path"),
    }
    data = ReportData()
    data.state = OvernightState(session_id="test-session", features=features)
    data.pr_urls = {}
    output = render_completed_features(data)

    assert f"### {home_repo_name}" in output, f"got: {output[:300]}"
    assert "### path" in output, f"got: {output[:300]}"
    assert output.index(f"### {home_repo_name}") < output.index("### path"), "home repo should come first"


# ---------------------------------------------------------------------------
# Test 2: pr_urls populated — PR URL appears in output for cross-repo group
# ---------------------------------------------------------------------------

def test_pr_url_in_cross_repo_output() -> None:
    """Cross-repo PR URL appears in output when pr_urls is populated."""
    features = {
        "feature-gamma": OvernightFeatureStatus(status="merged", repo_path="/some/path"),
    }
    pr_url = "https://github.com/org/repo/pull/42"
    data = ReportData()
    data.state = OvernightState(session_id="test-session", features=features)
    data.pr_urls = {"/some/path": pr_url}
    output = render_completed_features(data)

    assert pr_url in output, f"got: {output[:300]}"
    assert f"**PR**: {pr_url}" in output, f"got: {output[:300]}"


# ---------------------------------------------------------------------------
# Test 3: Single home repo feature — group header still present
# ---------------------------------------------------------------------------

def test_single_home_repo_feature() -> None:
    """Single home repo feature still renders a group header."""
    from cortex_command.overnight import report as _report_module
    home_repo_name = Path(_report_module.__file__).resolve().parent.parent.parent.name
    features = {
        "feature-delta": OvernightFeatureStatus(status="merged", repo_path=None),
    }
    data = ReportData()
    data.state = OvernightState(session_id="test-session", features=features)
    data.pr_urls = {}
    output = render_completed_features(data)

    assert f"### {home_repo_name}" in output, f"got: {output[:300]}"
    assert "**PR**:" not in output, "home repo group should not have a PR URL line"


# ---------------------------------------------------------------------------
# pytest-compatible tests (TDD and regression)
# ---------------------------------------------------------------------------

def test_render_uses_home_repo_name_from_integration_branches():
    """render_completed_features uses integration_branches to determine home repo name.

    Pre-Task 4: FAILS — render_completed_features ignores integration_branches and
    hard-codes the repo name using Path(__file__), so the output shows
    '### <repo-dir-name>' rather than '### wild-light'.
    Post-Task 4: PASSES once render_completed_features reads integration_branches
    to determine the home repo name dynamically.
    """
    features = {
        "feature-alpha": OvernightFeatureStatus(status="merged", repo_path=None),
    }
    data = _pytest_make_data(
        features,
        integration_branches={"/path/to/wild-light": "overnight/x"},
    )
    output = render_completed_features(data)
    assert "### wild-light" in output, f"Expected '### wild-light' in output, got:\n{output[:400]}"


def test_render_home_repo_group_header_regression():
    """render_completed_features shows '### <repo-dir-name>' for home repo — regression guard.

    Uses the actual repo root path in integration_branches, derived the same
    way render_completed_features currently derives it (via report.__file__).
    Passes before and after Task 4 because the home repo name in the header always
    matches the repo root directory name.

    NOTE: In worktree contexts the directory name is the worktree name rather than
    the repo name. The assertion uses the dynamic repo root name to remain correct
    in all contexts.
    """
    from cortex_command.overnight import report as _report_module
    home_repo_root = str(Path(_report_module.__file__).resolve().parent.parent.parent)
    expected_name = Path(home_repo_root).name
    features = {
        "feature-delta": OvernightFeatureStatus(status="merged", repo_path=None),
    }
    data = _pytest_make_data(
        features,
        integration_branches={home_repo_root: "overnight/x"},
    )
    output = render_completed_features(data)
    assert f"### {expected_name}" in output, (
        f"Expected '### {expected_name}' in output, got:\n{output[:400]}"
    )


# ---------------------------------------------------------------------------
# Tests for render_failed_features conflict rendering
# ---------------------------------------------------------------------------

def test_conflicted_feature_renders_summary_and_files() -> None:
    """Conflicted feature renders conflict summary and conflicted files inline."""
    features = {
        "feature-conflict": OvernightFeatureStatus(
            status="paused", error="merge conflict in src/foo.py"
        ),
    }
    data = _pytest_make_data(features)
    data.events = [
        {
            "event": "merge_conflict_classified",
            "feature": "feature-conflict",
            "details": {
                "conflicted_files": ["src/foo.py", "src/bar.py"],
                "conflict_summary": "Both branches modified the same function signature",
            },
        }
    ]
    output = render_failed_features(data)

    assert "Both branches modified the same function signature" in output, (
        f"Expected conflict summary in output, got:\n{output[:400]}"
    )
    assert "src/foo.py" in output, (
        f"Expected conflicted filename 'src/foo.py' in output, got:\n{output[:400]}"
    )
    assert "**Conflict summary**" in output, (
        f"Expected '**Conflict summary**' marker in output, got:\n{output[:400]}"
    )
    assert "**Conflicted files**" in output, (
        f"Expected '**Conflicted files**' marker in output, got:\n{output[:400]}"
    )


def test_conflicted_feature_empty_files_renders_summary_only() -> None:
    """Conflicted feature with empty conflicted_files renders summary but no files line."""
    features = {
        "feature-empty-files": OvernightFeatureStatus(
            status="paused", error="merge conflict in src/baz.py"
        ),
    }
    data = _pytest_make_data(features)
    data.events = [
        {
            "event": "merge_conflict_classified",
            "feature": "feature-empty-files",
            "details": {
                "conflicted_files": [],
                "conflict_summary": "classification failed",
            },
        }
    ]
    output = render_failed_features(data)

    assert "classification failed" in output, (
        f"Expected conflict summary 'classification failed' in output, got:\n{output[:400]}"
    )
    assert "**Conflict summary**" in output, (
        f"Expected '**Conflict summary**' marker in output, got:\n{output[:400]}"
    )
    assert "**Conflicted files**" not in output, (
        f"Expected no '**Conflicted files**' line in output, got:\n{output[:400]}"
    )


def test_non_conflicted_paused_feature_renders_no_conflict_lines() -> None:
    """Non-conflicted paused feature renders no conflict detail lines."""
    features = {
        "feature-timeout": OvernightFeatureStatus(
            status="paused", error="timed out after 30 minutes"
        ),
    }
    data = _pytest_make_data(features)
    data.events = []
    output = render_failed_features(data)

    assert "**Conflict summary**" not in output, (
        f"Expected no conflict summary for non-conflict pause, got:\n{output[:400]}"
    )
    assert "**Conflicted files**" not in output, (
        f"Expected no conflicted files for non-conflict pause, got:\n{output[:400]}"
    )
    assert "**Recovery branch**" not in output, (
        f"Expected no recovery branch for non-conflict pause, got:\n{output[:400]}"
    )


def test_render_failed_features_shows_recovery_branch() -> None:
    """Conflicted feature with conflicted_files renders the recovery branch line."""
    features = {
        "feature-name": OvernightFeatureStatus(
            status="paused", error="merge conflict in src/foo.py"
        ),
    }
    data = _pytest_make_data(features)
    data.events = [
        {
            "event": "merge_conflict_classified",
            "round": 1,
            "feature": "feature-name",
            "details": {
                "conflicted_files": ["src/foo.py"],
                "conflict_summary": "Both branches modified the same function",
            },
        }
    ]
    output = render_failed_features(data)

    assert "- **Recovery branch**: `pipeline/feature-name`" in output, (
        f"Expected recovery branch line in output, got:\n{output[:400]}"
    )


def test_render_failed_features_recovery_branch_shown_when_no_conflicted_files() -> None:
    """Conflicted feature with empty conflicted_files still renders the recovery branch line."""
    features = {
        "feature-name": OvernightFeatureStatus(
            status="paused", error="merge conflict"
        ),
    }
    data = _pytest_make_data(features)
    data.events = [
        {
            "event": "merge_conflict_classified",
            "round": 1,
            "feature": "feature-name",
            "details": {
                "conflicted_files": [],
                "conflict_summary": "classification failed",
            },
        }
    ]
    output = render_failed_features(data)

    assert "- **Recovery branch**: `pipeline/feature-name`" in output, (
        f"Expected recovery branch line even with empty conflicted_files, got:\n{output[:400]}"
    )


def test_render_failed_features_separates_blocker_failed_cascade_casualty() -> None:
    """A blocker_failed cascade casualty renders distinctly from a primary failure.

    Witnesses Task 6: the end-of-round sweep sets ``error == "blocker_failed"``
    on dependents it auto-fails. The morning report must group those casualties
    in a labelled section tagged with the ``blocker_failed`` reason so one OOV
    blocker with N dependents does not read as N+1 independent failures.
    """
    features = {
        "blocker": OvernightFeatureStatus(
            status="failed", error="Unknown complexity tier 'medium'"
        ),
        "dependent": OvernightFeatureStatus(
            status="failed", error="blocker_failed"
        ),
    }
    data = _pytest_make_data(features)
    data.events = []
    output = render_failed_features(data)

    # The cascade casualty is labelled/separated into its own subsection and
    # tagged with the blocker_failed reason.
    assert "Cascade casualties (blocker failed)" in output, (
        f"Expected a labelled cascade-casualties subsection, got:\n{output[:800]}"
    )
    assert "blocker_failed" in output, (
        f"Expected the blocker_failed reason tag in output, got:\n{output[:800]}"
    )
    assert "**dependent** (reason: `blocker_failed`)" in output, (
        f"Expected the dependent rendered as a tagged casualty, got:\n{output[:800]}"
    )

    # The primary failure renders ahead of the casualty section, and the
    # dependent is NOT rendered as a primary `### dependent:` failure heading.
    assert "### blocker:" in output, (
        f"Expected the primary failure heading, got:\n{output[:800]}"
    )
    assert "### dependent:" not in output, (
        f"Casualty must not render as a primary failure heading, got:\n{output[:800]}"
    )
    assert output.index("### blocker:") < output.index(
        "Cascade casualties (blocker failed)"
    ), "Primary failures should render before the cascade-casualties section"


# ---------------------------------------------------------------------------
# Tests for paused_reason rendering in the morning-report executive summary
# ---------------------------------------------------------------------------

def test_morning_report_distinguishes_api_rate_limit_pause() -> None:
    """Executive summary emits distinct text for paused_reason="api_rate_limit".

    Witnesses the additive `api_rate_limit` branch in render_executive_summary
    (Task 11). Catches implementations where the branch is unreachable, the
    literal is misspelled, or the branch order makes it dead code.
    """
    features = {
        "feature-stalled": OvernightFeatureStatus(status="pending"),
    }
    data = ReportData()
    data.state = OvernightState(
        session_id="test-session",
        features=features,
        paused_reason="api_rate_limit",
    )
    data.pr_urls = {}
    output = render_executive_summary(data)

    assert "API rate limit hit" in output, (
        f"Expected 'API rate limit hit' in output, got:\n{output[:600]}"
    )
    # Negative guard: must not collapse into the budget_exhausted message.
    assert "API budget exhausted" not in output, (
        f"Did not expect 'API budget exhausted' for api_rate_limit pause, got:\n{output[:600]}"
    )

    # Parallel regression guard: budget_exhausted still emits its own message.
    budget_data = ReportData()
    budget_data.state = OvernightState(
        session_id="test-session",
        features=features,
        paused_reason="budget_exhausted",
    )
    budget_data.pr_urls = {}
    budget_output = render_executive_summary(budget_data)

    assert "API budget exhausted" in budget_output, (
        f"Expected 'API budget exhausted' in output, got:\n{budget_output[:600]}"
    )
    assert "API rate limit hit" not in budget_output, (
        f"Did not expect 'API rate limit hit' for budget_exhausted pause, got:\n{budget_output[:600]}"
    )


# ---------------------------------------------------------------------------
# Integration tests for tier-conditional verification rendering (R13 / Task 5)
#
# Ten fixtures exercising the compat-shim helpers (`_read_tier`,
# `_read_acceptance`, `_read_last_phase_checkpoint`) and the rendered
# "How to try" line in `_render_feature_block`. Fixtures 4 and 10 specifically
# assert the generic fallback string — loud, visible degradation rather than
# silent empty. Plus two key-name assertion tests that pin the
# persistence-vs-user-facing distinction for `_read_tier`.
#
# Helpers in report.py use relative paths like ``Path("cortex/lifecycle/{feature}/…")``,
# so each test changes the working directory to ``tmp_path`` via
# ``monkeypatch.chdir`` and constructs the fixture files underneath.
# ---------------------------------------------------------------------------


def _write_plan(tmp_path: Path, feature: str, content: str) -> None:
    """Construct ``cortex/lifecycle/{feature}/plan.md`` under tmp_path."""
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "plan.md").write_text(content, encoding="utf-8")


def _write_events_log(tmp_path: Path, feature: str, events: list[dict]) -> None:
    """Construct ``cortex/lifecycle/{feature}/events.log`` (NDJSON, one event per line)."""
    import json as _json

    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    lines = [_json.dumps(e) for e in events]
    (feature_dir / "events.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_events_log_raw(tmp_path: Path, feature: str, raw: str) -> None:
    """Construct ``cortex/lifecycle/{feature}/events.log`` from raw text (for corrupt cases)."""
    feature_dir = tmp_path / "cortex" / "lifecycle" / feature
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "events.log").write_text(raw, encoding="utf-8")


def _render_how_to_try(feature: str) -> str:
    """Render the morning report for a single merged feature and extract the
    "How to try" line. Returns the line directly under the ``**How to try:**``
    marker.
    """
    features = {feature: OvernightFeatureStatus(status="merged", repo_path=None)}
    data = ReportData()
    data.state = OvernightState(session_id="test-session", features=features)
    data.pr_urls = {}
    output = render_completed_features(data)
    marker = "**How to try:**"
    assert marker in output, f"Expected '{marker}' in rendered output, got:\n{output[:600]}"
    lines = output.splitlines()
    idx = lines.index(marker)
    return lines[idx + 1]


GENERIC_FALLBACK = "See feature plan for verification steps."


# Plan-fixture builders -----------------------------------------------------

def _plan_with_acceptance(text: str = "Run `just test` and observe all green.") -> str:
    return (
        "# Plan\n\n"
        "## Outline\n\n"
        "### Phase 1: setup (tasks: 1)\n"
        "**Goal**: scaffold the work.\n"
        "**Checkpoint**: scaffolding compiles.\n\n"
        "### Phase 2: ship (tasks: 2)\n"
        "**Goal**: deliver.\n"
        "**Checkpoint**: tests pass locally.\n\n"
        "## Acceptance\n\n"
        f"{text}\n"
    )


def _plan_simple_with_outline(checkpoint: str = "the regression test now passes.") -> str:
    return (
        "# Plan\n\n"
        "## Outline\n\n"
        "### Phase 1: only (tasks: 1)\n"
        "**Goal**: fix it.\n"
        f"**Checkpoint**: {checkpoint}\n"
    )


def _plan_legacy_verification(text: str = "Manually exercise the X flow and confirm Y.") -> str:
    return (
        "# Plan\n\n"
        "## Verification Strategy\n\n"
        f"{text}\n"
    )


def _plan_degenerate() -> str:
    return (
        "# Plan\n\n"
        "## Tasks\n\n"
        "- Task 1: do the thing\n"
    )


def _plan_hybrid(outline_checkpoint: str = "outline-checkpoint-wins.",
                 legacy_text: str = "legacy-verification-should-be-ignored.") -> str:
    return (
        "# Plan\n\n"
        "## Outline\n\n"
        "### Phase 1: only (tasks: 1)\n"
        "**Goal**: do it.\n"
        f"**Checkpoint**: {outline_checkpoint}\n\n"
        "## Verification Strategy\n\n"
        f"{legacy_text}\n"
    )


def _plan_complex_no_acceptance(checkpoint: str = "final-phase-checkpoint-text.") -> str:
    return (
        "# Plan\n\n"
        "## Outline\n\n"
        "### Phase 1: setup (tasks: 1)\n"
        "**Goal**: scaffold.\n"
        "**Checkpoint**: stage one done.\n\n"
        "### Phase 2: ship (tasks: 2)\n"
        "**Goal**: ship it.\n"
        f"**Checkpoint**: {checkpoint}\n"
    )


def _plan_last_phase_missing_checkpoint(
    earlier_checkpoint: str = "earlier-phase-checkpoint-wins.",
) -> str:
    return (
        "# Plan\n\n"
        "## Outline\n\n"
        "### Phase 1: early (tasks: 1)\n"
        "**Goal**: groundwork.\n"
        f"**Checkpoint**: {earlier_checkpoint}\n\n"
        "### Phase 2: final (tasks: 2)\n"
        "**Goal**: wrap.\n"
    )


def _plan_legacy_plus_manual_acceptance(
    acceptance: str = "manual-acceptance-line.",
    legacy: str = "legacy-verification.",
) -> str:
    return (
        "# Plan\n\n"
        "## Verification Strategy\n\n"
        f"{legacy}\n\n"
        "## Acceptance\n\n"
        f"{acceptance}\n"
    )


class TestTenFixtureVerificationRendering:
    """Ten-fixture suite covering tier-conditional verification rendering."""

    # Fixture 1 -------------------------------------------------------------
    def test_fixture_1_complex_plan_with_acceptance(self, tmp_path, monkeypatch):
        """Complex plan with ``## Acceptance`` — renders the acceptance text."""
        from cortex_command.overnight.report import _read_acceptance

        feature = "f1-complex-with-acceptance"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_with_acceptance("acceptance-line-text-f1."))
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "complex"}],
        )

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "complex"
        assert _read_acceptance(feature) == "acceptance-line-text-f1."
        assert _render_how_to_try(feature) == "acceptance-line-text-f1."

    # Fixture 2 -------------------------------------------------------------
    def test_fixture_2_simple_plan_with_outline_checkpoint(self, tmp_path, monkeypatch):
        """Simple plan with ``## Outline`` + last-phase Checkpoint — renders it."""
        from cortex_command.overnight.report import _read_last_phase_checkpoint

        feature = "f2-simple-with-checkpoint"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_simple_with_outline("checkpoint-line-f2."))
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "simple"}],
        )

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "simple"
        assert _read_last_phase_checkpoint(feature) == "checkpoint-line-f2."
        assert _render_how_to_try(feature) == "checkpoint-line-f2."

    # Fixture 3 -------------------------------------------------------------
    def test_fixture_3_legacy_verification_strategy_only(self, tmp_path, monkeypatch):
        """Legacy plan with only ``## Verification Strategy`` — renders that section."""
        feature = "f3-legacy-verification"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_legacy_verification("legacy-text-f3."))
        # No events.log -> defaults to simple tier.

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "moderate"
        assert _render_how_to_try(feature) == "legacy-text-f3."

    # Fixture 4 -------------------------------------------------------------
    def test_fixture_4_degenerate_plan_generic_fallback(self, tmp_path, monkeypatch):
        """Degenerate plan — renders the generic fallback string (NOT empty)."""
        from cortex_command.overnight.report import (
            _read_acceptance,
            _read_last_phase_checkpoint,
        )

        feature = "f4-degenerate"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_degenerate())

        assert _read_acceptance(feature) == ""
        assert _read_last_phase_checkpoint(feature) == ""
        # Loud visible degradation, not silent empty.
        assert _render_how_to_try(feature) == GENERIC_FALLBACK

    # Fixture 5 -------------------------------------------------------------
    def test_fixture_5_hybrid_plan_new_shape_wins(self, tmp_path, monkeypatch):
        """HYBRID plan — new-shape reader (Outline) wins over legacy section."""
        from cortex_command.overnight.report import _read_last_phase_checkpoint

        feature = "f5-hybrid"
        monkeypatch.chdir(tmp_path)
        _write_plan(
            tmp_path, feature,
            _plan_hybrid(
                outline_checkpoint="new-shape-f5.",
                legacy_text="legacy-should-be-ignored-f5.",
            ),
        )
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "simple"}],
        )

        assert _read_last_phase_checkpoint(feature) == "new-shape-f5."
        rendered = _render_how_to_try(feature)
        assert rendered == "new-shape-f5."
        assert "legacy-should-be-ignored-f5." not in rendered

    # Fixture 6 -------------------------------------------------------------
    def test_fixture_6_complex_no_acceptance_falls_back_to_checkpoint(
        self, tmp_path, monkeypatch,
    ):
        """Complex tier with Outline but no Acceptance — falls back to last-phase Checkpoint."""
        from cortex_command.overnight.report import (
            _read_acceptance,
            _read_last_phase_checkpoint,
        )

        feature = "f6-complex-no-acceptance"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_complex_no_acceptance("complex-fallback-f6."))
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "complex"}],
        )

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "complex"
        assert _read_acceptance(feature) == ""
        assert _read_last_phase_checkpoint(feature) == "complex-fallback-f6."
        assert _render_how_to_try(feature) == "complex-fallback-f6."

    # Fixture 7 -------------------------------------------------------------
    def test_fixture_7_walk_backward_to_most_recent_populated_checkpoint(
        self, tmp_path, monkeypatch,
    ):
        """Simple plan; last phase heading present, Checkpoint field absent —
        walk backward to most recent populated Checkpoint."""
        from cortex_command.overnight.report import _read_last_phase_checkpoint

        feature = "f7-walk-backward"
        monkeypatch.chdir(tmp_path)
        _write_plan(
            tmp_path, feature,
            _plan_last_phase_missing_checkpoint("earlier-walked-back-f7."),
        )
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "simple"}],
        )

        assert _read_last_phase_checkpoint(feature) == "earlier-walked-back-f7."
        assert _render_how_to_try(feature) == "earlier-walked-back-f7."

    # Fixture 8 -------------------------------------------------------------
    def test_fixture_8_complex_prefers_acceptance_over_legacy(
        self, tmp_path, monkeypatch,
    ):
        """Legacy plan with manually-authored ``## Acceptance`` — complex tier
        prefers Acceptance (intentional going-forward stance)."""
        from cortex_command.overnight.report import _read_acceptance

        feature = "f8-complex-prefers-acceptance"
        monkeypatch.chdir(tmp_path)
        _write_plan(
            tmp_path, feature,
            _plan_legacy_plus_manual_acceptance(
                acceptance="manual-acceptance-f8.",
                legacy="legacy-should-lose-f8.",
            ),
        )
        _write_events_log(
            tmp_path, feature,
            [{"event": "lifecycle_start", "feature": feature, "tier": "complex"}],
        )

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "complex"
        assert _read_acceptance(feature) == "manual-acceptance-f8."
        rendered = _render_how_to_try(feature)
        assert rendered == "manual-acceptance-f8."
        assert "legacy-should-lose-f8." not in rendered

    # Fixture 9 -------------------------------------------------------------
    def test_fixture_9_complexity_override_escalates_to_complex(
        self, tmp_path, monkeypatch,
    ):
        """``complexity_override`` event escalated to ``tier=complex`` mid-lifecycle;
        plan still only has ``## Outline`` / no ``## Acceptance`` — same as fixture 6."""
        feature = "f9-override-to-complex"
        monkeypatch.chdir(tmp_path)
        _write_plan(tmp_path, feature, _plan_complex_no_acceptance("override-fallback-f9."))
        _write_events_log(
            tmp_path, feature,
            [
                {"event": "lifecycle_start", "feature": feature, "tier": "simple"},
                {"event": "complexity_override", "feature": feature,
                 "from": "simple", "to": "complex"},
            ],
        )

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "complex"
        assert _render_how_to_try(feature) == "override-fallback-f9."

    # Fixture 10 ------------------------------------------------------------
    def test_fixture_10_corrupted_events_log_complex_acceptance_only(
        self, tmp_path, monkeypatch,
    ):
        """Complex-tier plan with corrupted/missing events.log and an
        ``## Acceptance``-only verification source.

        Asserts:
          * ``_read_tier`` returns ``"simple"`` per R13a default (corrupted log
            falls back gracefully — NOT crash, NOT inferring tier from plan).
          * Because tier reads as simple, the simple-tier fallback chain
            (last-phase Checkpoint → Verification Strategy → generic fallback)
            runs. With no Outline and no Verification Strategy, the rendered
            line is the generic fallback string (loud visible degradation,
            NOT silent empty).
        """
        from cortex_command.overnight.report import (
            _read_acceptance,
            _read_last_phase_checkpoint,
        )

        feature = "f10-corrupted-events"
        monkeypatch.chdir(tmp_path)
        # Plan has ONLY an ## Acceptance section — no Outline, no Verification
        # Strategy. The acceptance section content would only be rendered if
        # tier resolved to complex; with a corrupted log it should not.
        plan_text = (
            "# Plan\n\n"
            "## Acceptance\n\n"
            "acceptance-text-f10.\n"
        )
        _write_plan(tmp_path, feature, plan_text)
        # Corrupted events.log: not valid JSON on any line.
        _write_events_log_raw(
            tmp_path, feature,
            "this is not json\n{also not json\n",
        )

        # R13a default: returns "simple" when events.log is malformed.
        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "moderate"
        # Acceptance text exists in the plan but is not consulted on simple tier.
        assert _read_acceptance(feature) == "acceptance-text-f10."
        # No Outline -> no last-phase checkpoint.
        assert _read_last_phase_checkpoint(feature) == ""
        # Generic fallback rendered — loud, visible degradation.
        assert _render_how_to_try(feature) == GENERIC_FALLBACK


# ---------------------------------------------------------------------------
# complexity_normalized rendering (backlog #278)
# ---------------------------------------------------------------------------

def _complexity_normalized_event(feature: str, task: int, original: str) -> dict:
    return {
        "event": "complexity_normalized",
        "round": 1,
        "feature": feature,
        "details": {"task": task, "original": original},
    }


def test_render_complexity_normalized_names_feature_and_original() -> None:
    """The report names the OOV feature and its original complexity value."""
    data = ReportData()
    data.events = [
        _complexity_normalized_event("oov-feature", 3, "medium"),
    ]
    output = render_complexity_normalized(data)

    assert "oov-feature" in output, f"got: {output!r}"
    assert "medium" in output, f"got: {output!r}"
    # Normalization direction is shown (-> complex).
    assert "complex" in output, f"got: {output!r}"


def test_render_complexity_normalized_dedups_resumed_feature() -> None:
    """Two identical (feature, task, original) events render exactly once.

    execute_feature re-parses and re-emits the same normalization each round
    for a paused-then-resumed feature; the renderer must collapse duplicates.
    """
    data = ReportData()
    data.events = [
        _complexity_normalized_event("oov-feature", 3, "medium"),
        _complexity_normalized_event("oov-feature", 3, "medium"),
    ]
    output = render_complexity_normalized(data)

    # The (feature, task, original) line appears exactly once.
    assert output.count("oov-feature") == 1, f"got: {output!r}"
    assert output.count("`medium`") == 1, f"got: {output!r}"
    # Section count reflects one unique normalization, not two events.
    assert "## Complexity Normalizations (1)" in output, f"got: {output!r}"


def test_render_complexity_normalized_empty_when_no_events() -> None:
    """The section is omitted entirely when no normalizations occurred."""
    data = ReportData()
    data.events = [{"event": "round_start", "round": 1}]
    assert render_complexity_normalized(data) == ""


def test_render_complexity_normalized_distinguishes_absent_from_oov() -> None:
    """461: an omitted field and an unrecognized value render as different rows.

    They resolve to different tiers and call for different corrections, so a
    renderer that showed both as `-> complex` (or showed the omission as the
    literal `None`) would misreport what the operator has to fix.
    """
    data = ReportData()
    data.events = [
        {"event": "complexity_normalized", "round": 1, "feature": "oov-feature",
         "details": {"task": 3, "original": "medium", "resolved": "complex"}},
        {"event": "complexity_normalized", "round": 1, "feature": "absent-feature",
         "details": {"task": 1, "original": None, "resolved": "moderate"}},
    ]
    output = render_complexity_normalized(data)

    assert "## Complexity Normalizations (2)" in output, f"got: {output!r}"
    assert "`medium` -> `complex`" in output, f"got: {output!r}"
    assert "*(absent)* -> `moderate`" in output, f"got: {output!r}"
    # The omission never renders as a Python None.
    assert "None" not in output, f"got: {output!r}"


def test_render_complexity_normalized_reads_pre_461_events() -> None:
    """461: events written before `resolved` existed still render as `complex`.

    A session log spanning the upgrade must not render its older rows with a
    blank or missing target tier.
    """
    data = ReportData()
    data.events = [_complexity_normalized_event("legacy-feature", 2, "medium")]
    output = render_complexity_normalized(data)

    assert "`medium` -> `complex`" in output, f"got: {output!r}"


# ---------------------------------------------------------------------------
# #313 R4/R5: effort-degradation rendering
# ---------------------------------------------------------------------------

def test_render_effort_degradation_lists_clamp_and_ignore() -> None:
    """Both the clamp and the warn-ignore degradations render with the feature."""
    data = ReportData()
    data.events = [
        {"event": "retry_effort_clamped", "feature": "feat-a",
         "model": "opus", "to_effort": "max"},
        {"event": "dispatch_effort_ignored", "feature": "feat-b",
         "model": "opus", "effort": "xhigh"},
    ]
    output = render_effort_degradation(data)
    assert "## Effort Degradations (2)" in output, f"got: {output!r}"
    assert "feat-a" in output and "clamped to `max`" in output, f"got: {output!r}"
    assert "feat-b" in output and "warn-ignored" in output, f"got: {output!r}"


def test_render_effort_degradation_dedups_by_feature_model() -> None:
    """Repeated clamp events for the same (feature, model) render once."""
    data = ReportData()
    data.events = [
        {"event": "retry_effort_clamped", "feature": "feat-a",
         "model": "opus", "to_effort": "max"},
        {"event": "retry_effort_clamped", "feature": "feat-a",
         "model": "opus", "to_effort": "max"},
    ]
    output = render_effort_degradation(data)
    assert "## Effort Degradations (1)" in output, f"got: {output!r}"
    assert output.count("feat-a") == 1, f"got: {output!r}"


def test_render_effort_degradation_empty_when_no_events() -> None:
    """The section is omitted entirely when no degradation occurred."""
    data = ReportData()
    data.events = [{"event": "round_start", "round": 1}]
    assert render_effort_degradation(data) == ""


def test_generate_report_includes_effort_degradation_heading() -> None:
    """generate_report wires the effort-degradation section into the report."""
    from cortex_command.overnight.report import generate_report

    data = ReportData()
    data.events = [
        {"event": "retry_effort_clamped", "feature": "feat-a",
         "model": "opus", "to_effort": "max"},
    ]
    assert "Effort Degradations" in generate_report(data)


# ---------------------------------------------------------------------------
# Task 6: recoverable features get no from-scratch-rebuild follow-up
# ---------------------------------------------------------------------------

def test_recoverable_no_rebuild_followup(tmp_path) -> None:
    """A recoverable deferred feature produces no 'Retry deferred' item.

    The genuine question-deferral still gets its existing follow-up.
    """
    from cortex_command.overnight.report import create_followup_backlog_items

    features = {
        "feat-recoverable": OvernightFeatureStatus(
            status="deferred", recoverable_branch="pipeline/feat-recoverable-2"
        ),
        "feat-question": OvernightFeatureStatus(status="deferred"),
    }
    data = _pytest_make_data(features)

    items = create_followup_backlog_items(data, backlog_dir=tmp_path)

    titles = [it.title for it in items]
    # Recoverable feature: NO rebuild follow-up.
    assert "Retry deferred: feat-recoverable" not in titles
    assert not list(tmp_path.glob("*-feat-recoverable.md"))
    # Genuine question-deferral: existing follow-up unchanged.
    assert "Retry deferred: feat-question" in titles
    assert list(tmp_path.glob("*-feat-question.md"))


# ---------------------------------------------------------------------------
# Task 7: recoverable features surfaced positively + excluded from deferred count
# ---------------------------------------------------------------------------

def test_recoverable_surface_positive() -> None:
    """Recoverable feature surfaced positively; deferred count excludes it.

    render_deferred_questions output stays byte-identical for the genuine
    question-deferral.
    """
    from cortex_command.overnight.report import (
        generate_report,
        render_deferred_questions,
    )
    from cortex_command.overnight.deferral import DeferralQuestion, SEVERITY_BLOCKING

    dq = DeferralQuestion(
        feature="feat-question",
        question_id=1,
        severity=SEVERITY_BLOCKING,
        context="implementing X",
        question="Which API endpoint should be used?",
    )
    features = {
        "feat-question": OvernightFeatureStatus(status="deferred"),
        "feat-recoverable": OvernightFeatureStatus(
            status="deferred", recoverable_branch="pipeline/feat-recoverable-2"
        ),
    }
    data = _pytest_make_data(features)
    data.deferrals = [dq]

    # (a) Report body positively surfaces the recoverable feature + its branch.
    body = generate_report(data)
    assert "Built, Merge-Blocked (Recoverable)" in body
    assert "pipeline/feat-recoverable-2" in body

    # (b) Exec-summary deferred-questions count is 1 (the question-deferral),
    #     not 2 — the recoverable feature is excluded.
    assert "- Features deferred: 1 (questions need answers)" in body

    # (c) render_deferred_questions is byte-identical to a baseline that lacks
    #     the recoverable feature in state — it is deferrals-driven, status-blind.
    baseline = _pytest_make_data(
        {"feat-question": OvernightFeatureStatus(status="deferred")}
    )
    baseline.deferrals = [dq]
    assert render_deferred_questions(data) == render_deferred_questions(baseline)


# ---------------------------------------------------------------------------
# Bug B: generated-ticket titles serialize as YAML-safe single-line scalars
# (R1 strict round-trip, R3 tolerant round-trip, R4 single-line sanitize,
# R5 layout preserved, plus the whole-backlog resolve() integration symptom).
# ---------------------------------------------------------------------------

def _frontmatter_keys_in_order(text: str) -> list[str]:
    """Return frontmatter keys in document order (first ``---`` block)."""
    lines = text.splitlines()
    assert lines[0] == "---"
    keys: list[str] = []
    for ln in lines[1:]:
        if ln == "---":
            break
        if ln and not ln.startswith(" ") and ":" in ln:
            keys.append(ln.split(":", 1)[0])
    return keys


def test_generated_titles_round_trip_strict(tmp_path) -> None:
    """R1: colon-bearing failed + deferred titles round-trip via the strict parser.

    Uses the REAL ``resolve_item._parse_frontmatter`` (yaml.safe_load) — the
    parser whose failure aborts the whole-backlog scan — and asserts the title
    returns exactly without raising.
    """
    from cortex_command.overnight.report import create_followup_backlog_items
    from cortex_command.backlog import resolve_item

    features = {
        "feat-fail:colon": OvernightFeatureStatus(status="failed", error="boom"),
        "feat-defer:colon": OvernightFeatureStatus(status="deferred"),
    }
    data = _pytest_make_data(features)
    items = create_followup_backlog_items(data, backlog_dir=tmp_path)

    by_title = {it.title: it for it in items}
    assert "Follow up: feat-fail:colon" in by_title
    assert "Retry deferred: feat-defer:colon" in by_title
    for title, it in by_title.items():
        fm = resolve_item._parse_frontmatter(tmp_path / it.filename)
        assert fm["title"] == title


def test_generated_title_tolerant_round_trip(tmp_path) -> None:
    """R3: realistic kebab title round-trips exactly through the tolerant index
    parser, on one physical line, with no YAML document-end (``...``) marker."""
    from cortex_command.overnight.report import create_followup_backlog_items
    from cortex_command.backlog import generate_index

    features = {"climb-gated-locomotion": OvernightFeatureStatus(status="deferred")}
    data = _pytest_make_data(features)
    items = create_followup_backlog_items(data, backlog_dir=tmp_path)
    it = items[0]
    title = "Retry deferred: climb-gated-locomotion"
    assert it.title == title

    text = (tmp_path / it.filename).read_text(encoding="utf-8")
    lines = text.splitlines()
    title_idx = next(i for i, ln in enumerate(lines) if ln.startswith("title:"))
    # The title occupies exactly one physical line (next key follows immediately).
    assert lines[title_idx + 1].startswith("status:")
    # No YAML document-end marker anywhere.
    assert all(ln.strip() != "..." for ln in lines)

    parsed = generate_index._parse_frontmatter(text)
    # generate_index strips wrapping quotes from the value (report.py consumer at
    # generate_index.py:162); mirror that to assert the exact round-trip.
    assert parsed["title"].strip("\"'") == title


def test_generated_title_newline_sanitized_single_line(tmp_path) -> None:
    """R4: an embedded newline in the feature name is collapsed so the title
    field is a single physical line the strict parser accepts (no raise)."""
    from cortex_command.overnight.report import create_followup_backlog_items
    from cortex_command.backlog import resolve_item

    features = {"line\nbreak": OvernightFeatureStatus(status="deferred")}
    data = _pytest_make_data(features)
    items = create_followup_backlog_items(data, backlog_dir=tmp_path)
    it = items[0]

    text = (tmp_path / it.filename).read_text(encoding="utf-8")
    lines = text.splitlines()
    title_idx = next(i for i, ln in enumerate(lines) if ln.startswith("title:"))
    # Single physical line: the very next line is the following key, so the
    # embedded newline did not fold the title across lines.
    assert lines[title_idx + 1].startswith("status:")

    # The strict parser (yaml.safe_load) accepts the serialized title scalar in
    # isolation and yields the sanitized one-line value. (Scope is the title
    # scalar only — lifecycle_slug carries the raw name but is never newline-
    # bearing in the real overnight flow, per spec Non-Requirements.)
    title_only = tmp_path / "title-only.md"
    title_only.write_text(f"---\n{lines[title_idx]}\n---\n", encoding="utf-8")
    fm = resolve_item._parse_frontmatter(title_only)
    assert fm["title"] == "Retry deferred: line break"


def test_generated_frontmatter_layout_preserved(tmp_path) -> None:
    """R5: only the title scalar is serialized — inline ``tags: [...]`` and the
    pre-fix field order are untouched."""
    from cortex_command.overnight.report import create_followup_backlog_items

    features = {"layout-feat": OvernightFeatureStatus(status="deferred")}
    data = _pytest_make_data(features)
    items = create_followup_backlog_items(data, backlog_dir=tmp_path)
    text = (tmp_path / items[0].filename).read_text(encoding="utf-8")

    # tags rendered inline exactly once.
    assert text.count("tags: [") == 1
    # Field order matches the pre-fix layout.
    assert _frontmatter_keys_in_order(text) == [
        "title", "status", "priority", "type", "tags", "created", "updated",
        "blocks", "blocked-by", "schema_version", "uuid", "lifecycle_slug",
        "session_id",
    ]


def test_whole_backlog_resolve_survives_colon_title(tmp_path) -> None:
    """Integration (the real Bug B symptom): the eager whole-backlog
    ``resolve()`` scan does not abort on a colon-titled generated ticket
    sitting beside a normal item."""
    from cortex_command.overnight.report import create_followup_backlog_items
    from cortex_command.backlog import resolve_item

    # A normal, valid backlog item.
    (tmp_path / "099-normal-item.md").write_text(
        "---\n"
        "title: A normal item\n"
        "status: backlog\n"
        "uuid: 11111111-1111-1111-1111-111111111111\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )

    features = {
        "feat-fail:colon": OvernightFeatureStatus(status="failed", error="boom"),
        "feat-defer:colon": OvernightFeatureStatus(status="deferred"),
    }
    data = _pytest_make_data(features)
    create_followup_backlog_items(data, backlog_dir=tmp_path)

    # The eager loop (resolve_item.py:423-431) parses EVERY file before routing.
    # Pre-fix it raised "failed to parse frontmatter" on the colon title, aborting
    # the whole backlog. Post-fix it must not.
    try:
        resolve_item.resolve("definitely-no-such-item-xyz", backlog_dir=tmp_path)
    except resolve_item.ResolutionError as exc:
        assert "failed to parse frontmatter" not in str(exc), (
            f"whole-backlog resolve() aborted on a generated ticket: {exc}"
        )


# ---------------------------------------------------------------------------
# Tests for failed-feature diagnostics rendering (R8)
# ---------------------------------------------------------------------------

import json as _json


def _write_task_output_event(
    path: Path,
    feature: str,
    *,
    output: str = "",
    child_stderr=None,
    exit_code=None,
    cwd=None,
    include_diagnostics: bool = True,
) -> None:
    """Write a single task_output event line to a pipeline-events.log fixture.

    When ``include_diagnostics`` is False, the diagnostics fields are omitted
    entirely (mirrors the success-path emit in feature_executor.py).
    """
    event = {
        "event": "task_output",
        "feature": feature,
        "task_number": 1,
        "task_description": "do a thing",
        "output": output,
    }
    if include_diagnostics:
        event["child_stderr"] = child_stderr
        event["exit_code"] = exit_code
        event["cwd"] = cwd
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(event) + "\n")


def test_failed_feature_renders_exit_code_and_stderr(tmp_path: Path) -> None:
    """Failed-feature block renders exit_code, cwd, and the stderr tail lines."""
    events_path = tmp_path / "pipeline-events.log"
    _write_task_output_event(
        events_path,
        "feat-crash",
        child_stderr="Traceback: ValueError boom at frobnicate()",
        exit_code=1,
        cwd="/work/feat-crash",
    )
    features = {
        "feat-crash": OvernightFeatureStatus(status="failed", error="ProcessError: exit code 1"),
    }
    data = _pytest_make_data(features)
    data.pipeline_events_path = events_path

    output = render_failed_features(data)

    assert "- **exit_code**: 1" in output, f"got:\n{output}"
    assert "/work/feat-crash" in output, f"got:\n{output}"
    assert "**stderr tail**" in output, f"got:\n{output}"
    assert "Traceback: ValueError boom at frobnicate()" in output, f"got:\n{output}"


def test_failed_feature_empty_stderr_renders_empty_marker(tmp_path: Path) -> None:
    """An empty/absent stderr renders the literal `(empty)` marker (silent crash)."""
    events_path = tmp_path / "pipeline-events.log"
    _write_task_output_event(
        events_path,
        "feat-silent",
        child_stderr="",
        exit_code=1,
        cwd="/work/feat-silent",
    )
    features = {
        "feat-silent": OvernightFeatureStatus(status="failed", error="ProcessError: exit code 1"),
    }
    data = _pytest_make_data(features)
    data.pipeline_events_path = events_path

    output = render_failed_features(data)

    assert "(empty)" in output, f"expected literal '(empty)' marker, got:\n{output}"


def test_failed_feature_none_exit_code_renders_unknown_marker(tmp_path: Path) -> None:
    """A None exit_code (timeout/connection failure) renders the literal `unknown`."""
    events_path = tmp_path / "pipeline-events.log"
    _write_task_output_event(
        events_path,
        "feat-timeout",
        child_stderr="connection reset",
        exit_code=None,
        cwd="/work/feat-timeout",
    )
    features = {
        "feat-timeout": OvernightFeatureStatus(status="failed", error="CLIConnectionError"),
    }
    data = _pytest_make_data(features)
    data.pipeline_events_path = events_path

    output = render_failed_features(data)

    assert "- **exit_code**: unknown" in output, (
        f"expected literal 'unknown' for None exit_code, got:\n{output}"
    )


def test_failed_feature_stderr_tail_exceeds_500_keeps_tail(tmp_path: Path) -> None:
    """A stderr longer than 500 chars but within the cap renders with its TAIL intact.

    Re-budget guard: pins the larger-than-500 cap intent. A regression to the
    500-char `output` cap would clip the diagnostically-valuable END and fail
    this test.
    """
    from cortex_command.overnight.report import _STDERR_TAIL_CAP

    tail_sentinel = "FINAL_FAILING_ASSERTION_AT_THE_END"
    # Build a stderr longer than 500 but within the tail cap, ending in the
    # sentinel so we can assert the tail survives.
    head = "X" * 700
    long_stderr = head + tail_sentinel
    assert len(long_stderr) > 500
    assert len(long_stderr) <= _STDERR_TAIL_CAP

    events_path = tmp_path / "pipeline-events.log"
    _write_task_output_event(
        events_path,
        "feat-long",
        child_stderr=long_stderr,
        exit_code=1,
        cwd="/work/feat-long",
    )
    features = {
        "feat-long": OvernightFeatureStatus(status="failed", error="ProcessError: exit code 1"),
    }
    data = _pytest_make_data(features)
    data.pipeline_events_path = events_path

    output = render_failed_features(data)

    assert tail_sentinel in output, (
        f"stderr tail was clipped (regression to 500 cap?); sentinel missing from:\n{output[-600:]}"
    )


def test_failed_feature_success_path_omits_diagnostics(tmp_path: Path) -> None:
    """A task_output event without diagnostics fields renders no diagnostics lines."""
    events_path = tmp_path / "pipeline-events.log"
    _write_task_output_event(
        events_path,
        "feat-nodiag",
        output="some assistant text",
        include_diagnostics=False,
    )
    features = {
        "feat-nodiag": OvernightFeatureStatus(status="failed", error="something else"),
    }
    data = _pytest_make_data(features)
    data.pipeline_events_path = events_path

    output = render_failed_features(data)

    assert "**exit_code**" not in output, f"got:\n{output}"
    assert "**stderr tail**" not in output, f"got:\n{output}"


def test_report_diagnostics_markers_match_brain_constants() -> None:
    """Report marker literals are byte-identical to the brain-prompt markers.

    Guards drift: an operator comparing the morning report and the brain prompt
    must see the same `(empty)`/`unknown` labels.
    """
    from cortex_command.overnight import report as _report_module
    from cortex_command.overnight import brain as _brain_module

    assert (
        _report_module._DIAGNOSTICS_EMPTY_STDERR
        == _brain_module._DIAGNOSTICS_EMPTY_STDERR
    )
    assert (
        _report_module._DIAGNOSTICS_UNKNOWN_EXIT
        == _brain_module._DIAGNOSTICS_UNKNOWN_EXIT
    )



# ---------------------------------------------------------------------------
# Integration-worktree loss: the reader half of the purged-worktree lifecycle
# (#465 Reqs 8, 9, 11).
#
# The event fixtures below are PRODUCER-DRIVEN: each one drives the real
# outcome_router path (Task 1's merge-target resolver, Task 2's deferral
# terminus) against a real on-disk git repo and reads back the log those paths
# actually wrote. Hand-written event dicts would green this reader against a
# contract the producer may not emit, which is the exact failure mode the
# section exists to catch.
# ---------------------------------------------------------------------------

import asyncio as _asyncio
import shutil as _shutil
import subprocess as _subprocess
from unittest.mock import patch as _patch


def _wtloss_git(cwd: Path, *args: str) -> str:
    return _subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    ).stdout.strip()


def _wtloss_build_repo(td: Path, session_id: str) -> tuple[Path, Path, str]:
    """A real home repo on main, a feature branch carrying a commit, an
    integration branch, and a real second worktree owning ``overnight/<id>``.

    Returns ``(home, worktree, feature_branch)``.
    """
    home = td / "home"
    home.mkdir()
    branch = f"overnight/{session_id}"

    _wtloss_git(home, "init", "-q", "-b", "main")
    _wtloss_git(home, "config", "user.email", "t@example.com")
    _wtloss_git(home, "config", "user.name", "Test")
    _wtloss_git(home, "config", "commit.gpgsign", "false")
    (home / "README.md").write_text("seed\n")
    _wtloss_git(home, "add", "README.md")
    _wtloss_git(home, "commit", "-q", "-m", "seed")

    feature_branch = f"pipeline/{session_id}-feat"
    _wtloss_git(home, "checkout", "-q", "-b", feature_branch)
    (home / "feature.txt").write_text("feature work\n")
    _wtloss_git(home, "add", "feature.txt")
    _wtloss_git(home, "commit", "-q", "-m", "feature commit")

    _wtloss_git(home, "checkout", "-q", "main")
    _wtloss_git(home, "branch", branch, "main")

    wt = td / "integration-worktree"
    _wtloss_git(home, "worktree", "add", "-q", str(wt), branch)
    _wtloss_git(home, "checkout", "-q", "main")

    return home, wt, feature_branch


def _wtloss_make_ctx(
    *,
    home: Path,
    worktree: Path | None,
    session_id: str,
    feature: str,
    feature_branch: str,
    home_repo_path: Path | None,
):
    from cortex_command.overnight.orchestrator import BatchConfig, BatchResult
    from cortex_command.overnight.outcome_router import OutcomeContext
    from cortex_command.overnight.types import CircuitBreakerState

    config = BatchConfig(
        batch_id=1,
        plan_path=home / "plan.md",
        test_command=None,
        base_branch=f"overnight/{session_id}",
        overnight_state_path=home / "overnight-state.json",
        overnight_events_path=home / "overnight-events.log",
        result_dir=home,
        pipeline_events_path=home / "pipeline-events.log",
        session_id=session_id,
    )
    return OutcomeContext(
        batch_result=BatchResult(batch_id=1),
        lock=_asyncio.Lock(),
        cb_state=CircuitBreakerState(consecutive_pauses=0),
        recovery_attempts_map={},
        worktree_paths={},
        worktree_branches={feature: feature_branch},
        repo_path_map={feature: None},
        integration_worktrees={},
        integration_branches={},
        session_id=session_id,
        backlog_ids={},
        feature_names=[feature],
        config=config,
        home_worktree_path=worktree,
        home_repo_path=home_repo_path,
    )


def _wtloss_drive_producer(td: Path, session_id: str, *, recoverable: bool) -> list[dict]:
    """Drive the REAL outcome_router against a purged integration worktree and
    return the events it wrote.

    ``recoverable=True`` gives the resolver the home repo and its integration
    branch, so it re-creates the worktree in place (Task 1). ``False`` withholds
    the repo, so re-creation is impossible and the feature is deferred (Task 2).
    """
    from cortex_command.overnight.events import read_events
    from cortex_command.overnight.outcome_router import apply_feature_result, set_backlog_dir
    from cortex_command.overnight.state import _normalize_repo_key
    from cortex_command.overnight.types import FeatureResult

    feature = f"{session_id}-feat"
    home, wt, feature_branch = _wtloss_build_repo(td, session_id)

    ctx = _wtloss_make_ctx(
        home=home,
        worktree=wt,
        session_id=session_id,
        feature=feature,
        feature_branch=feature_branch,
        home_repo_path=home if recoverable else None,
    )
    if recoverable:
        ctx.integration_branches[_normalize_repo_key(str(home))] = f"overnight/{session_id}"

    # The purge: TMPDIR takes the integration worktree mid-session.
    _shutil.rmtree(wt)

    # Keep the backlog write-back inside the temp dir; the deferral terminus
    # writes back unconditionally and must not touch the real backlog.
    backlog_dir = td / "backlog"
    backlog_dir.mkdir()
    set_backlog_dir(backlog_dir)
    try:
        with (
            _patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["feature.txt"],
            ),
            _patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
            _patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
            _patch(
                "cortex_command.pipeline.merge._check_ci_status",
                return_value="skipped",
            ),
        ):
            _asyncio.run(
                apply_feature_result(
                    feature,
                    FeatureResult(name=feature, status="completed"),
                    ctx,
                )
            )
    finally:
        set_backlog_dir(None)  # type: ignore[arg-type]

    return list(read_events(ctx.config.overnight_events_path))


def _wtloss_section(report: str) -> str:
    """Slice the Integration Worktree Loss section out of a full report."""
    heading = "## Integration Worktree Loss"
    assert heading in report, f"section heading missing from report:\n{report}"
    start = report.index(heading)
    rest = report[start + len(heading):]
    end = rest.find("\n## ")
    return heading + (rest if end == -1 else rest[:end])


def test_worktree_loss_section_names_branch_not_a_rerun(tmp_path: Path) -> None:
    """Req 8 — an unresolvable integration worktree defers the feature, and the
    report names the pipeline branch its finished work is on rather than the
    generic retry advice that would send the operator to rebuild it.

    Producer-driven: the events come from the real Task-2 deferral terminus.
    """
    from cortex_command.overnight.report import ReportData, generate_report

    session_id = "overnight-report-unresolved"
    events = _wtloss_drive_producer(tmp_path, session_id, recoverable=False)

    # The producer really did take the unrecoverable arm.
    deferrals = [
        e for e in events
        if e["event"] == "feature_deferred"
        and (e.get("details") or {}).get("unresolved_worktree") is True
    ]
    assert len(deferrals) == 1, f"producer emitted no unresolved-worktree deferral: {events}"
    branch = deferrals[0]["details"]["branch"]
    assert branch == f"pipeline/{session_id}-feat", f"got {branch!r}"

    data = ReportData(session_id=session_id, date="2026-08-07", events=events)
    section = _wtloss_section(generate_report(data))

    assert branch in section, f"branch not named in section:\n{section}"
    assert f"{session_id}-feat" in section, f"feature not named in section:\n{section}"
    assert "retry or investigate" not in section, (
        f"section advises the rebuild that discards the work:\n{section}"
    )


def test_worktree_loss_section_reports_rebuild_count(tmp_path: Path) -> None:
    """Req 9 — a worktree that was successfully re-created in place is reported
    as a rebuild count, so a recovered session is still visible in the morning.

    Producer-driven: the events come from the real Task-1 merge-target resolver.
    """
    from cortex_command.overnight.report import ReportData, generate_report

    session_id = "overnight-report-recreated"
    events = _wtloss_drive_producer(tmp_path, session_id, recoverable=True)

    # The producer really did take the recoverable arm.
    rebuilds = [
        e for e in events
        if e["event"] == "integration_worktree_missing"
        and (e.get("details") or {}).get("recreated") is True
    ]
    assert rebuilds, f"producer recorded no re-creation: {events}"
    assert rebuilds[0]["details"]["context"] == "merge_target"

    data = ReportData(session_id=session_id, date="2026-08-07", events=events)
    section = _wtloss_section(generate_report(data))

    assert f"{len(rebuilds)} time(s)" in section, f"rebuild count missing from:\n{section}"
    assert "re-created" in section, f"rebuild line missing from:\n{section}"


def test_worktree_loss_section_omitted_when_nothing_lost() -> None:
    """No loss events at all — the section is omitted entirely."""
    from cortex_command.overnight.report import (
        ReportData,
        render_integration_worktree_loss,
    )

    data = ReportData(session_id="s", date="2026-08-07", events=[
        {"event": "feature_merged", "feature": "a", "details": {}},
    ])
    assert render_integration_worktree_loss(data) == ""


def test_worktree_loss_renders_branch_not_recorded_when_absent() -> None:
    """A deferral whose branch was never recorded renders an explicit marker
    rather than an empty backtick pair the operator cannot act on."""
    from cortex_command.overnight.report import (
        ReportData,
        render_integration_worktree_loss,
    )

    data = ReportData(session_id="s", date="2026-08-07", events=[
        {
            "event": "feature_deferred",
            "feature": "feat-nobranch",
            "details": {
                "error": "integration worktree unresolved",
                "unresolved_worktree": True,
                "branch": None,
            },
        },
    ])
    section = render_integration_worktree_loss(data)

    assert "branch not recorded" in section, f"got:\n{section}"
    assert "retry or investigate" not in section, f"got:\n{section}"


def test_worktree_loss_sorts_mixed_branch_nullness() -> None:
    """Two deferrals sharing a feature name but differing in branch-nullness must
    still order — a bare sorted() compares None with str and raises TypeError,
    which takes the whole morning report down with it.

    Hand-built events, deliberately: the property under test is sort stability
    over event details, and a producer cannot be made to emit two same-named
    deferrals in one session. The producer-driven fixtures above cover the
    contract itself, so the producer-driven rule is not forgotten here.
    """
    from cortex_command.overnight.report import (
        ReportData,
        render_integration_worktree_loss,
    )

    def _deferral(branch: str | None) -> dict:
        return {
            "event": "feature_deferred",
            "feature": "feat",
            "details": {
                "error": "integration worktree unresolved",
                "unresolved_worktree": True,
                "branch": branch,
            },
        }

    data = ReportData(session_id="s", date="2026-08-07", events=[
        _deferral("pipeline/s-feat"),
        _deferral(None),
    ])
    section = render_integration_worktree_loss(data)

    assert "pipeline/s-feat" in section, f"got:\n{section}"
    assert "branch not recorded" in section, f"got:\n{section}"


# ---------------------------------------------------------------------------
# render_built_merge_blocked coverage (Req 11). The function is NOT modified by
# this task; these tests are its first coverage, and they pin it as a
# disposition DISTINCT from the unresolved-worktree deferral above — that path
# deliberately records no recoverable_branch, so it must not leak in here.
# ---------------------------------------------------------------------------

def test_built_merge_blocked_names_recoverable_branch() -> None:
    """A feature carrying recoverable_branch is named with its branch."""
    from cortex_command.overnight.report import render_built_merge_blocked

    data = _pytest_make_data({
        "feat-conflicted": OvernightFeatureStatus(
            status="deferred", recoverable_branch="pipeline/feat-conflicted-2"
        ),
    })

    output = render_built_merge_blocked(data)

    assert "## Built, Merge-Blocked (Recoverable)" in output, f"got:\n{output}"
    assert "feat-conflicted" in output, f"got:\n{output}"
    assert "pipeline/feat-conflicted-2" in output, f"got:\n{output}"


def test_built_merge_blocked_omitted_for_unresolved_worktree_deferral(
    tmp_path: Path,
) -> None:
    """An unresolved-worktree deferral is NOT a recoverable merge-block.

    It records no recoverable_branch (the merge was never attempted, so the
    branch is not a verified-mergeable recovery point), so the built-but-
    merge-blocked section stays empty and its heading is absent from the full
    report — while the worktree-loss section that owns this disposition renders.
    """
    from cortex_command.overnight.report import (
        ReportData,
        generate_report,
        render_built_merge_blocked,
    )

    session_id = "overnight-report-distinct"
    events = _wtloss_drive_producer(tmp_path, session_id, recoverable=False)
    feature = f"{session_id}-feat"

    data = ReportData(session_id=session_id, date="2026-08-07", events=events)
    data.state = _pytest_make_state({
        feature: OvernightFeatureStatus(status="deferred"),
    })

    assert render_built_merge_blocked(data) == "", (
        "unresolved-worktree deferral leaked into the recoverable merge-block section"
    )
    report = generate_report(data)
    assert "## Built, Merge-Blocked (Recoverable)" not in report, f"got:\n{report}"
    assert "## Integration Worktree Loss" in report, f"got:\n{report}"


def test_built_merge_blocked_empty_without_state() -> None:
    """No state loaded at all — the section is omitted rather than crashing."""
    from cortex_command.overnight.report import ReportData, render_built_merge_blocked

    data = ReportData()
    assert data.state is None
    assert render_built_merge_blocked(data) == ""
