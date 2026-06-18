"""Partial morning-report enrichment for the crash-recovery path (spec §R4, Task 6).

When the out-of-process recovery core (``recovery.recover_session``) drives a
pid-dead ``executing`` session to ``paused``, it sets
``paused_reason == "orchestrator_crash"`` *before* generating the morning
report, so the report renderer's new ``orchestrator_crash`` branch
(:func:`report.render_executive_summary` →
:func:`report._render_orchestrator_crash_banner`) fires and emits an
interrupted-session banner conveying:

  * the death timestamp (last ``overnight-events.log`` event ts), and the gap
    vs the last ``pipeline-events.log`` event ts when available;
  * the count of features left non-terminal (``running``/``pending``);
  * the orphan-reap outcome (from the ``recovery-complete.json`` sidecar, which
    recovery writes *after* the report — so recovery's own first render omits
    the reap line defensively, while a later re-render surfaces it).

These tests assert (1) recovery writes BOTH report paths and they contain the
new banner + a non-terminal-feature count; (2) a ``budget_exhausted`` report's
existing banner is byte-identical (no regression); (3) the gap line renders when
a ``pipeline-events.log`` is present; (4) a re-render with the reap sidecar
present surfaces the orphan-reap line.

The orphan reaper is monkeypatched so no real processes are touched, and
``SKIP_NOTIFICATIONS=1`` short-circuits the notify-hook shell-out that otherwise
blocks on non-tty stdin (the established suppression hatch).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import recovery, report
from cortex_command.overnight.recovery import (
    RECOVERY_COMPLETE_SIDECAR,
    ReapOutcome,
    recover_session,
)
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    save_state,
)

SESSION_ID = "overnight-2026-04-24-report"


# ---------------------------------------------------------------------------
# Fixtures (mirroring tests/test_recovery_core.py)
# ---------------------------------------------------------------------------


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running."""
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _dead_pid_payload(pid: int) -> dict:
    """A well-formed ``runner.pid`` payload whose recorded process is gone."""
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "session_id": SESSION_ID,
    }


def _write_event_line(log_path: Path, event: str, ts: datetime) -> None:
    """Append one well-formed event line (``ts`` + ``event``) to ``log_path``."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts.isoformat(), "event": event}) + "\n")


def _synthesize_stuck_session(
    root: Path,
    *,
    non_terminal: int = 1,
    death_ts: datetime | None = None,
    pipeline_ts: datetime | None = None,
) -> Path:
    """Build a stuck-``executing`` + dead-pid session dir under ``root``.

    Lays out ``{root}/cortex/lifecycle/sessions/{SESSION_ID}/`` with state at
    ``phase == "executing"`` carrying ``non_terminal`` running/pending features,
    a dead ``runner.pid``, an ``overnight-events.log`` (last event at
    ``death_ts``), and optionally a per-session ``pipeline-events.log`` (last
    event at ``pipeline_ts``). Returns the session dir.
    """
    lifecycle_root = root / "cortex" / "lifecycle"
    session_dir = lifecycle_root / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    features = {
        f"feature-{i}": OvernightFeatureStatus(status="running")
        for i in range(non_terminal)
    }
    # Add a terminal feature so the non-terminal count is a real subset, not the
    # whole feature set.
    features["feature-done"] = OvernightFeatureStatus(status="merged")

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features=features,
    )
    save_state(state, session_dir / "overnight-state.json")

    (session_dir / "runner.pid").write_text(json.dumps(_dead_pid_payload(_dead_pid())))

    death = death_ts or datetime(2026, 4, 24, 3, 15, 0, tzinfo=timezone.utc)
    _write_event_line(lifecycle_root / "overnight-events.log", "round_start", death)

    if pipeline_ts is not None:
        _write_event_line(
            session_dir / "pipeline-events.log", "heartbeat", pipeline_ts
        )

    return session_dir


# ---------------------------------------------------------------------------
# Test 1 — recovery writes both report paths with the new banner (spec §R4)
# ---------------------------------------------------------------------------


def test_recovery_writes_both_reports_with_interrupted_banner(tmp_path, monkeypatch):
    """Recovery writes BOTH report paths, each carrying the new
    ``orchestrator_crash`` banner header and the non-terminal-feature count.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")

    # Reaper must not touch real processes.
    monkeypatch.setattr(
        recovery,
        "reap_session_orphans",
        lambda *a, **k: ReapOutcome(matched=[111], terminated=[111]),
    )

    session_dir = _synthesize_stuck_session(tmp_path, non_terminal=2)

    result = recover_session(session_dir, trigger="manual")
    assert result.action == "recovered"

    session_report = session_dir / "morning-report.md"
    latest_report = tmp_path / "cortex" / "lifecycle" / "morning-report.md"

    # BOTH report paths exist (spec §R4 dual write).
    assert session_report.exists(), "session-specific report not written"
    assert latest_report.exists(), "latest-copy report not written"

    for path in (session_report, latest_report):
        text = path.read_text(encoding="utf-8")
        # The new branch's interrupted-session banner header.
        assert "Interrupted Session: orchestrator crash" in text, path
        # The death timestamp line is present and real (not "unknown").
        assert "death timestamp" in text, path
        assert "2026-04-24T03:15:00" in text, path
        assert "unknown" not in text.split("death timestamp")[1].split("\n")[0], path
        # The non-terminal-feature count (2 running features) is conveyed.
        assert "Features left non-terminal" in text, path
        assert "`running`/`pending`): 2" in text, path


