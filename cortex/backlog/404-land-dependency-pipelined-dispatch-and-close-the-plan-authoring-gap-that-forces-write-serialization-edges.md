---
schema_version: "1"
uuid: 70a333c2-71bc-45ad-8a9c-a8ca561b7876
title: Land dependency-pipelined dispatch and close the plan-authoring gap that forces write-serialization edges
status: complete
priority: medium
type: chore
created: 2026-07-20
updated: 2026-07-20
tags: ['lifecycle', 'skills', 'subagents', 'scheduling']
areas: ['skills', 'lifecycle']
lifecycle_phase: complete
lifecycle_slug: land-dependency-pipelined-dispatch-and-close
complexity: complex
criticality: high
spec: cortex/lifecycle/land-dependency-pipelined-dispatch-and-close/spec.md
---
## Why

#401 item 2 (dependency-pipelined dispatch) was scoped out; its review confirms the deferral.
`implement.md` still reads "Batch N+1 waits for batch N" (:136) and "**c. Wait** — all batch
tasks finish before proceeding" (:62). wild-light #358 (24 tasks, 2026-07-20) now supplies the
cost data #401 lacked — three schedules over the same plan, using observed per-task durations:

| schedule | makespan |
|---|---|
| level-batched (current prose) | 142 min |
| dependency-driven, same graph | 135 min |
| dependency-driven, minus one authored edge | **99 min** |

The barrier itself costs ~5%. **A single plan edge cost ~27%** — and `plan.md` is what told the
author to write it.

`plan.md`:86 instructs: same-file writes race, so "give them disjoint `Files`, or **serialize with
an explicit edge**." The hub-file seam rule (:84) that would have avoided this fires only at "≥3
tasks". #358's collision was exactly 2 tasks on `night_rig.gd` (12, 16) and 2 on `main.tscn`
(8, 16) — under the threshold, so the prescribed remedy was the edge. That edge (`16 ← 12`) is
not a logical dependency; it chained two independent phases and is the entire 135→99 delta.

Root cause of needing the edge at all: trunk mode means one shared working tree, so same-file
tasks cannot run concurrently. Trunk mode was forced because
`cortex-lifecycle-picker-decision` returned `{"fire": true, "reason": "dirty_tree"}` (concurrent
sessions had left backlog files uncommitted), and a dirty tree **hides the worktree option** —
the isolation that dissolves write-serialization edges is withdrawn exactly when concurrent
sessions make it most valuable. Nothing at approval time connects that choice to its cost three
phases later.

## Role

Land #401 item 2, and close the plan-authoring gap that makes it necessary: authors currently
have no way to express "these tasks conflict on a file but are not dependent," so the only
available tool is the wrong one.

1. **`implement.md` Task Dispatch** — permit dependency-pipelined dispatch: a pending task launches when its
   own `Depends on` set is `[x]` and its `Files` are disjoint from every *in-flight* task, without
   waiting for the batch. Keep the batch as the recording unit. (#401 item 2, verbatim.)
2. **`plan.md` authoring rules** — (a) drop the hub-file seam threshold from ≥3 to ≥2, or restate
   it as "any file two tasks would both edit"; (b) require write-serialization edges to be marked
   as such (they are dissolvable by isolation; logical edges are not); (c) add a graph-shape
   check — #358 had 11 topological levels for 24 tasks with four single-task levels where the
   whole fleet stalls on one agent.
3. **Post-plan checklist** — add a width item: flag a plan whose critical path is a large fraction
   of total tasks, the same way P1 flags oversized tasks.
4. **Picker guidance** — reconsider the dirty-tree worktree suppression, or surface the tradeoff
   at the approval surface ("worktree unavailable → same-file tasks will serialize"). A dirty tree
   caused by *other sessions* is the strongest argument for isolation, not against it.

## Integration

- **Worktree merge-back is per-BATCH and therefore reinforces the barrier.** `merge-back.md` runs at
  the Worktree Integration step "so later batches' worktrees branch from the updated HEAD and see prior batches' changes."
  Pipelined dispatch needs per-TASK merge-back, or worktree mode silently re-imposes the very
  synchronization item 1 removes. Decide this alongside item 1 — they are one mechanism, not two.
- **Measure the worktree entry cost before recommending it as a default.** A fresh worktree carries no
  `.godot`, so a Godot consumer reimports from scratch (wild-light: 205MB of imported assets). If that
  is 1-3 min per agent against ~12 min tasks it is 10-25% overhead, which changes when isolation is
  worth it. Unmeasured today.

- Item 1 is the unlanded half of #401; items 2-4 are its plan-side complement and are prose-only.
- Item 1 must respect the existing same-batch disjoint-`Files` rule — pipelining widens it to
  disjoint-with-all-in-flight, which is exactly what makes the marked edges from item 2 safe to
  drop.
- Checkpoint/commit discipline is unchanged: a task flips `[x]` only after its commit verifies.

## Edges

- A write-serialization edge must still be honoured under trunk mode; marking it only permits the
  dispatcher to ignore it when isolation is actually in effect. Dropping it unconditionally
  reintroduces the race.
- Graph-width guidance must not push authors to merge tasks to reduce level count — that trades a
  scheduling problem for an oversized-task problem (P1).
- Threshold change at `plan.md`:84 is authoring guidance, not a gate; it must not fail an
  otherwise-sound plan.

## Touch points

- `plugins/cortex-core/skills/lifecycle/references/implement.md` — §2 Task Dispatch, Constraints.
- `plugins/cortex-core/skills/lifecycle/references/plan.md` — authoring rules (:84 hub-file seam,
  :86 same-file remedy).
- `plugins/cortex-core/skills/lifecycle/references/orchestrator-checklist-plan.md` — width item.
- `cortex-lifecycle-picker-decision` / `worktree-entry.md` — dirty-tree suppression policy.
- Evidence: wild-light #358 implement, 2026-07-20 — 24 tasks, 11 levels, measured 142/135/99 min.
  Predecessor: #401 (items 1/3/6a landed; item 2 deferred).