# Research: subagent-model-routing

## Research Questions

1. **Does the Agent tool's `model` parameter work with Claude Max subscriptions?**
   → **Yes.** The `model` field accepts `sonnet`, `opus`, `haiku`, or full model IDs. No subscription-tier restrictions on model choice. The parameter works identically across Pro, Max, and API key plans.

2. **Which skills/processes spawn subagents today, and what model override do they use?**
   → **Interactive skills specify no model — all inherit Opus from the parent session.** The overnight runner has a well-defined model selection matrix in `dispatch.py`, but interactive Agent() calls in skills omit the `model` parameter entirely. This means every subagent spawned during an Opus 4.6 1M chat session also uses Opus 4.6, regardless of task complexity.

3. **Is there a Claude Code setting for default subagent model?**
   → **Yes — `CLAUDE_CODE_SUBAGENT_MODEL` environment variable.** However, the priority order between env var and per-invocation `model` param is disputed. Some sources say env var overrides per-invocation; others say per-invocation overrides env var (the conventional software pattern). GitHub issue anthropics/claude-code#10993 was filed specifically because this behavior is unclear, and Anthropic closed it without publishing a canonical resolution. No `settings.json` key exists for this. **The priority order must be empirically verified before choosing between approaches A and D.**

4. **What are the actual context requirements of typical subagent tasks?**
   → **Minimal.** Subagents start with fresh context. Typical tasks (codebase exploration, research, code review, planning) consume well under 200K tokens. The 1M window is only valuable for the main chat session where conversation history accumulates over extended work.

5. **Where should model routing logic live?**
   → **Three viable locations**: per-skill Agent() calls, env var, or a reference doc that instructs Claude when to specify `model: "sonnet"`. These are not mutually exclusive.

6. **What quality tradeoffs exist between Sonnet 4.6 and Opus 4.6 for non-critical tasks?**
   → **Sonnet 4.6 is highly capable for exploration, research, and planning.** The overnight runner already routes most work to Sonnet (only complex+high/critical goes to Opus). Quality difference is meaningful for deep reasoning and novel implementation but negligible for read-only analysis, exploration, and structured tasks.

## Codebase Analysis

### Interactive Spawn Sites (no model specified — all inherit Opus)

| Location | Task | Criticality | Sonnet-safe? |
|----------|------|-------------|--------------|
| `skills/lifecycle/SKILL.md:345` | Parallel multi-feature dispatch | LOW | Yes |
| `skills/research/SKILL.md:169` | Parallel research angle exploration | LOW | Yes |
| `skills/lifecycle/references/implement.md:37` | Per-task implementation | HIGH | Partially — already has criticality logic but no model param |
| `skills/discovery/` (via research skill) | Discovery research agents | LOW | Yes |
| `skills/critical-review/` | Parallel reviewer agents | MEDIUM | Yes |
| `claude/reference/parallel-agents.md` | Pattern doc for parallel agents | N/A | Should document model selection (currently lacks this guidance) |

### Overnight Spawn Sites (already routed correctly via dispatch.py)

| Location | Task | Model Selection |
|----------|------|-----------------|
| `claude/pipeline/dispatch.py:332` | Core dispatch | 2D matrix (complexity x criticality) |
| `claude/pipeline/conflict.py:328` | Merge conflict repair | Sonnet first, escalate to Opus |
| `claude/overnight/brain.py:224` | Retry triage | Hardcoded Sonnet (simple tier) |
| `claude/overnight/batch_runner.py` | Feature execution | Via dispatch matrix |

**Key insight**: The overnight runner already does intelligent model routing. The gap is entirely in interactive sessions where skills spawn subagents.

### Override Mechanisms Available

1. **`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`** — Global env var. Whether it overrides or is overridden by per-invocation `model` params is disputed (see RQ3).
2. **Per-invocation `model` param** — `Agent(model: "sonnet", ...)` in each skill's Agent() call. Granular control.
3. **Subagent frontmatter** — `model: sonnet` in agent definition YAML. Applies to named/typed agents.

### Model Selection Matrix (from dispatch.py, overnight reference)

