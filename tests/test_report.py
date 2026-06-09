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
        "artifact": f"cortex/lifecycle/{feature}/spec.md",
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
        lifecycle.mkdir(parents=True)

        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        output = render_critical_review_residue(data)

        assert "## Critical Review Residue (0)" in output
        assert "no lifecycle-context runs" in output or "total reviewer failure" in output

    def test_malformed_json_graceful_skip(self, tmp_path, monkeypatch):
        """(vi) Malformed JSON residue is skipped gracefully with a notice line."""
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
        feat_dir = lifecycle / "sparse-feature"
        feat_dir.mkdir(parents=True)
        # Minimal payload — no synthesis_status, no reviewers
        sparse = {
            "ts": "2026-04-22T00:00:00+00:00",
            "feature": "sparse-feature",
            "artifact": "cortex/lifecycle/sparse-feature/spec.md",
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
        lifecycle = tmp_path / "cortex" / "lifecycle"
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
        residue_dir = tmp_path / "cortex" / "lifecycle" / "test-feature"
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
        residue_dir = tmp_path / "cortex" / "lifecycle" / "clean-feature"
        residue_dir.mkdir(parents=True)
        residue_path = residue_dir / "critical-review-residue.json"

        # Simulate: no B-class findings → write is skipped entirely
        # Do NOT call atomic_write here — the spec says "do not write"
        assert not residue_path.exists(), (
            "Residue file must NOT exist when there are zero B-class findings"
        )

    def test_synthesis_failed_roundtrip(self, tmp_path, monkeypatch):
        """(xi) synthesis_status: 'failed' round-trips correctly through the renderer."""
        lifecycle = tmp_path / "cortex" / "lifecycle"
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


# ---------------------------------------------------------------------------
# Bug A: residue section is session-scoped (R6 / R8 / R9 / R10).
# ---------------------------------------------------------------------------

def _write_residue(lifecycle_root: Path, dir_name: str, payload: dict) -> None:
    """Write a residue JSON file under ``lifecycle_root/<dir_name>/``."""
    d = lifecycle_root / dir_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "critical-review-residue.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _residue(feature: str, findings: list | None = None) -> dict:
    return {
        "ts": "2026-04-22T00:00:00+00:00",
        "feature": feature,
        "artifact": f"cortex/lifecycle/{feature}/spec.md",
        "synthesis_status": "ok",
        "reviewers": {"completed": 1, "dispatched": 1},
        "findings": findings
        if findings is not None
        else [{"reviewer_angle": "security", "finding": "f"}],
    }


def _state(features: dict) -> OvernightState:
    return OvernightState(session_id="s", features=features)


class TestResidueSessionScope:
    """render_critical_review_residue filters to the session feature set."""

    def test_in_session_present_unrelated_absent(self, tmp_path, monkeypatch):
        """R6: residue in an in-session dir renders; an unrelated dir does not."""
        root = tmp_path / "cortex" / "lifecycle"
        _write_residue(root, "feat-a", _residue("feat-a"))
        _write_residue(root, "old-unrelated", _residue("old-unrelated"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-a": OvernightFeatureStatus(status="merged")})
        out = render_critical_review_residue(data)

        assert "feat-a" in out
        assert "old-unrelated" not in out

    def test_header_count_reflects_filtered_set(self, tmp_path, monkeypatch):
        """R8: the (N) header equals the rendered count, not the raw glob count."""
        root = tmp_path / "cortex" / "lifecycle"
        _write_residue(root, "feat-a", _residue("feat-a"))
        _write_residue(root, "feat-b", _residue("feat-b"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        both = ReportData()
        both.state = _state({
            "feat-a": OvernightFeatureStatus(status="merged"),
            "feat-b": OvernightFeatureStatus(status="merged"),
        })
        assert "## Critical Review Residue (2)" in render_critical_review_residue(both)

        only_a = ReportData()
        only_a.state = _state({"feat-a": OvernightFeatureStatus(status="merged")})
        assert "## Critical Review Residue (1)" in render_critical_review_residue(only_a)

    def test_join_on_dir_name_not_payload_feature(self, tmp_path, monkeypatch):
        """R9: inclusion is decided by the lifecycle dir name, not payload['feature']."""
        root = tmp_path / "cortex" / "lifecycle"
        # In-session dir name, but payload["feature"] is something else → renders.
        _write_residue(root, "feat-a", _residue("not-in-session-label"))
        # Out-of-session dir name, but payload["feature"] IS in-session → excluded.
        _write_residue(root, "old-dir", _residue("feat-a"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-a": OvernightFeatureStatus(status="merged")})
        out = render_critical_review_residue(data)

        assert "not-in-session-label" in out   # the feat-a dir's payload label rendered
        assert "## Critical Review Residue (1)" in out
        assert "old-dir" not in out

    def test_deferred_in_session_feature_renders(self, tmp_path, monkeypatch):
        """R9: the full keyset is used — a deferred (not merged) feature surfaces."""
        root = tmp_path / "cortex" / "lifecycle"
        _write_residue(root, "feat-deferred", _residue("feat-deferred"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-deferred": OvernightFeatureStatus(status="deferred")})
        out = render_critical_review_residue(data)

        assert "feat-deferred" in out
        assert "## Critical Review Residue (1)" in out

    def test_present_empty_state_renders_empty_zero(self, tmp_path, monkeypatch):
        """R10: present-but-empty state ({}) scopes to zero — NOT the whole tree."""
        root = tmp_path / "cortex" / "lifecycle"
        _write_residue(root, "some-old-feature", _residue("some-old-feature"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({})  # present but empty
        out = render_critical_review_residue(data)

        assert "## Critical Review Residue (0)" in out
        assert "some-old-feature" not in out
        assert "No in-session critical-review residue this cycle." in out

    def test_state_none_renders_unfiltered(self, tmp_path, monkeypatch):
        """R10: only absent state (None) renders unfiltered as a degraded fallback."""
        root = tmp_path / "cortex" / "lifecycle"
        _write_residue(root, "any-feature", _residue("any-feature"))
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()  # data.state is None
        out = render_critical_review_residue(data)

        assert "any-feature" in out
        assert "## Critical Review Residue (1)" in out

    def test_malformed_skip_respects_filter(self, tmp_path, monkeypatch):
        """R8/R10 interaction: a malformed residue out-of-session is silently
        filtered (no skip line); a malformed residue in-session still skips."""
        root = tmp_path / "cortex" / "lifecycle"
        (root / "feat-a").mkdir(parents=True)
        (root / "feat-a" / "critical-review-residue.json").write_text(
            "{ not valid json }", encoding="utf-8"
        )
        (root / "old-dir").mkdir(parents=True)
        (root / "old-dir" / "critical-review-residue.json").write_text(
            "{ also not valid }", encoding="utf-8"
        )
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-a": OvernightFeatureStatus(status="merged")})
        out = render_critical_review_residue(data)

        # In-session malformed still emits its skip line; the count is 1 (the
        # filtered set), and the out-of-session malformed never appears.
        assert "feat-a: residue file malformed, skipped." in out
        assert "## Critical Review Residue (1)" in out
        assert "old-dir" not in out


# ---------------------------------------------------------------------------
# Bug A: drift section is session-scoped + the drift path is CWD-independent
# (R7 narrowing gate, R11 re-anchor). This function had no prior coverage.
# ---------------------------------------------------------------------------

def _write_review_with_drift(lifecycle_root: Path, dir_name: str) -> Path:
    """Write a review.md with a detected Requirements Drift section."""
    d = lifecycle_root / dir_name
    d.mkdir(parents=True, exist_ok=True)
    (d / "review.md").write_text(
        "# Review\n\n"
        "## Requirements Drift\n\n"
        "**State**: detected\n"
        "**Findings**:\n"
        "- a requirement drifted\n",
        encoding="utf-8",
    )
    return d


class TestDriftSessionScope:
    """render_pending_drift narrows to the session set and resolves off-CWD."""

    def test_in_session_drift_renders_unrelated_excluded(self, tmp_path, monkeypatch):
        """R7: an in-session feature's drift renders; an unrelated one is excluded."""
        from cortex_command.overnight.report import render_pending_drift

        root = tmp_path / "cortex" / "lifecycle"
        _write_review_with_drift(root, "feat-a")
        _write_review_with_drift(root, "old-unrelated")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-a": OvernightFeatureStatus(status="deferred")})
        out = render_pending_drift(data)

        assert "### feat-a" in out
        assert "old-unrelated" not in out

    def test_merged_feature_still_excluded(self, tmp_path, monkeypatch):
        """R7: the narrowing gate is AND-composed — a merged in-session feature
        is still excluded by the pre-existing merged exclusion."""
        from cortex_command.overnight.report import render_pending_drift

        root = tmp_path / "cortex" / "lifecycle"
        _write_review_with_drift(root, "feat-merged")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({"feat-merged": OvernightFeatureStatus(status="merged")})
        out = render_pending_drift(data)

        # merged → omitted from drift; with nothing else, the section is empty.
        assert "feat-merged" not in out

    def test_drift_render_is_cwd_independent(self, tmp_path, monkeypatch):
        """R11: with CWD set elsewhere and CORTEX_REPO_ROOT at the fixture, the
        in-session drift still resolves (enumerator + per-feature read off-CWD)."""
        from cortex_command.overnight.report import render_pending_drift

        root = tmp_path / "cortex" / "lifecycle"
        _write_review_with_drift(root, "feat-a")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(elsewhere)  # CWD != fixture root

        data = ReportData()
        data.state = _state({"feat-a": OvernightFeatureStatus(status="deferred")})
        out = render_pending_drift(data)

        assert "### feat-a" in out

    def test_reimplementing_exclusion_is_cwd_independent(self, tmp_path, monkeypatch):
        """R11: the reimplementing pre-scan (read via the events path) still fires
        off-CWD — a feature whose latest phase_transition is `implement` stays
        excluded from drift even when CWD != root, while a sibling in-session
        feature with no such event still renders. The sibling makes this a
        two-sided discriminator: a broken pre-scan would WRONGLY surface the
        reimplementing feature rather than leaving the output empty."""
        from cortex_command.overnight.report import render_pending_drift

        root = tmp_path / "cortex" / "lifecycle"
        d = _write_review_with_drift(root, "feat-reimpl")
        (d / "events.log").write_text(
            json.dumps({"event": "phase_transition", "to": "implement"}) + "\n",
            encoding="utf-8",
        )
        _write_review_with_drift(root, "feat-ok")  # in-session, NOT reimplementing
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
        monkeypatch.chdir(elsewhere)  # CWD != fixture root

        data = ReportData()
        data.state = _state({
            "feat-reimpl": OvernightFeatureStatus(status="deferred"),
            "feat-ok": OvernightFeatureStatus(status="deferred"),
        })
        out = render_pending_drift(data)

        # The sibling renders (enumerator resolved off-CWD); the reimplementing
        # one is excluded (pre-scan read its events.log off-CWD). A CWD-relative
        # pre-scan would have missed the event and surfaced feat-reimpl.
        assert "### feat-ok" in out
        assert "feat-reimpl" not in out

    def test_present_empty_state_scopes_drift_to_zero(self, tmp_path, monkeypatch):
        """R10 parity: present-but-empty state ({}) scopes drift to zero."""
        from cortex_command.overnight.report import render_pending_drift

        root = tmp_path / "cortex" / "lifecycle"
        _write_review_with_drift(root, "some-old-feature")
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

        data = ReportData()
        data.state = _state({})  # present but empty → scope to zero
        assert render_pending_drift(data) == ""
