---
schema_version: "1"
uuid: f369e0e7-508b-42e7-9953-e49fdcacea57
title: implement-transition gate refuses because all-tasks-[x] is both its precondition and what makes its detector say review
status: complete
priority: high
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['lifecycle', 'served-loop', 'phase-authority']
areas: ['lifecycle']
---
> **SHIPPED (2026-07-17).** The split authority this ticket describes was closed by `e6857ec9` (the advance claim gate now resolves phase through `resolve_lifecycle_phase`, events-first per ADR-0025 — same fix tracked in [[393-advance-claim-gate-resolved-phase-by-artifact-making-the-implement-to-review-transition-unfireable]]). This session added the regression the fix lacked: the gate test is now parametrized over all three artifact-driven boundaries (implement→review, review→rework, review→complete) in `cortex_command/tests/test_lifecycle_event_claim_commit.py`, so the next boundary of this shape is a param, not a rediscovery. The crash-recovery property held: the invocation id still derives from stable table endpoints. Operators see the fix once the next release tag lands (the CLI is a non-editable wheel; see #393's release note).

## Why

The implement→review transition cannot be recorded through the verb that owns it. The implement phase's reference instructs the orchestrator to flip every task to `[x]` and then call `cortex-lifecycle-advance implement-transition --mode transition`. That verb gates on `from_state: implement`, and the gate resolves the current phase through `cortex_command/common.py`'s `_detect_lifecycle_phase_inner`, whose Step 3 returns `review` as soon as `total > 0 and checked == total`. The instructed precondition is therefore exactly the condition that makes the gate report a different phase and refuse. Hit live on lifecycle 380 with all nine tasks complete: every implement-arm call returned `claim_status: gate-mismatch`, `reason: from_state gate: detected phase 'review' does not match expected from_state 'implement'`, and the only way forward was the `sanctioned_override` hand-append the refusal itself names.

Underneath the deadlock is a split authority. `cortex-lifecycle-next` served `state: implement` for the same feature at the same moment, because it reduces events and the last `phase_transition` row was `plan→implement`. ADR-0025 makes events the authoritative phase source wherever machine rows exist, with artifact derivation as the legacy fallback — but the write path's gate is still on the fallback, so the two verbs in one wheel disagree, and the disagreement is load-bearing rather than cosmetic.

## Role

After this lands, a lifecycle whose tasks are all complete can record its own implement→review transition through the served verb, without an out-of-band append. The `next` reducer and the `advance` gate resolve phase through one authority, so a served state and a refused write can no longer describe the same feature differently. The sanctioned override returns to being an escape hatch for genuine drift rather than the routine path out of Implement.

## Integration

Touches the claim gate in the advance cluster and the phase resolver both it and `cortex-lifecycle-next` consume. The artifact-derived detector has other readers — statusline, dashboard, and the overnight report all resolve phase through it — so a change to its Step 3 semantics reaches those surfaces, while a change confined to the gate's authority does not. Any fix must keep the crash-recovery property that the invocation id derives from stable table endpoints rather than the volatile detected phase.

## Edges

- The detector's Step 3 is also what routes a resumed session to the right phase when no machine rows exist; a legacy lifecycle with no `phase_transition` rows must still resolve.
- Read-side tolerance is unchanged: historical logs are never rewritten, and legacy shapes keep parsing.
- Not a request to remove the artifact fallback — only to settle which authority the write-side gate consults.

## Touch points

- `cortex_command/common.py` — `_detect_lifecycle_phase_inner` Step 3 (`checked == total` → `review`) and the `detect_lifecycle_phase` wrapper the gate calls.
- `cortex_command/lifecycle/advance.py` — the claim path and its `gate-mismatch` refusal.
- `cortex_command/lifecycle/implement_transition.py` — the transition mode that cannot fire.
- `skills/lifecycle/references/implement.md` §4 — prescribes flip-then-transition, the order that triggers this.
- `cortex/adr/0025-*` — events-as-phase-authority, the decision the gate does not yet follow.
- Evidence: `cortex/lifecycle/lifecycleconfig-template-ships-dormant-skip-specify/events.log` carries a hand-appended `implement→review` row with no `invocation_id`, unlike its verb-emitted siblings.
