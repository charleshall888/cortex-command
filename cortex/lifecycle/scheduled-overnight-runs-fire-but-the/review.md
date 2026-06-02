# Review: scheduled-overnight-runs-fire-but-the

## Stage 1: Spec Compliance

### Requirement R1: Launcher emits a valid, complete `start` argv
- **Expected**: Rendered launcher invokes `cortex overnight start` with only flags `start` accepts; contains `--state <abs>`, `--format json`, `--force`; does NOT contain `--session-id`/`--launchd`; asserted against the parsed/tokenized invocation, not a comment grep.
- **Actual**: `launcher.sh:224-232` invokes `start --state <abs> --format json --force --scheduled`. `test_launcher_argv.py` renders the real template, tokenizes the cortex line, parses under the `start` subparser (no `SystemExit`), asserts `--state` is absolute, `--format json` parses to `ns.format == "json"`, `--force` sets `ns.force`, and asserts the forbidden set (`--session-id`, `--launchd`) is absent both as tokens and as parsed attrs.
- **Verdict**: PASS
- **Notes**: `--scheduled` (R8) is correctly allowed; the test asserts on the forbidden set, not an exhaustive allowlist, as the plan specified.

### Requirement R2: Scheduled runner detaches as a session leader via the real launcher→start linkage
- **Expected**: Launcher invokes `start` without `--launchd` so the runner spawns via `_spawn_runner_async`'s `Popen(start_new_session=True)`. Two complementary checks: (a) `os.getsid(pid)==pid` AND `os.getsid(pid)!=os.getsid(0)`; (b) the launcher argv routes through the no-`--launchd` path.
- **Actual**: `cli_handler.py:466-473` spawns with `start_new_session=True`. `test_spawn_session_leader.py` asserts both getsid conditions on a runner spawned through the production path. `test_launcher_argv.py`'s routing test spies both `_spawn_runner_async` and `_run_runner_inline` and asserts `handle_start` dispatches to the async-spawn path exactly once for the real no-`--launchd` launcher argv — the join that ties the launcher invocation to the session-leader behavior.
- **Verdict**: PASS
- **Notes**: Neither test is `skipUnless(darwin)`; both run under `just test`. The routing test closes the `os.getsid`-is-a-POSIX-proxy gap exactly as the plan's Task 3 context required.

### Requirement R3: State resolved explicitly, not via cwd
- **Expected**: Launcher passes an absolute `--state <path>`; R1 argv test asserts `--state` present with absolute value.
- **Actual**: `launcher.sh:216` sets `STATE_PATH="${SESSION_DIR}/overnight-state.json"` (absolute, since `SESSION_DIR` is). `test_launcher_argv.py:179-183` asserts `--state` present and `os.path.isabs(state_val)`.
- **Verdict**: PASS
- **Notes**: The darwin-gated cwd-not-repo integration test is appropriately platform-gated; the absolute-path argv guard is platform-agnostic.

### Requirement R4: caffeinate bound to the runner's lifetime, runner remains session leader
- **Expected**: Runner spawns a `caffeinate -i` child bound to its pid (`-w <runner_pid>`); caffeinate is NOT the Popen target/session leader and NOT spawned by the ~5s shim; assertion outlives `_SPAWN_HANDSHAKE_TIMEOUT_SECONDS`; applies to both scheduled and run-now.
- **Actual**: `runner.py:108-148` `_spawn_caffeinate_bound_to_runner` spawns `["caffeinate", "-i", "-w", str(os.getpid())]` best-effort. `runner.py:2149` calls it as the earliest action in `run()`, before `load_state` and lock acquisition — uniform for both paths. caffeinate is a child of the runner, never the Popen target.
- **Verdict**: PASS
- **Notes**: `-i` is the assertion, `-w` binds lifetime; bare-`-w` would hold no assertion (the documented wrong form). Best-effort spawn (missing binary returns None) so it cannot crash the runner.

