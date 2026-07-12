# Review: 374 — Served next/advance lifecycle loop (cycle 2)

Focused re-review. Cycle 1 returned CHANGES_REQUESTED with one blocking issue
(Issue 1: Task-17a's fold dropped `feature_complete`/`merge_anchor:"review"` on
the overnight/pipeline completion paths, producing an untested metrics
regression). Everything else (R1–R18, hazards H1–H7, code quality) already
PASSED in cycle 1 and was not re-reviewed. This cycle confirms only that the
rework resolves the blocking issue soundly and introduces no new defect.

Reworked in two commits: `6cb9c08f` (re-add the `resume` routing token to
SKILL.md Step 1) and `b72710a4` (the metrics events-first re-key).

## What I verified

### 1. The metrics fix genuinely resolves Issue 1 (commit `b72710a4`)

Operator chose remedy (b): re-key completion on the events-authority signal
(`phase_transition→complete`, ADR-0025) rather than re-emit `feature_complete`.
Read `extract_feature_metrics` and `compute_aggregates` in
`cortex_command/pipeline/metrics.py`. All four required properties hold:

1. **Fold completion counts COMPLETE.** Completion detection (lines 230–237)
   now returns `None` only when a log has NEITHER a `feature_complete` row NOR
   any `phase_transition` with `to == "complete"`. A folded completion (which
   emits only `review_verdict` + `phase_transition→complete`) is therefore
   counted complete, no longer dropped as in-progress.
2. **`merge_anchor` defaults to "review" for fold completions.** When there is
   no `feature_complete` row, `final_complete` is the `phase_transition→complete`
   row (line 253), which carries no `merge_anchor`, so `final_complete.get(
   "merge_anchor", "review")` (line 266) falls to `"review"`. `compute_aggregates`
   then buckets it into `avg_phase_durations_by_anchor["review"]` (lines 1074–
   1090) — the previously-starved bucket.
3. **Duration math anchors on the completion row's `ts`.** `last_ts_str =
   final_complete["ts"]` (line 328) drives `total_duration_seconds`; for a fold
   completion that is the `phase_transition→complete` timestamp.
4. **Legacy logs are unchanged — no double-count, no regression.** The
   ordering preference is explicit: `if complete_events: final_complete =
   complete_events[-1]` (last `feature_complete`) `else: ... phase_complete_
   events[0]` (lines 250–253). A legacy log carrying BOTH a `review→complete`
   transition and a later `feature_complete` telemetry row reads
   `feature_complete` first, reproducing the historical `ts`/`merge_anchor`/
   `tasks_total` exactly. Because a feature yields exactly one record, no
   double-count is possible at extract or aggregate level.

The fix is consistent with the events-authority model (ADR-0025): completion is
now recognized off the transition the served `advance` bodies actually emit,
with the legacy telemetry row honored only as a superset carrier when present.
It is the durable, model-aligned remedy, not a stop-gap.

### 2. The new test is real and non-self-sealing

`test_extract_feature_metrics_completion_is_events_first`
(`cortex_command/pipeline/tests/test_metrics.py:2123`) calls the REAL
`extract_feature_metrics` and `compute_aggregates` (imported directly, no stub).
It pins all four properties across three fixtures: (a) fold-only —
asserts `is not None`, `merge_anchor == "review"`, `total_duration_seconds ==
300.0`, `review_to_complete == 300.0`, and that the review anchor bucket is
populated; (b) both-rows legacy — asserts `merge_anchor == "merge"`,
`task_count == 5`, and `total_duration_seconds == 600.0` (the `feature_complete`
ts, NOT the earlier transition's 300 — this is the anti-double-count / anti-
regression pin); (c) `feature_complete`-only — asserts still complete. The test
would FAIL if completion silently reverted to a `feature_complete`-only gate
(fixture (a)'s `is not None` breaks) or if the row-precedence flipped
(fixture (b)'s 600.0/"merge"/5 assertions break). Not self-sealing.

### 3. Dangling "fold report" docstrings corrected

`grep -rn 'fold report' cortex_command/` → 0. Both
`cortex_command/overnight/advance_lifecycle.py` and
`cortex_command/pipeline/review_dispatch.py` now point at
`metrics.py:extract_feature_metrics` and accurately describe the events-first
detection + `"review"` default, replacing the reference to a non-existent report.

### 4. The fold was not disturbed

`uv run pytest tests/test_fold_completion.py
tests/test_advance_status_projection_sweep.py -q` → 17 passed. The AST fold
guards and the byte-identical phase-projection sweep still hold — the metrics
re-key touched only the reader, not the write path.
`uv run pytest cortex_command/pipeline/tests/test_metrics.py -q` → 57 passed.

### 5. The `resume` SKILL.md fix is accurate (commit `6cb9c08f`)

`resume` is a genuine member of `resolve.KNOWN_STATES`
(`cortex_command/lifecycle/resolve.py:55`), and the resolver serves
`"state": "resume"` for a resumable feature (line 210); the loop handles it as a
phase-keyed envelope. The SKILL.md edit names the routing state on the
resumable-feature paragraph, restoring the literal token that Task 19's rewrite
dropped. Both canonical and `plugins/cortex-core/` mirror copies were updated
identically (dual-source parity preserved). The parity/state-coverage test
`test_state_coverage_every_known_state_has_a_routing_row` passes.

## Requirements Drift

**State**: none
**Findings**: None. The rework is a defect repair of an in-scope observability
surface plus a parity regression fix — neither is new deliberate behavior. Task
20 already recorded the served-verb / events-authority / roll-forward semantics
in `project.md`; the events-first completion re-key is the correct expression of
the already-documented ADR-0025 events-authority model, not a departure from it.
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
