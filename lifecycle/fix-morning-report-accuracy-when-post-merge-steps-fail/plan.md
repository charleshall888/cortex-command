# Plan: fix-morning-report-accuracy-when-post-merge-steps-fail

## Overview

Implement a write-ahead log event (`FEATURE_MERGED`) that records a successful merge before any post-merge step runs, then use that event in `render_failed_features()` and `render_deferred_questions()` to annotate affected features with accurate "already on the integration branch — do NOT re-run" guidance. A new `tests/test_report.py` verifies annotation behavior for both render functions and the regression case.

## Tasks

### Task 1: Add FEATURE_MERGED constant and EVENT_TYPES entry
- **Files**: `claude/overnight/events.py`
- **What**: Register the new event type so `overnight_log_event` can accept it without raising `ValueError`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Add `FEATURE_MERGED = "feature_merged"` after `PLAN_GEN_DISPATCHED = "plan_gen_dispatched"` at line 77 of `claude/overnight/events.py`
  - Add `FEATURE_MERGED,` to the `EVENT_TYPES` tuple after `PLAN_GEN_DISPATCHED,` at line 125
  - All existing constants follow `SCREAMING_SNAKE_CASE` name → `"snake_case"` string pattern
- **Verification**: `grep -c 'FEATURE_MERGED = "feature_merged"' claude/overnight/events.py` = 1; `grep -c 'FEATURE_MERGED,' claude/overnight/events.py` = 1 — pass if both counts equal 1
- **Status**: [x] completed

### Task 2: Import FEATURE_MERGED and write event in _accumulate_result
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Add `FEATURE_MERGED` to the import from `events` and write the event as the first statement inside `if merge_result.success:` in `_accumulate_result`, before any post-merge step.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Import line (around line 67): `FEATURE_COMPLETE, FEATURE_DEFERRED,` → add `FEATURE_MERGED,` to the same import block from `claude.overnight.events`
  - Insertion point: `_accumulate_result` closure (line 1597), inside `async with lock:`. At line 1684, `if merge_result.success:` — insert `overnight_log_event(FEATURE_MERGED, config.batch_id, feature=name, details={"integration_branch": effective_branch}, log_path=config.overnight_events_path)` as the **first** statement inside that `if` block, before `tier = read_tier(name)` at line 1686
  - `effective_branch` is already in scope (computed at line 1674 via `_effective_base_branch(repo_path_map.get(name), integration_branches, config.base_branch)`)
  - `config.batch_id`, `config.overnight_events_path`, `name` are all in scope as closure variables
  - Do NOT wrap in `try/except` — absence of the event must unambiguously mean "never merged"
  - Do NOT add this event to the repair/ff-merge path in `_apply_feature_result`
- **Verification**: `grep -c 'FEATURE_MERGED' claude/overnight/batch_runner.py` ≥ 1 — pass if count ≥ 1. Interactive/session-dependent for placement: visual inspection of the file confirms `overnight_log_event(FEATURE_MERGED, ...)` is the first statement inside `if merge_result.success:`, before `tier = read_tier(name)`
- **Status**: [x] completed

### Task 3: Annotate merged features in render_failed_features()
- **Files**: `claude/overnight/report.py`
- **What**: Build a `merged_to_integration` set from `data.events` inside `render_failed_features()` and insert a warning line + override suggestion for any failed/paused feature that has a `feature_merged` event.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `render_failed_features(data: ReportData) -> str` starts at line 869 of `claude/overnight/report.py`
  - After the `conflict_info` set-building block (around line 908), add a `merged_to_integration: set[str] = set()` set-building loop — follow the identical pattern used for `retry_counts` at lines 895-899 and `conflict_info` at lines 902-908: iterate `data.events`, filter on `evt.get("event") == "feature_merged"`, extract `evt.get("feature", "")`, and add non-empty feature names to the set
  - Inside the `for name, fs in sorted(failed.items()):` loop, after appending the circuit breaker / retry / conflict lines (around line 926) and before the `suggestion = _suggest_next_step(error)` call at line 938:
    - If `name in merged_to_integration`: append a warning line and override the suggestion
    - Warning line: `⚠️ Feature is on the integration branch — merge succeeded but a post-merge step failed after the commit landed.`
    - Overridden suggestion text: `Investigate which post-merge step crashed (check overnight-events.log for the feature_deferred event details and error field). Do NOT re-run the feature — it is already on the integration branch. Address any missed post-merge steps manually (e.g., trigger review, update backlog item).`
    - The override replaces the value passed to `_suggest_next_step()` — or alternatively, skip the `_suggest_next_step` call and append the suggestion line directly. The simplest approach: `if name in merged_to_integration: suggestion = "<override text>"` before the suggestion append
  - `data.events` is `list[dict[str, Any]]` — already populated in `ReportData`
- **Verification**: `just test` exits 0 — pass if exit 0. (Test assertions for this task are added in Task 6.)
- **Status**: [x] completed

