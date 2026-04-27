# Research: Tighten lifecycle spec template and plan.md verification requirements

## Epic Reference

Background research at `research/harness-design-long-running-apps/research.md` covers the broader harness design epic (evaluator agent analysis, context reset patterns, codebase audit). This ticket addresses one specific gap identified there: ticket 019 — tighter spec and plan verification templates. The epic research's DR-3 explicitly recommends starting with a stricter spec template before adding any agent-based gate.

---

## Codebase Analysis

### Files that will change

1. **`skills/lifecycle/references/specify.md`** — the spec phase protocol; defines the spec template sections and orchestrator-review checklist (S1–S5). The current template already has `## Non-Requirements` and per-requirement `[Acceptance criteria]` fields, but no required `## Acceptance Criteria` section distinct from Requirements, and no required `## Agent-Verifiable Success Conditions` section. S1 already requires "objectively evaluable" criteria, but the pass bar is loosely defined.

2. **`skills/lifecycle/references/plan.md`** — the plan phase protocol; defines the Verification Strategy section format and orchestrator-review checklist (P1–P6). P4 already requires "concrete steps to confirm success, not vague 'verify it works'" — but the pass bar allows prose descriptions that an overnight agent self-attests against. The template Verification Strategy asks "how to verify the complete feature works end-to-end" without requiring commands.

3. **`skills/lifecycle/references/orchestrator-review.md`** — the shared orchestrator review checklists for both spec and plan. S1 and P4 are the relevant items. Tightening their pass criteria is the most targeted change.

**Key finding from the adversarial review**: The spec template already has the right *structure* in most ways — Requirements with acceptance criteria slots, Non-Requirements for scope exclusions, S1 and P4 checklist gates. The problem is *pass bar quality*, not missing sections.

### What the current format actually requires

**Spec template (specify.md §3)**:
```
## Problem Statement
## Requirements
  [Requirement]: [Acceptance criteria]    ← criteria already exist inline
## Non-Requirements
  - [Explicit exclusions]                 ← out-of-scope already exists
## Edge Cases
## Technical Constraints
## Open Decisions
```
S1 checklist gate: "Every requirement has acceptance criteria that can be objectively evaluated as met or not met."

**Gap**: S1's pass bar allows "the feature correctly performs X" as meeting "objectively evaluable" — because it avoids subjective language without requiring a binary command-based check.

**Plan template (plan.md §3)**:
```
## Verification Strategy
[How to verify the complete feature works end-to-end — prose]

Each task has:
  - **Verification**: what to test and how to confirm success [prose]
```
P4 checklist gate: "Verification steps actionable — each task's Verification field describes concrete steps to confirm success, not vague 'verify it works'."

**Gap**: P4's pass bar allows "read the file and confirm the section exists" without requiring the agent to record actual command output.

### Integration points

- **`claude/pipeline/prompts/implement.md`**: The builder prompt asks the feature worker to "verify your implementation works as described in the Verification field" — but does not require recording command output. Tightening plan.md's Verification format without tightening implement.md's checkpoint only shifts where the gap lives.
- **parser.py**: State machine only — not a quality gate. Should not be changed as part of this ticket.
- **orchestrator-review.md**: The primary enforcement point. Already has S1 and P4. Both need tighter pass criteria.
- **Critical review integration** (complex tier): spec.md and plan.md go through critical-review at approval. Updated templates will produce better input to these agents.

### Orchestrator-review skip rule — largest actual enforcement gap

Low-criticality + simple-tier features skip orchestrator review entirely. This means S1 and P4 never fire for the class of features most likely to be dispatched overnight without scrutiny. Any fix targeting S1 and P4 has zero effect on features that skip review. **This gap is not addressed by this ticket** (changing the skip rule requires a separate design decision), but it should be documented as an open question.

---

## Web Research

### Key patterns from prior art

