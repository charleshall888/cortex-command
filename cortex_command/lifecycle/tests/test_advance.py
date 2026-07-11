"""Tests for cortex-lifecycle-advance — the write-side executor that composes the
four B1 decision cores' fixed-source-order emission bodies inside the claim/commit
locking primitive (Task 6).

The tests hand ``advance`` an explicit ``log_path`` under ``tmp_path`` (rather than
relying on CWD/main-root resolution), so the primitive, the idempotency probes, and
the assertions all read/write the same physical log deterministically. Assertions
parse the real appended ``events.log`` rows — the write-side ordering invariant and
the dual-emission are the whole point of the verb.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.common import detect_lifecycle_phase, reduce_lifecycle_state
from cortex_command.lifecycle import advance as adv
from cortex_command.lifecycle.protocol import PROTOCOL_VERSION


def _feature_dir(tmp_path: Path, feature: str = "feat") -> Path:
    d = tmp_path / "cortex" / "lifecycle" / feature
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(feature_dir: Path) -> Path:
    return feature_dir / "events.log"


def _rows(feature_dir: Path) -> list[dict]:
    log = _log(feature_dir)
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _names(feature_dir: Path) -> list[str]:
    return [r["event"] for r in _rows(feature_dir)]


def _seed(feature_dir: Path, rows: list[dict]) -> None:
    _log(feature_dir).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def _appended(feature_dir: Path, before: int) -> list[str]:
    """Event names appended after the first *before* rows (isolates advance's own
    writes from any pre-seeded phase-scaffolding events)."""
    return [r["event"] for r in _rows(feature_dir)[before:]]


# Phase scaffolds — put the feature in a detectable phase so the claim's from_state
# gate (detect_lifecycle_phase) passes. Return the count of pre-seeded event rows.
def _plan_phase(fd: Path) -> int:
    """spec.md + plan.md present, not yet approved → detect_lifecycle_phase == 'plan'."""
    (fd / "spec.md").write_text("s", encoding="utf-8")
    (fd / "plan.md").write_text("- **Status**: [ ] a\n", encoding="utf-8")
    return len(_rows(fd))


def _specify_phase(fd: Path) -> int:
    """research.md + spec.md present, not yet spec_approved → 'specify'."""
    (fd / "research.md").write_text("r", encoding="utf-8")
    (fd / "spec.md").write_text("s", encoding="utf-8")
    return len(_rows(fd))


def _review_phase(fd: Path) -> int:
    """plan.md all-checked + plan_approved → 'review'."""
    (fd / "plan.md").write_text("- **Status**: [x] a\n", encoding="utf-8")
    _seed(fd, [{"event": "plan_approved", "feature": "feat", "dispatch_choice": "trunk"}])
    return len(_rows(fd))


def _implement_phase(fd: Path, *, tier: str = "simple") -> int:
    """plan.md with an unchecked task + plan_approved → 'implement'."""
    (fd / "plan.md").write_text("- **Status**: [ ] a\n", encoding="utf-8")
    _seed(fd, [
        {"event": "lifecycle_start", "feature": "feat", "criticality": "low", "tier": tier},
        {"event": "plan_approved", "feature": "feat", "dispatch_choice": "trunk"},
    ])
    return len(_rows(fd))


# ---------------------------------------------------------------------------
# Per-composed-transition write-side emission order (template: test_plan_decision)
# ---------------------------------------------------------------------------


def test_plan_branch_mode_emits_claim_then_legacy_then_commit(tmp_path: Path) -> None:
    """plan-decision/branch-mode-approved: advance_started → plan_approved →
    phase_transition(plan→implement) → advance_committed, in that order."""
    fd = _feature_dir(tmp_path)
    before = _plan_phase(fd)
    r = adv.advance(
        verb="plan-decision", feature="feat", decision="branch-mode-approved",
        dispatch_choice="trunk", from_state="plan", log_path=_log(fd),
    )
    assert r["state"] == "branch-mode-approved"
    assert r["advanced"] is True
    assert r["emitted"] == ["plan_approved", "phase_transition"]
    assert _appended(fd, before) == [
        "advance_started", "plan_approved", "phase_transition", "advance_committed",
    ]
    inv = r["invocation_id"]
    rows = _rows(fd)[before:]
    # Both machine rows carry the deterministic invocation_id.
    assert rows[0]["event"] == "advance_started" and rows[0]["invocation_id"] == inv
    assert rows[-1]["event"] == "advance_committed" and rows[-1]["invocation_id"] == inv
    # The legacy rows carry the additive invocation_id (advance-authored, distinguishable).
    assert rows[1]["dispatch_choice"] == "trunk" and rows[1]["invocation_id"] == inv
    assert rows[2]["from"] == "plan" and rows[2]["to"] == "implement" and rows[2]["invocation_id"] == inv


def test_review_verdict_approved_emission_order(tmp_path: Path) -> None:
    """review-verdict/APPROVED: review_verdict → phase_transition(review→complete)."""
    fd = _feature_dir(tmp_path)
    before = _review_phase(fd)
    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="APPROVED", cycle=1,
        drift="none", from_state="review", log_path=_log(fd),
    )
    assert r["state"] == "approved" and r["to_state"] == "complete"
    assert _appended(fd, before) == [
        "advance_started", "review_verdict", "phase_transition", "advance_committed",
    ]
    rows = _rows(fd)[before:]
    assert rows[1]["verdict"] == "APPROVED" and rows[1]["cycle"] == 1
    assert rows[2]["from"] == "review" and rows[2]["to"] == "complete"


def test_review_verdict_breach_interleaves_drift_row(tmp_path: Path) -> None:
    """CHANGES_REQUESTED cycle 1 with --breach: review_verdict → drift_protocol_breach
    → phase_transition(review→implement-rework)."""
    fd = _feature_dir(tmp_path)
    before = _review_phase(fd)
    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="CHANGES_REQUESTED", cycle=1,
        drift="detected", breach=True, retries=3, from_state="review", log_path=_log(fd),
    )
    assert r["state"] == "rework"
    assert _appended(fd, before) == [
        "advance_started", "review_verdict", "drift_protocol_breach",
        "phase_transition", "advance_committed",
    ]
    breach = [x for x in _rows(fd) if x["event"] == "drift_protocol_breach"][0]
    assert breach["retries"] == 3 and breach["cycle"] == 1


def test_spec_approve_emit_transition_order(tmp_path: Path) -> None:
    """spec-approve/approved with --emit-transition: spec_approved →
    phase_transition(specify→plan). Backend write-back is Task 14a (not core)."""
    fd = _feature_dir(tmp_path)
    before = _specify_phase(fd)
    r = adv.advance(
        verb="spec-approve", feature="feat", decision="approved", emit_transition=True,
        from_state="specify", log_path=_log(fd),
    )
    assert r["state"] == "approved" and r["to_state"] == "plan"
    assert _appended(fd, before) == [
        "advance_started", "spec_approved", "phase_transition", "advance_committed",
    ]


def test_spec_approve_no_transition_suppresses_edge(tmp_path: Path) -> None:
    """Standalone spec approval (no --emit-transition): spec_approved only, no
    phase_transition; the arm holds at specify (to_state == from_state)."""
    fd = _feature_dir(tmp_path)
    _specify_phase(fd)
    r = adv.advance(
        verb="spec-approve", feature="feat", decision="approved", emit_transition=False,
        from_state="specify", log_path=_log(fd),
    )
    assert r["emitted"] == ["spec_approved"]
    assert "phase_transition" not in _names(fd)


def test_implement_transition_routes_via_reducer(tmp_path: Path) -> None:
    """implement-transition mode transition routes review-vs-complete via the B1
    §4 rule (reused _resolve_route). A complex tier routes to review."""
    fd = _feature_dir(tmp_path)
    _implement_phase(fd, tier="complex")
    r = adv.advance(
        verb="implement-transition", feature="feat", mode="transition",
        from_state="implement", log_path=_log(fd),
    )
    assert r["state"] == "review" and r["to_state"] == "review"
    pt = [x for x in _rows(fd) if x["event"] == "phase_transition"][0]
    assert pt["from"] == "implement" and pt["to"] == "review" and pt["tier"] == "complex"


def test_plan_wait_emits_paused_and_holds(tmp_path: Path) -> None:
    """wait-approved: plan_approved{wait} → feature_paused{plan-approval,relayed-consent};
    to_state holds at plan; feature_paused carries the advance invocation_id."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    r = adv.advance(
        verb="plan-decision", feature="feat", decision="wait-approved",
        from_state="plan", log_path=_log(fd),
    )
    assert r["state"] == "wait-approved" and r["to_state"] == "plan"
    paused = [x for x in _rows(fd) if x["event"] == "feature_paused"][0]
    assert paused["slug"] == "plan-approval" and paused["kind"] == "relayed-consent"
    assert paused["invocation_id"] == r["invocation_id"]


