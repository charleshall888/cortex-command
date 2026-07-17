"""Tests for cortex-lifecycle-advance — the write-side executor that composes the
four B1 decision cores' fixed-source-order emission bodies inside one gate-checked
body (#397 retired the claim/commit locking primitive that used to wrap it).

The tests hand ``advance`` an explicit ``log_path`` under ``tmp_path`` (rather than
relying on CWD/main-root resolution), so the gate, the idempotency probes, and
the assertions all read/write the same physical log deterministically. Assertions
parse the real appended ``events.log`` rows — the write-side ordering invariant is
the whole point of the verb.
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


def test_plan_branch_mode_emits_legacy_rows_in_order(tmp_path: Path) -> None:
    """plan-decision/branch-mode-approved: plan_approved →
    phase_transition(plan→implement), in that order — and nothing else."""
    fd = _feature_dir(tmp_path)
    before = _plan_phase(fd)
    r = adv.advance(
        verb="plan-decision", feature="feat", decision="branch-mode-approved",
        dispatch_choice="trunk", from_state="plan", log_path=_log(fd),
    )
    assert r["state"] == "branch-mode-approved"
    assert r["advanced"] is True
    assert r["emitted"] == ["plan_approved", "phase_transition"]
    assert _appended(fd, before) == ["plan_approved", "phase_transition"]
    rows = _rows(fd)[before:]
    assert rows[0]["dispatch_choice"] == "trunk"
    assert rows[1]["from"] == "plan" and rows[1]["to"] == "implement"


def test_review_verdict_approved_emission_order(tmp_path: Path) -> None:
    """review-verdict/APPROVED: review_verdict → phase_transition(review→complete)."""
    fd = _feature_dir(tmp_path)
    before = _review_phase(fd)
    r = adv.advance(
        verb="review-verdict", feature="feat", verdict="APPROVED", cycle=1,
        drift="none", from_state="review", log_path=_log(fd),
    )
    assert r["state"] == "approved" and r["to_state"] == "complete"
    assert _appended(fd, before) == ["review_verdict", "phase_transition"]
    rows = _rows(fd)[before:]
    assert rows[0]["verdict"] == "APPROVED" and rows[0]["cycle"] == 1
    assert rows[1]["from"] == "review" and rows[1]["to"] == "complete"


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
        "review_verdict", "drift_protocol_breach", "phase_transition",
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
    assert _appended(fd, before) == ["spec_approved", "phase_transition"]


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


def test_batch_dispatches_are_idempotent_per_batch_number(tmp_path: Path) -> None:
    """Each batch is its own logical advance: batch 1 must not short-circuit on
    batch 0's recorded row.

    Regression (#393): the batch arm's table endpoints are implement→implement
    for EVERY batch, so any replay detection keyed on the bare endpoints would
    silently drop batch N's row after batch 0 landed (batches 1–6 of the
    discovering lifecycle went unrecorded). The emission-plan ``match`` carries
    the batch number, so the replay probe is idempotent per batch — the
    semantics the registry and implement.md §2b document.
    """
    fd = _feature_dir(tmp_path)
    _implement_phase(fd)
    first = adv.advance(verb="implement-transition", feature="feat", mode="batch",
                        batch=0, tasks=[1, 2], from_state="implement", log_path=_log(fd))
    second = adv.advance(verb="implement-transition", feature="feat", mode="batch",
                         batch=1, tasks=[3], from_state="implement", log_path=_log(fd))
    assert first["state"] == second["state"] == "dispatched"
    # Distinct batches are distinct advances — both rows land.
    assert second["emitted"] == ["batch_dispatch"]
    dispatched = [r for r in _rows(fd) if r["event"] == "batch_dispatch"]
    assert [r["batch"] for r in dispatched] == [0, 1]
    # A retry of the SAME batch replays benignly — no duplicate row.
    retry = adv.advance(verb="implement-transition", feature="feat", mode="batch",
                        batch=1, tasks=[3], from_state="implement", log_path=_log(fd))
    assert retry["replay"] == "already-emitted" and retry["emitted"] == []
    assert retry["advanced"] is True
    assert [r["batch"] for r in _rows(fd) if r["event"] == "batch_dispatch"] == [0, 1]


def test_plan_wait_emits_paused_and_holds(tmp_path: Path) -> None:
    """wait-approved: plan_approved{wait} → feature_paused{plan-approval,relayed-consent};
    to_state holds at plan."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    r = adv.advance(
        verb="plan-decision", feature="feat", decision="wait-approved",
        from_state="plan", log_path=_log(fd),
    )
    assert r["state"] == "wait-approved" and r["to_state"] == "plan"
    paused = [x for x in _rows(fd) if x["event"] == "feature_paused"][0]
    assert paused["slug"] == "plan-approval" and paused["kind"] == "relayed-consent"


