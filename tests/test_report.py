"""Annotation-behavior tests for render_failed_features and render_deferred_questions.

Verifies that when a ``feature_merged`` event is present for a feature that
later failed or deferred a blocking question, the morning report renderers
annotate the feature with "already on integration branch — do NOT re-run"
guidance. When no such event is present, the original text is preserved.
"""

from __future__ import annotations

from claude.overnight.deferral import DeferralQuestion, SEVERITY_BLOCKING
from claude.overnight.report import (
    ReportData,
    render_deferred_questions,
    render_failed_features,
)
from claude.overnight.state import OvernightFeatureStatus, OvernightState


class TestMergedFeatureAnnotations:
    """Verify annotation behavior keyed on the feature_merged event."""

    def test_render_failed_features_annotates_merged_feature(self):
        """Failed feature WITH feature_merged event gets the annotation."""
        state = OvernightState(
            session_id="test-session",
            integration_branch="overnight/test",
        )
        state.features["feat-x"] = OvernightFeatureStatus(
            status="failed",
            error="dispatch_review raised RuntimeError",
        )

        data = ReportData()
        data.state = state
        data.events = [{"event": "feature_merged", "feature": "feat-x"}]

        output = render_failed_features(data)

        assert "Feature is on the integration branch" in output
        assert "Do NOT re-run the feature" in output
        assert "overnight-events.log" in output

    def test_render_failed_features_no_annotation_without_merged_event(self):
        """Failed feature WITHOUT event does NOT get 'integration branch' text."""
        state = OvernightState(
            session_id="test-session",
            integration_branch="overnight/test",
        )
        state.features["feat-x"] = OvernightFeatureStatus(
            status="failed",
            error="dispatch_review raised RuntimeError",
        )

        data = ReportData()
        data.state = state
        data.events = []

        output = render_failed_features(data)

        assert "integration branch" not in output

    def test_render_deferred_questions_annotates_merged_blocking_deferral(self):
        """SEVERITY_BLOCKING deferral WITH feature_merged event gets override."""
        state = OvernightState(
            session_id="test-session",
            integration_branch="overnight/test",
        )
        state.features["feat-x"] = OvernightFeatureStatus(
            status="failed",
            error="dispatch_review raised RuntimeError",
        )

        data = ReportData()
        data.state = state
        data.events = [{"event": "feature_merged", "feature": "feat-x"}]
        data.deferrals = [
            DeferralQuestion(
                feature="feat-x",
                question_id=1,
                severity=SEVERITY_BLOCKING,
                context="ctx",
                question="q?",
                pipeline_attempted="dispatch_review()",
            )
        ]

        output = render_deferred_questions(data)

        assert "Feature is on the integration branch" in output
        assert "overnight-events.log" in output
        assert "re-run the feature" not in output

    def test_render_deferred_questions_no_annotation_without_merged_event(self):
        """SEVERITY_BLOCKING deferral WITHOUT event keeps the original text."""
        state = OvernightState(
            session_id="test-session",
            integration_branch="overnight/test",
        )
        state.features["feat-x"] = OvernightFeatureStatus(
            status="failed",
            error="dispatch_review raised RuntimeError",
        )

        data = ReportData()
        data.state = state
        data.events = []
        data.deferrals = [
            DeferralQuestion(
                feature="feat-x",
                question_id=1,
                severity=SEVERITY_BLOCKING,
                context="ctx",
                question="q?",
                pipeline_attempted="dispatch_review()",
            )
        ]

        output = render_deferred_questions(data)

        assert "Answer this question and re-run the feature" in output
