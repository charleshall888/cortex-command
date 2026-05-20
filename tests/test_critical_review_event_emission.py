"""Event-emission tests for ``cortex_command.critical_review`` (Req 7).

Covers the Requirement 7 field-additive extension of the
``sentinel_absence`` event with the optional ``source_path`` and
``snapshot_sha`` fields when the artifact was ad-hoc-snapshotted.

Two scenarios:

1. ``test_source_path_field_round_trip`` — a snapshotted ad-hoc input
   produces an ``events.log`` row whose JSON payload contains the
   original candidate path under ``source_path`` and the snapshot's full
   hex SHA-256 under ``snapshot_sha``. The fields flow from
   ``validate_artifact_path(..., allow_adhoc=True)`` through
   ``_build_sentinel_absence_event`` onto the dict and through
   ``append_event``'s ``json.dumps`` write.

2. ``test_newline_path_round_trips_through_json_escape`` — a candidate
   path containing a newline character passes ``validate_artifact_path``
   (POSIX permits any byte but NUL in a path), is preserved verbatim in
   ``source_path``, and JSON-round-trips through the events.log line.
   The raw bytes of the events.log row contain the JSON-escaped form
   (the literal two-character sequence ``\\n``); ``json.loads`` of the
   row recovers the original newline-containing string.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cortex_command.critical_review import (
    _build_sentinel_absence_event,
    append_event,
    validate_artifact_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scaffold_roots(tmp_path: Path) -> tuple[Path, Path]:
    """Build ``cortex/{lifecycle,research}/`` under ``tmp_path`` and return them.

    The ad-hoc snapshot landing dir ``cortex/_adhoc/`` is derived from the
    lifecycle root's ``.parent.parent``, so the scaffold guarantees the
    snapshot has a place to land.
    """
    lifecycle_root = tmp_path / "cortex" / "lifecycle"
    lifecycle_root.mkdir(parents=True)
    research_root = tmp_path / "cortex" / "research"
    research_root.mkdir(parents=True)
    return lifecycle_root, research_root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_source_path_field_round_trip(tmp_path: Path) -> None:
    """Req 7: snapshotted ad-hoc input produces an events.log row whose
    JSON payload carries the original path under ``source_path`` and the
    snapshot SHA under ``snapshot_sha``.
    """
    lifecycle_root, research_root = _scaffold_roots(tmp_path)
    feature = "test-feature"
    feature_dir = lifecycle_root / feature
    feature_dir.mkdir()

    # Build an ad-hoc input file outside both roots.
    outside = tmp_path / "outside.md"
    outside.write_text("ad-hoc input content\n", encoding="utf-8")
    expected_sha = hashlib.sha256(outside.read_bytes()).hexdigest()

    roots = [str(lifecycle_root), str(research_root)]
    result = validate_artifact_path(str(outside), roots, allow_adhoc=True)

    # Sanity: validation returned the extended ad-hoc shape.
    assert isinstance(result, dict)
    assert result["source_path"] == str(outside)
    assert result["snapshot_sha"] == expected_sha

    # Build the sentinel_absence event with the threaded fields and
    # append to events.log through the canonical writer.
    event = _build_sentinel_absence_event(
        feature=feature,
        reviewer_angle="code-quality",
        reason="absent",
        model_tier="sonnet",
        expected_sha=expected_sha,
        observed_sha=None,
        source_path=result["source_path"],
        snapshot_sha=result["snapshot_sha"],
    )
    events_log = feature_dir / "events.log"
    append_event(events_log, event)

    # The JSON row carries both new fields with the expected values.
    lines = events_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "sentinel_absence"
    assert payload["source_path"] == str(outside)
    assert payload["snapshot_sha"] == expected_sha
    # Base schema fields still present.
    assert payload["feature"] == feature
    assert payload["reviewer_angle"] == "code-quality"
    assert payload["reason"] == "absent"
    assert payload["model_tier"] == "sonnet"
    assert payload["expected_sha"] == expected_sha
    assert payload["observed_sha_or_null"] is None


def test_newline_path_round_trips_through_json_escape(tmp_path: Path) -> None:
    """Req 7 / Edge Case: a newline-containing candidate path passes
    validation, is preserved verbatim in ``source_path``, and the raw
    events.log row contains the JSON-escaped form ``\\n`` (two literal
    characters: backslash + ``n``). ``json.loads`` of the row recovers
    the original newline-containing string.
    """
    lifecycle_root, research_root = _scaffold_roots(tmp_path)
    feature = "newline-feature"
    feature_dir = lifecycle_root / feature
    feature_dir.mkdir()

    # POSIX permits any byte but NUL in a path; build a real file at a
    # path that contains a newline.
    newline_dir = tmp_path / "weird\nname"
    newline_dir.mkdir()
    src = newline_dir / "input.md"
    src.write_text("newline-in-path content\n", encoding="utf-8")
    expected_sha = hashlib.sha256(src.read_bytes()).hexdigest()

    roots = [str(lifecycle_root), str(research_root)]
    result = validate_artifact_path(str(src), roots, allow_adhoc=True)

    # Validation accepted the newline path and preserved it verbatim.
    assert isinstance(result, dict)
    assert "\n" in result["source_path"]
    assert result["source_path"] == str(src)
    assert result["snapshot_sha"] == expected_sha

    # Build the event and write it through append_event.
    event = _build_sentinel_absence_event(
        feature=feature,
        reviewer_angle="security",
        reason="absent",
        model_tier="opus",
        expected_sha=expected_sha,
        observed_sha=None,
        source_path=result["source_path"],
        snapshot_sha=result["snapshot_sha"],
    )
    events_log = feature_dir / "events.log"
    append_event(events_log, event)

    # The raw bytes of the events.log row contain the JSON-escaped
    # two-character sequence ``\n`` (backslash + literal 'n'), NOT a
    # real newline byte in the middle of the row. The row is exactly
    # one line + trailing newline.
    raw_bytes = events_log.read_bytes()
    assert raw_bytes.endswith(b"\n")
    # Strip the trailing line-terminator newline only; any newline byte
    # in the payload would have been JSON-escaped to ``\n``.
    payload_bytes = raw_bytes[:-1]
    # The events.log row is a single JSON line — no embedded newlines.
    assert b"\n" not in payload_bytes, (
        "Expected the embedded newline in source_path to be JSON-escaped "
        "to the two-character sequence \\n; found a raw newline byte "
        "inside the events.log row, which would corrupt JSONL parsing."
    )
    # The JSON-escaped form is the literal two-byte sequence b"\\n"
    # (backslash + 'n').
    assert b"\\n" in payload_bytes, (
        "Expected the JSON-escaped newline sequence \\\\n in the raw "
        "events.log bytes."
    )

    # json.loads of the row recovers the original newline-containing
    # string under source_path.
    payload = json.loads(payload_bytes.decode("utf-8"))
    assert payload["source_path"] == str(src)
    assert "\n" in payload["source_path"]
    assert payload["snapshot_sha"] == expected_sha
