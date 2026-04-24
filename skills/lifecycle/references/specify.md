# Specify Phase

Structured interview to surface hidden requirements, edge cases, and priorities before planning. Runs for both simple and complex tiers — adapts depth to what's already clear from research.

## Protocol

### 1. Load Context

Read `lifecycle/{feature}/research.md` for codebase analysis and open questions. If `lifecycle.config.md` exists at the project root, read it for project-specific constraints. If `requirements/project.md` exists, read it for project-level requirements. Scan `requirements/` for area docs relevant to this feature and read those too. Use requirements to avoid re-asking settled questions — focus the interview on feature-specific details that requirements don't already cover.

### 2. Structured Interview

Before asking questions, review the research artifact and feature description. For each interview area below, assess whether the answer is already evident:

- **Already clear**: State what you found and move on — don't ask the user to confirm the obvious
- **Partially covered**: Ask only about the gaps, referencing what's already known
- **Unclear**: Run the full interview for that area

For simple-tier features, many areas will often be self-evident — the interview may reduce to just a few targeted questions.

Ask about these areas in sequence, adapting based on answers:

**Problem statement**: What problem does this feature solve? Who benefits? What happens if it is not built?

**Requirements**: For each requirement, ask for acceptance criteria — how will you know it works? Probe for:
- Must-have vs nice-to-have distinction
- Measurable success criteria
- User-facing vs internal requirements

**Non-requirements**: What does this feature intentionally NOT do? Explicit exclusions prevent scope creep during implementation. Push back on vague boundaries.

**Edge cases**: What happens when inputs are unexpected, systems are unavailable, or users behave unexpectedly? Challenge optimistic assumptions.

**Technical constraints**: Surface constraints from the research findings. Ask about performance requirements, compatibility needs, and integration boundaries.

Ask probing questions — challenge assumptions, probe unstated expectations, identify missing requirements. Do not just confirm what is already written. Use the AskUserQuestion tool to present questions interactively — not as plain markdown text. Continue until all ambiguities are resolved.

### 2a. Research Confidence Check

**Missing research.md guard**: Before evaluating any signals, check whether `lifecycle/{feature}/research.md` exists.

- **If it does NOT exist**: Announce to the user that `research.md` is missing and Research must run before Specify can proceed. Then immediately trigger the cycle 1 loop-back: log a `confidence_check` event with `"signals": ["research.md missing"]` and `"action": "loop_back"`, and transition to Research bypassing /refine's Sufficiency Check (same override described below). Do not evaluate C1/C2/C3.
- **If it DOES exist**: proceed to the C1/C2/C3 signal evaluation below.

After the interview concludes, evaluate whether the research from `research.md` is still sufficient to write accurate acceptance criteria. Assess these three signals — each is a pass/fail gate:

**C1 (Approach invalidated)**: An interview answer materially invalidated the scope or approach described in `research.md` — the researched approach must be abandoned, not merely adjusted. **Calibration**: Only trigger when the spec can no longer use the researched approach at all. If the approach is still viable with modifications, C1 does not fire.

**C2 (Investigation unknowns)**: The interview surfaced unknowns that require reading codebase files not already covered in `research.md` in order to resolve them. **Calibration**: Only trigger when the unknowns require new file-level investigation. If they can be answered from what is already in `research.md` or from the user's input alone, C2 does not fire.

**C3 (Uncovered dependencies)**: Technical constraints or dependencies raised during the interview rely on codebase patterns not covered in `research.md`, and writing accurate acceptance criteria is impossible without them. **Calibration**: Only trigger when the missing patterns are required for accurate requirements — not merely helpful.

> **Note**: This checklist does NOT re-evaluate the four clarify.md §6 staleness signals (scope mismatch, files missing, empty/generic analysis, requirements drift). Those were evaluated at Research phase entry and are not re-checked here.

**If all three signals pass**: proceed to §3. No event is logged. Do not emit any acknowledgment to the user.

**Cycle count**: `current_cycle = (count of existing confidence_check events in lifecycle/{feature}/events.log) + 1`. On the first pass with zero existing confidence_check events, current_cycle = 1.

**If any signal is flagged AND current_cycle = 1**:

1. Present the signals flagged in §2a's Research Confidence Check as a bulleted list — one bullet per flagged signal, ≤15 words per bullet, no prose expansion outside the bullets. Then state that Research must be re-run. Example: a bullet of acceptable terseness might read:
   - `C2: spec needs read of hooks/commit-msg.sh — not in research.md`
2. Append a `confidence_check` event to `lifecycle/{feature}/events.log`:
   ```
   {"ts": "<ISO 8601>", "event": "confidence_check", "feature": "<name>", "cycle": 1, "signals": ["<C1|C2|C3 with description>", ...], "action": "loop_back"}
   ```
3. Transition back to Research — **bypassing /refine's Sufficiency Check**. Because Specify runs inside a /cortex:refine invocation (Step 5), the normal loop-back to Research would re-enter /cortex:refine Step 4, which applies a Sufficiency Check that may declare the existing `research.md` sufficient and skip back to Spec. This must not happen. Explicitly override: treat the existing `research.md` as invalidated and re-run Research from scratch regardless of Sufficiency Check criteria. This follows the same override pattern used in lifecycle SKILL.md's Discovery Bootstrap edge case.

**If any signal is flagged AND current_cycle ≥ 2**:

Present the signals flagged in §2a's Research Confidence Check as a bulleted list — one bullet per flagged signal, ≤15 words per bullet, no prose expansion outside the bullets. Then ask (via AskUserQuestion) whether to loop back to Research or proceed to §3 anyway.

