# Review: remove-dead-throttled-dispatch-wrapper-keep-concurrencymanager-acquire-release

## Stage 1: Spec Compliance

### Requirement 1: Delete `throttled_dispatch()` and its export
- **Expected**: `throttled_dispatch` function removed from `throttle.py`; export removed from `__init__.py`; no live references outside historical lifecycle artifacts.
- **Actual**: `grep -c '^async def throttled_dispatch' cortex_command/overnight/throttle.py` = 0; `grep -c 'throttled_dispatch' cortex_command/overnight/__init__.py` = 0; the only remaining mention in `cortex_command/` is the spec-mandated historical-note comment at `cortex_command/overnight/throttle.py:15` (allowed/required).
- **Verdict**: PASS
- **Notes**: Historical note records deletion date `2026-05-04` and points at the lifecycle slug for revert context — satisfies spec §Technical Constraints reversibility requirement.

### Requirement 2: Delete `ConcurrencyManager.report_rate_limit()` and `report_success()`
- **Expected**: Both methods removed; brain.py:237 caller removed; `grep -rn 'report_rate_limit\|report_success' cortex_command/` = 0; tests pass.
- **Actual**: Grep returns zero matches in `cortex_command/`. `just test` (and `pytest cortex_command/{overnight,pipeline,init}/tests/`) passes — 612 passed, 1 xpassed.
- **Verdict**: PASS

### Requirement 3: Remove shrinkage state and orphaned `import time`
- **Expected**: All seven private fields removed; `stats` property removed-or-trimmed; class docstring sanitized; `import time` removed; module not mentioning "adaptive concurrency"/"sliding window".
- **Actual**: `grep -rn '_total_rate_limits|_reductions|_restorations|_rate_limit_timestamps|_window_seconds|_consecutive_successes|_successes_to_restore' cortex_command/` returns no matches; `grep -c '^import time' cortex_command/overnight/throttle.py` = 0; `grep -ci 'adaptive concurrency|sliding window' cortex_command/overnight/throttle.py` = 0. `stats` property entirely deleted (judgment call permitted by spec; Task 4 removed sole caller).
- **Verdict**: PASS
- **Notes**: Class docstring at `cortex_command/overnight/throttle.py:104-108` rewritten to describe only the surviving semaphore behavior. Permitted-judgment-call accepted: deleting `stats` outright instead of trimming was the right call given Task 4 removed the only caller.

### Requirement 4: Trim `ThrottleConfig`
- **Expected**: `backoff_base_seconds`, `backoff_max_seconds`, `rate_limit_threshold` removed.
- **Actual**: `grep -c 'backoff_base_seconds\|backoff_max_seconds\|rate_limit_threshold' cortex_command/overnight/throttle.py` = 0. Dataclass docstring at `cortex_command/overnight/throttle.py:48-54` documents only the three surviving fields.
- **Verdict**: PASS

### Requirement 5: Remove `throttle_backoff` event emission
- **Expected**: No emitter remains anywhere.
- **Actual**: `grep -rn 'throttle_backoff' cortex_command/` returns no matches. Removal happens automatically as a consequence of deleting `throttled_dispatch` (the sole emitter).
- **Verdict**: PASS

### Requirement 6: Drop `extra_fields={"throttle_stats": manager.stats}` from `save_batch_result` call
- **Expected**: `grep -c 'throttle_stats' cortex_command/overnight/orchestrator.py` = 0; tests pass.
- **Actual**: Grep = 0; the call at `cortex_command/overnight/orchestrator.py:464` is now `save_batch_result(batch_result, result_path)`. Tests pass.
- **Verdict**: PASS