def test_revise_short_circuits_no_claim(tmp_path: Path) -> None:
    """revise emits nothing and takes no claim — no events.log write at all."""
    fd = _feature_dir(tmp_path)
    r = adv.advance(verb="plan-decision", feature="feat", decision="revise",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "revise" and r["advanced"] is False
    # revise short-circuits before the primitive — no events.log write at all.
    assert not _log(fd).exists()


# ---------------------------------------------------------------------------
# Idempotent re-invocation (crash-between-emissions repair)
# ---------------------------------------------------------------------------


def test_double_invocation_is_idempotent(tmp_path: Path) -> None:
    """Re-running the same logical advance appends no duplicate legacy rows and
    exactly one advance_committed; the second run re-derives the same invocation_id
    and reports already-committed."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    first = adv.advance(verb="plan-decision", feature="feat",
                        decision="branch-mode-approved", dispatch_choice="trunk",
                        from_state="plan", log_path=_log(fd))
    second = adv.advance(verb="plan-decision", feature="feat",
                         decision="branch-mode-approved", dispatch_choice="trunk",
                         from_state="plan", log_path=_log(fd))
    assert first["invocation_id"] == second["invocation_id"]
    assert second["commit_status"] == "already-committed"
    assert second["emitted"] == []
    names = _names(fd)
    assert names.count("plan_approved") == 1
    assert names.count("phase_transition") == 1
    assert names.count("advance_committed") == 1


# ---------------------------------------------------------------------------
# Orphaned advance_started recovery by invocation_id
# ---------------------------------------------------------------------------


def test_orphaned_claim_recovered_by_invocation_id(tmp_path: Path) -> None:
    """A crash after claim but before the legacy side effects leaves an orphaned
    advance_started; re-invoking the same logical advance resumes that claim (same
    invocation_id, no duplicate advance_started) and completes the transition."""
    fd = _feature_dir(tmp_path)
    inv = adv.derive_invocation_id("feat", "plan", "implement", "")
    # Simulate the orphan: only the claim row landed (side effects + commit lost).
    _seed(fd, [{"ts": "t", "event": "advance_started", "feature": "feat",
                "from_state": "plan", "to_state": "implement", "invocation_id": inv}])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["invocation_id"] == inv
    assert r["claim_status"] == "resumed"
    assert r["advanced"] is True
    # Exactly one advance_started (the orphan was reused, not duplicated).
    assert _names(fd).count("advance_started") == 1
    assert _names(fd) == [
        "advance_started", "plan_approved", "phase_transition", "advance_committed",
    ]


# ---------------------------------------------------------------------------
# Dual-emission parsed-field compatibility — INDEPENDENT legacy reader
# ---------------------------------------------------------------------------


def test_dual_emission_independent_legacy_reader_parses(tmp_path: Path) -> None:
    """The advance-authored legacy rows are canonically serialized and carry only
    an ADDITIVE invocation_id, so the INDEPENDENT legacy readers
    (detect_lifecycle_phase / reduce_lifecycle_state) parse them unchanged and see
    the phase advance — not a self-read of advance's own machine rows."""
    fd = _feature_dir(tmp_path)
    # Seed a plan-phase feature (spec.md + plan.md present, plan not yet approved).
    (fd / "spec.md").write_text("spec", encoding="utf-8")
    (fd / "plan.md").write_text("- **Status**: [x] a\n", encoding="utf-8")
    _seed(fd, [{"event": "spec_approved", "feature": "feat", "decision": "approved"}])
    assert detect_lifecycle_phase(fd)["phase"] == "plan"  # not approved yet

    adv.advance(verb="plan-decision", feature="feat", decision="branch-mode-approved",
                dispatch_choice="trunk", from_state="plan", log_path=_log(fd))

    # The independent artifact reader now sees the plan_approved + plan→implement
    # transition advance's legacy rows carry (1 checked / 1 total → review).
    detected = detect_lifecycle_phase(fd)
    assert detected["phase"] == "review"
    # The reducer tolerates the additive invocation_id on the phase_transition row.
    assert reduce_lifecycle_state(_log(fd)).corrupted is False
    # Prove the assertion reads the advance-authored legacy row, not a machine row,
    # and that invocation_id is purely ADDITIVE on top of the legacy field contract.
    pt = [x for x in _rows(fd) if x["event"] == "phase_transition"][0]
    assert pt.get("invocation_id") is not None  # advance-authored
    assert {"ts", "event", "feature", "from", "to", "invocation_id"} == set(pt)


# ---------------------------------------------------------------------------
# Refusal-envelope golden — names missing evidence AND sanctioned override
# ---------------------------------------------------------------------------


def test_refusal_on_gate_mismatch_names_evidence_and_override(tmp_path: Path) -> None:
    """A from_state gate mismatch refuses with a {state: refused} envelope naming
    the missing evidence AND the sanctioned override (cortex-lifecycle-event log)."""
    fd = _feature_dir(tmp_path)
    # Reality is 'research' (empty log/dir) but the caller asserts from_state=plan.
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "refused"
    assert r["claim_status"] == "gate-mismatch"
    assert "plan" in r["missing_evidence"]
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]
    # No advance_committed landed; the claim never staked either.
    assert "advance_committed" not in _names(fd)


