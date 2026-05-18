# Research: Discovery output density — author-centric prose at gate

## Codebase Analysis

### Surface area: what files would change under each candidate lever

- `skills/discovery/SKILL.md` (~107 lines). Gate prose at lines 72–90 ("Research → Decompose approval gate, spec R4") names `## Headline Finding` as the gate's first content section followed by the full `## Architecture` section. A `--- IF MISSING ---` fallback at 74–75 surfaces a warning when Headline Finding is empty/whitespace-only. Under every candidate lever this file changes — either to suppress sections, to render slots, or to invoke a new lint.

- `skills/discovery/references/research.md` (~205 lines). The discovery research-artifact template. HTML-comment authoring directives at lines 79–84 (Headline Finding: "One paragraph. State the verdict and the one or two key findings supporting it"), 118–127 (Architecture: "Name the pieces by role, integration shape, seam-level edges"), 139–160 (`### Why N pieces` falsification-gate merge-history when piece_count > 5, with template walk-back rule R1), 165–172 (Decision Records: `### DR-1: [Decision title]` numbering scheme). The DR-N/RQ-N/OQ-N labeling scheme emerges from the numbered structure even though the template does not name the acronym scheme.

- `cortex_command/discovery.py` (~686 lines). The discovery skill's helper module: event emission (`approval_checkpoint_responded`, `architecture_section_written`) and events.log path resolution. **Zero rendering logic.** There is no Python surface where length validation could be inserted today without building one.

- `skills/discovery/references/decompose.md`. Consumes `### Pieces` bullets 1:1 (lines 11–13: each bullet becomes one ticket candidate). Load-bearing for any change that touches Architecture/Pieces shape. Line 121 contains a directly-relevant deferral: "The scanner runs once at decompose ticket-write time. Defense-in-depth at architecture-write time is deferred." This is the named gap.

- `bin/cortex-check-prescriptive-prose`. Section-partitioned LEX-1 scanner. SCAN_GLOBS at lines 41–45 covers `skills/**/*.md` and `cortex/backlog/*.md` only. **Does NOT scan `cortex/research/**/*.md` or `cortex/lifecycle/**/research.md`.** A new lint targeting research artifacts is greenfield scope; the existing scanner is a code-shape precedent but not a coverage precedent.

- `tests/test_discovery_gate_presentation.py`. Pins verbatim marker phrases (`R1_HEADLINE_MARKER_PHRASE = "State the verdict and the one or two key findings supporting it"`) and asserts ordering. **Pins template fidelity, not produced-output compliance.** This is the test class that passed under Phase 1 while production artifacts drifted.

- `tests/test_skill_size_budget.py`. 500-line cap on SKILL.md files. Closest existing precedent in the repo for "structural enforcement of content length" via a measurable property — could be cloned for per-section word budgets on research artifacts.

- `skills/lifecycle/SKILL.md` "Kept user pauses" inventory + `tests/test_lifecycle_kept_pauses_parity.py`. The research→decompose gate is a kept user pause. Any new sub-pause (e.g., a lint-block step) must update both in lockstep, with a named user-facing affordance.

### Reader-study replication on current artifacts

Sampled the smallest- and largest-Headline current artifacts.

**`cortex/research/cursor-skill-port/research.md`** — Headline Finding = **171 words** (single paragraph). Forward references in the Headline alone: `A-zero-change` / `B-content-only` / `C-behavioral-degradation` rubric labels used as if known (rubric is implicit later in Codebase Analysis), `DR-3`/`DR-5` cited before Decision Records section, `OQ7`/`OQ8` and `R1`/`R3`/`R13` cited without anchor. Architecture's first Pieces bullet is **243 words** ("Release-publish path…") densely citing `DR-5` and `DR-3` before either is defined. Author-process narration: the Architecture block closes with "(piece_count = 3; "Why N pieces" subsection skipped per template R3 — fires only when piece_count > 5. The honest decomposition omits the converter/publish split that earlier drafts presented separately…)."

**`cortex/research/interactive-overnight-mode/research.md`** — Headline Finding = **402 words**. Forward references: `Architecture A`/`B`/`C` labels cited in Headline before defined, `DR-3`/`DR-5`/`DR-6` cited before Decision Records, `Q1`/`Q2`/`Q6`/`Q7` cited before Open Questions, ticket numbers `#208`/`#214` named without gloss, spec-anchor references `R17`/`R18`/`R1` named without in-artifact gloss. Architecture's first Pieces bullet is **262 words**. Author-process narration is severe — the entire closing paragraph of the Architecture section is a verbatim merge-history record produced by the `### Why N pieces` template directive even though that subsection only fires at piece_count > 5: "Decomposition history: original was 7 pieces… Walked back per template rule R1 across three iterations… cost-telemetry-and-decision-artifact dropped per explicit user direction…"

