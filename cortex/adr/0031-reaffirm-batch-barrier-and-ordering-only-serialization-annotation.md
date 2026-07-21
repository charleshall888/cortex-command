---
status: accepted
---

# Reaffirm the batch barrier; adopt ordering-only write-serialization annotation

_Decision date: 2026-07-20 (#404 — dependency-pipelined dispatch evidence review)._

## Context

ADR-0030 deferred dependency-pipelined dispatch until "the upstream dispatch-mode substrate is stable and a measured case survives token accounting." Backlog ticket #404 presented wild-light #358's 142/135/99-minute batch schedule as that measured case, arguing that a mis-drawn dependency edge (task 16 listed as depending on task 12) serialized two independent phases, and that removing it would collapse the plan's DAG depth from 11 levels to 8 and save wall-clock time.

Forensics on the #358 evidence graded it insufficient to clear ADR-0030's bar:

- The 142/135/99-minute schedule comparison rests on a single mid-run simulation, not a completed or repeated run.
- Real per-task durations are available for only 12 of the 24 tasks; the remaining 12 are placeholders, and those placeholders are concentrated in exactly the tasks the disputed edge moves — the batches whose timing the simulation is trying to prove.
- The run cited was 54% complete at the point the numbers were captured.
- The artifact the numbers were drawn from is no longer on disk, so the claim cannot be independently re-verified.

What the forensics did confirm, and what survives as a structural fact independent of the contested timing numbers: the disputed edge — task 16's `Depends on: [12]` — was not a logical dependency but an undeclared same-file write-serialization edge, and removing it cuts the plan's DAG depth from 11 levels to 8. That fact says the #358 plan was over-serialized by one honest conflict mislabeled as a fake logical dependency; it does not say pipelined dispatch would help wall-clock time by any measured amount.

## Decision

**Re-affirm ADR-0030's batch barrier.** Batch N+1 still waits for batch N; no in-flight Files-disjointness gate, no per-task dispatch/completion events, no `implement.md` §2 semantics change. The #358 evidence does not clear the bar ADR-0030 set, and every blocker ADR-0030 named is still live (see Preconditions below).

**Adopt the ordering-only write-serialization annotation as the plan-authoring complement.** The structural fact that survives forensics — one honest same-file conflict masquerading as a fake logical dependency — is a plan-authoring gap, not a dispatch-mechanics gap. Authors who need to serialize two tasks that share a file, without asserting a logical dependency between them, now have an honest vocabulary for it: `**Depends on**: [12] (write-serialization: night_rig.gd)`. The annotation carries `mustRunAfter` semantics:

- **Ordering-only, not a logical dependency.** The annotated task must not start before the task it cites completes, but the two tasks do not otherwise constrain each other.
- **Relaxable, never deletable.** A future executor that runs per-task isolation (so same-file writes cannot collide) may relax an annotated edge to a weaker not-before ordering. No executor — present or future — deletes the edge outright; the annotation records author intent that must survive even when its enforcement mechanism changes.
- **A real edge today.** Until such an executor exists, the overnight pipeline and every other consumer treat the annotated edge as an ordinary `Depends on` edge for cycle detection, topological batching, and depth accounting. The annotation changes authoring vocabulary, not dispatch mechanics.

This closes the authoring gap #358 hit — the plan author needed either a disjoint-`Files` remedy or a fake dependency, and reached for the fake dependency because no honest annotated form existed — without touching dispatch.

## Preconditions for revisiting the batch barrier

Any future proposal to relax the batch barrier (pipelined dispatch across batches, or concurrent same-file writes under isolation) must clear all of the following before it is a measured case rather than a repeat of #404:

1. **Durable per-task dispatch/completion events.** Today, per-task completion is derived from the git checkpoint at batch boundaries (ADR-0030); pipelining needs per-task-scoped events that survive session boundaries and crashes, not just batch-scoped ones.
2. **A metrics batch-semantics decision.** `metrics.py` currently assumes batch-shaped timing; pipelining requires a decision about what a "task duration" metric means once tasks overlap in wall-clock time.
3. **A fused per-task checkpoint+merge-back that closes the stale-base window.** Per-batch checkpoint+merge-back (assumed by `merge-back.md`) is safe only because every task in a batch starts from the same committed base. Pipelined dispatch reopens a stale-base window between a task's start and its merge unless checkpoint and merge-back are fused into one atomic per-task step.
4. **An admission policy during the `implement-batch-failure` pause.** The batch barrier gives failure handling a clean boundary — nothing new is admitted once a batch fails. Pipelining needs an explicit policy for what, if anything, is admitted while an earlier task's failure is still being resolved.
5. **A commit-serialization story.** Concurrent per-task commits need a story for ordering and conflict resolution at the commit layer, not just at the file-write layer.
6. **Substrate pinnability.** ADR-0030 already established that the dispatch mode (synchronous vs. background) is runtime-owned and not stably pinnable across the installed base. Pipelining is a mode-dependent orchestration shape; it needs the substrate to be pinnable (or the harness to tolerate both modes without behavioral drift) before it can be written as durable prose.
7. **#39886 mitigation.** This pre-existing, externally-tracked issue must be mitigated before concurrent same-file writes under isolation can be assumed safe. Today's annotation adds no reliance on "isolation is in effect" — its forward relaxation clause stays gated behind this precondition, a deferred dependency made explicit rather than eliminated.
8. **A freshness/re-record story for `plan_approved`'s `dispatch_choice`.** Surfaced by this spec's own review: the `dispatch_choice` field on the `plan_approved` event (introduced by [ADR-0012](0012-merged-plan-approval-and-dispatch-selection.md)) is written by an emitter that is idempotent on event name only — it does not compare the incoming choice against any prior recorded value. A plan-redo pass that changes the dispatch choice is therefore never re-recorded; a consumer reading the row after a redo reads the original, stale choice. Pipelining would ride a second axis (dispatch shape, not just branch mode) on the same field, so this staleness gap must close before the field can be trusted for pipelining decisions either.

## Trade-off

Bounded straggler idling persists — a batch still waits on its slowest task before the next batch starts, mitigated only by straggler isolation at plan-authoring time (graph-width checks, hub-file guidance), not by runtime coordination. In exchange: prose stays correct on every runtime version (per [ADR-0030](0030-mode-agnostic-interactive-dispatch.md)), plans are safe under both the interactive and overnight executors without version-skew hazard, and the change adds zero new coordination machinery. The alternative — building pipelining on evidence graded as a single mid-run simulation with half its data placeholder — would have added real coordination machinery on an unmeasured case.

## Relation to ADR-0030

This ADR reaffirms [ADR-0030](0030-mode-agnostic-interactive-dispatch.md)'s batch barrier and promotes it from `proposed` to `accepted` via an in-file amendment (see ADR-0030's "Reaffirmed by ADR-0031" section) rather than a bare frontmatter flip, per the [ADR-README](README.md) no-content-duplication and promotion-gate conventions. ADR-0030 named the batch barrier and deferred dependency-pipelined dispatch pending "a measured case survives token accounting"; this ADR is the record of that case being presented, evaluated, and found insufficient, plus the concrete preconditions a future case must clear.
