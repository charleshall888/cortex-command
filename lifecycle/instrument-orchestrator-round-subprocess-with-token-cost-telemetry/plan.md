# Plan: instrument-orchestrator-round-subprocess-with-token-cost-telemetry

## Overview

Instrument `_spawn_orchestrator` to redirect its stdout to a session-scoped file with `--output-format=json`, extract round-loop emission into a testable `_emit_orchestrator_round_telemetry` helper, and wire the round loop to invoke the helper after `_poll_subprocess` returns inside a try/finally that closes the orchestrator stdout handle on every exit branch (success, non-zero, stall, shutdown, exception). Per-skill aggregator surfaces the new `orchestrator-round,<tier>` bucket without aggregator-side change.

## Tasks

### Task 1: Extend `Skill` Literal with `"orchestrator-round"` (R4)
- **Files**: `cortex_command/pipeline/dispatch.py`
- **What**: Append `"orchestrator-round"` to the closed `Skill` Literal at line 156, with an inline comment marking the value as documentation-only and never passed to `dispatch_task` (emission goes via `pipeline.state.log_event` from runner.py).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Edit the Literal definition at `cortex_command/pipeline/dispatch.py:156-164`.
  - Inline comment wording must contain the substring `documentation-only` (acceptance grep at R4b checks for it).
  - The runtime guard at `dispatch.py:432` rejects unknown skills only inside `dispatch_task`; runner.py emits via `pipeline.state.log_event` and is unaffected.
  - `metrics.py:668` falls back to `"legacy"` for unknown skills — this entry is documentation-only — but the in-place comment must say so to prevent a future reader from threading `dispatch_task("orchestrator-round", ...)` calls.
