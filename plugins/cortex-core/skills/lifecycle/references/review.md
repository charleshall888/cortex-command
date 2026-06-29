# Review Phase

Two-stage review: spec compliance first, then code quality. Complex tier only. The reviewer must NOT modify any files.

## Protocol

### 1. Gather Review Inputs

- Read `cortex/lifecycle/{feature}/spec.md` for requirements
- Identify files changed during implementation by reading the git log for commits since the lifecycle started, or by comparing plan.md's file lists
- Read `cortex/lifecycle/{feature}/plan.md` for the verification strategy
- Load requirements docs following the shared tag-based loading protocol (`load-requirements.md`): run `cortex-load-requirements --feature {feature}`, read every listed non-skipped path, and record the printed path list for injection into the reviewer prompt. When the verb emits its no-match fallback note (no area docs matched), the drift check covers project.md only.

### 2. Launch Review Sub-Task

Dispatch a focused review sub-task with read-only instructions using the reviewer prompt below.

**Model**: `sonnet` for low/medium criticality, `opus` for high/critical

### Reviewer Prompt Template

Before dispatching, substitute `{spec_path}` with the absolute path to the spec file.

```
You are reviewing the {feature} implementation against its specification.

## Specification
Read `{spec_path}` before beginning the review.

## Project Requirements
{the path list cortex-load-requirements printed in §1, each path on its own line; if the verb emitted its no-match fallback note, relay that note instead}

## Changed Files
{list of files modified during implementation}

## Instructions

### Stage 1: Spec Compliance
For each requirement in the specification, verify the implementation matches:
- Read the relevant source files
- Check that acceptance criteria are met
- Rate each requirement: PASS / FAIL / PARTIAL

If any requirement is FAIL, skip Stage 2 and write the verdict.

### Stage 2: Code Quality
Only run this stage if all requirements PASS or PARTIAL (no FAIL):
- Naming conventions: consistent with project patterns?
- Error handling: appropriate for the context?
- Test coverage: verification steps from the plan executed?
- Pattern consistency: follows existing project conventions?

### Requirements Drift
Using the project requirements provided above, compare the implementation against stated requirements.
Note: requirements drift does NOT influence the verdict. This is an observation only.
- If the implementation matches all stated requirements and introduces no new behavior not reflected in them: state = none
- If the implementation introduces behavior not captured in the requirements docs, or changes behavior in a way requirements don't reflect: state = detected; list each drifted item as a bullet; name the requirements file that needs updating

### Write Review
Write your review to cortex/lifecycle/{feature}/review.md using the format below.

The Verdict section is a JSON object with exactly these fields:
- "verdict": one of "APPROVED", "CHANGES_REQUESTED", or "REJECTED"
- "cycle": the review cycle number (integer)
- "issues": array of issue strings (empty array if none)

Use exactly these field names and values — not "overall"/"result"/"status", and not "PASS"/"FAIL"/"APPROVED_WITH_NOTES" (those are Stage 1 rating values, not verdicts).

Your review.md includes a ## Requirements Drift section using exactly this format:
## Requirements Drift
**State**: none | detected
**Findings**:
- (one bullet per drifted item, or "None" if state is none)
**Update needed**: (path to requirements file that needs updating, or "None")
The requirements_drift value in the verdict JSON matches: "none" when State is none, "detected" when State is detected.

When drift IS detected, also include a ## Suggested Requirements Update section immediately after Requirements Drift. This section provides the exact content the orchestrator will append to the named requirements file:
## Suggested Requirements Update
**File**: (path to the requirements file to update, e.g. cortex/requirements/project.md)
**Section**: (existing section heading where the content belongs, e.g. "## Quality Attributes")
**Content**:
```
(exact markdown content to append — a single bullet point, constraint, or paragraph that captures the drifted concern)
```
Write the content as it should appear in the requirements file — not as a description of what to add. Keep it concise (1-3 lines). If drift spans multiple requirements files, include one Suggested Requirements Update section per file.

When drift is NOT detected, omit the Suggested Requirements Update section entirely.

Do NOT modify any source files. This is a read-only review.
```

### 3. Review Artifact Format

```markdown
# Review: {feature}

## Stage 1: Spec Compliance

### Requirement 1: {requirement text}
- **Expected**: {what the spec says}
- **Actual**: {what the implementation does}
- **Verdict**: PASS / FAIL / PARTIAL
- **Notes**: {details if FAIL or PARTIAL}

...

<!-- Requirements Drift and Suggested Requirements Update sections use the exact formats defined in §2 inside the dispatched reviewer prompt. -->

## Stage 2: Code Quality
<!-- Only present if Stage 1 has no FAIL verdicts -->

- **Naming conventions**: {assessment}
- **Error handling**: {assessment}
- **Test coverage**: {assessment}
- **Pattern consistency**: {assessment}

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
```

