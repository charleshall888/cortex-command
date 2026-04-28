# Plan: instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates

## Overview

Thread a closed-vocabulary `skill: Skill` Literal kwarg (plus retry-aware `attempt`/`escalated`/`escalation_event` and review-aware `cycle`) through `dispatch_task` and the seven caller files, then mirror `compute_model_tier_dispatch_aggregates()` with a parallel `compute_skill_tier_dispatch_aggregates()` that uses a conditional `(skill, tier)` / `(skill, tier, cycle)` bucket key over `pipeline-events.log`. Land in dependency order: dispatch-side scaffolding → retry-side threading → caller updates → tests → aggregator → CLI/output → final regression sweep.

## Tasks

### Task 1: Add `Skill` Literal type, runtime guards, and new kwargs to `dispatch_task` in `dispatch.py`

- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Define `Skill` Literal at module scope, add five new keyword-only parameters to `dispatch_task` (`skill: Skill`, `attempt: int = 1`, `escalated: bool = False`, `escalation_event: bool = False`, `cycle: int | None = None`), add two `ValueError`-raising runtime guards, and extend the `dispatch_start` log_event dict with the new fields in the spec'd insertion order. Updates the docstring to document the closed-vocabulary convention and the cycle-only-for-review-fix rule.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - `Skill = Literal["implement", "review", "review-fix", "conflict-repair", "merge-test-repair", "integration-recovery", "brain"]` declared near line 150 (after `_VALID_CRITICALITY` frozenset, before `MODEL_ESCALATION_LADDER`) — follows the existing module-scope-constants convention (`TIER_CONFIG` line 119, `_VALID_CRITICALITY` line 150, `MODEL_ESCALATION_LADDER` line 154).
  - Signature edit lives at `dispatch.py:333-346`. Append the five new keyword-only params after the existing `repo_root: Optional[Path] = None` line; preserve keyword-only semantics by placing them after a `*,` separator if one is needed (existing signature has no `*,` because all current params are positional-or-keyword — introduce `*,` before `skill` to enforce keyword-only-ness for both `skill` and the four optionals).
  - First runtime guard pattern: `if skill not in get_args(Skill): raise ValueError(...)` — placed at the top of `dispatch_task` after existing complexity validation (after line 392 `must be one of {sorted(TIER_CONFIG)}`). Import `get_args` from `typing`.
  - Second runtime guard pattern: `if cycle is not None and skill != "review-fix": raise ValueError(...)` — placed immediately after the first guard.
  - `dispatch_start` emission lives at lines 444-454. Replace the dict literal with one that interleaves the new keys in this order: `event, feature, skill, attempt, escalated, escalation_event, [cycle if not None], complexity, criticality, model, effort, max_turns, max_budget_usd`. Use a conditional dict construction (e.g., build the dict, then `if cycle is not None: event_dict["cycle"] = cycle` inserted before `complexity` — Python dict insertion order is the JSONL key order so `cycle` must be inserted before `complexity` is added when cycle is non-None).
  - Pattern reference: existing complexity validation at `dispatch.py:388-394` for the `raise ValueError` shape.
- **Verification**: Run all four checks; pass if all exit 0 (or grep returns documented count): `python3 -c "from cortex_command.pipeline.dispatch import Skill; from typing import get_args; assert set(get_args(Skill)) == {'implement', 'review', 'review-fix', 'conflict-repair', 'merge-test-repair', 'integration-recovery', 'brain'}"` (R1 acceptance, exit 0); `python3 -c "import inspect; from cortex_command.pipeline.dispatch import dispatch_task; sig = inspect.signature(dispatch_task); p = sig.parameters; assert p['skill'].default is inspect.Parameter.empty and p['skill'].kind == inspect.Parameter.KEYWORD_ONLY; assert p['attempt'].default == 1; assert p['escalated'].default is False; assert p['escalation_event'].default is False; assert p['cycle'].default is None"` (R2 acceptance, exit 0); `grep -nE "raise ValueError\\(.*unregistered skill" cortex_command/pipeline/dispatch.py | wc -l` returns ≥ 1 (R3 guard present); `grep -nE "raise ValueError\\(.*cycle.*review-fix" cortex_command/pipeline/dispatch.py | wc -l` returns ≥ 1 (R14 guard present).
- **Status**: [x] complete

