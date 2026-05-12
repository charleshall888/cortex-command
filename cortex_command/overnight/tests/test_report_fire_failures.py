"""Tests for :func:`report.render_scheduled_fire_failures` (Task 12, spec §R13).

The morning-report integration of the launcher fail-marker contract: when
the launchd-fired launcher script writes
``<session_dir>/scheduled-fire-failed.json`` on fire-time spawn failures
(EPERM/command-not-found), the morning report's
``render_scheduled_fire_failures`` section surfaces each marker with
timestamp, error class, session id, and the absolute path to the marker
JSON for diagnostics.

Coverage:
  * Empty list — section is omitted entirely (returns "").
  * Single failure — renders section header and entry with absolute
    marker path.
  * Multiple failures — every entry is rendered.
  * Section text contains absolute paths so the user can copy-paste to
    inspect the marker.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.overnight.fail_markers import FailedFire
from cortex_command.overnight.report import (
    ReportData,
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
