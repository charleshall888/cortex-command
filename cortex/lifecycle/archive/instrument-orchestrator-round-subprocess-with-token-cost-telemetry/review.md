# Review: instrument-orchestrator-round-subprocess-with-token-cost-telemetry

## Stage 1: Spec Compliance

### Requirement R1: `_spawn_orchestrator` redirects subprocess stdout to a session-scoped file
- **Expected**: PIPE removed from `_spawn_orchestrator`, `--output-format=json` added to argv, `<session_dir>/orchestrator-round-{round_num}.stdout.json` used as stdout file path.
- **Actual**: At `cortex_command/overnight/runner.py:682-726`, the function takes a `stdout_path: Path` parameter, opens `stdout_handle = open(stdout_path, "wb")`, passes it to `subprocess.Popen(..., stdout=stdout_handle, stderr=subprocess.DEVNULL)`, and includes `--output-format=json` in argv. The caller at runner.py:1769-1771 constructs `session_dir / f"orchestrator-round-{round_num}.stdout.json"`. Acceptance greps confirm: PIPE count = 0, `--output-format=json` count = 2 (argv literal + module docstring reference inside the helper window), `orchestrator-round-{round_num}` count = 3.
- **Verdict**: PASS
- **Notes**: The Task 3 deviation (stderr → DEVNULL) is consistent with the spec's intent — DEVNULL has the same no-consumer semantics as the prior buffered PIPE and removes a latent stderr-pipe-fill deadlock. Functional behavior is preserved (no observer existed before, none exists now), and the spec's line "stderr/stdin behavior remain unchanged" is satisfied at the consumer-visibility level. No regression risk identified — the only reachable change is that an OS pipe is no longer allocated.

### Requirement R2: Emit `dispatch_start` between dry-run gate and `_spawn_orchestrator`
- **Expected**: `pipeline_log_event` call placed AFTER the per-round `if dry_run: ... continue` (runner.py:1751-1756) and BEFORE `_spawn_orchestrator(...)`. Required fields: `event="dispatch_start"`, `feature="<orchestrator-round-{round_num}>"`, `skill="orchestrator-round"`, `complexity=<tier>`, `criticality="medium"`, `model=null`, `attempt=1`. Per-session `pipeline-events.log`. Pytest acceptance + dry-run negative assertion.
- **Actual**: At runner.py:1765-1795, `pipeline_log_event` is invoked after the `if dry_run: ... continue` block (1751-1756) and before `_spawn_orchestrator` (1798). All required fields present with correct values; `model=None` is explicit. Path is `session_dir / "pipeline-events.log"`. The test class `TestDispatchStart::test_dispatch_start_emits_skill_and_null_model` asserts the field shape; `TestDryRun::test_dry_run_branch_has_no_pipeline_log_event` asserts no `pipeline_log_event` call inside the dry-run gate body via AST walk. `pytest -k dispatch_start` exits 0 (2 passed).
- **Verdict**: PASS
- **Notes**: AST gate-placement test is a structural pin rather than a behavioral integration test, but the placement is unambiguous and the dry-run negative assertion is also AST-structural. Acceptable given the spec's note that driving `runner.run` end-to-end requires extensive harness mocking.

### Requirement R3: Emit `dispatch_complete` (success) or `dispatch_error` (failure) after `_poll_subprocess`
- **Expected**: Branch by exit_code + envelope shape; `dispatch_complete` only when exit=0 AND envelope is dict AND not error-shaped (`is_error` falsy AND `subtype` does not start with `"error_"`); else `dispatch_error` with reason recorded in `details`. Defensive `.get()` chains. Cache fields tolerated as None.
- **Actual**: `_emit_orchestrator_round_telemetry` at runner.py:729-855 implements the branch as specified: success_shaped at lines 800-805, dispatch_error reason classification at lines 821-833 covering `parse_failure`, `envelope_shape_drift` (with `top_level_type` recorded), `is_error`, and `non_zero_exit`. Field extraction uses `envelope.get(...)` and `usage.get(...)` chains throughout, with `model = envelope.get("model") or envelope.get("model_id")` matching spec model-name-drift handling. `pytest -k "dispatch_complete or dispatch_error or parse_failure"` exits 0 (7 passed). The success fixture populates `input_tokens=1842`, `output_tokens=612`, `cache_creation_input_tokens=5120`, `cache_read_input_tokens=23450`; the error fixture's `is_error=True` triggers `dispatch_error` with `details["reason"]=="is_error"`.
- **Verdict**: PASS
- **Notes**: All four failure branches (parse_failure, shape_drift, is_error, non_zero_exit) explicitly tested. `dispatch_error` carries the same field set as `dispatch_complete` (cost_usd, duration_ms, num_turns, model, token fields) plus `details`, satisfying the spec's "missing fields are None" requirement.