**Binary pass/fail acceptance criteria** (Addy Osmani, Kinde, QuantumBlack): The dominant pattern for agentic specs is `[command] → [expected observable output] → pass if X`. "The login is broken, fix it" is not binary. "`pytest tests/auth/ -v` exits 0 and includes `PASS src/auth.test.py`" is binary.

**Hard "Never" constraints for out-of-scope** (GSA-TTS, Addy Osmani): Effective out-of-scope sections use explicit forbidden-action format: "Do not modify [path]. Do not change [behavior]. If [condition] arises, stop and defer." Prose ("should not touch the auth layer") is reinterpretable; path exclusions are not.

**QuantumBlack two-layer gate**: Layer 1 — deterministic section-presence check (is the section there?). Layer 2 — agentic critic evaluating testability ("Are these criteria actually runnable?"). The agentic critic is the `/critical-review` analog already present in this system for complex-tier features.

**Self-report without ground truth** (overnight failure research): The dominant cause of overnight agent failures is agents claiming completion based on self-assessment rather than runnable check output. The implement.md checkpoint's self-attestation pattern is the root cause; plan.md's Verification field format is where the fix should be applied.

**GIVEN/WHEN/THEN format** (Gherkin, Kiro): Most widely-adopted format for human-readable + machine-parseable acceptance criteria. Can be used as the required format for S1-passing acceptance criteria.

### Limitations of the "runnable command" pattern

Non-deterministic verification is a real constraint in this codebase:
- Hook-triggered behaviors require live Claude Code sessions (cannot be tested with a bare command)
- File-content checks for negative behaviors (verify X was NOT written) can be expressed as `grep -c 'pattern' file` = 0
- Session-dependent outputs (morning report with live data) cannot be reproduced by command alone

The `[command] → [output] → pass/fail` pattern should be required *where applicable*; the template should include a legitimate exception path for interactive/session-dependent verification, with a required rationale.

---

## Requirements & Constraints

**Primary constraint** (requirements/project.md): "A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. The spec is the entire communication channel."

**Night handoff constraint**: The orchestrator cannot ask clarifying questions during overnight execution. Specs and plans must be self-contained. Subjective Verification fields force the feature worker to interpret intent — exactly the failure mode the overnight failure research identifies.

**Scope constraint** (from backlog item + epic research DR-3): This ticket covers template/guidance changes only — no evaluator agent, no runtime agent gate. The evaluator agent was considered (epic research DR-1) and deferred pending rubric definition. This ticket's scope is authoring-time structure improvements.

**Pipeline constraint**: implement.md's checkpoint is out of scope for this ticket. The checkpoint change (require command-output evidence rather than self-attestation) is a separate concern that would affect the implementation pipeline — it is flagged here as a gap but not addressed by template changes alone.

---

## Tradeoffs & Alternatives

### Alternative 1: Template-only (guidance approach)
Update specify.md and plan.md with clearer required section guidance. No enforcement.

**Verdict: Insufficient.** Agents under time pressure write prose that satisfies section schemas without providing runnable commands. The current Non-Requirements and acceptance criteria fields are already "required" in the template — they are still filled with prose. Adding more sections produces the same result.

### Alternative 2: Enforcement via orchestrator-review extension (S6, S7)
Add new checklist items for explicit acceptance criteria section and agent-verifiable success conditions.

**Verdict: Partially useful, but creates redundancy.** S1 already covers measurable acceptance criteria. Adding S6/S7 with the same intent creates two items that can fire on the same gap, diluting signal and consuming the 2-cycle cap without improving quality. The better path is tightening S1's pass bar, not adding redundant items.

### Alternative 3: Tighten S1 and P4's pass criteria (recommended primary change)
Change S1's pass criteria from "objectively evaluable" to "binary: expressible as a pass/fail check an agent can run or perform observationally." Change P4's pass criteria from "describes concrete steps" to "names a specific command or file/content check that produces an observable binary result, OR provides a rationale for why interactive/session-dependent verification is required."

