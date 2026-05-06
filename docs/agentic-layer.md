[← Back to README](../README.md)

For full skill descriptions and trigger details, see [skills-reference.md](skills-reference.md).

# Agentic Layer

**For:** Existing users, contributors, or anyone building on or tuning this skill system.  **Assumes:** Basic familiarity with the repo and Claude Code.

The agentic layer is the workflow orchestration system built on top of Claude Code skills. It coordinates how development work flows from a vague idea through research, specification, planning, implementation, and review — across single features, parallel batches, or fully autonomous overnight sessions. Skills are the primitive units; hooks wire them into the development environment at the right moments; and state files let the system resume across sessions and tool invocations.

This document is a reference for the full skill inventory, the main workflow diagrams, and the lifecycle phase map. It covers the core skills organized by functional group, both ASCII diagrams showing how they connect, and the tier/criticality model that governs model selection and review requirements. Start with the diagrams for an orientation, then consult the skill table for individual trigger and output details. Optional skills (UI design enforcement, `pr-review`) ship as separate plugins in the `cortex-command` marketplace; see [docs/setup.md](setup.md) for install instructions.

---

## Skills

Skill count current as of this writing. `skills/` is the authoritative source — run `ls skills/` for the live list.

For the full skill inventory and per-skill trigger details, see [skills-reference.md](skills-reference.md).

---

## Workflow Diagrams

### Diagram A — Main Workflow Flow

```mermaid
graph TD
    START([New idea / request])
    DEV["/cortex-core:dev · routing hub"]

    LC["/lifecycle\nfull interactive · single feature\nClarify → Research → Specify → Plan → Implement → Review → Complete"]
    DISC["/discovery\nresearch + decompose\ncreates backlog tickets"]
    BACKLOG[("Backlog<br/>draft → refined → complete")]
    REQ([requirements/project.md])

    REFINE["/refine\nClarify → Research → Specify\nsets status: refined"]
    GATE{"Readiness\ngate\nresearch ✓  spec ✓"}

    OVN["/overnight\nselect · plan · execute\nparallel workers per feature"]
    INTBR["overnight/&#123;session&#125; branch"]

    MR["/morning-review\nanswer deferrals\nadvance lifecycles\nmerge PR → main"]

    MAIN([main branch])

    START --> DEV
    DEV -->|"interactive · single feature"| LC
    DEV -->|"vague / research"| DISC
    DEV -->|"batch / what's next"| BACKLOG

    DISC -->|"creates tickets"| BACKLOG

    REQ -->|"informs scope"| DISC

    BACKLOG -->|"autonomous · pick item"| REFINE
    REFINE -->|"status: refined + artifacts"| GATE
    GATE -->|"eligible"| OVN
    GATE -->|"needs more prep"| REFINE

    OVN --> INTBR
    INTBR --> MR
    MR -->|"PR merged"| MAIN
    MR -->|"closes tickets"| BACKLOG

    LC -->|"Complete · closes ticket"| MAIN
```

### Diagram B — Lifecycle Phase Sequence

```
[Discovery artifacts] -----------------------------+
                                                   |  (skips Clarify + Research + Specify)
                                                   v
+---------+    +----------+    +---------+    +--------+    +-----------+    +--------+    +----------+
| Clarify +--> | Research +--> | Specify +--> |  Plan  +--> | Implement +--> | Review +--> | Complete |
+---------+    +----------+    +---------+    +--------+    +-----------+    +--------+    +----------+
[________________ /cortex-core:refine _______________]
                                                                  |              |
                                                                  |  [rework]    |
                                                                  ^--------------+

Review phase conditions:
  - Skipped for simple tier (1-5 files, existing pattern, clear requirements)
  - Required for complex tier (6+ files, novel pattern, ambiguous scope)
  - Always forced for high and critical criticality
```

---

## Lifecycle Phase Map

| Phase | Artifact produced | Next phase | Conditions |
|-------|-------------------|------------|------------|
| Clarify | none (sets complexity + criticality) | Research | Always; skipped when fully bootstrapped from discovery |
| Research | `research.md` | Specify | Always; may be bootstrapped from discovery |
| Specify | `spec.md` | Plan | Always; may be bootstrapped from discovery |
| Plan | `plan.md` | Implement | Always; orchestrator-review required before approval |
| Implement | Source code + commits | Review or Complete | Always |
| Review | `review.md` | Complete | Complex tier only; forced for high/critical criticality |
| Complete | events.log closure | — | Always |

### Tiers

Features are classified into one of two tiers before planning begins:

- **Simple**: 1–5 files, existing pattern, clear requirements. Skips the Review phase.
- **Complex**: 6+ files, novel pattern, or ambiguous scope. Includes the Review phase.

### Criticality and Model Selection

Criticality is set per-feature and drives which models run at each phase and whether review is forced:

| Criticality | Research/Plan | Explore model | Build model | Review |
|-------------|--------------|---------------|-------------|--------|
| low | Single | Haiku | Sonnet | Tier-based |
| medium | Single | Haiku | Sonnet | Tier-based |
| high | Single | Sonnet | Opus | Forced |
| critical | Parallel, competing plans | Sonnet | Opus | Forced (Opus reviewer) |

---

## Workflow Narratives

> **See also:** [Interactive Phases Guide](interactive-phases.md) — covers what questions to expect, what each phase produces, and how artifacts flow between `/cortex-core:lifecycle`, `/cortex-core:refine`, and `/cortex-core:discovery`.

### 1. Structured Single-Feature

The most common path. The user asks `/cortex-core:dev` what to work on, or names a specific feature. `/cortex-core:dev` classifies the request as a single non-trivial feature and routes to `/cortex-core:lifecycle feature-name`. The lifecycle skill starts with a Clarify phase — focused questions about scope, complexity, and criticality — then runs research (codebase exploration plus a read of `requirements/project.md`), then moves to specify, where an interview surfaces acceptance criteria. Planning produces a task breakdown that the orchestrator reviews before approval. Implementation proceeds as a series of commits, one per task *(PreToolUse hook: `hooks/cortex-validate-commit.sh` fires here and blocks any `git commit` whose message fails the style rules)*. If the feature is complex tier (6+ files, novel pattern) or high/critical criticality, the review phase runs a multi-agent verdict — four Sonnet reviewers in parallel, then an Opus cross-validator. On completion, `events.log` is updated, the backlog item is closed, and a PR is created.

### 2. Multiple Features via /overnight

When multiple backlog items are ready, the user runs `/cortex-core:refine` per feature to produce `research.md` and `spec.md` for each, then `/overnight` to plan and execute them in a batch. The overnight runner creates git worktrees (one per feature) *(WorktreeCreate hook fires here, setting up branch isolation for each worker)*, dispatches feature workers using the `cortex_command/pipeline/` execution module, and merges results into an integration branch. `/morning-review` closes the loop — reading the overnight report, closing completed lifecycles, and surfacing any features that need follow-up.

### 3. Autonomous Overnight

In the evening, the user runs `/overnight` to plan a batch of features for unattended execution *(SessionStart hook: `hooks/cortex-scan-lifecycle.sh` fires here, injecting `LIFECYCLE_SESSION_ID` and active feature state into context so the session begins oriented to current work)*. **Prerequisite**: selected features must already have discovery artifacts (`research:` and `spec:` fields in their backlog YAML frontmatter) — `/overnight` does not run interactive research or spec phases. The plan lists the eligible features and estimated duration; after user approval, the runner detaches in a tmux session and begins working. Through the night, the runner selects features from the approved batch, creates branches, and runs lead agents with a tier-based conflict-aware scheduling system to avoid resource contention. Each feature picks up at the plan phase (or implement, if already planned). In the morning, `/morning-review` walks the overnight report: it reads `lifecycle/morning-report.md`, closes completed lifecycles, merges approved PRs, and surfaces any features that need follow-up. For the full architecture and operational guide, see [Overnight: In Depth](overnight.md).

### 4. Discovery to Backlog

The user has a vague topic or area of uncertainty rather than a concrete feature. `/cortex-core:discovery topic` runs a deep research phase — exploring the codebase, reading requirements, and potentially searching external sources — then produces a structured spec and decomposes the work into discrete backlog tickets. Each ticket gets YAML frontmatter that may include `research:` and `spec:` fields pointing to the discovery artifacts. When the user later runs `/cortex-core:backlog pick` on one of those tickets and routes it through `/cortex-core:lifecycle`, the lifecycle skill detects the pre-existing artifacts and skips the research and specify phases, bootstrapping directly into planning.

---

## Hook Inventory

Hooks in `hooks/` are shared entry points. Hooks in `claude/hooks/` are specific to Claude Code's permission and session model.

