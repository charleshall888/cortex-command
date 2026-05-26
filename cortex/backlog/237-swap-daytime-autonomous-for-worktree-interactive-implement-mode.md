---
schema_version: "1"
uuid: 9de0e122-b600-41b0-8519-838148d36617
title: "Swap daytime autonomous for worktree-interactive implement mode"
status: complete
priority: high
type: epic
created: 2026-05-18
updated: 2026-05-26
tags: [lifecycle, worktree-interactive, daytime-swap, epic]
areas: [lifecycle, skills, pipeline, overnight-runner]
discovery_source: cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md
session_id: null
lifecycle_phase: wontfix
lifecycle_slug: null
---

# Epic: Swap daytime autonomous for worktree-interactive implement mode

## Role

Reshape the lifecycle implement-phase preflight by replacing "Implement in autonomous worktree" (daytime SDK pipeline) with a new "Implement on feature branch with worktree" option that runs interactively in the active Claude Code session and ends with a PR. Bare "Create feature branch" coexists; overnight pipeline is unchanged. Per the post-critical-review user resolution of DR-7, the swap also cancels in-flight tickets `#228` and `#230` — daytime autonomous goes away regardless of `#228`'s near-readiness because the swap is committed on user preference. Decompose targets Variant A (active session `cd`s into the worktree).

## Integration

Top-level coordinator. Five children break the work into ticketed pieces: preflight menu shape, worktree lifecycle (creation + cleanup), Variant A end-to-end (interaction model + PR-creation hook), bidirectional concurrency guards (per-feature lock + overnight rejection mirror + inverse-direction overnight guard), and the daytime-autonomous removal sweep. The daytime-autonomous removal must land after the new interactive mode is functional to avoid leaving the lifecycle without an autonomous-equivalent path; the menu update must land before the removal sweep to avoid stale references. Resolves the wontfix architectural answer named in `#135` (shared-git-index race) for the interactive path.

## Edges

- Bound by the lifecycle implement-phase preflight contract: menu options route by user selection, each option owns its own dispatch path.
- Bound by the worktree-creation primitive's sandbox-safe-path contract: canonical path resolution via `cortex-worktree-resolve`; `.claude/settings.local.json` copy and `.venv` symlink semantics from `create_worktree`.
- Bound by the events.log schema for lifecycle events.
- Bound by the backlog frontmatter schema: cancellation of `#228` and `#230` updates their status with documentation pointing to this discovery as the supersedence record.
- Bound by the project's day/night split contract: daytime is interactive collaboration, overnight is autonomous handoff; this epic preserves that split by removing the daytime-autonomous escape hatch.

## Touch points

- `cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md` — discovery artifact and source-of-truth for architecture.
- `skills/lifecycle/references/implement.md` §1 (menu) and §1a (daytime dispatch alternate path, deleted by `#246`).
