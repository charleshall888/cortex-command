[← Back to Agentic Layer](agentic-layer.md)

# Claude Code SDK Integration

**For:** Contributors and operators who want to understand how this project is wired to the Claude Code SDK.

The project uses the SDK in two structurally different ways: direct `Agent` tool calls embedded in skill instruction files (daytime, interactive), and the Python `claude_agent_sdk.query()` API called from the overnight execution pipeline (autonomous). These paths have different control points, different permission models, and different reasons for existing.

> For a full analysis of current SDK usage patterns and evaluated trade-offs, see [`research/claude-code-sdk-usage/research.md`](../research/claude-code-sdk-usage/research.md).

---

## Path A: Interactive — Agent Tool in Skills

Skills that run daytime dispatch use the `Agent` tool directly inside their SKILL.md instruction files. The agent orchestrator (Claude itself, reading the skill) makes the tool call.

| File | Usage |
|------|-------|
| `skills/lifecycle/SKILL.md` | `Agent(isolation: "worktree")` — parallel multi-feature execution; each feature gets an isolated branch `worktree/{name}` |
| `skills/lifecycle/references/implement.md` | `Agent(isolation: "worktree")` — per-task batch isolation during implementation |
| `skills/lifecycle/references/clarify-critic.md` | `Agent(subagent_type: "general-purpose")` — fresh adversarial critic; read-only, no worktree |
| `skills/research/SKILL.md` | Three parallel `Agent` calls — independent research angles; read-only, no worktree |
| `skills/critical-review/SKILL.md` | `Agent` call — fresh unanchored reviewer |

**Key constraint: no `subagent_type` on write agents.** Worktree-isolated agents omit `subagent_type` (defaults to general-purpose). Only read-only agents explicitly pass `subagent_type: "general-purpose"`.

