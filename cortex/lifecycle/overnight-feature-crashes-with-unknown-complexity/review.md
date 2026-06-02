# Review: overnight-feature-crashes-with-unknown-complexity

Cycle 1. Read-only spec-compliance and code-quality review of the 9 implementation
commits `8c44a255..4a3b1946`. All cited tests were run read-only via
`.venv/bin/python -m pytest`; the changed-file suite is 139 passing.

## Stage 1: Spec Compliance

### R1 — Normalize OOV complexity at the parser boundary, expose normalized tasks
- **Expected**: `parse_feature_plan` coerces a present-but-OOV per-task `**Complexity**`
  to `complex`, records `{task, original}` on the returned plan; parser does no logging.
  Unit test asserts `complexity == "complex"` and the original is recorded.
- **Actual**: `parser.py` adds `VALID_COMPLEXITIES = {trivial, simple, complex}`, a
  `FeaturePlan.normalized_complexities` field, and coerces OOV→`complex` while appending
  `{"task": task_num, "original": <oov>}`. `_parse_tasks` returns `(tasks, normalized)`.
  An absent field keeps the `simple` default (edge case honored). Tests
  `test_present_oov_complexity_normalizes_to_complex_and_records_original` and
  `test_absent_complexity_keeps_simple_default_and_records_nothing` pass.
- **Verdict**: PASS
- **Notes**: Parser remains pure (no event emission), correctly deferring to the caller.

### R2 — Surface every OOV normalization as a structured, report-visible event
- **Expected**: dispatch caller emits a registered event per normalized task carrying
  feature/task/original; report scanner surfaces it. `grep -c "<event>"` ≥ 1; a
  `test_report.py` test asserts the report names the feature + original value.
- **Actual**: `COMPLEXITY_NORMALIZED = "complexity_normalized"` added to `events.py`
  `EVENT_TYPES`; registered in `bin/.events-registry.md` (`grep -c` = 1). `execute_feature`
  emits one event per `feature_plan.normalized_complexities` entry via `overnight_log_event`
  to `config.overnight_events_path`. `report.render_complexity_normalized` scans
  `data.events` (= `read_events(overnight-events.log)`), de-dups by `(feature, task,
  original)`, renders a `## Complexity Normalizations (N)` section. Tests pass.
- **Verdict**: PASS
- **Notes**: Verified the implementation note — the emit uses `config.batch_id` as the
  `round` positional, matching the `log_event(event, round, ...)` signature and all sibling
  `overnight_log_event` calls in feature_executor. The emit→read→render chain is closed:
  the event lands in the same `overnight-events.log` that `read_events` consumes.

### R3 — Keep the dispatch enum guard as a backstop
- **Expected**: `resolve_model` raise and `dispatch_task` `tier is None` raise unchanged;
  a test asserts (a) the raise fires for a directly-passed unknown tier and (b) an
  end-to-end normalized plan never triggers it.
- **Actual**: `dispatch.py` is not in the changed set; the raises remain at lines 233 and
  520–522. `test_dispatch.py` adds `test_resolve_model_raises_on_directly_passed_unknown_tier`
  (asserts the `ValueError` for `"medium"`) and `test_normalized_plan_never_triggers_resolve_model_guard`
  (parses an OOV plan, confirms normalization to `complex`, then calls `resolve_model` without
  raising). Both pass.
- **Verdict**: PASS
- **Notes**: (a) covers the `resolve_model` raise; the `dispatch_task` `tier is None` raise is
  the same invariant downstream of the same `resolve_model` call and is left structurally
  intact. Acceptable coverage of the backstop intent.

### R4 — Repair every parser test that asserts an OOV complexity survives
- **Expected**: tests expecting `complexity == "moderate"` updated to `complex`; the line-526
  truncation discriminator switched to an in-vocabulary sentinel pair; suite exits 0; no
  remaining assertion expects a post-parse complexity outside `{trivial, simple, complex}`.
- **Actual**: `test_mixed_separators_all_parsed` switched `moderate`→`complex`; the two
  outline/H3 regression assertions switched `moderate`→`complex` (with explanatory comments);
  the `test_unrelated_h2_after_last_task_truncates_task_body` discriminator switched to a
  `trivial` (Task 2) / `complex` (under `## SomeOther`) sentinel pair, preserving the H2-leak
  diagnostic. `test_parser.py` exits 0; no surviving OOV assertion.
