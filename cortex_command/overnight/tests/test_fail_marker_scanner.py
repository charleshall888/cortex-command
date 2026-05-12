"""Tests for :func:`fail_markers.scan_session_dirs` (Task 12, spec §R13).

This is the consumer side of the fail-marker contract that Task 3
establishes: the launchd-fired launcher writes
``<session_dir>/scheduled-fire-failed.json`` on EPERM/command-not-found
spawn failures. The scanner walks ``<state_root>/sessions/*`` for those
markers and returns a list of :class:`FailedFire` dataclasses.

Coverage:
  * Happy-path parse with all required fields.
  * Multiple session dirs with mixed states (some with markers, some
    without — the scanner must only return markers that exist).
  * Corrupt JSON in one marker (skipped with warning, doesn't crash).
  * The ``since`` filter (markers before the cutoff are excluded).
  * Missing state root (returns ``[]``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cortex_command.overnight.fail_markers import FailedFire, scan_session_dirs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_marker(
    session_dir: Path,
    *,
    ts: str,
    error_class: str = "command_not_found",
    error_text: str = "cortex binary not found at /usr/local/bin/cortex",
    label: str = "com.charleshall.cortex-command.overnight-schedule.s.123",
    session_id: str = "s",
    extra: dict | None = None,
) -> Path:
    """Write a well-formed ``scheduled-fire-failed.json`` to ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts,
        "error_class": error_class,
        "error_text": error_text,
        "label": label,
        "session_id": session_id,
    }
    if extra:
        payload.update(extra)
    marker = session_dir / "scheduled-fire-failed.json"
    marker.write_text(json.dumps(payload), encoding="utf-8")
    return marker


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_state_root_returns_empty_list(tmp_path: Path) -> None:
    """A non-existent state root returns ``[]`` without raising."""
    nowhere = tmp_path / "does-not-exist"
    assert scan_session_dirs(nowhere) == []


def test_state_root_without_sessions_subdir_returns_empty_list(
    tmp_path: Path,
) -> None:
    """A state root that has no ``sessions/`` subdir returns ``[]``."""
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    assert scan_session_dirs(tmp_path / "cortex" / "lifecycle") == []


def test_empty_sessions_dir_returns_empty_list(tmp_path: Path) -> None:
    """A ``sessions/`` dir with no session subdirs returns ``[]``."""
    (tmp_path / "sessions").mkdir()
    assert scan_session_dirs(tmp_path) == []


def test_happy_path_single_marker(tmp_path: Path) -> None:
    """A single well-formed marker is parsed into a FailedFire."""
    sdir = tmp_path / "sessions" / "overnight-2026-05-04-2200"
    _write_marker(
        sdir,
        ts="2026-05-04T22:00:11Z",
        error_class="EPERM",
        error_text="Operation not permitted: /usr/local/bin/cortex",
        label="com.charleshall.cortex-command.overnight-schedule.alpha.1",
        session_id="overnight-2026-05-04-2200",
    )

    result = scan_session_dirs(tmp_path)
    assert len(result) == 1
    failure = result[0]
    assert isinstance(failure, FailedFire)
    assert failure.ts == "2026-05-04T22:00:11Z"
    assert failure.error_class == "EPERM"
    assert failure.error_text == "Operation not permitted: /usr/local/bin/cortex"
    assert failure.label == "com.charleshall.cortex-command.overnight-schedule.alpha.1"
    assert failure.session_id == "overnight-2026-05-04-2200"
    # session_dir is the absolute path containing the marker
    assert failure.session_dir == sdir.resolve()


def test_multiple_sessions_mixed_states(tmp_path: Path) -> None:
    """Sessions with markers are returned; sessions without are skipped."""
    # Session A: has a marker
    sdir_a = tmp_path / "sessions" / "session-a"
    _write_marker(
        sdir_a,
        ts="2026-05-04T22:00:11Z",
        session_id="session-a",
        label="com.charleshall.cortex-command.overnight-schedule.a.1",
    )

    # Session B: no marker (only an unrelated file)
    sdir_b = tmp_path / "sessions" / "session-b"
    sdir_b.mkdir(parents=True)
    (sdir_b / "overnight-state.json").write_text("{}", encoding="utf-8")

    # Session C: has a marker, later timestamp
    sdir_c = tmp_path / "sessions" / "session-c"
    _write_marker(
        sdir_c,
        ts="2026-05-05T23:30:00Z",
        session_id="session-c",
        label="com.charleshall.cortex-command.overnight-schedule.c.1",
    )

    result = scan_session_dirs(tmp_path)
    assert len(result) == 2
    session_ids = {f.session_id for f in result}
    assert session_ids == {"session-a", "session-c"}
    # Sorted ascending by ts
    assert result[0].session_id == "session-a"
    assert result[1].session_id == "session-c"


