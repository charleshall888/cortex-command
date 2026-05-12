# Research: vertical-planning

## Premise (from user)

Dexter Horthy (HumanLayer) talk *"Everything We Got Wrong About Research-Plan-Implement"* (Coding Agents Conference, 2026-03-03) argues that **outlines force vertical planning** and **models default to horizontal plans**. The user's observed pain: spec/plan documents are too dense to skim, so they go un-read. The hypothesis: an outline-shaped artifact would help both human review and agent rigor (explicit checkpoints, dependency tree, ordering).

This research went through two passes — initial breadth-first survey, then four parallel deep-research streams (primary-source dive, codebase audit, adversarial pressure-test, empirical/design-space). The deep pass materially changed the picture.

## Headline (after deep pass)

1. **The load-bearing rigor claim is not empirically grounded.** No peer-reviewed work shows outline-first plans reduce AI-agent error vs flat task lists, holding other variables constant. Practitioner claims trace to a single upstream source (HumanLayer) that **retracted its own predecessor framework** in the same writeup.
2. **Cortex already has the universal primitives.** Across 7 surveyed frameworks, the only universal elements are dependency-aware decomposition, vertical-slice discipline, and per-task verification. Cortex has all three via `Depends on: [N,M]` + parallel-dispatch + critical-review. Structure-outline-as-separate-artifact is idiosyncratic to QRSPI.
3. **Anthropic's official Skills docs are silent on this entire pattern family.** No mention of outlines, vertical slices, structure outlines, or checkpoints in the Skills overview.
4. **Real Claude users are abandoning more-structured plans** (Claude Code issues #12337, #12366) — adopting outlines moves cortex toward the failure mode users are escaping.
5. **The original recommendation (in-place `## Outline` section, "Alt-D") survives but is not the strongest move.** Cheaper-and-better alternatives: **H (status quo + measure first)**, **J (topological-sort renderer with critical-path)**, **I (spec-side phase tagging with rendered outline)**.
6. **CLAUDE.md OQ3 applies**: cortex's policy requires citing a specific `lifecycle/<feature>/events.log` or `retros/<date>.md` line when adopting a remediation. The horizontal-plan failure mode is currently **anticipated, not observed in cortex's own evidence**.

## Research Questions

1. **What does the talk specifically propose, and what is the framework?**
   → **CRISPY** (7 stages: Classify → Research → Design Discussion → Structure Outline → Plan → Implement → Yield) and its evolution **QRSPI** (8 stages). The new layer is **Stage 4: Structure Outline** — ~2 pages of markdown, "C header file" analogy, listing vertical-slice phases + testing checkpoints before the detailed Plan stage.
   → **However**: primary-source dive could not retrieve the video transcript (every transcript service tried failed). Horthy's own production prompts at `humanlayer/.claude/commands/{research_codebase,create_plan,implement_plan}.md` **do not contain** "structure outline" — confirming the term is post-talk. There is no Horthy-authored example or template anywhere on the public web. The closest filled-in template is **community-built** at `matanshavit/qrspi/.claude/commands/qrspi/4_structure.md`. [Stream-A: Primary-source dive]

2. **Are the three quoted claims verbatim?**
   → **#1 ("Models default to horizontal plans. The structure outline is the most reliable way to force vertical planning — more reliable than any prompt instruction.")**: NOT verifiable in any retrievable primary or close-secondary source. The vertical/horizontal contrast is well-attested across multiple sources but the "more reliable than any prompt instruction" superlative is not. **Treat as paraphrase, not Horthy verbatim.**
   → **#2 ("A 1,000-line plan contains as many surprises as 1,000 lines of code.")**: Closely supported but smoothed. Heavybit-attributed verbatim Horthy: *"A 1,000-line plan tends to produce about 1,000 lines of code, so there was no actual reading 'savings.'"* and *"Don't read the plans. Please read the code."*
   → **#3 (three RPI failure modes)**: All three well-attested. Instruction-budget verbatim from co-founder Kyle: *"frontier LLMs can follow about 150 to 200 instructions with good consistency."* Magic-words verbatim: *"the difference between good and bad results was a single line: 'Work back and forth with me, starting with your open questions and outline before writing the plan.'"* Plan-reading-illusion well-supported; the label itself is a secondary-source coinage.
   → **Critical nuance**: Horthy explicitly retracts his earlier "review the plan, not the code" advice. *"I was wrong. I am humble enough to admit when I was wrong."* The structure outline is a fix for a problem he himself created. **Cortex would be importing v2 of a framework whose v1 was actively harmful.** [Stream-A]

3. **Where does cortex's current `plan.md`/`spec.md`/`index.md` sit on the vertical/horizontal axis? (Quantitative)**
   → **138 plans across `lifecycle/` + `lifecycle/archive/`. 1,044 total tasks. Mean plan = 152 lines, max = 379. Max single-task Context = 804 words.** Task-count distribution: median 7, p90 14, max 20. `[cortex_command/pipeline/parser.py:282-329]`
   → **Dependency shape**: 20 flat (all `none`), 18 linear chains, **97 DAG-with-parallelism**, 3 unparseable. The DAG already supports vertical execution when the agent decomposes that way.
   → **Vertical-slice qualification by heuristic** (Task 1 contains `minimal/stub/skeleton/scaffold/bootstrap/baseline` AND later tasks contain `replace/harden/expand/wire/broaden`): **8/138 (5.8%)**. Confidence is low because the heuristic is rough. Manual inspection of one (`rebuild-overnight-runner-under-cortex-cli`) shows it is incremental but not "thin end-to-end thread first" — it builds module-by-module, not slice-by-slice.
   → **Zero plans use `## Phase N:` headings; zero have `## Outline` sections; zero reference "vertical slice / walking skeleton / tracer bullet."** No precedent for phase-axis structure. [Stream-B]
   → **Spec shape**: 140 specs, mean 101 lines, max 291. Median 9 requirements. **Only 62/140 (44%) use any MoSCoW token**; should-have/won't/could-have are sparse. MoSCoW classification is enforced by S3 but not consistently surfaced. [Stream-B]

4. **What does the cortex plan parser actually require, and what would break under each design?**
   → **Single parser path**: `cortex_command/pipeline/parser.py:282-329` (`parse_feature_plan` + `_parse_tasks`). Required: `# Plan: <name>` H1; `### Task N: description` headings; task-body terminator at next `### Task` OR next `^## ` heading OR EOF; `Files`, `Depends on`, `Complexity` (defaults to `simple`), `Status` per task. `Depends on` regex extracts `\d+` only. Consumers: `feature_executor.py:529` (overnight per-task dispatch), `batch_plan.py:15` (batch rendering). [Stream-B]
   → **Hard break**: tasks nested under `## Phase N:` headings between `## Tasks` and tasks → first task body terminates at next `## Phase 2:`, fields after the boundary parse as empty/missing, dispatch silently flattens. **No diagnostic.**
   → **Hard break**: `Depends on: phase-1` → regex extracts `[1]`, points to Task 1. **Wrong semantics, no error.**
   → **Soft break (likely OK)**: top-of-doc `## Outline` section ABOVE `## Tasks`. Parser is task-heading-anchored, would still find all `### Task` headings. Overview-section extractor might match the wrong section depending on order — manageable.
   → **The dual-source mirror burden**: any change to canonical `skills/lifecycle/...` propagates to `plugins/cortex-core/skills/lifecycle/...` via `just build-plugin`. Pre-commit drift hook enforces. Adding an artifact doubles the file count under regenerated mirror. [Stream-B]

5. **Does cortex already enforce vertical (slice-first) ordering anywhere?**
   → Implicitly via `Depends on: [N, M]` and parallel-dispatch. The format does not *require* tasks to be ordered as vertical slices — plans can still be horizontal (all DB first, all API second) and pass orchestrator review. **P1–P8 checklist gates have no phase-grouping or checkpoint check.** `[skills/lifecycle/references/orchestrator-review.md:152-165]`
   → No "checkpoint" concept distinct from per-task Verification. Per-task Verification ≠ a state-of-system gate.

6. **Is cortex's instruction budget plausibly above Horthy's 150–200 cap?**
   → Lifecycle reference set + lifecycle SKILL.md + critical-review SKILL.md = **2,148 lines** total. **43% over the ~1,500-line threshold.** Lines ≠ instructions, but directive density is high in `plan.md` (multiple nested numbered subsections, hard-gate tables, §1b critical-tier dual-plan flow at ~110 lines). Adopting outlines adds gate text + template text to this surface, exacerbating the budget. [Stream-B]

7. **Does outline-first measurably improve agent rigor? (load-bearing claim)**
   → **No rigorous empirical support specific to AI coding-agent plans.** [Stream-D]
   → **Closest adjacent peer-reviewed evidence**:
     - **Plan-and-Solve Prompting** (Wang et al., arXiv 2305.04091): plan-then-solve beats zero-shot CoT 5–15 pts on math/symbolic benchmarks (GSM8K, AQuA, SVAMP, StrategyQA). On GPT-3. **Not coding tasks. Old model.** Quality 4/5.
     - **PlanBench / "LLMs Can't Plan"** (Valmeekam et al., NeurIPS 2023, arXiv 2402.01817): GPT-4 ~34% on BlocksWorld-Hard, Claude 3 Opus ~59%. **Structuring the prompt does NOT rescue planning errors** — diagnosis is that LLMs cannot plan, period, regardless of prompt shape. Quality 5/5. Direct refutation of the rigor claim.
     - **"Why Reasoning Fails to Plan"** (arXiv 2601.22311): long-horizon failures stem from step-wise greedy policies, NOT from how tasks are decomposed. *"Improving local reasoning alone is insufficient … regardless of whether obtained via prompting."* Quality 5/5.
     - **"The Prompting Inversion"** (arXiv 2510.22251): on GPT-4o, structured prompts beat zero-shot 97% vs 93% on GSM8K; **on GPT-5, the inversion** — structured prompts 94% vs zero-shot 96.36%. **As models improve, structured scaffolding stops helping and starts hurting** via "hyper-literal interpretation" and "over-constraint." Threatens the rigor claim against current Opus/Sonnet. Quality 4/5.
     - **BOAD** (arXiv 2512.23631): auto-discovered hierarchical agent structures beat manually-designed roles on SWE-bench, *"indicating human-crafted roles can be misaligned with LLM behavior."* **Direct counter-evidence to hand-authored outlines.** Quality 5/5.
     - **MAST taxonomy** (arXiv 2503.13657): "poor task decomposition" — too granular OR too broad — is a catalogued failure mode. **Both over- and under-decomposition fail.** Quality 3/5.
   → **Practitioner claim ("2-3x productivity gains" with structure outlines)**: anecdote-grade. No held-out benchmark, no controlled ablation, sample of one team's workflow. Quality 1/5.
   → **Practical implication**: the strong claim ("forces the agent to think better") should be downgraded to a hypothesis. The weak claim ("helps the human skim") is well-supported by general document-design evidence and doesn't need LLM literature.

8. **What do adjacent prior-art frameworks actually do? (Triangulation)** [Stream-C]

| Element | CRISPY | A. Osmani | PRPs | Spec Kit | EvanFlow | Erturk | Anthropic Skills | **In ≥3** |
|---|---|---|---|---|---|---|---|---|
| Dependency-aware decomposition | yes | yes | yes (phases table) | yes (`[P]` markers) | yes | implicit | no | **YES** |
| Vertical-slice discipline | yes | yes | implicit | yes | yes | yes | no | **YES** |
| Per-task verification | yes | yes | yes (validation cmds) | yes | yes (RED test) | no | no | **YES** |
| Separate "outline / structure" file | **yes** | no | no (inline phase table) | no (split across 3 files) | no | no | no | **NO — idiosyncratic to CRISPY** |
| C-header-style signatures pre-plan | **yes** | no | no | partial (`contracts/`) | no | no | no | **NO — idiosyncratic to CRISPY** |
| Explicit checkpoints | yes (8 stages) | yes (every 2-3 tasks) | yes (Ralph loop) | partial | yes (HITL gates) | no | no | **YES, mechanism varies wildly** |

   → **Universal**: dependency decomposition, vertical-slice discipline, per-task verification. **Cortex already has all three.**
   → **Idiosyncratic to CRISPY**: separate outline artifact, C-header signatures, eight discrete stages.
   → **Frameworks disagree on what a "checkpoint" is** — stage gate, test gate, human-approval pause, validation command. Adopting "checkpoints" without specifying which mechanism imports incoherence.

9. **Is HumanLayer's framing the upstream source for everyone else?**
   → Yes — Addy Osmani, vibecoding.app, Red Hat "harness engineering," and others *cite or echo HumanLayer's framing*. This is one upstream source diffusing through the practitioner ecosystem, not independent confirmation. Erturk's vertical-slice post (independent) does NOT mention outlines as the mechanism — he just commits vertically. **Anthropic's official guidance (independent) is silent.** [Stream-C]

10. **Does the claim transfer to cortex's autonomous overnight runner?**
    → **Probably worse-suited than to interactive use.** HumanLayer's setup is interactive pair-coding with humans reviewing plans. Cortex's overnight runner is autonomous with a critical-review tier. The "plan-reading illusion" Horthy warns about is *more dangerous* in cortex's autonomous setting (no human pause to catch outline↔plan drift). **The remedy (more plan artifact) is *worse-suited* to autonomous runs than to interactive ones**, because each new artifact adds a drift surface that no human is watching in real time. [Stream-C]

## Codebase Analysis (snapshot)

**Plan size, real numbers** [Stream-B]:

| Metric | Value |
|---|---|
| Total plans | 138 (active 87, archive 51) |
| Lines: p25/p50/p75/p90/max | 87 / 141 / 213 / 256 / **379** |
| Tasks/plan: p50/p90/max | 7 / 14 / **20** |
| Total tasks | 1,044 |
| Max Context-words/task | **804** (`integrate-autonomous-worktree-option-into-lifecycle-pre-flight` Task 2) |
| Plans with DAG-with-parallelism | 97/138 |
| Plans qualifying as vertical-sliced (heuristic) | **8/138 (5.8%)** |

**Spec size**: 140 specs, mean 101 lines, max 291. Median 9 requirements. MoSCoW token usage: 62/140 (44%) — should-have, won't, could-have all sparse.

**Plan parser path**: single point at `cortex_command/pipeline/parser.py:282-329`. Hard-breaks on nested `## Phase N:` headings inside `## Tasks`. Soft-OK on top-of-doc outline sections.

**Orchestrator-review checklist surface**: R1–R5 (research), S1–S6 (spec), P1–P8 (plan). `[skills/lifecycle/references/orchestrator-review.md:127-165]`. New gate would slot at P9 / S7.

**`index.md`** is 16–18 lines, YAML frontmatter + wikilink stubs. Written by `skills/lifecycle/SKILL.md:108-142`, appended by phase references. Used by reviewer for tag-based requirements loading. **Repurposing it as outline surface would break the reviewer's tag-extraction logic.**

**Existing related lifecycle work**:
- **`backlog/019` (complete)**: tightened acceptance criteria. Solved authoring-time clarity but not review-time digestibility.
- **`research/openspec-for-lifecycle-specs/decomposed.md`**: looked at delta specs / structural validation. Concluded openspec's three-way artifact split was not worth adopting because cortex already has research/spec/plan. Did not consider outlines or vertical-slice phasing. **Constraint: that prior conclusion ("don't add a 4th artifact") pushes this discovery toward in-place section over new file.**
- **Critical-tier `Architectural Pattern` field** (5-element closed enum): the only existing top-of-doc structural anchor. Closest precedent for adding a structural gate.

**Cross-skill integration**: spec template is duplicated between `skills/lifecycle/references/specify.md` and `skills/refine/references/specify.md` — any change must land in both. Critical-review reads plan as prose (no parser dependence). Discovery decomposition produces backlog tickets, not lifecycle artifacts.

## Web & Documentation Research

**Primary source (Horthy talk)**: NOT retrieved. Multiple transcript services tried (youtube-transcript.io, kome.ai, tactiq.io, etc.) — all failed for `YwZR6tc7qYg`. Wayback blocked. Conclusion: Horthy has not published a primary-source structure-outline template. The "~2 pages, signatures + types + phase order + verification" definition exists only in second-hand summaries. [Stream-A]

**Closest-to-primary**: Heavybit interview write-up (verbatim Horthy quotes), Horthy's own production prompts (which DON'T contain "structure outline"), `humanlayer/advanced-context-engineering-for-coding-agents/ace-fca.md` (Aug 2025, pre-CRISPY).

