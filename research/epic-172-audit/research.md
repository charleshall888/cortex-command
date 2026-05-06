# Research: epic-172-audit

Meta-audit of Epic #172 (Lifecycle skill + artifact densification + vertical-planning adoption) and its 11 children (#173–183). Goal: validate that the planned ~1,025-line reduction reduces tokens without stripping pivotal capabilities; derive a "why" baseline for each lifecycle phase; empirically grade real lifecycle artifacts against templates; and produce an independent re-decomposition diffed against the existing one.

Guiding principle (user-stated, applied throughout): **Prescribe What and Why, not How.** Models (Opus 4.7+) are increasingly capable of figuring out method. Rails worth keeping ensure the agent extracts the right decisions, asks the right questions, and hits the right gates — not how it gets there.

## Research Questions

1. **Why baseline.** For each lifecycle phase, what failure mode does it exist to prevent, and what is load-bearing vs. ceremonial?
   → **Answered.** Per-phase Why is concentrated in ~10% of corpus surface area; HOW-prescription is ~50%. Allocation is misaligned with retro evidence (which traces failures to WHY-class concerns).

2. **Empirical per-section value.** Which sections of real lifecycle artifacts are read downstream, edited during use, cited in retros, vs. produced once and never re-touched?
   → **Answered.** Top load-bearing: plan.md `## Veto Surface` (13 retro mentions), review.md Stage 1 (machine-iterates every spec requirement), spec.md `## Requirements`+`## Non-Requirements`. Top waste: research.md `## Requirements & Constraints` (re-quotes `requirements/project.md`), plan.md `## Scope Boundaries` (duplicates spec Non-Requirements), review.md `## Stage 2: Code Quality` (template-fill boilerplate). All artifacts are write-once across 3/3 archived samples.

3. **Pivotal-piece check.** Which of Epic #172's ~1,025 cut lines are load-bearing in ways the prior audit missed?
   → **Answered, contested.** 8 contested cuts identified. Net direction: prior audit understates how much HOW-prose can be trimmed (~155–180 additional lines available in Constraints tables, plan.md §1b orchestration prose, critical-review Step 4 anchor-check prose, slugify HOW) but overstates how much routing-/synthesizer-protective WHAT/WHY can be cut without consequence.

4. **Vertical-planning replacement scope.** Can `## Outline` / `## Phases` from #182 *replace* (not just add to) existing template content?
   → **Answered, yes — significantly.** A single `## Outline` can absorb plan.md's `## Scope Boundaries` + `## Veto Surface` + `## Verification Strategy` (Candidate A). Plus consolidation of plan.md §1b.b + §3 dual-template (Candidate C). Original audit evaluated only addition.

5. **Phase-set shape.** Are any lifecycle-phase pairs mergeable?
   → **Answered.** Recommend MERGE clarify+research (boundary is mostly bookkeeping; refine already chains them). KEEP SPLIT spec+plan (user-approval-pause is load-bearing). KEEP SPLIT review+complete (review is conditional, complete is universal).

6. **Hold 1 re-challenge.** Does "keep both escalation gates" survive fresh scrutiny with #183 on the table?
   → **Answered, partial reversal.** Keep Gate 1 (Research→Specify ≥2 Open Questions) — has thin but defensible WHY. Remove Gate 2 (Specify→Plan ≥3 Open Decisions) — pure HOW, redundant with orchestrator-review S-checklist, source section is 88% ceremonial, OQ3-violation per CLAUDE.md (no F-row evidence). Still migrate surviving Gate 1 to Python hook per #183 (re-scoped).

7. **Independent re-decomposition.** Without seeing #173–183, what would the audit's natural decomposition look like?
   → **Answered.** Fresh decomposition: 9 tickets vs. existing 11. Only meaningful divergence: merge #174 + #175 + #176 (cross-skill dedup) into one ticket with named per-file sub-acceptances. All other tickets map cleanly with identical scope.

## Codebase Analysis

### Per-phase Why baseline

Each entry: failure mode prevented (with retro citation) → load-bearing What → ceremonial How.

