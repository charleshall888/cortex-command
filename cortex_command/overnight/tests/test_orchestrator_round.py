"""Python-helper invariants for the orchestrator-round synthesizer flow.

Sibling to ``test_orchestrator_round_telemetry.py``. Covers three
synthesizer-related Python-observable invariants from
``lifecycle/build-shared-synthesizer-for-critical-tier-dual-plan-flow-interactive-overnight``
Task 9:

  1. ``test_synthesizer_gate_disabled_returns_false`` — direct unit
     test on Task 4's :func:`read_synthesizer_gate`. Asserts fail-closed
     semantics: ``False`` for missing files, missing fields, and
     ``synthesizer_overnight_enabled: false`` configs.
  2. ``test_synthesizer_post_orchestrator_high_confidence_writes_plan_md`` —
     given a canned orchestrator stdout containing a high-confidence
     ``<!--findings-json-->`` envelope, the post-orchestrator-turn
     processing logic copies the selected variant to
     ``lifecycle/{feature}/plan.md`` and appends a v2
     ``plan_comparison`` event.
  3. ``test_synthesizer_post_orchestrator_low_confidence_defers`` — same
     setup with ``confidence: "low"``; ``PLAN_SYNTHESIS_DEFERRED`` is
     logged and ``deferral.write_deferral`` is called (mocked) with a
     ``DeferralQuestion`` whose ``feature`` field matches.

All three test method names contain the substring ``synthesizer`` so
the spec's verification command (``pytest -k synthesizer -v``) selects
them.

**Scope**: These tests cover Python-side invariants given canned LLM
stdout — they do NOT exercise the LLM's prompt-following decisions in
``orchestrator-round.md``'s Step 3b prose. That layer (whether the LLM
honors the criticality branch, dispatches the right number of variants,
calls the synthesizer with correct inputs) is verified by spec
acceptance greps against ``orchestrator-round.md`` text (Task 6
verification) plus the manual operator validation gate from spec
Requirement 7 — not by these unit tests.

**Path-(b) note**: ``runner.py`` does not currently expose an
envelope-handler entry point as a callable Python function — the
orchestrator agent itself writes ``plan.md`` and emits the v2
``plan_comparison`` event from inside its subprocess turn (per
``orchestrator-round.md`` Step 3b). Per Task 9's Context guidance,
tests 2 and 3 therefore exercise the helper-level invariants the
runner / orchestrator code path depends on (LAST-occurrence regex
extraction, ``events.log_event`` signature, ``write_deferral``
signature) via a thin in-test scaffold that mirrors the prompt's
prescribed actions. No speculative refactoring of ``runner.py`` is
introduced.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.overnight import deferral as deferral_module
from cortex_command.overnight import events
from cortex_command.overnight.cli_handler import read_synthesizer_gate
from cortex_command.overnight.deferral import DeferralQuestion


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _extract_synthesizer_envelope(stdout_text: str) -> dict | None:
    """Parse the LAST ``<!--findings-json-->`` block from orchestrator stdout.

    Mirrors the LAST-occurrence anchor pattern prescribed by
    ``cortex_command/overnight/prompts/orchestrator-round.md`` Step 3b.4
    (and the canonical ``skills/lifecycle/references/plan.md`` §1b
    extraction). Returns ``None`` when no anchor is present or the JSON
    that follows the last anchor cannot be parsed.

    The function is local to this test module and exists only to render
    the prompt-prescribed extraction logic as Python so the
    Python-observable invariants downstream of it (variant-copy,
    plan_comparison event shape, deferral routing) can be exercised
    without spawning the orchestrator subprocess. It is NOT a
    production helper — the production extraction lives in the
    orchestrator agent's prompt turn.
    """
    matches = list(re.finditer(r"^<!--findings-json-->\s*$", stdout_text, re.MULTILINE))
    if not matches:
        return None
    # Take everything after the LAST anchor and try to parse a JSON object.
    tail = stdout_text[matches[-1].end():].strip()
    # A JSON object may be followed by trailing prose; greedily decode the
    # first JSON value at the head of the tail.
    decoder = json.JSONDecoder()
    tail = tail.lstrip()
    try:
        obj, _idx = decoder.raw_decode(tail)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _process_synthesizer_envelope(
    *,
    stdout_text: str,
    feature: str,
    feature_dir: Path,
    events_path: Path,
    deferred_dir: Path,
    round_num: int,
) -> dict:
    """Apply the post-orchestrator-turn invariants to a canned stdout.

    Mirrors the orchestrator-round.md Step 3b.5/3b.7 routing logic in
    pure Python so the Python-observable side effects (plan.md
    contents, events.log entries, write_deferral invocations) can be
    asserted. Returns a dict describing the routing decision for test
    introspection.

    On ``verdict ∈ {"A","B","C"}`` AND ``confidence ∈ {"high","medium"}``:
      - Copies ``plan-variant-{verdict}.md`` content to ``plan.md``.
      - Appends a v2 ``plan_comparison`` event with
        ``disposition: "auto_select"``, ``schema_version: 2``.

    On ``confidence: "low"`` OR malformed envelope:
      - Logs ``PLAN_SYNTHESIS_DEFERRED`` to events.
      - Calls ``deferral.write_deferral`` with a ``DeferralQuestion``
        whose ``feature`` field matches.
    """
    envelope = _extract_synthesizer_envelope(stdout_text)
    is_malformed = envelope is None
    verdict = (envelope or {}).get("verdict")
    confidence = (envelope or {}).get("confidence", "low")

    high_or_medium = (
        not is_malformed
        and verdict in ("A", "B", "C")
        and confidence in ("high", "medium")
    )

    if high_or_medium:
        variant_path = feature_dir / f"plan-variant-{verdict}.md"
        plan_path = feature_dir / "plan.md"
        plan_path.write_text(
            variant_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        # The v2 ``plan_comparison`` row is written as raw JSONL append
        # to the per-feature events.log (matching orchestrator-round.md
        # Step 3b.5, lines 335-354). It is NOT routed through
        # events.log_event — that helper validates the event name
        # against EVENT_TYPES (overnight session-scope events only) and
        # tags entries with the session id; the per-feature
        # plan_comparison row is feature-scoped, not session-scoped.
        comparison_row = {
            "ts": "2026-05-04T00:00:00+00:00",
            "event": "plan_comparison",
            "schema_version": 2,
            "feature": feature,
            "selected": verdict,
            "selection_rationale": envelope.get("rationale", ""),
            "selector_confidence": confidence,
            "position_swap_check_result": envelope.get(
                "position_swap_check_result", "agreed"
            ),
            "disposition": "auto_select",
            "operator_choice": None,
        }
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(comparison_row) + "\n")
        return {"disposition": "auto_select", "verdict": verdict}

    # Low-confidence or malformed → emit PLAN_SYNTHESIS_DEFERRED + write_deferral.
    events.log_event(
        events.PLAN_SYNTHESIS_DEFERRED,
        round=round_num,
        feature=feature,
        details={
            "reason": "low_confidence" if envelope is not None else "malformed_envelope",
            "selector_confidence": confidence,
        },
        log_path=events_path,
    )
    question = DeferralQuestion(
        feature=feature,
        question_id=0,
        severity=deferral_module.SEVERITY_BLOCKING,
        context="Synthesizer returned low confidence on plan-variant comparison.",
        question=(
            "Synthesizer could not pick a high-confidence variant; please "
            "select manually from the surviving plan-variant files."
        ),
        options_considered=["plan-variant-A.md", "plan-variant-B.md"],
        pipeline_attempted=(
            "Dispatched parallel plan-gen variants and an Opus synthesizer "
            "Task sub-agent; envelope verdict/confidence did not meet the "
            "auto-select threshold."
        ),
    )
    deferral_module.write_deferral(question, deferred_dir=deferred_dir)
    return {"disposition": "deferred", "verdict": verdict}


def _make_lifecycle_event_log(
    feature_dir: Path, criticality: str = "critical"
) -> Path:
    """Write a stub ``lifecycle/{feature}/events.log`` with a lifecycle_start row.

    The ``criticality: "critical"`` row exists per Task 9's Context: the
    runtime branch in orchestrator-round.md reads this file for the most-
    recent ``lifecycle_start``/``criticality_override`` row when deciding
    whether to take the synthesizer path. The Python tests below do not
    re-read this file (the gate-read is exercised separately), but it is
    written so the on-disk fixture matches the spec's expected layout.
    """
    feature_dir.mkdir(parents=True, exist_ok=True)
    log = feature_dir / "events.log"
    log.write_text(
        json.dumps(
            {
                "v": 1,
                "ts": "2026-05-04T00:00:00+00:00",
                "event": "lifecycle_start",
                "criticality": criticality,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return log


def _build_canned_orchestrator_stdout(
    *,
    verdict: str,
    confidence: str,
    rationale: str = "Variant A is structurally cleaner.",
) -> str:
    """Render a canned orchestrator stdout containing a synthesizer envelope.

    Includes a leading prose line that mentions the anchor (without being
    one) so the LAST-occurrence semantics get exercised — the extraction
    helper must skip the prose mention and pick up the real terminating
    anchor.
    """
    envelope = {
        "schema_version": 2,
        "per_criterion": {
            "completeness": {"A": 9, "B": 7},
            "feasibility": {"A": 8, "B": 8},
        },
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "position_swap_check_result": "agreed" if confidence != "low" else "disagreed",
    }
    # Note the prose line referring to the anchor — the LAST-occurrence
    # extractor must walk past this and pick the real envelope below.
    return (
        "Orchestrator round complete. Note: the synthesizer envelope is "
        "delimited by the `<!--findings-json-->` anchor.\n"
        "\n"
        "<!--findings-json-->\n"
        f"{json.dumps(envelope)}\n"
    )


# ---------------------------------------------------------------------------
# Test 1: read_synthesizer_gate fail-closed semantics
# ---------------------------------------------------------------------------


class TestSynthesizerGate:
    """Direct unit test on Task 4's ``read_synthesizer_gate`` helper.

    Covers Spec Requirement 7 fail-closed semantics: ``False`` returned
    when the file is absent, the field is missing, or the value is
    explicitly ``false``.
    """

    def test_synthesizer_gate_disabled_returns_false(self, tmp_path: Path) -> None:
        """Default config (flag absent or false) returns False; missing file returns False.

        Three cases all exercise the same fail-closed semantic:

          a. ``synthesizer_overnight_enabled: false`` — explicit False.
          b. Frontmatter present but the field is absent — fail-closed.
          c. The config file is missing entirely — fail-closed.

        Each case asserts ``read_synthesizer_gate(path) is False``.
        """
        # Case (a): explicit "false"
        config_a = tmp_path / "lifecycle.config.md"
        config_a.write_text(
            "---\n"
            "type: feature\n"
            "synthesizer_overnight_enabled: false\n"
            "---\n"
            "# body\n",
            encoding="utf-8",
        )
        assert read_synthesizer_gate(config_a) is False

        # Case (b): field absent from frontmatter
        config_b = tmp_path / "lifecycle.config.b.md"
        config_b.write_text(
            "---\n"
            "type: feature\n"
            "test-command: just test\n"
            "---\n"
            "# body\n",
            encoding="utf-8",
        )
        assert read_synthesizer_gate(config_b) is False

        # Case (c): missing file
        missing = tmp_path / "nonexistent-lifecycle.config.md"
        assert not missing.exists()
        assert read_synthesizer_gate(missing) is False


# ---------------------------------------------------------------------------
# Test 2: high-confidence envelope → plan.md + v2 plan_comparison event
# ---------------------------------------------------------------------------


class TestPostOrchestratorHighConfidence:
    """High-confidence canned envelope produces plan.md + v2 plan_comparison.

    The orchestrator subprocess is NOT spawned. A canned stdout is fed
    through a thin in-test scaffold that mirrors the post-orchestrator-
    turn invariants prescribed by ``orchestrator-round.md`` Step 3b.5
    (LAST-occurrence anchor extraction → variant copy → events.log
    append). The assertions are over Python-observable artifacts: the
    on-disk ``plan.md`` content and the JSONL row appended to
    ``events.log``.
    """

    def test_synthesizer_post_orchestrator_high_confidence_writes_plan_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """High-confidence verdict A → plan.md == variant-A; v2 plan_comparison logged."""
        # Set LIFECYCLE_SESSION_ID so events.log_event tags entries.
        monkeypatch.setenv("LIFECYCLE_SESSION_ID", "overnight-2026-05-04-synth-hc")

        feature = "synthesizer-high-confidence-fixture"
        feature_dir = tmp_path / "cortex" / "lifecycle" / feature
        feature_dir.mkdir(parents=True, exist_ok=True)
        _make_lifecycle_event_log(feature_dir)

        # Stub variant files. The high-confidence test asserts plan.md
        # ends up byte-equal to variant-A.
        variant_a_text = "# Plan variant A\n\nVariant A body — chosen by synthesizer.\n"
        variant_b_text = "# Plan variant B\n\nVariant B body — not chosen.\n"
        (feature_dir / "plan-variant-A.md").write_text(
            variant_a_text, encoding="utf-8"
        )
        (feature_dir / "plan-variant-B.md").write_text(
            variant_b_text, encoding="utf-8"
        )

        events_path = feature_dir / "events.log"
        deferred_dir = tmp_path / "deferred"

        stdout_text = _build_canned_orchestrator_stdout(
            verdict="A", confidence="high"
        )

        decision = _process_synthesizer_envelope(
            stdout_text=stdout_text,
            feature=feature,
            feature_dir=feature_dir,
            events_path=events_path,
            deferred_dir=deferred_dir,
            round_num=1,
        )

        # Routing decision matches the canned envelope.
        assert decision == {"disposition": "auto_select", "verdict": "A"}

        # plan.md byte-equals variant-A.
        plan_path = feature_dir / "plan.md"
        assert plan_path.exists(), "plan.md was not written"
        assert plan_path.read_text(encoding="utf-8") == variant_a_text

        # events.log gained a plan_comparison row with v2 schema fields.
        # The row is appended as raw JSONL (top-level keys), matching the
        # orchestrator-round.md Step 3b.5 prescription.
        rows = _read_jsonl(events_path)
        # First row is the lifecycle_start fixture; the appended row is
        # the plan_comparison event.
        plan_comparison_rows = [r for r in rows if r.get("event") == "plan_comparison"]
        assert len(plan_comparison_rows) == 1, (
            f"expected exactly 1 plan_comparison row, "
            f"got events={[r.get('event') for r in rows]}"
        )
        rec = plan_comparison_rows[0]
        assert rec.get("schema_version") == 2, (
            f"expected schema_version=2, got {rec.get('schema_version')!r}"
        )
        assert rec.get("disposition") == "auto_select"
        assert rec.get("selected") == "A"
        assert rec.get("selector_confidence") == "high"
        assert rec.get("operator_choice") is None
        # No deferred dir written for high-confidence path.
        assert not deferred_dir.exists() or not list(deferred_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Test 3: low-confidence envelope → PLAN_SYNTHESIS_DEFERRED + write_deferral
# ---------------------------------------------------------------------------


class TestPostOrchestratorLowConfidence:
    """Low-confidence canned envelope routes through the deferral channel.

    Asserts ``PLAN_SYNTHESIS_DEFERRED`` is logged and
    ``deferral.write_deferral`` is called (mocked) with a
    ``DeferralQuestion`` whose ``feature`` field matches the
    feature-under-test. The mock target is at the Python layer per Task
    9's Context guidance.
    """

    def test_synthesizer_post_orchestrator_low_confidence_defers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Low-confidence verdict → PLAN_SYNTHESIS_DEFERRED logged; write_deferral mocked."""
        monkeypatch.setenv("LIFECYCLE_SESSION_ID", "overnight-2026-05-04-synth-lc")

        feature = "synthesizer-low-confidence-fixture"
        feature_dir = tmp_path / "cortex" / "lifecycle" / feature
        feature_dir.mkdir(parents=True, exist_ok=True)
        _make_lifecycle_event_log(feature_dir)

        # Stub variant files (their content is irrelevant for the low-
        # confidence path; they are written so the on-disk layout matches
        # the spec's expected fixture).
        (feature_dir / "plan-variant-A.md").write_text(
            "# Plan variant A\n", encoding="utf-8"
        )
        (feature_dir / "plan-variant-B.md").write_text(
            "# Plan variant B\n", encoding="utf-8"
        )

        events_path = feature_dir / "events.log"
        deferred_dir = tmp_path / "deferred"

        stdout_text = _build_canned_orchestrator_stdout(
            verdict="A", confidence="low"
        )

        # Mock target: deferral.write_deferral. The test scaffold imports
        # the symbol via ``deferral_module.write_deferral`` so monkeypatch
        # on the module attribute intercepts the in-test call.
        captured: dict = {}

        def _fake_write_deferral(question, deferred_dir=None, **kw):
            captured["question"] = question
            captured["deferred_dir"] = deferred_dir
            # Return a sentinel path; the scaffold does not introspect it.
            return Path("/dev/null")

        monkeypatch.setattr(
            deferral_module, "write_deferral", _fake_write_deferral
        )

        decision = _process_synthesizer_envelope(
            stdout_text=stdout_text,
            feature=feature,
            feature_dir=feature_dir,
            events_path=events_path,
            deferred_dir=deferred_dir,
            round_num=1,
        )

        # Routing decision is deferred.
        assert decision["disposition"] == "deferred"

        # plan.md must NOT have been written on the deferred path.
        plan_path = feature_dir / "plan.md"
        assert not plan_path.exists(), (
            "plan.md should not be written when synthesizer defers"
        )

        # events.log gained PLAN_SYNTHESIS_DEFERRED.
        rows = _read_jsonl(events_path)
        deferred_rows = [
            r for r in rows if r.get("event") == events.PLAN_SYNTHESIS_DEFERRED
        ]
        assert len(deferred_rows) == 1, (
            f"expected exactly 1 PLAN_SYNTHESIS_DEFERRED row, "
            f"got events={[r.get('event') for r in rows]}"
        )
        deferred_rec = deferred_rows[0]
        assert deferred_rec.get("feature") == feature
        # The reason is "low_confidence" (envelope parsed; confidence=low).
        assert deferred_rec.get("details", {}).get("reason") == "low_confidence"

        # write_deferral was called with a DeferralQuestion whose feature
        # field matches.
        assert "question" in captured, "write_deferral was never called"
        question = captured["question"]
        assert isinstance(question, DeferralQuestion)
        assert question.feature == feature
        # The deferred_dir kwarg was forwarded.
        assert captured["deferred_dir"] == deferred_dir


