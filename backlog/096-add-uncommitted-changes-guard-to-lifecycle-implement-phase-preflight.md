---
schema_version: "1"
uuid: ceb58ab0-8e34-447d-89ae-dd881c627ab7
title: "Add uncommitted-changes guard to lifecycle implement-phase pre-flight"
status: complete
priority: high
type: feature
created: 2026-04-20
updated: 2026-04-21
parent: "93"
tags: [lifecycle, preflight, trunk-safety]
discovery_source: research/revisit-lifecycle-implement-preflight-options/research.md
areas: [skills]
complexity: simple
criticality: high
spec: lifecycle/add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight/spec.md
session_id: null
lifecycle_phase: complete
---

# Add uncommitted-changes guard to lifecycle implement-phase pre-flight

Prerequisite for flipping the recommended default to "Implement on current branch" (ticket #097). Adds a single guard that demotes the current-branch option when the working tree has uncommitted changes.

## Findings from discovery

Today's pre-flight (`implement.md §1`) has no guards on option 3 ("Implement on main"). The text states "tiny, trunk-safe changes where a branch would be overhead" but this gate is unenforced. Zero trunk-safety incidents in the retro corpus, but the current worktree-first default plausibly suppresses the failure surface rather than eliminates it.

Pattern already exists in `skills/pr/SKILL.md` — checks "No uncommitted changes in working tree" before proceeding. This ticket reuses that pattern.

## Research Context

See `research/revisit-lifecycle-implement-preflight-options/research.md` DR-3. The research rejected a plan-complexity ("≥5 tasks") gate: task count is orthogonal to trunk damage, the threshold is uncalibrated, and the guard would punish decomposed-but-safe work while letting through the actual danger case (one large task on core infra). A criticality-aware demotion was also rejected for first delivery (deferred to a follow-up if incidents occur).

## Acceptance

- Before presenting the pre-flight `AskUserQuestion`, the skill runs `git status --porcelain`.
- If non-empty, the "Implement on current branch" option is demoted: its description prefix includes a one-line warning about the uncommitted state, and it is not the recommended default for this invocation (even after #097 lands).
- The guard does not block selection — the user can still pick the current-branch option knowingly.
- Guard behavior documented in `implement.md §1` alongside the existing worktree-agent context guard.

## Out of scope

- Plan-complexity gate (rejected in research).
- Criticality-aware demotion (deferred).
- Flipping the recommended default (that's #097).
- Modifying the other three options.

## Spec-phase decisions

- Exact warning text surfaced to the user when the guard fires.
- Whether "demote" means reordering in the `AskUserQuestion` list, changing which option is recommended, or both.
