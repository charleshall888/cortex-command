# Requirements: observability

> Last gathered: 2026-04-03 (updated 2026-04-08)

**Parent doc**: [requirements/project.md](project.md)

## Overview

The observability area covers five subsystems that give the developer visibility into active Claude sessions: the terminal statusline (in-session context and lifecycle state), the web dashboard (full overnight session monitoring), the notification system (macOS desktop and Android push alerts), the in-session status CLI (`overnight-status` for sandbox-safe one-shot status), and optional sandbox socket access (tmux socket allowlisting for full interactive access). The first four subsystems read from the same file-based session state; none can write to it. Sandbox socket access is a configuration concern, not a runtime subsystem.

## Functional Requirements

### Statusline

- **Description**: A 3-line terminal prompt extension that shows session context, git state, and active lifecycle feature phase. Rendered by `claude/statusline.sh`.
- **Inputs**: Claude Code hook JSON (context utilization, model), `lifecycle/*/events.log`, `lifecycle/overnight-state.json`
- **Outputs**: 3 lines of ANSI-colored text to stdout, logged to `claude/statusline.log`
- **Acceptance criteria**:
  - Context percentage and progress bar match actual token usage in the active session
  - Active lifecycle feature name and phase match `events.log`
  - Pipeline mode shows round progress and active feature names when `overnight-state.json` is present
  - Output always fits in 3 lines; degrades gracefully on narrow (≥80 col) terminals
  - Invocation latency < 500ms
  - Renders without error when no lifecycle feature is active (shows git state only)
- **Priority**: must-have

### Dashboard

- **Description**: A read-only FastAPI web application at `http://localhost:$DASHBOARD_PORT` (default 8080) that monitors overnight sessions in real time. Renders session panels, feature cards, fleet overview, alerts, and a swim-lane timeline via HTMX polling.
- **Inputs**: `lifecycle/overnight-state.json`, `lifecycle/pipeline-events.log`, per-feature `events.log` and `plan.md`, `lifecycle/active-session.json`
- **Outputs**: Live HTML UI updated via HTMX at ~5s intervals; alert notifications dispatched via notify scripts
- **Acceptance criteria**:
  - Feature status badges, model, and phase progress reflect actual state within 7s of a state file change
  - Cost tracking accumulates correctly from `agent-activity.jsonl` (incremental reads, no double-counting)
  - Circuit breaker alert fires once per session when dispatch is halted
  - Stall alert fires when a feature has no activity for >5 minutes
  - Missing or malformed session files are silently ignored (last-good state retained)
  - Session change (new overnight session started) resets event offset and re-reads from the beginning
- **Priority**: must-have

### Notifications

- **Description**: macOS desktop notifications via `terminal-notifier` (`hooks/cortex-notify.sh`) deliver alerts on Stop/Notification events.
- **Inputs**: Claude Code Stop/Notification hook JSON; dashboard alert evaluation
- **Outputs**: macOS desktop notification; terminal bell
- **Acceptance criteria**:
  - macOS notification fires on session stop with correct type label (permission / idle / complete)
  - Subagent sessions are suppressed (no notification when `agent_id` is present in hook JSON)
  - Notification delivery failure is silent (hook exits 0; session is not blocked)
  - Dashboard-triggered notifications respect the same deduplication (stall fires once; clears when resolved)
- **Priority**: must-have

### Runtime Adoption Telemetry

- **Description**: Per-script invocation shim (`bin/cortex-log-invocation`) writes one JSONL record per `bin/cortex-*` invocation to `lifecycle/sessions/<id>/bin-invocations.jsonl`. Aggregator CLI (`bin/cortex-invocation-report`) reads the per-session logs and reports adoption (default human-readable, `--json`, `--check-shims`, `--self-test` modes). Composed with DR-5 static parity lint (ticket 102) for full coverage of script-adoption failure modes — DR-5 catches missing wiring; runtime telemetry catches wired-but-never-invoked scripts.
- **Inputs**: helper invocation calls from each `bin/cortex-*` script's shim line; `LIFECYCLE_SESSION_ID` environment variable; aggregator scans `lifecycle/sessions/*/bin-invocations.jsonl` glob.
- **Outputs**: per-session JSONL log file (`lifecycle/sessions/<id>/bin-invocations.jsonl`); aggregator stdout (default + `--json` modes); error breadcrumb at `~/.cache/cortex/log-invocation-errors.log` recording fail-open categories.
- **Acceptance criteria**: Spec R1–R18 acceptance criteria from `lifecycle/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/spec.md` (helper fail-open contract, JSONL schema, sessions inventory, aggregator output structure, `--check-shims` pre-commit gate, `--self-test` round-trip, plugin distribution byte-identity).
- **Priority**: P1 (closes the runtime-adoption-failure detection gap that DR-5 cannot reach).