def test_revise_short_circuits_no_claim(tmp_path: Path) -> None:
    """revise emits nothing and takes no claim — no events.log write at all."""
    fd = _feature_dir(tmp_path)
    r = adv.advance(verb="plan-decision", feature="feat", decision="revise",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "revise" and r["advanced"] is False
    # revise short-circuits before the primitive — no events.log write at all.
    assert not _log(fd).exists()


# ---------------------------------------------------------------------------
# Idempotent re-invocation (replay + crash-between-emissions repair)
# ---------------------------------------------------------------------------


def test_double_invocation_is_idempotent(tmp_path: Path) -> None:
    """Re-running the same logical advance appends no duplicate legacy rows; the
    second run short-circuits as a benign replay (all planned emissions present)
    even though the phase has already moved past the gate."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    adv.advance(verb="plan-decision", feature="feat",
                decision="branch-mode-approved", dispatch_choice="trunk",
                from_state="plan", log_path=_log(fd))
    second = adv.advance(verb="plan-decision", feature="feat",
                         decision="branch-mode-approved", dispatch_choice="trunk",
                         from_state="plan", log_path=_log(fd))
    assert second["replay"] == "already-emitted"
    assert second["advanced"] is True
    assert second["emitted"] == []
    names = _names(fd)
    assert names.count("plan_approved") == 1
    assert names.count("phase_transition") == 1


def test_partial_crash_resumes_missing_emissions(tmp_path: Path) -> None:
    """A crash between appends (the non-phase-moving row landed, the
    phase_transition was lost) resumes on re-invocation: on an events-authority
    log (a phase_transition row present, the served loop's normal shape) the gate
    still sees the pre-transition phase, the present row is skipped, and the
    missing row lands."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    _seed(fd, [{"ts": "t", "event": "phase_transition", "feature": "feat",
                "from": "specify", "to": "plan"},
               {"ts": "t", "event": "plan_approved", "feature": "feat",
                "dispatch_choice": "trunk"}])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["advanced"] is True
    assert r["emitted"] == ["phase_transition"]
    assert _names(fd).count("plan_approved") == 1
    plan_exits = [x for x in _rows(fd)
                  if x["event"] == "phase_transition" and x.get("from") == "plan"]
    assert len(plan_exits) == 1 and plan_exits[0]["to"] == "implement"


# ---------------------------------------------------------------------------
# Parsed-field compatibility — INDEPENDENT legacy reader
# ---------------------------------------------------------------------------


def test_emitted_rows_parse_for_independent_legacy_reader(tmp_path: Path) -> None:
    """The advance-authored legacy rows are canonically serialized, so the
    INDEPENDENT legacy readers (detect_lifecycle_phase / reduce_lifecycle_state)
    parse them unchanged and see the phase advance."""
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
    assert reduce_lifecycle_state(_log(fd)).corrupted is False
    # The emitted row is exactly the legacy field contract — nothing additive.
    pt = [x for x in _rows(fd) if x["event"] == "phase_transition"][0]
    assert {"ts", "event", "feature", "from", "to"} == set(pt)


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
    assert r["refusal"] == "gate-mismatch"
    assert "plan" in r["missing_evidence"]
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]
    # Nothing landed — the refusal precedes every emission.
    assert _names(fd) == []


# ---------------------------------------------------------------------------
# Pause-scoping (R12 / hazard 10) — event-backed refuses, describe-only never does
# ---------------------------------------------------------------------------


def test_advance_refuses_to_cross_event_backed_pause(tmp_path: Path) -> None:
    """An active feature_paused of an enforced kind (relayed-consent) blocks any
    NON-owning verb; the refusal names the pause, the TYPED resume arm for a
    slug that has one (#400 — the hand-append stays the fallback, never the
    recommendation), AND the sanctioned override."""
    fd = _feature_dir(tmp_path)
    _seed(fd, [
        {"event": "plan_approved", "feature": "feat", "dispatch_choice": "wait"},
        {"event": "feature_paused", "feature": "feat", "slug": "plan-approval",
         "kind": "relayed-consent"},
    ])
    r = adv.advance(verb="implement-transition", feature="feat", mode="batch",
                    batch=0, tasks=[1], from_state="implement", log_path=_log(fd))
    assert r["state"] == "refused"
    assert r["pause"]["kind"] == "relayed-consent"
    assert "plan-approval" in r["missing_evidence"]
    assert "cortex-lifecycle-advance plan-decision" in r["typed_resume"]
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]
    assert "batch_dispatch" not in _names(fd)  # refused before any emission


