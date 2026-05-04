# Plan: Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release

## Overview

Delete the dead `throttled_dispatch` wrapper and its rate-limit-reactive shrinkage layer in `cortex_command/overnight/throttle.py` while preserving `ConcurrencyManager.acquire`/`release` and the tier cap. Then thread `paused_reason="api_rate_limit"` end-to-end through the pipeline retry path, feature executor, orchestrator, morning report, and runner notifications so post-deletion 429-induced session pauses surface to operators with the correct cause label instead of the latent `"budget_exhausted"` mislabel. Decomposition prefers many small per-file tasks over a single mega-task because the deletion bundle and the pause-reason refactor touch disjoint files in mostly independent ways — a final acceptance sweep validates the whole.

> Note on line numbers: spec.md was authored 2026-04-29 and several files have drifted. Each task's **Context** field cites both the spec line range (authoritative for intent) and the current actual location (for the implementer to edit). Spec confusion between orchestrator.py and runner.py for the `1949/1957` sites is corrected here.

## Tasks

### Task 1: Update brain.py — delete report_rate_limit guard, lazy import, and rewrite docstrings
- **Files**: `cortex_command/overnight/brain.py`
- **What**: Delete the `manager.report_rate_limit()` call and its surrounding `infrastructure_failure` guard, delete the `ConcurrencyManager as _CM` lazy import (sole consumer was the deleted call), and rewrite both the function docstring and the `manager` parameter docstring to remove references to `throttled_dispatch`, the "deadlock at MAX_5" rationale, and "rate limit reporting" semantics.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R7. Spec cites brain.py:194-196 (function docstring), 204 (param docstring), 210-211 (lazy import), 237 (call). Current locations after drift: function docstring at 198-200 (lines: `Calls dispatch_task directly (not throttled_dispatch) ... would deadlock at MAX_5`), param docstring at 208 (`manager: Optional ConcurrencyManager for rate limit reporting.`), lazy import at 215 (`from cortex_command.overnight.throttle import ConcurrencyManager as _CM`), call site at 240-241 (`if result.error_type == "infrastructure_failure" and manager is not None:` then `manager.report_rate_limit()`). The `manager` parameter stays on `request_brain_decision` for caller-side compatibility per spec Open Question #4 resolution; only the body usage is removed. New docstring should explain `request_brain_decision` calls `dispatch_task` directly because that is the only dispatch path the runner uses (the wrapper alternative no longer exists). Per Edge Cases section of spec, the deleted guard fires on `infrastructure_failure` (CLIConnectionError), not 429s — this is documented in the spec's Edge Cases section and need not be commented in code.
- **Verification**: `grep -c 'throttled_dispatch' cortex_command/overnight/brain.py` = 0 AND `grep -c 'report_rate_limit' cortex_command/overnight/brain.py` = 0 AND `grep -c 'ConcurrencyManager as _CM' cortex_command/overnight/brain.py` = 0 AND `grep -c 'rate limit reporting' cortex_command/overnight/brain.py` = 0 AND `python3 -c 'import inspect; from cortex_command.overnight.brain import request_brain_decision; assert "manager" in inspect.signature(request_brain_decision).parameters'` exits 0.
- **Status**: [x] completed

### Task 2: Delete the wrapper-only test in test_brain.py
- **Files**: `cortex_command/overnight/tests/test_brain.py`
- **What**: Delete the test method `test_dispatch_failure_infrastructure_calls_report_rate_limit` in full.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R8. Currently at test_brain.py:248-265. The test exclusively exercises `report_rate_limit()` invocation via mock; deleting the underlying method (Task 3) makes this test meaningless. Deleting it here unblocks Task 3's `grep -rn 'report_rate_limit' cortex_command/` acceptance gate, which would otherwise still hit this file. Pure deletion — no replacement.
- **Verification**: `grep -c 'test_dispatch_failure_infrastructure_calls_report_rate_limit' cortex_command/overnight/tests/test_brain.py` = 0.
- **Status**: [x] completed

