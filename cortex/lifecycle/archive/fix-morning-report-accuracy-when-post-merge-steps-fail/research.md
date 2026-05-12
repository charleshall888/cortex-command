# Research: Fix morning report accuracy when post-merge steps fail

## Codebase Analysis

### Files that will change

1. **`claude/overnight/events.py`**
   - Add `FEATURE_MERGED = "feature_merged"` constant (in the constants block)
   - Add to the `EVENT_TYPES` tuple — required before any call to `overnight_log_event(FEATURE_MERGED, ...)`, which raises `ValueError` on unregistered types

2. **`claude/overnight/batch_runner.py`** — two insertion points:
   - **`_accumulate_result`** (~line 1684): first statement inside `if merge_result.success:`, before `read_tier()`, `requires_review()`, `dispatch_review()`. This is the primary concurrent execution path.
   - **`_apply_feature_result` — repair/ff-merge path** (~line 1244): immediately after `ff_result.returncode == 0` in the `repair_completed` branch, before any other calls. This path does a fast-forward merge (`git merge --ff-only`) via subprocess — currently logs `TRIVIAL_CONFLICT_RESOLVED` or `REPAIR_AGENT_RESOLVED` but no `FEATURE_MERGED`. Lower risk (cleanup_worktree is wrapped in try/except pass), but still needs the event for completeness.

3. **`claude/overnight/report.py`**
   - **`render_failed_features()`** (~line 869): build a set of feature names with `feature_merged` events from `data.events`; annotate matching features with "merged to integration branch — failure in post-merge processing" and a distinct suggested action
   - **`render_deferred_questions()`** (critical gap): the dispatch_review crash path leaves features as `deferred` (not `failed`/`paused`). `render_failed_features()` only iterates `fs.status in ("failed", "paused")` — a dispatch_review crash would never appear there. The annotation must also cover features appearing in `render_deferred_questions()` that have a `feature_merged` event.

4. **`skills/morning-review/references/walkthrough.md`** — Section 4 (~lines 259-283)
   - The walkthrough reads from the pre-rendered `lifecycle/morning-report.md`, NOT from events or state directly. No new event queries are needed in the walkthrough.
   - Required change: prose clarification for features annotated as "merged — post-merge crash" — change suggested action from "create investigation ticket / investigate and retry" to reflect that the merge already landed ("verify integration branch and advance lifecycle if merge is good").

### Relevant existing patterns

**Event logging** (`overnight_log_event` call style):
```python
overnight_log_event(
    FEATURE_MERGED,
    config.batch_id,
    feature=name,
    details={"integration_branch": config.integration_branch},
    log_path=config.overnight_events_path,
)
```
Follows the same signature as `FEATURE_COMPLETE`. Fields: `v`, `ts`, `event`, `session_id`, `round`, `feature`, `details` (all optional except event/ts/v).

**Event format in `overnight-events.log`** (JSONL):
```json
{"v": 1, "ts": "<ISO8601>", "event": "feature_merged", "session_id": "...", "round": 1, "feature": "...", "details": {"integration_branch": "overnight/..."}}
```

**Set-building pattern** (already used in `render_failed_features` for retry counts and conflict info):
```python
merged_to_integration: set[str] = set()
for evt in data.events:
    if evt.get("event") == "feature_merged":
        feat = evt.get("feature", "")
        if feat:
            merged_to_integration.add(feat)
```
`data.events` is the session-level `overnight-events.log` (via `read_events(events_path)` at ReportData construction). **Not** per-feature `lifecycle/{feature}/events.log` files — those are separate and used only by `render_pending_drift`.

### Integration points and dependencies

- `overnight_log_event` validates against `EVENT_TYPES` — `events.py` must be updated before `batch_runner.py` change goes live
- `_accumulate_result` is a closure inside `run_batch()`; it captures `config`, `batch_result`, `lock`, etc. All required params (`config.batch_id`, `name`, `config.overnight_events_path`) are in scope
- The `if merge_result.success:` block is inside `async with lock:` — no lock interleaving between the event write and the subsequent post-merge steps
- `render_failed_features()` takes only `data: ReportData` — no new parameters needed since `data.events` already carries the full session events log
- The dispatch_review crash path writes `FEATURE_DEFERRED` and appends to `batch_result.features_deferred` — features here appear in `render_deferred_questions()`, not `render_failed_features()`

### Conventions to follow

- Event constant: `SCREAMING_SNAKE_CASE` name, `"snake_case"` string value; both the constant and `EVENT_TYPES` entry must be added
- Do not wrap the `FEATURE_MERGED` write in `try/except` — absence of the event must mean "never merged"; silently swallowing the write defeat the WAL guarantee
- The `details` dict should include `"integration_branch"` to distinguish from a remote push (merge is to the local integration worktree, not necessarily to remote)
- Test patterns: `test_report.py` uses `_pytest_make_data(features)` + `data.events = [...]` + assertion on rendered output; `test_batch_runner.py` uses `patch.object(batch_runner_module, "overnight_log_event")`
- Walkthrough is the repo-side file at `skills/morning-review/references/walkthrough.md` (symlinked; edit the repo copy)