**Three additional patterns beyond the ticket's three.**
1. *Headline-paragraph negation rebuttal* — pre-emptive caveats packed into the Headline ("B does NOT X / B does NOT Y / the alternative is presented as a v1-spec choice rather than a closed decision"). The author surfaces risk-management impulse at the wrong slot; the right slot is Decision Records (trade-offs).
2. *Citation-as-credibility-signal in Pieces* — `[path:line]` drops inside Pieces bullets are not load-bearing for gate readers' decisions but signal authorial rigor. Distinct from `[file:line]` in Codebase Analysis where the citation IS load-bearing.
3. *Conditional clauses repeated across sections* — the same structural distinction restated in 4 different sections (Headline, RQ-answer, table preamble, DR-body). Repeated re-framing of one claim, not restatement of it. Cause: the template asks each section to be "self-contained" without naming a canonical anchor.

### Does the pattern reproduce in non-discovery skills?

Partial yes. `cortex/lifecycle/add-project-glossary-at-cortex-requirements/research.md` reproduces heavy `[file:line]` citation density and `L91–L114` spec-anchor forward references. But it has no `## Headline Finding` or `## Architecture` section — lifecycle research follows the simpler `skills/research/SKILL.md` schema (Codebase / Web / Requirements / Tradeoffs / Adversarial / Open Questions). The catastrophic gate-display density concentrates at discovery because:
1. Discovery has a user-facing gate that quotes the artifact verbatim.
2. The discovery template adds Headline + Architecture + Decision Records sections on top of the lifecycle-research schema — sections the meta-skill does not require.
3. Lifecycle research feeds Specify (structured interview), not verbatim presentation.

The underlying authoring pattern (forward refs, citation density) reproduces; the user-facing reading damage is currently localized at the discovery gate. The adversarial review flags this as potentially circular reasoning — see Open Questions.

### Existing enforcement infrastructure

No infrastructure currently lints produced research artifacts. Two precedents bind in this repo:
- Lexical scanners on a fixed file glob (`cortex-check-prescriptive-prose`).
- Pytest tests against canonical source files (`test_discovery_gate_presentation.py`, `test_skill_size_budget.py`).

Prose discipline in template HTML comments has zero enforcement — empirically confirmed by the 171–402 word Headlines that shipped against "one paragraph."

## Web Research

### Mechanisms that BIND prose-output constraints (ranked)

1. **Structural separation via fresh-context generation pass.** A second agent with explicit reader rubric produces the public-facing artifact. Matches Anthropic's extended-thinking model (thinking absorbs exploration, output stays reader-facing). Pinker's Curse of Knowledge identifies this exact mechanism as the empirically-validated fix: *show drafts to people outside your field*. The author cannot regress their own mind to pre-knowledge state by intention.
2. **Slot-based template with bounded free-text per slot + post-hoc validator.** Slot shape constrains form; validator catches density violations post-generation. Caveat: Anthropic Structured Outputs (public beta) **drops** `maxItems`/`maxLength` constraints — schema enforces field presence, NOT density per field. Density binding must be external (Vale-style lint, custom validator).
3. **Critic-loop with explicit rubric.** Self-Refine reports gains, but the rubric must be concrete. Generic "make this more reader-centric" recapitulates the original failed directive — Reflexion literature is unambiguous: "If you don't define what 'good' means, the critique becomes generic and revision won't improve much."
4. **Curated positive few-shot examples.** Anthropic guidance: positive examples beat negative instructions. Brittle to example contamination — one author-centric example in the skill prompt is replicated regardless of any directive against it.

### Why prose-only directives drift

- **Attention decay over long generations** (COLM 2024, "Measuring and Controlling Instruction Drift"). Longer dialogs reduce weight on initial tokens. A "one paragraph" directive embedded once in a long skill prompt loses weight as the artifact grows.
- **Anthropic explicit guidance.** "Be concise" loses to "Limit your response to 2–3 sentences" with specific numeric bounds. The Phase 1 directive ("One paragraph. State the verdict…") is the failing pattern by Anthropic's own framing.
- **Positive examples > negative instructions.** Anthropic prompt-engineering best practices explicitly: positive examples are more effective than "don't do X." The current template's directives are a mix; the strongest binding shape is positive exemplar.
- **System-prompt-only enforcement is structurally lower-weight** than user-turn enforcement. Density rules embedded deep in SKILL.md sit in the lowest-weight position.
- **Drift is bounded stochastic, not monotonic decay.** Structural reinforcement (re-statement at generation point, post-hoc validator, structured output) controls it. Pure prose discipline does not.