### Task 3: Delete throttled_dispatch and supporting state from throttle.py + remove from __init__ exports
- **Files**: `cortex_command/overnight/throttle.py`, `cortex_command/overnight/__init__.py`
- **What**: Delete `throttled_dispatch()`, `ConcurrencyManager.report_rate_limit()`, `ConcurrencyManager.report_success()`, the entire shrinkage state in `__init__` (`_total_rate_limits`, `_reductions`, `_restorations`, `_rate_limit_timestamps`, `_window_seconds`, `_consecutive_successes`, `_successes_to_restore`), and the `ThrottleConfig` fields `backoff_base_seconds`, `backoff_max_seconds`, `rate_limit_threshold`. Delete the `stats` property entirely (no caller will exist after Task 4 lands — the orchestrator was its sole consumer). Rewrite the module-level docstring to describe the post-deletion module purpose (tier-bound concurrency caps via `ConcurrencyManager.acquire`/`release` plus tier resolution via `load_throttle_config`); the new docstring must contain "tier" and "concurrency" and must NOT contain backoff/adaptive/shrinkage/"rate limit" vocabulary. Rewrite the `ConcurrencyManager` class docstring to remove "adaptive concurrency" / "sliding window" language. Remove the orphaned `import time` (sole consumer was `report_rate_limit`). Add a 5-line "Historical note" comment block near the top of the file referencing the deletion. Use the spec template's `<YYYY-MM-DD>` placeholder and substitute the actual deletion-commit date at implementation time (run `date -u +%Y-%m-%d` when authoring the comment, do not paste a literal date from the plan example). Example shape: `# Historical note: an adaptive rate-limit-backoff wrapper (throttled_dispatch) was deleted in <YYYY-MM-DD> after evidence showed it was never wired into the live dispatch path. If rate-limit-induced session pauses become a problem in production, see git log for the deletion commit and lifecycle/remove-dead-throttled-dispatch-wrapper-keep-concurrencymanager-acquire-release/ for context.` Delete the `throttled_dispatch` entry from `__init__.py:58` exports.
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**: Spec R1, R2, R3, R4, R5, R11 plus the reversibility-comment requirement from spec §Technical Constraints. Current line map: `import time` at throttle.py:11; `ThrottleConfig` dataclass at 45-62 with backoff fields at 60-62 and their docstrings at 52-54; `ConcurrencyManager` class at 107-199 (`__init__` 117-132, `current_concurrency` property 135-137, `stats` property 140-148, `acquire` at 150, `release` at 154, `report_rate_limit` 158-183, `report_success` 185-199); `throttled_dispatch` at 206-271 with `throttle_backoff` event emission at 261. KEEP unchanged: `SubscriptionTier` enum (25-30), `_TIER_DEFAULTS` (33-37), `current_concurrency` property (135-137), `acquire` (150), `release` (154), `load_throttle_config()` (65-100). The `throttle_backoff` event lives only inside `throttled_dispatch` so its emission is removed automatically by deleting that function. Deletion order within the file does not matter; all changes are self-contained.
- **Verification**: `grep -c '^async def throttled_dispatch' cortex_command/overnight/throttle.py` = 0 AND `grep -c 'throttled_dispatch' cortex_command/overnight/__init__.py` = 0 AND `grep -rn 'throttled_dispatch' cortex_command/ tests/ claude/ docs/` returns no matches outside historical lifecycle/research artifacts AND `grep -rn 'report_rate_limit\|report_success' cortex_command/` = 0 AND `grep -rn '_total_rate_limits\|_reductions\|_restorations\|_rate_limit_timestamps\|_window_seconds\|_consecutive_successes\|_successes_to_restore' cortex_command/` = 0 AND `grep -c '^import time' cortex_command/overnight/throttle.py` = 0 AND `grep -c 'backoff_base_seconds\|backoff_max_seconds\|rate_limit_threshold' cortex_command/overnight/throttle.py` = 0 AND `grep -ci 'adaptive concurrency\|sliding window' cortex_command/overnight/throttle.py` = 0 AND `grep -rn 'throttle_backoff' cortex_command/` returns no matches outside historical artifacts AND `python3 -c 'import ast,sys; m = ast.parse(open("cortex_command/overnight/throttle.py").read()); d = ast.get_docstring(m) or ""; sys.exit(0 if ("tier" in d.lower() and "concurrency" in d.lower() and not any(x in d.lower() for x in ("backoff","adaptive","shrinkage","rate limit"))) else 1)'` exits 0 AND `python3 -c 'from cortex_command.overnight import throttle; from cortex_command.overnight.throttle import ConcurrencyManager, SubscriptionTier, ThrottleConfig, load_throttle_config; m = ConcurrencyManager(ThrottleConfig()); assert hasattr(m, "acquire") and hasattr(m, "release")'` exits 0.
- **Status**: [x] completed

