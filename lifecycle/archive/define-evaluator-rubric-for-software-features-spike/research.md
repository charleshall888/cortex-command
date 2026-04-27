# Research: Define evaluator rubric for software features (spike)

## Epic Reference

Background context from [research/harness-design-long-running-apps/research.md](../../research/harness-design-long-running-apps/research.md) — the epic investigated patterns from Anthropic's long-running agent article. This ticket is scoped to one finding: whether a post-implementation evaluator rubric is warranted for the overnight runner.

## Codebase Analysis

### What ticket 019 introduced

Ticket 019 (commit `8b34c66`) made targeted changes to three documentation/template files — no runtime code changes:

- **`skills/lifecycle/references/orchestrator-review.md`**: S1 (spec acceptance criteria) and P4 (plan verification steps) now require "binary-checkable" criteria in one of three formats: (a) runnable command + expected output + pass/fail, (b) observable state naming specific file/pattern/result, or (c) "Interactive/session-dependent: [rationale]" annotation. Prose criteria like "confirm the feature works correctly" explicitly do not pass.
- **`skills/lifecycle/references/specify.md`**: Updated the Requirements section template with binary-checkable format inline.
- **`skills/lifecycle/references/plan.md`**: Updated Verification placeholders in both competing-plan prompt and standard template. Added prohibition against "Verification fields that consist only of prose descriptions requiring human judgment."

### Companion ticket 025 (self-sealing prevention)

Ticket 025 (commit `c2daec5`) added self-sealing verification defenses:
- P7 checklist item in `orchestrator-review.md` for detecting self-sealing verification
- Builder instruction #6 in `implement.md` telling workers to flag self-sealing rather than self-certify
- Inlined prohibition in `claude/overnight/prompts/orchestrator-round.md` Step 3b sub-agent prompt

### Where spec compliance checking happens today

| Layer | Mechanism | What it checks | Coverage gap |
|-------|-----------|----------------|-------------|
| Runtime | Merge gate (`claude/pipeline/merge.py`) | Tests pass after merge | Binary only — no spec compliance |
| Runtime | No-commit guard (`batch_runner.py` ~line 1275) | `changed_files` non-empty | Catches empty implementations |
| Prompt | Review phase (`review.md`) | Per-requirement PASS/FAIL/PARTIAL + code quality | Daytime only; skipped for simple/low features |
| Prompt | Orchestrator review (`orchestrator-review.md`) | S1/P4/P7 on artifacts | Skipped for low+simple; overnight Step 3b skips entirely |
| Prompt | Brain agent (`batch-brain.md`) | SKIP/DEFER/PAUSE triage | Post-failure only — does not evaluate spec compliance |

### Post-019 overnight session results (April 7-8, 2026)

Session `overnight-2026-04-07-0008` is the first overnight run after ticket 019 (merged April 3). Results:

- **6 features completed**, all merged, clean run verdict
- **0 spec compliance failures** among the 6 newly built features
- **0 test failures** — all features passed tests before merge
- **4 rounds** completed over 37h 57m

All 6 features had binary-checkable acceptance criteria in their specs (visible in morning report "How to try" sections). This is the direct effect of 019's S1/P4 enforcement — specs now contain runnable verification commands rather than prose descriptions.

**One requirements drift flag** was raised, but for a pre-existing feature (`wire-requirements-drift-check-into-lifecycle-review`), not one built in this session. The drift flag noted that `render_pending_drift()` in `report.py` introduces a morning report section not described in `requirements/project.md`. This is scope creep in the requirements-drift-check feature itself (ironic), not a failure of the 6 features built under 019's rules.

**State/batch mismatch warning**: The morning report noted "6 feature(s) show 'merged' in state but have no merge recorded in batch results." This is an operational issue in the overnight runner's state tracking, not a spec compliance concern.

**Conclusion**: The central question — do spec-intent violations persist after 019? — has a provisional answer: **no, not in this sample**. One overnight session (6 features) is a small sample, but the absence of any spec violation combined with the structural improvement (binary-checkable criteria are now enforced at authoring time) supports the status quo recommendation.

### Status of the three observed failure instances

