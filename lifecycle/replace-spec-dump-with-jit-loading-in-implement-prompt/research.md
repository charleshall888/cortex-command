# Research: Replace spec dump with JIT loading in implement prompt

## Epic Reference

Background context from epic research at `research/harness-design-long-running-apps/research.md` — this ticket addresses the "Context bloat: `_read_spec_excerpt` does not excerpt" finding (DR-3 area) and the brain agent context concerns identified in the deep investigation.

## Codebase Analysis

### Files That Will Change

**Prompt Templates:**

1. `claude/pipeline/prompts/implement.md` — Currently receives `{spec_excerpt}` (full spec) into "## Specification Context" section (line 11). Rendered by `_render_template()` in batch_runner.py:815. Template variables: feature, task_number, task_description, plan_task, spec_excerpt, worktree_path, learnings, integration_worktree_path.

2. `claude/overnight/prompts/batch-brain.md` — Labels inputs as "complete, untruncated" (lines 17, 21, 27). Template variables: feature, task_description, retry_count, learnings, spec_excerpt, has_dependents, last_attempt_output. Rendered by brain.py:214.

**Python Modules:**

3. `claude/overnight/batch_runner.py`:
   - `_read_spec_excerpt()` (lines 345-355): Reads entire spec unconditionally. Called at line 793.
   - `_read_learnings()` (lines 358-372): Reads all accumulated learnings unconditionally. Called at line 813.
   - `_handle_failed_task()` (lines 453-525): Builds BrainContext with full learnings + spec + output.
   - `_run_task()` (lines 737-880): Passes full spec_excerpt and learnings to implement.md template.

4. `claude/overnight/brain.py` — `BrainContext` dataclass (lines 59-79) and `request_brain_decision()` (lines 187-267).

5. `claude/pipeline/retry.py` — `_append_learnings()` (lines 73-119) already truncates output to 2,000 chars (line 102). Reusable pattern.

### Existing Patterns

- **Template rendering**: `_render_template(template_path, variables_dict)` uses `template.replace(f"{{{key}}}", value)`. All variables must be strings.
- **Path resolution**: `_read_spec_excerpt()` checks explicit `spec_path` from state first, falls back to `lifecycle/{feature}/spec.md`.
- **Output truncation**: retry.py:102 caps at 2,000 chars with `"\n... (truncated)"` marker.
- **Missing file fallback**: Functions return descriptive fallback strings, not exceptions (e.g., `"(No prior learnings.)"`, `"(No specification file found.)"`).
- **Function naming**: `_read_*()` for full-content reads, `_get_*()` for references/identifiers.

### Integration Points

- **Spec path resolution**: `OvernightFeatureStatus.spec_path` (state.py:92) populated by orchestrator; flows through state to `_run_feature()` to `_run_task()`.
- **Sandbox allowlist**: `dispatch.py:405-418` sets up per-agent sandbox. `integration_base_path` IS passed to `dispatch_task` (batch_runner.py:851, retry.py:250-251), so agents can read from `integration_base_path + "/lifecycle/{feature}/spec.md"`. However, the roundtrip is untested — no test verifies agents can actually read lifecycle artifacts.
- **Learnings flow**: `_append_learnings()` → `progress.txt` → `_read_learnings()` → all task prompts + brain agent. Only written during retries (retry.py:277). First-attempt successes never trigger learnings.

### Token Size Data

| Metric | Value |
|--------|-------|
| Median spec size | ~2,000-2,300 tokens |
| Max spec size | ~4,200 tokens (build-setup-merge-local-skill) |
| Per-worker injection | 2,000-4,200 tokens |
| Batch of 3×4 workers | 24,000-50,400 tokens/round |
| Brain agent total context | 15,000-20,000+ tokens |

## Web Research

### Anthropic Context Engineering Guidance

Anthropic's [context engineering guide](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) explicitly recommends: "agents built with the 'just in time' approach maintain lightweight identifiers (file paths, stored queries, web links) and use these references to dynamically load data into context at runtime using tools." The guiding metric: "the smallest set of high-signal tokens that maximize the likelihood of some desired outcome."

The [harness design article](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) validates that learnings should be an external artifact agents read on demand, not injected upfront — the `claude-progress.txt` pattern.

### Multi-Agent Context Patterns

- **Google ADK handle pattern**: Agents see only lightweight references; use `LoadArtifactsTool` to load on demand. Directly analogous to JIT spec loading.
- **Report-based handoff**: Workers write structured artifacts that downstream agents read, rather than having content injected by orchestrators (Addy Osmani).
- **Claude Code MCP lazy loading**: Achieves "95% context reduction" by providing a `search_tools` tool with `detail_level` parameter instead of loading all tool definitions upfront.

### Truncation Research