### Requirement 7: Update brain.py docstring, call site, and dead import
- **Expected**: docstring rewritten; `report_rate_limit` call + guard removed; lazy `_CM` import removed; "rate limit reporting" parameter docstring rewritten; `manager` parameter signature preserved.
- **Actual**: All four greps return 0 (`throttled_dispatch`, `report_rate_limit`, `ConcurrencyManager as _CM`, `rate limit reporting`). Function docstring at `cortex_command/overnight/brain.py:196-213` correctly says "Calls `dispatch_task` directly because that is the only dispatch path the runner uses." The `manager` parameter is preserved with explanatory docstring noting it's "retained for caller-side compatibility; not used in the body." Inspect-based signature check passes.
- **Verdict**: PASS

### Requirement 8: Delete `test_dispatch_failure_infrastructure_calls_report_rate_limit`
- **Expected**: Test method removed.
- **Actual**: `grep -c 'test_dispatch_failure_infrastructure_calls_report_rate_limit' cortex_command/overnight/tests/test_brain.py` = 0.
- **Verdict**: PASS

### Requirement 9: Update `requirements/multi-agent.md:45`
- **Expected**: Old line removed; new line contains "fixed at the tier cap", "api_rate_limit", "pause the session".
- **Actual**: `grep -c 'adaptive: reduces by 1 after 3 rate-limit errors' requirements/multi-agent.md` = 0; "fixed at the tier cap" = 1; "api_rate_limit" = 2; "pause the session" = 1. Line 45 reads exactly the spec-mandated replacement.
- **Verdict**: PASS

### Requirement 10: Repoint `throttle_backoff` monitoring item in opus-4-7 research
- **Expected**: `throttle_backoff` removed; `monitor `api_rate_limit` event rates` present; `pipeline-events.log` referenced.
- **Actual**: All three greps satisfy the spec.
- **Verdict**: PASS

### Requirement 11: Rewrite throttle.py module docstring
- **Expected**: Docstring contains "tier" and "concurrency", excludes "backoff"/"adaptive"/"shrinkage"/"rate limit".
- **Actual**: AST-extracted module docstring is "Subscription-tier-bound concurrency caps for overnight orchestration. Provides ``ConcurrencyManager.acquire``/``release`` to enforce a fixed concurrency limit derived from the operator's subscription tier, plus ``load_throttle_config`` to resolve the tier and any overrides into a ``ThrottleConfig``." — passes the python3 helper.
- **Verdict**: PASS

### Requirement 12: Test suite passes
- **Expected**: `just test` exit code = 0 with no previously-passing tests now skipped.
- **Actual**: `just test` runs the three pytest suites and prints `[PASS]` for each: `pytest cortex_command/overnight/tests/` 36 passed; `pytest cortex_command/pipeline/tests/` 240 passed; `pytest cortex_command/init/tests/` ~336 (combined run reports 612 passed, 1 xpassed). No skips of previously-passing tests.
- **Verdict**: PASS

### Requirement 13: Module imports cleanly
- **Expected**: Python one-liner round-trips `ConcurrencyManager(ThrottleConfig())` and `acquire`/`release` attributes.
- **Actual**: One-liner exits 0.
- **Verdict**: PASS

### Requirement 14: Update `docs/overnight-operations.md`
- **Expected**: `grep -c 'adaptive rate-limit backoff|Adaptive downshift|prunes a 300-second sliding window|report_rate_limit()|report_success()' docs/overnight-operations.md` = 0.
- **Actual**: Literal grep = 0 (PASS). Both targeted sites are correctly rewritten: line 90 reads "Subscription-aware ConcurrencyManager enforcing tier-bound concurrency cap"; the `Adaptive downshift` paragraph at the old line 281 is replaced with a one-line note at line 281: "Rate-limit pauses are routed through the pipeline api_rate_limit → pause_session path; no in-process shrinkage."
- **Verdict**: PARTIAL
- **Notes**: A residual reference to the deleted mechanism remains at `docs/overnight-operations.md:283`: *"Picking `max_200` on a plan only capable of `max_5` throughput starves into the adaptive downshift before the first round finishes."* The lowercase phrase "adaptive downshift" escapes the R14 grep (which targets capitalized "Adaptive downshift"), so the literal acceptance check passes — but R14's intent is to remove operator-facing references to the deleted behavior in the canonical operations doc, and this sentence still describes a now-nonexistent mechanism as if it's a tuning concern. The implementer correctly flagged this. The intent was previously about the `report_rate_limit` shrinkage layer; post-deletion, picking the wrong tier no longer "starves into the adaptive downshift" — it just deadlocks the slot or pauses the session via `api_rate_limit`. Recommend rewording (e.g., "Picking `max_200` on a plan only capable of `max_5` throughput will saturate the slot semaphore and surface as session-pausing `api_rate_limit` events."). Considered non-blocking because the literal acceptance grep passes; flagged in `issues` for follow-up.

