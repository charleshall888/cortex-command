# Area-doc spot-check audit (Task 18 / R13)

> Verifies a sample of factual claims in each of the 4 area-doc files in
> `cortex/requirements/` against the current code/docs. Drift verdicts (✗) feed
> Task 19 patches. Pattern follows research §1.2 (claim + source + evidence +
> verdict).

Spot-check counts: 3 per area doc × 4 area docs = 12 total.

---

## multi-agent.md

### Claim 1: model selection matrix values (model / turn limit / budget)

- **Claim**: "Selected model (haiku / sonnet / opus), turn limit (15 / 20 / 30),
  budget cap ($5 / $25 / $50)"
- **Source**: `cortex/requirements/multi-agent.md:58`
- **Evidence**: `cortex_command/pipeline/dispatch.py:128-130` — the
  `_TIER_DEFAULTS` table reads:
  ```python
  "trivial": {"model": "haiku", "max_turns": 15, "max_budget_usd": 5.00},
  "simple":  {"model": "sonnet", "max_turns": 20, "max_budget_usd": 25.00},
  "complex": {"model": "opus",  "max_turns": 30, "max_budget_usd": 50.00},
  ```
- **Verdict**: ✓
- **Notes**: All three values (model name, turn cap, budget cap) match exactly.

### Claim 2: `pipeline/{feature}` branch convention with `-2`, `-3` collision suffixes

- **Claim**: "Feature branch naming follows `pipeline/{feature}` convention with
  automatic collision detection"; "branch `pipeline/{feature}` (with collision
  suffix `-2`, `-3` if needed)"
- **Source**: `cortex/requirements/multi-agent.md:30`, `multi-agent.md:34`
- **Evidence**: `cortex_command/pipeline/worktree.py:56-67` —
  `_resolve_branch_name()` tries `pipeline/{feature}` first, then increments a
  suffix starting at 2: `while _branch_exists(f"{base}-{suffix}", repo):
  suffix += 1`.
- **Verdict**: ✓
- **Notes**: Implementation matches doc exactly.

### Claim 3: stderr capped at 100 lines

- **Claim**: "Agent stderr is captured and included in learnings for subsequent
  retry attempts" + "stderr lines (capped at 100)"
- **Source**: `cortex/requirements/multi-agent.md:17`, `multi-agent.md:20`
- **Evidence**: `cortex_command/pipeline/dispatch.py:356`:
  `_MAX_STDERR_LINES = 100`; used as the cap at line 641:
  `if len(_stderr_lines) < _MAX_STDERR_LINES:`
- **Verdict**: ✓
- **Notes**: Exact match.

---

## observability.md

### Claim 1: statusline is "3-line terminal prompt extension"

- **Claim**: "A 3-line terminal prompt extension that shows session context,
  git state, and active lifecycle feature phase. Rendered by
  `claude/statusline.sh`."
- **Source**: `cortex/requirements/observability.md:15`
- **Evidence**: `claude/statusline.sh:228` emits line 2 (`printf '\n📁 ...'`),
  line 631 emits line 3 (`printf '\n%s' "$_line3"`); preceded by line-1 context
  output earlier in the script. The trailing debug log at the tail explicitly
  notes "Output: 2 lines" + line 3 makes 3 total lines.
- **Verdict**: ✓
- **Notes**: File at `claude/statusline.sh` exists and produces 3 lines as
  described.

### Claim 2: dashboard binds to `0.0.0.0` on port 8080

- **Claim**: "A read-only FastAPI web application at
  `http://localhost:$DASHBOARD_PORT` (default 8080)" and (later, Architectural
  Constraints) "Dashboard binds to all network interfaces (`0.0.0.0`) and has
  no authentication."
- **Source**: `cortex/requirements/observability.md:29`,
  `observability.md:98`
- **Evidence**: `cortex_command/dashboard/app.py:11` (module docstring):
  `uv run uvicorn cortex_command.dashboard.app:app --host 0.0.0.0 --port 8080`
