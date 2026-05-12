---
id: 004
title: "Prep hooks and apiKeyHelper for sharing"
type: chore
status: complete
priority: high
parent: 003
tags: [shareability, install, hooks]
created: 2026-04-02
updated: 2026-04-02
discovery_source: cortex/research/shareable-install/research.md
session_id: null
lifecycle_phase: review
lifecycle_slug: prep-hooks-and-apikey-for-sharing
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/prep-hooks-and-apikey-for-sharing/spec.md
---

# Prep hooks and apiKeyHelper for sharing

## Context

Two problems block sharing cortex-command's hook and auth setup:

1. Hook files have generic names (`validate-commit.sh`, `cleanup-session.sh`, etc.) that collide with any power user's existing `~/.claude/hooks/`. Installing silently overwrites theirs.
2. `settings.json` references `apiKeyHelper: ~/.claude/get-api-key.sh` — a script that doesn't exist in the repo and isn't created by setup. New subscription users get a file-not-found error at Claude Code startup.

## Findings

From `research/shareable-install/research.md`:

- All hook files need a `cortex-` prefix (e.g. `cortex-validate-commit.sh`) to eliminate collision risk. This cascades to: the hooks block in `settings.json` (15+ path strings across 7 event types), the `check-symlinks` recipe in the justfile, and all docs referencing hook paths by name.
- The apiKeyHelper fix is a stub script shipped in the repo: calls `~/.claude/get-api-key-local.sh` if present, returns empty otherwise. Empty return = subscription billing fallback in both interactive Claude Code and `runner.sh` (lines 46–65).
- `runner.sh` reads `~/.claude/settings.json` only (not `settings.local.json`), so the stub must be registered in `settings.json` and symlinked to `~/.claude/get-api-key.sh`.

## Acceptance Criteria

- All hook files renamed to `cortex-*`; all references updated atomically in a single commit (no partial state where file is renamed but settings.json still points to old path)
- `claude/get-api-key.sh` stub exists in repo and is symlinked to `~/.claude/get-api-key.sh` by `deploy-config`
- Stub returns empty without interactive Claude Code startup error (verified)
- `runner.sh` falls back to subscription billing with warning (not error) when stub returns empty (verified)
- Primary user re-runs `just deploy-hooks` (or `just setup-force`) after merge; all hooks fire correctly with new names
