# Research: Measure xhigh vs high effort cost delta on representative task

> Topic: Measure cost, turn-count, and qualitative-quality delta between `high` and `xhigh` effort settings on a single synthetic lifecycle-implement-style task, verifying/adding SDK `effort` wiring in `claude/pipeline/dispatch.py` as needed, to inform the DR-3 Wave 2 (#090) adoption decision for overnight lifecycle implement defaults.
>
> Tier: complex. Criticality: high.

## Epic Reference

Scoped from the opus-4-7-harness-adaptation epic research: [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md). The epic's Open Question 2 and DR-3 Wave 2 are this ticket's direct antecedents; this research is ticket-specific and does not reproduce the epic's cross-ticket scope.

## Codebase Analysis

### SDK wiring — already in place, with one correction

- `claude/pipeline/dispatch.py:438` already constructs `ClaudeAgentOptions(..., effort=effort, ...)`. The `effort` string flows through from `dispatch_task()`'s `effort_override` parameter (line 342) via `EFFORT_MAP` resolution at line 395.
- `EFFORT_MAP` (dispatch.py:126–130) hard-codes `{"trivial":"low", "simple":"medium", "complex":"high"}`. `xhigh` is not in the map — but the `effort_override` parameter bypasses it.
- **Correction to Agent 1 finding**: `max_tokens` is NOT a valid `ClaudeAgentOptions` field on the installed SDK. `ClaudeAgentOptions(max_tokens=64000)` raises `TypeError: got an unexpected keyword argument 'max_tokens'`. The CLI binary `claude` v2.1.114 has no `--max-tokens` flag either. There is **no path to wire `max_tokens` through the SDK/CLI subprocess transport** — `max_tokens` is a Messages-API-level concept that this harness does not expose. The spike cannot add the wiring because there is nothing to wire. If `xhigh` output exceeds the CLI's internal output budget, the failure mode is silent truncation surfacing as `stop_reason: "max_tokens"` inside an assistant message (detectable from the SDK stream).
- Verified installed SDK is `claude_agent_sdk` **v0.1.41** (not v0.1.63). At v0.1.41, `effort` is typed `Literal["low","medium","high","max"] | None` — `xhigh` is not in the Literal. Python's `@dataclass` does NOT enforce `Literal` at runtime; it is a static-type hint only. Empirically `ClaudeAgentOptions(effort="xhigh")` passes dataclass init and is forwarded as `--effort xhigh` to the CLI subprocess (`subprocess_cli.py:315-316`). CLI v2.1.114 `--help` explicitly lists `xhigh` as valid. The SDK Literal gap is a type-checker warning, not a runtime blocker.
- `dispatch_task()`'s docstring at dispatch.py:371 documents valid effort values as `"low","medium","high","max"` — xhigh is missing. If the spike touches dispatch.py, it should correct the docstring.

### Event telemetry and aggregation

- Per-dispatch `dispatch_start` and `dispatch_complete` events are written to `lifecycle/{feature}/events.log` by `claude/pipeline/dispatch.py` (lines 443–452 and 509–516 respectively). `dispatch_start` includes `effort` as a field; `dispatch_complete` includes `cost_usd`, `duration_ms`, `num_turns`.
- `claude/pipeline/metrics.py::pair_dispatch_events()` pairs start/complete events per feature and yields per-dispatch tuples including outcome, cost, and turn count.
- **`compute_model_tier_dispatch_aggregates()` at metrics.py:442 buckets by `"<model>,<tier>"` — not by effort.** Two runs at the same (model, tier) with different effort levels collide into the same bucket. The aggregator reports `n_completes=2, mean=(a+b)/2` with effort information erased. This is #087's current design (effort was not a scope for #087).
- At n<30, `pair_dispatch_events()` suppresses p95 fields (returns `None`) and sets `max_turns_observed`. At n=1, `mean == median == max`, `p95 = None`. Nothing crashes; the output is mean-of-one.

### Dispatch entry points

- `dispatch_task()` (dispatch.py:332–345) already accepts `effort_override` and is the right production-realistic entry point for the spike harness.
- `retry_task()` in `claude/pipeline/retry.py:165–252` does NOT accept `effort_override`. Production adoption (#090) may need this parameter added; spike measurement does not.
- `ResultMessage.total_cost_usd` and `ResultMessage.num_turns` are the SDK's ground-truth per-dispatch figures. `DispatchResult.cost_usd` propagates the former. `num_turns` reaches only `events.log` (via `log_event` call at dispatch.py:509–516), not the `DispatchResult`.

### Prompt template and synthetic task shape

- `claude/pipeline/prompts/implement.md` is the lifecycle-implement system prompt template, rendered by `claude/overnight/feature_executor.py:560–569` with variables: `feature`, `task_number`, `task_description`, `plan_task` (Files / Depends on / Complexity), `spec_path`, `worktree_path`, `learnings`, `integration_worktree_path`.
- The template tells the agent to read the spec "on demand" — meaning real implement tasks have variable-size spec reads as part of the turn loop. A synthetic task that bundles its spec as inline context misses this dynamic.

### Files that would change for the spike measurement (no defaults flipped)

- New: `lifecycle/archive/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/synthetic-task/` — a pinned synthetic task (scratch worktree state + prompt + expected acceptance criteria).
- New: `lifecycle/archive/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/harness.py` — thin Python script that calls `dispatch_task()` twice with different `effort_override` values, writes local events.log, prints summary.
- New: `lifecycle/archive/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/report.md` — the deliverable.
- Touched (docstring only, if time): `claude/pipeline/dispatch.py:371` — add `xhigh` to documented effort values.

## Web Research

### SDK and CLI reality

- Released `claude-agent-sdk` v0.1.63 defines `effort: Literal["low","medium","high","max"] | None = None` — no `xhigh` in the type. Our installed version is older (v0.1.41) with the same Literal. Python `@dataclass` does not enforce `Literal`, so `effort="xhigh"` is accepted at runtime and shelled to the CLI. This is working today.
- Claude Code CLI v2.1.x `--help` exposes `low | medium | high | xhigh | max` — five effort levels. `max` is distinct from `xhigh`. The SDK missing `xhigh` in its Literal is an SDK type-hint bug, not a wire-level limitation.

### Pricing and cost mechanics

- Opus 4.7 is flat `$5 / MTok input, $25 / MTok output`, 5m cache write $6.25 / 1h cache write $10, cache read $0.50 — **no effort-level pricing tier**. Source: [pricing](https://platform.claude.com/docs/en/about-claude/pricing).
- Per-token rates are identical across effort levels; cost delta is entirely token-consumption driven. Migration guide: *"Claude Opus 4.7 should have strong out-of-the-box performance on existing Claude Opus 4.6 prompts and evals at the same `$5 / $25` per MTok pricing."*
- **New tokenizer in 4.7** may produce 1.0–1.35× more tokens for the same text vs 4.6. This is an independent cost axis orthogonal to effort, and it cancels within-experiment (both arms use 4.7) but does NOT cancel for a reader comparing measured costs against a 4.6 mental baseline.

### `max_tokens` constraint — soft, and not exposed here

- Per Anthropic: *"When running Claude Opus 4.7 at `xhigh` or `max` effort, set a large `max_tokens` so the model has room to think and act across subagents and tool calls. Starting at 64k tokens and tuning from there is a reasonable default."* ([Effort docs](https://platform.claude.com/docs/en/build-with-claude/effort)).
- **This is a soft recommendation, not a hard dispatch-time validation.** Behavior when `max_tokens` is insufficient: mid-stream truncation with `stop_reason: "max_tokens"`, no error.
- Per adaptive thinking docs: *"At `high` and `max` effort levels, Claude may think more extensively and can be more likely to exhaust the `max_tokens` budget. If you observe `stop_reason: "max_tokens"` in responses, consider increasing `max_tokens` to give the model more room, or lowering the effort level."*
- **We cannot configure `max_tokens` through this harness** (not an `OptionsOptions` field, not a CLI flag). The spike must detect truncation via `stop_reason` monitoring rather than prevent it by config.

### Cost/turn telemetry

- `ResultMessage` carries: `subtype`, `duration_ms`, `duration_api_ms`, `is_error`, `num_turns`, `session_id`, `stop_reason`, `total_cost_usd`, `usage: {input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, `model_usage`, `permission_denials`, `errors`.
- `total_cost_usd` is the pre-computed dispatch total from the CLI — **no manual summing required**.
- Per-assistant-turn `usage` is preserved on each `AssistantMessage` (v0.1.49 changelog).

### Prompt caching interaction with effort

- Anthropic's [prompt caching doc](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) lists cache invalidators (tool definitions, web search toggle, citations, speed setting, tool choice, images, thinking params) but does NOT list `effort` as an invalidator. Inferred: flipping `high` ↔ `xhigh` between consecutive calls should preserve system-prompt and tool-definition caching. Not explicitly guaranteed — worth empirically confirming via `cache_read_input_tokens`.

### Benchmark data — no official high-vs-xhigh comparison

- Anthropic has NOT published a `high` vs `xhigh` benchmark delta on Opus 4.7. The Opus 4.7 Claude Code blog post includes an "Agentic coding performance by effort" chart without printed numbers per level. Vellum and artificialanalysis.ai reviews run only at `max` effort. **The spike's measurement is genuinely informative, not duplicative.**
- Unverified single-source community estimates ([apiyi.com](https://help.apiyi.com/en/claude-opus-4-7-xhigh-effort-mode-explained-en.html)): xhigh ≈ 1.5× tokens of high; 5–6% quality delta; xhigh 50–80% slower than high. Treat as noisy priors, not load-bearing.

### Key sources

- [Effort docs](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Migration guide](https://platform.claude.com/docs/en/about-claude/models/migration-guide)
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python)
- [claude-agent-sdk-python v0.1.63 types.py](https://raw.githubusercontent.com/anthropics/claude-agent-sdk-python/v0.1.63/src/claude_agent_sdk/types.py)

## Requirements & Constraints

### Dispatch configuration (from `requirements/multi-agent.md`, `requirements/pipeline.md`, and `claude/pipeline/dispatch.py`)

- Per-dispatch budget caps are **tier-based, not effort-based**: `trivial→$5, simple→$25, complex→$50` (multi-agent.md line 55; `TIER_CONFIG` at dispatch.py:118–122).
- Per-dispatch turn caps are also tier-based: 15 / 20 / 30.
- Effort levels are NOT mentioned in `requirements/`. Effort and tier are orthogonal concepts — tier selects model/turn/budget; effort modulates per-turn reasoning depth within the selected model.
- Budget exhaustion → session pauses without crashing (`pipeline.md` §Session Orchestration line 25, `multi-agent.md` §Agent Spawning line 21).

### Quality attributes that xhigh adoption must preserve

- **Graceful partial failure** (`project.md` §QA line 29): individual task failures don't block the rest. xhigh tokens-consumed increases must not push more tasks past the $50 cap.
- **Fail-forward model** (`pipeline.md` line 37): one feature's failure doesn't block others.
- **Repair loop is cost-bounded**: 2 test-failure attempts, single Sonnet→Opus escalation for merge conflicts. xhigh-at-doubled-per-repair-cost tightens this envelope proportionally (`pipeline.md` lines 132–133).

### Spike scope boundaries (from backlog/089 and 090)

- In scope for #089: confirm SDK wiring (done — already wired), measure cost/turn delta on one synthetic task, report qualitative quality delta. Measurement only.
- Out of scope for #089: full benchmark suite, changing `EFFORT_MAP`, flipping production defaults, `max_tokens` adoption logic (belongs to #090 if applicable — but per Web Research, `max_tokens` is not exposed in this harness anyway).
- #090 (adoption) is blocked by #089 and requires a rationale citing this measurement.

### No documented spike methodology

Requirements files describe production behavior, not experimental methodology. The spike is exploratory; a/b comparison conventions are ad-hoc.

## Tradeoffs & Alternatives

Scoped by user decisions (synthetic task; add wiring if missing — though per Codebase + Adversarial, there is nothing to wire; n=1 per effort). Within those:

### Axis 1 — Synthetic task shape

- **A — Multi-file edit with test-runner step** (e.g., "add a field to a dataclass, update 3 callsites, run pytest, fix failures"). Highest representativeness of the implement phase #090 is scoped to. **Adversarial caveat**: a stochastic test runner at n=1 can add 5–15 turns of noise that swamps effort-level signal. If A is chosen, pin to a **deterministic, fast test step** (pure-function unit test, no external fixtures) OR drop the test step and verify by diff inspection.
- **B** — Single-file refactor, no test run. Cheap/clean signal-to-cost but doesn't exercise iteration depth, tool-loop, or self-verification where xhigh's benefit is hypothesized.
- **C** — Bug-fix task with failing test. Narrower than implement; n=1 first-attempt luck dominates.
- **D** — Research-only task. Wrong phase.

**Recommended**: **A with deterministic test step** OR **A with inspection-only verification**. Pin task state, prompt, and acceptance criteria in `lifecycle/{slug}/synthetic-task/` so the exact starting conditions are reproducible. Decide test-step shape in Spec.

### Axis 2 — Measurement harness

- **X** — Full overnight-runner invocation. Maximum realism but many confounders (worktree IO, merge, retry).
- **Y** — Standalone script using `claude_agent_sdk.query()` directly. Minimum confounding but bypasses project SDK config (env scrubbing, settings injection, `_worktree_settings`).
- **Z** — Thin wrapper around existing `dispatch_task()` with different `effort_override` values, pointed at a scratch worktree.

**Recommended**: **Z**, with "scratch worktree" clarified as: a throwaway git branch of the real repo with `git reset` between arms to ensure the second arm doesn't see the first arm's commits. Rationale: matches the production decision surface (#090 will flip defaults in this code path), reuses real env/settings handling, avoids orchestrator noise.

### Axis 3 — Cost/turn extraction

- **P** — #087 aggregator over events.log. **Broken as-applied**: the aggregator buckets by (model, tier), not by effort. Both runs land in the same `opus,complex` bucket with effort info erased.
- **Q** — SDK direct via `ResultMessage.total_cost_usd` and `num_turns` / `DispatchResult.cost_usd`.
- **R** — Both with cross-check. Not viable per (P) without extending the aggregator to 3-key buckets (scope creep into #087).

**Recommended**: **Q (SDK direct only).** The SDK fields are ground-truth and per-dispatch. Do NOT stretch to R — fixing the aggregator to bucket by effort is #087 scope, not #089.

### Axis 4 — Report format / decision framing

- **F1** — Raw numbers only.
- **F2** — Derived ratios + recommended action.
- **F3** — Structured decision matrix (cost-delta band × quality-delta band → action), bands pre-committed before data.

**Recommended**: **F3 with an explicit "inconclusive" region.** Bands must include a "delta < noise-floor → gather more data" outcome. The noise floor must sum: prompt-cache ordering effect (measurable via `cache_read_input_tokens`), task-path nondeterminism (unknown at n=1, conservative assumption ±20% turn count), and tokenizer jitter within Opus 4.7 (small). Pre-commit the matrix in the spec before running anything.

### Additional notes

- `EFFORT_MAP` flip-scope for #090 is (i) global, (ii) criticality-aware 2D matrix, (iii) per-phase override. #090 says "lifecycle implement phase" — argues against (i). The spike measurement on a single (complex, high, opus) datapoint says nothing about other matrix cells; the report MUST scope its recommendation to `opus + complex + high` and explicitly disclaim generalization.

## Adversarial Review

### Assumptions that do not hold

- **"We need to wire `max_tokens`."** `ClaudeAgentOptions(max_tokens=64000)` raises `TypeError`; CLI v2.1.114 has no `--max-tokens` flag. The "wiring gap" premise is false. The spike has nothing to wire; truncation (if it occurs) surfaces only as `stop_reason: "max_tokens"` in the SDK message stream. Mitigation: **capture per-message `stop_reason` and fail the spike (don't report a number) if either arm truncates.**
- **"The SDK Literal gap blocks us."** At runtime, `@dataclass` does not enforce `Literal`. `effort="xhigh"` passes through to the CLI. The Literal gap is a static-type-check warning, nothing more.
- **"Cross-check R de-risks #087."** The aggregator doesn't distinguish effort-level buckets; extending it is #087 scope. Drop R in favor of Q.

### Failure modes and edge cases at n=1

- **Prompt-cache contamination across arms.** Running `high` then `xhigh` against the same repo/spec warms cache breakpoints; the second run's `cache_read_input_tokens` is high and its `total_cost_usd` is depressed (cache reads ~10% of input price). Run-order reversal flips the effect. At n=1, randomization is a coin flip, not a mitigation. **Only defensible response**: log `cache_read_input_tokens` and `cache_creation_input_tokens` per arm; report both **raw cost** and **uncached-equivalent cost** (recompute as if cache reads priced at full input rate) as bounding numbers.
- **Test-runner stochasticity.** A single flake in a pytest step can add 5–15 turns of turn-count variance — likely exceeding the effort-level signal. Either pick a task whose test step is fully deterministic or drop the test step.
- **F3 at n=1 is honesty theater unless bands include an explicit noise floor.** Pre-committing bands before data prevents post-hoc adjustment but doesn't cure n=1; a point estimate lands in whatever band based on noise as much as signal. Bands MUST include an "inconclusive — gather more data" region sized to the noise floor.
- **Single-cell generalization.** A (complex, high, opus) datapoint says nothing about whether xhigh should flip for (simple, medium, sonnet), (trivial, high, haiku), etc. xhigh's marginal value likely scales non-linearly with model capability: a small model at xhigh may burn turns on reasoning it can't complete. The report MUST scope its recommendation narrowly.
- **Synthetic vs. real distribution bias vectors**:
  - Tool-loop depth distribution — real tasks are bimodal; synthetic easy-path tasks live in the low mode and understate xhigh's benefit on thrashy tasks.
  - Read-on-demand spec pattern — real tasks re-read the spec through the turn loop; synthetic tasks with inline spec miss this dynamic.
  - Worktree size — `Glob`/`Grep` token consumption scales with repo size; a fresh scratch playground under-counts.
  - Integration-conflict escalation — real retry path escalates models on merge conflicts; synthetic tasks that don't hit conflicts don't measure xhigh's conflict-resolution effect.

### Qualitative quality judgment corruption

- **Anchoring** from seeing cost delta first; **confirmation bias** from ticket-framing priming the rater to find xhigh worthwhile; **output-length conflation** (xhigh tends to produce longer messages; raters systematically conflate length with quality); **single rater** — no inter-rater reliability; **commit-diff bias** — the final diff loses the trajectory information where xhigh's benefit (fewer dead-ends) actually manifests.

Mitigations the spike should commit to:
- Blind the rater by stripping `effort` / `cost_usd` metadata from outputs before review.
- Pre-register a rubric: correctness, completeness, code style, test coverage of acceptance criteria — separate per-axis scores.
- Rate on the **full transcript** (tool calls, message sequence, dead-ends), not only the diff.
- Report: rater identity/role, time-to-review, known prior priors. Caveat single-rater loudly.

### Anti-patterns to avoid

- **Scope creep**: R (de-risk aggregator), unrelated dispatch.py refactors, any production default change. All belong to other tickets.
- **Docstring drift**: dispatch.py:371's effort-value list doesn't include `xhigh`. If the spike touches dispatch.py at all, fix the docstring in the same commit — 1 line, not scope creep.
- **"Scratch worktree" fuzziness**: must specify whether isolation is intended (separate checkout) or non-committing (git-reset between arms). Write it down in Spec.

### Recommended mitigations (ranked)

1. Drop the `max_tokens` wiring premise entirely — nothing to wire.
2. Update `dispatch_task()` docstring to list `xhigh` as valid (1-line change, same commit as spike harness).
3. Capture per-message `stop_reason`; fail the spike (no number reported) if either arm truncates.
4. Log `cache_read_input_tokens` + `cache_creation_input_tokens` per arm; report raw cost AND uncached-equivalent cost.
5. Use SDK direct (Q) not aggregator cross-check (R); stay within #089 scope.
6. Scope recommendation explicitly to `opus + complex + high`; disclaim other matrix cells.
7. Pre-commit F3 bands with an "inconclusive — gather more data" region sized to the noise floor.
8. Blind the qualitative rater and pre-register the rubric; rate on full transcript.
9. Pin the task to a deterministic test step or no test step.
10. Include a "why this doesn't generalize" section covering n=1, single task, single cell, cache-order, and 4.6→4.7 tokenizer shift as a separate cost axis.

## Open Questions

- **Task concreteness** — The synthetic-task shape is recommended (A with deterministic test or inspection-only) but not yet specified. The exact prompt, starting worktree state, and acceptance criteria must be pinned in Spec. *Deferred: will be resolved in Spec by asking the user.*
- **Rater and rubric** — The qualitative-quality judgment needs a named rater, a pre-registered per-axis rubric, and a blinding procedure. *Deferred: will be resolved in Spec.*
- **Noise-floor commitment for F3 bands** — The "inconclusive" band's size depends on a pre-committed noise floor (cache-order swing + task-path nondeterminism + tokenizer jitter). The concrete numeric threshold must be fixed in Spec before running either arm. *Deferred: will be resolved in Spec.*
- **stop_reason truncation handling** — If either arm stops with `stop_reason: "max_tokens"`, does the spike abort and report "no signal available"? The current recommendation is yes; confirm in Spec. *Deferred: will be resolved in Spec.*
