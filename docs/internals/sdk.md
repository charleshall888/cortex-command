[← Back to Agentic Layer](../agentic-layer.md)

# Claude Code SDK Integration

**For:** Contributors and operators who want to understand how this project is wired to the Claude Code SDK.

The project uses the SDK in two structurally different ways: direct `Agent` tool calls embedded in skill instruction files (interactive), and the Python `claude_agent_sdk.query()` API called from the overnight execution pipeline (autonomous). These paths have different control points, different permission models, and different reasons for existing.

> For a full analysis of current SDK usage patterns and evaluated trade-offs, see [`cortex/research/archive/claude-code-sdk-usage/research.md`](../../cortex/research/archive/claude-code-sdk-usage/research.md) (archived).

> For overnight runner operations and architecture, see [overnight-operations.md](../overnight-operations.md).

---

## Path A: Interactive — Agent Tool in Skills

Skills use the `Agent` tool directly inside their SKILL.md instruction files. The agent orchestrator (Claude itself, reading the skill) makes the tool call.

| File | Usage |
|------|-------|
| `skills/lifecycle/SKILL.md` | `Agent(isolation: "worktree")` — parallel multi-feature execution; each feature gets an isolated branch `worktree/{name}` |
| `skills/lifecycle/references/implement.md` | `Agent(isolation: "worktree")` — per-task batch isolation during implementation |
| `skills/refine/references/clarify-critic.md` | `Agent(subagent_type: "general-purpose")` — fresh adversarial critic; read-only, no worktree |
| `skills/research/SKILL.md` | Three parallel `Agent` calls — independent research angles; read-only, no worktree |
| `skills/critical-review/SKILL.md` | `Agent` call — fresh unanchored reviewer |

**Key constraint: no `subagent_type` on write agents.** Worktree-isolated agents omit `subagent_type` (defaults to general-purpose). Only read-only agents explicitly pass `subagent_type: "general-purpose"`.

**Key constraint: worktree isolation is preferred for parallel dispatch.** Same-repo worktrees live at `<repo>/.claude/worktrees/{name}/` — the Anthropic-aligned repo-relative default that lives under the project's trust scope and needs no per-shell sandbox registration. The `.mcp.json` sandbox deny is filename-scoped (blocks agent writes to `.mcp.json`) and does NOT block `git worktree add` from creating the worktree directory or checking out other files. `Agent(isolation: "worktree")` triggers the `WorktreeCreate` hook which creates the directory via the single `resolve_worktree_root()` chokepoint. See [Worktree Isolation](#worktree-isolation) below.

---

## Path B: Autonomous — Python `claude_agent_sdk.query()`

The overnight pipeline calls the SDK programmatically from Python, wrapping `query()` with model selection, budget enforcement, error classification, and activity logging. This path runs without human interaction.

**Entry point:** `cortex_command/pipeline/dispatch.py`

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
| `model` | **Unset.** cortex selects no model; the dispatch runs on the CLI default (→ ADR-0032) |
| `max_turns` | 15 / 20 / 30 (trivial / simple / complex) |
| `max_budget_usd` | $5 / $25 / $50 (trivial / simple / complex) |
| `permission_mode` | `"bypassPermissions"` — overnight agents run without permission prompts |
| `allowed_tools` | `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` |

**Model selection: none.** cortex does not choose a model for any dispatch — interactive or overnight. `ClaudeAgentOptions.model` is left unset, so each dispatch runs on the CLI's own default, and the dispatching agent picks the model where one is picked at all. The former *(complexity, criticality)* pipeline matrix, the *(role, criticality)* lifecycle matrix behind the `cortex-resolve-model` verb, and the `haiku → sonnet → opus` retry ladder were all removed together; see `adr/0032-cortex-selects-no-model` for what was traded away and why.

Max turns and budget still scale on the complexity axis.

**Model observability.** Not choosing the model does not mean not recording it. `AssistantMessage` reports the model each dispatch actually ran on; `dispatch.py` captures the first non-empty value and emits it twice — once as a one-shot `dispatch_model_observed` event (so the dashboard can badge a dispatch that is still running) and again on `dispatch_complete` (so `pair_dispatch_events` can bucket it). `dispatch_start` carries no `model` key, because nothing has replied when it is written; the pairing falls back to the start event so metrics written before ADR-0032 still aggregate.

**Effort selection matrix (`_EFFORT_MATRIX`):**

Effort is resolved centrally in `cortex_command/pipeline/dispatch.py` via `resolve_effort(complexity, criticality, skill)`. The 2D `_EFFORT_MATRIX` constant replaces the legacy 1D `EFFORT_MAP` (which keyed only on complexity). The matrix has 12 cells (3 complexity × 4 criticality):

