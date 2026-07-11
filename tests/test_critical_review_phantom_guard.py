"""Write-guard tests for the three critical-review telemetry writers (Reqs 2, 3).

Spec ``investigate-critical-review-telemetry-creating-phantom``, Phase 1.

The guard sits immediately before the ``log_event_at`` call in
``_cmd_check_synth_stable``, ``_cmd_check_artifact_stable``, and
``_cmd_record_exclusion`` (``cortex_command/critical_review/__init__.py``). When
the target ``cortex/lifecycle/{feature}/`` dir does NOT already exist, the writer
emits a one-line stderr note, skips the ``mkdir``+append, and returns
``EXIT_TELEMETRY_SKIPPED`` (4). This prevents a non-feature ``<path>``-arg review
from creating a phantom lifecycle dir.

Exit-code contract under test:
  0 = clean / recorded
  2 = OSError
  3 = drift / absence (genuine invalidation)
  4 = telemetry-skipped (target lifecycle dir absent)

Coverage:
  (a) Req 2 — each of the three subcommands invoked with a ``--feature`` whose
      ``cortex/lifecycle/{feature}/`` dir does NOT exist creates no directory,
      writes no events.log, and returns exit 4 (the dir-absent skip).
  (b) Req 3 — auto-trigger invariant: when the dir already exists, each writer
      appends normally; a genuine drift/absence still returns exit 3 (synth /
      artifact) and ``record-exclusion`` records and returns 0.
  (c) Req 2(a)/(b) — exit 4 is observably distinct from both 3 (genuine
      invalidation) and 0 (successful record / clean check).

Invocation idioms mirror ``tests/test_variant_a_writer_sites_baseline.py``: the
argparse entry point ``cortex_command.critical_review.main`` is driven with an
explicit ``--lifecycle-root`` rooted under ``tmp_path``. ``check-synth-stable``
reads sentinel-free stdin (monkeypatched); ``check-artifact-stable`` reads a
sentinel-free ``--input-file``; ``record-exclusion`` always attempts a write
(it does no sentinel parsing).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cortex_command.critical_review import EXIT_TELEMETRY_SKIPPED
from cortex_command.critical_review import main as cr_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_check_synth_stable(
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_root: Path,
    feature: str,
    stdin_text: str = "no sentinel here",
    expected_sha: str = "deadbeef",
) -> int:
    """Invoke ``check-synth-stable`` with sentinel-free stdin (status -> absent)."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    return cr_main(
        [
            "--lifecycle-root",
            str(lifecycle_root),
            "check-synth-stable",
            "--feature",
            feature,
            "--expected-sha",
            expected_sha,
        ]
    )


def _run_check_artifact_stable(
    lifecycle_root: Path,
    feature: str,
    input_file: Path,
    expected_sha: str = "deadbeef",
) -> int:
    """Invoke ``check-artifact-stable`` reading sentinel-free ``--input-file``."""
    input_file.write_text("no sentinel here either\n", encoding="utf-8")
    return cr_main(
        [
            "--lifecycle-root",
            str(lifecycle_root),
            "check-artifact-stable",
            "--feature",
            feature,
            "--reviewer-angle",
            "code-quality",
            "--expected-sha",
            expected_sha,
            "--model-tier",
            "sonnet",
            "--input-file",
            str(input_file),
        ]
    )


def _run_record_exclusion(
    lifecycle_root: Path,
    feature: str,
    expected_sha: str = "abc123",
) -> int:
    """Invoke ``record-exclusion`` (always attempts a write — no sentinel parse)."""
    return cr_main(
        [
            "--lifecycle-root",
            str(lifecycle_root),
            "record-exclusion",
            "--feature",
            feature,
            "--reviewer-angle",
            "code-quality",
            "--reason",
            "absent",
            "--model-tier",
            "sonnet",
            "--expected-sha",
            expected_sha,
        ]
    )


# ===========================================================================
# (a) Req 2 — dir-absent skip: no dir, no events.log, exit 4
# ===========================================================================


