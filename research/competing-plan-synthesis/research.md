# Research: competing-plan-synthesis

## Research Questions

1. **Architecture choice — is parallel-and-pick right when the user is unavailable?**
   → **Parallel-and-pick is appropriate as the dispatch mechanism IF autonomous synthesis ships at all (gated on the load-bearing roadmap question — see Open Questions).** Architecture A (status-quo dispatch + autonomous rank-and-pick selector + defer-to-morning runtime fallback) is the lowest-risk shipped design. **B-prime** (rank-and-pick + constrained-graft on the typed plan schema) is structurally bounded under invariants 1-4 but n=1 corpus evidence does not justify its complexity now — it is documented as the pre-cleared next-step architecture. Sequential GAN (C) sacrifices diversity that is the load-bearing property of plan-phase; parallel+GAN (D) is a strict superset of A's cost with little marginal value; **unbounded** hybrid composition (B) is not formally well-defined on plan artifacts (Q3).

2. **Anti-sway scaffolding transfer — which `/critical-review` protections apply?**
   → **Most transfer with adaptation; the substitution is more substantial than initially expected.** Envelope extraction, role separation, B-only refusal gate, and anchor checks transfer directly. The class taxonomy (A/B/C → ranking-axis taxonomy) and JSON envelope schema (per-variant scoring on multiple axes) need adaptation. The A→B downgrade rubric needs full redesign — its "fix-invalidation argument" semantics are tied to artifact-vs-objection geometry that doesn't apply to plan-vs-plan ranking. The transferable invariant is the *structural shape* (forced per-finding commitment + synthesizer evidence re-examination + B-only refusal), not the specific content.

