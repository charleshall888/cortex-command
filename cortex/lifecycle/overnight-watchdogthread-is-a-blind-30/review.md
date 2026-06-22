# Review: overnight-watchdogthread-is-a-blind-30

## Stage 1: Spec Compliance

### Requirement 1: Monotonic inactivity clock (not poll-tick counting)
- **Expected**: `run()` measures inactivity with a monotonic clock from an injectable source (default `time.monotonic`); tracks `last_activity_at` and `started_at`; inactivity = `now - last_activity_at`. `grep -c monotonic` ≥ 1.
- **Actual**: `runner_primitives.py:169-170` sets `started_at = self._clock()` and `last_activity_at = self._clock()`; `:219-220` computes `now = self._clock()` and `now - last_activity_at > self._timeout_seconds`. `clock: Callable[[], float] = time.monotonic` injected at `:145`. `grep -c monotonic` = 3.
- **Verdict**: PASS
- **Notes**: The old `elapsed += poll_interval` tick-counter is fully gone; the docstring (`:104-106`) states the monotonic rationale (host-scheduling-delay immunity), which the ceiling test exercises via `_StepClock`.

### Requirement 2: Two production-defaulted seams; default probe None = blind-timer-equivalent
- **Expected**: `__init__` gains `activity_probe` (callable → `(size, mtime_ns)` or `None`) and `clock`. Default `probe=None` ⇒ inactivity never resets ⇒ behaves exactly as today's blind 1800s timer. A test asserts probe=None still kills after `timeout_seconds`.
- **Actual**: `__init__` at `:144-145` adds `activity_probe=None` and `clock=time.monotonic`. In `run()` the probe block is gated by `if self._activity_probe is not None:` (`:197`), so with `probe=None` `last_activity_at` is never updated and the inactivity tier fires deterministically at `timeout_seconds`. `test_watchdog_blind_timer_kills_when_probe_none` (`test_runner_threading.py:428`) asserts the kill fires AND `stall_reason == "inactivity"`.
- **Verdict**: PASS
- **Notes**: The blind-default preserves the Phase-1 orchestrator behavior exactly, as the spec's "Phase 1 ships alone" edge case requires.

### Requirement 3: Inactivity tier reset semantics
- **Expected**: reset when `size` grew OR `mtime_ns` advanced, or first appearance from a missing/None baseline. Kill via `_kill_for_stall()` only when inactivity > `STALL_TIMEOUT_SECONDS` (1800). A forever-advancing probe is NOT killed; a static probe IS killed.
- **Actual**: `:204-217` — `saw_activity` distinguishes never-seen from `(0,0)`; first appearance resets (`:204-208`); `size > prev_size or mtime_ns > prev_mtime_ns` resets (`:211-213`); `size < prev_size` re-baselines without reset (`:214-217`). `test_watchdog_reset_keeps_growing_child_alive` proves a growing probe survives past timeout; `test_watchdog_kills_silent_child_with_inactivity_reason` proves a static probe is killed.
- **Verdict**: PASS
- **Notes**: Reset logic correctly uses OR across the two signals and treats first-appearance as activity.

### Requirement 4: Absolute-ceiling tier (never-reset)
- **Expected**: `ABSOLUTE_CEILING_SECONDS = 14400.0` with a `#:` comment marking it a deliberate conservative guess tied to Req-7 telemetry; kills once `now - started_at` exceeds it regardless of activity. A forever-advancing probe + tiny ceiling IS killed.
- **Actual**: `runner_primitives.py:39-46` defines `ABSOLUTE_CEILING_SECONDS: float = 14400.0` with the `#:` docstring stating the guess + that ceiling-kills are logged via the reason marker (the data the revisit consumes). `run()` checks `now - started_at > self._ceiling_seconds` (`:223-225`). `test_watchdog_ceiling_kills_forever_growing_child` sets `timeout_seconds=10_000, ceiling_seconds=25` so ONLY the ceiling can fire, and asserts `stall_reason == "ceiling"`. `grep -c ABSOLUTE_CEILING_SECONDS` = 2.
- **Verdict**: PASS
- **Notes**: The test correctly isolates the ceiling tier from the inactivity tier (huge timeout, tiny ceiling), so a kill there can only be the ceiling.