### Non-LLM prior art

Pinker's "Curse of Knowledge" (The Sense of Style) is the closest empirical parallel to this exact failure. The expert author cannot remember what it's like to not know something. The prescribed mechanism is **external** (show drafts to outsiders), **not internal discipline** (try harder to remember the reader). This matches the discovery skill's pattern exactly: the author-agent that produces the dense artifact cannot self-correct from inside the same generation context.

The compressor / gate-brief mechanism is the LLM-shaped instantiation of "show drafts to outsiders."

### Anti-patterns

- Prose-only conciseness directives ("be concise," "one paragraph").
- Negative instructions ("don't write author-centric prose").
- JSON Schema length constraints (Anthropic drops them).
- Generic critic rubrics ("make this clearer").
- System-prompt-buried density rules.

## Requirements & Constraints

### Directly governing constraints

- **CLAUDE.md Skill / phase authoring guidelines.** "Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low." The current Phase 1 mechanism is prose-only enforcement of a behavioral constraint; the cost of deviation is not low (the user complaint).

- **CLAUDE.md Solution Horizon.** "Before suggesting a fix, ask whether you already know it will need to be redone — because a follow-up is already planned, the same patch would apply in multiple known places you can name, or it sidesteps a constraint you can already name. If yes, propose the durable version, or surface both choices with the tradeoff." Two of three triggers fire by current knowledge: (a) the ticket names lifecycle research / plan / spec as places the same patterns likely show up; (b) Phase 1 already failed once. Per Solution Horizon, the obligation is to surface the tradeoff between narrow and durable, not silently pick the narrow lever.

- **CLAUDE.md "Prescribe What and Why, not How."** The current template prescribes How (DR-N numbering scheme, walk-back protocol R1, merge-history record format). This is procedural narration the principle explicitly says to resist. Any spec must reduce How-prescription and re-anchor on What and Why.

- **CLAUDE.md MUST-escalation policy.** Format-conformance is OQ3-eligible. A new MUST requires an `events.log` F-row showing the soft form was skipped AND an `effort=high` dispatch result. The cleanest alignment is to avoid MUST entirely — runtime-enforced binding (lint, helper, structural shape) sidesteps the policy because it doesn't ask the model to comply; it measures output.

- **project.md Skill-helper module pattern.** "When a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry." A new research-artifact validator fits this pattern — either as a subcommand of `cortex_command/discovery.py` or as a new `bin/cortex-check-*` scanner.

- **project.md Two-mode gate pattern.** Pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide). Any new scanner should adopt this shape. Note: a `--staged` mode is the wrong shape for a gate that fires mid-skill-execution, before commit — see Adversarial Review's failure mode #4.

- **project.md SKILL.md size cap.** 500 lines, exceptions via in-file comment, default fix is extraction. Adding template directives concentrates structure; extracting validation to a helper distributes it.

### Adjacent deferral that this work effectively closes

`skills/discovery/references/decompose.md:121` — verbatim: "The scanner runs once at decompose ticket-write time. **Defense-in-depth at architecture-write time is deferred.**" This deferral predates the current ticket and is named in the discovery skill's own reference. Extending validation to architecture-write time is exactly the gap.

### Scope boundaries

In scope: AI workflow orchestration (discovery skill, research-phase template, decompose phase, research→decompose gate); skill authoring patterns (helper modules, `bin/cortex-check-*`, two-mode gates); cross-skill template hygiene if the lever extends to lifecycle/refine.

Out of scope: dotfiles, machine config, application code, published packages.

## Tradeoffs & Alternatives

The four ticket-named candidates plus six the evidence surfaces. Each scored on binding-mechanism class, complexity, reversibility, alignment with repo patterns.