### Requirement R5: Correct the false detach claims
- **Expected**: `grep -c "reparents to PID 1" launcher.sh` = 0; the docs line claiming the launcher "detaches into its own process group" rewritten to describe the real `start_new_session` detach.
- **Actual**: `grep -c "reparents to PID 1"` = 0. `docs/overnight-operations.md:233` now reads "The detach happens inside cortex: `start` spawns the runner via `subprocess.Popen(..., start_new_session=True)`, so the runner becomes its own session leader and survives launchd's process-group SIGTERM ... the launcher no longer re-implements detachment in bash."
- **Verdict**: PASS

### Requirement R6: Launcher parses the discriminator; distinguishes dead from slow-but-live
- **Expected**: A live-vs-dead discriminator; dead → failure marker with real `error_class`; slow-but-live → distinct advisory marker (not a failure); `--format json` present.
- **Actual**: `cli_handler.py` splits the conflated `spawn_timeout`: dead child → `spawn_died`, live child → `spawn_unconfirmed` (`child_alive: True`). Under `--scheduled`, `_write_spawn_outcome` writes a single-token `spawn-outcome` file. `launcher.sh:254-318` branches on the token: `spawn_died` → `scheduled-fire-failed.json`, `spawn_unconfirmed` → distinct `scheduled-fire-advisory.json` (with `kind`/`severity` fields). `test_launcher_envelope.py` asserts each branch.
- **Verdict**: PASS
- **Notes**: The launcher reads the token via shell builtins (`[ -f ]`/`$(cat)`), robust under launchd's degraded env — a sound method choice within the spec's What.

### Requirement R7: Dead fire surfaced loudly; slow-but-live as advisory
- **Expected**: `spawn_died` rendered as failure in both `cortex overnight status` and the morning report; advisory rendered as a distinct non-failure "awaiting confirmation" state in both; stale advisory escalates.
- **Actual**: `report.render_scheduled_fire_failures` (report.py:1652) renders failures; advisories render as "scheduled fire started — awaiting confirmation" (report.py:1746) and are excluded from the failure tally. `handle_status` (cli_handler.py:846-929) filters advisories out of the failure tally. `fail_markers.scan_advisory_dirs` escalates a stale advisory (age > 300s AND no live `runner.pid` AND phase not executing/complete) to a `FailedFire` with `kind="advisory_escalated"`. `test_report_fire_failures.py` covers all three cases.
- **Verdict**: PASS
- **Notes**: The stale-advisory escalation (Task 6 extension) is inferred purely at read time; nothing is written back, consistent with read-only surfaces.

### Requirement R8: Slow-start neither kills nor mislabels a healthy runner
- **Expected**: A live-child handshake timeout does NOT `killpg`; runner left running; advisory recorded; fire-path budget constant > 5.0.
- **Actual**: `cli_handler.py:556-567` — when `child.poll() is None`, no `_terminate_orphan_child`/`killpg`, returns `spawn_unconfirmed`/`child_alive: True`. `_FIRE_HANDSHAKE_TIMEOUT_SECONDS = 20.0` (cli_handler.py:55), used when `args.scheduled`. `test_spawn_handshake.py` asserts (a) `os.killpg` never called, (b) `child.poll() is None`, (c) `spawn_unconfirmed` envelope + `spawn-outcome` token written, and `_FIRE_HANDSHAKE_TIMEOUT_SECONDS > 5.0`.
- **Verdict**: PASS