**Adjacent prior art** (full content retrieved by Stream C):
- **Addy Osmani `agent-skills/skills/planning-and-task-breakdown`**: process-discipline skill. Vertical slicing mandated, XS-XL task sizing, checkpoints every 2-3 tasks. Dependency tree inline as ASCII. *No separate outline file.*
- **Wirasm/PRPs-agentic-eng**: PRP = "PRD + curated codebase intelligence + agent runbook." Phases live in a *table inside plan.md*. Has Ralph Loop validation.
- **HumanLayer `12-factor-agents`**: HumanLayer's *other* framework — does not mandate outlines. Undercuts CRISPY's universality claim.
- **EvanFlow**: TDD-driven; checkpoints are *human-approval gates* (mandatory pause before git ops), not outline sections.
- **GitHub Spec Kit**: Sequential constitution → spec → plan → tasks. Vertical slices organized by user story; `[P]` parallel markers. *No outline file.*
- **Mehmet Erturk**: Ships by *commit shape*, not artifact shape. **Direct counter-evidence**: a practitioner gets vertical slices without any of the proposed CRISPY scaffolding.
- **Anthropic Skills overview**: Mentions *none* of: planning outlines, vertical slices, structure outlines, checkpoints, task breakdown. **Strong negative evidence.**

**Real-user signal on more-structured plans**: Claude Code GitHub issues #12337 ("New plan mode is too verbose… one conversation already used 42% of my 5-hour quota") and #12366 ("plans 6-10x longer than before, full of over-engineering"). Users are *abandoning* structured plan output for over-verbosity.