3. **Hybrid composability and validation — when can variants be merged?**
   → **Distinguish unbounded merge from bounded graft.** **Unbounded composition** (synthesizer free to merge arbitrary plan content) is NOT formally well-defined on plan artifacts and should not ship: three-way-merge fails on overlapping semantic edits [arXiv:1802.06551]; refinement calculus has no "merge alternatives" operation [Springer LNCS]; LLM literature has no validated multi-section plan synthesis technique (`NOT_FOUND(query="multi-section structured plan synthesis empirical evaluation", scope="published evidence)`). **Constrained graft** (insert one named task from a non-winning variant into the winner; mechanically renumber `Depends on`) IS bounded under Appendix invariants 1-4 (mechanically checkable). Q7 Signal 2 documents one historical case where the user supplied exactly this operation manually — positive prior evidence that graft is a realistic resolution. **For shipping: A only now (n=1 too small to ground B-prime's complexity); B-prime documented as pre-cleared next step.**

4. **Trigger and routing — does the autonomous path exist today? (revised post-conversation)**
   → **The path exists; the critical-tier branch on it does not.** `[cortex_command/overnight/prompts/orchestrator-round.md:201-273]` Step 3b dispatches plan-gen sub-agents for features whose `plan_path` is missing on disk. The dispatch template at lines 236-260 is a **bare single-agent prompt** ("design an implementation approach, then write a complete plan to {{feature_plan_path}}") — it does NOT consult criticality and does NOT invoke the §1b dual-plan flow. The eligibility gate at `[cortex_command/overnight/backlog.py:39]` accepts `status ∈ ("backlog", "ready", "in_progress", "implementing", "refined")`, so a `/refine`-output feature (status: refined, has spec, no plan) entering overnight already triggers Step 3b — but Step 3b runs single-agent, regardless of criticality. `/refine` does NOT invoke plan-phase itself [confirmed via codebase agent]. **Per `[research/overnight-plan-building/research.md:5-6, 89]` Step 3b has not been observed to fire in production** because users typically run `/lifecycle plan` first, but the dispatch wiring is live — the path is dormant, not absent. **The work is therefore wiring (extend Step 3b with a criticality branch that invokes the shared synthesizer for critical-tier features), not path-building from scratch.**

5. **Synthesis-specific failure modes — what's new vs. user-selection?**
   → **Position bias is empirically the dominant risk.** GPT-4 flips 20-40% of decisions on order-swap; consistency 57% (Haiku, Gemini-1.0-pro) to 82% (Claude-3.5-Sonnet, GPT-4) on MTBench [Judging the Judges, arXiv:2406.07791]. Critically: *"as the answer quality gap enlarges, judges generally become more position consistent"* — bias is **worst when candidates are similar**, which is exactly our case (variants generated for same spec). Verbosity bias and self-enhancement bias are documented [MT-Bench, arXiv:2306.05685]. Mitigations are well-established: swap-and-require-agreement, randomized labels, heterogeneous-judge majority voting. Architecture A's selector confines the failure surface to "wrong pick" (bounded, auditable from the existing `plan_comparison` event); **unbounded** hybrid composition (B; rejected per Q3) introduces unbounded failure surface (incoherent plans). Note: A's "wrong pick" failure includes the graft-needed case from Q7 Signal 2 — the historically-correct answer can be outside A's variant set; B-prime would address this but is not shipped now.

6. **Auditability — what artifacts must persist?**
   → **Extend the existing `plan_comparison` event schema; do NOT introduce a separate `plan-synthesis.md` artifact.** The current event already logs all variants, summaries, task counts, and risk profiles [plan.md:113-115]. Adding `selection_rationale`, `selector_confidence`, `position_swap_check_result`, and `axis_routing` keeps the audit trail compact and maps to the existing morning-report rendering surface. A separate artifact would duplicate `plan.md` content (the chosen plan IS the synthesis result) and create artifact-management overhead.

7. **Empirical baseline — what does the corpus tell us?**
   → **Sparse, with two distinct signals.** Four `plan_comparison` events exist across the lifecycle corpus (146 features in `lifecycle/`), all in interactive sessions, all with non-null `selected` fields, none with `selected: "none"`. **Signal 1 (diversity)**: variants show shallow diversity — they differ on task ordering and granularity (16/14/13 tasks; "bottom-up" vs "events-registry-first" vs "runner-first"), NOT on architectural strategy. Decompositions, not architectures. **Signal 2 (resolution shape)**: one of four ("rebuild-overnight-runner-under-cortex-cli") resolved as "Plan A with Plan B `runner_primitives.py` extraction grafted in" — a constrained graft. This is **positive prior evidence that targeted graft is a realistic resolution operation in some critical-tier cases** when no single variant dominates (cf. B-prime in Feasibility Assessment). It is not by itself sufficient to justify shipping graft automation — n=1 is too small to ground that complexity tradeoff — but it is structurally informative: the historically-correct answer in 25% of observed cases was outside the variant set, meaning rank-and-pick over the available variants would have been wrong on that case.

## Codebase Analysis

### §1b "Competing Plans (Critical Only)" — current internals

The Critical-tier dual-plan flow lives at `[plugins/cortex-interactive/skills/lifecycle/references/plan.md:21-119]`:

- **Dispatch**: 2-3 parallel Sonnet plan agents via Task tool `[plan.md:27-28]`
- **Plan agent prompt**: Verbatim template `[plan.md:30-92]`. Agents receive spec.md and research.md inline, instructed to "design an independent implementation approach" and "explore a different architectural strategy, decomposition, or ordering than the obvious default" `[plan.md:47]`
- **Code budget**: Strict separation between structural context (paths, signatures, types, pattern references) and prohibited code (function bodies, imports, error handling, test code) `[plan.md:50-65]`
- **Collection**: Wait for all; if 1 succeeds use it sole; if all fail fall back to single-plan `[plan.md:94]`
- **User selection**: Comparison table presented `[plan.md:96-105]`; user selects variant or rejects all `[plan.md:107-109]`
- **Event log schema**: `{"ts","event":"plan_comparison","feature","variants":[{"label","approach","task_count","risk"}],"selected":"Plan A|none"}` `[plan.md:113-115]`
- **Hard-coupling**: Tightly integrated into the lifecycle skill's main interactive context. `NOT_FOUND(query="autonomously invoke §1b competing-plans flow", scope="claude/overnight/, claude/pipeline/, plugins/cortex-interactive/skills/refine/")`

### Anti-sway scaffolding in `/critical-review`

The skill at `[plugins/cortex-interactive/skills/critical-review/SKILL.md]` was designed against the eagerly-swayed-synthesizer failure mode documented in `[research/critical-review-scope-expansion-bias/research.md]`. Load-bearing protections, in transfer-priority order:

- **Forced class commitment** `[SKILL.md:90-99]`: A=fix-invalidating, B=adjacent-gap, C=framing. JSON envelope schema `[SKILL.md:119-134]` forces classification before prose synthesis.
- **Envelope extraction with malformed-envelope handling** `[SKILL.md:176-182]`: LAST-occurrence anchor for the `<!--findings-json-->` delimiter; on malformed envelope, untagged prose passes through to synthesizer's `## Concerns` section (not C-class) and is excluded from A-class tally.
- **A→B downgrade rubric** `[SKILL.md:203-260]`: Four triggers (absent / restates / adjacent / vague) force downgrade. Straddle exemption when `straddle_rationale` is populated. Eight worked examples ground each trigger.
- **Within-class through-lines** `[SKILL.md:200]`: A/B/C through-lines are distinct; do not merge across classes.
- **B-only refusal gate** `[SKILL.md:261]`: If A-class count is zero after re-examination, no `## Objections` section. Demoted to `## Concerns`.
- **Synthesizer is fresh Opus** `[SKILL.md:184-186]`: Not the orchestrator that derived the angles, not any reviewer.
- **Anchor checks** `[SKILL.md:344, 348]`: Dismiss/Apply must point to artifact text, not memory of conversation.

**Transfer assessment**:
- **Direct transfer**: envelope extraction + malformed-envelope handling, role separation (synthesizer ≠ generator of any variant), B-only refusal, anchor checks
- **Adapt**: class taxonomy (A/B/C → ranking-axis taxonomy fit for plan comparison); JSON envelope (per-variant scoring on multiple axes rather than per-finding severity)
- **Redesign**: A→B downgrade rubric — its "fix-invalidation argument" semantics belong to artifact-critique geometry, not ranking geometry

### Autonomous invocation gap

`[research/overnight-plan-building/research.md:5-6, 89]` documents that the overnight orchestrator's plan-gen sub-agents "have not been observed to trigger in production sessions" — every feature entering the overnight pipeline already has `plan_path` pointing to an existing file. Plan-gen Steps 3a-3e are "a fallback for features that enter sessions without pre-existing plans — a safety net, not a hot path."

`/cortex-interactive:refine` runs Clarify → Research → Spec only and does NOT invoke plan-phase `[premise-confirmed via codebase agent]`.

The §1b critical-tier flow has only ever fired in interactive `/cortex-interactive:lifecycle plan` sessions. **No autonomous path exists today.** Discovery scope must include building the autonomous path, not just the synthesizer.

### Empirical baseline

Four `plan_comparison` events found across `[lifecycle/*/events.log]` (146 features in `lifecycle/`):

- `[lifecycle/install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions/events.log]` — 3 variants, selected Plan C with Task 6 split
- `[lifecycle/archive/fix-overnight-runner-silent-crash-…/events.log]` — 3 variants, selected Plan B
- `[lifecycle/archive/disambiguate-orchestrator-prompt-tokens-…/events.log]` — 2 variants, selected Plan A
- `[lifecycle/archive/rebuild-overnight-runner-under-cortex-cli/events.log]` — 3 variants, selected "Plan A with Plan B runner_primitives.py extraction grafted in"

Variant differences: predominantly task ordering and granularity (16/14/13 tasks; "bottom-up" vs "events-registry-first" vs "runner-first"). **Not orthogonal architectural strategies** — this is the diversity gap addressed in DR-3. **Constrained graft was the user's chosen resolution in 1 of 4 cases** — not because the user "did the LLM's job manually," but because rank-and-pick over the available variants was insufficient and the user supplied the graft to reach the right answer. n=1 is too small to ground a base-rate decision on shipping graft automation, but the case is structurally informative: rank-and-pick is closed over the input variants and the historically-correct answer was outside that closure.

### Adjacent infrastructure

- Lifecycle artifact registration follows `[lifecycle/{feature}/index.md]` inline `artifacts:` array + wikilink pattern `[plan.md:233-239]`
- **Existing deferral system** `[requirements/pipeline.md:87-95]`: *"When the pipeline encounters an ambiguous decision that cannot be resolved autonomously, it writes a structured deferral question and surfaces it in the morning report."* Critical-tier plan selection is the canonical case this system was designed for.
- `~/.claude/notify.sh` async notification path `[requirements/pipeline.md:28]` — wired-in pathway for operator push notifications during overnight runs
- `/cortex-interactive:research` parallel-dispatch architecture — role-orthogonal agents with non-overlapping contracts; cited by `[research/critical-review-scope-expansion-bias/research.md]` Q3 (line 9) as structurally avoiding the synthesis bias that motivated `/critical-review`. **Caveat (audit during this discovery)**: on inspection of `[plugins/cortex-interactive/skills/research/SKILL.md]`, /research's Tradeoffs agent emits a `Recommended approach` (single-agent recommendation produced inside the agent's own context) and the Adversarial agent receives a synthesizer-produced summary of prior findings — both are single-point-of-failure synthesis steps without /critical-review's anti-sway protections (no class-tagged JSON envelopes, no evidence re-examination, no anchor checks). The "role-orthogonal" claim holds at the level of role labels but breaks down inside agent prompts where aggregation still happens. /research is *less swayed* than pre-fix /critical-review, not bias-immune.

