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

### No post-019 overnight session data exists

The only overnight sessions (April 1, 2026 — runs 1650 and 2112) predate ticket 019 (merged April 3). There is **no empirical evidence** to determine whether 019's changes eliminate the spec-violation failure pattern. The backlog item anticipated this: "This spike should not begin until item 019 has been implemented and some overnight sessions have run."

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

### The overnight gap

The lifecycle review phase verifies spec compliance with per-requirement PASS/FAIL/PARTIAL verdicts — but runs during daytime interactive work, not during overnight execution. The overnight pipeline has no equivalent. Between "tests pass" and "spec compliance verified," there is no overnight-time check.

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

### Recommended approach

**Alternative A (status quo)**, with Alternative C as a low-cost enhancement if justified by future post-019 overnight data. Escalation path if new failures emerge: first try review rubric refinement (C, S-M effort), then evaluator agent (D, L effort) only if review-level checks are insufficient.

## Open Questions

- No post-019 overnight sessions have run yet. The spike's central question — do spec-intent violations persist after 019? — cannot be answered with current data. The recommended action is to run overnight sessions and revisit this spike after observing results.
- If the review rubric refinement (Alternative C) is pursued, should it apply to all features regardless of tier/criticality, or only to features that already qualify for review? The current skip logic for simple/low creates a coverage gap that is relevant to this question.
