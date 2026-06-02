"""Tests for the morning-report + status scheduled-fire surfaces.

The launchd-fired launcher writes two kinds of fire-time marker (spec
§R6/§R7/§R13):

  * ``scheduled-fire-failed.json`` — a genuine failure (EPERM /
    command-not-found / ``spawn_died`` dead fire). Surfaced by
    ``render_scheduled_fire_failures`` and the status failure tally.
  * ``scheduled-fire-advisory.json`` — a live-but-slow
    (``spawn_unconfirmed``) fire. Surfaced as a DISTINCT non-failure
    "scheduled fire started — awaiting confirmation" advisory and
    EXCLUDED from the failure tally — UNLESS it goes stale (age >
    threshold + no live runner.pid + session not executing/complete), in
    which case it ESCALATES to a failure at read time.

Coverage:
  * ``render_scheduled_fire_failures`` empty/single/multiple (regression).
  * A ``spawn_died`` marker renders as a failure in status + report.
  * A fresh advisory renders as a non-failure advisory in status +
    report and is excluded from the failure tally.
  * A stale advisory escalates to a failure in status + report.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler, fail_markers
from cortex_command.overnight.fail_markers import FailedFire, FireAdvisory
from cortex_command.overnight.report import (
    ReportData,
    collect_report_data,
    render_scheduled_fire_advisories,
    render_scheduled_fire_failures,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_failure(
    *,
    ts: str = "2026-05-04T22:00:11Z",
    error_class: str = "EPERM",
    error_text: str = "Operation not permitted: /usr/local/bin/cortex",
    label: str = "com.charleshall.cortex-command.overnight-schedule.s.1",
    session_id: str = "overnight-2026-05-04-2200",
    session_dir: Path | None = None,
) -> FailedFire:
    return FailedFire(
        ts=ts,
        error_class=error_class,
        error_text=error_text,
        label=label,
        session_id=session_id,
        session_dir=session_dir or Path("/tmp/cortex/lifecycle/sessions") / session_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_render_empty_returns_empty_string() -> None:
    """When ``scheduled_fire_failures`` is empty, the section is omitted."""
    data = ReportData()
    assert data.scheduled_fire_failures == []
    output = render_scheduled_fire_failures(data)
    assert output == ""


def test_render_single_failure_includes_section_header_and_entry() -> None:
    """A single failure renders the section header plus one entry."""
    data = ReportData()
    data.scheduled_fire_failures = [
        _make_failure(
            ts="2026-05-04T22:00:11Z",
            error_class="command_not_found",
            error_text="cortex binary not found at /usr/local/bin/cortex",
            label="com.charleshall.cortex-command.overnight-schedule.alpha.1",
            session_id="overnight-2026-05-04-2200",
            session_dir=Path("/Users/me/proj/cortex/lifecycle/sessions/overnight-2026-05-04-2200"),
        ),
    ]
    output = render_scheduled_fire_failures(data)

    # Section header with count
    assert "## Scheduled-Fire Failures (1)" in output
    # Per-failure subheader
    assert "### overnight-2026-05-04-2200 — command_not_found" in output
    # Fields surfaced
    assert "2026-05-04T22:00:11Z" in output
    assert "command_not_found" in output
    assert "cortex binary not found at /usr/local/bin/cortex" in output
    assert "com.charleshall.cortex-command.overnight-schedule.alpha.1" in output


def test_render_single_failure_contains_absolute_marker_path() -> None:
    """The rendered section includes the absolute marker path for diagnostics."""
    session_dir = Path("/Users/me/proj/cortex/lifecycle/sessions/overnight-2026-05-04-2200")
    data = ReportData()
    data.scheduled_fire_failures = [
        _make_failure(session_dir=session_dir),
    ]
    output = render_scheduled_fire_failures(data)

    expected_marker = session_dir / "scheduled-fire-failed.json"
    assert str(expected_marker) in output, (
        f"absolute marker path {expected_marker} not in rendered output:\n"
        f"{output}"
    )
    # And the path is absolute (not relative)
    assert str(expected_marker).startswith("/")


def test_render_multiple_failures_renders_every_entry() -> None:
    """Every failure in the list is rendered as its own entry."""
    failures = [
        _make_failure(
            ts="2026-05-04T22:00:11Z",
            error_class="EPERM",
            session_id="session-aaa",
            session_dir=Path("/tmp/cortex/lifecycle/sessions/session-aaa"),
            label="com.charleshall.cortex-command.overnight-schedule.aaa.1",
        ),
        _make_failure(
            ts="2026-05-05T23:30:00Z",
            error_class="command_not_found",
            session_id="session-bbb",
            session_dir=Path("/tmp/cortex/lifecycle/sessions/session-bbb"),
            label="com.charleshall.cortex-command.overnight-schedule.bbb.2",
        ),
        _make_failure(
            ts="2026-05-06T01:15:42Z",
            error_class="EPERM",
            session_id="session-ccc",
            session_dir=Path("/tmp/cortex/lifecycle/sessions/session-ccc"),
            label="com.charleshall.cortex-command.overnight-schedule.ccc.3",
        ),
    ]
    data = ReportData()
    data.scheduled_fire_failures = failures
    output = render_scheduled_fire_failures(data)

    # Section header has the right count
    assert "## Scheduled-Fire Failures (3)" in output

    # Every session appears in the output
    for failure in failures:
        assert failure.session_id in output
        # The marker path is rendered for each
        marker = Path(failure.session_dir) / "scheduled-fire-failed.json"
        assert str(marker) in output
        # Timestamps and labels surface
        assert failure.ts in output
        assert failure.label in output


def test_render_two_failures_count_matches() -> None:
    """The section count matches the list length even for two entries."""
    data = ReportData()
    data.scheduled_fire_failures = [
        _make_failure(session_id="s1", session_dir=Path("/tmp/s1")),
        _make_failure(session_id="s2", session_dir=Path("/tmp/s2")),
    ]
    output = render_scheduled_fire_failures(data)
    assert "## Scheduled-Fire Failures (2)" in output
    assert "### s1" in output
    assert "### s2" in output


# ---------------------------------------------------------------------------
# Failure vs advisory distinction (spec §R6/§R7) — helpers
# ---------------------------------------------------------------------------


def _write_failure_marker(
    session_dir: Path,
    *,
    ts: str,
    error_class: str = "spawn_died",
    error_text: str = "scheduled overnight fire died before claiming runner.pid",
    label: str = "com.charleshall.cortex-command.overnight-schedule.s.1",
    session_id: str = "s",
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts,
        "error_class": error_class,
        "error_text": error_text,
        "label": label,
        "session_id": session_id,
    }
    marker = session_dir / "scheduled-fire-failed.json"
    marker.write_text(json.dumps(payload), encoding="utf-8")
    return marker


def _write_advisory_marker(
    session_dir: Path,
    *,
    ts: str,
    error_class: str = "spawn_unconfirmed",
    error_text: str = "scheduled overnight fire started but not yet confirmed",
    label: str = "com.charleshall.cortex-command.overnight-schedule.s.1",
    session_id: str = "s",
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts,
        "kind": "advisory",
        "severity": "advisory",
        "error_class": error_class,
        "error_text": error_text,
        "label": label,
        "session_id": session_id,
    }
    marker = session_dir / "scheduled-fire-advisory.json"
    marker.write_text(json.dumps(payload), encoding="utf-8")
    return marker


def _write_session_state(
    session_dir: Path,
    session_id: str,
    *,
    phase: str = "planning",
    scheduled_start: str | None = None,
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "plan_ref": "cortex/lifecycle/test/plan.md",
        "current_round": 1,
        "phase": phase,
        "features": {},
        "round_history": [],
        "started_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:00:00",
        "schema_version": 1,
    }
    if scheduled_start is not None:
        payload["scheduled_start"] = scheduled_start
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def _iso_now(offset_seconds: float = 0.0) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_args(session_dir: Path, *, fmt: str = "json") -> argparse.Namespace:
    return argparse.Namespace(format=fmt, session_dir=str(session_dir))


def _run_status_json(
    session_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> dict:
    """Run ``handle_status`` in JSON mode against ``session_dir`` and parse."""
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )
    rc = cli_handler.handle_status(_status_args(session_dir, fmt="json"))
    captured = capsys.readouterr()
    assert rc == 0, f"unexpected stderr={captured.err!r}"
    return json.loads(captured.out.strip())


# ---------------------------------------------------------------------------
# (a) spawn_died renders as a failure in status + report
# ---------------------------------------------------------------------------


def test_spawn_died_renders_as_failure_in_report(tmp_path: Path) -> None:
    """A ``spawn_died`` failure marker is collected into the failure tally."""
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    sessions_root = lifecycle_root / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_failure_marker(
        sdir, ts="2026-05-04T22:00:11Z", session_id="overnight-2026-05-04-2200"
    )

    advisories, escalated = fail_markers.scan_advisory_dirs(lifecycle_root)
    failures = fail_markers.scan_session_dirs(lifecycle_root)
    assert advisories == []
    assert escalated == []
    assert len(failures) == 1
    assert failures[0].error_class == "spawn_died"
    assert failures[0].kind == "failure"

    data = ReportData()
    data.scheduled_fire_failures = failures
    output = render_scheduled_fire_failures(data)
    assert "## Scheduled-Fire Failures (1)" in output
    assert "spawn_died" in output


def test_spawn_died_renders_as_failure_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A ``spawn_died`` marker shows in the status JSON ``fire_failures`` list."""
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200")
    _write_failure_marker(
        sdir, ts="2026-05-04T22:00:11Z", session_id="overnight-2026-05-04-2200"
    )

    payload = _run_status_json(sdir, monkeypatch, capsys)
    assert len(payload["fire_failures"]) == 1
    assert payload["fire_failures"][0]["error_class"] == "spawn_died"
    assert payload.get("fire_advisories") == []