def test_corrupt_marker_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One corrupt marker is skipped; valid ones are still returned."""
    # Valid marker
    sdir_good = tmp_path / "sessions" / "good"
    _write_marker(sdir_good, ts="2026-05-04T22:00:11Z", session_id="good")

    # Corrupt marker — invalid JSON
    sdir_bad = tmp_path / "sessions" / "bad"
    sdir_bad.mkdir(parents=True)
    (sdir_bad / "scheduled-fire-failed.json").write_text(
        "{not valid json", encoding="utf-8"
    )

    result = scan_session_dirs(tmp_path)
    assert len(result) == 1
    assert result[0].session_id == "good"

    captured = capsys.readouterr()
    assert "corrupt fail-marker" in captured.err
    # The corrupt marker's path should appear in the warning so the user
    # can find and inspect it.
    assert "bad" in captured.err


def test_marker_missing_required_fields_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A marker missing required keys is skipped with a warning."""
    sdir = tmp_path / "sessions" / "incomplete"
    sdir.mkdir(parents=True)
    # Missing ``label`` and ``session_id``.
    (sdir / "scheduled-fire-failed.json").write_text(
        json.dumps({"ts": "2026-05-04T22:00:11Z", "error_class": "EPERM",
                    "error_text": "denied"}),
        encoding="utf-8",
    )

    result = scan_session_dirs(tmp_path)
    assert result == []

    captured = capsys.readouterr()
    assert "missing keys" in captured.err


def test_marker_non_object_payload_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A marker whose JSON root is not an object is skipped."""
    sdir = tmp_path / "sessions" / "weird"
    sdir.mkdir(parents=True)
    (sdir / "scheduled-fire-failed.json").write_text(
        json.dumps(["not", "an", "object"]), encoding="utf-8"
    )

    result = scan_session_dirs(tmp_path)
    assert result == []

    captured = capsys.readouterr()
    assert "not a JSON object" in captured.err


def test_since_filter_excludes_old_markers(tmp_path: Path) -> None:
    """Markers older than ``since`` are filtered out; newer ones kept."""
    # Old marker — before cutoff
    sdir_old = tmp_path / "sessions" / "old-session"
    _write_marker(
        sdir_old,
        ts="2026-05-04T20:00:00Z",
        session_id="old-session",
        label="com.charleshall.cortex-command.overnight-schedule.old.1",
    )

    # New marker — after cutoff
    sdir_new = tmp_path / "sessions" / "new-session"
    _write_marker(
        sdir_new,
        ts="2026-05-05T22:00:00Z",
        session_id="new-session",
        label="com.charleshall.cortex-command.overnight-schedule.new.1",
    )

    cutoff = datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)
    result = scan_session_dirs(tmp_path, since=cutoff)

    assert len(result) == 1
    assert result[0].session_id == "new-session"


def test_since_filter_keeps_unparseable_ts(tmp_path: Path) -> None:
    """A marker with an unparseable ts is kept (don't drop silently)."""
    sdir = tmp_path / "sessions" / "weird-ts"
    _write_marker(
        sdir,
        ts="not-a-valid-timestamp",
        session_id="weird-ts",
        label="com.charleshall.cortex-command.overnight-schedule.weird.1",
    )

    cutoff = datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)
    result = scan_session_dirs(tmp_path, since=cutoff)
    assert len(result) == 1
    assert result[0].session_id == "weird-ts"


def test_since_none_returns_all_markers(tmp_path: Path) -> None:
    """When ``since`` is None, every well-formed marker is returned."""
    for i, ts in enumerate(
        ["2025-01-01T00:00:00Z", "2026-05-04T22:00:00Z", "2027-12-31T23:59:00Z"]
    ):
        sdir = tmp_path / "sessions" / f"session-{i}"
        _write_marker(
            sdir,
            ts=ts,
            session_id=f"session-{i}",
            label=f"com.charleshall.cortex-command.overnight-schedule.s.{i}",
        )

    result = scan_session_dirs(tmp_path, since=None)
    assert len(result) == 3
    # Sorted ascending by ts
    assert [f.session_id for f in result] == [
        "session-0",
        "session-1",
        "session-2",
    ]


def test_to_dict_serializes_session_dir_as_string(tmp_path: Path) -> None:
    """``FailedFire.to_dict`` casts ``session_dir`` to a string for JSON."""
    sdir = tmp_path / "sessions" / "ser"
    _write_marker(sdir, ts="2026-05-04T22:00:11Z", session_id="ser")
    result = scan_session_dirs(tmp_path)
    assert len(result) == 1

    d = result[0].to_dict()
    assert isinstance(d["session_dir"], str)
    assert d["session_dir"] == str(sdir.resolve())
    # Round-trips through JSON without errors
    json.dumps(d)
