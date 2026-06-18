# Review: overnight-run-now-runner-left-session

## Stage 1: Spec Compliance

### Requirement 1: Runner-pid-death detection predicate (false-positive-free)
- **Expected**: Pure read-only predicate flags recovery iff `phase == "executing"` AND `verify_runner_pid` is False; no event-log staleness term; does not false-positive on live work.
- **Actual**: `recovery.needs_recovery_pid_death(session_dir)` returns `_session_phase(session_dir) == "executing" and not status._is_runner_pid_live(session_dir)`. `_is_runner_pid_live` wraps the create_time-±2s `verify_runner_pid` primitive. No staleness term. `tests/test_recovery_predicate.py` covers executing+dead→True, executing+live→False, paused/complete→False.
- **Verdict**: PASS
- **Notes**: Mirrors the `fail_markers` shape per spec; phase-other-than-executing short-circuits to False. Tested behaviorally (real live pid for the false case).

### Requirement 2: Recovery core sequence
- **Expected**: Single idempotent function: re-confirm under lock → transition→`paused` + `paused_reason="orchestrator_crash"` + atomic save → `update_active_session_phase` (retain pointer) → partial report → reap → `clear_runner_pid`; uses pure primitives, NOT the runner's `_transition_paused`/`_generate_morning_report`.
- **Actual**: `recovery.recover_session` performs steps 1-7 in exactly the spec order using `state_mod.transition`, `state_mod.save_state`, `ipc.update_active_session_phase`, `report.generate_and_write_report`, `reap_session_orphans`, `ipc.clear_runner_pid`. It never references the runner's in-process-lock helpers. `crash_recovery_attempts` is incremented at step 2. `tests/test_recovery_core.py` drives a synthesized stuck+dead-pid session and asserts final `phase==paused`, `paused_reason==orchestrator_crash`, report exists, runner.pid cleared.
- **Verdict**: PASS
- **Notes**: Active-session pointer is retained (`update_active_session_phase`, not cleared) per spec step 3. Report write is best-effort (try/except) so a render failure does not block the transition/reap/clear — appropriate.

### Requirement 3: Idempotency + concurrency safety
- **Expected**: Whole sequence under `ipc._acquire_takeover_lock`; second invocation a no-op (guarded by phase ∈ {paused,complete} and a `recovery-complete.json` sidecar); never relies on `transition` raising; atomic writes.
- **Actual**: Lock acquired at function top, released in `finally` via `LOCK_UN` + `os.close`. Layered guard under the lock: (a) sidecar-exists short-circuit checked FIRST, (b) post-lock state reload with `phase in ("paused","complete")` catch-first guard, then a unified-predicate re-confirm. Sidecar written atomically via `ipc._atomic_write_json` as step 7. `tests/test_recovery_idempotency.py` proves the second call is a no-op via mtime+raw-bytes stability and confirms the phase guard works even with the sidecar removed (never relying on `transition` raising).
- **Verdict**: PASS
- **Notes**: Single-valued `paused_reason` design (no `_recovered` flip in state) keeps the completion marker out of the clobberable state file — the sidecar is the race-authoritative marker, exactly as specced.

### Requirement 4: Partial morning report with the interrupted banner
- **Expected**: Recovery writes a partial report conveying death timestamp + gap vs pipeline-events ts, non-terminal-feature count, and reap outcome; both report paths written. (Banner via the `orchestrator_crash` branch in `render_executive_summary`, NOT a `--interrupted` flag.)
- **Actual**: `recover_session` sets `paused_reason="orchestrator_crash"` BEFORE calling `report.generate_and_write_report`, so `render_executive_summary` dispatches to `_render_orchestrator_crash_banner` (keyed on `paused_reason`, line 589). The banner renders the death ts (last overnight-events.log event), the pipeline-events gap line when present, the non-terminal count, and the reap line (from the sidecar). `generate_and_write_report` writes both `session_dir/morning-report.md` and `project_root/cortex/lifecycle/morning-report.md`. `tests/test_recovery_report.py` asserts both paths exist, the banner header + non-terminal count + death ts + gap line render, and that the `budget_exhausted` banner is byte-unchanged (no regression).
- **Verdict**: PASS
- **Notes**: Render path is exactly the `orchestrator_crash` branch as the spec note describes; no `--interrupted` flag is used on the recovery path. Reap line is defensively omitted on recovery's own first render (sidecar written after the report) and surfaces on a later re-render — tested.