### Task 4: Annotate SEVERITY_BLOCKING deferrals in render_deferred_questions()
- **Files**: `claude/overnight/report.py`
- **What**: Build a `merged_to_integration` set from `data.events` inside `render_deferred_questions()` and override the "To unblock" action for any `SEVERITY_BLOCKING` deferral whose feature has a `feature_merged` event.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - `render_deferred_questions(data: ReportData) -> str` starts at line 834 of `claude/overnight/report.py`
  - `render_deferred_questions` does not currently access `data.events`. Add the same set-building loop (identical to Task 3's loop) immediately before the `for dq in sorted_deferrals:` loop at line 851
  - Inside the `for dq in sorted_deferrals:` loop, the action is determined by `dq.severity` (lines 857-862). Override the `SEVERITY_BLOCKING` action when `dq.feature in merged_to_integration`:
    - Original: `"Answer this question and re-run the feature"`
    - Override: `"Feature is on the integration branch — do NOT re-run. Investigate the post-merge failure (see error details above and overnight-events.log). Address missed post-merge steps manually (review dispatch, backlog write-back)."`
    - Non-blocking and informational severity deferrals are never annotated (these features completed normally)
  - `SEVERITY_BLOCKING` is already imported from `claude.overnight.deferral` at line 29
- **Verification**: `just test` exits 0 — pass if exit 0. (Test assertions for this task are added in Task 6.)
- **Status**: [x] completed

### Task 5: Update walkthrough.md Section 4
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Add handling guidance in Section 4 for failed features annotated with the "integration branch" warning, making clear that these must not get investigation/re-run backlog tickets.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Section 4 starts at line 259 of `skills/morning-review/references/walkthrough.md`
  - Current step 4 (line 268) asks the user to create a backlog investigation item for every failed feature
  - Add a branch before step 4: if the feature's report entry contains the text "Feature is on the integration branch", do NOT ask about creating an investigation ticket — instead:
    - State that the feature is already on the integration branch
    - Do not create a re-run or investigation ticket for the feature itself
    - Instruct: verify the feature is present on the integration branch; identify which post-merge step failed (check `overnight-events.log`); address the missed step manually (e.g., trigger review, update backlog item); advance the lifecycle manually
  - Insert this as a new numbered step or condition check before the existing step 4 prompt
  - Edit the repo copy at `skills/morning-review/references/walkthrough.md` (it is symlinked; the system deployment reads from this path)
- **Verification**: `grep -c 'integration branch' skills/morning-review/references/walkthrough.md` ≥ 1 — pass if count ≥ 1
- **Status**: [x] completed

### Task 6: Write tests for annotation behavior
- **Files**: `tests/test_report.py` (new file)
- **What**: Create a test module with four test cases covering: (1) failed feature WITH `feature_merged` event gets annotation in `render_failed_features`, (2) failed feature WITHOUT event does NOT get "integration branch" text, (3) SEVERITY_BLOCKING deferred feature WITH event gets overridden "To unblock" in `render_deferred_questions`, (4) SEVERITY_BLOCKING deferred feature WITHOUT event gets original "re-run the feature" text.
- **Depends on**: [3, 4]
- **Complexity**: complex
- **Context**:
  - `from claude.overnight.report import ReportData, render_failed_features, render_deferred_questions`
  - `from claude.overnight.state import OvernightState, OvernightFeatureStatus` — `OvernightFeatureStatus` (aliased as `OvernightFeatureState` in state.py; the actual class is `OvernightFeatureStatus` at line 62 of `claude/overnight/state.py`)
  - `from claude.overnight.deferral import DeferralQuestion, SEVERITY_BLOCKING`
  - Build `OvernightState` directly: `OvernightState(session_id="test-session", integration_branch="overnight/test")`
  - Set features dict: `state.features["feat-x"] = OvernightFeatureStatus(status="failed", error="dispatch_review raised RuntimeError")`
  - Build `ReportData`: `data = ReportData(); data.state = state; data.events = [...]`
  - `feature_merged` event dict shape: `{"event": "feature_merged", "feature": "feat-x"}`
  - `DeferralQuestion(feature="feat-x", question_id=1, severity=SEVERITY_BLOCKING, context="ctx", question="q?", pipeline_attempted="dispatch_review()")`
  - Follow the class-based test pattern from `tests/test_no_commit_classification.py`: `class TestXxx:` with `def test_yyy(self):` methods
  - Four test methods:
    1. `test_render_failed_features_annotates_merged_feature` — asserts `"Feature is on the integration branch"`, `"Do NOT re-run the feature"`, and `"overnight-events.log"` all appear in output
    2. `test_render_failed_features_no_annotation_without_merged_event` — asserts `"integration branch"` does NOT appear in output
    3. `test_render_deferred_questions_annotates_merged_blocking_deferral` — asserts `"Feature is on the integration branch"` and `"overnight-events.log"` appear and `"re-run the feature"` does NOT appear
    4. `test_render_deferred_questions_no_annotation_without_merged_event` — asserts `"Answer this question and re-run the feature"` IS present (original text preserved)
- **Verification**: `just test` exits 0 — pass if exit 0
- **Status**: [x] completed

## Verification Strategy

After all tasks complete:
1. `just test` exits 0 — all existing tests plus the four new `test_report.py` tests pass
2. `grep -c 'FEATURE_MERGED = "feature_merged"' claude/overnight/events.py` = 1
3. `grep -c 'FEATURE_MERGED' claude/overnight/batch_runner.py` ≥ 1
4. `grep -c 'integration branch' skills/morning-review/references/walkthrough.md` ≥ 1
5. Inspect `batch_runner.py` around line 1685: confirm `overnight_log_event(FEATURE_MERGED, ...)` is the first statement inside `if merge_result.success:`, before `tier = read_tier(name)`
