# Review: adopt-xhigh-effort-default-for-overnight-lifecycle-implement

## Stage 1: Spec Compliance

### Requirement 1: Centralized 2D effort matrix replaces `EFFORT_MAP`
- **Expected**: `_EFFORT_MATRIX` present, no `EFFORT_MAP` references in non-test code, exactly 12 cells.
- **Actual**: `cortex_command/pipeline/dispatch.py` defines `_EFFORT_MATRIX` at lines 149-162 with 12 (complexity, criticality) cells. `grep "EFFORT_MAP"` returns 0 in dispatch.py. `len(_EFFORT_MATRIX) == 12` is enforced by `test_effort_matrix_policy`.
- **Verdict**: PASS

### Requirement 2: Effort matrix values match the policy table
- **Expected**: Each cell matches the spec §1 table; `test_effort_matrix_policy` exits 0.
- **Actual**: All 12 cell values in dispatch.py match the spec table verbatim (haiku→low; trivial-high/critical→high; simple-*→high; complex-low/medium→high; complex-high/critical→xhigh). The unit test at `test_dispatch.py:928-956` literally enumerates all 12 cells with the spec values and asserts equality of the entire `_EFFORT_MATRIX` dict. Verified passing in the full sweep.
- **Verdict**: PASS

### Requirement 3: Skill-based overrides on Opus only
- **Expected**: `review-fix` and `integration-recovery` get `effort="max"` only when resolved model is Opus; `model` arg is the post-`model_override` value; `test_effort_skill_overrides` passes.
- **Actual**: `_SKILL_EFFORT_OVERRIDES` defined at lines 169-172 (flat dict, not 3D, per spec Non-Requirements). `resolve_effort` gates the override on `model == "opus"` at line 271. The dispatch site at line 523-524 computes the post-override `model` first, then passes it to `resolve_effort`, so the gate sees the effective model. The four spec-listed assertions are present in `test_effort_skill_overrides` (lines 967-1002), plus an extra assertion that non-overriding skill `implement` on Opus stays at the matrix value (xhigh).
- **Verdict**: PASS

### Requirement 3a: `integration-recovery` dispatch site forces Opus
- **Expected**: `model_override="opus"` adjacent to the existing `dispatch_task` call at integration_recovery.py:215-225; integration test passes.
- **Actual**: `cortex_command/overnight/integration_recovery.py:224` adds `model_override="opus"` inside the `dispatch_task` invocation at line 216. `test_integration_recovery_forces_opus` (test file:33) records the kwargs and asserts `model_override == "opus"`. The test is wrapped in class `TestIntegrationRecoveryForcesOpus`; the spec's bare-method selector requires `::TestIntegrationRecoveryForcesOpus::test_integration_recovery_forces_opus` to invoke. This is a test-class-structure deviation from the spec wording but does not affect the test's correctness — it passes when invoked correctly.
- **Verdict**: PASS

### Requirement 4: `dispatch_task` consults the matrix at the existing call site
- **Expected**: `effort = effort_override if effort_override is not None else resolve_effort(complexity, criticality, skill, model)` adjacent to the existing line 439 logic; no `EFFORT_MAP[complexity]` references.
- **Actual**: `dispatch.py:524` reads exactly `effort = effort_override if effort_override is not None else resolve_effort(complexity, criticality, skill, model)`, where `model` is the post-`model_override` value resolved one line above (523). `grep "EFFORT_MAP\[complexity\]"` returns 0.
- **Verdict**: PASS

### Requirement 5: `dispatch_task` docstring lists new effort vocabulary AND adaptive-thinking framing
- **Expected**: Vocabulary `"low", "medium", "high", "xhigh", "max"` + Opus 4.7 note + adaptive/behavioral-signal/maximum reasoning text near the effort docstring.
- **Actual**: Docstring at lines 470-478 lists all five effort values, notes `xhigh` is "Opus 4.7-only and is silently downgraded by non-Opus models", and frames effort as "a behavioral signal capping the maximum reasoning depth — the model adapts thinking down for simpler tasks". Three grep counts confirm: vocabulary string=3, "Opus 4.7"=1, adaptive/maximum/behavioral=5.
- **Verdict**: PASS

### Requirement 6: SDK upgraded to expose `stop_reason`
- **Expected**: `pyproject.toml` pins `claude-agent-sdk` to a constrained version; `ResultMessage` has `stop_reason: str | None`; parser extracts `stop_reason`; `test_sdk_parser_extracts_stop_reason` exits 0.
- **Actual**: `pyproject.toml:10` pins `claude-agent-sdk>=0.1.46,<0.1.47` (single-version effective range). `test_sdk_parser_extracts_stop_reason` at test_dispatch.py:864-921 bypasses the test stub, imports the real `claude_agent_sdk._internal.message_parser`, feeds a canned CLI JSON line with `"stop_reason": "max_tokens"`, and asserts `ResultMessage.stop_reason == "max_tokens"`. The SDK pin tightness (effectively single-version) is justified in the plan's Veto Surface to avoid three known downstream hazards (effort int arm v0.1.55, sniffio v0.1.67, mcp floor v0.1.70). Spec said "lowest version >=0.1.46 that resolves cleanly"; `>=0.1.46,<0.1.47` satisfies that literal phrase while documenting the rationale for not opening the upper bound.
- **Verdict**: PASS