| Complexity \ Criticality | low | medium | high | critical |
|--------------------------|-----|--------|------|----------|
| trivial | haiku | haiku | sonnet | sonnet |
| simple | sonnet | sonnet | sonnet | sonnet |
| complex | sonnet | sonnet | opus | opus |

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A: Env var default** (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`) | S | If env var overrides per-invocation params: no per-task granularity. If per-invocation overrides env var: this becomes viable with full granularity. Priority order is disputed (see RQ3). | Verify priority order empirically |
| **B: Per-skill model params** — Add `model: "sonnet"` to Agent() calls in skills | M | Maintenance burden — every new skill needs to remember model selection. Risk of drift. | Audit all skills with Agent() calls |
| **C: Reference doc guidance** — Add model selection rules to a conditionally-loaded reference doc that instructs Claude when to use `model: "sonnet"` vs `model: "opus"` | S | Soft enforcement — Claude may not always follow the guidance. But this matches how other cross-cutting concerns (verification mindset, parallel agents) are already handled. | Write reference doc, add conditional loading rule |
| **D: Reference doc + per-skill model params** — A conditionally-loaded reference doc instructs Claude to default subagents to Sonnet; critical skills explicitly pass `model: "opus"` | M | Most complete solution. Reference doc catches new/unmodified skills by convention. Per-skill overrides preserve Opus where needed. No env var conflict. | Write reference doc, update critical skills |

## Decision Records

### DR-1: Primary routing mechanism

- **Context**: Need to route most interactive subagents to Sonnet while preserving Opus for the main chat session's 1M context window.
- **Options considered**:
  - (A) Env var only — simple. Whether per-skill overrides work depends on disputed priority order (see RQ3). If per-invocation overrides env var, A is viable with full granularity. If env var overrides per-invocation, A blocks Opus escalation.
  - (B) Per-skill only — granular but high maintenance
  - (C) Reference doc only — soft enforcement, may not be reliable
  - (D) Reference doc + per-skill model params — doc instructs Claude to default subagents to Sonnet; critical skills explicitly pass `model: "opus"`
- **Recommendation**: **Conditional on priority order verification.**
  - If per-invocation overrides env var: **Option A** (env var `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`) is sufficient and strictly simpler. Per-skill `model: "opus"` overrides would work for critical tasks. A reference doc documenting the convention is still useful but not load-bearing.
  - If env var overrides per-invocation: **Option D** (reference doc + per-skill). Skills that need Opus pass `model: "opus"` without env var interference.
  - Either way, add model selection guidance to CLAUDE.md (not a conditionally-loaded doc — it's small enough to be always-loaded and avoids the trigger-definition problem).
- **Verification step**: Set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and spawn an agent with `model: "opus"`. Check which model the agent actually uses. This resolves the recommendation definitively.
- **Trade-offs**: Option A is simpler if priority order allows it. Option D provides the same outcome but with more moving parts. Both rely on Claude following guidance for the Opus escalation cases.

### DR-2: Where Opus remains justified in interactive sessions

- **Context**: Not all subagent work is equal. Some tasks benefit materially from Opus.
- **Options considered**: Route everything to Sonnet vs. preserve Opus for specific task types
- **Recommendation**: Preserve Opus for implementation sub-tasks dispatched from lifecycle implement phase when criticality is high/critical. All other interactive subagent work (research, exploration, critic review, planning, discovery) routes to Sonnet.
- **Trade-offs**: Implementation quality for critical features is preserved at the cost of higher token usage for those specific tasks.

## Open Questions

- **Env var priority order**: Must be empirically verified before choosing between approaches A and D. Test: set `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, spawn an agent with `model: "opus"`, check which model runs. This is a **blocker** for the final recommendation.
- ~~**What constraint is this solving?**~~ **Resolved**: All three — rate limits/throttling, daily usage caps, and general efficiency (Sonnet suffices for non-critical subagent work). Model routing addresses multiple binding constraints simultaneously, not just a single bottleneck.
- **Token usage measurement**: What is the actual token usage difference between Opus and Sonnet subagents for typical tasks? Post-implementation validation, not a blocker.
