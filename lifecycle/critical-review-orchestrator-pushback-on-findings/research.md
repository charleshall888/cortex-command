# Research: Tune `/cortex:critical-review` so the main agent re-examines synthesis findings before applying

**Topic anchor**: Add orchestrator pushback discipline at Step 4 (re-examine A-class findings against the artifact, reclassify with rationale, then proceed) AND strengthen one upstream lever (synthesizer framing OR class-tag rigor — choice deferred to Research). Goal: stop the main agent treating high-confidence synthesis output as a decisive verdict.

**User's evidence**: After a critical-review surfaced "6 A-class fix-invalidating findings" with confident framing, the main agent applied them without re-examining whether each truly rose to fix-invalidating. The agent's own recap: "I rolled over."

**Tier**: complex. **Criticality**: high.

## Codebase Analysis

### Files that will change

- `skills/critical-review/SKILL.md` — primary target
  - Step 4 (lines 274–304): Apply Feedback — site of orchestrator pushback discipline
  - Step 2c (lines 76–132): reviewer prompt — site of class-tag rigor option
  - Step 2d (lines 181–220): synthesizer prompt — site of synthesizer framing option
  - Step 2c.5 (lines 173–179): envelope extraction — affected if class-tag rigor adds a required field
  - Step 2e (lines 232–268): residue write — affected if reclassification needs a field

- `skills/refine/references/clarify-critic.md` — secondary target (sync invariant)
  - Disposition Framework (lines 67–89) explicitly says "reproduced from /cortex:critical-review Step 4 to avoid silent drift." Sync requirement may not survive structural inspection — see Adversarial §5.

- `tests/test_critical_review_classifier.py` and fixtures — test surface
  - `tests/fixtures/critical-review/pure_b_aggregation.md`, `straddle_case.md` exercise the existing A/B boundary
  - 3-of-3 stochastic pass requirement; tests check class counts and synthesis phrases — they do NOT cover Step 4 disposition logic

### Auto-trigger call sites (blast radius)

- `skills/lifecycle/references/specify.md` §3b (line 151) — fires after Complex specs
- `skills/lifecycle/references/plan.md` §3b (line 243) — fires after Complex plans
- `skills/discovery/references/research.md` §6b — manual trigger on research.md
- Auto-fires on every Complex+medium/high/critical lifecycle feature

### Existing scaffolding to coordinate with

- **Step 2c reviewer prompt**: A/B/C class definitions (line 87–93), Straddle Protocol (lines 95–97) with optional `straddle_rationale` field, JSON envelope schema (lines 117–130) including `evidence_quote`
- **Step 2c.5 envelope extraction**: last-occurrence delimiter anchor, `json.loads` with strict schema validation, malformed envelopes route prose to untagged `## Concerns` and **exclude from A-class tally**
- **Step 2d synthesizer**: instruction #3 (line 198) — "Before accepting any finding's class tag, re-read its `evidence_quote` field against the artifact content provided above" with explicit re-classify-with-note pattern; B→A refusal gate (line 199); anti-verdict opener (line 203) — "No fix-invalidating objections after evidence re-examination. The concerns below are adjacent gaps or framing notes — do not read as verdict."
- **Step 2e residue write**: atomic tempfile + `os.replace` to `lifecycle/{feature}/critical-review-residue.json`; payload schema in line 266; consumed by `cortex_command/overnight/report.py::render_critical_review_residue`
- **Step 4 anchor checks (×2)**: Dismiss anchor (line 282), self-resolve-before-Ask anchor (line 286). Apply bar (line 303): "Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask."

### Prior lifecycles touching this skill (all complete)

