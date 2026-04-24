---
schema_version: "1"
uuid: e327a6e7-fabb-47f5-b99e-35a30c995ab0
title: "Build MCP control-plane server with versioned runner IPC contract"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, mcp, overnight-runner, overnight-layer-distribution]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
---

# Build MCP control-plane server with versioned runner IPC contract

## Context from discovery

The project's north star is "autonomous multi-hour development: send Claude to work with a plan, let it spin up its own teams." A terminal-only `cortex overnight start` forces users out of Claude Code to kick off the very workflow that's supposed to be Claude-initiated. DR-1 folds the originally-deferred control plane into the core work so the north-star UX ships from day one, not as a later retrofit.

The pattern is [`dylan-gluck/mcp-background-job`](https://github.com/dylan-gluck/mcp-background-job): the MCP server doesn't host the runner; it shells out to it, tracks state, and exposes tools for `start_run` / `status` / `logs` / `cancel`. The runner is long-lived and lives outside any Claude session.

## Scope

- `cortex mcp-server` subcommand — stdio MCP server exposing tools: `overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`
- Versioned runner IPC contract:
  - `lifecycle/overnight-state.json` gains a `schema_version` field; external consumers detect compat breaks
  - PID and PGID record at `lifecycle/sessions/{id}/runner.pid` — written atomically on start, removed on clean exit; `cancel` signals the PGID
  - Cursor-based log tailing: `events.log`, `agent-activity.jsonl`, and `escalations.jsonl` gain offset-based reads so `overnight_logs --since <cursor>` is idempotent and cheap
- Tool schemas bounded to stay under MCP's 25 K token output cap (`MAX_MCP_OUTPUT_TOKENS` is the escape hatch, but default-safe is the goal)
- Documentation: how to add `cortex mcp-server` to a user's Claude Code MCP config

## Out of scope

- Remote / Cloudflare-hosted MCP variant (DR-3: architectural mismatch — can't see user's local worktree)
- SEP-1686 Tasks support (not yet in a released MCP version)
- Plugin monitor integration (monitors die with session; not suitable for multi-hour runs)

## Research

See `research/overnight-layer-distribution/research.md` DR-1 (merged decision, IPC contract specified), feasibility row G (now folded into core scope), and `_plugin-mcp-report.md` for the full MCP limits catalog.