# ---------------------------------------------------------------------------
# (b) fresh advisory renders as a non-failure advisory, excluded from tally
# ---------------------------------------------------------------------------


def test_fresh_advisory_is_non_failure_in_report(tmp_path: Path) -> None:
    """A fresh advisory is partitioned out of the failure tally."""
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    sessions_root = lifecycle_root / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200")
    _write_advisory_marker(
        sdir, ts=_iso_now(), session_id="overnight-2026-05-04-2200"
    )

    advisories, escalated = fail_markers.scan_advisory_dirs(lifecycle_root)
    failures = fail_markers.scan_session_dirs(lifecycle_root)
    assert failures == []
    assert escalated == []
    assert len(advisories) == 1
    assert advisories[0].error_class == "spawn_unconfirmed"
    assert advisories[0].kind == "advisory"

    data = ReportData()
    data.scheduled_fire_advisories = advisories
    # Failure section omitted; advisory section present and distinct.
    assert render_scheduled_fire_failures(data) == ""
    advisory_output = render_scheduled_fire_advisories(data)
    assert "Awaiting Confirmation" in advisory_output
    assert "scheduled fire started — awaiting confirmation" in advisory_output


def test_fresh_advisory_collect_report_data_excludes_from_tally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: collect_report_data keeps a fresh advisory out of failures."""
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    sessions_root = lifecycle_root / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200")
    _write_advisory_marker(
        sdir, ts=_iso_now(), session_id="overnight-2026-05-04-2200"
    )

    monkeypatch.setattr(
        "cortex_command.overnight.report._resolve_user_project_root",
        lambda: tmp_path,
    )
    data = collect_report_data(state_path=sdir / "overnight-state.json")
    assert data.scheduled_fire_failures == []
    assert len(data.scheduled_fire_advisories) == 1
    assert data.scheduled_fire_advisories[0].error_class == "spawn_unconfirmed"


def test_fresh_advisory_is_non_failure_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A fresh advisory shows in ``fire_advisories``, NOT ``fire_failures``."""
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200")
    _write_advisory_marker(
        sdir, ts=_iso_now(), session_id="overnight-2026-05-04-2200"
    )

    payload = _run_status_json(sdir, monkeypatch, capsys)
    assert payload["fire_failures"] == []
    assert len(payload["fire_advisories"]) == 1
    assert payload["fire_advisories"][0]["error_class"] == "spawn_unconfirmed"


