---
id: 006
title: "Make `just setup` additive by default"
type: feature
status: complete
priority: high
parent: 003
blocked-by: []
tags: [shareability, install, setup]
created: 2026-04-02
updated: 2026-04-02
discovery_source: cortex/research/shareable-install/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: make-just-setup-additive-by-default
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/make-just-setup-additive-by-default/spec.md
---

# Make `just setup` additive by default

## Context

`just setup` uses `ln -sf` everywhere, silently overwriting any existing files at target paths. New users lose their existing config with no warning. The fix is to make `just setup` check first and skip conflicts, while preserving the destructive behavior under `just setup-force`.

## Findings

From `research/shareable-install/research.md` (DR-3, DR-5):

Each symlink target is classified as:
- `new` — target doesn't exist → install immediately
- `update` — target is already a symlink pointing to this repo → reinstall (safe re-run)
- `conflict` — target exists and points elsewhere, or is a regular file → skip, add to pending list

After install, setup prints the pending conflict list with instructions to run `/setup-merge` from within the cortex-command repo directory.

`just setup-force` preserves the current behavior (all targets overwritten unconditionally via `ln -sf`). This is what the repo owner runs on their own machine.

`settings.local.json` handling: even in additive mode, create `settings.local.json` with the correct `sandbox.filesystem.allowWrite` path for this clone location. For new users this file doesn't exist yet, so there is no conflict — it is always safe to create.

Note: if ticket 005 takes the `@import` fallback path (i.e. `~/.claude/rules/` is unverified), `~/.claude/CLAUDE.md` must be handled as a merge target rather than a conflict-skip target. This ticket's collision detection logic should accommodate that possibility.

## Acceptance Criteria

- `just setup` classifies all targets; reports `new`/`update`/`conflict` before making any changes
- `new` and `update` targets are installed; `conflict` targets are skipped with a clear message
- Pending conflict list printed at end with instruction to run `/setup-merge`
- `settings.local.json` created with correct `allowWrite` path even in additive mode (no prompt needed — new file)
- `just setup-force` preserves current destructive behavior end-to-end; must deploy BOTH the rules/ symlinks (`~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md`) AND `~/.claude/CLAUDE.md` → `claude/Agents.md` to give the repo owner the complete instruction set
- Existing owner install (all symlinks pointing to this repo) produces zero conflicts on `just setup` re-run
- Collision detection classifier covers all symlink targets, including `~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` (classify as `new`/`update`/`conflict` per the same rules as other targets)