## Domain & Prior Art

The vertical-slice pattern is decades old (user stories, walking skeleton, tracer bullet). What is new in CRISPY is **structurally enforcing the slice in an AI agent's planning artifact** — using artifact shape (not prompt instruction) as the enforcement mechanism.

**That mechanism claim is the load-bearing one and is not empirically grounded** (see Q7).

**Provenance hazard**: Adopting CRISPY's structure outline means importing v2 of a framework whose v1 (RPI) the same author retracted. Per Heavybit verbatim Horthy: *"I was wrong … Don't read the plans. Please read the code."* Cortex would be adopting an unverified remediation for a HumanLayer-team-specific failure mode that cortex has not observed in its own evidence.

## Feasibility Assessment (expanded)

**Original alternatives (A–H) plus deep-pass additions (I–L):**

| Alt | Effort | Risks | Description |
|----|--------|-------|-------------|
| **A** — New `outline.md` artifact | M | Adds phase, slows lifecycle 5–10 min/feature; outline-plan drift; mirror burden | CRISPY-faithful: separate file between spec and plan |
| **B** — Restructure `plan.md` outline-first | M | **Hard parser break** at `cortex_command/pipeline/parser.py:282-329`; legacy plans need migration | Outline header + phases + tasks nested |
| **C** — Promote `index.md` to outline | S | Breaks reviewer's tag-extraction; conflates navigation with content | Repurpose existing wikilink TOC |
| **D** — In-place `## Outline` section | S-M | Outline duplicates task summaries; review fatigue may worsen for medium plans | Single template revert; medium drift risk |
| **E** — Mermaid as embedded artifact | S | Mermaid render varies; agents must author valid syntax | Single visual + retain flat list |
| **F** — Two-phase plan (outline → plan) | L | Substantial workflow change; depends on unsupported "forces reasoning" claim | Outline = approval surface, plan = agent-only |
| **G** — Tier scope (critical/complex only) | XS-S | Combinable with any base; matches Plan-and-Solve evidence (helps where horizon is long) | Apply only at criticality threshold |
| **H** — Status quo + measure first | XS | Defers improvement; risk of indefinite stall — but measurement is cheap | Instrument review skips, plan re-reads, agent failure modes |
| **I** — Spec-side phase tags (NEW) | S | Tags decorative; agents still horizontal inside phases | `Phases:` in spec, `Phase: <name>` per task, outline rendered |
| **J** — Topological-sort renderer (NEW) | S-M | Bad dependency data → misleading viz, but surfaces existing bugs vs creating new ones | `cortex plan-render --outline` consumes existing DAG, layered Mermaid + critical path. Zero authoring change. |
| **K** — Plan-as-questions (NEW) | M | Agents skip questions and freelance; medium rollback | Decision tree, not numbered list. Forces conditional thinking. |
| **L** — Slice-budget hard cap (NEW) | M | Artificial slice boundaries; review fragmentation | Token-counted gate making horizontal accumulation mechanically impossible. Generation-time constraint, not approval surface. |

