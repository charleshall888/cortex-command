---
schema_version: "1"
uuid: 237dcafa-b9e4-4eaa-a090-d7c1dba28b9e
title: "Extend /setup-merge with dynamic per-component opt-in for skills and hooks"
status: backlog
priority: high
type: feature
tags: [setup, configurability, user-configurable-setup, setup-merge]
created: 2026-04-10
updated: 2026-04-10
parent: "063"
blocked-by: []
discovery_source: research/user-configurable-setup/research.md
---

# Extend /setup-merge with dynamic per-component opt-in for skills and hooks

## Context from discovery

Today `/setup-merge` handles per-category prompts for settings.json sections (permissions allow/deny, hooks block, sandbox, statusLine, plugins, apiKeyHelper) but not for the skill and hook files themselves — those are deployed wholesale by `deploy-skills` and `deploy-hooks` in the justfile. Users who want only part of the agentic layer have no supported opt-out path.

Research §1.A catalogs 26 skills across four clusters (core dev flow, overnight/review, lifecycle ancillary, UI toolchain) and §1.B catalogs 13 hooks across SessionStart, PreToolUse, PostToolUse, Notification, SessionEnd, and Worktree event types. §2 maps hard dependencies into three bands:

- **Band C (install floor)**: `lifecycle`, `backlog`, `commit`, `dev` skills; `cortex-validate-commit.sh`, `cortex-sync-permissions.py`, `cortex-scan-lifecycle.sh` hooks; `update-item`, `create-backlog-item`, `generate-backlog-index` bin utilities. Cannot be opted out without breaking core workflows.
- **Band B (moderate coupling)**: `overnight`, `morning-review`, `critical-review`, `discovery`, `refine`, and the worktree hooks. Soft dependencies — opting in to `morning-review` without `overnight` produces graceful empty-state behavior ("no sessions to review"), not corruption. Users figure out the relationship from the UX, not the tooling.
- **Band A (cleanly optional)**: UI toolchain, plugins, reference docs, rules files, notifications, dashboard, `harness-review`, `skill-creator`, `diagnose`, `retro`, `evolve`, `fresh`, `devils-advocate`, `requirements`, `pr`, `pr-review`, several hooks. Each is invocation-only or advisory.

## Research context from DR-2, DR-3, DR-4

- **DR-2**: Reuse `lifecycle.config.md` — do not add a new config file. Add new `skills:` and `hooks:` top-level sections to the existing YAML frontmatter. Existing lifecycle phase readers ignore the new sections.
- **DR-3**: No named bundles. Band C is the install floor; above it, per-component enable is the unit of selection.
- **DR-4**: Install-time selection for skills and hooks. Runtime opt-out for auto-invoked skills (`critical-review`'s `skip-review` flag) is explicitly out of scope for this epic.

## What this ticket delivers

- `/setup-merge` is extended to discover skills and hooks by scanning the filesystem at prompt time:
  - Skills: every directory under `skills/` containing a `SKILL.md`
  - Hooks: every `*.sh` file in `hooks/` and `claude/hooks/`
  - No hand-curated component manifest — the discovery result is always current with the repo state. Adding a new skill or hook automatically surfaces it in the next `/setup-merge` run.
- Per-skill and per-hook prompts are displayed grouped by cluster (per research §1.A and §1.B) for scannability. Install-floor items are merged unconditionally and flagged as such in the UI. Non-floor items default to enabled but are individually opt-out-able.
- Selections are written to `lifecycle.config.md`'s new top-level `skills:` and `hooks:` sections. Format is additive — existing lifecycle phase readers ignore the new sections.
- `deploy-bin` in the justfile reads the same `lifecycle.config.md` state and skips bin utilities scoped to opted-out skills. Concretely: when `overnight` is not enabled, `overnight-start` and `overnight-schedule` are not symlinked. The skill-to-bin-utility mapping lives via convention (e.g., `overnight-*` binaries belong to the `overnight` skill) — exact shape is a spec-phase decision.
- The existing `lifecycle.config.md` template in `skills/lifecycle/assets/` gains the new sections as commented-out examples.

## Success signals

- A user cloning cortex-command and running `just setup` can answer `/setup-merge` prompts to opt out of (say) overnight, all UI skills, notifications, and the dashboard. After setup, `ls ~/.claude/skills/` and `ls ~/.claude/hooks/` reflect only their selections. `overnight-start` is not on their PATH.
- A user running `/setup-merge` after a cortex-command update sees prompts for any new skills or hooks added since their last run, without anyone updating a component list.
- `lifecycle.config.md` at the repo root carries the user's selections in human-readable form; opening it shows which components are enabled/disabled.
- Existing lifecycle phase reads of `lifecycle.config.md` continue to work unchanged (the new sections are ignored by phases that don't consume them).

## Out of scope

- Runtime opt-out for auto-invoked skills (`critical-review`, `skip-review` flag) — separate future work.
- Dependency graph resolution between Band B items. If a user opts into `morning-review` without `overnight`, they see empty state and figure it out. No auto-selection cascade, no enforced "you must also enable X" validation.
- Uninstall semantics beyond "skip on fresh install." Setting `enable: false` on an already-installed component does not remove its symlink — users who want true uninstall run `rm` manually or re-run `just setup-force`.
- A `cortex-doctor` CLI that reports drift between configured and installed state.
- Heavy components that are not symlinked at all (overnight runner Python modules, conflict pipeline, dashboard) — they remain read in-place from `$CORTEX_COMMAND_ROOT`. This ticket only gates the symlinks and the skill-scoped bin utilities.

## References

- Research artifact: `research/user-configurable-setup/research.md`
- Decision records: DR-2 (reuse `lifecycle.config.md`), DR-3 (no bundles), DR-4 (install-time selection per type)
- Existing `/setup-merge` skill: `.claude/skills/setup-merge/`
- Existing `lifecycle.config.md` template: `skills/lifecycle/assets/lifecycle.config.md`
- Existing `lifecycle.config.md` at repo root: `lifecycle.config.md`
- Deployment entry points: `justfile` recipes `setup`, `deploy-skills`, `deploy-hooks`, `deploy-bin`
