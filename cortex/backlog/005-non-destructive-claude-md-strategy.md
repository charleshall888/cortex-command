---
id: 005
title: "Non-destructive CLAUDE.md strategy"
type: feature
status: complete
priority: medium
parent: 003
tags: [shareability, install, claude-md]
created: 2026-04-02
updated: 2026-04-02
discovery_source: cortex/research/shareable-install/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: non-destructive-claude-md-strategy
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/non-destructive-claude-md-strategy/spec.md
---

# Non-destructive CLAUDE.md strategy

## Context

`just setup` currently replaces `~/.claude/CLAUDE.md` with a symlink to `claude/Agents.md`. New users lose their existing global agent instructions. The goal is to inject cortex-command's instructions without touching the user's file.

## Findings

From `research/shareable-install/research.md` (DR-4):

Claude Code loads all `.md` files from `.claude/rules/` automatically at project scope, with symlink support explicitly documented. The equivalent at user scope (`~/.claude/rules/`) is mentioned in community sources but **not prominently documented by Anthropic** — this must be verified before implementation. If user-scope `~/.claude/rules/` loads automatically, deploying a symlink there is the cleanest approach (never touches `~/.claude/CLAUDE.md`). If not, the fallback is `@import` injection into the user's existing `~/.claude/CLAUDE.md`.

`claude/Agents.md` currently contains a mix of genuinely generic rules (safe for any user) and cortex-command-specific content (only correct after full install). A full content audit is required — not just removing the settings symlink line. Known cortex-command-specific content includes: the Settings Architecture section, the Conditional Loading table (references cortex-command skills), and `/commit` skill invocation instructions.

**Fallback coupling**: if `@import` injection is needed, `~/.claude/CLAUDE.md` becomes a write target rather than a conflict-skip target. This changes the scope of ticket 006 (`just setup` additive) — that ticket's collision detection must be updated to handle CLAUDE.md as a merge target if this fallback applies.

## Acceptance Criteria

- Verify `~/.claude/rules/` loads at user scope: create `~/.claude/rules/test.md` with a distinctive instruction; confirm it applies in a project that has no `.claude/CLAUDE.md`; remove test file
- Full content audit of `claude/Agents.md` with explicit decision on which sections are generic vs cortex-specific
- `claude/Agents.md` split into two files with documented rationale for the boundary
- `~/.claude/CLAUDE.md` is not modified (primary path) OR `@import` appended idempotently if `~/.claude/rules/` is unverified (fallback path)
- Cortex-command instructions apply in all projects on the machine after install
- If fallback path is taken: ticket 006 acceptance criteria updated to handle CLAUDE.md as merge target
