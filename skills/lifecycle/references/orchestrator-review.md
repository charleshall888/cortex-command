# Orchestrator Phase Review

Quality gate: nothing reaches the user until the artifact passes its checklist or hits the cycle cap.

## Applicability

Read both fields with `cortex-lifecycle-state --feature {feature}` (JSON; defaults criticality `medium`, tier `simple` when a key is absent). On `"corrupted": true`, follow the corrupted-state rule in `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` — treat the feature as requiring review.

**Skip** when criticality is `low` AND tier is `simple` — proceed directly to user presentation / the next phase, logging no orchestrator events. Run for all other combinations.

## Protocol

### 1. Execute Review

Rate every item in the phase checklist for the artifact — Post-Specify (`spec.md`) or Post-Plan (`plan.md`) — **pass** or **flag**. Flag anything unsatisfied or materially weak; a flag requires a fix before user presentation. Run in the main conversation (artifact already in context; no subagent).

### 2. Handle Verdict

**Pass** → show a one-line assessment (e.g. "Spec clean, criteria measurable"), then proceed.

**Flag** → cycle 3 or beyond goes to Escalation (step 4); otherwise Fix Dispatch (step 3).

### 3. Fix Dispatch

Per flagged issue, pick a fix mode:

- **Fresh subagent** (Task tool) — for rework needing no user input; avoids anchoring to the flawed artifact. Resolve its model, never hardcoding:
  ```bash
  model=$(cortex-resolve-model --role orchestrator-fix --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality --raw)")
  ```
  Pass `$model`; on nonzero exit, halt and escalate. Dispatch with the template at `${CLAUDE_SKILL_DIR}/references/fix-agent-prompt-template.md`.
- **Same conversation** — for rework needing user input (preference decides): explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to step 1 with the same checklist; relay only the re-review verdict from the fix-agent envelope.

### 4. Escalation

Max **2 review cycles per phase** (counter resets each phase; don't start cycle 3). At the cap with an issue persisting, stop and escalate: present what was checked, what was tried per cycle, and what's unresolved; the user decides, do not continue reviewing.

## Checklists

**Binary-checkable** (S1, P4): one of (a) a runnable command with observable output and pass/fail (exit 0, grep count ≥ N); (b) an observable state naming the file path, the string/pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.