### In-Session Status CLI

- **Description**: A standalone bash script (`bin/overnight-status`, deployed to `~/.local/bin/overnight-status`) that produces a one-shot status report of the active overnight session from within a sandboxed Claude Code session. Also invocable as `/overnight status` via the overnight skill.
- **Inputs**: `~/.local/share/overnight-sessions/active-session.json` (session pointer), `lifecycle/sessions/{id}/overnight-state.json`, `lifecycle/sessions/{id}/.runner.lock`, `lifecycle/sessions/{id}/overnight-events.log`
- **Outputs**: Human-readable status report to stdout including runner liveness, session phase, feature progress, recent events, and failed-feature errors
- **Acceptance criteria**:
  - Exits 0 when session data found (active or last-known); exits 1 only when no session data exists at all
  - Runner liveness reported via `kill -0` on PID from `.runner.lock` ("alive", "dead", or "no lock file")
  - Session phase and feature counts by status (pending/running/merged/failed/deferred) from `overnight-state.json`
  - Last 5 events from `overnight-events.log` displayed as timeline
  - Failed features listed with error messages
  - Falls back to most recent `lifecycle/sessions/` directory when `active-session.json` is absent or shows `phase: complete`
  - Handles corrupt `overnight-state.json` gracefully (falls back to events-only output)
- **Priority**: must-have

### Sandbox Socket Access

- **Description**: Optional tmux socket allowlisting via `just setup-tmux-socket` to restore full tmux access (`tmux has-session`, `tmux list-sessions`, `tmux attach`) from within sandboxed Claude Code sessions. Grants access to the default tmux socket at `/private/tmp/tmux-{UID}/default`.
- **Inputs**: `~/.claude/settings.json` (existing `allowUnixSockets` array), `$(id -u)` (current UID)
- **Outputs**: Updated `~/.claude/settings.local.json` with combined `allowUnixSockets` array (preserving existing GPG socket entry)
- **Acceptance criteria**:
  - `settings.local.json` contains both the tmux socket and GPG agent socket in `allowUnixSockets`
  - Existing `sandbox.filesystem.allowWrite` entries in `settings.local.json` are preserved (arrays replace, not merge)
  - Setup prints a clear warning about granting access to all tmux sessions
  - Idempotent: re-running skips if tmux socket already present
- **Priority**: should-have
- **Note**: `settings.local.json` arrays replace (not merge with) `settings.json` arrays. The setup recipe must write a self-contained array containing all required sockets.

## Non-Functional Requirements

- **Latency**: Statusline < 500ms per invocation; dashboard total refresh ≤ 7s; notification dispatch fire-and-forget with 5s curl timeout
- **Availability**: Dashboard process crash does not affect Claude session; statusline failure is non-blocking (no crash, no output is acceptable)
- **No writes**: All three subsystems are read-only with respect to session state files
- **Resource usage**: One FastAPI process + 4 asyncio polling tasks; no database; in-memory cache only

## Architectural Constraints

- Dashboard binds to all network interfaces (`0.0.0.0`) and has no authentication. It is unauthenticated and accessible to any host on the local network by design. Not suitable for untrusted networks.
- Dashboard is read-only and cannot modify session state, trigger retries, or dispatch features.
- ANSI output uses the basic 16-color palette (not 256-color or truecolor) to avoid byte overhead in Claude Code terminal width calculations.
- Notifications are stateless — no retention, no inbox.

## Dependencies

- **Statusline**: `jq` (with pure-bash fallback), `git`
- **Dashboard**: Python 3, FastAPI, Jinja2, HTMX (embedded in templates); file-based session state at `lifecycle/`
- **Notifications (macOS)**: `terminal-notifier` (installed via `brew install terminal-notifier`); Ghostty terminal
- **In-Session Status CLI**: `jq`, `bash`; file-based session state at `lifecycle/sessions/` and `~/.local/share/overnight-sessions/`
- **Sandbox Socket Access**: `jq`, `just` (setup recipe); `~/.claude/settings.json` and `~/.claude/settings.local.json`

## Edge Cases

- **No active session**: Statusline renders git state only; dashboard hides Session and Fleet panels
- **Session directory rotation**: Dashboard resets event offset to 0 on session ID change and re-reads from scratch; possible duplicate alerts on first poll after reset
- **jq unavailable**: Statusline falls back to pure-bash regex parsing; may fail on complex JSON