### Task 4: Drop throttle_stats extra_fields from orchestrator.save_batch_result call
- **Files**: `cortex_command/overnight/orchestrator.py`
- **What**: Drop the `extra_fields={"throttle_stats": manager.stats}` argument from the `save_batch_result(batch_result, result_path, ...)` call. After Task 3 deletes `ConcurrencyManager.stats`, this argument would raise `AttributeError`; this task removes the read.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R6. Current location: orchestrator.py:461 (spec said line 449). The current full line is: `save_batch_result(batch_result, result_path, extra_fields={"throttle_stats": manager.stats})`. After this task: `save_batch_result(batch_result, result_path)`. Per research §Additional load-bearing call site, no other reader of the `throttle_stats` JSON field exists in dashboard or morning report (verified). Touch only this single line — Task 9 will handle the other orchestrator.py changes (`paused_reason`/`abort_reason` propagation).
- **Verification**: `grep -c 'throttle_stats' cortex_command/overnight/orchestrator.py` = 0.
- **Status**: [x] completed

### Task 5: Update requirements/multi-agent.md adaptive-shrinkage acceptance criterion
- **Files**: `requirements/multi-agent.md`
- **What**: Replace the line that states "Concurrency limit is 1–3 agents, adaptive: reduces by 1 after 3 rate-limit errors within 5 minutes, restores after 10 consecutive successes" with the spec-mandated replacement: "Concurrency limit is 1–3 agents, fixed at the tier cap (`SubscriptionTier`-bound). Rate limits surface via the pipeline `api_rate_limit` error type and pause the session per the Model Selection Matrix."
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R9. Currently at requirements/multi-agent.md:45 (verified). This is the load-bearing acceptance criterion of the must-have "Parallel Dispatch" requirement; without this edit the requirements doc and code drift on a must-have. Bullet indentation is `  - ` (two-space prefix per existing list style); preserve indentation.
- **Verification**: `grep -c 'adaptive: reduces by 1 after 3 rate-limit errors' requirements/multi-agent.md` = 0 AND `grep -c 'fixed at the tier cap' requirements/multi-agent.md` ≥ 1 AND `grep -c 'api_rate_limit' requirements/multi-agent.md` ≥ 1 AND `grep -c 'pause the session' requirements/multi-agent.md` ≥ 1.
- **Status**: [x] completed

### Task 6: Update docs/overnight-operations.md throttle row + adaptive downshift paragraph
- **Files**: `docs/overnight-operations.md`
- **What**: Rewrite the table row at line 90 to drop "adaptive rate-limit backoff" — replace the row's value with `Subscription-aware ConcurrencyManager enforcing tier-bound concurrency cap`. Delete the entire "Adaptive downshift" paragraph at line 281 and replace with a one-line note: `Rate-limit pauses are routed through the pipeline api_rate_limit → pause_session path; no in-process shrinkage.`
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R14. Currently lines 90 (table row reading `| `throttle.py` | Subscription-aware `ConcurrencyManager` with adaptive rate-limit backoff |`) and 281 (paragraph reading `Adaptive downshift: `report_rate_limit()` prunes a 300-second sliding window; after 3 rate-limit events the effective concurrency drops by 1 (floor of 1). `report_success()` restores the shift after 10 consecutive successes. The escalation ladder itself (haiku → sonnet → opus) does not downgrade.`). docs/overnight-operations.md is the canonical operator-facing documentation per project CLAUDE.md ("Overnight docs source of truth: docs/overnight-operations.md owns the round loop and orchestrator behavior"). Preserve surrounding markdown structure (table column delimiters at line 90; paragraph spacing at 281).
- **Verification**: `grep -c 'adaptive rate-limit backoff\|Adaptive downshift\|prunes a 300-second sliding window\|report_rate_limit()\|report_success()' docs/overnight-operations.md` = 0.
- **Status**: [x] completed