# ---------------------------------------------------------------------------
# Test 2 — budget_exhausted banner is unchanged (no regression) (spec §R4)
# ---------------------------------------------------------------------------


def test_budget_exhausted_banner_unchanged_no_regression():
    """The existing ``budget_exhausted`` banner renders exactly as before; the
    new crash branch must not perturb non-crash reasons.
    """
    state = OvernightState(
        session_id="overnight-budget",
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="paused",
        paused_reason="budget_exhausted",
        features={"feature-a": OvernightFeatureStatus(status="pending")},
    )
    data = report.ReportData(state=state)

    summary = report.render_executive_summary(data)

    # The exact pre-existing budget banner text is present, verbatim.
    assert (
        "> **Session paused: API budget exhausted.** Features in `pending` status "
        "will resume on `/overnight resume`." in summary
    )
    # The crash banner does NOT leak into a non-crash report.
    assert "Interrupted Session: orchestrator crash" not in summary
    assert "death timestamp" not in summary


# ---------------------------------------------------------------------------
# Test 3 — the event-gap line renders when a pipeline-events.log is present
# ---------------------------------------------------------------------------


def test_crash_banner_renders_event_gap_when_pipeline_log_present(tmp_path, monkeypatch):
    """When a ``pipeline-events.log`` exists, the banner conveys the gap between
    the death ts and the last pipeline event ts.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: ReapOutcome()
    )

    death = datetime(2026, 4, 24, 3, 0, 0, tzinfo=timezone.utc)
    # Workers kept logging 120s past the orchestrator's last event.
    pipeline = datetime(2026, 4, 24, 3, 2, 0, tzinfo=timezone.utc)
    session_dir = _synthesize_stuck_session(
        tmp_path, non_terminal=1, death_ts=death, pipeline_ts=pipeline
    )

    recover_session(session_dir, trigger="manual")

    text = (session_dir / "morning-report.md").read_text(encoding="utf-8")
    assert "pipeline-events.log` event: 2026-04-24T03:02:00" in text
    assert "gap vs death: 120s" in text


# ---------------------------------------------------------------------------
# Test 4 — a re-render with the reap sidecar present surfaces the reap line
# ---------------------------------------------------------------------------


def test_crash_banner_surfaces_reap_outcome_from_sidecar(tmp_path, monkeypatch):
    """When the ``recovery-complete.json`` sidecar records reap counts, a report
    re-render surfaces the orphan-reap outcome line (defensive: omitted when the
    sidecar is absent).
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    session_dir = lifecycle_root / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="paused",
        paused_reason="orchestrator_crash",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_event_line(
        lifecycle_root / "overnight-events.log",
        "round_start",
        datetime(2026, 4, 24, 4, 0, 0, tzinfo=timezone.utc),
    )

    # Sidecar with recorded reap counts (as recovery would write at step 7).
    (session_dir / RECOVERY_COMPLETE_SIDECAR).write_text(
        json.dumps(
            {
                "session_id": SESSION_ID,
                "trigger": "manual",
                "paused_reason": "orchestrator_crash",
                "recovered_at": "2026-04-24T04:00:05+00:00",
                "reap": {
                    "matched": 3,
                    "terminated": 2,
                    "killed": 1,
                    "unreaped": 1,
                },
            }
        )
    )

    data = report.collect_report_data(
        state_path=session_dir / "overnight-state.json",
        events_path=lifecycle_root / "overnight-events.log",
    )
    summary = report.render_executive_summary(data)

    assert "Orphan workers reaped: 3 matched" in summary
    assert "1 force-killed" in summary
    assert "1 un-reaped" in summary


def test_crash_banner_omits_reap_line_without_sidecar(tmp_path, monkeypatch):
    """Absent the sidecar (or its ``reap`` key), the reap line is omitted while
    the death-ts and non-terminal lines still render (defensive coupling).
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    session_dir = lifecycle_root / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="paused",
        paused_reason="orchestrator_crash",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_event_line(
        lifecycle_root / "overnight-events.log",
        "round_start",
        datetime(2026, 4, 24, 5, 0, 0, tzinfo=timezone.utc),
    )

    data = report.collect_report_data(
        state_path=session_dir / "overnight-state.json",
        events_path=lifecycle_root / "overnight-events.log",
    )
    summary = report.render_executive_summary(data)

    # The crash banner still renders its test-gated content...
    assert "Interrupted Session: orchestrator crash" in summary
    assert "Features left non-terminal" in summary
    # ...but the optional reap line is omitted.
    assert "Orphan workers reaped" not in summary