- If the user chooses to loop back: repeat the cycle 1 loop-back procedure above (announce, log event with the current cycle number and `"action": "loop_back"`, re-run Research bypassing Sufficiency Check).
- If the user chooses to proceed: append a `confidence_check` event with `"action": "declined"` and continue to §3.
  ```
  {"ts": "<ISO 8601>", "event": "confidence_check", "feature": "<name>", "cycle": <n>, "signals": ["<C1|C2|C3 with description>", ...], "action": "declined"}
  ```

### 2b. Pre-Write Checks

Before drafting §3, run the checks below. All checks are silent on pass: if every check passes, proceed to §3 with no output. On failure, surface only the specific failing claim or unresolved item as a single terse bullet (≤15 words) — no preamble, no restatement of the check, no pass-side narration.

**Verification check**: For any claim the spec will make about code behavior, verify it against actual code before writing it. Perform all four sub-checks; on failure, surface only the specific failing claim. Common failure modes:
- **Git command syntax**: If the spec references a `git diff` command, confirm whether two-dot (`A..B`) or three-dot (`A...B`) semantics are correct for the intended comparison. These are not interchangeable — two-dot produces an empty diff when one ref is an ancestor of the other.
- **Function behavior**: Before asserting what a function does, accepts, or returns — read it. Do not infer from its name or call sites alone.
- **File paths**: Before referencing a file path in a requirement, verify the file exists at that path.
- **State ownership**: Before asserting that a function writes or persists a value, confirm which function owns that write and when it runs. A function that increments a counter in memory may have its write silently overwritten if another function owns the writeback at end-of-batch.

**Research cross-check**: Re-read `lifecycle/{feature}/research.md` in full. For each explicit behavioral requirement, constraint, guard, or edge case documented in research — verify it appears in the spec's Requirements, Edge Cases, or Technical Constraints. A requirement present in research but absent from the spec is a silent omission, not a scope decision. On failure, surface only the specific omitted item. If an omission is intentional, note it explicitly in Non-Requirements or Open Decisions.

**Open Decision Resolution**: Before adding any item to `## Open Decisions`, attempt to resolve it using this order:

1. Check `research.md` — if the answer is evident from research findings, incorporate it into Requirements, Technical Constraints, or the spec body instead. Do not list it as open.
2. Ask the user directly — the user is present during spec; implementation may run overnight without them.
3. Defer to `## Open Decisions` only if the decision requires implementation-level context that cannot be obtained without writing or reading the actual code (e.g., choosing between two patterns that are only distinguishable once in the codebase).

Any item that IS deferred must include a one-sentence reason why it cannot be resolved at spec time. No output on pass; on failure, surface only the specific unresolved item as a terse bullet.

### 3. Write Specification Artifact

Compile answers into `lifecycle/{feature}/spec.md`.

**If §2a ended with the user declining to loop back** (i.e., a `confidence_check` event with `"action": "declined"` is present in `lifecycle/{feature}/events.log`): prepend the following callout to the spec, before `## Problem Statement`, substituting one bullet per flagged signal from that event:

```markdown
> **Advisory — research gaps noted**: The confidence check identified gaps during the interview that were not resolved before proceeding. The requirements below may be incomplete or inaccurate in these areas. This warning is intentional; downstream phases should proceed normally.
> - [signal description for each flagged signal]
```

Omit this callout entirely when §2a passed cleanly or no loop-back occurred.

```markdown
# Specification: {feature}

## Problem Statement
[One paragraph: what this solves, who benefits, why it matters]

## Requirements
1. [Requirement]: [Acceptance criteria — binary-checkable: (a) command + expected output + pass/fail (e.g., "`just test` exits 0, pass if exit code = 0"), (b) observable state naming specific file and pattern (e.g., "`grep -c 'keyword' path/file` = 1"), or (c) "Interactive/session-dependent: [rationale]" if a command check is not possible]
2. [Requirement]: [Acceptance criteria — same format as above]
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
```

### 3a. Orchestrator Review

Before presenting the artifact to the user, read and follow `references/orchestrator-review.md` for the `specify` phase. The orchestrator review must pass before proceeding to user approval.

### 3b. Critical Review

After orchestrator review passes, check `lifecycle/{feature}/events.log` for the most recent `lifecycle_start` or `criticality_override` event. Extract `tier`.

**Run** when `tier = complex`: invoke the `critical-review` skill with the spec artifact. Present the synthesis to the user before spec approval.

**Skip** when `tier = simple`. Proceed directly to user approval.

### 4. User Approval

Present the specification summary and use the AskUserQuestion tool to collect approval — not as plain markdown text. The summary must include these approval surface fields:

- **Produced** (one-line summary of the artifact)
- **Value** (what problem this solves and why it's worth building now — flag weak value cases explicitly)
- **Trade-offs** (alternatives considered and rationale for chosen approach)

The user must approve before proceeding to Plan. If the user requests changes, revise the spec and re-present.

### 5. Transition

Append a `phase_transition` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "specify", "to": "plan"}
```

If `commit-artifacts` is enabled in project config (default), stage `lifecycle/{feature}/` and commit using `/cortex:commit`.

After approval, proceed to Plan.

## Hard Gate

Do NOT write any implementation code during this phase. The goal is to define WHAT to build, not HOW to build it.

| Thought | Reality |
|---------|---------|
| "The requirements are obvious from the research" | Obvious requirements still have hidden edge cases. The interview surfaces what you assume you already know. |
| "I already know what to build" | Knowing what to build is not the same as having agreed requirements. The spec is the contract. |
| "This is too simple for a spec" | Even simple features have assumptions worth validating. The interview adapts — if everything is clear, it finishes quickly. |
| "I'll add this to Open Decisions since I'm not sure" | Not sure = ask the user. The user is present during spec; implementation may run overnight without them. Defer only when implementation-level context is genuinely required and unavailable at spec time. |