| Instance | Failure | Addressed by | Status |
|----------|---------|-------------|--------|
| 1 | Self-sealing log entry (retro 2026-04-02-1629) | Ticket 025 — P7 checklist, builder instruction 6, Step 3b inline prohibition | Prompt-layer fix; runtime gap for overnight-generated plans tracked by backlog 036 |
| 2 | CHANGES_REQUESTED after all 9 tasks succeeded | Ticket 019 — S1/P4 binary-checkable enforcement | Structurally prevented at authoring time |
| 3 | No-commit guard firing (zero commits) | Existing guard in `batch_runner.py` | Already caught in production |

### Documented gaps remaining after 019 + 025

- Low+simple features skip orchestrator review entirely
- Overnight-generated plans (Step 3b) skip orchestrator review; only inlined prohibition covers self-sealing
- `verification_passed` field in exit reports is dead code (tracked by backlog 036)
- Pipeline implement prompt (`claude/pipeline/prompts/implement.md`) lacks the self-sealing prohibition

## Web Research

### Evaluator rubric prior art

**Scale AI's Agentic Rubrics**: Two-phase pipeline where an agent explores the repo and generates a structured rubric checklist, then a separate LLM judge scores patches against it. Four axes: File Change (edits minimal and scoped), Spec Alignment (requirements satisfied), Integrity (no shortcuts), Runtime (correct execution). Execution-free — no sandbox needed. Key insight: per-spec rubric generation outperforms fixed templates.

**ASDLC Adversarial Code Review Pattern**: Fresh AI session (the "Critic Agent") receives spec and code diff. Operates in separate context to avoid self-confirmation bias. Catches architectural constraint violations that pass all tests.

**Evaluator-Optimizer Workflow (Anthropic)**: Canonical pattern where one LLM generates and another evaluates in a loop. Works best when clear evaluation criteria exist.

### Key research findings

**Per-spec rubrics dramatically outperform generic ones**: Pearson correlation of 0.825 vs 0.562 against human grading (ACL 2025 research). Generic rubrics "fail to capture the nuances of specific programming problems." Implication: if a rubric is built, it should be generated per-spec, not from a fixed template.

**Correlated error hypothesis**: AI generators and reviewers from the same model family share blind spots. Without external specs, both reason from the code alone — circular validation. Grounding review in human-authored specs improved developer adoption of suggestions by 90.9%.

**Self-confirmation bias is confirmed real**: Same model/context generates and evaluates → it misses its own errors. Separate sessions with fresh context are essential. The PGE (Planner-Generator-Evaluator) pattern specifically addresses this.

### What a rubric would look like (if warranted)

Based on converging web research, an evaluator rubric for software features would use four axes (adapted from Scale AI):
1. **Spec Alignment**: Does each spec requirement have a corresponding implementation?
2. **Integrity**: No shortcuts — hardcoded values, disabled tests, bypassed validation, stubbed implementations?
3. **Architectural Compliance**: Implementation follows project conventions and constraints?
4. **Completeness**: Edge cases and non-happy-path scenarios addressed?

Best practices: per-spec generation (not fixed template), categorical integer scoring (1-5), structured reasoning per finding, 2-3 max iterations before escalation.

## Requirements & Constraints

### Relevant requirements

- **Quality bar** (`project.md`): "Tests pass and the feature works as specced. ROI matters." Deliberately minimal.
- **Complexity philosophy** (`project.md`): "Must earn its place by solving a real problem that exists now."
- **Handoff readiness** (`project.md`): "The spec is the entire communication channel." Evaluator rubric would be derived entirely from spec.
- **Graceful partial failure** (`project.md`): Evaluator must not block the pipeline — findings should surface in morning report, not gate merges.
- **Fail-forward model** (`pipeline.md`): One feature's failure must not block others.
- **Cost-bounded repair caps** (`pipeline.md`): Max 2 attempts for test failures, single escalation for merge conflicts. Any evaluator needs similar bounding.
- **Orchestrator-dispatched agents** (`multi-agent.md`): Evaluator would be dispatched by orchestrator, not self-invoked by worker.

### Current definition of feature success in the pipeline

A feature is `merged` when: (1) worker produces commits, (2) branch merges cleanly, (3) test command passes, (4) no CI gate blocks. Notably absent: no spec-compliance check, no acceptance-criteria verification, no scope check.

### The overnight gap — confirmed and worse than expected

The lifecycle review phase verifies spec compliance with per-requirement PASS/FAIL/PARTIAL verdicts — but it **never runs during overnight execution**. Investigation of the post-019 overnight session confirmed this structurally:

