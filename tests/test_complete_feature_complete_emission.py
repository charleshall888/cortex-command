"""Round-trip field-set + real-consumer test for the migrated ``feature_complete`` row (#331 Phase 3, Reqs 16/17).

Phase 3 of #331 migrated ``complete.md`` Step 11's ``feature_complete`` emission
from a raw-JSON literal to the ``cortex-lifecycle-event log`` verb (shipped by
#330)::

    cortex-lifecycle-event log --event feature_complete --feature {slug} \
        --set-json tasks_total={N} --set-json rework_cycles={N} \
        --set merge_anchor=merge

The verb emits the ADR-0020 canonical row shape (spaced ``json.dumps``, ``…Z``
second-precision ts, NO auto ``schema_version``). This test pins:

(1) **Field-set + values invariant** (Req 17): the migrated row's parsed object
    has the exact key-set ``{ts, event, feature, tasks_total, rework_cycles,
    merge_anchor}``, with ``tasks_total``/``rework_cycles`` ints,
    ``merge_anchor == "merge"``, and NO ``schema_version``/``worktree_path``.

(2) **Real-consumer classification** (Req 17): the same emitted row flows through
    the *actual* downstream consumers without regression —
    - ``detect_lifecycle_phase`` routes it to ``complete``;
    - ``extract_feature_metrics`` carries ``merge_anchor == "merge"`` through and
      reads ``feature``/``ts`` (both hard-indexed via unguarded ``[]``) without
      KeyError;
    - ``compute_aggregates`` / ``avg_phase_durations_by_anchor`` buckets a
      ``"merge"``-anchored feature under the interactive anchor (regime
      partition).

(3) **``pr_opened`` ADR-0020 exemption regression guard**: ``pr_opened`` is NOT
    migrated to the uniform ``cortex-lifecycle-event`` machinery — it stays a
    hand-constructed dict literal, now inside
    ``cortex_command.lifecycle.record_pr_opened`` (the verb that composes
    complete.md's former Steps 4+5), so this asserts the literal still
    carries ``schema_version`` before ``feature``.

Emission is driven in-process via ``cortex_command.lifecycle_event._run`` (the
``test_lifecycle_event.py`` idiom) — NOT the bare PATH binstub, which may resolve
a stale pre-#330 wheel lacking ``--set``/``--set-json``. The ts is frozen by
monkeypatching the verb's ``_now_iso`` time source so the round-trip is
deterministic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cortex_command.common import detect_lifecycle_phase
from cortex_command.lifecycle_event import _run
from cortex_command.pipeline.metrics import (
    compute_aggregates,
    extract_feature_metrics,
)

# Repo root: tests/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]

SLUG = "offload-completemd-pr-state-routing-and"
FROZEN_TS = "2026-01-01T00:00:00Z"

# The exact key-set the migrated ``feature_complete`` (merge form) row carries
# per Req 17 / Proposed ADR 0017.
EXPECTED_KEY_SET = {
    "ts",
    "event",
    "feature",
    "tasks_total",
    "rework_cycles",
    "merge_anchor",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_feature_complete(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tasks_total: int = 3,
    rework_cycles: int = 1,
) -> dict:
    """Drive the verb to emit one ``feature_complete`` row and return it parsed.

    Replicates the production invocation from ``complete.md`` Step 11:
    ``--set-json`` for the two int counts, ``--set`` for the literal
    ``merge_anchor=merge``. The ts is frozen so the round-trip is deterministic.
    """
    (root / "cortex" / "lifecycle").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)
    # Freeze the verb's time source for a deterministic ts round-trip.
    monkeypatch.setattr(
        "cortex_command.lifecycle_event._now_iso", lambda: FROZEN_TS
    )

    rc = _run([
        "log",
        "--event", "feature_complete",
        "--feature", SLUG,
        "--set-json", f"tasks_total={tasks_total}",
        "--set-json", f"rework_cycles={rework_cycles}",
        "--set", "merge_anchor=merge",
    ])
    assert rc == 0, "verb exited non-zero"

    log_path = root / "cortex" / "lifecycle" / SLUG / "events.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"expected 1 row, got {len(lines)}: {lines!r}"
    return json.loads(lines[0])


# ---------------------------------------------------------------------------
# (1) Field-set + values invariant (Req 16, 17)
# ---------------------------------------------------------------------------


class TestFeatureCompleteRoundTrip:
    """The migrated ``feature_complete`` row preserves field-set + values."""

    def test_exact_key_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The parsed row has EXACTLY the merge-form key-set — nothing more."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert set(row.keys()) == EXPECTED_KEY_SET, (
            f"key-set drift: extra={set(row.keys()) - EXPECTED_KEY_SET}, "
            f"missing={EXPECTED_KEY_SET - set(row.keys())}"
        )

    def test_no_schema_version_no_worktree_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The migrated row carries no ``schema_version`` and no ``worktree_path``."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert "schema_version" not in row
        assert "worktree_path" not in row

    def test_base_field_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``event``/``feature`` carry their expected literal values."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert row["event"] == "feature_complete"
        assert row["feature"] == SLUG

    def test_counts_are_ints(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``tasks_total``/``rework_cycles`` are JSON ints (not strings/bools)."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert row["tasks_total"] == 3
        assert isinstance(row["tasks_total"], int)
        assert not isinstance(row["tasks_total"], bool)
        assert row["rework_cycles"] == 1
        assert isinstance(row["rework_cycles"], int)
        assert not isinstance(row["rework_cycles"], bool)

    def test_rework_cycles_zero_stays_int(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The simple-tier ``rework_cycles=0`` case stays a JSON int 0."""
        row = _emit_feature_complete(tmp_path, monkeypatch, rework_cycles=0)
        assert row["rework_cycles"] == 0
        assert isinstance(row["rework_cycles"], int)

    def test_merge_anchor_is_merge_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``merge_anchor`` is the literal string ``"merge"`` (the interactive regime)."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert row["merge_anchor"] == "merge"
        assert isinstance(row["merge_anchor"], str)

    def test_ts_is_frozen_second_precision_z(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``ts`` is the frozen value and matches ``%Y-%m-%dT%H:%M:%SZ``."""
        row = _emit_feature_complete(tmp_path, monkeypatch)
        assert row["ts"] == FROZEN_TS
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", row["ts"]), row["ts"]


# ---------------------------------------------------------------------------
# (2) Real-consumer classification (Req 17)
# ---------------------------------------------------------------------------


class TestRealConsumerClassification:
    """The migrated row flows through the actual downstream consumers."""

    def test_detect_lifecycle_phase_routes_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``detect_lifecycle_phase`` routes a dir holding the migrated row to ``complete``.

        The verb wrote ``events.log`` to disk; feed that real feature dir to the
        on-disk consumer (the ``"feature_complete"`` substring check in
        ``common.py``).
        """
        _emit_feature_complete(tmp_path, monkeypatch)
        feature_dir = tmp_path / "cortex" / "lifecycle" / SLUG
        result = detect_lifecycle_phase(feature_dir)
        assert result["route"] == "complete", result

    def test_extract_feature_metrics_carries_merge_anchor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``extract_feature_metrics`` carries ``merge_anchor`` and reads ``feature``/``ts``.

        Feeding only the single migrated row exercises the hard-indexed
        ``feature``/``ts`` reads (unguarded ``[]`` in ``metrics.py``) — absence
        would KeyError. ``merge_anchor`` must survive as ``"merge"``, and the int
        counts must carry through to ``task_count``/``rework_cycles``.
        """
        row = _emit_feature_complete(tmp_path, monkeypatch)

        # No KeyError here proves feature/ts are present and indexable.
        metrics = extract_feature_metrics([row])
        assert metrics is not None, "feature_complete row not recognized as complete"
        assert metrics["merge_anchor"] == "merge"
        assert metrics["feature"] == SLUG
        assert metrics["task_count"] == 3
        assert metrics["rework_cycles"] == 1

    def test_compute_aggregates_buckets_under_merge_anchor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ``"merge"``-anchored feature buckets under the interactive anchor.

        ``avg_phase_durations_by_anchor`` partitions per-feature durations by
        ``merge_anchor`` so the legacy overnight regime (``"review"``) and the
        interactive regime (``"merge"``) do not corrupt each other's calibration.
        A merge-anchored feature must land in the ``"merge"`` bucket, NOT the
        legacy ``"review"`` default.

        ``compute_aggregates`` excludes ``tier is None`` features, so a synthetic
        ``lifecycle_start`` (tier=complex) seeds a groupable tier; the migrated
        ``feature_complete`` row supplies the ``merge_anchor`` under test.
        """
        row = _emit_feature_complete(tmp_path, monkeypatch)

        lifecycle_start = {
            "ts": FROZEN_TS,
            "event": "lifecycle_start",
            "feature": SLUG,
            "tier": "complex",
        }
        metrics = extract_feature_metrics([lifecycle_start, row])
        assert metrics is not None
        assert metrics["tier"] == "complex"
        assert metrics["merge_anchor"] == "merge"

        aggregates = compute_aggregates([metrics])
        assert "complex" in aggregates, aggregates
        by_anchor = aggregates["complex"]["avg_phase_durations_by_anchor"]
        assert "merge" in by_anchor, by_anchor
        assert "review" not in by_anchor, (
            f"merge-anchored feature leaked into the legacy review bucket: {by_anchor}"
        )


# ---------------------------------------------------------------------------
# (3) pr_opened ADR-0020 exemption regression guard
# ---------------------------------------------------------------------------


RECORD_PR_OPENED_PY = (
    REPO_ROOT / "cortex_command" / "lifecycle" / "record_pr_opened.py"
)


class TestPrOpenedStaysHandWritten:
    """``pr_opened`` is NOT migrated to ``cortex-lifecycle-event``; it stays a
    hand-constructed dict literal and must keep its ``schema_version`` key.

    ``pr_opened``'s write moved out of complete.md Step 5's raw-JSON literal
    and into ``cortex_command.lifecycle.record_pr_opened`` (the verb that
    composes complete.md's former Steps 4+5 — see that module's docstring).
    It is still a hand-authored dict, not routed through ``log_event``'s
    uniform ``{ts, event, feature, ...}`` shape, so the exempt schema
    (``schema_version`` before ``feature``) must survive the move.
    """

    def test_pr_opened_literal_retains_schema_version_before_feature(self) -> None:
        """The hand-written ``pr_opened`` row literal still carries
        ``schema_version`` before ``feature``.

        A future migration that dropped ``schema_version`` or routed
        ``pr_opened`` through ``log_event``'s field order would regress the
        ``statusline.sh``/``scan_lifecycle`` consumers; this guard catches it.
        The end-to-end emitted-row shape (actual key order via
        ``json.dumps``) is exercised by
        ``cortex_command/lifecycle/tests/test_record_pr_opened.py::
        test_pr_opened_event_schema_is_exempt_shape``; this is the
        source-level companion.
        """
        source = RECORD_PR_OPENED_PY.read_text(encoding="utf-8")
        assert '"event": "pr_opened"' in source, (
            "pr_opened row literal not found in "
            "cortex_command/lifecycle/record_pr_opened.py — either it was "
            "migrated (ADR-0020 exemption broken) or moved"
        )
        assert '"schema_version": 1' in source, (
            "pr_opened row literal lost its schema_version key in "
            "cortex_command/lifecycle/record_pr_opened.py"
        )
        sv_idx = source.index('"schema_version": 1')
        feature_idx = source.index('"feature": feature', sv_idx)
        assert sv_idx < feature_idx, (
            "schema_version must precede feature in the pr_opened row literal"
        )