**Verdict: Most targeted and least disruptive.** One change per gate, zero redundancy, directly addresses the pass-bar quality gap. Does not require new sections that will be filled with schema-satisfying prose.

### Alternative 4: Hybrid — tighten S1/P4 + update specify.md template phrasing to guide authors
Change the acceptance criteria description in specify.md to require binary-checkable format by default. Change plan.md's Verification Strategy description to require commands with expected outputs. This is additive to Alternative 3 — the template guidance sets author expectations; the checklist enforces them at review time.

**Verdict: Recommended.** Template phrasing guides authors at write time; S1/P4 enforce at review time. Two reinforcing layers, no redundancy.

---

## Adversarial Review

### Failure modes and edge cases

1. **New sections filled with schema-compliant prose**: Adding a required `## Agent-Verifiable Success Conditions` section does not prevent agents from writing "Run the test suite and confirm no failures" — which satisfies section presence but is identical to the current prose deferrals. Section headers solve nothing if the pass bar is unchanged.

2. **Out-of-scope / Non-Requirements redundancy**: `## Non-Requirements` already exists in the template and is enforced by S4. The proposal to add an explicit out-of-scope section largely duplicates an existing required section. The real gap is S4's pass bar, not the section's existence.

3. **S1/P4 duplication if S6/S7 added**: Two checklist items covering the same failure pattern create ambiguity. An agent can mark S1 "pass" and S6 "fail" for the same criteria, consuming a fix cycle without clarity. One tighter item outperforms two loose items.

4. **Orchestrator-review skip rule nullifies all checklist fixes**: Low+simple features skip orchestrator review. S1 and P4 — no matter how tight — never fire for these features. This is the largest enforcement gap and is not addressed by any of the proposed changes.

5. **Runnable-command format fails for interactive verification**: Hooks that trigger during Claude Code sessions, integration tests that require live process state, and negative-write checks cannot always be expressed as a single runnable command. Requiring runnable commands without an exception path will produce superficially compliant but semantically hollow verification steps for these cases.

6. **implement.md checkpoint is the downstream enforcement gap**: Even with a correct Verification field, the builder prompt allows self-attestation ("I verified it works"). Tightening the template closes the authoring gap; closing the execution gap requires implement.md to require command-output recording. This is a follow-on change worth tracking.

### Key assumptions that may not hold

- **"The template is missing required structure"**: The existing template already has `[Acceptance criteria]` slots and `## Non-Requirements`. The gap is pass-bar quality, not structural absence.
- **"Adding sections produces runnable criteria"**: Agents fill sections with schema-satisfying prose under time pressure. The format of the content (binary-checkable) is what needs to change, not section existence.
- **"Orchestrator-review is a universal gate"**: It is not. Low+simple features bypass it. Any enforcement strategy that relies solely on orchestrator-review has a silent bypass path.

---

## Open Questions

- **S1/P4 pass bar definition**: Deferred — will be resolved in Spec by defining the exact pass criteria wording and examples during the structured requirements interview. The spec must define "binary-checkable" with examples (exit code, file existence, grep count, test pass/fail) and the legitimate exception path.
- **Exception path for non-deterministic verification**: Deferred — will be resolved in Spec. Must determine whether the author must specify why a command-based check is not possible, or just acknowledge the limitation with a rationale note.
- **implement.md checkpoint fix**: Should this be tracked as a follow-on ticket, or addressed in scope here? (Recommendation: separate ticket — it affects the implementation pipeline and warrants its own spec.)
- **Skip rule for low+simple features**: The orchestrator-review skip rule creates an enforcement gap for the feature class most likely to go overnight without scrutiny. Should the skip rule be narrowed? (Recommendation: separate backlog item — out of scope for this ticket.)
- **Backward compatibility**: Should existing specs and plans be updated to the new format? (Recommendation: no — the backlog item explicitly says "going forward." The new format applies at authoring time; existing artifacts are not retroactively invalid.)
