# Specification: Wire review phase into overnight runner

## Problem Statement

The overnight batch runner (`batch_runner.py`) treats merged features as complete without consulting the lifecycle review gating matrix. Complex-tier and high/critical-criticality features that should receive spec-compliance review are auto-approved with synthetic `review_verdict: APPROVED, cycle: 0` events by the morning review skill. This means overnight-built features ship without the quality gate the lifecycle was designed to enforce. The fix is to dispatch real review agents from the batch runner for qualifying features, support a 2-cycle rework loop for non-APPROVED verdicts, and make morning review synthetic events conditional.

## Requirements

### R1: Add `read_tier()` to `claude/common.py`

Add a `read_tier(feature, lifecycle_base=Path("lifecycle"))` function that mirrors `read_criticality()`. Scans `lifecycle/{feature}/events.log` for the last JSON line containing a `"tier"` field (from `lifecycle_start` or `complexity_override` events). Returns the tier as a string. Defaults to `"simple"` when no matching event is found.

**Acceptance criteria**: `python -c "from cortex_command.common import read_tier; print(read_tier.__doc__)"` exits 0. `grep -c 'def read_tier' claude/common.py` = 1.

### R2: Add review gating logic to batch_runner.py post-merge flow

In both post-merge success paths (`_apply_feature_result` line ~1335 and `_accumulate_result` line ~1654), insert review dispatch logic between the merge success check and the existing `FEATURE_COMPLETE` log + `cleanup_worktree` call. The logic:

1. Read tier via `read_tier(feature)` and criticality via `read_criticality(feature)`
2. Apply the gating matrix via `requires_review(tier, criticality)`:

   | Criticality | simple | complex |
   |-------------|--------|---------|
   | low         | skip   | review  |
   | medium      | skip   | review  |
   | high        | review | review  |
   | critical    | review | review  |

3. If review is not required: fall through to existing FEATURE_COMPLETE flow unchanged.
4. If review is required: dispatch review agent (see R3).

**Acceptance criteria**: `grep -c 'requires_review' claude/overnight/batch_runner.py` >= 2 (called in both code paths).

### R3: Dispatch review agent for qualifying features

When the gating matrix requires review:

1. Write `phase_transition` event (`from: "implement", to: "review"`) to `lifecycle/{feature}/events.log`
2. Read `lifecycle/{feature}/spec.md` to populate `{spec_excerpt}`
3. Dispatch a review agent using `dispatch_task()` with the prompt template at `claude/pipeline/prompts/review.md`, substituting `{feature}`, `{spec_excerpt}`, `{worktree_path}`, and `{branch_name}`
4. Model selection follows the existing dispatch model matrix (determined by complexity + criticality)
5. After the agent completes, read the verdict from `lifecycle/{feature}/review.md` — the review agent writes this artifact to disk per the updated pipeline prompt (R7)

**Event write ownership**: The review agent writes ONLY the `lifecycle/{feature}/review.md` artifact. All `events.log` writes (phase_transition, review_verdict, feature_complete) are owned by batch_runner. This prevents duplicate events.

**Acceptance criteria**: `grep -c 'dispatch_task' claude/overnight/batch_runner.py` increases by at least 1 from current count. `grep -c 'review.md' claude/overnight/batch_runner.py` >= 1.

### R4: Handle review verdicts overnight (2-cycle rework loop)

After the review agent completes, parse the verdict JSON block from `lifecycle/{feature}/review.md`. The verdict block contains `{"verdict": "...", "cycle": N, "issues": [...], "requirements_drift": "..."}`.

**APPROVED (any cycle)**: Write `review_verdict` event to `lifecycle/{feature}/events.log`. Write `phase_transition` event (`from: "review", to: "complete"`). Write `feature_complete` event to `lifecycle/{feature}/events.log`. Then continue to existing FEATURE_COMPLETE pipeline log + `_write_back_to_backlog("merged")` + `cleanup_worktree` flow.

**CHANGES_REQUESTED, cycle 1**: Write `review_verdict` event to events.log. Enter rework:
1. Write the review agent's findings (issues list from review.md) to `lifecycle/{feature}/learnings/orchestrator-note.md`, prefixed with `## Review Feedback (cycle 1)` and a summary of what needs fixing
2. Dispatch a fresh fix agent using `dispatch_task()` with a rework prompt that includes: the review findings, the spec excerpt, and the worktree path. The fix agent reads the review feedback and modifies only the flagged code.
3. After the fix agent completes, re-merge the updated worktree to the integration branch
4. Dispatch a second review agent (cycle 2) using the same prompt template
5. Parse the cycle 2 verdict from `lifecycle/{feature}/review.md` (overwritten by the second review)

**CHANGES_REQUESTED or REJECTED, cycle 2** (or REJECTED at any cycle): Write `review_verdict` event to events.log. Set feature status to `deferred`. Write back to backlog as `in_progress`. Write a deferral file at `lifecycle/deferred/{feature}-review.md` containing the review feedback for morning triage. Clean up worktree.