### Requirement 5: Orphan reaping by session-marker enumeration
- **Expected**: Enumerate via psutil, select only `CORTEX_RUNNER_CHILD=1` AND `LIFECYCLE_SESSION_ID==session_id`; never broad-match `claude`; SIGTERM→grace→SIGKILL; re-read create_time before each signal (TOCTOU guard).
- **Actual**: `reap_session_orphans` → `_select_matched` → `_env_matches_session` requires the AND of both markers; un-introspectable env is a non-match (swallowed). SIGTERM→`wait_procs`(grace)→SIGKILL per pass, with `_toctou_alive` re-reading create_time immediately before each signal. Bounded fixpoint (`_REAP_FIXPOINT_MAX_PASSES=3`) catches children forked during the grace window; still-matched pids at the cap surface as `unreaped` (never broad-matched). `tests/test_recovery_reaper.py` asserts: only env-matched selected, a same-session interactive `claude` lacking `CORTEX_RUNNER_CHILD` never selected, fixpoint reaps a 2nd-pass child, survivor SIGKILLed, unreaped surfaced at cap, TOCTOU create_time-change skips the kill, per-process exception isolation. Fixture-driven selection, no real kill — per spec.
- **Verdict**: PASS
- **Notes**: The brain-path `claude -p` marker question (spec Open Decision) is handled correctly by the fallback: unmatched classes surface as `unreaped` rather than triggering a broad match. The `_RUNNER_CHILD_MARKER` docstring correctly documents why `LIFECYCLE_SESSION_ID` alone is insufficient (interactive sessions carry it).

### Requirement 6: Persistent guardian (the automatic trigger)
- **Expected**: A single host-level launchd guardian on a StartInterval cadence (NOT per-session) scanning all `executing` sessions, applying the predicate, invoking the recovery core; install/remove verbs; documented who-watches-the-watchman posture; reuse `scheduler/macos.py`.
- **Actual**: `guardian.scan_and_recover` enumerates `sessions/*/` (skipping symlinks, requiring `overnight-state.json`), applies the unified `needs_recovery` predicate, invokes `recover_session(trigger="guardian")`, with per-session try/except isolation (an `action="error"` result per poison session, scan continues). `scheduler/macos.py` `build_guardian_plist_dict` produces a fixed-label (`GUARDIAN_LABEL`) plist with `StartInterval=300`, `ThrottleInterval=60`, NO bare `KeepAlive`, threading `CORTEX_REPO_ROOT`. `install_guardian`/`remove_guardian` reuse `_bootstrap_and_verify` / `launchctl bootout` + `_safe_unlink`, idempotent re-install. `tests/test_guardian_scan.py` proves a stuck session recovered while a healthy one is untouched and a poison one is isolated, parametrized over BOTH enumeration orders. `tests/test_guardian_install.py` (14 tests) covers the plist shape, label, no-KeepAlive, idempotent re-install, off-macOS guard.
- **Verdict**: PASS
- **Notes**: Single-agent design is the load-bearing choice and is documented. The who-watches-the-watchman story (StartInterval re-fire + ThrottleInterval floor, manual verb backstop) is in both the plist builder docstring and `docs/overnight-operations.md`.

### Requirement 7: Manual recovery verb (complementary surface)
- **Expected**: `cortex overnight recover [--session <id>]` from a writer-authorized surface, NOT in read-only `status`; self-heals/reports cleanly when nothing to recover.
- **Actual**: `cli._dispatch_overnight_recover` resolves the target via `--session` (with `session_validation.resolve_session_dir` R17 validation + containment) or the active-session pointer, then calls `recovery.recover_session(trigger="manual")`. Prints "nothing to recover" and exits 0 on no-op / no resolvable session. The verb is a distinct subparser (`recover`), separate from `status`. `tests/test_cli_overnight_recover.py` (6 tests) covers --help listing --session, recovery of a synthesized stuck session to paused, and clean no-op paths.
- **Verdict**: PASS
- **Notes**: Not folded into `status` — respects the `observability.md` read-only constraint. Invalid session id returns exit 1 (distinct from the clean no-op exit 0), which is reasonable.

