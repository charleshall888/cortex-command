# Research: Claude Code SDK Usage

## Research Questions

1. What Claude Code SDK primitives does this project currently use (Agent, worktree isolation, team mode, RemoteTrigger, SendMessage, Task tools, CronCreate, etc.) and in which files?
   → **Answered below in Codebase Analysis. Summary: `Agent` tool (with and without worktree isolation) + `claude_agent_sdk.query()` Python SDK + hook events. Everything else is unused.**

2. How is the `Agent` tool used — what subagent types, how often, and in what contexts (inline vs. skill instructions)?
   → **Two distinct invocation paths: (1) direct `Agent` tool calls embedded in SKILL.md instruction files for interactive parallel execution, and (2) Python `claude_agent_sdk.query()` calls in the overnight pipeline for fully autonomous dispatch. Subagent type used in cortex-command skill files: `"general-purpose"` only (in clarify-critic.md). All other skill-level Agent calls omit `subagent_type` entirely. The Python pipeline path does not use subagent types — it selects models directly via Haiku/Sonnet/Opus.**

3. How is worktree isolation (`isolation: "worktree"`) used and where?
   → **Used in lifecycle skill for parallel multi-feature execution and in implement.md for parallel task batches. Backed by WorktreeCreate/WorktreeRemove hooks that handle the git operations. Sandbox restriction on `.claude/worktrees/` makes `Agent(isolation: "worktree")` the only safe path (manual `git worktree add` is forbidden in sandbox).**

4. How are `RemoteTrigger`, `SendMessage`, and Task tools (`TaskCreate`, `TaskUpdate`, etc.) used across skills and hooks?
   → **None are used. The project implements equivalent functionality through its own file-based state machine, NDJSON event logs, and Python orchestration modules.**

5. What Claude Code SDK capabilities exist that this project doesn't currently use at all?
   → **SendMessage, TaskCreate/TaskUpdate/TaskList/TaskGet/TaskStop/TaskOutput, CronCreate/CronDelete/CronList, TeamCreate/TeamDelete, EnterPlanMode/ExitPlanMode, EnterWorktree/ExitWorktree, RemoteTrigger, Agent `run_in_background`, Agent `resume`, per-agent `mode` override.**

6. Where are the biggest gaps between current SDK usage and the overnight autonomous execution vision?
   → **In-memory context restoration on agent interrupt (distinct from the existing state-machine recovery in `interrupt.py`, which already handles state restart); scheduled triggering (shell scripts instead of CronCreate); and cross-session task visibility (file state is queryable but only by agents that explicitly read the files — `status.py` provides some cross-session query capability already).**

7. Are there any mismatches — places where SDK primitives are used in suboptimal ways or not used where they clearly should be?
   → **Experimental agent teams enabled but unused (and `teammateMode=inprocess` is an active global configuration, not just a dormant env var); the Python orchestration layer reinvents what SDK Task tools provide; `run_in_background` is absent from parallel lifecycle skill invocations, though applying it there is architecturally constrained by the sequential batch-verify-merge dependency chain.**

---

## Codebase Analysis

### Two Invocation Paths for the Agent SDK

The project uses the SDK in two structurally different ways:

**Path A: Interactive/Skill — `Agent` tool in SKILL.md instruction files**

Embedded directly in skill markdown files as prose instructions to Claude. These calls happen at human-interaction time (daytime workflow).

| File | Usage | Notes |
|------|-------|-------|
| `skills/lifecycle/SKILL.md` (lines 347–353) | `Agent(isolation: "worktree", prompt: "/lifecycle {feature}")` | Parallel multi-feature execution; each feature gets isolated worktree branch `worktree/{name}` |
| `skills/lifecycle/references/implement.md` (line 44) | `Agent(isolation: "worktree")` | Per-task batch isolation during implementation phase |
| `skills/lifecycle/references/clarify-critic.md` (lines 15–22) | `Agent(subagent_type: "general-purpose")` | Fresh adversarial critic agent; no worktree needed (read-only) |
| `skills/research/SKILL.md` | 3 parallel `Agent` calls (no subagent_type) | Independent research angles in parallel; no isolation (read-only) |
| `skills/critical-review/SKILL.md` | `Agent` call (no subagent_type) | Fresh unanchored review agent |
| `claude/reference/parallel-agents.md` | Reference examples | Patterns for when to use worktree vs. non-isolated dispatch |