| Candidate | Binding mechanism | Complexity | Reversibility | Alignment |
|---|---|---|---|---|
| A: Template authoring-directive trim | Prose discipline | Low | Trivial | **Mixed — same class as Phase 1 fix** |
| B: Audience split (decompose vs gate, two artifacts) | Structural at artifact level | Medium–high | Medium | Contradicts archived spec's Non-Req (recoverable) |
| C: Cross-skill authoring framework | Depends on shape | High | Low | Solution Horizon durable; **premature on current evidence** |
| D: Gate-only suppression | Prose discipline (negative routing) | Low | Trivial | Low — already flagged fragile by archived crit-review |
| E: Multi-pass / gate-brief generator | Structural separation via fresh-context generation | Medium–high | Medium | **Matches Pinker external-critic prior art and Anthropic extended-thinking model** |
| F: Slot template with caps | Prose discipline (template shape) | Low | Trivial | Same structural shape as Phase 1 — caveat applies |
| G: Output linter over `cortex/research/**/*.md` | Runtime validation | Medium | Trivial | **Matches `cortex-check-prescriptive-prose` precedent shape; greenfield scope** |
| H: Two-section template (author-private + reader-public) | Structural delimiter + helper | Medium | Medium | Binds only if a Python helper enforces the split, not prose |
| I: Inline positive/failing examples in template | Prose discipline with anchor | Trivial | Trivial | Additive only |
| J: Extended-thinking absorption | Prompt shaping | Low | Trivial | Speculative |

### Where the load-bearing change actually lives

Adversarial review crystallized this: F (slot template) is structurally identical to the Phase 1 mechanism — directive in template + structural test pinning the directive. The mechanism that *did not bind*. G (lint over produced output) is the genuinely novel binding mechanism. F is decorative without G; G stands alone as a binding mechanism without F. Treating F+G as one bundle obscures this — the spec should evaluate G against alternatives (corpus-regression test, worked-example template, gate-brief generator E) rather than treat F's slot caps as load-bearing.

### Where the agents' "F+G is durable" claim borrows credibility it doesn't earn

The Web research cited Pinker's Curse of Knowledge as supporting structural separation. The empirically-validated mechanism Pinker names is **an external reader, not a syntactic lint**. The candidate that matches Pinker's prior art is E (gate-brief generator with fresh context + reader rubric), not F+G. F+G is a syntactic lint that catches lexical drift patterns; it is not an outside reader. Conflating these mechanisms is the same author-centric blindness this research is about — the agents looked at what they could measure and called the rest equivalent.

### Where Solution Horizon was silently violated

Per `CLAUDE.md`: when same-patch-in-multiple-places or foreseeable-follow-up triggers fire, "propose the durable version, or surface both choices with the tradeoff." The ticket explicitly names both triggers. A defer of Candidate C without surfacing the narrow-vs-durable tradeoff to the user is a Solution Horizon violation by current knowledge. The spec phase must surface this tradeoff explicitly.

### Recommended approach (revised after adversarial review)

The strongest evidence-grounded recommendation is **G as the load-bearing binding mechanism, paired with E (gate-brief generator) as the structural-separation lever Pinker's prior art validates**, with F's slot-template change reframed as a content-shape revision (template trim of How-prescriptive directives — DR-N numbering, walk-back narration, named-contract-surface vocabulary) rather than as load-bearing on its own.

**G — lint over produced research artifacts.** New `bin/cortex-check-research-output` (or extension of `cortex-check-prescriptive-prose` to a new SCAN_GLOBS entry). Pattern surface: forward references to undefined vocabulary (acronyms cited before defined), Why-N narration tokens in non-Why-N sections, citation-as-credibility-signal density in Pieces, conditional-clause repetition across sections. Caps derived from the compression-test corpus (~2.5× compression baseline), not asserted. Lint mode (block vs warn) is an explicit binding choice the spec must commit on.

**E — fresh-context gate-brief generator.** A skill-internal sub-dispatch invoked at the research→decompose gate. Takes the dense research.md as input; produces a ≤200-word reader-facing brief with explicit reader rubric ("first-time cold reader at a decision gate"). The gate displays the brief, not the raw artifact. Decompose continues to consume `### Pieces` from the dense artifact. This decouples production from consumption — the load-bearing structural separation Pinker's prior art validates.

**F (revised) — template trim.** Drop DR-N/OQ-N/§N cross-reference vocabulary, drop Why-N walk-back narration, replace "named contract surfaces" with reader-facing vocabulary. Not load-bearing on its own (Phase 1 evidence); reduces the temptation surface for the patterns G lints against.

**Solution Horizon obligation.** The spec must surface to the user: (a) the narrow F+G+E lever scoped to discovery, (b) the durable C lever scoped cross-skill (lifecycle research / plan / spec same authoring framework), and (c) the tradeoff between them. The recommendation defaults to (a) on the empirical grounds that the user-facing damage is currently localized at the discovery gate, but the deferral of (b) must be explicit and named, not silent.

