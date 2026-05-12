# Specification: fix-morning-report-accuracy-when-post-merge-steps-fail

## Problem Statement

When the overnight runner successfully merges a feature to the integration branch but a subsequent post-merge step crashes (such as `dispatch_review` raising an exception), the runner records the feature as `deferred` or `failed` — the same status used for features that never merged at all. The morning report presents these features as genuine pipeline failures with "investigate and retry" guidance, which is incorrect: the merge already landed, re-running the feature would duplicate work, and the human wastes time investigating a phantom failure instead of addressing the specific post-merge step that crashed. This fix adds a `feature_merged` event written before any post-merge step runs, and uses that event in the report to give accurate context and correct remediation guidance.

## Requirements

All requirements are must-have.

1. **FEATURE_MERGED constant registered**: Add `FEATURE_MERGED = "feature_merged"` to `claude/overnight/events.py` and add the constant to the `EVENT_TYPES` tuple.
   - Acceptance criteria: `grep -c 'FEATURE_MERGED = "feature_merged"' claude/overnight/events.py` = 1

2. **Event written before post-merge steps in `_accumulate_result`**: Immediately after `merge_result.success` is True in `_accumulate_result` — before any call to `read_tier()`, `requires_review()`, or `dispatch_review()` — write `overnight_log_event(FEATURE_MERGED, config.batch_id, feature=name, details={"integration_branch": effective_branch}, log_path=config.overnight_events_path)`. Use the `effective_branch` local variable already computed earlier in `_accumulate_result` via `_effective_base_branch(...)` — do not use `config.base_branch` directly (see Technical Constraints).
   - Acceptance criteria: Interactive/session-dependent — correct placement requires visual inspection of `batch_runner.py` to confirm the event write is the first statement inside `if merge_result.success:`, preceding `read_tier(name)`. Supporting check: `grep -c 'FEATURE_MERGED' claude/overnight/batch_runner.py` ≥ 1

3. **`render_failed_features()` annotates merged features**: For any feature with `status in ("failed", "paused")` that has a `feature_merged` event in `data.events`, `render_failed_features()` inserts the following warning line before the `Suggested next step` and replaces the `_suggest_next_step()` return value:
   - Warning line: `⚠️ Feature is on the integration branch — merge succeeded but a post-merge step failed after the commit landed.`
   - Suggested next step override: `Investigate which post-merge step crashed (check overnight-events.log for the feature_deferred event details and error field). Do NOT re-run the feature — it is already on the integration branch. Address any missed post-merge steps manually (e.g., trigger review, update backlog item).`
   - Acceptance criteria: `just test` exits 0 AND new tests assert that `render_failed_features(data)` output:
     - contains `"Feature is on the integration branch"` when `data.events` includes a `feature_merged` event for a failed feature
     - contains `"Do NOT re-run the feature"` in the same scenario
     - contains `"overnight-events.log"` in the same scenario

4. **`render_deferred_questions()` annotates merged features**: For any deferred feature with `SEVERITY_BLOCKING` that has a `feature_merged` event in `data.events`, `render_deferred_questions()` overrides the `> **To unblock**:` line, replacing "Answer this question and re-run the feature" with: `Feature is on the integration branch — do NOT re-run. Investigate the post-merge failure (see error details above and overnight-events.log). Address missed post-merge steps manually (review dispatch, backlog write-back).`
   - Acceptance criteria: `just test` exits 0 AND new tests assert that `render_deferred_questions(data)` output for a SEVERITY_BLOCKING deferred feature with a `feature_merged` event:
     - does NOT contain `"re-run the feature"`
     - contains `"Feature is on the integration branch"`
     - contains `"overnight-events.log"`

5. **Annotation wording elements**: The annotation in Requirements 3 and 4 must include all four elements: (a) a clear statement that the feature is on the integration branch, (b) explicit "do NOT re-run" guidance, (c) a reference to `overnight-events.log` for error details, (d) actionable next steps for missed post-merge work. Requirements 3 and 4's ACs together verify all four elements via string assertions.
   - Acceptance criteria: Verified by the string assertions in Requirements 3 and 4 — no additional AC needed here.

6. **Walkthrough Section 4 updated**: In `skills/morning-review/references/walkthrough.md` Section 4, add handling for features annotated with the "integration branch" warning. When such a feature appears, the walkthrough must:
   - State that the feature is already on the integration branch
   - NOT suggest creating an investigation or re-run backlog ticket for the feature itself
   - Instruct: verify the feature is on the integration branch; identify which post-merge step failed; address that step manually; advance the lifecycle manually
   - Acceptance criteria: `grep -c 'integration branch' skills/morning-review/references/walkthrough.md` ≥ 1

7. **Regression — happy path unaffected**: Features that fail pre-merge have no `feature_merged` event and receive no annotation in either `render_failed_features()` or `render_deferred_questions()`.
   - Acceptance criteria: `just test` exits 0 AND new test asserts that `render_failed_features(data)` output for a failed feature WITHOUT a `feature_merged` event does NOT contain the string `"integration branch"`

