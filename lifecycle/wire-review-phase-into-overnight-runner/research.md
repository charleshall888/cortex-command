# Research: Wire review phase into overnight runner

## Codebase Analysis

### batch_runner.py post-merge flow

Two code paths handle successful merges in `claude/overnight/batch_runner.py`:

1. **`_apply_feature_result`** (line ~1296): the primary path for worktree-less features. On `result.status == "completed"`:
   - Gets changed files via `_get_changed_files()`
   - Guards: if no changed files → pauses the feature
   - Calls `merge_feature()` from `claude.pipeline.merge`
   - On success: appends to `batch_result.features_merged`, logs `FEATURE_COMPLETE`, writes back to backlog as "merged", calls `cleanup_worktree()` — **no review dispatch**

2. **`_accumulate_result`** (line ~1570): worktree-mode parallel path. Same shape — on `merge_result.success` at line ~1654: logs `FEATURE_COMPLETE`, writes backlog as "merged", cleans worktree — **no review dispatch**

**Insertion point**: In both paths, between the `FEATURE_COMPLETE` log and `cleanup_worktree()`. The worktree is still live at that point, which is required by `claude/pipeline/prompts/review.md` (references `{worktree_path}`).

### Feature status lifecycle

`OvernightFeatureStatus` in `claude/overnight/state.py` (line 61):
```
FEATURE_STATUSES = ("pending", "running", "merged", "paused", "failed", "deferred")
```

There is no "reviewing" status. Review is not represented in the overnight feature status lifecycle.

### Exit report format

`_EXIT_REPORT_ACTIONS` (line 442): `{"complete", "question"}`. Exit reports are per-task (not per-feature), read from `lifecycle/{feature}/exit-reports/{N}.json`. The review agent doesn't need to use exit reports — it writes `lifecycle/{feature}/review.md` and logs events to `events.log` directly.

### Dispatch infrastructure