**Review agent failure** (agent errors, exits without writing review.md, or review.md lacks a parseable verdict JSON block): Log a `review_verdict` event with `verdict: "ERROR"` and `cycle: 0`. Set feature status to `deferred`. Write back to backlog as `in_progress`. Clean up worktree.

**Fix agent failure** (rework agent errors during cycle 1 rework): Skip cycle 2 review. Set feature status to `deferred`. Write a deferral file with the cycle 1 review feedback plus the fix agent failure. Clean up worktree.

**Acceptance criteria**: `grep -c 'deferred\|orchestrator-note' claude/overnight/batch_runner.py` >= 2. Interactive/session-dependent: dispatch a review agent for a complex/high feature overnight and verify the correct verdict handling path executes.

### R5: Make morning review synthetic events conditional

In `skills/morning-review/references/walkthrough.md` section 2b, change the lifecycle advancement logic:

1. Before writing synthetic events for a merged feature, read its tier and criticality via `read_tier()` and `read_criticality()`
2. Apply `requires_review(tier, criticality)` to determine if the feature should have been reviewed
3. **If the feature should NOT have been reviewed** (simple/low or simple/medium per gating matrix): write synthetic events as today (`review_verdict: APPROVED, cycle: 0`, phase transitions, `feature_complete`)
4. **If the feature SHOULD have been reviewed**: check `lifecycle/{feature}/events.log` for an existing real `review_verdict` event (cycle >= 1):
   - If `review_verdict` AND `feature_complete` both present: skip synthetic events entirely (batch_runner already wrote real ones)
   - If `review_verdict` present but `feature_complete` missing (partial write / crash recovery): write the remaining events (`phase_transition` review→complete, `feature_complete`) to complete the lifecycle
   - If neither present: this is an error state — do NOT write synthetic APPROVED. Note in the walkthrough output that the feature was expected to be reviewed but wasn't.

The existing `feature_complete` guard (skip if feature_complete already exists in events.log) remains unchanged.

**Acceptance criteria**: `grep -c 'requires_review' skills/morning-review/references/walkthrough.md` >= 1. `grep -c 'cycle.*0' skills/morning-review/references/walkthrough.md` >= 1 (synthetic cycle 0 marker still present for intentional skips).

### R6: Extract gating matrix and review dispatch to shared functions

**R6a: Gating function** — Extract the gating matrix logic to `claude/common.py`:

```
def requires_review(tier: str, criticality: str) -> bool
```

Returns `True` when the combination requires review per the matrix. Called from batch_runner (R2), walkthrough (R5), and available for implement.md reference.

**R6b: Review dispatch helper** — Extract the full review dispatch + verdict handling + rework loop flow to a shared async helper in batch_runner (or a new module in `claude/pipeline/`):

```
async def dispatch_review(feature, worktree_path, branch_name, spec_path, complexity, criticality, ...) -> ReviewResult
```

Encapsulates: R3 (dispatch review agent), R4 (verdict handling + rework loop), and events.log writes. Called from both `_apply_feature_result` and `_accumulate_result` to prevent code divergence.

**Acceptance criteria**: `grep -c 'def requires_review' claude/common.py` = 1. `grep -c 'def dispatch_review\|async def dispatch_review' claude/overnight/batch_runner.py claude/pipeline/*.py` = 1.

### R7: Update pipeline review prompt template

Update `claude/pipeline/prompts/review.md` to produce output compatible with R4's verdict parsing:

1. Instruct the review agent to write its review to `lifecycle/{feature}/review.md` on disk (not just structured console output)
2. Include a verdict JSON block with fields: `verdict` (APPROVED | CHANGES_REQUESTED | REJECTED), `cycle` (integer), `issues` (array of strings), `requirements_drift` (none | detected)
3. Include a `## Requirements Drift` section in the output format
4. Align the output structure with the interactive review protocol's format so R4 can parse either consistently

The interactive review protocol at `skills/lifecycle/references/review.md` is NOT modified — only the pipeline prompt template is updated.

**Acceptance criteria**: `grep -c 'review.md' claude/pipeline/prompts/review.md` >= 1 (file write instruction). `grep -c 'cycle' claude/pipeline/prompts/review.md` >= 1 (cycle field in verdict). `grep -c 'requirements_drift' claude/pipeline/prompts/review.md` >= 1.

## Non-Requirements

- **No new feature statuses**: No "reviewing" status is added to `FEATURE_STATUSES`. The feature remains in "running" during review, then transitions to "merged" (APPROVED) or "deferred" (non-APPROVED after rework exhausted).
- **No changes to review criteria**: The gating matrix itself is not modified. The interactive review protocol (`skills/lifecycle/references/review.md`) is not modified. This ticket wires existing infrastructure into the overnight runner.
- **No explicit review timeout**: Review agents use the same dispatch defaults as implementation agents. No review-specific timeout is added.
- **No skepticism tuning**: The skepticism tuning protocol from spike 021 is deferred until real review data is collected from this implementation.
- **No subset task re-execution**: The rework agent is dispatched as a standalone fix agent, not by re-running specific plan tasks. Idempotency tokens from the original implementation are not invalidated.

