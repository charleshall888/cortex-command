# Review: wire-review-phase-into-overnight-runner

## Stage 1: Spec Compliance

### Requirement R1: Add `read_tier()` to `claude/common.py`

- **Expected**: `read_tier(feature, lifecycle_base=Path("lifecycle"))` function that mirrors `read_criticality()`, scans events.log for last JSON line with "tier" field, defaults to "simple".
- **Actual**: `read_tier` at `claude/common.py:204` mirrors `read_criticality` exactly. Scans JSONL lines for "tier" field, returns last match, defaults to "simple". Signature matches: `read_tier(feature: str, lifecycle_base: Path = Path("lifecycle")) -> str`.
- **Verdict**: PASS
- **Notes**: Clean implementation. Docstring is present. Acceptance criteria met: `grep -c 'def read_tier' claude/common.py` = 1.

### Requirement R2: Add review gating logic to batch_runner.py post-merge flow

- **Expected**: `requires_review()` called in both post-merge success paths (`_apply_feature_result` line ~1335 and `_accumulate_result` line ~1654). Read tier and criticality, apply gating matrix, dispatch review if required.
- **Actual**: `requires_review()` is called directly only in `_accumulate_result` (line 1688). `_apply_feature_result` accepts a `review_result` parameter (line 1216) and handles deferred results (line 1340), but does not call `requires_review()` itself. The architecture relies on `_accumulate_result` handling all successful merges inline (lines 1684-1743) rather than delegating to `_apply_feature_result`. Since `_accumulate_result` is the only entry point and handles the merge success path directly, review gating is functionally applied to all normal post-merge paths.
- **Verdict**: PARTIAL
- **Notes**: The literal acceptance criterion (`grep -c 'requires_review' claude/overnight/batch_runner.py` >= 2) is met (2 matches: import + call), but `requires_review` is only *called* once, not in "both code paths" as the spec states. `_apply_feature_result` has infrastructure for handling a `review_result` parameter but it is always passed `None` from `_accumulate_result`. Functionally equivalent for the current call graph, but if `_apply_feature_result` is called directly in the future with a completed merge, review gating would be bypassed.

### Requirement R3: Dispatch review agent for qualifying features

- **Expected**: Write phase_transition event, read spec.md, dispatch review agent via `dispatch_task()` with prompt template, read verdict from review.md. Event write ownership: batch_runner owns events.log, review agent writes only review.md.
- **Actual**: `dispatch_review()` in `claude/pipeline/review_dispatch.py` handles all of this. It writes the phase_transition event (line 186), reads the spec (line 195), loads and formats the prompt template (line 218), dispatches via `dispatch_task()` (line 250), and parses the verdict from review.md (line 262). Event write ownership is correct: all events.log writes are in `dispatch_review()` (called by batch_runner), and the review agent only writes review.md per the prompt instructions.
- **Verdict**: PARTIAL
- **Notes**: Functionally complete. However, the literal acceptance criterion "`grep -c 'dispatch_task' claude/overnight/batch_runner.py` increases by at least 1" is not met -- the count remains at 1 (import only) because `dispatch_task` is called indirectly through `dispatch_review`. Similarly, `grep -c 'review.md' claude/overnight/batch_runner.py` = 0 (versus required >= 1) because review.md reading is encapsulated in `review_dispatch.py`. These are reasonable architectural decisions (encapsulation in a shared helper per R6b) that conflict with the literal grep-based acceptance criteria.

### Requirement R4: Handle review verdicts overnight (2-cycle rework loop)

- **Expected**: APPROVED -> write events, complete. CHANGES_REQUESTED cycle 1 -> write feedback to orchestrator-note.md, dispatch fix agent, re-merge, cycle 2 review. CHANGES_REQUESTED/REJECTED cycle 2+ -> defer. ERROR handling for agent failures, fix agent failures, SHA circuit breaker, re-merge failures.
- **Actual**: All verdict handling paths are implemented in `dispatch_review()` (lines 268-575):
  - APPROVED (line 268): writes review_verdict, phase_transition, feature_complete events. Correct.
  - ERROR (line 295): writes review_verdict ERROR event, returns deferred. Correct.
  - REJECTED (line 312): writes review_verdict, writes deferral file, returns deferred. Correct.
  - CHANGES_REQUESTED cycle 1 (line 330): writes review_verdict, writes orchestrator-note.md (line 355), captures before SHA (line 361), dispatches fix agent (line 381), checks fix agent failure (line 393), SHA circuit breaker (line 419), re-merge (line 438), cycle 2 review dispatch (line 494), cycle 2 verdict handling (lines 512-555). Correct.
  - CHANGES_REQUESTED cycle 2+ (line 340): writes deferral and returns deferred. Correct.
  - Unexpected verdict (line 557): treated as ERROR. Correct.
- **Verdict**: PARTIAL
- **Notes**: Two minor deviations: (1) Orchestrator-note.md heading uses `# Review Feedback (Cycle 1)` (H1) instead of the spec's `## Review Feedback (cycle 1)` (H2, lowercase "cycle"). (2) Deferral files use the existing deferral system naming (`{feature}-q{N}.md`) instead of the spec's `lifecycle/deferred/{feature}-review.md`. Both are defensible design choices -- the H1 is the only heading in the file, and reusing the existing deferral system integrates with the morning review Section 3 workflow. One potential issue: the `dispatch_review()` call from `_accumulate_result` does not pass `integration_branch` or `base_branch`, so the re-merge after rework defaults to `base_branch="main"`. If the session uses integration branches, the rework re-merge could target the wrong branch.

