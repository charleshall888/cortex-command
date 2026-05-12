# Research: build-shared-synthesizer-for-critical-tier-dual-plan-flow-interactive-overnight

Implementation-level research for ticket #160. The architecture-level decisions (DR-1 through DR-7) are resolved in `research/competing-plan-synthesis/research.md`; this artifact picks up at the implementation layer.

## Codebase Analysis

### Files that will change or be created

**New files (location TBD per Open Question 1):**
- `cortex_command/{pipeline,lifecycle,overnight}/plan_synthesizer.py` — Python helper (location debated below)
- `cortex_command/overnight/prompts/plan-synthesizer.md` — packaged prompt fragment, loaded via `importlib.resources.files()` mirroring `pipeline/conflict.py:288-292`
- `cortex_command/{pipeline,lifecycle,overnight}/tests/test_plan_synthesizer.py` — unit tests

**Edits:**
- `plugins/cortex-interactive/skills/lifecycle/references/plan.md` §1b lines 21-119 — replace user-pick with synthesizer invocation; preserve user-pick as fallback when synthesizer defers (subject to OQ-2 scope decision)
- `cortex_command/overnight/prompts/orchestrator-round.md` Step 3b lines 201-273 — add criticality branch dispatching 2-3 plan-gen sub-agents writing `plan-variant-*.md` files; orchestrator turn ends; `batch_runner.py` runs synthesizer between turns (subject to OQ-3 call-site decision)
- `cortex_command/overnight/events.py` — add event constants (e.g., `PLAN_SYNTHESIS_DISPATCHED`, `PLAN_SYNTHESIS_ESCALATED`, `PLAN_SYNTHESIS_DEFERRED`) if Sonnet→Opus escalation ladder ships
- `requirements/pipeline.md` §87-95 — extend deferral-trigger list to include orchestrator-side synthesizer (subject to OQ-7 requirements amendment)

### Skill→Python invocation precedent

There is **no precedent for a skill directly invoking a Python helper as a function call**. The two existing patterns are:

1. **Skill dispatches sub-agent via Task tool** — most synthesis-like work in cortex (e.g., `/critical-review` Step 2d Opus synthesizer at `plugins/cortex-interactive/skills/critical-review/SKILL.md:184-186`).
2. **Skill invokes `python3 -m cortex_command.<module>` from a bash block** — precedent in `plugins/cortex-interactive/skills/lifecycle/references/implement.md:92,126` calling `daytime_pipeline` and `daytime_result_reader` (per `requirements/observability.md:144` audit).

The §1b call site can use either. The trade-offs are detailed under "Tradeoffs & Alternatives" below.

### Call-layer for synthesizer dispatch

The interactive §1b path runs in a Claude lifecycle-skill session — it already dispatches plan-gen sub-agents from skill context (`plan.md:27-28`). A synthesizer dispatch from the same skill context is permissible.

The overnight Step 3b path runs **inside the orchestrator agent's prompt-driven turn**. The orchestrator agent is constrained by `requirements/multi-agent.md:74`: *"Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents."* Whether the orchestrator itself counts as "an individual agent" for the purpose of this rule is genuinely ambiguous (see Adversarial Review #7 below).

The repair-agent precedent at `cortex_command/pipeline/conflict.py:208-528` is **not** dispatched from inside an orchestrator turn — it runs from `batch_runner.execute_feature()`, between turns, in Python orchestration code. That precedent supports a "synthesizer runs between turns from `batch_runner.py`" architecture, not a "synthesizer runs inside the orchestrator's prompt turn" architecture.

### Existing deferral system

`cortex_command/overnight/deferral.py` exposes `write_deferral(question: DeferralQuestion, deferred_dir: Path = DEFAULT_DEFERRED_DIR) → Path` (lines 151-219). The `DeferralQuestion` dataclass (lines 49-87) requires:
- `feature: str`
- `question_id: int` (auto-assigned via `next_question_id()` if 0)
- `severity: "blocking" | "non-blocking" | "informational"`
- `context: str`
- `question: str`
- `options_considered: list[str]`
- `pipeline_attempted: str`
- `default_choice: Optional[str]` (omitted for blocking)
- `created_at: str` (auto-generated)

