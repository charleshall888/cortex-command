---
schema_version: "1"
uuid: cd7ac4f3-3737-401b-b8f1-29271c4a60bf
title: batch_dispatch is not idempotent per batch number, so every batch after zero is silently dropped
status: complete
priority: medium
type: bug
created: 2026-07-16
updated: 2026-07-17
tags: ['lifecycle', 'served-loop', 'events']
areas: ['lifecycle']
---
> **SHIPPED (2026-07-17).** Landed as `2bdb750e` under the #393 closure batch, one commit before this ticket was picked up: the batch number now joins the invocation-id derivation (`advance.py` composes it with any caller `--discriminator` via a `\x1f` separator, so that flag's concurrent-invocation purpose survives), making the emission idempotent per batch number while a retry of the same batch still resumes its own claim. `test_batch_dispatches_are_idempotent_per_batch_number` pins it. The registry row and `implement.md` §2b needed no edits — the semantics they document are now the semantics the verb has. Historical single-row logs stay as they are.

## Why

`bin/.events-registry.md` records `batch_dispatch` as emitted by the implement-cluster verb "idempotent per batch number", and the implement phase's reference prescribes `cortex-lifecycle-advance implement-transition --mode batch --feature <name> --batch <N> --tasks '[...]'`. The verb derives its invocation id from `(feature, from_state, to_state, discriminator)`, and `discriminator` is a separate CLI flag defaulting to the empty string — `--batch` never reaches it. Batch mode's endpoints are both `implement`, so every batch of a given feature derives the *same* id. Batch 1 therefore matches batch 0's committed pair, hits the idempotent-replay short-circuit, and returns `commit_status: already-committed`, `emitted: []`.

The failure is silent and the prose is what triggers it: an orchestrator following `implement.md` verbatim gets a success-shaped envelope (`state: dispatched`, `advanced: true`) for a batch that recorded nothing. Observed on lifecycle 380 — two batches ran and committed real work, but `events.log` carries only `batch: 0`. Any consumer reconstructing dispatch history from events sees a single batch and undercounts the rest, which matters most for the multi-batch overnight runs the event exists to measure.

## Role

After this lands, each batch of a feature records its own `batch_dispatch` row when the orchestrator follows the documented invocation, and re-invoking the same batch is what replays idempotently — matching what the registry already claims. Dispatch history reconstructed from events matches dispatch history as it happened, and the registry's "idempotent per batch number" stops being aspirational.

## Integration

Touches the invocation-id derivation shared by every advance arm and the batch mode that supplies its discriminator, plus the prose that prescribes the invocation. The id derivation is deliberately keyed on stable business identity so a crash-recovery retry resumes its orphaned claim — whatever distinguishes batches must preserve that property rather than reintroduce volatility. The registry row and the skill prose must move with the verb so the three stop disagreeing.

## Edges

- Re-invoking the *same* batch must still replay idempotently — this is about distinguishing batches, not weakening replay.
- Historical logs are never rewritten; existing single-row lifecycles stay as they are and readers keep tolerating them.
- The `--discriminator` flag has a separate documented purpose (concurrent invocations) that must survive.

## Touch points

- `cortex_command/lifecycle/advance.py` — `derive_invocation_id(feature, effective_from, to_state, discriminator)` and the `--discriminator` argparse default.
- `cortex_command/lifecycle/implement_transition.py` — batch mode, which accepts `--batch` but does not thread it into the id.
- `skills/lifecycle/references/implement.md` §2b — prescribes the invocation without `--discriminator`.
- `bin/.events-registry.md` — the `batch_dispatch` row claiming "idempotent per batch number".
- Evidence: `cortex/lifecycle/lifecycleconfig-template-ships-dormant-skip-specify/events.log` — one `batch_dispatch` row (`batch: 0`) for a feature that dispatched two batches; batch 1 returned invocation id `7a583b8e980e0bad`, identical to batch 0's.