### Requirement 15: Propagate upstream `error_type` in `retry.py` pause_session branch
- **Expected**: `error_type="budget_exhausted"` literal removed; event name `retry_paused_budget_exhausted` removed.
- **Actual**: Both greps = 0. `cortex_command/pipeline/retry.py:398` now propagates `error_type=error_type`; event name at `cortex_command/pipeline/retry.py:384` is `"retry_paused_session"`. The local-scope `error_type` carries the upstream value from line 355.
- **Verdict**: PASS
- **Notes**: A trailing inline comment at `retry.py:380` still reads "budget_exhausted: session-wide condition — zero retries" — comment is now slightly stale (the branch fires for both `budget_exhausted` and `api_rate_limit` post-Task-15). Cosmetic-only; would not cause behavior drift.

### Requirement 16: Add `_SESSION_HALT_ERROR_TYPES` and propagate `result.error_type` in feature_executor
- **Expected**: Constant defined; literal `error="budget_exhausted"` replaced with propagation.
- **Actual**: `grep -c '_SESSION_HALT_ERROR_TYPES' cortex_command/overnight/feature_executor.py` = 2; literal grep = 0. Constant defined at line 69 (`_SESSION_HALT_ERROR_TYPES = ("budget_exhausted", "api_rate_limit")`) and used at line 668.
- **Verdict**: PASS

### Requirement 17: Replace `budget_exhausted` literals with set membership in orchestrator.py + propagate `paused_reason`/`abort_reason`
- **Expected**: `grep -c '"budget_exhausted"' cortex_command/overnight/orchestrator.py` = 0 (excluding format-string templates); `_SESSION_HALT_ERROR_TYPES` referenced.
- **Actual**: Literal grep = 0. `_SESSION_HALT_ERROR_TYPES` imported from feature_executor at line 51 and referenced at lines 296, 397. Write sites at lines 300, 314, 401, 406, 448, 454 all propagate `result.error` / `failed_result.error` / `batch_result.abort_reason` correctly. The `BATCH_BUDGET_EXHAUSTED` and `SESSION_BUDGET_EXHAUSTED` event-type *constants* (events.py:69-70) retain their `*_budget_exhausted` historical names but now fire for both causes; the actual cause is correctly captured in `details["reason"]`. Spec did not require renaming these event-type tags.
- **Verdict**: PASS

### Requirement 18: `report.py` morning-report distinguishes api_rate_limit pauses
- **Expected**: New branch at `report.py:435-439` extends to `api_rate_limit` with distinct text.
- **Actual**: `cortex_command/overnight/report.py:447-458` has both branches: `budget_exhausted` keeps "API budget exhausted"; new `elif` for `api_rate_limit` emits "API rate limit hit. Features in `pending` status remain queued for resume; consult `pipeline-events.log` for retry context."
- **Verdict**: PASS
- **Notes**: Implementer used `render_executive_summary`/`ReportData` rather than the spec's `render_morning_report`/`MorningReportData` — confirmed those alternate symbols don't exist in `report.py`; the agent matched the actual renderer. Acceptable.

