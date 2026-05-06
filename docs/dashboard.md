[← Back to Agentic Layer](agentic-layer.md)

# Overnight Dashboard

**For:** Users running overnight sessions who want real-time visibility into session progress.  **Assumes:** The overnight runner is set up and you have at least one session running or recently completed.

The dashboard is a real-time FastAPI web app that monitors overnight autonomous development sessions. It reads the same files the overnight runner writes and displays live state in a browser via HTMX polling. It is optional but recommended for unattended sessions — open it on a second monitor before you go to bed.

---

## Launching the Dashboard

```
cortex dashboard
```

Opens at `http://localhost:8080` (or `$DASHBOARD_PORT` if set, or `--port <int>`). Includes a PID check — if an instance is already running, the command prints the URL and exits without starting a second server.

**Prerequisite**: `cortex dashboard` requires a cortex-registered project — run `cortex init` once in your project before launching the dashboard, or set `CORTEX_REPO_ROOT` to point at a registered project. The verb fails with a `RuntimeError` if `.claude/` is not present in the resolved root.

Contributors with a clone of cortex-command can alternatively run `just dashboard` (requires a clone of cortex-command) from the repo root.

### Prerequisites

- Python 3.12+ and the project uv venv (`just python-setup` — same prerequisite as the overnight runner)
- No additional setup required

---

## What It Shows

The dashboard is divided into seven panels.

### 1. Session Panel

Live indicator, session ID, phase status, current round, elapsed time, progress bar, and feature counts broken down by status (merged / running / pending / paused / failed / deferred). When no session is active, the panel falls back to showing the last completed session.

### 2. Feature Cards

One card per feature in the session. Each card shows the feature title, status badge, model tier, and complexity. Running features display the current phase and a task progress bar. Failed features show the error message and recovery attempt count. Alert badges surface deferred questions, stalls, rework, and failures at a glance.

### 3. Agent Fleet Panel

Count of active agents and, for each agent: its feature slug, current phase, duration, and last activity timestamp. Useful for confirming that agents are making progress and not stalled.

### 4. Alerts Banner

Circuit breaker status and per-feature alert indicators with severity-coded colors. A tripped circuit breaker means the runner has paused new dispatches due to repeated failures.

### 5. Round History Table

Chronological list of completed rounds with feature counts and per-round durations. Shows how the session has progressed over time.

### 6. Swim-Lane Timeline

Horizontal timeline of feature execution, color-coded by phase (spec, plan, implement, review), with time ticks along the axis. Gives a visual overview of how features overlapped and where time was spent.

### 7. Pipeline Panel

Monitors active interactive pipeline execution (separate from overnight). Visible only when an interactive pipeline session is running alongside the overnight session.

---

## Session History

Navigate to `/sessions` to list past sessions. `/sessions/{session_id}` shows the per-session detail view for any completed session. Both views are read-only.

---

## Data Sources

The dashboard reads directly from files written by the overnight runner — no separate data pipeline is needed:

- `overnight-state.json` — session metadata and per-feature statuses. Key fields: `session_id` (unique session identifier), `phase` (session phase: `planning` | `executing` | `complete` | `paused`), `current_round` (1-based round number), `started_at` (ISO 8601 UTC timestamp), `features` (mapping of feature slug → status object with `status`, `started_at`, `completed_at`, `error`, and `recovery_attempts`), `round_history` (list of completed round summaries).
- `overnight-events.log` — NDJSON event stream (one JSON object per line). Each line has the form: `{"v": 1, "ts": "<ISO-8601>", "event": "<type>", "session_id": "...", "round": N}` with optional `"feature"` and `"details"` fields. Event types include `session_start`, `feature_start`, `feature_complete`, `feature_failed`, `circuit_breaker`, and others.
- `lifecycle/{slug}/plan.md` — task-level progress for each feature
- `backlog/*.md` — feature titles and frontmatter status fields
- `metrics.json` — API cost data

For the schemas, state machine, and lifecycle of these files, see [overnight-operations.md](overnight-operations.md).

### Polling Intervals

The dashboard uses two polling layers:

| Layer | Target | Interval |
|-------|--------|----------|
| Backend (server-side) | `overnight-state.json` and per-feature files | every 2 s |
| Backend (server-side) | `overnight-events.log` (NDJSON tail) | every 1 s |
| Backend (server-side) | Backlog counts | every 30 s |
| HTMX (browser-side) | All dashboard panels | every 5 s |

Total state-change latency is up to approximately 7 seconds (2 s backend read + 5 s HTMX refresh).

---

## Visual Evaluation with Playwright MCP

Playwright MCP gives Claude interactive browser access to the running dashboard — navigate, screenshot, and inspect the UI using Claude's multimodal vision. This closes the feedback loop between code changes and visual outcomes during interactive development.

### Prerequisites

- **Node.js 18+** must be installed (`node --version` to verify). All Python-based skills (`ui-judge`, `ui-a11y` — now in the `cortex-ui-extras` plugin from the `cortex-command` marketplace) work without Node.js; only Playwright MCP requires it.
- On first use, the MCP server automatically downloads Chromium browser binaries (~150MB). No manual setup step is required, but the first tool call will be slower while the download completes.

### Per-Session Setup

Before using Playwright MCP tools, start the dashboard with fixture data:

```
just dashboard-seed   # load fixture data
just dashboard        # start dashboard server at http://localhost:8080
```

Then ask Claude to navigate and screenshot the dashboard — for example: *"Take a screenshot of the dashboard at localhost:8080 and describe what you see."*

### Playwright MCP and Existing Evaluation Skills

The three visual evaluation tools are complementary and serve different purposes:

| Tool | Purpose | When to use |
|------|---------|-------------|
| `ui-judge` skill (plugin) | Structured rubric-based evaluation (UICrit pattern) | Overnight sessions, automated quality gates, scoring against defined criteria |
| `ui-a11y` skill (plugin) | Accessibility checking against WCAG guidelines | Verifying accessibility compliance |
| Playwright MCP | Ad-hoc interactive visual access | Development-time inspection, iterating on UI changes, exploratory visual debugging |

`ui-judge` and `ui-a11y` are no longer bundled by default. They ship in the `cortex-ui-extras` plugin from the `cortex-command` marketplace and require the plugin to be installed and enabled (`/plugin install cortex-ui-extras@cortex-command`; see [docs/setup.md](setup.md) for the full install walkthrough).

Playwright MCP is a development tool for interactive sessions — it is **not** used in overnight or autonomous agent runs. Overnight evaluation uses `ui-judge` and `ui-a11y` (when the plugin is enabled), which produce structured output compatible with unattended execution. Playwright MCP's per-session approval prompt makes it incompatible with unattended use.

### Bumping the Playwright MCP Version

The MCP server is pinned to a specific version in `.mcp.json` to avoid regressions. To update, edit `.mcp.json` and change the `@playwright/mcp@<version>` string to the desired version, then restart Claude Code to pick up the change.

---

## Known Limitations

- No authentication layer — the server binds to `0.0.0.0` (all interfaces) and is accessible to any host on the local network. Do not expose the port beyond a trusted local or internal network. (The `127.0.0.1` address visible in `app.py` is a pre-launch port-availability probe, not the listen address.)
- Session history is read-only — the dashboard cannot trigger retries or modify session state.
- Visual layout may vary between active and idle states; some panels (Agent Fleet, Pipeline) are hidden when there is no active session.
