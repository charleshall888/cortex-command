---
schema_version: "1"
uuid: b6555b1a-1b0b-402f-b821-38e9e7cfa466
title: "Remove single-agent worktree dispatch and flip recommended default to current branch"
status: refined
priority: medium
type: feature
created: 2026-04-20
updated: 2026-04-22
parent: "93"
blocked-by: []
tags: [lifecycle, preflight, worktree, cleanup]
discovery_source: research/revisit-lifecycle-implement-preflight-options/research.md
areas: [skills,lifecycle,hooks]
session_id: 0a9a2798-939a-401c-8175-f9d2de6bc64c
lifecycle_phase: implement
lifecycle_slug: remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch
complexity: complex
criticality: high
spec: lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md
plan: lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/plan.md
---

# Remove single-agent worktree dispatch and flip recommended default to current branch

Reshapes the implement-phase pre-flight from four options to three by removing the single-agent `Agent(isolation: "worktree")` path entirely, and promotes "Implement on current branch" to the recommended default (behind the guard added in #096).

## Findings from discovery

Research's DR-1 recommended *demote* option 1 based on thin evidence:

- 1 observed successful dispatch in event logs (`devils-advocate-smart-feedback-application`, 2026-04-12, merged in 8 min).
- Retro corpus documents failure modes but is a negative-signal instrument — cannot distinguish "unused" from "used successfully."
- Live-steerability (DR-2 of epic #074) unused in retros, but retros don't capture successful steering either.

**User override** (post-decomposition review): remove option 1 entirely rather than demote. Rationale: preserving scaffolding for a feature with thin usage evidence incurs maintenance cost (TC8 events.log divergence, AskUserQuestion sharp edge, `§1a` verbatim prompt, `.dispatching` marker, cleanup-hook coordination) without offsetting benefit. Mitigation for the "medium feature that wants inline review" niche: option 4 (create feature branch) provides PR-based workflow without the inner-agent context ceiling.

This ticket therefore implements *removal*, not demotion. It reverses epic #074's DR-2 (co-exist) explicitly.

## Research Context

See `research/revisit-lifecycle-implement-preflight-options/research.md` DR-1 and Trade-offs section. Also see `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md` for the original epic #074 rationale being reversed.

## Acceptance

- Pre-flight in `implement.md §1` presents three options instead of four: "Implement on current branch" (recommended, guarded per #096), "Implement in autonomous worktree", "Create feature branch".
- `implement.md §1a` (Worktree Dispatch alternate path, ~80 lines covering the verbatim prompt, state-write boundaries, `.dispatching` marker semantics, TC8/AskUserQuestion known limitations) is deleted in full.
- `implement.md §1` routing logic no longer references §1a.
- Associated scaffolding is audited and removed: `hooks/cortex-cleanup-session.sh` `worktree/agent-*` handling; SKILL.md Step 2 "Worktree-aware phase detection" sub-section if specific to §1a; SKILL.md Step 2 "Dispatching Marker Check" sub-section if specific to §1a (keep if still used by the autonomous worktree path).
- Option 3 ("Implement on current branch") is the recommended default when the #096 guard does not fire.
- Epic #074's backlog or research artifacts receive a decision-drift note recording the reversal.

## Out of scope

- Changes to option 2 (autonomous worktree / daytime pipeline) behavior — that's #094 and #095.
- The uncommitted-changes guard itself — that's #096.
- Criticality-aware demotion of option 3 (deferred).

## Spec-phase decisions

- Whether to keep the `.dispatching` marker logic for future reuse or delete it along with §1a.
- Where to record the epic #074 DR-2 reversal (decomposed.md of the old epic? a top-level drift note?).
- Whether to remove `worktree/agent-*` branch cleanup logic immediately or keep it as a belt-and-suspenders measure for any stale state left from prior option-1 invocations.