### Task 2: Update `retry.py` — accept `skill` kwarg, snapshot `initial_model`/`previous_attempt_model`, thread attempt/escalated/escalation_event into `dispatch_task` call

- **Files**: `cortex_command/pipeline/retry.py`
- **What**: Add required `skill: Skill` keyword-only parameter to `retry_task` signature, snapshot `initial_model` immediately after `current_model = resolve_model(...)` at line 212, introduce a `previous_attempt_model: Optional[str] = None` local before the retry loop, compute `escalated`/`escalation_event` per attempt, forward all four new kwargs (plus existing `skill`) into the `dispatch_task` call at line 240, and update `previous_attempt_model = current_model` at the end of each loop iteration.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Import `Skill` from `cortex_command.pipeline.dispatch` (already imports `dispatch_task` from same module).
  - Signature edit at retry.py:165-179. Add `skill: Skill` after `repo_path: Path | None = None` as keyword-only — introduce `*,` separator if not already present.
  - Snapshot pattern (after line 212 `current_model: str = resolve_model(complexity, _criticality_val)`):
    - `initial_model = current_model`  (snapshot, never mutated)
    - `previous_attempt_model: Optional[str] = None`  (set before loop)
  - Threading inside the existing `for attempt in range(1, total_attempts + 1):` loop at line 215:
    - Compute `is_escalated = current_model != initial_model` (sticky, true on every attempt at non-initial tier).
    - Compute `is_escalation_event = current_model != previous_attempt_model` (one-shot, true on first attempt only at a newly-escalated tier — note: when `previous_attempt_model is None` on the very first attempt, this evaluates True, so guard the comparison: `is_escalation_event = previous_attempt_model is not None and current_model != previous_attempt_model`).
    - Forward to `dispatch_task` at line 240: add `skill=skill, attempt=attempt, escalated=is_escalated, escalation_event=is_escalation_event` to the kwarg list.
  - **Snapshot placement (load-bearing, do not deviate)**: `previous_attempt_model = current_model` MUST be captured BEFORE `current_model` can mutate within the same iteration. The escalate recovery arm at retry.py:~412 mutates `current_model = next_model` mid-iteration — placing the snapshot AFTER that line (e.g., at the loop tail) would record the post-escalation model and silently break `escalation_event=True` detection on the next iteration's first attempt at the new tier. Two correct placements (pick one):
    - **Top-of-loop placement (recommended)**: insert `previous_attempt_model = current_model` as the very first statement at the START of each iteration of the `for attempt in range(...)` loop, BEFORE computing `is_escalated`/`is_escalation_event` and BEFORE the dispatch_task call. Net effect: on iteration 1 it sets `previous=initial_value (None)`; on iteration 2+ it captures the model that was used in the prior iteration's just-completed dispatch (because nothing has mutated `current_model` since that dispatch returned, except potentially `current_model = next_model` in the escalate arm at the END of the prior iteration).
    - **Pre-mutation placement**: insert `previous_attempt_model = current_model` ONLY in the escalate arm, immediately BEFORE `current_model = next_model` at retry.py:~412. The retry arm and other arms do not update `previous_attempt_model` because `current_model` is unchanged on those paths and the comparison naturally evaluates `current_model != previous_attempt_model = False`. Trade-off vs top-of-loop: less visually obvious and easier to break in future refactors.
  - Trace verification under Task 8's expected sequence (Sonnet→Opus escalation followed by retry-class failures at Opus) under top-of-loop placement: iter 1 enters with `prev=None, current=Sonnet → escalation_event=False, dispatch (1, F, F), failure escalates current=Opus`; iter 2 enters with `prev=Sonnet (snapshotted at top), current=Opus → escalation_event=(Opus≠Sonnet)=True, dispatch (2, T, T)`; iter 3 enters with `prev=Opus (snapshotted at top), current=Opus → escalation_event=False, dispatch (3, T, F)`; iter 4 same shape → `(4, T, F)`. Matches Task 8's expected sequence exactly.
