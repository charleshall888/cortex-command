---
schema_version: "1"
uuid: a5d0a0c4-933c-4a6a-acfa-84bdd39aabba
title: 'Trim the interactive implement loop''s orchestration overhead: report round-trips, batch barriers, flat model tiering'
status: backlog
priority: medium
type: chore
created: 2026-07-18
updated: 2026-07-18
tags: ['lifecycle', 'skills', 'token-efficiency', 'subagents']
areas: ['skills', 'lifecycle']
---
## Why

A 25-task interactive lifecycle implement (wild-light #353, 2026-07-17/18, ~28 agent dispatches
across 9 batches plus a rework cycle) paid a measurable slice of its wall-clock to the
orchestration layer this repo owns, not to builds or verification. The observed costs, each an
instance pointing at the harness surface underneath it:

- **Every dispatch ended in two fetch round-trips.** Builders stop as background teammates whose
  idle notification carries no report, and a blocking SubagentStop hook can eat the final message
  outright — so the orchestrator sent "please send your exit report" and waited, ~28 times. The
  root protocol (bare idle pings, stop-hook return-eating) is Claude Code's, but the fix is
  entirely ours: the builder prompt template can mandate delivering the exit report *before*
  stopping. Two #353 agents did exactly that unprompted and their reports arrived with zero
  round-trips.
- **Batch barriers idled ready work.** The implement loop's batches are BSP-style — batch N+1
  waits for all of batch N — so one ~30-minute straggler (a complex registry task) blocked
  sibling-independent tasks whose dependencies were already `[x]`. The plan's dependency graph
  already encodes everything needed to dispatch a task the moment its own deps land.
- **One model tier fits nobody.** `cortex-resolve-model --role builder --criticality high`
  resolved once per feature, so a comment-only trivial task (plan Complexity: trivial) ran the
  same top-tier model — and paid the same stop-hook probe pipeline — as a 5-file architectural
  task. The plan's per-task `Complexity` field exists precisely to drive tiering and the
  overnight pipeline already consumes it; interactive dispatch ignores it.
- **Completions are unobservable.** `implement-transition --mode batch` stamps `batch_dispatch`
  rows, but nothing records when a task *finished* — per-task wall-clock for any future speed
  pass has to be reconstructed from git timestamps and transcripts.
- **The review phase duplicated its most expensive step.** A reviewer's scoped sub-verifier
  expanded into a full second review — including a duplicate ~11-minute full-suite run — and
  nearly clobbered `review.md`; convergence was luck, not design.

## Proposed direction

Land the small, high-leverage prose/verb changes; measure before anything structural:

1. **Builder prompt template** (`skills/lifecycle/references/implement.md`): add a mandatory
   final step — deliver the exit report (status, files, verification outcome, commit hash,
   deviations) via SendMessage to the orchestrator, or write it to
   `cortex/lifecycle/{slug}/task-reports/task-{N}.md`, BEFORE stopping. Report-hijack by a
   blocking stop hook then costs nothing.
2. **Dispatch semantics** (`implement.md` §2): permit dependency-pipelined dispatch — a pending
   task may launch when its own `Depends on` set is `[x]` and its `Files` are disjoint from
   every in-flight task's, without waiting for the rest of the batch. Keep the batch as the
   *recording* unit (`batch_dispatch` is idempotent per batch number) or add a per-task
   dispatch row; either way the checkpoint/commit discipline is unchanged.
3. **Per-task model tiering** (`implement.md` model resolution): resolve the builder model per
   task from (role, criticality, task Complexity) instead of once per feature —
   `cortex-resolve-model` may need a `--complexity` axis; trivial/simple tasks also warrant a
   documented lighter verification posture.
4. **Completion stamps** (wheel: `implement-transition` or a sibling arm + events registry): a
   `task_complete` row (task id, commit sha, ts) so dispatch→complete duration is a first-class
   observable.