### Requirement 7: `_stubs.py:ResultMessage` mirrors the upgraded SDK shape
- **Expected**: `stop_reason: str | None = None` appended as the LAST field; existing positional constructions still work.
- **Actual**: `cortex_command/tests/_stubs.py:72` adds `stop_reason: str | None = None` as the last dataclass field, after `structured_output`. Comment at lines 68-71 documents the SDK position (between `session_id` and `total_cost_usd`) vs the stub's append-last placement, citing Spec Req #7 directly. Full sweep (579 passed, 1 xpassed) confirms existing positional constructions remain valid.
- **Verdict**: PASS

### Requirement 8: Dispatch event logging captures `stop_reason` at BOTH emitters
- **Expected**: `dispatch.py` ResultMessage handler emits `stop_reason` on `dispatch_complete`; emits `dispatch_truncation` BEFORE `dispatch_complete` when reason is in `{max_tokens, model_context_window_exceeded}`. Same for `runner.py:_emit_orchestrator_round_telemetry`. Both unit tests pass.
- **Actual**: `dispatch.py:646-671` reads `stop_reason` via `getattr(message, "stop_reason", None)`, emits a `dispatch_truncation` event (with feature/stop_reason/model/effort) BEFORE `dispatch_complete` when the reason matches the allow-list, and includes `stop_reason` on the `dispatch_complete` event payload. The truncation allow-list is a LOCAL set literal per spec Edge Cases. `runner.py:857` extracts `stop_reason` from envelope; lines 880-912 emit `dispatch_truncation` (with feature/stop_reason/model/effort) BEFORE `dispatch_complete` (which carries `stop_reason`) when the success-shaped path is taken. Both unit tests are present and verified by the full sweep.
- **Verdict**: PASS

### Requirement 9: New exact-key-list assertion test for `dispatch_complete` events
- **Expected**: `test_dispatch_complete_exact_key_list` asserts the exact key set `{event, feature, cost_usd, duration_ms, num_turns, stop_reason}`.
- **Actual**: `test_dispatch_instrumentation.py:516-576` constructs a happy-path dispatch, reads via `_read_jsonl` (which strips `ts`), extracts the single `dispatch_complete` event's keys, and asserts equality with exactly those six keys. Note: this enforces the SDK-emitter shape only (the runner-emitter envelope path emits a superset including `model`, `input_tokens`, etc.) — but the spec's wording is unambiguous about "the new exact-key-list test for `dispatch_complete` events" referring to the dispatch_task path with the named six keys, which is what the test enforces.
- **Verdict**: PASS

### Requirement 10: Regression test for effort value passthrough to SDK CLI subprocess
- **Expected**: For each effort value in `{low, medium, high, xhigh, max}`, `ClaudeAgentOptions(effort=v)` constructs cleanly AND `["--effort", v]` propagates to the CLI argv.
- **Actual**: `test_effort_value_passthrough` (test_dispatch.py:1005-1069) bypasses the conftest stub, imports the real SDK + transport, iterates all five effort values, asserts `opts.effort == value`, builds argv via `SubprocessCLITransport._build_command`, and asserts the `--effort` flag pair appears with the correct value. Includes an explicit `else: raise AssertionError` if the flag is missing.
- **Verdict**: PASS

### Requirement 11: `docs/sdk.md` documents the new effort matrix and skill overrides
- **Expected**: `_EFFORT_MATRIX` referenced; `review-fix` near `max`; the override fires only on Opus cells (~25% coverage note).
- **Actual**: `docs/sdk.md` includes the matrix table (lines 70-87) showing all 12 cells and their resolved effort levels, the skill-overrides table (lines 95-96) with `review-fix → max` and `integration-recovery → max`, and the explicit ~25% coverage caveat at line 100. Adaptive-thinking framing at line 89 cites Anthropic's Opus 4.7 guidance. `_EFFORT_MATRIX` mentioned 2 times.
- **Verdict**: PASS

### Requirement 12: `docs/overnight-operations.md` documents rationale, framing, and rollback
- **Expected**: Anthropic citation, #089 closure citation, adaptive-thinking framing, rollback monitoring procedure with `metrics.json` query example, threshold (>2× over 2-3 rounds), and rollback path.
- **Actual**: Section "Effort policy rationale and rollback monitoring" at lines 314-344 covers: Anthropic guidance citation (line 318), #089 closure rationale (line 320), adaptive-thinking framing (line 322), rollback monitoring procedure with `jq` query example against `metrics.json` (lines 324-340), >2× per-bucket mean threshold over 2-3 rounds (line 342), and rollback path that reverts the matrix flip while keeping observability infrastructure (line 344). Grep counts: xhigh=7, rollback=7, adaptive/maximum-reasoning/behavioral-signal=3.
- **Verdict**: PASS

