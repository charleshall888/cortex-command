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

- **Description**: Two notification scripts deliver alerts through different channels: macOS desktop notifications via `terminal-notifier` (`hooks/cortex-notify.sh`), and Android push notifications via ntfy.sh HTTP API (`hooks/cortex-notify-remote.sh`).
- **Inputs**: Claude Code Stop/Notification hook JSON; dashboard alert evaluation; `NTFY_TOPIC` environment variable; `TMUX` environment variable
- **Outputs**: macOS desktop notification; Android push via `https://ntfy.sh/$NTFY_TOPIC`; terminal bell
- **Acceptance criteria**:
  - macOS notification fires on session stop with correct type label (permission / idle / complete)
  - Android notification fires when `NTFY_TOPIC` is set and session is running in tmux
  - Subagent sessions are suppressed (no notification when `agent_id` is present in hook JSON)
  - Notification delivery failure is silent (hook exits 0; session is not blocked)
  - Dashboard-triggered notifications respect the same deduplication (stall fires once; clears when resolved)
- **Priority**: must-have

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
- **Notifications (Android)**: `curl`, `jq`, `NTFY_TOPIC` env var, tmux session (`TMUX` env var), network access to ntfy.sh
- **In-Session Status CLI**: `jq`, `bash`; file-based session state at `lifecycle/sessions/` and `~/.local/share/overnight-sessions/`
- **Sandbox Socket Access**: `jq`, `just` (setup recipe); `~/.claude/settings.json` and `~/.claude/settings.local.json`

## Edge Cases

- **No active session**: Statusline renders git state only; dashboard hides Session and Fleet panels
- **Session directory rotation**: Dashboard resets event offset to 0 on session ID change and re-reads from scratch; possible duplicate alerts on first poll after reset
- **jq unavailable**: Statusline falls back to pure-bash regex parsing; may fail on complex JSON
- **ntfy.sh unreachable**: Remote notification silently times out after 5s; macOS notification unaffected
- **NTFY_TOPIC not set**: Remote notification hook exits silently at line 10; no error raised
- **Not running in tmux**: Remote notification hook exits silently; session name identification skipped

- **Stale PID in `.runner.lock`**: Runner died but lock file not cleaned up; `kill -0` returns non-zero; status CLI reports "dead (stale PID)" rather than "alive"
- **Corrupt `overnight-state.json`**: Truncated write during active session; status CLI falls back to events-only output
- **`settings.local.json` array clobber**: Adding `allowUnixSockets` via naive jq write could destroy `filesystem.allowWrite`; setup recipe uses deep merge to preserve sibling keys
- **tmux socket grants broad access**: Allowlisting the default tmux socket grants access to ALL tmux sessions, not just the overnight runner; acceptable for single-user personal tooling

## Open Questions

- None