---

## Web Research

### Prior art and reference implementations

**Write-Ahead Log (WAL) pattern** is the direct prior art. Sequence: *write event to durable log first, then perform the action*. Presence in the log = committed state, regardless of what crashes afterward. Absence = never started. This maps precisely to writing `FEATURE_MERGED` before any post-merge step: if the process crashes during post-merge, the log contains the merge event and absence of a post-merge-complete event — an unambiguous record. ([architecture-weekly.com](https://www.architecture-weekly.com/p/the-write-ahead-log-a-foundation), PostgreSQL WAL docs)

**Event Sourcing** (Azure Architecture Center): "Saving an event is a single operation — it is inherently atomic." Post-merge steps become subscribers of that event. If a subscriber fails, the core state (merge happened) is already durable. The morning report is a derived projection of the event store, and must respect the merge event as authoritative state. ([learn.microsoft.com/azure/architecture/patterns/event-sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing))

**Tekton Pipelines — `FailureIgnored` reason code**: Direct production analog. When a PipelineTask is marked `onError: continue`, a failed TaskRun gets `status: False, reason: FailureIgnored`. The PipelineRun message explicitly surfaces: `"Tasks Completed: 1 (Failed: 1 (Ignored: 1))"`. This is named-status annotation for partial failures in pipeline reports — exactly the pattern needed here. ([tekton.dev/docs/pipelines](https://tekton.dev/docs/pipelines/pipelines/))

**Jenkins `post` section**: Main pipeline stages and post-section are separate. Post-section failures don't automatically reclassify the build result. The build reflects the main stages; post-section failures are captured separately. ([jenkins.io/doc/pipeline/tour/post](https://www.jenkins.io/doc/pipeline/tour/post/))

**Empirical CI/CD research** (arXiv:2504.11839, April 2025): "Code merge and product release serve as more effective milestones for process optimization and risk control." Pre-merge failures are owned by the developer; post-merge failures shift responsibility to the organization/infrastructure. Labeling a post-merge crash as a feature failure misattributes responsibility.

### Known patterns and anti-patterns

**Patterns to apply:**
- Write-event-first / log-before-action: `FEATURE_MERGED` must be the first write after `merge_result.success`, before any post-merge step
- Named reason codes for partial failures: "merged to integration branch — post-merge crash" should be a distinct classification in the report, not a subvariant of the generic failure message
- Projection from event log: report derives status by scanning event log, not by trusting process exit code alone

**Anti-patterns to avoid:**
- Trusting process exit code as the sole state indicator — the core anti-pattern being fixed
- Late annotation: writing the event after post-merge steps complete (or only on success) defeats the WAL guarantee
- Conflating infrastructure failures with feature failures: post-merge crashes are an infrastructure responsibility, not a feature failure

---

## Requirements & Constraints

*(From `requirements/pipeline.md` and `requirements/project.md`)*

**Feature status lifecycle** (must-have): `pending → running → merged` (success path); `running → paused` (recoverable); `running → deferred` (ambiguous/human decision); `running → failed` (unrecoverable). A feature on the `merged` path being classified as `failed` is a mis-classification against the defined lifecycle.

**Audit trail**: `lifecycle/pipeline-events.log` is the designated append-only JSONL audit record. Writing `FEATURE_MERGED` here is aligned with this mechanism. Note: the session-level log is `overnight-events.log`; per-feature `lifecycle/{feature}/events.log` is separate and not the target for this event.

**Sole writer constraint**: `batch_runner.py` is the sole authorized writer to `events.log`. No other process (review dispatcher, separate script) should write `FEATURE_MERGED`.

**Atomicity**: All state writes use tempfile + `os.replace()`. The `overnight_log_event` plain `open(..., "a")` write is not atomic against OS-level crashes (power loss, OOM), but handles clean crashes (exceptions) correctly — which covers the post-merge exception case being fixed.

**Integration branch persistence**: `overnight/{session_id}` branches persist after session completion and are not auto-deleted. Git history is a valid fallback at morning-review time, but the events log approach does not depend on it.

**Morning report commit placement**: The morning report commit lands on local `main`; artifact commits land on the integration branch. This is stable — no change needed here.

**File-based state**: No database or server. Any solution must use existing file artifacts (events.log, integration branch git history). The events log approach is fully aligned.

**Morning = strategic review, not debugging sessions** (project.md philosophy): The morning report must accurately surface what happened so the human does not need to do forensic investigation. Misclassifying merged features as failed violates this principle.

---

## Tradeoffs & Alternatives

### Alternative A: Events log approach (recommended)

Write `FEATURE_MERGED` to `overnight-events.log` immediately after `merge_result.success`, before any post-merge step. `render_failed_features()` and `render_deferred_questions()` build a set from `data.events` and annotate accordingly.

**Pros:**
- Idiomatic — fits existing forensic event log pattern exactly; `read_events()` and `data.events` already in place
- Durable: append-only file survives post-merge crashes
- Zero new infrastructure: `EVENT_TYPES`, `overnight_log_event`, `read_events`, `ReportData.events` all exist
- Backward-compatible: old sessions lack the event; absence = no annotation (correct behavior for historical failures)
- Works for report regeneration: same events log → same annotation on any replay

**Cons:**
- Introduces `feature_merged` alongside `feature_complete` — semantics distinction must be documented (merged-but-post-merge-not-done vs. fully-complete)
- `open(..., "a")` is not atomic against hardware-level crashes; truncated final line degrades gracefully (JSONDecodeError caught by `read_events`)
- Must register constant in `events.py` before deployment

### Alternative B: Git branch inspection

`report.py` does `git log <integration_branch>..HEAD` to check if failed feature commits appear on the integration branch.

**Pros:** Ground truth — git is authoritative; works retroactively for historical sessions

**Cons:**
- Introduces subprocess calls to `report.py` (currently has none for git state)
- Integration worktree may be cleaned up by morning; integration branch may be merged and deleted
- Fragile in the walkthrough context (which is a prompt document, not Python code)
- No durability on report regeneration in a different environment
- False negative risk: commits not findable after branch cleanup

### Alternative C: Hybrid (event + git fallback)

Write event AND do git inspection as fallback for historical sessions.

**Cons:** All cons of B plus all work of A; marginal value only for historical sessions that already had the bug.

### Recommended: Alternative A

Events log approach, applied to both `_accumulate_result` and the `_apply_feature_result` repair path. Annotation in both `render_failed_features()` and `render_deferred_questions()`.

---

## Adversarial Review

### Critical gap: dispatch_review crash leaves feature as `deferred`, not `failed`

When `dispatch_review` throws in `_accumulate_result`, the `except Exception` handler writes `FEATURE_DEFERRED` and appends to `batch_result.features_deferred`. The feature ends up with status `deferred` in the state — **not** `failed` or `paused`. `render_failed_features()` only iterates `fs.status in ("failed", "paused")` — the originally reported bug case would never appear there. The `FEATURE_MERGED` event annotation must also be applied in `render_deferred_questions()`. Without this, the implementation can write the event correctly and never produce an annotation.

### Three merge paths, not two

`_apply_feature_result` has a repair/fast-forward path (`ff_result.returncode == 0`) that merges via subprocess (`git merge --ff-only`) — currently no `FEATURE_MERGED` event is written there. The post-merge risk on this path is lower (cleanup_worktree is try/except pass; review_result=None so dispatch_review never called), but the event should still be written for completeness.

### ValueError propagation risk

If `FEATURE_MERGED` is not registered in `EVENT_TYPES` when `overnight_log_event(FEATURE_MERGED, ...)` is called, a `ValueError` propagates out of `_accumulate_result` inside `async with lock:`. This could crash the feature's execution slot. Mitigation: register the constant in `events.py` as part of the same change — never deploy the `batch_runner.py` change without it.

### Do not wrap in try/except

The value of writing `FEATURE_MERGED` before post-merge steps is precisely that its absence is meaningful (merge never happened). Wrapping the write in `try/except` and silently continuing would produce false negatives — a failed write looks identical to "merge never happened" in the events log. If the write fails, the exception should propagate.

### Walkthrough reads from rendered report, not events

Section 4 of the walkthrough reads from the pre-rendered `lifecycle/morning-report.md`. It does not query events or state directly. The walkthrough change is purely prose: update the suggested action for features annotated as "merged — post-merge crash" (do not suggest creating an investigation backlog ticket; instead suggest verifying the integration branch).

### `data.events` vs. per-feature events logs

`data.events` is the session-level `overnight-events.log`. Per-feature `lifecycle/{feature}/events.log` files are separate and used only by `render_pending_drift`. The `FEATURE_MERGED` event must be written to `config.overnight_events_path` (the session log), and the set-building in `render_*` functions must read from `data.events`. If these are confused in implementation, the event is never found.

### Event write records integration branch commit, not remote push

`merge_result.success = True` means the feature merged to the local integration branch in the integration worktree — not necessarily pushed to remote. The `details` dict in the event and the annotation wording should say "merged to integration branch" to avoid implying a remote push occurred.

---

## Open Questions

- **Deferred feature annotation UX**: When a feature appears in `render_deferred_questions()` and has a `feature_merged` event, should it be annotated the same way as in `render_failed_features()` (inline annotation), or should there be a separate "merged but deferred" section? The spec phase should decide the exact UX for the deferred-plus-merged case.
- **repair_completed path event details**: The repair path (ff-merge) writes a different event chain (`TRIVIAL_CONFLICT_RESOLVED`/`REPAIR_AGENT_RESOLVED`) — should the `feature_merged` event include a flag indicating it was via repair rather than direct merge? Probably no — the distinction is already in the prior events — but spec should confirm.