- **Verification**: Run all three checks; pass if all exit 0: `python3 -c "import inspect; from cortex_command.pipeline.retry import retry_task; sig = inspect.signature(retry_task); assert sig.parameters['skill'].kind == inspect.Parameter.KEYWORD_ONLY and sig.parameters['skill'].default is inspect.Parameter.empty"` (skill kwarg required); `grep -nE "initial_model = current_model" cortex_command/pipeline/retry.py | wc -l` returns ≥ 1 (snapshot present); `grep -nE "previous_attempt_model" cortex_command/pipeline/retry.py | wc -l` returns ≥ 3 (initialized + compared + updated).
- **Status**: [x] complete

### Task 3: Update `feature_executor.py` — pass `skill="implement"` to `retry_task` call site

- **Files**: `cortex_command/overnight/feature_executor.py`
- **What**: Add `skill="implement"` to the `retry_task` invocation at feature_executor.py:587. This is the implement-side dispatch entry point for per-feature task execution.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Single-call edit. Locate `retry_task(...)` at line 587 and append `skill="implement"` as a kwarg to the call.
- **Verification**: `grep -nE "retry_task\\(" cortex_command/overnight/feature_executor.py | grep -v "skill=" | wc -l` returns 0 (every retry_task call site includes a `skill=` kwarg).
- **Status**: [x] complete

### Task 4: Update `review_dispatch.py` — pass skill+cycle at three call sites

- **Files**: `cortex_command/pipeline/review_dispatch.py`
- **What**: Add `skill="review"` to the dispatch_task call at line 252 (initial review). Add `skill="review-fix", cycle=1` to line 383 (cycle-1 fix). Add `skill="review-fix", cycle=2` to line 496 (cycle-2 re-review).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Three call-site edits in one file. Each `dispatch_task(...)` invocation gains a `skill=...` kwarg; the two review-fix sites also gain `cycle=...`.
- **Verification**: `grep -nE "dispatch_task\\(" cortex_command/pipeline/review_dispatch.py | grep -v "skill=" | wc -l` returns 0; `grep -nE "cycle=1" cortex_command/pipeline/review_dispatch.py | wc -l` returns ≥ 1; `grep -nE "cycle=2" cortex_command/pipeline/review_dispatch.py | wc -l` returns ≥ 1.
- **Status**: [x] complete

### Task 5: Update `conflict.py`, `merge_recovery.py`, `integration_recovery.py`, `brain.py` — pass skill at four caller sites

- **Files**: `cortex_command/pipeline/conflict.py`, `cortex_command/pipeline/merge_recovery.py`, `cortex_command/overnight/integration_recovery.py`, `cortex_command/overnight/brain.py`
- **What**: Add the appropriate `skill=` kwarg to each `dispatch_task` call: `conflict.py:328` → `skill="conflict-repair"` (renamed from research's `merge-repair`), `merge_recovery.py:332` → `skill="merge-test-repair"` (renamed from research's `test-repair`), `integration_recovery.py:216` → `skill="integration-recovery"`, `brain.py:224` → `skill="brain"`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Four single-call edits across four files. Each follows the same shape: locate the `dispatch_task(...)` invocation at the cited line and append the matching `skill=` kwarg.
- **Verification**: `grep -nE "dispatch_task\\(" cortex_command/pipeline/conflict.py cortex_command/pipeline/merge_recovery.py cortex_command/overnight/integration_recovery.py cortex_command/overnight/brain.py | grep -v "skill=" | wc -l` returns 0 (every dispatch_task call site in these four files includes a `skill=` kwarg).
- **Status**: [x] complete

### Task 6: Add `dispatch_task` validation tests to `test_dispatch.py`

- **Files**: `cortex_command/pipeline/tests/test_dispatch.py`
- **What**: Add two test methods that assert `dispatch_task` raises `ValueError` for an unregistered skill string (R3) and for `cycle` passed alongside a non-`review-fix` skill (R14). Each test must use `pytest.raises(ValueError)` with the offending value in the asserted message-substring.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Test names must match spec acceptance: `test_dispatch_task_rejects_unregistered_skill` and `test_dispatch_task_rejects_cycle_for_non_review_fix`.
  - First test calls `dispatch_task(skill="not-a-real-skill", ...)` (rest of args minimal/mocked) inside `pytest.raises(ValueError, match="not-a-real-skill")`.
  - Second test calls `dispatch_task(skill="implement", cycle=2, ...)` inside `pytest.raises(ValueError, match="cycle")`.
  - Use the file's existing async-test pattern; `dispatch_task` is an async function so wrap with `@pytest.mark.asyncio` per the file's existing conventions.