- **Verdict**: PASS

### R5 — Deterministically fail in-session dependents of a failed blocker via a sweep
- **Expected**: a pure helper over `OvernightState` transitions every non-terminal feature
  whose `intra_session_blocked_by` contains a now-`failed` feature to `failed` with reason
  `blocker_failed`; re-applies to a fixpoint; fires only on terminal `failed`. Tests assert
  the direct case and a transitive `A→B→C`.
- **Actual**: `state.sweep_blocker_failed_dependents` loops to a fixpoint, computes the
  `failed`-blocker set each pass, and `update_feature_status(..., "failed",
  error="blocker_failed")` for any non-terminal dependent (`pending`/`running`/`paused`) of a
  failed blocker. `paused` blockers do not cascade; `paused` dependents of a failed blocker
  ARE swept. Tests cover direct, transitive, paused-blocker-no-cascade, and
  paused-dependent-swept. All pass.
- **Verdict**: PASS
- **Notes**: Pure over its argument (no persistence) per spec; persistence is the caller's job.

### R6 — The sweep lets the loop terminate cleanly instead of churning
- **Expected**: the sweep drives `intra_session_blocked_by` dependents to terminal `failed` so
  `_count_pending` reaches 0 and the loop takes the clean `pending == 0` exit. Test asserts
  `_count_pending(state) == 0` after the sweep over a failed-subtree-only state.
- **Actual**: Verified the wiring directly (the flagged coverage concern). `runner.py:2563–2565`
  calls `load_state` → `sweep_blocker_failed_dependents` → `_save_state_locked` at the branch
  re-convergence point — placed OUTSIDE the `if not batch_plan_path.exists(): … else: …` block
  (same indent as the `batch_plan_path` assignment), so it runs every round on BOTH the
  batch-plan and no-batch-plan branches, after `_apply_batch_results` and before `_count_merged`
  / the merged-delta evaluation. `_count_pending` counts `pending`/`running`/`paused`; the sweep
  drives those to terminal `failed`, so the next iteration's top-of-loop `_count_pending` (line
  2229, after reloading state) reads 0 and breaks at line 2242. `test_runner.py`
  `test_pending_reaches_zero_after_sweep_over_failed_subtree` confirms `_count_pending == 0`
  post-sweep on an `A(failed)→B→C` state. Passes.
- **Verdict**: PASS
- **Notes**: The flagged R5 coverage gap (helper test does not drive the full round loop) is
  real but mitigated: the runner-level test exercises the exact runner call, and direct
  reading of runner.py confirms the call site is unconditional and correctly ordered. See
  Stage 2.

### R7 — Surface cascade casualties distinctly
- **Expected**: auto-failed dependents tagged `blocker_failed`, distinguishable from primary
  failures so one blocker + N dependents does not read as N+1 independent failures. Test
  asserts the report renders the casualty with `blocker_failed` and separates/labels it.
- **Actual**: `render_failed_features` partitions `failed` into `cascade_casualties`
  (`error == "blocker_failed"`) and `primary_failures`; primaries render as `### {name}:`
  headings, casualties render under a labelled `### Cascade casualties (blocker failed) (N)`
  subsection tagged with `(reason: blocker_failed)`.
  `test_render_failed_features_separates_blocker_failed_cascade_casualty` asserts the casualty
  is NOT a `### dependent:` heading, the primary renders ahead of the casualty section, and the
  reason tag is present. Passes.
- **Verdict**: PASS

### R8 — Resolve the dispatch path's lifecycle reads/writes against the project root
- **Expected**: the dispatch-critical plan read and criticality/tier read resolve against
  `_resolve_user_project_root()`; the remaining sibling reads/writes resolved consistently or
  enumerated as a follow-up — silent partial fixes not acceptable. Prefer passing a
  root-resolved base to `read_criticality`/`read_tier` over changing the global default.
  Test from a non-root CWD returns the declared criticality and the plan parses.
