# Research: Tighten §1b plan-agent prompt to require strategy-level distinction

## Codebase Analysis

### Files that will change

- **`plugins/cortex-interactive/skills/lifecycle/references/plan.md`** (canonical) — target line is 47 inside the verbatim plan-agent prompt template (lines 30–92). Plan Format spec begins at line 67.
- **`skills/lifecycle/references/plan.md`** (dual mirror — same content) — `bin/cortex-check-parity` enforces drift detection at pre-commit. Both files MUST be updated atomically. (Note: `bin/cortex-check-parity` is bypassable via `--no-verify`. There is no test for byte-equality of the references/ source files specifically — `tests/test_lifecycle_phase_parity.py` covers phase detection, not source-file parity.)

### Current §1b structure

The §1b "Competing Plans (Critical Only)" section spans plan.md:21–149. Key landmarks:

- Line 22: criticality gate ("When criticality is `critical`...").
- Line 27: dispatch instruction emphasizes verbatim use of the template ("Use the plan agent prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions").
- Line 28: model is sonnet for plan agents.
- Lines 30–92: the verbatim plan-agent prompt template.
- Line 47 (the target): *"Your approach should be distinct — explore a different architectural strategy, decomposition, or ordering than the obvious default"*.
- Lines 67–92: Plan Format (`# Plan: {feature}`, `## Overview`, `## Tasks`, `## Verification Strategy`, `## Sizing`).
- Lines 96+: comparison table format and `plan_comparison` event schema (includes `variants[].label`, `approach`, `task_count`, `risk`).

### Historical variant evidence (n=4)

Four `plan_comparison` events exist across the lifecycle corpus (146 features). All four are runner/hook/prompt internals:

| Feature | Plan A approach | Plan B approach | Plan C approach | Resolution |
|---|---|---|---|---|
| `install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions` | bottom-up data-first | events-registry-first | runner-first/test-driven | C selected |
| `rebuild-overnight-runner-under-cortex-cli` | contract-layer-first | bottom-up primitives w/ runner_primitives.py extraction | foundation-first w/ CLI wired before runner | "A with B's runner_primitives.py extraction grafted in" — outside the variant set |
| `fix-overnight-runner-silent-crash-signal-handling-unregistered-events-and-batch-plan-path-mismatch` | linear by failure area | test-first (foundation → fixes → verification) | risk-ordered parallel waves | B selected |
| `disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape` | test-first; 5 tasks; bundled atomic-commit | source-first; 6 tasks; separate atomic-commit | n/a (only A vs B) | A selected |

**Empirical signal from the corpus**: variants differ on **task ordering** (bottom-up vs top-down, contract-first vs foundation-first, test-first vs source-first, parallel vs sequential) and **task granularity** (5/6 tasks; 16/14/13 tasks; bundled vs separated). None of the four cases show variants differing on architectural strategy (e.g., event-driven vs pipeline). One case (rebuild-overnight-runner, 25%) was resolved by graft outside the variant set.

The corpus skews heavily toward fix/refactor tickets on existing infra. There are no greenfield or spec-heavy cases in the n=4 corpus. (See Adversarial Review §1.)

### No pre-existing taxonomy in the codebase

Searched `skills/`, `plugins/cortex-interactive/skills/`, `docs/`, `requirements/`. No architectural-pattern taxonomy exists today.

### In-house pattern for taxonomies in prompts

The closest precedent is `plugins/cortex-interactive/skills/critical-review/SKILL.md:30`, which uses an **open menu** ("representative angle examples — not an exhaustive set. Pick angles most likely to reveal real problems for this specific artifact, choosing from the menu or inventing new angles that fit the artifact better"). This is the only taxonomy-shaped construct in the skill prompts and uses the open-with-examples shape.

### Downstream and sibling tickets

- **#160 (synthesizer)** — does not exist yet as code. The motivation chain "synthesizer needs distinct variants to rank well" assumes an unbuilt consumer.
- **#161, #162** — wiring tickets for interactive and overnight surfaces (out of scope for #159).
- **#163** — calibration probes (out of scope for #159).
- **#158 (parent epic)** — `competing-plan-synthesis` epic.

