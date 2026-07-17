[← Back to Agentic Layer](agentic-layer.md)

# Roll-forward exit procedure — served lifecycle loop

**For:** The operator who needs to back the lifecycle out of the 374 served `next`/`advance` loop.  **Assumes:** Familiarity with the served-verb class ([ADR-0024](../cortex/adr/0024-served-lifecycle-verb-class-and-coexistence.md)) and the phase-authority cutover ([ADR-0025](../cortex/adr/0025-events-as-phase-authority-with-legacy-fallback.md)).

This is the **standing exit** for the served lifecycle loop. Read it before you reach for `git revert`.

## Why this is a roll-forward, not a revert

The phase-authority cutover (ADR-0025) made `events.log` the authoritative phase source wherever machine rows exist; the artifact-presence derivation (`common.detect_lifecycle_phase`) demoted to a legacy fallback reached only when the log carries no state-establishing machine row. **That cutover forfeited the cheap prose-side rollback.** Before it, "undo the routing change" was a `git revert` of skill prose. After it, phase authority lives in `events.log` plus the wheel resolver, and there is no one-file revert that restores artifact-authority without reintroducing the dual-authority drift the cutover exists to kill.

So the sanctioned way out is to **roll forward**: de-route the shipped prose off the served verbs, leave the wheel verbs callable for out-of-repo consumers, quarantine the transition vocabulary under a named owner, and let dual-emission carry old readers through the grace window. Nothing here is a hard cut — every step keeps the coexistence contract intact.

**When to reach for this.** The permanent `scan_lifecycle` mismatch detector (ADR-0025) is the tripwire: it reports events-vs-backlog divergence forever, so a hand-edited artifact that the resolver now overrides, or a served-loop behavior you need to stop shipping, surfaces there for a human. A sustained pattern of such reports — or an operator decision to retire the served loop ahead of a protocol-floor bump — is the signal that a roll-forward is warranted.

## Step 1 — Name the trigger, owner, and decision-record home up front

