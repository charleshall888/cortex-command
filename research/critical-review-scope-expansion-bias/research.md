# Research: critical-review scope-expansion bias

## Research Questions

1. **Is the scope-expansion pattern real and recurring, or a one-off operator error?** → **Partially answered.** The Kotlin session is the first *documented* instance of /critical-review output pushing an operator toward a wrong-layer fix. No retros, lifecycle artifacts, or research docs surface a second concrete failure. However, the underlying structural defects in the skill's prompt text are not unique to that session — they're generic properties of the synthesis pipeline. The right framing: the Kotlin case was the first *observed* failure; the mechanism that produced it is load-bearing every time the skill runs. Absence of documented prior cases is evidence the misread is rare, not that the defect isn't there. **Epistemic caveat**: the recommendations in this research rest on a single observed failure. Every sufficiency claim in §Feasibility is a Kotlin-case counterfactual, not a general claim. Confounds (operator domain expertise, artifact quality, session state, selection bias toward noticed flips) are not isolated and cannot be without a second case. Base-rate instrumentation — logging /critical-review outcomes and operator disposition decisions — is a legitimate candidate fix point in its own right and may warrant shipping ahead of the structural epics (see Open Questions). No retrospective exists for the Kotlin session; the RCA is the same operator's post-hoc reconstruction.

2. **Which of the four hypothesized root causes are supported by the current SKILL.md text?** → **All four are real and grounded in specific prompt lines.** Plus two additional structural defects surfaced by the codebase audit (H5 Dismiss-rationale leakage, H6 convergence-signal never aggregated). See §Decision Records for per-hypothesis grounding.

3. **Do /diagnose, /refine, /research, or other parallel-dispatch skills share the failure mode?** → **No — /research avoids it structurally, and the other skills don't implement the pattern.** /research uses role-orthogonal agents (each with a distinct non-overlapping contract), instructs its Tradeoffs agent to be balanced, and hands the Adversarial agent a *summary* of prior findings rather than raw objections — all three are structural protections against the critical-review failure mode. /diagnose uses competing-hypotheses convergence logic that is stronger than critical-review's through-line flagging. /refine does not reimplement the pattern; it inherits critical-review's defects at callsites. `clarify-critic.md` has H1–H4 but solves H5 (Dismiss leakage) via a structured output contract that critical-review has not adopted. The pattern that needs fixing is isolated to critical-review's core prompts.

4. **What techniques from adversarial-review / peer-review / red-team literature distinguish fix-invalidating from scope-expanding objections?** → **Five established techniques, converging on the same idea.** Conventional Comments' mandatory `blocking:` / `non-blocking:` decorators; Google's "in this CL" test; academic peer review's Major/Minor separation; CVSS/OWASP's orthogonal severity × scope axes; AI Safety via Debate's prosecutor/judge separation with a single binary question ("does any objection refute *this specific proposal*?"). The consensus prior-art move is forcing reviewers to commit to blocking status *per finding* before writing prose, and introducing a downstream *judge* (not synthesizer) who rules specifically on refutation.

5. **Where is the leverage — reviewer prompts, synthesis, Apply/Ask gate, operator framing, or a pattern anchor?** → **Synthesis (FP2) is load-bearing; reviewer classification (FP1) is its prerequisite.** FP2 restructures the synthesizer to separate A-class (fix-invalidating), B-class (adjacent gap), and C-class (framing) findings and refuses to let B-only evidence be promoted to an A-class verdict. FP1 is the data-shape change upstream that makes FP2 tractable. FP3 (tighter Apply bar on C-class) only works once FP1 tags exist. FP4 (operator-facing preamble) is low-efficacy — an experienced operator still flipped in the Kotlin case, so a hint header won't save the next one. FP5 (architectural-pattern anchor) is high-complexity and carries false-anchor risk. FP6 (required input framing) is the cleanest *input-side* standalone ticket and attacks a different failure mode than FP1+FP2 (prevent generation vs. contain aggregation).

