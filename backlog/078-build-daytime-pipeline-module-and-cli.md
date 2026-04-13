---
schema_version: "1"
uuid: fe080031-8f44-4b19-8681-63f9b54accc0
title: "Build daytime pipeline module and CLI"
status: backlog
priority: medium
type: feature
created: 2026-04-13
updated: 2026-04-13
parent: "074"
blocked-by: ["076"]
tags: [lifecycle, overnight-runner, daytime-pipeline, autonomous-worktree]
areas: [lifecycle, overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
---

## Scope

Build a single-feature daytime pipeline that reuses the decomposed
orchestration modules. New module `claude/lifecycle/daytime_pipeline.py`
plus CLI entry point
`python3 -m claude.lifecycle.daytime_pipeline`. Consumes
`feature_executor.execute_feature` and
`outcome_router.apply_feature_result` from the refactored overnight
modules; does not duplicate orchestration glue.

## Scope includes

- Module + CLI entry point mirroring `batch_runner.py`'s argparse +
  `asyncio.run()` pattern
- Events.log written to main repo's working tree, **not** the daytime
  worktree (DR-3 — avoids the TC8 pattern)
- Per-feature `lifecycle/{feature}/deferred/` for ambiguity surfacing
  instead of shared `lifecycle/deferred/` (DR-4 — avoids morning-report
  collision)
- Subprocess lifecycle: PID file, orphan prevention (parent-death
  handling), and mid-merge SIGKILL recovery protocol
- Budget caps and `_ALLOWED_TOOLS` for daytime agents (decide same as
  overnight, or differ — spec resolves)
- Brain-triage behavior for daytime: inherit, simplify, or skip (spec
  resolves; currently no agreed default)

## Scope excludes

- Skill pre-flight integration (that's #079)
- Changes to overnight behavior (regression expectation: zero)
- Morning report changes

## Acceptance

- CLI invocation runs a single feature end-to-end in an isolated
  worktree and merges on success, matching the test-gate + auto-revert
  behavior of overnight
- Deferred features produce a file in
  `lifecycle/{feature}/deferred/`; main session can read these files
- Events.log entries are written to the main repo's CWD and readable by
  the invoking process immediately
- Subprocess cleans up its worktree + branch on exit (success or
  failure); orphaned state is recoverable
- Unit tests for the driver logic (mocking feature_executor /
  outcome_router); manual acceptance test on a small real feature

## Research Context

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`,
especially DR-3 (events.log placement), DR-4 (per-feature deferred
namespacing), and the "Open Questions" section on subprocess lifecycle.
Several design decisions are explicitly left to this ticket's spec phase.