**Top 5 picks (post-deep-pass)**:

| Alt | Effort | Best-case win | Worst-case failure | Rollback cost | Drift risk |
|---|---|---|---|---|---|
| **H** (status quo + measure) | XS | Avoid building the wrong thing; gather own evidence | 2-week delay | Zero | None — no artifact to drift |
| **J** (topological renderer) | S-M | Human review-fatigue solved with no authoring change; bonus: surfaces bad Depends-on declarations | Bad dep data → misleading viz | Low — stop rendering | Low — viz is recomputed, can't drift |
| **I** (spec-side phase tags) | S | Slice decision lives at spec time; outline is tag rollup | Tags decorative; agents horizontal inside phases | Low — drop the field | Low — single source of truth |
| **D** (in-place `## Outline` in plan.md) | S-M | Both outline and tasks in one file → cannot drift across files | Outline duplicates summaries; review fatigue worsens | Low-medium | Medium — outline and body can disagree as plans evolve |
| **G** (tier-scoped, paired with any base) | XS-S | Limits blast radius; matches Plan-and-Solve evidence | Tier classifier wrong | Low — adjust threshold | Low — same as base alt, smaller surface |

## Decision Records (revised)

### DR-1 (REVISED): Where to start — measurement vs adoption

- **Context**: Original recommendation was D (in-place outline section). Deep pass shows the rigor claim is unsupported and the human-skim claim is real but cheaply addressable via J or I.
- **Options**: Adopt D directly (original); start with H (measure) → escalate to J/I; start with J (renderer) immediately as low-cost win.
- **Recommendation**: **Start with H, escalate to J or I.** Two-week measurement of the actual problem (review fatigue, plan-reading skip rate, plan-task ordering) before committing to artifact change. The user's pain ("I find myself not reading specs and plans") is the proper success metric — measurable via session telemetry on plan-file reads, not via "we built an outline."
- **Trade-offs**: Defers improvement by ~2 weeks. But the cost of building D and finding it didn't help (or worse, finding it duplicated / drifted) is much higher than 2 weeks of measurement.

