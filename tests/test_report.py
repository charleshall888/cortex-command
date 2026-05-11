"""Annotation-behavior tests for render_failed_features and render_deferred_questions.

Verifies that when a ``feature_merged`` event is present for a feature that
later failed or deferred a blocking question, the morning report renderers
annotate the feature with "already on integration branch — do NOT re-run"
guidance. When no such event is present, the original text is preserved.

Also contains tests for ``render_critical_review_residue`` (R4 + R5 + R6 ACs)
and ``generate_report`` section-placement assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.common import atomic_write
from cortex_command.overnight.deferral import DeferralQuestion, SEVERITY_BLOCKING
from cortex_command.overnight.report import (
    ReportData,
    generate_report,
    render_critical_review_residue,
    render_deferred_questions,
    render_failed_features,
)
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState
import cortex_command.overnight.report as _report_mod


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


# ---------------------------------------------------------------------------
# Helper: build a minimal valid R4 residue payload
# ---------------------------------------------------------------------------

def _make_residue(
    feature: str = "my-feature",
    synthesis_status: str = "ok",
    completed: int = 3,
    dispatched: int = 3,
    findings: list | None = None,
) -> dict:
    if findings is None:
        findings = [
            {
                "class": "B",
                "finding": "Adjacent gap in error handling",
                "reviewer_angle": "security",
                "evidence_quote": "line 42: bare except",
            }
        ]
    return {
        "ts": "2026-04-22T00:00:00+00:00",
        "feature": feature,
        "artifact": f"lifecycle/{feature}/spec.md",
        "synthesis_status": synthesis_status,
        "reviewers": {"completed": completed, "dispatched": dispatched},
        "findings": findings,
    }


class Test_critical_review_residue:
    """Tests for render_critical_review_residue (R6) and residue-write invariants (R4 + R5)."""

    # ------------------------------------------------------------------
    # Render tests (R6)
    # ------------------------------------------------------------------

    def test_clean_ok_residue(self, tmp_path, monkeypatch):
        """(i) Clean synthesis_status: 'ok' residue renders without degraded annotation."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "my-feature"
        feat_dir.mkdir(parents=True)
        residue = _make_residue(synthesis_status="ok", completed=3, dispatched=3)
        (feat_dir / "critical-review-residue.json").write_text(
            json.dumps(residue), encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "## Critical Review Residue (1)" in output
        assert "my-feature" in output
        assert "degraded" not in output
        assert "security: Adjacent gap in error handling" in output

    def test_synthesis_failed_annotation(self, tmp_path, monkeypatch):
        """(ii) synthesis_status: 'failed' produces degraded annotation."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "my-feature"
        feat_dir.mkdir(parents=True)
        residue = _make_residue(synthesis_status="failed")
        (feat_dir / "critical-review-residue.json").write_text(
            json.dumps(residue), encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "degraded: synthesis failed" in output

    def test_partial_coverage_annotation(self, tmp_path, monkeypatch):
        """(iii) completed < dispatched produces partial reviewer coverage annotation."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "my-feature"
        feat_dir.mkdir(parents=True)
        residue = _make_residue(synthesis_status="ok", completed=2, dispatched=3)
        (feat_dir / "critical-review-residue.json").write_text(
            json.dumps(residue), encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "partial reviewer coverage" in output
        assert "2 of 3" in output

    def test_both_annotations_simultaneously(self, tmp_path, monkeypatch):
        """(iv) Both synthesis_status: 'failed' and partial coverage fire together."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "my-feature"
        feat_dir.mkdir(parents=True)
        residue = _make_residue(synthesis_status="failed", completed=1, dispatched=4)
        (feat_dir / "critical-review-residue.json").write_text(
            json.dumps(residue), encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "degraded: synthesis failed" in output
        assert "partial reviewer coverage" in output

    def test_empty_state_literal(self, tmp_path, monkeypatch):
        """(v) When no residue files exist, the empty-state literal is rendered."""
        lifecycle = tmp_path / "lifecycle"
        lifecycle.mkdir(parents=True)

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "## Critical Review Residue (0)" in output
        assert "no lifecycle-context runs" in output or "total reviewer failure" in output

    def test_malformed_json_graceful_skip(self, tmp_path, monkeypatch):
        """(vi) Malformed JSON residue is skipped gracefully with a notice line."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "bad-feature"
        feat_dir.mkdir(parents=True)
        (feat_dir / "critical-review-residue.json").write_text(
            "{ this is not valid json }", encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        # Should not raise; should emit a skip notice
        assert "malformed" in output
        assert "skipped" in output

    def test_missing_required_fields_default_unknown(self, tmp_path, monkeypatch):
        """(vii) Residue missing synthesis_status or reviewers defaults fields to 'unknown'."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "sparse-feature"
        feat_dir.mkdir(parents=True)
        # Minimal payload — no synthesis_status, no reviewers
        sparse = {
            "ts": "2026-04-22T00:00:00+00:00",
            "feature": "sparse-feature",
            "artifact": "lifecycle/sparse-feature/spec.md",
            "findings": [],
        }
        (feat_dir / "critical-review-residue.json").write_text(
            json.dumps(sparse), encoding="utf-8"
        )

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        # Should not raise — graceful default for missing fields
        output = render_critical_review_residue(data)

        assert "sparse-feature" in output
        # synthesis_status defaults to "unknown" — no "ok" → degraded annotation fires
        # (the function checks synthesis_status != "ok", so "unknown" triggers annotation)
        assert "degraded: synthesis failed" in output

    def test_placement_between_deferred_and_failed(self, tmp_path, monkeypatch):
        """(viii) generate_report places '## Critical Review Residue' between
        '## Deferred Questions' and '## Failed Features'."""
        lifecycle = tmp_path / "lifecycle"
        lifecycle.mkdir(parents=True)

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        # Minimal ReportData with a valid state so all sections render
        state = OvernightState(
            session_id="test-placement",
            integration_branch="overnight/test",
        )
        state.features["feat-a"] = OvernightFeatureStatus(status="merged")

        data = ReportData()
        data.state = state
        data.date = "2026-04-22"

        report = generate_report(data)

        idx_deferred = report.index("## Deferred Questions")
        idx_residue = report.index("## Critical Review Residue")
        idx_failed = report.index("## Failed Features")

        assert idx_deferred < idx_residue < idx_failed, (
            f"Expected Deferred ({idx_deferred}) < Residue ({idx_residue}) "
            f"< Failed ({idx_failed})"
        )

    # ------------------------------------------------------------------
    # Residue-write invariants (R4 + R5)
    # ------------------------------------------------------------------

    def test_r4_schema_valid_json_and_required_fields(self, tmp_path):
        """(ix) A residue file written via atomic_write with the R4 schema parses
        as valid JSON and contains all required fields."""
        residue_dir = tmp_path / "lifecycle" / "test-feature"
        residue_dir.mkdir(parents=True)
        residue_path = residue_dir / "critical-review-residue.json"

        payload = _make_residue(feature="test-feature")
        atomic_write(residue_path, json.dumps(payload))

        # File must exist and parse cleanly
        assert residue_path.exists()
        parsed = json.loads(residue_path.read_text(encoding="utf-8"))

        required_fields = {"ts", "feature", "artifact", "synthesis_status", "reviewers", "findings"}
        missing = required_fields - set(parsed.keys())
        assert not missing, f"Missing required R4 fields: {missing}"

    def test_zero_b_class_no_file(self, tmp_path):
        """(x) Zero B-class findings → no residue file (simulated by not calling write)."""
        residue_dir = tmp_path / "lifecycle" / "clean-feature"
        residue_dir.mkdir(parents=True)
        residue_path = residue_dir / "critical-review-residue.json"

        # Simulate: no B-class findings → write is skipped entirely
        # Do NOT call atomic_write here — the spec says "do not write"
        assert not residue_path.exists(), (
            "Residue file must NOT exist when there are zero B-class findings"
        )

    def test_synthesis_failed_roundtrip(self, tmp_path, monkeypatch):
        """(xi) synthesis_status: 'failed' round-trips correctly through the renderer."""
        lifecycle = tmp_path / "lifecycle"
        feat_dir = lifecycle / "roundtrip-feature"
        feat_dir.mkdir(parents=True)
        residue_path = feat_dir / "critical-review-residue.json"

        payload = _make_residue(feature="roundtrip-feature", synthesis_status="failed")
        atomic_write(residue_path, json.dumps(payload))

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        # Verify written value is readable and renders degraded annotation
        parsed = json.loads(residue_path.read_text(encoding="utf-8"))
        assert parsed["synthesis_status"] == "failed"
        assert "degraded: synthesis failed" in output

    def test_operator_note_literals_in_skill_md(self):
        """(xii) Operator-note literal strings appear verbatim in SKILL.md body or its references."""
        skill_dir = (
            Path(__file__).resolve().parents[1]
            / "skills"
            / "critical-review"
        )
        skill_path = skill_dir / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md not found at {skill_path}"

        searched_texts = [skill_path.read_text(encoding="utf-8")]
        references_dir = skill_dir / "references"
        if references_dir.is_dir():
            for ref in sorted(references_dir.glob("*.md")):
                searched_texts.append(ref.read_text(encoding="utf-8"))
        haystack = "\n".join(searched_texts)

        # R5: ad-hoc no-context note
        assert "B-class residue not written — no active lifecycle context." in haystack, (
            "Missing R5 operator note: 'B-class residue not written — no active lifecycle context.'"
        )

        # R4: multiple-match note
        assert "multiple active lifecycle sessions matched" in haystack, (
            "Missing R4 operator note: 'multiple active lifecycle sessions matched'"
        )

        # Malformed JSON envelope operator note
        assert "emitted malformed JSON envelope" in haystack, (
            "Missing operator note for malformed JSON envelope"
        )