## Non-Requirements

- Retroactive annotation of historical sessions — old `overnight-events.log` files without `feature_merged` events are treated as neutral (no annotation); no backfill
- Git branch inspection as an alternative or fallback — entirely events-log-based; no subprocess calls to git from `report.py`
- A new status category in `OvernightFeatureState` — features remain `deferred`/`failed`/`paused` in state; only report rendering changes
- Writing `FEATURE_MERGED` into per-feature `lifecycle/{feature}/events.log` files — goes into session-level `overnight-events.log` only
- Annotation in the completed features section — only failed and SEVERITY_BLOCKING deferred sections are affected
- Annotation for non-blocking deferrals — non-blocking deferrals allow the pipeline to continue and terminate as `complete`; they do not appear in `render_deferred_questions()`
- Writing `FEATURE_MERGED` in the repair/ff-merge path (`_apply_feature_result`) — that path has no `dispatch_review`, no `read_tier`, and no path to `FEATURE_DEFERRED`; the failure mode this fix addresses cannot occur there
- Retroactive remediation of the specific session that triggered this ticket (already triaged)

## Edge Cases

- **Old sessions without `feature_merged` events**: `merged_to_integration` set is empty; all existing render behavior is unchanged. No annotation fires.
- **Feature deferred before any merge** (pre-merge deferral, e.g., ambiguous intent): No `feature_merged` event in the session log for that feature. Annotation does not fire. Correct behavior.
- **SEVERITY_BLOCKING deferral without a `feature_merged` event**: Renders with the existing "Answer this question and re-run the feature" text unchanged. Correct.
- **`FEATURE_MERGED` written but process crashes before `FEATURE_DEFERRED`** (clean exception in between): Events log has `FEATURE_MERGED` but the feature never appears in state as deferred/failed. Annotation code never runs (feature not in iterated collections). No error.
- **`FEATURE_MERGED` followed by `FEATURE_COMPLETE`** (happy path with review approved): Feature is in `features_merged`, not in failed/deferred sections. Annotation never evaluated. Correct.
- **JSONDecodeError on events log read**: `read_events()` already handles corrupted lines with a warning. Degrades to "no events found" — annotation does not fire. Acceptable residual risk (hardware-level crash only).
- **`ValueError` from unregistered event type**: Prevented by deploying `events.py` change before `batch_runner.py` is used. The `events.py` and `batch_runner.py` changes must ship together — never deploy `batch_runner.py` with `FEATURE_MERGED` calls if `events.py` has not been updated. A `ValueError` propagating inside `async with lock:` in `_accumulate_result` would crash that feature's execution slot.

## Changes to Existing Behavior

- **ADDED**: `FEATURE_MERGED = "feature_merged"` event type constant in `claude/overnight/events.py`
- **ADDED**: `feature_merged` event written to `overnight-events.log` after every successful merge in `_accumulate_result` (standard merge path only)
- **MODIFIED**: `render_failed_features()` — features with a `feature_merged` event in the session log receive an additional warning line and a different suggested next step
- **MODIFIED**: `render_deferred_questions()` — SEVERITY_BLOCKING deferred features with a `feature_merged` event receive a different "To unblock" action that does not suggest re-running the feature
- **MODIFIED**: `skills/morning-review/references/walkthrough.md` Section 4 — guidance updated for features annotated as "merged — post-merge crash"

## Technical Constraints

- `overnight_log_event` validates event type against `EVENT_TYPES` (raises `ValueError` on unregistered types) — the `events.py` change (constant + tuple entry) must be deployed atomically with or before the `batch_runner.py` change
- Do NOT wrap `overnight_log_event(FEATURE_MERGED, ...)` in `try/except` — absence of the event must unambiguously mean "never merged"; a swallowed write failure would silently create false negatives
- The `FEATURE_MERGED` event writes to `config.overnight_events_path` (session-level `overnight-events.log`), NOT to any per-feature `lifecycle/{feature}/events.log`
- The `details` dict must use `effective_branch` — the local variable computed in `_accumulate_result` via `_effective_base_branch(repo_path_map.get(name), integration_branches, config.base_branch)` just before the `if merge_result.success:` check. Do NOT use `config.base_branch` directly — it is a home-repo default that diverges from the per-feature resolved integration branch in multi-repo sessions
- `render_deferred_questions()` does not currently access `data.events`; the fix adds set-building from `data.events` before the deferral iteration loop — same pattern used in `render_failed_features()` for retry counts and conflict info
- `_accumulate_result` is a closure inside `run_batch()`; `effective_branch`, `config`, `name`, and `config.overnight_events_path` are all in scope at the insertion point without new parameters
- `skills/morning-review/references/walkthrough.md` is the repo source file (symlinked to `~/.claude/skills/morning-review/references/walkthrough.md`); always edit the repo copy
