# Research: reduce-critical-review-influence

Reduce how strongly /cortex-core:critical-review's findings sway the main agent when the reviewer is being performatively adversarial rather than substantively correct. Scope: /cortex-core:critical-review only (not clarify-critic, not /devils-advocate). The user delegated lever selection to the research output — investigate all internal surfaces and recommend a mix of source filtering, tighter Apply bar, and less-authoritative presentation framing.

## Codebase Analysis

### Lever surfaces inside skills/critical-review/

| # | Surface | File / lines | Current text fragment |
|---|---------|--------------|----------------------|
| 1 | Reviewer prompt voice | `references/reviewer-prompt.md:11–13, :60` | "You are conducting an adversarial review…" / "Do not cover other angles. Do not be balanced." |
| 2 | Synthesizer prompt voice | `references/synthesizer-prompt.md:10, :46, :50` | "synthesizing findings from multiple independent adversarial reviewers" / forbidden-balanced-sections / "Do not be balanced. Do not reassure. Find the through-lines and make the strongest case." |
| 3 | A→B downgrade rubric | `references/a-to-b-downgrade-rubric.md` (4 triggers, 8 worked examples) | absent / restates / adjacent (+ Straddle exemption) / vague |
| 4 | Step 4 Apply Feedback defaults | `SKILL.md:99–115` | Apply/Dismiss/Ask; **anchor-checks fire only on Dismiss** ("dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence"); empirical-measurement clause requires actual measurement for Apply/Dismiss |
| 5 | Step 3 "Present" gag rule | `SKILL.md:97` | "Output the review result directly. Do not soften or editorialize." |
| 6 | Residue write | `references/residue-write.md` (R4 schema) | persists **B-class only** to `cortex/lifecycle/{feature}/critical-review-residue.json` |
| 7 | Verification gates | `references/verification-gates.md` | sentinel-first Phase 1 SHA verification + Phase 2 envelope extraction; orthogonal to voice |
| 8 | Angle menu | `references/angle-menu.md` | artifact-specificity acceptance criterion gates angle distinctness |
| 9 | Fallback reviewer prompt | `references/fallback-reviewer-prompt.md:10, :40` | mirrors reviewer-prompt voice |

### Integration shape

- **Auto-trigger sites**: `skills/lifecycle/references/specify.md:145–151` (§3b) and `skills/lifecycle/references/plan.md:267–273` (§3b). Both gate on `tier = complex` only — **NOT additionally on `criticality`**, despite the SKILL.md frontmatter description claiming "Complex + medium/high/critical." This is a documented-vs-actual gate mismatch.
- **Manual trigger**: `skills/discovery/references/research.md:184` via explicit `<path>` argument.
- **Apply/Dismiss/Ask classification**: performed by the **orchestrator running the lifecycle skill**, not by critical-review itself. No JSON or event hand-back into the lifecycle; only B-class findings persist (to residue JSON).
- **Residue consumer**: `cortex_command/overnight/report.py:1004–1056` reads `cortex/lifecycle/*/critical-review-residue.json` for the morning report.
- **Events registry**: `bin/.events-registry.md:111–112` registers `sentinel_absence` and `synthesizer_drift`. New tuning events require a registry row naming the consumer.

### Existing patterns and conventions

- **Atomic dispatch ceremony**: `cortex-critical-review prepare-dispatch / record-exclusion / verify-synth-output` in `cortex_command/critical_review.py` collapse path-validate + SHA-pin + sentinel-parse into single subprocess calls.
- **Atomic events.log append** (`append_event`, tempfile + `os.replace`).
- **Residue atomic rename** (inline `python3 -c` tempfile + `os.replace`).
- **`<!--findings-json-->` LAST-occurrence anchor** for envelope extraction; reused by `skills/lifecycle/references/plan.md:90–94` for the plan-variant synthesizer.
- **Reclassification-note format**: `Synthesizer re-classified finding N from A→B: <rationale>`.
- **Straddle exemption pattern**: a downgrade trigger conditionally suppressed by a populated envelope field (`straddle_rationale`).
- **Class-tag gating**: zero A-class → no `## Objections` section. Currently the only "swayable-only-if-A-survives" lever; tuning the rubric to downgrade more A→B suppresses Objections, which the orchestrator reads as "verdict."

### Recent tuning history (commits)

