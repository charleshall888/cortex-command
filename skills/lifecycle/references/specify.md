# Specify Phase

Structured interview to surface hidden requirements, edge cases, and priorities before planning. Runs for both simple and complex tiers — adapts depth to what's already clear from research.

## Protocol

### 1. Load Context

Read `cortex/lifecycle/{feature}/research.md` for codebase analysis and open questions. If `cortex/lifecycle.config.md` exists at the project root, read it for project-specific constraints. Load requirements using the shared tag-based loading protocol — read `load-requirements.md` at the absolute path the lifecycle body resolved and propagated (see lifecycle SKILL.md "Reference-path propagation") and follow it. If no `cortex/requirements/` directory or files exist, note this and proceed. Use requirements to avoid re-asking settled questions — focus the interview on feature-specific details that requirements don't already cover.

If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview.

### 2. Structured Interview

Before asking questions, review the research artifact and feature description. For each interview area below, assess whether the answer is already evident:

- **Already clear**: State what you found and move on — don't ask the user to confirm the obvious
- **Partially covered**: Ask only about the gaps, referencing what's already known
- **Unclear**: Run the full interview for that area

Ask about these areas in sequence, adapting based on answers:

**Problem statement**: What problem does this feature solve? Who benefits? What happens if it is not built?

**Requirements**: For each requirement, ask for acceptance criteria — how will you know it works? Probe for:
- Must-have vs nice-to-have distinction
- Measurable success criteria
- User-facing vs internal requirements

**ADR posture (in-the-moment)**: When negotiating a requirement decision, if it meets the three-criteria gate from `cortex/adr/README.md` (Hard to reverse + Surprising without context + Real trade-off), draft an ADR proposal in the spec's `## Proposed ADR` section in the same turn rather than deferring.

**Non-requirements**: What does this feature intentionally NOT do? Explicit exclusions prevent scope creep during implementation. Push back on vague boundaries.

**Edge cases**: What happens when inputs are unexpected, systems are unavailable, or users behave unexpectedly? Challenge optimistic assumptions.

**Technical constraints**: Surface constraints from the research findings. Ask about performance requirements, compatibility needs, and integration boundaries.

Probe — do not just confirm what is already written. Use the AskUserQuestion tool to present questions interactively — not as plain markdown text. Continue until all ambiguities are resolved.

**Interview posture (interactive default)**: Assume the work is verified interactively — the user is present in-session to confirm acceptance criteria. Do not interrogate how criteria would be verified autonomously or overnight; user-present, in-session verification is a first-class, legitimate outcome. This governs interview *posture* only — the §3 acceptance-criteria format still prefers testable criteria and does not relax binary-checkability.

**Cadence**: Ask one question at a time, waiting for the user's response before posing the next. Do not batch questions into a single turn. This cadence is the canonical rule at `skills/interview/references/loop.md`.

**File-path citation**: When recommending an acceptance criterion derived from code, name the file path that grounds it so the user can flag a wrong-place-to-implement before any code is written. For intent-only criteria with no codebase grounding, omit the citation — do not fabricate.

**Verification posture**: When citing a file path or a function-behavior claim during the interview, verify it against the actual code before accepting the user's confirmation. (§2b's end-of-interview check still runs.)

**Edge-case invention**: When a requirement's acceptance criteria look under-specified, invent one concrete edge-case scenario that would stress the criterion and surface it to the user before locking. Apply judgmentally — skip when the criteria are already tight.

### 2a. Research Confidence Check

**Missing research.md guard**: Before evaluating any signals, check whether `cortex/lifecycle/{feature}/research.md` exists.

- **If it does NOT exist**: Announce to the user that `research.md` is missing and Research must run before Specify can proceed. Then immediately trigger the cycle 1 loop-back: log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, and transition to Research bypassing /refine's Sufficiency Check (same override described below). Do not evaluate C1/C2/C3.
- **If it DOES exist**: proceed to the C1/C2/C3 signal evaluation below.

After the interview concludes, evaluate whether the research from `research.md` is still sufficient to write accurate acceptance criteria. Assess these three signals — each is a pass/fail gate:

**C1 (Approach invalidated)**: An interview answer materially invalidated the scope or approach described in `research.md` — the researched approach must be abandoned, not merely adjusted. **Calibration**: Only trigger when the spec can no longer use the researched approach at all. If the approach is still viable with modifications, C1 does not fire.

**C2 (Investigation unknowns)**: The interview surfaced unknowns that require reading codebase files not already covered in `research.md` in order to resolve them. **Calibration**: Only trigger when the unknowns require new file-level investigation. If they can be answered from what is already in `research.md` or from the user's input alone, C2 does not fire.