### Plan Format and downstream consumers (orchestrator-review)

If a new field (e.g., `**Architectural Pattern**`) is added between `## Overview` and `## Tasks`, the P-checklist in `plugins/cortex-interactive/skills/lifecycle/references/orchestrator-review.md` does not currently evaluate this field. Adding it as a non-evaluated field is decorative; adding it as an evaluated field requires a corresponding P-checklist entry and possibly downstream consumer updates (event schema, morning-report rendering of `plan_comparison`).

## Web Research

### Multi-agent diversity literature

Convergent finding from 2024–2026 papers: **enumerated bounded-set vocabularies produce stronger diversity gains than open-ended "be different" instructions.**

- **Spark Effect** (arXiv:2510.15568, Oct 2025) — persona-conditioned agents using a **controlled vocabulary of 9 thinking methods + 20 competencies** lifted diversity from 3.14/10 to 7.90/10. **+4.76 points, p<0.001, Cohen's d=2.88**, closing 82% of the gap to human experts. The tagger "defaults to that controlled vocabulary and only proposes a new label when no suitable match exists" — bounded, not open.
- **Dipper** (arXiv:2412.15238, NUS 2024) — enumerated 7-prompt candidate pool. Three Qwen2-MATH-1.5B with diverse prompts beat one 7B model. Introduces Fidelity-Adjusted Semantic Volume (FASV); diversity correlates up to 0.8 with ensemble performance.
- **Meta-Debate** (arXiv:2601.17152, 2026) — dynamic role assignment via peer-review of role-specific proposals. Outperforms uniform role assignment by up to 74.8%.
- **Debate-to-Write** (COLING 2025) — persona-driven multi-agent framework; "assigning distinct roles to personas, each with a unique argumentative perspective, improved the semantic diversity of generated content."
- **General agent-scaling finding**: "Homogeneous agents saturate early because their outputs are strongly correlated, whereas heterogeneous agents contribute complementary evidence." Open-ended "be different" prompting does not produce heterogeneity at scale.

### Architecture-pattern taxonomies

Multiple sources converge on a canonical short list (Shaw & Garlan / Shaw & Clements):

- pipes-and-filters
- layered
- event-driven (event-bus / publish-subscribe)
- blackboard (shared-data with multiple specialists)
- client-server
- broker
- microkernel (plug-in)
- component-based

Modern practitioner short list (Red Hat): layered, event-driven, microservices, microkernel, space-based.

LLM-friendly short list candidate (under 10, named, distinguishable): **pipeline / event-driven / layered / shared-data / plug-in** — five categories spanning the realistic strategy space for orchestration code. These names are heavily represented in LLM training data, so distinctness is reliable.

### Position-bias literature

- **Shi et al. 2024**, "Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge" (arXiv:2406.07791, ACL 2025.ijcnlp-long.18). 15 LLM judges, MTBench + DevBench, 22 tasks, ~150,000 evaluation instances.
  - Direct quote: *"those of similar quality are difficult to judge, increasing the likelihood of position bias"*
  - Direct quote: *"the positional consistency of judge models is closely tied to the magnitude of quality differences between candidate answers, with more equivocal instances where quality differences approach parity tending to confound LLM judges and lead to increased position bias"*
  - Documents a **parabolic relationship** between Position Consistency and answer quality gap (δq); lowest PC at minimal differentials.
  - Authors note mitigation remains an open problem; no in-paper solution proposed.
- **Caveat**: "similar" in this paper is measured in *output quality space*, not architectural-pattern space. Same-pattern variants could still be cleanly distinguishable in quality space; the literature's support for "diverse architectures → easier ranking" is suggestive, not direct.

### Multi-agent code-generation: existing systems use open-ended sampling