1. **`batch_runner.py`** merges features after implementation and marks them `status: "merged"` in overnight-state.json. It never checks the tier/criticality gating matrix and never dispatches a review agent.
2. **Morning review skill** (`walkthrough.md` §2b) unconditionally batch-writes synthetic `review_verdict: APPROVED` events with `cycle: 0` for all merged features — no `review.md` produced, no spec compliance check performed.
3. **3 of 6 features** in the post-019 session were complex-tier and should have been reviewed per the gating matrix in `implement.md`, but the overnight runner never consults that matrix.

The gap is not just "no spec-compliance check" — the review phase is designed, documented, and referenced in the gating matrix, but **never wired into the overnight execution path**. The morning review creates the appearance of review (synthetic events in events.log) without the substance.

This aligns with the Anthropic harness article's warning about self-validation: the system produces approval artifacts without an independent evaluation agent running. The early-phase evaluators (orchestrator review during research/specify) do run and catch real issues (3 flags across 4 features), but the post-implementation review — the phase designed to catch spec violations — is structurally absent.

## Tradeoffs & Alternatives

### A: Status quo + 019 (no rubric)

Rely on tightened verification (019), self-sealing guards (025), and existing no-commit guard. Accept that some spec compliance issues may reach the review phase.

- **Pros**: Zero cost. All three observed instances addressed. Aligned with "complexity must earn its place."
- **Cons**: Self-sealing prevention is prompt-layer only (runtime gap for Step 3b). No catch for failure patterns outside the three observed categories. Simple/low features skip review entirely.
- **Coverage**: All three observed instances.

### B: Template-based rubric (authoring-time checklist)

Add checklist items to the builder prompt template that the implementing agent self-verifies against.

- **Pros**: Minimal cost (S effort). No runtime overhead. Applies to all tiers.
- **Cons**: Self-verification is the problem — adding more self-check items is vulnerable to the same bias. Increases builder prompt length.
- **Coverage**: Marginal improvement. Does not structurally prevent any failure mode.

### C: Review rubric refinement (explicit criteria for existing review phase)

Make the review phase criteria more explicit: add structured categories for provenance, coverage, and verification integrity to `review.md`.

- **Pros**: Leverages existing infrastructure (no new agent/pipeline phase). Reviewer is already a separate agent with fresh context. S-M effort.
- **Cons**: Only applies to features that reach review (simple/low skip). Cannot reliably check provenance via git log. Catches issues after implementation, not before.
- **Coverage**: Strong for spec compliance (instance 2). Weak for provenance (instance 1).

### D: Independent evaluator agent

New pipeline phase between implementation and review. Separate agent applies rubric to spec + diff + tests.

- **Pros**: Strongest separation of concerns. Can apply checks impractical in review prompt.
- **Cons**: L effort. Extra API call per feature. New failure modes (crash, loops, false negatives). Research concluded: "addresses a problem not yet observed in practice." Blocking prerequisite: rubric must be defined first.
- **Coverage**: Theoretically highest. In practice, limited to whatever rubric specifies — which does not yet exist.

### E: Provenance-based checks

Verify completion evidence was not authored by the implementing agent. Runtime enforcement of the self-sealing prohibition.

- **Pros**: Directly targets instance 1. Orthogonal to other alternatives.
- **Cons**: Prompt-layer version already deployed. Runtime enforcement requires file authorship tracking (M effort). One confirmed instance in project history. Explicitly scoped out of 025 spec.
- **Coverage**: Narrow — instance 1 only.

### F: Wire review phase into overnight runner

Add a post-merge review dispatch to the overnight pipeline for features that qualify per the gating matrix (complex tier, or high/critical criticality). The review agent already exists (`review.md` reference); the gap is the dispatch call in the batch runner.

- **Pros**: Uses existing review infrastructure. Addresses the structural gap directly. No new rubric or agent needed. M effort.
- **Cons**: Adds API cost per reviewed feature. Needs bounding (cycle cap, timeout). Morning review synthetic events must be conditional (only for features not already reviewed).
- **Coverage**: All complex-tier features would get independent post-implementation spec compliance review.

### Recommended approach (updated April 8, 2026)