### Requirement 5: Robust stat
- **Expected**: missing file = no activity (no reset, no crash); reset on first appearance; size decrease re-baselines without resetting; every stat error caught (`except OSError`) so a blip never kills the daemon thread.
- **Actual**: `_stat_activity` (`runner.py:1757-1771`) catches `FileNotFoundError → None`; the broader `except OSError` wraps the probe call inside `run()` (`:198-201`), degrading a transient blip (e.g. EACCES) to no-reset. Missing→appears and stat-raises paths covered by `test_batch_runner_watchdog_probe_targets_pipeline_events_log` (None-on-missing) and `test_watchdog_probe_oserror_does_not_reset_or_crash` (raises → no reset, no crash, still kills).
- **Verdict**: PASS
- **Notes**: The split is deliberate and documented — narrow `FileNotFoundError` in the probe, broad `OSError` at the call site — and the OSError test proves both halves (no reset → still kills; no crash → kill path still runs).

### Requirement 6: New state thread-confined; no locks in reset path
- **Expected**: reset/ceiling bookkeeping is `run()`-local; no field added to `WatchdogContext`/`RunnerCoordination` except the Req-7 marker; reset path takes no `kill_lock`/`state_lock`.
- **Actual**: `started_at`, `last_activity_at`, `last_seen`, `saw_activity` are all locals in `run()` (`:169-175`). `WatchdogContext` carries only `stall_flag` + `stall_reason` (`:89-90`). `RunnerCoordination` unchanged (`:67-70`). The reset branch (`:197-217`) acquires no locks; `kill_lock` appears only on the kill path (`:237`); `state_lock` untouched.
- **Verdict**: PASS
- **Notes**: Clean separation — the only new shared field is the permitted Req-7 marker.

### Requirement 7: Kill-reason marker (must-have)
- **Expected**: records which tier fired (`inactivity` vs `ceiling`), threaded to the stall-handling log; sole feedback loop on the guessed ceiling; a test asserts ceiling-kill tagged distinctly from inactivity-kill. `grep -cE "ceiling|inactivity" runner.py` ≥ 1 in the stall region.
- **Actual**: `_kill_for_stall(reason)` sets `wctx.stall_reason = reason` BEFORE `stall_flag.set()` (`:235-236`), so a reader observing the flag also observes the reason. Both stall handlers thread it: orchestrator `_o_reason = o_wctx.stall_reason or "inactivity"` → `details={"stall_reason": _o_reason}` (`runner.py:2880-2892`); batch `_b_reason` → `details` (`:2995-3006`). Tests assert `stall_reason == "inactivity"` (silence/blind/oserror) and `== "ceiling"` (ceiling). `grep -cE "ceiling|inactivity" runner.py` = 19.
- **Verdict**: PASS
- **Notes**: Ordering (reason before flag) is correct and commented. The reason is a field on the existing kill events, not a new event type (per Non-Requirements).

### Requirement 8: Shutdown + poll ordering preserved
- **Expected**: `shutdown_event.wait()` wake-return and `proc.poll()` early-return run BEFORE any stat/reset. Existing `test_shutdown_event_wakes_watchdog_sleep` and `test_concurrent_cancel_and_stall_dont_double_kill` still pass.
- **Actual**: `run()` order is `shutdown_event.wait()` (`:179-183`, returns on wake) → `proc.poll() is not None` (`:188-189`, returns if dead) → probe/reset (`:197+`) → tier checks (`:219-225`). Both named tests pass (verified in the run — 51 passed, 2 skipped).
- **Verdict**: PASS
- **Notes**: The invariant comment at `:185-187` explicitly states the early-return runs before any stat/reset so reset never extends a child past a shutdown request.

