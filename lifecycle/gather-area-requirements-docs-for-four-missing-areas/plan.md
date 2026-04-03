# Plan: gather-area-requirements-docs-for-four-missing-areas

## Overview

Run four parallel codebase recon agents (one per area), consolidate their questions into a single ≤8-question Q&A round with the user, then write all four area docs from the findings + answers. Pipeline doc is derived from `docs/pipeline.md` plus source files, not gathered from scratch.

**LIVE EXECUTION REQUIRED**: Tasks 2 and 7 use `AskUserQuestion` and block on user input. Do not run this plan unattended in an overnight session — it will stall at Task 2 and discard all Task 1 recon work.

## Tasks

### Task 1: Parallel codebase reconnaissance for all four areas
- **Files**: none (read-only)
- **What**: Dispatch 4 parallel agents to read the relevant source files for each area and produce (a) structured findings on capabilities, constraints, and dependencies, and (b) a list of questions requiring user judgment. Pipeline agent reads `docs/pipeline.md` + all six source files (`state.py`, `conflict.py`, `merge_recovery.py`, `deferral.py`, `metrics.py`, `batch_runner.py`). The three other agents read the source files identified in `research.md` for their respective areas.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Observability sources: `claude/statusline.sh`, `claude/dashboard/app.py`, `claude/dashboard/data.py`, `hooks/cortex-notify-remote.sh`
  - Remote-access sources: `skills/tmux/SKILL.md`, `hooks/cortex-notify-remote.sh`, `docs/setup.md`
  - Multi-agent sources: `claude/pipeline/worktree.py`, `claude/pipeline/dispatch.py`, `claude/reference/parallel-agents.md`
  - Pipeline sources: `docs/pipeline.md`, `claude/overnight/state.py`, `claude/pipeline/conflict.py`, `claude/pipeline/merge_recovery.py`, `claude/overnight/deferral.py`, `claude/pipeline/metrics.py`, `claude/overnight/batch_runner.py`
  - Pipeline pre-answered: dashboard no-authentication + localhost-only = permanent architectural constraints; do not ask
  - Remote-access: write at capability level; do not ask about tmux skill future
  - Agent output format: structured findings (capabilities list, constraints, dependencies) + questions list
- **Verification**: Each agent returns non-empty findings with at least a capabilities list and a (possibly empty) questions list. If fewer than 4 agents return non-empty findings, proceed with available findings — note any failed area as a gap in that doc's Open Questions section rather than aborting. Do not require all 4 to succeed before proceeding to Task 2.

### Task 2: Consolidate Q&A round
- **Files**: none (interaction only)
- **What**: Merge all four agents' question lists; deduplicate cross-area questions; present ≤8 questions total via `AskUserQuestion`; record answers for use in Tasks 3–6. If any agent produced no questions, that area has no Q&A needs.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - **REQUIRES LIVE USER**: `AskUserQuestion` blocks on user input. Do not attempt overnight.
  - Question cap: ≤8 total across all four areas
  - Deduplication: if two areas ask the same question, ask once and apply the answer to both
  - **Question priority if total exceeds 8**: cut evolution-intent questions before permanent/temporary questions; note cut questions in the relevant area doc's Open Questions section
  - **Partial Task 1 handling**: if an agent returned no findings for an area, skip that area's questions in consolidation. That area's doc will be written with minimal content and an Open Question flagging the need for re-recon.
  - Use `AskUserQuestion` tool for the consolidated round
  - Answers are the input to Tasks 3–6
- **Verification**: AskUserQuestion tool returns answers for all presented questions

### Task 3: Write requirements/observability.md
- **Files**: `requirements/observability.md` (create)
- **What**: Write the observability area doc from Task 1 findings + Task 2 answers. Three functional requirement sections: Statusline, Dashboard, Notifications. Follow `gather.md` template. Parent backlink to `requirements/project.md`. No "when to load" guidance.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Template structure: `skills/requirements/references/gather.md`
  - Sections: Overview → Functional Requirements (§ Statusline, § Dashboard, § Notifications) → Non-Functional Requirements → Architectural Constraints → Dependencies → Edge Cases → Open Questions
  - Header: `# Requirements: observability` + `> Last gathered: 2026-04-03` + `**Parent doc**: [requirements/project.md](project.md)`
  - Statusline: bash script `claude/statusline.sh`; 3 output modes; color via 16-color codes
  - Dashboard: FastAPI + Jinja2 `claude/dashboard/`; reads `lifecycle/` state files; 9 HTML templates
  - Notifications: `hooks/cortex-notify-remote.sh`; ntfy.sh HTTP API; suppresses subagent sessions
- **Verification**: File exists at `requirements/observability.md`; has all required template sections; parent backlink present; 60–120 lines

### Task 4: Write requirements/remote-access.md
- **Files**: `requirements/remote-access.md` (create)
- **What**: Write the remote-access area doc at capability level — describe what the system must provide (session persistence, remote session reattachment, mobile push alerting) without encoding any specific tool as a permanent requirement. The tmux skill's future is under review; the doc must describe capabilities, not tmux.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Template: same as Task 3
  - Capability framing: "The system must support persistent terminal sessions that survive network interruptions" NOT "tmux must be used"
  - Current implementations reference: `skills/tmux/SKILL.md` (session management), `hooks/cortex-notify-remote.sh` (push notifications via ntfy.sh + Tailscale)
  - Broken reference: `docs/setup.md` references non-existent `remote/SETUP.md` — note this in Open Questions or Edge Cases as a known documentation gap
  - Platform: macOS primary; document as such
