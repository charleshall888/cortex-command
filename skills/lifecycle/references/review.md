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

CRITICAL: The Verdict section MUST contain a JSON object with exactly these fields:
- "verdict": one of "APPROVED", "CHANGES_REQUESTED", or "REJECTED"
- "cycle": the review cycle number (integer)
- "issues": array of issue strings (empty array if none)

Do NOT use alternative field names like "overall", "result", or "status".
Do NOT use alternative values like "PASS", "FAIL", or "APPROVED_WITH_NOTES".

Your review.md MUST include a ## Requirements Drift section using exactly this format:
## Requirements Drift
**State**: none | detected
**Findings**:
- (one bullet per drifted item, or "None" if state is none)
**Update needed**: (path to requirements file that needs updating, or "None")
The requirements_drift value in the verdict JSON MUST match: "none" when State is none, "detected" when State is detected.

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

After the reviewer sub-task completes and `lifecycle/{feature}/review.md` is confirmed on disk, update `lifecycle/{feature}/index.md`:
- If `"review"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"review"` to the artifacts inline array
- Add wikilink: `- Review: [[{lifecycle-slug}/review|review.md]]`
  (where `{lifecycle-slug}` is the feature directory name, e.g. `add-lifecycle-feature-indexmd-for-obsidian-navigation`)
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
{"ts": "<ISO 8601>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED|CHANGES_REQUESTED|REJECTED", "cycle": <N>}
```

### 5. Transition

- APPROVED → log the transition and proceed to Complete automatically — do not ask the user for confirmation:
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
  ```
- CHANGES_REQUESTED cycle 1 → log the transition and return to Implement automatically — do not ask the user for confirmation:
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "implement"}
  ```
- Otherwise → log the escalation, then present findings to user and await direction (user input required — this is a genuine concern):
  ```
  {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "escalated"}
  ```

## Constraints

| Thought | Reality |
|---------|---------|
| "The implementation looks good, I can just approve it" | Review each requirement against the spec individually. Gestalt impressions miss specific gaps. |
| "I'll just fix the issues myself instead of flagging them" | The reviewer does not modify files. Flagging issues preserves separation of concerns and creates a paper trail. |
| "Code quality issues are minor, I'll let them pass" | Minor issues compound. Flag them as PARTIAL with notes — the implementer can address them quickly. |
| "I'll use `overall: PASS` for the verdict" | The verdict JSON must use exactly `"verdict": "APPROVED"` (or `CHANGES_REQUESTED` / `REJECTED`). State detection parses this exact field name and these exact values. |