### Task 7: Repoint throttle_backoff monitoring item in opus-4-7 research
- **Files**: `research/opus-4-7-harness-adaptation/research.md`
- **What**: Replace the bullet at line 195 referencing "monitor `throttle_backoff` event rates post-migration for one week" with text that points at `api_rate_limit` events in `pipeline-events.log`. New bullet text: "Mitigation: monitor `api_rate_limit` event rates in `pipeline-events.log` post-migration for one week."
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R10. Currently the line at research/opus-4-7-harness-adaptation/research.md:195 reads `- **Trade-offs**: We may miss non-prompt regressions (e.g., if 4.7's rate-limit signature differs from 4.6 and our adaptive throttler mis-classifies). Mitigation: monitor `throttle_backoff` event rates post-migration for one week.` Update only the "Mitigation:" sentence — preserve the leading "- **Trade-offs**:" framing and the preceding clause about rate-limit signatures (the "adaptive throttler" reference there describes pre-deletion observed behavior in the migration context and is fine as historical narrative).
- **Verification**: `grep -c 'throttle_backoff' research/opus-4-7-harness-adaptation/research.md` = 0 AND `grep -c 'monitor .api_rate_limit. event rates' research/opus-4-7-harness-adaptation/research.md` ≥ 1 AND `grep -c 'pipeline-events.log' research/opus-4-7-harness-adaptation/research.md` ≥ 1.
- **Status**: [x] completed

### Task 8: Propagate upstream error_type in retry.py pause_session branch + update event-name assertion in test_escalation.py
- **Files**: `cortex_command/pipeline/retry.py`, `cortex_command/pipeline/tests/test_escalation.py`
- **What**: At the `pause_session` branch (`elif recovery_path == "pause_session":`), replace the hardcoded `error_type="budget_exhausted"` keyword in the `RetryResult(...)` construction with `error_type=error_type` so the upstream-classified value (either `"budget_exhausted"` or `"api_rate_limit"` per the local `error_type` variable from line 355) propagates downstream. Replace the event-name string `"retry_paused_budget_exhausted"` with the generic `"retry_paused_session"` in the `log_event(...)` call — the actual upstream error type is already recorded in the existing `"error_type"` field in that same dict. In `test_escalation.py`, update the existing assertion at line 684 (`pause_events = [e for e in events if e.get("event") == "retry_paused_budget_exhausted"]`) to match the new event name `"retry_paused_session"`, and rename the surrounding test method `test_budget_exhausted_logs_retry_paused_budget_exhausted_event` (line 656) to `test_budget_exhausted_logs_retry_paused_session_event` to keep the test name aligned with what it asserts. The test still exercises the `budget_exhausted` cause; only the event-name string changes.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R15. Current line locations: retry.py line 379 (`elif recovery_path == "pause_session":`), line 384 (`"event": "retry_paused_budget_exhausted"`), line 387 (`"error_type": error_type` — already correctly propagating in the log dict), line 398 (`error_type="budget_exhausted"` in the RetryResult). The local `error_type` variable is set at line 355 from `result.error_type or "unknown"` and ERROR_RECOVERY classification at line 356 routes both `"budget_exhausted"` and `"api_rate_limit"` to `pause_session` per `dispatch.py:246`. The session-halting set (Task 9) treats both as halting, so propagating the actual value is safe and required for downstream label fidelity. test_escalation.py:656 names the test method after the old event string and line 684 filters log events by the literal — the test must move with the rename or `just test` exits non-zero. Per spec Non-Requirements, this counts as "modifying existing tests," not introducing new ones.
- **Verification**: `grep -c 'error_type="budget_exhausted"' cortex_command/pipeline/retry.py` = 0 AND `grep -c 'retry_paused_budget_exhausted' cortex_command/pipeline/retry.py` = 0 AND `grep -c 'retry_paused_budget_exhausted' cortex_command/pipeline/tests/test_escalation.py` = 0 AND `grep -c 'retry_paused_session' cortex_command/pipeline/tests/test_escalation.py` ≥ 1.
- **Status**: [x] completed

### Task 9: Add _SESSION_HALT_ERROR_TYPES set and propagate result.error_type in feature_executor
- **Files**: `cortex_command/overnight/feature_executor.py`
- **What**: Define a module-scope tuple constant named `_SESSION_HALT_ERROR_TYPES` whose values are the two session-halting error type strings (`"budget_exhausted"` and `"api_rate_limit"`) near the top of the module. Replace the literal-string check `if getattr(result, "error_type", None) == "budget_exhausted":` with a membership check against the constant. Replace the hardcoded `error="budget_exhausted"` keyword in the immediately-following `FeatureResult(...)` construction with the actual `result.error_type` value so the upstream error type propagates downstream. Per spec Open Decisions, the constant lives here (rather than a new shared module); orchestrator.py and runner.py will reference it from feature_executor in Tasks 10 and 12.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R16. Current line locations: feature_executor.py:663 (the `if getattr(result, "error_type", None) == "budget_exhausted":` check), 667 (the `error="budget_exhausted"` literal). Define the constant alongside other module-scope constants at the top of the file. Branch behavior is unchanged — both error types remain session-halting and bypass brain triage; only the comparison shape and the propagated label change.
- **Verification**: `grep -c '_SESSION_HALT_ERROR_TYPES' cortex_command/overnight/feature_executor.py` ≥ 1 AND `grep -c 'error="budget_exhausted"' cortex_command/overnight/feature_executor.py` = 0.
- **Status**: [x] completed