### Requirement R9: Verifier no longer false-fails on Darwin 25+
- **Expected**: `_bootstrap_and_verify` accepts the durable armed fact instead of requiring the volatile `state = waiting` substring; an e2e variant with `state = not running` verifies (exit 0).
- **Actual**: `macos.py:76-78` `_VERIFY_STATE_SUBSTRINGS = (b"state = not running", b"state = waiting")`; the verifier accepts either (macos.py:958). `test_scheduler_e2e.py` (darwin-gated) covers the `not running` variant.
- **Verdict**: PASS
- **Notes**: Implementation chose the allowlist-widen interim (an acceptable scope call per the plan's Risk note); the durable calendar-block parse remains a future option, not required by the spec acceptance.

### Requirement R10: Bookkeeping completes regardless of the liveness probe
- **Expected**: Probe is advisory; `scheduled_start` write and sidecar entry both complete on inconclusive probe; `cortex overnight schedule` exits 0 with a non-fatal warning.
- **Actual**: `_mint_and_install` (macos.py:493-512) catches `LaunchctlVerifyError`, sets `last_verify_inconclusive = True`, and returns the install as successful. `_write_sidecar_entry` runs inside the `schedule_lock()` critical section (macos.py:378). `handle_schedule` (cli_handler.py:1777-1825) writes `scheduled_start`, then surfaces a stderr warning and returns 0 when inconclusive. `test_cli_schedule.py` exercises the probe-failure path.
- **Verdict**: PASS

### Requirement R11: `session_start` logged once, at fire, by the runner
- **Expected**: (a) the schedule branch of the skill flow does not invoke prep-time `session_start` (gated to run-now); (b) a runner test asserts exactly one `session_start` with the real session id, not `manual`.
- **Actual**: Skill flow gated: `SKILL.md:74,77-78` and `new-session-flow.md:170,187` — prep-time `session_start` is in the run-now branch only; the schedule branch reaches launch without it. `handle_launch` (cli_handler.py:1978-1981) explicitly does NOT log `session_start` (the commit 36df2bb7 reconciliation). Runner logs the sole fire-time `session_start` at runner.py:1078-1083. `test_runner_session_start.py` asserts the single-event invariant.
- **Verdict**: PASS
- **Notes**: Verified the orchestrator's flagged composition defect: `handle_launch` no longer logs `session_start`; the runner is the sole fire-time author; run-now prose retains its gated prep-time log. Reconciliation is correct.

### Requirement R12: Status renders a scheduled-dormant state (display-only, inferred)
- **Expected**: When `scheduled_start` future AND no live `runner.pid` AND not executing/complete, render "Scheduled (dormant) — fires at {scheduled_start}" and suppress the watchdog block; read explicit per-session path; `PHASES` unchanged (`len==5`, no `scheduled_dormant`/`scheduled`).
- **Actual**: `status.py:110-137` `_is_scheduled_dormant` is conjunctive (future + not executing/complete + no live runner.pid). `render_status` (status.py:294-402) prints the dormant line and suppresses Elapsed/Watchdog. `test_status_scheduled_start.py` asserts the dormant render, suppression, the executing/live-pid negatives, and `len(PHASES)==5` AND `scheduled_dormant`/`scheduled` not in `PHASES`.
- **Verdict**: PASS

### Requirement R13: `scheduled_start` cleared when the runner fires
- **Expected**: Runner clears `scheduled_start` on start via atomic `save_state` on the explicit per-session path; not a phase transition.
- **Actual**: `runner.py:1074-1076` — `if state.scheduled_start is not None: state.scheduled_start = None; save_state(state, state_path)`, a plain field write on the explicit `state_path`. `test_runner_clear_scheduled_start.py` asserts `scheduled_start is None` post-start.
- **Verdict**: PASS

### Requirement R14: Spent one-shot jobs torn down
- **Expected**: After a successful fire the runner/launcher issues `launchctl bootout gui/$(id -u)/<label>` so the annually-recurring job cannot refire.
- **Actual**: `launcher.sh:270` on the `started` branch issues `launchctl bootout "gui/$(id -u)/${LABEL}"` (best-effort) before self-clean. `test_scheduler_bootout_on_fire.py` (darwin-gated) covers it.
- **Verdict**: PASS

### Requirement R15: GC reaps spent schedules by timestamp
- **Expected**: `schedule()` GC reaps sidecar entries with past `scheduled_for_iso` plus their plist+launcher, regardless of `launchctl print` registration.
- **Actual**: `macos.py:_gc_pass` (749+) reaps entries where `_is_spent(scheduled_for_iso, now)` is true, removing the plist/launcher under `$TMPDIR/cortex-overnight-launch/` and the sidecar entry. `test_plist_gc.py` seeds a past entry + files and asserts all three are removed.
- **Verdict**: PASS

### Requirement R16: Document inert `Year` key and caffeinate-no-wake
- **Expected**: Docs note the inert `Year` key and that `caffeinate -i` only prevents idle sleep during a run (does not wake a sleeping Mac).
- **Actual**: `docs/overnight-operations.md` contains both notes (`grep -c "Year"` ≥ 1, `grep -ci "caffeinate"` ≥ 1).
- **Verdict**: PASS

### Requirement R17: Replace the stale `$CORTEX_COMMAND_ROOT`
- **Expected**: Skill files resolve session paths via `cortex --print-root`'s `root` field (or `bootstrap_session`'s `state_dir`), not `$CORTEX_COMMAND_ROOT`.
- **Actual**: `grep -c "CORTEX_COMMAND_ROOT"` = 0 in both `SKILL.md` and `new-session-flow.md`. `SKILL.md:85` and `new-session-flow.md:9` resolve via `cortex --print-root`'s `root`.
- **Verdict**: PASS

