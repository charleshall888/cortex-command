# Research: IndyDevDan Multi-Agent Patterns

> Source: [One Agent Is NOT ENOUGH: Agentic Coding BEYOND Claude Code](https://youtu.be/M30gp1315Y4) by IndyDevDan
> Supplemented with: [agenticengineer.com roadmap](https://agenticengineer.com/top-2-percent-agentic-engineering), [claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery), [claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability), [Claude Code Agent Teams docs](https://code.claude.com/docs/en/agent-teams)

## Research Questions

1. **Does best-of-N (competing parallel agents) outperform retry-with-escalation?** → **Already in use for exploration; not worth extending to implementation.** cortex-command already deploys three distinct best-of-N variants: parallel-for-coverage (/research, 3-5 agents), parallel-for-independence (/critical-review, per-angle reviewers + Opus synthesis), and competing-on-same-task (lifecycle plan phase, 2-3 competing plan agents for critical features). These work well for their respective purposes. For implementation tasks, the cost multiplication (linear token scaling per agent) combined with Git reconciliation complexity makes best-of-N impractical. Self-correcting loops (retry + learnings, which cortex-command already uses) outperform single-pass by ~40% at lower cost. The existing boundary — best-of-N for exploration/design, retry-with-escalation for implementation — is sound and already operational.

2. **Would formalizing a trust progression model improve cortex-command?** → **No — the existing system already encodes trust progression implicitly.** IndyDevDan's 5-stage model (Base → Better → More → Custom → Orchestrator) maps directly to what cortex-command already has: model selection matrix (trust through model tiers), retry with learnings (better), parallel dispatch (more), per-feature worktree isolation (custom), overnight orchestrator (orchestrator). Naming the stages adds no operational value.

3. **Is hook-based WebSocket event streaming worth adopting over file-polling?** → **No.** The current 7s worst-case latency is acceptable for overnight monitoring. WebSocket streaming would add a persistent server process, a new protocol, and SQLite dependency for marginal latency improvement. The real observability gap is depth (agent internal state, token breakdown, error root cause), not latency.

4. **Should interactive work have structured multi-agent orchestration?** → **Not yet — current subagent patterns are functional for existing needs.** Interactive multi-agent already includes staged dispatch with dependency ordering (/research), parallel-then-synthesize (/critical-review), and batch implementation dispatch (/lifecycle implement). The model routing gap (backlog #044-046) is now resolved. Claude Code Agent Teams remains experimental (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var, no session resumption, one team per session). Revisit if a concrete interactive workflow emerges that breaks under the current subagent pattern — not on GA status alone.

5. **Does cortex-command have a stop-hook validation pattern?** → **No — this is a genuine gap, but adoption requires pipeline-layer changes beyond the hook itself.** The current Stop hook only sends notifications. IndyDevDan's pattern uses stop hooks to block agent completion until acceptance criteria pass (tests, build, lint). Claude Code supports this via `{"decision": "block", "reason": "..."}` return value. However, a blocking stop hook forces the agent to continue within the same `query()` call, consuming additional turns and budget. If forced continuation pushes cost past the tier ceiling ($5/$25/$50), the SDK signals `budget_exhausted`, which the retry pipeline maps to `pause_session` — halting all features, not just the failing one. Adopting stop-hook validation requires: (a) verifying the Stop hook stdin JSON schema includes `stop_hook_active`, (b) adding a `stop_hook_block` error type to the dispatch error classification so the retry pipeline can distinguish forced-continuation budget exhaustion from genuine budget exhaustion, and (c) checking `stop_hook_active` to prevent infinite loops. The hook itself is simple; the pipeline integration is the real work.

6. **Are there gaps in cortex-command's session-start context injection?** → **No significant gaps.** cortex-command's `cortex-scan-lifecycle.sh` already exceeds IndyDevDan's approach: lifecycle state, pipeline status, feature matching, fresh-resume prompts, and metrics injection. IndyDevDan loads git status and recent issues — cortex-command gets git state via the statusline instead.

## Codebase Analysis

### Current Multi-Agent Architecture

**Overnight (fully implemented):**
- Parallel dispatch via `asyncio.gather()` with semaphore (1-3 workers) — `claude/pipeline/dispatch.py`
- 2D model selection matrix (complexity x criticality → haiku/sonnet/opus) — `dispatch.py:134-147`
- Fixed escalation ladder: haiku → sonnet → opus — `dispatch.py:151-157`
- Sequential retry (max 3) with learnings in `progress.txt` — `claude/pipeline/retry.py:165-433`
- Circuit breaker: 3 consecutive pauses halt session — `retry.py:299-323`
- Worktree isolation per feature — `requirements/multi-agent.md`

**Interactive (functional for current needs):**
- Parallel-for-coverage: /research dispatches 3-5 agents across independent angles (SKILL.md lines 65-171)
- Parallel-for-independence: /critical-review dispatches per-angle reviewers + Opus synthesis (SKILL.md lines 70-137)
- Competing-on-same-task: lifecycle plan phase dispatches 2-3 competing plan agents for critical features (plan.md line 23)
- Batch implementation: lifecycle implement dispatches per-task agents in topological batches (implement.md line 48)
- Model routing: backlog #044-046 resolved (interactive subagents now routed to Sonnet for non-critical tasks)
- No stop-hook validation for implementation quality
- No inter-agent messaging or shared task lists (uses independent subagents coordinated by orchestrator conversation)

### Existing Best-of-N Patterns

The system already uses three distinct best-of-N variants with accepted cost multipliers:

| Pattern | Where Used | Agents | Cost Multiplier | Purpose |
|---------|-----------|--------|-----------------|---------|
| Parallel-for-coverage | /research | 3-5 | 3-5x | Explore independent angles, eliminate blind spots |
| Parallel-for-independence | /critical-review | 3-4 + Opus | 4-5x | Prevent anchoring bias across challenge angles |
| Competing-on-same-task | Lifecycle plan (critical) | 2-3 | 2-3x | Find non-obvious decompositions for critical features |

The boundary: best-of-N for exploration/design artifacts (no Git reconciliation needed), retry-with-escalation for implementation (agent produces code diffs that must merge cleanly).

### Hook System (8 event types configured)

| Event | Hooks | Validation? |
|-------|-------|-------------|
| SessionStart | cortex-sync-permissions.py, cortex-scan-lifecycle.sh, cortex-setup-gpg-sandbox-home.sh | No |
| SessionEnd | cortex-cleanup-session.sh | No |
| PreToolUse (Bash) | cortex-validate-commit.sh | **Yes** — blocks invalid commits |
| PostToolUse (Bash) | cortex-tool-failure-tracker.sh | No |
| PostToolUse (Write\|Edit) | cortex-skill-edit-advisor.sh | No |
| Notification (permission_prompt) | cortex-notify.sh, cortex-notify-remote.sh, cortex-permission-audit-log.sh | No |
| Stop | cortex-notify.sh, cortex-notify-remote.sh | **No — notification only** |
| WorktreeCreate/Remove | cortex-worktree-create.sh, cortex-worktree-remove.sh | No |

**Key gap:** No stop-hook validation. The Stop hook fires on every completion but only sends notifications. No mechanism to block completion when tests fail, build breaks, or acceptance criteria aren't met. Adoption requires pipeline-layer changes (see Q5 above).

### Dashboard Observability

- File polling: 2s (state files), 1s (events), 5s (HTMX refresh) — ~7s worst-case latency
- No WebSocket, SSE, or push-based updates
- Alert system: stall (5m timeout), circuit breaker, deferred, high rework
- Notifications: macOS desktop + Android push via ntfy.sh

**Observability depth gaps** (not addressed by switching to WebSocket):
- No agent internal state visibility (only final turn events)
- No per-turn token/cost breakdown
- No error root cause drill-down (only first-line error message)
- No git push/pull status visibility in real time

## Web & Documentation Research

### Claude Code Agent Teams (Experimental)

Official feature as of Claude Code v2.1.32. Key mechanics:
- Lead session spawns teammates, each with own context window
- Shared task list with dependency tracking and file-lock-based claiming
- Inter-agent messaging (direct + broadcast)
- Quality gates: `TaskCompleted` hook (exit 2 to block), `TeammateIdle` hook
- Subagent definitions reusable as teammate roles
- Token cost scales linearly with teammate count
- Recommended team size: 3-5 teammates, 5-6 tasks per teammate

Limitations: no session resumption with in-process teammates, no nested teams, lead is fixed, one team per session, split panes require tmux/iTerm2.

### Stop Hook Validation Pattern

Three outcomes for a stop hook:
1. Exit 0 → agent stops normally
2. Return `{"decision": "block", "reason": "..."}` → agent continues working
3. Run validation (tests, build, lint) and decide

**Critical safety:** Must check `stop_hook_active` flag. When true, agent is already in forced-continuation from a previous block. Always `exit 0` when flag is true to prevent infinite loops.

**Pipeline interaction risk:** A blocking stop hook forces the agent to continue within the same `query()` call, consuming additional turns and budget against the tier ceiling. This can trigger `budget_exhausted` classification, which the retry pipeline maps to `pause_session` — a session-wide halt. The dispatch error classification system (`ERROR_RECOVERY` in dispatch.py) has no category for "stop hook forced continuation." Adopting stop-hook validation requires adding this distinction.

**Hook timeout behavior:** A stop hook that exceeds its 60s timeout is killed and its output discarded — Claude Code proceeds as if no decision was made. The agent completes normally and the feature is marked complete with potentially failing tests. This is the exact failure mode the stop hook is meant to prevent.

**"Ralph Wiggum" pattern:** Maintain a marker file; agent must explicitly remove the marker to complete. Transforms "best effort" into "guaranteed completion."

### Industry Multi-Agent Patterns (2026)

- Every major tool shipped multi-agent in Feb 2026 (Grok Build, Windsurf, Cursor, Claude Code, Codex CLI, Devin)
- Parallel agents with git worktrees is table stakes
- Self-correcting loop agents outperform single-pass by ~40% (AutoGen, Reflexion benchmarks)
- Cost is the dominant concern: "which tool won't torch my credits?"
- Anti-pattern: running competing agents on the same implementation task (Git reconciliation complexity)

## Domain & Prior Art

### IndyDevDan's Framework

**Core Four Leverage Points:** Context, Model, Prompt, Tools — every agent system depends on these. cortex-command maps cleanly: CLAUDE.md + hooks (Context), model matrix (Model), skill prompts (Prompt), tool allowlists (Tools).

**Multi-Agent Progression Model:** IndyDevDan's Base → Better → More → Custom → Orchestrator stages map to cortex-command features (skills/hooks, parallel dispatch, per-feature isolation, overnight orchestrator). The overnight system implements the full progression; interactive work uses subagents effectively for current needs.

**IndyDevDan's Hook-Based Observability:**
- 12 hook event types → HTTP POST → Bun server → SQLite → WebSocket → Vue dashboard
- Dual-color visualization (app + session)
- Real-time broadcasting via WebSocket
- Builder/Validator agent team pattern with stop-hook quality gates

**Key difference from cortex-command:** IndyDevDan's observability is generic and portable (works across any project). cortex-command's is specialized for overnight session monitoring with domain-specific panels (feature cards, swim lanes, fleet view). The approaches optimize for different things.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **Post-merge test validation** | — | — | **Already implemented** via `test_command` in `BatchConfig` + `merge.py:run_tests()`. Per-repo configurable via `lifecycle.config.md` `test-command:` field. |
| **Document test-command for new repos** | S | None | None — docs update only |
| **Best-of-N extension beyond current use** | M | Cost multiplication; Git reconciliation for implementation; unclear selection criteria | Agent Teams or manual worktree orchestration |
| **WebSocket event streaming** | L | New server process, new dependency (SQLite), protocol complexity for marginal latency gain | Bun or equivalent server runtime |
| **Trust progression formalization** | S | No operational value; adds naming without changing behavior | None |

## Decision Records

### DR-1: Post-merge test validation already exists — stop-hook not needed

- **Context**: The initial research identified stop-hook validation as a gap, but deeper investigation revealed that cortex-command already has a per-repo configurable `test_command` that runs post-merge via `merge.py:run_tests()`. This was missed because the research focused on hook-layer patterns from IndyDevDan's framework rather than tracing the existing pipeline.
- **Options considered**: (A) Stop hook with test/build validation + dispatch pipeline changes, (B) PostToolUse hook that validates after every Bash command, (C) Pre-merge validation — **already implemented** via `test_command` in `BatchConfig`
- **Recommendation**: No new mechanism needed. Option C is already in place: `merge_feature()` runs `test_command` after each feature merge; failures trigger the repair agent (`integration_recovery.py`); unresolvable failures pause the feature. The `test_command` is per-repo configurable via `lifecycle.config.md` frontmatter (`test-command:` field) and threaded through CLI args → batch plan → merge → review dispatch rework loop.
- **Action taken**: Expanded `docs/overnight.md` "Per-repo Overnight" section to document `lifecycle.config.md` setup and the `test-command` field, since the existing mechanism was poorly documented for new repo onboarding.
- **Why stop-hook was wrong**: The Stop hook fires on every response completion (dozens per session), not just at feature completion. Running tests each time is wasteful and interacts adversarially with the budget ceiling and circuit breaker. Post-merge is the correct checkpoint — it runs exactly once per feature, at the boundary where validation matters.

### DR-2: Best-of-N boundary is already correct — no change needed

- **Context**: The system already uses three distinct best-of-N variants for exploration/design work (parallel-for-coverage, parallel-for-independence, competing-on-same-task). These are working well. The question is whether to extend best-of-N to implementation tasks.
- **Options considered**: (A) Best-of-N for implementation tasks, (B) Best-of-N for more design tasks, (C) Keep current boundary
- **Recommendation**: Option C — the existing boundary (best-of-N for exploration/design, retry-with-escalation for implementation) is sound. The anti-pattern of competing agents on implementation tasks (Git reconciliation, conflicting diffs) is well-documented. The cost multiplier is accepted for exploration where it adds value (eliminating blind spots, preventing anchoring) but not justified for implementation where retry + learnings achieves comparable outcomes.
- **Trade-offs**: May occasionally miss a better implementation approach. Acceptable given the reconciliation complexity.

### DR-3: Agent Teams — conscious deferral, not monitoring

- **Context**: Claude Code Agent Teams provides structured multi-agent orchestration with shared task lists and inter-agent messaging. It is experimental with known limitations.
- **Options considered**: (A) Adopt Agent Teams now, (B) Monitor for GA and reassess, (C) Consciously defer — no action until a specific interactive workflow breaks under the current subagent pattern
- **Recommendation**: Option C — conscious deferral. The current subagent pattern handles existing interactive needs (research, review, implementation dispatch). Rather than passively monitoring Anthropic's release notes, revisit only when a concrete interactive workflow surfaces that requires inter-agent communication and cannot be accomplished with independent subagents. As the project's overnight autonomy increases, human coordination of interactive work will decrease — that transition is the natural trigger, not a feature GA announcement.
- **Trade-offs**: Missing out on early Agent Teams adoption if it stabilizes quickly. Acceptable — the downside of premature adoption (experimental limitations, session resumption bugs) outweighs the upside.

### DR-4: Event-streaming observability is not worth the complexity

- **Context**: IndyDevDan's WebSocket-based dashboard provides real-time event streaming. cortex-command's file-polling dashboard has ~7s latency.
- **Options considered**: (A) WebSocket event streaming via hook → HTTP POST → server, (B) SSE from dashboard to browser (keep file polling on backend), (C) Keep current HTMX polling
- **Recommendation**: Option C — keep current approach. The 7s latency is acceptable for overnight monitoring. The real observability gaps are depth (agent internal state, token breakdown, error context), not latency. Those gaps require agent-side instrumentation, not transport changes.
- **Trade-offs**: Dashboard updates are slightly delayed. Acceptable for unattended overnight sessions.

## Open Questions

- None. The discovery's primary finding (stop-hook validation gap) turned out to be already addressed by the existing `test_command` post-merge mechanism. The remaining action was documentation, which has been completed in `docs/overnight.md`.