# ---------------------------------------------------------------------------
# Negative-shape coverage: malformed envelope triggers the deferred path too
# ---------------------------------------------------------------------------


class TestPostOrchestratorMalformedEnvelope:
    """Malformed envelope (no anchor) routes through the deferral channel.

    Spec Requirement 4 + Edge Cases ("Synthesizer returns malformed JSON
    envelope") prescribe that LAST-occurrence extraction failure is
    treated as ``confidence: "low"``. This negative-shape test guards
    against a regression where a missing anchor is silently treated as a
    high-confidence pick.
    """

    def test_synthesizer_malformed_envelope_defers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ``<!--findings-json-->`` anchor → deferral routing fires."""
        monkeypatch.setenv(
            "LIFECYCLE_SESSION_ID", "overnight-2026-05-04-synth-malformed"
        )

        feature = "synthesizer-malformed-envelope-fixture"
        feature_dir = tmp_path / "cortex" / "lifecycle" / feature
        feature_dir.mkdir(parents=True, exist_ok=True)
        _make_lifecycle_event_log(feature_dir)
        (feature_dir / "plan-variant-A.md").write_text(
            "# A\n", encoding="utf-8"
        )
        (feature_dir / "plan-variant-B.md").write_text(
            "# B\n", encoding="utf-8"
        )

        events_path = feature_dir / "events.log"
        deferred_dir = tmp_path / "deferred"

        # Canned stdout with no anchor at all → extraction returns None.
        stdout_text = "Orchestrator round complete. No envelope emitted.\n"

        captured: dict = {}

        def _fake_write_deferral(question, deferred_dir=None, **kw):
            captured["question"] = question
            return Path("/dev/null")

        monkeypatch.setattr(
            deferral_module, "write_deferral", _fake_write_deferral
        )

        decision = _process_synthesizer_envelope(
            stdout_text=stdout_text,
            feature=feature,
            feature_dir=feature_dir,
            events_path=events_path,
            deferred_dir=deferred_dir,
            round_num=1,
        )

        assert decision["disposition"] == "deferred"
        rows = _read_jsonl(events_path)
        deferred_rows = [
            r for r in rows if r.get("event") == events.PLAN_SYNTHESIS_DEFERRED
        ]
        assert len(deferred_rows) == 1
        # Reason for malformed is "malformed_envelope".
        assert (
            deferred_rows[0].get("details", {}).get("reason")
            == "malformed_envelope"
        )
        # write_deferral still receives a DeferralQuestion with the right feature.
        assert captured["question"].feature == feature
