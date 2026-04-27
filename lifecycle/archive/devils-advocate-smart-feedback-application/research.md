# Research: Add a smart feedback application step to /devils-advocate

## Clarified Intent

Add a "smart feedback application" step to `/devils-advocate` that, after making the case, classifies each of its own objections as Apply / Dismiss / Ask — sharpening the artifact where objections are concrete, dismissing weak ones, and asking only on real tie-breaks. Adapted from `/critical-review` Step 4 but calibrated for the inline single-context execution model: **default to Dismiss**, **require anchor-to-source for Apply** (anchor source = lifecycle artifact when one exists, conversation-stated direction when no lifecycle exists). Devils-advocate must remain distinct from critical-review post-change — no fresh-agent dispatch, no parallel reviewers, no opus synthesis.

## Codebase Analysis

### Files that will change

**Primary target:**
- `skills/devils-advocate/SKILL.md` — currently 94 lines. Insertion point for new step: between Step 2 (Make the Case) and Success Criteria. Single-file skill, no `references/` directory.

**Documentation (possibly updated):**
- `docs/skills-reference.md` (lines 112–115) — describes devils-advocate output format. Update only if output materially changes.
- `docs/agentic-layer.md` (line 43) — "Produces" column. Same conditional.

**No tests, hooks, or settings dependencies.** Skill is pure markdown deployed via `skills/ → ~/.claude/skills/` symlink.

### Current devils-advocate structure (verbatim)

Top-level sections in `skills/devils-advocate/SKILL.md`:
1. Frontmatter (`name`, `description`)
2. Intro paragraph
3. `## Input Validation` — 3 numbered checks
4. `## Step 1: Read First` — lifecycle artifact read order (`plan.md → spec.md → research.md`), otherwise conversation context
5. `## Step 2: Make the Case` — four H3 subsections: `### Strongest Failure Mode`, `### Unexamined Alternatives`, `### Fragile Assumption`, `### Tradeoff Blindspot`
6. `## Success Criteria` — 5 bullets
7. `## Output Format Example` — Kafka/webhooks example
8. `## Error Handling` — 3-row table
9. `## What This Isn't` — final paragraph (verbatim below)

**"What This Isn't" verbatim (lines 92–94):**

> Not a blocker. The user might hear the case against and proceed anyway — that's fine. The point is they proceed with eyes open. Stop after making the case. Don't repeat objections after they've been acknowledged. Don't negotiate or defend your position if the user decides to proceed anyway.

### Critical-review Step 4 verbatim (source pattern)

From `skills/critical-review/SKILL.md` lines 197–217:

> ## Step 4: Apply Feedback
>
> Immediately after presenting the synthesis, work through each objection independently. Do not wait for the user.
>
> For each objection, assign one of three dispositions:
>
> **Apply** — the objection identifies a concrete problem and the correct fix is clear and unambiguous. [...] Fix these without asking.
>
> **Dismiss** — the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements. State the dismissal reason briefly. **Anchor check**: if your dismissal reason cannot be pointed to in the artifact text and lives only in your memory of the conversation, treat it as Ask instead — that is anchoring, not a legitimate dismissal.
>
> **Ask** — [...] Hold these for the end.
>
> **Before classifying as Ask, attempt self-resolution.** [...] **Anchor check**: if your resolution relies on conclusions from your prior work on this artifact rather than new evidence found during the check, treat it as Ask — that is anchoring, not resolution. Uncertainty still defaults to Ask.
>
> [...] Re-read the artifact in full. Write the updated artifact with all "Apply" fixes incorporated. Present a compact summary [...]

### Critical-review §2a Project Context loading

From `skills/critical-review/SKILL.md` lines 16–22: §2a loads `requirements/project.md` and `lifecycle.config.md`'s `type:` field, constructs a `## Project Context` block, and **injects it into fresh dispatched reviewer agents' prompts**. Its purpose is bootstrapping fresh agents that have zero conversation state. **It does not transfer literally to devils-advocate**, which runs inline with the host agent's existing context. At most, project context could be consulted opportunistically during self-resolution lookups — not pre-loaded.

### Drift-coupled mirrors of CR Step 4

