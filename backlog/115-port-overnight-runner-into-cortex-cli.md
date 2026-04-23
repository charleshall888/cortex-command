---
schema_version: "1"
uuid: e8311326-418f-47db-b3f4-852efc3ef192
title: "Rebuild overnight runner under cortex CLI"
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
blocked-by: [114, 117]
discovery_source: research/overnight-layer-distribution/research.md
---

# Rebuild overnight runner under cortex CLI

## Context from discovery

**Framed as a rebuild, not a port.** Critical review of the decomposition surfaced that the original "port runner.sh under a Python entry point" framing understated scope by ~2.3×. Quantified surface:

- `cortex_command/overnight/runner.sh` is **1,362 lines** (codebase report claimed 600+)
- `cortex_command/overnight/*.py` is **~10,400 LOC across 22 modules**
- `cortex_command/pipeline/*.py` is **~5,500 LOC across 10 modules**
- Tests: **~13,300 LOC across `cortex_command/overnight/tests/` + `cortex_command/pipeline/tests/`**
- **50** inline Python snippets in runner.sh (grep for `python3 -c|python3 <<|python3 -m`)
- **23** `REPO_ROOT` occurrences in runner.sh alone
- **25** atomic-write sites (`os.replace | NamedTemporaryFile`) across 7 files
- **4** `set -m` process-group sites (lines 644, 649, 715, 725) with `kill -- -$PID` watchdog at `trap cleanup` (line 526)

This is a rebuild of the orchestration layer. Wrapping 1,362 lines of bash + 50 inline Python snippets + 10 process-group/trap hooks under a Python entry point is not wrapping — it is either rewriting the orchestration layer in Python or keeping bash as a launched subprocess (which introduces its own packaging problems since `uv tool install -e` ships Python entry points, not bash scripts). That design choice is part of this ticket's scope.

Shared contracts with 117 (`cortex setup`): runner.sh hard-codes `~/.claude/notify.sh` at **13 call sites** (lines 522, 675, 750, 800, 1012, 1072, 1097, 1130, 1257, 1267, 1287, 1289 + design comment at 846) and reads `~/.claude/settings.json` for `apiKeyHelper` at lines 50-66. 117 owns the deploy-to-home pipeline that creates those paths. This ticket is now explicitly gated on 117 (`blocked-by: [114, 117]`) so the new `~/.claude/*` surface is in place before the runner's path-literal sites are updated.

## Scope

- `cortex overnight start` — replaces today's `runner.sh` entry point, invoked via `uv tool install -e .`'s entry point
- `cortex overnight status <session-id>` — structured status output (JSON and human)
- `cortex overnight cancel <session-id>` — signals runner's process group; see ticket 116 for PID/PGID persistence
- `cortex overnight logs <session-id> [--tail] [--since <cursor>]` — append-only log streaming with cursor protocol
- Preserve today's load-bearing guarantees: atomic state writes (all 25 call sites), process-group management (the 4 `set -m` sites + `kill -- -$PID` watchdog), signal-based graceful shutdown at `trap cleanup SIGINT SIGTERM SIGHUP`
- Update all 23 `REPO_ROOT` sites + `CORTEX_COMMAND_ROOT` + `$PYTHONPATH` assumptions to work under `uv tool install -e` semantics; decide whether bash remains as a subprocess or the orchestration layer becomes pure Python
- Update the 50 inline Python snippets — each reads from `os.environ['REPO_ROOT']` or literal `~/.claude/...` paths that must be ported to package-resource semantics
- **Unresolved design question for planning**: prompt template substitution at runner.sh:379-393 reads `$REPO_ROOT/cortex_command/overnight/prompts/orchestrator-round.md` and does 6 `t.replace('{...}', ...)` calls with absolute paths. The prompt is handed to `claude -p` as stdin, so the paths it contains must still resolve on the host side (state, plan, events, session_dir). Which paths are "package-internal" (load via `importlib.resources`) vs. "user-repo-internal" (absolute paths on host filesystem)? The planning phase must answer this.
- Update the 13 `~/.claude/notify.sh` call sites to use the deploy-resolution shape 117 establishes
- Retire `bin/overnight-start`, `bin/overnight-status`, `bin/overnight-schedule` shim scripts (coordinate with 117's `just deploy-bin` retirement — these are linked call sites)
- Test migration: ~13,300 LOC of tests in `cortex_command/overnight/tests/` and `cortex_command/pipeline/tests/` must stay green through the rebuild

## Out of scope

- MCP server / IPC contract (ticket 116)
- `bin/overnight-schedule` migration to LaunchAgents — separate ticket #112, lands on this new shape after this ticket
- Dashboard migration (dashboard stays where it is for now, invoked from the same codebase)

## Research

See `research/overnight-layer-distribution/research.md` — Codebase Analysis, "Hard constraints that block naive repackaging" (the 7 coupling points), and the dependency matrix in DR-2. Also `_codebase-report.md` for the full file inventory.
