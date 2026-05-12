---
schema_version: "1"
uuid: e8311326-418f-47db-b3f4-852efc3ef192
title: "Rebuild overnight runner under cortex CLI"
status: complete
priority: high
type: feature
parent: 113
tags: [distribution, cli, overnight-runner, overnight-layer-distribution]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: rebuild-overnight-runner-under-cortex-cli
lifecycle_phase: implement
session_id: null
blocks: []
blocked-by: []
discovery_source: cortex/research/overnight-layer-distribution/research.md
complexity: complex
criticality: critical
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

Shared contracts with 117 (now complete; see 117's review.md): 117 was pure retirement — no `cortex setup` subcommand was built. runner.sh hard-codes `~/.claude/notify.sh` at **13 call sites** (lines 522, 675, 750, 800, 1012, 1072, 1097, 1130, 1257, 1267, 1287, 1289 + design comment at 846) and reads `~/.claude/settings.json` for `apiKeyHelper` at lines 50-66. 117 retired the repo-owned deploy-to-home pipeline; `~/.claude/notify.sh` is now machine-config's responsibility (cortex-command no longer ships `hooks/cortex-notify.sh`), and `~/.claude/settings.json` is entirely user-owned. The runner can no longer assume either path is cortex-controlled. See also 117's Task 11 Non-Req note for the full post-117 hook ownership split.

## Open Decisions

- **Notify.sh resolution strategy**: the 13 runner.sh notify call sites need a post-117 answer. Options: (a) depend on machine-config having `~/.claude/notify.sh` and keep the `|| true` fallback; (b) provide a local fallback (no-op or stdout) when the path doesn't resolve; (c) route notifications through a cortex-CLI-aware mechanism (e.g., `cortex notify` subcommand shipped alongside `cortex overnight`). Pick one in the spec phase.
- **apiKeyHelper reading**: `~/.claude/settings.json` is now user-owned via machine-config. The runner still needs `apiKeyHelper` for the auth flow; decide whether to keep reading the literal path (brittle but simple) or route through a cortex-CLI config lookup.

## Scope

- `cortex overnight start` — replaces today's `runner.sh` entry point, invoked via `uv tool install -e .`'s entry point
- `cortex overnight status <session-id>` — structured status output (JSON and human)
- `cortex overnight cancel <session-id>` — signals runner's process group; see ticket 116 for PID/PGID persistence
- `cortex overnight logs <session-id> [--tail] [--since <cursor>]` — append-only log streaming with cursor protocol
- Preserve today's load-bearing guarantees: atomic state writes (all 25 call sites), process-group management (the 4 `set -m` sites + `kill -- -$PID` watchdog), signal-based graceful shutdown at `trap cleanup SIGINT SIGTERM SIGHUP`
- Update all 23 `REPO_ROOT` sites + `CORTEX_COMMAND_ROOT` + `$PYTHONPATH` assumptions to work under `uv tool install -e` semantics; decide whether bash remains as a subprocess or the orchestration layer becomes pure Python
- Update the 50 inline Python snippets — each reads from `os.environ['REPO_ROOT']` or literal `~/.claude/...` paths that must be ported to package-resource semantics
- **Unresolved design question for planning**: prompt template substitution at runner.sh:379-393 reads `$REPO_ROOT/cortex_command/overnight/prompts/orchestrator-round.md` and does 6 `t.replace('{...}', ...)` calls with absolute paths. The prompt is handed to `claude -p` as stdin, so the paths it contains must still resolve on the host side (state, plan, events, session_dir). Which paths are "package-internal" (load via `importlib.resources`) vs. "user-repo-internal" (absolute paths on host filesystem)? The planning phase must answer this.
- Update the 13 `~/.claude/notify.sh` call sites per the notify-resolution decision in Open Decisions above
- Retire `bin/overnight-start`, `bin/overnight-status`, `bin/overnight-schedule` shim scripts (117 already retired `just deploy-bin`; `bin/` migration to `cortex-interactive` plugin is ticket 120's scope)
- Test migration: ~13,300 LOC of tests in `cortex_command/overnight/tests/` and `cortex_command/pipeline/tests/` must stay green through the rebuild

## Out of scope

- MCP server / IPC contract (ticket 116)
- `bin/overnight-schedule` migration to LaunchAgents — separate ticket #112, lands on this new shape after this ticket
- Dashboard migration (dashboard stays where it is for now, invoked from the same codebase)

## Research

See `research/overnight-layer-distribution/research.md` — Codebase Analysis, "Hard constraints that block naive repackaging" (the 7 coupling points), and the dependency matrix in DR-2. Also `_codebase-report.md` for the full file inventory.