Note: `subagent_type` is used in one skill file only — `clarify-critic.md` with `"general-purpose"`. Other skills omit it (defaulting to general-purpose behavior).

**Path B: Autonomous/Pipeline — Python `claude_agent_sdk.query()` in overnight runner**

Used programmatically within the Python orchestration layer during overnight execution.

| File | Usage | Notes |
|------|-------|-------|
| `claude/pipeline/dispatch.py` | `async for message in query(prompt=task, options=options)` | Core dispatch; full control over model, budget, options, error handling |
| `claude/pipeline/conflict.py` | `dispatch_task()` → `query()` | Repair agent dispatch for merge conflicts; escalates Sonnet → Opus on quality failure |
| `claude/overnight/batch_runner.py` | Imports `dispatch_task` from dispatch.py | Per-feature/per-batch execution driver |
| `claude/overnight/runner.sh` | Spawns Python orchestrator which calls `query()` | Bash entry point; resolves API key, manages tmux session |

### Python SDK Wrapper (`claude/pipeline/dispatch.py`)

The project wraps `claude_agent_sdk.query()` with significant proprietary logic:

**Imports used:**
```python
from claude_agent_sdk import (
    query, ClaudeAgentOptions, AssistantMessage, ResultMessage,
    TextBlock, ToolUseBlock, ToolResultBlock, UserMessage,
    CLIConnectionError, ProcessError
)
```

**ClaudeAgentOptions configured per-dispatch:**
- `model`: Resolved from 2D complexity × criticality matrix (Haiku/Sonnet/Opus)
- `max_turns`: 15 / 20 / 30 by tier (complexity axis)
- `max_budget_usd`: $5 / $25 / $50 by tier (complexity axis)
- `permission_mode: "bypassPermissions"` — all dispatched overnight agents run without prompts
- `allowed_tools`: `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`
- `cwd`, `env`, `settings`, `effort`: populated per task context

**Model selection matrix (complexity × criticality):**

|  | low | medium | high | critical |
|---|-----|--------|------|----------|
| **trivial** | Haiku | Haiku | Sonnet | Sonnet |
| **simple** | Sonnet | Sonnet | Sonnet | Sonnet |
| **complex** | Sonnet | Sonnet | Opus | Opus |

Note: max_turns and max_budget_usd scale with the complexity axis only; criticality affects model selection but not turn/budget limits.

**Error classification from exceptions:**

| Error Type | Trigger | Recovery |
|------------|---------|----------|
| agent_timeout | asyncio.TimeoutError | retry |
| agent_test_failure | "test failed", "pytest" patterns | escalate model |
| agent_refusal | "i cannot", "i will not" | pause_human |
| agent_confused | "i'm not sure", "i don't understand" | escalate model |
| infrastructure_failure | CLIConnectionError | pause_human |
| budget_exhausted | ResultMessage.is_error=True | pause_session |
| api_rate_limit | "rate_limit_error" | pause_session |
| task_failure / unknown | ProcessError, other | retry |

### Interrupt Recovery (`claude/overnight/interrupt.py`)

The project has a dedicated interrupt recovery module that runs at overnight session startup. It finds features stuck in `running` status (from a prior interrupted session), classifies their worktree state (no_worktree / empty_worktree / worktree_with_N_commits), logs `interrupted` events, and resets them to `pending` for retry. `runner.sh` calls this at startup.

This is distinct from SDK `resume: session_id` — the existing mechanism restores the state machine and retries from scratch. SDK session resumption would restore an agent's in-memory conversation context (potentially useful for very long agents that accumulated substantial reasoning context before being cut off, but not required for correctness).

### Worktree Isolation: Implementation Details

- **Creation**: `WorktreeCreate` hook (`claude/hooks/worktree-create.sh`) receives JSON from SDK; creates `$CWD/.claude/worktrees/$NAME` with branch `worktree/$NAME` from HEAD; symlinks `.venv`; outputs absolute path to stdout
- **Removal**: `WorktreeRemove` hook handles cleanup; sends notification
- **Sandbox constraint**: `.claude/worktrees/` is Seatbelt-restricted, making `Agent(isolation: "worktree")` mandatory (manual `git worktree add` is blocked)
- **Git reference pattern**: Use `git log HEAD..worktree/{name}` from main CWD — no `cd` into worktree (hardcoded Claude Code security check rejects compound `cd && git` commands)
- **Naming**: `worktree/{name}` where `name` = the `name` parameter passed to `Agent`