### Task 10: Replace budget_exhausted literals with set membership and propagate paused_reason/abort_reason in orchestrator.py
- **Files**: `cortex_command/overnight/orchestrator.py`
- **What**: Add a module-level import that brings `_SESSION_HALT_ERROR_TYPES` into orchestrator's namespace from `cortex_command.overnight.feature_executor`. At each comparison site where `result.error == "budget_exhausted"` or `failed_result.error == "budget_exhausted"`, replace with set-membership against `_SESSION_HALT_ERROR_TYPES`. At each write site where `abort_reason = "budget_exhausted"`, `paused_reason = "budget_exhausted"`, or `_fs.error = "budget_exhausted"`, replace with the actual upstream value (`result.error`, `failed_result.error`, or equivalent in scope) so `"api_rate_limit"` propagates when that's the cause. The `details={"abort_reason": "budget_exhausted"}` dicts passed into event logging must similarly carry the propagated value.
- **Depends on**: [4, 9]
- **Complexity**: complex
- **Context**: Spec R17. Current sites in orchestrator.py (verified by grep): 293 (`result.error == "budget_exhausted"` comparison), 297 (`batch_result.abort_reason = "budget_exhausted"`), 303 (`_fs.error = "budget_exhausted"`), 311 (`details={"abort_reason": "budget_exhausted"}`), 394 (`failed_result.error == "budget_exhausted"`), 398 (`batch_result.abort_reason = "budget_exhausted"`), 403 (`details={"abort_reason": "budget_exhausted"}`), 445 (`state_for_pause.paused_reason = "budget_exhausted"`), 451 (`"reason": batch_result.abort_reason` — already propagates the abort_reason field, no change needed). Spec said sites at 281, 285, 291, 299, 382, 386, 391, 433 plus 1949/1957 — the latter two were a spec error (those are runner.py sites, handled in Task 12); the former eight have shifted to the verified line set above. Round-loop check at orchestrator.py is NOT a separate site — that lives in runner.py:2032 (Task 12). Depends on Task 4 because Task 4 removes the `extra_fields={"throttle_stats": manager.stats}` read at line 461 BEFORE Task 3 deletes the `stats` property from `ConcurrencyManager` — without that ordering, the post-Task-3 codebase would `AttributeError` on the orphaned read; serialization is for cross-file symbol-deletion ordering, not for git merge-conflict avoidance (non-overlapping hunks merge cleanly). Depends on Task 9 to define the `_SESSION_HALT_ERROR_TYPES` constant being imported.
- **Verification**: `grep -cE '"budget_exhausted"' cortex_command/overnight/orchestrator.py` = 0 (the 8 verified sites all replaced) AND `grep -c '_SESSION_HALT_ERROR_TYPES' cortex_command/overnight/orchestrator.py` ≥ 2 (≥1 import-bringing-into-namespace + ≥1 use site).
- **Status**: [x] completed

### Task 11: Distinguish api_rate_limit in morning-report pause section
- **Files**: `cortex_command/overnight/report.py`
- **What**: Extend the existing `if getattr(data.state, "paused_reason", None) == "budget_exhausted":` branch to also handle `"api_rate_limit"` with distinct text. Recommended: keep the `budget_exhausted` text as-is ("Session paused: API budget exhausted. Features in `pending` status will resume on `/overnight resume`."); add a parallel branch for `api_rate_limit` emitting "Session paused: API rate limit hit. Features in `pending` status remain queued for resume; consult `pipeline-events.log` for retry context."
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R18. Current location: report.py:447 (spec said 435). The existing branch appends two lines to `lines` (the body line + a blank line) before the trailing `lines.append("")`. Preserve the same `lines.append(...)` shape for the new branch. `data.state` shape is from `OvernightState`; `paused_reason` field already accepts arbitrary strings (no enum constraint).
- **Verification**: `grep -cE 'paused_reason.*api_rate_limit|api_rate_limit.*paused_reason' cortex_command/overnight/report.py` ≥ 1 AND `grep -c 'API rate limit' cortex_command/overnight/report.py` ≥ 1.
- **Status**: [x] completed

