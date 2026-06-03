---
schema_version: "1"
uuid: 0048a013-cb5c-4149-b7fd-0bb8b3c2ef91
title: "Lifecycle implement: auto-enter worktree, drop the cd handoff"
status: complete
priority: medium
type: feature
created: 2026-05-19
updated: 2026-05-19
tags: [lifecycle, worktree-interactive, ux]
areas: [skills]
session_id: null
lifecycle_phase: research
lifecycle_slug: lifecycle-implement-auto-enter-worktree-drop
complexity: complex
criticality: high
spec: cortex/lifecycle/lifecycle-implement-auto-enter-worktree-drop/spec.md
---

> **Reconciliation (ADR-0008):** Auto-enter via `EnterWorktree` survives on the picker-fired path. The "Authorization framing" open question below is now answered — the user's live picker selection carries the authorization, with no persisted `CLAUDE.md` clause (the fence model ADR-0006 introduced was removed by ADR-0008). Frontmatter status unchanged.

## Problem

When the lifecycle implement phase offers the worktree-interactive option (`skills/lifecycle/references/implement.md` §1 / §1a), the user-visible flow today is:

1. The 3-option branch picker fires (`Implement on current branch` / `Implement on feature branch with worktree` / `Create feature branch`) — a conscious re-decision per feature.
2. After picking the worktree option, the skill creates the `interactive/{slug}` worktree at `$TMPDIR/cortex-worktrees/interactive-{slug}/` and prints a handoff message offering two continuation paths: **Variant A** (`cd {path}` and re-invoke `/cortex-core:lifecycle`) or **Variant B** (`claude --worktree={path}` in a fresh session).
3. The user types one of those two continuations themselves and the implement phase resumes inside the worktree.

The friction shaped real behavior: feature #246 (a 25-commit removal sweep that would have benefited from worktree isolation for parallel batches) ran entirely on trunk because the worktree path felt heavier than the work warranted. The cognitive interruption is the branch picker; the literal-keystroke cost is the cd handoff.

## Desired UX

Lifecycle implement enters the worktree seamlessly when worktree-interactive mode is the right answer. Concretely:

- No conscious "which branch" re-decision per feature when the repo has a configured default.
- No `cd {path}` step or `claude --worktree=` relaunch — the same Claude session continues inside the worktree.
- No A/B variant copy in the handoff message because there is no handoff to make.
- The implement-phase orchestrator and its builder sub-tasks all operate from within the worktree as if the user had `cd`'d there at session start.
- Trunk-safe overrides remain reachable for tiny fixes that don't warrant a worktree.

## Why it matters

The current friction silently nudges users toward implementing on trunk. That undermines the design intent of the worktree-interactive flow — protecting trunk and giving parallel batches index-safe isolation — which is the entire reason the daytime autonomous pipeline was retired in #246. If the replacement flow has enough friction that it gets skipped, the retirement bought less than intended.

The lever is small. Removing the cd handoff and defaulting the branch mode for repos that want worktree-interactive as the daytime default would make the worktree flow the path of least resistance for the common case, with explicit override for the exceptions.

## What is known

Anthropic's Claude Code platform ships an `EnterWorktree` tool that switches a running session's working directory into an existing worktree mid-conversation. Passing `path=<existing-worktree-path>` enters a worktree the skill has already created (`cortex_command.pipeline.worktree.create_worktree` is the existing helper). The tool's gating rule — "use only when explicitly instructed by the user or by CLAUDE.md / memory" — is satisfied by the user choosing the worktree branch option (or by a documented project-level authorization for the lifecycle skill).

`ExitWorktree` provides the symmetric teardown for session cleanup without removing the worktree branch.

## Open questions for research / spec

These are not prescriptions — research should decide. Surfacing them so the next phase knows what to chase:

- **Branch-mode default**: is a `lifecycle.config.md` field like `branch-mode: worktree-interactive` the right shape? Per-repo only, or per-feature override via backlog frontmatter? What's the trunk-safe escape hatch when the default doesn't fit a tiny fix?
- **Authorization framing**: should the project-level CLAUDE.md authorize the lifecycle skill to call `EnterWorktree`, or should the user's explicit picker selection carry the authorization on its own? What's the cleanest way to satisfy the platform tool's gating rule without ceremony?
- **Session state implications**: `EnterWorktree` reloads CWD-dependent caches (system prompt sections, memory files, plans directory). What breaks if the worktree's `.claude/settings.local.json` differs from the main repo's? Does the existing copy step in `create_worktree` already handle this, or does it create a settings-drift surface?
- **Phase composition**: implement phase enters the worktree, but research/spec/plan ran in the main tree. Is the right model "enter at implement, exit at complete"? Or earlier? What happens if the user resumes a partially-implemented feature — is the worktree re-entered or treated as fresh?
- **Complete-phase teardown**: today's complete-phase Step 8 cleanup runs from outside the worktree (the hard-guard refuses to run from inside). If the session is auto-entered, the user has to `ExitWorktree(action="keep")` before complete-phase cleanup. Does the skill orchestrate that itself, or is there still a user-facing exit step?
- **Backwards-compatibility**: what happens to in-flight lifecycles that already created an `interactive/{slug}` worktree under the old Variant A/B model? Can the auto-enter path resume into a worktree from a prior session, or does the existing-worktree case need its own handling?
- **Variant B preservation**: is the fresh-session `claude --worktree=...` path still useful for any case (e.g., true conversational isolation), or does auto-enter subsume it cleanly?

## Non-prescription

This ticket deliberately does not specify *how* implement.md changes. The research/spec phase should weigh the open questions above and propose a shape. The platform tool exists; the rest is design.

## Cross-references

- Parent retirement that motivated the replacement: #237 (epic) → #246 (this PR's removal sweep).
- Siblings that delivered the current worktree-interactive flow: #238 (menu integration), #240 (variant-A end-to-end).
- Active lifecycle on a related design surface: `shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits` — auto-enter into a per-feature worktree reduces this surface for daytime work.