`skills/lifecycle/references/clarify-critic.md` already contains a copy of CR Step 4's Apply/Dismiss/Ask framework (lines 67–79). Its preamble reads (line 69):

> (Apply/Dismiss/Ask framework below — including the self-resolution step — matches `/critical-review` Step 4 — reproduced here to avoid silent drift.)

The consolidate lifecycle's research.md flagged this exact risk (line 27): *"Inter-skill coupling: clarify-critic.md:60 explicitly says 'Mirror the critical-review skill's framework exactly' for the Apply/Dismiss/Ask logic. This is prose-level coupling, not code reuse — CR framework changes will silently drift clarify-critic.md."*

Adding devils-advocate as a third mirror raises drift count from 2 to 3, with an additional complication: devils-advocate's mirror would use **inverted** anchor semantics (CR anchors Dismiss-to-artifact; DA anchors Apply-to-source).

### Prior consolidate lifecycle constraints

The APPROVED `consolidate-devils-advocate-critical-review` lifecycle's `spec.md` Edge Cases section explicitly preserved "What This Isn't":

> **DA's "What This Isn't" section**: This section ("Not a blocker. Stop after making the case.") should be retained as-is — it is behavioral guidance not covered by the 4 elements, and it is not part of the error handling or examples being trimmed.

That spec also contains explicit Non-Requirements:

> This spec does NOT change /critical-review's core structure, dispatch prompt, Step 4 logic, or Apply/Dismiss/Ask definitions
>
> This spec does NOT introduce any 'DA invokes CR' or 'CR invokes DA' delegation pattern

This work introduces semantic shape-sharing (not delegation, but invariant coupling), which is in the same family as the boundary the consolidate spec drew, and re-opens a line that consolidate explicitly preserved.

## Web Research

### Self-critique loops in LLM agent frameworks