### Settings: SDK-Related Configuration

From `claude/settings.json`:

```json
"env": {
  "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",  // Team mode enabled
  "teammateMode": "inprocess"                    // ACTIVE: all sessions share terminal when teams are used
}
```

**Important**: `teammateMode=inprocess` is a live global configuration affecting all sessions — not a dormant flag. Its interaction with the existing `isolation: "worktree"` parallel dispatch (which does not use Teams) is unexamined. The teams feature is enabled globally but no skills invoke TeamCreate, so in practice there are no teammates to conflict — but the setting could affect behavior if any tool accidentally triggers team mode.

`apiKeyHelper` script resolves `ANTHROPIC_API_KEY` for subagent spawning. Sandbox write allowlist includes `lifecycle/sessions/` for overnight state files.

### Complete Hook Inventory

**Lifecycle hooks relevant to SDK:**

| Event | Hook | Purpose |
|-------|------|---------|
| WorktreeCreate | `claude/hooks/worktree-create.sh` | Creates isolated git worktree for Agent isolation |
| WorktreeRemove | `claude/hooks/worktree-remove.sh` | Cleans up worktree + sends completion notification |
| SessionStart | `scan-lifecycle.sh` | Injects active lifecycle/overnight state into context |
| SessionEnd | `cleanup-session.sh` | Removes `.session` lock files from lifecycle dirs |
| PreToolUse(Bash) | `validate-commit.sh` | Enforces commit message style |
| PostToolUse(Bash) | `tool-failure-tracker.sh` | Tracks Bash failures; warns at 3 consecutive |
| PostToolUse(Write\|Edit) | `skill-edit-advisor.sh` | Advises on skill editing best practices |
| Stop / Notification | `notify.sh`, `notify-remote.sh` | macOS and Android push notifications |
| Notification(permission_prompt) | `permission-audit-log.sh` | Logs permission prompts to session-scoped file |

### What Is NOT Used

| SDK Primitive | Status | Equivalent Used Instead |
|---------------|--------|------------------------|
| `SendMessage` | Not used | No inter-agent signaling needed; agents are independent |
| `TaskCreate/TaskUpdate/TaskList/TaskGet/TaskStop/TaskOutput` | Not used | `overnight-state.json` + `events.log` (NDJSON) + Python state machine + `status.py` |
| `CronCreate/CronDelete/CronList` | Not used | `bin/overnight-start` + shell + tmux |
| `TeamCreate/TeamDelete` | Not used | Teams env var set and `teammateMode` active; TeamCreate never invoked |
| `EnterPlanMode/ExitPlanMode` | Not used | Lifecycle `plan.md` phase with no read-only enforcement |
| `EnterWorktree/ExitWorktree` | Not used | `isolation: "worktree"` on Agent (implicit) |
| `RemoteTrigger` | Not used | Tailscale + mosh + tmux for remote monitoring |
| `run_in_background` (on Agent) | Not used | Python asyncio in overnight path; sequential in skill path (by design — see feasibility) |
| `resume` (Agent parameter) | Not used | interrupt.py handles state-machine recovery; SDK resume would add in-memory context restoration |
| Per-agent `mode` override | Not used | Overnight: globally `bypassPermissions`; skills: inherit |
| `model` override on Agent tool | Not used | Overnight: dispatch.py matrix; skills: inherit |

---

## Web & Documentation Research

### Claude Code Agent SDK Capabilities (Current)

**`Agent` tool — confirmed parameters:**
- `description` (required): Short summary shown to user
- `prompt` (required): Full task instructions
- `subagent_type`: Agent type — built-in types: `"Explore"`, `"general-purpose"`, and custom types. Omitting defaults to general-purpose
- `model`: `"sonnet" | "opus" | "haiku"` — overrides model for this agent
- `run_in_background`: boolean — fire-and-forget; use `TaskOutput` to retrieve results
- `name`: string — makes agent addressable via `SendMessage({to: name})`
- `team_name`: string — assigns agent to an agent team
- `mode`: `"acceptEdits" | "bypassPermissions" | "default" | "dontAsk" | "plan" | "auto"`
- `isolation`: `"worktree"` — creates an isolated git worktree for the agent's work

**`SendMessage` — agent-to-agent communication:**
- Routes to agent by name (`to: "agent-name"`) or broadcasts to all
- Enables real-time coordination within a session
- Peers must have been launched with `name` parameter set
- Requires experimental agent teams feature or same-session subagent context