- **"Lost in the Middle" (Stanford/UC Berkeley, NeurIPS 2023)**: LLMs perform best when relevant information appears at beginning or end of context. Directly supports head+tail over head-only.
- **SWE-agent**: Uses 5,000+5,000 char head/tail strategy when output exceeds 10,000 chars.
- **JetBrains research**: LLM-generated summaries mask failure signals (+15% runtime waste). Observation masking (head+tail) outperformed summarization in 4/5 SWE-bench settings while being 52% cheaper.
- **Critical finding**: Summaries "smooth over signs indicating that the agent should already stop trying." For brain agent triage, this means head+tail preserves raw diagnostic signal better than summarization.

### Parallel Dispatch Cost Multiplication

Every token in the system prompt template is multiplied by the number of parallel workers. With prompt caching, cached tokens still count against the context window's attention budget even if API cost is reduced.

## Requirements & Constraints

### Load-Bearing Requirements

1. **"The spec is the entire communication channel"** (requirements/project.md:13) — Features must have "all lifecycle artifacts fully self-contained." Spec accessibility cannot be degraded.

2. **Learnings for retry avoidance** (requirements/multi-agent.md:67) — "Each retry appends learnings to progress.txt; subsequent agents receive this history to avoid repeating failed approaches." This is a functional requirement.

3. **Learnings truncation at 2,000 chars per entry** (requirements/multi-agent.md:68) — Already an explicit constraint. Individual entries are capped, but the aggregate file is not.

4. **Atomic state writes** (requirements/pipeline.md:93) — All state writes use tempfile + `os.replace()`. Permanent architectural constraint.

5. **Repair attempt caps are fixed** (requirements/pipeline.md:101) — Max 2 for test failures, single escalation for merge conflicts. Cost-bounded.

### Scope Boundaries

**In scope**: Modifying how agents receive specs (injection → JIT), how brain receives context (full → truncated), how learnings are gated (always → conditional).

**Out of scope**: Changing state file atomicity, removing learnings tracking, changing repair attempt caps, removing worktree isolation, changing escalation ladder.

### Constraint Tensions

- **"Spec is entire communication channel"** vs. **JIT loading**: If JIT loading fails silently, the communication channel is broken. The spec must remain accessible — only the delivery mechanism changes.
- **"Agents receive learnings to avoid repeating failed approaches"** vs. **failure-gated learnings**: Gating must preserve the functional requirement for tasks that need learnings while eliminating injection for tasks that don't.

## Tradeoffs & Alternatives

### Change 1: Spec Loading

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
| **A: JIT with {spec_path}** (proposed) | Replace `{spec_excerpt}` with path + "read if needed" instruction | Largest savings (2-4K tokens/worker); agents self-regulate | Depends on agent judgment; requires sandbox access verification; breaks prompt cache prefix |
| **B: Inject relevant section only** | Parse spec for section matching task name/topic | Keeps spec immediately available; saves ~50% | Fragile parser; requires well-structured headings; still upfront injection |
| **C: Inject summary/abstract** | Add TLDR section to spec, inject only that + path for full spec | Quick orientation; falls back to JIT gracefully | Requires maintaining summary in sync; still some upfront injection |
| **D: Do nothing** | Keep current approach | No risk; spec always available | Wastes 9,600-48,000 tokens/round |

**Recommended: A** — Aligns with Anthropic's own guidance. Largest savings with minimal implementation cost. Pair with error handling for inaccessible specs.

### Change 2: Brain Truncation

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
| **A: Head+tail at ~2,000 tokens** (proposed) | Cap last_attempt_output with head+tail; cap learnings to recent entries | 86% token reduction; preserves head/tail signal | Loses mid-output debugging arc; brain may misclassify structural vs. transient |
| **B: Structured extraction** | Parse for error messages, stack traces, final state only | Very focused context (~1K tokens) | Fragile regex; misses "what was being attempted" context |
| **C: Keep full + "focus on" instruction** | Add guidance to ignore successful steps | No information loss; no parsing | Token usage unchanged; instruction compliance unreliable |
| **D: Two-pass brain** | Pass 1: truncated → quick call; Pass 2: full context if uncertain | Adaptive; preserves full context for edge cases | Doubles latency for uncertain cases; over-engineered for classification |

**Recommended: A with caution** — Head+tail is well-supported by research. But the "complete, untruncated" labeling in batch-brain.md was a deliberate signal-preservation choice. Requires monitoring and prompt update.