Tuning class (precedent for this work):
- `2fed8ab6` — anchor-check empirical-measurement rule at Step 4 line 106.
- `15f6fabb` — added A→B downgrade rubric + 8 worked examples.
- `2325ffa5`, `efbe4e99` — `fix_invalidation_argument` field on findings.
- `4daba2db` — closed the **orchestrator-pushback-on-findings** lifecycle (Alternative F).
- `d89d555b` — differentiated critical-review vs /devils-advocate descriptions.

Seven archived lifecycles tuned critical-review prior to this request (under `cortex/lifecycle/archive/`):
- `classify-critical-review-findings-by-class-and-add-b-class-action-surface`
- `consolidate-devils-advocate-critical-review`
- `critical-review-orchestrator-pushback-on-findings` (**this is the current rubric path; implemented, not abandoned**)
- `critical-review-self-resolve-before-asking`
- `critical-review-skill-audit`
- `restructure-critical-review-step-4-to-suppress-dismiss-output`
- `tighten-critical-review-dismiss-criterion`

## Web Research

### Prior art

- **Anthropic — Harness design for long-running apps**: "tuning a standalone evaluator to be skeptical is far more tractable than making a generator self-critical." Claude evaluators historically "identify legitimate issues, then talk itself into deciding they weren't a big deal" — **evaluator-side capitulation is real**. Convert subjective judgments to "concrete, gradable terms" with weighted, named criteria; calibrate with few-shot examples and detailed score breakdowns.
- **SycEval (arXiv 2502.08177)**: **58.19% overall capitulation rate** across frontier models. **Citation-based rebuttals produce the highest *regressive* sycophancy** — authoritative-sounding citations more reliably corrupt a correct stance than simple disagreement does. **Preemptive rebuttals are worse than in-context** (61.75% vs 56.52%). **78.5% persistence** after capitulation.
- **Confidence/Diversity paper (arXiv 2601.19921)**: LLMs are natively overconfident; **raw confidence hurts**, calibrated confidence helps. **Diversity at proposal time beats weighting at aggregation**.
- **Agent-Review-Panel (wan-huiyan)**: production pattern uses **blind final scoring, calibrated skepticism levels (20–60% per persona), sycophancy detection (intervene when >50% position changes lack new evidence), correlated-bias warning (unanimous agreement flagged as the most dangerous failure mode), severity verification gates** demanding `[EXISTING_DEFECT]` evidence for P0, **post-judge re-verification that demotes hallucinated findings**.
- **Adversarial-Review skill (poteto/noodle)**: orchestrator policy: *"Using the stated intent and brain principles as your frame, state which findings you would accept and which you would reject — and why. Reviewers are adversarial by design; not every finding warrants action."* — explicit anti-capitulation framing.
- **Jesse Vincent's "competitive cookie" pattern**: competitive framing ("whoever finds more issues wins") inflates finding count but **biases toward performative findings**.
- **Production multi-critic skills (Ultra Review, 9-agent setup)**: admit ~25% of suggestions are noise even with prompt tuning; rely on human judgment as final filter.

### Patterns and anti-patterns

Patterns:
1. Generator/evaluator role separation (universally endorsed).
2. Calibrated severity + hard thresholds, not free-form confidence.
3. Multi-flag escalation, isolated-flag triage.
4. Evidence-tagging on findings (`[EXISTING_DEFECT]`, `[WEB-VERIFIED]`).
5. Anchor orchestrator disposition on stated intent, not on critic phrasing.
6. Diversity at proposal time, not at aggregation.
7. Verification gates and post-judge re-verification (closest to "challenge the challenger" that works in production — but only against factually-checkable claims).

Anti-patterns:
1. Letting the critic self-report severity/confidence raw (LLMs overconfident; visible raw confidence produces cascades).
2. Preemptive / front-loaded critic prompts (more capitulation than in-context).
3. Treating authoritative citation as automatic credibility.
4. Competitive framings ("whoever finds more issues wins").
5. Unanimous critic agreement treated as confirmation (correlated bias from shared training data).
6. Pure prose-only "don't capitulate" instructions in the orchestrator prompt (unreliable per SycEval persistence).
7. Auto-applying critic findings.
8. **"Challenge the challenger" without grounding — re-introduces the same sycophancy one layer up. Meta-review must be claim verification, not opinion arbitration.**

## Requirements & Constraints

