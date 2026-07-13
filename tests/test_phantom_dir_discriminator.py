"""Discriminator tests for ``is_phantom_lifecycle_dir`` (spec Reqs 5, 6, 7).

The predicate (``cortex_command/common.py``) classifies a lifecycle dir as a
telemetry-only phantom iff it has no ``research.md``/``spec.md``/``plan.md`` AND
its JSONL-parsed ``event``-type set is non-empty and a subset of
``{synthesizer_drift, sentinel_absence}``. The empty/absent/unparseable case is
deliberately out of scope (owned by ``scan_lifecycle._is_stale``), so these
tests do not assert anything about an empty events.log.

Fixtures are built under ``tmp_path`` and encode synthetic JSONL with a recent
``ts`` rather than reading live archive paths. The ``synthesizer_drift`` and
``sentinel_absence`` shapes mirror the live events
(``cortex/lifecycle/.../events.log`` and the doc-audit archive) but use a recent
timestamp so they model a live phantom at birth, not the now-``feature_wontfix``
capped archived content.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from cortex_command.common import is_phantom_lifecycle_dir


def _recent_ts() -> str:
    """Return an ISO-8601 ``Z``-suffixed timestamp from one hour ago.

    Recent enough that ``_is_stale`` would pass the dir through to the
    phantom predicate (the gap this discriminator closes).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    one_hour_ago = now - datetime.timedelta(hours=1)
    return one_hour_ago.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_events(feature_dir: Path, events: list[dict]) -> None:
    """Write a JSONL events.log (one ``json.dumps`` per line) into the dir."""
    feature_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(event) for event in events]
    (feature_dir / "events.log").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _synthesizer_drift_event(feature: str) -> dict:
    """A ``synthesizer_drift`` event with a recent ts (birth signature)."""
    return {
        "ts": _recent_ts(),
        "event": "synthesizer_drift",
        "feature": feature,
        "expected_sha": "a" * 64,
        "observed_sha_or_null": None,
    }


def _sentinel_absence_event(feature: str, angle: str) -> dict:
    """A ``sentinel_absence`` event with a recent ts (birth signature)."""
    return {
        "ts": _recent_ts(),
        "event": "sentinel_absence",
        "feature": feature,
        "reviewer_angle": angle,
        "reason": "absent",
        "model_tier": "sonnet",
        "expected_sha": "b" * 64,
        "observed_sha_or_null": None,
    }


def _sentinel_advisory_event(feature: str, angle: str) -> dict:
    """A ``sentinel_advisory`` event with a recent ts (birth signature).

    Advisory-clean: the read-sentinel was absent but the gate wrapper's
    re-hash of the pinned artifact matched (stable), so the gate passes with an
    advisory rather than a hard-fail ``sentinel_absence``. Carries the existing
    reviewer-angle/role fields; the matched re-hash means ``observed`` equals
    ``expected``.
    """
    return {
        "ts": _recent_ts(),
        "event": "sentinel_advisory",
        "feature": feature,
        "reviewer_angle": angle,
        "reason": "absent_rehash_stable",
        "model_tier": "sonnet",
        "expected_sha": "c" * 64,
        "observed_sha_or_null": "c" * 64,
    }


# ---------------------------------------------------------------------------
# (a) Birth signatures of live phantoms ARE classified as phantoms.
# ---------------------------------------------------------------------------


def test_lone_synthesizer_drift_is_phantom(tmp_path: Path):
    """A lone recent-ts ``synthesizer_drift`` event, no artifacts -> phantom."""
    feature = "doc-audit-phantom"
    feature_dir = tmp_path / feature
    _write_events(feature_dir, [_synthesizer_drift_event(feature)])

    assert is_phantom_lifecycle_dir(feature_dir) is True


def test_three_sentinel_absence_is_phantom(tmp_path: Path):
    """Three recent-ts ``sentinel_absence`` events, no artifacts -> phantom."""
    feature = "sentinel-absence-phantom"
    feature_dir = tmp_path / feature
    _write_events(
        feature_dir,
        [
            _sentinel_absence_event(feature, "Phase dependency graph"),
            _sentinel_absence_event(feature, "Helper vs parameter callers"),
            _sentinel_absence_event(feature, "Phase dependency graph"),
        ],
    )

    assert is_phantom_lifecycle_dir(feature_dir) is True