### Requirement R5: Make morning review synthetic events conditional

- **Expected**: Morning review walkthrough reads tier/criticality, applies `requires_review()`, writes synthetic events only for non-review-required features, handles crash recovery for review-required features.
- **Actual**: `skills/morning-review/references/walkthrough.md` Section 2b (lines 86-156) implements the full conditional logic: step 3 reads tier and criticality, step 4 applies gating check referencing `requires_review()`, step 5 writes synthetic events for non-review-required features (including `cycle: 0`), step 6 handles three cases for review-required features (already complete, crash recovery, missing review). Edge case table updated with all scenarios.
- **Verdict**: PASS
- **Notes**: Acceptance criteria met: `grep -c 'requires_review' walkthrough.md` >= 1 (yes, at line 102). `grep -c 'cycle.*0' walkthrough.md` >= 1 (yes, synthetic cycle 0 markers present at lines 119-121).

### Requirement R6: Extract gating matrix and review dispatch to shared functions

- **Expected**: R6a: `requires_review(tier, criticality) -> bool` in `claude/common.py`. R6b: `async def dispatch_review(...)` as shared helper in `claude/pipeline/`.
- **Actual**: R6a: `requires_review` at `claude/common.py:245`. R6b: `async def dispatch_review(...)` at `claude/pipeline/review_dispatch.py:119`.
- **Verdict**: PASS
- **Notes**: Acceptance criteria met: `grep -c 'def requires_review' claude/common.py` = 1. `grep -c 'async def dispatch_review' claude/pipeline/review_dispatch.py` = 1. `dispatch_review` is called from `_accumulate_result` in batch_runner, preventing code divergence between the two paths (only one call site needed since `_accumulate_result` handles the merge success path directly).

### Requirement R7: Update pipeline review prompt template

- **Expected**: Prompt instructs review agent to write review.md to disk, includes verdict JSON with verdict/cycle/issues/requirements_drift fields, includes Requirements Drift section.
- **Actual**: `claude/pipeline/prompts/review.md` instructs the agent to write to `lifecycle/{feature}/review.md` (line 51), specifies the verdict JSON format with all four fields (lines 53-57), includes a Requirements Drift section (lines 44-47), and provides verdict criteria and review discipline guidelines.
- **Verdict**: PASS
- **Notes**: Acceptance criteria met: `grep -c 'review.md' prompts/review.md` >= 1 (2 matches). `grep -c 'cycle' prompts/review.md` >= 1 (3 matches). `grep -c 'requirements_drift' prompts/review.md` >= 1 (3 matches). Template aligns with the interactive review format for consistent parsing.

## Requirements Drift

**State**: detected
**Findings**:
- The pipeline requirements (`requirements/pipeline.md`) document the feature execution lifecycle as `pending -> running -> merged/paused/failed/deferred` but do not mention a review phase, review gating matrix, or post-merge review dispatch. The new behavior where qualifying features go through a review cycle (with potential rework loop) between merge and completion is not reflected.
- The pipeline requirements list per-feature metrics including "review verdicts" in the Metrics section, suggesting review was anticipated, but the actual gating mechanism and dispatch flow are not described as functional requirements.
- The deferral system requirements do not mention review-originated deferrals as a deferral source.
**Update needed**: requirements/pipeline.md

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `read_tier` mirrors `read_criticality`. `requires_review` follows the predicate naming convention. `ReviewResult` dataclass follows existing result types. `dispatch_review` follows `dispatch_task` naming. `parse_verdict` is clear and descriptive.
- **Error handling**: Thorough. `dispatch_review` handles: missing spec (returns ERROR), missing prompt template (returns ERROR), agent failure, unparseable verdict, fix agent failure, SHA circuit breaker, re-merge failure, and unexpected verdict values. Each failure path writes appropriate events and deferral files. The `parse_verdict` function gracefully handles missing files, malformed JSON, and absent code blocks.
- **Test coverage**: Unit tests cover `read_tier` (7 tests: normal, multiple, empty, missing, override, malformed JSON, no tier field) and `requires_review` (all 8 matrix cells). `parse_verdict` has 7 tests (valid, CHANGES_REQUESTED, malformed, missing file, no block, empty, surrounding text). No integration tests for `dispatch_review` or the batch_runner wiring, which is acknowledged in R4's acceptance criteria as session-dependent.
- **Pattern consistency**: Follows existing project conventions. Uses `log_event` for events.log writes (same as lifecycle skill). Uses `write_deferral` for deferral files (same as existing deferral system). Lazy import for circular dependency avoidance follows existing pattern in batch_runner. `_write_review_deferral` helper follows the `_write_*` internal helper pattern.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R2: requires_review() called in only one code path (accumulate_result) instead of both paths as specified; _apply_feature_result has review_result handling but is always passed None", "R3: grep-based acceptance criteria not met literally due to dispatch_task and review.md being encapsulated in review_dispatch.py helper", "R4: orchestrator-note.md heading uses H1 instead of spec's H2; deferral files use existing q-number naming instead of spec's {feature}-review.md naming; dispatch_review call does not pass integration_branch/base_branch which may cause rework re-merge to target wrong branch in integration-branch sessions"], "requirements_drift": "detected"}
```
