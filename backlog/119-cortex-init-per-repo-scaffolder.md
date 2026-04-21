---
schema_version: "1"
uuid: e2f12538-0606-44ca-a64c-9677389083af
title: "Add cortex init per-repo scaffolder for lifecycle/backlog/retros/requirements"
status: backlog
priority: medium
type: feature
parent: 113
tags: [distribution, cli, scaffolding, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [114]
discovery_source: research/overnight-layer-distribution/research.md
---

# Add cortex init per-repo scaffolder for lifecycle/backlog/retros/requirements

## Context from discovery

cortex-command's `lifecycle/`, `backlog/`, `retros/`, `requirements/` directories live in the user's working repo, not in `~/.claude/`. This is the content that semantically belongs to the user's project — feature plans, ticket history, session retrospectives. The prior-art scan found this is essentially shadcn-only territory: every other AI-agent framework writes to `~/.claude/`, `~/.continue/`, `~/.config/opencode/` (dotfile destinations). DR-7 endorses the shadcn pattern (`npx shadcn init`) for this tier: materialize templates into the target repo; user owns the code.

## Scope

- `cortex init [--path <repo-root>]` — run inside a git repo, creates `lifecycle/`, `backlog/`, `retros/`, `requirements/` with README/template files
- `cortex init --update` — pulls new templates without overwriting user edits (idempotent)
- Ship reasonable starter templates: `requirements/project.md` stub, `backlog/README.md`, `lifecycle/README.md`, `retros/README.md`, `lifecycle.config.md` with `type: other` default
- Declines to run if the directories already exist with user content, unless `--update` is passed; `--force` flag for full overwrite with confirmation prompt
- Documented in the bootstrap's post-install message so users know the verb exists

## Out of scope

- Opinionated tailoring by project type (could be a later enhancement — `cortex init --type library`, `--type app`)
- Migration from existing non-cortex layouts

## Research

See `research/overnight-layer-distribution/research.md` DR-7 (shadcn-style scaffolding) and `_prior-art-report.md` (shadcn/ui philosophy section). Note that shadcn explicitly documents "users own maintenance and don't get automatic bug fixes" as a trade-off — this applies here too.