- **Ticket 132** (`classify-critical-review-findings...`): shipped A/B/C class system + JSON envelope + Step 2c.5 extraction + synthesizer evidence re-examination (2d #3) + B→A refusal gate + B-class residue + morning-report integration + V2 fixtures. **Most adjacent prior work; the upstream lever options layer directly on what 132 just shipped.**
- **Ticket 067** (`restructure-critical-review-step-4`): suppressed Dismiss output in Step 4 summary. Compact summary format at lines 292–301 (Apply direction-verbs, Dismiss-as-count-only, Ask consolidated) is **load-bearing** — pushback mechanism must not reintroduce Dismiss verbosity.
- **`critical-review-self-resolve-before-asking`**: added self-resolution paragraph + Dismiss anchor check; replicated in clarify-critic.md.
- **`tighten-critical-review-dismiss-criterion`**: added Dismiss anchor check.
- **`consolidate-devils-advocate-critical-review`**: restructured /devils-advocate to match critical-review precision patterns.

## Web Research

### Anthropic harness-design post (the user's reference)

Source: https://www.anthropic.com/engineering/harness-design-long-running-apps

**The article directly contradicts the orchestrator-side intervention pattern.** Anthropic explicitly states the tractable lever is upstream:

> "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work."

> "once that external feedback exists, the generator has something concrete to iterate against."

The "rolling over" failure mode in their post describes **evaluator leniency**, not generator capitulation:

> "the [initial] evaluator's logs [showed] it identify legitimate issues, then talk itself into deciding they weren't a big deal... It took several rounds of this development loop before the evaluator was grading in a way that I found reasonable."

Their fix: few-shot calibrated severity tags + hard structural gates (sprint pass/fail thresholds), not main-agent re-examination.

> "I calibrated the evaluator using few-shot examples with detailed score breakdowns. This ensured the evaluator's judgment aligned with my preferences, and reduced score drift across iterations."

> "Each criterion had a hard threshold, and if any one fell below it, the sprint failed."

### Authority bias and overconfidence in LLM judges

- **Authority bias** (arxiv 2410.02736): canonical academic name for the failure mode. Mitigation: "reference-guided verification — provide source document and explicitly verify each claim against that specific source." Direct support for evidence-grounded re-examination.
- **Overconfidence in LLM-as-Judge** (arxiv 2508.06225): consumers see rationale not just label; LLM-as-Fuser pattern grounds decision in ensemble critique. Supports "reclassify with rationale" half.
- **Sycophancy under rebuttal** (arxiv 2502.08177; "Necessary Friction" / Silicon Mirror, arxiv 2604.00478): forcing rationale generation in the consumer reduced sycophancy on Claude Sonnet 4 by 85.7% in one study. Argues for explicit friction prompt language at the consuming agent.
- **Co-Evolving Critics** (arxiv 2601.06794): "static critics become stale" — argues for synthesizer framing over fixed class taxonomies long-term.

### Production case study: Slack security-investigation harness

ZenML LLMOps DB: 5-class plausibility taxonomy (Trustworthy / Highly-plausible / Plausible / Speculative / Misguided) with field-validated distributions across 170k findings. Critic filters ~26% of findings before reaching the consumer. Citation-required findings: "include only events supported by credible citations." Critic also identifies up to 3 significant gaps to focus consumer attention. Direct support for upstream filtering with citation requirements and structured gap-naming.

### Strongest combined recommendation across the literature

Claim+citation framing (synthesizer side) PLUS reference-guided re-examination (orchestrator side). The two reinforce each other only when re-examination has falsifiable material — i.e., the finding cites a verifiable artifact location.

## Requirements & Constraints

### Project philosophy

- **Complexity bar** (`requirements/project.md` L19): "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." — combination intervention must justify each half independently.
- **ROI bar** (L21): "Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster." — bounds scope; new pushback must demonstrate observable wrong-decision reduction.
- **Maintainability through simplicity** (L31): Step 4 already carries Apply/Dismiss/Ask + 2 anchor checks + Apply bar + self-resolve; cognitive surface is non-trivial.

### Multi-agent constraints

`requirements/multi-agent.md` is **silent on whether the orchestrator must defer to peer agent output**. No requirement text mandates orchestrator deference to synthesizer output. No prohibition either.

### Direct precedent for orchestrator rationale

`requirements/pipeline.md` L130: "**Orchestrator rationale convention**: When the orchestrator resolves an escalation or makes a non-obvious feature selection decision, the relevant events.log entry should include a `rationale` field. Routine forward-progress decisions do not require this field." — direct precedent for an "orchestrator pushback rationale" pattern, but pipeline-side, not critical-review-side.

### Hard contract invariants (must be preserved)

1. **events.log schema**: Event type names are consumed by `cortex_command/overnight/report.py` and `cortex_command/pipeline/metrics.py`. **No new event types.** Note: `clarify_critic` is a *lifecycle* event, NOT a critical-review event. Critical-review writes only to `critical-review-residue.json`, not events.log.
2. **`critical-review-residue.json` schema** (Step 2e): additive **optional** fields only. Existing payload includes `ts, feature, artifact, synthesis_status, reviewers{completed,dispatched}, findings[]`. Morning-report consumer is `render_critical_review_residue` in `cortex_command/overnight/report.py`.
3. **JSON envelope class enum** (Step 2c.5): A/B/C only. New classes break Step 2c.5 schema validation.
4. **Step 4 compact summary format** (ticket 067): Apply direction-verbs, Dismiss-as-count-only, Ask consolidated. **Pushback mechanism must not reintroduce Dismiss verbosity.**
5. **Softened imperatives** (ticket 053): no CRITICAL/MUST/NEVER framing in critical-review prose.

### Open backlog items

**No open ticket conflicts.** Tickets 053, 067, 132 (most adjacent) all complete. Ticket 086 ("Extend output-floors.md with M1 Subagent Disposition") is blocked but does not constrain critical-review (which is excluded from output floors per ticket 053).

## Tradeoffs & Alternatives

### Orchestrator-side options (Step 4)

| Option | Description | Complexity | Effect-size | Alignment |
|--------|-------------|-----------|-------------|-----------|
| (a) Inline Apply-bar strengthening | Append re-examination sentence to existing Apply-bar paragraph | Low (~3 LOC) | Medium-low (implicit trigger) | Strong |
| (b) New Step 4.0 sub-step | Explicit named pre-classification pass for A-class findings | Medium (~10–15 LOC) | High (mandatory named step) | Medium (duplicates 2d structure) |
| (c) New "Pushback" disposition (4-way) | Apply/Dismiss/Ask/Pushback | High (~20+ LOC, summary format change) | High but at high cost | Weak (fractures 067 format) |
| (d) Wrap Apply with reclassification pre-check | Insert paragraph before Apply definition; A→B reclassification routes through B/C handling; no new step or disposition | Low-medium (~5–8 LOC) | High (mandatory inline check at the failure site) | Strong (mirrors existing anchor-check pattern) |

### Upstream-side options

| Option | Description | Complexity | Effect-size | Alignment |
|--------|-------------|-----------|-------------|-----------|
| (e) Synthesizer framing | Replace closing line with claims-not-verdict framing; per-finding `confidence` tier | Low (~3–5 LOC) | Medium (treats framing symptom not class-tag cause) | Strong |
| (f) Class-tag rigor | Add required `fix_invalidation_argument` field on A-class findings | Medium (~10–15 LOC across reviewer + extractor + synthesizer) | High (forces upstream discrimination at tagging time) | Strong (sibling to existing `straddle_rationale`) |
| (g) Tighten A-class definition | Revise definition; possibly Straddle Protocol tweak | Very low (~1–2 LOC) | Low-medium (definitions without enforcement drift) | Strong |

### Tradeoffs agent's recommended pairing: (d) + (f)

- (d) gives orchestrator a mandatory checkpoint at the rolling-over moment without new step/disposition surface; mirrors existing anchor-check pattern.
- (f) gives (d) falsifiable material to push back against — without (f), orchestrator pushback is fuzzy "did the quote say that?" judgment.
- Combined: three independent shots at catching loose A-tags (reviewer justification → synthesizer downgrade → orchestrator re-check).

### Redundancy argument (Tradeoffs agent)

(d) is not redundant with Step 2d #3 because:
1. Different **anchoring**: synthesizer anchors on reviewer findings (treats them as material); orchestrator anchors on artifact ownership (asks "does this invalidate MY fix?").
2. Different **stakes**: synthesizer surfaces a note; orchestrator changes the disposition.
3. Different **failure modes caught**: materiality vs evidence support.

**Note**: This argument is challenged by the Adversarial agent — see §1 below.

## Adversarial Review

### 1. The Anthropic post directly contradicts the user's combination premise

The Tradeoffs agent's "different anchoring" defense collapses on prompt inspection. Step 2d instruction #3 (line 198) literally says "re-read its `evidence_quote` field against the artifact content provided above" — the synthesizer **already has the artifact in context** and is **already** told to re-read evidence against it. The "different anchoring" is not a structural fact; it is a fictive distinction between two passes that read the same artifact against the same evidence quotes. Anthropic's post directly says inline self-criticism instructions like (d)'s are the harder lever.

**Cleaner intervention**: upstream-only. Strengthen (f); drop (d). The combination cannot independently justify each half against project.md L19.

### 2. (d) dilutes the existing Apply bar rather than reinforcing it

Step 4 already carries: Dismiss anchor check (282), self-resolve-before-Ask anchor (286), Apply bar (303), C-class default-to-Ask (284), summary format (067). Adding a fourth gate ("re-examine A-class evidence_quote before Apply") is structurally identical to the inline guidance Anthropic warns is hard to land. Why would the new sentence land when the existing Apply-bar sentence ("Apply when and only when the fix is unambiguous and confidence is high") already implies the same operation and apparently doesn't fire in the failure mode?

### 3. (f)'s required field becomes a compliance ritual without a synthesizer-side discriminator

Reviewer agents will produce **always-filled** `fix_invalidation_argument` strings. They will not write "this argument is weak, please downgrade me." Synthesizer needs explicit rubric language to detect fabricated/weak arguments — Step 2d #3 only says re-read the `evidence_quote`. Without rubric extension, the field is decorative.

Test fixtures confirm the gap: `pure_b_aggregation.md` and `straddle_case.md` do not exercise "reviewer tagged A and provided weak invalidation argument" — that is the exact case (f) is designed to catch.

### 4. Schema invariants conflict with the "required" framing

Adding `fix_invalidation_argument` as **required** to A-class findings:
- Reviewers may emit A-class envelopes without the field under token pressure → Step 2c.5 validation failure → prose routes to untagged → **excluded from A-class tally**. This is the inverse of desired behavior: a reviewer with a real A-class concern but a weak/missing argument now disappears entirely instead of being downgraded to B.
- Residue payload (line 266) — does the field propagate to `critical-review-residue.json`? Yes → `report.py:887` needs updating; no → loss of auditability for the field justifying orchestrator pushback.

The contract permits **additive optional** only. (f) as currently described is additive-required, which violates the invariant unless explicitly downgraded.

### 5. Cross-skill propagation is structurally inappropriate

`clarify-critic.md` line 69: "reproduced from /cortex:critical-review Step 4 to avoid silent drift." But the failure modes are **not symmetric**:
- critical-review handles A/B/C-tagged objections about a plan/spec the orchestrator wrote.
- clarify-critic handles **untagged prose objections** about a confidence assessment — there is no class taxonomy and no `evidence_quote` field. The (d) intervention "re-read evidence_quote against artifact" cannot be propagated verbatim — only rewritten with divergent semantics.

Furthermore, clarify-critic Ask items merge into §4 Q&A which is **user-resolved**, not orchestrator-resolved. The rolling-over failure mode targeted by (d) cannot fire there because the orchestrator isn't unilaterally applying.

### 6. (d) introduces an inverse failure (defensive A-dismissal) without a guard

The user's failure: orchestrator treats synthesis as verdict. (d) gives the orchestrator authority to reclassify A→B inline with a one-line rationale — **without** a parallel anchor-check escape hatch. Compare:
- Existing Dismiss anchor (282): "if your dismissal reason cannot be pointed to in the artifact text and lives only in your memory of the conversation, treat it as Ask"
- Existing self-resolve anchor (286): "if your resolution relies on conclusions from your prior work on this artifact rather than new evidence found during the check, treat it as Ask"

(d) needs a symmetric guard: A→B reclassification must default to **A preservation** when rationale doesn't ground in artifact text. Otherwise (d) inverts the failure mode under a procedural blessing.

### 7. Residue schema needs `reclassified_from: "A"`

If (d) ships, A→B reclassifications leak into morning-report B-class residue indistinguishable from organic B-class findings. `report.py:887` aggregates these. The residue payload must add `reclassified_from: "A"` to keep the morning B-class signal honest.

### 8. Step 4 is structurally untestable today

Step 4 is **prompt-only**; no programmatic hook fires it. Existing `test_critical_review_classifier.py` checks class counts and synthesis phrases in stdout. Step 4 fires after Step 3 presents — may or may not appear in captured stdout. **No existing test asserts Step 4 dispositions.** Without observable Step 4 telemetry (events.log entry or structured stdout block), this change is structurally untestable and silent regression is undetectable.

### 9. The diagnosis itself may be misplaced

Step 2d already includes an explicit anti-verdict instruction (line 203): "No fix-invalidating objections after evidence re-examination. The concerns below are adjacent gaps or framing notes — do not read as verdict." If verdict-reading persists despite this opener firing, the leak may be at reviewer prompt level (reviewers using verdict verbs like "blocks/invalidates"), not at Step 4. **Cheaper experiment before shipping**: instrument the existing anti-verdict opener firing rate vs. orchestrator capitulation rate. Without that data, the failure mode is anecdotal and the fix is speculative.

## Open Questions

**Scope resolution (Research Exit Gate, 2026-04-25)**: User pivoted from Combination to **upstream-only**. The orchestrator-side intervention (d) is dropped from scope. Spec scopes to (f) class-tag rigor at Step 2c + synthesizer rubric extension at Step 2d. Rationale: Anthropic guidance ("tuning a standalone evaluator to be skeptical turns out to be far more tractable") + Adversarial argument that (d) duplicates Step 2d #3 on prompt-text inspection.

1. **Premise reconsideration given Anthropic guidance**: **RESOLVED** — Pivot to upstream-only confirmed by user.

2. **Measurement before intervention**: **RESOLVED** — User chose to proceed with upstream-only changes rather than measure-first. Instrumentation may be considered as an optional follow-on but does not gate this lifecycle.

3. **(f) required vs optional field contract**: **Deferred: will be resolved in Spec via structured interview.** Required violates Step 2c.5's strict envelope schema and risks excluding real A-class findings via validation failure; optional risks vestigial use. Spec to weigh "optional with synthesizer-side absent-argument-flagging" vs alternatives.

4. **(f) synthesizer-side rubric**: **Deferred: will be resolved in Spec via structured interview.** Spec to define explicit rubric language for grading `fix_invalidation_argument` quality (e.g., "an argument that restates the finding without connecting evidence to fix-failure should trigger A→B downgrade").

5. **(d) inverse-failure anchor check**: **OBVIATED** — (d) dropped from scope.

6. **Residue schema additive field**: **OBVIATED** — was contingent on (d) shipping.

7. **Clarify-critic propagation**: **OBVIATED** as a (d)-propagation question. **Deferred: will be evaluated in Spec** — separately, whether clarify-critic.md's "reproduced to avoid silent drift" comment needs any update given that critical-review's upstream-side mechanisms (class taxonomy, evidence_quote, JSON envelope) have no clarify-critic analogue. Likely no change required since (d) is dropped, but Spec should explicitly confirm.

8. **Step 4 observability**: **OBVIATED** — no Step 4 changes in upstream-only scope.

9. **Tradeoffs agent's "different anchoring" claim**: **RESOLVED** — moot given upstream-only pivot. The Adversarial challenge stands as the load-bearing argument; Tradeoffs' "different anchoring" defense is acknowledged as post-hoc.

### Out-of-scope (after pivot)

- (d) orchestrator pushback at Step 4
- Any change to Step 4 prose, dispositions, anchor checks, or summary format
- `critical-review-residue.json` schema changes
- Step 4 telemetry / events.log changes
- Clarify-critic.md changes contingent on Step 4 propagation

### In-scope (after pivot)

- Step 2c reviewer prompt: class-tag rigor mechanism (likely `fix_invalidation_argument` field on A-class findings; required vs optional TBD in Spec)
- Step 2d synthesizer prompt: rubric extension to grade `fix_invalidation_argument` quality and apply A→B downgrade when argument is weak
- Step 2c.5 envelope extraction: schema validation update for new field
- Optionally Step 2c A-class definition tightening (option g) if the Spec finds it complementary
- `tests/fixtures/critical-review/`: new fixture(s) exercising "reviewer tagged A with weak invalidation argument that should be downgraded"
- `tests/test_critical_review_classifier.py`: test additions for the new behavior