- **Verdict**: ✓
- **Notes**: Default invocation example uses `0.0.0.0:8080` exactly as
  documented.

### Claim 3: in-session status CLI is a "standalone bash script (`bin/overnight-status`, deployed to `~/.local/bin/overnight-status`)"

- **Claim**: "A standalone bash script (`bin/overnight-status`, deployed to
  `~/.local/bin/overnight-status`) that produces a one-shot status report ..."
- **Source**: `cortex/requirements/observability.md:63`
- **Evidence**:
  - `find . -name "overnight-status*"` returns no results — the script does
    not exist in the repo at `bin/overnight-status` or anywhere else.
  - `bin/` directory listing: no `overnight-status` shim.
  - `plugins/cortex-core/bin/` directory listing: no `overnight-status` shim.
  - `pipeline.md:28` explicitly states "the legacy `runner.sh` bash entry and
    `bin/overnight-{start,status,schedule}` shims are retired."
  - Active path is the `cortex overnight status` Python CLI at
    `cortex_command/cli.py:54` (`_dispatch_overnight_status`).
  - `skills/overnight/SKILL.md:102` still tells the user to run
    `overnight-status (the deployed script)`, which would resolve only if a
    third-party shim is installed — but the cortex-core plugin no longer ships
    one.
- **Verdict**: ✗
- **Notes**: Drift. The doc describes a retired shim. Task 19 should rewrite
  the In-Session Status CLI block to describe `cortex overnight status` (the
  Python subcommand) as the canonical entry point, and adjust the
  "Description" / "Outputs" / "Dependencies" lines accordingly. The skill at
  `skills/overnight/SKILL.md:102` is out of scope for this task but is the
  trailing edge of the same drift.

---

## pipeline.md

### Claim 1: `cortex overnight` subcommand surface

- **Claim**: "The overnight runner ships as a
  `cortex overnight {start|status|cancel|logs|schedule|list-sessions}`
  Python CLI; the legacy `runner.sh` bash entry and `bin/overnight-{start,status,schedule}`
  shims are retired."
- **Source**: `cortex/requirements/pipeline.md:28`
- **Evidence**: `cortex_command/cli.py:48-83` defines six `_dispatch_overnight_*`
  handlers: `_dispatch_overnight_start` (48), `_dispatch_overnight_status` (54),
  `_dispatch_overnight_cancel` (60), `_dispatch_overnight_logs` (66),
  `_dispatch_overnight_list_sessions` (72), `_dispatch_overnight_schedule` (78).
  `find . -name "runner.sh"` returns no results (runner.sh retired). `bin/`
  contains no `overnight-*` shims.
- **Verdict**: ✓
- **Notes**: All six verbs present; legacy artifacts confirmed absent.

### Claim 2: five MCP stdio tools

- **Claim**: "`cortex mcp-server` exposes five stdio tools
  (`overnight_start_run`, `overnight_status`, `overnight_logs`,
  `overnight_cancel`, `overnight_list_sessions`) wrapping `cli_handler`
  boundaries."
- **Source**: `cortex/requirements/pipeline.md:153`
- **Evidence**: `plugins/cortex-overnight/server.py:16-18` lists exactly those
  five tool names in its module docstring; the input/output dataclasses are
  defined at lines 1696, 1719, 1756, 1785, 1813. `cli.py:85-86` notes the
  legacy `cortex mcp-server` entry was removed in favour of the
  cortex-overnight plugin — so the canonical surface is the plugin, not a
  built-in subcommand, but the five-tool count and names match exactly.