**C3 (Uncovered dependencies)**: Technical constraints or dependencies raised during the interview rely on codebase patterns not covered in `research.md`, and writing accurate acceptance criteria is impossible without them. **Calibration**: Only trigger when the missing patterns are required for accurate requirements — not merely helpful.

> **Note**: Do not re-evaluate clarify.md §6 staleness signals — those were checked at Research entry.

**If all three signals pass**: proceed to §3. No event is logged. Do not emit any acknowledgment to the user.

**Cycle count**: `current_cycle = (count of existing confidence_check events in cortex/lifecycle/{feature}/events.log) + 1`. On the first pass with zero existing confidence_check events, current_cycle = 1.

**If any signal is flagged AND current_cycle = 1**:

1. Present the signals flagged in §2a's Research Confidence Check as a bulleted list — one bullet per flagged signal, ≤15 words per bullet, no prose expansion outside the bullets. Then state that Research must be re-run.
2. Transition back to Research — **bypassing /refine's Sufficiency Check**: treat the existing `research.md` as invalidated and re-run Research from scratch (otherwise /refine Step 4 may declare it sufficient and skip back to Spec).

**If any signal is flagged AND current_cycle ≥ 2**:

Present the flagged signals as in cycle 1, then ask (via AskUserQuestion) whether to loop back to Research or proceed to §3 anyway.

- If the user chooses to loop back: repeat the cycle 1 loop-back procedure above (announce, re-run Research bypassing Sufficiency Check).
- If the user chooses to proceed: continue to §3.

### 2b. Pre-Write Checks

Before drafting §3, run the checks below. All checks are silent on pass: if every check passes, proceed to §3 with no output. On failure, surface only the specific failing claim or unresolved item as a single terse bullet (≤15 words) — no preamble, no restatement of the check, no pass-side narration.

**Verification check**: For any claim the spec will make about code behavior, verify it against actual code before writing it. Perform all four sub-checks. Common failure modes:
- **Git command syntax**: If the spec references a `git diff` command, confirm whether two-dot (`A..B`) or three-dot (`A...B`) semantics are correct for the intended comparison.
- **Function behavior**: Before asserting what a function does, accepts, or returns — read it. Do not infer from its name or call sites alone.
- **File paths**: Before referencing a file path in a requirement, verify the file exists at that path.
- **State ownership**: Before asserting that a function writes or persists a value, confirm which function owns that write and when it runs — an in-memory increment can be silently overwritten by an end-of-batch writeback owner.

**Research cross-check**: Re-read `cortex/lifecycle/{feature}/research.md` in full. For each explicit behavioral requirement, constraint, guard, or edge case documented in research — verify it appears in the spec's Requirements, Edge Cases, or Technical Constraints. A requirement present in research but absent from the spec is a silent omission, not a scope decision. If an omission is intentional, note it explicitly in Non-Requirements or Open Decisions.

**Open Decision Resolution**: Before adding any item to `## Open Decisions`, attempt to resolve it using this order:

1. Check `research.md` — if the answer is evident from research findings, incorporate it into Requirements, Technical Constraints, or the spec body instead. Do not list it as open.
2. Ask the user directly — the user is present during spec; resolve open decisions now, because the implementer works from the spec and is not in a position to resolve them mid-implementation.
3. Defer to `## Open Decisions` only if the decision requires implementation-level context that cannot be obtained without writing or reading the actual code (e.g., choosing between two patterns that are only distinguishable once in the codebase).

Any item that IS deferred must include a one-sentence reason why it cannot be resolved at spec time.

### 3. Write Specification Artifact

Compile answers into `cortex/lifecycle/{feature}/spec.md`.

**If §2a ended with the user declining to loop back** (i.e., a `confidence_check` event with `"action": "declined"` is present in `cortex/lifecycle/{feature}/events.log`): prepend the following callout to the spec, before `## Problem Statement`, substituting one bullet per flagged signal from that event:

```markdown
> **Advisory — research gaps noted**: The confidence check identified gaps during the interview that were not resolved before proceeding. The requirements below may be incomplete or inaccurate in these areas. This warning is intentional; downstream phases should proceed normally.
> - [signal description for each flagged signal]
```

Omit this callout entirely when §2a passed cleanly or no loop-back occurred.

```markdown
# Specification: {feature}

## Problem Statement
[One paragraph: what this solves, who benefits, why it matters]

## Phases
<!-- Group requirements into phases. ≥1 phase for complexity=simple; ≥2 phases for complexity=complex. Each phase name below must match the **Phase** tag on its requirements in `## Requirements`. -->
- **Phase 1: <name>** — <one-line goal>
- **Phase 2: <name>** — <one-line goal>