**Key constraint: worktree isolation is mandatory in sandbox.** `.claude/worktrees/` is Seatbelt-restricted. `Agent(isolation: "worktree")` triggers the `WorktreeCreate` hook which creates the directory — manual `git worktree add` is blocked. See [Worktree Isolation](#worktree-isolation) below.

---

## Path B: Autonomous — Python `claude_agent_sdk.query()`

The overnight pipeline calls the SDK programmatically from Python, wrapping `query()` with model selection, budget enforcement, error classification, and activity logging. This path runs without human interaction.

**Entry point:** `claude/pipeline/dispatch.py`

```python
from claude_agent_sdk import (
    query, ClaudeAgentOptions, AssistantMessage, ResultMessage,
    TextBlock, ToolUseBlock, ToolResultBlock, UserMessage,
    CLIConnectionError, ProcessError
)

async for message in query(prompt=task, options=options):
    # stream AssistantMessage / ResultMessage events
```

**`ClaudeAgentOptions` per dispatch:**

| Option | Value |
|--------|-------|
| `model` | Resolved from complexity × criticality matrix (see below) |
| `max_turns` | 15 / 20 / 30 (trivial / simple / complex) |
| `max_budget_usd` | $5 / $25 / $50 (trivial / simple / complex) |
| `permission_mode` | `"bypassPermissions"` — overnight agents run without permission prompts |
| `allowed_tools` | `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` |

**Model selection matrix (complexity × criticality):**

|  | low | medium | high | critical |
|---|-----|--------|------|----------|
| **trivial** | Haiku | Haiku | Sonnet | Sonnet |
| **simple** | Sonnet | Sonnet | Sonnet | Sonnet |
| **complex** | Sonnet | Sonnet | Opus | Opus |

Max turns and budget scale on the complexity axis only; criticality affects model selection.

**Error classification and recovery:**

| Error type | Trigger | Recovery |
|------------|---------|----------|
| `agent_timeout` | `asyncio.TimeoutError` | retry |
| `agent_test_failure` | "test failed", "pytest" in output | escalate model |
| `agent_refusal` | "i cannot", "i will not" | pause for human |
| `agent_confused` | "i'm not sure", "i don't understand" | escalate model |
| `infrastructure_failure` | `CLIConnectionError` | pause for human |
| `budget_exhausted` | `ResultMessage.is_error=True` | pause session |
| `api_rate_limit` | "rate_limit_error" in message | pause session |
| `task_failure` / `unknown` | `ProcessError`, other exceptions | retry |

Model escalation ladder on retry: Haiku → Sonnet → Opus (terminal).

**Where `query()` is called:**

- `claude/pipeline/dispatch.py` — main implementation dispatch
- `claude/pipeline/conflict.py` — repair agent dispatch for merge conflicts (Sonnet, escalates to Opus)

---

## Worktree Isolation

Both paths use worktree isolation for parallel execution. The SDK's `isolation: "worktree"` parameter triggers a `WorktreeCreate` hook that provisions the worktree and branch.

**`claude/hooks/worktree-create.sh`** (registered on `WorktreeCreate` event):
- Receives `{"cwd": "...", "name": "...", "session_id": "..."}` on stdin
- Creates `$CWD/.claude/worktrees/$NAME` as a git worktree
- Creates branch `worktree/$NAME` from HEAD
- Symlinks `.venv` into the worktree for Python tooling
- Writes absolute worktree path to stdout (required by SDK)

**`claude/hooks/worktree-remove.sh`** (registered on `WorktreeRemove` event):
- Cleans up the worktree directory
- Sends a completion notification

**Branch naming:** `worktree/{name}` where `name` is the `name` parameter passed to `Agent(name: "...")`. Always use the `name` parameter so branches are identifiable.

**Git reference pattern from main repo:** Use `git log HEAD..worktree/{name} --oneline` — do not `cd` into the worktree for git operations (Claude Code's security check rejects compound `cd && git` commands).

---

## Settings Configuration

From `claude/settings.json`:

```json
"env": {
  "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
  "teammateMode": "inprocess"
}
```

`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables the agent teams feature globally. `teammateMode: "inprocess"` is an **active** configuration — if any tool invokes TeamCreate, teammates share the same terminal. No skills currently call TeamCreate, so in practice teams are enabled but dormant.

`apiKeyHelper` resolves `ANTHROPIC_API_KEY` for subagent spawning in the Python overnight pipeline. See `claude/get-api-key.sh`.

---

## Interrupt Recovery

`claude/overnight/interrupt.py` runs at the start of every `overnight-start`. It finds features stuck in `running` status (from a prior interrupted session), classifies their worktree state, and resets them to `pending` for retry.

This handles the correctness concern for interrupted overnight agents. The SDK's `resume: session_id` parameter is a different capability — it restores an agent's in-memory conversation context, which could reduce token waste if an agent was far into a complex task when interrupted. The project does not currently use it; `interrupt.py`'s state-machine reset is sufficient for correctness.

---

## Intentional Design Choices

**File-based state over SDK Task tools.** The overnight runner uses `overnight-state.json`, NDJSON event logs, and Python dataclasses rather than `TaskCreate`/`TaskUpdate`. File state survives SDK version changes, persists across any kind of process crash, and is readable with standard tools (`cat`, `python3 -c`, `jq`). SDK task state persistence across multi-hour sessions is unclear. `status.py` already provides cross-session queryability for live sessions.

**Python orchestration layer over Agent Teams.** The `claude/pipeline/` and `claude/overnight/` modules reinvent some of what Agent Teams provides (lead + worker pattern, parallel dispatch). The Python layer exists because it provides controls the Teams API doesn't expose: the 2D model selection matrix, per-tier budget limits, structured error classification, and repair agent escalation. Agent Teams is also still experimental. This trade-off should be revisited when Teams reaches stable and exposes equivalent control surfaces.

**`interrupt.py` over SDK session resumption.** The state-machine recovery on restart (resetting stuck features to pending) was purpose-built for the overnight use case and handles correctness without requiring session ID tracking. SDK resumption is a future optimization, not a correctness gap.

**`overnight-start` + tmux over CronCreate.** The current scheduling mechanism launches the runner in a named tmux session, providing terminal attachment, output visibility, and graceful signal handling. CronCreate's process model (whether it produces a persistent, attachable session) is untested for overnight use.

---

## SDK Primitives Not Used

| Primitive | Why not used |
|-----------|-------------|
| `SendMessage` | Overnight agents run independently; no inter-agent signaling needed at current feature independence level |
| `TaskCreate` / `TaskUpdate` / task tools | File-based state is more durable; `status.py` provides queryability |
| `CronCreate` | `overnight-start` + tmux handles scheduling with better visibility |
| `TeamCreate` / `TeamDelete` | Teams feature enabled but Python orchestration layer provides required control granularity |
| `EnterPlanMode` / `ExitPlanMode` | Lifecycle phases are structurally separated; read-only enforcement not yet added |
| `EnterWorktree` / `ExitWorktree` | `isolation: "worktree"` on Agent is the safe path in sandbox |
| `RemoteTrigger` | Tailscale + mosh + tmux handles remote access |
| `run_in_background` | Interactive skill dispatch is synchronously coupled to the batch verify-and-merge loop |
| `resume` (Agent parameter) | `interrupt.py` handles correctness; in-memory context restoration not yet needed |
| Per-agent `mode` override | Overnight agents use global `bypassPermissions`; skill agents inherit |
| `model` override on Agent tool | Interactive agents inherit parent model; overnight agents use dispatch.py matrix |