class TestDirAbsentSkip:
    """Each writer with a ``--feature`` whose lifecycle dir does not exist
    creates no directory, writes no events.log, and returns exit 4.
    """

    def test_check_synth_stable_dir_absent_skips_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "phantom-feature"
        feature_dir = lifecycle_root / feature

        rc = _run_check_synth_stable(monkeypatch, lifecycle_root, feature)

        assert rc == EXIT_TELEMETRY_SKIPPED
        assert not feature_dir.exists(), "guard must not create the lifecycle dir"
        assert not (feature_dir / "events.log").exists(), "no events.log written"

    def test_check_artifact_stable_dir_absent_skips_write(
        self, tmp_path: Path
    ) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "phantom-feature"
        feature_dir = lifecycle_root / feature
        input_file = tmp_path / "reviewer-output.txt"

        rc = _run_check_artifact_stable(lifecycle_root, feature, input_file)

        assert rc == EXIT_TELEMETRY_SKIPPED
        assert not feature_dir.exists(), "guard must not create the lifecycle dir"
        assert not (feature_dir / "events.log").exists(), "no events.log written"

    def test_record_exclusion_dir_absent_skips_write(self, tmp_path: Path) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "phantom-feature"
        feature_dir = lifecycle_root / feature

        rc = _run_record_exclusion(lifecycle_root, feature)

        assert rc == EXIT_TELEMETRY_SKIPPED
        assert not feature_dir.exists(), "guard must not create the lifecycle dir"
        assert not (feature_dir / "events.log").exists(), "no events.log written"

    def test_dir_absent_skip_emits_stderr_note(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The skip path emits a one-line stderr note naming the feature.

        Confirms the skip is operator-visible (per the guard's stderr note),
        not a silent suppression.
        """
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "phantom-feature"

        rc = _run_record_exclusion(lifecycle_root, feature)

        assert rc == EXIT_TELEMETRY_SKIPPED
        captured = capsys.readouterr()
        assert "telemetry skipped" in captured.err
        assert feature in captured.err


# ===========================================================================
# (b) Req 3 — auto-trigger invariant: dir exists -> normal append + real verdict
# ===========================================================================


class TestAutoTriggerInvariant:
    """When the lifecycle dir already exists, each writer appends normally and
    the genuine verdict surfaces (exit 3 for drift/absence; exit 0 + recorded
    for record-exclusion).
    """

    def test_check_synth_stable_dir_exists_writes_and_returns_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "real-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        rc = _run_check_synth_stable(monkeypatch, lifecycle_root, feature)

        # Sentinel absent -> genuine synthesizer_drift verdict (exit 3).
        assert rc == 3
        events_log = feature_dir / "events.log"
        assert events_log.exists()
        rows = _read_jsonl(events_log)
        assert len(rows) == 1
        assert rows[0]["event"] == "synthesizer_drift"
        assert rows[0]["feature"] == feature

    def test_check_artifact_stable_dir_exists_writes_and_returns_3(
        self, tmp_path: Path
    ) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "real-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)
        input_file = tmp_path / "reviewer-output.txt"

        rc = _run_check_artifact_stable(lifecycle_root, feature, input_file)

        # Sentinel absent -> genuine sentinel_absence verdict (exit 3).
        assert rc == 3
        events_log = feature_dir / "events.log"
        assert events_log.exists()
        rows = _read_jsonl(events_log)
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_absence"
        assert rows[0]["feature"] == feature
        assert rows[0]["reason"] == "absent"

    def test_record_exclusion_dir_exists_records_and_returns_0(
        self, tmp_path: Path
    ) -> None:
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        feature = "real-feature"
        feature_dir = lifecycle_root / feature
        feature_dir.mkdir(parents=True)

        rc = _run_record_exclusion(lifecycle_root, feature)

        assert rc == 0
        events_log = feature_dir / "events.log"
        assert events_log.exists()
        rows = _read_jsonl(events_log)
        assert len(rows) == 1
        assert rows[0]["event"] == "sentinel_absence"
        assert rows[0]["feature"] == feature


# ===========================================================================
# (c) Req 2(a)/(b) — exit 4 distinct from both 3 and 0
# ===========================================================================


class TestSkipExitCodeDistinctness:
    """The dir-absent skip exit (4) is observably distinct from the genuine
    invalidation exit (3) and from the successful-record / clean exit (0).
    """

    def test_skip_exit_is_distinct_constant(self) -> None:
        """EXIT_TELEMETRY_SKIPPED is a single constant distinct from 0, 2, 3."""
        assert EXIT_TELEMETRY_SKIPPED == 4
        assert EXIT_TELEMETRY_SKIPPED not in (0, 2, 3)

    def test_check_synth_stable_skip_distinct_from_invalidation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same sentinel-free input: dir-absent -> 4, dir-present -> 3.

        The orchestrator (which routes on exit code) can tell "skipped: no
        lifecycle dir" from "invalidated: drift detected" (Req 2a).
        """
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "feat"

        # Dir absent -> skip.
        rc_absent = _run_check_synth_stable(monkeypatch, lifecycle_root, feature)
        assert rc_absent == EXIT_TELEMETRY_SKIPPED

        # Same invocation after the dir exists -> genuine invalidation.
        (lifecycle_root / feature).mkdir()
        rc_present = _run_check_synth_stable(monkeypatch, lifecycle_root, feature)
        assert rc_present == 3
        assert rc_absent != rc_present

    def test_record_exclusion_skip_distinct_from_recorded(
        self, tmp_path: Path
    ) -> None:
        """Same record-exclusion call: dir-absent -> 4, dir-present -> 0.

        A skipped record (4) MUST NOT signal that an exclusion was persisted
        (0) when it was not (Req 2b).
        """
        lifecycle_root = tmp_path / "cortex" / "lifecycle"
        lifecycle_root.mkdir(parents=True)
        feature = "feat"

        # Dir absent -> skip, no persistence.
        rc_absent = _run_record_exclusion(lifecycle_root, feature)
        assert rc_absent == EXIT_TELEMETRY_SKIPPED
        assert not (lifecycle_root / feature).exists()

        # Same invocation after the dir exists -> genuine recorded exclusion.
        (lifecycle_root / feature).mkdir()
        rc_present = _run_record_exclusion(lifecycle_root, feature)
        assert rc_present == 0
        assert (lifecycle_root / feature / "events.log").exists()
        assert rc_absent != rc_present