- **Stale PID in `.runner.lock`**: Runner died but lock file not cleaned up; `kill -0` returns non-zero; status CLI reports "dead (stale PID)" rather than "alive"
- **Corrupt `overnight-state.json`**: Truncated write during active session; status CLI falls back to events-only output
- **`settings.local.json` array clobber**: Adding `allowUnixSockets` via naive jq write could destroy `filesystem.allowWrite`; setup recipe uses deep merge to preserve sibling keys
- **tmux socket grants broad access**: Allowlisting the default tmux socket grants access to ALL tmux sessions, not just the overnight runner; acceptable for single-user personal tooling

## Install-mutation invocations

The pre-install in-flight guard at `cortex_command.install_guard.check_in_flight_install`
is opt-in by callers — not invoked at package import. New install-mutation entry points
must call it explicitly. Maintainers introducing one should re-run the audit greps below
and classify any new match.

**Audit sweeps** (run from repo root):

```sh
# Module-form invocations (python -m cortex_command.<module>)
grep -rn "python3 -m cortex_command\." --include="*.md" --include="*.sh" --include="*.toml" --include="Justfile" --include="justfile" .

# Shell-form invocations (cortex upgrade subcommand)
grep -rn "cortex upgrade" --include="*.md" --include="*.sh" --include="*.toml" --include="Justfile" --include="justfile" --include="*.py" .
```

**Current classification** (reviewed 2026-04-29 after ticket 141 no-clone-install migration):

- **Install-mutation**: `plugins/cortex-overnight-integration/server.py:_ensure_cortex_installed()` is the only install-mutation entry point under wheel install — it runs before each MCP tool handler delegates to a `cortex` subprocess; on cortex-absent it shells out to `uv tool install --reinstall git+<url>@<tag>` under a flock at `${XDG_STATE_HOME}/cortex-command/install.lock`, writes a sentinel on failure, and logs to `${XDG_STATE_HOME}/cortex-command/last-error.log` with `stage: "first_install"` (per spec R7f). The hook is its own concurrency guard via the flock; no `check_in_flight_install()` call is needed because first-install precedes any other install-mutation entry point in time.
- **Advisory (no install-mutation, retains guard)**: `cortex_command.cli._dispatch_upgrade()` — post-141 prints `/plugin update` and `uv tool install --reinstall` instructions and exits 0 without running any install. The `check_in_flight_install()` call is retained as the first statement of the handler for layered safety, but no install actually fires.
- **Dormant under wheel install (clone-install legacy)**: the `_orchestrate_upgrade` and `_orchestrate_schema_floor_upgrade` paths in `plugins/cortex-overnight-integration/server.py` (R10/R11/R12 in MCP auto-update flow) short-circuit under wheel install per ticket 141 Task 16 — they detect the absence of `.git/` at `cortex_root` and return early. Even when they fire (clone-install path retained for backward compatibility), the spawned `cortex upgrade` process is now advisory-only.
- **Non-install-mutation** (no guard call needed): `python3 -m cortex_command.overnight.smoke_test` (justfile), `python3 -m cortex_command.dashboard.seed [--clean]` (justfile), `python3 -m cortex_command.overnight.report` (morning-review), `python3 -m cortex_command.pipeline.metrics` (cortex-scan-lifecycle hook), `python3 -m cortex_command.common detect-phase` (lifecycle skill), `python3 -m cortex_command.overnight.daytime_pipeline` (lifecycle implement skill), `python3 -m cortex_command.overnight.daytime_result_reader` (lifecycle implement skill), `python3 -m cortex_command.overnight.batch_runner` (runner.sh, batch dispatch).
- **Documentation/comments only** (not invocation sites): `install.sh:64` error message, `cortex_command/install_guard.py` docstring, research/spec/backlog notes.

**Stale-pointer self-heal warning narrowing**: pre-ticket-151, `import cortex_command` fired the guard, so a stale active-session pointer would emit the self-heal warning on every package import — including IDE introspection and pytest collection. Ticket 151 narrowed the warning to fire only when `_dispatch_upgrade` runs against a stale pointer. Post-ticket-141, `_dispatch_upgrade` itself no longer runs an install (it is advisory-only), so the original self-heal-via-`_dispatch_upgrade` path is effectively dormant. The active install-mutation entry point (`_ensure_cortex_installed`) does not consume the active-session pointer, so no self-heal warning fires from the wheel-install path. Future telemetry/UX work may surface stale pointers through a different channel (e.g., `cortex overnight status` advisory).

## Open Questions

- None