- **Verification**: Run both tests; pass if exit 0: `pytest cortex_command/pipeline/tests/test_dispatch.py -k "test_dispatch_task_rejects_unregistered_skill or test_dispatch_task_rejects_cycle_for_non_review_fix" -v` (exit 0); `grep -E 'pytest\\.raises\\(ValueError.*"not-a-real-skill"' cortex_command/pipeline/tests/test_dispatch.py | wc -l` returns ≥ 1 (R3.b); `grep -E 'pytest\\.raises\\(ValueError.*cycle' cortex_command/pipeline/tests/test_dispatch.py | wc -l` returns ≥ 1 (R14.b).
- **Status**: [x] complete

### Task 7: Add `dispatch_start` emission test to `test_dispatch_instrumentation.py`

- **Files**: `cortex_command/pipeline/tests/test_dispatch_instrumentation.py`
- **What**: Add `test_dispatch_start_includes_skill_fields` that runs a single `dispatch_task` invocation through to event emission, parses the emitted JSONL `dispatch_start` line, and asserts both presence and order of the new keys via `list(event.keys())`. Also include a non-`review-fix` invocation case to assert `cycle` is absent from the dict.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - File already exists with `dispatch_start`-shaped tests; reuse the file's existing event-capture pattern (likely a `tmp_path` log file + `parse_events()` call). Inspect the file's existing test scaffolding before authoring.
  - Expected key order for `cycle is not None` case: `["event", "feature", "skill", "attempt", "escalated", "escalation_event", "cycle", "complexity", "criticality", "model", "effort", "max_turns", "max_budget_usd"]`. For `cycle is None` case: same minus `cycle`.
- **Verification**: `pytest cortex_command/pipeline/tests/test_dispatch_instrumentation.py -k test_dispatch_start_includes_skill_fields -v` exit 0 (R4.b).
- **Status**: [x] complete

### Task 8: Add retry threading test to `test_retry.py`

- **Files**: `cortex_command/pipeline/tests/test_retry.py`
- **What**: Add `test_retry_threads_attempt_escalated_and_escalation_event` that mocks `dispatch_task`, drives `retry_task` through a 4-attempt scenario (Sonnet first attempt → Opus escalation → retry-class failure at Opus → second retry at Opus), and asserts the kwarg sequence on each call.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Use `unittest.mock.AsyncMock` (or equivalent) to patch `dispatch_task` at its import site in `retry.py`.
  - Drive 4 attempts by returning sequential failure types from the mock such that recovery_path classifies as `escalate` after attempt 1, then `retry` for attempts 2-3, then success/failure at attempt 4.
  - Assertions, one per attempt: assert `kwargs["attempt"]`, `kwargs["escalated"]`, `kwargs["escalation_event"]` match the expected tuple for each call (4 attempts → 4 assertion blocks).
  - Expected sequence: `(1, False, False)` → `(2, True, True)` → `(3, True, False)` → `(4, True, False)`.
- **Verification**: `pytest cortex_command/pipeline/tests/test_retry.py -k test_retry_threads_attempt_escalated_and_escalation_event -v` exit 0; `grep -E "kwargs\\[['\\\"]escalation_event['\\\"]\\]" cortex_command/pipeline/tests/test_retry.py | wc -l` returns ≥ 4 (R6.b).
- **Status**: [x] complete

### Task 9: Add cycle-threading test to `test_review_dispatch.py`

- **Files**: `cortex_command/pipeline/tests/test_review_dispatch.py`
- **What**: Add `test_cycle_threaded_at_review_fix_sites` that mocks `dispatch_task` and drives the review-cycle code path that reaches both `review_dispatch.py:383` and `review_dispatch.py:496`. Assert the `kwargs["cycle"]` value is 1 at the first call and 2 at the second call.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**:
  - Patch `dispatch_task` in the `review_dispatch` module namespace.
  - Drive at least two cycles of CHANGES_REQUESTED→fix→re-review so both call sites fire.
  - Use `mock.call_args_list` to retrieve all calls; assert `mock.call_args_list[i].kwargs["cycle"]` == expected for the two review-fix calls. The initial review at line 252 (skill="review", no cycle) should NOT have `cycle` in its kwargs — verify this absence as well to defend against accidental cycle-pollution at the non-review-fix site.