### 4. Process Verdict

After the reviewer sub-task completes and `cortex/lifecycle/{feature}/review.md` is confirmed on disk:

Before proceeding, validate that review.md contains a `## Requirements Drift` section. If the section is absent (e.g., the reviewer ran out of context), re-dispatch the reviewer with this targeted instruction: "review.md is missing the ## Requirements Drift section. Read the existing review.md, then append the ## Requirements Drift section in the correct format. Do not modify any other section." If the section remains absent after one re-dispatch, escalate to the user.

Register `"review"` in the `artifacts` array of `cortex/lifecycle/{feature}/index.md` per the canonical artifact-registration procedure in backlog-writeback.md (loaded at lifecycle Step 2).

| Verdict | Cycle | Action |
|---------|-------|--------|
| APPROVED | any | Proceed to Complete |
| CHANGES_REQUESTED | 1 | Re-enter Implement for flagged tasks with reviewer feedback |
| CHANGES_REQUESTED | 2 | Escalate to user — present the reviewer's analysis and ask for direction |
| REJECTED | any | Escalate to user immediately — recommend revisiting the plan or spec |

The cycle counter prevents infinite rework loops. After cycle 2, always escalate to the user regardless of verdict.

After reading the verdict from the review artifact (state detection parses the exact `"verdict"` field name and its exact values), append a `review_verdict` event to `cortex/lifecycle/{feature}/events.log`:

```bash
cortex-lifecycle-event log --event review_verdict --feature <name> --set verdict=<APPROVED|CHANGES_REQUESTED|REJECTED> --set-json cycle=<N> --set requirements_drift=<none|detected>
```

Where `requirements_drift` is read from the `"requirements_drift"` field in the verdict JSON block.

### 4a. Auto-Apply Requirements Drift

After logging the `review_verdict` event, check whether `requirements_drift` is `"detected"`. If so:

1. **Read the suggested update**: Parse the `## Suggested Requirements Update` section from `cortex/lifecycle/{feature}/review.md`. Extract `File`, `Section`, and `Content` fields.

2. **If the section is missing or unparseable, enforce the protocol via re-dispatch**: The reviewer is expected to emit a `## Suggested Requirements Update` section whenever `requirements_drift: detected`. When the section is absent or unparseable on the first pass, re-dispatch the reviewer with a targeted instruction:

   > "review.md flags `requirements_drift: detected` but is missing the `## Suggested Requirements Update` section. Read the existing review.md, then append the section in the format documented in §2 (File / Section / Content). Do not modify any other section."

   The re-dispatch follows a max-retry cap of `2` (initial dispatch + 2 retries = 3 passes); exit the loop as soon as a pass yields a parseable section and continue with step 3.

   If all 3 passes complete without producing a parseable `## Suggested Requirements Update` section, the retry loop is exhausted. Do **not** block the verdict processing. Instead, log a `drift_protocol_breach` event to `cortex/lifecycle/{feature}/events.log` with `state=detected` and `suggestion=missing`, then fall through to step 5 (skip auto-apply). The breach event surfaces in the morning report so the gap is visible rather than silent.

   Event format:

   ```bash
   cortex-lifecycle-event log --event drift_protocol_breach --feature <name> --set state=detected --set suggestion=missing --set-json retries=2
   ```

3. **Apply the update**: Append the Content at the end of the named Section in the target file.

4. **Report to the user**: Display what was changed:
   ```
   Requirements updated: {file} → {section}
     Added: {first line of content}
   ```

5. **Skip auto-apply after exhausted retries**: log a brief notice — "Requirements drift detected but no suggested update was provided after re-dispatch; breach logged for morning report" — and continue to §5 Transition without blocking.

### 5. Transition

Proceed automatically — do not ask the user for confirmation when the verdict is APPROVED or CHANGES_REQUESTED cycle 1. Announce the transition briefly and continue.

- APPROVED → log the transition and proceed to Complete automatically:
  ```bash
  cortex-lifecycle-event log --event phase_transition --feature <name> --set from=review --set to=complete
  ```
- CHANGES_REQUESTED cycle 1 → log the transition and return to Implement automatically:
  ```bash
  cortex-lifecycle-event log --event phase_transition --feature <name> --set from=review --set to=implement-rework
  ```
- Otherwise → log the escalation, then present findings to user and await direction (user input required — this is a genuine concern):
  ```bash
  cortex-lifecycle-event log --event phase_transition --feature <name> --set from=review --set to=escalated
  ```

## Constraints

- Flag minor code quality issues as PARTIAL with notes — minor issues compound.
- If uncertain about requirements drift, log `detected` with a note — false positives auto-apply a small update; false negatives silently hide drift.
