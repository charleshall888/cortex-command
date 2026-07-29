"""Tests for cortex-morning-review-advance-lifecycle — the morning-review
walkthrough §2b per-feature lifecycle-advancement façade (checkbox counting,
the tier/criticality review gate, and the transition emission).

``advance_lifecycle()`` reads real events.log/plan.md files under a tmp
project root and calls the real ``log_event`` writer (also against that tmp
root, via ``LIFECYCLE_SESSION_ID``-independent CWD resolution) — so these
tests chdir into the tmp root rather than monkeypatching ``log_event``,
since ``log_event`` resolves its own path internally with no override hook.
Assertions read back the appended rows from the real events.log, following
the ``test_prepare_worktree.py`` precedent of pinning the discriminated
``state`` + payload for every branch.

**Fixtures carry ``phase_transition`` rows.** They did not until #421, and that
made a whole class of bug invisible: with no machine rows, the events-first
resolver falls back to the artifact detector, so the caller-supplied and
gate-side derivations could not disagree by construction and every advance
tautologically passed. One fixture even pinned ``from == "review"`` for a
feature that was never reviewed. A chain seeded here must be one a real run
would actually emit.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from cortex_command.common import resolve_lifecycle_phase
from cortex_command.overnight import advance_lifecycle as al


def _feature_dir(root: Path, feature: str = "feat") -> Path:
    d = root / "cortex" / "lifecycle" / feature
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_events(feature_dir: Path, lines: list[dict]) -> Path:
    path = feature_dir / "events.log"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def _read_events(feature_dir: Path) -> list[dict]:
    path = feature_dir / "events.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _short_road(feature: str = "feat", **start) -> list[dict]:
    """The machine rows a no-review (short-road) feature carries at completion.

    ``spec.approved-direct`` routes specify straight to implement, skipping plan
    — so the feature sits at ``implement`` when morning review reaches it.
    """
    rows: list[dict] = []
    if start:
        rows.append({"event": "lifecycle_start", "feature": feature, **start})
    rows += [
        {"event": "spec_approved", "feature": feature, "decision": "approved-direct"},
        {"event": "phase_transition", "feature": feature, "from": "specify", "to": "implement"},
    ]
    return rows


def _long_road(feature: str = "feat", **start) -> list[dict]:
    """The machine rows a review-required feature carries when it reaches review."""
    return [
        {"event": "lifecycle_start", "feature": feature, **start},
        {"event": "phase_transition", "feature": feature, "from": "specify", "to": "plan"},
        {"event": "plan_approved", "feature": feature, "dispatch_choice": "trunk"},
        {"event": "phase_transition", "feature": feature, "from": "plan", "to": "implement"},
        {"event": "phase_transition", "feature": feature, "from": "implement", "to": "review"},
    ]


@pytest.fixture()
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """chdir into a fresh tmp project root — log_event() resolves via CWD."""
    (tmp_path / "cortex").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_lifecycle_dir(project_root: Path) -> None:
    r = al.advance_lifecycle("ghost", project_root=project_root)
    assert r == {"state": "no-lifecycle-dir"}


def test_already_complete_skips(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(fd, [{"event": "feature_complete", "feature": "feat"}])
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r == {"state": "already-complete"}
    # Nothing new appended.
    assert len(_read_events(fd)) == 1


def test_simple_medium_advances_via_implement_exit_arm(project_root: Path) -> None:
    """A feature that never entered review exits via the implement-transition arm.

    It records ONE ``phase_transition`` implement→complete and no verdict. The
    pre-#421 path fired the review-verdict arm here, which manufactured a
    synthetic ``review_verdict{cycle: 0, APPROVED}`` for something nobody
    reviewed — a row ``_has_real_review_verdict`` already refused to believe.
    """
    fd = _feature_dir(project_root)
    _write_events(fd, _short_road(tier="simple", criticality="medium"))
    (fd / "plan.md").write_text(
        "- **Status**: [x] done\n- **Status**: [ ] todo\n- **Status**: [x] done\n"
    )
    # The gate's own oracle sees the feature at implement before the call.
    assert resolve_lifecycle_phase(fd)["phase"] == "implement"

    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"
    assert r["tasks_total"] == 3
    assert r["rework_cycles"] == 0

    events = _read_events(fd)
    new_events = events[3:]
    assert [e["event"] for e in new_events] == ["phase_transition"]
    assert new_events[0]["from"] == "implement" and new_events[0]["to"] == "complete"
    assert not any(e["event"] == "review_verdict" for e in events)
    assert not any(e["event"] == "feature_complete" for e in events)
    for e in new_events:
        assert e["feature"] == "feat"
        assert "ts" in e

    # Events-first status projection: complete.
    assert resolve_lifecycle_phase(fd)["route"] == "complete"


def test_missing_plan_defaults_tasks_total_to_zero(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    _write_events(fd, _short_road(tier="simple", criticality="low"))
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"
    assert r["tasks_total"] == 0


@pytest.mark.parametrize(
    "tier,criticality",
    [("complex", "low"), ("complex", "medium"), ("simple", "high"), ("simple", "critical")],
)
def test_review_required_tiers_gate(project_root: Path, tier: str, criticality: str) -> None:
    fd = _feature_dir(project_root)
    seed = _long_road(tier=tier, criticality=criticality)
    _write_events(fd, seed)
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "missing-review"
    assert _read_events(fd) == seed


def test_default_tier_and_criticality_when_absent(project_root: Path) -> None:
    """No lifecycle_start event at all: defaults to simple/medium -> no review required."""
    fd = _feature_dir(project_root)
    _write_events(fd, _short_road())
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"


def test_crash_recovery_appends_only_the_missing_transition(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    seed = _long_road(tier="complex", criticality="medium") + [
        {"event": "review_verdict", "feature": "feat", "verdict": "CHANGES_REQUESTED", "cycle": 1},
        {"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 2},
    ]
    _write_events(fd, seed)
    (fd / "plan.md").write_text("- **Status**: [x] done\n- **Status**: [x] done\n")
    assert resolve_lifecycle_phase(fd)["phase"] == "review"

    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-crash-recovery"
    assert r["tasks_total"] == 2
    assert r["rework_cycles"] == 1

    events = _read_events(fd)
    # The real cycle-2 review_verdict is already present, so the advance body
    # emits only the missing phase_transition review→complete (no duplicate
    # verdict) — and no feature_complete.
    new_events = events[len(seed):]
    assert [e["event"] for e in new_events] == ["phase_transition"]
    assert new_events[0]["from"] == "review" and new_events[0]["to"] == "complete"
    assert not any(e["event"] == "feature_complete" for e in events)

    assert resolve_lifecycle_phase(fd)["route"] == "complete"


def test_missing_review_writes_nothing(project_root: Path) -> None:
    fd = _feature_dir(project_root)
    seed = _long_road(tier="complex", criticality="medium")
    _write_events(fd, seed)
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r == {"state": "missing-review"}
    assert _read_events(fd) == seed


def test_synthetic_cycle_zero_does_not_count_as_real_review(project_root: Path) -> None:
    """A prior run's own synthetic cycle:0 APPROVED must not satisfy the
    'real review' check for the required-review path (regression guard for
    the cycle >= 1 boundary)."""
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        _long_road(tier="complex", criticality="medium")
        + [{"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 0}],
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "missing-review"


def test_malformed_line_is_skipped_not_fatal(project_root: Path) -> None:
    """A torn line with both gate axes still recoverable is not corruption."""
    fd = _feature_dir(project_root)
    path = fd / "events.log"
    rows = _short_road(tier="simple", criticality="medium")
    path.write_text(
        json.dumps(rows[0]) + "\n"
        + "not-json-at-all\n"
        + "".join(json.dumps(r) + "\n" for r in rows[1:])
    )
    r = al.advance_lifecycle("feat", project_root=project_root)
    assert r["state"] == "advanced-complete"


# ---------------------------------------------------------------------------
# #421 — the caller and the arm must agree, and a refusal must be audible
# ---------------------------------------------------------------------------


def test_corrupted_reduction_is_treated_as_review_required(project_root: Path) -> None:
    """A corrupted reduction must never be auto-completed.

    ``implement_transition._resolve_route`` treats ``corrupted`` as
    ``("review", "complex")``. When this caller did not, it took the no-review
    branch while the arm routed to ``review`` — landing
    ``phase_transition{to: "review"}`` under an ``advanced-complete`` report.
    ``_is_machine_complete`` matches only ``to: "complete"``, so every later run
    replayed and reported completion forever.
    """
    fd = _feature_dir(project_root)
    path = fd / "events.log"
    # Torn line AND no recoverable tier/criticality axis -> reduction.corrupted.
    path.write_text(
        "{tier: not-json\n"
        + json.dumps(
            {"event": "phase_transition", "feature": "feat", "from": "specify", "to": "implement"}
        )
        + "\n"
    )
    # Raw text, not parsed rows — the torn line is the point of the fixture.
    before = path.read_text()

    r = al.advance_lifecycle("feat", project_root=project_root)

    assert r == {"state": "missing-review"}
    assert path.read_text() == before, "a corrupted feature must not be advanced"


def test_a_refused_advance_is_audible_and_returns_advance_refused(
    project_root: Path, caplog
) -> None:
    """A refusal must not be reported as success.

    This call site set its ``state`` before calling ``advance`` and returned it
    unconditionally, so a refused transition surfaced to the CLI as
    ``advanced-complete`` with no events written and no warning — the operator
    had nothing to act on.

    The refusal is manufactured with **real machine rows that contradict**: the
    log's last ``phase_transition`` lands the feature at ``plan`` while the
    review arm's table ``from_state`` is ``review``. An artifact-fallback log
    (no ``phase_transition`` rows at all) no longer refuses — a table-derived
    from_state has nothing to gate against there, and gating on the artifact
    detector made the first machine row unwritable by construction.
    """
    fd = _feature_dir(project_root)
    seed = [
        {"event": "lifecycle_start", "feature": "feat", "tier": "complex", "criticality": "high"},
        # A real verdict, so the review-verdict arm is the one selected...
        {"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 1},
        # ...but the line-position-last machine row puts the feature at `plan`,
        # which that arm's table from_state of `review` contradicts.
        {"event": "phase_transition", "feature": "feat", "from": "specify", "to": "plan"},
    ]
    _write_events(fd, seed)
    (fd / "review.md").write_text(
        '```json\n{"verdict": "APPROVED", "cycle": 1, "issues": []}\n```\n'
    )

    with caplog.at_level(logging.WARNING, logger="cortex_command.overnight.advance_lifecycle"):
        r = al.advance_lifecycle("feat", project_root=project_root)

    assert r == {"state": "advance-refused"}
    assert "advance-refused" in al.KNOWN_STATES
    assert _read_events(fd) == seed, "refused, so nothing may be appended"
    warning = next(rec.getMessage() for rec in caplog.records if "REFUSED" in rec.getMessage())
    assert "feat" in warning
    assert str(fd / "events.log") in warning


def test_a_non_complete_route_is_never_reported_as_complete(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller asserts the route it actually got.

    Requirement 5 should make this unreachable, but reporting completion on the
    arm's say-so without checking is exactly how the divergence stayed invisible.
    Forced here, since no natural input reaches it once the gates agree.
    """
    fd = _feature_dir(project_root)
    _write_events(fd, _short_road(tier="simple", criticality="medium"))

    monkeypatch.setattr(
        al, "advance", lambda **kw: {"state": "review", "to_state": "review", "advanced": True}
    )
    r = al.advance_lifecycle("feat", project_root=project_root)

    assert r["state"] != "advanced-complete"
    assert r["state"] in al.KNOWN_STATES