- **Self-Refine** (Madaan et al., 2023, https://arxiv.org/abs/2303.17651) — canonical iterative critique→revise loop. Effective for stylistic polish; weaker for reasoning correction.
- **Reflexion** (Shinn et al., 2023, https://arxiv.org/pdf/2303.11366) — uses trial-and-error signals, not pure self-judgment.
- **CRITIC** (Gou et al., ICLR 2024, https://arxiv.org/abs/2305.11738) — explicitly frames LLM intrinsic self-verification as unreliable; critique must interact with **external tools** (search, code executor) to verify claims.
- **Constitutional AI** (Anthropic, 2022, https://arxiv.org/abs/2212.08073) — critique-revise loop where principles act as **external anchors**; the critic must cite a constitutional rule.
- **LangChain Reflection pattern** (https://blog.langchain.com/reflection-agents/) — community-documented design pattern with growing literature flagging it as double-edged.

### Anchoring bias in single-context self-review (load-bearing finding)

- **"Anchoring Bias in Large Language Models: An Experimental Study"** (https://arxiv.org/abs/2412.06593) — tested several "just tell the model" mitigations and found them **all ineffective**: Chain-of-Thought, "Thoughts of Principles", explicit "ignoring anchor hints", reflection-based approaches. Conclusion: surface-level prompt interventions do not overcome the underlying anchoring vulnerability — only **multi-angle/multi-faceted information exposure** helps.
- **"Large Language Models Cannot Self-Correct Reasoning Yet"** (Huang et al., ICLR 2024, https://arxiv.org/abs/2310.01798) — DeepMind. Intrinsic self-correction does not improve and **often degrades** performance on arithmetic, QA, code, plan generation, and graph coloring. Self-correction works only when leveraging external sources.
- **"Cross-Context Review (CCR)"** (https://arxiv.org/html/2603.12123) — directly names the pattern: "start a new session, give the model only the final artifact with no production history, and ask it to review." Frames fresh-session review as the structural fix and characterizes in-context self-review as anchoring-prone.

**Implication for this feature**: Prompt-level instructions cannot rescue single-context self-review. The "default to Dismiss + anchor-to-source" calibration is a prompt-level intervention applied to the same agent that produced the critique. The literature says this category of intervention does not work.

### Citation-grounded critique pattern (prior art for the proposed approach)

- **ClaimCheck** (https://arxiv.org/html/2503.21717) — operationalizes citation-grounded critique: weaknesses must "explicitly quote or otherwise make explicit reference via paraphrase to a specific claim" in the source. Ungrounded critiques are treated as invalid.
- **OpenAI LLM Critics** (McAleese et al., https://cdn.openai.com/llm-critics-help-catch-llm-bugs-paper.pdf) — critic format requires attaching comments to verbatim quotes. Quoting is structural, not soft.
- **"According to..." prompting** (Weller et al., https://arxiv.org/html/2305.13252v2) — directs models to ground responses in source text, measured via exact-quotation overlap.
- **Deterministic Quoting** (Yeung, https://mattyyeung.github.io/deterministic-quoting) — design pattern from healthcare LLM work where any claim in "quote" format must be a verbatim source substring, enforced **outside** the model.

**Convergent pattern**: structural requirement is *quote something verbatim or the critique doesn't count*. Prior art is solid — the approach has academic precedent. **But**: in every cited case, enforcement is either by a separate critic agent or by an external validator — not by the same agent producing the critique.

### Decision-science: devil's advocacy

- **Schwenk 1990 meta-analysis** (Organizational Behavior and Human Decision Processes, https://www.sciencedirect.com/science/article/abs/pii/074959789090051A) — both DA and dialectical inquiry produce higher-quality recommendations. Documents **both failure modes**: DA being ignored (under-applied) AND DA over-dominating. Implementation determines which failure mode dominates.
- **Janis-derived groupthink work** (https://link.springer.com/article/10.1007/s42001-020-00083-8) — DA only works when (a) role is structurally assigned, (b) objections are evaluated on evidence not rhetoric, (c) the group does not mistake "we considered" for "we disarmed."

### Anti-patterns documented for self-critique loops

- **Snorkel "Self-Critique Paradox"** (https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/) — *"Self-refine loops degrade performance on easy tasks while rescuing hard ones."* Accuracy collapsing 98% → 57% on high-confidence tasks; the critic primed to find errors invents them; judges prefer hedged answers over correct confident ones. Recommendation: **"If your agent is confident and the task is standard, shut the critic up."**
- **Google Research / DeepMind** (https://research.google/blog/can-large-language-models-identify-and-correct-their-mistakes/) — LLMs cannot reliably find reasoning errors even when they exist, and **invent errors when primed to look for them**.
- Documented anti-patterns: infinite revision spirals, hedging drift, invented errors, complexity creep, anchoring to recent context.

### URLs that failed to fetch
- https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/ — JS-only page; meta description and search snippets used.
- ArXiv abstract pages for 2412.06593 and 2310.01798 returned only abstracts; sufficient for the load-bearing claims.

## Requirements & Constraints

### project.md (verbatim)

> **Daytime work quality**: Research before asking. Don't fill unknowns with assumptions — jumping to solutions before understanding the problem produces wasted work.
>
> **Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct.
>
> **Quality bar**: Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself.
>
> **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows.

### multi-agent.md

Does NOT govern devils-advocate. Devils-advocate is single-context, not multi-agent. Only tangentially relevant rule (line 72): *"Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents."* — consistent with devils-advocate's existing inline model.

### lifecycle.config.md

`skip-review: false` — full lifecycle review will gate this change. Review criteria are trivial for a SKILL.md edit (frontmatter present, symlink pattern, JSON validity — all automatically satisfied).

### CLAUDE.md / claude/rules/

No project-level constraint on how skills should handle their own user contracts.

### Scope boundaries

- Skills are in-scope (`requirements/project.md` "AI workflow orchestration").
- Devils-advocate sits outside multi-agent governance.
- The load-bearing requirement is project.md's **"Complexity must earn its place"** — this single principle is the bar this feature must clear.

## Tradeoffs & Alternatives

### 1. Unit of classification

- **A. 1 H3 section = 1 objection** (4 dispositions per run). Recommended by tradeoffs agent.
  - Pros: simplest; bounded; matches singular prose ("the most likely way", "the one hidden load-bearing assumption").
  - Cons: Unexamined Alternatives section can name multiple alternatives. Forcing one disposition collapses them. Either valid alternatives get dismissed alongside speculative ones, or speculative alternatives get applied alongside valid ones — precision loss.
- **B. Multi-objection per section, each classified separately**.
  - Pros: faithful to multi-claim sections; matches `/critical-review`'s discrete-objection iteration.
  - Cons: requires restructuring Step 2's prose output into bullets, or adding a parse pass.
- **C. Hybrid (section default + sub-objection breakouts)**.
  - Pros: flexible.
  - Cons: "allowed but optional" rules in skill prose are reliably ignored.

### 2. Project Context loading

- **A. Add a Step 0 analogous to CR §2a**.
  - Pros: parallel structure with critical-review.
  - Cons: duplicated work — host agent already has context.
- **B. Skip entirely**. Recommended by tradeoffs agent.
  - Pros: honors inline model; no duplication; keeps skill short.
  - Cons: cold-invocation case (fresh session, no prior context) lacks fallback.
- **C. Conditional on no-lifecycle**.
  - Pros: targets the gap.
  - Cons: adds branching.

### 3. Anchor source generalization

- **A. Unified concept, two realizations** (lifecycle artifact OR user-stated direction). Recommended by tradeoffs agent.
- **B. Two separate code paths**. Cons: duplicates apply loop.
- **C. Broad anchor universe** (any conversation text). Cons: defeats the anchor rule's purpose.

### 4. Where the apply loop lives

- **A. New Step 3 "Apply Feedback"** between Step 2 and Success Criteria. Recommended.
- **B. Restructure Step 2** to combine case-making with classification. Cons: breaks Step 2 identity.
- **C. Inline disposition tags inside Step 2**. Cons: discoverability drops.

### 5. "Stop after making the case"

- **A. Delete entirely.** Cons: loses the load-bearing anti-argument guard.
- **B. Revise** to "Stop after applying any clear-cut fixes and presenting the dismissed/asked objections — don't keep arguing." Tradeoffs agent recommended this.
- **C. Keep verbatim, frame apply loop as optional epilogue.** Cons: contradiction; optional steps in skill prose are reliably ignored.

### 6. No-lifecycle case mechanics

- **A. Apply loop runs, presents revisions verbally** (no file writeback). Tradeoffs agent recommended.
- **B. Skip apply loop entirely when no lifecycle.**
- **C. Propose-and-confirm model.**

### Tradeoffs agent's recommended approach

Skip Project Context loading (B), unified anchor source (A), new Step 3 (A), revise "Stop after making the case" (B), 1-section-1-objection (A), no-lifecycle apply runs verbally (A).

## Adversarial Review

The adversarial agent attacked each tradeoffs recommendation and made a strong descope case. Findings ordered by severity.

### Attacks on the calibration mechanism

- **Citation theatre is still anchoring.** The web research is unambiguous (arXiv 2412.06593: prompt-level "ignore the anchor" instructions do not work in single-context; Huang et al. 2310.01798: LLMs cannot self-correct reasoning without external grounding). The proposed anchor-to-source rule requires the *same host agent that produced the critique* to select which artifact text a fix "anchors to." That selection is itself anchored — the agent will find text supporting the fix it already wants to apply. Critical-review's anchor rule works **structurally** because the synthesizing agent did not produce the critiques (a fresh Opus synthesizer operating on outputs from fresh reviewers). Transplanting the rule into single-context strips it of the structural property that made it work. **The calibration does not solve the problem the literature flags as unsolvable; it makes the bias legible but still operative.**

- **No-lifecycle case collapses every Apply into a structural Dismiss.** Suppose the user says "use Postgres for OLAP queries on historical data" and devils-advocate's Unexamined Alternatives proposes "use DuckDB instead." For the apply loop to classify this as Apply, it must cite user-stated text that grounds the fix — but the user's text says "Postgres", which is what the fix contradicts. The only user text that could anchor the fix is the user text the fix overrides. Either: (a) the rule forces Dismiss on every conversation-mode Apply, making the apply loop dead code there; or (b) the rule permits citing user text the fix opposes (the rule with its teeth pulled). **The "apply loop runs, presents verbally" recommendation hides this contradiction.**

- **"Conversation-stated direction" is unstructured; clarify-critic.md is not the precedent claimed.** Clarify-critic.md works because the orchestrator **freezes source text into a fresh critic agent's prompt at dispatch time**. Devils-advocate is inline; there is no dispatch, no freeze. The "conversation-stated direction" is a rolling transcript across N turns where the user may have updated the direction mid-conversation and the agent's own prior responses are interleaved. Anchoring to "what the user said" is unresolvable without a structured input contract that does not exist for inline skills.

### Attacks on the per-section design

- **"1 section = 1 objection" forces information loss on the section that routinely has multiple.** The Output Format Example's Unexamined Alternatives section currently demonstrates a multi-alternative pattern. The body text says "Name approaches that weren't considered" — plural. Under the recommendation, one disposition covers the whole section, so if alternative A is concrete-and-applyable but alternative B is speculative, the agent must pick one disposition for both. The recommendation makes the apply loop's precision strictly worse on the section where DA currently adds the most specific value.

- **Dispositions are incoherent on Tradeoff Blindspot** (and arguably also on Fragile Assumption). A Tradeoff Blindspot finding is by definition a *judgment about priorities*, not a fix. There is no "Apply" — the whole category is a sensibility the user either adopts or doesn't. Under the "default to Dismiss" rule, this section will always Dismiss, turning 25% of the critique into a structural dead zone. The 4-section design shape mismatches the information content of at least one section.

### Attacks on the structural risk

- **Schwenk over-domination: the apply loop structurally amplifies the critique.** Current devils-advocate outputs an opinion the user can accept or reject. The proposed apply loop lets devils-advocate **edit the lifecycle artifact** under Apply, upgrading the critique from "advisory opinion" to "artifact mutation." Schwenk 1990 documents both failure modes (ignored AND over-dominating); the proposed design moves the failure distribution toward over-domination by adding a mechanism for the critique to write itself into the source of truth. The "default to Dismiss" prompt-level guard operates on the same agent that web research shows cannot suppress anchoring via prompt instructions. **The calibration is the wrong type of countermeasure against the risk the design introduces.**

- **Self-critique paradox is not neutralized by default-to-Dismiss.** Snorkel's finding: critic loops applied to high-confidence correct output make it worse because agents primed to find errors invent errors. Default-to-Dismiss addresses the *disposition* an invented error gets but does not prevent the *invention*. The apply loop re-primes the agent to evaluate its own prior critique — a second critic pass stacked on a first. The web research's strongest signal is that this stacking is the anti-pattern. Snorkel's recommendation is **"shut the critic up"**, not "run the critic and bias its output." There is no analysis of when the apply loop should run vs. skip; it is recommended to always run.

### Attacks on mirror count and the "Stop after making the case" revision

- **Silent drift across three mirrors — already empirically evidenced.** The consolidate lifecycle's research.md flagged this exact risk and the fix (inline comment) is *textual warning*, not technical guarantee. Adding a third mirror multiplies the invariants future editors must hold. Worse, devils-advocate's mirror would be **inverted** (CR anchors Dismiss-to-artifact; DA anchors Apply-to-source). A future editor reading "matches /critical-review Step 4" will assume identity and propagate a CR change verbatim, breaking the intentional inversion.

- **The "Stop after making the case" line is load-bearing and the revision quietly relaxes it.** The original line's function is to prevent the agent from re-asserting itself after the user has heard the case. The recommended revision ("Stop after applying any clear-cut fixes and presenting the dismissed/asked objections — don't keep arguing") inserts two re-assertion channels (artifact edits; dispositions summary) between "case made" and "stop." A dispositions summary that says "I applied these 2 and dismissed these 2 because X" **is** continued argument, presented with structural authority. The original line was specifically targeted at this behavior. The consolidate lifecycle just preserved this line as load-bearing two cycles ago — re-opening it without new evidence is re-litigation.

### Attack on the value case

- **No reproduced user problem cited.** The lifecycle's own events.log shows the orchestrator escalated complexity/criticality during clarify because requirements alignment was *"asserted without demonstrated evidence — Complexity must earn its place is being waved rather than tested."* Project.md states (verbatim): *"Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."* The recommended design adds: a new Step 3, a disposition schema, an anchor sub-rule, a third Apply/Dismiss/Ask mirror, a revised user-contract line, and a conversation-mode handling rule. **No concrete user report of "devils-advocate over-applied / under-applied" has been cited.** The failure modes listed come from 1990 decision-science literature and 2024 LLM papers, not from observed devils-advocate behavior in this codebase. The machinery is symmetry-with-critical-review, not a fix for a reproduced failure.

- **Apply-without-file-writeback is structurally indistinguishable from current behavior.** In conversation mode, "apply loop runs, presents revisions verbally" is just "make a case the user can verbally accept or reject" — which is what current devils-advocate already does. Adding a dispositions classification and presenting revised text verbally is ceremony around an existing capability.

### Adversarial agent's recommended mitigations

1. **Descope to "do nothing" or to a minimal note.** The strongest finding: no reproduced user problem, mirror count rises, "Stop after making the case" is quietly relaxed, calibration does not neutralize the unfixable anchoring. Leave devils-advocate as the consolidate lifecycle left it. Users who want artifact edits applied use `/critical-review`.
2. **If shipping anyway: cut conversation-mode apply entirely.** Restrict the apply loop to lifecycle case only. In conversation mode, devils-advocate produces the 4 sections and stops.
3. **If shipping anyway: gate the apply loop on explicit user request, not default-on.** Require an explicit opt-in trigger ("devil's advocate — and apply what sticks") so the default invocation is unchanged.
4. **If shipping anyway: do not add a third mirror.** Inline with explicit inversion callout: *"adapted from /critical-review Step 4 with INVERTED anchor semantics: CR anchors Dismiss-to-artifact, DA anchors Apply-to-source. Changes to CR Step 4 must not be propagated verbatim here."*
5. **If shipping anyway: preserve "Stop after making the case" verbatim; locate the apply loop above it.** Insert new steps before "What This Isn't" without modifying that section, so the final behavioral guard remains intact.
6. **If shipping anyway: per-objection dispositions, not per-section.** Accept the loss of simplicity to preserve apply-loop precision on multi-claim sections.

## Open Questions

The adversarial review surfaces decisions that **cannot be made without user input** — they affect whether and how the feature ships at all. These must be resolved before the spec phase begins:

1. **Descope decision (load-bearing)**: Does this feature ship as planned, ship in a reduced form, or descope entirely? The cost/benefit landscape has changed materially since clarify:
   - **Descope**: leave devils-advocate alone. Users wanting artifact edits use `/critical-review`. Zero cost, preserves consolidate lifecycle's just-shipped contract, no third mirror, no "Stop after making the case" relitigation.
   - **Lifecycle-only apply**: ship the apply loop, but only when a lifecycle artifact exists. Drops the broken no-lifecycle case. Solves about half the structural problems.
   - **Opt-in apply**: ship as designed, but the apply loop only runs when the user adds an explicit trigger ("apply what sticks"). Default invocation unchanged.
   - **Ship as planned**: accept the adversarial findings as known limitations and ship the full design with the user's chosen calibration.

2. **Third-mirror policy**: Does this work add a third copy of the Apply/Dismiss/Ask framework to the repo? Or does it pause to first build a shared reference, or does it inline with an explicit inversion-callout comment? The consolidate lifecycle previously paid a visible cost to limit drift — this work should engage that decision explicitly, not silently re-add a mirror.

3. **Tradeoff Blindspot dead-zone**: 25% of devils-advocate's output (Tradeoff Blindspot) is structurally non-applyable because it produces sensibilities, not fixes. Should that section be exempt from the apply loop, or should the apply loop be designed to accept "Apply = the user should adopt this sensibility" as a valid disposition?

4. **Anchor mechanics for the no-lifecycle case** — *if* the no-lifecycle case ships at all: how does an Apply cite user-stated text when the Apply's purpose is to contradict user-stated text? The structural contradiction in §"No-lifecycle case collapses every Apply into a structural Dismiss" must be resolved before the no-lifecycle apply path can be specified.

5. **"Stop after making the case" disposition**: keep verbatim and locate the apply loop above it (adversarial recommendation), or revise to integrate (tradeoffs recommendation)? The consolidate lifecycle's preservation of this line means revision is re-litigation; the user should explicitly re-open the decision or let it stand.

6. **Per-section vs per-objection unit**: tradeoffs agent recommends 1 section = 1 objection; adversarial agent argues this destroys precision on multi-alternative sections. Which is correct depends on how often Unexamined Alternatives sections actually surface multiple discrete alternatives in practice — the user has the empirical data (they have invoked devils-advocate repeatedly).