- **Verification**: `pytest cortex_command/pipeline/tests/test_review_dispatch.py -k test_cycle_threaded_at_review_fix_sites -v` exit 0; `grep -E "kwargs\\[['\\\"]cycle['\\\"]\\]" cortex_command/pipeline/tests/test_review_dispatch.py | wc -l` returns ≥ 2 (R13.b).
- **Status**: [x] complete

### Task 10: Add `compute_skill_tier_dispatch_aggregates()` function to `metrics.py`

- **Files**: `cortex_command/pipeline/metrics.py`
- **What**: Add a parallel function mirroring `compute_model_tier_dispatch_aggregates()` (line 442). Group paired records by a CONDITIONAL bucket key: `"<skill>,<tier>"` for non-review-fix skills, `"<skill>,<tier>,<cycle>"` for review-fix (with `legacy-cycle` substring when cycle is missing). Bucket missing-`skill` records as `"legacy"` (NOT `"unknown"`). Reuse the per-bucket statistics shape from the model-tier aggregator (cost mean/median/p95, turns mean/median/p95, count, error count, cap rate). Inherit the `n_completes < 30` p95 suppression from metrics.py:534-541.
- **Depends on**: none (works against existing event shape; missing fields fall through to legacy bucket)
- **Complexity**: complex
- **Context**:
  - Place the new function immediately after `compute_model_tier_dispatch_aggregates()` ends (around line 561). Mirror the function's signature: `def compute_skill_tier_dispatch_aggregates(paired: list[dict]) -> dict[str, dict]:`.
  - Re-use the same record-extraction pattern: read `start_event = record["start"]`, then extract `skill = start_event.get("skill", "legacy")`, `tier = ...` (existing field), `cycle = start_event.get("cycle")`.
  - Bucket key construction:
    - if `skill == "review-fix"`: `bucket_key = f"{skill},{tier},{cycle if cycle is not None else 'legacy-cycle'}"`
    - else: `bucket_key = f"{skill},{tier}"`
  - Sentinel collision check: do NOT use the string `"unknown"` for missing-skill records — that string is the existing untiered sentinel at metrics.py:496-497 and would silently merge two distinct bucket families. Use `"legacy"` instead.
  - Reuse the same statistics-computation block from the existing aggregator. If the existing function has internal helpers (e.g., `_compute_bucket_stats()`), call them directly; otherwise, copy the block (acceptable per spec — research §"Tradeoffs & Alternatives" justified parallel-function over generic-refactor for this ticket).
  - Pattern reference: `compute_model_tier_dispatch_aggregates()` at metrics.py:442-561.
- **Verification**: `python3 -c "from cortex_command.pipeline.metrics import compute_skill_tier_dispatch_aggregates; assert callable(compute_skill_tier_dispatch_aggregates)"` exit 0; `grep -nE "def compute_skill_tier_dispatch_aggregates" cortex_command/pipeline/metrics.py | wc -l` returns 1.
- **Status**: [x] complete

### Task 11: Add `--report skill-tier-dispatch` CLI mode and `_format_skill_tier_dispatch_report()` formatter to `metrics.py`