### Task 12: Distinguish api_rate_limit in user-facing pause notifications + round-loop check
- **Files**: `cortex_command/overnight/runner.py`
- **What**: At runner.py:1579 (the post-completion notification branch on `paused_reason == "budget_exhausted"`), extend with a parallel `elif paused_reason == "api_rate_limit":` branch emitting "Overnight session paused — Anthropic API rate limit. Resume with /overnight resume when retry budget recovers (typically minutes). Session: {session_id}". At runner.py:2032 (the round-loop early-out check `if state.paused_reason == "budget_exhausted":`), extend the check to recognize both reasons as session-halting (`if state.paused_reason in ("budget_exhausted", "api_rate_limit"):` — or import `_SESSION_HALT_ERROR_TYPES` from feature_executor for consistency); update the print line and the `details={"reason": ...}` payload to use the actual `state.paused_reason` value rather than the hardcoded `"budget_exhausted"`.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Spec R19. Current line locations: 1579-1584 (post-completion `_notify(...)` block reading `if paused_reason == "budget_exhausted":` then `_notify(f"Overnight session paused — API budget exhausted. ...")`), 2030-2043 (round-loop early-out: `state = state_module.load_state(state_path)` then `if state.paused_reason == "budget_exhausted":` then `print("Session paused: API budget exhausted — stopping round loop", flush=True)` and `events.log_event(events.CIRCUIT_BREAKER, round=round_num, details={"reason": "budget_exhausted"}, log_path=events_path)` then `break`). Spec said sites at 1510-1515 and 1949-1957 — line drift only. The round-loop print message text should also read "Session paused — stopping round loop" (cause-agnostic) or branch by reason. Either approach satisfies the verification grep; choose the cause-agnostic variant for brevity. For the round-loop check, either re-import `_SESSION_HALT_ERROR_TYPES` from feature_executor (consistent with Task 10) or inline a local tuple — judgment call within the spec's permitted leeway.
- **Verification**: `grep -cE 'paused_reason.*api_rate_limit|api_rate_limit.*paused_reason' cortex_command/overnight/runner.py` ≥ 1 AND `grep -c 'API rate limit' cortex_command/overnight/runner.py` ≥ 1 AND `grep -cE 'details=\{"reason": "budget_exhausted"\}' cortex_command/overnight/runner.py` = 0.
- **Status**: [x] completed

### Task 13: Rename archaeological throttle_stats fixture key in test_overnight_state.py
- **Files**: `cortex_command/overnight/tests/test_overnight_state.py`
- **What**: Rename the literal `throttle_stats` fixture key (used in 5 places at lines 185-221) to a generic name such as `extra_diagnostic` or `extra_payload`. The test exercises the generic `extra_fields` round-trip and is unrelated to throttle behavior; it currently uses `throttle_stats` as a self-supplied label. After Task 4 drops the only production write of `throttle_stats`, the literal in this test corpus becomes archaeological vocabulary that future readers may misinterpret as a still-live integration shape. Renaming preserves the round-trip test's coverage of `save_batch_result(extra_fields=...)` while removing the misleading vocabulary.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec §Edge Cases acknowledges "the label remains in the test corpus but is purely a test-data string, not a behavioral coupling" — this task lifts that acknowledgment into the file. The 5 sites are line 185 (fixture construction), 217-218 (presence check), 220-221 (value assertion). Choose `extra_diagnostic` (descriptive of generic diagnostic-data round-trip) or any equivalent neutral label. Touch only this test file; the round-trip behavior under test is unchanged.
- **Verification**: `grep -c 'throttle_stats' cortex_command/overnight/tests/test_overnight_state.py` = 0 AND `just test` exits 0 (test still passes with renamed fixture).
- **Status**: [x] completed

