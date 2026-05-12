---
schema_version: "1"
uuid: 29c04548-afdd-4a84-a50f-7b973065f9c0
title: "Migration guide + script for existing symlink-based installs"
status: wontfix
priority: medium
type: chore
parent: 113
tags: [distribution, migration, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-27
lifecycle_slug: null
lifecycle_phase: complete
session_id: null
blocks: []
blocked-by: [118]
discovery_source: cortex/research/overnight-layer-distribution/research.md
---

# Migration guide + script for existing symlink-based installs

## Context from discovery

Existing cortex-command users (effectively the maintainer today, plus anyone who has cloned during the current install model) have symlinks in `~/.claude/skills/*`, `~/.claude/hooks/*`, and `~/.local/bin/*` pointing back at the repo. Moving to the plugin model means removing those symlinks and reinstalling via the new bootstrap + plugin install flow. Slash commands also change namespace from `/commit`, `/lifecycle`, etc. to `/cortex:commit`, `/cortex:lifecycle`.

The user base is small enough that this is a one-time bespoke migration, but it has to actually work because the maintainer is the first migrator. Research flagged this as a known unresolved item.

## Scope

- `docs/migration-to-plugins.md` — step-by-step guide:
  1. Back up current `~/.claude/` (`tar` or `cp -r`)
  2. Remove existing cortex-command symlinks in `~/.claude/skills/`, `~/.claude/hooks/`, `~/.local/bin/` (list the specific targets)
  3. Run the bootstrap installer from ticket 118
  4. Add the marketplace from ticket 122, install `cortex-interactive` (+ optionally `cortex-overnight-integration`)
  5. Update muscle memory / aliases / shell completions for the `/cortex:*` namespace
- `bin/migrate-to-plugins.sh` (or `cortex migrate` subcommand) — scripted version of the steps above with dry-run mode and confirmation prompts
- Handle both outcomes cleanly: users who had the full install and users who only had subsets (e.g., just skills, no runner)

## Out of scope

- Rollback path (forward-only migration; users keep the backup from step 1 if they need to revert)
- Migrating the `cortex-command-plugins` extras repo — separate concern; that marketplace is already plugin-shaped

## Research

See `research/overnight-layer-distribution/research.md` Risks Acknowledged ("Migration cost is small but real"), Open Questions ("Old installs migration") — the research explicitly noted this needs a decomposition ticket.