Output: `deferred/{feature}-q{NNN}.md` written atomically. Directly callable by the synthesizer, *if* the requirements admit synthesizer-emitted deferrals as a category (OQ-7 below).

### Criticality field

Two carriers exist; the events.log copy is authoritative for lifecycle-phase decisions:

1. **Backlog frontmatter `priority`** — `cortex_command/overnight/backlog.py:39` defines `PRIORITIES = ("critical", "high", "medium", "low")`. There is **no `criticality` field** in backlog frontmatter.
2. **`lifecycle/{feature}/events.log` `lifecycle_start.criticality`** — JSON-shaped event with values `"critical"|"high"|"medium"|"low"`. Read by `plan.md:14-19` to branch into §1b. Authoritative for plan-phase decisions.

For Step 3b's criticality branch, the read is from `lifecycle/{feature}/events.log` (most-recent `lifecycle_start` or `criticality_override` event). `cortex_command/overnight/backlog.py:39` eligibility filter reads frontmatter for backlog selection; that's a separate gate.

### `plan_comparison` event v1 schema

Defined inline at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:113-115`:

```json
{"ts":"...","event":"plan_comparison","feature":"...","variants":[{"label":"...","approach":"...","task_count":N,"risk":"..."}],"selected":"Plan A|none"}
```

The event is **appended as JSONL from skill markdown bash blocks** — it is NOT in `cortex_command/overnight/events.py` constants. There is no event-versioning precedent on events.log. The closest precedent for `schema_version` is `cortex_command/overnight/ipc.py` (runner-pid contract) and `active-session.json`.

The 4 historical events (`research/competing-plan-synthesis/research.md` Q7) are unversioned.

### `/critical-review` transferable scaffolding

From `plugins/cortex-interactive/skills/critical-review/SKILL.md`:
- **JSON envelope schema** (lines 119-134): forces classification before prose synthesis
- **Envelope extraction with malformed-envelope handling** (lines 176-182): LAST-occurrence anchor `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)`; on extraction failure, untagged prose passes through to `## Concerns` (not A-class)
- **Fresh-Opus synthesizer** (lines 184-186): synthesizer must not be a reviewer agent
- **Anchor checks** (lines 344, 348): Dismiss/Apply must point to artifact text, not memory
- **B-only refusal gate** (line 261): if A-class count is zero, no `## Objections` section

The structural shape transfers; the A/B/C taxonomy needs adaptation to a ranking-axis taxonomy (e.g., simplicity / scope coverage / risk profile / implementation velocity), and the A→B downgrade rubric needs full redesign for plan-vs-plan ranking.

### Test infrastructure

Each `cortex_command/<package>/` has its own `tests/` subdirectory. The repair-agent's unit tests live at `cortex_command/pipeline/tests/test_repair_agent.py`. Test patterns: `tempfile.TemporaryDirectory()`, `unittest.mock.patch` for SDK calls, dataclass factories. Repo-root `tests/` holds integration tests (CLI, runner, hooks, install).

The synthesizer's unit-testable components: swap-loop control flow, label blinding, identical-variants short-circuit, planted-flaw probe scaffolding, JSON envelope parsing, deferral-emission decision. All deterministic Python; SDK call is the one boundary that needs mocking.

## Web Research

### Canonical pairwise-judge prompt template

The MT-Bench `pair-v2` system prompt (lm-sys/FastChat, `fastchat/llm_judge/data/judge_prompts.jsonl`) is the reference template. Key features:

> "Please act as an impartial judge ... Your evaluation should consider factors such as the helpfulness, relevance, accuracy, depth, creativity, and level of detail of their responses. Begin your evaluation by comparing the two responses and provide a short explanation. **Avoid any position biases and ensure that the order in which the responses were presented does not influence your decision.** Do not allow the length of the responses to influence your evaluation. Do not favor certain names of the assistants. Be as objective as possible. After providing your explanation, output your final verdict by strictly following this format: `[[A]]` if assistant A is better, `[[B]]` if assistant B is better, and `[[C]]` for a tie."

Use blinded labels (`Variant 1` / `Variant 2`); structured terminal token (`[[A|B|C]]`) for cheap regex parsing; or replace with Anthropic tool-use forced JSON envelope.

### No mainstream library ships swap-and-require-agreement

