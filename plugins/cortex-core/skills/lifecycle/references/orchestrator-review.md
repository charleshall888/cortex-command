# Orchestrator Phase Review

Quality gate between phase-artifact write and user presentation: nothing reaches the user until the artifact passes the phase checklist or hits the cycle cap.

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

Max **2 review cycles per phase** (the counter resets each phase; don't start cycle 3). At the cap with an issue persisting, stop and escalate: present what was checked, what was tried per cycle, and what remains unresolved. The user then decides — do not continue reviewing.

## Checklists

**Binary-checkable** (S1, P4): one of (a) a runnable command with observable output and pass/fail (exit 0, grep count ≥ N); (b) an observable state naming the file path, the string/pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

### Post-Specify Checklist (`spec.md`)

| # | Item | Criteria |
|---|------|----------|
| S1 | Binary-checkable acceptance criteria | All binary-checkable (above); prose like "confirm it works" fails. |
| S2 | Edge cases handled | Edge Cases covers failure modes, unexpected inputs, boundaries, and concurrency relevant to the feature. |
| S3 | MoSCoW justified | Must/should/won't reflect real priority, not "everything is must-have". |
| S4 | Non-requirements are concrete boundaries | Names concrete scope boundaries, not vague "not in scope for now". |
| S5 | Constraints grounded | Cite specific codebase patterns, ADRs, or architectural decisions — not generic best practices. |
| S6 | Behavioral changes documented | Modifying/removing/extending existing behavior gets a `## Changes to Existing Behavior` section (MODIFIED/REMOVED/ADDED); omit only for pure-greenfield work. |
| S7 | Spec phases present | `## Phases` with ≥1 phase; each requirement's `**Phase**` tag matches one. Skip on `criticality=low AND tier=simple`. |

### Post-Plan Checklist (`plan.md`)

| # | Item | Criteria |
|---|------|----------|
| P1 | Task sizing | Each task targets 5-15 min, 1-5 files; flag outliers. |
| P2 | Dependency graph complete | Every task has `**Depends on**`; no missing edge where one task's output feeds another. |
| P3 | Structural context sufficient | Each Context field lets a fresh subagent execute without reading unrelated files. |
| P4 | Binary-checkable verification | Binary-checkable (above); "verify it works" fails. |
| P5 | Code budget respected | Prose and structural context only — no function bodies, imports, or copy-paste-ready code. |
| P6 | Files/Verification consistency | Every file Verification implies is listed in Files. |
| P7 | No self-sealing verification | An artifact the task itself creates is benign only if it's the primary deliverable — harmful (flag) if it's a side-channel recording an external condition. |
| P8 | Architectural Pattern present + in taxonomy | `**Architectural Pattern**` valued in {event-driven, pipeline, layered, shared-state, plug-in}; gated on `criticality = critical` (when §1b ran), N/A otherwise. Semantic fit belongs to the synthesizer. |
| P9 | Outline present | `## Outline`; ≥2 phases for `complexity=complex`, ≥1 for `simple`. Each phase names its task IDs plus `**Goal**` and `**Checkpoint**`. |
| P10 | Acceptance on complex plans | `complexity=complex` plans have a `## Acceptance` whole-feature criterion. Skip on simple — the last-phase Checkpoint is the contract there. |