### DR-2 (REVISED): Apply to all tiers vs critical/complex only

- **Context**: User said "all" but the empirical evidence (Plan-and-Solve) suggests scaffolding helps mostly on long-horizon tasks. Prompting Inversion suggests scaffolding can hurt on capable models.
- **Recommendation**: **Default-on for `critical/complex`, default-off for `simple/low`** — invert the original recommendation. Trivial features should not pay outline overhead. Critical features already have the dual-plan synthesizer flow which is the higher-leverage rigor mechanism.
- **Trade-offs**: Inconsistent shape across tiers; matches existing skip-rule mental model.

### DR-3 (UNCHANGED): Visual dependency tree (Mermaid) vs text-only

- **Context**: Multiple prior-art sources include Mermaid. Cortex agents can author Mermaid; the dashboard could render it.
- **Recommendation**: **Mermaid optional, text-outline required** *if* outline is adopted. But under the J alternative, Mermaid is **rendered**, not authored — which is strictly better.

### DR-4 (UNCHANGED): Differentiated outline shapes for spec vs plan

- **Recommendation**: If outlines adopted, **differentiated formats**. Spec outline = "Requirements at a Glance" (MoSCoW grouping + 1-line acceptance summary). Plan outline = "Phase Outline" (phases + checkpoints + task IDs per phase). Two templates to maintain — but each fits its artifact's role.