- `dispatch_task` (`claude/pipeline/dispatch.py`): wraps `claude_agent_sdk.query()`, selects model from `_MODEL_MATRIX` based on `(complexity, criticality)`. For complex/high → opus; complex/medium or simple/* → sonnet.
- `retry_task` (`claude/pipeline/retry.py`): wraps `dispatch_task` with Ralph Loop (max 3 retries), diff-based circuit breaker.
- `claude/pipeline/prompts/review.md`: overnight review prompt template with `{feature}`, `{spec_excerpt}`, `{worktree_path}`, `{branch_name}` placeholders. Already exists but is not wired into any dispatch call.

### Existing rework/retry infrastructure

The batch runner has **no rework cycle for review feedback**. The only retry mechanisms are:
1. **Ralph Loop** (`retry_task`): retries on task failure, max 3 attempts
2. **Merge recovery** (`recover_test_failure`): one attempt to fix test failures post-merge
3. **Conflict repair**: trivial fast-path or repair agent, gated at `recovery_depth < 1`

None involve review feedback. The implement → review → CHANGES_REQUESTED → re-implement loop exists only in the interactive lifecycle (`implement.md` section 3), not in batch_runner.

- `recovery_attempts` (state.py line 94): tracks test-failure recovery cycles, gated at 1
- `recovery_depth` (state.py line 95): tracks merge-conflict repair agent dispatches, gated at 1

### Review phase protocol (review.md)

`skills/lifecycle/references/review.md` defines three verdicts:

| Verdict | Cycle | Action |
|---------|-------|--------|
| APPROVED | any | Proceed to Complete |
| CHANGES_REQUESTED | 1 | Re-enter Implement for flagged tasks with reviewer feedback |
| CHANGES_REQUESTED | 2 | Escalate to user |
| REJECTED | any | Escalate to user immediately |

The review agent writes `lifecycle/{feature}/review.md` containing spec compliance ratings, requirements drift check, code quality assessment, and a verdict JSON block. It logs a `review_verdict` event to `lifecycle/{feature}/events.log`.

Model selection by criticality: sonnet for low/medium, opus for high/critical.

### Implement phase gating matrix

`implement.md` lines 127-144 — the Review Gate:

| Criticality | simple | complex |
|-------------|--------|---------|
| low | Complete | Review |
| medium | Complete | Review |
| high | Review | Review |
| critical | Review | Review |

Criticality defaults: `read_criticality()` in `claude/common.py` (line 161) scans events.log for the last `"criticality"` field, defaults to `"medium"` if absent.

**Missing `read_tier()` function**: There is no centralized `read_tier()` analogue to `read_criticality()`. Tier is parsed ad-hoc from the `lifecycle_start` event's `"tier"` field. A `read_tier()` function needs to be added to `claude/common.py`.

### Morning review synthetic events

`skills/morning-review/references/walkthrough.md` section 2b (lines 84-121):

For **every** completed (merged) feature, unconditionally appends four synthetic events:
```json
{"event": "phase_transition", "from": "implement", "to": "review"}
{"event": "review_verdict", "verdict": "APPROVED", "cycle": 0}
{"event": "phase_transition", "from": "review", "to": "complete"}
{"event": "feature_complete", "tasks_total": N, "rework_cycles": 0}
```

The `cycle: 0` marker distinguishes synthetic from real reviews (real reviews start at cycle 1). Currently writes these for ALL merged features regardless of tier/criticality — the problem the backlog item describes.

### Events.log real examples

Real review events from existing lifecycles:
```json
{"event": "review_verdict", "verdict": "APPROVED", "cycle": 1, "requirements_drift": "detected"}
{"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1}
{"event": "review_verdict", "verdict": "APPROVED", "cycle": 2}
```

The `requirements_drift` field is present in newer events (added by the wire-requirements-drift feature).

## Alternative Approaches

### Option A: Post-merge review in batch_runner (backlog item's approach)

Hook into both merge success paths between `FEATURE_COMPLETE` log and `cleanup_worktree()`. Dispatch review agent using existing `dispatch_task()` with `claude/pipeline/prompts/review.md`. Parse verdict from `lifecycle/{feature}/review.md` or events.log.

**Strengths**: Natural insertion point, worktree still live, dispatch infrastructure exists. Review happens overnight — morning sees real verdicts.

**Challenges**: CHANGES_REQUESTED rework requires re-dispatching implementation tasks, which means keeping the worktree alive and looping back into `execute_feature` logic — non-trivial. Two code paths need the same logic.

### Option B: Pre-merge review

Review runs at the end of `execute_feature` (line ~1062) before returning `FeatureResult(status="completed")`. The worktree is already set up. Review happens before merge, catching issues earlier.

**Strengths**: Cleaner architecturally — issues caught before merge. Rework can happen in the same worktree before merge attempt.

**Challenges**: Increases per-feature latency in the batch. Changes the meaning of `FeatureResult(status="completed")` to include review. Feature result would need to carry review metadata.

**Assessment**: Pre-merge review is architecturally cleaner for rework cycles, but it changes the execute_feature contract. The batch runner currently treats "completed" as "all tasks done, ready to merge." Adding review before this return means redefining "completed" to include "reviewed." This is a deeper change than the backlog item scopes.

### Option C: Morning review performs real review

Instead of overnight dispatch, the morning review skill dispatches real reviewers for qualifying features during the walkthrough.

**Assessment**: Rejected. The morning session currently completes in minutes; review agents for complex/opus features take significant time. Also, the branch is already merged to main — CHANGES_REQUESTED would require a follow-up task, not in-place rework. This defeats the purpose.

### Option D: Separate post-batch review pass

A new `review_runner.py` runs after each batch round, filtering for features needing review and dispatching reviewers. Isolates review latency from implementation.

**Assessment**: Over-engineered for the current scope. The batch runner already handles post-merge steps (test recovery, conflict resolution). Adding review dispatch inline is more consistent than a separate runner.

### Recommended approach

**Option A (post-merge in batch_runner)** with a simplification for CHANGES_REQUESTED handling:

For the overnight context, limit review to a single cycle (no rework loop). On CHANGES_REQUESTED or REJECTED: log the real `review_verdict` event with the reviewer's findings, then **pause the feature** so the morning report surfaces the review feedback. This avoids the complexity of re-dispatching implementation tasks overnight while still providing real spec compliance checks.

The full rework loop (CHANGES_REQUESTED → re-implement → re-review) can be added later if morning reports show features frequently getting CHANGES_REQUESTED verdicts that are trivially fixable.

This matches the user's input during Clarify: "if the retries fail, then I would think we mark it failed or paused."

## Open Questions

- Should the new `read_tier()` function follow the same pattern as `read_criticality()` (scan events.log for the last `lifecycle_start` or `complexity_override` event with a `"tier"` field, default to `"simple"` if absent)?