- **AlpacaEval** `is_randomize_output_order=True` — shuffle-randomization across dataset; **insufficient at N=2-3**.
- **LangChain `PairwiseStringEvaluator`** `randomize_order=True` — same shuffle pattern.
- **openevals** (`langchain-ai/openevals`) — single-output evaluators only; no built-in pairwise swap.
- **JudgeLM** — implements swap as *training-time augmentation*, not inference-time technique.

Reference implementation (~20 lines, Chauzov 2025):

```python
def evaluate_with_position_swap(judge_llm, response_a, response_b, prompt):
    result_1 = judge_llm.compare(prompt, response_a, response_b)  # A first
    result_2 = judge_llm.compare(prompt, response_b, response_a)  # B first
    if result_1 == 'response_1' and result_2 == 'response_2': return 'A'
    elif result_1 == 'response_2' and result_2 == 'response_1': return 'B'
    else: return 'tie'
```

Empirically (Chauzov 2025): position-swap raised judge-human agreement from 65% → 77% on a benchmark; tie rate rose 8% → 19% — the extra ~11% are genuinely ambiguous cases worth deferring. **The swap mechanism IS the confidence threshold; no separate calibration step needed.**

**Build/buy verdict: BUILD.** ~20 lines around a judge call. Reuse MT-Bench prompt as fragment base; openevals's "Thus, the score should be:" forced-terminal-sentence trick; tool-use forcing for JSON schema.

### JSON envelope via Anthropic tool-use forcing

Recommended pattern: define an evaluator tool with `input_schema`, set `tool_choice={"type": "tool", "name": "submit_judgment"}`. Per-criterion scoring schema:

```json
{"type": "object", "properties": {
  "per_criterion": {"type": "object", "properties": {
    "feasibility": {"type": "integer", "enum": [1,2,3,4,5]},
    "completeness": {"type": "integer", "enum": [1,2,3,4,5]},
    "risk_coverage": {"type": "integer", "enum": [1,2,3,4,5]},
    "task_decomposition_quality": {"type": "integer", "enum": [1,2,3,4,5]}
  }, "required": [...]},
  "verdict": {"type": "string", "enum": ["A", "B", "C_tie"]},
  "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
  "rationale": {"type": "string", "maxLength": 1500}
}, "required": ["per_criterion", "verdict", "confidence", "rationale"]}
```

Per-criterion scores BEFORE rationale forces commitment. Anthropic Structured Outputs beta (`anthropic-beta: structured-outputs-2025-11-13`) on Sonnet 4.5 / Opus 4.1 is stronger but beta-only; tool-use forcing is the safer dependency.

### Anti-sycophancy techniques (2025-2026)

- **Anthropic harness-design article** (`https://www.anthropic.com/engineering/harness-design-long-running-apps`): *"Separating the agent doing the work from the agent judging it proves to be a strong lever"* + *"tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work."* Few-shot calibration with detailed breakdowns aligns evaluator preferences. Article extended/superseded by `effective-harnesses-for-long-running-agents` — same lessons, no retraction.
- **"Challenging the Evaluator: LLM Sycophancy Under User Rebuttal"** (arXiv:2509.16533): LLMs *"are more likely to endorse counterarguments when framed as follow-ups rather than simultaneous evaluations"* — present all variants in a single prompt (MT-Bench pattern), not sequential rebuttal.
- **SycEval** (arXiv:2502.08177): sycophancy in 58.19% of cases on Claude-Sonnet, GPT-4o, Gemini-1.5-Pro overall; mitigated by using a different model family for rebuttal.
- **Sycophancy Is Not One Thing** (arXiv:2509.21305): sycophantic agreement and praise are encoded along distinct linear directions.

**Concrete techniques to bake into the prompt:**
1. Blinded labels (`Variant 1` / `Variant 2`)
2. Fresh-agent role separation (no shared history with generators)
3. Per-criterion scoring BEFORE prose rationale
4. Few-shot examples showing "evaluator picks the worse variant when warranted"
5. Negative reminder text: *"When uncertain, assign low confidence"*
6. Explicit instruction to ignore variant order and length (MT-Bench formula)

### Defer-to-morning patterns