### Requirement 8: runner.pid clear-on-crash
- **Expected**: A non-signaled runner exit best-effort clears `runner.pid`; recovery also clears it; the recorded-pid write path is unchanged.
- **Actual**: `runner.run`'s `finally` block calls `ipc.clear_runner_pid(session_dir, expected_session_id=session_id)` (CAS on session_id), swallowing errors, so a crash/exception loop-exit leaves no stale pid. The signal path (`_cleanup`) and clean path (`_post_loop`) already clear it; this broadens to the third path. `runner.pid` is still recorded with `os.getpid()` in `_start_session` (unchanged). `tests/test_runner_finally_clears_pid.py` covers the CAS clear behavior, the foreign-owner no-op (CAS safety), plus an AST wiring guard.
- **Verdict**: PASS
- **Notes**: The CAS on `session_id` correctly prevents a displaced owner from clobbering a successor's claim. AST guard is justified (verify_runner_pid ±2s create_time makes a full in-process `run` drive infeasible) and paired with behavioral coverage of the clear itself.

### Requirement 9: Crash-loop resume guard
- **Expected**: `crash_recovery_attempts` counter on `OvernightState`; resume refuses to auto-resume an `orchestrator_crash`-paused session past a small bound (default 1) without `--force`; a clean pause is unaffected.
- **Actual**: `state.crash_recovery_attempts: int = 0` with `__post_init__` validation and `load_state` backward-compat default. `runner._crash_loop_resume_declined` declines iff (not force) AND `paused_reason==orchestrator_crash` AND `attempts > CRASH_RECOVERY_RESUME_BOUND (1)` AND the `recovery-complete.json` sidecar exists. `--force` (threaded through `cli.py` start parser → `cli_handler` direct `run()` and async-spawn argv) bypasses it. `tests/test_crash_loop_guard.py` covers decline-over-bound, proceed-with-force, budget_exhausted-never-declined, at-bound-resumes, no-sidecar-resumes.
- **Verdict**: PASS
- **Notes**: The sidecar requirement on the decline path is a thoughtful addition — the over-bound counter alone is not the decline signal (a counter could survive from an unrelated path); the sidecar is the race-authoritative "recovery actually ran" marker.

### Requirement 10: Event registration + docs
- **Expected**: New event names registered in `bin/.events-registry.md`; `docs/overnight-operations.md` documents the supervision model/recovery sequence/manual verb/guardian + caffeinate limitation; `docs/internals/pipeline.md` links to it. `grep -c "recover"` ≥1 and `grep -c "caffeinate"` ≥1.
- **Actual**: `orchestrator_crash_recovered` registered in both `events.py` `EVENT_TYPES` and `bin/.events-registry.md` (row 145). The events-registry audit gate exits 0 (stale-deprecation warnings are pre-existing, unrelated rows). `docs/overnight-operations.md` has a full "Out-of-Process Supervision" section (supervision model, recovery sequence, manual verb, persistent guardian, who-watches-the-watchman, caffeinate-sleep limitation). `docs/internals/pipeline.md` links to it (line 156-159). `grep -c "recover"` = 45, `grep -c "caffeinate"` = 6.
- **Verdict**: PASS
- **Notes**: One minor doc inaccuracy (see Stage 2 Test/Pattern notes): the events-registry row's prose says the report surfaces recovery via `OvernightState.paused_reason="orchestrator_crash_recovered"`, but the implementation deliberately keeps `paused_reason="orchestrator_crash"` single-valued. Comment-only; no behavioral impact and does not fail the gate.