| (complexity, criticality) | Effort |
|---|---|
| (trivial, low) | low |
| (trivial, medium) | low |
| (trivial, high) | high |
| (trivial, critical) | high |
| (simple, low) | high |
| (simple, medium) | high |
| (simple, high) | high |
| (simple, critical) | high |
| (complex, low) | high |
| (complex, medium) | high |
| (complex, high) | xhigh |
| (complex, critical) | xhigh |

`xhigh` aligns with Anthropic's Opus 4.7 guidance (*"Start with `xhigh` for coding and agentic use cases"*). Effort is a behavioral signal that caps the *maximum* reasoning depth — the model adapts thinking down for simpler tasks rather than always spending the full ceiling.

`resolve_effort` no longer takes a model. It used to, for two reasons that are both gone: the skill overrides below were gated on the resolved model being opus, and a runtime guard checked the cell against a per-model supported-effort vocabulary. cortex no longer selects a model (→ ADR-0032), so neither can be evaluated here. `resolve_effort` still owns the complexity and criticality enum guards, which `resolve_model` used to carry.

**Skill-based effort overrides (applied after matrix lookup, unconditional):**

| Skill | Effort override |
|---|---|
| `review-fix` | max |
| `integration-recovery` | max |

These fire for every dispatch of those two skills. The opus gate that formerly restricted them — and the `model_override="opus"` that `integration_recovery.py` passed specifically to satisfy it — were removed together, so the coverage caveat that used to sit here (the override firing for only ~25% of review-fix dispatches) no longer applies. All other skills (`implement`, `review`, `conflict-repair`, `merge-test-repair`, `brain`) use the matrix value.

**Effort vocabulary support per model** (informational — cortex cannot act on it, since it does not know which model will run):

| Model | Supported effort levels |
|---|---|
| haiku | low, medium, high (xhigh/max unverified — assume not supported) |
| sonnet | low, medium, high, max (xhigh NOT supported) |
| opus 4.7 | low, medium, high, xhigh, max |

Because the running model is not known at resolve time, a cell requesting an unsupported effort is caught at the CLI boundary rather than by a pre-dispatch guard. That path is described next, and it was already the backstop before model selection was removed.

