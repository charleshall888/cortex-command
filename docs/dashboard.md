[← Back to Agentic Layer](agentic-layer.md)

# Overnight Dashboard

**For:** Users running overnight sessions who want real-time visibility into session progress.  **Assumes:** The overnight runner is set up and you have at least one session running or recently completed.

The dashboard is a real-time FastAPI web app that monitors overnight autonomous development sessions. It reads the same files the overnight runner writes and displays live state in a browser via HTMX polling. It is optional but recommended for unattended sessions — open it on a second monitor before you go to bed.

Both launch paths bind `127.0.0.1` (loopback only) by default: the shipped `cortex dashboard` verb always binds loopback, and the contributor recipe `just dashboard` defaults to loopback with LAN exposure available only as an explicit opt-in — `DASHBOARD_HOST=0.0.0.0 just dashboard`, or equivalently `just dashboard_host=0.0.0.0 dashboard`.

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

### Viewing the Dashboard Remotely

Loopback-only is deliberate for the shipped `cortex dashboard` verb, which offers no `--host` flag. Remote viewing is served by port-forwarding over the existing Tailscale mesh rather than by binding another interface:

```
ssh -L 8080:127.0.0.1:8080 <host>
```

With the tunnel open, browse to `http://localhost:8080` on the viewing machine — the dashboard stays bound to loopback on the machine running the session, and the Tailscale mesh supplies the secure channel.

---

## Seeding Fixture Data

```
just dashboard-demo
```

`dashboard-demo` is the single command: it seeds the fixture corpus into an isolated per-user root and serves the dashboard against that root in one invocation. Without the justfile, run the same two steps directly:

```
cortex-dashboard-seed                    # writes the fixture root, then prints the serve command
cortex dashboard --root <printed root>   # serves the dashboard against that root
```

### Where the fixtures land

