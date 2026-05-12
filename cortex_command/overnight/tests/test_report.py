#!/usr/bin/env python3
"""Tests for render_completed_features grouping by repo."""

import pytest
from pathlib import Path

from cortex_command.overnight.report import ReportData, render_completed_features, render_executive_summary, render_failed_features
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

@pytest.mark.xfail(reason="Pre-Task 4: render_completed_features ignores integration_branches")
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

        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "simple"
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
        assert read_tier(feature, lifecycle_base=tmp_path / "cortex" / "lifecycle") == "simple"
        # Acceptance text exists in the plan but is not consulted on simple tier.
        assert _read_acceptance(feature) == "acceptance-text-f10."
        # No Outline -> no last-phase checkpoint.
        assert _read_last_phase_checkpoint(feature) == ""
        # Generic fallback rendered — loud, visible degradation.
        assert _render_how_to_try(feature) == GENERIC_FALLBACK