- **Actual**: `execute_feature` computes `lifecycle_base = _resolve_lifecycle_base()`
  (= `_resolve_user_project_root() / "cortex" / "lifecycle"`) and threads it through ALL
  ~12 lifecycle literals AND the sibling module-level helpers — not just the local: `_get_spec_path`,
  `_read_spec_content`, `_read_learnings`, `_read_exit_report`, and `_handle_failed_task`
  each take a `lifecycle_base` keyword and use it for every path (plan.md, exit-reports,
  progress/orchestrator-note, activity log, `mark_task_done_in_plan` writes). `read_criticality`
  is called with `lifecycle_base=lifecycle_base`; its global default is unchanged (common.py not
  modified). `read_tier` is not called in this path, so no gap. The dispatch-path test
  (`tests/test_feature_executor.py::TestRootResolvedLifecycleReads`) sets `CORTEX_REPO_ROOT` to a
  fixture root, chdirs elsewhere, runs the real parse + real `read_criticality`, and asserts
  `parse_error is False`, `complexity == "simple"`, and `criticality == "critical"` (not the
  `medium` default). Passes.
- **Verdict**: PASS
- **Notes**: Verified the implementation note — this is NOT a silent partial fix. Every
  module-level sibling helper threads `lifecycle_base`; no CWD-relative `Path("cortex/lifecycle/…")`
  literal remains in the dispatch path of `execute_feature`. The spec's preference (pass a base
  rather than change the global default) is honored.

### R9 — Close the runtime backlog-resolver gap for slug ≠ filename-stem
- **Expected**: route the slug≠stem case through canonical `resolve_item.resolve`
  (uuid/backlog_id/lifecycle_slug frontmatter); test resolves the file and emits no
  `backlog_write_failed`.
- **Actual**: `_find_backlog_item_path` adds strategy-4: on a `None` from strategy-3, call
  `_backlog_resolve(feature, backlog_dir)` and return `resolution.item` on `status == "ok"`
  (else `None`). Tests `test_resolves_when_lifecycle_slug_differs_from_stem` and
  `test_write_back_emits_no_backlog_write_failed` pass: the slug≠stem case resolves to the
  correct file and no `backlog_write_failed` is logged.
- **Verdict**: PASS
- **Notes**: Verified the implementation note — strategy-4 IS largely redundant. Strategy-3
  (`update_item._find_item`) already delegates to the canonical `resolve()` (update_item.py:135),
  whose 5-step chain includes exact `lifecycle_slug`-frontmatter matching (resolve_item.py:468–470).
  So the slug≠stem case already resolves at strategy-3; strategy-4 re-runs the identical
  `resolve()` call and can only reproduce strategy-3's result. The redundancy is benign (no
  behavior change, no wrong-file risk, fail-safe `None` on ambiguity), but it is dead code. R9's
  acceptance is genuinely satisfied regardless. Flagged as a minor cleanup in Stage 2, not a
  blocker.

### R10 — Land the plan-gen commit on the integration branch via a Python helper
- **Expected**: a Python step commits generated plan files inside the integration worktree
  (`cwd=worktree`), not the cwd-pinned orchestrator agent. Integration assertion confirms the
  commit lands on `overnight/{session_id}` and not `main`; a unit test asserts git runs with
  `cwd` = the worktree. Worktree-absent must fail safe.
- **Actual**: `_commit_round_plans_in_worktree` (+ `_resolve_feature_integration_worktree`)
  copies each feature's home-tree plan.md into its integration worktree and runs `git add` /
  `git diff --cached --quiet` / `git commit` with `cwd = worktree` and `env` stripped of
  `GIT_DIR` — mirroring `_commit_followup_in_worktree`. Home-repo features resolve to
  `state.worktree_path`; cross-repo to `state.integration_worktrees[repo]`. Absent/torn-down
  worktrees are skipped (logs `integration_worktree_missing`, never crashes, never
  `followup_commit_failed` rc=128); the home-tree copy is intentionally left for the dispatch
  path's root-resolved read. The helper is called in the round loop after the orchestrator
  returns and before batch dispatch. `orchestrator-round.md` Step 3d (prose `/commit`) is
  replaced with an explicit "Do NOT commit … the runner commits them into each feature's
  integration worktree" instruction. Tests: real-git `TestPlanCommitLandsOnIntegrationBranch`
  (commit on `overnight/{id}`, `main` HEAD unchanged, home copy remains), unit
  `test_plan_commit_runs_git_with_cwd_equal_to_worktree`, plus staged-path and absent-worktree
  fail-safe tests. All pass.