### Task 14: Update unenumerated user-facing strings in plan.py and overnight SKILL.md
- **Files**: `cortex_command/overnight/plan.py`, `plugins/cortex-overnight-integration/skills/overnight/SKILL.md`
- **What**: At `cortex_command/overnight/plan.py:206`, rewrite the line `lines.append("- **Parallel dispatch**: Tier-based adaptive throttle (1-3 workers depending on API subscription tier)")` so it no longer says "adaptive throttle" — recommended replacement: `lines.append("- **Parallel dispatch**: Tier-based concurrency cap (1-3 workers depending on API subscription tier)")`. At `plugins/cortex-overnight-integration/skills/overnight/SKILL.md:106`, rewrite the bullet `- Execution strategy (rounds, tier-based adaptive throttle, feature count)` to drop "adaptive" — recommended: `- Execution strategy (rounds, tier-based concurrency cap, feature count)`. Both are user-facing strings (the `plan.py` line renders into the morning-review session plan shown to the operator; the SKILL.md line is the cortex-overnight MCP tool's user-visible description) that, post-deletion, would advertise behavior the harness no longer has.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Task 6 covers `docs/overnight-operations.md` and Task 5 covers `requirements/multi-agent.md`, but neither touches the runtime-rendered string in `cortex_command/overnight/plan.py` nor the plugin-shipped SKILL.md. `plan.py:206` is appended unconditionally inside the `## Execution Strategy` section of the rendered plan (verified at lines 200-208 in current source). The plugin SKILL.md is canonical (not auto-generated from elsewhere) per project CLAUDE.md.
- **Verification**: `grep -c 'adaptive throttle' cortex_command/overnight/plan.py` = 0 AND `grep -c 'tier-based concurrency cap\|Tier-based concurrency cap' cortex_command/overnight/plan.py` ≥ 1 AND `grep -c 'adaptive throttle' plugins/cortex-overnight-integration/skills/overnight/SKILL.md` = 0 AND `grep -c 'tier-based concurrency cap' plugins/cortex-overnight-integration/skills/overnight/SKILL.md` ≥ 1.
- **Status**: [x] completed

### Task 15: Add minimal end-to-end test for paused_reason="api_rate_limit" morning-report branch
- **Files**: `cortex_command/overnight/tests/test_report.py`
- **What**: Add a single test method `test_morning_report_distinguishes_api_rate_limit_pause` to the existing `test_report.py` that constructs an `OvernightState` with `paused_reason="api_rate_limit"`, wraps it in the data shape `render_morning_report` expects (a `MorningReportData` or equivalent — match the existing test patterns in the file), invokes the renderer, and asserts the resulting markdown contains the substring `"API rate limit hit"`. Optionally add a parallel assertion that the existing `paused_reason="budget_exhausted"` path emits `"API budget exhausted"` (regression guard — if the file already has this coverage, do not duplicate). Per the user's resolution to the critical-review Ask: this is the one approved deviation from the spec's Non-Requirement banning new tests, scoped to a single test that witnesses the additive branch reachability surfaced by Tasks 11+12. The test does NOT need to exercise the full retry.py → feature_executor.py → orchestrator.py propagation chain — that chain's correctness is the implementer's responsibility, and the morning-report branch is the user-visible end of the chain (testing it confirms at least one consumer of the new value works).
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: This task overrides the spec Non-Requirement "Do NOT introduce new tests beyond modifying existing ones" — user-approved scope expansion captured in events.log critical_review event. Existing `test_report.py` patterns (imports, fixture construction shape) serve as the template — match them. Touch only `test_report.py`; no new test file. The point of the test is to catch implementations where Task 11's branch is unreachable, the literal is misspelled, or the branch order makes it dead code — none of which Task 11's grep can detect.
- **Verification**: `grep -c 'test_morning_report_distinguishes_api_rate_limit_pause' cortex_command/overnight/tests/test_report.py` ≥ 1 AND `just test` exits 0 (new test passes against the post-Task-11 implementation).
- **Status**: [x] completed

### Task 16: Final acceptance sweep — run all spec greps + just test
- **Files**: none
- **What**: Run the complete acceptance grep suite from spec.md (R1-R19) as a single post-implementation sweep, plus `just test`. Per spec §"Acceptance gate sequencing note", these gates have inter-requirement dependencies and must run after all listed changes have landed.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
- **Complexity**: simple
- **Context**: Each preceding task already includes its own per-task acceptance verification (so individual tasks can verify in isolation), but several depend on sibling tasks completing — e.g., Task 3's `grep -rn 'report_rate_limit\|report_success' cortex_command/` only goes to zero after Task 2 deletes the test method that mentions `report_rate_limit`. This task re-runs the full suite as the final gate. The grep targets are enumerated in spec.md acceptance fields; run each, plus `just test` (project test command per `lifecycle.config.md`).
- **Verification**: All spec.md acceptance greps from R1-R19 return their required values, AND `just test` exits 0 with no skipped tests that were previously passing.
- **Status**: [x] completed

## Verification Strategy

Per-task verification is the local gate (each task's **Verification** field is independently runnable). Task 13 is the final cross-cutting gate that re-runs everything after all changes land — it catches any inter-task drift the per-task gates miss. The grep targets cover three classes:

1. **Symbol existence** (R1-R8): no references to deleted symbols/strings remain in the codebase outside historical lifecycle/research artifacts.
2. **Documentation alignment** (R9, R10, R14): the three doc surfaces no longer describe the deleted behavior; new pointers target the surviving `api_rate_limit` → `pause_session` path.
3. **Pause-reason fidelity** (R15-R19): `paused_reason="api_rate_limit"` round-trips end-to-end through retry.py → feature_executor.py → orchestrator.py → report.py + runner.py with distinct user-facing messaging.

`just test` is the runtime gate: any incidental break (import errors, signature mismatches, fixture drift) surfaces here. If `just test` fails, the failing test name identifies which task to revisit.

After all tasks pass, the implementation phase will commit the lifecycle artifacts per `lifecycle.config.md` (`commit-artifacts: true`).

## Veto Surface

- **Module-scope constant placement** (Task 9 vs new shared module): spec Open Decisions allows judgment. Plan places `_SESSION_HALT_ERROR_TYPES` in `feature_executor.py` (closer to its primary consumer); orchestrator.py and runner.py import from there. If reviewer prefers a new `cortex_command/overnight/_constants.py`, that's a refactor variant.
- **Stats property removal vs trim** (Task 3): spec R3 allows either. Plan removes the property entirely because Task 4 deletes the sole caller (`orchestrator.py:461`); no surviving consumer, so the property has zero callers. If reviewer prefers a stub returning `{"current_limit": ..., "max_limit": ...}` for forward-compat, that's a one-line variant inside Task 3.
- **Round-loop print text in Task 12**: cause-agnostic ("Session paused — stopping round loop") vs cause-specific ("Session paused: API rate limit hit — stopping round loop"). Plan picks cause-agnostic for brevity; either passes the grep.
- **Reversibility comment placement in throttle.py** (Task 3): plan places near the top of the file (post-imports, pre-class). Spec says "near the top" without specifying exact placement.
- **No competing-plans variant generated**: criticality is `high`, not `critical`, so the §1b competing-plans flow does not apply per the lifecycle protocol — single plan only. If user wants competing variants anyway, escalate criticality first.
- **One new test added for the additive `api_rate_limit` propagation chain** (Task 15): user-approved scope expansion overriding the spec's "Do NOT introduce new tests" Non-Requirement. The single test in Task 15 witnesses the morning-report branch (Task 11); the propagation chain (retry.py → feature_executor.py → orchestrator.py) remains verified by per-file greps + `just test` only.
- **No state.schema_version bump for the new `paused_reason="api_rate_limit"` value**: plan does not address forward-compat for an older runner reading a state.json paused by post-PR code. The OLD runner.py:1579 falls into the `else:` branch and emits "Overnight complete — {merged}/{total} features merged. Morning report ready." for any non-budget_exhausted reason — which silently misrepresents a 429-paused session as clean. cortex-command's distribution model (single user, latest tag pinned per machine) makes downgrade-then-resume an edge case, but it is not impossible.

## Scope Boundaries

Maps to spec.md "Non-Requirements":
- **NOT modifying** `ConcurrencyManager.acquire()` / `release()` semantics, `SubscriptionTier` enum, `_TIER_DEFAULTS`, callers of `acquire`/`release`.
- **NOT modifying** `dispatch.py` `ERROR_RECOVERY` mapping or `api_rate_limit` → `pause_session` routing — pause-trigger logic and retry budget unchanged. R15-R19 only correct downstream label propagation.
- **NOT introducing** a replacement passive observer event (e.g., `rate_limit_observed`) — pure deletion, no replacement event.
- **NOT introducing** a config flag to gate the deletion — full removal, no opt-in path.
- **NOT restructuring** `ConcurrencyManager` beyond field removal — class stays in place with the same name.
- **NOT introducing** new tests beyond modifying/deleting existing ones — deletion shrinks the test surface.
- **NOT modifying** `cortex_command/overnight/events.py` `EVENT_TYPES` (verified: `throttle_backoff` not registered there).