def test_refusal_on_interleaved_state_moving_row(tmp_path: Path) -> None:
    """A foreign state-moving row landing between advance's side effects and commit
    makes commit refuse ('state moved since claim') and name the interleaved row."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    orig_log_event_at = adv.log_event_at

    def _inject(log_path, event_dict):  # emit, then slip in a foreign transition
        orig_log_event_at(log_path, event_dict)
        if event_dict.get("event") == "phase_transition":
            orig_log_event_at(log_path, {"event": "review_verdict", "feature": "feat",
                                         "verdict": "APPROVED", "cycle": 9})

    adv.log_event_at = _inject
    try:
        r = adv.advance(verb="plan-decision", feature="feat",
                        decision="branch-mode-approved", dispatch_choice="trunk",
                        from_state="plan", log_path=_log(fd))
    finally:
        adv.log_event_at = orig_log_event_at
    assert r["state"] == "refused"
    assert r["commit_status"] == "state-moved"
    assert r["interleaved_row"]["event"] == "review_verdict"
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]


# ---------------------------------------------------------------------------
# Pause-scoping (R12 / hazard 10) — event-backed refuses, describe-only never does
# ---------------------------------------------------------------------------


def test_advance_refuses_to_cross_event_backed_pause(tmp_path: Path) -> None:
    """An active feature_paused of an enforced kind (relayed-consent) blocks a
    crossing advance; the refusal names the pause AND the sanctioned override."""
    fd = _feature_dir(tmp_path)
    _seed(fd, [
        {"event": "plan_approved", "feature": "feat", "dispatch_choice": "wait"},
        {"event": "feature_paused", "feature": "feat", "slug": "plan-approval",
         "kind": "relayed-consent"},
    ])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "refused"
    assert r["pause"]["kind"] == "relayed-consent"
    assert "plan-approval" in r["missing_evidence"]
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]
    assert "advance_started" not in _names(fd)  # refused before the claim


def test_legacy_kindless_pause_fails_closed_and_refuses(tmp_path: Path) -> None:
    """A legacy feature_paused with no kind fails closed to the most-restrictive
    (enforced) kind — advance still refuses (hazard 3 parity)."""
    fd = _feature_dir(tmp_path)
    _seed(fd, [{"event": "feature_paused", "feature": "feat"}])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "refused"
    assert r["pause"]["kind"] == "relayed-consent"


def test_advance_does_not_refuse_on_describe_only_pause_kind(tmp_path: Path) -> None:
    """A judgment/config-conditional pause kind is describe-only metadata — it is
    NEVER a refusal. The discrimination is tested at the pause-decision level (so it
    is not entangled with Task 6's claim from_state gate) AND end-to-end: a
    superseded config-conditional pause in history does not block a normal advance."""
    fd = _feature_dir(tmp_path)
    # Decision-level: an ACTIVE config-conditional pause is not a refusal.
    active_config = [{"event": "feature_paused", "feature": "feat",
                      "slug": "some-conditional", "kind": "config-conditional"}]
    assert adv._pause_refusal(active_config, "someid") is None
    # ...whereas an active enforced pause IS a refusal (the discriminator).
    active_enforced = [{"event": "feature_paused", "feature": "feat",
                        "slug": "plan-approval", "kind": "relayed-consent"}]
    assert adv._pause_refusal(active_enforced, "someid") is not None

    # End-to-end: a config-conditional pause superseded by a later transition (so the
    # feature is advanceable, detect == 'plan') never blocks advance.
    (fd / "spec.md").write_text("s", encoding="utf-8")
    (fd / "plan.md").write_text("- **Status**: [ ] a\n", encoding="utf-8")
    _seed(fd, [
        {"event": "feature_paused", "feature": "feat", "slug": "c", "kind": "config-conditional"},
        {"event": "spec_approved", "feature": "feat", "decision": "approved"},
        {"event": "phase_transition", "feature": "feat", "from": "specify", "to": "plan"},
    ])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "branch-mode-approved" and r["advanced"] is True


def test_wait_approved_retry_is_not_self_blocked(tmp_path: Path) -> None:
    """The pause pre-check exempts the invocation that authored the active pause, so
    a wait-approved retry resumes idempotently rather than refusing on its own pause."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    first = adv.advance(verb="plan-decision", feature="feat", decision="wait-approved",
                        from_state="plan", log_path=_log(fd))
    second = adv.advance(verb="plan-decision", feature="feat", decision="wait-approved",
                         from_state="plan", log_path=_log(fd))
    assert first["invocation_id"] == second["invocation_id"]
    assert second["state"] == "wait-approved"
    assert second["emitted"] == []  # idempotent — no duplicate rows
    assert _names(fd).count("feature_paused") == 1
    assert _names(fd).count("advance_started") == 1  # no duplicate claim on replay