### DR-5 (REVISED): Enforcement mechanism

- **Context**: Original recommendation was orchestrator gate. Deep pass shows the cheaper experiment is **a single P-check that flags plans where >60% of tasks share a single layer (DB-only, API-only, UI-only)** — directly addressing the horizontal-plan failure if it actually exists.
- **Recommendation**: **Add the horizontal-plan P-check first** (one orchestrator-review gate, ~1-day work). If it fires on real plans, that's evidence the horizontal failure mode exists in cortex. If it never fires, the rigor claim doesn't apply and adoption rests entirely on the human-skim claim.
- **Trade-offs**: Detector is heuristic; agent could game it; but cheap to ship and informative regardless.

### DR-6 (NEW): Provenance disclosure

- **Context**: We are considering adopting v2 of a framework whose author retracted v1. The "structure outline" is community-reified (matanshavit/qrspi); no Horthy-authored template exists.
- **Recommendation**: **If we adopt, document this provenance explicitly in the skill reference** — so future readers know they're using community interpretation, not a Horthy spec. Avoid quoting the unverified "more reliable than any prompt instruction" claim as fact in cortex docs.

## Open Questions

These are now the questions that actually decide the path forward:

1. **Have we actually observed the horizontal-plan failure mode in cortex?** Per CLAUDE.md OQ3, adoption needs an artifact-link: a `lifecycle/<feature>/events.log` or `retros/<date>.md` line where a horizontal plan caused a real regression. **If no such evidence exists, the adoption case for the rigor claim collapses to anticipation, not observation.** What evidence are we willing to wait for?

