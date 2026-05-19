---
schema_version: "1"
uuid: 6c945638-4fc4-4f1b-ad68-1c1e102c24b4
title: "Lifecycle implement: auto-enter worktree via EnterWorktree (Approach A, deferred design surface)"
status: backlog
priority: medium
type: feature
created: 2026-05-19
updated: 2026-05-19
tags: [lifecycle, worktree-interactive]
areas: [skills]
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

## Problem

Approach A — mid-session auto-enter of the `interactive/{slug}` worktree via the platform `EnterWorktree(path=...)` tool — was deferred from the `lifecycle-implement-auto-enter-worktree-drop` lifecycle (the per-repo `branch-mode: worktree-interactive` default, "Approach C"). ADR-0004 (amended in commit `93654e07`) records the C/A split framing and forward-references this ticket by slug `lifecycle-implement-auto-enter-worktree-deferred`.

A's deferred design surface comprises one genuine platform-side constraint plus a small set of cortex-side scoping decisions. This ticket captures both so the next refinement cycle can decompose A and ship it incrementally — the framing is **"decompose A's design surface and ship,"** not "wait for upstream."

## Deferred design surface

### (1) Platform-side constraint

**`ExitWorktree` cross-session no-op interacting with same-session Complete-phase re-invocation.** Per the live tool schema, `ExitWorktree` is a no-op for worktrees created outside the current session. When the multi-step Complete phase re-invokes in the same session that auto-entered the worktree, the Step 8 hard guard refuses to run from inside the worktree — but `ExitWorktree` cannot programmatically restore an out-of-worktree CWD in that case. The interaction model between auto-enter (which keeps the session inside the worktree across the implement → review → complete sequence) and the Complete-phase hard guard needs an explicit decision: either restructure the Complete-phase teardown to not require an outside-worktree CWD, or document a session-boundary at which the user is expected to exit the worktree before Complete fires.

This is a cortex-side decision (we choose the interaction model) anchored on a real platform constraint (we cannot make `ExitWorktree` exit a worktree it didn't create this session).

### (2) Cortex-side scoping decisions

**(2a) `cortex init` opt-in clause for consumer-repo `EnterWorktree` authorization.** The platform tool's gating rule requires `EnterWorktree` to be authorized either by explicit user instruction or by `CLAUDE.md` / memory. For the lifecycle skill to call `EnterWorktree` automatically, consumer repos need a documented authorization shape. The deferred decision: should `cortex init` write a clause into the consumer's `CLAUDE.md` (or a sibling memory file) authorizing the lifecycle skill to call `EnterWorktree` for `interactive/{slug}` paths it just created? Or should the user's branch-picker selection itself carry sufficient explicit-instruction authorization without a persisted clause? The opt-in shape, write-path, and rollback story all need to be decided.

**(2b) WorktreeCreate-hook bypass interaction with auto-enter.** ADR-0004's permanent-bypass clause documents that the WorktreeCreate hook is bypassed for the lifecycle skill's interactive-worktree path (the hook's interactive prompts would deadlock the orchestrator). Auto-enter via `EnterWorktree` happens immediately after `create_worktree` returns; the deferred decision is whether auto-enter inherits the bypass cleanly or introduces a new interaction surface that the bypass clause needs to be expanded to cover.

## Acceptance criteria for `status: refined`

Move this ticket to `status: refined` when both of these decisions are documented (project-scope, cortex-only — no upstream dependency):

1. **Cross-session-exit interaction model.** A documented decision (in the refinement-phase spec or an ADR amendment) recording how auto-enter composes with the Complete-phase hard guard given `ExitWorktree`'s cross-session no-op semantics.
2. **Consumer-repo authorization shape.** A documented decision (same scope) recording whether `cortex init` writes a `CLAUDE.md` clause, the user's picker selection carries authorization implicitly, or some hybrid — including the rollback / uninstall story.

## Cross-references

- This lifecycle's spec: `cortex/lifecycle/lifecycle-implement-auto-enter-worktree-drop/spec.md` (R8 defines this ticket's frontmatter shape; R7 records the ADR amendment).
- ADR-0004 amendment recording the C/A split framing: commit `93654e07` (Task 9 of the lifecycle-implement-auto-enter-worktree-drop feature), section `## branch-mode default (Approach C) + Approach A deferred design surface` in `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md`.
- Parent ticket (the C lifecycle that shipped first): `cortex/backlog/249-lifecycle-implement-auto-enter-worktree.md`.
