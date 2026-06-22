"""Regression tests for status timezone normalization (Task 9 / R6/R8).

Reproduces the **actual reported crash** behind backlog #311: ``cortex
overnight status`` raised ``TypeError: can't compare offset-naive and
offset-aware datetimes`` when a **dormant/scheduled** session carried a
**naive-local** ``scheduled_start`` written by the scheduler. The crash
fires at the ``fires_at <= now`` compare in ``_is_scheduled_dormant``
(``status.py:184``) — reached only for non-``executing``/non-``complete``
phases, because the predicate early-returns on those before the compare.

Task 8 fixed ``_parse_iso`` to normalize naive→system-local→UTC via
``.astimezone(timezone.utc)`` so every compare site compares aware-vs-aware.
These tests run under a non-UTC ``TZ`` (``America/New_York``) via
``monkeypatch.setenv`` + ``time.tzset()`` so naive timestamps resolve to a
non-UTC local offset and any UTC-skew regression is observable.

Each test asserts the post-fix behavior:
  (a) no exception,
  (b) output lacks ``Error reading status:``,
  (c) the dormant "fires at" / elapsed decision matches the
      local-wall-clock interpretation (not skewed by the UTC offset).

Against the pre-fix ``_parse_iso`` (naive passthrough) the **primary**
(dormant) case raises ``TypeError`` and these assertions fail; post-fix
they pass.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cortex_command.overnight import status as status_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state(
    tmp_path: Path,
    session_id: str,
    *,
    phase: str,
    started_at: str,
    scheduled_start: str | None,
) -> Path:
    """Write a session state under tmp_path's cortex/lifecycle/sessions tree.

    Mirrors the ``_write_render_state`` fixture shape from
    ``test_status_scheduled_start.py``. No ``runner.pid`` is created, so the
    liveness probe reports no live runner (a precondition for the
    scheduled-dormant render).

    Returns the per-session state path.
    """
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "plan_ref": "cortex/lifecycle/test/plan.md",
        "current_round": 1,
        "phase": phase,
        "features": {},
        "round_history": [],
        "started_at": started_at,
        "updated_at": started_at,
        "schema_version": 1,
    }
    if scheduled_start is not None:
        payload["scheduled_start"] = scheduled_start
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


@pytest.fixture
def ny_tz(monkeypatch: pytest.MonkeyPatch):
    """Pin the process timezone to America/New_York for the test body.

    A non-UTC offset makes naive timestamps resolve to a wall clock that
    differs from UTC, so any reintroduced UTC-skew (e.g. a naive value
    wrongly stamped as UTC) is observable. ``time.tzset()`` applies the env
    change to ``datetime.now()`` / ``.astimezone()`` immediately.
    """
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    # ``monkeypatch`` restores the TZ env var on teardown; re-apply it to the
    # C library so subsequent tests in the process see the original zone.
    monkeypatch.undo()
    time.tzset()


def _prepare_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark ``tmp_path`` as a cortex project and point resolution at it.

    Creates the ``.git`` and ``cortex/`` markers the upward-walk resolver
    looks for, and sets ``CORTEX_REPO_ROOT`` so ``status``'s call-time
    project-root resolution lands on ``tmp_path`` verbatim.
    """
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "cortex").mkdir(exist_ok=True)
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))


def _local_naive_offset(delta: timedelta) -> str:
    """Return a naive-local ISO timestamp ``delta`` from the local wall clock.

    Under ``America/New_York`` (UTC-4/-5) a value in the local future maps to
    a UTC time that is still in the future post-fix; if it were wrongly
    reinterpreted naive-as-UTC it would land in the past, flipping the
    dormant decision — which is exactly the skew these tests guard against.
    """
    return (datetime.now() + delta).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Primary case — the reported live crash (dormant naive-local scheduled_start)
# ---------------------------------------------------------------------------