**Alternative F (wire existing review into overnight)** as the primary action. The investigation revealed the review phase is designed but never dispatched — this is the highest-ROI fix. Alternative C (review rubric refinement) becomes a follow-on if the wired-in reviewer proves too positive once running. Alternative D (independent evaluator) remains the escalation path if review-level checks are insufficient.

The original recommendation (Alternative A, status quo) is no longer appropriate: the "status quo" includes a structural gap where complex features bypass review entirely during overnight execution, masked by synthetic approval events.

## Open Questions

- ~~No post-019 overnight sessions have run yet.~~ **Resolved (April 8, 2026)**: Session `overnight-2026-04-07-0008` ran 6 features post-019 with zero spec compliance failures. Binary-checkable criteria enforcement appears effective. Sample size is small (1 session, 6 features).
- ~~If the review rubric refinement (Alternative C) is pursued, should it apply to all features regardless of tier/criticality?~~ **Reframed**: The primary issue is not rubric quality but review dispatch. Alternative F (wire review into overnight) should respect the existing gating matrix: review runs for complex-tier features and for high/critical criticality features regardless of tier.
- Should the morning review skill's synthetic approval events be removed entirely, or should they remain as a fallback for features where overnight review was intentionally skipped (simple/low)? Deferred: depends on implementation details of Alternative F.
- Per the Anthropic article's second recommendation ("iteratively tune the evaluator for skepticism"), should the existing review.md criteria be calibrated after wiring in the overnight dispatch? This is Alternative C as a follow-on — worth tracking but not blocking.

## Spike Conclusions

Answers to the three questions posed by backlog item 021, grounded in the post-019 overnight session (`overnight-2026-04-07-0008`, 6 features, April 7-8 2026) and the review-phase investigation conducted during this spike.

### Question 1: Are there overnight failures where a feature passed tests but violated spec intent?

**No spec-intent violations detected in the post-019 sample.** All 6 features built in session `overnight-2026-04-07-0008` passed tests and merged without spec compliance issues. The morning report flagged one requirements drift item, but it was for a pre-existing feature (`wire-requirements-drift-check-into-lifecycle-review`), not one built in this session.

However, the investigation revealed a more fundamental problem: **the post-implementation review phase never ran**. All 6 features received synthetic `review_verdict: APPROVED` events at `cycle: 0`, batch-stamped by the morning review skill (`walkthrough.md` §2b) at a single timestamp. No `review.md` files were produced. No independent review agent evaluated any feature. Three complex-tier features (accessibility, hover-states, swim-lane) that should have been reviewed per the gating matrix in `implement.md` were auto-approved without evaluation.

The absence of detected spec violations cannot be treated as evidence that none occurred — the system that would detect them was not running.

### Question 2: Can spec-intent failures be prevented by tighter plan.md verification requirements (019)?

**019's binary-checkable criteria enforcement is working at authoring time.** All 6 overnight features had runnable verification commands in their specs (visible in the morning report's "How to try" sections). This is a direct improvement over the pre-019 era where specs contained prose acceptance criteria.

But 019 addresses a different layer than the overnight gap. 019 ensures specs are well-defined; it does not ensure implementations are checked against those specs. The overnight runner's `batch_runner.py` treats a merged feature as complete (`merged → status: "complete"`) without consulting the gating matrix or dispatching a review agent. The review phase — the mechanism that would check spec compliance — is designed but never wired into the overnight execution path.

**019 is necessary but not sufficient.** Good specs without post-implementation review are like well-defined test cases that are never executed.

### Question 3: If an independent evaluator is warranted, what are the specific criteria?

**A new evaluator is not warranted. The existing review agent has appropriate criteria — it just needs to be dispatched.**

The lifecycle's review phase (`skills/lifecycle/references/review.md`) already implements:
- **Stage 1: Spec Compliance** — per-requirement PASS/FAIL/PARTIAL verdicts grounded in the spec
- **Stage 2: Code Quality** — naming conventions, error handling, test coverage, pattern consistency
- **Requirements Drift detection** — flags implementation behavior not covered by requirements

These criteria align with the four-axis rubric identified in web research (Spec Alignment, Integrity, Architectural Compliance, Completeness). The existing review agent is an independent evaluator with fresh context — it matches the Anthropic article's recommendation for separating generator from evaluator.