2. **Is the goal "help me skim" or "force the agent to think better"?** These are different problems. Skim is solvable cheaply (J renderer or I spec-tags). Agent-rigor is unsupported empirically and may or may not transfer to cortex's autonomous overnight runner.

3. **Is the bigger problem actually plan length, not plan structure?** Max single-task Context = 804 words. Mean plan = 152 lines. The cheapest skim improvement may be a **hard cap on Context-field word count with overflow into per-task appendix files** (variant of L).

4. **Do we accept the empirical case as inconclusive?** If yes, the lowest-regret moves are H (measure) and J (renderer). If we want to act on the practitioner-grade evidence anyway, we go to D or I.

5. **Critical-tier scope**: do we apply outlines (if adopted) only to critical-tier where the dual-plan synthesizer already runs, or also to complex-tier where the heaviest plans actually live?

6. **`index.md` interaction**: per Stream-B, repurposing `index.md` as outline (Alt-C) breaks reviewer tag-extraction. Removing C from consideration?

7. **Legacy plans**: gate skips them, backfilled retroactively, or new gate applies only to plans created after rollout?

8. **Are we OK shipping a horizontal-plan detector P-check (DR-5) as the first move regardless?** It's one orchestrator gate, ~1-day work, immediately informative.

## Epistemic notes

