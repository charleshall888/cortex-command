# Review Phase

Two-stage review: spec compliance first, then code quality. Complex tier only. The reviewer must NOT modify any files.

## Protocol

### 1. Gather Review Inputs

- Read `lifecycle/{feature}/spec.md` for requirements
- Identify files changed during implementation by reading the git log for commits since the lifecycle started, or by comparing plan.md's file lists
- Read `lifecycle/{feature}/plan.md` for the verification strategy
- Load requirements docs using the structured tag-based protocol:
  1. Read `requirements/project.md` (always)
  2. Read `lifecycle/{feature}/index.md` and extract the `tags:` array from its YAML frontmatter
  3. Read the Conditional Loading section of `requirements/project.md`; for each tag word in the tags array, check case-insensitively whether any Conditional Loading phrase contains that word; collect the area doc paths for all matches
  4. If matching area docs are found, read them too. Record the full list of loaded requirements files (project.md + matched area docs) for injection into the reviewer prompt. If no tags match or no area docs are found, load project.md only and note: "no area docs matched for tags: {tags}; drift check covers project.md only"

### 2. Launch Review Sub-Task

Dispatch a focused review sub-task with read-only instructions using the reviewer prompt below.

**Model**: `sonnet` for low/medium criticality, `opus` for high/critical

### Reviewer Prompt Template

```
You are reviewing the {feature} implementation against its specification.

## Specification
{contents of lifecycle/{feature}/spec.md, or a summary with a path to read it}

## Project Requirements
{list of requirements docs loaded in §1, each on its own line with path and summary; if only project.md loaded, note 'only project.md loaded — no area docs matched tags'}

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
Write your review to lifecycle/{feature}/review.md using the format below.

The Verdict section is a JSON object with exactly these fields:
- "verdict": one of "APPROVED", "CHANGES_REQUESTED", or "REJECTED"
- "cycle": the review cycle number (integer)
- "issues": array of issue strings (empty array if none)

Alternative field names like "overall", "result", or "status" are not used.
Alternative values like "PASS", "FAIL", or "APPROVED_WITH_NOTES" are not used.

Your review.md includes a ## Requirements Drift section using exactly this format:
## Requirements Drift
**State**: none | detected
**Findings**:
- (one bullet per drifted item, or "None" if state is none)
**Update needed**: (path to requirements file that needs updating, or "None")
The requirements_drift value in the verdict JSON matches: "none" when State is none, "detected" when State is detected.

When drift IS detected, also include a ## Suggested Requirements Update section immediately after Requirements Drift. This section provides the exact content the orchestrator will append to the named requirements file:
## Suggested Requirements Update
**File**: (path to the requirements file to update, e.g. requirements/project.md)
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

## Requirements Drift

**State**: none | detected
**Findings**:
- (one bullet per drifted item, or "None" if state is none)
**Update needed**: (path to requirements file that needs updating, or "None")

## Suggested Requirements Update
<!-- Only present when State is detected -->
**File**: (path)
**Section**: (heading)
**Content**:
```
(exact content to append)
```

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

After the reviewer sub-task completes and `lifecycle/{feature}/review.md` is confirmed on disk:

Before proceeding, validate that review.md contains a `## Requirements Drift` section. If the section is absent (e.g., the reviewer ran out of context), re-dispatch the reviewer with this targeted instruction: "review.md is missing the ## Requirements Drift section. Read the existing review.md, then append the ## Requirements Drift section in the correct format. Do not modify any other section." If the section remains absent after one re-dispatch, escalate to the user.

Update `lifecycle/{feature}/index.md`:
- If `"review"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"review"` to the artifacts inline array
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

| Verdict | Cycle | Action |
|---------|-------|--------|
| APPROVED | any | Proceed to Complete |
| CHANGES_REQUESTED | 1 | Re-enter Implement for flagged tasks with reviewer feedback |
| CHANGES_REQUESTED | 2 | Escalate to user — present the reviewer's analysis and ask for direction |
| REJECTED | any | Escalate to user immediately — recommend revisiting the plan or spec |

The cycle counter prevents infinite rework loops. After cycle 2, always escalate to the user regardless of verdict.

After reading the verdict from the review artifact, append a `review_verdict` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED|CHANGES_REQUESTED|REJECTED", "cycle": <N>, "requirements_drift": "none|detected"}
```

Where `requirements_drift` is read from the `"requirements_drift"` field in the verdict JSON block.

### 4a. Auto-Apply Requirements Drift

After logging the `review_verdict` event, check whether `requirements_drift` is `"detected"`. If so:

1. **Read the suggested update**: Parse the `## Suggested Requirements Update` section from `lifecycle/{feature}/review.md`. Extract `File`, `Section`, and `Content` fields.

2. **If the section is missing or unparseable**: Skip auto-apply. Log a warning to the user: "Requirements drift detected but no suggested update was provided — manual update needed." Do not block the verdict processing.

3. **Apply the update**: Read the target requirements file. Find the section heading. Append the content after the last bullet or paragraph in that section. Write the file.

4. **Report to the user**: Display what was changed:
   ```
   Requirements updated: {file} → {section}
     Added: {first line of content}
   ```

   In interactive sessions, the user sees this immediately.

### 5. Transition

- APPROVED → log the transition and proceed to Complete automatically — do not ask the user for confirmation:
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
  ```
- CHANGES_REQUESTED cycle 1 → log the transition and return to Implement automatically — do not ask the user for confirmation:
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "implement-rework"}
  ```
- Otherwise → log the escalation, then present findings to user and await direction (user input required — this is a genuine concern):
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "escalated"}
  ```

## Constraints

| Thought | Reality |
|---------|---------|
| "Code quality issues are minor, I'll let them pass" | Minor issues compound. Flag them as PARTIAL with notes — the implementer can address them quickly. |
| "I'll use `overall: PASS` for the verdict" | The verdict JSON must use exactly `"verdict": "APPROVED"` (or `CHANGES_REQUESTED` / `REJECTED`). State detection parses this exact field name and these exact values. |
| "Requirements drift is hard to assess without clear traceability" | Assess against the requirements docs loaded in §1. If uncertain, log `detected` with a note — false positives auto-apply a small update; false negatives silently hide drift. |
| "Requirements drift should influence whether I approve the feature" | Drift is an observation only. The verdict reflects spec compliance and code quality. A feature with detected drift may still be APPROVED. The drift is auto-applied to requirements after the verdict. |