### Requirement R18: Planning helpers exposed via CLI
- **Expected**: Mutating `cortex overnight launch` + read-only `cortex overnight prepare` wired in cli.py; skill flow calls these verbs; `launch --help`/`prepare --help` exit 0; `cortex-check-bare-python-import` passes for `skills/overnight/`; contract gate passes for the new verbs.
- **Actual**: Both subparsers registered (cli.py:703-785); handlers `handle_prepare` (read-only, no mutation) and `handle_launch` (select→validate→render→bootstrap→extract, structured envelope) in cli_handler.py:1902-1963+. Against the working tree, `python3 -m cortex_command.cli overnight launch/prepare --help` both exit 0 and both verbs appear in `overnight --help`. Skill prose (SKILL.md:65-78, new-session-flow.md:54-166) calls the verbs. `test_cli_launch_prepare.py` asserts `launch` returns a structured envelope (`launched`, `session_id`, `state_path`, `extracted_specs`) and `prepare` renders plan JSON without mutating state (it asserts no session dir is created).
- **Verdict**: PASS
- **Notes**: The installed wheel at `~/.local/bin/cortex` is STALE (predates these verbs, so `cortex overnight launch --help` exits non-zero against it). This is an environment artifact — a wheel-vs-working-tree mismatch per `project.md`'s "Wheel-binstub vs working-tree invocation" constraint — NOT a source defect. The working tree under review registers both verbs correctly, and `just test` (working-tree) is green. Re-running `uv tool install --reinstall` updates the binstub; this is operational, not a code issue.

### Requirement R19: `bootstrap_session` creates the top-level state symlink
- **Expected**: `bootstrap_session` creates the top-level `cortex/lifecycle/overnight-state.json` symlink at the per-session state file so no-arg `load_state()` does not raise; overwritten per bootstrap.
- **Actual**: `plan.py:579-589` — resolves `_default_state_path()`, ensures the parent dir, unlinks any existing pointer, and `symlink_to(session_state_path)`. `test_bootstrap_symlink.py` asserts the symlink exists and no-arg `load_state()` returns the session state.
- **Verdict**: PASS
- **Notes**: The unlink+symlink_to sequence is not atomic (a sub-millisecond window where the pointer is absent), but the spec requires only a single-active-session pointer overwritten per bootstrap, not atomic replacement — concurrent multi-session bootstrap is an explicitly unsupported mode (spec Edge Cases). Acceptable.