**SDK Task Tools (`TaskCreate`, `TaskUpdate`, etc.):**
- Cross-session task coordination shared across agents
- `TaskCreate`: creates work items with optional `addBlockedBy` dependencies
- `TaskUpdate`: transitions status `pending → in_progress → completed`
- Auto-unblocks dependent tasks on completion
- State shared via `CLAUDE_CODE_TEAM_TASKS_DIR` environment variable
- **Note**: Task state lives in memory/SDK layer — persistence characteristics unclear; file-based state is more durable for multi-hour overnight sessions

**`CronCreate` / scheduled triggers:**
- Creates recurring scheduled agents (via `/loop` or directly)
- Stored and executed by Claude Code daemon
- Simpler than shell cron for Claude-specific schedules
- `/schedule` skill already wraps this capability

**Session resumption:**
- `resume: session_id` on Agent tool restores full in-memory context of prior session
- Session IDs accessible from Agent results (not always surfaced by default)
- Useful when an agent accumulated significant reasoning context before interruption — not a correctness mechanism (interrupt.py already provides that)

**`run_in_background: true`:**
- Agent fires immediately without blocking; use `TaskOutput` to poll or be notified on completion
- Unlocks parallelism, but result collection and error handling must shift to TaskOutput

**`EnterPlanMode` / `ExitPlanMode`:**
- `mode: "plan"` restricts agent to read-only; no Edit/Write/Bash
- Enforces analysis-before-action at the SDK level
- `ExitPlanMode` returns the plan text and can require lead approval before execution proceeds