### What this approach does NOT do

- Does NOT solve the author-centric prose pattern in lifecycle research / plan / spec. Deferred to Candidate C as a Phase 2 driven by evidence.
- Does NOT introduce JSON Schema validation (Anthropic drops length constraints; not the right mechanism).
- Does NOT rely on prose discipline at the gate (E moves rendering into a fresh-context generation pass).
- Does NOT pin the spec to specific word-count caps in this research artifact. Caps must be derived from compression-test corpus in the spec phase.
- Does NOT eliminate the prose-discipline component entirely — E's reader rubric is itself prose-prompted, but in a fresh context where attention-decay does not apply to the original directive.

## Adversarial Review

### Failure modes of slot-template + lint (F+G as originally framed)

- **The lint-as-blocker / lint-as-warning bifurcation is unresolved and each branch fails.** As blocker: drift on a tight cap becomes infinite-revision (model regenerates, hits cap, regenerates again). Escape hatch is `--force`, structurally identical to "click through warnings." As warning: same affordance the Phase 1 fix had — user sees signal at the gate, ships anyway. Either mode replicates the Phase 1 failure shape unless the spec commits explicitly to one and names what user behavior must change.
- **Pinning slot caps in tests constrains the template's directive, not the model's output.** The Phase 1 test pinned the marker phrase verbatim; the test passed; production drifted to 402 words. The test class implied by F+G is empirically indistinguishable from the class that just failed.
- **The lint must fire mid-skill-execution, not at pre-commit.** Research artifacts are produced by a running skill; the gate fires before commit. The existing `--staged` precedent is the wrong shape. The lint's invocation point is itself prose-instructed in SKILL.md — same failure class F+G is trying to escape.
- **Slot caps don't address Pieces or Architecture drift, which is half the user's complaint.** Ticket: *"When [/discovery] outputs the whole pieces and architecture section, it is very complicated."* Agent 4's preserve-decompose-contract framing left Architecture/Pieces untouched. The 243-word Pieces bullets reproduce the three patterns; slot caps in a new Decision Surface header don't reach them.
- **The recommendation creates a new kept user pause without naming it.** Per CLAUDE.md: identify the user-facing affordance every gate protects. The kept-pauses inventory + parity test would need updating in lockstep.

### Where the synthesis anchored vs. evidence-grounded

- **Pinker's structural fix is external critic, not internal lint.** F+G borrowed Pinker's credibility without inheriting the mechanism. E (gate-brief generator) is what matches the prior art.
- **"Lifecycle research doesn't suffer" is unmeasured.** The empirical evidence is one direction (user complained about discovery). Absence of complaint elsewhere is not evidence of cleanness — could be evidence of user not engaging at that angle. Discovery may be the visible-damage skill, not the only-damage skill.
- **The 30–40 word slot caps are asserted, not evidence-grounded.** Compression-test data: 171 words → ~68 compressed, 402 → ~160. Even the compressed honest version exceeds asserted caps by 2–5×. Caps must be derived from the corpus, not from authoring intuition.
- **"F+G preserves the decompose contract" understates the cost.** The gate-display contract still relies on prose discipline ("suppress Architecture body") in any form of F+G that doesn't move rendering into a separate generation pass. That's exactly the fragile mechanism the archived crit-review flagged.

### Assumptions that may not hold

- **A slot template is structurally different from the current template.** The current template IS a slot template — `## Headline Finding` with an HTML-comment directive. Phase 1 added that slot; it drifted. Adding more slots with shorter caps is the same structural shape with smaller surfaces. The archived spec's own self-flag: "Subdividing one drift-prone slot into five identically-governed slots may *increase* aggregate drift."
- **The model respects numeric word caps in HTML comments.** "≤30 words" in an HTML comment is prose. No generation-time enforcement. Anthropic's bounded-conciseness guidance applies to response generation, not to template-fill at length where attention-decay binds harder.
- **Lint catching drift translates to drift being fixed.** Phase 1 had visible-at-gate signal. Production shipped at 171–402 words. There is no evidence in this repo that more granular signal (lint output rather than gate prose drift) changes user behavior at the gate.
- **The SKILL.md gate prose can be rewritten to display slots reliably.** That rewrite is itself a prose instruction in the same drift class. F+G inherits this unaddressed.

### Alternative framings under-weighted by the primary research

