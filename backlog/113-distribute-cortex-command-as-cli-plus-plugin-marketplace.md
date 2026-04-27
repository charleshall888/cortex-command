---
schema_version: "1"
uuid: 3f12ca5d-0eef-480a-804d-fcbe2dd57223
title: "Distribute cortex-command as cortex CLI + plugin marketplace"
status: complete
priority: high
type: epic
tags: [distribution, plugin, cli, overnight-layer-distribution]
areas: [install, overnight-runner, skills]
created: 2026-04-21
updated: 2026-04-27
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: [102, 103, 104]
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
---

# Distribute cortex-command as cortex CLI + plugin marketplace

## Context from discovery

cortex-command today is installed by cloning the repo and running `just setup`, which symlinks skills/hooks/bin into `~/.claude/` and `~/.local/bin/`. That works for the maintainer but creates sharp edges for anyone else: global settings clobbered, `just` as a hard prereq, no Claude-initiated overnight starts, no way to take a subset of the system. The plugin model went GA in 2026 Claude Code and is now the standard distribution shape for skills + hooks + MCP servers.

This epic repackages the system as two plugins (`cortex-interactive`, `cortex-overnight-integration`) hosted in this repo's marketplace, sitting on top of a `curl | sh`-installable `cortex` CLI that owns the runner, dashboard, MCP control-plane server, config deployment, and per-repo scaffolder. The existing `cortex-command-plugins` repo continues to host truly optional per-project extras.

## Scope

- CLI tier: `cortex` binary via `uv tool install -e .`, subcommands for `overnight {start,status,cancel,logs}`, `mcp-server`, `setup`, `init`, `upgrade`
- MCP control-plane server (modeled on `dylan-gluck/mcp-background-job`) so Claude Code can initiate overnight sessions without the user leaving the chat
- Runner IPC contract: versioned state-file schema, PID/PGID persistence, cursor-based log tailing
- Bootstrap installer (`curl -fsSL https://cortex.sh/install | sh`)
- Plugin tier: `cortex-interactive` (non-runner skills + interactive hooks + plugin bin/) and `cortex-overnight-integration` (overnight skill + runner-required hooks) with a `.claude-plugin/marketplace.json` in this repo
- Skill namespace migration to `/cortex:*`
- Lifecycle skill learns to gracefully degrade the "Implement in autonomous worktree" option when the runner CLI isn't installed
- Per-repo scaffolder (`cortex init`) that materializes `lifecycle/`, `backlog/`, `retros/`, `requirements/` templates into the user's target repo
- Migration guide + script for existing symlink-based installs
- Optional Homebrew tap as a thin wrapper around the curl installer

## Out of scope

- Full remote MCP / Cloudflare-hosted port (architectural mismatch — see DR-3)
- PyInstaller or standalone-binary distribution (kills forkability — approach F)
- Absorbing `cortex-command-plugins` into this repo (DR-9 keeps it separate)
- Migration of `bin/overnight-schedule` to LaunchAgents — separate ticket #112, lands on the new CLI shape after this epic (DR-10)
- Agent-invokable script extraction — separate epic #101, scripts live in the CLI tier when it ships

## Research

See `research/overnight-layer-distribution/research.md` for full findings, feasibility assessment, and decision records (DR-1 through DR-10). The Decision inventory table in the Summary section lists every consequential call and its resolution.

## Epic size note

Post-decomposition critical review quantified 115 at XL (not L as originally sized) — 1,362 lines of bash + ~17K non-test LOC of Python + ~13K LOC of tests, with 50 inline Python snippets and 23 `REPO_ROOT` sites in runner.sh alone. 115 is ~10× the surface of 117 + 119 combined and is the critical-path bottleneck for 6 of 12 children. Epic-level: realistically XL-XXL for a single maintainer. The epic's own scope lists 5 new owned components (CLI, MCP server, setup subcommand, plugin marketplace, scaffolder) and is more honestly described as a rebuild of the distribution layer than as a packaging change.

## Children

- 114: `cortex` CLI skeleton
- 115: **Rebuild** overnight runner under the CLI (XL, gated on 117)
- 116: MCP control-plane server + runner IPC contract
- 117: `cortex setup` subcommand + retire #006/#007 code
- 118: Bootstrap installer (`curl | sh`)
- 119: `cortex init` per-repo scaffolder
- 120: `cortex-interactive` plugin
- 121: `cortex-overnight-integration` plugin (gated on 115, 116, 120)
- 122: Plugin marketplace manifest + install docs (gated on 115, 116, 117, 120, 121)
- 123: Lifecycle autonomous-worktree graceful degrade
- 124: Migration guide + script for existing users (gated on full CLI being functional)
- 125: Homebrew tap (optional)

## Downstream epic coordination

This epic explicitly blocks tickets #102, #103, #104 (children of #101 scripts epic). Those tickets target `bin/` layout and `just deploy-*` recipes that #115 and #117 retire; landing them first would produce throwaway work. #112 (LaunchAgent scheduler) is an open question — it is currently `in_progress` with an active lifecycle session; user decision pending on whether to gate it on #114 retroactively.