- **Verification**: `python -c "from cortex_command.pipeline.dispatch import Skill; from typing import get_args; assert 'orchestrator-round' in get_args(Skill)"` — pass if exit 0. Plus `grep -A 1 '"orchestrator-round"' cortex_command/pipeline/dispatch.py | grep -c 'documentation-only'` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Add pinned envelope fixtures
- **Files**: `cortex_command/overnight/tests/fixtures/orchestrator_envelope_success.json`, `cortex_command/overnight/tests/fixtures/orchestrator_envelope_error.json`
- **What**: Capture two canonical `claude -p --output-format=json` envelopes — one success-shaped, one error-shaped — as pinned fixtures the telemetry tests load. Includes a top-level `_cli_version` field naming the Claude CLI version used to generate the fixture so future shape drift is recoverable.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Success-fixture required keys: `result`, `session_id`, `usage` (with `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`), `total_cost_usd`, `duration_ms`, `num_turns`, `model` (or `model_id`), `is_error: false`, `subtype: "success"`. Cache-token fields may legitimately be absent for non-cached sessions; the success fixture should include realistic non-zero values to exercise the full extraction path.
  - Error-fixture required keys: same shape but with `is_error: true` (or `subtype` starting with `error_`); usage may be absent or zero.
  - Captured-from-live-CLI is the goal; if live capture is impractical, hand-construct a shape consistent with the headless docs (https://code.claude.com/docs/en/headless) and annotate `_cli_version: "synthetic"`.
- **Verification**: `python -c "import json; e=json.load(open('cortex_command/overnight/tests/fixtures/orchestrator_envelope_success.json')); assert isinstance(e, dict) and 'usage' in e and 'total_cost_usd' in e and not e.get('is_error', False)"` — pass if exit 0. Plus `python -c "import json; e=json.load(open('cortex_command/overnight/tests/fixtures/orchestrator_envelope_error.json')); assert isinstance(e, dict) and (e.get('is_error') is True or str(e.get('subtype', '')).startswith('error_'))"` — pass if exit 0.
- **Status**: [x] complete

### Task 3: Modify `_spawn_orchestrator`, extract emission helper, and wire round-loop caller (R1, R2, R3, R6, R8)
- **Files**: `cortex_command/overnight/runner.py`
- **What**: Single atomic task that (a) modifies `_spawn_orchestrator` to take a `stdout_path: Path` parameter, redirect stdout to that path, and add `--output-format=json`; (b) introduces a module-level `_emit_orchestrator_round_telemetry` helper that takes envelope text, exit code, round number, tier, and log path, parses defensively, and emits `dispatch_complete` (success-shaped) or `dispatch_error` (otherwise); (c) updates the sole caller at `runner.py:1626` to construct the stdout path, emit `dispatch_start` after the dry-run gate and before spawn, and invoke the helper after `_poll_subprocess` returns — all inside a try/finally that closes the orchestrator stdout handle on every exit branch (success, non-zero, stall, shutdown, exception). Combining function-signature change and caller update into one task eliminates the broken-intermediate-commit window.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - **Sub-change A — `_spawn_orchestrator` signature and body** (`runner.py:682-716`, the function actually spans 35 lines including the watchdog setup tail):
    - New signature parameter `stdout_path: Path` is added after `spawned_procs`. Return tuple `(proc, wctx, watchdog)` unchanged.
    - argv gains `"--output-format=json"` after `"--max-turns", str(ORCHESTRATOR_MAX_TURNS)`.
    - `stdout=subprocess.PIPE` is replaced by a write-mode file handle on `stdout_path` (the file must be opened by `_spawn_orchestrator` so the resulting handle is held by `Popen.stdout` for the caller to close).
    - `start_new_session=True`, `env={**os.environ, "CORTEX_RUNNER_CHILD": "1"}`, stderr/stdin behavior remain unchanged.
  - **Sub-change B — module-level helper `_emit_orchestrator_round_telemetry`**:
    - Signature: `_emit_orchestrator_round_telemetry(envelope_text: str | None, exit_code: int | None, round_num: int, log_path: Path) -> None`. The caller is responsible for reading the stdout file before invoking; the helper accepts the text (or `None` if the read failed).
    - Helper performs defensive `.get()` chained extraction (mirroring `pressure_runner.py`'s `data.get(...)` pattern), guards `isinstance(envelope, dict)` before any field access, and decides between `dispatch_complete` and `dispatch_error` per the spec branch rules (R3).
    - Helper invokes `pipeline_log_event` once with the resulting event dict. All I/O (parse, log_event call) is wrapped in `try/except Exception` with a `[telemetry]`-prefixed stderr breadcrumb on failure — never re-raises (fire-and-forget contract per `docs/overnight-operations.md`).
    - The helper is module-private (underscore-prefixed) and module-level so the test module can import and exercise it directly without driving the round loop.
  - **Sub-change C — round-loop caller** (`runner.py:1612-1664`):
    - The dry-run gate is at lines 1612-1617 (6 lines). The new `dispatch_start` emission must be placed STRICTLY between the `continue` at line 1617 and `_spawn_orchestrator(...)` at line 1626 — never inside or before the dry-run gate (R8 forbids dry-run telemetry writes).
    - The caller constructs the stdout path as `session_dir / f"orchestrator-round-{round_num}.stdout.json"` and passes it into `_spawn_orchestrator`.
    - `dispatch_start` is emitted via `pipeline_log_event` directly (precedent at runner.py:1301-1318); fields are `event="dispatch_start"`, `feature=f"<orchestrator-round-{round_num}>"` (literal angle brackets — invalid as a real feature name; protects FIFO pairing), `skill="orchestrator-round"`, `complexity=<tier>`, `criticality="medium"`, `model=None`, `attempt=1`. Per-session log path: `session_dir / "pipeline-events.log"` (NOT the repo-root `lifecycle/pipeline-events.log`; per-session matches `feature_executor.py`'s `config.pipeline_events_path` convention and is auto-discovered by `discover_pipeline_event_logs` at `metrics.py:270`).
    - **Spawn-and-poll lifecycle is wrapped in try/finally**. The try block runs `_spawn_orchestrator`, `_poll_subprocess`, branch handling (stall/non-zero/success), and the helper invocation. The finally block runs `proc.stdout.close()` if `proc` was constructed and `proc.stdout` is non-None and not already closed — this guarantees the write file descriptor is closed on every exit branch including stall (`break` at 1653), shutdown (`break` at 1634 when `exit_code is None`), non-zero exit (continues to batch_runner), and any exception. Re-opening the path for read is NOT a substitute for closing the write handle — the original handle must be closed explicitly.
    - After `_poll_subprocess` returns and BEFORE the existing stall-branch / non-zero-branch checks, the caller reads `stdout_path.read_text()` (wrapped in `try/except Exception` with stderr breadcrumb on failure → pass `None` to the helper) and invokes `_emit_orchestrator_round_telemetry(envelope_text, exit_code, round_num, session_dir / "pipeline-events.log")`.
    - The existing `events.ORCHESTRATOR_FAILED` emission at `runner.py:1659` and stall handling at `1636-1653` are unchanged (telemetry is additive, not a replacement) — but the try/finally close hook fires REGARDLESS of which branch is taken inside.
    - Do NOT modify `dry_run_echo` at `runner.py:1613` — its synthesized argv already omits `--dangerously-skip-permissions` and `--max-turns`; widening the gap with `--output-format=json` is a pre-existing design choice (Non-Requirements).
- **Verification**:
  - **AST-bounded structural check** for `_spawn_orchestrator`: `python -c "import ast; tree = ast.parse(open('cortex_command/overnight/runner.py').read()); fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_spawn_orchestrator'); src = ast.unparse(fn); assert 'subprocess.PIPE' not in src, 'PIPE still present'; assert 'stdout_path' in src, 'stdout_path not wired'; assert '--output-format=json' in src, 'output-format flag missing'"` — pass if exit 0.
  - **AST-based helper presence check**: `python -c "import ast; tree = ast.parse(open('cortex_command/overnight/runner.py').read()); names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]; assert '_emit_orchestrator_round_telemetry' in names"` — pass if exit 0.
  - **Caller-arity smoke check**: `python -c "import inspect; from cortex_command.overnight.runner import _spawn_orchestrator; assert 'stdout_path' in inspect.signature(_spawn_orchestrator).parameters"` — pass if exit 0 (proves the new parameter is wired at the API boundary; signature mismatch with the call site would fail Task 4 tests).
  - Functional verification of dispatch_start placement, dispatch_complete/error branching, fire-and-forget, and dry-run silence is deferred to Task 4 tests (`pytest cortex_command/overnight/tests/test_orchestrator_round_telemetry.py`).
- **Status**: [x] complete

### Task 4: Add telemetry test module (R2, R3, R5, R6, R7, R8 + fd-lifecycle)
- **Files**: `cortex_command/overnight/tests/test_orchestrator_round_telemetry.py`
- **What**: Create a single pytest module containing seven test groups: helper-direct emission tests (success → dispatch_complete; error envelope → dispatch_error; malformed JSON → dispatch_error with `parse_failure`; non-dict envelope → dispatch_error with `envelope_shape_drift`); fire-and-forget on injected `pipeline_log_event` exception; aggregator-bucket end-to-end (feeding hand-constructed events through `discover_pipeline_event_logs` → `pair_dispatch_events` → `compute_skill_tier_dispatch_aggregates`, plus `_format_skill_tier_dispatch_report` substring presence-check); stalled-round isolation (orphan dispatch_start does not poison subsequent rounds via per-round-unique feature names); dry-run gate behavior; fd-lifecycle assertions.
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**:
  - Test module path matches the spec acceptance commands: `cortex_command/overnight/tests/test_orchestrator_round_telemetry.py`.
  - **Strategy commitment — helper-direct + hand-constructed events; do NOT drive `runner.run` end-to-end**: import `_emit_orchestrator_round_telemetry` from `cortex_command.overnight.runner` and exercise it directly with synthetic envelope text; for aggregator/stalled-round tests, hand-construct event dicts and feed them through the public `pair_dispatch_events` / `compute_skill_tier_dispatch_aggregates` API. This avoids the cost of mocking `_check_concurrent_start`, `install_signal_handlers`, `_install_sigterm_tree_walker`, `auth.ensure_sdk_auth`, `WatchdogThread`, `_apply_batch_results`, `_spawn_batch_runner`, and `_post_loop` — none of which are relevant to the telemetry behavior under test. Existing tests under `cortex_command/overnight/tests/` follow this helper-isolation pattern; the only tests that drive `runner.run` end-to-end live in `tests/` at the repo root and use full subprocess boundary, which is out of scope for this module.
  - **Test naming conventions** match the spec's `pytest -k` filters: `test_dispatch_start_*`, `test_dispatch_complete_*`, `test_dispatch_error_*`, `test_parse_failure_*`, `test_fire_and_forget_*`, `test_aggregator_bucket_*`, `test_stalled_round_isolation_*`, `test_dry_run_*`, `test_fd_lifecycle_*`.
  - **Helper tests** (`test_dispatch_complete_*`, `test_dispatch_error_*`, `test_parse_failure_*`): load fixture text from `cortex_command/overnight/tests/fixtures/orchestrator_envelope_{success,error}.json`, invoke `_emit_orchestrator_round_telemetry` with various combinations of envelope text and exit codes, then read the resulting per-session `pipeline-events.log` and assert the expected event-type and field shape. Cache-token fields tolerated as `None` for the success fixture if absent; if present, assert non-None — do NOT require all four to be populated (the spec explicitly tolerates absence per Edge Cases).
  - **Dispatch-start test** (`test_dispatch_start_*`): construct a temporary `session_dir`, invoke `pipeline_log_event` directly with the same fields the round-loop caller uses (or use a thin wrapper helper if Task 3 introduces one), then assert the resulting JSONL line has the expected fields and `model is None`.
  - **Aggregator-bucket test** (`test_aggregator_bucket_*`): write `[start_R1, complete_R1]` JSONL to a temp `pipeline-events.log` and call `compute_skill_tier_dispatch_aggregates` directly. Import `_format_skill_tier_dispatch_report` from `cortex_command/pipeline/metrics.py:1196` and assert the rendered string contains the substring `"orchestrator-round"` (presence-check only — no column-alignment byte assertion per spec R5).
  - **Stalled-round isolation test** (`test_stalled_round_isolation_*`): hand-construct `[start_R1, start_R2, complete_R2]` and call `pair_dispatch_events(events)` directly. Assert `len(result) == 1`, `result[0]["feature"] == "<orchestrator-round-2>"`. Capture stderr via `capsys` and assert it does not contain `"orphan"` (orphan dispatch_start records silently stay in the FIFO queue per `metrics.py:405`/`metrics.py:439`; only orphan complete/error emit warnings).
  - **Dry-run test** (`test_dry_run_*`): rather than driving `runner.run` end-to-end (which would invoke signal handlers and other process-global side effects), assert the placement structurally: `python -m ast` walk the round-loop function, find the `if dry_run:` branch, walk its body and assert no `pipeline_log_event` call occurs inside it. Pair this with a positive assertion: walk the same function and assert `dispatch_start` emission appears in a sibling branch outside the `dry_run` block. This converts the dry-run check from a tautological "events absent" assertion into a structural "emission is correctly gated" assertion.
  - **fd-lifecycle test group** (`test_fd_lifecycle_*`): construct a `Popen`-shaped fake whose `stdout` attribute is a real `tempfile.NamedTemporaryFile` opened in write-mode. Invoke the round-loop spawn-and-emit code path (or a thin testable wrapper exposing the try/finally close protocol), force each branch (success, non-zero exit, stall flag set, shutdown via `exit_code=None`, exception raised inside the try block), and assert `proc.stdout.closed is True` after each branch. This is the regression guard against fd leak across rounds.
  - Use `tmp_path` fixture for ephemeral session directories.
- **Verification**: `pytest cortex_command/overnight/tests/test_orchestrator_round_telemetry.py -v` — pass if exit 0 and all named test groups present and passing.
- **Status**: [ ] pending

## Verification Strategy

After all tasks land, run `just test` to confirm both the new telemetry test module passes AND the existing dry-run snapshot at `tests/test_runner_pr_gating.py` (which filters DRY-RUN lines with path/SHA normalization) still passes — `just test` exit 0 covers both. If `tests/test_runner_pr_gating.py` fails because the dry-run snapshot picks up an unexpected `DRY-RUN ` line, do NOT regenerate the fixture: the failure indicates Task 3 leaked telemetry into the dry-run branch and Task 3 must be re-fixed before proceeding.

Optional out-of-band smoke check (manual operator step, not a CI gate): run `cortex overnight start` for one round in a scratch repo, then check `lifecycle/sessions/<latest>/pipeline-events.log` for an `orchestrator-round` `dispatch_start`/`dispatch_complete` pair, and verify `compute_skill_tier_dispatch_aggregates` surfaces an `orchestrator-round,<tier>` bucket. Fixtures and unit tests already cover the deterministic path.

## Veto Surface

- **Skill Literal extension (Task 1) is documentation-only**: the aggregator works whether or not `"orchestrator-round"` is in the Literal (`metrics.py:668` buckets unknown skills as `"legacy"`). The plan keeps R4 because canonical-vocabulary documentation prevents future readers from threading `dispatch_task("orchestrator-round", ...)` calls. If you'd rather omit Task 1 entirely, R4 disappears with no functional impact.
- **Per-round-unique feature names vs single sentinel**: spec mandates `<orchestrator-round-{round_num}>`. A single shared sentinel (`<orchestrator-round>`) would simplify the FIFO mental model but breaks down if a stalled round leaves an orphan start that mispairs the next round's complete. Per-round uniqueness is the safer choice.
- **Task 3 atomicity**: combining function-signature change, helper extraction, and caller wiring into a single atomic task eliminates the intermediate-broken-commit window and the dependency-edge ambiguity. The trade-off is a larger single task (one file, more changes) instead of three smaller ones. The combined task is still bounded to one file (`runner.py`) and the work is structurally cohesive — splitting introduces commit-state hazards without simplifying the work.
- **Helper extraction vs inline emission**: extracting `_emit_orchestrator_round_telemetry` adds one module-level function to runner.py. The trade-off is testability: the helper can be unit-tested without driving the round loop. If you'd rather inline the emission and skip the helper, Task 4 must drive the round loop end-to-end (mocking ~10 helpers including signal handlers) — substantially more harness for identical coverage.
- **Fixtures hand-constructed vs live-captured**: Task 2 prefers live capture but allows synthetic fallback annotated with `_cli_version: "synthetic"`. Live capture requires running `claude -p` with `--output-format=json` once.
- **`dispatch_error` for error-shaped success envelopes**: spec Edge Cases line 53 maps `is_error: true` (with exit 0) to `dispatch_error`. This prevents zero-token success envelopes from polluting the orchestrator-round bucket. If preferred, an alternative is emitting `dispatch_complete` with a flag, but this contradicts the spec's bucket-purity guarantee.

## Scope Boundaries

Maps to spec Non-Requirements. Explicitly out of scope:

- Stall-failure event emission in the watchdog stall branch (`runner.py:1636-1653`).
- Updating ticket 111's `verification.md` with a live R11/R12 baseline.
- Threading cache-token fields through `pair_dispatch_events`'s output dict.
- Editing `requirements/pipeline.md:27` ("stdout remains clean").
- Token-cost optimization or model-tier reshuffling of the orchestrator-round.
- Instrumentation of the `cortex-batch-runner` subprocess.
- Historical backfill of past sessions.
- Surfacing the new bucket in the dashboard or morning report.
- Repairing `dry_run_echo`'s synthesized-argv divergence (pre-existing; widened marginally by `--output-format=json`).
- De-dup guarding for orchestrator-round events appearing in both root and per-session logs (no emitter exists today).
