---
schema_version: "1"
uuid: 7ed502f8-399b-40c1-8cde-603c9cbf82fd
title: "Decompose batch_runner and enable daytime autonomous-worktree pipeline"
status: backlog
priority: medium
type: epic
tags: [lifecycle, overnight-runner, worktrees, multi-agent, refactor, modularization]
areas: [lifecycle, skills, overnight-runner]
created: 2026-04-13
updated: 2026-04-13
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
---

## Framing (post-discovery)

This epic started with a single user-facing goal: add a daytime
autonomous-worktree pipeline option to `/lifecycle` that reuses
overnight primitives, to escape the TC4 context-exhaustion ceiling on
the current single-agent worktree path.

Discovery found a bigger structural opportunity behind that goal:
`batch_runner.py` (2198 LOC, no dedicated unit tests) mixes three
distinct architectural layers — session coordination, per-feature
execution, and outcome routing. Decomposing that file along its natural
seams is justified on overnight's own maintainability and testability
grounds, *and* makes the daytime pipeline a cheap consumer rather than
a duplicated code path.

The epic is therefore scoped as a five-phase refactor + integration:
Phases 1–3 decompose overnight; Phase 4 builds the daytime pipeline as
a thin consumer; Phase 5 integrates it into the lifecycle skill
pre-flight.

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`
for the full analysis, responsibility map, decision records, and
alternatives considered.

## Children (5 phases)

1. **#075** — Extract `feature_executor.py` from batch_runner.py
2. **#076** — Extract `outcome_router.py` from batch_runner.py
   (blocked-by 075)
3. **#077** — Rename batch_runner.py → `orchestrator.py`, thin CLI
   wrapper, integration tests (blocked-by 076)
4. **#078** — Build daytime pipeline module + CLI (blocked-by 077)
5. **#079** — Integrate autonomous worktree option into lifecycle
   pre-flight (blocked-by 078)

## Original problem (preserved for context)

The current `/lifecycle` implement-phase pre-flight offers three
branch-selection options:

1. Implement in worktree (recommended, ships today)
2. Implement on main
3. Create feature branch

Option 1 dispatches the entire implement → review → complete cycle to a
single `Agent(isolation: "worktree")` call. An empirical probe confirmed
the inner agent has no `Agent` tool, no `AskUserQuestion`, and no Task
tools — it is physically constrained to sequential inline per-task
dispatch inside one conversation. Context exhaustion is inevitable for
features with many tasks (TC4 in the shipped spec). The shipped feature
is correct for small/medium features but does not scale.

The overnight pipeline already solves per-task fresh context with
`batch_runner.py` + `dispatch.py`: a Python orchestrator (no context
window) dispatches per-task Claude agents via `claude_agent_sdk.query()`
with hard turn/budget limits, then dispatches a post-merge review agent
via `review_dispatch.py`. The core primitives are standalone.

## Proposed direction (original)

Replace the single-agent "Implement in worktree" option with an
**autonomous worktree** option that reuses overnight pipeline primitives
as a single-feature pipeline — essentially a "mini overnight session"
for one feature, invoked from a daytime `/lifecycle` session.

Three pre-flight options would become:

1. **Implement on current branch** — trunk-based; matches today's
   "Implement on main" semantics
2. **Create feature branch and implement there** — explicit branch
   checkout for PR workflow; main session changes branch (matches
   today's "Create feature branch" with its `git checkout` warning)
3. **Implement in autonomous worktree** — new; dispatches the feature
   through a pipeline-style orchestrator that uses overnight's
   per-task dispatch, post-merge review, and test-gated merge

Goals for option 3:
- Per-task fresh context (no TC4)
- Hard turn/budget ceilings per task
- Post-merge review agent (better than inline review)
- Test-command gate with auto-revert on failure (already exists in
  `merge.py`)
- Main session never changes branch — all work in the worktree
- Progress surfaced to the main session via event log / state file
- No morning report — single-feature daytime invocation; result
  surfaces directly back to the main session when done

## What /discovery must determine

Research should focus on **viability and complexity**, not jump to
implementation. Key questions:

### Architectural fit

1. Which overnight primitives can be reused cleanly as-is vs. which
   require refactoring? Concretely: `dispatch_task()`,
   `dispatch_review()`, `merge_feature()`, `retry_task()`,
   the test-gate + auto-revert logic in `merge.py`
2. What session-level machinery (ConcurrencyManager, escalations.jsonl,
   strategy.json, morning report, round loop) is irrelevant and must
   NOT come along? Is the boundary between "pipeline primitives" and
   "session orchestration" clean enough to extract?
3. How does this interact with the existing session state files
   (`overnight-state.json`, `overnight-strategy.json`,
   per-session event log)? Do we need a mini-session concept, or can
   we run without one?
4. What's the right entry point — a new Python CLI
   (`implement-autonomous-feature`?), a shared library call from a
   lifecycle hook, or something else?

### Communication back to the main session

5. How does the main Claude session learn about progress? Tail
   `events.jsonl`? Poll a status file? Wait synchronously for the
   subprocess to exit and read final state?
6. What does the main session show the user during the run? A summary
   on completion only, or live task-level progress?
7. How are escalations surfaced? The overnight pipeline uses
   `escalations.jsonl` with an orchestrator-resolved loop. For
   daytime single-feature, what happens when the inner pipeline hits
   an ambiguity — does the main session prompt the user, or does the
   pipeline defer/fail the feature like overnight does?

### Permission and interactivity

8. Overnight runs `bypassPermissions`. The current "Implement in
   worktree" accepts this. Is that the right call for autonomous
   worktree too? What tools does the per-task agent need beyond
   `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`?
9. If the inner pipeline needs to ask the user something mid-run,
   what's the protocol? (Probably: it cannot; escalate or defer like
   overnight does.)

### Complexity and brittleness

10. How much new code does this require vs. refactoring existing code?
    What's the risk of refactoring `batch_runner.py` to separate the
    pipeline core from session machinery? Does overnight still work
    after the refactor?
11. What happens if the pipeline fails partway — is the worktree
    recoverable? Can the user inspect what went wrong and continue?
    How does this interact with `cortex-cleanup-session.sh`?
12. Does this create a third path that competes with overnight? When
    should a user pick "autonomous worktree" vs. "queue for
    overnight"? If the answer is always "queue for overnight if it's
    large," does the autonomous worktree option pay for its own
    complexity?
13. What tests would this need? Integration testing a mini pipeline
    is expensive — is there a cheaper way to verify correctness?

### Scope

14. Does option 3 REPLACE the current "Implement in worktree" or
    co-exist with it? If it replaces, what's the migration path for
    any docs/skills/callers referencing the single-agent path? If it
    co-exists, why?
15. How does this interact with backlog item #073 (documenting
    overnight pipeline)? Should #073 be a blocker so the refactor
    targets a known shape, or should they proceed in parallel?

## Out of scope for this epic

- Morning report changes — autonomous worktree is daytime-only
- Multi-feature daytime sessions — single feature per invocation
- Overnight behavior changes — overnight continues working as today

## Success criteria for discovery

A decomposed backlog of child tickets (or a decision to shelve the
epic) with enough confidence to answer: is this worth building, and
if so, what's the shape of the work?