### Requirement R4: `Skill` Literal extended with `"orchestrator-round"` plus inline documentation comment
- **Expected**: Add `"orchestrator-round"` to the closed Literal at `dispatch.py:156` with an inline comment matching `# documentation-only; emitted via pipeline.state.log_event from runner.py and never passed to dispatch_task`.
- **Actual**: At `cortex_command/pipeline/dispatch.py:164`: `"orchestrator-round",  # documentation-only: never passed to dispatch_task; runner.py emits via pipeline.state.log_event`. The acceptance test `python3 -c "from cortex_command.pipeline.dispatch import Skill; from typing import get_args; assert 'orchestrator-round' in get_args(Skill)"` exits 0. Grep for documentation-only matches 1 line.
- **Verdict**: PASS
- **Notes**: Comment wording differs slightly from the spec literal but conveys equivalent content (per spec's "or wording with the same content" allowance).

### Requirement R5: Aggregator surfaces `orchestrator-round,<tier>` bucket end-to-end and report formatter renders it
- **Expected**: Integration test feeds JSONL through `discover_pipeline_event_logs → pair_dispatch_events → compute_skill_tier_dispatch_aggregates`; asserts bucket key + non-null cost_usd/num_turns; calls `_format_skill_tier_dispatch_report` and asserts substring presence.
- **Actual**: `TestAggregatorBucket::test_aggregator_bucket_orchestrator_round` (lines 362-435) constructs the lifecycle/sessions/s1/pipeline-events.log layout, writes paired start+complete via `pipeline_log_event`, calls all three pipeline functions, asserts `"orchestrator-round,complex" in aggregates`, `bucket["n_completes"] == 1`, non-null `estimated_cost_usd_mean` and `num_turns_mean`, and `"orchestrator-round" in rendered`. Test passes.
- **Verdict**: PASS

### Requirement R6: Fire-and-forget telemetry contract
- **Expected**: Any exception during stdout-file open, JSON parse, or `pipeline_log_event` is caught, logged with `[telemetry]` prefix, never propagates.
- **Actual**: Helper-level try/except at runner.py:748-855 wraps the entire emission with stderr breadcrumb. `TestFireAndForget::test_fire_and_forget_pipeline_log_event_raises` monkeypatches `state.log_event` to raise `RuntimeError`; helper does not propagate, breadcrumb appears on stderr. `test_fire_and_forget_malformed_json_does_not_raise` confirms malformed JSON results in `dispatch_error` rather than exception. The round-loop emission path also wraps `pipeline_log_event` for `dispatch_start` (runner.py:1773-1795) in try/except with `[telemetry]` breadcrumb. Stdout-read failure at runner.py:1810-1818 is similarly guarded. Pytest acceptance passes.
- **Verdict**: PASS

### Requirement R7: Stalled rounds do not poison subsequent rounds' pairing within a single session
- **Expected**: With `[start_R1, start_R2, complete_R2]`, `pair_dispatch_events` returns 1 paired result for R2 with no orphan warnings on stderr.
- **Actual**: `TestStalledRoundIsolation::test_stalled_round_isolation_orphan_start_silent` constructs exactly the spec's three-event sequence, calls `pair_dispatch_events`, asserts `len(result) == 1`, `result[0]["feature"] == "<orchestrator-round-2>"`, `result[0]["outcome"] == "complete"`, and verifies no `"orphan"` substring in `capsys.readouterr().err`. Passes.
- **Verdict**: PASS

### Requirement R8: Dry-run mode emits no telemetry
- **Expected**: When `dry_run=True`, no stdout file created, no dispatch records appended. `tests/test_runner_pr_gating.py` continues to pass; AST or behavioral assertion that `pipeline-events.log` is absent or has no orchestrator-round records.
- **Actual**: `tests/test_runner_pr_gating.py` exits 0 (13 passed). `TestDryRun::test_dry_run_branch_has_no_pipeline_log_event` asserts via AST that the dry-run gate body contains no `pipeline_log_event` call; `test_dry_run_dispatch_start_emitted_outside_dry_run_branch` asserts the literal `"dispatch_start"` appears outside that gate's body. The dry-run path at runner.py:1751-1756 contains only `dry_run_echo`, state mutation, and `continue` — no telemetry emission, no stdout file open.
- **Verdict**: PASS
- **Notes**: AST-only assertion is acceptable here because the dry-run code path is structurally simple (3 statements before `continue`); a behavioral regression that re-introduces telemetry would be syntactically detectable.

## Requirements Drift

**State**: none
**Findings**: None — the implementation extends existing pipeline.md acceptance criteria ("Audit trail", "Metrics and Cost Tracking") in their natural direction by adding `orchestrator-round` records to per-session `pipeline-events.log`. The Task 3 stderr → DEVNULL change does not contradict project.md (no project requirement constrains orchestrator-subprocess stderr handling) or pipeline.md (the audit-trail criterion describes pipeline-events.log JSONL append semantics, not subprocess stderr buffering). Functional pre-change behavior was buffer-with-no-consumer; functional post-change behavior is discard-with-no-consumer — equivalent at the observability boundary. Cache-token fields (cache_creation_input_tokens / cache_read_input_tokens) are emitted but the spec explicitly excludes threading them through `pair_dispatch_events`'s output dict, and pipeline.md's "Metrics and Cost Tracking" criteria do not enumerate cache fields, so no requirements update is needed.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Helper name `_emit_orchestrator_round_telemetry` matches the runner.py underscore-private convention (`_spawn_orchestrator`, `_spawn_batch_runner`, `_poll_subprocess`, `_count_pending`, `_save_state_locked`, etc.). The verb-noun-context pattern is consistent. Local variable names (`envelope_text`, `parse_reason`, `top_level_type`, `success_shaped`, `event_dict`) are descriptive and match the spec's terminology. PASS.
- **Error handling**: Defensive `.get()` chains throughout (`envelope.get("usage", {}) or {}`, `envelope.get("model") or envelope.get("model_id")`); `isinstance(envelope, dict)` guards before `.get()` to handle non-dict top-level drift; both the helper and the dispatch_start emission site at runner.py:1773-1795 have try/except with `[telemetry]`-prefixed stderr breadcrumbs and no propagation. The stdout-read failure path at runner.py:1810-1818 emits a separate breadcrumb before invoking the helper with `envelope_text=None`, which the helper handles via the `parse_failure` branch. Fire-and-forget contract correctly observed. PASS.
- **Test coverage**: 20 tests across 7 test classes — TestDispatchStart (1), TestDispatchComplete (2), TestDispatchError (3), TestParseFailure (2), TestFireAndForget (2), TestAggregatorBucket (1), TestStalledRoundIsolation (1), TestDryRun (2), TestFdLifecycle (6). Every spec acceptance criterion has a matching test. The fd-lifecycle tests exercise five branches (success, non-zero, stall, shutdown, exception) plus a structural pin asserting `<proc>.stdout.close()` exists in `runner.run`'s AST. The Task 4 deviation (in-test `_round_loop_close_handle` wrapper mirroring the production try/finally rather than driving the production path) is compensated by the structural AST pin (`test_fd_lifecycle_runner_finally_block_present`) — if the production close-protocol is removed or refactored away, the AST pin fires. This is sufficient because (a) driving `runner.run` end-to-end is impractical given the harness mocking burden, (b) the close protocol itself is a 7-line try/finally with no branching logic worth integration-testing, and (c) the wrapper is a verbatim copy of the production block (lines 1859-1872 vs 638-654). PASS.
- **Pattern consistency**: `pipeline_log_event` import-and-call pattern at runner.py:1773-1788 matches the precedent at runner.py:1301-1318 — local import within the call site (not module-level), one event dict argument, fire-and-forget try/except wrapping. Per-session log path `session_dir / "pipeline-events.log"` matches `feature_executor.py`'s `config.pipeline_events_path` convention (also picked up by `discover_pipeline_event_logs` at metrics.py:288 via `sessions/*/pipeline-events.log` glob). The stdout file lives in `session_dir`, consistent with other per-round artifacts (`batch-{n}-results.json`, `batch-plan-round-{n}.md`, `overnight-strategy.json`). PASS.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
