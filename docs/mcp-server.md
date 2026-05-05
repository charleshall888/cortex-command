[← Back to overnight-operations.md](overnight-operations.md)

# Cortex MCP Control-Plane Server

**For:** operators wiring `cortex-overnight` into Claude Code (or another MCP client) and debugging the control-plane interface. **Assumes:** familiarity with `docs/overnight-operations.md` and the round-loop / state-file architecture it describes.

> **Jump to:** [What this server is](#what-this-server-is) | [Registration](#registration) | [Tool inventory](#tool-inventory) | [Cursor pagination](#cursor-pagination) | [Per-session escalations](#per-session-escalations) | [Recovery](#recovery) | [Caveats](#caveats) | [Diagnostics](#diagnostics) | [Bypassing the in-flight guard](#bypassing-the-in-flight-guard)

This doc owns the **control-plane interface** plane. It is a sibling of `overnight-operations.md` (round loop / orchestrator), `internals/pipeline.md` (per-task pipeline internals), and `internals/sdk.md` (model-selection mechanics). When a question is about *how Claude Code talks to a running overnight session*, it lives here. When the question is about what the runner does *after* it has been told to start, follow the cross-link to `overnight-operations.md`.

---

## What this server is

`cortex mcp-server` is a stdio-transport MCP server that exposes five tools for driving the overnight runner from a Claude Code conversation. It is stateless: every tool call reads or writes filesystem-grounded state under `lifecycle/sessions/{session_id}/`, which means an MCP client can be restarted or replaced without affecting an in-flight runner.

Two install paths exist; both register the same `cortex mcp-server` subprocess:

1. **CLI registration** — `claude mcp add cortex-overnight ...` (covered in [Registration](#registration)). Best for operators who want one-off control without touching plugins.
2. **Plugin install** — `/plugin install cortex-overnight` from inside Claude Code, which ships a `.mcp.json` registering the same server.

The MCP server logs only to `stderr`; `stdout` is reserved for the JSON-RPC stream. Do not redirect `stdout` and do not enable any tooling that writes to it.

---

## Registration

To register the server in your user-scoped Claude Code config:

```
claude mcp add cortex-overnight --scope user --transport stdio -- cortex mcp-server
```

After registration, restart Claude Code. The five tools listed below become available in any session.

If you prefer plugin-based distribution, run `/plugin install cortex-overnight` from a Claude Code session. The plugin's bundled `.mcp.json` is equivalent to the `claude mcp add` command above.

---

## Tool inventory

All five tools take JSON object inputs and return JSON object outputs. Schemas are summarized; consult the server's tool descriptions at runtime for canonical field types.

### `overnight_start_run`

Spawns a new overnight runner.

- **Input (required):** `confirm_dangerously_skip_permissions: true` (the literal value `true`; any other value or omission is rejected).
- **Input (optional):** `state_path: string`.
- **Output:** `{session_id, pid, started_at}`.

This tool spawns a multi-hour autonomous agent that bypasses permission prompts and consumes Opus tokens. The `confirm_dangerously_skip_permissions` parameter is required precisely so that a model cannot silently start a run without an operator's explicit instruction. Calls without the parameter return a tool-execution error whose body re-states this warning, not a bare schema-validation failure — so the model sees the warning text in the error response.

If another runner is already alive on the same lock, the tool returns `{started: false, reason: "concurrent_runner_alive", existing_session_id: ...}`. There is no race window.

### `overnight_status`

Reads the current session's state file.

- **Input (optional):** `session_id: string` — when omitted, the active-session pointer is auto-discovered.
- **Output:** `{session_id, phase, current_round, started_at, updated_at, features: {pending, running, merged, paused, deferred, failed}, integration_branch, paused_reason}`.

If no `session_id` is supplied and no active session exists, the response is `{session_id: null, phase: "no_active_session"}`.

### `overnight_logs`

Returns paginated log lines for a session.

- **Input (required):** `session_id: string`.
- **Input (optional):**
  - `files: ("events" | "agent-activity" | "escalations")[]` — defaults to `["events"]`.
  - `cursor: string | null` — opaque token returned by a previous response. See [Cursor pagination](#cursor-pagination).
  - `limit: int` — defaults to 100, capped at 200 by the server.
  - `tail: int | null` — when set, returns the last N lines instead of paginating from the start.
- **Output:** `{lines, next_cursor, eof}`. On invalidation, `{lines: [], cursor_invalid: true, next_cursor: null, eof: false}`.

A request for a `session_id` that does not exist returns a structured tool-execution error (`{error: "session_not_found", session_id: ...}`), not a JSON-RPC protocol error.

### `overnight_cancel`

Cancels a running session.

- **Input (required):** `session_id: string`.
- **Input (optional):** `force: bool` — defaults to `false`. See [Recovery](#recovery).
- **Output:** `{cancelled, signal_sent, reason, pid_file_unlinked}` where `reason` is one of: `"cancelled"`, `"no_runner_pid"`, `"magic_mismatch"`, `"start_time_skew"`, `"signal_not_delivered_within_timeout"`.

`overnight_cancel` sends `SIGTERM` to the runner's process group, waits up to 10 seconds for graceful shutdown, then sends `SIGKILL` to any survivors. The runner walks its full descendant tree on `SIGTERM` so workers and grandchildren are reached.

### `overnight_list_sessions`

Lists active and recently-terminated sessions.

- **Input (optional):**
  - `status: ("planning" | "executing" | "paused" | "complete")[]`.
  - `since: string` (ISO 8601).
  - `limit: int` — defaults to 10.
  - `cursor: string | null`.
- **Output:** `{active, recent, total_count, next_cursor}` where each session entry is `{session_id, phase, started_at, updated_at, integration_branch}`.

Default behavior (no filters) returns all active sessions plus the 10 most recent terminated sessions.

---

## Cursor pagination

`overnight_logs` and `overnight_list_sessions` use opaque cursor tokens for pagination.

**Client contract:**

1. Make an initial request without `cursor`.
2. If the response contains `next_cursor: <some-string>`, pass that string back **unmodified** in the next request to fetch the following page.
3. If the response contains `next_cursor: null`, you have reached the end of the available data (also indicated by `eof: true` for `overnight_logs`).
4. If a response contains `cursor_invalid: true`, the underlying log file was rotated or truncated since your previous read. Discard your saved cursor and retry the request without one to re-baseline.

The cursor is an **opaque token**. Do not parse, modify, or persist its internal contents — its representation is server-internal and may change without notice. Treating it as opaque is what protects clients from breakage when the server's pagination internals evolve.

---

## Per-session escalations

Escalations — the worker-to-orchestrator side channel described in `docs/overnight-operations.md` — live at:

```
lifecycle/sessions/{session_id}/escalations.jsonl
```

Every active session has its own escalations file. There is no repo-level `escalations.jsonl` anymore; the legacy path was removed as part of the MCP control-plane work. To read escalation records via the MCP layer, call `overnight_logs` with `files: ["escalations"]` and the desired `session_id`.

---

## Recovery

### Cancelling a `SIGSTOP`'d runner

If a runner has been hard-stopped (`SIGSTOP`), the standard `SIGTERM`-then-`SIGKILL` escalation will not exit it: signals are queued but cannot be processed while the process is stopped. In that case `overnight_cancel` returns `{cancelled: false, reason: "signal_not_delivered_within_timeout", pid_file_unlinked: false}` and leaves `runner.pid` in place — preventing a fresh start until the lock is cleared.

Manual recovery procedure:

1. Call `overnight_cancel(session_id, force=true)`. This re-runs the signal escalation but unlinks `runner.pid` regardless of whether the process exited. Response is `{cancelled: false, reason: "signal_not_delivered_within_timeout", pid_file_unlinked: true, pid: <runner_pid>}`.
2. The hard-stopped process is still alive. Send `SIGKILL` directly: `kill -9 <pid>` (using the `pid` field from the cancel response).
3. A fresh `overnight_start_run` call will now succeed because `runner.pid` is gone.

Use `force=true` only when you accept that the runner process may persist as a zombie until you reap it manually with `kill -9`.

### Stale lock from a crashed runner

If a previous runner crashed without cleaning up its `runner.pid`, the next `overnight_start_run` call detects the stale lock via the IPC verifier (PID liveness check), unlinks the dead lock atomically, and proceeds. No manual intervention is required.

---

## Caveats

### macOS App Nap

macOS aggressively suspends background processes whose parent terminal has lost focus or whose laptop lid is closed. A long-running overnight session started from a Claude Code conversation will be subject to App Nap once the surrounding terminal is no longer foreground. For headless lid-closed sessions — the canonical "leave it running overnight" use case — wrap the start command in `caffeinate -i`:

```
caffeinate -i cortex overnight start ...
```

Or, when starting via the MCP server: launch your Claude Code session from a `caffeinate -i`-wrapped terminal. The runner inherits the suspension-immunity from the surrounding `caffeinate` process group.

The runner does not self-spawn under `caffeinate` in v1; this is a known caveat documented here rather than a bug.

### macOS detached-runner survival on logout

The runner spawns with `start_new_session=True` and reparents to PID 1 / `launchd` after the parent MCP-server process exits, which empirically allows it to survive operator logout. This behavior is not contractually guaranteed by macOS; if you observe a runner dying on logout, it is a known caveat rather than a regression in the MCP layer.

---

## Diagnostics

### `runner-bootstrap.log`

When the MCP server spawns a runner via `overnight_start_run`, the runner's stdout and stderr are redirected to:

```
lifecycle/sessions/{session_id}/runner-bootstrap.log
```

This file captures pre-`events.log`-init failures: import errors, missing dependencies, `session_dir` permission errors, early uncaught exceptions, and anything else that prevents the runner from initializing its own structured logging. If a fresh `overnight_start_run` call returns a `pid` but `events.log` never appears, `runner-bootstrap.log` is the first place to look.

Once the runner has initialized its event log, normal operational logging continues to flow through `events.log` and `agent-activity.jsonl` as documented in `docs/overnight-operations.md`. `runner-bootstrap.log` is therefore most useful for the first few seconds of a session's lifetime — and most diagnostic when the session never produces an `events.log` at all.

---

## Bypassing the in-flight guard

The cortex install flow refuses to upgrade `cortex` while an overnight runner is alive (phase `!= "complete"`). The check exists because the IPC contract and the per-session escalations layout are not backwards-compatible during a release transition: a mid-run upgrade would split the in-memory OLD-code runner from the on-disk NEW-code state and silently corrupt orchestrator state. The error message names the active `session_id` and points at recovery options.

When you consciously accept the risk, the guard is bypassable via `CORTEX_ALLOW_INSTALL_DURING_RUN=1`. **Do not export this variable.** Pass it inline on the command:

```
CORTEX_ALLOW_INSTALL_DURING_RUN=1 cortex ...
```

Exporting via `export CORTEX_ALLOW_INSTALL_DURING_RUN=1` (or persisting it in `~/.zshrc` / `~/.bashrc`) silently re-disables the in-flight guard for *every* future `cortex` invocation in that shell session, including ones spawned by the runner itself. Because the runner inherits its environment to its child workers, an exported value also propagates into worker processes and orchestrator subprocesses — so a single careless `export` defeats the safety check across the entire process tree, not just for the upgrade you intended. Keep the variable inline-only.

### Split-brain escalations consequence

If you bypass the guard mid-run, the OLD-code runner is still using its in-memory bindings from before the upgrade. Specifically: the orchestrator agent (which is re-spawned each round and re-imports modules) will pick up the NEW write path — `lifecycle/sessions/{session_id}/escalations.jsonl` — while the in-memory OLD-code `feature_executor.py` and `outcome_router.py` continue writing to whatever path their imports resolved at runner-launch time. Under the migration, the old default is the deleted repo-level `lifecycle/escalations.jsonl`.

The result is a **split-brain escalations state**:

- Orchestrator-agent writes land in the per-session file.
- OLD-code worker writes target a path that no longer exists (or, if you re-create it, exists outside the session-scoped read path the orchestrator now uses).
- The orchestrator's cycle-breaking logic — which scans escalations for repeated questions in the active session — sees only the orchestrator's own writes, not the worker's. Cycle detection silently degrades.

This is the central reason the in-flight guard exists. The bypass is provided for emergency operator overrides, not as a routine upgrade path.

### Recovery after a bypassed in-flight upgrade

Once the active run has fully completed (phase `complete` or paused-and-not-resuming), clean up any legacy file the OLD-code processes may have written during the bypass window:

```
git rm lifecycle/escalations.jsonl
```

Commit the deletion. The next overnight run will be entirely on the per-session layout and the split-brain window closes. If the file does not exist when you check, no cleanup is required — the OLD-code path may have failed cleanly under the missing-directory error rather than silently writing.