- **LangGraph `interrupt()`** (`docs.langchain.com/oss/python/langgraph/interrupts`): cleanest first-class defer mechanism. `interrupt(payload)` raises `GraphInterrupt`, runtime persists state, execution resumes via `Command(resume=value)`. Structurally equivalent to cortex's `deferred/{feature}-q{NNN}.md` sentinel.
- **Airflow `HITLOperator`** (already in research.md DR-6).
- **CrewAI / AutoGen** — no first-class defer.

Suggested defer-signal structure:
```json
{"kind": "plan_synthesis_defer",
 "reason": "swap_disagreement | low_per_criterion_confidence | no_condorcet_winner",
 "candidates": [...],
 "per_criterion_scores": {...},
 "swap_results": [...],
 "suggested_human_action": "review_in_morning"}
```

### Pairwise vs. listwise for N=2-3

Published evidence is unambiguous: **pairwise wins on quality, listwise wins on cost**. At N=3, listwise is 1 call (~3× faster) but position bias is harder to mitigate (3!=6 permutations). Pairwise tournament with swap-and-require-agreement at N=3: 3 head-to-head matches (A-B, A-C, B-C), each with swap = 6 calls; aggregate by Condorcet winner. If no Condorcet winner exists, defer.

For N=2: 2 calls (one swap pair). Cost is bounded.

## Requirements & Constraints

### Project-level (`requirements/project.md`)