### Requirement 19: `runner.py` distinguishes api_rate_limit in user-facing notifications and round-loop check
- **Expected**: Notification branch and round-loop check both extend to `api_rate_limit`; "API rate limit" present.
- **Actual**: `cortex_command/overnight/runner.py:1602-1614` notification has both branches with distinct text. `cortex_command/overnight/runner.py:2073-2086` round-loop check uses `state.paused_reason in ("budget_exhausted", "api_rate_limit")` (inlined tuple — permitted by spec/plan); print message is cause-agnostic "Session paused — stopping round loop"; `details={"reason": state.paused_reason}` propagates the actual cause.
- **Verdict**: PASS
- **Notes**: Implementer judgment to inline the tuple rather than import `_SESSION_HALT_ERROR_TYPES` is consistent with existing literal-comparison style in runner.py. Cause-agnostic round-loop print is permitted per plan §Veto Surface.

## Requirements Drift

**State**: none
**Findings**:
- None — implementation matches all stated requirements, and the spec already includes a corresponding edit to `requirements/multi-agent.md:45` (Task 5/R9) that brings the requirements doc in line with the new tier-cap-only behavior. The pause-reason propagation chain (R15-R19) is consistent with `requirements/pipeline.md:128` ("Graceful degradation: Budget exhaustion and rate limits pause the session rather than crashing it") and `requirements/multi-agent.md:63` ("On `budget_exhausted` or `api_rate_limit`: pause the entire session"). No new behavior emerges that isn't reflected in the requirements docs.

**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `_SESSION_HALT_ERROR_TYPES` follows the module-private SCREAMING_SNAKE_CASE convention used elsewhere (`_TIER_DEFAULTS`, etc.). Event name `retry_paused_session` is generic-but-cause-tagged, matching the existing `retry_paused_for_human` naming style.
- **Error handling**: Appropriate. The `report.py` branches preserve the existing `lines.append(...)` shape; the `runner.py` notification branches preserve the existing try/except wrapper at runner.py:1622. Orchestrator state-write failures continue to be swallowed via the existing `pass  # Don't let state-write failure ...` pattern.
- **Test coverage**: Plan verification steps executed. Per-task acceptance greps run clean. `just test` passes (612 passed, 1 xpassed across the three test suites). The new test `test_morning_report_distinguishes_api_rate_limit_pause` at `cortex_command/overnight/tests/test_report.py:291-333` exercises both branches and includes a regression guard for the pre-existing `budget_exhausted` path. Task 13's fixture rename (`throttle_stats` → `extra_diagnostic`) keeps round-trip coverage and removes archaeological vocabulary as planned. Dual-source mirror at `plugins/cortex-overnight-integration/skills/overnight/SKILL.md` and canonical `skills/overnight/SKILL.md` are byte-identical.
- **Pattern consistency**: Follows existing project conventions. The historical-note comment at `cortex_command/overnight/throttle.py:15-20` matches the spec template format and the project's reversibility-comment pattern. The `_SESSION_HALT_ERROR_TYPES` constant is correctly placed at module scope in `feature_executor.py` (per plan §Veto Surface decision). The `paused_reason` propagation chain follows the existing `phase`/`status` field-propagation idiom in `OvernightState`.

### Minor cosmetic notes (non-blocking)

- `retry.py:380` inline comment still reads "budget_exhausted: session-wide condition — zero retries" — true for both `budget_exhausted` AND `api_rate_limit` now, but the comment names only one cause. Recommend updating to "session-halting cause (budget_exhausted or api_rate_limit) — zero retries" or similar; comment-only, no behavioral effect.
- `docs/overnight-operations.md:283` references "the adaptive downshift" — flagged in R14 above. Recommend rewording to remove the dangling pointer to the deleted mechanism.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["docs/overnight-operations.md:283 still references 'the adaptive downshift' (lowercase) — escapes R14 grep but describes the deleted mechanism; recommend rewording", "cortex_command/pipeline/retry.py:380 inline comment names only 'budget_exhausted' but the branch now fires for both budget_exhausted and api_rate_limit; cosmetic only"], "requirements_drift": "none"}
```
