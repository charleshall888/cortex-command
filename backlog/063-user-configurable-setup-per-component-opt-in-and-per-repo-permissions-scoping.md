---
schema_version: "1"
uuid: 5d182b14-ee91-4035-9bfc-7242bc0c2b9f
title: "User-configurable setup: per-component opt-in and per-repo permissions scoping"
status: complete
priority: high
type: epic
tags: [setup, configurability, user-configurable-setup]
created: 2026-04-10
updated: 2026-04-11
parent: null
blocked-by: []
discovery_source: research/user-configurable-setup/research.md
---

# User-configurable setup: per-component opt-in and per-repo permissions scoping

## Context

Today, `just setup` deploys the entire agentic layer wholesale — 26 skills, 13 hooks, full settings.json, all bin utilities. Users who clone or fork cortex-command and only want part of it (e.g., "I want lifecycle but not overnight," "I want commit but not all the review hooks") have no opt-in path beyond manually deleting symlinks post-install. Separately, per-repo permission scoping — "in this specific repo, use project-only permissions, ignore the global allow list" — has no mechanism today; Claude Code's native merge is strictly additive with no negation.

The discovery surveyed the component inventory (80+ opt-in-able units across skills, hooks, bin utilities, heavy components, plugins), mapped hard dependencies into three bands (cleanly optional, moderately coupled, install floor), investigated Claude Code settings layering capabilities (merge is strictly additive; no native per-repo override mechanism), and surveyed prior art across oh-my-zsh, chezmoi, mise, ESLint, git config, direnv, and others.

The minimum viable delivery uses two existing mechanisms: the `/setup-merge` skill (already ships per-category prompts for settings.json sections) for install-time component selection, and Claude Code's documented `CLAUDE_CONFIG_DIR` environment variable combined with direnv for per-repo user-scope swaps. Both paths avoid adding new config files, new mutation layers, or new drift surfaces.

## Scope

- Extend `/setup-merge` to discover skills and hooks dynamically (by scanning `skills/*/SKILL.md`, `hooks/*.sh`, `claude/hooks/*.sh`) and prompt for each individually. Selections written to new `skills:` / `hooks:` sections in `lifecycle.config.md`. Install floor (Band C) merged unconditionally.
- Document the `CLAUDE_CONFIG_DIR` + direnv pattern as the per-repo permissions scoping mechanism. Docs-only deliverable with a short upstream-audit preamble.

## Children

- 064: Extend `/setup-merge` with dynamic per-component opt-in for skills and hooks
- 065: Document `CLAUDE_CONFIG_DIR` + direnv pattern for per-repo permissions scoping

## Out of scope

- New config files beyond the existing `lifecycle.config.md` (DR-2).
- Named bundles (DR-3).
- SessionStart hooks that mutate `~/.claude/settings.json` (DR-1 chose `CLAUDE_CONFIG_DIR` over mutation; DR-8 preserves the real scope if Option D is ever reconsidered).
- Runtime hook guards for per-repo hook disable (deferred — the `CLAUDE_CONFIG_DIR` shadow covers the case technically; build only if friction is proven).
- A `cortex-doctor` diagnostic CLI (deferred — useful once drift surfaces stabilize; premature now).
- A `bin/cortex-shadow-config` generator (deferred — start with docs; build the generator only if manual `cp -r` friction is observed).
- Runtime opt-out for auto-invoked skills like `critical-review` (the `skip-review` flag in `lifecycle.config.md` is "documented but not implemented" per research §1.E; wiring it into the lifecycle review phase is separate runtime work not in scope for this discovery).
- Install-time gating for heavy components beyond skill-scoped bin utilities (the overnight runner, conflict pipeline, and dashboard are not symlinked — they're invoked via bin utilities that #064 handles).
- Global user-level config file capturing install state. The install is the commitment; `lifecycle.config.md` holds the per-project state.

## Research

See `research/user-configurable-setup/research.md` for the full investigation, decision records (DR-1 through DR-8), feasibility assessment, and prior art review.

## Decompose summary

The discovery went through multiple rounds of review before landing on this 2-ticket shape:

- **Research round 1** (rewritten after critical review): original draft deferred the commissioned per-repo permissions use case as "stretch — may not be needed." Rewrite centered it, chose `CLAUDE_CONFIG_DIR` over settings mutation, and dropped the proposed `.cortex/config.md` + named bundles.
- **Decompose round 1**: produced 5 tickets. Critical review flagged priority overload (four items marked `high`), false serialization behind a "gating" audit, Band B dependency resolution recreating bundles by another name, and audit-routing encoded as ticket prose tooling cannot read.
- **Decompose round 2**: expanded to 6 tickets with audit-routing per ticket, split schemas, and a dependency resolver. Devil's advocate flagged that the routing-in-prose problem persisted, the split was over-surgery, and the direnv adoption assumption was untested.
- **Decompose round 3 (this version)**: cut to 2 tickets. The maintainability question ("are we creating something maintainable?") was the decisive lens — the 6-ticket shape had ~6 drift surfaces for one maintainer on a framework under constant churn. Dynamic discovery (scanning `skills/` and `hooks/` at prompt time) eliminates the component manifest. Docs-only for the per-repo mechanism eliminates the generator, the staleness handling, and the direnv-adoption bet. Band B dependency resolution is dropped in favor of the observation that "soft coupling" (e.g., `morning-review` without `overnight`) produces graceful empty-state behavior, not corruption.

The 2-ticket shape delivers both commissioned capabilities with minimal new infrastructure and is the smallest change that honors the project's "complexity must earn its place" principle.