- **Files**: `cortex_command/pipeline/metrics.py`
- **What**: Extend the argparse `--report` choices from `["tier-dispatch"]` to `["tier-dispatch", "skill-tier-dispatch"]` at line 1042-1046. Add `_format_skill_tier_dispatch_report()` formatter mirroring `_format_tier_dispatch_report()` at line 890. Add a conditional print branch at line 1118+ that calls the new formatter when `args.report == "skill-tier-dispatch"`. Prepend a 2-3 line header to the formatter output documenting (a) idempotency-skip under-counting and (b) orphan-dispatch silent-drop.
- **Depends on**: [10, 12]
- **Complexity**: simple
- **Context**:
  - Place `_format_skill_tier_dispatch_report()` immediately after `_format_tier_dispatch_report()` ends (around line 1016). Mirror the signature: `def _format_skill_tier_dispatch_report(metrics_data: dict[str, Any], since: datetime | None) -> str:`.
  - The new aggregator output lives in `metrics_data["skill_tier_dispatch_aggregates"]` (key added by Task 12). Iterate buckets, sort lexicographically, format as a fixed-width table mirroring the model-tier report.
  - Header strings: must include both substrings `idempot` and `orphan` so the R11 grep accepts (e.g., "Note: idempotency-skipped tasks emit no dispatch_start, so per-skill counts may under-count vs task_* events. Crashed dispatches with no terminal event are silently dropped (orphan-handling carve-out, separate ticket).").
  - argparse update at line 1042-1046: replace `choices=["tier-dispatch"]` with `choices=["tier-dispatch", "skill-tier-dispatch"]`.
  - Conditional print at line 1118+: add `elif args.report == "skill-tier-dispatch":` branch that mirrors the existing tier-dispatch branch but calls the new formatter.
- **Verification**: `python3 -m cortex_command.pipeline.metrics --report skill-tier-dispatch --help 2>&1 | grep -c skill-tier-dispatch` returns ≥ 1 (R9 acceptance); `python3 -m cortex_command.pipeline.metrics --report skill-tier-dispatch 2>&1 | grep -E "idempot|orphan" | wc -l` returns ≥ 2 (R11 acceptance, after the empty-data path is exercised — the header always prints regardless of bucket count).
- **Status**: [x] complete

### Task 12: Wire both aggregators into `metrics.py` `main()` output

- **Files**: `cortex_command/pipeline/metrics.py`
- **What**: After computing `model_tier_dispatch_aggregates` at line 1081, add a parallel `skill_tier_dispatch_aggregates = compute_skill_tier_dispatch_aggregates(all_paired)` line. Add `"skill_tier_dispatch_aggregates": skill_tier_dispatch_aggregates` to the output dict at line 1085-1090.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - Two-line addition. Mirrors the surrounding `model_tier_dispatch_aggregates` lines exactly.
  - Pattern reference: lines 1081 and 1090 (existing model-tier wiring).
- **Verification**: `python3 -m cortex_command.pipeline.metrics && python3 -c "import json; d = json.load(open('lifecycle/metrics.json')); assert 'skill_tier_dispatch_aggregates' in d and 'model_tier_dispatch_aggregates' in d"` exit 0 (R10 acceptance).
- **Status**: [x] complete

### Task 13: Add `TestSkillTierDispatchAggregates` class to `test_metrics.py`

- **Files**: `cortex_command/pipeline/tests/test_metrics.py`
- **What**: Extend the existing `_start()` helper signature to accept `skill: str = "implement"` (default preserves existing test compatibility per spec Technical Constraints). Add a new `TestSkillTierDispatchAggregates` class with the six required test methods enumerated below. Each must perform a behavioral assertion against `compute_skill_tier_dispatch_aggregates()` output, not merely contain the spec-required string literals.
- **Depends on**: [10, 11, 12]
- **Complexity**: complex
- **Context**:
  - Existing `_start()` helper is at test_metrics.py:54-287 inside `TestPairDispatchEvents`. Insert `skill: str = "implement"` into the kwargs list AFTER `model` and BEFORE `ts` (the canonical insertion point: keeps related event-keys grouped, matches the new `dispatch_start` JSONL key order from Task 1, and preserves existing tests because no current caller passes `model`/`ts` positionally — verified by grep of the existing TestPairDispatchEvents). Pass through to the constructed event dict.
  - New class must contain EXACTLY these six method names (verified by enumeration in the verification step): `test_single_bucket_grouping_non_review_fix`, `test_multi_bucket_grouping_across_skills`, `test_review_fix_cycle_disentanglement`, `test_review_fix_legacy_cycle_bucketing`, `test_legacy_bucket_for_missing_skill`, `test_p95_suppression_below_threshold`.
  - **Each test method must invoke `compute_skill_tier_dispatch_aggregates()` against a hand-built fixture and assert on the returned dict — not merely contain the spec-required string literals.** Specifically:
    - `test_review_fix_cycle_disentanglement`: build two paired records with `skill="review-fix"`, one with `cycle=1` and one with `cycle=2`, both at the same tier; assert the result dict contains exactly the two distinct keys matching `^review-fix,.*,1$` and `^review-fix,.*,2$` (e.g., `assert "review-fix,sonnet,1" in result and "review-fix,sonnet,2" in result and len([k for k in result if k.startswith("review-fix,")]) == 2`).
    - `test_legacy_bucket_for_missing_skill`: build a paired record with the `skill` key absent from the start event; assert a key matching `^legacy,` appears in the result (e.g., `assert any(k.startswith("legacy,") for k in result)`). The key must be bucket-key-shaped (`legacy,<tier>`), not the bare string `"legacy"`.
    - The other four methods follow the same pattern: fixture → `compute_skill_tier_dispatch_aggregates(...)` → behavioral assertion on the result dict.
  - Legacy-bucket test must construct the start event directly (not via `_start()`) so the `skill` key is genuinely absent rather than defaulting to `"implement"`.