5. **Reviewer template** (`skills/lifecycle/references/review.md`): a single-writer rule for
   `review.md` (only the dispatched reviewer writes it; verifier sub-agents return findings as
   messages) and a share-the-tallies convention (the full suite runs once; verifiers consume its
   output, never re-run it).
6. **Plan-authoring conventions** (`references/plan.md` / the P-checklist): (a) hub-file
   guidance — when several tasks would edit one coordinator file, the plan gives it a
   registration seam early so later tasks add files instead of serializing 4-deep edit chains
   (observed twice in #353); (b) evidence-rig dress rehearsal — a task that builds a capture/
   evidence rig must produce and validate a discarded sample of the exact committed-evidence
   shape end-to-end (all three #353 rig defects surfaced only at the real shoot, costing a fix
   round).

## Role

The verification-layer twin of this ticket lives in the consuming project (wild-light #373:
probe dedupe, green-stamp, suite-to-area mapping, known-red battery reconciliation). This ticket
owns what only the harness can change: the templates, the dispatch loop, the model resolution,
and the event schema. After it lands, an interactive implement's per-task overhead is a template
constant, ready tasks never idle behind stragglers, trivial tasks stop paying complex-task
prices, and per-task timing is queryable from `events.log` alone.

## Integration

- The implement and review skill references' dispatch prose and prompt templates are the main
  surfaces; the parity-tested kept-pause inventory is untouched.
- Item 4 touches the wheel (advance arms + the events registry) and therefore the protocol
  parity test; items 1/2/5/6 are prose-only.
- Item 2 must respect the existing same-batch disjoint-`Files` rule — pipelining widens it to
  disjoint-with-all-in-flight.
- Item 3 extends `cortex-resolve-model`'s axis set; the overnight pipeline already reads task
  Complexity for model/turn budgets — reuse that mapping rather than minting a second one.
- Related, same source lifecycle: the `--from-state <detected>` override on `plan-decision` /
  `review-verdict` cleanly cleared two reducer-race gate-mismatches that the refusal text only
  offers the hand-append escape for — worth folding into the refusal message or the loop prose
  as the preferred remedy.

## Edges

- The exit-report file and SendMessage paths must be equivalent in content so the orchestrator
  reads one shape; the report is builder output, never hook output — a blocked stop must not be
  able to replace it.
- Pipelined dispatch must not outrun checkpointing: a task may only flip `[x]` after its commit
  is verified, exactly as today; the plan file stays the single coordination surface.
- Per-task tiering must never downgrade the model for tasks whose Complexity is absent or
  malformed — absent means inherit the feature-level resolution (fail-safe up, not down).
- A `task_complete` event is additive to the events registry and versioned under the same
  protocol range discipline as every other row; consumers treat its absence as "old lifecycle",
  not an error.
- Single-writer for `review.md` must keep the missing-drift-section re-dispatch escape working —
  the rule constrains *who* writes, not the retry protocol.

## Touch points

- `plugins/cortex-core/skills/lifecycle/references/implement.md` — §2 Task Dispatch (batch
  semantics, model resolution) and the Builder Prompt Template.
- `plugins/cortex-core/skills/lifecycle/references/review.md` — §2 Reviewer Prompt Template and
  the §4 missing-drift-section re-dispatch escape.
- `plugins/cortex-core/skills/lifecycle/references/plan.md` — authoring rules (hub-file seam,
  dress-rehearsal convention) + `orchestrator-checklist-plan.md`.
- `cortex_command/lifecycle/` advance arms + `bin/.events-registry.md` — the `task_complete`
  row (item 4) and the `--from-state` refusal-message note.
- `cortex-resolve-model` — the per-task Complexity axis (item 3).
- Timing basis: wild-light #353 implement, 2026-07-17/18 — 25 tasks + 1 rework cycle, ~28
  dispatches, 9 batches; twin ticket wild-light #373 owns the verification layer.
