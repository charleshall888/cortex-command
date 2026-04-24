---
schema_version: "1"
uuid: 86a87121-2737-4b2a-8505-3ed605721d0f
title: "Publish cortex-overnight-integration plugin (overnight skill + runner hooks)"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, plugin, overnight-runner, overnight-layer-distribution]
areas: [skills, overnight-runner]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [116, 120]
discovery_source: research/overnight-layer-distribution/research.md
---

# Publish cortex-overnight-integration plugin (overnight skill + runner hooks)

## Context from discovery

The second plugin in the DR-2 split. Installed on top of `cortex-interactive` by users who want Claude-initiated overnight starts and the integration bits that only make sense when the runner CLI is present. Installation implies the user also has the CLI tier installed — the plugin references `cortex` subcommands and the MCP control-plane server (ticket 116) via `.mcp.json`.

## Scope

- Plugin layout under `plugins/cortex-overnight-integration/` in this repo with `.claude-plugin/plugin.json`
- Skills included (renamed to `/cortex:*`): `overnight` (the user-facing entry point to overnight workflow)
- `critical-review` and `morning-review` land here if the codebase check in ticket 120 finds they import `claude.overnight.*` at module load; otherwise they stay in `cortex-interactive`
- Hooks included: runner-only hooks that aren't useful in interactive flows (re-evaluate the list during implementation based on what ticket 115 leaves standing)
- `.mcp.json` registering `cortex mcp-server` so enabling the plugin auto-starts the control-plane MCP server
- Document the explicit dependency on the CLI tier being installed; plugin should surface a clear error if `cortex` isn't on PATH

## Out of scope

- The runner itself (ticket 115) and the MCP server implementation (ticket 116) — this plugin is the Claude-side integration, not the runner
- Marketplace listing (ticket 122)

## Research

See `research/overnight-layer-distribution/research.md` DR-2 (plugin split), DR-1 (MCP server integration), and the dependency matrix table in DR-2 for what belongs here vs. `cortex-interactive`.