- **Primary video transcript was not retrieved** despite multiple transcript services tried. All Horthy quotes are sourced from third-party interviews/summaries, with claim #1 ("more reliable than any prompt instruction") not verifiable in any retrieved corpus.
- **Empirical validation of the rigor claim is practitioner-grade (1/5)**, with peer-reviewed adjacent literature pointing *away* from prompt-structuring as the lever for LLM planning failures (Kambhampati line; Prompting Inversion; BOAD).
- **Cortex's instruction-budget surface (2,148 lines) is already 43% over Horthy's threshold** — adopting outlines pushes further into the regime he warns against.
- **Anthropic's official Skills docs are silent on outlines, vertical slices, checkpoints**. Strong negative evidence: if Anthropic believed structure outlines were load-bearing for skill execution, they'd say so.
- **Real Claude Code users are abandoning more-structured plan output** (issues #12337, #12366). Adopting outlines moves cortex toward the failure users are escaping.
- **The strongest argument for adoption** is the human-skim claim, which doesn't require LLM literature support. The cheapest test of that claim is the J renderer (no authoring change, computes outline from existing DAG).
- **The strongest argument against adoption** is provenance: importing v2 of a framework whose author retracted v1, with no observed cortex-side failure to remediate.

## Citations

- [Everything We Got Wrong About Research-Plan-Implement — Dexter Horthy (YouTube — transcript not retrieved)](https://www.youtube.com/watch?v=YwZR6tc7qYg)
- [HumanLayer Heavybit interview — verbatim Horthy quotes](https://www.heavybit.com/library/article/whats-missing-to-make-ai-agents-mainstream)
- [HumanLayer ace-fca.md (pre-CRISPY)](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)
- [Horthy's actual production prompts (humanlayer/.claude/commands/)](https://github.com/humanlayer/humanlayer/tree/main/.claude/commands)
- [matanshavit/qrspi — community structure-outline template](https://github.com/matanshavit/qrspi)
- [From RPI to QRSPI (Alex Lavaee — close-listener secondary)](https://alexlavaee.me/blog/from-rpi-to-qrspi/)
- [CRISPY framework field notes (tonyrosario)](https://github.com/tonyrosario/coding-agents-field-notes/blob/main/research/2026-03/coding-agents/crispy-rpi-framework.md)
- [Plan-and-Solve Prompting (arXiv 2305.04091)](https://arxiv.org/abs/2305.04091)
- [PlanBench (arXiv 2206.10498)](https://arxiv.org/abs/2206.10498)
- [LLMs Can't Plan, But Can Help Planning in LLM-Modulo (arXiv 2402.01817)](https://arxiv.org/abs/2402.01817)
- [Why Reasoning Fails to Plan (arXiv 2601.22311)](https://arxiv.org/abs/2601.22311)
- [The Prompting Inversion (arXiv 2510.22251)](https://arxiv.org/html/2510.22251v1)
- [BOAD: Discovering Hierarchical SE Agents (arXiv 2512.23631)](https://arxiv.org/pdf/2512.23631v1)
- [MAST taxonomy (arXiv 2503.13657)](https://arxiv.org/html/2503.13657v3)
- [Tree of Thoughts (arXiv 2305.10601)](https://arxiv.org/pdf/2305.10601)
- [Addy Osmani planning-and-task-breakdown SKILL](https://github.com/addyosmani/agent-skills/blob/main/skills/planning-and-task-breakdown/SKILL.md)
- [Wirasm/PRPs-agentic-eng](https://github.com/Wirasm/PRPs-agentic-eng)
- [HumanLayer 12-factor-agents](https://github.com/humanlayer/12-factor-agents)
- [evanklem/evanflow](https://github.com/evanklem/evanflow)
- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [Mehmet Erturk — Vertical Slices: The Only Way to Ship With AI](https://ertyurk.com/posts/full-stack-vertical-slices-the-only-way-to-ship-with-ai/)
- [Anthropic Skills overview](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- [Claude Code issue #12337 — plan mode too verbose](https://github.com/anthropics/claude-code/issues/12337)
- [Claude Code issue #12366 — plan mode over-optimizing](https://github.com/anthropics/claude-code/issues/12366)