def test_an_approved_review_reads_as_complete_downstream(project_root: Path) -> None:
    """End-to-end: after the approved path runs, morning review sees completion.

    This is the whole point of the ticket. ``missing-review`` here means an
    APPROVED review recorded nothing — the symptom that led an operator to
    conclude a passing feature had merged unreviewed.
    """
    fd = _feature_dir(project_root)
    _write_events(
        fd,
        _long_road(tier="complex", criticality="high")
        + [{"event": "review_verdict", "feature": "feat", "verdict": "APPROVED", "cycle": 1}],
    )
    (fd / "plan.md").write_text("- **Status**: [x] done\n")

    first = al.advance_lifecycle("feat", project_root=project_root)
    assert first["state"] == "advanced-crash-recovery"

    events = _read_events(fd)
    assert al._has_real_review_verdict(events)
    assert al._is_machine_complete(events)

    second = al.advance_lifecycle("feat", project_root=project_root)
    assert second == {"state": "already-complete"}


def test_every_state_is_known(project_root: Path) -> None:
    seen = set()

    seen.add(al.advance_lifecycle("ghost", project_root=project_root)["state"])

    fd1 = _feature_dir(project_root, "f1")
    _write_events(fd1, [{"event": "feature_complete", "feature": "f1"}])
    seen.add(al.advance_lifecycle("f1", project_root=project_root)["state"])

    fd2 = _feature_dir(project_root, "f2")
    _write_events(fd2, _short_road("f2", tier="simple", criticality="low"))
    seen.add(al.advance_lifecycle("f2", project_root=project_root)["state"])

    fd3 = _feature_dir(project_root, "f3")
    _write_events(fd3, _long_road("f3", tier="complex", criticality="medium"))
    seen.add(al.advance_lifecycle("f3", project_root=project_root)["state"])

    fd4 = _feature_dir(project_root, "f4")
    _write_events(
        fd4,
        _long_road("f4", tier="complex", criticality="medium")
        + [{"event": "review_verdict", "feature": "f4", "verdict": "APPROVED", "cycle": 1}],
    )
    seen.add(al.advance_lifecycle("f4", project_root=project_root)["state"])

    # A refusal: real machine rows land the feature at `plan`, contradicting the
    # review arm's table from_state of `review`. (An artifact-fallback log no
    # longer refuses — see test_a_refused_advance_is_audible_and_returns_advance_refused.)
    fd5 = _feature_dir(project_root, "f5")
    _write_events(
        fd5,
        [
            {"event": "lifecycle_start", "feature": "f5", "tier": "complex", "criticality": "high"},
            {"event": "review_verdict", "feature": "f5", "verdict": "APPROVED", "cycle": 1},
            {"event": "phase_transition", "feature": "f5", "from": "specify", "to": "plan"},
        ],
    )
    (fd5 / "review.md").write_text(
        '```json\n{"verdict": "APPROVED", "cycle": 1, "issues": []}\n```\n'
    )
    seen.add(al.advance_lifecycle("f5", project_root=project_root)["state"])

    assert seen <= set(al.KNOWN_STATES)
    assert seen == {
        "no-lifecycle-dir",
        "already-complete",
        "advanced-complete",
        "missing-review",
        "advanced-crash-recovery",
        "advance-refused",
    }


def test_cli_emits_json(project_root: Path, capsys) -> None:
    fd = _feature_dir(project_root)
    _write_events(fd, _short_road(tier="simple", criticality="medium"))
    rc = al.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "advanced-complete"


def test_cli_exits_0_with_error_state_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def _boom(feature, project_root=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(al, "advance_lifecycle", _boom)
    rc = al.main(["--feature", "feat"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error"
    assert "boom" in obj["message"]
