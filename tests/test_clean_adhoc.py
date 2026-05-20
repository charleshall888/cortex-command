"""Tests for ``cortex_command.clean.run_adhoc`` — Task 8 (ticket-255).

Covers Requirement 9 of the gate-policy-taxonomy-and-critical-review
spec for the ``cortex-clean --adhoc`` retention recipe. This task ships
the skeleton + pin-set construction + retention basics; concurrency
scenarios (d) and (e) are deferred to Task 9.

Scenarios in this file:

  (a) old-and-unpinned snapshot is deleted
  (b) old-and-pinned-by-active-events.log snapshot retained
  (c) new-and-unpinned snapshot retained
  (f) ``.staging-*`` and ``.tombstone-*`` paths are ignored
  (g) old-and-pinned-by-archived-events.log snapshot retained
  (h) old-and-pinned-by-sessions-events.log snapshot retained
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from cortex_command.clean import RETENTION_SECONDS, run_adhoc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Build a minimal repo scaffold under ``tmp_path`` and return the root."""
    repo = tmp_path / "repo"
    (repo / "cortex" / "lifecycle").mkdir(parents=True)
    (repo / "cortex" / "_adhoc").mkdir(parents=True)
    return repo


def _make_snapshot(repo: Path, content: bytes, *, age_seconds: float | None = None) -> tuple[Path, str]:
    """Create a snapshot directory under ``cortex/_adhoc/<sha[:2]>/<sha[2:]>/``.

    Returns ``(leaf_dir, full_sha)``. If ``age_seconds`` is provided,
    the leaf directory's mtime is back-dated by that many seconds.
    """
    full_sha = hashlib.sha256(content).hexdigest()
    leaf = repo / "cortex" / "_adhoc" / full_sha[:2] / full_sha[2:]
    leaf.mkdir(parents=True)
    (leaf / "snapshot.md").write_bytes(content)
    if age_seconds is not None:
        target_mtime = time.time() - age_seconds
        os.utime(leaf, (target_mtime, target_mtime))
    return leaf, full_sha


def _write_events_log(events_log: Path, rows: list[dict]) -> None:
    """Write JSONL rows into ``events_log`` (creating parent dirs)."""
    events_log.parent.mkdir(parents=True, exist_ok=True)
    with events_log.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Scenario (a): old-and-unpinned snapshot is deleted
# ---------------------------------------------------------------------------