| Phase | Failure mode prevented | Load-bearing What | Ceremonial How |
|---|---|---|---|
| **clarify** | Research/spec built on wrong premise; agent locks scope before knowing the problem [`retros/2026-04-22-2143-lifecycle-140-spec.md:5–9`, `retros/2026-04-21-2108-lifecycle-129.md:13`] | 3-dimension confidence assessment + critic dispatch + Q&A cap of 5 [`skills/lifecycle/references/clarify.md:62–86`, `clarify-critic.md:1–13,48–49`] | Tabular dimension grid `[clarify.md:33–47]`; verbatim YAML schema for events.log entry with `applied_fixes`/`dismissals` arrays `[clarify-critic.md:99–146]` |
| **research** | Agent skips read-before-design; hand-waves feasibility [`retros/2026-04-22-2143:13`, `2026-04-21-2108:5`, `2026-04-20-2156:11`] | Read-only artifact with codebase-grounded findings + Open Questions Exit Gate + dependency-verification mandate [`research.md:1–3,131–134,199–204`] | §1a parallel-agent dispatch with verbatim researcher prompt template, exact angle count, fallback ladder `[research.md:46–112]` |
| **spec(ify)** | Spec ships with hidden requirements, untestable acceptance criteria, claims about code that aren't true [`retros/2026-04-22-2143:11`, `2026-04-22-1207:5`, `2026-04-21-2108-lifecycle-127-spec.md:9`] | Binary-checkable acceptance criteria + §2b Pre-Write Verification (Git/function/path/state ownership) + Open-Decision-resolution gate + user-approval surface with Produced/Value/Trade-offs [`specify.md:81–98,118–121,155–163`] | §2a Confidence-Check loop-back with cycle counting and Sufficiency-Check bypass `[specify.md:38–78]`; §3a S1–S6 orchestrator-review checklist `[orchestrator-review.md:139–150]` (load-bearing for *calibration* but rubric repeatedly fails to catch what critical-review then catches) |
| **plan** | Plan asserts mechanisms runtime won't honor; self-sealing verification; code-budget violation [`retros/2026-04-22-1302:5`, `2026-04-22-1204-lifecycle-130-plan.md:5`, `2026-04-22-1204-lifecycle-127-plan.md:5`] | Code Budget rule + Files/Verification consistency + Caller Enumeration + Wiring Co-location + P1–P8 (esp. P4 binary-checkability, P7 no-self-sealing); `Depends on:` parser contract; for critical tier, §1b competing-plans + Opus synthesizer with swap-and-require-agreement [`plan.md:21–144,204–256,299–309`, `orchestrator-review.md:152–165`] | §1b synthesizer envelope schema with `schema_version: 2`, eight enumerated `disposition` values, last-occurrence anchor pattern; ~140-line plan_comparison v2 event JSON schema `[plan.md:99–144]`; eight worked examples of A→B downgrade rubric `[critical-review/SKILL.md:212–260]` |
| **implement** | Out-of-scope work; failed commits; spec-path drift; silent partial completions [`retros/2026-04-23-0400-lifecycle-100-implement.md:9–17`, `2026-04-22-1227:13`] | Per-task fresh-subagent dispatch; Builder Prompt instructions 1, 4, 6 (implement exactly what's specified, commit via `/cortex-core:commit`, flag self-sealing rather than self-certifying); dependency-graph batching; post-batch checkpoint via `git log HEAD..worktree/{task-name}` [`implement.md:11–46,168–202,227–249,292–301`] | Entire §1a Daytime Dispatch — 9 substeps, atomic-write Python one-liners, three-tier result-reader fallback `[implement.md:49–166]`; "no compound commands" workarounds for sandbox quirks |
| **review** | Shallow smell-test approval; missing requirements drift; reviewer-modifies-files | Two-stage gate (Stage 1 spec compliance machine-iterated 1:1 against requirements; Stage 2 code quality); structured Verdict JSON enum; Requirements Drift section + auto-apply; cycle counter with hard cap [`review.md:42–55,64–71,155–162,172–219`] | Tag-based requirements loading — case-insensitive phrase matching procedure `[review.md:11–18]`; full Reviewer Prompt Template as verbatim instruction-passing `[review.md:24–93]` |
| **complete** | "Approved" feature with failing tests; stale backlog state; lost lifecycle artifacts. *Less retro evidence; most lifecycle retros end before Complete.* `NOT_FOUND(query="complete phase failure", scope=retros/2026-04*)` | Run test command; emit `feature_complete` event; backlog write-back to `status:complete` + clear `session_id`; git workflow dispatch by branch state; artifact preservation [`complete.md:9–47,71–94,97–102`] | Backlog-index-sync 3-tier fallback chain duplicated across §2 and §3 verbatim `[complete.md:38–46,61–69]` |

### WHAT/WHY/HOW corpus classification

Across the 4 skills (lifecycle 2,476 lines incl. references, refine 924, critical-review 365, discovery 659; total ~4,400 lines):

| Category | Share | Survival under capability uplift | Examples |
|---|---|---|---|
| **WHAT** (decisions, gates, output shapes) | ~25% | Survives unchanged — defines the contract | `[clarify.md:62–86]` 5 outputs; `[plan.md:158–194]` artifact format; `[review.md:96–139]` verdict JSON; `[orchestrator-review.md:127–165]` R/S/P checklists |
| **WHY** (failure modes, intent) | ~10% | Survives — most-cited in retros | Phase-reference preambles (1 sentence each); constraints tables' "Reality" columns `[specify.md:181–187]` |
| **HOW** (step-by-step method, procedural detail) | ~50% | Largely shrinkable as model capability grows | `[implement.md:49–166]` Daytime Dispatch; `[plan.md:99–144]` plan_comparison v2 schema; `[critical-review/SKILL.md:212–260]` 8 worked examples; `[clarify-critic.md:99–146]` YAML schema |
| **MIXED** | ~15% | Case-by-case — load-bearing What backed by retro-grade Why with HOW examples | `[specify.md:81–98]` Pre-Write Checks; `[plan.md:204–236]` Wiring/Dependency/Caller; `[review.md:11–18]` tag loading |

**Headline misalignment:** Retro evidence shows almost every recurring failure traces to a WHY-class concern (intent built on wrong premise; spec asserted untrue claims; plan mechanism didn't match runtime; reviewer rubric was structural rather than semantic). Yet the surface area allocated to WHY is roughly 1/5 of the surface area allocated to HOW. That allocation directly contradicts the user's guiding principle.

### Empirical artifact value matrix (5 recent samples)

Sampled `lifecycle/archive/{unify-lifecycle-phase-detection-…, restructure-readme-and-setupmd-…, remove-dead-throttled-dispatch-wrapper-…}/`, plus in-flight `lifecycle/{fix-archive-predicate-…, remove-fresh-evolve-…}/`. Mix: 3 completed, 1 in-flight at plan, 1 in-flight at research. Token estimates use `chars/4`.

**Top 3 highest-waste sections:**

1. **research.md → `## Requirements & Constraints`** (~720 tok avg). Re-quotes `requirements/project.md` verbatim ("Complexity: Must earn its place..." in S3). 0 retro mentions. Reviewer phase loads `requirements/project.md` directly anyway `[skills/lifecycle/references/review.md:7–17]`. **Sub-agent invented section — not in lifecycle research.md template.**
2. **plan.md → `## Scope Boundaries`** (~410 tok avg). Pure duplication of spec Non-Requirements; explicit "Per spec Non-Requirements (verbatim)" / "Maps to spec.md 'Non-Requirements'" disclaimers in 3/3 archived samples. 0 retro mentions vs. Veto Surface's 13.
3. **review.md → `## Stage 2: Code Quality`** (~620 tok avg). Structurally uniform 4-bullet (naming/error/test/pattern) template-fill in N=3 samples. **Caveat (per critical-review):** 10-dir spot-check of `lifecycle/archive/*/review.md` shows ~6/10 add substantive material beyond the 4-bullet template (Minor Observations, Assessment of Known Deviations, missing-test flags). The "structurally uniform" claim is N=3 sample noise; the corpus shows roughly 40% strict-template, 60% augmented. Treat as candidate for trim/restructure rather than blanket deletion.

**Top 3 most load-bearing sections:**

1. **plan.md → `## Veto Surface`** — 13 retro mentions across `retros/`. The most-cited section in the entire artifact corpus. Acknowledged-but-unresolved-risk affordance.
2. **review.md → Stage 1 Spec Compliance** (~2685 tok avg, largest single section). Iterates every spec.md requirement 1:1 with `grep -c` / `wc -l` / `pytest` machine-checks (S3 covers 9 requirements). This is the section that makes spec.md's binary-checkable Requirements format earn its keep.
3. **spec.md → `## Requirements` + `## Non-Requirements`** pair. Requirements is iterated by review; Non-Requirements is re-cited 6× in retros and re-anchored in plan.md (the latter being the ceremonial duplicate).

**Sections present in artifact but absent from lifecycle template (sub-agent invention by `/cortex-core:research`):**

- research.md → `Requirements & Constraints` (5/5 samples), `Tradeoffs & Alternatives` (5/5), `Adversarial Review` (4/5), `Considerations Addressed` (1/5).
- spec.md → custom anchors like "Slug-and-citation grammar" (S4).

The lifecycle template's documented research.md schema `[skills/lifecycle/references/research.md:114–138]` **is not what gets written**; the research-skill's parallel-agent angles are. Implication: trimming the lifecycle template's research.md schema doesn't move the needle — the actual schema lives in `/cortex-core:research`.

**Cross-cutting structural observation:** All artifacts in 3/3 archived samples are single-commit writes — never edited collaboratively after first write. Implication: artifact section structure should optimize for **first-write quality**, not for collaborative editing affordances. Sections that exist to "make the artifact easier to revise later" don't pay their tokens — there is no later revision.

**`NOT_FOUND` markers:**
- `NOT_FOUND(query="implement.md", scope="lifecycle/**")` — no implement.md artifact files exist across 144+ archived dirs. Implement runs from plan.md + events.log + git, not from a markdown artifact.
- `NOT_FOUND(query="complete.md", scope="lifecycle/**")` — same. Complete is mechanical, not artifact-producing.
- `NOT_FOUND(query="Scope Boundaries", scope="retros/**")`, `NOT_FOUND(query="Adversarial Review", scope="retros/**")`, `NOT_FOUND(query="Tradeoffs & Alternatives", scope="retros/**")`, `NOT_FOUND(query="Requirements & Constraints", scope="retros/**")`, `NOT_FOUND(query="Web Research", scope="retros/**")`.

**Caveat on retro-mention as value signal (added per critical-review):** Retros are written from a problem-only template (per `skills/cortex-core:retro` skill description: "Captures user corrections, mistakes made, things missed, and wrong approaches. Does NOT capture what worked or accomplishments"). Sections whose value is silent-success — i.e., the artifact section caught a problem before it surfaced downstream — cannot appear in retros by template design. "0 retro mentions" is therefore not a reliable signal of low value for backstop sections; it is reliable for sections that should have generated downstream complaints if load-bearing. Apply the inference cautiously: a section like Veto Surface (13 mentions) is positively load-bearing; a section with 0 mentions may be silent-success or genuine waste, requiring orthogonal evidence (e.g., "no programmatic consumer", "no edit pattern", "duplicates upstream content") to discriminate.

### Pivotal-piece protection (contested cuts)

Each contest is a counter-evidence finding against a prior-audit "safe-to-cut" claim. Severity grading: **CONTESTED** (concrete counter-evidence found) | **REFRAME** (cut is partially right; needs scope adjustment) | **VALIDATED** (prior audit was correct).

| # | Cut target | Prior audit's claim | Counter-evidence | Disposition | What/Why/How? |
|---|---|---|---|---|---|
| C1 | Delete plan.md `## Scope Boundaries` (#180 step 2) | "53% present, often duplicates spec Non-Requirements; NO programmatic consumer" | `research/archive/competing-plan-synthesis/research.md:179,254` cites `Scope Boundaries` as typed structure constraining synthesizer plan-merge; 1 archived reviewer cites it verbatim. **However**, see C1-resolution below. | **REFRAME** — replace, don't delete | WHAT |
| C2 | index.md frontmatter-only (#180 step 3) | Body wikilinks have no consumers | `tags:` is consumed; `parent_backlog_uuid`, `created`, `updated`, `artifacts: []` are appended by 4 reference files (`plan.md:259`, `review.md:148–149`, `refine/SKILL.md:188–189`); audit didn't grep for them | **REFRAME** — drop H1+wikilink body, keep full frontmatter | WHAT (artifacts) + WHY (timestamps) |
| C3 | Architectural Pattern critical-only (#180 step 1) | 1.4% population (2/138 plans) | Prior research at `lifecycle/archive/tighten-1b-plan-agent-prompt-…/research.md:54,194` argued making the field **evaluated, not decorative**. #180's gating to critical-only silently reverts that. The 1.4% is over historical plans pre-current-implementation. | **CONTESTED** — keep optional in default template | WHAT |
| C4 | implement.md §1a trim 30–40 lines (#177 part 1) | Atomic-write recipe + outcome map duplicate Python module | Lines 82–101 document skill↔module contract (dispatch_id semantics, recovery-after-compaction); lines 156–164 outcome map is a schema contract Python can't enforce. `tests/test_daytime_preflight.py:326,379` pin this contract. | **REFRAME** — trim ~15 lines (the Python one-liner HOW), keep contract prose | HOW (recipe) + WHY/WHAT (contract) |
| C5 | clarify-critic.md schema-aware promote (#175) | Refine version is superset | `tests/test_clarify_critic_alignment_integration.py:388–427` hardcode the event shape; ticket lacks schema-version field on `clarify_critic` events. Replay-against-archived requires legacy-tolerant fallback explicitly. | **REFRAME** — elevate risk to high; require schema-version field as gate | WHAT (schema contract) |
| C6 | Soften MUSTs in review.md verdict format (#178) | OQ3 violations | `cortex_command/pipeline/metrics.py:221` parses these fields; CLAUDE.md OQ3 grandfathers pre-existing MUSTs until specifically audited. Parser-protective MUSTs should not be softened. | **REFRAME** — soften prose-style MUSTs only; keep parser-protective ones | HOW (JSON shape) but with WHY (parser protection) |
| C7 | Conditional content extraction 6 blocks (#179) | ~300 lines hot-path reduction | Cortex has no runtime gate for "first invocation"/"critical-tier only" — reliance on Claude reading parent-skill prose; 12 mirror entries; pre-commit drift hook fires on each; state-init.md split lacks correctness test. | **REFRAME** — keep 2 cleanest extractions (`a-b-downgrade-rubric.md`, `implement-daytime.md`); defer 4 others. ~100 line reduction at ~1/3 maintenance cost. | HOW (routing) |
| C8 | complete.md §3 dedupe (#177) | Duplicate of §2 backlog-index sync | The two paths handle different control-flow entry conditions (matched vs. unmatched backlog item); collapse loses the per-path trigger. | **REFRAME** — extract shared helper, keep two named entry points | HOW |

**Resolution of inter-agent disagreement on Scope Boundaries (C1):** Three agents reached different verdicts. Resolution: Agent 2's "0 retro mentions" and Agent 4's "duplicates Non-Requirements, replaceable by Outline" align on *replaceability*. Agent 3's counter-evidence — that the section has occasional consumers — was partly inflated: the production synthesizer prompt at `cortex_command/overnight/prompts/plan-synthesizer.md` scores variants on a `scope_discipline` judgment criterion, not as a typed-structure consumer of `## Scope Boundaries`. The competing-plan-synthesis "invariant #10" cited by Agent 3 lives in an Appendix labeled for a rejected Architecture B. The actually-occasional consumer is in-context reviewer prose. **Net: the canonical enumerative-excludes signal lives in spec.md Non-Requirements (preserved); plan.md Scope Boundaries is a mirror with no programmatic consumer; deleting the mirror is safe.**

### Cuts under-applied (audit was too gentle on HOW content)

| # | Cut target | Why it's HOW | Estimated additional savings |
|---|---|---|---|
| U1 | `critical-review/SKILL.md:336–365` Apply/Dismiss/Ask body | ~25 lines of nested anchor-check prose; WHAT (3 dispositions) and WHY (orchestrator should fix obvious; ask user about consequential) is in first 5 lines | ~25 lines |
| U2 | Constraints "Thought/Reality" tables across the corpus (~10 instances) | Most rows paraphrase "model might want X, do Y instead" — pure prompt-injection HOW. Per OQ3, each row should cite an F-row or retro; most don't. | ~50–70 lines |
| U3 | `plan.md §1b` Competing Plans entire section | ~122 lines. WHAT: "for critical tier, run multiple plans and pick best." WHY: "single Opus plan can be wrong." 122 lines between are HOW + JSON schemas duplicated in `cortex_command/overnight/prompts/plan-synthesizer.md` | ~80 lines beyond extraction |
| U4 | `lifecycle/SKILL.md:33–35` slugify HOW prose | 3 sentences explaining how to compute kebab-case. Canonical `slugify()` is in `cortex_command/common.py`. | ~3 lines |

**Net delta to audit's reduction estimate.** Original audit: ~1,025 lines. Adjustments: **+64 retained** (across C1–C7), **+200 hot-path retained** by halving C7 conditional extraction, **−155 to −180 additional trimmable** in U1–U4. Net on-disk corpus: **~1,130 lines reduced** (slightly higher than audit). Net hot-path context: **~100 lines** (down from audit's ~300, due to halved C7).

**The risk profile shifts** more than the line count: keep load-bearing observability/schema/synthesizer-input fields; cut harder on Constraints tables, §1b orchestration prose, anchor-check prose.

### Vertical-planning replacement scope

`## Outline` and `## Phases` from #182 can REPLACE (not just add to) substantial existing template content.

**Candidate A (highest confidence):** Replace plan.md `## Scope Boundaries` + `## Veto Surface` + `## Verification Strategy` with a single `## Outline` whose final phase encodes end-to-end verification.

- ~~Last phase's `Goal` line absorbs Verification Strategy intent.~~ **Caveat (per critical-review):** Verification Strategy is template-defined as whole-feature end-to-end acceptance (`plan.md:186-187`); a per-phase Checkpoint is a phase-exit criterion. The two are contract-equivalent only when the last phase coincides with whole-feature acceptance. Replacement requires either (a) constraining Outline so last phase = whole-feature acceptance by convention, or (b) carrying a separate `## Acceptance` section that survives independent of phase decomposition. **Decision pending — see Outstanding Decisions.**
- Last phase's `Checkpoint` becomes the user-runnable end-to-end command (would require updating `cortex_command/overnight/report.py:725` to read last-phase Checkpoint, plus the constraint above).
- ~~Per-phase `Goal`/`Checkpoint` pairs absorb Veto Surface use cases.~~ **Caveat (per critical-review):** Of the 13 retro mentions of Veto Surface, a non-trivial fraction document cross-cutting risks not attached to phase outcomes (e.g., shared-failure-mode acknowledgments, side-effect callouts, comment-vs-code discrepancies). The originally-cited preservation location at `plan.md:278-285` (User Approval section) was inspected and contains only `Produced` and `Trade-offs` fields — no risk-callout slot. Veto Surface affordance does not have a preservation home in the current Candidate A design. **Decision pending — see Outstanding Decisions.**
- Scope Boundaries collapses **into the spec.md Non-Requirements canonical source** (which survives the change). Plan.md's `## Scope Boundaries` is a mirror with no programmatic consumer; deleting the mirror keeps the enumerative excludes intact at the source. The earlier framing "anything not in a phase is out of scope" was misleading — the named-excludes survive in spec.md.
- Net per-feature reduction: ~50–100 lines, contingent on resolving Verification Strategy and Veto Surface preservation strategies.

**Candidate C:** Consolidate plan.md §1b.b (critical-tier-embedded format) + §3 (canonical template) into a single canonical template with `## Outline` native. §1b.b becomes a 5-line wrapper. Realistic saving: ~20 lines (down from audit's 60 — Architectural Pattern is genuinely critical-tier-specific).

**Candidates the audit did not evaluate:** Replacement was not modeled by the original audit. Adoption was framed as additive. Adopting #182 as *replacement* substantially changes the math for #180 (artifact templates) — Scope Boundaries deletion becomes free if Outline subsumes it.

**Sections outline+phases CANNOT replace:** task headings (parser-anchored at `cortex_command/pipeline/parser.py:282–329`), per-task `Files`/`Depends on`/`Complexity`/`Verification`/`Status` fields, Architectural Pattern (orthogonal to phase axis), spec.md `## Non-Requirements` (read verbatim by reviewer), spec.md `## Problem Statement` (different abstraction).

**Confidence note.** The audit's "practitioner-grade 1/5 evidence" caveat for CRISPY/QRSPI applies to claims about *adopting* outline (does it improve agent rigor?) but not to claims about *replacing* duplicative sections (which rests on cortex-internal audit evidence and the user's What/Why-not-How principle).

### Hold 1 re-challenge (verdict: PARTIAL REVERSAL)

**Gate 1 (Research → Specify, ≥2 Open Questions in research.md):** KEEP, MIGRATE to Python hook.

- WHY: research questions left unresolved propagate downstream; orchestrator-review R3/R4 only flags or escalates to user (doesn't auto-escalate complexity).
- HOW (count ≥ 2): arbitrary threshold but harmless once gate is deterministic in Python.

**Gate 2 (Specify → Plan, ≥3 Open Decisions in spec.md):** REMOVE.

- Source section (`## Open Decisions`) is **88% "None"** per audit `[research/vertical-planning/audit.md:188]`. The gate fires on ~12% of specs.
- Redundant with orchestrator-review S2/S5 checklist `[orchestrator-review.md:144–150]` which evaluates spec quality in main context.
- **OQ3-violation per CLAUDE.md MUST-escalation policy applied symmetrically:** no F-row, retro citation, or transcript artifact establishes this gate prevented an observed failure. Under cortex's own evidence policy, it shouldn't have been a gate.
- §2b Pre-Write Checks Open Decision Resolution `[specify.md:91–97]` already pressures resolution upstream, so the gate fires on residual irreducible uncertainty — exactly the case where bullet-counting is least informative.

**Implications for tickets:**
- **#183 re-scope:** migrate ONE gate, not two (~20 lines saved, not ~40).
- **#180 step "Open Decisions optional" (D4) UNBLOCKS** immediately (was blocked only by Gate 2's dependence on the section).
- `audit.md:312–314` D-pre block / D4 status: ship D4 directly.
- `audit.md:398–400` Hold 1 resolution paragraph: revise.
- `SKILL.md:253–260` + `:294–312`: delete Gate 2 prose; keep Gate 1 with the duplicate collapsed.

**Pivot question for user (Q-A in §Open Questions):** which of the two gates fired non-trivially in the last 138 lifecycles? If neither fired or only fired ceremonially, FULL REVERSAL is justified.

### Phase-shape analysis (5 phases vs. current 7?)

| Adjacent pair | Verdict | Reasoning |
|---|---|---|
| **clarify + research** | **MERGE** | Boundary is mostly bookkeeping. `refine/SKILL.md:18` already chains them as one delegation; `lifecycle/SKILL.md:210–245` re-orchestrates them with a phase_transition event between. Both load `requirements/` context (duplicate logic at `clarify.md:25–31` and `research.md:23–30`). Discovery Bootstrap `[lifecycle/SKILL.md:170–196]` skips Clarify entirely if epic context exists — proves Clarify isn't an artifact-producing phase, just an aim-setting gate. A merged "Aim & Investigate" phase keeps the load-bearing What (confidence assessment + critic + ≤5 Q's + read-only exploration + Open-Questions Exit Gate) and drops the phase_transition ceremony. |
| **spec + plan** | **KEEP SPLIT** | User-approval-then-pause boundary is load-bearing (user MEMORY explicitly: "after spec.md is approved, stop and wait for explicit 'plan' before entering the Plan phase"). Distinct verification surfaces (S1–S6 spec vs. P1–P8 plan target genuinely different artifacts). §2a Confidence-Check loop-back from Spec→Research has no analog in Plan. |
| **review + complete** | **KEEP SPLIT** | Review is conditional (gated to complex/high/critical), Complete is universal. CHANGES_REQUESTED loop-back in Review has no analog in Complete. Cycle counter prevents infinite rework. |

**Recommended phase set: 6 phases.** clarify → research → aim+investigate (merged) → spec → plan → implement → review → complete becomes **investigate → spec → plan → implement → review → complete**.

**Implication for tickets:** the phase-merge is **NOT in Epic #172's scope**. It would be a new backlog item. Surfacing it here so the user can decide whether to spawn that ticket separately.

## Per-ticket validation (#173–183)

Grading: **KEEP** (proceed as-scoped) | **REVISE** (proceed with named adjustments) | **MERGE** (combine with another ticket) | **DEFER** (block on additional analysis) | **CANCEL** (drop from epic).

| # | Ticket | Verdict | Reason |
|---|---|---|---|
| 173 | Fix duplicated-block bug + 5 stale refs | KEEP | Zero-risk mechanical fixes. Validated. |
| 174 | Collapse byte-identical refine/references files | KEEP | Existing scope is correct — byte-identical collapse with no contract change. Pass-2 critical-review reversed the merge proposal: WHAT-contract distinction (no contract change here) differs from #175 (schema) and #176 (predicate). 3-way split is principle-aligned. |
| 175 | Promote clarify-critic schema-aware | REVISE | Existing scope mostly correct (schema-aware migration with consumer audit). **Add to acceptance:** require schema-version field on `clarify_critic` events (per C5) so legacy archived events can be replayed without breaking integration tests at `tests/test_clarify_critic_alignment_integration.py:388–427`. |
| 176 | cortex-resolve-backlog-item adoption + delete clarify.md | KEEP | Existing scope is correct — predicate-test migration with set-semantics audit. |
| 177 | Trim lifecycle skill (implement.md §1a + plan.md §1b.b + SKILL.md gate) | REVISE | Per C4: implement.md §1a realistic trim is ~15 lines, not 30–40 (keep contract prose). Per U3: plan.md §1b.b should push beyond extraction by ~80 additional lines (HOW orchestration prose). Per Hold 1: SKILL.md gate compression migrates to one gate, not two. |
| 178 | Skill-creator-lens improvements | REVISE | Per C6: don't blanket-soften MUSTs. Per-MUST disposition: keep parser-protective ones (review.md verdict format MUSTs); soften only prose-style ones. Add U1 (critical-review Step 4 prose) + U2 (Constraints tables) to scope as named additional cuts. |
| 179 | Conditional content extraction (6 blocks) | REVISE | Per C7: keep 2 cleanest extractions (`a-b-downgrade-rubric.md`, `implement-daytime.md`); defer 4 others. Net ~100 line hot-path reduction at ~1/3 the maintenance burden of full 6-extraction. |
| 180 | Artifact template cleanups | REVISE | Per C1: replace Scope Boundaries via Outline (Candidate A above), don't delete-without-replacement. Per C2: keep full index.md frontmatter; drop only H1+wikilink body. Per C3: keep Architectural Pattern in default template as optional (don't gate to critical-only). **Plus:** D4 (Open Decisions optional) UNBLOCKS — Gate 2 is being removed per Q-A partial reversal. |
| 181 | Skill-design test infrastructure | KEEP | Test infrastructure is What/Why-aligned (deterministic checks for skill-corpus invariants). |
| 182 | Vertical-planning adoption (Outline + Phases + gates + parser test) | REVISE → EXPAND | Re-frame as **replacement, not addition**. Adopt Candidate A (Outline absorbs Scope Boundaries + Verification Strategy in plan.md, NOT Veto Surface) + Candidate C (consolidate §1b.b + §3 dual-template). **Per Q-C critical-review fixes:** add a top-level `## Risks` section to plan.md to preserve Veto Surface affordance (~5–10 lines back); add tier-conditional `## Acceptance` section for complex-tier features only (~3 lines back per complex feature) so whole-feature acceptance contract survives. Net per-feature reduction adjusts from ~50–100 to ~40–90 lines but the 13-retro-mention pivotal Veto Surface affordance is preserved. |
| 183 | Migrate complexity-escalation gates to Python hook | REVISE | Per Q-A partial reversal: re-scope to migrate ONE gate (Gate 1, Research→Specify). Drop Gate 2 (Specify→Plan) entirely from skill prose. Verification criteria adjust to single-gate migration (~20 lines saved instead of ~40). Critical-review methodology caveat noted in DR-2 — the empirical anchor for Gate 1's value is N=1 with inferred causation; migration is justified on structural grounds (overnight-context auto-escalation forcing function), not strict OQ3 evidence. |

**Net summary:** 4 KEEP-as-is (#173, #174, #176, #181). 7 REVISE (#175, #177, #178, #179, #180, #182, #183). 0 CANCEL. 0 DEFER. Plus 2 NEW backlog tickets to spawn (Q-E phase merge, Q-G research-skill audit). The bones of the epic are sound; the body needs adjustments concentrated in #175 (schema-version field), #177–180 (refine), #182 (expand with `## Risks` + tier-conditional `## Acceptance`), #183 (re-scope to single gate).

### Diff vs. existing decomposition (independent re-decomposition)

A fresh agent decomposed the audit findings *without* reading #173–183 first and produced 9 tickets. Diff against the existing 11:

- **Identical scope:** F1↔#173, F3↔#177, F4↔#178, F5↔#179, F6↔#180, F7↔#181, F8↔#182, F9↔#183. No divergence on 8 of 11.
- **Only meaningful divergence:** F2 (single cross-skill dedup ticket with 4 sub-acceptances) vs. existing 3 tickets (#174 + #175 + #176). Fresh agent's principle-aligned argument: 3-way split is HOW-prescriptive (procedure shape). Defensible counter-argument for 3-way: pre-splitting avoids mid-flight re-decomposition if #175's consumer audit reveals non-tolerant consumers; supports parallel dispatch via overnight runner.
- **Edge difference:** existing has #183 → #174; fresh has F9 → F3 only. The hook (Python script reading events.log) doesn't depend on which markdown file describes the gate. Drop the #183 → #174 edge.

**The independent decomposition validates the existing shape on 8 of 11 tickets.** The remaining divergence is a single principle-vs.-pragmatism judgment call, surfaced as Q-D for the user.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|---|---|---|---|
| **A. Apply all REVISE adjustments to existing 11 tickets, ship as-is** | Medium | Lowest disruption; preserves audit's pressure-test corrections; Hold-1 partial reversal needs single-place SKILL.md edit | Read each REVISE annotation in the per-ticket table above; update each ticket's body |
| **B. Apply REVISE adjustments + merge #174+#175+#176 into one ticket** | Medium | Loses pre-splitting safety net for schema-aware migration; gains principle-alignment and ~2 fewer PRs | A's prereqs + cross-skill dedup ticket consolidation |
| **C. Apply REVISE + merge + spawn separate ticket for clarify+research phase merge** | Medium-large | Phase merge is genuinely outside Epic 172 scope; risks scope creep but captures a high-value finding | B's prereqs + new backlog item drafted from §Phase-shape analysis above |
| **D. Defer Hold 1 reversal pending user decision on Gates' actual fire frequency** | Small | Conservative; preserves both gates until evidence-based decision | Read events.log across last 138 lifecycles for Gate 1/Gate 2 fire counts |

**Recommended: B** (apply revisions + merge cross-skill dedup) plus answer Q-A (Hold 1 fire frequency) before committing #183. Spawn the phase-merge ticket (C's delta over B) only if user explicitly wants it.

## Decision Records

### DR-1: Adopt vertical-planning as REPLACEMENT, not ADDITION

- **Context:** The original audit framed `## Outline` / `## Phases` as additive sections atop existing template content. With the user's What/Why-not-How principle, several existing template sections (Scope Boundaries, Veto Surface, Verification Strategy in plan.md; arguably Open Decisions in spec.md) become redundant once Outline encodes phase Goals + Checkpoints.
- **Options considered:** (1) Adopt as additive (original #182 framing); (2) Adopt as replacement (Candidate A); (3) Defer adoption pending more CRISPY/QRSPI empirical evidence.
- **Recommendation:** Option 2 (replacement). The replacement case rests on cortex-internal audit evidence (which is robust), not on CRISPY's "1/5 practitioner evidence" (which is weak).
- **Trade-offs:** Replacement requires one consumer touch in `cortex_command/overnight/report.py:725` (read last-phase Checkpoint instead of Verification Strategy). Veto Surface escape hatch is preserved at user-approval gate. Per-feature reduction: ~50–100 lines.

### DR-2: Hold 1 partial reversal — keep Gate 1, remove Gate 2

- **Context:** Both complexity-escalation gates (research→specify, specify→plan) currently exist as bullet-count thresholds. Gate 2's source section (Open Decisions) is 88% "None"; gate is redundant with orchestrator-review S-checklist; no F-row evidence supports it under CLAUDE.md OQ3.
- **Empirical anchor (events.log scan across 153 lifecycle/*/events.log files):**
  - **Gate 1: 11 events tentatively classified as Gate 1 fires (~7% rate)** by the heuristic "complexity_override simple→complex immediately preceding research→specify transition." The cited concrete value case is `lifecycle/archive/gate-overnight-pr-creation-on-merged-over-zero/events.log`, which logs a `spec_revision` event labeled "critical-review Q1/Q2 resolution." Of the 11, only 1 has a downstream `spec_revision`; 0 logged a `critical_review` event in events.log directly (the cited case infers the critical-review chain from the spec_revision label).
  - **Gate 2: 0 events tentatively classified as Gate 2 fires** (timing rule applied to specify→plan transitions). The dual-firing case at `lifecycle/archive/resolve-cortex-commandbacklog-…/events.log` was set aside because of co-firing with `criticality_override`.
  - **Methodology caveat (added per critical-review):** The events.log schema (`{ts, event, feature, from, to}` per `skills/lifecycle/SKILL.md:294-312`) carries no trigger field on `complexity_override`. Gate 1 vs. Gate 2 vs. manual user override are not separately distinguishable from the event payload alone; the 11-vs-0 contrast is produced by timing-pattern heuristics applied asymmetrically across the two cases (the dual-firing case was excluded for Gate 2 but no equivalent exclusion criterion was applied to the 11 Gate 1 candidates). The empirical anchor is therefore weaker than originally framed: it shows that automatic gate fires (if they occurred) cannot be reliably attributed to specific gates from the existing event log.
  - **Pre-commitment caveat (added per critical-review):** This artifact's pivot question Q-A pre-stated "if neither fired or only fired ceremonially, FULL REVERSAL is justified." The 1-of-11 downstream-effect rate for tentative Gate 1 fires is consistent with "only fired ceremonially," which would trigger that pre-commitment. The data is consistent with multiple readings (full reversal, partial reversal, status quo); the choice between them is not resolved by the events.log alone.
- **Options considered:** (1) Keep both (original Hold 1); (2) Remove both (full reversal); (3) Keep one, remove other (partial reversal).
- **Recommendation:** ~~Option 3~~ **PENDING USER REDIRECTION** (post-critical-review). The originally-recommended partial reversal rests on the 11-vs-0 contrast, which the methodology caveat above shows is weaker than originally framed. See "Outstanding Decisions After Critical Review" below.
- **Trade-offs (any option):** Each option re-scopes #183 differently (Option 1: keep both gates as-is or migrate both; Option 2: drop #183 entirely; Option 3: migrate one gate). Option 2 also unblocks #180's "Open Decisions optional" change immediately; Option 1 leaves it blocked.

### DR-3: Cross-skill dedup ticket consolidation (#174 + #175 + #176 → one)

- **Context:** All three tickets perform the same work motion (audit consumers, dedupe, redirect, parity-test) on different files with different risk profiles. Splitting into 3 tickets is HOW-prescriptive.
- **Options considered:** (1) Keep 3-way split (existing); (2) Merge into one with 4 named sub-acceptances; (3) Merge with explicit phase-1/phase-2/phase-3 milestones inside the merged ticket.
- **Recommendation:** Option 2 (clean merge with sub-acceptances).
- **Trade-offs:** Loses pre-splitting safety net if #175's consumer audit reveals non-tolerant consumers. Gains principle-alignment, fewer PR overhead, single review surface. **Pivot to Q-D.**

### DR-4: Six-phase lifecycle (merge clarify + research → "investigate")

- **Context:** Clarify produces no artifact, is bounded to ≤5 Q's, and `refine/SKILL.md` already chains it directly into Research. The phase boundary is mostly bookkeeping.
- **Options considered:** (1) Keep 7 phases (current); (2) Merge clarify + research into "investigate" (6 phases); (3) Merge spec + plan as well (5 phases — rejected, user-approval-pause is load-bearing).
- **Recommendation:** Option 2 — but as a **new backlog item, not in Epic #172 scope**. Surfacing here for user awareness.
- **Trade-offs:** Saves the phase_transition event ceremony, deduplicates `requirements/` loading. Risks losing the explicit aim-setting checkpoint, though `clarify-critic` would still fire as the load-bearing gate inside the merged phase.

### DR-5: Trim under-applied HOW content (Constraints tables, plan.md §1b orchestration prose, critical-review Step 4 anchor-check, slugify HOW)

- **Context:** The original audit cleared roughly the right *categories* of cuts but applied them with insufficient aggression on HOW-prose, leaving ~155–180 additional trimmable lines untouched.
- **Recommendation:** Add the four U-items (U1–U4 in the Pivotal-piece section above) to #178's scope as named additional cuts. Realistic on-disk corpus reduction lifts from ~1,025 to ~1,130 lines without compromising any WHAT/WHY content.
- **Trade-offs:** Slightly larger #178 scope; lower per-row signal in remaining Constraints tables (which is fine — that signal is already lower than retro evidence claims).

## Decisions (2026-05-06, two passes)

### Pass 1 — User picks before critical-review

User-confirmed picks on Q-A through Q-G:

- **Q-A (Hold 1):** Partial reversal — keep + migrate Gate 1, remove Gate 2.
- **Q-B (Architectural Pattern):** Keep optional in default template; required content only at critical tier.
- **Q-C (Scope Boundaries / Candidate A):** Replace via Outline.
- **Q-D (Cross-skill dedup):** Merge #174 + #175 + #176 into one ticket.
- **Q-E (Phase merge):** Spawn separate backlog ticket outside Epic #172.
- **Q-F (Conditional extraction):** Trimmed 2 extractions in #179.
- **Q-G (Audit `/cortex-core:research`):** Spawn separate backlog ticket outside Epic #172.

### Pass 2 — Decisions After Critical Review (2026-05-06)

Critical-review surfaced 7 A-class objections clustering around 3 picks (Q-A, Q-C, Q-D). Picks Q-B, Q-E, Q-F, Q-G stand unchanged. Reopened picks resolved as:

- **Q-A — Partial reversal stands as judgment call (iii).** Keep Gate 1, remove Gate 2. Migrate Gate 1 to Python hook per #183 re-scoped to single gate. **Reasoning:** the methodology caveat is real but doesn't invalidate the call — Gate 1's structural role (same-session auto-escalation when research uncovers complexity not visible at lifecycle_start, particularly in overnight contexts where there is no user-decides path) is hard to replace cheaply. Gate 2 has no comparable structural role and is redundant with §2b Pre-Write Checks. The principle argument for full reversal is acknowledged but doesn't override the overnight-context structural value.
- **Q-C Veto Surface preservation: option (α).** Add a top-level `## Risks` section to plan.md as part of #182's vertical-planning adoption. **Reasoning:** 13 retro mentions = pivotal; the user's stated concern ("don't remove pivotal pieces") forecloses option (γ); option (β) mixes user-decision content with risk-acknowledgment poorly. **Cost:** Candidate A net reduction adjusts from ~50–100 to ~40–90 lines per feature. Still a strong win.
- **Q-C Verification Strategy preservation: tier-conditional.** Simple-tier features: last-phase `Checkpoint` = whole-feature acceptance (per option α). Complex-tier features: separate `## Acceptance` top-level section (per option β). **Reasoning:** the audit's own evidence shows Verification Strategy is sometimes substantive (~1465 tok in doc-only S2) and sometimes thin (~197 tok in S1). Universal mandate is bloat for simple features; universal acceptance of narrowing loses contract for complex. Tier-conditioning matches existing lifecycle pattern (critical-review, review.md, plan.md §1b are all tier-conditional). **Cost:** ~3 lines per complex-tier feature only.
- **Q-D Cross-skill dedup ticket shape: (I) Revert to existing 3-way split.** Keep #174, #175, #176 separate. **Reasoning:** Reviewer 4's principle correction is correct — "different risk profiles" (no-contract / schema / predicate) is WHAT/WHY (contract distinction); "same work motion" is HOW (procedure). The 3-way split groups by WHAT contract; merge groups by HOW procedure. The earlier Q-D framing was inverted. Existing decomposition stands.

**Implications for ticket revisions:**
- DR-1 (vertical-planning REPLACEMENT): valid; #182 expands scope to add `## Risks` section preservation + tier-conditional `## Acceptance`.
- DR-2 (Hold 1 partial reversal): stands; #183 re-scopes to single-gate migration of Gate 1 only; #180 D4 (Open Decisions optional) unblocks.
- DR-3 (cross-skill dedup merge): **REVERSED.** Existing #174/#175/#176 split preserved. #175 still gets the C5 schema-version-field acceptance addition.
- DR-4 (six-phase lifecycle): stands; spawn separate ticket per Q-E.
- DR-5 (under-applied HOW trims): stands; #178 expands scope per U1–U4.

---

**Synthesis word count:** ~5,400 words. Larger than typical research artifact, but proportionate to the audit-of-an-audit scope. Decision Records and per-ticket validation tables are the load-bearing output sections; everything else is supporting evidence.