- **AgentCoder** (arXiv:2312.13010), **MapCoder** (ACL 2024, aclanthology.org/2024.acl-long.269), **Blueprint2Code** (PMC12575318): all use open-ended plan/blueprint sampling without enumerated strategy axes — exactly the pattern producing cosmetic-only diversity. Strategy-axis pre-assignment is general-MAD best practice but not standard in code-gen.
- **Anthropic "Multi-agent coordination patterns"** explicitly names the "split-and-merge" pattern but does not prescribe how to force genuine perspective diversity.

### Domain-misalignment caveat

Spark Effect and Dipper findings come from solution-space exploration (math reasoning). Plan-gen for cortex tickets is implementation-decomposition, where the constraint is the existing codebase shape, not problem-search-space breadth. The analogy is suggestive, not load-bearing.

## Requirements & Constraints

### Project requirements (`requirements/project.md`)

- **Simplicity discipline (lines 19–21)**: *"Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."*
- **Maintainability through simplicity (line 32)**: System must remain navigable as it grows.
- **Handoff readiness (lines 13–14)**: Lifecycle artifacts must be fully self-contained for overnight handoff.

### Multi-agent requirements (`requirements/multi-agent.md`)

- Parallel dispatch with intra-session blocking is the model. No explicit constraint on plan-variant diversity, but criticality is a routing axis (criticality-based model selection: low/medium → Sonnet, high/critical → Sonnet/Opus).

### Pipeline requirements (`requirements/pipeline.md`)

- Deferral system: when an ambiguous decision cannot be resolved autonomously, write a structured deferral question and surface it in the morning report. Plan selection is the canonical deferral use-case.

### CLAUDE.md policy

- **OQ3 (MUST-escalation)**: Soft positive-routing phrasing is the default. To add MUST/CRITICAL/REQUIRED escalation requires evidence link (events.log F-row, retros entry, or transcript) AND prior `effort=high`/`xhigh` dispatch failure. Lowercase "must" in normal English prose is not the OQ3 target — RFC-2119-style markers are. The proposed prompt language uses lowercase "must" and should not trigger OQ3, but any later tightening to uppercase MUST/REQUIRED would.
- **OQ6 (tone)**: keep prompt language rule-focused, not tone-focused. No bearing on this edit beyond avoiding warmth-laden phrasing.

### Source research (`research/competing-plan-synthesis/research.md`)