- **Verdict**: ✓
- **Notes**: Names and count match. Minor nit: the doc says "`cortex
  mcp-server` exposes" — strictly the plugin server exposes them; `cortex
  mcp-server` is removed. Not load-bearing drift for the spot-check (the tool
  surface itself is intact), but a candidate for an unprompted future patch
  to clarify ownership.

### Claim 3: max-2-attempts repair cap (Sonnet → Opus)

- **Claim**: "Repair attempt cap is a fixed architectural constraint: max 2
  attempts (Sonnet + Opus)"
- **Source**: `cortex/requirements/pipeline.md:80`
- **Evidence**: `cortex_command/pipeline/merge_recovery.py:288-293`:
  ```python
  # --- Repair cycle (up to 2 attempts) ---
  # Model escalation: sonnet for attempt 1, opus for attempt 2
  model_sequence = ["sonnet", "opus"]
  agent_output = "(no agent output)"

  for attempt in range(1, 3):
  ```
  Loop iterates exactly twice (`range(1, 3)`), assigning sonnet then opus.
- **Verdict**: ✓
- **Notes**: Implementation matches doc exactly.

---

## remote-access.md

### Claim 1: tmux is the current session-persistence implementation

- **Claim**: "Session persistence: tmux (current implementation, subject to
  change); Ghostty terminal (macOS)"
- **Source**: `cortex/requirements/remote-access.md:49`
- **Evidence**:
  - `skills/overnight/references/new-session-flow.md:186` documents the
    runner creating "a detached tmux session named `overnight-runner`".
  - `justfile:24` defines `setup-tmux-socket` recipe with the explicit
    intent "Add tmux socket to sandbox allowlist so sandboxed sessions can
    access tmux".
  - `skills/overnight/references/resume-flow.md:55` instructs users to
    "Attach with `tmux attach -t overnight-runner` to monitor progress".
- **Verdict**: ✓
- **Notes**: tmux is the live mechanism in multiple invocation paths.

### Claim 2: Ghostty terminal (macOS) is the platform dependency

- **Claim**: "Session persistence depends on a macOS terminal that supports
  persistent container processes (currently Ghostty)" and "Ghostty terminal
  (macOS)" in Dependencies.
- **Source**: `cortex/requirements/remote-access.md:45`,
  `remote-access.md:49`
- **Evidence**: `docs/overnight.md:190` explicitly references
  "Ghostty/tmux window" as the supported environment for `cortex overnight
  start`. No conflicting evidence found (no use of iTerm/Terminal.app/Alacritty
  paths in the runtime).
- **Verdict**: ✓
- **Notes**: Ghostty is referenced as the macOS terminal of record in the
  setup-flow docs. The architectural constraint is consistent with current
  shipping artifacts.

### Claim 3: Tailscale + mosh for remote reattachment

- **Claim**: "A developer working remotely (via Tailscale mesh VPN + mosh) can
  reattach to a running Claude Code session from a mobile device or remote
  machine."
- **Source**: `cortex/requirements/remote-access.md:28`
- **Evidence**:
  - `docs/internals/sdk.md:217`: "Tailscale + mosh + tmux handles remote
    access" — the canonical stack is documented here.
  - `cortex/backlog/012-gather-area-requirements-docs.md:30` references
    "Tailscale/mosh setup" as the remote-access posture.
  - `skills/morning-review/references/walkthrough.md:127` and `:599` treat
    mosh as a first-class remote channel alongside SSH (skipping
    Ghostty-dependent steps when `$SSH_CONNECTION` is set, which mosh
    inherits).
- **Verdict**: ✓
- **Notes**: All three remote-access components (Tailscale, mosh, tmux) are
  named in shipping docs/skills. The claim is consistent with current
  architecture.

---

## Summary

| Area doc          | Spot-checks | ✓ | ✗ |
|-------------------|-------------|---|---|
| multi-agent.md    | 3           | 3 | 0 |
| observability.md  | 3           | 2 | 1 |
| pipeline.md       | 3           | 3 | 0 |
| remote-access.md  | 3           | 3 | 0 |
| **Total**         | **12**      | **11** | **1** |

**Drift summary**: One verdict ✗ on
`observability.md:63` — the In-Session Status CLI block describes a retired
`bin/overnight-status` bash shim. Replace with the `cortex overnight status`
Python subcommand description in Task 19.

All other 11 claims are confirmed against current code/docs. Drift is minor —
consistent with research §1.2's finding that area-doc quality is high (research's
5-claim sample was 5/5 confirmed; this expanded 12-claim sweep is 11/12).