def test_dormant_naive_local_scheduled_start_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, ny_tz
) -> None:
    """Reproduces backlog #311: dormant session, naive-local ``scheduled_start``.

    Phase is ``planning`` (NOT executing/complete) so ``_is_scheduled_dormant``
    reaches the ``fires_at <= now`` compare that crashed pre-fix. ``started_at``
    is aware so the earlier ``render_status`` elapsed compare does not pre-empt
    the dormant compare — isolating the reported crash site.

    Post-fix: no exception, no ``Error reading status:``, and the dormant
    "fires at" line renders because the future local wall-clock time is
    correctly interpreted (a UTC-skew would push it into the past and suppress
    the dormant render).
    """
    _prepare_repo_root(tmp_path, monkeypatch)
    sched = _local_naive_offset(timedelta(hours=1))  # naive-local, near a fire boundary
    _write_state(
        tmp_path,
        "overnight-2026-06-22-2200",
        phase="planning",
        started_at="2026-05-04T10:00:00+00:00",  # aware: passes the elapsed compare
        scheduled_start=sched,
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Error reading status:" not in out
    # Correct local-wall-clock interpretation: the fire is in the future, so
    # the session renders scheduled-dormant (a UTC-skew would read it as past).
    assert f"Scheduled (dormant) — fires at {sched}" in out
    # Executing-run metrics are suppressed for a merely-pending fire.
    assert "Elapsed" not in out


# ---------------------------------------------------------------------------
# Secondary case — executing naive started_at (render_status elapsed compare)
# ---------------------------------------------------------------------------


def test_executing_naive_started_at_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, ny_tz
) -> None:
    """Executing session with a **naive** ``started_at`` exercises the
    ``render_status`` elapsed compare (``status.py:343``).

    Pre-fix the naive ``started_at`` would crash the ``now - _parse_iso(...)``
    subtraction against the aware ``now``; post-fix it normalizes to UTC and
    the elapsed line renders without error.
    """
    _prepare_repo_root(tmp_path, monkeypatch)
    started = _local_naive_offset(timedelta(hours=-2))  # naive-local, 2h ago
    _write_state(
        tmp_path,
        "overnight-2026-06-22-2300",
        phase="executing",
        started_at=started,
        scheduled_start=None,
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Error reading status:" not in out
    assert "Elapsed" in out
    assert "Scheduled (dormant)" not in out


# ---------------------------------------------------------------------------
# Aware started_at — aware values pass through converted, not reinterpreted
# ---------------------------------------------------------------------------


def test_executing_aware_started_at_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, ny_tz
) -> None:
    """Executing session with an **aware** ``started_at`` renders cleanly.

    Aware production timestamps convert to UTC and compare aware-vs-aware
    under a non-UTC ``TZ`` without exception or error.
    """
    _prepare_repo_root(tmp_path, monkeypatch)
    started = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    _write_state(
        tmp_path,
        "overnight-2026-06-22-0100",
        phase="executing",
        started_at=started,
        scheduled_start=None,
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Error reading status:" not in out
    assert "Elapsed" in out


# ---------------------------------------------------------------------------
# Mixed — naive started_at + aware scheduled_start in one dormant session
# ---------------------------------------------------------------------------


def test_mixed_naive_and_aware_timestamps_render_dormant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, ny_tz
) -> None:
    """Mixed-tz session: naive ``started_at`` + aware future ``scheduled_start``.

    Exercises both the ``render_status`` elapsed compare (naive ``started_at``)
    and the dormant compare (aware ``scheduled_start``) in a single dormant
    render. Post-fix both normalize to UTC and the dormant line renders without
    error.
    """
    _prepare_repo_root(tmp_path, monkeypatch)
    started = _local_naive_offset(timedelta(hours=-1))  # naive-local, 1h ago
    sched = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()  # aware future
    _write_state(
        tmp_path,
        "overnight-2026-06-22-0200",
        phase="planning",
        started_at=started,
        scheduled_start=sched,
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Error reading status:" not in out
    assert f"Scheduled (dormant) — fires at {sched}" in out
    assert "Elapsed" not in out
