---
schema_version: "1"
uuid: e8311326-418f-47db-b3f4-852efc3ef192
title: "Port overnight runner into cortex CLI"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, cli, overnight-runner, overnight-layer-distribution]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [114]
discovery_source: research/overnight-layer-distribution/research.md
---

# Port overnight runner into cortex CLI

## Context from discovery

The codebase report identified ~92 files (5.3 MB) that must ship together as the overnight bundle: `claude/overnight/runner.sh`, `claude/overnight/*.py`, `claude/pipeline/*.py`, `claude/pipeline/prompts/*.md`, `claude/overnight/prompts/*.md`, `claude/common.py`, plus the `bin/overnight-{start,status,schedule}` entry points. Tight coupling today includes hardcoded paths, process-group management (`set -m` for watchdog), signal handling, atomic tempfile+os.replace writes, and prompt template substitution.

This ticket migrates that bundle under the `cortex overnight` subcommand family so `cortex overnight start` / `status` / `cancel` / `logs` are first-class, replacing today's `bin/overnight-{start,status,schedule}` scripts.

## Scope

- `cortex overnight start` — wraps today's `runner.sh` logic, invoked via `uv tool install -e .`'s entry point
- `cortex overnight status <session-id>` — structured status output (JSON and human)
- `cortex overnight cancel <session-id>` — signals runner's process group; see ticket 116 for PID/PGID persistence
- `cortex overnight logs <session-id> [--tail] [--since <cursor>]` — append-only log streaming
- Preserve today's load-bearing guarantees: atomic state writes, process-group management, signal-based graceful shutdown
- Update all hardcoded `$REPO_ROOT`, `CORTEX_COMMAND_ROOT`, `$PYTHONPATH` assumptions to work under `uv tool install -e` semantics
- Update prompt template substitution to load from package resources, not filesystem paths
- Retire `bin/overnight-start`, `bin/overnight-status`, `bin/overnight-schedule` shim scripts (or have them delegate to the CLI for one release to ease migration)

## Out of scope

- MCP server / IPC contract (ticket 116)
- `bin/overnight-schedule` migration to LaunchAgents — separate ticket #112, lands on this new shape after this ticket
- Dashboard migration (dashboard stays where it is for now, invoked from the same codebase)

## Research

See `research/overnight-layer-distribution/research.md` — Codebase Analysis, "Hard constraints that block naive repackaging" (the 7 coupling points), and the dependency matrix in DR-2. Also `_codebase-report.md` for the full file inventory.