Do not begin de-routing until these three are written down in the decision record. An unowned exit window accretes debt (the #377 lesson); an unrecorded trigger makes the exit un-auditable.

Trigger: a sustained `scan_lifecycle` mismatch-detector divergence pattern, a served-loop correctness defect that cannot wait for a wheel release, or an explicit operator decision to retire the served loop.

Owner: **charliemhall@gmail.com** — repo maintainer / lifecycle-area owner. The owner authorizes the roll-forward, sequences the commits below, and is accountable for closing the coexistence window at the eventual protocol-floor bump.

Decision-record home: a new ADR under `cortex/adr/` (an amendment to ADR-0024/ADR-0025 if the change is bounded, a fresh record if it re-litigates the served-verb class). The ADR states the trigger that fired, the owner, and the roll-forward scope, and back-points to this procedure.

## Step 0 — Confirm the force-source wrappers are in place

**Precondition, verify first.** Every served verb must have a force-source `bin/` wrapper — one that honors `CORTEX_COMMAND_FORCE_SOURCE` — so the roll-forward can be exercised against working-tree source without a wheel reinstall, including the loop's entry verb, whose wrapper (`bin/cortex-lifecycle-resolve`) was the last one closed (Task 8 / spec R9). Confirm `bin/cortex-lifecycle-resolve`, `bin/cortex-lifecycle-next`, `bin/cortex-lifecycle-advance`, and `bin/cortex-lifecycle-describe` all exist and route through the force-source branch. If any wrapper is missing, the remediation channel has a hole at that verb and the roll-forward cannot be driven deterministically — close it before proceeding.

## Step 2 — Revert the SKILL.md prose to phase-table routing (one commit)

De-route the shipped prose off the served verbs in a **single commit**. `skills/lifecycle/SKILL.md` (and any phase-reference prose absorbed into the loop) stops invoking `cortex-lifecycle-next` / `cortex-lifecycle-advance` and returns to the phase-dispatch-table routing it used before the loop landed. Keep the change to prose only: this commit must not touch the wheel verbs, the transition table, or the events schema. Commit via `/cortex-core:commit`; the dual-source mirrors regenerate at pre-commit.

After this commit no shipped prose commands the served verbs, which narrows the served loop's blast radius to the wheel side while everything below stays callable.

## Step 3 — Leave the wheel verbs callable

Do **not** delete or disable `cortex-lifecycle-next`, `cortex-lifecycle-advance`, `cortex-lifecycle-describe`, or the typed transition subcommands. Retirement is a separate, later decision — a protocol-floor bump decided by the operator on a telemetry-informed trigger, not this roll-forward (ADR-0024 coexistence policy). Out-of-repo and stale-plugin consumers still call these verbs; cutting them here would convert a reversible roll-forward into a hard break. The verbs stay callable; only the shipped prose stopped commanding them (Step 2).

## Step 4 — Verify tolerant reading via the reverse-direction golden

Prove that old readers still project correctly over the machine-written logs the loop already emitted. The reverse-direction golden (spec R16 arm h; driven by `tests/test_lifecycle_reverse_golden.py`, whose fixture `README.md` pins the reader set) covers exactly this guarantee: each enumerated legacy reader — `cortex-lifecycle-state`, `cortex-lifecycle-counters`, the statusline derivation, `dashboard/data.py`, `scan_lifecycle`, and `generate_index.py` — reproduces its correct legacy-phase projection over a mixed log carrying the `advance_started` / `advance_committed` rows and the `invocation_id` field (historical content since #397 retired the claim/commit protocol — see ADR-0020's #397 amendment — but permanent in the on-disk corpus). Run it:

```
uv run pytest tests/test_lifecycle_reverse_golden.py -q
```

A green run confirms the additive machine content is inert to every old reader, so de-routing the prose (Step 2) has not stranded any consumer. If it fails, stop — the roll-forward is not safe until tolerant reading is restored.

## Step 5 — Quarantine the transition vocabulary under a named owner

If the roll-forward makes any transition event dead in-repo, quarantine it rather than deleting it. Mark the row in `bin/.events-registry.md` as `deprecated-pending-removal` with a filled `deprecation_date` and a rationale, exactly as the existing retired-event rows do. **The #377 lesson is that an unowned deprecation window accretes debt**, so each quarantined row carries a named owner.

Quarantine owner: **charliemhall@gmail.com** — runs `just check-events-registry-audit` (`bin/cortex-check-events-registry --audit`) on a recurring cadence to surface stale `deprecated-pending-removal` rows, and owns the follow-up cleanup PR that prunes each row once its grace window has elapsed and no in-flight session can still emit it. The audit's `owner` column is the bump authority of record; a row without a named owner fails the audit.

Note the differing trigger: the served verbs' *eventual* retirement runs through the same `deprecated-pending-removal` template but fires on a **protocol-floor bump**, not a calendar grace window (ADR-0024). This step covers only vocabulary made dead by *this* roll-forward.

## Step 6 — Keep dual-emission live through the grace window

Do not narrow the legacy-vocabulary emission as part of the roll-forward. While any advance-authored transition may still be read by an old consumer, the `advance` verb keeps emitting the exact legacy event vocabulary — `phase_transition`, `review_verdict`, `spec_approved`, `plan_approved`, `feature_complete` — as its rows, so old readers parse them. (The additive `advance_started`/`advance_committed` machine rows and `invocation_id` field that used to ride alongside were retired with the claim/commit protocol — #397, ADR-0020 amendment — and survive only as historical log content.) The legacy vocabulary contracts **only** at an operator-decided protocol-floor bump (ADR-0024), never as a side effect of exiting the loop. Collapsing it early would strand exactly the out-of-repo readers Step 3 and Step 5 are protecting.

## At a glance

| Step | Action | Reversible-by-design? |
|------|--------|-----------------------|
| 1 | Record trigger + owner + decision-record home | — (governance) |
| 0 | Confirm force-source wrappers (incl. `cortex-lifecycle-resolve`) | precondition |
| 2 | Revert SKILL.md prose to phase-table routing (one commit) | yes — prose only |
| 3 | Leave the wheel verbs callable | yes — no deletion |
| 4 | Verify tolerant reading via the reverse-direction golden | verification gate |
| 5 | Quarantine dead vocabulary as `deprecated-pending-removal`, named owner | yes — no deletion |
| 6 | Keep dual-emission live through the grace window | yes — no contraction |

The single-oracle events-authority (ADR-0025) is kept throughout; this procedure changes what *commands* the loop, never who *owns* the phase fact.