| File | Event | Purpose | Agents |
|------|-------|---------|--------|
| `hooks/cortex-validate-commit.sh` | PreToolUse | Validate commit message: imperative mood, ≤72 chars subject, no trailing period, blank line before body | Claude only |
| `hooks/cortex-scan-lifecycle.sh` | SessionStart | Inject `LIFECYCLE_SESSION_ID`, active feature state, and overnight execution state into context | Claude only |
| *desktop notifier* | Stop, Notification | Desktop notifications via terminal-notifier when Claude needs input or completes (macOS) — user/machine-config responsibility; no script shipped by this repo | Claude only |
| `hooks/cortex-cleanup-session.sh` | SessionEnd | Remove `.session` lock files from `lifecycle/*/` when a Claude Code session ends (skips on `/clear`) | Claude only |
| `claude/hooks/cortex-sync-permissions.py` | PreToolUse | Merge MCP allow/deny patterns from `settings.json` so permissions stay consistent | Claude only |
| `claude/hooks/cortex-permission-audit-log.sh` | Notification (permission_prompt) | Append one line per permission prompt to a session-scoped log in `$TMPDIR` for sandbox tuning diagnostics | Claude only |
| `claude/hooks/cortex-tool-failure-tracker.sh` | PostToolUse (Bash) | Track Bash tool failures by exit code; surface a warning via `additionalContext` after 3 failures for the same tool in one session | Claude only |
| `claude/hooks/cortex-output-filter.sh` | PreToolUse (Bash) | Filter test runner output to failures/summary before context entry; patterns configured in `.claude/output-filters.conf` per project | Claude only |
| `claude/hooks/cortex-skill-edit-advisor.sh` | PostToolUse (Write\|Edit) | Advise on skill editing best practices when a Write or Edit touches a file inside `skills/` | Claude only |
| `claude/hooks/cortex-worktree-create.sh` | WorktreeCreate | Create a git worktree with branch isolation for parallel overnight or feature work | Claude only |
| `claude/hooks/cortex-worktree-remove.sh` | WorktreeRemove | Clean up the worktree directory and merged branch after work completes | Claude only |

### Hooks Architecture

#### Event Types

Claude Code fires hooks at six lifecycle points, each corresponding to a registered key in `claude/settings.json`:

| Event | When it fires | Typical use |
|-------|--------------|-------------|
| `SessionStart` | Once per session, before any tool use | Inject context, set up credentials, merge permissions |
| `SessionEnd` | When the session terminates | Clean up lock files, flush logs |
| `PreToolUse` | Before every tool invocation (filtered by `matcher`) | Block or allow tool calls, validate arguments |
| `PostToolUse` | After every tool invocation (filtered by `matcher`) | Track failures, advise on side-effects |
| `Notification` | On permission prompts and informational events | Log permission requests, send alerts |
| `WorktreeCreate` / `WorktreeRemove` | When Claude Code creates or destroys a git worktree | Provision / clean up branch-isolated worktree directories |

Multiple hooks can be registered for the same event; they run in the order listed under that event key in `settings.json`.

#### JSON Output Contract