def test_old_and_unpinned_snapshot_is_deleted(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    leaf, _sha = _make_snapshot(
        repo, b"orphan content\n", age_seconds=RETENTION_SECONDS + 60
    )

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert not leaf.exists(), "old-and-unpinned snapshot directory should be deleted"


# ---------------------------------------------------------------------------
# Scenario (b): old-and-pinned-by-active-events.log snapshot retained
# ---------------------------------------------------------------------------


def test_old_and_pinned_by_active_events_log_is_retained(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    leaf, full_sha = _make_snapshot(
        repo, b"active-pinned content\n", age_seconds=RETENTION_SECONDS + 60
    )
    events_log = repo / "cortex" / "lifecycle" / "feat-active" / "events.log"
    _write_events_log(
        events_log,
        [
            {
                "ts": "2026-05-19T00:00:00Z",
                "event": "sentinel_absence",
                "feature": "feat-active",
                "snapshot_sha": full_sha,
            },
        ],
    )

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert leaf.exists(), "snapshot pinned by an active events.log should NOT be deleted"


# ---------------------------------------------------------------------------
# Scenario (c): new-and-unpinned snapshot retained
# ---------------------------------------------------------------------------


def test_new_and_unpinned_snapshot_is_retained(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # Fresh mtime — well under the 7-day retention threshold.
    leaf, _sha = _make_snapshot(repo, b"fresh content\n", age_seconds=60)

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert leaf.exists(), "new-and-unpinned snapshot should be retained (mtime < 7d)"


# ---------------------------------------------------------------------------
# Scenario (f): .staging-* and .tombstone-* paths are ignored
# ---------------------------------------------------------------------------


def test_staging_and_tombstone_paths_are_ignored(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    adhoc_root = repo / "cortex" / "_adhoc"

    # An in-flight ``.staging-*`` directory at the fanout level. The
    # cleaner should not descend into it nor delete it.
    staging_fanout = adhoc_root / ".staging-abcdef0123456789"
    staging_fanout.mkdir()
    (staging_fanout / "marker").write_text("staging", encoding="utf-8")
    # Back-date so age alone would qualify it.
    target_mtime = time.time() - (RETENTION_SECONDS + 60)
    os.utime(staging_fanout, (target_mtime, target_mtime))

    # A queued-deletion ``.tombstone-*`` directory at the fanout level.
    tombstone_fanout = adhoc_root / ".tombstone-fedcba9876543210"
    tombstone_fanout.mkdir()
    (tombstone_fanout / "marker").write_text("tombstone", encoding="utf-8")
    os.utime(tombstone_fanout, (target_mtime, target_mtime))

    # ``.staging-*`` and ``.tombstone-*`` also appear at the leaf level
    # under a real-looking fanout dir. Build a fanout dir with a valid
    # 2-hex name, then place a ``.staging-*`` leaf inside it.
    fanout = adhoc_root / "ab"
    fanout.mkdir()
    staging_leaf = fanout / (".staging-" + ("c" * 62) + ".file")
    staging_leaf.mkdir()
    (staging_leaf / "x").write_text("y", encoding="utf-8")
    os.utime(staging_leaf, (target_mtime, target_mtime))

    tombstone_leaf = fanout / (".tombstone-" + ("d" * 62))
    tombstone_leaf.mkdir()
    (tombstone_leaf / "x").write_text("y", encoding="utf-8")
    os.utime(tombstone_leaf, (target_mtime, target_mtime))

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert staging_fanout.exists(), ".staging-* fanout dir should be ignored"
    assert tombstone_fanout.exists(), ".tombstone-* fanout dir should be ignored"
    assert staging_leaf.exists(), ".staging-* leaf dir should be ignored"
    assert tombstone_leaf.exists(), ".tombstone-* leaf dir should be ignored"


# ---------------------------------------------------------------------------
# Scenario (g): old-and-pinned-by-archived-events.log snapshot retained
# ---------------------------------------------------------------------------


def test_old_and_pinned_by_archived_events_log_is_retained(tmp_path: Path) -> None:
    """Spec Requirement 9 + Task 8 critical-review follow-up: pin set
    must include archived lifecycles at
    ``cortex/lifecycle/archive/<feature>/events.log``."""
    repo = _make_repo(tmp_path)
    leaf, full_sha = _make_snapshot(
        repo, b"archive-pinned content\n", age_seconds=RETENTION_SECONDS + 60
    )
    events_log = (
        repo / "cortex" / "lifecycle" / "archive" / "feat-archived" / "events.log"
    )
    _write_events_log(
        events_log,
        [
            {
                "ts": "2026-04-01T00:00:00Z",
                "event": "sentinel_absence",
                "feature": "feat-archived",
                "snapshot_sha": full_sha,
            },
        ],
    )

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert leaf.exists(), (
        "snapshot pinned by an archived events.log should NOT be deleted; "
        "pin-set construction must walk cortex/lifecycle/archive/"
    )


def test_archived_pin_dry_run_lists_no_deletion_for_pinned_snapshot(
    tmp_path: Path,
) -> None:
    """Spec Verification gate: ``cortex-clean --adhoc --dry-run`` against
    a fixture with an archived-pin snapshot prints no deletion candidate
    and leaves the snapshot in place."""
    repo = _make_repo(tmp_path)
    leaf, full_sha = _make_snapshot(
        repo, b"archive-pinned dry-run\n", age_seconds=RETENTION_SECONDS + 60
    )
    events_log = (
        repo / "cortex" / "lifecycle" / "archive" / "feat-archived" / "events.log"
    )
    _write_events_log(
        events_log,
        [
            {
                "ts": "2026-04-01T00:00:00Z",
                "event": "sentinel_absence",
                "feature": "feat-archived",
                "snapshot_sha": full_sha,
            },
        ],
    )

    import io

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = run_adhoc(repo, dry_run=True, stdout=stdout_buf, stderr=stderr_buf)

    assert exit_code == 0
    assert leaf.exists()
    assert str(leaf) not in stdout_buf.getvalue()


# ---------------------------------------------------------------------------
# Scenario (h): old-and-pinned-by-sessions-events.log snapshot retained
# ---------------------------------------------------------------------------


def test_old_and_pinned_by_sessions_events_log_is_retained(tmp_path: Path) -> None:
    """Spec Requirement 9 + Task 8 critical-review follow-up: pin set
    must include sessions at
    ``cortex/lifecycle/sessions/<uuid>/events.log``."""
    repo = _make_repo(tmp_path)
    leaf, full_sha = _make_snapshot(
        repo, b"sessions-pinned content\n", age_seconds=RETENTION_SECONDS + 60
    )
    session_uuid = "014f9926-741a-4355-afa8-c98c19fc8599"
    events_log = (
        repo
        / "cortex"
        / "lifecycle"
        / "sessions"
        / session_uuid
        / "events.log"
    )
    _write_events_log(
        events_log,
        [
            {
                "ts": "2026-05-01T00:00:00Z",
                "event": "sentinel_absence",
                "feature": "session-feature",
                "snapshot_sha": full_sha,
            },
        ],
    )

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert leaf.exists(), (
        "snapshot pinned by a sessions/<uuid>/events.log should NOT be deleted; "
        "pin-set construction must walk cortex/lifecycle/sessions/"
    )


# ---------------------------------------------------------------------------
# Bonus coverage: dry-run prints unpinned candidates
# ---------------------------------------------------------------------------


def test_dry_run_prints_candidates_without_deleting(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    leaf, _sha = _make_snapshot(
        repo, b"dry-run target\n", age_seconds=RETENTION_SECONDS + 60
    )

    import io

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = run_adhoc(repo, dry_run=True, stdout=stdout_buf, stderr=stderr_buf)

    assert exit_code == 0
    assert leaf.exists(), "dry-run must not delete anything"
    assert str(leaf) in stdout_buf.getvalue()


# ---------------------------------------------------------------------------
# Bonus coverage: stray (non-hex-fanout) directories are skipped
# ---------------------------------------------------------------------------


def test_stray_non_hex_directory_is_skipped(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    stray = repo / "cortex" / "_adhoc" / "README"
    stray.mkdir()
    (stray / "info").write_text("stray", encoding="utf-8")
    target_mtime = time.time() - (RETENTION_SECONDS + 60)
    os.utime(stray, (target_mtime, target_mtime))

    exit_code = run_adhoc(repo)

    assert exit_code == 0
    assert stray.exists(), "non-SHA-shaped directories must not be deleted"


# ---------------------------------------------------------------------------
# Bonus coverage: empty repo (no archive/ or sessions/) does not error
# ---------------------------------------------------------------------------


def test_fresh_repo_without_archive_or_sessions_does_not_error(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # No archive/, no sessions/, no snapshots, no events.log files.
    exit_code = run_adhoc(repo)
    assert exit_code == 0
