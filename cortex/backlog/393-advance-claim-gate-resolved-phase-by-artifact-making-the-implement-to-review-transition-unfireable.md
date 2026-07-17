---
schema_version: "1"
uuid: 4d4ab38e-210d-4c40-98e8-97623360ea74
title: Advance claim gate resolved phase by artifact, making the implement-to-review transition unfireable
status: backlog
priority: high
type: bug
created: 2026-07-16
updated: 2026-07-16
tags: ['lifecycle', 'events-log']
areas: ['agentic-layer']
---
# Advance claim gate resolved phase by artifact, making the implement-to-review transition unfireable

## Why

Two defects in the served advance loop, found while running a lifecycle to completion. The first is fixed; the second is open.

**Fixed (commit `e6857ec9`)**: the advance claim gate resolved the current phase with the legacy artifact-presence derivation instead of the events-first resolver that the events-first ADR makes authoritative. The artifact derivation reports `review` as soon as every plan task is checked. Because the implement reference has the orchestrator flip those checkboxes in its task-dispatch step, *before* its transition step invokes the verb, the implement-to-review claim was refused by construction — its precondition was its own refusal condition. The prose mandated a call that could never succeed.

The evidence that this was never noticed: of the 244 recorded implement-to-review rows across every lifecycle in this repo, **zero** carry an invocation id — meaning every single one was written by prose or the out-of-band hand-append, never through the claim gate. Since the claim primitive shipped, no gated implement-to-review transition has ever succeeded. Event-driven boundaries were unaffected, because each verb stakes its claim *before* emitting the event that moves the detector.

**Every artifact-driven boundary is affected, not just one.** The first draft of this ticket said only the implement-to-review boundary broke; that was measured too early and is wrong. The review-verdict boundary fails identically: the reviewer's verdict lands in the review artifact, which moves the artifact derivation to the rework state, and the verb is only invoked afterward — so a claim from the review state is refused for the same structural reason. **Three** boundaries were confirmed live, in one lifecycle run: implement-to-review (the plan's tasks are all checked before the verb is called), review-to-rework (the reviewer's changes-requested verdict lands in the artifact first), and review-to-complete (likewise for an approved verdict). The general rule: wherever the artifact that *triggers* a transition is written before the verb that records it, the artifact derivation has already advanced past the state the gate demands. The landed fix covers all three, because it asks the log where the feature is rather than inferring it from files. The count is three because that is how many the run happened to cross — treat the rule as the finding, not the tally.

**Still open**: the batch-dispatch record deduplicates on the invocation, not the batch number. Both the implement reference and the events registry claim the emission is "idempotent per batch number". In practice a second batch returns the first batch's invocation id with an empty emission list, so its row is silently dropped. In the lifecycle that surfaced this, batches 1 through 6 went unrecorded — the log shows only batch 0, understating what actually ran. The rows feed pipeline metrics; nothing gates on them, so the damage is telemetry, not control flow.

## Role

Restore the invariant that the loop's two sides agree on what phase a feature is in. The state server already resolves events-first; the claim gate did not, so the server and the gate could disagree about the same feature at the same moment — the server saying `implement` while the gate insisted `review`. A gate that contradicts the server is worse than no gate: it blocks the correct call and teaches operators to reach for the hand-append, which is exactly the habit that hid this for weeks.

## Integration

The gate fix is landed and carries two regression tests: one pinning that the implement-to-review claim is granted when the plan is fully checked but the log still says implement (verified non-vacuous by mutation — reverting the fix fails exactly that test), and one pinning that a genuine events mismatch still refuses, so events-first does not quietly become gate-free. The existing gate test only ever exercised an empty feature directory resolving to `research`, which is why a plan-bearing feature's gate was never covered.

The fix reaches operators through the normal tag and auto-release ritual; the CLI is a non-editable wheel installed from a tag, so a working-tree fix is inert until released. The lifecycle that found this recorded its own transition via the sanctioned hand-append rather than swapping the shared global CLI mid-flight.

## Edges

- The remaining batch-dispatch work is to key idempotency on the batch number as documented, or to correct both the reference and the registry to describe what the code does. Do not assume the docs are right — this ticket exists because a claim nobody re-derived was believed for weeks.
- Backfilling the missing batch rows was considered and declined: hand-appending rows the verb was supposed to own is the same bypass that hid the phase defect.
- Worth auditing whether any other caller of the legacy artifact derivation should be events-first. The fix corrected the gate only; the derivation is documented as a fallback for features with no machine rows, and that use stays legitimate.
- The landed regression coverage pins the implement-to-review boundary. The review-verdict boundary fails for the same reason and is fixed by the same change, but has no test of its own — add one, and prefer a parametrisation over the artifact-driven boundaries to a second copy, so the next boundary of this shape is covered by construction.
- Both affected boundaries were found by hitting them, one after the other, in a single lifecycle run. Nothing in the test suite exercises a plan-bearing or review-bearing feature through the gate: the existing gate test uses an empty feature directory, which resolves to the initial state and passes trivially. That gap is the reason this class of defect is invisible.

## Touch points

- `cortex_command/lifecycle_event.py` — the claim gate (fixed)
- `cortex_command/common.py` — the artifact derivation and the events-first resolver
- `cortex_command/lifecycle/implement_transition.py` — the batch-mode idempotency (open)
- `cortex_command/tests/test_lifecycle_event_claim_commit.py` — the gate's regression coverage
- `bin/.events-registry.md` — the per-batch-number claim that does not match behavior
- `skills/lifecycle/references/implement.md` — the same claim in the reference prose