## Edge Cases

- **Missing tier in events.log**: `read_tier()` defaults to `"simple"`. With criticality defaulting to `"medium"`, the gating matrix yields "skip review" — safe default (simple/medium = no review).
- **Missing spec.md**: If `lifecycle/{feature}/spec.md` does not exist (the review prompt template requires `{spec_excerpt}`), skip review for this feature and log a warning. A feature without a spec cannot be meaningfully reviewed against one.
- **Review agent writes no review.md**: Treated as review failure — verdict: ERROR, feature deferred. Covered by R4's failure handling.
- **review.md exists but verdict JSON is malformed or missing**: Treated as review failure — verdict: ERROR, feature deferred.
- **Feature already has review_verdict in events.log** (from a previous attempt or manual lifecycle run): The batch_runner's review dispatch should still proceed — the overnight review is independent of any prior interactive review. The new review_verdict event is appended alongside the old one.
- **Worktree already cleaned up**: If `cleanup_worktree` was called prematurely (should not happen given the insertion point), the review agent cannot access the code. Treat as review failure — feature deferred.
- **Fix agent produces no commits during rework**: SHA circuit breaker — if `before_sha == after_sha` after the fix agent, skip cycle 2 review and defer the feature. The fix agent couldn't address the review feedback.
- **Re-merge fails after rework**: If `merge_feature` fails after the fix agent's changes (conflict with other features merged in the same round), defer the feature with the merge failure reason appended to the deferral file.
- **Partial event writes (crash recovery)**: R5 handles this — if `review_verdict` exists in events.log but `feature_complete` is missing, morning review completes the lifecycle.

## Changes to Existing Behavior

- **MODIFIED: batch_runner.py post-merge flow** → After successful merge, qualifying features now go through review dispatch (with up to 2 cycles and 1 rework) before logging FEATURE_COMPLETE. Non-qualifying features proceed as today.
- **MODIFIED: morning review walkthrough 2b** → Synthetic `review_verdict: APPROVED, cycle: 0` events are now written only for features that legitimately skip review per the gating matrix, not for all merged features unconditionally. Handles partial write recovery.
- **MODIFIED: `claude/pipeline/prompts/review.md`** → Updated to produce R4-compatible output: disk write of review.md, verdict JSON with cycle and requirements_drift fields, requirements drift section.
- **ADDED: `read_tier()` in `claude/common.py`** → New function mirroring `read_criticality()` for tier detection from events.log.
- **ADDED: `requires_review()` in `claude/common.py`** → New shared function encoding the gating matrix decision.
- **ADDED: `dispatch_review()` helper** → Shared async function encapsulating the full review dispatch + verdict handling + rework loop, called from both post-merge code paths.
- **ADDED: Review-related events in per-feature events.log** → batch_runner now writes `phase_transition`, `review_verdict`, and `feature_complete` events to `lifecycle/{feature}/events.log` for reviewed features (batch_runner owns all event writes; review agent writes only the review.md artifact).
- **ADDED: Deferral files for review failures** → Non-APPROVED features after rework exhaustion produce `lifecycle/deferred/{feature}-review.md` for morning triage.

## Technical Constraints

- **Two code paths**: Both `_apply_feature_result` (line ~1335) and `_accumulate_result` (line ~1654) need the review dispatch. The `dispatch_review()` helper (R6b) is called from both paths.
- **Worktree timing**: Review dispatch and rework must happen BEFORE `cleanup_worktree()`. The worktree is kept alive through the entire review-rework-review cycle.
- **Event write ownership**: batch_runner owns all `lifecycle/{feature}/events.log` writes. The review agent writes only `lifecycle/{feature}/review.md`. This prevents duplicate events from the review agent and batch_runner writing the same event types.
- **Per-feature events.log writes**: batch_runner currently writes only to the pipeline-level log (`config.overnight_events_path`). This feature adds writes to `lifecycle/{feature}/events.log` (NDJSON format, one JSON object per line). Use the same JSON serialization pattern as the lifecycle skill.
- **Model selection**: The review agent's model is determined by `dispatch_task`'s existing model matrix based on complexity + criticality. No override needed.
- **Prompt template placeholders**: `claude/pipeline/prompts/review.md` uses `{feature}`, `{spec_excerpt}`, `{worktree_path}`, `{branch_name}`. The `{spec_excerpt}` must be read from `lifecycle/{feature}/spec.md` before dispatch.
- **Learnings injection for rework**: Review feedback is written to `lifecycle/{feature}/learnings/orchestrator-note.md`. The fix agent receives this as context. The existing `_read_learnings()` mechanism in batch_runner reads this file.
- **Re-merge after rework**: After the fix agent commits changes, `merge_feature()` must be called again to merge the updated worktree to the integration branch before cycle 2 review.

## Open Decisions

None — all decisions resolved at spec time.
