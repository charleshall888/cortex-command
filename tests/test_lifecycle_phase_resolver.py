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


def test_resolver_rework_cap_phase_is_exempt_from_the_detector(tmp_path: Path) -> None:
    """454+470: the discriminated `escalated:rework-cap:<n>` phase is held to the
    same rule as the bare `escalated` it sits beside — and that rule is *exempt*.

    #454's R3 requirement stands unchanged: the discriminant narrates, it never
    changes terminality, so both forms must answer identically. #470 corrected
    which answer. An escalated feature is stopped awaiting operator direction and
    is not done, so a ticket reading `in_progress` is correct rather than
    divergent; the old `is True` fired on every SessionStart with no operator
    action that could clear it. Both forms now answer False, in both directions.
    """
    fd = tmp_path / "feat"
    # Cycle comes from the events.log review_verdict row count; review.md
    # supplies the verdict. Two rows + CHANGES_REQUESTED = the rework cap.
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1},
            {"ts": "2026-01-01T00:00:02Z", "event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 2},
        ],
    )
    (fd / "review.md").write_text('{"verdict": "CHANGES_REQUESTED", "cycle": 2}\n', encoding="utf-8")

    resolved = resolve_lifecycle_phase(fd)
    encoded = _encode_phase(
        resolved["phase"], int(resolved["checked"]), int(resolved["total"]), int(resolved["cycle"])
    )
    assert encoded == "escalated:rework-cap:2"
    assert _is_terminal_mismatch(encoded, "in_progress") is False
    # Same rule as the undiscriminated form: the discriminant changes the
    # narration, never the terminality.
    assert _is_terminal_mismatch("escalated", "in_progress") is False
    # Exempt in *both* directions — an operator who abandons an escalated
    # feature and closes its ticket is equally correct, so neither state pairing
    # is a divergence.
    assert _is_terminal_mismatch(encoded, "complete") is False
    assert _is_terminal_mismatch("escalated", "complete") is False


def test_cancelled_lifecycle_with_a_closed_ticket_is_not_a_mismatch(tmp_path: Path) -> None:
    """470: `cancelled` is terminal and pins `abandoned` as its expected ticket
    status, so the two agreeing must not read as divergence.

    Before the fix `cancelled` was absent from the detector's terminal set while
    present in `common._EVENTS_TERMINAL_STATES`, inverting the bug: a correctly
    cancelled lifecycle whose ticket was correctly closed reported a mismatch,
    and the only way to clear it was to reopen the ticket.
    """
    fd = tmp_path / "feat"
    _write_events(
        fd,
        [
            {"ts": "2026-01-01T00:00:01Z", "event": "lifecycle_cancelled"},
        ],
    )
    resolved = resolve_lifecycle_phase(fd)
    encoded = _encode_phase(
        resolved["phase"], int(resolved["checked"]), int(resolved["total"]), int(resolved["cycle"])
    )
    assert encoded == "cancelled"
    assert _is_terminal_mismatch(encoded, "abandoned") is False
    assert _is_terminal_mismatch(encoded, "wont-do") is False
    # Still actionable in the one direction that has an action: the lifecycle is
    # abandoned but the ticket claims someone is on it. Closing it clears this.
    assert _is_terminal_mismatch(encoded, "in_progress") is True


def test_stale_complete_still_reports_after_the_escalated_exemption(tmp_path: Path) -> None:
    """470 guard: exempting `escalated` must not cost the #075-shape.

    The detector's original purpose — events say the feature finished, the ticket
    still says it is being worked — is the case that must survive every narrowing
    of the terminal set.
    """
    fd = tmp_path / "feat"
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
    assert _is_terminal_mismatch(encoded, "in_progress") is True
    assert _is_terminal_mismatch("complete:awaiting-merge", "in_progress") is True
    # And the inverse #075 direction: mid-implement events, closed ticket.
    assert _is_terminal_mismatch("implement", "complete") is True


# ---------------------------------------------------------------------------
# Drift tripwire — the resolver's machine-state set stays pinned to the table
# ---------------------------------------------------------------------------


def test_resolver_machine_state_names_match_transition_table() -> None:
    """`_MACHINE_STATE_NAMES` is a literal mirror of `transition_table.STATE_NAMES`
    (kept literal to keep `common` dependency-light); pin them equal so the table
    growing a state fails loudly here rather than silently dropping events-authority
    for that state."""
    assert common._MACHINE_STATE_NAMES == tt.STATE_NAMES


def test_resolver_terminal_event_map_key_set_is_pinned() -> None:
    """`_TERMINAL_EVENT_TO_STATE`'s key set is the terminal-event vocabulary, pinned
    as a golden literal.

    Every current key already has behavioural coverage elsewhere (`feature_wontfix`
    via the #210 parity tests, the other two via this module and `test_complete_route`),
    so what this pin adds is structural: growing the dict a fourth key wires a new
    event straight into events-authority, and no behavioural test can fail for a
    branch nothing exercises yet. Editing this literal is the intended cost of
    adding a terminal event.
    """
    assert set(common._TERMINAL_EVENT_TO_STATE) == {
        "feature_complete",
        "feature_wontfix",
        "lifecycle_cancelled",
    }


def test_resolver_terminal_event_map_values_are_terminal_machine_states() -> None:
    """Every state a terminal event pins must be both servable and terminal.

    Two invariants the key-set pin above cannot catch, since repointing an existing
    key leaves the key set intact:

    - value in `_MACHINE_STATE_NAMES` — a state the resolver cannot serve would be
      dropped by the same guard that ignores a malformed `phase_transition` target,
      silently demoting the event to the artifact fallback;
    - value in `_EVENTS_TERMINAL_STATES` — a terminal event pinning a non-terminal
      state would take the `-paused` annotation path, narrating a finished feature
      as paused.
    """
    values = set(common._TERMINAL_EVENT_TO_STATE.values())
    assert values <= common._MACHINE_STATE_NAMES
    assert values <= common._EVENTS_TERMINAL_STATES


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
