# Research: Add overnight session observability from within Claude Code sandbox

## Codebase Analysis

### Current State

From within a sandboxed Claude Code session, the only observability into an overnight run comes from reading lifecycle state files. The sandbox blocks:

- **tmux socket access**: `/private/tmp/tmux-503/default` — all tmux commands fail with "Operation not permitted"
- **localhost network access**: `WebFetch(domain:localhost)` and `WebFetch(domain:127.0.0.1)` are in the deny list (`claude/settings.json:203-204`), blocking dashboard access via curl
- **Process attachment**: no way to stream runner output or diagnose crashes in real-time

### Sandbox Configuration Architecture

The sandbox settings are structured as:

- **Repo defaults**: `claude/settings.json` — committed, shared
- **Machine overrides**: `~/.claude/settings.local.json` — gitignored, machine-specific

The `allowUnixSockets` field already exists under `sandbox.network` and is used for the GPG agent socket:
```json
"allowUnixSockets": ["~/.local/share/gnupg/S.gpg-agent.sandbox"]
```

This establishes the pattern for adding more unix socket paths.

`settings.local.json` currently contains only a `filesystem.allowWrite` override. It can accept additional `network.allowUnixSockets` entries via deep merge.

### tmux Socket Details

- **Default socket path**: `/private/tmp/tmux-503/default` (macOS, UID 503)
- **Path construction**: `/private/tmp/tmux-{UID}/default` — UID-specific, not expressible with `~`
- **No custom socket**: The runner (`bin/overnight-start`) uses `tmux new-session -d -s "$SESSION"` without `-S` — always the default socket
- **Session naming**: `overnight-runner` (with collision avoidance: `overnight-runner-2`, etc.)

### Available State Files

All session state lives under `lifecycle/sessions/{session_id}/`:

| File | Contents | Use for Status |
|------|----------|----------------|
| `overnight-state.json` | Full state machine: phase, features dict (status, round, timing, errors), round history | Primary: feature progress, phase, errors |
| `session.json` | Lightweight manifest: type, session_id, started, feature slugs | Quick: session identity |
| `overnight-events.log` | JSONL events: session_start, round_start/complete, orchestrator_failed, circuit_breaker, stall_timeout | Timeline: what happened when |
| `pipeline-events.log` | JSONL from batch_runner: dispatch, merge, retry, budget events per feature | Detailed: per-feature execution trace |
| `.runner.lock` | Single PID number | Liveness: is the process still alive? |
| `morning-report.md` | Post-run summary (when complete) | Final: completed session overview |
| `overnight-strategy.json` | Hot files, integration health, recovery notes | Diagnostic: strategic decisions |

The pointer to the active session is at `~/.local/share/overnight-sessions/active-session.json` (outside repo, contains `session_id`, `repo_path`, `state_path`, `phase`).

### Dashboard

- **App**: `claude/dashboard/app.py` (FastAPI)
- **Port**: 8080 default (`DASHBOARD_PORT` env var), binds `0.0.0.0`
- **PID file**: `claude/dashboard/.pid`
- **Endpoints**: `/health` (JSON), `/` (full HTML), `/sessions/{id}` (detail), plus HTMX partials for fleet, alerts, features, timeline
- **Data source**: reads the same state files listed above via `claude/dashboard/poller.py`

### Existing Overnight Tooling

- `skills/overnight/SKILL.md` — planning and launch skill with `/overnight resume` subcommand
- `/overnight resume` reads `overnight-state.json` for feature status/phase but does NOT check process liveness or tmux session state
- `bin/overnight-start` — launch script only, no status capability
- No `/overnight status` subcommand or standalone status script exists

## Approach Analysis

### Approach A: tmux Socket Allowlist

Add the tmux default socket to `allowUnixSockets` in `settings.local.json`:

```json
{
  "sandbox": {
    "network": {
      "allowUnixSockets": ["/private/tmp/tmux-503/default"]
    }
  }
}
```

**Pros:**
- Full visibility: `tmux has-session`, `tmux list-sessions`, `tmux attach` all work
- Minimal code change — one config entry
- Enables crash diagnosis by attaching to the session directly
- Follows the established `settings.local.json` pattern for machine-specific overrides

**Cons:**
- Path is UID-specific (`tmux-503`) — not portable across machines or users
- Must go in `settings.local.json` (machine-specific), not `settings.json` (committed)
- Grants full tmux access to the sandbox — all sessions, not just overnight-runner
- `tmux attach` from within Claude Code may not render correctly (nested terminal)
- Does not help non-interactive status checks (still need to parse tmux pane content)

**Verdict:** Provides the full-access escape hatch the user wants. Low effort, high reward for the interactive case. Not sufficient alone for programmatic status queries.

### Approach B: `/overnight status` Subcommand

Add a status subcommand to the overnight skill (or a standalone `bin/overnight-status` script) that reads state files + checks PID liveness:

1. Read `active-session.json` to find the current session
2. Read `overnight-state.json` for phase and feature progress
3. Read `.runner.lock` and check `kill -0 $PID` for process liveness
4. Read tail of `overnight-events.log` for recent activity
5. Format a one-shot status report

**Pros:**
- Works entirely within existing sandbox constraints (file reads + PID check via `kill -0`)
- Structured output suitable for both human and programmatic consumption
- Can aggregate information from multiple state files into a coherent view
- No security implications — read-only access to files already in the sandbox

**Cons:**
- Cannot stream runner output or show what Claude is currently doing
- PID check may fail if `.runner.lock` contains a stale PID (process died but lock wasn't cleaned)
- Adds a new skill/script to maintain

**Verdict:** Complements tmux access. Good for quick "is it alive and what's it doing?" checks without the overhead of attaching to tmux.

### Approach C: Dashboard Access from Sandbox

Remove `localhost`/`127.0.0.1` from the deny list to allow `curl http://localhost:8080/health`.

**Pros:**
- Dashboard already provides rich status, feature cards, timeline
- `/health` endpoint exists for quick liveness check
- HTMX partials could be fetched individually for focused status

**Cons:**
- Removing localhost from deny affects ALL sandbox network access, not just the dashboard
- The deny rule likely exists for security reasons (preventing sandboxed agents from accessing arbitrary local services)
- Dashboard may not be running during the overnight session
- HTML output is not ideal for programmatic consumption from within Claude Code

**Verdict:** Too broad a security relaxation for a narrow use case. Not recommended as a primary approach.

### Approach D: Runner Output Log (Alternative)

Have the runner tee its output to a log file under the session directory, readable from within the sandbox.

**Pros:**
- No sandbox config changes needed
- Provides historical output (not just current state)
- File-based, fits the observability pattern

**Cons:**
- Requires modifying the runner itself
- tmux already captures output — this duplicates it
- Does not provide real-time streaming (file-based tail lag)
- More invasive than the other approaches

**Verdict:** Not worth the runner modification. tmux socket access provides the same capability more cleanly.

### Recommended Approach: A + B (Hybrid)

1. **tmux socket allowlist** (Approach A) for full interactive access — attach to diagnose crashes, view live output
2. **`/overnight status` one-shot** (Approach B) for quick programmatic checks — is it alive, what phase, any errors

Approach C is rejected (too broad). Approach D is rejected (unnecessary if A is implemented).

## Open Questions

- Should `overnight status` be a subcommand of the existing `/overnight` skill or a standalone `bin/overnight-status` script? The skill route keeps it discoverable; the script route makes it callable from hooks/automation. Deferred: will be resolved in Spec by asking the user.
