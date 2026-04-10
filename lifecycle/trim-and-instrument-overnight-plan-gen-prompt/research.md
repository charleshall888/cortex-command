# Research: Trim and instrument overnight plan-gen prompt

## Epic Reference

This ticket is scoped from `research/overnight-plan-building/research.md` (epic discovery). The epic established that the current orchestrator architecture already achieves three-way context isolation (DR-1 recommends status quo — Approach A), and listed conditional prompt inclusion as an "Open Question" idea. This ticket attempts to act on that idea plus a ticket-originated instrumentation addition. Scope here is the narrow trimming+instrumentation work only — no architectural extraction.

## Codebase Analysis

### fill_prompt mechanism

`claude/overnight/runner.sh:379-394` — flat `str.replace()` substitution over exactly six tokens via an inline `python3 -c` heredoc. The tokens are `{state_path}`, `{plan_path}`, `{events_path}`, `{session_dir}`, `{round_number}`, `{tier}`. No conditional inclusion, no block excision, no multi-variant template support.

```bash
fill_prompt() {
    local round_num="$1"
    STATE_PATH="$STATE_PATH" PLAN_PATH="$PLAN_PATH" EVENTS_PATH="$EVENTS_PATH" \
    SESSION_DIR="$SESSION_DIR" \
    ROUND_NUM="$round_num" TIER="$TIER" TEMPLATE="$PROMPT_TEMPLATE" python3 -c "
import os
t = open(os.environ['TEMPLATE']).read()
t = t.replace('{state_path}', os.environ['STATE_PATH'])
...
"
}
```

Called from `runner.sh:633` as `FILLED_PROMPT=$(fill_prompt "$ROUND")`. Under `set -e`, any helper exception kills the runner outright — fill_prompt has no error handling.

### Steps 3a-3e structure

`claude/overnight/prompts/orchestrator-round.md:232-278` — contiguous textual region. Begins with `### 3. Generate Missing Plans and Validate` (line 232), ends just before `### 4. Generate Batch Master Plan` (line 280). Cleanly excisable by HTML comment delimiters. Step 3b contains the full inline plan-gen sub-agent prompt (lines 240-265) that gets passed to the Task tool.

**Load-bearing cross-reference**: `orchestrator-round.md:296` (Step 4a excluded-feature handling) says *"same mechanism as Step 3e for missing plans"*. If Steps 3a-3e are excised wholesale, this textual reference dangles. Any excision design must rewrite Step 4a to describe the mechanism directly, or else preserve Steps 3a and 3e (see Mitigations).

### events.py — canonical event module

`claude/overnight/events.py` defines ~45 event-type constants (lines 32-76) validated against an `EVENT_TYPES` tuple (lines 78-124). `log_event()` at line 184 raises `ValueError` on unknown event types. Adding a new event requires a two-file change: constants block + tuple membership. Drift between them produces runtime traceback.

Default write target is `lifecycle/overnight-events.log` (symlinked to per-session `lifecycle/sessions/{session_id}/overnight-events.log`).

### Correction to ticket framing: `pipeline-events.log` vs `overnight-events.log`

The ticket's original framing implied targeting `pipeline-events.log`. That's wrong. Two distinct logs exist with different writers and schemas:

- `lifecycle/sessions/{session_id}/overnight-events.log` — **orchestrator/runner events** via `claude.overnight.events.log_event()`. This is the correct target for plan-gen instrumentation.
- `lifecycle/sessions/{session_id}/pipeline-events.log` — **worker dispatch events** via `claude.pipeline.state.log_event()` (a different function), called from `batch_runner.py:884,911,942`.

The two share a function name by accident. They are architecturally separate.

### LLM-side log_event precedent

Exactly one LLM-side `log_event` call exists in the orchestrator prompt today: `orchestrator-round.md:295-313` (Step 4a, `FEATURE_FAILED` for batch_plan exclusions). Uses `from claude.overnight.events import FEATURE_FAILED, log_event` and `from claude.overnight.orchestrator_io import ...`. The `orchestrator_io.py` module is the sanctioned import surface for orchestrator-prompt-executed Python.

The pattern is **sanctioned but not battle-tested** — one call site with a small production sample.

### Round-membership filter — lives only in the prompt

`orchestrator-round.md:162-173` contains the round filter as inline pseudocode:

```python
current_round = {round_number}
features_to_run = [
    f for f in features
    if f.get("status") == "paused"
    or (f.get("round_assigned") or 0) <= current_round
]
```

**No Python helper exists.** `runner.sh` has no callable to answer "which features are in this round?" — if the trim's conditional needs that answer, the filter must either be inlined into a new `python3 -c` helper in runner.sh or factored into a shared module in `state.py` / a new `round_filter.py`.

### Plan-gen sub-agent dispatch mechanism

Orchestrator-round.md Step 3b instructs the LLM to dispatch Task (Agent-tool) sub-agents directly. Zero Python-side involvement — no helper, no Python wrapper, no batch_runner.py code path. Instrumentation of "did a dispatch actually happen" must either be LLM-side (instruct the LLM to log) or hook-side (claim-hook on the Agent tool call).

### State transitions that promote features to `pending`

Four distinct paths — the tradeoffs agent only analyzed the first:

1. **`orchestrator-round.md:131` — escalation resolution**. Reads escalations from `lifecycle/escalations.jsonl`; only workers write these via `deferral.py:370 write_escalation()`; workers only run post-plan-existence gate — so promoted features *had* a plan_path at dispatch time.
2. **`interrupt.py:130-145 handle_interrupted_features()`** — runs at `runner.sh:570` BEFORE the main loop. Resets any `running`-status feature to `pending` with **no plan_path validation**. If a worker was interrupted and its worktree has been pruned (`git worktree prune` at runner.sh:580), the `plan_path` reference may now be orphaned.
3. **paused features re-included** — `orchestrator-round.md:162-173` filter includes `status == "paused"` unconditionally. A paused feature's `plan_path` could reference a file since deleted.
4. **`orchestrator-round.md:131` escalation resolution (T0 vs T1 mismatch)** — even within the escalation-resolution path, a plan_path that existed at dispatch time T0 may not exist at T1 between rounds. Worktree-local plan files can be lost to cleanup or reset.

**Implication**: Step 3a (hard-fail on missing spec) and Step 3e (final plan-existence validation) act as the **last-chance disk existence check** for all four paths. Trimming them unconditionally removes the safety net for edge cases the tradeoffs agent did not enumerate.

### LIFECYCLE_SESSION_ID export order bug (pre-existing)

`runner.sh:708` exports `LIFECYCLE_SESSION_ID` only inside the batch_runner branch — AFTER the orchestrator spawn at `runner.sh:643`. On round 1, the orchestrator runs without the variable. The existing Step 4a `log_event` call tags events with `session_id: "manual"` (events.py:191 fallback) on round 1 and gets the correct value on round 2+. This is a silent data-quality bug that any new LLM-side instrumentation inherits. Fix is a two-line move of the export above the orchestrator spawn.

### Files that will change