# ---------------------------------------------------------------------------
# (c) stale advisory escalates to a failure in status + report
# ---------------------------------------------------------------------------


def test_stale_advisory_escalates_to_failure_in_report(tmp_path: Path) -> None:
    """An old advisory with no live runner + non-executing phase escalates."""
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    sessions_root = lifecycle_root / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    # Session never reached its round loop (phase planning), no runner.pid.
    _write_session_state(sdir, "overnight-2026-05-04-2200", phase="planning")
    stale_ts = _iso_now(
        offset_seconds=-(fail_markers.STALE_ADVISORY_THRESHOLD_SECONDS + 60)
    )
    _write_advisory_marker(
        sdir, ts=stale_ts, session_id="overnight-2026-05-04-2200"
    )

    advisories, escalated = fail_markers.scan_advisory_dirs(lifecycle_root)
    assert advisories == []
    assert len(escalated) == 1
    assert escalated[0].kind == "advisory_escalated"
    assert escalated[0].error_class == "spawn_unconfirmed"
    assert "escalated" in escalated[0].error_text.lower()

    # And it renders in the failure section with the advisory marker path.
    data = ReportData()
    data.scheduled_fire_failures = escalated
    output = render_scheduled_fire_failures(data)
    assert "## Scheduled-Fire Failures (1)" in output
    assert "scheduled-fire-advisory.json" in output


def test_stale_advisory_not_escalated_when_session_executing(
    tmp_path: Path,
) -> None:
    """An executing session means the slow start resolved — no escalation."""
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    sessions_root = lifecycle_root / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200", phase="executing")
    stale_ts = _iso_now(
        offset_seconds=-(fail_markers.STALE_ADVISORY_THRESHOLD_SECONDS + 60)
    )
    _write_advisory_marker(
        sdir, ts=stale_ts, session_id="overnight-2026-05-04-2200"
    )

    advisories, escalated = fail_markers.scan_advisory_dirs(lifecycle_root)
    assert escalated == []
    assert len(advisories) == 1


def test_stale_advisory_escalates_to_failure_in_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A stale advisory surfaces in the status ``fire_failures`` tally."""
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    sdir = sessions_root / "overnight-2026-05-04-2200"
    _write_session_state(sdir, "overnight-2026-05-04-2200", phase="planning")
    stale_ts = _iso_now(
        offset_seconds=-(fail_markers.STALE_ADVISORY_THRESHOLD_SECONDS + 60)
    )
    _write_advisory_marker(
        sdir, ts=stale_ts, session_id="overnight-2026-05-04-2200"
    )

    payload = _run_status_json(sdir, monkeypatch, capsys)
    assert payload["fire_advisories"] == []
    assert len(payload["fire_failures"]) == 1
    assert payload["fire_failures"][0]["kind"] == "advisory_escalated"
    assert payload["fire_failures"][0]["error_class"] == "spawn_unconfirmed"