- **Verdict**: PASS
- **Notes**: Satisfies the CLAUDE.md "structural separation over prose-only enforcement"
  preference. The `integration_worktree_missing` event is already registered (reused, not new).

## Requirements Drift
**State**: detected
**Findings**:
- The R5/R6/R7 dependent-failure cascade introduces a new failure-propagation rule: a feature
  at terminal `failed` now deterministically transitions its in-session `intra_session_blocked_by`
  dependents to `failed` with reason `blocker_failed` (via an end-of-round sweep, to a fixpoint).
  `cortex/requirements/pipeline.md` "Feature Execution and Failure Handling" documents the status
  lifecycle and the fail-forward model ("one feature's failure does not block other features") but
  has no rule for failure cascading to `blocked-by` dependents. The new behavior is not reflected
  in the requirements.
**Update needed**: cortex/requirements/pipeline.md

## Suggested Requirements Update
**File**: cortex/requirements/pipeline.md
**Section**: Feature Execution and Failure Handling → Acceptance criteria
**Content**:
```
  - When a feature reaches terminal `failed`, an end-of-round sweep transitions every
    not-yet-terminal feature whose `intra_session_blocked_by` lists it to `failed` with
    reason `blocker_failed`, re-applying to a fixpoint so transitive chains resolve. A
    `paused` blocker (recoverable) does not cascade; only terminal `failed` triggers it.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `sweep_blocker_failed_dependents`,
  `_commit_round_plans_in_worktree`, `_resolve_feature_integration_worktree`,
  `render_complexity_normalized`, and `VALID_COMPLEXITIES` follow existing module idioms. The
  new event constant `COMPLEXITY_NORMALIZED` matches the `EVENT_TYPES` convention. Module-level
  helpers consistently use keyword-only `lifecycle_base` with a back-compatible default.
- **Error handling**: Appropriate, including the spec's fail-safe paths. The R5 sweep is pure
  and cannot leave partial state (caller persists via the atomic `_save_state_locked`). The R10
  worktree-absent path is robust: `None`/non-dir worktree → skip + `integration_worktree_missing`
  event; `OSError` on copy → skip; `git commit` rc≠0 → stderr warning, no crash; the whole
  helper is wrapped in a try/except at the call site. The "no `followup_commit_failed` rc=128
  against a removed worktree" edge is satisfied. `git diff --cached --quiet` correctly skips the
  empty-commit case.
- **Test coverage**: The plan's verification steps are executed; the full changed-file suite is
  139 passing. The R5 coverage concern flagged in the brief is real (the pure-helper test does
  not drive the full round loop) but adequately mitigated: `test_runner.py` adds a runner-level
  test exercising the exact `state_module.sweep_blocker_failed_dependents` call the round loop
  performs and asserting `runner._count_pending == 0`, and direct reading of `runner.py:2551–2565`
  confirms the call is unconditional on both branches and correctly ordered before the
  merged/pending evaluation. R10's real-git integration test is a strong addition.
- **Pattern consistency**: R10's helper mirrors `_commit_followup_in_worktree`
  (`cwd=worktree_path`, env without `GIT_DIR`) as the spec directs. R8 follows the existing
  `read_criticality(feature, lifecycle_base=...)` parameterization rather than mutating the
  global default. R2's report renderer follows the established "return empty string → section
  omitted" convention used by sibling `render_*` functions.
- **Minor cleanup (non-blocking)**: R9's strategy-4 in `_find_backlog_item_path` is redundant —
  strategy-3 (`_find_item`) already routes through the same canonical `resolve()` whose 5-step
  chain includes `lifecycle_slug`-frontmatter matching, so strategy-4 re-runs an identical call
  that can only reproduce strategy-3's result. It is benign (fail-safe `None` on ambiguity, no
  wrong-file risk) but dead code; consider removing it or, if kept defensively, documenting why
  it can ever differ from strategy-3. Does not affect correctness or the verdict.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