- `claude/overnight/runner.sh` — `fill_prompt()` at 379-394 (if deliverable #1 ships); `export LIFECYCLE_SESSION_ID` move to ~567 (data-quality prereq); new `log_event` call if emitting a runner-side event
- `claude/overnight/prompts/orchestrator-round.md` — Steps 3a-3e at 232-278 (delimiters or excision); Step 4a textual reference at 296; potentially a new `log_event` call in Step 3b for instrumentation
- `claude/overnight/events.py` — new EVENT_TYPES constants and tuple membership
- (Optional) `claude/overnight/round_filter.py` — new helper if A7 (shared filter) chosen
- `tests/` — new test coverage (see Test Gap below)

### Test coverage gap

No existing test exercises `fill_prompt()` with the real 320-line template. `tests/test_runner_signal.py:85-87` uses a stub template `"Round {round_number} prompt for {state_path}\n"`. `tests/test_runner_resume.py` only tests the extracted `count_pending()` helper. The tradeoffs agent's "80-120 lines including tests" estimate is optimistic — a minimal useful test suite needs state fixtures, filter-contract assertions, structural checks on excised prompt, and golden-file comparisons. Closer to 200-300 lines of test code for a full deliverable-#1 implementation.

## Requirements & Constraints

### Pipeline-events.log — framed as batch_runner output

`requirements/pipeline.md:126`: "`lifecycle/pipeline-events.log` provides an append-only JSONL record of all dispatch and merge events."

Referenced at `pipeline.md:17, 141` as session-orchestration output (batch_runner.py). No explicit mention of LLM-orchestrator-driven writes. No explicit prohibition either. Event schema is informal — "all dispatch and merge events" is the only characterization.

### Per-feature events.log ownership — explicit

`requirements/pipeline.md:62`: **"batch_runner owns all `events.log` writes; review agent writes only `review.md`."**

This is the strongest ownership statement in requirements and rules out LLM-side writes to per-feature `lifecycle/{feature}/events.log`. It does not cover `overnight-events.log` (the session-level log), which is where the Step 4a LLM-side write lives.

### Context efficiency framing — narrow

`requirements/project.md:33` frames "context efficiency" exclusively in terms of tool output filtering via preprocessing hooks. Does not explicitly endorse or prohibit orchestrator prompt content trimming. No requirement rules out conditional prompt inclusion, template variants, or block excision. No requirement on orchestrator prompt size or input-token budgets.

### State-ordering constraint — not codified in requirements

The Step 0 → Step 3 ordering constraint is documented only in `research/overnight-plan-building/research.md:85,156,165,181`. No requirements file mentions it. It's informally architectural, not a codified invariant.

### Orchestrator rationale convention

`requirements/pipeline.md:127`: "When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field." Not directly relevant, but establishes a precedent that orchestrator-driven events.log entries are a sanctioned pattern even though batch_runner owns the writes.

### Multi-agent / Agent-tool constraints

`requirements/multi-agent.md:48, 72` — parallelism decisions live in the orchestrator prompt; agents do not spawn peer agents. No explicit requirement about observability of Agent-tool-spawned subagents.

## Web Research

### Conditional prompt inclusion patterns

Jinja2 `{% if %}...{% endif %}` is the dominant canonical pattern: LangChain PromptTemplate (with Jinja2/Mustache/f-string formats), Microsoft Semantic Kernel's `jinja2_prompt_template`, PromptLayer blog posts, Promplate (FSM-based), Instructor docs. Mustache is the logic-less alternative. Fragment composition (separate files, thin controller concatenates) is cited as the maintainability-oriented alternative when conditionals proliferate.

Delimiter-based sed/awk excision is not documented as a pattern in any mainstream prompt-engineering source.

No published consensus that conditional blocks are a smell for prompts. The counter-argument comes from generalized feature-flag literature, not prompt-specific sources.

### Sub-dispatch observability — Claude Code first-party hooks

Claude Agent SDK documents a full hook lifecycle including:
- `PreToolUse` (with matcher regex — the `Agent`/Task tool is explicitly matchable)
- `PostToolUse` (with result)
- `SubagentStart` / `SubagentStop` (provides `agent_id`, `agent_type`, `agent_transcript_path`)

Reference implementation: `disler/claude-code-hooks-multi-agent-observability` — uses SubagentStart/SubagentStop hooks to forward real-time observability events to a server. Uses `agent_type` to differentiate. The canonical pattern for "did a sub-dispatch fire" is a harness hook, not LLM self-audit.

OpenTelemetry AI Agent Observability initiative (langgraph, crewai, autogen, Claude Code) converges on harness-side instrumentation. LangSmith and Langfuse render execution trees from harness-side traces.

### LLM self-audit reliability — evidence weighs against

- **"The Stability Trap"** (arXiv 2601.11783) documents "consistent binary verdict based on inconsistent accompanying justifications" — LLMs' yes/no about whether they did something can be stable even when the reasoning is unstable.
- **ReliabilityBench** (arXiv 2601.06112) measures `pass^k` consistency and shows LLM agents drift across runs.
- **LLMAuditor** (arXiv 2402.09346) positions itself as an external audit framework, implicitly conceding LLMs can't reliably self-audit.
- Claude Code's own docs and every mainstream framework (LangSmith, Langfuse, OpenTelemetry AI) route audit through the harness, not the model.

**There is no published evidence supporting LLM self-audit as reliable. There is published evidence against.**

### Prompt trimming impact

No rigorous behavior-change benchmarks. Token cost math is proportional (~14% of system prompt at 46 of ~320 lines). Claude Agent SDK docs note "even unused tools get tokenized and billed" — closest first-party endorsement of trimming unused content, but that's about tool *definitions*, not prompt instructions.

## Tradeoffs & Alternatives

### Deliverable #1 (conditional prompt inclusion) — alternative designs

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **A1**: Substitution variable | Add `{plan_gen_block}` token; substitute block text or empty string | Reuses existing `str.replace()` pattern | Requires a sibling file; dangling Step 4a reference |
| **A2**: Split template files | Factor Steps 3a-3e into `orchestrator-round-plan-gen.md`; concatenate conditionally | Each fragment is self-contained | Brittle positional concatenation; two files to keep in sync |
| **A3**: Delimiter excision | `<!-- PLAN_GEN_START --> ... <!-- PLAN_GEN_END -->` in `fill_prompt()` strips conditionally | Single source file; inline visibility | Regex strip in `fill_prompt`; silent typo failure |
| **A4**: LLM-side early exit | Keep block; instruct LLM to skip Steps 3a-3e when no feature needs plan-gen | Zero runner.sh changes; runs post-Step 0 | **Does not save input tokens** (the only real benefit) |
| **A5**: Do nothing | Ship only deliverable #2 | Zero risk | User asked for both |
| **A6**: Check after Step 0 but pre-orchestrator | Infeasible — Step 0 is inside the orchestrator invocation | — | Would need two orchestrator sessions or Python-side Step 0 |
| **A7**: Shared filter helper | Factor round filter into `round_filter.py`, used by runner.sh AND the prompt | Eliminates drift | New module; filter semantics must be exact |
| **A1+partial**: Preserve 3a and 3e, excise 3b-3d only | Keeps the disk-existence safety net for all promotion paths | Addresses adversarial review failure mode #1 | Harder to implement — 3a-3e are contiguous text; needs careful splitting |

### Deliverable #2 (instrumentation) — alternative targets

| Approach | Description | Reliability | Verdict |
|---|---|---|---|
| **B1**: Transcript parsing | Capture orchestrator stdout, parse for marker line, log Python-side | Low — no capture exists today; marker still LLM-emitted | Reject |
| **B2**: LLM-side `log_event` → `overnight-events.log` | Instruct orchestrator to call `log_event()` inline via `orchestrator_io` | Medium (one sanctioned precedent; LLM self-audit concerns) | **Candidate** |
| **B3**: Per-feature `events.log` (LLM-side) | Append to `lifecycle/{feature}/events.log` | Medium, but violates `batch_runner owns all events.log writes` rule | Reject (requirements violation) |
| **B4**: New dedicated log file | `lifecycle/plan-gen-events.log` | Same as LLM-side option picked | Reject (disproportionate) |
| **B5**: Tag state mutation | Add field to `OvernightFeatureStatus` | Low — state is not an audit trail | Reject |
| **B6**: Claude Code hook (`PreToolUse` matcher: "Agent") | Harness-side hook fires deterministically | **High** — runs outside model control | See granularity problem below |

### The harness-hook alternative (B6) — granularity problem

Initially attractive because it eliminates LLM self-audit reliability concerns entirely. But:

1. **Granularity**: Hook matchers are tool-name-level, not prompt-content-level. A `matcher: "Agent"` hook fires for every Agent dispatch — plan-gen, critical-review, skill-dispatched research, future orchestrator sub-work. No way to distinguish plan-gen specifically without parsing the prompt text passed to the sub-agent.
2. **Scope**: `claude/settings.json` is the repo's committed template. A global PreToolUse Agent hook would fire on every Claude Code session that uses sub-agents, not just the overnight runner. The overnight runner has no dedicated settings file — it inherits from `claude/settings.json` plus whatever's in `settings.local.json`.
3. **`--dangerously-skip-permissions` compatibility**: No empirical evidence in this repo that PreToolUse hooks with `matcher: "Agent"` have been tested under `-p` mode. The `Notification` hook with `matcher: "permission_prompt"` is explicitly bypassed by `-p`. Other hook behavior under `-p` is undocumented here.
4. **Zero precedent in repo**: This repo's settings.json uses `matcher: "Bash"` only. Adding a first-of-its-kind Agent-matcher hook would need a spike to validate.

**Verdict**: Hooks approach does not cleanly obviate deliverable #2. It trades LLM-reliability risk for granularity+scope+sandbox unknowns. For today's orchestrator (Step 3b is the only Agent dispatch in the prompt), the hook would work 1:1, but any future refactor that adds another Agent dispatch silently breaks the instrumentation. Not worth pursuing for this ticket.

## Adversarial Review

An adversarial agent challenged the tradeoffs synthesis. Key findings:

### The state-ordering verdict was incomplete

The tradeoffs agent claimed Step 0 → Step 3 ordering is a non-issue because only workers write escalations and workers only run post-plan-existence. True for one path — but **three other paths can promote features to `pending` without validating `plan_path`**:

- `interrupt.py:130-145 handle_interrupted_features()` — resets `running → pending` on every round, no plan_path check, runs BEFORE the main loop at runner.sh:570. If a worker's worktree was pruned (runner.sh:580 `git worktree prune`), the plan_path may now be orphaned.
- `orchestrator-round.md:162-173` round filter — `status == "paused"` features are unconditionally re-included. A paused feature's plan_path could reference a file since deleted between rounds.
- `orchestrator-round.md:131` escalation resolution — even in the "safe" path, `plan_path` that existed at dispatch T0 may not exist at T1 between rounds (worktree cleanup).

Steps 3a and 3e are the **last-chance disk existence check** for all four paths. Removing them unconditionally removes the safety net.

### Step 4a textual reference dangles

`orchestrator-round.md:296` says "same mechanism as Step 3e for missing plans". If Steps 3a-3e are excised, this reference dangles on the first release. The A1 design as proposed by the tradeoffs agent is broken on day one unless Step 4a is rewritten as a prerequisite.

### LIFECYCLE_SESSION_ID export order bug (existing)

`runner.sh:708` exports `LIFECYCLE_SESSION_ID` only inside the batch_runner branch — AFTER the orchestrator spawn at 643. Round 1 log_event calls tag events `session_id: "manual"`. Step 4a already has this latent bug. Any new LLM-side instrumentation inherits it. Fix: move the export above the orchestrator spawn (~line 567, after `SESSION_ID` is read).

### `fill_prompt()` fail-closed semantics

Under `set -e`, a helper exception in `fill_prompt()` kills the runner entirely. Needs explicit fail-open policy (include the full block, log a `plan_gen_filter_error` warning event, continue).

### `plan_gen_skipped` emission is noise, not signal

Emitting `plan_gen_skipped` every round in the steady state (when the block is excised) inverts the signal-to-noise ratio — the opposite of the trimming goal. Drop it. **Absence of `plan_gen_dispatched` IS the "skipped" signal.**

### Round filter drift risk (A7)

Even with a shared helper, the orchestrator prompt pseudocode and the Python helper must be kept *semantically identical* including edge cases like the `(f.get('round_assigned') or 0)` null guard. A contract test is required to enforce this.

### Test coverage is non-trivial

The tradeoffs agent's "80-120 lines including tests" is optimistic. A minimum-viable test suite for deliverable #1 needs: state fixture builder, filter-contract test (both callers produce the same filter on diverse states), structural test that the excised prompt has no dangling Step 3 references, golden-file comparison of `fill_prompt()` outputs, round-1 vs round-2+ attribution test. Closer to 200-300 lines of test code.

### Instrumentation fields should be actionable

The tradeoffs agent's proposed schema `{features: [], count}` tells you THAT plan-gen fired but not WHY. The adversarial review argues for:
- `features: [slugs]`
- `reason: "missing_plan_path"` (future-proof for other reasons)
- `spec_paths: {slug: path}` and `plan_paths: {slug: expected_path}` — so the post-hoc audit can see what the orchestrator expected vs. what was missing
- Drop timing, drop model, drop exit reason (those belong in a completion event we're also dropping)

### Adversarial verdict on each deliverable

**Deliverable #1 (trim): retire.** The research epic explicitly calls the overhead "negligible cost" (DR-1 line 184). The trimming saves ~700 tokens / ~$0.02 per round at Opus rates — pennies per session. The behavior-change risk (Step 4a dangling reference, first-time-execution path, filter drift, worktree edge cases) is real and unmeasured. The prompt file also functions as human-readable documentation of the overnight flow — splitting it reduces readability for humans in exchange for marginal model savings. Production has had zero plan-gen invocations; optimizing the steady-state path is premature.

**Deliverable #2 (instrument): ship reduced.** One event (`plan_gen_dispatched`) via LLM-side `log_event` to `overnight-events.log`. Drop `plan_gen_completed` (inferrable from absence of `feature_failed` with `stage: plan_gen`) and `plan_gen_skipped` (noise). Prerequisites: fix the `LIFECYCLE_SESSION_ID` export order; add an events.py constant-validation test that imports the prompt, scans for `log_event(` calls, and asserts each event name is in EVENT_TYPES.

## Recommended Approach (post-adversarial synthesis)

**Option A (minimal, recommended by adversarial review):**
1. **Skip deliverable #1 entirely.** Retire from ticket; the research epic does not actually endorse it and the behavior-change risks outweigh the penny-per-session savings.
2. **Ship a reduced deliverable #2**: one `plan_gen_dispatched` event via LLM-side `log_event` in Step 3b, with actionable fields.
3. **Ship two prerequisite fixes**: (a) move `export LIFECYCLE_SESSION_ID` above the orchestrator spawn; (b) add an events.py constant-validation test.
4. Estimated scope: ~50 lines across 3-4 files.

**Option B (full ticket, with adversarial mitigations applied):**
1. Ship deliverable #1 as **A1+partial** — keep Steps 3a and 3e always in the prompt, conditionally excise only Steps 3b-3d (the actual plan-generation work). Preserves the disk-existence safety net for all four state-promotion paths.
2. Pre-rewrite Step 4a to remove the "same mechanism as Step 3e" textual reference.
3. Factor the round filter into a shared helper (A7) with a contract test.
4. Add fail-open semantics to `fill_prompt()` helper with a `plan_gen_filter_error` observability event.
5. Ship deliverable #2 as in Option A (one event, actionable fields).
6. Ship both prerequisite fixes (LIFECYCLE_SESSION_ID export, events.py constant validation test).
7. Add tests: state fixtures, filter contract, structural excision, golden-file comparison.
8. Estimated scope: ~200-300 lines.

**Option C (deliverable #2 only, deferred #1):**
1. Ship Option A's deliverable #2 now (and its prerequisites).
2. Gather baseline data over the next few overnight sessions via the instrumentation.
3. If plan-gen never fires (as expected), revisit deliverable #1 in a future ticket with empirical support for retiring Steps 3a-3e entirely rather than conditionally. If it fires unexpectedly, the data tells us not to trim.

The research recommendation is **Option C** — it delivers the auditable signal the ticket wants, defers the risky trim until there's data, and retires the prerequisite bug. Option A is also defensible if the user accepts closing deliverable #1 outright. Option B is viable but higher risk-to-benefit for the marginal savings.

## Open Questions

These need Spec-phase resolution with the user. Each is a consequential decision — not a gap the research can fill.

- **Q1 (scope): Ship deliverable #1 at all?** Research finds the overhead is pennies per session, the epic research does not endorse trimming, and the behavior-change risks (dangling references, worktree edge cases, test gap) are real. Options: (a) retire deliverable #1 — Option A; (b) defer deliverable #1 until instrumentation data justifies it — Option C; (c) ship the mitigated trim — Option B.
- **Q2 (scope, conditional on Q1=yes): If shipping deliverable #1, which partitioning?** Options: (i) excise all of Steps 3a-3e; (ii) excise only 3b-3d, preserving 3a and 3e as a permanent safety net; (iii) keep everything but move the round-level check into an LLM-side early-exit at the top of Step 3 (A4 — saves turns not tokens).
- **Q3 (instrumentation schema): event schema and field set for `plan_gen_dispatched`.** The adversarial review recommends: `{features: [slugs], reason: "missing_plan_path", spec_paths: {slug: path}, plan_paths: {slug: expected_path}}`. Confirm or revise.
- **Q4 (prerequisite fix): `LIFECYCLE_SESSION_ID` export order.** This is an existing data-quality bug that is not technically part of the ticket. Ship as a prerequisite in the same PR, split into its own commit, or spin out to a separate ticket?
- **Q5 (test scope): test coverage policy for deliverable #1.** If deliverable #1 ships, does the user want: (a) minimal unit tests on the new helpers only; (b) full structural coverage including golden-file comparison of the excised prompt; (c) integration test that runs a mock overnight round? The research estimates 200-300 lines of test code for option (b).