# ---------------------------------------------------------------------------
# Concurrency: exactly one commit, one explicit in-flight refusal
# ---------------------------------------------------------------------------


def test_second_claimant_refused_in_flight(tmp_path: Path) -> None:
    """A different invocation (via --discriminator) that finds an unresolved claim on
    the same (feature, from_state) is refused 'in-flight transition'."""
    fd = _feature_dir(tmp_path)
    inv_a = adv.derive_invocation_id("feat", "plan", "implement", "sessionA")
    _seed(fd, [{"ts": "t", "event": "advance_started", "feature": "feat",
                "from_state": "plan", "to_state": "implement", "invocation_id": inv_a}])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", discriminator="sessionB", log_path=_log(fd))
    assert r["state"] == "refused" and r["claim_status"] == "in-flight"
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]


# ---------------------------------------------------------------------------
# House-style: slug guard, KNOWN_STATES, never-crash CLI
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "..", ""])
def test_unsafe_slug_errors_before_any_write(tmp_path: Path, bad: str) -> None:
    r = adv.advance(verb="plan-decision", feature=bad, decision="cancelled",
                    from_state="plan", log_path=_log(_feature_dir(tmp_path)))
    assert r["state"] == "error"


def test_refused_and_error_are_known_states() -> None:
    assert "refused" in adv.KNOWN_STATES
    assert "error" in adv.KNOWN_STATES
    # Every B1 decision state is reachable through advance's returned state.
    for s in ("branch-mode-approved", "wait-approved", "cancelled", "revise",
              "approved", "rework", "escalated", "dispatched", "review", "complete"):
        assert s in adv.KNOWN_STATES


def test_cli_emits_json_and_exits_0(tmp_path: Path, capsys) -> None:
    fd = _feature_dir(tmp_path)
    rc = adv.main([
        "plan-decision", "--feature", "feat", "--decision", "revise",
        "--from-state", "plan", "--log-path", str(_log(fd)),
    ])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "revise"
    assert obj["protocol"] == PROTOCOL_VERSION


def test_cli_never_crashes_on_unexpected_exception(tmp_path: Path, monkeypatch, capsys) -> None:
    def _boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(adv, "advance", _boom)
    rc = adv.main(["plan-decision", "--feature", "feat", "--decision", "cancelled"])
    assert rc == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["state"] == "error" and "kaboom" in obj["message"]
