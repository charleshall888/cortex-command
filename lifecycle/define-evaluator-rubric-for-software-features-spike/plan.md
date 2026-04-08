# Plan: Define evaluator rubric for software features (spike)

## Overview

Document-production spike with three deliverables: spike conclusions answering the original 3 questions in research.md, a v0 skepticism-tuning protocol in research.md, and a backlog ticket for wiring the review phase into the overnight runner. No code changes — all tasks edit markdown or create new markdown files.

## Tasks

### Task 1: Write spike conclusions section in research.md
- **Files**: `lifecycle/define-evaluator-rubric-for-software-features-spike/research.md`
- **What**: Add a `## Spike Conclusions` section at the end of research.md with three subsections (`### Question 1`, `### Question 2`, `### Question 3`) answering the backlog item's original three questions. Each answer cites evidence from the post-019 overnight data and review-phase investigation already documented in the same file. Include an escalation path (Alternative C → D) for future failures.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The three questions from `backlog/021-define-evaluator-rubric-for-software-features.md` lines 30-37: (1) Are there overnight failures where a feature passed tests but violated spec intent? (2) Can failures be prevented by tighter plan.md verification (019)? (3) If an evaluator is warranted, what are the criteria? Evidence is in the `### Post-019 overnight session results` and `### The overnight gap — confirmed and worse than expected` sections of research.md.
- **Verification**: `grep -c '## Question' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 3 — pass if count is 3
- **Status**: [x] complete

### Task 2: Write skepticism tuning protocol in research.md
- **Files**: `lifecycle/define-evaluator-rubric-for-software-features-spike/research.md`
- **What**: Add a `## Skepticism Tuning Protocol` section to research.md defining a v0 framework for iteratively calibrating evaluator skepticism. Must include four subsections: (a) data to collect from evaluator runs, (b) signals indicating the evaluator is too positive, (c) prompt adjustments to make, (d) review cadence. Explicitly framed as pre-empirical — to be refined after Alternative F ships and produces real evaluator data.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The protocol is grounded in the Anthropic article's recommendation ("iteratively tune the evaluator for skepticism — reading evaluator logs, identifying judgment gaps, and updating prompts over several rounds"). Current events.log format uses NDJSON with fields like `event`, `verdict`, `issues`, `cycle`. The review phase reference at `skills/lifecycle/references/review.md` defines the existing review criteria (Stage 1: per-requirement PASS/FAIL/PARTIAL, Stage 2: code quality). Protocol must work with these existing formats.
- **Verification**: `grep -c '## Skepticism Tuning Protocol' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 1 — pass if count is 1
- **Status**: [x] complete

### Task 3: Create Alternative F backlog ticket
- **Files**: `backlog/043-wire-review-phase-into-overnight-runner.md`
- **What**: Create a new backlog item for "Wire review phase into overnight runner" with standard YAML frontmatter. Must include: `parent: "021"`, `type: feature`, `status: backlog`, `priority: medium`, tags referencing overnight and review. Body describes the structural gap (batch_runner.py never dispatches review), the fix (add post-merge review dispatch for features qualifying per gating matrix), and scope boundaries (morning review synthetic events, cycle cap, timeout).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Next available ID is 043. Frontmatter schema matches existing items (see `backlog/040-*.md` for recent example). The ticket body should reference: `batch_runner.py` merged→complete shortcut, `walkthrough.md` §2b synthetic events, the gating matrix in `skills/lifecycle/references/implement.md`, and the existing review agent at `skills/lifecycle/references/review.md`.
- **Verification**: `ls backlog/043-wire-review*overnight*.md` returns exactly one file — pass if exit 0; `grep -c 'parent:.*021' backlog/043-wire-review-phase-into-overnight-runner.md` = 1 — pass if count is 1
- **Status**: [x] complete

### Task 4: Update lifecycle index and verify all acceptance criteria
- **Files**: `lifecycle/define-evaluator-rubric-for-software-features-spike/index.md`
- **What**: Append `plan` to the artifacts array and add the plan wikilink to index.md. Then run all spec acceptance criteria to verify deliverables.
- **Depends on**: [1, 2, 3]
- **Complexity**: trivial
- **Context**: index.md currently has `artifacts: [research, spec]`. Add `plan` to make `[research, spec, plan]`. Add wikilink line `- Plan: [[define-evaluator-rubric-for-software-features-spike/plan|plan.md]]`.
- **Verification**: `grep -c 'plan' lifecycle/define-evaluator-rubric-for-software-features-spike/index.md` >= 2 — pass if count is at least 2 (artifacts array + wikilink)
- **Status**: [x] complete

## Verification Strategy

Run all spec acceptance criteria in sequence:
1. `grep -c '## Question' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 3
2. `ls backlog/*wire-review*overnight*.md` returns exactly one file
3. `grep -c 'parent:.*021' backlog/043-wire-review-phase-into-overnight-runner.md` = 1
4. `grep -c '## Skepticism Tuning Protocol' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 1
5. `grep -c 'Alternative F' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` >= 2