- **Complexity must earn its place** (`project.md:19`): a reusable Python helper + shared prompt fragment is justified only if both surfaces (interactive §1b + overnight Step 3b) demonstrably need it now. The bundling decision is load-bearing for the ticket as written; if the value-prop changes (see Adversarial Review #4), this constraint may push toward overnight-only scope.
- **File-based state** (`project.md:25`): synthesizer outputs (chosen variant, deferral sentinels) must land in files, not a service.
- **Graceful partial failure** (`project.md:31`): synthesizer failures must not crash the orchestrator round; synthesizer crashes should fall through to defer-to-morning.

### Multi-agent constraints (`requirements/multi-agent.md`)

- **CRITICAL — agents do not spawn peer agents** (`multi-agent.md:74`): "Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents." Direct interaction with Step 3b architecture: synthesizer dispatch from inside orchestrator-agent turn-context is structurally ambiguous (Adversarial Review #7).
- **Orchestrator dispatch-template substitution contract** (`multi-agent.md:50`): two token tiers — session-level `{token}` pre-filled by `fill_prompt()`, per-feature `{{feature_X}}` substituted by orchestrator agent. New tokens added for synthesizer-related state must follow this convention.
- **Pre-deploy no-active-runner check** (`multi-agent.md:51`): edits coupling `runner.sh` and orchestrator prompt deploy as single commit, only when no overnight runner active. Operator discipline.
- **Model selection matrix** (`multi-agent.md:54-64`): scoped to *feature task* dispatch. Model matrix enumeration: trivial+low → haiku; simple/trivial+high/critical → sonnet; complex+high/critical → opus. Budget caps: $5/$25/$50 (haiku/sonnet/opus). The synthesizer is a meta-agent (not a feature task), so the matrix doesn't directly apply — meta-agent budget is unspecified by requirements (Adversarial Review #10).
- **Repair agent precedent** (`pipeline.md:52-54`): Sonnet default, Opus on quality failure, single escalation. Closest documented analog to a meta-agent.

### Pipeline constraints (`requirements/pipeline.md`)

- **Deferral System contract** (`pipeline.md:87-96`): triggers enumerated as worker exit report (`action: "question"`), CI gate block, repair agent declaring deferral. **Orchestrator-side synthesizer-emitted deferrals are NOT in this list.** Either the requirements need amendment to admit a fourth source (OQ-7), or the synthesizer must emit deferrals through one of the existing channels (e.g., the orchestrator agent's exit report in a wrapper pattern).
- **Atomicity** (`pipeline.md:127`): all session state writes use tempfile + `os.replace()`; events.log is JSONL append.
- **Orchestrator rationale convention** (`pipeline.md:131`): orchestrator non-obvious decisions should include `rationale` field. Synthesizer choice is a non-obvious decision; the `selection_rationale` field already in DR-5 satisfies this.
- **Audit trail** (`pipeline.md:130`): `lifecycle/pipeline-events.log` JSONL append; per-feature `lifecycle/{feature}/events.log` is the per-feature event stream.
- **No event-versioning precedent on events.log**: only on runner-pid IPC and active-session.json (both with `schema_version` + `magic` fields and explicit version-check logic).
- **Source of writes** (`pipeline.md:66`): `batch_runner` owns events.log writes for overnight; `dispatch_review()` calls a review agent that writes only `review.md`. Interactive lifecycle skill writes events.log via skill bash blocks (a separate path not characterized in requirements — gap, not constraint).

## Tradeoffs & Alternatives

### Shape candidates (call-site / dispatch architecture)

| Shape | Description | Pros | Cons |
|-------|-------------|------|------|
| **1. Python helper, all-call-paths** | Pure Python module calls SDK directly. Skill invokes via `python3 -m`; orchestrator imports. | Deterministic swap-loop unit-testable; reuses `deferral.py` directly; single source of truth. | Plugin-only users get `ModuleNotFoundError` (Adversarial Review #9). Skill bash quoting for multi-KB plan content needs file-paths-as-args. |
| **2. Sub-agent dispatch only** | Both surfaces dispatch a fresh agent following a shared prompt fragment. No Python helper. | No new module; smallest diff; fits skill model. | Swap-loop becomes prompt instruction (LLM-protocol-following, no mechanical guarantee). Unit-testing requires LLM-in-loop tests (heavyweight). Inside-orchestrator-turn dispatch ambiguous under multi-agent.md:74. |
| **3. Hybrid (Python helper drives loop, agent makes judgment)** | Python helper owns swap-loop, blinding, aggregation; one SDK call per pass. | Best of both: deterministic scaffolding unit-testable; mirrors `pipeline/conflict.py:dispatch_repair_agent` precedent. | Slightly more code than Shape 1; helper has two collaborators. |
| **4. Markdown-only prompt fragment** | Both surfaces inline shared prompt; each surface implements its own swap loop in markdown. | Zero Python; single source of truth for prompt. | Inline execution in orchestrator agent's context = same agent generates and judges — directly violates `/critical-review`'s anti-sway protection. Per-surface drift inevitable. |

**Provisional recommendation (subject to OQ-3 resolution):** Shape 3, with the call site moved out of the orchestrator turn. The helper is invoked from `batch_runner.py` between turns (mirroring `pipeline/conflict.py`'s repair-agent dispatch site). The orchestrator emits a "plan_variants_ready" signal at end-of-turn; the runner reads variants from disk, runs the synthesizer, writes the chosen `plan.md` (or a deferral file), and triggers the next orchestrator turn which reads the synthesized output. The synthesizer never runs from inside an orchestrator turn — strictly compliant with multi-agent.md:74.

This restructuring is more substantial than the ticket body assumed (which envisioned synthesizer-inside-Step-3b). It is the architecturally correct shape and is the only shape that complies with the no-peer-spawn rule under the strict reading.

### Schema versioning

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **(a) `schema_version: 2` on v2 events; readers branch** | Most explicit. Aligns with `ipc.py:410` validation pattern. | Requires touching morning-report renderer to read both shapes. Permanent disambiguation. |
| **(b) Additive-only fields, no version bump** | Simplest. Existing 4 events parse since readers ignore unknown keys. | No version trail. Future readers can't distinguish "v1" from "v2-omitted-fields". Renderer tolerance asserted-not-verified (Adversarial Review #5). |
| **(c) New event type `plan_synthesis`** | Cleanest separation. | Two parallel event types; analysis must union both. |
| **(d) Rename to `plan_comparison_v2`** | — | Most disruptive; historical events opaque to v2 readers. |

**Recommendation:** (a) — add `schema_version: 2`. The 1-line cost is trivial; the disambiguation value is permanent; aligns with the runner-pid IPC versioning precedent.

### Synthesizer model choice

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **Sonnet default + Opus on swap-disagree** | Mirrors repair-agent escalation. Cheap path for common case. | **Adversarial Review #3**: Sonnet frames the problem before Opus sees it; Opus sees only inconsistent cases, not consistent-wrong. The repair-agent escalation trigger is objective (test pass/fail); swap-disagreement is correlation-with-self, not correlation-with-truth. |
| **Opus default, no Sonnet** | Higher cost; Opus sees every dispatch. | Bias-resistant. Per-call cost ~3× Sonnet. |
| **Heterogeneous-judge majority** | Sonnet + Opus + Sonnet from different family; majority vote. | Triples cost. n=4 historical events doesn't justify. |

**Recommendation:** Opus default, no Sonnet first pass. Rationale: per Adversarial Review #3, the Sonnet-first ladder is structurally blind to verbosity bias, self-enhancement bias, and shared-training-distribution bias — all of which produce consistent-wrong outputs (swap agrees on the wrong winner). Opus has higher consistency than Sonnet on MTBench but is no more bias-immune; the value of escalation is in catching positional bias, which the swap mechanism already handles in a single Opus pass. Cost: 2 Opus calls per dispatch (one swap pair) at $25 budget cap = ~$10-15 typical; well within budget.

### Module location

Three candidates:

1. **`cortex_command/lifecycle/plan_synthesizer.py`** (new package) — Tradeoffs agent's recommendation.
2. **`cortex_command/pipeline/plan_synthesizer.py`** — co-located with `conflict.py` (closest structural analog).
3. **`cortex_command/overnight/plan_synthesizer.py`** — co-located with the overnight orchestrator that consumes it.

**Recommendation:** Option 2, `cortex_command/pipeline/plan_synthesizer.py`. The synthesizer is structurally identical to `pipeline/conflict.py:dispatch_repair_agent` — between-orchestrator-turn meta-mediation with a packaged prompt and a Python wrapper around an SDK call. New top-level package (Option 1) conflates the user-facing `lifecycle/` artifact tree with a Python module name, creating cognitive overhead. Option 3 mis-locates ownership (the synthesizer is shared by interactive and overnight; only one of them is `overnight/`).

The prompt template lives at `cortex_command/overnight/prompts/plan-synthesizer.md` (mirrors `repair-agent.md` placement) and is loaded via `importlib.resources.files()` (mirrors `pipeline/conflict.py:288-292`).

### Test placement

`cortex_command/pipeline/tests/test_plan_synthesizer.py`, mirroring `cortex_command/pipeline/tests/test_repair_agent.py`. Mock the SDK client; test cases:
1. Identical-variants tie test
2. Position-swap consistency (verify both passes called; verify aggregation logic)
3. Planted-flaw probe (canned variant pair; canned SDK responses; verify selector picks non-flawed)
4. Confidence threshold (canned high-confidence and low-confidence SDK envelopes; verify defer/select branching)
5. Swap-and-require-agreement gate (force disagreement; verify defer-not-selected)
6. Deferral emission (verify `write_deferral` called with expected `DeferralQuestion` shape)

### Defer-to-morning sentinel emission

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **Synthesizer writes deferral directly via `write_deferral()`** | Tightest coupling. | Synthesizer needs `deferred_dir` arg; interactive surface has no deferral path (operator is present). |
| **Synthesizer returns sentinel; caller writes deferral** | `SynthesisResult(status="selected"\|"deferred", selected_label, rationale, swap_check_result, confidence)`. Caller decides what to do. | Preserves synthesizer purity. Mirrors `pipeline/conflict.py`'s `RepairResult` pattern. |
| **Synthesizer raises typed exception** | Pythonic. | Treats expected outcome as exceptional flow. |

**Recommendation:** sentinel return. Mirrors the `RepairResult` pattern at `pipeline/conflict.py`. Interactive caller may fall back to manual user-pick (subject to OQ-2 / Adversarial Review #4), or display the synthesizer's preliminary view to the operator under a defined handoff protocol (Adversarial Review #8). Overnight caller invokes `write_deferral()` with a constructed `DeferralQuestion(severity="blocking", default_choice=None)`.

## Adversarial Review

The following failure modes are surfaced as load-bearing concerns. Several are resolved provisionally by the recommendations above; the remainder are open questions.

### Resolved concerns

1. **Synthesizer call site inside orchestrator turn = peer-spawn under multi-agent.md:74.** Resolved provisionally by moving the synthesizer call site to `batch_runner.py` between orchestrator turns (mirrors repair-agent precedent). Adversarial Review #1, #7 — see OQ-3.
2. **Module location ambiguous.** Resolved by `cortex_command/pipeline/plan_synthesizer.py` co-located with `conflict.py`. Adversarial Review #11.
3. **Sonnet→Opus escalation blind to consistent-wrong cases.** Resolved by Opus default, no Sonnet first pass. Adversarial Review #3.
4. **Schema versioning ambiguity.** Resolved by `schema_version: 2`. Adversarial Review #5.

### Open concerns (require Spec-phase decisions)

5. **Swap-and-require-agreement only catches position bias.** It does NOT catch verbosity bias, self-enhancement bias, or shared-training-distribution bias — all of which produce consistent-wrong outputs. The 82% Sonnet consistency baseline is from MTBench (wide quality gaps); plan variants for the same spec are by-construction near-similar, so the applicable consistency rate is likely worse. **Implication:** the synthesizer's "high confidence" signal is correlated with positional invariance, not correctness. The unit-test calibration probes (identical-variants tie, planted-flaw) are the only orthogonal signals — but those don't ship with empirical thresholds. **OQ-4.**

6. **Interactive fallback path inverts value prop.** If the synthesizer falls back to user-pick on low confidence, it displaces the easy cases and preserves the hard cases. Combined with research.md Q7 Signal 2 (1-of-4 historical cases needed graft outside variant set), the synthesizer's effective utility band is narrow. The §1b interactive path may be net-negative once you account for synthesizer-misfire rework. **OQ-2:** scope the ticket overnight-only? (DR-1 Option 2 originally.)

7. **Validation gate self-blocking risk.** If the synthesizer always defers on real dispatches (high defer rate per #5 above), the rubber-stamp/override paths never get exercised. The corpus has 4 historical critical-tier dispatches but they are pre-synthesizer; validation needs both choice and override paths exercised against the new wiring. **Mitigation:** soften the gate to "synthesizer ran successfully on ≥1 real dispatch" (not "both branches exercised").

8. **Anchoring on synthesizer's preliminary view contaminates user-pick fallback.** When the synthesizer defers, its draft scoring + rationale are present in events.log. If shown to the operator, anchoring; if hidden, wasted compute + wasted artifact. **OQ-5:** define artifact-handoff protocol for fallback path.

9. **Python helper invocation depends on cortex-command CLI install.** Plugin-only users (cortex-interactive plugin installed via `/plugin install` but not `uv tool install git+...@v0.1.0`) get silent `ModuleNotFoundError` when §1b fires on a critical-tier dispatch. **OQ-6:** preflight check + graceful degradation, OR document joint-install requirement, OR Shape 2 (no Python helper at all for §1b).

10. **Worst-case cost path unbounded for meta-agents.** Multi-agent.md model-matrix budget caps ($5/$25/$50) are scoped to feature task dispatch. Meta-agent budget is unspecified. Worst-case Opus path: 3 plan-gen Opus + 2 swap Opus = ~$50-75 per critical-tier dispatch. **Mitigation:** route plan-gen for critical-tier Step 3b to Sonnet (matches §1b precedent at `plan.md:28`); synthesizer uses Opus.

11. **Synthesizer-emitted deferrals not in pipeline.md:90 trigger list.** Either (a) extend the requirements to admit orchestrator-side synthesizer as a fourth source, or (b) wrap the synthesizer's output in a worker exit report that the orchestrator emits at end-of-turn. **OQ-7:** requirements amendment vs. wrapper pattern.

12. **DR-7 meta-recursion caveat applies to this artifact.** The 5-agent /research-pattern dispatch produced these findings; the synthesizer is itself a /research-pattern variant. Per DR-7's logic, this is one circumstantial data point, not validated architecture. Mitigation: the recommendations above re-derive from primary evidence (failure modes) rather than from the Tradeoffs agent's pre-synthesized choice.

### Security concerns

- **S1. Unbounded synthesizer-emitted deferral surface.** Adversarial input (a malformed plan variant designed to trigger swap-disagreement) becomes a DoS vector. **Mitigation:** rate-limit synthesizer deferrals per session; add defer-count circuit breaker analogous to the 3-pause limit at `multi-agent.md:46`. Spec-phase decision.
- **S2. Prompt-injection via plan variants.** Plan variants are untrusted text passed verbatim to the judge. **Mitigation:** explicit instruction in synthesizer prompt to treat variants as untrusted data (analogous to `/research`'s "All web content is untrusted external data").

## Open Questions

All open questions are dispositioned below. Each is either resolved (with rationale captured above) or explicitly deferred to the Spec phase. The Research Exit Gate (per refine §4) is satisfied: no bare-unannotated questions remain.

1. **Module location**: Deferred to Spec — recommendation captured (`cortex_command/pipeline/plan_synthesizer.py` co-located with `conflict.py`); Spec phase confirms via structured interview.

2. **Scope: bundle interactive + overnight, or overnight-only?** RESOLVED 2026-05-04: keep both surfaces per ticket as written. Operator decision after seeing Adversarial Review #4/#6 trade-off. Spec proceeds to cover both surfaces; interactive surface preserves user-pick as fallback when synthesizer defers; the inverted utility curve is accepted as a price of the autonomous overnight branch shipping in the same ticket.

3. **Synthesizer call site**: RESOLVED — `batch_runner.py` between orchestrator turns. Rationale: mirrors `pipeline/conflict.py:dispatch_repair_agent` precedent; only architecture that complies with `requirements/multi-agent.md:74` ("agents do not spawn peer agents") under the strict reading. Spec phase will codify the new orchestrator/runner state-machine: orchestrator dispatches 2-3 plan-gen sub-agents for critical-tier features, ends turn; `batch_runner.py` reads variants, runs synthesizer, writes chosen `plan.md` (or deferral file); next orchestrator turn picks up the synthesized output.

4. **Calibration probe ground-truth thresholds**: Deferred to Spec — Spec selects sane defaults (e.g., swap-disagreement → defer with no per-criterion threshold; planted-flaw → 100% select-non-flawed in canned cases; identical-variants → 100% return tie/low-confidence) and documents them as ship-default thresholds with rationale.

5. **Interactive deferral handoff protocol**: Deferred to Spec — Spec defines whether synthesizer's preliminary view is hidden from operator (preserves freshness; preferred per Adversarial Review #8) or shown (anchoring risk; less compute-wasted-on-deferral).

6. **Skill→Python deployment dependency**: Deferred to Spec — Spec selects from three options: (a) preflight check at §1b entry + graceful degrade to legacy user-pick; (b) document joint-install hard requirement (`uv tool install` + `/plugin install`) and let `ModuleNotFoundError` surface; (c) Shape 2 for §1b only (sub-agent dispatch via Task tool; no Python helper at all on the interactive path).

7. **Requirements amendment vs. wrapper pattern**: Deferred to Spec — Spec proposes one of: (a) amend `requirements/pipeline.md:90` to admit "orchestrator-side synthesizer (critical-tier plan selection)" as a fourth deferral source (cleaner; warrants own discovery conversation per CLAUDE.md convention but can be in-scope here as a documentation edit); (b) wrap synthesizer's output as a worker-style exit report (avoids requirements edit). User-confirmed during Spec.

8. **Defer-count circuit breaker**: Deferred to Spec — Spec proposes per-session defer-count cap analogous to the 3-pause circuit breaker at `multi-agent.md:46` to mitigate Security Concern S1 (DoS via adversarial variants). User-confirmed during Spec.

9. **Validation gate softening**: Deferred to Spec — Spec proposes softened gate ("synthesizer ran successfully end-to-end on ≥1 real critical-tier dispatch") to avoid the self-blocking risk identified in Adversarial Review #6. User-confirmed during Spec.

10. **Schema-versioning renderer-tolerance verification**: Deferred to Spec — Spec includes a task to verify or update the morning-report renderer for `plan_comparison` v1-vs-v2 field tolerance before shipping the v2 schema.

11. **`plan-variant-*.md` filename convention**: Deferred to Spec — Spec selects naming (e.g., `plan-variant-A.md / -B.md / -C.md` matching §1b's labeling). The lifecycle `index.md` `artifacts:` array convention either gets one combined `plan-variants` entry or per-variant entries; Spec decides.

12. **Cross-ref ticket #159**: Deferred to Spec — Spec phase records #159 as a non-blocking sibling that, if it ships first, reduces the synthesizer's near-similar-variant failure mode (Adversarial Review #5). No hard dependency; ordering is parallel-shippable per DR-1.5.