### Change 3: Learnings Gating

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
| **A: Gate on failure history** (proposed) | Skip learnings for clean-run tasks | Avoids 1-3K tokens for successful sequences; trivial implementation | Downstream tasks blind to upstream dead-ends; first-attempt successes never write learnings |
| **B: Always inject, truncate to last N entries** | Cap at last 500 tokens or last 10 lines | Always available; removes old noise | Still injects into clean-run tasks; truncation point needs tuning |
| **C: Filter by task name** | Parse learnings for mentions of current task number | Highly targeted; maximum signal-to-noise | Fragile parsing; cross-task learnings lost |

**Recommended: A** — Most features run clean on first 1-2 tasks. Gate is trivial to implement. But must preserve full learnings for brain agent (brain is making final irreversible decisions).

## Adversarial Review

### Failure Modes and Edge Cases

1. **Sandbox access roundtrip is untested**: `integration_base_path` IS passed to dispatch (batch_runner.py:851), but no test verifies that agents can actually read `lifecycle/{feature}/spec.md` through the allowlist. The path depends on `Path.cwd()` at dispatch time — if working directory changes before dispatch (async task switching), the allowlist breaks silently. JIT spec loading would surface as "file not found" rather than a clear sandbox error.

2. **Cascading failure from gated learnings**: If task 1 succeeds (no learnings written) and task 2 fails, task 2 has no learnings from task 1's execution context. Since `_append_learnings()` only triggers during retries (retry.py:277), first-attempt successes never generate learnings. Downstream tasks are blind to upstream dead-ends in clean feature runs.

3. **Head+tail truncation destroys the debugging arc**: If retries follow a pattern of "tried approach A → failed → tried approach B → failed → tried approach C → failed," head+tail shows only the first and last approaches. The brain's batch-brain.md line 17 says "patterns across attempts often reveal whether the failure is structural or transient." Truncating the middle removes exactly the cross-attempt pattern the brain needs.

4. **Spec versioning gap**: If task 1 reads the spec via JIT, then the feature pauses and resumes in a later session after the spec was edited, tasks 2-7 see a different spec than task 1 was implemented against. No spec hash is stored in completion tokens to detect this drift.

5. **Brain prompt regression**: The "complete, untruncated" language in batch-brain.md is load-bearing — it tells the brain it has everything needed for a final, irreversible SKIP/DEFER/PAUSE decision. Silently truncating without updating the prompt creates false assumptions. The brain makes one-shot decisions that cascade to downstream tasks, human interruptions, and session continuation.

### Assumptions That May Not Hold

- **"Most task descriptions are self-contained"**: Specs are feature-level, not task-level. Plan.md provides task-specific coupling (dependencies, line numbers, architectural assumptions), but plan.md is NOT injected into task prompts. Tasks with upstream dependencies (e.g., "Depends on [1]") need more context than their description alone provides.

- **Token savings estimates ignore prompt caching**: If the same spec is injected into every task dispatch for a feature, the Claude Agent SDK likely caches that prefix. With JIT loading, the cache prefix breaks (different input distribution), and file I/O tool calls add latency + token overhead. Actual savings may be 5-10% rather than 30-40%.

- **Brain triage quality will not degrade**: The brain is making a single, irreversible decision on an exhausted task. If truncation causes a wrong SKIP (instead of DEFER/PAUSE), the cascade includes: downstream tasks break, feature fails permanently, human gets an incorrect morning report. The adversarial finding is that we cannot assume truncation preserves decision quality without empirical validation.

### Recommended Mitigations

1. **Spec access validation**: Add a regression test verifying agents can read lifecycle artifacts from within sandboxed worktrees. Add defensive error handling in implement.md: if spec is unreadable, surface clearly instead of failing silently.

2. **Brain layer exemption**: Preserve full learnings and full last_attempt_output for the brain agent. The brain makes final, irreversible decisions — it should not operate on truncated context. Apply truncation only to task workers in implement.md.

3. **Learnings gating scope**: Gate learnings only for task agents, not the brain. And only gate when progress.txt is empty/absent (no prior failures in this feature), not per-task.

4. **Prompt truth**: If truncating any brain input, update batch-brain.md to say "truncated" instead of "untruncated." The prompt must reflect reality.

5. **Spec hash for resumed sessions**: Store a spec content hash in the completion token for each task. On session resume, verify the spec hasn't changed before dispatching remaining tasks.

6. **Measure before committing**: Instrument actual token usage per dispatch to validate savings estimates against prompt caching behavior. If savings are <10%, the architectural cost may not be justified for Changes 2 and 3.

## Open Questions

- Should the brain agent be exempted from truncation entirely, or should it receive truncated learnings/spec but untruncated last_attempt_output? The brain's decision quality is the highest-stakes question in this ticket.
- What is the actual prompt caching hit rate for spec content across task dispatches within a feature? If high, JIT loading may break the cache and increase net cost.
- Should spec.md be frozen (copied to a versioned path) at feature start to prevent spec drift for resumed sessions?
