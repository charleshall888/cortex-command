"""End-to-end fidelity: one captured stderr reaches BOTH surfaces (R10 / Task 10).

This is a *cross-layer identity* test, not a truncation-fidelity test. The
per-layer tests (Tasks 1,4,5,6,7,8) each check one layer in isolation — but a
hardcoded stub at any single layer would pass all of them while breaking real
end-to-end propagation. This test closes that gap by driving BOTH surfaces from
a SINGLE source value:

    one DispatchDiagnostics bundle  ->  rendered brain prompt   (via the carrier)
                                    ->  morning report block     (via task_output)

Both reads trace back to that one bundle. If a stub hardcoded a stderr literal
at the brain layer or the report layer, the sentinel defined once here would
fail to appear at that surface and this test would fail.

The sentinel is deliberately SHORT and high-entropy-free (``SENTINEL_STDERR_ec79``)
so that (a) the cue-anchored redaction does not consume it and (b) it survives
both the brain's full render and the report's display cap identically — keeping
this test about identity, not truncation (the report-cap-not-clipping-the-tail
property is owned by Task 8's re-budget guard test).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cortex_command.overnight.brain as brain_module
from cortex_command.overnight.brain import BrainContext
from cortex_command.overnight.report import (
    ReportData,
    render_failed_features,
)
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState
from cortex_command.pipeline.dispatch import DispatchDiagnostics


# The single source of truth for this test. Defined ONCE; flows into both
# surfaces from the one DispatchDiagnostics bundle below.
_SENTINEL_STDERR = "SENTINEL_STDERR_ec79"
_SENTINEL_EXIT_CODE = 42
_SENTINEL_CWD = "/tmp/worktrees/fidelity-ec79"


class TestDiagnosticsFidelity(unittest.TestCase):
    """One captured DispatchDiagnostics bundle reaches the brain AND the report."""

    def _bundle(self) -> DispatchDiagnostics:
        """The single diagnostics bundle that feeds both surfaces.

        Constructed once per test; both the brain render and the report event
        are sourced from THIS object, so a stub at either layer cannot pass.
        """
        return DispatchDiagnostics(
            child_stderr=_SENTINEL_STDERR,
            exit_code=_SENTINEL_EXIT_CODE,
            cwd=_SENTINEL_CWD,
        )

    # --- surface (a): the rendered brain prompt, via the carrier --------------

    def _render_brain_prompt(self, diagnostics: DispatchDiagnostics) -> str:
        """Render the brain prompt the same way ``request_brain_decision`` does.

        Mirrors ``test_brain.py``'s ``TestBrainDiagnosticsRendering`` render
        path: build a ``BrainContext`` carrying the bundle as
        ``last_attempt_diagnostics`` and render the real ``_BRAIN_TEMPLATE`` via
        ``_render_template`` with ``_format_diagnostics`` (the same function the
        production render path uses).
        """
        ctx = BrainContext(
            feature="fidelity-feat",
            task_description="do the failing thing",
            retry_count=2,
            learnings="some learnings",
            spec_excerpt="spec text",
            last_attempt_output="",  # empty-output crash case this feature targets
            has_dependents=False,
            last_attempt_diagnostics=diagnostics,
        )
        return brain_module._render_template(
            brain_module._BRAIN_TEMPLATE,
            {
                "feature": ctx.feature,
                "task_description": ctx.task_description,
                "retry_count": str(ctx.retry_count),
                "learnings": ctx.learnings,
                "spec_excerpt": ctx.spec_excerpt,
                "has_dependents": str(ctx.has_dependents),
                "last_attempt_output": ctx.last_attempt_output,
                "final_attempt_diagnostics": brain_module._format_diagnostics(
                    ctx.last_attempt_diagnostics
                ),
            },
        )

    # --- surface (b): the morning report block, via the task_output event -----

    def _render_report_block(
        self, diagnostics: DispatchDiagnostics, events_path: Path
    ) -> str:
        """Render the failed-feature report block, sourcing the SAME bundle.

        Emits a ``task_output`` event dict carrying the bundle's
        ``child_stderr``/``exit_code``/``cwd`` (mirroring ``feature_executor.py``'s
        emit shape at ~line 705) into a temp ``pipeline-events.log``, then calls
        ``render_failed_features`` for that feature — the real report read path
        (``_read_last_task_diagnostics``).
        """
        feature = "fidelity-feat"
        task_output_event = {
            "event": "task_output",
            "feature": feature,
            "task_number": 1,
            "task_description": "do the failing thing",
            "output": "",  # empty on a worker crash — diagnostics ride separately
            "child_stderr": diagnostics.child_stderr,
            "exit_code": diagnostics.exit_code,
            "cwd": diagnostics.cwd,
        }
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(task_output_event) + "\n")

        features = {
            feature: OvernightFeatureStatus(
                status="failed", error="ProcessError: exit code 42"
            ),
        }
        data = ReportData()
        data.state = OvernightState(session_id="test-session", features=features)
        data.pr_urls = {}
        data.pipeline_events_path = events_path
        return render_failed_features(data)

    # --- the cross-layer identity assertion -----------------------------------

    def test_sentinel_propagates_source_to_brain_and_report(self) -> None:
        """One bundle's sentinel reaches BOTH the brain prompt and the report.

        Anti-stub: the sentinel is defined ONCE (``_SENTINEL_STDERR``) and the
        bundle is constructed ONCE here; both surfaces read from that single
        object. A hardcoded stub at either layer would fail to surface THIS
        sentinel and break this test.
        """
        bundle = self._bundle()

        # Sanity: the sentinel really is the bundle's stderr (single source).
        self.assertEqual(bundle.child_stderr, _SENTINEL_STDERR)

        # Surface (a): the rendered brain prompt contains the sentinel + the
        # exit_code + the cwd (values, not just a heading).
        brain_prompt = self._render_brain_prompt(bundle)
        self.assertIn(
            _SENTINEL_STDERR,
            brain_prompt,
            f"sentinel missing from brain prompt:\n{brain_prompt}",
        )
        self.assertIn(str(_SENTINEL_EXIT_CODE), brain_prompt)
        self.assertIn(_SENTINEL_CWD, brain_prompt)

        # Surface (b): the failed-feature report block contains the SAME
        # sentinel, sourced from the same bundle via the task_output event.
        with tempfile.TemporaryDirectory() as tmpdir:
            events_path = Path(tmpdir) / "pipeline-events.log"
            report_block = self._render_report_block(bundle, events_path)

        self.assertIn(
            _SENTINEL_STDERR,
            report_block,
            f"sentinel missing from report block:\n{report_block}",
        )
        self.assertIn(str(_SENTINEL_EXIT_CODE), report_block)
        self.assertIn(_SENTINEL_CWD, report_block)

        # Cross-layer identity: the SAME sentinel reached both surfaces. (If a
        # stub at one layer substituted a different literal, exactly one of the
        # two `assertIn`s above would already have failed.)
        self.assertIn(_SENTINEL_STDERR, brain_prompt)
        self.assertIn(_SENTINEL_STDERR, report_block)


if __name__ == "__main__":
    unittest.main()