def test_owning_verb_resumes_through_its_own_pause(tmp_path: Path) -> None:
    """The typed resume the refusal recommends must actually work: the pause's
    owning verb (plan-decision for plan-approval) crosses its own pause,
    supersedes it with the routed transition, and the gate accepts the
    '-paused' phase suffix for exactly that crossing (#400 finding 3 — without
    this the only way out of a pause is the untyped hand-append the refusal is
    supposed to demote)."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    _seed(fd, [
        {"ts": "t", "event": "phase_transition", "feature": "feat",
         "from": "specify", "to": "plan"},
        {"ts": "t", "event": "plan_approved", "feature": "feat",
         "dispatch_choice": "wait"},
        {"ts": "t", "event": "feature_paused", "feature": "feat",
         "slug": "plan-approval", "kind": "relayed-consent"},
    ])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "branch-mode-approved" and r["advanced"] is True
    assert r["emitted"] == ["phase_transition"]  # plan_approved probe: already present
    # The pause is superseded — the feature resolves to implement, unpaused.
    from cortex_command.common import resolve_lifecycle_phase
    assert resolve_lifecycle_phase(fd)["phase"] == "implement"


def test_pause_refusal_without_typed_arm_omits_typed_resume(tmp_path: Path) -> None:
    """A pause slug with no typed verb arm carries no typed_resume — only the
    generic hand-append fallback — and no owning verb, so nothing crosses it."""
    rows = [
        {"event": "feature_paused", "feature": "feat", "slug": "phase-exit",
         "kind": "phase-exit-wait"},
    ]
    r = adv._pause_refusal(rows, "plan-decision")
    assert r is not None and "typed_resume" not in r
    assert "cortex-lifecycle-event log" in r["sanctioned_override"]


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
    assert adv._pause_refusal(active_config, "spec-approve") is None
    # ...whereas an active enforced pause IS a refusal (the discriminator) for
    # any verb that does not own the pause slug.
    active_enforced = [{"event": "feature_paused", "feature": "feat",
                        "slug": "plan-approval", "kind": "relayed-consent"}]
    assert adv._pause_refusal(active_enforced, "spec-approve") is not None
    assert adv._pause_refusal(active_enforced, "plan-decision") is None  # owning verb

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
    """A wait-approved retry replays idempotently (all its emissions are already
    present) rather than refusing on the pause it authored."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    adv.advance(verb="plan-decision", feature="feat", decision="wait-approved",
                from_state="plan", log_path=_log(fd))
    second = adv.advance(verb="plan-decision", feature="feat", decision="wait-approved",
                         from_state="plan", log_path=_log(fd))
    assert second["state"] == "wait-approved"
    assert second["replay"] == "already-emitted"
    assert second["emitted"] == []  # idempotent — no duplicate rows
    assert _names(fd).count("feature_paused") == 1


# ---------------------------------------------------------------------------
# Historical machine rows (retired claim/commit pair) stay inert
# ---------------------------------------------------------------------------


def test_historical_machine_rows_are_inert(tmp_path: Path) -> None:
    """Logs written under the retired claim/commit protocol carry
    advance_started/advance_committed rows and invocation_id fields; advance
    ignores them (they match no emission probe and no significant-event set)."""
    fd = _feature_dir(tmp_path)
    _plan_phase(fd)
    _seed(fd, [{"ts": "t", "event": "advance_started", "feature": "feat",
                "from_state": "specify", "to_state": "plan", "invocation_id": "abc"},
               {"ts": "t", "event": "advance_committed", "feature": "feat",
                "from_state": "specify", "to_state": "plan", "invocation_id": "abc"}])
    r = adv.advance(verb="plan-decision", feature="feat",
                    decision="branch-mode-approved", dispatch_choice="trunk",
                    from_state="plan", log_path=_log(fd))
    assert r["state"] == "branch-mode-approved" and r["advanced"] is True
    assert r["emitted"] == ["plan_approved", "phase_transition"]


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