- **Verification**: Run all checks; pass if all exit 0 (or grep returns documented count): `pytest cortex_command/pipeline/tests/test_metrics.py::TestSkillTierDispatchAggregates -v` exit 0 (Cycle 1 functional gate); `python3 -c "from cortex_command.pipeline.tests.test_metrics import TestSkillTierDispatchAggregates; methods = {m for m in dir(TestSkillTierDispatchAggregates) if m.startswith('test_')}; required = {'test_single_bucket_grouping_non_review_fix', 'test_multi_bucket_grouping_across_skills', 'test_review_fix_cycle_disentanglement', 'test_review_fix_legacy_cycle_bucketing', 'test_legacy_bucket_for_missing_skill', 'test_p95_suppression_below_threshold'}; assert required <= methods, f'missing: {required - methods}'"` exit 0 (method-name enumeration gate, replaces the bypassable count-only check); `grep -E 'compute_skill_tier_dispatch_aggregates\\(' cortex_command/pipeline/tests/test_metrics.py | wc -l` returns ≥ 7 (one definition + at least one call per of the six new test methods, satisfies R7.c); `grep -E '"review-fix,.*,1"' cortex_command/pipeline/tests/test_metrics.py | wc -l` returns ≥ 1 AND `grep -E '"review-fix,.*,2"' cortex_command/pipeline/tests/test_metrics.py | wc -l` returns ≥ 1 (R7.d, source-string presence); `grep -E '"legacy,' cortex_command/pipeline/tests/test_metrics.py | wc -l` returns ≥ 1 (R8.b strengthened: bucket-key-shape `"legacy,` rather than bare `"legacy"`, eliminates collision with comments / unrelated occurrences).
- **Status**: [x] complete

### Task 14: Run full test suite and confirm no regressions

- **Files**: none (verification only)
- **What**: Run `just test` and resolve any regressions. Confirm the helper-signature change in test_metrics.py did not perturb the existing `TestPairDispatchEvents` cases. Confirm the new aggregator does not affect `compute_model_tier_dispatch_aggregates()` output for unchanged inputs.
- **Depends on**: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
- **Complexity**: simple
- **Context**:
  - Running `just test` is the canonical project-wide regression sweep per CLAUDE.md.
  - If any pre-existing tier-dispatch test breaks, inspect first whether the `_start()` helper-signature change (Task 13) accidentally altered event-dict shape — it should not, because `skill` is added as an additional key, not a replacement for any existing key.
- **Verification**: `just test` exit 0 (R12 acceptance).
- **Status**: [x] complete

## Verification Strategy

End-to-end verification proceeds in three layers:

1. **Unit-level (Tasks 6–9, 13)**: Each new test method asserts contract behavior — signature shape, runtime guards, retry threading, cycle threading, aggregator bucketing.
2. **Integration-level (Tasks 11, 12)**: `python3 -m cortex_command.pipeline.metrics --report skill-tier-dispatch` exits 0 and prints the new report; `lifecycle/metrics.json` contains both aggregator keys.
3. **Regression sweep (Task 14)**: `just test` exits 0 with no regressions in `test_dispatch.py`, `test_dispatch_instrumentation.py`, `test_retry.py`, `test_review_dispatch.py`, `test_metrics.py`, or any other suite.

