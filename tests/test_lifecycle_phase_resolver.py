#!/usr/bin/env python3
"""Tests for the events-first shared lifecycle-phase resolver (spec R15 / ADR-0025).

`common.resolve_lifecycle_phase` is the single place the read path decides
"events-first, else artifacts": events.log is authoritative wherever a machine
row (a `phase_transition` or terminal event) exists, and
`detect_lifecycle_phase`'s artifact-presence derivation is the legacy fallback
reached only when no machine row is present.

These tests cover the three derivation cases the spec's acceptance names:

  (a) machine-rows -> event-derived   (events win over the artifact tree)
  (b) legacy       -> artifact-derived (no machine row -> byte-identical fallback)
  (c) divergence   -> detector-reports (the REAL `_is_terminal_mismatch` fires on
                      the resolver's events-first output vs a terminal backlog)

plus a drift tripwire keeping the resolver's machine-state set pinned to the
transition table (`STATE_NAMES`).
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command import common
from cortex_command.common import detect_lifecycle_phase, resolve_lifecycle_phase
from cortex_command.hooks.scan_lifecycle import _encode_phase, _is_terminal_mismatch
from cortex_command.lifecycle import transition_table as tt


def _write_events(feature_dir: Path, rows: list[dict]) -> None:
    feature_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in rows]
    (feature_dir / "events.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_plan(feature_dir: Path, checked: int, total: int) -> None:
    """Write a plan.md whose Status checkboxes encode `checked`/`total`."""
    feature_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(total):
        box = "x" if i < checked else " "
        lines.append(f"### Task {i + 1}: t{i + 1}\n- **Status**: [{box}]\n")
    (feature_dir / "plan.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) machine-rows -> event-derived
# ---------------------------------------------------------------------------


def test_resolver_events_win_over_artifacts(tmp_path: Path) -> None:
    """Machine rows present: the events-derived state supersedes the artifact route.

    Artifacts alone (spec.md, unapproved) would derive "specify"; the log's
    phase_transition rows drive the machine to "implement", and the resolver
    serves the events-derived state.
    """
    fd = tmp_path / "feat"
    fd.mkdir()
    (fd / "spec.md").write_text("spec", encoding="utf-8")
    _write_plan(fd, checked=1, total=3)
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "spec_approved", "feature": "feat"},
            {"ts": "2026-01-01T00:00:02Z", "event": "plan_approved", "feature": "feat"},
            {
                "ts": "2026-01-01T00:00:03Z",
                "event": "phase_transition",
                "from": "plan",
                "to": "implement",
            },
        ],
    )

    resolved = resolve_lifecycle_phase(fd)
    assert resolved["route"] == "implement", resolved
    assert resolved["phase"] == "implement"
    # checked/total/cycle stay artifact-sourced (plan progress is not events-state).
    assert resolved["checked"] == 1
    assert resolved["total"] == 3
    assert resolved["cycle"] == 1


def test_resolver_terminal_event_derives_complete(tmp_path: Path) -> None:
    """A terminal machine row (feature_complete) derives the terminal state."""
    fd = tmp_path / "feat"
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "lifecycle_start"},
            {"ts": "2026-01-01T00:00:02Z", "event": "feature_complete"},
        ],
    )
    assert resolve_lifecycle_phase(fd)["route"] == "complete"


def test_resolver_events_paused_annotation(tmp_path: Path) -> None:
    """When the last significant event is feature_paused, the events-first path
    annotates the (non-terminal) events-derived state with -paused."""
    fd = tmp_path / "feat"
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "phase_transition", "from": "plan", "to": "implement"},
            {"ts": "2026-01-01T00:00:02Z", "event": "feature_paused", "kind": "relayed-consent"},
        ],
    )
    resolved = resolve_lifecycle_phase(fd)
    assert resolved["route"] == "implement"
    assert resolved["paused"] is True
    assert resolved["phase"] == "implement-paused"


# ---------------------------------------------------------------------------
# (b) legacy -> artifact-derived (no machine row)
# ---------------------------------------------------------------------------


def test_resolver_legacy_fallback_no_machine_rows(tmp_path: Path) -> None:
    """No phase_transition / terminal event -> the resolver returns the artifact
    derivation byte-for-byte (legacy fallback)."""
    fd = tmp_path / "feat"
    fd.mkdir()
    # Empty dir -> the artifact reader's default "research" (step 6).
    # Deliberately NO events.log -> no machine row at all.
    assert resolve_lifecycle_phase(fd) == detect_lifecycle_phase(fd)
    assert resolve_lifecycle_phase(fd)["route"] == "research"


def test_resolver_approval_only_log_is_legacy_fallback(tmp_path: Path) -> None:
    """spec_approved / plan_approved are NOT machine rows: a standalone-refine
    log with no phase_transition falls through to artifact derivation."""
    fd = tmp_path / "feat"
    fd.mkdir()
    (fd / "spec.md").write_text("s", encoding="utf-8")
    (fd / "plan.md").write_text("### Task 1: t\n- **Status**: [ ]\n", encoding="utf-8")
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "spec_approved"},
            {"ts": "2026-01-01T00:00:02Z", "event": "plan_approved"},
        ],
    )
    # No phase_transition -> resolver == detect_lifecycle_phase (both "implement",
    # gated by plan_approved).
    assert resolve_lifecycle_phase(fd) == detect_lifecycle_phase(fd)


# ---------------------------------------------------------------------------
# (c) divergence -> the REAL _is_terminal_mismatch reports it
# ---------------------------------------------------------------------------


def test_resolver_divergence_reported_by_real_detector(tmp_path: Path) -> None:
    """Hand-edited plan.md on a machine-rows feature: events win, and the real,
    permanent mismatch detector reports the events-vs-backlog divergence.

    The plan.md is hand-flipped to all-checked (artifact derivation would read
    "review"); the log's phase_transition keeps the machine at "implement". The
    resolver serves "implement" (events win), so a backlog row that was closed to
    a terminal status without finishing the lifecycle (#075-shape) is caught by
    the real `_is_terminal_mismatch`.
    """
    fd = tmp_path / "feat"
    fd.mkdir()
    (fd / "spec.md").write_text("s", encoding="utf-8")
    _write_plan(fd, checked=5, total=5)  # hand-edited: looks done
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "spec_approved"},
            {"ts": "2026-01-01T00:00:02Z", "event": "plan_approved"},
            {"ts": "2026-01-01T00:00:03Z", "event": "phase_transition", "from": "plan", "to": "implement"},
        ],
    )

    # Events win over the hand-edit: resolver says implement, artifact says review.
    resolved = resolve_lifecycle_phase(fd)
    assert resolved["route"] == "implement", resolved
    assert detect_lifecycle_phase(fd)["route"] == "review"  # the diverging artifact view

    encoded = _encode_phase(
        resolved["phase"], int(resolved["checked"]), int(resolved["total"]), int(resolved["cycle"])
    )
    # Backlog was closed to a terminal status while events say implement -> the
    # REAL detector fires (events-terminal False != backlog-terminal True).
    assert _is_terminal_mismatch(encoded, "complete") is True
    # Control: a non-terminal backlog agrees with the events phase -> no mismatch.
    assert _is_terminal_mismatch(encoded, "in_progress") is False


def test_resolver_terminal_events_vs_nonterminal_backlog_reports(tmp_path: Path) -> None:
    """Inverse divergence: events say complete, backlog still non-terminal -> the
    real detector reports it on the resolver's events-first output."""
    fd = tmp_path / "feat"
    _write_plan(fd, checked=1, total=3)  # artifact looks mid-implement
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "feature_complete"},
        ],
    )
    resolved = resolve_lifecycle_phase(fd)
    encoded = _encode_phase(
        resolved["phase"], int(resolved["checked"]), int(resolved["total"]), int(resolved["cycle"])
    )
    assert encoded == "complete"
    assert _is_terminal_mismatch(encoded, "in_progress") is True


# ---------------------------------------------------------------------------
# Drift tripwire — the resolver's machine-state set stays pinned to the table
# ---------------------------------------------------------------------------


def test_resolver_machine_state_names_match_transition_table() -> None:
    """`_MACHINE_STATE_NAMES` is a literal mirror of `transition_table.STATE_NAMES`
    (kept literal to keep `common` dependency-light); pin them equal so the table
    growing a state fails loudly here rather than silently dropping events-authority
    for that state."""
    assert common._MACHINE_STATE_NAMES == tt.STATE_NAMES


def test_resolver_ignores_unknown_transition_target(tmp_path: Path) -> None:
    """A phase_transition `to` outside the table's state set never overrides the
    artifact fallback (a malformed row must not corrupt the derivation)."""
    fd = tmp_path / "feat"
    fd.mkdir()
    (fd / "research.md").write_text("r", encoding="utf-8")
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "phase_transition", "from": "x", "to": "bogus-state"},
        ],
    )
    # Unknown `to` ignored -> no machine state -> artifact fallback (research.md
    # present -> the reader's step-5 "specify").
    assert resolve_lifecycle_phase(fd) == detect_lifecycle_phase(fd)
    assert resolve_lifecycle_phase(fd)["route"] == "specify"