The seeder writes to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/dashboard-seed/`. Seeding no longer writes into your own repo. Earlier versions targeted the operator's real repository so fixtures would appear alongside real work, and that is what made them dangerous: they clobbered canonical lifecycle files, replaced the single-active-session `overnight-state.json` symlink with a regular file, installed a fake `executing` session that the launchd guardian treated as an unattended recovery target, and leaked fixture output into git history. Containing the seeder to an isolated root removes all of it by construction — `--clean` can no longer reach a tracked file, and the 990–999 backlog ID reservation the old regime required is gone rather than replaced.

`cortex-dashboard-seed --root PATH` overrides the default root; `--print-root` prints the resolved root and exits; `--clean` removes only what the seeder wrote, under that same resolved root. If you ran the pre-containment seeder against a project repo, `cortex-dashboard-seed --sweep-legacy` removes the stray `99[0-9]-seed-*.md` backlog files it left behind — a one-time migration, not part of normal use.

`cortex dashboard --root PATH` sets the root for that one process only. Do not export or inline-prefix `CORTEX_REPO_ROOT` to view fixtures: it is the unvalidated root funnel for most of the codebase, and a fixture root satisfies every marker check that guards it — so any persistence beyond one command silently redirects backlog creation, lifecycle verbs, and overnight writes into the throwaway tree.

**Behavioral note**: `just dashboard-seed` alone no longer populates your own dashboard. `just dashboard-demo` is the replacement.

### Seeded and unseeded runs cover different regimes

Both regimes matter, and neither substitutes for the other:

| Run | Corpus | What it exercises |
|-----|--------|-------------------|
| Unseeded (`cortex dashboard`) | your real project | An unseeded project is the only exercise of the near-empty and degraded rendering path the panels commit to |
| Seeded (`just dashboard-demo`) | isolated fixture root | Seeded runs cover volume and state variety — epics and children, every blocker outcome, both deferral vocabularies, lifecycle artifacts, and rendered markdown |

---

## What It Shows

The dashboard is divided into ten panels plus an Alerts Banner.

### Alerts Banner

Circuit breaker status and per-feature alert indicators with severity-coded colors. A tripped circuit breaker means the runner has paused new dispatches due to repeated failures.

### 1. Session Panel

Live indicator, session ID, phase status, current round, elapsed time, progress bar, and feature counts broken down by status (merged / running / pending / paused / failed / deferred). When no session is active, the panel falls back to showing the last completed session.

### 2. Open Questions / Escalations

Surfaces worker-to-orchestrator escalations for the active session — open questions, deferred work, and blocking items that require human review. Reads from the per-session `escalations.jsonl` file.

### 3. Feature Cards

One card per feature in the session. Each card shows the feature title, status badge, model tier, and complexity. Running features display the current phase and a task progress bar. Failed features show the error message and recovery attempt count. Alert badges surface deferred questions, stalls, rework, and failures at a glance.

### 4. Recent Activity Stream

Tails the most recent entries from `overnight-events.log`, surfacing the live event stream so operators can see what the runner is doing right now without scanning the full log.

### 5. Agent Fleet Panel

Count of active agents and, for each agent: its feature slug, current phase, duration, and last activity timestamp. Useful for confirming that agents are making progress and not stalled.

### 6. Swim-Lane Timeline

Horizontal timeline of feature execution, color-coded by phase (spec, plan, implement, review), with time ticks along the axis. Gives a visual overview of how features overlapped and where time was spent.

### 7. Metrics Baseline

API cost and token-usage rollups read from `metrics.json`. Provides at-a-glance spend tracking for the active session and a baseline for comparing against prior runs.

### 8. Round History Table

Chronological list of completed rounds with feature counts and per-round durations. Shows how the session has progressed over time.

### 9. Pipeline Panel

Monitors active interactive pipeline execution (separate from overnight). Visible only when an interactive pipeline session is running alongside the overnight session.

### 10. Backlog

Backlog status counts and ready-queue summary, sourced from `cortex/backlog/`. Provides context on what's queued for the next session without leaving the dashboard.

### 11. Triage Board

Every active ticket as a row, grouped one section per epic with a flat list beneath for items no epic parents, sourced from the same backlog snapshot as § 10. Rows carry status, priority, and type, plus an ineligibility reason, unresolved blocker refs, or a deferral flag where they apply — the persistent answer to "what should I work on, and what's blocked on what" without re-running triage in a session. Rows are non-navigational disclosures; the per-ticket reader is a separate surface.

---

## Session History

Navigate to `/sessions` to list past sessions. `/sessions/{session_id}` shows the per-session detail view for any completed session. Both views are read-only.

---

## Data Sources

The dashboard reads directly from files written by the overnight runner — no separate data pipeline is needed:

**Session state**

- `~/.local/share/overnight-sessions/active-session.json` — session pointer. Resolves which session directory the state and event files live in; the dashboard falls back to the local `cortex/lifecycle/` copies when the pointer is absent.
- `overnight-state.json` — session metadata and per-feature statuses. Key fields: `session_id` (unique session identifier), `phase` (session phase: `planning` | `executing` | `complete` | `paused`), `current_round` (1-based round number), `started_at` (ISO 8601 UTC timestamp), `features` (mapping of feature slug → status object with `status`, `started_at`, `completed_at`, `error`, and `recovery_attempts`), `round_history` (list of completed round summaries).
- `overnight-events.log` — NDJSON event stream (one JSON object per line). Each line has the form: `{"v": 1, "ts": "<ISO-8601>", "event": "<type>", "session_id": "...", "round": N}` with optional `"feature"` and `"details"` fields. Event types include `session_start`, `feature_start`, `feature_complete`, `feature_failed`, `circuit_breaker`, and others.
- `pipeline-state.json` — interactive pipeline state, read from `cortex/lifecycle/sessions/latest-pipeline/`. Absent is the normal "no active pipeline" signal, and the Pipeline panel reflects that.
- `pipeline-events.log` — `dispatch_start` events supplying each feature's model tier, complexity, budget, and criticality.
- `metrics.json` — API cost and token-usage data

**Per-feature files** (under `cortex/lifecycle/{slug}/`)

- `plan.md` — task-level progress for each feature
- `events.log` — phase transitions and per-phase timings
- `agent-activity.jsonl` — tool activity, last-activity timestamps, and incremental cost deltas (read by offset, so no double-counting)
- `escalations.jsonl` — open questions and worker-to-orchestrator escalations
- `exit-reports/*.json` — per-task worker exit reports
- `pr.json` — the feature's PR artifact
- `learnings/progress.txt` — recovery attempt history for failed and paused features

**Backlog and configuration**

- `cortex/backlog/*.md` — feature titles and frontmatter status fields
- `cortex/backlog/archive/*.md` — archived items, so a blocker pointing at a terminal ticket resolves as resolved rather than missing
- `cortex/lifecycle.config.md` — backlog backend. The `cortex/backlog/` reads above happen only while `resolve_backlog_backend(root)` resolves to `cortex-backlog`; under any other backend the dashboard stands down rather than showing stale local counts.

For the schemas, state machine, and lifecycle of these files, see [overnight-operations.md](overnight-operations.md).

### Polling Intervals

The dashboard uses two polling layers:

| Layer | Target | Interval |
|-------|--------|----------|
| Backend `_poll_state_files` | `overnight-state.json`, `pipeline-state.json`, and per-feature files | every 2 s |
| Backend `_poll_jsonl_events` | `overnight-events.log` (NDJSON tail) | every 1 s |
| Backend `_poll_alerts` | Alert evaluation (stalls, failures, circuit breaker) | every 5 s |
| Backend `_poll_slow` | Backlog counts, ticket feed, dispatch details, metrics | every 30 s |
| HTMX (browser-side) | Alerts Banner, Session, Feature Cards, Agent Fleet, Swim-Lane, Round History, Escalations | every 5 s |
| HTMX (browser-side) | Recent Activity Stream | every 3 s |
| HTMX (browser-side) | Metrics Baseline, Backlog, Triage Board | every 30 s |

Total state-change latency is up to approximately 7 seconds (2 s backend read + 5 s HTMX refresh) for panels on the 5 s HTMX interval. For 30 s-polling panels (Metrics Baseline, Backlog, Triage Board), end-to-end latency is up to approximately 32 seconds.

---

## Visual Evaluation with Playwright MCP

Playwright MCP gives Claude interactive browser access to the running dashboard — navigate, screenshot, and inspect the UI using Claude's multimodal vision. This closes the feedback loop between code changes and visual outcomes during interactive development.

### Prerequisites

- **Node.js 18+** must be installed (`node --version` to verify). All Python-based skills (`ui-judge`, `ui-a11y` — now in the `cortex-ui-extras` plugin from the `cortex-command` marketplace) work without Node.js; only Playwright MCP requires it.
- On first use, the MCP server automatically downloads Chromium browser binaries (~150MB). No manual setup step is required, but the first tool call will be slower while the download completes.

### Per-Session Setup

Before using Playwright MCP tools, start the dashboard with fixture data:

```
just dashboard-demo   # seed the fixture root and serve the dashboard against it
```

The server comes up at `http://localhost:8080`. See [Seeding Fixture Data](#seeding-fixture-data) for what the fixtures cover and where they live.

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

- No authentication layer — both launch paths bind `127.0.0.1` (loopback only) by default, so the dashboard is reachable only from the local machine. The contributor recipe `just dashboard` can bind other interfaces via an explicit opt-in (`DASHBOARD_HOST=0.0.0.0 just dashboard`); the shipped `cortex dashboard` verb offers no equivalent, and remote viewing goes through the `ssh -L` port-forward described above.
- Session history is read-only — the dashboard cannot trigger retries or modify session state.
- Visual layout may vary between active and idle states; with no active session the Agent Fleet and Pipeline panels stay in place and render empty-state text (`fleet stood down · no session`, `no pipeline · refinement queue empty`) rather than disappearing.

### Threat model

The loopback default is defense-in-depth, not a sanitizer. The dashboard renders agent-generated markdown as unescaped HTML and validates neither the `Host` nor the `Origin` header, so a residual DNS-rebinding risk against an unauthenticated local service remains accepted rather than closed. What the bind default changes is who can reach the server at all.

With the default in place, only the local machine can. Once the `DASHBOARD_HOST` opt-in binds another interface, anyone on the same layer-2 broadcast domain can read session state, feature names, and log excerpts without authenticating. Do not expose that port to the public internet, and do not treat "local network" as equivalent to "home network" — hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs are all "local" to a non-loopback bind and are not trusted peers. The framing trap bites hardest at 2am, so the corollary is worth stating plainly: the opt-in assumes a peer set the operator controls end-to-end, and every other case is better served by the `ssh -L` port-forward above.
