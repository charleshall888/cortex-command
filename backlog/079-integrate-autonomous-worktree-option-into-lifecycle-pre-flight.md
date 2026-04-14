---
schema_version: "1"
uuid: e68ca237-c75d-42fd-830b-ac2fd2245e27
title: "Integrate autonomous worktree option into lifecycle pre-flight"
status: complete
priority: medium
type: feature
created: 2026-04-13
updated: 2026-04-14
parent: "074"
blocked-by: []
tags: [lifecycle, skills, autonomous-worktree]
areas: [lifecycle, skills]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: integrate-autonomous-worktree-option-into-lifecycle-pre-flight
complexity: complex
criticality: high
---

## Scope

User-facing layer that connects the daytime pipeline subprocess (#078)
to the `/lifecycle` implement-phase pre-flight. Adds a fourth pre-flight
option — "Implement in autonomous worktree" — that **co-exists** with
the current single-agent "Implement in worktree" option (DR-2; does not
replace).

## Scope includes

- Update `skills/lifecycle/references/implement.md` pre-flight to offer
  four options with guidance on when to pick which (small / live-
  steerable → single-agent worktree; medium / many-task → autonomous
  worktree; trunk-based → main; PR-flow → feature branch)
- Main-session invocation protocol: shell out to the #078 CLI, pass
  spec / plan / complexity / criticality / base-branch / test-command /
  main-CWD events-log path; block on subprocess exit
- Result surfacing: on success show summary + PR URL; on deferred
  surface `lifecycle/{feature}/deferred/*.md` interactively; on failure
  show last N events + retry guidance
- Worktree prefix decision: `worktree/agent-*` (inherits existing
  cleanup hook + potential race) vs. new `worktree/daytime-*` (requires
  hook update, avoids race). Pick one; apply consistently
- `.dispatching` marker replacement: flock on lock file, PID file with
  liveness check, or named lock — pick one and implement the
  double-dispatch guard
- Concurrent daytime + overnight guard: pre-flight check that fails
  fast if overnight is active on the same repo; avoids two pipelines
  racing `git merge` to `main`
- Skill-level behavior tests for the four-option decision tree;
  integration test that the skill correctly invokes the #078 CLI with
  expected args

## Scope excludes

- Subprocess internals, failure recovery, event logging mechanics
  (those are #078)
- Changes to `batch_runner.py` / `orchestrator.py` / `feature_executor.py`
  / `outcome_router.py` (those are #075–#077)
- Morning report changes

## Acceptance

- Users invoking `/lifecycle implement` on a refined feature see four
  pre-flight options with clear guidance
- Selecting autonomous worktree launches the #078 subprocess; main
  session surfaces results correctly for success / deferred / failure
- Cleanup hook handles the chosen worktree prefix without racing a
  running subprocess
- Double-dispatch is prevented (second `/lifecycle implement` on the
  same feature during an active autonomous run is rejected with a clear
  message)
- Starting autonomous worktree while overnight is running is rejected
  with a clear message

## Research Context

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`,
DR-2 (co-exist, not replace), and the "Open Questions" section
covering worktree prefix / cleanup race / `.dispatching` replacement /
concurrent daytime+overnight guard. Each of those is resolved in this
ticket's spec phase.
