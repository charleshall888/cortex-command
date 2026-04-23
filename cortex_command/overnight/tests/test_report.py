#!/usr/bin/env python3
"""Tests for render_completed_features grouping by repo."""

import pytest
from pathlib import Path

from cortex_command.overnight.report import ReportData, render_completed_features, render_failed_features
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState


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
