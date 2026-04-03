# Requirements: observability

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The observability area covers three subsystems that give the developer real-time visibility into active Claude sessions: the terminal statusline (in-session context and lifecycle state), the web dashboard (full overnight session monitoring), and the notification system (macOS desktop and Android push alerts). All three subsystems read from the same file-based session state; none can write to it.

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

## Edge Cases

- **No active session**: Statusline renders git state only; dashboard hides Session and Fleet panels
- **Session directory rotation**: Dashboard resets event offset to 0 on session ID change and re-reads from scratch; possible duplicate alerts on first poll after reset
- **jq unavailable**: Statusline falls back to pure-bash regex parsing; may fail on complex JSON
- **ntfy.sh unreachable**: Remote notification silently times out after 5s; macOS notification unaffected
- **NTFY_TOPIC not set**: Remote notification hook exits silently at line 10; no error raised
- **Not running in tmux**: Remote notification hook exits silently; session name identification skipped

## Open Questions

- None