- **Verification**: File exists at `requirements/remote-access.md`; no tmux-specific tooling encoded as a requirement; capability language used throughout; 60–120 lines

### Task 5: Write requirements/multi-agent.md
- **Files**: `requirements/multi-agent.md` (create)
- **What**: Write the multi-agent orchestration area doc. Cover agent spawning patterns, worktree isolation, parallel dispatch conditions (3+ unrelated tasks + no shared state + clear file boundaries), and model selection matrix.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Template: same as Task 3
  - Parallel dispatch go/no-go: 3+ unrelated tasks, no shared state, clear file boundaries (from `claude/reference/parallel-agents.md`)
  - Worktree isolation: `claude/pipeline/worktree.py`; branches `pipeline/{feature}`; created at `.claude/worktrees/{feature}/` or `$TMPDIR/overnight-worktrees/`
  - Model selection: `claude/pipeline/dispatch.py`; escalation Haiku → Sonnet → Opus; task complexity × phase × criticality matrix
  - Agent SDK: `claude_agent_sdk.query()` with `ClaudeAgentOptions`; error recovery map (`ERROR_RECOVERY` dict)
- **Verification**: File exists at `requirements/multi-agent.md`; model selection matrix documented; worktree isolation pattern documented; parallel dispatch conditions explicit; 60–120 lines

### Task 6: Write requirements/pipeline.md
- **Files**: `requirements/pipeline.md` (create)
- **What**: Derive the pipeline area doc from `docs/pipeline.md` + source file analysis (Task 1 findings) + Task 2 answers. Translate implementation descriptions into requirements language. Encode dashboard no-auth/localhost-only as permanent architectural constraints without asking. Apply Q&A answers to bounded question categories only.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Template: same as Task 3
  - Derivation sources: `docs/pipeline.md` (primary) + Task 1 pipeline findings
  - **"Derive" means**: translate implementation facts into requirement statements. Example: `docs/pipeline.md` says "Valid phases: planning → executing → complete" → requirement: "Phase transitions are forward-only; no phase may transition to a prior phase."
  - **Translation selection criterion**: include a construct in Q&A if its value represents a meaningful design choice with alternatives (e.g., the 2-repair-attempt cap could be 1, 2, or 3). Skip constructs that are purely technical/mechanical (file path names, JSONL field types). When uncertain, document as current implementation state in Architectural Constraints rather than asking.
  - Pre-answered constraints (do not ask): dashboard unauthenticated + localhost-only = permanent; document as Architectural Constraints
  - Q&A categories (bounded — do not expand): (a) which limitations are permanent vs. temporary; (b) evolution intent per subsystem; (c) source-vs-docs contradictions surfaced by Task 1
  - Key subsystems to cover: state management, dispatch + model selection, conflict resolution + merge recovery, deferral, metrics + cost tracking, smoke test gate
  - State file locations: `lifecycle/overnight-state.json`, `lifecycle/master-plan.md`, `lifecycle/pipeline-events.log`
- **Verification**: File exists at `requirements/pipeline.md`; dashboard constraints documented as architectural constraints; state machine documented (phases + statuses); no docs/pipeline.md implementation details copied verbatim as requirements; 80–150 lines

### Task 7: Per-area approval with follow-up handling
- **Files**: possibly updates to any of the 4 area docs
- **What**: Present all four draft docs for review. Use `AskUserQuestion` for per-area approval. If a user's answer surfaces a follow-up question, ask up to 2 targeted follow-up questions for that area before proceeding. Revise and re-present any area that needs changes. Repeat until all four areas are approved.
- **Depends on**: [3, 4, 5, 6]
- **Complexity**: complex
- **Context**:
  - **REQUIRES LIVE USER**: approval and follow-up Q&A block on user input
  - Per-area approval: each area is approved independently
  - Follow-up cap: ≤2 follow-up questions per area; if still unresolved after 2, note the remaining gap in the doc's Open Questions section and proceed
  - Rework scope: if an area needs significant revision, rewrite only that area doc
  - "Self-contained" check before approval: the doc must not have unresolved questions that would prevent an agent from starting implementation work in that area today
- **Verification**: All 4 files exist and are confirmed approved by user; no area has unresolved blocking open questions

### Task 8: Commit all approved docs
- **Files**: `requirements/observability.md`, `requirements/remote-access.md`, `requirements/multi-agent.md`, `requirements/pipeline.md`
- **What**: Stage all four approved area docs and commit using the `/commit` skill.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
  - Use `/commit` skill; never run `git commit` directly
  - Stage the four files specifically; do not stage unrelated changes
  - Commit subject: "Add area requirements docs for observability, remote-access, multi-agent, pipeline"
- **Verification**: `git log --oneline -1` shows the commit; `ls requirements/` shows all four files; `git show --stat HEAD` lists all four files

## Verification Strategy

After Task 8 completes:
1. `ls requirements/` — all four files present alongside `project.md`
2. `git show --stat HEAD` — commit contains exactly the four new files
3. Spot-check each file: parent backlink present, has Functional Requirements section with acceptance criteria, has Architectural Constraints section, 60–150 lines
4. Check `requirements/pipeline.md` specifically: dashboard no-auth constraint present under Architectural Constraints; state machine phases documented
5. Check `requirements/remote-access.md` specifically: no tmux-specific tooling encoded as a requirement; capability language used