- **DR-3 Option 4** (the intervention this ticket implements): *"Tighten the §1b plan-agent prompt to require strategy-level distinction (forbid ordering-only differentiation; require each variant to inhabit a named architectural-pattern category)"* — the primary fix per DR-3 ordering.
- **DR-3 Option 3** (conditional escalation): routing-agent layer that pre-assigns architectural axes — the documented next step if Option 4 underperforms in production.
- **DR-3 input-dependency warning**: *"Option 4 still depends on spec/research seeding architectural-strategy alternatives in the inputs. If they don't... neither prompt-tightening nor routing-agent will produce real diversity."*
- **DR-4** (selector mitigations): strip variant labels, randomize order, swap-and-require-agreement. Applies to the synthesizer (#160), not this ticket.
- **Q5** (position-bias): cited above; the empirical anchor for "candidates too similar → position bias dominates."
- **Q7** (corpus signal): n=4 historical events; ordering/granularity diversity, no architectural-strategy diversity.

## Tradeoffs & Alternatives

The intervention space spans a one-dimensional axis from "do nothing extra" to "force closed enumerated taxonomy."

### A. Negative-only edit (delete "or ordering")

- **Pros**: smallest possible change. Doesn't introduce a taxonomy that can go stale.
- **Cons**: weak Opus-4.7 leverage (negative without positive scaffolding). Doesn't tell the agent what the *replacement* axis should be — agents may rename "ordering" framings as "decomposition" framings to satisfy the literal prompt. Doesn't catch the actual Q7 failure mode (which manifested as decomposition framings, not literal "ordering" labels).

### B. Negative + positive open ("each plan must inhabit a named architectural-pattern category")

- **Pros**: positive instruction (better Opus 4.7 leverage). Forces the agent to *name* its category, making category-collision mechanically inspectable.
- **Cons**: "named architectural-pattern category" is itself underspecified. Agents can name "the bottom-up category" and satisfy the literal instruction while still producing the Q7 failure mode. Open-ended phrasing leaves the agent to invent categories from scratch; under context pressure, may converge on the same low-imagination categories the corpus already shows.

### C. Closed taxonomy ("Choose ONE of: event-driven, pipeline, layered, registry, blackboard")

- **Pros**: strongest mechanical guarantee of cross-variant distinction. Most directly addresses the synthesizer's leverage problem. Aligns with empirical literature (Spark Effect, Dipper) which directly supports closed enumerated vocabularies.
- **Cons**: goes stale (architectural-pattern taxonomies are inherently domain-specific). Constrains future work — features needing a hybrid or out-of-taxonomy pattern get coerced. Misaligned with the canonical in-house pattern (`critical-review/SKILL.md:30` uses open menu). May be a category error for typical sub-1000-line tickets — many fix-flavored tickets only sensibly inhabit one pattern (the existing one), forcing 2 of 3 plan agents into pattern-token cosplay.

### D. Open taxonomy with examples ("e.g., event-driven, pipeline, layered, registry — name your category")

- **Pros**: aligns directly with the in-house pattern (`critical-review/SKILL.md:30`). Examples anchor what "architectural pattern" means without locking the agent into a specific list. Doesn't go stale.
- **Cons**: the "or invent" escape hatch defeats the constraint — a plan agent told to invent a new category will invent one that fits its preferred decomposition, restoring the failure mode. Slightly more prompt real estate than A or B.

### E. Per-agent axis assignment in dispatch (routing-agent layer)

Deferred per ticket scope (#159 explicitly out-of-scopes the routing-agent layer; research.md DR-3 Option 3 is the conditional escalation if D/F underperforms).

### F. Self-check requirement (orthogonal modifier)

- **Pros**: forces the agent to articulate both the category name *and* its differentiation from the obvious approach. Makes the failure mode visible in the variant artifact. Composable with B/C/D/G.
- **Cons**: standalone, just adds metadata to the existing failure mode. Adds output-format complexity — requires updating the synthesizer's expected schema and the orchestrator-review P-checklist.

### G. Hybrid: closed taxonomy with escape hatch

- **Pros**: closed-list mechanical distinctness with an escape valve.
- **Cons**: strictly worse than D or C — still has staleness; escape hatch only mitigates it; requires two design decisions (the list + the escape criteria).

### Recommendation tension

The agents producing the tradeoff and adversarial reviews disagree on the right answer:

- **Tradeoffs agent recommends D + F** (open taxonomy with examples + self-check) — primarily on in-house-convention alignment with `critical-review/SKILL.md:30`.
- **Adversarial agent recommends C** (closed taxonomy, no escape) — primarily on direct empirical literature evidence (Spark/Dipper) and the observation that the in-house convention argument inverts the project's stated empirical preferences. The adversarial agent additionally questions whether the tightening should ship at all before the synthesizer (#160) provides an empirical consumer signal.

The right answer depends on a Spec-phase user judgment — see Open Questions below.

## Adversarial Review

### Failure modes and edge cases

1. **Empirical base is thin and skewed**. n=4 cases are all runner/hook/prompt internals; three are fix-flavored, one is a substantial rebuild. None are greenfield or spec-heavy. The recommendation may not generalize to features where ordering distinctions are the legitimate primary differentiator.
2. **"Decomposition was the diversity all along" hypothesis**. For sub-1000-line edits, "bottom-up vs registry-first vs runner-first" may be the correct level of distinction. Plan B's `runner_primitives.py` extraction in `rebuild-overnight-runner-under-cortex-cli` was a meaningful module-boundary insight at the decomposition level — it's what the user grafted in. Forcing strategy-level distinction may suppress this useful signal.
3. **Architectural-pattern taxonomy is a category error for typical work**. Shaw/Garlan patterns describe whole-system topologies. For a 113-line crash-fix plan, only one pattern fits (the existing runner's). Forcing 2–3 plan agents to produce variants in different categories produces one valid plan plus 1–2 contortions ("event-driven" because the fix touches a signal handler) — worse signal than the status quo.
4. **The graft path becomes harder**. The 1/4 historical case resolved by grafting Plan B's module into Plan A's structure relied on the variants sharing most of their decomposition shape. Architecturally distinct variants have less surface compatibility — mechanical graft becomes structurally infeasible.
5. **Input-dependency failure pushed downstream**. DR-3 itself flags this. If specs don't surface architectural choice points, prompt agents are forced to *invent* strategy distinctions unsupported by the spec/research. Inventing distinctions = hallucinating constraints.
6. **Solving for an unproven consumer**. The synthesizer (#160) does not exist. n=4 historical cases were resolved by humans (3/4 picks, 1/4 graft). No evidence exists that an automated synthesizer over the same n=4 variants would have benefited from architectural-pattern partitioning.

### Anti-patterns and structural concerns

7. **In-house convention as defensibility shield**. The tradeoffs agent's preference for D over C rests primarily on `critical-review/SKILL.md:30`, treating one in-house precedent as load-bearing against direct empirical literature. The convention argument inverts the project's stated empirical preferences. Note the analogy doesn't fully transfer: critical-review's open menu is for *angles* (genuinely unbounded space); architectural patterns have a well-known closed canon.
8. **Plan format field ripples to orchestrator-review**. Adding `**Architectural Pattern**` field requires either an orchestrator-review P-checklist entry (atomic update) or accepting that the field is decorative and weakens the intervention. The "~6 lines of net change" estimate is incomplete.
9. **Dual-source mirror bypass risk**. `bin/cortex-check-parity` is bypassable via `--no-verify`. There is no test for byte-equality of the references/ source files specifically. Drift could slip through silently.
10. **OQ3 risk likely safe but proceed carefully**. Lowercase "must" in proposed prompt text doesn't trigger OQ3. However, the n=4 corpus is below the policy's 2+ retros threshold for analogous re-evaluation triggers; if the prompt is later tightened to uppercase MUST/REQUIRED, it would require evidence per OQ3, and the absence of an effort-first dispatch attempt would be disqualifying.

### Assumptions that may not hold

11. **"Synthesizer ranks better with distinct variants" is asserted, not measured**. Position-bias literature measures "similarity" in output quality space, not architectural-pattern space. Equating same-pattern with similar-from-synthesizer-perspective is a leap unsupported by the cited evidence.
12. **Spark Effect / Dipper are domain-misaligned**. Both produced diversity gains for solution-space exploration (math reasoning). Plan-gen for cortex is implementation-decomposition. The analogy is suggestive, not load-bearing.
13. **The "or invent" escape hatch defeats the constraint** (in option D). A plan agent told to invent a new category will invent one that fits its preferred decomposition, restoring the failure mode. The escape clause must be removed or constrained for the prompt edit to actually bite — which collapses D into C.
14. **No cheap unit test for "did the prompt edit produce more architecturally distinct variants?"**. The prompt-template verbatim copy means adding categorization language requires a full plan-gen run to test. Stochastic and expensive.

### Recommended mitigations

- **M1**: Replay the n=4 corpus against the proposed edited prompt before shipping, to measure whether resulting variants are (a) more architecturally distinct, (b) more useful to a human picker, (c) more useful to a hypothetical synthesizer.
- **M2**: If shipping with a taxonomy, prefer closed (C) over open-with-escape (D). The empirical literature directly supports closed enumeration; the in-house convention does not generalize.
- **M3**: Drop the `**Architectural Pattern**` field unless the orchestrator-review P-checklist is updated atomically.
- **M4**: Preserve the graft path explicitly — add a clause to §1b acknowledging variants may be combined post-selection.
- **M5**: Add a byte-equality test for `skills/lifecycle/references/plan.md` and `plugins/cortex-interactive/skills/lifecycle/references/plan.md`.
- **M6**: Define the success criterion for Option 4 in the spec *before* implementation (e.g., "in the next 5 critical-tier plan_comparison events, ≥3 show variants with genuinely different patterns judged by independent reviewer"). Without this, the conditional escalation to Option 3 cannot be evaluated.

## Open Questions

These questions were not resolved within the research dispatches; they require user judgment in the Spec-phase interview.

1. **Should we ship this at all before the synthesizer (#160) provides an empirical consumer signal?** The adversarial agent argues #159 optimizes for an unbuilt consumer against an untested hypothesis, and that humans (the current consumers) may actually prefer ordering/decomposition distinctions because they map to actionable risk profiles. The discovery research (DR-3) argues #159 ships in parallel with #160 specifically because it's independent of the synthesizer build. The user must decide whether the empirical literature evidence + DR-3 ordering is strong enough to ship without first replaying the n=4 corpus through an edited prompt.
   - *Deferred to Spec-phase user decision.*

2. **Open vs closed taxonomy**. Empirical literature (Spark Effect, Dipper) supports closed enumerated vocabularies for diversity gains. In-house convention (`critical-review/SKILL.md:30`) uses open with examples. Critical-review's open menu is for genuinely unbounded angle space; architectural patterns have a well-known closed canon, so the convention may not transfer. Choice between options C, D, B determines whether the taxonomy is closed, open-with-examples, or fully open.
   - *Deferred to Spec-phase user decision.*

3. **What taxonomy?** If a taxonomy is included (closed or open-with-examples), candidate lists include:
   - **Web-recommended LLM-friendly short list**: pipeline / event-driven / layered / shared-data / plug-in.
   - **Shaw/Garlan canonical**: pipes-and-filters, layered, event-driven, blackboard, client-server, broker, microkernel, component-based.
   - **Cortex-flavored short list** (proposed in adversarial mitigation M2): registry-first, event-driven, layered, pipeline, fix-in-place — named for cortex's typical work shape.
   - The Q7 historical variants ("bottom-up vs events-registry-first vs runner-first") map cleanly onto NONE of these — confirming they are decomposition framings, not architectural patterns.
   - *Deferred to Spec-phase user decision.*

4. **Should the Plan Format gain a new field (`**Architectural Pattern**`) between `## Overview` and `## Tasks`?** If yes, orchestrator-review.md's P-checklist needs an atomic update; otherwise the field is decorative. If no, the categorization lives in `## Overview` prose and is harder to inspect mechanically.
   - *Deferred to Spec-phase user decision.*

5. **Should we explicitly preserve the graft path?** The 1/4 historical case resolved by graft (`rebuild-overnight-runner` → "A with B's `runner_primitives.py` extraction grafted in"). Strategy-distinct variants have less surface compatibility, making graft harder. Adding a clause to §1b acknowledging post-selection combination is M4 from the adversarial review.
   - *Deferred to Spec-phase user decision.*

6. **Should we add a success-criterion baseline to the ticket?** M6 from the adversarial review. Without a defined success criterion, the conditional escalation to Option 3 cannot be evaluated. Candidate criterion: "in the next N critical-tier plan_comparison events, ≥M show variants with genuinely different patterns judged by independent reviewer."
   - *Deferred to Spec-phase user decision.*

7. **Should we add a byte-equality test for the dual-source mirror?** M5 from the adversarial review. `bin/cortex-check-parity` is bypassable via `--no-verify`; no pytest covers byte-equality of the references/ files.
   - *Deferred to Spec-phase user decision* (this is in scope as "may need" infrastructure for a one-line edit; could be a separate ticket).

8. **Phrasing audit for OQ3**. The proposed positive language uses lowercase "must" — verified non-triggering for OQ3. Spec must confirm no uppercase MUST/CRITICAL/REQUIRED slips in.
   - *Resolved during research*: lowercase "must" is exempt; the implementer must keep the language in lowercase imperative form to avoid OQ3 escalation requirements.
