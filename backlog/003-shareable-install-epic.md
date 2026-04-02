---
id: 003
title: "Make cortex-command shareable without overwriting users' global Claude settings"
type: epic
status: backlog
priority: high
tags: [shareability, install, setup]
created: 2026-04-02
updated: 2026-04-02
discovery_source: research/shareable-install/research.md
---

# Make cortex-command shareable without overwriting users' global Claude settings

## Context

`just setup` currently deploys config to `~/.claude/` via destructive symlinks with no collision detection. New users who already have Claude Code configured lose their `settings.json`, `CLAUDE.md`, hooks, and any skills with matching names — silently. Additionally, `settings.json` references `apiKeyHelper: ~/.claude/get-api-key.sh`, a file that doesn't exist in the repo, blocking new subscription users at startup.

The goal is a shareable install model where new users can adopt cortex-command without losing their existing setup.

## Scope

- `just setup` becomes additive by default; `just setup-force` preserves current destructive symlink behavior for the repo owner
- Hook files prefixed `cortex-` to eliminate name collisions
- `~/.claude/CLAUDE.md` never replaced; cortex-command instructions injected via `~/.claude/rules/`
- `~/.claude/settings.json` never replaced for new users; cortex-command entries merged in via `/setup-merge` skill
- `apiKeyHelper` replaced with a stub that delegates to machine-local config or falls back to subscription

## Children

- 004: Prep hooks and apiKeyHelper for sharing
- 005: Non-destructive CLAUDE.md strategy
- 006: Make `just setup` additive by default
- 007: Build `/setup-merge` local skill

## Research

See `research/shareable-install/research.md` for full findings, decision records, and feasibility assessment.