After Task 14 passes, manually exercise the CLI on a real `pipeline-events.log` (run during a previous overnight session) to confirm the report renders sensibly with mixed legacy + new events. This step is interactive — no automated verification command — but is a useful smoke test before declaring the feature complete.

## Veto Surface

- **Required-skill-from-day-1 fail-loud rollout**: spec §Open Decisions Q1 documents this as final, but the consequence is that any in-flight overnight session at PR merge time crashes with `TypeError`. Mitigation is operational coordination ("don't merge while overnight runs"), not technical. If the user prefers the soft-rollout `Skill | None = None` path, Tasks 1, 2, 6, and the runtime guard in Task 1 all change.
- **Tasks 1+2 split signature change from caller updates** (Tasks 3, 4, 5): intermediate state between Task 1's commit and Task 5's commit is RUNTIME-BROKEN — every existing `dispatch_task` and `retry_task` caller raises `TypeError` until all callers are updated. The plan's per-task verifications (`inspect.signature` + `grep`) cannot detect this because they don't import callers; only Task 14's `just test` regression sweep catches it. This is a deliberate decomposition trade-off: collapsing all 7 caller updates into Task 1 would create an 8-file mega-task, destroy the Task 4/Task 5 parallelism (both `Depends on: [1]`), and mix signature-edit and caller-update concerns. The plan accepts the broken-intermediate-state window in exchange for parallel caller updates and clean per-file diff readability. If the user prefers eliminating the broken-intermediate-state window, Tasks 1, 2 each gain a `pytest cortex_command/pipeline/tests/` step in their Verification (eliminates parallelism within Tasks 1-5 by serializing on the test suite), OR Tasks 1-5 are explicitly marked as squash-into-one-commit at the lifecycle's commit boundary (requires lifecycle/orchestrator support that may not exist).
- **Vocabulary renames** `merge-repair` → `conflict-repair` and `test-repair` → `merge-test-repair`: spec §Open Decisions Q3 locks this in. If reverted, Tasks 5 and the `Skill` Literal in Task 1 both change.
- **Three-dimensional bucket key for review-fix only**: critical-review §4 Q2 and spec R7 lock this in. If the user prefers a uniform two-dimensional `(skill, tier)` key, Task 10's bucket logic and Task 13's review-fix tests both change.
- **Conditional `cycle` field on `dispatch_start`**: cycle is present only when non-None. If the user prefers always-present `cycle` (with `null` for non-review-fix), Task 1's emission dict simplifies but the legacy-cycle bucketing logic in Task 10 still has to handle missing-cycle events from historical data.
- **Parallel function vs generic refactor**: research §Tradeoffs locked in parallel-function for this ticket; epic-101 horizon may revisit when 3+ aggregators exist. If reverted, Tasks 10 and 11 collapse into a single parameterized aggregator/formatter pair.

## Scope Boundaries

Maps to the spec's Non-Requirements section. Out of scope for this ticket:

- No retrofitting of historical `dispatch_start` events to add `skill`. Historical events bucket as `"legacy"` at read time.
- No interactive tool-call instrumentation (ticket 103's surface).
- No dashboard changes — dashboard reads `agent-activity.jsonl`, not `dispatch_start`.
- No central skill registry beyond the `Skill` Literal — no `skills.py`, no JSON config, no external validation.
- No fix for the `pair_dispatch_events()` orphan blind spot. Documented in report header; new backlog item filed during implementation.
- No `"other"` or `null` escape hatch in the Literal vocabulary.
- No composable `--group-by` CLI syntax. Named-mode `--report skill-tier-dispatch` per user direction.
- No graceful degradation for the required `skill` kwarg. Calling `dispatch_task` without `skill` raises `TypeError` at the Python level — intentional fail-loud.
- No documentation updates beyond `dispatch.py` docstring (Task 1). Updates to `docs/pipeline.md` or `docs/overnight-operations.md` are deferred unless they enumerate `dispatch_start` event keys verbatim (verified by spec time grep — neither doc enumerates the keys).
