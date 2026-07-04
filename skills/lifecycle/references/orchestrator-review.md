# Orchestrator Phase Review

Quality gate between phase-artifact write and user presentation: review the artifact against a phase checklist, dispatch fixes for flagged items, and surface it to the user only once it passes or the cycle cap is reached.

## Applicability

Read both fields with `cortex-lifecycle-state --feature {feature}` (JSON; defaults criticality `medium`, tier `simple` when a key is absent). If the output has `"corrupted": true`, follow the corrupted-state rule in `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` — treat the feature as requiring review.

**Skip** when criticality is `low` AND tier is `simple` — proceed directly to user presentation / the next phase, logging no orchestrator events. Run for all other combinations.

## Protocol

### 1. Execute Review

Select the checklist for the artifact — Post-Specify (`spec.md`) or Post-Plan (`plan.md`) — and rate every item **pass** or **flag**. Flag anything unsatisfied or materially weak; a flag requires a fix before user presentation. Run in the main conversation — the artifact is already in context, so don't dispatch a subagent.

### 2. Handle Verdict

**Pass** → show a one-line assessment (e.g. "Spec clean: 6 requirements with measurable criteria, edge cases covered, scope explicit"), then proceed.

**Flag** → cycle 3 or beyond goes to Escalation (step 4); otherwise Fix Dispatch (step 3).

### 3. Fix Dispatch

Per flagged issue, pick a fix mode:

- **Fresh subagent** (Task tool) — for thinking-quality rework needing no user input; fresh context avoids anchoring to the flawed artifact. Resolve its model, never hardcoding:
  ```bash
  model=$(cortex-resolve-model --role orchestrator-fix --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
  ```
  Pass `$model`; on nonzero exit, halt and escalate. Dispatch with the template at `${CLAUDE_SKILL_DIR}/references/fix-agent-prompt-template.md`.
- **Same conversation** — for rework needing user input (preference decides the answer): explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to step 1 with the same checklist. Read the fix-agent envelope but relay only the re-review verdict.

### 4. Escalation

Max **2 review cycles per phase** (the counter resets each phase; don't start cycle 3). At the cap with an issue persisting, stop and escalate: present what was checked (the flagged items), what was tried (fixes per cycle), and what remains unresolved. The user then decides — do not continue reviewing.

## Checklists

**Binary-checkable** (used by S1 and P4): satisfied in one of three forms — (a) a runnable command with observable output and an explicit pass/fail (exit 0, grep count ≥ N); (b) an observable state naming the file path, the string/pattern to find, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither (a) nor (b) applies.

### Post-Specify Checklist (`spec.md`)

| # | Item | Criteria |
|---|------|----------|
| S1 | Binary-checkable acceptance criteria | Every requirement's acceptance criteria are binary-checkable (above). Prose like "confirm it works" fails even without subjective language. |
| S2 | Edge cases handled | Edge Cases section covers failure modes, unexpected inputs, boundary conditions, and concurrent scenarios relevant to the feature. |
| S3 | MoSCoW justified | Must/should/won't distinctions are explicit and reflect real priority, not "everything is must-have". |
| S4 | Non-requirements are concrete boundaries | Non-Requirements section names concrete scope boundaries, not vague "not in scope for now". |
| S5 | Constraints grounded | Technical Constraints reference specific codebase patterns, ADRs, or architectural decisions — not generic best practices. |
| S6 | Behavioral changes documented | If the feature modifies/removes/extends existing behavior (including additions to an existing domain), a `## Changes to Existing Behavior` section lists specific MODIFIED/REMOVED/ADDED entries. Omission is acceptable only for pure-greenfield work in a new domain. |
| S7 | Spec phases present | `## Phases` section with ≥1 phase; each requirement carries a `**Phase**` tag matching a declared phase. Skip on `criticality=low AND tier=simple`. |

### Post-Plan Checklist (`plan.md`)

| # | Item | Criteria |
|---|------|----------|
| P1 | Task sizing | Each task targets 5-15 min and 1-5 files; flag outliers. |
| P2 | Dependency graph complete | Every task has `**Depends on**`; no missing edge where one task's output feeds another. |
| P3 | Structural context sufficient | Each Context field lets a fresh subagent execute without reading unrelated files. |
| P4 | Binary-checkable verification | Each Verification field is binary-checkable (above). "Verify it works" / "confirm the section was added" fail. |
| P5 | Code budget respected | Prose and structural context only — no function bodies, imports, or copy-paste-ready code. |
| P6 | Files/Verification consistency | Every file Verification implies is in Files; no verification requires modifying an unlisted file. |
| P7 | No self-sealing verification | When Verification references an artifact the same task creates: benign if that artifact is the task's primary deliverable; harmful (flag) if it's a side-channel recording an external condition. |
| P8 | Architectural Pattern present + in taxonomy | Structural check: an `**Architectural Pattern**` field valued in {event-driven, pipeline, layered, shared-state, plug-in}. Gated on `criticality = critical` (when §1b ran); N/A otherwise. Semantic fit belongs to the synthesizer. |
| P9 | Outline present | `## Outline` section; ≥2 phases for `complexity=complex`, ≥1 for `simple`. Each phase names its task IDs and has `**Goal**` and `**Checkpoint**`. |
| P10 | Acceptance on complex plans | `complexity=complex` plans have a `## Acceptance` section with a whole-feature criterion. Skip on simple — the last-phase Checkpoint is the contract there. |