def test_lone_sentinel_advisory_is_phantom(tmp_path: Path):
    """A lone recent-ts ``sentinel_advisory`` event, no artifacts -> phantom.

    The advisory-clean gate outcome is a critical-review telemetry writer that
    can create a lifecycle-shaped dir, so ``sentinel_advisory`` is in
    ``_TELEMETRY_ONLY_EVENT_TYPES`` and a dir whose only events are advisory
    must still classify as a phantom (not a real research-phase lifecycle).
    """
    feature = "sentinel-advisory-phantom"
    feature_dir = tmp_path / feature
    _write_events(
        feature_dir,
        [_sentinel_advisory_event(feature, "Phase dependency graph")],
    )

    assert is_phantom_lifecycle_dir(feature_dir) is True


# ---------------------------------------------------------------------------
# (b) A freshly-started legitimate lifecycle is NOT a phantom (still surfaced).
# ---------------------------------------------------------------------------


def test_fresh_legitimate_lifecycle_not_phantom(tmp_path: Path):
    """``lifecycle_start``/``clarify_critic`` JSONL, no artifacts yet -> NOT phantom.

    This is the Req 6/7 false-positive guard: an artifact-less but
    legitimately-started lifecycle must still be surfaced so the operator can
    resume it. Its JSONL event-set is not a telemetry subset.
    """
    feature = "fresh-legit-lifecycle"
    feature_dir = tmp_path / feature
    _write_events(
        feature_dir,
        [
            {
                "schema_version": 1,
                "ts": _recent_ts(),
                "event": "lifecycle_start",
                "feature": feature,
                "tier": "complex",
                "criticality": "high",
                "entry_point": "refine",
            },
            {
                "schema_version": 3,
                "ts": _recent_ts(),
                "event": "clarify_critic",
                "feature": feature,
                "parent_epic_loaded": True,
                "findings_count": 5,
                "status": "ok",
            },
        ],
    )

    assert is_phantom_lifecycle_dir(feature_dir) is False


# ---------------------------------------------------------------------------
# (c) A real dir lacking lifecycle_start but with other non-telemetry events
#     is NOT classified (the "has lifecycle_start" discriminator was refuted).
# ---------------------------------------------------------------------------


def test_real_dir_without_lifecycle_start_not_phantom(tmp_path: Path):
    """No ``lifecycle_start`` but a non-telemetry event present -> NOT phantom.

    Spec Req 7: ~16% of real dirs lack ``lifecycle_start``; the predicate must
    not key on its presence. A ``clarify_critic`` event alone (no artifacts) is
    outside the telemetry allow-set, so the dir is not a phantom.
    """
    feature = "real-no-lifecycle-start"
    feature_dir = tmp_path / feature
    _write_events(
        feature_dir,
        [
            {
                "schema_version": 3,
                "ts": _recent_ts(),
                "event": "clarify_critic",
                "feature": feature,
                "parent_epic_loaded": False,
                "findings_count": 6,
                "status": "ok",
            },
        ],
    )

    assert is_phantom_lifecycle_dir(feature_dir) is False


# ---------------------------------------------------------------------------
# (d) A hybrid YAML-block + JSONL events.log with non-telemetry JSONL events
#     is NOT classified (its JSONL set is not a telemetry subset).
# ---------------------------------------------------------------------------


def test_hybrid_yaml_block_plus_jsonl_not_phantom(tmp_path: Path):
    """Hybrid multi-line YAML block + non-telemetry JSONL lines -> NOT phantom.

    The predicate reads events.log as JSONL (one ``json.loads`` per line,
    skipping unparseable lines). The multi-line YAML block lines fail to parse
    and are skipped; the surviving JSONL ``review_verdict`` event is outside the
    telemetry allow-set, so the JSONL set is not a telemetry subset.
    """
    feature = "hybrid-yaml-jsonl"
    feature_dir = tmp_path / feature
    feature_dir.mkdir(parents=True, exist_ok=True)

    yaml_block = (
        "- event: legacy_record\n"
        "  ts: 2026-05-01T00:00:00Z\n"
        "  note: |\n"
        "    a multi-line YAML block record that predates JSONL\n"
    )
    jsonl_line = json.dumps(
        {
            "ts": _recent_ts(),
            "event": "review_verdict",
            "feature": feature,
            "verdict": "CHANGES_REQUESTED",
        }
    )
    (feature_dir / "events.log").write_text(
        yaml_block + jsonl_line + "\n", encoding="utf-8"
    )

    assert is_phantom_lifecycle_dir(feature_dir) is False


# ---------------------------------------------------------------------------
# Supporting guards: artifact presence defeats classification.
# ---------------------------------------------------------------------------


def test_telemetry_only_with_artifact_not_phantom(tmp_path: Path):
    """Telemetry-only events.log but a real ``research.md`` present -> NOT phantom."""
    feature = "telemetry-with-artifact"
    feature_dir = tmp_path / feature
    _write_events(feature_dir, [_synthesizer_drift_event(feature)])
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")

    assert is_phantom_lifecycle_dir(feature_dir) is False