**Agent Teams (`TeamCreate`/`TeamDelete`, `SendMessage`):**
- Experimental (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` required)
- Lead creates/manages teammates; each has independent context window
- Mailbox-based messaging (peer-to-peer + broadcast)
- Shared task list for distributed work coordination
- `teammateMode: "inprocess"` (shared terminal) or `"tmux"` (separate panes)

---

## Domain & Prior Art

**How other projects use the Claude Code SDK:**

1. **Task-tool-centric orchestration**: Many Agent SDK examples show TaskCreate used as the primary coordination primitive, with agents claiming and completing tasks from a shared queue. This trades file-based state durability for cross-session visibility. The cortex-command approach (file state + `status.py`) provides durability and some queryability, but real-time cross-session visibility requires reading raw files.

2. **Agent Teams as orchestrator pattern**: The "lead + teammates" pattern mirrors the cortex-command overnight runner's "orchestrator + worker agents" pattern, but moves the coordination into the SDK layer rather than a Python wrapper. The Python wrapper offers finer control over model selection, budgeting, and error handling — which the SDK Teams API doesn't expose directly.

3. **SendMessage for dependency-driven work**: Projects with interdependent agents use SendMessage to signal completion and unblock downstream work. Cortex-command's worktree agents are intentionally independent (single features per worktree), so SendMessage adds value only if interdependent features are introduced.

4. **Plan mode as safety gate**: Common pattern in autonomous coding tools is `mode: "plan"` for the analysis phase to prevent premature writes. The cortex-command lifecycle already structurally separates phases, but there's no enforcement that a plan-phase agent can't accidentally write files.

**Distinction from the cortex-command architecture:**
The SDK-native approach optimizes for simplicity and built-in coordination. The cortex-command approach optimizes for control and durability. The main opportunity is selective SDK adoption where it adds value without replacing the custom control layer.

---

## Feasibility Assessment

| Opportunity | Effort | Risks | Prerequisites |
|-------------|--------|-------|---------------|
| **Per-agent `mode` override** (e.g., `plan` mode for plan-phase agents) | S | Lifecycle already segregates phases structurally; adds enforcement only | Identify which phases warrant read-only enforcement |
| **CronCreate for overnight scheduling** (replace `overnight-start` shell script) | S | `overnight-start` wraps tmux setup; CronCreate may not replicate all tmux lifecycle management | Understand CronCreate's process/session model first (see open questions) |
| **`run_in_background` in lifecycle skill** (launch parallel feature agents without blocking) | M | Lifecycle batch dispatch is **synchronously coupled** to the verify-and-merge loop: orchestrator must check `git log HEAD..worktree/{name}` and merge worktrees between batches. Breaking to fire-and-forget requires redesigning the batch protocol, not just adding a flag. | Redesign batch orchestration protocol in implement.md |
| **SDK session resumption for in-memory context restoration** (complement to existing interrupt.py state recovery) | M | interrupt.py already handles correctness; session IDs must be captured and persisted in dispatch.py; value proportional to how often agents have substantial accumulated reasoning context | Confirm session_id is reliably surfaced from query() ResultMessage |
| **Task tools alongside file state** (cross-session task visibility in overnight runner) | M | State divergence between SDK tasks and NDJSON event log; SDK task persistence unclear across multi-hour sessions; existing `status.py` already provides some queryability | Understand SDK task durability guarantees; may need to treat file state as strict source of truth |
| **SendMessage for inter-agent coordination** (signal completion of interdependent features) | M | Requires named agents and same session scope | Only valuable if overnight sessions begin running interdependent features in parallel |
| **SDK Agent Teams to replace Python orchestration** | XL | Python wrapper provides model selection matrix, budget controls, error classification — Teams doesn't expose these | Stable Teams API; extensive testing; V2 direction |

---

## Decision Records

### DR-1: File-based state vs. SDK Task tools

- **Context**: The overnight runner uses a state machine (`overnight-state.json`, NDJSON event logs, Python dataclasses, `status.py`) rather than the SDK's Task tools.
- **Options considered**: (A) Use SDK Task tools as primary state, (B) File-based state (current), (C) Hybrid with file state as source of truth + SDK tasks for cross-session visibility
- **Recommendation**: **Hybrid (C)** — Use TaskCreate/TaskUpdate in parallel with the existing file state, treating file state as source of truth. This adds real-time cross-session visibility while preserving durability. However, this is lower priority than framed in the initial research: `status.py` already provides some cross-session queryability.
- **Trade-offs**: Added complexity of keeping two state representations in sync; unclear if SDK task state persists across session boundaries for multi-hour jobs.

### DR-2: Python orchestration vs. Agent Teams

- **Context**: The overnight runner is a bespoke Python system that largely reinvents what Agent Teams provides.
- **Options considered**: (A) Keep Python layer (current), (B) Replace with Agent Teams
- **Recommendation**: **Keep Python layer for now (A)** — The Python wrapper provides controls (model selection matrix, tiered budgets, custom error classification) that Agent Teams doesn't expose. The SDK Teams API is still experimental. Revisit when Teams reaches stable.
- **Trade-offs**: Python layer is significant maintenance surface; Agent Teams would reduce it, but at the cost of control granularity.

### DR-3: Session resumption vs. existing interrupt recovery

- **Context**: `interrupt.py` already handles the correctness problem of interrupted overnight sessions: it resets stuck-running features to pending at startup. SDK `resume: session_id` is a different capability — restoring an agent's in-memory conversation context.
- **Options considered**: (A) Rely on interrupt.py (current), (B) Add SDK session ID capture and attempted resume before falling back to interrupt.py
- **Recommendation**: **Low-priority enhancement (B, deferred)** — The correctness gap is already closed by interrupt.py. SDK resume adds token efficiency for agents that had significant in-context reasoning before interruption. Worth capturing session IDs opportunistically, but not a high-priority change.
- **Trade-offs**: Session state may not survive long interruptions anyway; requires testing with actual overnight crash scenarios.

### DR-4: `teammateMode=inprocess` active configuration

- **Context**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and `teammateMode=inprocess` are both set globally in settings.json. The teams feature is enabled but no TeamCreate calls are ever made. No conflicts observed in practice, but the interaction with the existing worktree isolation pattern is unexamined.
- **Recommendation**: Leave as-is but document as a potential confound. If agent teams are ever used deliberately, `inprocess` mode means teammates share the same terminal — which may or may not be desired.

---

## Open Questions

- **SDK task tool durability**: Do TaskCreate/TaskUpdate task records persist across session boundaries in multi-hour overnight runs? The answer determines whether hybrid state is viable or creates a false visibility surface.
- **Session ID surfacing from query()**: Is `session_id` reliably accessible from `claude_agent_sdk.query()` ResultMessage? The dispatch.py code doesn't currently capture it.
- **CronCreate process model**: Does CronCreate launch in a tmux session or as a plain background process? The current `overnight-start` uses tmux for persistence and visibility — CronCreate's process model needs to match or we accept reduced visibility.
- **Inter-feature dependencies**: The overnight runner currently assumes independent features. If the project begins supporting interdependent features in one session, SendMessage and task dependencies become critical. Is this use case in scope?