6. **Does objection-class bucketing risk diluting the skill's value (license to dismiss)?** → **Real but asymmetric; guard must be a ticket-level acceptance criterion, not a deferred design question.** The cited literature (Conventional Comments, testdouble) reports that labeled severity reduces thrash in *human-to-human code review* — a context where reviewer/author social pressure creates the dilution defense. That mechanism does not transport to LLM→single-operator review, where the operator can silently scan past B-class findings without any social friction. The guard is therefore load-bearing and must be enforced at the ticket contract, not relegated to a design question. **Required guard (committed, not deferred):** any FP1+FP2 ticket must specify an action surface for B-class findings — either auto-logging each B-class finding as a follow-up backlog ticket, or an equivalent mechanism that produces observable residue when a B-class finding is not actioned. FP2's "refuse B-only → A-class promotion" is a *non-promotion* rule only; it does not prevent silent dismissal. The action surface is a distinct mechanism and must be scoped into the same epic.

## Codebase Analysis

### Critical-review skill — grounded defect audit

The skill at `/Users/charlie.hall/.claude/skills/critical-review/SKILL.md` has six structural defects relative to the observed failure mode:

- **H1 "Incomplete" conflated with "incorrect"** — present. Step 2c reviewer prompt (SKILL.md:92-94) asks for `### What's wrong` with no class distinction. Step 2d synthesis (SKILL.md:162) asks to `find the through-lines — claims or concerns that appear across multiple angles` — "concerns" is permissive and includes adjacent gaps. Nothing differentiates "this objection invalidates the fix" from "this objection identifies an adjacent pre-existing gap."
- **H2 No architectural-pattern anchor** — present. Step 2a (SKILL.md:16-22) loads `requirements/project.md` for functional domain context, but no step directs reviewers to examine the codebase for pattern precedent. The skill is read-only on the artifact; it cannot weigh "this fix matches an existing pattern at file:line" because it never looks.
- **H3 Synthesis told not to be balanced** — present. Step 2d (SKILL.md:178-179) instructs `Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.` Combined with the closing `These are the strongest objections. Proceed as you see fit.` (SKILL.md:166), the output reads as verdict ("strongest objections" = these are facts) sitting awkwardly next to prosecution framing ("proceed as you see fit" = you decide). The ambiguity resolves toward verdict when the synthesis narrative is coherent.
- **H4 Apply/Ask skew on framing claims** — present. Step 4's Apply bar (SKILL.md:226) says `Apply when and only when the fix is unambiguous and confidence is high.` "Unambiguous" describes the *direction* of the fix, not the correctness of the objection's *frame*. A framing objection ("the real defect is upstream") can be unambiguous in direction yet reframe the problem. The Dismiss anchor-check (SKILL.md:205) exists; no equivalent anchor-check guards Apply classification of frame-shifting objections.
- **H5 Dismiss-rationale leakage** — **already mitigated**. Backlog item 067 (status: complete) removed the Dismiss-reporting requirement entirely. No new ticket needed here; noted only to avoid duplicate scoping.
- **H6 Convergence signal unused** — present. Step 2c requires each reviewer to emit a `### Convergence signal` line (SKILL.md:100-102), but nothing in Step 2d instructs the synthesizer to aggregate these signals or use them for conflict/overlap detection. The convergence data is generated and silently discarded.

### Cross-skill audit

- **/research** (`skills/research/SKILL.md`) — different architecture, avoids the failure mode. Five orthogonal agents (Codebase, Web, Requirements & Constraints, Tradeoffs, Adversarial) with non-overlapping contracts. Requirements agent: "read and report — do not synthesize tradeoffs." Adversarial agent: dispatched with a *summary* of prior findings, not raw objections. No "do not be balanced" framing on the Tradeoffs agent.
- **/diagnose** — does not implement parallel-reviewer synthesis. Uses competing-hypotheses convergence (independent hypothesis agents must converge on the same root cause with non-overlapping evidence to declare convergence; otherwise all theories proceed).
- **/refine** — no parallel-reviewer dispatch. Invokes /critical-review at callsites; inherits its defects there.
- **/lifecycle `clarify-critic.md`** — has H1–H4 (same reviewer/synthesis design as critical-review) but solves H5 via a structured output contract (dismissals land in events.log only, user-facing response is reserved for Ask merge).
- **/discovery** — invokes /research (which avoids the pattern), not /critical-review directly.

