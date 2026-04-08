# Specification: Define evaluator rubric for software features (spike)

## Problem Statement

The overnight runner has a structural gap where the post-implementation review phase — designed to catch spec compliance violations via independent agent evaluation — is never dispatched. Complex-tier features that should be reviewed per the gating matrix get synthetic `APPROVED` verdicts batch-written by the morning review skill without any evaluation occurring. This spike answers the original three questions (grounded in post-019 overnight data and review-phase investigation), produces a concrete backlog ticket for wiring review into the overnight runner, and defines a v0 skepticism-tuning protocol for calibrating evaluators once they are running.

## Requirements

1. **Spike conclusions in research.md**: Add a `## Spike Conclusions` section to the existing `research.md` answering the backlog item's three original questions with evidence from the post-019 overnight session and the review-phase investigation. Each question gets its own subsection. Acceptance: `grep -c '## Question' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 3.

2. **Backlog ticket for Alternative F**: Create a backlog item for "Wire review phase into overnight runner" using the standard backlog format with YAML frontmatter. The ticket must reference this spike as its origin (`parent: "021"`). Acceptance: `ls backlog/*wire-review*overnight*.md` returns exactly one file, and `grep -c 'parent:.*021' backlog/*wire-review*overnight*.md` = 1.

3. **Skepticism-tuning protocol (v0)**: Add a `## Skepticism Tuning Protocol` section to `research.md` defining a framework for iteratively calibrating evaluator skepticism per the Anthropic article's recommendation. The protocol must define: (a) what data to collect from evaluator runs, (b) what signals indicate the evaluator is too positive, (c) what prompt adjustments to make, and (d) a review cadence. Framed as v0 — explicitly pre-empirical, to be refined against real evaluator data after Alternative F ships. Acceptance: `grep -c '## Skepticism Tuning Protocol' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` = 1.

4. **Updated research artifact**: The existing `research.md` must reflect the post-019 overnight findings, the review-phase-skip investigation, and the reframed recommendation (Alternative F). Acceptance: `grep -c 'Alternative F' lifecycle/define-evaluator-rubric-for-software-features-spike/research.md` >= 2.

## Non-Requirements

- No implementation code. This spike produces document updates and a backlog ticket, not runtime changes.
- No new evaluator agent. The finding is that the existing review agent should be wired in, not that a new agent is needed.
- No changes to the morning review skill, batch runner, or any overnight pipeline code. Those belong to the Alternative F implementation ticket.
- No rubric definition. The investigation concluded a new rubric is not warranted — the existing review phase criteria are sufficient if actually executed.
- No separate finding.md artifact. The spike's conclusions are folded into `research.md` to avoid duplicating the analysis across two files in the same directory.

## Edge Cases

- If the Alternative F backlog ticket duplicates an existing backlog item: check `backlog/` for existing items mentioning "review" + "overnight" before creating. If a duplicate exists, update it rather than creating a new one.
- If future overnight sessions reveal spec compliance failures despite 019: the conclusions section should include an explicit escalation path (Alternative C → D) so the recommendation can be revisited without re-running the spike.

## Changes to Existing Behavior

- MODIFIED: `research.md` gains `## Spike Conclusions` and `## Skepticism Tuning Protocol` sections — extending the research artifact to serve as the spike's complete output document.
- ADDED: Backlog item for Alternative F — extends the backlog with a concrete follow-on from this spike's investigation.

## Technical Constraints

- The skepticism-tuning protocol must be actionable with the current events.log format — it cannot depend on new logging fields that don't exist yet. Framed as v0 to be refined after first real evaluator runs.
- The backlog ticket must follow the standard format (YAML frontmatter with schema_version, uuid, id, title, type, status, priority, parent, tags, etc.) so it is compatible with `update-item` and the overnight runner's feature selection.

## Open Decisions

- What numeric ID to assign the Alternative F backlog ticket. Must be determined at creation time by checking the highest existing ID in `backlog/`. Cannot be resolved at spec time because the ID space changes as other tickets are created.
