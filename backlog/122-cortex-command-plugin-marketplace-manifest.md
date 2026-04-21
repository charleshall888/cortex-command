---
schema_version: "1"
uuid: 7a291fcc-a9c8-4df2-97e2-81e0c01c5016
title: "Publish plugin marketplace manifest for cortex-command"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, plugin, marketplace, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [120, 121]
discovery_source: research/overnight-layer-distribution/research.md
---

# Publish plugin marketplace manifest for cortex-command

## Context from discovery

Claude Code plugin marketplaces are git repos with a `.claude-plugin/marketplace.json`. This ticket wires up this repo as a marketplace hosting the two core plugins (`cortex-interactive`, `cortex-overnight-integration`), so users can add it with `/plugin marketplace add charleshall888/cortex-command` and install with `/plugin install cortex-interactive@cortex-command`.

DR-9 keeps the existing `cortex-command-plugins` repo as the separate "extras" marketplace for truly optional per-project skills (android-dev, ui-extras, pr-review, dev-extras). Users who want both add both marketplaces; users who want only core add one.

## Scope

- Create `.claude-plugin/marketplace.json` at this repo's root listing both plugins with versions, descriptions, and source paths (`plugins/cortex-interactive`, `plugins/cortex-overnight-integration`)
- Installation docs (README section + `docs/install.md`): how to add the marketplace, install each plugin, and when to add `cortex-command-plugins` for extras
- Document the two-marketplace UX clearly — two `/plugin marketplace add` commands, then pick what you want from each
- Consider (but don't block on) submission to `anthropics/claude-plugins-official` for the core plugin so users can skip the `marketplace add` step

## Out of scope

- Absorbing `cortex-command-plugins` into this repo (DR-9 keeps separate)
- Plugin content itself (tickets 120, 121)

## Research

See `research/overnight-layer-distribution/research.md` DR-9 (separate extras marketplace), `_plugin-mcp-report.md` (marketplace + `marketplace.json` reference), and the prior-art report's note that "marketplace = git repo with a manifest" is the dominant content-distribution shape.
