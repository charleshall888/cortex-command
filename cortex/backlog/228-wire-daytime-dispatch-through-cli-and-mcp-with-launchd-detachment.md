---
schema_version: "1"
uuid: 5fef3a25-7e3d-4ddb-9d18-8bd45a4b5dba
title: "Wire daytime dispatch through cortex CLI + MCP with launchd detachment"
status: refined
priority: high
type: feature
tags: [daytime-pipeline, mcp, cli, launchd, overnight-runner]
created: 2026-05-16
updated: 2026-05-16
complexity: complex
criticality: high
areas: [overnight-runner]
spec: cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md
---

# Wire daytime dispatch through cortex CLI + MCP with launchd detachment

## Context

Overnight dispatch and daytime dispatch are architecturally asymmetric in how they spawn:

| Surface | Overnight | Daytime |
|---------|-----------|---------|
| MCP tools | 6 (`overnight_start_run`, `overnight_schedule_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) | 0 |
| `cortex` CLI verb | `cortex overnight start --format json` | none |
| Spawn mechanism | "runner detached under launchd by design" (see `plugins/cortex-overnight/server.py:2329`) | Direct `cortex-daytime-pipeline` entry-point invocation, no detachment |

Overnight's launchd detachment lets a Claude session call `overnight_start_run` via MCP and have the runner spawn in a fresh process tree — escaping the calling session's Seatbelt sandbox state. Daytime has no equivalent: invoking `cortex-daytime-pipeline` from inside a Claude session (e.g., via the Bash tool) leaves the dispatched child claude session as a descendant of the calling claude process, inheriting that process's Seatbelt sandbox.

That inherited sandbox blocks the child claude session's unconditional `mkdir ~/.claude/session-env/<child-uuid>/` (the binary's `XJ8()` in the Bash tool's `dU7().buildExecCommand()` shell-command builder), because the calling session's `allowWrite` only grants its own session-env subdir, not the dispatched child's. Symptoms: every Bash invocation in the dispatched session fails with `EPERM: mkdir /Users/.../.claude/session-env/<child-uuid>`, and the dispatch defers with no commits landed.

Empirical evidence:
- All daytime dispatches triggered from inside a Claude session (`session_id: <parent-uuid>` in events.log) hit the EPERM and defer; documented across multiple lifecycles (`cortex/lifecycle/lead-refine-4-complexity-value-gate/exit-reports/*.json`, `cortex/lifecycle/archive/rewrite-verification-mindsetmd-.../exit-reports/4.json`).
- The identical command run from a fresh terminal (`session_id: "manual"` in events.log) completes through all 5 tasks in ~7.5 minutes and only pauses on `no_commit_guard` (a separate hygiene check), with zero session-env errors. See dispatch `abc4b0bd1e054fcfb2600cbdede979f0` (2026-05-16, paused on stale-branch).

The cleanest fix is architectural parity: give daytime the same CLI verb + MCP tool surface + launchd detachment that overnight has.

## Proposed change

1. **Add `daytime` verb to the `cortex` CLI** (alongside `overnight`). The verb should:
   - Accept `--feature <slug>` and `--format json` arguments.
   - Spawn `cortex-daytime-pipeline --feature <slug>` as a launchd-detached process, using the same async-spawn pattern the overnight verb uses (referenced as "Task 6 async-spawn refactor" in `plugins/cortex-overnight/server.py:2329`).
   - Return a JSON envelope on stdout with `started: bool`, `pid: int`, `feature: str`, `started_at: ISO8601`, mirroring the overnight start contract.
   - Refuse with `concurrent_dispatch` (versioned JSON, non-zero exit) when a PID file at `cortex/lifecycle/<feature>/daytime.pid` indicates another dispatch is live for the same feature.

2. **Add MCP tools to `plugins/cortex-overnight/server.py`** (or a parallel `plugins/cortex-daytime/server.py` if the team prefers separation):
   - `daytime_start_run` (input: feature slug + confirmation; calls `cortex daytime start --format json`)
   - `daytime_status` (input: feature slug; reads `cortex/lifecycle/<feature>/daytime-result.json` + recent events)
   - `daytime_logs` (input: feature slug, optional cursor; paginates `daytime.log` or `pipeline-events.log`)
   - `daytime_cancel` (input: feature slug; signals the detached process by PID)

3. **Document the constraints**:
   - `cortex-daytime-pipeline` direct invocation continues to work but is documented as "fresh-terminal-only" — calling it from a Bash tool inside a Claude session is unsupported.
   - The MCP tools are the supported entry point for Claude-session-initiated daytime dispatches.
   - Add a doc section under `docs/overnight-operations.md` (or a new `docs/daytime-operations.md`) explaining the two entry points and when each applies.

## Acceptance

- `cortex daytime start --feature <slug> --format json` exits 0 with a JSON spawn envelope on stdout and the dispatch process detached under launchd (verified by `ps -o ppid= -p <returned-pid>` not pointing at the calling shell).
- `mcp__plugin_cortex-overnight_cortex-overnight__daytime_start_run` (or equivalent in the chosen plugin) is invocable from a Claude session and successfully spawns a dispatch whose `events.log` shows progress events with `session_id: "<manual-style>"` (not the calling Claude session's UUID), no `EPERM` events, and no `Sandbox failed to initialize` events.
- A `tests/test_daytime_cli_detached_spawn.py` (or similar) asserts the spawned dispatch process is not a descendant of the test process (via PID/PGID inspection).
- The existing `cortex-daytime-pipeline` entry point continues to work when invoked directly from a fresh terminal (regression guard).

## Out of scope

- Refactoring `cortex_command/overnight/daytime_pipeline.py` internals — this ticket only adds a wrapper above the existing pipeline.
- Restructuring the overnight runner's process model — overnight already works.
- Replacing the no-commit-guard pause (separate concern; tracked elsewhere if relevant).
- Migrating dispatched-session auth from OAuth to API key — `--bare` mode investigation surfaced this as a tangent, not a blocker.

## References

- **Related completed**: #116 (MCP control-plane server with versioned runner IPC), #078 (build daytime-pipeline module + CLI), #140 (investigate daytime-pipeline blockers).
- **MCP overnight precedent**: `plugins/cortex-overnight/server.py:2046-2400` — `overnight_start_run` tool + `_delegate_overnight_start_run` subprocess delegate.
- **CLI overnight precedent**: `cortex overnight start --format json` (entry point in cortex CLI bin).
- **Symptom artifacts**: `cortex/lifecycle/lead-refine-4-complexity-value-gate/exit-reports/{1,2,3,4}.json` (from-Claude-session failures), and the same feature's dispatch `abc4b0bd1e054fcfb2600cbdede979f0` (from-fresh-terminal success — only paused on stale-branch, no sandbox errors).
- **Binary internals (for context, not action)**: Claude Code 2.1.143's Bash tool calls `z77()` → `XJ8()` → `mkdir(~/.claude/session-env/<session-id>/)` unconditionally per Bash invocation. Sandbox inheritance from the calling Claude session is what fails this for nested daytime dispatches; launchd detachment removes the inheritance.