- **MUST-escalation policy (CLAUDE.md:72–80)**: defaults to soft positive-routing post Opus 4.7; pre-existing MUSTs grandfathered until audited (per #85). **Adding** a MUST requires evidence; **softening** is direction-aligned. **The user's complaint is an OQ3-eligible correctness/routing failure (not the tone-perception carve-out)** — the orchestrator applies wrong fixes because reviewer prose was confidently asserting incorrect things.
- **"Prescribe What and Why, not How" (CLAUDE.md:64–70)**: rules out procedural narration like "if reviewer uses these words, downweight by 40%." Any new lever expresses *what* class is being downweighted and *why*, not *how* the model should detect performativity.
- **SKILL.md size cap (project.md:30)**: 500 lines (current critical-review SKILL.md is 115). Default fix: extract to `references/`. **New tuning logic lands in `references/`, not SKILL.md.**
- **Skill-helper modules (project.md:31)**: critical-review already has `cortex_command/critical_review.py` for verification-gate logic (path-validate + SHA-pin + sentinel-parse). This is the home for **structural** logic; **prompt-voice tuning lives in `references/`**.
- **Tone/voice policy (docs/policies.md)**: governs Claude's user-facing output, not internal skill instruction language. **Internal prompt voice IS in scope** — but per the adversarial review caveat below, the synthesizer's prose IS surfaced verbatim to the user under Step 2d.5 Exit 0, so this is a boundary case.
- **Solution horizon (project.md:21)**: tuning existing levers is the simpler-fix path, not a stop-gap. Larger redesigns (confidence scoring, meta-reviewer) need named follow-ups.
- **Defense-in-depth (project.md:39)**: keep verification gates orthogonal from voice tuning.
- **Structural separation > prose-only enforcement (CLAUDE.md:58)**: "A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction." **Implication: prefer structural gates (rubric trigger, envelope field, control-flow gate) over prose like "be skeptical of confident reviewers."**

### Load-bearing protective directives (flagged in spec 067 R8)

These directives are explicitly preserved against post-Opus-4.7 warmth-training regression per backlog #082 / #085:

- `SKILL.md:97`: "Output the review result directly. Do not soften or editorialize." (Step 3 Present)
- `synthesizer-prompt.md:50`: "Do not be balanced. Do not reassure. Find the through-lines and make the strongest case."
- `synthesizer-prompt.md:46`: forbidden-balanced-sections rule.
- `reviewer-prompt.md:60`: "Do not cover other angles. Do not be balanced."
- `fallback-reviewer-prompt.md:42`: "Do not be balanced. Do not reassure. Find the problems."

**These were deliberately preserved as anti-sycophancy anchors. Softening them requires an evidence artifact per the MUST-escalation policy — not direction-aligned without measured failure.**

## Tradeoffs & Alternatives

Ten alternatives evaluated. Below: the four-lever recommended mix from the alternatives analysis, followed by the adversarial pushback that materially reshapes the recommendation.

### Original alternatives mix (alternatives agent's recommendation)

- **A — Extend A→B downgrade rubric (Triggers 5 & 6)** in `references/a-to-b-downgrade-rubric.md`. Trigger 5: "no quote from artifact." Trigger 6: "speculative blast-radius without measurement." Add 4 worked examples paralleling the existing 8.
- **B — Symmetric Apply-bar evidence requirement** at `SKILL.md:103–106`. Today only Dismiss requires artifact pointability; Apply does not. Require Apply to cite verbatim artifact quote OR fresh measurement.
- **G — Default-flip ambiguous routing** at `SKILL.md:106`. Today "Default ambiguous to Ask." Flip to "Default ambiguous to Dismiss when finding lacks artifact reference."
- **C/H merged — Less-authoritative voice** at `SKILL.md:97` (Step 3) and `synthesizer-prompt.md:50` (final paragraph). Reframe "Do not soften or editorialize" and "Do not be balanced. Do not reassure" as candidate-framing.

Rejected: D (attacks signal generation), E (gameable self-confidence; redundant with A), F (already implemented as the current state — see adversarial review), I (reduces frequency not sway), J (conflicts with load-bearing invariant).

### Adversarial review (substantial reshaping)

The adversarial review surfaced **ten failure modes** that change the recommendation:

1. **Test infrastructure is latently broken.** `tests/test_critical_review_classifier.py::_extract_synthesizer_template` (lines 210–227) anchors on `### Step 2d: Opus Synthesis` in SKILL.md expecting `---` delimiters. Commit `16fbcd7e` moved that body to `references/synthesizer-prompt.md`; SKILL.md Step 2d is now descriptive prose with **no `---` delimiters**. The 5 deterministic-trigger tests are latently broken under the current rubric. **Layering Trigger 5/6 fixtures on top compounds the rot.**
2. **Trigger 5 is fakeable.** Substring-presence-of-quote check at the synthesizer is model-judgment, not deterministic. A reviewer who pastes any irrelevant artifact line into `evidence_quote` passes the trigger while remaining substantively wrong. **The trigger gates on quote presence, not quote-relevance.** Training reviewers toward compliance theater.
3. **Trigger 6 double-counts existing gates.** SKILL.md:106 already requires actual measurement for empirical claims (latency/file-size/blast-radius). Trigger 6 at the synthesizer layer cannot run measurements (synthesizer is text-bound) and degenerates to prose-pattern matching on hedge words ("could," "might"), making it semantically equivalent to Trigger 4 (vague).
4. **Apply-bar symmetric evidence routes to Ask, not Dismiss.** Net effect: more Ask routing. The user's complaint is "orchestrator listens too much," not "too many Ask." Symmetric Apply-bar without parallel default-flip on Ask shifts where capitulation manifests rather than reducing it.
5. **Default-flip G silently dismisses cross-cutting concerns.** Findings that reference **project-wide patterns or constraints the artifact inherits but doesn't restate** get silently dismissed. Re-creates the failure mode that motivated archived `restructure-critical-review-step-4-to-suppress-dismiss-output` work.
6. **Cumulative dampening of A+B+G+C/H is over-correlated, not three-layer defense.** Trace a single performative A-class finding: Trigger 5 fires → downgrade A→B → B-class doesn't go through Apply/Dismiss (residue only) → Apply-bar (B) has no effect → G default-flip doesn't apply (no longer ambiguous). The compounding Agent 4 claims is partially imaginary on a per-finding basis. Where they *do* compound is on truly-A-class findings (which is exactly where we want the orchestrator to listen).
7. **Softening load-bearing voice anchors removes the warmth-training counterweight.** Backlog #082/#085 deliberately preserved these against post-Opus-4.7 warmth regression. Removing them doesn't make the synthesizer less performative — it removes the only training-counterweight against Claude *self-talking-itself-out-of-finding-issues* (the Anthropic harness-design failure mode). The proposed change targets the **symptom** (orchestrator listens too much) by removing a counterweight against a **different** failure mode (synthesizer self-softening), making both failure modes more likely.
8. **Auto-trigger gate mismatch is a latent bug AND higher-leverage fix.** SKILL.md:3 frontmatter claims "Complex + medium/high/critical" gating but actual gates at `specify.md:149` and `plan.md:271` are `tier = complex` only. **A quarter (or more) of auto-triggers are unintentional (complex + low-criticality)** — fixing this gate could resolve a meaningful chunk of the "listens too much" pain without rubric tuning. The alternatives agent missed this as higher-leverage.
9. **Alternative F was not "tried and pivoted away from" — it was *implemented* and *is* the current rubric.** The `fix_invalidation_argument` field, the 4-trigger A→B rubric, the 8 worked examples, and the deterministic synthesizer tests were all delivered by the archived `critical-review-orchestrator-pushback-on-findings` lifecycle. The user's "still overly listened to" complaint **comes after that ship**. The honest read: **adding Triggers 5/6 + Apply-bar + default-flip is doubling down on the rubric path the user has implicitly judged insufficient.**
10. **"Performatively adversarial vs substantively correct" is the same model judgment relocated.** Adding 2 more triggers asks the synthesizer to make 6 versions of the same judgment instead of 4. If the model judgment is the bottleneck (SycEval: 58% capitulation), more rubric triggers buy nothing.

### Recommended sequence (adversarial-revised)

The adversarial review's mitigations, in priority order:

1. **M1 — Fix the latent test breakage first.** Update `_extract_synthesizer_template()` to read from `references/synthesizer-prompt.md`. Confirm baseline 5 deterministic tests pass under the current rubric before adding fixtures. **Prerequisite for any rubric work.**
2. **M3 — Fix the auto-trigger gate mismatch.** Make `specify.md:149` and `plan.md:271` honor `criticality` per the SKILL.md description ("Complex + medium/high/critical"). Add a `lifecycle_critical_review_skipped` event when tier=complex but criticality=low. **Highest-leverage, lowest-risk** intervention — may dissolve a substantial portion of the "listens too much" complaint without rubric tuning. After this, measure for a week before deciding if rubric work is still needed.
3. **M6 — Baseline measurement.** Count Apply/Dismiss/Ask dispositions per lifecycle over recent runs. Determine whether the problem is Apply-rate bias (orchestrator-side weighting) or per-Apply cost (each Apply spawns disproportionate rework). The proposed rubric changes only address the former.
4. **M2 — Add an anti-test for over-dampening.** Author a "strong-argument-ratify" fixture: A-class finding with concrete `fix_invalidation_argument` that names a specific failure path and passes hypothetical Triggers 5/6. Assert the synthesizer **ratifies A** (no A→B reclassification note). Without this falsification path, any rubric expansion is a one-way ratchet toward more Dismiss/Downgrade.
5. **M4 — If rubric expansion is kept**, drop Trigger 6 entirely (renaming of Trigger 4) and **replace Trigger 5 with a deterministic quote-verification step in the verification-gates path, not the synthesizer rubric prose.** At Step 2c.5 Phase 2, when extracting envelope, also assert `evidence_quote in artifact_text_at_dispatch` via Python substring match. Findings with quotes that don't substring-match the artifact get auto-downgraded to C-class with `quote_unverified` rationale before the synthesizer sees them. **Structural (not prose), deterministic (not model-judgment), unfakeable (not gameable by the reviewer).** Keeps voice anchors intact.
6. **M5 — Do NOT soften the load-bearing voice anchors** without a measured-failure evidence artifact per the MUST-escalation policy. The user's complaint is *not* the kind of behavior-failure artifact #085 demands. Editing voice anchors to address an orchestrator-listening complaint treats the wrong surface.
7. **M7 — If, after M1–M6, the orchestrator-listening problem persists**, consider a single focused Step 4 change ("Default ambiguous to Dismiss when no parent-requirement-anchored evidence") paired with M2's anti-test. Do this as **one focused change at Step 4** rather than four levers across four surfaces.

## Considerations Addressed

The Clarify-critic surfaced considerations that should inform research scope. None were formal alignment-origin findings (no parent epic), so they appear here rather than as a `research-considerations` channel:

- **"Performatively adversarial vs substantively correct" — is the distinction operationalizable?** Addressed in adversarial finding #10 and patterns/anti-patterns: it is the same model judgment, and adding triggers relocates the judgment without solving it. Structural quote-verification (M4) is the only fully-deterministic version.
- **Critical-review's auto-trigger as a deliberate safeguard.** Addressed: the auto-trigger gate mismatch (adversarial finding #8) is itself part of the problem — the gate runs MORE often than the SKILL.md description implies. Fixing M3 reduces unintended triggers without weakening intentional ones.
- **7 archived prior tuning iterations — what worked, what residual gap motivates this.** Addressed in Codebase Analysis: the most relevant prior is `critical-review-orchestrator-pushback-on-findings`, which delivered the current rubric (Alternative F is the current state). The user's complaint is residual to that shipped work, suggesting the rubric path has reached its ceiling.

## Open Questions

These need user input during Spec:

1. **Should M3 (auto-trigger gate fix) be the first deliverable in this lifecycle, or split into a separate, fast lifecycle?** It is independently shippable and high-leverage. Splitting lets us measure its impact before committing to further rubric work. Bundling keeps the lifecycle scope coherent but delays measurement.
2. **Is M6 (Apply-rate baseline measurement) acceptable as a pre-implementation step, or should we ship a change first and measure?** Measuring first is the disciplined move per the adversarial review, but it costs a week of latency before any user-visible change.
3. **Are the load-bearing voice anchors (`SKILL.md:97`, `synthesizer-prompt.md:50`, etc.) truly out of scope for this lifecycle, or is there a path to revisit them with an evidence artifact?** The adversarial review says do not touch them; the user's "investigate all levers" phrasing leaves room. Defer-vs-touch is a user decision.
4. **Is M4 (structural quote-verification at Step 2c.5) in scope?** It is the only fully-deterministic version of Trigger 5, but it lives in `cortex_command/critical_review.py` (Python module) rather than in `references/`, expanding the change surface beyond pure prompt edits.
5. **Should we add a reviewer-side confidence/severity field (Alternative E) for future telemetry**, even though raw self-reported confidence is gameable? It is additive, doesn't change current behavior, and gives future tuning a continuous lever.
6. **Anti-test for over-dampening (M2) — required precondition or optional?** Without it, any rubric expansion ships as a one-way ratchet. With it, the lifecycle scope grows.