### Backlog coverage

- `backlog/067-restructure-critical-review-step4-suppress-dismiss-output.md` — **complete**. Removed the Dismiss output requirement. Addresses H5. Does not touch Step 2c/2d reviewer/synthesis prompts.
- `research/audit-interactive-phase-output-for-decision-signal/research.md` — prior research; framed the H5 problem. Does not address H1–H4.
- No other backlog items cover the reviewer-prompt structure, synthesis structure, Apply-bar tightening for framing claims, operator-facing framing, or architectural-pattern anchor.

## Domain & Prior Art

Five established review methodologies classify objections along orthogonal severity × scope × actionability axes rather than producing a single verdict score. The consensus move is forcing reviewers to commit to blocking status per finding.

- **Conventional Comments** ([conventionalcomments.org](https://conventionalcomments.org/)) — mandatory `label [decorator]:` grammar with nine labels and `(blocking)`/`(non-blocking)`/`(if-minor)` decorators. Three of nine labels (nitpick, thought, note) are inherently non-blocking.
- **Google's eng-practices — code review comments** ([google.github.io/eng-practices](https://google.github.io/eng-practices/review/reviewer/comments.html)) — "In this CL" test: a comment is either blocking for the current change, or it's prefixed `Nit:`/`FYI:`/`Consider:` and logged as a follow-up.
- **Academic peer review Major/Minor split** — Major revisions trigger re-review; Minor revisions are editor-only. Reviewers must segregate comments *before* submission — the two-section requirement is a forcing function.
- **CVSS v4.0 / OWASP Risk Rating** — severity and scope are orthogonal axes, not a single verdict. CVSS's explicit *Scope* metric distinguishes in-component from cross-component impact.
- **AI Safety via Debate** (Irving, Christiano, Amodei 2018, [arXiv:1805.00899](https://arxiv.org/abs/1805.00899)) — prosecutor/judge separation. Judge's single question: "Does any objection refute *the specific proposal under review*?" — narrower than "summarize findings."
- **Constitutional AI** ([arXiv:2212.08073](https://arxiv.org/abs/2212.08073)) — critique-then-revise hierarchy outperforms direct revision. The analogue: a forced classification step *before* synthesis proposes replacements.

**Bucketing-as-license-to-dismiss in the literature**: The Conventional Comments and testdouble [non-blocking review](https://testdouble.com/insights/should-code-review-be-mandatory-non-blocking-review) writeups report that labels *reduce* thrash, not dilute review. The failure mode documented in the literature is the inverse — *unlabeled* comments create ambiguous dismissal ("repeated dismissals become org-level won't-fix"). No large-scale study shows labeled severity dilutes review quality.

**Chesterton's-fence guard on layer-switching** — engineering literature ([Broad on Chesterton's Fence](https://kulor.medium.com/chestertons-fence-a-mental-model-for-software-engineering-5fca09add1c4)) warns against review comments demanding rewriting of code whose purpose is unestablished. Applied to /critical-review: a synthesis narrative recommending a different layer should require an explicit refutation of the original layer's adequacy (a demonstrated failure of the minimal fix), not merely the existence of adjacent issues at another layer.

## Feasibility Assessment

| Fix Point | Effort | Risks | Prerequisites |
|---|---|---|---|
| FP1: Reviewer-prompt classification (A/B/C tags) | S | **Classifier accuracy is untested.** LLM reviewers have not been piloted on A/B/C classification; FP2's "refuse B-only promotion" rule is load-bearing on classification precision that this research has not established. Straddle cases (A+B — e.g., "this fix matches the existing pattern but the pattern itself is wrong") have no protocol. Classification pressure can push reviewers toward A-class because "that's what counts." Modest per-reviewer prompt bloat (~150 words × N). | None. Ships alone as an observability change; leverage comes when paired with FP2. |
| FP2: Synthesizer-prompt restructure (class-separated output, refuse B-only → A-class promotion) | M | **Highest-risk.** May produce a more bureaucratic, less punchy output — the skill's value prop is "strongest coherent challenge." May under-weight genuine A-class framing challenges if reviewers misclassified. | FP1 (otherwise synthesizer must classify itself, which is lossy). Can ship without FP1 with a rubric but quality drops. |
| FP3: Apply-bar tightening for C-class framing | S | Minimal. Ask isn't Dismiss, so downside is capped at "more questions asked." Operators may over-tag C-class to force questions. | FP1 for the C-class tag. |
| FP4: Operator-facing preamble ("this is prosecution, not verdict") | XS | Low-efficacy — preambles get skimmed. Real risk: provides cover ("we told them") for not shipping the structural fix. | None. Trivially shippable. |
| FP5: Architectural-pattern anchor (orchestrator cites pattern precedent, injected as evidence) | L | **Highest-complexity.** Pattern-identification is open-ended. False pattern matches would poison reviewer prompts with a misleading anchor — worse than no anchor. Most useful in exactly the cases where it's least needed (the orchestrator already knew the fix was right). | None, but needs careful design to avoid false-anchor poisoning. |
| FP6: Required input framing (one-sentence "what the fix is and why" at invocation) | S | UX friction — skill now requires input it used to infer. Reviewers may challenge the framing (C-class), arguably fine, arguably a new surface. | None. Cleanest standalone ticket. |

**Sufficiency evaluation against the Kotlin case:**
- FP1 alone: **insufficient** — findings tagged B still cluster into a through-line.
- FP2 alone (with rubric): **likely sufficient** — synthesizer refuses to promote B-only to verdict, Kotlin flip doesn't happen.
- FP1+FP2: **sufficient and robust.**
- FP3 alone: **insufficient** — auto-apply wasn't the Kotlin failure; operator interpretation was.
- FP4 alone: **insufficient** — experienced operator still flipped in the Kotlin case.
- FP5 alone: **potentially sufficient** for Kotlin specifically, but fragile.
- FP6 alone: **likely sufficient** — reviewers are told the proposed fix explicitly, cannot silently re-diagnose.

## Decision Records

### DR-1: Frame the problem as three independent concerns, not one fix
- **Context**: The user explicitly requested "don't prescribe a single fix; the problem space may split into multiple independent concerns." The fix points partition cleanly into three groups attacking different failure points.
- **Options considered**: (a) Single combined fix shipping FP1+FP2+FP3+FP4+FP5+FP6. (b) Sequential single-leverage-point fix (FP2 only, see DR-4). (c) Three independent epics each addressing a distinct failure surface.
- **Recommendation**: **(c) three independent epics.** Objection-class handling (FP1+FP2), input-side anchoring (FP5/FP6), and operator-interface guardrails (FP3+FP4) address different failure points (aggregation vs. generation vs. last-mile routing) and should be scopable, shippable, and evaluable independently. This matches the user's framing.
- **Required cross-epic acceptance criteria**: The objection-class handling epic (FP1+FP2) must include a B-class action-surface mechanism as an explicit acceptance criterion — not a deferred design question. Without the action surface, the epic reproduces the exact dilution failure mode that motivated bucketing; see Q6 and the dismissal-guard objection in /critical-review Round 1.
- **Trade-offs**: Three epics means three rounds of review, commits, and integration. Cost: coordination overhead. Benefit: each epic ships with a clear acceptance criterion tied to a distinct failure mode, and low-confidence fix points (FP5) can be deferred without blocking high-confidence ones (FP2).

### DR-2: H1–H4 are real defects grounded in prompt text
- **Context**: The user's post-hoc RCA identified four root causes. Research needs to validate which are grounded in current SKILL.md text vs. attributed by the operator.
- **Options considered**: Treat all four as hypotheses; accept only those supported by specific lines.
- **Recommendation**: **All four are real.** Specific line citations in §Codebase Analysis. H1 (SKILL.md:92-94, 162), H2 (SKILL.md:16-22), H3 (SKILL.md:178-179, 166), H4 (SKILL.md:205, 226). No hypothesis can be dropped based on prompt-text inspection.
- **Trade-offs**: None — this is an evidence finding.

### DR-3: H5 (Dismiss leakage) is out of scope — already addressed
- **Context**: The codebase audit surfaced H5 as a sixth structural defect. Backlog 067 (complete) already removed the Dismiss output requirement.
- **Options considered**: (a) Include H5 in scope to validate the prior fix. (b) Exclude H5 — 067 is complete and no evidence of regression.
- **Recommendation**: **(b) exclude.** Any H5 re-audit belongs in a separate verify-067 ticket if drift is observed, not this discovery.
- **Trade-offs**: Risk 067's fix has regressed silently. Low probability; verifiable any time.

### DR-4: FP2 (synthesizer restructure) is load-bearing; FP1 is its prerequisite
- **Context**: Five of six fix points could ship alone. The Kotlin failure content was four B-class adjacent-gap findings (analytics flushing, post-submit flow, create-order, third-party checkout) that the synthesizer aggregated into a C-class verdict ("the real defect is upstream, both fixes insufficient"). That verdict framing emerged in *synthesis*, not in the reviewer objections themselves. FP2 directly addresses the B→A promotion at the synthesis layer.
- **Options considered**: (a) Ship FP2 alone with synthesizer-side classification (FP1 not shipped). (b) Ship FP1+FP2 together. (c) Ship FP6 alone as an input-layer alternative.
- **Recommendation**: **(b) FP1+FP2 together, scoped as one epic with two tickets, plus a B-class action surface as a required acceptance criterion (see DR-1, Q6).** FP1 is the data-shape prerequisite; FP2 is the consumer. Shipping FP2 alone forces the synthesizer to re-classify the reviewers' raw output, which is lossy and expensive. Shipping FP1 alone produces typed findings that nothing consumes.
- **Trade-offs**: FP6 attacks the C-class emergence problem at the input layer — complementary, not substitute. Scoped as the lead of a second epic (see DR-6). FP5 does not address the Kotlin failure content and is deferred (see DR-6).

### DR-5: FP4 (operator preamble) ships only with an explicit "this is a hint, not a fix" framing
- **Context**: FP4 is the lowest-efficacy fix point. A preamble header could be mistaken for the structural fix.
- **Options considered**: (a) Ship FP4 standalone. (b) Don't ship FP4. (c) Ship FP4 *only* as a low-cost marginal improvement with an acceptance criterion that it not be claimed as the fix.
- **Recommendation**: **(c)** — if shipped at all, ticket must state it's a stopgap/hint, not the structural solution. Decision on ship/don't-ship deferred to planning.
- **Trade-offs**: Adds process overhead to a cheap change. Worth it to prevent "FP4 is done, problem solved" misreads.

### DR-6: FP5 (architectural-pattern anchor) is deferred; FP6 (input framing) is the input-side lead
- **Context**: The input-side epic originally paired FP6 (required input framing at invocation) and FP5 (orchestrator-supplied pattern anchor). On re-analysis of the Kotlin failure, FP5 does not apply: reviewers raised B-class adjacent-gap findings, not C-class "wrong layer" objections. The verdict framing emerged in synthesis, not from reviewers missing a pattern. FP5's remaining justification (preventing C-class reviewer objections when reviewers don't see the codebase) does not map to any documented failure and carries real false-anchor risk — a wrong pattern citation poisons reviewer prompts worse than no anchor.
- **Options considered**: (a) Ship FP5 and FP6 as co-equal. (b) Lead with FP6 and defer FP5. (c) Drop FP5 entirely.
- **Recommendation**: **(b) — FP6 is the input-side lead; FP5 is deferred with a strengthened rationale.** FP6 gives the synthesizer an explicit proposal frame it must argue against rather than re-frame around (addressing C-class emergence in synthesis). It carries no false-anchor risk because the operator supplies the anchor and owns its accuracy. FP5 remains a backlog candidate for a future C-class-reviewer-objection failure mode if one is documented; without that, its complexity-to-value ratio does not justify shipping.
- **Trade-offs**: Dropping FP5 entirely loses the placeholder for a possible future case. Keeping it deferred with an explicit "re-evaluate if documented" condition retains that optionality at low cost.

### DR-7: Meta-concern — /critical-review will be run on this research.md
- **Context**: /discovery's research phase invokes /critical-review on the research artifact itself before transitioning to decompose. This research surfaces defects in /critical-review. Running the possibly-flawed skill on research about that flaw is meta-recursive.
- **Options considered**: (a) Skip /critical-review on this research. (b) Run /critical-review and treat its output as ordinary review input subject to the normal Apply/Dismiss/Ask gate. (c) Use /research's adversarial agent instead.
- **Recommendation**: **(b)** — run /critical-review as the protocol requires and evaluate its output on its merits. The recursion is a limitation of this research, not a confirmatory frame. Do not treat verdict-like synthesis tone as confirmation of the research's thesis; specific objections with artifact citations must be evaluated directly. If the /critical-review output exhibits the scope-expansion failure mode this research describes, that is one data point of circumstantial evidence — not proof and not disproof.
- **Trade-offs**: The meta-recursion is irreducible. Treat it as an epistemic limit, not a rhetorical asset.

## Open Questions

- **Which action surface should B-class findings use?** The guard is committed (see Q6, DR-1) — B-class findings must have an action surface as an acceptance criterion of the FP1+FP2 epic. The open question is the mechanism: auto-generate a follow-up backlog ticket per B-class finding, emit a structured residue file, escalate to an Ask summary, or something else. This is a design choice during FP2 planning, not a decision about whether to include the guard.
- **Why three classes rather than two or more?** FP1's A/B/C is asserted, not derived from the cited prior art (Conventional Comments: 9 labels + decorators; peer review: 2; CVSS: 2-axis; Debate: 1 binary). Prior art's actual move is binary blocking-status commitment; this research implements a three-content-type taxonomy. Before FP1 ships, the class count must be derived — either from a straddle-case analysis, a pilot on historical /critical-review outputs, or an explicit argument for the ternary collapse.
- **What is the straddle-case protocol?** A finding that is simultaneously A and B (e.g., "this fix matches the existing pattern but the pattern itself is wrong") is not handled by the current FP1 spec. FP2's "refuse B-only → A-class promotion" rule breaks on unlabeled straddle findings. Either the classifier must emit multi-class tags, or the rubric must define a precedence rule, or the taxonomy must be redesigned as orthogonal axes.
- **Should a base-rate instrumentation ticket ship ahead of the structural epics?** The research rests on n=1 documented failure. A lightweight instrumentation epic — logging /critical-review invocations, angle counts, operator Apply/Dismiss/Ask distributions, and retrospective outcome — would let future structural changes be evaluated against measured base rates rather than post-hoc RCAs. May warrant scoping as a zeroth epic.
- **Where does H6 (convergence signal unused) live?** The codebase audit flagged Step 2c's `### Convergence signal` as emitted-but-unconsumed. None of FP1–FP6 addresses it. Decide: add a seventh fix point (synthesizer must aggregate convergence signals and surface reviewer-angle overlap explicitly), defer explicitly, or remove the convergence signal field from the reviewer prompt.
- **How does FP5 (pattern anchor) identify patterns without false matches?** The trade-off agent flagged false-anchor poisoning as the worst risk. A pattern-identification sub-task that grep's for sibling usages would be lightweight but brittle; a full codebase scan rivals the reviewers in cost. If FP5 survives to planning, the sub-problem is pattern-identification reliability.
- **Does the Kotlin case warrant a documented retrospective?** No retro exists for that session. The user could write one; this research would reference it. Not blocking — the failure is well-described in the discovery topic — but the absence means the RCA is post-hoc operator reconstruction, not primary-source.
- **Should /lifecycle's clarify-critic.md adopt the same A/B/C bucketing?** It shares H1–H4 with /critical-review. If the FP1+FP2 pattern proves out, clarify-critic is the natural next port. Out of scope for this discovery; worth a follow-up ticket if the initial fix lands well.