### Requirement 11: Close the planning-phase heartbeat blind window
- **Expected**: A runner-level heartbeat on a fixed cadence across ALL `executing` sub-phases (planning + batch) so event-log staleness becomes a valid liveness signal in every phase.
- **Actual**: `RunnerHeartbeatThread` (daemon, `RUNNER_HEARTBEAT_INTERVAL_SECONDS=300`) emits `events.HEARTBEAT` (reusing the registered literal, source=`runner`) across the full planning→batch span; sleeps on `_stop_event.wait` and honors `coord.shutdown_event`; started in `run()` (skipped under dry_run), stopped in the `finally`; `set_round` re-stamps the round. `tests/test_runner_heartbeat.py` simulates the planning-phase window (silent log) and asserts a single emit advances `status._read_last_event_ts` (the exact source Task 15's predicate keys on), drives a real thread tick, and covers stop/shutdown reaping, set_round, and best-effort swallow.
- **Verdict**: PASS
- **Notes**: Additive — does not touch the batch `_heartbeat_loop`; a redundant beat during the batch span is harmless. One AST wiring guard (`test_run_is_wired_to_start_the_runner_heartbeat`) is justified and paired with strong behavioral coverage.

### Requirement 12: Staleness predicate for the wedged case (safe threshold + SIGKILL-before-transition)
- **Expected**: `executing` AND pid alive AND last heartbeat older than a threshold strictly > `STALL_TIMEOUT_SECONDS` (1800s) flags a wedged runner; recovery SIGKILLs the create_time-verified runner BEFORE transitioning.
- **Actual**: `WEDGED_STALENESS_SECONDS=2700.0` with a module-level `assert WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS` fail-loud invariant. `needs_recovery_wedged` requires executing + pid-alive + a real parseable last-event ts older than the threshold (absent/unparseable ts → not stale). `recover_session` calls `_sigkill_wedged_runner` (which re-verifies via `verify_runner_pid` before `os.kill(pid, SIGKILL)`) BEFORE `state.transition` in the wedged branch only. `tests/test_recovery_wedged.py` covers the threshold relationship, the boundary cases (±60s), the no-heartbeat case, the SIGKILL-before-transition call ordering (shared call log), a regression guard that pid-death does NOT SIGKILL, and the guardian path via the unified gate.
- **Verdict**: PASS
- **Notes**: The 900s margin over 1800s lets the in-process watchdog self-heal first, exactly the spec's safety rationale. `_sigkill_wedged_runner` re-verifies create_time ±2s immediately before the kill so a reused pid is never signalled.

### Requirement 13: Document the caffeinate-sleep limitation
- **Expected**: Document that `caffeinate -i -w <runner_pid>` dies with the runner, bounding hard-dead detection to next machine wake; name the guardian, the wake bound, and the manual verb as the immediate path; `grep -c "caffeinate"` ≥1.
- **Actual**: `docs/overnight-operations.md` "The caffeinate-sleep limitation (macOS)" section explains the bound, distinguishes the alive-but-wedged (prompt) vs hard-dead (next-wake) latency floors, names the manual `recover` verb as the immediate path, and notes the optional future guardian-maintained caffeinate should-have. `grep -c "caffeinate"` = 6. ADR-0011 also records it.
- **Verdict**: PASS
- **Notes**: The "still strictly better than stuck-forever" framing matches the spec.

### Non-Requirements honored
- **#262 systemic circuit breaker NOT changed**: confirmed — no edits to `outcome_router.py` breaker counting; `cortex_command/overnight/tests/test_synthesizer_circuit_breaker.py` (modified only) passes. PASS.
- **runner.pid record-pid unchanged**: `_start_session` still records `os.getpid()`; no schema bump (`schema_version` stays 1). PASS.
- **No migration off file-based state**: recovery is grounded in existing file artifacts (state.json, runner.pid, events.log, the new sidecar). PASS.

### Recovery↔resume ordering (central race-safety concern)
- **Expected**: The resume guard must acquire the takeover lock and read the `recovery-complete.json` sidecar + counter BEFORE `handle_interrupted_features` mutates state.
- **Actual**: `_start_session` acquires the takeover lock at the TOP of the resume path (inside `deferred_signals`), then runs `_crash_loop_resume_declined` (reads sidecar + counter) and returns the refusal sentinel BEFORE `interrupt.handle_interrupted_features` is called — all under the one held FD, which is then threaded into `_check_concurrent_start` and `write_runner_pid` (lock acquired once, never twice). `tests/test_crash_loop_guard.py::test_guard_declines_before_feature_status_reset` drives `_start_session` with a tripwire on `handle_interrupted_features` and asserts a `running` feature stays un-reset on a declined resume; the symmetric `--force` test asserts interrupt recovery runs when the guard is bypassed.
- **Verdict**: PASS — the lock reorder is correct and directly tested.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the codebase. Module-level constants (`WEDGED_STALENESS_SECONDS`, `CRASH_RECOVERY_RESUME_BOUND`, `RUNNER_HEARTBEAT_INTERVAL_SECONDS`, `ORCHESTRATOR_CRASH_PAUSED_REASON`, `RECOVERY_COMPLETE_SIDECAR`, `GUARDIAN_LABEL`) are named, documented, and test-referenced rather than bare literals. Private helpers use the `_leading_underscore` convention; dataclasses (`ReapOutcome`, `RecoveryResult`) mirror existing result-object patterns. Trigger values (`"guardian"`/`"manual"`) are threaded consistently.
- **Error handling**: Appropriately layered. Best-effort swallowing where the spec calls for it: the report render (must not block transition/reap/clear), the heartbeat emit (liveness not durability), the finally pid-clear, the completion-event emit (unregistered-name ValueError), per-process reaper exceptions, and the SIGKILL of a vanished/reused pid. Fail-loud where it matters: the `assert WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS` invariant; the guardian's per-session isolation records `action="error"` rather than silently dropping; `transition` still raises on illegal phases (the recovery core just never relies on that, using catch-first phase guards). The takeover lock is always released in a `finally` (LOCK_UN + os.close).
- **Test coverage**: Strong and predominantly behavioral. The plan's per-task Verification steps are exercised by real integration tests driving synthesized on-disk sessions through the actual code paths (recovery core, idempotency, report, wedged, guardian scan, crash-loop ordering, reaper selection). The central race-safety concern (recovery↔resume ordering) is directly tested with a tripwire. Three AST/source-inspection wiring guards exist (`test_run_finally_is_wired_to_clear_runner_pid`, `test_run_is_wired_to_start_the_runner_heartbeat`, and the finally-stops-thread assertion within it) — but each is (a) explicitly justified by the `verify_runner_pid` ±2s create_time constraint that makes a faithful in-process `run()` drive infeasible, and (b) paired with behavioral tests of the underlying contract (the CAS clear, the heartbeat emit/tick). None is a self-sealing or stand-alone wiring guard. Full suite: 2556 passed, 1 deselected (the known network-blocked `test_mcp_subprocess_contract` test).
- **Pattern consistency**: Atomic writes use the shared `ipc._atomic_write_json` (tempfile + os.replace) for the sidecar and `save_state` for state; consistent with the codebase's atomicity constraint. Takeover-lock fd handling matches the established `try: LOCK_UN ... finally: os.close(fd)` pattern (the helper returns a bare fd, not a context manager) and is applied identically in `recover_session` and `_start_session`. The guardian plist reuses only the generic launchctl primitives and deliberately does NOT reuse the per-session one-shot machinery (label minting, sidecar index, GC) — the correct separation for a single persistent host-level agent. Event registration follows the events-registry + EVENT_TYPES dual-registration convention.

## Requirements Drift
**State**: detected
**Findings**:
- The implementation introduces an out-of-process supervision model not captured in `cortex/requirements/project.md`: a single long-lived launchd guardian daemon (a new persistent process class) and two new writer surfaces (`cortex overnight recover`, `cortex overnight guardian {scan,install,remove}`) that can mutate session state. `project.md` describes the overnight runner and asserts observability surfaces are read-only, but has no line acknowledging a host-level supervisor daemon or the writer verbs. `pipeline.md` likewise has no guardian/supervision/recover entry. The decision is recorded in ADR-0011 (and `project.md`'s "Architectural Decision Records" convention says skills back-point to ADRs), which partially mitigates, but the architecture-level requirements doc itself carries no pointer to the new supervision model. Drift is observational only and does not affect the verdict.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints (append a new bullet)
**Content**:
```markdown
- **Out-of-process runner supervision**: A single persistent host-level launchd guardian plus a manual `cortex overnight recover` verb detect overnight-runner death/wedge and run a writer-authorized recovery core (transition→`paused`, partial report, session-marker orphan reap, clear stale `runner.pid`). These are the only session-state writers outside the runner itself; observability surfaces stay read-only. → ADR-0011: out-of-process overnight-runner supervision.
```

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