- **Gate-side rendering, not authoring-side enforcement.** The E variant. Artifact authored as-is for decompose; gate dispatches a fresh sub-agent with explicit reader rubric to produce a ≤200-word brief. Matches Pinker's empirical mechanism and Anthropic's extended-thinking model. Agent 4 dismissed E because "compressor is itself prose-prompted" — but every candidate is prose-prompted at some level. The relevant distinction is whether the prose runs in the same context that produced the density (attention-decay applies) or in a fresh context (it doesn't).
- **Corpus-regression test against produced artifacts.** Snapshot real `cortex/research/*/research.md` files; assert word-count budgets, jargon density, forward-reference rates as quality bars. New artifacts get measured; CI fails when corpus mean drifts. Structurally load-bearing because it doesn't depend on the model reading prose — it depends on `tests/` running.
- **Drop the template, write a worked example.** Anthropic positive-example guidance outranks negative directives. A research.md template containing a worked Headline Finding of ~50 words on a representative topic, marked as exemplar, may bind better than cap directives.
- **The vocabulary problem ≠ the density problem.** User: *"throwing out technical terms"* (vocabulary) AND *"a ton of words to say not very much"* (density). Word-count caps address density only. The three reader-study patterns include forward references to undefined vocabulary — a separate mechanism (banned-token blocklist: `DR-N`, `OQ-N`, `§N`, named-contract compounds) is needed.

### Mitigations the spec phase must address

- Commit explicitly on lint mode (blocker vs warning) and name what user behavior must change at the gate.
- Derive word-count caps from compression-test corpus, not assert them.
- Treat G (lint) as the load-bearing change; F (slot template) as content-shape revision; E (gate-brief) as the structural separation Pinker's prior art validates.
- Surface the Solution Horizon tradeoff (narrow F+G+E vs durable C cross-skill) to the user explicitly, per CLAUDE.md obligation.
- Update kept-pauses inventory + parity test in lockstep if a new sub-pause is introduced.
- Acceptance criterion: re-run the four-agent reader-study on N≥3 artifacts produced under the new mechanism; report which of the 6 patterns reproduce. Ship only if pattern count drops below a stated threshold.
- Consider extending `cortex-check-prescriptive-prose` SCAN_GLOBS rather than introducing a new binary — justify the choice in the spec.

## Open Questions

These questions are deliberately unresolved at research-exit. Each shapes the spec phase materially and the user should drive resolution at spec-time, not in this artifact.

1. **Lint mode at the gate: blocker or warning?** Both modes have known failure cases (infinite-revision vs click-through). The spec must commit. Resolution: ask user at spec-interview time.
2. **Word-count cap derivation.** Adversarial review showed the compression-test data implies caps of ~70–160 words for honest Headlines on complex topics, not 30–40. The spec must derive caps from corpus measurement, not authoring intuition. Resolution: spec phase will measure the existing corpus and propose caps; user approves.
3. **Architecture/Pieces drift scope.** User's complaint names "pieces and architecture section." F+G as originally framed leaves Architecture/Pieces untouched. The spec must decide whether E (gate-brief generator) covers this by displacing the gate-display contract, or whether a separate mechanism is needed for Pieces drift. Resolution: ask user at spec-interview time.
4. **Vocabulary mechanism vs density mechanism.** Forward-reference patterns (`DR-N` before definition, contract-named compounds) are a vocabulary problem; word counts don't reach them. A banned-token blocklist or definition-required check is a separate mechanism. Resolution: spec must specify both, or surface that vocabulary is deferred.
5. **Solution Horizon tradeoff: narrow lever vs cross-skill durable framework.** Per CLAUDE.md, the obligation is to surface this tradeoff explicitly to the user, not silently pick narrow. Resolution: ask user at spec-interview time; surface the two options with the cost/durability tradeoff.
6. **Gate-brief generator (E) as primary fix vs Phase 2 contingency.** E matches Pinker's prior art and Anthropic's structural-separation guidance. The narrow alternative is F+G with a deferred E if F+G underperforms — but that defer-the-durable framing is exactly what Solution Horizon warns against. Resolution: ask user at spec-interview time.
7. **Lint scope: extend `cortex-check-prescriptive-prose` or new binary.** Two precedents is maintenance cost. The spec should justify the choice. Resolution: spec phase will weigh; user approves.
8. **Kept-pauses inventory update.** A new lint sub-pause requires naming a user-facing affordance per CLAUDE.md. Resolution: spec phase will name; lockstep update to inventory + parity test.