### Requirement 13: `metrics.py` aggregator extended to bucket by `(model, tier, skill, effort)`
- **Expected**: `pair_dispatch_events` propagates `effort`; bucket keys gain effort axis; `legacy-effort` sentinel for records without effort; `test_aggregator_buckets_by_effort` and `test_metrics_json_exposes_effort_bucket` pass; existing snapshot tests updated in lockstep.
- **Actual**: `pair_dispatch_events` (metrics.py:404, 439) propagates `effort` from start events into both `dispatch_complete` and `dispatch_error` paired records. `compute_model_tier_dispatch_aggregates` (line 521) builds key `f"{model},{tier},{effort}"` with `effort = rec.get("effort") or "legacy-effort"`. `compute_skill_tier_dispatch_aggregates` (lines 688, 690) builds either `f"{skill},{tier},{effort},{cycle_part}"` for review-fix or `f"{skill},{tier},{effort}"` otherwise. Both new tests are present (test_metrics.py:1239, 1326) and exercise pair-through, distinct-bucket, and full-pipeline `metrics.json` outputs with cost-mean assertions. Existing fixtures updated: `dispatch_since_boundary.jsonl` low→high, `dispatch_over_cap.jsonl` high→xhigh; 16 additional bucket-key assertions updated across test_metrics.py and test_orchestrator_round_telemetry.py per Task 7 expansion (commit 540b4ce). Full sweep clean.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None — the work is internal to the pipeline/overnight stack (effort policy, SDK pin, observability axes); it does not change the in-scope/out-of-scope boundaries, the day/night philosophy, the file-based-state architectural constraint, or any other invariant in `requirements/project.md`. The model-selection-matrix mention in In Scope (line 48) is a top-level reference that the implementation extends (effort axis added) but does not contradict.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `_EFFORT_MATRIX`, `_SKILL_EFFORT_OVERRIDES`, `_MODEL_SUPPORTED_EFFORTS`, `resolve_effort` mirror the existing `_MODEL_MATRIX` / `resolve_model` pair in dispatch.py — same leading-underscore convention for module-private constants, same `resolve_*` verb-noun shape for the lookup function, same dict-of-tuples shape. The `legacy-effort` sentinel parallels the existing `untiered,untiered` and `legacy` (skill) sentinels in metrics.py. Consistent.
- **Error handling**: The runtime guard uses `raise ValueError` (lines 274-279) rather than the literal `assert` in spec §3. The deviation is documented inline in the docstring (lines 262-268) citing the plan's Veto Surface — `assert` is stripped under `python -O` / `PYTHONOPTIMIZE=1`, defeating the spec's "MUST fail loudly" intent. `ValueError` matches the existing convention at dispatch.py:213-232/513-521. The truncation allow-list is a LOCAL set literal in both emitters (per spec Edge Cases), so unknown future stop_reason values pass through to `dispatch_complete` without spurious truncation events. Edge cases (None model in runner-path, missing effort field, legacy records) are all handled: `runner.py` resolves effort against a "sonnet" fallback model since the actual model is unknown at dispatch_start emission time (documented in commit ec7b9ee); metrics.py gracefully buckets effort-less records under `legacy-effort`. Defensive `getattr(message, "stop_reason", None)` in dispatch.py protects against pre-0.1.46 stub regressions.
- **Test coverage**: Every spec verification step has a corresponding test. The spec's enumerated unit/integration tests (`test_effort_matrix_policy`, `test_effort_skill_overrides`, `test_effort_value_passthrough`, `test_sdk_parser_extracts_stop_reason`, `test_max_tokens_truncation_emits_dispatch_truncation_event_via_dispatch_task`, `test_max_tokens_truncation_emits_dispatch_truncation_event_via_orchestrator_round`, `test_dispatch_complete_exact_key_list`, `test_aggregator_buckets_by_effort`, `test_metrics_json_exposes_effort_bucket`, `test_integration_recovery_forces_opus`) are all present. The runtime guard gets its own dedicated test (`test_effort_runtime_guard_rejects_unsupported_effort_for_model`) using monkeypatch to force a synthetic xhigh-on-haiku scenario. Lockstep updates to fixtures and existing assertions covered.
- **Pattern consistency**: Matrix shape mirrors `_MODEL_MATRIX` (same 3×4 cell layout, same dict-of-tuples). Skill override is a flat dict (not 3D) per spec Non-Requirements. Local truncation allow-lists in both emitters (per spec Edge Cases). `dispatch_truncation` event payload shape (feature/stop_reason/model/effort) identical across both emitters. `effort` propagation through `pair_dispatch_events` mirrors the existing `skill` and `cycle` propagation. Bucket-key string format `<model>,<tier>,<effort>` for model_tier and `<skill>,<tier>,<effort>[,<cycle>]` for skill_tier mirrors the existing comma-separated stringification pattern. Consistent with established codebase idioms throughout.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