The gap is not in criteria or agent design. The gap is in dispatch: `batch_runner.py` never calls the review phase after merge. The fix is **Alternative F: wire the existing review phase into the overnight runner** for features qualifying per the gating matrix (complex tier, or high/critical criticality regardless of tier). A new backlog ticket (043) has been created for this work.

**Escalation path**: If future overnight sessions with review enabled reveal that the existing review criteria are insufficient (e.g., reviewer consistently approves features that fail morning review), pursue Alternative C (review rubric refinement) to tune the criteria. If review-level checks remain insufficient, escalate to Alternative D (independent evaluator agent with a per-spec generated rubric).

## Skepticism Tuning Protocol

> **v0 — pre-empirical.** This protocol is defined before the overnight review phase is running. It will be refined against real evaluator data after Alternative F (backlog ticket 043) ships and produces review verdicts from overnight sessions.

### (a) Data to collect from evaluator runs

After Alternative F wires review into the overnight runner, each reviewed feature will produce events in `lifecycle/{feature}/events.log`:

- `review_verdict` events with `verdict` (APPROVED/CHANGES_REQUESTED/REJECTED), `cycle` count, and `issues` array
- `review.md` files with per-requirement PASS/FAIL/PARTIAL verdicts, code quality findings, and requirements drift observations

Collect across overnight sessions:
- **Approval rate**: percentage of reviewed features receiving APPROVED on cycle 1
- **Issue density**: average number of issues per reviewed feature
- **Verdict distribution**: ratio of APPROVED vs CHANGES_REQUESTED vs REJECTED
- **Requirements drift detection rate**: how often drift is flagged as "detected" vs "none"
- **Morning review correlation**: whether features approved by the overnight reviewer are also accepted during morning human review, or whether the human finds issues the reviewer missed

### (b) Signals indicating the evaluator is too positive

- **Approval rate > 90% on first cycle** across 10+ reviewed features — the reviewer is not finding anything. Compare against the orchestrator review's flag rate during research/specify phases (currently ~50% on first cycle for the post-019 session).
- **Zero CHANGES_REQUESTED or REJECTED** across 3+ overnight sessions — the reviewer never pushes back.
- **Morning review finds issues in features the reviewer approved** — direct evidence of missed problems. Track as a "reviewer miss" counter.
- **Requirements drift always "none"** — the reviewer is not checking for scope creep despite evidence that it occurs (the drift checker already flagged one instance).
- **Issue array always empty on APPROVED verdicts** — the reviewer approves without noting anything, even minor observations.

### (c) Prompt adjustments to make

If positivity signals are triggered:

1. **Add explicit skepticism instruction** to the review agent dispatch: "Your job is to find what is wrong, not to confirm the implementation is correct. If you approve with zero issues, explain why no issues exist."
2. **Lower the APPROVED threshold** in `review.md` Stage 1: require PASS on all must-have requirements (currently allows PARTIAL). Make PARTIAL trigger CHANGES_REQUESTED rather than allowing approval with advisory notes.
3. **Add a "reviewer miss" feedback loop**: when the morning review identifies an issue the overnight reviewer missed, append the miss to a `reviewer-calibration.md` file that the reviewer reads at dispatch time. This grounds future reviews in concrete prior failures (the article's "reading evaluator logs and identifying judgment gaps").
4. **Inject adversarial framing**: change the reviewer's system prompt from neutral assessment to adversarial review — "assume the implementation has at least one problem and find it." This is the Anthropic article's core insight: tuning for skepticism is more tractable than tuning for accuracy.
5. **Rotate review agent model**: if Sonnet consistently approves, try dispatching Opus for a subset of features to check whether a different model finds issues Sonnet missed. If Opus finds more, escalate the default review model.

### (d) Review cadence

- **After first 3 overnight sessions with review enabled**: initial calibration check. Are positivity signals already visible? If approval rate is already < 80%, the reviewer may be appropriately calibrated.
- **Monthly thereafter**: scan accumulated review verdicts for drift toward positivity. Compare current-month approval rate against first-3-sessions baseline.
- **On any reviewer miss** (morning review finds issue in overnight-approved feature): immediate tuning cycle — apply the first applicable adjustment from (c) above, then monitor the next overnight session.
- **After 3 tuning adjustments**: if the reviewer is still too positive after 3 rounds of prompt adjustments, escalate to Alternative C (full review rubric refinement) or Alternative D (independent evaluator agent).