**What actually rejects an unsupported `--effort` is the dispatched CLI binary, not the model (#313).** The SDK renders `effort` as a raw `--effort` flag, and the *binary* validates it: old `claude` (≤2.1.69, e.g. the version `claude-agent-sdk` bundled) **hard-rejects** an unsupported value (`error: option '--effort <level>' argument '…' is invalid`, exit ≠ 0); modern `claude` (≥2.1.186) **warn-ignores** it (`Warning: Unknown --effort value '…' — ignoring it`, exit 0, runs at the default effort). Neither "silently downgrades." Because the SDK's `_find_cli` prefers its bundled binary, cortex resolves the **best-available** CLI (`cortex_command/cli_resolver.py`, → ADR-0014) and pins it via `ClaudeAgentOptions(cli_path=…)`; an `--effort` hard-reject then clamps once to `max` (universally accepted) and a warn-ignore is surfaced as a `dispatch_effort_ignored` note — degradation is always loud, never silent.

For the post-flip rollback monitoring procedure (querying `metrics.json` per-effort cost buckets, the >2× threshold for human investigation, and the matrix-flip revert path), see [overnight-operations.md](../overnight-operations.md).

**Error classification and recovery:**

Classification is heuristic — triggers are substring matches against lowercased agent output, not structured signals. Misclassification is possible, particularly for refusals (Claude's refusal language varies across model versions) and test failures (any output mentioning "pytest" matches, including success messages).

| Error type | Trigger | Recovery |
|------------|---------|----------|
| `agent_timeout` | `asyncio.TimeoutError` | retry |
| `agent_test_failure` | "test failed", "pytest" in output | retry |
| `agent_refusal` | "i cannot", "i will not" | pause for human |
| `agent_confused` | "i'm not sure", "i don't understand" | retry |
| `infrastructure_failure` | `CLIConnectionError` | pause for human |
| `budget_exhausted` | `ResultMessage.is_error=True` | pause session |
| `api_rate_limit` | "rate_limit_error" in message | pause session |
| `task_failure` / `unknown` | `ProcessError`, other exceptions | retry |

There is no model escalation on retry — the ladder was removed with model selection (→ ADR-0032). A retry-classified failure re-dispatches with accumulated learnings; when attempts run out the loop pauses for a human.

**Where `query()` is called:**

- `cortex_command/pipeline/dispatch.py` — main implementation dispatch
- `cortex_command/pipeline/conflict.py` — repair agent dispatch for merge conflicts (up to two attempts)

---

## Model Selection Rationale

**cortex no longer selects models** (→ ADR-0032 `adr/0032-cortex-selects-no-model`). There is no lifecycle role matrix, no pipeline matrix, and no escalation ladder; the dispatching agent chooses, or the CLI default applies.

What survives is guidance at the dispatch sites, not a lookup. It is worth stating once here so an editor of any one site knows the shape:

- **Gather fan-out is breadth-first read-and-report.** Parallel research and competing-plan dispatches benefit from breadth across many agents rather than maximum depth in each; the orchestrator synthesizes, so per-agent depth is not the bottleneck. A cheaper tier usually fits.
- **Judgment dispatches are not gather.** The research **adversarial** wave (which runs last, over a summary of the others), **critical-review**'s reviewers and synthesizer, and the **clarify-critic** exist to catch what the cheap pass missed. Cheaping them out is a false economy — this is the one asymmetry worth remembering when choosing.
- **Reviewer count, not reviewer model, is what criticality buys.** Escalating criticality raises the number of reviewer angles and triggers the adversarial wave; it was never a per-reviewer model upgrade (requirements ruling 2026-07-16, retained).

Two load-bearing model-profile facts not owned elsewhere: Opus has a **128K max output token** ceiling, and Claude Code's built-in **Explore agent uses Haiku**.

The dated benchmark evidence that originally motivated these conclusions is preserved in `cortex/research/opus-4-7-harness-adaptation/`.

---

## Worktree Isolation

Both paths use worktree isolation for parallel execution. The SDK's `isolation: "worktree"` parameter triggers a `WorktreeCreate` hook that provisions the worktree and branch.

**`claude/hooks/cortex-worktree-create.sh`** (registered on `WorktreeCreate` event):
- Receives `{"cwd": "...", "name": "...", "session_id": "..."}` on stdin
- Shells out to `cortex-worktree-resolve "$NAME"` (the single resolver chokepoint) to compute the worktree path — `<repo>/.claude/worktrees/$NAME` for same-repo dispatch — then creates it as a git worktree
- Creates branch `worktree/$NAME` from HEAD
- Symlinks `.venv` into the worktree for Python tooling
- Writes absolute worktree path to stdout (required by SDK)

**`claude/hooks/cortex-worktree-remove.sh`** (registered on `WorktreeRemove` event):
- Cleans up the worktree directory
- Sends a completion notification

**Branch naming:** `worktree/{name}` where `name` is the `name` parameter passed to `Agent(name: "...")`. Always use the `name` parameter so branches are identifiable.

**Git reference pattern from main repo:** Use `git log HEAD..worktree/{name} --oneline` — do not `cd` into the worktree for git operations (Claude Code's security check rejects compound `cd && git` commands).

**Stale worktrees:** If an interactive session (Path A) is interrupted mid-run, the worktree directory and branch may be left behind. The next run of the same skill with the same feature name will fail at hook level because `cortex-worktree-create.sh` exits non-zero when the target directory already exists. Clean up manually before retrying:

```bash
git worktree remove "$(cortex-worktree-resolve {name})"   # removes the directory (resolves to <repo>/.claude/worktrees/{name})
git branch -d worktree/{name}                              # removes the branch (use -D if unmerged)
```

---

## Settings Configuration

From `~/.claude/settings.json` (user-global; the project-local `claude/settings.json` was retired):

```json
"env": {
  "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
  "teammateMode": "inprocess"
}
```

`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables the agent teams feature globally. `teammateMode: "inprocess"` is an **active** configuration — if any tool invokes TeamCreate, teammates share the same terminal. No skills currently call TeamCreate, so in practice teams are enabled but dormant.

`apiKeyHelper` resolves `ANTHROPIC_API_KEY` for subagent spawning in the Python overnight pipeline. Configure it in `~/.claude/settings.local.json` (machine-local, not committed) — the runner checks both `settings.json` and `settings.local.json`. When not configured, subagents use subscription billing.

---

## Interrupt Recovery

`cortex_command/overnight/interrupt.py` runs at the start of every `cortex overnight start` invocation. It finds features stuck in `running` status (from a prior interrupted session), classifies their worktree state for diagnostic logging, and resets them to `pending` for retry. The recovery action (reset to pending) is the same regardless of worktree classification.

Note: **recovery attempt counts are preserved across restarts.** A feature that exhausted its retry budget before the interrupt begins the next session with no remaining attempts and will be paused immediately after a single dispatch. If this is unexpected, reset `retries` manually in `overnight-state.json` before relaunching.

The SDK's `resume: session_id` parameter is a different capability — it restores an agent's in-memory conversation context, which could reduce token waste if an agent was far into a complex task when interrupted. The project does not currently use it; `interrupt.py`'s state-machine reset is the baseline recovery mechanism.

---

## Intentional Design Choices

**File-based state over SDK Task tools.** The overnight runner uses `overnight-state.json`, NDJSON event logs, and Python dataclasses rather than `TaskCreate`/`TaskUpdate`. File state survives SDK version changes, persists across any kind of process crash, and is readable with standard tools (`cat`, `python3 -c`, `jq`). SDK task state persistence across multi-hour sessions is unclear. `status.py` already provides cross-session queryability for live sessions.

**Python orchestration layer over Agent Teams.** The `cortex_command/pipeline/` and `cortex_command/overnight/` modules reinvent some of what Agent Teams provides (lead + worker pattern, parallel dispatch). The Python layer exists because it provides controls the Teams API doesn't expose: the 2D model selection matrix, per-tier budget limits, structured error classification, and repair agent escalation. Agent Teams is also still experimental. This trade-off should be revisited when Teams reaches stable and exposes equivalent control surfaces.

**`bypassPermissions` with `Bash` access.** Overnight agents run with `permission_mode: "bypassPermissions"` and `Bash` in the allowed tool list. This means an overnight agent can execute arbitrary shell commands in its worktree without prompts. The asymmetry between Bash subprocesses and SDK in-process tool calls runs the OPPOSITE direction from what one might intuit: per Anthropic [#26616](https://github.com/anthropics/claude-code/issues/26616) and the official sandboxing docs at https://code.claude.com/docs/en/sandboxing, the sandbox CONSTRAINS Bash subprocess writes via OS-kernel enforcement (Seatbelt on macOS), while Write/Edit tools run in-process in the SDK and bypass the sandbox entirely — they are constrained only by the permission system. This is a deliberate trade-off for autonomous execution — prompts in an unattended session would stall the runner. Operators should be aware that agents operating on real codebases with `bypassPermissions + Bash` have broad execution access for in-process tool calls. Mitigation: agents run in isolated worktrees, not on the main branch directly; `bypassPermissions` is scoped to the Python pipeline path only (interactive skills inherit the parent session's permission model); per-spawn sandbox enforcement applies an OS-kernel deny-set to Bash-routed writes against critical git-state paths. See [`docs/overnight-operations.md` — Per-spawn sandbox enforcement](../overnight-operations.md#per-spawn-sandbox-enforcement) for the orchestrator deny-set, dispatch allow-set, and `CORTEX_SANDBOX_SOFT_FAIL` kill-switch.

**`interrupt.py` over SDK session resumption.** The state-machine recovery on restart (resetting stuck features to pending) was purpose-built for the overnight use case and handles correctness without requiring session ID tracking. SDK resumption is a future optimization, not a correctness gap.

**`cortex overnight schedule` (launchd LaunchAgent) + detached Python fork over CronCreate.** The current scheduling mechanism uses macOS launchd LaunchAgents (see `cortex overnight schedule`) to fire `cortex overnight start` at a target time. At launch, `_spawn_runner_async` in `cortex_command/overnight/cli_handler.py` forks a detached Python process that operates without a controlling terminal. Output and state are surfaced via `cortex overnight status` and `cortex overnight logs <session-id>` rather than terminal attachment. CronCreate's process model (whether it produces a persistent, attachable session) is untested for overnight use.

---

## SDK Primitives Not Used

| Primitive | Why not used |
|-----------|-------------|
| `SendMessage` | Overnight agents run independently; no inter-agent signaling needed at current feature independence level |
| `TaskCreate` / `TaskUpdate` / task tools | File-based state is more durable; `status.py` provides queryability |
| `CronCreate` | `cortex overnight schedule` (launchd LaunchAgent) + detached Python fork handles scheduling with status/logs visibility |
| `TeamCreate` / `TeamDelete` | Teams feature enabled but Python orchestration layer provides required control granularity |
| `EnterPlanMode` / `ExitPlanMode` | Lifecycle phases are structurally separated; read-only enforcement not yet added |
| `EnterWorktree` / `ExitWorktree` | `isolation: "worktree"` on Agent is the safe path in sandbox |
| `RemoteTrigger` | Tailscale + mosh + tmux handles remote access |
| `run_in_background` | Dispatch mode (sync vs. background) is owned by the Claude Code runtime, not this repo; the builder's exit report lives in its final message in whatever shape the runtime delivers, and per-task completion is derived from the git checkpoint, never the return-delivery shape (ADR-0030) |
| `resume` (Agent parameter) | `interrupt.py` handles correctness; in-memory context restoration not yet needed |
| Per-agent `mode` override | Overnight agents use global `bypassPermissions`; skill agents inherit |
| `model` override on Agent tool | Interactive agents inherit parent model; overnight agents use dispatch.py matrix |
