# Orchestrator Phase Review

Quality gate between phase artifact write and user presentation. The orchestrator reviews the artifact against phase-specific checklists, dispatches fixes for flagged issues, and only surfaces the artifact to the user once it passes or the cycle cap is reached.

## Applicability

Before running this protocol, determine whether orchestrator review applies. Read both fields by running `cortex-lifecycle-state --feature {feature}` (emits JSON). Defaults: criticality `medium`, tier `simple` when the key is absent.

If that output contains `"corrupted": true`, the events.log is corrupted and the tier/criticality are unknowable — treat the feature as requiring review (run the protocol below) rather than applying the skip rule and defaulting.

**Skip rule**: Skip orchestrator review when criticality is `low` AND tier is `simple`. Proceed directly to user presentation or the next phase.

Run review for all other combinations.

If the review is skipped, do not log any orchestrator events.

## Protocol

### 1. Execute Review

Select the checklist matching the artifact — Post-Specify (after `spec.md`) or Post-Plan (after `plan.md`), from the Checklists section below — then evaluate the artifact against every item, assigning each **pass** or **flag**. Flag any item that is not satisfied or is materially weak; a flag requires a fix before user presentation.

Run this review in the main conversation — do not dispatch a subagent; the artifact is already in context.

### 2. Handle Verdict

**On pass**: Show the user a one-line assessment summarizing what was checked and the result. Example: "Spec clean: 6 requirements with measurable criteria, edge cases covered, scope boundaries explicit."

Then proceed to user presentation or the next phase as normal.

**On flag**: Check the cycle counter. If this is cycle 3 or beyond, go to Escalation (step 4). Otherwise, proceed to Fix Dispatch (step 3).

### 3. Fix Dispatch

For each flagged issue, determine the appropriate fix mode:

**Fresh subagent** (via Task tool): Use for thinking-quality rework that does not require user input. Fresh context prevents anchoring to the flawed artifact.

**Model for fresh subagent fixes**: resolve the fix sub-agent model at dispatch by running the verb against the feature criticality — do not hardcode a model literal:

```bash
model=$(cortex-resolve-model --role orchestrator-fix --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Pass the captured `$model` as the fresh fix sub-agent's model. On nonzero exit from `cortex-resolve-model`, halt and escalate rather than guessing or substituting a model.

**Same conversation**: Use for interactive rework that requires user input — where user preference determines the answer. Explain the issue to the user, gather their input, and then revise the artifact in the current context.

After all fixes complete, increment the cycle counter, return to step 1 (Execute Review) with the same checklist. Read the fix-agent envelope but do not relay it to the user — only the re-review verdict surfaces.

#### Fix Agent Prompt Template

Dispatch the fresh fix sub-agent using the fix-agent prompt template at the body-resolved **fix-agent-prompt-template** path (lifecycle SKILL.md Reference-path propagation).

### 4. Escalation

The orchestrator runs a maximum of **2 review cycles per phase** — one cycle is a complete pass through the checklist, and the counter resets for each new phase (do not start cycle 3). When the cycle cap is reached (2 cycles completed, issue persists), stop reviewing and escalate to the user. Present:

- What was checked (the flagged checklist items)
- What was tried (fixes dispatched in each cycle)
- What remains unresolved (items still flagged after 2 cycles)

After escalation, the user decides how to proceed. Do not continue reviewing.

## Checklists

**Binary-checkable** (used by S1 and P4) means satisfied in at least one of three forms: (a) a runnable command with observable output and an explicit pass/fail criterion (e.g., exit code = 0, grep count ≥ N); (b) an observable state naming the specific file path, the specific string/pattern to find, and the expected true/false result; (c) annotated `Interactive/session-dependent: [one-sentence rationale]` when neither (a) nor (b) applies.

### Post-Specify Checklist

Evaluate against `cortex/lifecycle/{feature}/spec.md`:

| # | Item | Criteria |
|---|------|----------|
| S1 | Binary-checkable acceptance criteria | Every requirement has acceptance criteria that are binary-checkable (see the definition above). Prose criteria like "confirm the feature works correctly" do not pass even if they avoid subjective language. |
| S2 | Edge cases identified and handled | Edge Cases section covers failure modes, unexpected inputs, boundary conditions, and concurrent scenarios relevant to the feature |
| S3 | MoSCoW classification justified | Must-have vs should-have vs won't-do distinctions are explicit, and the classification reflects actual priority rather than "everything is must-have" |
| S4 | Non-requirements are explicit boundaries | Non-Requirements section defines concrete scope boundaries, not vague statements like "not in scope for now" |
| S5 | Technical constraints grounded | Technical Constraints section references specific codebase patterns, ADRs, or architectural decisions — not generic best practices |
| S6 | Behavioral changes documented | If the feature modifies, removes, or extends existing system behavior (including new additions to an existing domain), a `## Changes to Existing Behavior` section is present with specific MODIFIED/REMOVED/ADDED entries. Omission is acceptable only for pure-greenfield work in a new domain with no existing behavior to reference. |
| S7 | Spec phases section present | Spec contains `## Phases` section with ≥1 phase; each requirement carries a `**Phase**` tag matching one of the declared phases. Skip on `criticality=low AND tier=simple` per the existing skip rule. |

### Post-Plan Checklist

Evaluate against `cortex/lifecycle/{feature}/plan.md`:

| # | Item | Criteria |
|---|------|----------|
| P1 | Task sizing within bounds | Each task targets 5-15 minutes and 1-5 files; tasks outside this range are flagged |
| P2 | Dependency graph complete | Every task has a `**Depends on**` field; no missing edges where one task's output is another's input |
| P3 | Structural context sufficient | Each task's Context field provides enough information (file paths, function signatures, pattern references) for a fresh subagent to execute without reading unrelated files |
| P4 | Binary-checkable verification steps | Each task's Verification field is binary-checkable (see the definition above). Prose-only Verification fields like "verify it works" or "confirm the section was added" do not pass. |
| P5 | Code budget respected | Plan contains prose and structural context only — no function bodies, import statements, or copy-paste-ready code |
| P6 | Files/Verification consistency | Every file implied by Verification is listed in Files; no verification step requires modifying unlisted files |
| P7 | No self-sealing verification | For each task, cross-reference the Verification field against the Files list: does Verification reference an artifact that the same task creates? If yes, apply the operational test: if the task's stated purpose is to create that artifact (it is the primary deliverable), the self-check is benign. If the task's purpose is to verify an external condition and the artifact is a side-channel for recording that verification, the self-check is harmful — flag it as self-sealing. |
| P8 | Architectural Pattern field present and in taxonomy | Structural check only (field presence + closed-set membership): the plan contains a `**Architectural Pattern**` field whose value is one of the five categories: event-driven, pipeline, layered, shared-state, plug-in. Gated on `criticality = critical` (when §1b ran); explicitly N/A for non-critical plans. Semantic fit is not checked here — that domain belongs to the synthesizer. |
| P9 | Plan outline section present | Plan contains `## Outline` section. For `complexity=complex` plans, ≥2 phases required; for `complexity=simple` plans, ≥1 phase acceptable. Each phase names its task IDs in the heading; each phase has `**Goal**` and `**Checkpoint**` fields. |
| P10 | Acceptance section present on complex plans | For `complexity=complex` plans, plan contains `## Acceptance` section with whole-feature acceptance criterion. Skip on `complexity=simple` plans — last-phase Checkpoint is the contract there. |