### Requirement R20: Registry, parity, and mirror discipline — advisory is a marker file
- **Expected**: Fire diagnostics are marker files (no `EVENT_TYPES`/registry change); `just check-events-registry` passes; zero mirror drift after `just build-plugin`; `cortex-check-parity` passes.
- **Actual**: Diagnostics are marker files (`scheduled-fire-failed.json`, `scheduled-fire-advisory.json`); no new event literal. Verified: `just check-events-registry` exit 0; `git diff --quiet plugins/cortex-overnight/skills/overnight/` after `just build-plugin` = no drift; `cortex-check-parity` exit 0. `cortex-check-contract` exits 1 on exactly 12 PRE-EXISTING violations (cortex-worktree-create `--feature` in docs/agentic-layer.md, docs/internals/sdk.md, skills/lifecycle/; cortex-discovery flags in skills/discovery/) — none in files this feature touched, none about the `launch`/`prepare` verbs.
- **Verdict**: PASS
- **Notes**: The pre-existing contract debt is out of scope and pre-dates this feature (matches the orchestrator context exactly); this feature adds zero new contract violations.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation matches the three loaded requirements docs. The new behaviors all have an existing requirements home: the scheduled-launch sidecar, GC, lock, and `runner.pid` IPC are already documented in `pipeline.md` (Dependencies, lines 152-158); the `scheduled_start` field and the `starting` display-state precedent are documented in `pipeline.md:153`; the `cortex overnight status` scheduled-dormant/advisory renders are read-time inferences over file-based state, fully consistent with `observability.md`'s read-only In-Session Status CLI contract (lines 62-74, 93). The `launch`/`prepare` verbs are a CLI surface promotion of existing planning helpers, consistent with `project.md`'s "Skill-helper modules" constraint. No new behavior falls outside the stated requirements.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. Constants follow the existing `_SPAWN_HANDSHAKE_TIMEOUT_SECONDS` style (`_FIRE_HANDSHAKE_TIMEOUT_SECONDS`, `_SPAWN_OUTCOME_FILENAME`, `STALE_ADVISORY_THRESHOLD_SECONDS`). Marker filenames mirror the existing `scheduled-fire-failed.json` convention. Dataclasses (`FailedFire`, `FireAdvisory`) match the module's existing style with `to_dict()` helpers.
- **Error handling**: Appropriate and defensive throughout. Atomic writes (tempfile + `durable_fsync` + `os.replace`) for the spawn-outcome token and all new state; best-effort spawns (caffeinate, bootout, marker writes) swallow errors so a non-load-bearing failure never crashes the runner or launcher; the bash launcher hand-rolls JSON (with escaping) precisely because python may be the thing that failed; corrupt/missing markers are skipped with a stderr warning rather than aborting the scan; the inconclusive-probe path degrades to a warning + exit 0 rather than losing bookkeeping.
- **Test coverage**: The plan's platform-agnostic verifications are all executed and green under `just test` (6/6): argv-render + routing + session-leader (Task 3), non-kill/spawn_unconfirmed/budget (Task 4), launcher token-read branches (Task 5), marker render + stale-advisory escalation (Task 6), bookkeeping-completes via probe mock (Task 8), GC-by-timestamp (Task 13), runner caffeinate/clear-scheduled_start/single-session_start (Tasks 2/9/10), dormant + PHASES invariant (Task 11), bootstrap symlink (Task 17). The true end-to-end fire behaviors (verifier e2e, bootout-on-fire) are correctly darwin-gated, as the spec's Technical Constraints require. The discriminator/non-kill tests use a deterministic sleeper-beyond-budget design, avoiding timing flakiness.
- **Pattern consistency**: Follows existing conventions — the launcher remains a self-contained bash template with `@@MARKER@@` substitution; the discriminator token-file approach reuses the atomic-write idiom; the dormant state mirrors the documented `starting` display-only precedent without mutating `PHASES`; read-time inference for advisory escalation honors the read-only status/report contract; the CLI verbs follow the established `cortex overnight` subparser + `handle_*` handler shape. The dual-source mirror was rebuilt and is drift-free.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
