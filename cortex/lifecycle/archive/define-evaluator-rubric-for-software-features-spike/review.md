# Review: define-evaluator-rubric-for-software-features-spike

## Stage 1: Spec Compliance

### Requirement 1: Spike conclusions in research.md
- **Expected**: A `## Spike Conclusions` section in `research.md` with exactly 3 subsections answering the backlog item's three original questions. Acceptance: `grep -c '## Question' research.md` = 3.
- **Actual**: `research.md` contains a `## Spike Conclusions` section with three subsections: `### Question 1`, `### Question 2`, `### Question 3`. Each cites evidence from the post-019 overnight session and the review-phase investigation. Verified count: 3.
- **Verdict**: PASS

### Requirement 2: Backlog ticket for Alternative F
- **Expected**: A backlog item for "Wire review phase into overnight runner" with standard YAML frontmatter and `parent: "021"`. Acceptance: `ls backlog/*wire-review*overnight*.md` returns exactly one file; `grep -c 'parent:.*021' ...` = 1.
- **Actual**: `backlog/043-wire-review-phase-into-overnight-runner.md` exists as the only matching file. Frontmatter includes `parent: "021"`. Both acceptance criteria met. Verified: one file returned, count = 1.
- **Verdict**: PASS

### Requirement 3: Skepticism-tuning protocol (v0)
- **Expected**: A `## Skepticism Tuning Protocol` section in `research.md` defining (a) data to collect, (b) signals indicating over-positivity, (c) prompt adjustments, (d) review cadence. Framed as v0/pre-empirical. Acceptance: `grep -c '## Skepticism Tuning Protocol' research.md` = 1.
- **Actual**: `research.md` contains the section with all four required subsections: `(a) Data to collect from evaluator runs`, `(b) Signals indicating the evaluator is too positive`, `(c) Prompt adjustments to make`, `(d) Review cadence`. The section opens with an explicit `> v0 — pre-empirical.` framing note. Verified count: 1.
- **Verdict**: PASS

### Requirement 4: Updated research artifact
- **Expected**: `research.md` reflects post-019 overnight findings, review-phase-skip investigation, and reframed recommendation (Alternative F). Acceptance: `grep -c 'Alternative F' research.md` >= 2.
- **Actual**: `grep -c 'Alternative F'` = 6. The file contains: a full post-019 overnight session analysis section, an in-depth investigation of the review-phase structural gap, and a reframed recommendation section where Alternative F is the primary action. The original Alternative A (status quo) recommendation is explicitly retracted.
- **Verdict**: PASS

## Requirements Drift

**State**: detected

**Findings**:
- The research.md investigation documents that `batch_runner.py` never dispatches the post-implementation review phase, and that the morning review skill (`walkthrough.md` §2b) unconditionally writes synthetic `review_verdict: APPROVED` events at `cycle: 0` for all merged features. Neither the review-dispatch gap nor the synthetic-approval behavior is described in `requirements/pipeline.md`. The pipeline requirements describe feature execution succeeding at merge + test gate passage — they do not mention a review phase dispatch step, a gating matrix, or the condition under which review_verdict events are written. The spike's backlog ticket (043) targets correcting this behavior, but the requirements doc does not yet reflect the intended future behavior either.
- `requirements/pipeline.md`'s "Metrics and Cost Tracking" section lists `review verdicts` as a per-feature metric (`lifecycle/*/events.log` → `lifecycle/metrics.json`), which implies reviews happen — but the pipeline requirements contain no requirement for when or whether the review phase is dispatched. This is an implicit assumption not stated as a requirement.

**Update needed**: `requirements/pipeline.md` — needs a "Post-Merge Review Dispatch" functional requirement section describing the gating matrix (tier × criticality), the conditions under which the review agent is dispatched, and the handling of synthetic approval events for intentionally-skipped features. This update belongs as a follow-on to backlog ticket 043.

## Suggested Requirements Update

**Target**: `requirements/pipeline.md`

**Proposed new section** ("Post-Merge Review Dispatch"):

> **Post-Merge Review Dispatch**: After a feature merges and passes the test gate, the pipeline dispatches a review phase if `requires_review(tier, criticality)` returns true (per the gating matrix in `claude/common.py`). Qualifying features run a review agent that writes `lifecycle/{feature}/review.md` with a verdict JSON (`APPROVED` / `CHANGES_REQUESTED` / `REJECTED` / `ERROR`) and a Requirements Drift observation. Features that do not qualify (e.g., simple-tier non-critical changes) receive a synthetic `review_verdict: APPROVED` event at `cycle: 0` so downstream consumers (morning report, metrics) see a uniform shape. The review phase does not block merge — it gates lifecycle completion only.
>
> **Inputs**: `lifecycle/{feature}/spec.md`, the merged diff on the integration branch, tier/criticality from events.log.
>
> **Outputs**: `lifecycle/{feature}/review.md`, `review_verdict` event in events.log, optional rework dispatch on `CHANGES_REQUESTED` (max 2 cycles, then defer).
>
> **Dependencies**: `claude/common.py::read_tier`, `claude/common.py::requires_review`, `claude/pipeline/review_dispatch.py`, `claude/pipeline/prompts/review.md`.

**Evidence trail**:
- `research.md` post-019 overnight investigation showing the review-dispatch gap (this review, Requirement 4).
- `backlog/043-wire-review-phase-into-overnight-runner.md` (this review, Requirement 2).
- `research.md` `## Spike Conclusions` section (this review, Requirement 1).

## Stage 2: Code Quality

- **Naming conventions**: All new sections follow existing `research.md` heading conventions (`##` for top-level sections, `###` for subsections). The backlog ticket filename (`043-wire-review-phase-into-overnight-runner.md`) matches the kebab-case pattern used by all other backlog items. YAML frontmatter field names are consistent with the existing backlog schema (`schema_version`, `uuid`, `id`, `title`, `type`, `status`, `priority`, `parent`, `tags`, `areas`, `created`, `updated`, `session_id`, `lifecycle_phase`, `lifecycle_slug`, `complexity`, `criticality`).
- **Error handling**: Not applicable — this is a document-only spike with no runtime code changes.
- **Test coverage**: All five spec acceptance criteria from the plan's Verification Strategy section were verifiable and pass. The plan marked all four tasks `[x] complete`. No verification steps were omitted.
- **Pattern consistency**: The `## Spike Conclusions` section follows the same evidence-first, interpretation-second structure used in the `## Codebase Analysis` and `## Web Research` sections above it. The backlog ticket's `## Origin`, `## The structural gap`, `## What to implement`, and `## Scope boundaries` sections match the structure of comparable backlog items (e.g., 041, 042). The `v0 — pre-empirical` framing of the tuning protocol is consistent with the project's stated pattern of iterative improvement (`requirements/project.md`: "some design will be discovered through use"). The index.md `artifacts` array correctly includes `plan` after plan creation, matching the pattern in other lifecycle index files.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