### Requirement 9: batch_runner watchdog wired to pipeline-events.log
- **Expected**: `_spawn_batch_runner` receives the session `pipeline-events.log` path and builds the watchdog with that activity source; spawn sites + `_FakeWatchdog` updated; orchestrator passes no probe in Phase 1.
- **Actual**: `_spawn_batch_runner` takes `pipeline_events_path: Path` (`runner.py:1784`) and builds `activity_probe=lambda: _stat_activity(pipeline_events_path)` (`:1837`). Call site threads `pipeline_events_path=pipeline_events_path` (`:2982`), the same `session_dir / "pipeline-events.log"` computed at `:2798`. The capture-test `test_batch_runner_watchdog_probe_targets_pipeline_events_log` records the real `activity_probe` kwarg and drives it missing→present→grown against that exact file.
- **Verdict**: PASS
- **Notes**: Path-resolution chain (plan's `--plan session_dir/...` ⇒ `result_dir=session_dir` ⇒ `pipeline_events_path`) matches; the capture-test (not a vacuous whole-file grep) proves wiring. `_FakeWatchdog` already swallows `**kwargs`, so no signature break.

### Requirement 10: STALL_TIMEOUT_SECONDS stays 1800
- **Expected**: unchanged so `recovery.py`'s `assert WEDGED(2700) > STALL(1800)` and `test_recovery_wedged.py` keep passing.
- **Actual**: `runner.py:87` `STALL_TIMEOUT_SECONDS: float = 1800.0`. `recovery.py:98` `WEDGED_STALENESS_SECONDS = 2700.0`; `:103` `assert WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS` imports and passes (verified). `test_recovery_wedged.py` passes in the run.
- **Verdict**: PASS
- **Notes**: This is the hard non-goal guard — the number is preserved, the assert holds.

### Requirement 11: Orchestrator invoked with streaming output (de-risk-gated)
- **Expected**: `--output-format=json` → `--output-format=stream-json` + `--verbose` (only after Req 12 PASS); parser change (Req 13) already in place in the same/earlier commit. AC asserts the actual constructed argv (the bare grep was hardened to non-vacuous).
- **Actual**: De-risk VERDICT: PASS. Orchestrator argv at `runner.py:1502-1504` is `--output-format=stream-json`, `--verbose`, `--include-partial-messages`; `--output-format=json` is gone. `test_orchestrator_spawn_argv_uses_stream_json` captures the real spawn argv and asserts all three flags present AND `--output-format=json` absent. Req-13 parser (`_select_orchestrator_result_envelope`) is present in the same shipped state.
- **Verdict**: PASS
- **Notes**: The de-risk rider (`--include-partial-messages`) is correctly bundled, beyond the spec's original two-flag wording — assessed as a deliberate, operator-approved scope addition (see Stage-2 + the rider note in phase2-derisk.md). The argv test asserts the constructed list, not a whole-file grep.

### Requirement 12: De-risk gate (FIRST Phase-2 task)
- **Expected**: empirically verify stream-json to a redirected file advances mtime/size mid-stream; if it fails, do not land Reqs 11/13, fall back per operator decision; outcome recorded in the Phase-2 commit message; exactly one `^VERDICT:` line.
- **Actual**: `phase2-derisk.md` records `VERDICT: PASS` with method (real `claude -p` against a regular-file stdout, 0.5s size polling, two runs A/B), findings (Run A plain stream-json plateaued ~100s on one 29KB message; Run B + `--include-partial-messages` grew continuously, max silence 9.05s vs 1800s timeout), and a documented operator decision to bundle the rider. `grep -cE "^VERDICT: (PASS|FAIL)"` = 1.
- **Verdict**: PASS
- **Notes**: The de-risk is genuinely consumed — the rider directly drove the argv (Req 11) and parser tolerance (Req 13). The mechanism note (why not PTY: it is event-emission granularity, not libc buffering) is sound and correctly justifies `--include-partial-messages` over a PTY wrapper.

### Requirement 13: Orchestrator result parsing handles stream-json NDJSON (telemetry-only)
- **Expected**: extract the terminal `type:"result"` object instead of whole-file `json.loads`; telemetry-only (reads usage/cost/duration/turns/model/is_error/subtype/stop_reason/effort, never `result`); a test feeds a stream-json fixture and asserts terminal-result extraction + is_error/error_* classification.
- **Actual**: `_select_orchestrator_result_envelope` (`runner.py:1547`) tries whole-file `json.loads` FIRST (legacy single-envelope fast path), then on failure selects the LAST line whose top-level `type == "result"`, skipping non-result/blank/non-JSON lines, raising `ValueError` on all-garbage. `_emit_orchestrator_round_telemetry` (`:1635`) consumes it and never reads a `result` field. `test_orchestrator_telemetry.py` feeds a multi-line fixture with partial-message lines, a result-SHAPED-but-wrong-top-level-type decoy, an EARLIER genuine result with different values, blank + garbage lines, and asserts the LAST terminal result wins (`cost==0.0421`, not the decoy 99.99 or earlier 0.0001) AND that `is_error=True` / `subtype=error_*` classify as `dispatch_error`.
- **Verdict**: PASS
- **Notes**: This is the strongest test in the set — the decoy with a result-shaped body but `type:"system"` discriminates a naive "any result-shaped line" implementation, and the earlier genuine result discriminates "first" vs "last". Blast radius is telemetry legibility only, as scoped.

### Requirement 14: Orchestrator watchdog wired to its chosen child signal + why-not comment
- **Expected**: `_spawn_orchestrator` builds the watchdog with `activity_probe` over `stdout_path` (de-risk PASS); a code comment records why NOT `overnight-events.log` (parent heartbeat advances it regardless of child progress; guardian owns that signal but cannot catch a hung child).
- **Actual**: `runner.py:1541` `activity_probe=lambda: _stat_activity(stdout_path)`. The why-not comment (`:1522-1540`) states the parent `RunnerHeartbeatThread` advances `overnight-events.log` regardless of child progress (would never fire), the guardian owns parent-event-staleness but watches the PARENT and cannot catch a hung orchestrator CHILD, and the ceiling is the backstop for a loud-but-stuck child. `test_orchestrator_watchdog_probe_targets_stdout_path` captures the probe and drives it across the file's growth.
- **Verdict**: PASS
- **Notes**: The comment is accurate and load-bearing — it captures the architectural rationale the spec's "Proposed ADR: None" section relies on (code comment instead of new ADR).

### Requirement 15: Docs honesty
- **Expected**: update the stall-watchdog row (~line 43) for per-site activity-reset + absolute ceiling + per-site asymmetry; update the WEDGED>STALL margin prose (~line 301) for the honest post-change relationship.
- **Actual**: `docs/overnight-operations.md:43` describes per-site child-inactivity (`STALL_TIMEOUT_SECONDS`, resets on each child-progress write, `stall_reason="inactivity"`), the never-reset ceiling (`ABSOLUTE_CEILING_SECONDS` 14400s, `stall_reason="ceiling"`), and the asymmetry (batch watches `pipeline-events.log`; orchestrator watches its stream-json stdout). `:301` states the two layers no longer race on a shared stall definition (watchdog keys on child silence, guardian on parent-event/heartbeat staleness), the strict-greater margin lets the watchdog self-heal first, and the guardian cannot catch an active-but-doomed child mid-round — the ceiling owns that case. The stale "No event written to events log for 30 minutes" text is gone.
- **Verdict**: PASS
- **Notes**: Honest and complete — explicitly names the widened worst-case (active-but-doomed child → absolute ceiling, not 2700s), matching the spec's Technical Constraints honesty note.

### Non-Requirements / Acceptance
- **Hard non-goal (do NOT merely raise STALL_TIMEOUT)**: Honored — `STALL_TIMEOUT_SECONDS` stays 1800; the ceiling is a separate never-reset tier, and the `WEDGED(2700) > STALL(1800)` assert still holds (verified). PASS.
- **No guardian/RunnerHeartbeatThread/recovery.py change**: `recovery.py` is untouched (the assert and `test_recovery_wedged.py` pass unchanged). PASS.
- **No parent-written heartbeat as reset signal**: Both probes stat child-written files (batch → `pipeline-events.log`; orchestrator → its own stream-json `stdout_path`); the why-not comment explicitly rejects `overnight-events.log`. PASS.
- **No new event type**: The kill path reuses `ORCHESTRATOR_FAILED` / `BATCH_RUNNER_STALLED`; `stall_reason` is a `details` field on the existing events, not a new event type. PASS.
- **Acceptance criteria**: A growing-past-30-min child survives (`test_watchdog_reset_keeps_growing_child_alive`); a silent child is killed with `stall_reason="inactivity"` (`test_watchdog_kills_silent_child_with_inactivity_reason`); a forever-active-but-doomed child by `stall_reason="ceiling"` (`test_watchdog_ceiling_kills_forever_growing_child`); the orchestrator resets on stream-json stdout growth (de-risk PASS branch, probe-capture test); `just test` green for the feature group (51 passed, 2 skipped across the feature suites; full `tests` group 2002 passed per the briefing). The shipped code state matches the recorded PASS verdict. PASS.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the module. `activity_probe`/`clock`/`ceiling_seconds` are keyword-only seams matching the existing `poll_interval_seconds`/`kill_escalation_seconds` style. `_stat_activity` mirrors the `_stat_key` shape from `common.py:209` (returns `(size, mtime_ns)` — a deliberate 2-tuple subset of the 3-tuple `(exists, st_mtime_ns, st_size)`, sufficient because `None` already encodes "absent"). `_select_orchestrator_result_envelope` and `stall_reason` read naturally. The `_o_reason`/`_b_reason` locals follow the file's `_o_`/`_b_` orchestrator/batch prefix convention.
- **Error handling**: Appropriate and deliberately layered. The narrow `FileNotFoundError` in `_stat_activity` + broad `except OSError` at the probe call site in `run()` is the right split (documented at `runner_primitives.py:194-196` and `runner.py:1763-1765`): a missing file is the normal "no activity yet" case; a transient EACCES/EIO blip degrades to no-reset rather than killing the daemon thread. The telemetry parser is fire-and-forget with a `[telemetry]`-prefixed breadcrumb and never re-raises, matching the existing convention. `_kill_for_stall` re-checks `proc.poll()` under `kill_lock` and tolerates `ProcessLookupError` on every signal call. Setting `stall_reason` before `stall_flag` is the correct ordering for a flag-observing reader.
- **Test coverage**: Strong and discriminating. The behavioral threading tests inject a `_StepClock` + fake probe so timing is exact (no real sleeps on the reset path) and assert OUTCOMES — `test_watchdog_reset_keeps_growing_child_alive` fails against a blind impl (a blind timer would kill the growing child); the silence/blind/ceiling tests assert the exact `stall_reason` tag, so a mis-tagged tier fails; the ceiling test isolates the tier via `timeout_seconds=10_000, ceiling_seconds=25`. The argv test (`test_orchestrator_spawn_argv_uses_stream_json`) asserts the REAL captured spawn list (all three flags present + `--output-format=json` absent), not a whole-file grep — the comment at `test_runner_sandbox.py:124-131` explicitly calls out the vacuous-grep hazard and avoids it. Both probe-capture tests record the real `activity_probe` kwarg and drive it missing→present→grown against the exact target file. The NDJSON test includes a decoy non-terminal result-shaped line, an earlier genuine result, and partial-message lines, proving "last terminal result wins" rather than "any result-shaped line". The plan's verification steps are executed.
- **Pattern consistency**: Consistent with existing `runner.py`/`runner_primitives.py` conventions. The watchdog keeps the no-blocking-sleep loop shape (`coord.shutdown_event.wait(timeout=...)`), the daemon-thread model, and the `WatchdogContext`-per-subprocess pattern. The `_stat_activity` helper reuses the established safe-stat idiom. The telemetry selector preserves backward-compat with the single-envelope path (whole-file `json.loads` tried first). No refactor of `runner.run()` that would break the `test_runner_heartbeat.py` AST-walk (it passes).

## Requirements Drift
**State**: detected
**Findings**:
- The **absolute ceiling** concept (`ABSOLUTE_CEILING_SECONDS`, 14400s, never-reset secondary kill tier) is a new operator-tunable behavior not captured in any requirements area doc. `cortex/requirements/pipeline.md` (the overnight-runner area doc) describes the pipeline/recovery surface but contains no description of the in-process stall watchdog at all — no `STALL_TIMEOUT`, no ceiling, no in-process-watchdog-vs-guardian supervision split.
- The **per-site activity-reset model** (batch watches `pipeline-events.log`, orchestrator watches its stream-json stdout; the watchdog now keys on child silence rather than a blind 30-minute timer) is new behavior absent from pipeline.md.
- The **`--include-partial-messages` dependency** — the orchestrator's child-progress signal now depends on a specific Claude Code flag whose removal/regression (cf. Issue #25670) would silently degrade the orchestrator watchdog to ceiling-only — is an operational coupling not recorded in the requirements docs.
- The **`stall_reason` telemetry** (`inactivity` vs `ceiling` on kill events, the sole feedback loop for revisiting the guessed ceiling) is a new observable not noted in `cortex/requirements/observability.md`.
- Note: the briefing referenced `cortex/requirements/glossary.md`, which does not exist; the actual requirements files are `multi-agent.md`, `observability.md`, `pipeline.md`, `project.md`, `remote-access.md`. This does not change the verdict (drift is observation-only) but the canonical target for the supervision/watchdog description is `pipeline.md`.

**Update needed**: cortex/requirements/pipeline.md (primary); cortex/requirements/observability.md (secondary, for the stall_reason observable)

## Suggested Requirements Update

**File**: cortex/requirements/pipeline.md
**Section**: Overnight runner supervision (new subsection, alongside the recovery/guardian behavior)
```
- In-process stall watchdog: per spawned child (orchestrator, batch_runner), a monotonic
  inactivity timer (`STALL_TIMEOUT_SECONDS`, 1800s) that RESETS on each child-progress write
  to the watched child signal (batch → `pipeline-events.log`; orchestrator → its stream-json
  stdout, which requires `--output-format=stream-json --verbose --include-partial-messages`),
  plus a never-reset `ABSOLUTE_CEILING_SECONDS` (14400s) backstop for a loud-but-stuck child.
  This is distinct from and strictly inside the guardian's `WEDGED_STALENESS_SECONDS` (2700s)
  parent-staleness window; the watchdog owns child silence, the guardian owns parent/host wedge.
```

**File**: cortex/requirements/observability.md
**Section**: Overnight kill/stall telemetry
```
- Stall-kill events (`ORCHESTRATOR_FAILED`, `BATCH_RUNNER_STALLED`) carry a `stall_reason`
  field (`inactivity` | `ceiling`) distinguishing a silent/wedged child from an
  absolute-ceiling kill — the feedback signal for tuning the (currently guessed) ceiling value.
```

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