## Requirements
1. [Requirement]: [Acceptance criteria — binary-checkable: (a) command + expected output + pass/fail (e.g., "`just test` exits 0, pass if exit code = 0"), (b) observable state naming specific file and pattern (e.g., "`grep -c 'keyword' path/file` = 1"), or (c) "Interactive/session-dependent: [rationale]" if a command check is not possible]. **Phase**: <name>
2. [Requirement]: [Acceptance criteria — same format as above]. **Phase**: <name>
...

## Non-Requirements
- [What this feature intentionally does NOT do]
- [Explicit scope boundary]

## Edge Cases
- [Edge case]: [Expected behavior]

## Changes to Existing Behavior
<!-- Include when this feature modifies, removes, or extends existing system behavior — including new additions that change the behavioral surface of a domain (e.g., a new skill changes available commands). Omit only for pure-greenfield work in a new domain with no existing behavior to reference. -->
- [MODIFIED: existing behavior] → [new behavior]
- [REMOVED: behavior being eliminated]
- [ADDED: new behavior extending an existing domain]

## Technical Constraints
- [Constraint from research or architecture]

## Open Decisions
- [Only when implementation-level context is required and unavailable at spec time — include a one-sentence reason why. Resolution at spec time is strongly preferred; ask the user if uncertain.]

## Proposed ADR
None considered.
<!-- For each ADR-shaped decision negotiated during the interview, replace the default body above with one sub-entry per proposal in the shape:

### Proposed ADR: <NNNN-slug>
[One-paragraph context, decision, and trade-off summary suitable for promotion into cortex/adr/<NNNN-slug>.md.]
-->
```

### 3a. Orchestrator Review

Before presenting the artifact to the user, read and follow the orchestrator-review protocol (use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest: the **orchestrator-review** target) for the `specify` phase. The orchestrator review must pass before proceeding to user approval.

### 3b. Critical Review

After orchestrator review passes, read the active tier and criticality (rules: criticality-matrix.md §Reading lifecycle state — use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest):

- `cortex-lifecycle-state --feature {feature} --field tier`
- `cortex-lifecycle-state --feature {feature} --field criticality`

Also resolve the active backlog backend once via `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0) before deciding to skip — the non-local seed-tier fail-safe below keys on it, and the gate-protocol reference is consulted only on the skip branch, so the backend read happens here at the inline decision rather than inside the gate ref.

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the spec artifact. Present the synthesis to the user before spec approval.

**Non-local seed-tier fail-safe**: when the resolved backend ≠ `cortex-backlog` AND the run condition above did not fire because `tier = simple` (the skip-silent seed) AND `cortex/lifecycle/{feature}/research.md` exists (the resume-to-spec signature that Clarify may have been bypassed and the seed left un-reconciled), the `simple` seed is not trustworthy — invoke the `critical-review` skill with the spec artifact and present the synthesis before spec approval, rather than skipping. The local `cortex-backlog` path skips this branch (its seed is re-sourced from backlog frontmatter on resume, so it is trustworthy).

Otherwise, read and follow the critical-review gate protocol (use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest: the **critical-review-gate** target) for the `specify` phase.

### 4. User Approval

Present the specification summary and use the AskUserQuestion tool to collect the operator's disposition. The summary must include these approval surface fields:

- **Produced** (one-line summary of the artifact)
- **Value** (what problem this solves and why it's worth building now — flag weak value cases explicitly)
- **Trade-offs** (alternatives considered and rationale for chosen approach)
- **Proposed ADRs** (comma-separated `<NNNN-slug>` list from the spec's `## Proposed ADR` section; value is `None` when that section's body is `None considered.`)

Enumerate the options on that call explicitly as: `Approve` | `Request changes` | `Cancel`. Route on the response:

- **Approve**: append a `spec_approved` event to `cortex/lifecycle/{feature}/events.log`, then append the `phase_transition` event from §5 below, then auto-advance to Plan. Proceed automatically — do not ask the user for confirmation again.
  ```
  {"ts": "<ISO 8601>", "event": "spec_approved", "feature": "<name>"}
  ```
- **Request changes**: collect the requested changes, revise the spec, and re-present the approval surface. Do not emit `spec_approved` on intermediate revision loops; only the final `Approve` selection emits the event.
- **Cancel**: append a `lifecycle_cancelled` event and halt. The user can resume by re-invoking `/cortex-core:lifecycle`.

### 5. Transition

On `Approve`, append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "specify", "to": "plan"}
```

## Hard Gate

Do NOT write any implementation code during this phase. The goal is to define WHAT to build, not HOW to build it.