## Web & Documentation Research

### Anthropic harness-design article

[https://www.anthropic.com/engineering/harness-design-long-running-apps] — three load-bearing claims for our problem:

1. *"Tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work."* Mechanisms cited: live interaction (Playwright MCP), few-shot calibration with score breakdowns, iterative prompt tuning. Documented failure: evaluator would *"identify legitimate issues, then talk itself into deciding they weren't a big deal and approve the work anyway"* — direct support for the user's framing that synthesizers are eagerly swayed.
2. *"When asked to evaluate work they've produced, agents tend to respond by confidently praising the work — even when, to a human observer, the quality is obviously mediocre."* Maps to the load-bearing constraint: **the synthesizer must not have produced any variant**.
3. File-based handoff with context resets: *"Communication was handled via files: one agent would write a file, another agent would read it and respond either within that file or with a new file that the previous agent would read in turn."* Aligns with the existing `lifecycle/{feature}/` artifact-as-handoff pattern.

The article's pattern is **entirely sequential** — generate, evaluate, refine, repeat. It does NOT use parallel-and-pick or competitive synthesis. Its strategic-pivot mechanism (*"refine the current direction if scores were trending well, or pivot to an entirely different aesthetic if the approach wasn't working"*) supports an "all-variants-weak → trigger replan" gate but does not specify a numeric threshold. **The article is silent on the multi-variant aggregation problem at the heart of our discovery.**

### Multi-proposal synthesis literature

- **Self-Consistency** [Wang et al. 2022, arXiv:2203.11171] aggregates short-answer outputs by majority vote. `NOT_FOUND(query="self-consistency on multi-section structured documents", scope="published variants)`.
- **AI Safety via Debate** [Irving et al. 2018, arXiv:1805.00899] establishes the judge-only pattern theoretically; empirical judge-tuning to resist sycophancy is not detailed for plan-length artifacts.
- **Multi-agent debate** [Du et al. 2023, arXiv:2305.14325] uses cross-round consensus on short answers; documented failure: *"premature convergence, shared bias reinforcement, and limited evidence exploration"* [arXiv:2510.12697].
- **Pairwise > holistic ranking**: *"pairwise comparisons lead to more stable results and smaller differences between LLM judgments and human annotations relative to direct scoring"* [eugeneyan.com/writing/llm-evaluators/]. Arena-Lite tournament [arXiv:2411.01281] achieves O(N) tournament ≈ O(N²) accuracy. For 2-3 candidates, pairwise is the empirically-supported choice.
- **Tree-of-Thoughts** [Yao et al. 2023, arXiv:2305.10601] picks paths; no merge primitive.
- **Graph-of-Thoughts** [Besta et al. 2023, arXiv:2308.09687] is the only retrieved framework with an explicit AGGREGATE primitive — *"merge best-scoring thoughts into a new one."* `NOT_FOUND(query="GoT-aggregate vs GoT-best-pick on plan artifacts", scope="published empirical evaluation)`.

### Program/spec merging traditions

- **Three-way merge** (diff3, AST merge): textual/syntactic merge with overlapping-edits → conflict surface for human resolution [Sousa et al., arXiv:1802.06551; Schesch et al. ASE 2024]. Semantic conflicts are the hardest because *"the merged modification is compiled without error but malfunctions."*
- **Refinement calculus / Z schema operators** (∧, ∨): *"co-refinement"* addresses partial-view amalgamation [Springer LNCS]; does NOT merge competing-complete specs. Conjunction often unsatisfiable; disjunction too weak.
- **Refinement calculus has no "merge alternatives" operation.** Empirical confirmation that hybrid-plan composition has no off-the-shelf formal primitive.
- Implication: "compose a hybrid" must be reframed as **selection + targeted graft** if it ships at all — but the corpus shows the only hybrid ever shipped was a manual user-grafting decision.

### Autonomous decision-making under absent operator

- **Saga pattern**: forward-progress + compensation. Maps to "synthesizer commits must be cheap to roll back" if it ships.
- **Temporal / Airflow defer**: durable arbitrarily-long waits with no worker resource cost. Airflow 3.1+ ships explicit `HITLOperator` [airflow.apache.org/docs/apache-airflow/stable/tutorial/hitl.html]. Established practice for human-decision-needed-but-human-offline.
- **"Defer to morning"** as a named pattern: `NOT_FOUND(query="defer to morning workflow pattern", scope="academic + engineering literature)`. Composable from Temporal's durable-await + Saga compensable commits, but no canonical name.
- Empirical caveat: HITL queues that grow faster than the human drains them become *"Human Lost in the Queue"* [medium.com/@basilpuglisi]. Defer-always shifts cost to morning batch-review fatigue.

### Position-bias and synthesizer-bias literature

- **Position bias quantified**: GPT-4 flips 20-40% on order swap; consistency 57% (Haiku, Gemini-1.0-pro) to 82% (Claude-3.5-Sonnet, GPT-4) on MTBench [Judging the Judges, arXiv:2406.07791]. Critical: *"as the answer quality gap enlarges, judges generally become more position consistent"* — bias **worst when candidates are similar**, exactly our case.
- **Verbosity bias** [MT-Bench, arXiv:2306.05685]: longer responses rated higher independent of content quality.
- **Self-enhancement bias**: LLMs favor outputs they generated.
- **Mitigations** (published methodology): swap-and-require-agreement; randomization; heterogeneous-judge majority voting; Bradley-Terry / Elo aggregation for tournaments; identical-answer test (must return tie); order-swap consistency.
- `NOT_FOUND(query="planted-flaw probe for plan-synthesis judge calibration", scope="published methodology)` — the obvious calibration probe is not formalized in the retrieved literature.

## Domain & Prior Art

### Structurally similar

- `/critical-review` parallel-reviewer-then-synthesizer pattern (cortex internal): closest in-house precedent. Its structural protections are the canonical anti-sway scaffolding for cortex.
- `/research` parallel-dispatch with role-orthogonal agents (cortex internal): the cited counterexample to /critical-review's defects — agents have non-overlapping contracts, so the synthesizer is partitioning, not aggregating. *(Direct match for our preferred direction in DR-3.)*
- Anthropic harness-design GAN pattern (external): sequential, not parallel.
- LLM-as-judge tournaments (literature): direct fit for ranking N variants pairwise.

### Not yet solved

- Multi-section structured plan synthesis specifically: no published evidence any technique works.
- Hybrid composition on plan artifacts: no formal primitive in version-control merge or refinement calculus.

### Lesson

Where literature has validated techniques (short-answer aggregation, code merge), they don't transfer cleanly to plan artifacts. Where it has analogous patterns (GAN, debate-with-judge), they're sequential or short-form. Cortex's internal `/research` skill is the strongest structural template for parallel multi-agent work that avoids the synthesis bias.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|---|---|---|---|
| **A: Status quo + autonomous rank-and-pick selector** | M | Position bias on similar variants; selector picks wrong; no escape hatch unless E-fallback shipped; shallow variant diversity (Q7); historically-correct answer can be outside variant set (Q7 graft case) | F (instrumentation); orthogonality validation; events.log evidence per OQ3 |
| **B-prime: Rank-and-pick + constrained graft (single-task insertion against typed plan schema)** | M-L | Synthesizer mis-grafts (mechanically-checkable invariants 1-4 catch dependency/file-closure errors; semantic invariants 5-10 still need review); n=1 corpus evidence is thin justification for shipping; introduces "when to graft vs. just pick" decision | All A's + post-graft DAG/file-closure validator + acceptance criterion for which graft operations are bounded |
| **B: Auto-synthesizer with unbounded hybrid composition** | L | Cross-variant graph incoherence; dependency renumbering breaks `Depends on [N, M]`; launders contradictions; no formal merge primitive | All A's + hybrid-coherence checker (10 invariants, see Appendix) + adapted critical-review pass |
| **C: Sequential GAN replacement of §1b** | L | Loses diversity exploration that's load-bearing for plan-phase; iteration budget exhaustion produces unfinished plan; evaluator-capture | All A's + iteration budget contract + evaluator-skepticism calibration |
| **D: Parallel diversity → GAN refinement** | XL | Strict superset of A and C costs; wrong-winner amplification (refinement polishes bad-strategy plan); stop-condition coordination | All A's and C's combined |
| **E: Defer to morning (existing deferral system)** | S | Round-skip not surfaced clearly; skip-storm cascade; lifecycle stuck after N defers without escalation | Morning-report renderer entry; escalation rule after N defers |
| **F (zeroth epic): Base-rate instrumentation** | S-M | Calendar cost: 30+ overnight sessions before design proceeds | None |
| **G (zeroth epic): Async-notify-with-timeout** | S | False sense of reachability if notify.sh delivery is unreliable; queue overload | F (instrumentation) |

## Decision Records

### DR-1: Build a shared autonomous synthesizer wired into both interactive §1b and overnight Step 3b (resolved post-conversation)

- **Context**: The roadmap conversation (events.log:discovery_conversation_resolved, 2026-05-04) resolved the framing question by surfacing that an earlier ticket (#158, since repurposed) misread the codebase: the overnight plan-gen path EXISTS today via `[cortex_command/overnight/prompts/orchestrator-round.md:201-273]` Step 3b but uses a single-agent prompt that doesn't consult criticality. The synthesis system has value in **interactive mode independent of overnight** (replacing §1b's user-pick step when operator wants the system to decide) AND **as an extension of Step 3b** (handling critical-tier features that hit the dormant plan-gen path). The shared-mechanism shape ships once, wires twice.
- **Options considered**:
  1. Interactive-mode UX only (touches `plan.md`; overnight stays bare single-agent)
  2. Overnight extension only (touches `orchestrator-round.md` Step 3b; interactive keeps user-pick)
  3. **Both, shared mechanism**: build synthesis logic as a reusable component (extracted prompt fragment + Python helper); wire into both surfaces
- **Recommendation**: **Option 3**, per operator decision (2026-05-04). Synthesis logic ships as a single reusable mechanism; interactive §1b gets opt-in auto-synthesis (operator-triggered or default-with-override); overnight Step 3b gets a criticality branch that invokes the same mechanism automatically for critical-tier features. DRs 2-7 all activate.
- **Trade-offs**: Slightly larger initial scope than (1) or (2) alone, but extracting the synthesis logic up-front avoids a second-pass refactor when extending to the second surface. Shared mechanism enforces consistency across surfaces (same anti-sway protections, same event-schema, same calibration). The implementation order in DR-1.5 (below) sequences interactive-first to validate the design before overnight wiring.

### DR-1.5: Implementation order — interactive first, overnight after validation

- **Context**: Shape (3) ships into two surfaces. Order matters for risk: shipping into overnight first means autonomous-only critical-tier plans land without an interactive-mode dry run. Shipping interactive first means operators exercise the synthesizer in attended mode where they can override misfires before extending to unattended overnight.
- **Recommendation**: Two tickets, parallel where possible:
  1. **Tighten §1b plan-agent prompt** (DR-3 Option 4) — independent of synthesizer; ships in parallel with #2
  2. **Build synthesizer + ship to both surfaces** (DR-2 + DR-4 + DR-5 + DR-7) — synthesizer is built once and wired into interactive §1b and overnight `orchestrator-round.md` Step 3b in the same ticket. Basic probes (identical-variants, swap-consistency, planted-flaw) ship as unit tests inside this ticket. The validation gate (interactive surface exercised against ≥1 real critical-tier dispatch before overnight branch is enabled) lives as task ordering inside this ticket's lifecycle rather than as a ticket boundary, and is codified as an explicit acceptance criterion in the ticket body.
- **Trade-offs**: Combining synthesizer-build with both consumers in one ticket (vs. splitting interactive and overnight wiring across two) trades a smaller per-ticket scope for a complete E2E deliverable that covers both critical-tier resolution paths. Justified because the synthesizer is a pure function over plan variants — call-site-agnostic by design — so the interactive vs. overnight split would partition wiring details inside one feature rather than separating distinct features. Per project requirements *"Complexity: Must earn its place by solving a real problem that exists now,"* the validation gate is preserved as task ordering inside the lifecycle rather than recreated as ticket structure. Calibration probes ship as unit tests inside #2; empirical threshold tuning happens against production operator-disposition data, not pre-shipment work.

### DR-2: If autonomy ships, Architecture A only — but B-prime (constrained graft) is structurally bounded and pre-cleared as future option

- **Context**: Hybrid composition in its **unbounded form** (Architectures B, D — synthesizer free to merge arbitrary plan content) is not formally well-defined on plan artifacts. Three-way-merge fails on overlapping semantic edits; refinement calculus has no merge-alternatives operation; LLM literature has no validated multi-section plan synthesis. Plan artifacts have typed structure (`Depends on [N, M]`, file-list invariants, `Veto Surface`, `Scope Boundaries`) that arbitrary merge violates. **However**, the corpus shows the realistic resolution operation in 1 of 4 observed cases is a **constrained graft**: insert a single named task from a non-winning variant into the winner's task list, mechanically renumber `Depends on` references. This operation is bounded under Appendix invariants 1-4 (mechanically checkable: per-task closure, cross-task file closure, dependency-graph integrity, DAG) and is structurally distinct from arbitrary merge.
- **Options considered**: A (rank-and-pick), B-prime (rank-and-pick + constrained graft), B (unbounded hybrid), C (sequential GAN), D (parallel + GAN), E (defer to morning).
- **Recommendation**: **A only as the shipped autonomy** (with E as runtime fallback when selector confidence is low) — n=1 corpus evidence does not justify the added complexity of B-prime now, per the project principle *"Complexity: Must earn its place by solving a real problem that exists now."* **B-prime is acknowledged as structurally valid and pre-cleared as the next-step architecture** if A is empirically observed to fail on graft-needed cases. Reject B (unbounded hybrid), C (kills diversity), D (compound failure surface).
- **Trade-offs**: A's variant ceiling is the historically-observed graft-needed failure mode (Q7 Signal 2). The user's actual choice in 1 of 4 cases is unreachable under A; the defer-to-morning fallback is gated on a confidence signal A's selector lacks for graft cases. **This is an accepted trade-off, not a denied failure mode**: B-prime is the documented next step in the architecture progression, not closed off. If the empirical signal from production A-runs shows graft-needed cases recurring, B-prime ships next without re-litigating from scratch.

### DR-3: Tighten the §1b plan-agent prompt before adding routing-layer complexity

- **Context**: Q7 Signal 1 documents that current §1b produces ordering-variants, not architectural-strategy variants. The plan-agent prompt at `[plan.md:47]` admits ordering-distinction explicitly: *"explore a different architectural strategy, decomposition, **or ordering** than the obvious default."* The diversity gap can be attacked at two layers: (a) **at the plan-agent prompt** (cheap one-line edit — forbid ordering-only differentiation, require each variant to inhabit a named architectural-pattern category), or (b) **at a new routing-agent layer above the plan agents** (added complexity). Adding a routing-agent layer above a permissive plan-agent prompt does not change what the prompt admits — the routing label can still be satisfied by ordering-distinction within the assigned axis.
- **Options considered**:
  1. Transfer /critical-review's A/B/C scaffolding directly
  2. Adapt the structural shape but redesign the class taxonomy for ranking
  3. Add a routing-agent layer that assigns each plan agent a specific architectural axis pre-routing
  4. **Tighten the §1b plan-agent prompt to require strategy-level distinction** (forbid ordering-only differentiation; require each variant to inhabit a named architectural-pattern category)
- **Recommendation**: **Option 4 first**, per the project principle *"Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."* Option 4 is a one-line edit at `plan.md:47`; routing-agent (Option 3) is a new agent layer. **If post-tightening empirical observation shows variants still converge on near-duplicate strategies, escalate to Option 3** (routing agent) as conditional follow-up. Option 3 is the conditional next step, not the primary fix.
- **Trade-offs**: Option 4 still depends on spec/research seeding architectural-strategy alternatives in the inputs. If they don't (as Q7's corpus suggests is possible), neither prompt-tightening nor routing-agent will produce real diversity — both layers are downstream of an inputs problem that requires upstream work (spec/research generation that surfaces architectural choice points). The choice is between spending effort on the simpler intervention now (Option 4) and reserving the harder intervention (routing-agent) for cases where the simpler one demonstrably fails. **For the selector itself**: even under Option 4, the selector's job is still ranking — apply DR-4's swap-and-require-agreement mitigations regardless of which layer the diversity comes from. Note: this entire DR is moot if the discovery is re-aimed per the load-bearing roadmap question (see Open Questions).

### DR-4: Required mitigations against synthesizer position bias

- **Context**: Position bias flips 20-40% of GPT-4 decisions; even Claude-3.5-Sonnet (highest measured) has 18% inconsistency; bias is worst when candidates are similar [Judging the Judges, arXiv:2406.07791]. Plan variants for the same spec are by construction similar.
- **Options considered**:
  1. Single-pass selector
  2. Swap-and-require-agreement (run selector with variants in two orders; declare winner only if both orders agree)
  3. Tournament with Bradley-Terry / Elo aggregation
- **Recommendation**: Option 2 minimum, optional Option 3. Strip variant labels before presenting to selector (no "Plan A" / "Plan B" framing; use blinded tokens). Randomize order. Re-run in swapped order. If results disagree, escalate to morning (E-fallback).
- **Trade-offs**: 2x compute for swap-check. Small absolute cost on the selector tier; large variance reduction.

### DR-5: Re-use `plan_comparison` event schema; do NOT introduce `plan-synthesis.md`

- **Context**: The chosen variant's content IS the synthesis result; a separate `plan-synthesis.md` artifact would duplicate `plan.md` content and create artifact-management overhead.
- **Options considered**:
  1. New `plan-synthesis.md` artifact
  2. Extend `plan_comparison` event schema
  3. Both
- **Recommendation**: Option 2. Add fields: `selection_rationale` (synthesizer's per-axis differentiator citations), `selector_confidence` (calibrated rating), `position_swap_check_result` (passed / disagreed / abstained), `axis_routing` (per-variant axis assignments).
- **Trade-offs**: Slightly larger event payloads. Acceptable.

### DR-6: Evaluate async-notify-with-timeout (G) BEFORE autonomous synthesis design

- **Context**: The discovery's framing collapses two distinct cases: (a) operator unreachable for 8 hours, (b) operator can respond to phone push within an hour. Plan selection is a 30-second decision. The existing deferral system `[requirements/pipeline.md:87-95]` and `~/.claude/notify.sh` `[requirements/pipeline.md:28]` together already support an async-notify path that resolves case (b) without autonomous synthesis.
- **Options considered**:
  1. Skip async-notify; build autonomous synthesis
  2. Build async-notify-with-timeout (push phone, hold round, resume on response or N-min timeout → defer-to-morning)
  3. Build both as complementary tiers
- **Recommendation**: Option 2 first. Cost out the async-notify alternative against autonomous synthesis. If async resolves 80%+ of cases at one-tenth the design cost, autonomous synthesis may be unnecessary.
- **Trade-offs**: Adds an evaluation step before any synthesis design. Aligned with DR-1 (defer until baseline) — async-notify is a low-cost intervention that can be measured against the same instrumentation.

### DR-7: Meta-recursion epistemic caveat (analog to /critical-review-scope-expansion-bias DR-7)

- **Context**: The artifact under review was produced by a /research-pattern parallel dispatch (Codebase / Web / Tradeoffs / Adversarial agents converging on a synthesizer's recommendation, exactly per `[plugins/cortex-interactive/skills/research/SKILL.md]`'s architecture). The artifact's recommendations include guidance on which parallel-dispatch architecture cortex should adopt for plan-vs-plan synthesis. This is structurally circular: a /research-pattern dispatch is recommending /research-pattern (or its prompt-tightened variant per DR-3 Option 4).
- **Disposition**: This DR exists to surface the circularity, not to invalidate the recommendations. By the standard set in `[research/critical-review-scope-expansion-bias/research.md]` DR-7 (*"the recursion is a limitation of this research, not a confirmatory frame… one data point of circumstantial evidence — not proof and not disproof"*), the recommendations should be read as a single data point of circumstantial evidence about parallel-pattern viability, not as a /research-pattern self-validation. The /research SKILL.md audit caveat in Adjacent Infrastructure (above) is consistent with /research-pattern being *less* swayed than pre-fix /critical-review, not bias-immune.
- **Cross-ref**: This caveat applies symmetrically across DR-3 (regardless of which option ships) and DR-4 (whose mitigations are a /research-pattern-recommended scaffold). DR-1's call for empirical observation applies here too: if the /research-pattern (or DR-3 Option 4 tightening) produces a flawed plan-vs-plan synthesizer in production, that observation re-runs the prior in a fresh discovery — not in this artifact's recommendation chain.

## Open Questions

- **[LOAD-BEARING] Will the team's roadmap commit to unattended overnight critical-tier plan-phase invocation?** This question gates the entire artifact. The autonomous path does not exist today (Q4); DR-1's "defer until baseline" cannot accumulate signal until the path exists; DR-6's async-notify has nothing to notify on. **If yes**: the discovery's primary deliverable should be the path-building epic (e.g., `cortex overnight start --include-unrefined` or similar) as the zeroth-zeroth epic, with DR-1's instrumentation following it. **If no / unclear**: reduce scope to async-notify-with-timeout (DR-6 alone) for the existing interactive `/cortex-interactive:lifecycle plan` flow when the operator is mid-session-but-away, drop DR-1/DR-2/DR-3, treat synthesis design as out-of-scope until the path exists. **If maybe**: gate this discovery on a roadmap conversation; produce the conversation-output as the discovery's only artifact.
- **Does `~/.claude/notify.sh` reach the operator reliably enough to ground a 60-min-timeout async path?** Empirical question requires deployment data.
- **If DR-3 Option 4 (prompt-tightening) is shipped, what is the strategy-level distinction taxonomy?** Needs to be specified in the §1b plan-agent prompt: named architectural-pattern categories or a per-spec instruction template? Cannot answer until prompt-tightening is implemented; deferred to that work.
- **What confidence threshold defines "selector low-confidence → defer to morning" (DR-4 escalation)?** Needs calibration probes (planted-flaw test, identical-variants tie test) — neither is formalized in retrieved literature, so we'd be designing from scratch.
- **Should the `plan_comparison` schema extension (DR-5) be backward-compatible or versioned?** Existing 4 events have v1 schema; v2 needs migration semantics.

---

## Appendix: Hybrid-validity invariants (if Architecture B were ever pursued)

For reference only — DR-2 rejects Architecture B. If a future re-evaluation flips that decision, any hybrid-coherence checker MUST enforce:

1. **Files/Verification closure (per task)** — already required `[plan.md:204-205]`; hybrid must preserve task-by-task after composition
2. **Cross-task file closure** — every file referenced in any `Verification` field must be either in `Files` of some task in the same plan, or a pre-existing repo file
3. **Dependency-graph integrity** — every value in `Depends on` must reference an existing task number after renumbering
4. **Acyclic dependencies** — composed `Depends on` graph must remain a DAG
5. **Architectural-strategy consistency** — all tasks reconcilable to a single `Overview` architecture (hardest to check automatically)
6. **Caller-enumeration completeness** `[plan.md:207-211]` — re-run post-composition; hybrid may add callers source-variant didn't enumerate
7. **No self-sealing verification** `[plan.md:64-66, 230-231]` — verification must not reference artifacts the same task creates solely for verification
8. **Wiring co-location preserved** `[plan.md:179-183]` — `bin/cortex-*` deploy and consumer wiring must stay in the same task; parity-check fails otherwise
9. **Complexity classification preserved** `[plan.md:186-197]` — task `Complexity` tier must remain valid for `Files` footprint after composition
10. **Scope-boundary union-not-intersection** — `Scope Boundaries` is intersection across variants (only items both exclude); `Files` set is union; mistaking one for the other is a likely synthesizer bug

Invariants 1-4 are mechanically checkable; 5, 7, 10 require semantic review; 6, 8, 9 are mechanically checkable with codebase-aware tooling (cortex-check-parity already covers #8).
