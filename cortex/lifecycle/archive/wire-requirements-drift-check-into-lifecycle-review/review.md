# Review: wire-requirements-drift-check-into-lifecycle-review

## Stage 1: Spec Compliance

### Requirement 1: Mandatory drift section
- **Expected**: review.md must include `## Requirements Drift` section; review.md without it is incomplete; review phase protocol validates the section exists before logging `review_verdict`.
- **Actual**: The review artifact format in `review.md` (line 98) includes `## Requirements Drift` as a required section. Section 4 (Process Verdict, line 124) validates that `## Requirements Drift` exists before proceeding and specifies re-dispatch if absent. The reviewer prompt template (lines 72-78) explicitly requires the section.
- **Verdict**: PASS

### Requirement 2: Two-state structured format
- **Expected**: Exact fill-in template with `**State**: none | detected`, `**Findings**:` bullets, and `**Update needed**:` field.
- **Actual**: The artifact format (lines 96-103) matches the exact template from the spec. The reviewer prompt (lines 72-78) reproduces the same template. The `_read_requirements_drift()` helper in `report.py` (lines 749-792) parses `**State**:` and `**Findings**:` correctly. It also handles "None" findings by filtering them out (line 789: `if line != "- None"`).
- **Verdict**: PASS

### Requirement 3: Verdict JSON extended with `requirements_drift`
- **Expected**: Verdict JSON gains `"requirements_drift"` field with values `"none"` or `"detected"`. Machine-readable channel for drift status.
- **Actual**: The artifact format example (line 116) shows `{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}`. The `review_verdict` event (line 146) includes `"requirements_drift": "none|detected"`. The reviewer prompt (line 78) states the value must match the `**State**:` field. However, the CRITICAL block (lines 64-67) says "exactly these fields" and lists only three (verdict, cycle, issues) -- it does not list `requirements_drift` as a fourth required field. The field is referenced separately five lines later. This creates a minor ambiguity: an agent following the "exactly these fields" instruction literally could omit `requirements_drift`.
- **Verdict**: PARTIAL
- **Notes**: The CRITICAL block that says "exactly these fields" lists only three fields. The `requirements_drift` field is specified separately below, and the artifact example includes it, so in practice the reviewer will likely include it. But the word "exactly" combined with an incomplete list is a documentation inconsistency that could cause issues with a very literal agent.

### Requirement 4: Replaces Requirements Compliance
- **Expected**: Existing conditional `## Requirements Compliance` section is removed and replaced by mandatory `## Requirements Drift`.
- **Actual**: No occurrence of "Requirements Compliance" exists in `review.md`. The `## Requirements Drift` section is present in the artifact format (line 98) and the reviewer prompt (line 72). Replacement is complete.
- **Verdict**: PASS

### Requirement 5: Drift does not influence verdict
- **Expected**: Verdict reflects spec compliance and code quality only. Drift is observation only. Reviewer prompt must explicitly state this. Feature with detected drift may still be APPROVED.
- **Actual**: The reviewer prompt (lines 56-59) explicitly states: "requirements drift does NOT influence the verdict. This is an observation only." The constraints table (line 175) reinforces: "Drift is an observation only. The verdict reflects spec compliance and code quality. A feature with detected drift may still be APPROVED."
- **Verdict**: PASS

### Requirement 6: Requirements doc loading (tag-based protocol in section 1)
- **Expected**: Replace freeform scan with structured 4-step protocol: (1) read project.md always, (2) read index.md tags, (3) match tags against Conditional Loading phrases case-insensitively, (4) load matched area docs or note "no area docs matched."
- **Actual**: Section 1 (lines 12-16) implements the exact 4-step protocol: (1) Read `requirements/project.md` always, (2) Read index.md and extract tags, (3) Check Conditional Loading section case-insensitively for tag word matches, (4) Record the full list; if no matches, note "no area docs matched for tags: {tags}; drift check covers project.md only". The reviewer prompt template (lines 33-34) injects the resolved list.
- **Verdict**: PASS

### Requirement 7: Reviewer is read-only
- **Expected**: Reviewer sub-task must not modify any requirements files. Enforced via prompt and read-only convention.
- **Actual**: The reviewer prompt (line 80) states: "Do NOT modify any source files. This is a read-only review." Section 2 (line 20) says "Dispatch a focused review sub-task with read-only instructions." The constraints table (line 171) reinforces the no-modification rule.
- **Verdict**: PASS

### Requirement 8: Morning report surfaces drift
- **Expected**: `_read_requirements_drift(feature)` helper following `_read_verification_strategy()` pattern. Returns None when review.md absent, dict with state/findings when found. Called for all features where review.md exists (not just merged). Handles malformed sections.
- **Actual**: `_read_requirements_drift()` (lines 749-792) follows the `_read_verification_strategy()` pattern closely: same file existence check, same regex-based section extraction. Returns None when review.md absent or section not found. Returns `{"state": "malformed", "findings": []}` when section exists but `**State**:` line is missing. Returns `{"state": <value>, "findings": [<bullets>]}` for valid sections. Called in two locations: (a) completed features block (line 562) for merged features, and (b) `render_pending_drift()` (line 638) which scans all `lifecycle/*/review.md` files excluding merged and re-implementing features. Together these two call sites cover all features where review.md exists.
- **Verdict**: PASS

### Requirement 9: No stall -- drift never blocks overnight merges
- **Expected**: Detected drift never stalls the overnight session and does not prevent merging.
- **Actual**: No merge-blocking logic is added. The drift information is purely rendered in report output (lines 562-570 for completed features, lines 598-659 for pending drift). No changes to `claude/common.py` or the lifecycle state machine. The review phase protocol does not gate on drift state for the APPROVED -> Complete transition.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- The `render_pending_drift()` function (lines 598-659 of report.py) introduces a new top-level morning report section `## Requirements Drift Flags` that is not described in `requirements/project.md`. This is new morning reporting behavior (scanning non-completed features for drift) that extends the overnight execution framework's reporting capabilities beyond what project requirements currently document.
**Update needed**: requirements/project.md

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `_read_requirements_drift()` follows the established `_read_*()` private helper convention (cf. `_read_verification_strategy`, `_read_learnings_summary`, `_read_recovery_log_last_entry`). `render_pending_drift()` follows the `render_*()` public function convention (cf. `render_completed_features`, `render_deferred_questions`).

- **Error handling**: Appropriate. `_read_requirements_drift()` returns None for missing files/sections and handles malformed sections gracefully with `{"state": "malformed", "findings": []}`. The completed features block (lines 568-569) surfaces malformed state to the user. `render_pending_drift()` filters out re-implementing features (stale review.md from prior cycles) to avoid false positives.

- **Test coverage**: No new test files were added for `_read_requirements_drift()` or `render_pending_drift()`. The spec does not explicitly require tests, and the plan's verification strategy (manual verification steps) was the stated approach. However, these are regex-based parsers with edge cases (malformed sections, missing fields) that would benefit from unit tests.

- **Pattern consistency**: Strong. The new helper mirrors `_read_verification_strategy()` structurally. The `render_pending_drift()` function follows the same pattern as other `render_*()` functions (returns empty string when nothing to render, uses ReportData, returns joined lines). The call site in `generate_report()` (line 1297) places the section between completed features and deferred questions, which is a logical position.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