Hooks communicate their decision to Claude Code by writing JSON to **stdout**. The structure is:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow" | "deny",
    "permissionDecisionReason": "Human-readable explanation (present when denying)",
    "updatedInput": { "command": "..." },
    "additionalContext": "Extra context surfaced to the agent alongside the tool result"
  }
}
```

Key rules:
- **Exit code is always 0.** Hooks in this project block tool calls through the JSON `permissionDecision` field — not through a non-zero exit code. A non-zero exit is an unexpected error, not a deliberate block.
- **`"allow"`** lets the tool call proceed. The `permissionDecisionReason` field may be omitted.
- **`"deny"`** blocks the tool call. Claude Code surfaces `permissionDecisionReason` to the agent as the explanation.
- **`"updatedInput"`** (PreToolUse only) replaces the tool's input before execution. The object must match the tool's input schema (e.g., `{"command": "..."}` for Bash). Used by `cortex-output-filter.sh` to wrap test runner commands with output-filtering pipelines so only failures and summaries enter the context window.
- **`"additionalContext"`** appends advisory text to the tool result that the agent sees after the tool completes. Used by PostToolUse hooks (e.g., `cortex-tool-failure-tracker.sh`) and also available in PreToolUse hooks to annotate allowed calls.
- Hooks that are purely advisory (notifications, PostToolUse advisors) may omit the `hookSpecificOutput` key entirely or write no output at all.

#### Stdin Contract

Hooks that need request context receive a JSON object on **stdin** before they write any output. The schema varies by event type:

- **`PreToolUse`** — `{"tool_name": "Bash", "tool_input": {"command": "..."}, ...}`. Used by `cortex-validate-commit.sh` to extract the git commit command and its message.
- **`SessionStart`** — `{"cwd": "/path/to/project", "session_id": "...", ...}`. Used by `claude/hooks/cortex-sync-permissions.py` to locate the project's `settings.local.json` and by `claude/hooks/cortex-worktree-create.sh` to determine where to create the new worktree.
- **`WorktreeCreate`** — `{"cwd": "...", "name": "...", "session_id": "...", "hook_event_name": "WorktreeCreate"}`. `cortex-worktree-create.sh` reads `cwd` and `name` to construct the worktree path and branch name.
- **`Notification`** — `{"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "...", "title": "..."}`. Used by `cortex-permission-audit-log.sh` to log the prompt. Note: `hook_event_name` is always `"Notification"` for all notification events; `notification_type` discriminates between event subtypes.

Hooks that do not need request context (e.g., desktop-notifier scripts, `cortex-cleanup-session.sh`) ignore stdin.

#### Ordering

Within a single event, hooks execute sequentially in registration order. If a `PreToolUse` hook returns `"deny"`, Claude Code stops the tool call immediately — subsequent hooks for the same event are **not** invoked. For other event types (PostToolUse, SessionStart, Notification), all hooks run regardless of individual outcomes.

#### Failure Behavior

- If a hook exits with a non-zero code, Claude Code treats it as an unexpected error. The tool call is not blocked by this alone, but Claude Code may surface the stderr output as a warning.
- If a hook writes invalid JSON or no output when a permission decision is expected, Claude Code falls back to its default behavior (typically `ask`).
- Hook timeouts are configured per-hook in `settings.json` (e.g., `"timeout": 5` seconds). A hook that exceeds its timeout is killed; its output is discarded and Claude Code proceeds as if no decision was made.

---

## Reference Documents

Four markdown files agents load on-demand based on task context. These are not general documentation — they are conditional reference material shipped via plugins and pulled in only when specific conditions apply.

| File | Purpose | When agents load it |
|------|---------|---------------------|
| `claude-skills.md` | Rules for building Claude Code skills — frontmatter, triggers, output contracts | Creating or editing SKILL.md files |
| `context-file-authoring.md` | Rules for authoring context files (project/user instruction files) | Modifying project-level instruction files |
| `parallel-agents.md` | Protocol for dispatching parallel agents safely | Deciding whether to run agents in parallel |
| `verification-mindset.md` | Verification discipline — evidence before claims, no speculation | Before claiming success, tests pass, or bug fixed |

For overnight runner operations and architecture (state schemas, recovery, allowed-tool allow-list, dispatch matrix), see [overnight-operations.md](overnight-operations.md).

---

## Integration Points

1. **events.log** — Append-only per-feature lifecycle journal stored at `lifecycle/{feature}/events.log`. Phase transitions write structured entries; `/cortex-core:lifecycle resume` reads the log to determine which phase to restart from. `/morning-review` scans it to identify completions. Powers all progress reporting.

2. **cortex-scan-lifecycle hook** — Runs at SessionStart and injects `LIFECYCLE_SESSION_ID`, the active feature's current phase, and overnight execution state into the session context. This is what makes the system appear continuous across `/clear` invocations and new terminal sessions.

3. **cortex-validate-commit hook** — Pre-execution gate on all `git commit` commands. Enforces imperative mood, ≤72-character subject line, no trailing period, and a blank line before the body.

4. **Backlog index** (`backlog/index.md`) — Generated by `/cortex-core:backlog reindex`. `/cortex-core:dev` reads it during triage to identify ready work. Items are auto-closed by `/cortex-core:lifecycle complete` and `/morning-review`, keeping the index current without manual intervention.

5. **pipeline-state.json** — Persistent execution state written by the overnight runner's `cortex_command/pipeline/state.py`. Records which features are complete, in-progress, or blocked. Enables the overnight runner to resume interrupted execution — features already merged are skipped when the runner restarts.

6. **Discovery bootstrap** — When `/cortex-core:lifecycle` starts a feature, it checks the backlog item's YAML frontmatter for `research:` and `spec:` fields. If those fields point to existing artifacts from a prior `/cortex-core:discovery` run, it copies them into `lifecycle/{feature}/` and skips the research and specify phases entirely, saving hours of redundant exploration.

7. **requirements context** — `requirements/project.md` and per-area requirement files inform both lifecycle research and discovery sessions. The `/cortex-core:requirements` skill maintains them. They act as a stable design compass that keeps individual feature work aligned with broader project goals.

8. **overnight-state.json + morning-report.md** — The overnight runner writes execution state to `overnight-state.json` and archives a full session report. `lifecycle/morning-report.md` is a regular file that the writer overwrites each session; `lifecycle/sessions/latest-overnight` is the symlink that points at the current session directory. See [overnight-operations.md](overnight-operations.md#core-state-files) for the full file inventory. `/morning-review` reads the report to determine what succeeded, what needs review, and what should carry over to the next session.

---

## UI Design Enforcement

The UI skills ship as the `cortex-ui-extras` plugin in the `cortex-command` marketplace. Install via `/plugin install cortex-ui-extras@cortex-command`; see [docs/setup.md](setup.md) for the full install walkthrough.

---

## Keeping This Document Current

The skill table and hook table were accurate at the time this document was written. `skills/` and `hooks/` + `claude/hooks/` are the authoritative sources — run `ls skills/` or `ls hooks/ claude/hooks/` for the live lists.

When adding a skill: add a row to the appropriate table section and update Diagram A if the skill introduces a new routing path in the main workflow. When adding a hook: add a row to the Hook Inventory table with its trigger event, purpose, and agent scope.
