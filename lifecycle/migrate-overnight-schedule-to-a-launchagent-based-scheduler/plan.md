# Plan: migrate-overnight-schedule-to-a-launchagent-based-scheduler

## Overview

Build a new `cortex_command/overnight/scheduler/` package containing a `Scheduler` protocol and a single `MacOSLaunchAgentBackend` that renders a `launchd` plist into `$TMPDIR`, copies a paired bash launcher script alongside it, and bootstraps the agent via `launchctl bootstrap gui/$(id -u)`. Layer two new CLI subcommands (`cortex overnight schedule` and an async-spawn `cortex overnight start`), surface them through the MCP server (`overnight_schedule_run` plus an updated `overnight_start_run`), wire a fail-marker scanner that surfaces fire-time failures across morning report and `cortex overnight status`, then retire `bin/overnight-schedule` and its parity-check special cases. Ordering: protocol → backend → async-start CLI flag → launcher → sidecar/GC + schedule-lock → schedule CLI → cancel/cross-cancel → MCP wiring → bin removal → docs → fail-marker consumer → e2e smoke.

## Open Decisions Resolved Here

- **Launcher language: bash.** Three reasons: (1) `setsid nohup /usr/bin/caffeinate -i exec ...` is the canonical Unix pattern launchd templates expect; (2) the launcher needs no shared Python state with the scheduler module — its job is detach + invoke + structured-error fallback; (3) avoids ~100ms Python interpreter startup at fire time. The fail-marker JSON write (R13) is small enough for a shell-level structured emit with shell-escaped fields. Shipped via Python package data; copied per-schedule to `$TMPDIR/cortex-overnight-launch/launcher-{label}.sh` so the launcher and plist are paired ephemeral artifacts.
- **`Scheduler` protocol shape.** Four methods on a `typing.Protocol`:
  - `schedule(target: datetime, session_id: str, env: dict[str, str], repo_root: Path) -> ScheduledHandle`
  - `cancel(label: str) -> CancelResult`
  - `list_active() -> list[ScheduledHandle]`
  - `is_supported() -> bool` (staticmethod)
  - `ScheduledHandle` is a frozen `@dataclass`: `label, session_id, plist_path, launcher_path, scheduled_for_iso, created_at_iso`. `CancelResult` is a frozen `@dataclass`: `label, bootout_exit_code, sidecar_removed: bool, plist_removed: bool, launcher_removed: bool`. Backend dispatch via `get_backend() -> Scheduler` chooses `MacOSLaunchAgentBackend()` on `sys.platform == "darwin"`, else returns an `_UnsupportedScheduler` whose methods raise `NotImplementedError` and whose `is_supported()` returns `False`.

## Tasks

### Task 1: Scaffold scheduler package and protocol
- **Files**:
  - `cortex_command/overnight/scheduler/__init__.py` (new)
  - `cortex_command/overnight/scheduler/protocol.py` (new)
  - `cortex_command/overnight/scheduler/dispatch.py` (new)
  - `cortex_command/overnight/tests/test_scheduler_protocol.py` (new)
- **What**: Create the package skeleton, the `Scheduler` `Protocol`, the `ScheduledHandle` and `CancelResult` dataclasses, and the `get_backend()` dispatcher. Add `_UnsupportedScheduler` for non-darwin. No macOS implementation yet — that lands in Task 2.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `Protocol` follows `typing.Protocol` (PEP 544). Mirror the dataclass-frozen pattern used in `cortex_command/overnight/state.py:184` (`OvernightState`). `__init__.py` re-exports `Scheduler`, `ScheduledHandle`, `CancelResult`, `get_backend`. `get_backend()` reads `sys.platform`; tests can monkeypatch the platform check. Test file asserts: protocol has the four methods, dataclasses have the listed fields, `get_backend()` returns `_UnsupportedScheduler` on a patched non-darwin and `MacOSLaunchAgentBackend` on darwin (the macOS branch will be importable as a stub class for now — Task 2 fleshes it out).
- **Verification**: `pytest cortex_command/overnight/tests/test_scheduler_protocol.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 2: macOS backend — plist render, env snapshot, bootstrap, post-bootstrap verify
- **Files**:
  - `cortex_command/overnight/scheduler/macos.py` (new)
  - `cortex_command/overnight/scheduler/labels.py` (new)
  - `cortex_command/overnight/tests/test_plist_validation.py` (new)
  - `cortex_command/overnight/tests/test_env_snapshot.py` (new)
  - `cortex_command/overnight/tests/test_target_time_validation.py` (new)
- **What**: Implement `MacOSLaunchAgentBackend.schedule()` end-to-end except for the launcher script body (Task 3) and sidecar writes (Task 4). Build the plist via `plistlib.dumps`, round-trip through `plistlib.loads` for structural validation, write to `$TMPDIR/cortex-overnight-launch/{label}.plist`, run `launchctl bootstrap gui/$(id -u) <plist>`, then verify with `launchctl print gui/$(id -u)/<label>` (look for `state = waiting` substring). Implements R6, R7, R15, R16, and the label-construction rule (R6 label format with epoch+1 retry once on collision).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Label format: `com.charleshall.cortex-command.overnight-schedule.{session_id}.{epoch_seconds}` (DR-6, never reuse). `labels.py` exposes `mint_label(session_id, now_epoch=None) -> str` and `parse_label(label) -> tuple[session_id, epoch]`.
  - `MacOSLaunchAgentBackend` constructor takes no args; reads `os.environ` lazily inside `schedule()`. Env snapshot picks `PATH` always, then `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CORTEX_REPO_ROOT`, `CORTEX_WORKTREE_ROOT` if present (R15). `HOME`/`USER`/`LOGNAME`/`TMPDIR` are NOT set — launchd inherits them.
  - Plist keys: `Label`, `ProgramArguments` (argv array pointing at the launcher script + repo_root + label arg), `RunAtLoad: false`, `StartCalendarInterval` dict (Year/Month/Day/Hour/Minute populated from target datetime), `EnvironmentVariables` dict, `StandardOutPath`/`StandardErrorPath` set to `<session_dir>/launchd-stdout.log` and `launchd-stderr.log` (the wrapper resolves session_dir via the IPC session-path helper).
  - Target-time parsing: `HH:MM` resolved against today; if past, roll to tomorrow. `YYYY-MM-DDTHH:MM` parsed via `datetime.fromisoformat`. Reject Feb 29 in non-leap years with `ValueError("target time invalid: Feb 29 not in {year}")` — `datetime` itself raises; catch and re-raise with the spec's exact phrasing. Past times rejected with `"target time is in the past"`. 7-day ceiling check.
  - Round-trip validation: `plistlib.loads(plistlib.dumps(plist_dict))` must equal original; on mismatch raise `PlistValidationError(label, key)`.
  - Bootstrap-and-verify is one method `_bootstrap_and_verify(plist_path: Path, label: str) -> None`. Calls `subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)], capture_output=True)`. On non-zero exit: raise `LaunchctlBootstrapError(stderr, exit_code)`. On success: poll `launchctl print gui/{uid}/{label}` up to 1.0 s for `b"state = waiting"` substring; raise `LaunchctlVerifyError` if absent.
  - The backend leaves sidecar writes, GC, and launcher-script copying as method seams (`_write_sidecar_entry`, `_gc_pass`, `_install_launcher_script`) that Tasks 3 and 4 fill in. Stubs that no-op here are acceptable — they're integrated end-to-end in Task 5's CLI smoke test.
  - Tests:
    - `test_plist_validation.py`: happy round-trip; typo'd top-level key (e.g. `LabeI` for `Label`) rejected; bootstrap fakes via `monkeypatch.setattr(subprocess, "run", ...)` exercise post-bootstrap `state = waiting` and `state = waiting`-absent branches.
    - `test_env_snapshot.py`: covers all five env vars present, none present, partial, and assertion that `HOME`/`USER`/`TMPDIR` are NOT in the dict.
    - `test_target_time_validation.py`: HH:MM today; HH:MM past rolling to tomorrow; ISO 8601 valid; ISO 8601 past; ISO 8601 Feb 29 in 2026 (non-leap); ISO 8601 > 7 days out.
- **Verification**: `pytest cortex_command/overnight/tests/test_plist_validation.py cortex_command/overnight/tests/test_env_snapshot.py cortex_command/overnight/tests/test_target_time_validation.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Bash launcher script + fail-marker writes + immediate notification
- **Files**:
  - `cortex_command/overnight/scheduler/launcher.sh` (new — package data)
  - `cortex_command/overnight/scheduler/macos.py` (extend `_install_launcher_script` from Task 2)
  - `cortex_command/overnight/tests/test_launcher_fail_marker.py` (new)
  - `pyproject.toml` (modify — add `launcher.sh` to package-data)
- **What**: Write the bash launcher that launchd executes at fire time (R9). The launcher detaches via `setsid nohup` wrapping `caffeinate -i` wrapping the cortex binary invoked with `overnight start --launchd --session-id <id>`, then exits 0 after fork. On EPERM (errno 1) or command-not-found (exit 127) it: (1) writes `<session_dir>/scheduled-fire-failed.json` (R13); (2) **fires an immediate macOS notification via `osascript -e 'display notification "Scheduled overnight run failed at fire time — see <session_dir>" with title "cortex-overnight" sound name "Basso"'`** so the user is informed at the moment of failure rather than waiting until they next interact with the system; (3) removes its own plist and launcher copy from `$TMPDIR/cortex-overnight-launch/`; (4) exits non-zero so launchd records the failure. `_install_launcher_script` copies the templated bash file from package-data to `$TMPDIR/cortex-overnight-launch/launcher-{label}.sh` and `chmod +x`. The bash file is a template with `@@PLIST_PATH@@`, `@@LAUNCHER_PATH@@`, `@@SESSION_DIR@@`, `@@LABEL@@`, `@@CORTEX_BIN@@`, `@@SESSION_ID@@` markers replaced at install time.
- **Depends on**: [2, 6]
- **Complexity**: complex
- **Context**:
  - Launcher structure (prose, not code): the script performs five operations in order. (1) Install an error trap on EPERM (errno 1) and command-not-found (exit 127). (2) On trap fire, write a JSON sentinel at `<session_dir>/scheduled-fire-failed.json` containing the fields `{ts, error_class, error_text, label, session_id}` — written BEFORE any cleanup so a failed runner doesn't lose the diagnostic. (3) Remove the plist file at `$PLIST_PATH` and the launcher copy at `$LAUNCHER_PATH`. (4) Detach the runner using `setsid nohup` wrapping `/usr/bin/caffeinate -i` wrapping the cortex binary invoked with `overnight start --launchd --session-id <id>`, redirecting stdin from `/dev/null` and appending stdout/stderr to `<session_dir>/runner-stdout.log` and `<session_dir>/runner-stderr.log`. (5) `disown` the background job and `exit 0`. The launcher is a templated bash file with `@@PLIST_PATH@@`, `@@LAUNCHER_PATH@@`, `@@SESSION_DIR@@`, `@@LABEL@@`, `@@CORTEX_BIN@@`, `@@SESSION_ID@@` markers replaced at install time by `_install_launcher_script`.
  - The `--launchd` flag is a new internal-only flag on `cortex overnight start` (introduced in Task 6) that signals "do not perform the spawn-handshake again — you're already detached".
  - Self-delete order: write fail-marker BEFORE plist/launcher removal so a failed runner doesn't lose the diagnostic. Successful spawn path removes the plist and launcher after the runner is backgrounded.
  - Post-fork detection of runner-died-in-first-second is NOT the launcher's responsibility — Task 6's `runner.spawn-pending` sentinel handles that for the run-now path; the schedule path delegates to the runner's existing `_check_concurrent_start` and morning report.
  - Tests use a fake `cortex` binary path (a tempfile shell stub) and assert: (a) EPERM on the cortex binary triggers fail-marker write; (b) command-not-found triggers fail-marker; (c) successful fork creates expected log files and removes plist + launcher; (d) JSON shape valid (parse with `json.loads`).
  - `pyproject.toml`: add `launcher.sh` to `[tool.setuptools.package-data]` under the `cortex_command.overnight.scheduler` key (or equivalent for the project's existing build-system block — match the convention already in use).
- **Verification**: `pytest cortex_command/overnight/tests/test_launcher_fail_marker.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Sidecar index + plist garbage collection + cross-process lock
- **Files**:
  - `cortex_command/overnight/scheduler/sidecar.py` (new)
  - `cortex_command/overnight/scheduler/lock.py` (new — `fcntl.flock` helper for the schedule-lock contract)
  - `cortex_command/overnight/scheduler/macos.py` (wire `_write_sidecar_entry`, `_remove_sidecar_entry`, `_gc_pass`, and the lock-acquire/release seam from Task 2)
  - `cortex_command/overnight/tests/test_sidecar_index.py` (new)
  - `cortex_command/overnight/tests/test_plist_gc.py` (new)
- **What**: Implement `~/.cache/cortex-command/scheduled-launches.json` with atomic writes and the GC pass that runs at every `schedule()` call (R8, R19). On first use, `mkdir -p ~/.cache/cortex-command/`. Schema: list of `{label, session_id, plist_path, launcher_path, scheduled_for_iso, created_at_iso}`. GC enumerates `*.plist` under `$TMPDIR/cortex-overnight-launch/`, removes any whose label is absent from sidecar OR whose `launchctl print gui/$(id -u)/<label>` exits 113 (job not registered); removes the paired `launcher-*.sh` for the same label. **Cross-process serialization**: an exclusive `fcntl.flock` on `~/.cache/cortex-command/scheduled-launches.lock` is acquired BEFORE `_gc_pass` runs and held continuously through `_install_launcher_script` → plist write → `_bootstrap_and_verify` → `_write_sidecar_entry`, then released. This prevents the race where Process B's GC observes Process A's just-written plist as orphan and removes it before A's sidecar entry lands.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - `sidecar.py` exposes `read_sidecar() -> list[ScheduledHandle]`, `add_entry(handle)`, `remove_entry(label) -> bool`, `find_by_session_id(session_id) -> ScheduledHandle | None`. Atomic writes follow `cortex_command/common.py:durable_fsync()` — tempfile in same dir + `os.replace`.
  - `lock.py` exposes `schedule_lock() -> ContextManager[None]` — a `fcntl.LOCK_EX` flock on `~/.cache/cortex-command/scheduled-launches.lock`, opened in `'a'` mode so the lockfile auto-creates. Mirror the existing pattern at `cortex_command/overnight/ipc.py:18` and `runner.py:24`. The lock is process-scoped (one acquire per `schedule()` call); it does NOT span the entire CLI session.
  - Corruption handling: if the sidecar file fails to JSON-decode, log a single warning, return empty list, and let the next write overwrite it (R8 cancel-list "warn but don't crash").
  - GC pass (`_gc_pass(self) -> int`) returns count of removed files; logs at INFO. Idempotent: multiple back-to-back calls are no-ops once stale files are gone. **GC must only be called inside the schedule_lock**; standalone GC invocation is not part of the contract.
  - `test_sidecar_index.py`: covers add/remove/find/round-trip; corrupt JSON → empty read; missing parent dir → first call creates it; concurrent writers via threaded test using `os.replace` semantics.
  - `test_plist_gc.py`: stale plist (label absent from sidecar) removed; in-flight plist (label in sidecar AND `launchctl print` exits 0) preserved; orphan launcher.sh paired with stale plist also removed; corrupt sidecar handled gracefully (no crash, no plist removal — fail closed); **concurrent-schedule serialization test**: two threads call `schedule()` simultaneously with mocked `launchctl`; assert both succeed (or one fails cleanly), and that GC does not remove the in-flight plist of either invocation.
- **Verification**: `pytest cortex_command/overnight/tests/test_sidecar_index.py cortex_command/overnight/tests/test_plist_gc.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 5: `cortex overnight schedule` CLI subcommand
- **Files**:
  - `cortex_command/cli.py` (modify — register `schedule` subparser around lines 303–358)
  - `cortex_command/overnight/cli_handler.py` (modify — add `handle_schedule()`)
  - `cortex_command/overnight/state.py` (modify — exercise existing `scheduled_start` write path; field already defined at lines 223, 263, 406)
  - `cortex_command/overnight/tests/test_cli_schedule.py` (new)
  - `skills/overnight/SKILL.md` (modify — Step 7 mention of new command, paired with this task per Wiring Co-Location)
- **What**: Wire the `schedule` subparser, dispatch to `handle_schedule(target_time, dry_run, format)`, which: (1) validates target time, (2) calls `Scheduler.is_supported()` — exits with `"cortex overnight scheduling requires macOS"` if False, (3) calls cross-cancel runner-active check (Task 7 will fill this seam — leave a `_check_no_active_runner()` helper that returns True for now), (4) calls `get_backend().schedule(...)`, (5) **writes `scheduled_start` (the resolved fire-time ISO 8601 string) to the session state file via the existing atomic state-write helper, AFTER `_write_sidecar_entry` has succeeded — this restores the observability hook that `bin/overnight-schedule` previously provided and that Task 7's cancel-side clear and `handle_status` surfacing both depend on**, (6) prints session_id, label, scheduled_for_iso (or JSON if `--format json`). Implements R1, the macOS-only gate from R5, the spec R7 acceptance text "before writing scheduled_start to the state file", and the SKILL.md Step 7 mention from R10 + spec MODIFIED. The SKILL.md edit changes the bash command to `cortex overnight schedule <target>` and adds `dangerouslyDisableSandbox: true` to the example.
- **Depends on**: [2, 3, 4]
- **Complexity**: complex
- **Context**:
  - Subparser pattern: mirror the existing `cortex overnight start` subparser in `cortex_command/cli.py:303–358`. New `schedule` subparser accepts positional `target_time`, optional `--dry-run`, optional `--format json`.
  - `handle_schedule` signature: `def handle_schedule(target_time: str, dry_run: bool, output_format: str, repo_root: Path) -> int` (returns exit code).
  - Repo root resolution: reuse `_resolve_repo_path()` already in `cli_handler.py`.
  - Session id generation: reuse the same UUID4 helper used by `handle_start` (find via grep — most likely `_make_session_id()` in `cli_handler.py` or `state.py`).
  - SKILL.md change is in the "Schedule for later" branch around lines 226–241. Replace the `overnight-schedule <target>` invocation with `cortex overnight schedule <target>`; add `dangerouslyDisableSandbox: true` parameter on the Bash tool call example.
  - Test file: smoke-test `--dry-run` exit 0 and printed format; smoke-test non-darwin exits with the macOS-only error; smoke-test invalid target time exits non-zero with the spec's error string.
- **Verification**:
  - `pytest cortex_command/overnight/tests/test_cli_schedule.py -v` — pass if exit 0.
  - `grep -c 'cortex overnight schedule' skills/overnight/SKILL.md` ≥ 1.
  - `grep -c 'dangerouslyDisableSandbox' skills/overnight/SKILL.md` ≥ 1.
- **Status**: [ ] pending

### Task 6: Async-spawn `cortex overnight start` with liveness-checked handshake
- **Files**:
  - `cortex_command/overnight/cli_handler.py` (modify — refactor `handle_start`)
  - `cortex_command/overnight/scheduler/spawn.py` (new — pid handshake helper with liveness probe)
  - `cortex_command/overnight/tests/test_spawn_handshake.py` (new)
  - `tests/test_runner_signal.py` (modify — read runner.pid post-handshake and signal that pid; proc.pid is now the shim and gone after 5s)
  - `tests/test_runner_followup_commit.py` (modify — same pattern: read runner.pid and signal it instead of proc.pid)
  - `tests/test_cli_overnight_format_json.py` (verify still passes; the pre-flight JSON refusal must still run before async-spawn — covered by ordering pinned in this task's What)
- **What**: Refactor `handle_start` so the caller returns within 5 seconds (R2, R18). Flow:
  1. **`--dry-run` short-circuit (PINNED INLINE)**: if `args.dry_run` is true, take the existing inline path that writes `DRY-RUN` lines to the parent's stdout. Dry-run does NOT enter the async-spawn fork — preserves the 11 `tests/test_runner_pr_gating.py` assertions on `result.stdout`.
  2. **Pre-flight ordering (PINNED)**: the existing concurrent-runner JSON refusal at `cli_handler.py:269-288` runs BEFORE the async-spawn step. Test `test_cli_overnight_format_json.py:245` (which prepopulates a live `runner.pid` to trigger the JSON-refusal path) depends on this ordering and continues to pass without change.
  3. Write `<session_dir>/runner.spawn-pending` sentinel.
  4. Fork the runner via `subprocess.Popen` with `start_new_session=True` + `stdin=DEVNULL` + redirected stdout/stderr to `<session_dir>/runner-stdout.log` and `runner-stderr.log` (run-now path; the schedule path uses launchd's launcher script which already detaches).
  5. Poll for `<session_dir>/runner.pid` appearance up to 5.0 s. On appearance, **read the pid and apply a liveness probe `os.kill(pid, 0)` — if it raises `ProcessLookupError`, the runner has already died; return `started: false`, `error_class: spawn_died`, clean up sentinel and reap the dead Popen handle.**
  6. On verified-live: return `started: true`, session_id, pid, clean up sentinel.
  7. **On timeout: terminate the orphan child** before returning. Issue `os.killpg(os.getpgid(child.pid), signal.SIGTERM)` (the child is a process-group leader by `start_new_session=True`), wait up to 1.0 s for `Popen.wait`, escalate to `SIGKILL` if it does not exit, then return `started: false`, `error_class: spawn_timeout`, clean up sentinel. **This prevents the runner from materializing `runner.pid` post-timeout, which would contradict the `started: false` return**.
  8. Add `--launchd` internal flag that signals "skip the spawn-handshake — you ARE the runner now"; this branch in `handle_start` execs the runner directly without fork.
  9. Add a new `phase: starting` value to `cortex overnight status` for the window between sentinel write and runner.pid appearance.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Existing `handle_start` lives at `cortex_command/overnight/cli_handler.py:127`. Today it blocks for the full runner duration. Split into `_spawn_runner_async()` (new, returns immediately after liveness-checked handshake) and `_run_runner_inline()` (existing-blocking-path renamed; only invoked under `--launchd` OR `--dry-run`).
  - `spawn.py` exposes `wait_for_pid_file(path: Path, timeout: float = 5.0, poll_interval: float = 0.05) -> int | None`. Returns pid on appearance + liveness-verified, None on timeout. Internally: loop with `time.sleep(poll_interval)` between `path.exists()` checks (50ms tick = ~100 polls in the 5s window, low CPU); on appearance, read pid and call `os.kill(pid, 0)` — return None if `ProcessLookupError`, return pid otherwise.
  - **Signal propagation contract change**: under async-spawn, `proc.pid` (the parent shim) is gone within 5s and the runner runs under a new process group. Existing tests that did `os.kill(proc.pid, signal.SIGHUP)` and asserted on `proc.returncode == -signal.SIGHUP` (`tests/test_runner_signal.py:179`, `tests/test_runner_followup_commit.py:206-227`) must be rewritten to (a) call `cortex overnight start` and read its JSON output for the `pid` field, OR (b) read `<session_dir>/runner.pid` after the shim exits, then send the signal to that pid and assert via `cortex overnight status` (or a sentinel file) that the runner's signal handler fired. This is a behavioral surface change — operators who Ctrl-C `cortex overnight start` today expect SIGINT to reach the runner; under async-spawn the shim has returned and Ctrl-C does nothing. Documented in the Veto Surface.
  - `runner.pid` write is at `cortex_command/overnight/ipc.py:234` (`write_runner_pid()`); it already exists — no change needed in ipc.py.
  - `phase: starting` addition: add `STARTING = "starting"` to the existing phase enum at `cortex_command/overnight/state.py` (find via grep — the `PHASES` tuple). `cortex overnight status` reports `STARTING` when `runner.spawn-pending` exists and `runner.pid` does not.
  - Test file: happy path (handshake within 1 s, liveness verified); slow spawn (handshake at 4.5 s); timeout-with-orphan-kill (parent times out, child is killpg'd, no late `runner.pid` appears); **runner-crash-in-first-second (pid file appears, liveness probe `os.kill(pid, 0)` raises ProcessLookupError → `started: false, error_class: spawn_died`)**; `--launchd` flag bypasses handshake; `--dry-run` flag bypasses handshake and writes DRY-RUN to parent stdout.
  - **Caveat on test fidelity**: the runner-crash-in-first-second test cannot reproduce the production kernel-scheduler race in pure-Python — but with the liveness probe added, the failure mode is no longer fixture-dependent: any time `os.kill(pid, 0)` raises ProcessLookupError, the function returns `started: false`. The test asserts the LIVENESS-PROBE BRANCH, not the kernel race, which is the load-bearing behavior.
  - The 5-second budget is for the run-now path. The schedule path's launcher script runs in launchd's detached context; the spawn-pending sentinel is written by the launcher, and the launchd-spawned runner deletes it after writing runner.pid. **Sentinel-deletion ordering**: the launchd-path runner MUST write `runner.pid` BEFORE deleting `runner.spawn-pending`, so a status query never observes both files absent during a live spawn. This ordering is enforced in the runner's existing code path; if it is not currently enforced, add a small change to `runner.py` to enforce it (this is in scope for Task 6 since it touches the same handshake protocol).
- **Verification**: `pytest cortex_command/overnight/tests/test_spawn_handshake.py tests/test_runner_signal.py tests/test_runner_followup_commit.py tests/test_cli_overnight_format_json.py tests/test_runner_pr_gating.py -v` — pass if exit 0. The expanded suite catches the in-repo callers Task 6 affects.
- **Status**: [ ] pending

### Task 7: `cortex overnight cancel` extension + cross-cancel guards + status surfacing
- **Files**:
  - `cortex_command/overnight/cli_handler.py` (modify — extend `handle_cancel`, add cross-cancel checks, surface `scheduled_start` in `handle_status` JSON and human output)
  - `cortex_command/cli.py` (modify — `cancel` subparser gets `--list`, `--force`)
  - `cortex_command/overnight/tests/test_cancel_scheduled.py` (new)
  - `cortex_command/overnight/tests/test_cross_cancel.py` (new)
  - `cortex_command/overnight/tests/test_status_scheduled_start.py` (new — asserts handle_status surfaces scheduled_start)
- **What**: Extend `handle_cancel` to handle scheduled launches: (1) with no args, list both active runners and pending schedules, prompt for selection; (2) with a session_id, look up sidecar via `find_by_session_id`; if found, `launchctl bootout gui/$(id -u)/<label>`, remove plist + launcher + sidecar entry, clear `scheduled_start` state file field; (3) with `--list`, just print both. Implement cross-cancel guards (R14): `cortex overnight schedule` checks for **(a) an active runner** via `ipc.read_runner_pid` + `ipc.verify_runner_pid` AND **(b) a `runner.spawn-pending` sentinel that has not yet aged out** (catches the 5-second handshake window between Task 6's sentinel write and runner.pid appearance). Exits non-zero if either is true; this fills the seam left in Task 5. `cortex overnight start` checks sidecar for pending schedules and exits non-zero unless `--force`. Wire `_check_no_active_runner` (left as a stub in Task 5) to do both the runner-pid check AND the spawn-pending sentinel check. **Also: extend `handle_status` to surface `scheduled_start` in both the JSON output (add field to the JSON envelope at `cli_handler.py:383-389`) and the human-readable output, so the field Task 5 now writes is observable; otherwise the entire scheduled_start observability hook is dead and Task 7's clear-on-cancel is no-op-imitating-correctness.**
- **Depends on**: [5, 6]
- **Complexity**: complex
- **Context**:
  - `handle_cancel` lives in `cortex_command/overnight/cli_handler.py` (alongside `handle_start`).
  - Backend: extend `MacOSLaunchAgentBackend.cancel(label) -> CancelResult` to do `launchctl bootout`, then remove plist, launcher, sidecar entry. Returns the `CancelResult` dataclass with field-level success indicators so the CLI can print useful diagnostics.
  - For the active-runner check, `ipc.read_runner_pid()` is at `cortex_command/overnight/ipc.py:381` and `verify_runner_pid()` at `:392`. **Additionally**, check for `<session_dir>/runner.spawn-pending` existence with an mtime-age guard (treat sentinel files older than 30s as stale and ignore them) — this closes the gap that the cross-cancel guard misses sessions in `phase: starting`.
  - `--force` on `start` bypasses the schedule check but does NOT cancel the schedule — explicit user choice to let both run; runner's `_check_concurrent_start` (`runner.py:711`) handles the eventual collision.
  - State file `scheduled_start` clear: the field is written by Task 5's `handle_schedule()`. Use the existing atomic state-write helper (find via grep — likely `state.write()` or similar). This clear is now meaningful because the write-side exists.
  - **`handle_status` surfacing**: the existing JSON envelope at `cli_handler.py:383-389` emits `session_id, phase, current_round, features`. Add `scheduled_start` (None when absent; ISO 8601 string when set). Human output: print "Scheduled fire: <ISO 8601>" when set. The dashboard at `cortex_command/dashboard/data.py` will pick this up via the same status JSON consumed elsewhere — no dashboard-side change required for v1.
  - Tests: `test_cancel_scheduled.py` exercises schedule-then-cancel-then-launchctl-print-exits-113 path (mock subprocess.run for launchctl, real sidecar writes via tmpdir). `test_cross_cancel.py` covers schedule-while-runner-active fails, schedule-while-spawn-pending-sentinel-fresh fails, schedule-while-spawn-pending-sentinel-stale-30s succeeds, start-while-schedule-pending fails, start-while-schedule-pending-with-force succeeds. `test_status_scheduled_start.py` covers handle_status output with scheduled_start absent and present.
- **Verification**: `pytest cortex_command/overnight/tests/test_cancel_scheduled.py cortex_command/overnight/tests/test_cross_cancel.py cortex_command/overnight/tests/test_status_scheduled_start.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 8: MCP tool `overnight_schedule_run`
- **Files**:
  - `plugins/cortex-overnight-integration/server.py` (modify — add new tool around the existing `overnight_start_run` block at line 2424)
  - `plugins/cortex-overnight-integration/tests/test_overnight_schedule_run.py` (new)
- **What**: Add `overnight_schedule_run` MCP tool. Inputs: `target_time: str`, optional `state_path: str`, `confirm_dangerously_skip_permissions: Literal[True]`. Output: `scheduled: bool`, `session_id: str`, `label: str`, `scheduled_for_iso: str`. Implementation calls `subprocess.run(["cortex", "overnight", "schedule", target_time, "--format", "json"], timeout=30)` and parses the JSON output. Per spec R10: this is the MCP path — no `dangerouslyDisableSandbox` flag exists at this layer; the MCP server's subprocess inherits the MCP server's own Seatbelt context (the existing pattern, no per-call gate to wire).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Mirror the structure of `overnight_start_run` at `plugins/cortex-overnight-integration/server.py:2424` and its delegate `_delegate_overnight_start_run` at `:1951`.
  - Use the existing `confirm_dangerously_skip_permissions` literal-True gate pattern.
  - Test scenarios: happy path (CLI mocked to return JSON success), CLI nonzero exit → `scheduled: false`, CLI timeout → MCP raises, missing `confirm_dangerously_skip_permissions` → tool refuses.
- **Verification**: `pytest plugins/cortex-overnight-integration/tests/test_overnight_schedule_run.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 9: MCP tool `overnight_start_run` async update
- **Files**:
  - `plugins/cortex-overnight-integration/server.py` (modify — update timeout and delegate semantics around lines 1951–2424)
  - `plugins/cortex-overnight-integration/tests/test_overnight_start_run.py` (modify — update test for new async semantics; create if absent)
- **What**: Update `overnight_start_run` to reflect async-spawn semantics from Task 6. Set subprocess timeout to **30 s (per spec R12)**. Update the comment at lines 1956–1958 — claim that the runner is detached is now accurate by design. Output schema unchanged but documented as fast-return: `started: true` plus `session_id` returned within ~5 s in the typical case.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - The existing tool already returns `started` + `session_id`; behavior change is in `cortex overnight start` itself (Task 6), not the MCP shape.
  - **Spec contradiction note** (resolved by this plan): spec R12 specifies 30 s with concrete rationale ("the spawn path includes plist write + bootstrap + launchctl print verify + sidecar atomic write + concurrent-runner check; while typical latency is sub-second, the 30s budget preserves headroom for slow-disk and disk-pressure cases without producing spurious MCP failures"). Spec "Changes to Existing Behavior" line 77 mentions 10 s without rationale. The plan picks **30 s** because R12's reasoning is concrete and the MCP layer favors slow-success over false-failure (a 10 s timeout that fires after launchctl has already bootstrapped the job tells Claude "scheduling failed" while a job is in fact armed — a worse UX than a slower successful return). A separate spec-update ticket should align line 77 to R12's 30 s; that follow-up is mechanical and out of scope for this plan.
  - Test additions: slow-spawn-but-handshake-within-30s succeeds; async-return-shape (caller sees `started: true` immediately) verified via mocked CLI; timeout boundary test at 30 s.
- **Verification**: `pytest plugins/cortex-overnight-integration/tests/test_overnight_start_run.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 10: Delete `bin/overnight-schedule` and parity-check special cases + update in-repo callers of blocking `cortex overnight start`
- **Files**:
  - `bin/overnight-schedule` (delete)
  - `bin/cortex-check-parity` (modify — remove `overnight-schedule` bare-name allowance near line 92 / line 715)
  - `plugins/cortex-interactive/bin/cortex-check-parity` (modify — same removal in the dual-source mirror)
  - `justfile` (modify — remove `overnight-schedule` recipe at lines 77–79; **also rewrite the `overnight-run` recipe at lines 65–75 to reflect async-spawn semantics — change recipe comment from foreground-blocking phrasing to "async-spawn; runner detaches; use `cortex overnight status` to track"**; remove `deploy-bin`, `setup-force`, `check-symlinks` recipe entries IF present — if `grep -n 'deploy-bin\|setup-force\|check-symlinks' justfile` returns no matches, that part of the task is a no-op)
  - `README.md` (modify — line 125-126 documents `just overnight-run # Run overnight in foreground`. Update to reflect that the runner detaches and the recipe returns within 5s)
- **What**: Retire the old scheduler and update in-repo callers of blocking `cortex overnight start` semantics. Removes the `bin/overnight-schedule` script entirely, removes the parity-check special case in both copies of `bin/cortex-check-parity`, removes the corresponding `justfile` recipes, **and updates the `justfile`'s `overnight-run` recipe and `README.md` to match Task 6's async-spawn semantics — the `# Run overnight in foreground` claim becomes false post-Task-6 and would mislead users into thinking the runner failed when in fact it detached**. Per spec R3: must be one change so parity-check passes (`bin/cortex-check-parity` rejects intermediate states).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - The bare-name allowance in `bin/cortex-check-parity` is at line 92 (comment) and line 715 (the un-prefixed-script-allowed list). Identical pattern in the mirror at `plugins/cortex-interactive/bin/cortex-check-parity`.
  - The `justfile` recipe is at lines 77–79; verify the exact range with `grep -n 'overnight-schedule' justfile`.
  - After deletion, the dual-source pre-commit hook still passes because the mirror was also updated.
- **Verification**:
  - `test ! -e bin/overnight-schedule` — pass if exit 0.
  - `grep -rn 'overnight-schedule' bin/ skills/ plugins/cortex-overnight-integration/ docs/ justfile` — pass if zero matches (exit 1 from grep). The listed paths exclude `lifecycle/` and `research/` so historical artifacts are out of scope by construction.
  - `bin/cortex-check-parity --self-test` — pass if exit 0. (The script exposes `--self-test` at `bin/cortex-check-parity:1086` which runs the inline fixture cases via `run_self_test()` at `:1021`.)
- **Status**: [ ] pending

### Task 11: Update `docs/overnight-operations.md` scheduling section
- **Files**:
  - `docs/overnight-operations.md` (modify — Scheduled Launch subsection at lines 231–240, plus TCC/Section 9 if needed)
- **What**: Rewrite the scheduling section per R17. Document: (a) `cortex overnight schedule <target>` usage; (b) the LaunchAgent mechanism in one paragraph (plist in `$TMPDIR`, fires via launchd, no tmux); (c) operational caveats: machine must be powered on and not sleeping at fire time (locked is fine), reboot drops pending schedules (re-schedule after reboot), SSH/headless contexts not supported; (d) cancel/list operations; (e) TCC requirement: Full Disk Access must be granted to the cortex binary (path printed by `which cortex`) — failures surface via fire-time fail markers in the morning report, not at schedule time.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - Existing scheduling subsection is at lines 231–240. The TCC subsection (Section 9) at the bottom of the file may already mention fail markers — confirm and extend as needed.
  - This is the canonical doc for overnight; per CLAUDE.md the round-loop and orchestrator behavior live here. Stay in scope: rewrite scheduling only; do not edit the round-loop section.
- **Verification**:
  - `grep -c 'launchd\|LaunchAgent' docs/overnight-operations.md` ≥ 3 (per spec R17 acceptance).
  - `grep -c 'Full Disk Access' docs/overnight-operations.md` ≥ 1 (per spec R13 acceptance).
- **Status**: [ ] pending

### Task 12: Fail-marker scanner module + morning-report integration + status surface
- **Files**:
  - `cortex_command/overnight/fail_markers.py` (new — small scanner module)
  - `cortex_command/overnight/report.py` (modify — fold fail-marker findings into `collect_report_data` and add a `render_scheduled_fire_failures` section)
  - `cortex_command/overnight/cli_handler.py` (modify — `handle_status` surfaces fail-markers found across sibling session dirs; add a `fire_failures` field to the JSON envelope and a "Recent scheduled-fire failures" line to human output)
  - `cortex_command/overnight/tests/test_fail_marker_scanner.py` (new)
  - `cortex_command/overnight/tests/test_report_fire_failures.py` (new — exercises `render_scheduled_fire_failures`)
- **What**: Build the consumer side of the fail-marker contract that Task 3 writes (R13). `fail_markers.py` exposes a single function `scan_session_dirs(state_root: Path, since: datetime | None = None) -> list[FailedFire]` returning a list of dataclass `FailedFire(ts, error_class, error_text, label, session_id, session_dir)` parsed from `<state_root>/sessions/*/scheduled-fire-failed.json`. `report.py` calls this from `collect_report_data` and adds a new `render_scheduled_fire_failures(data) -> str` section that surfaces each failure with timestamp, error class, session_id, and the absolute path to the fail-marker JSON for diagnostics. `cli_handler.py`'s `handle_status` calls the same scanner and surfaces fail-markers in both JSON and human output — this gives the user three layered surfaces: (1) immediate macOS notification at fire time (Task 3); (2) `cortex overnight status` immediately surfaces it any time the user runs status; (3) the next runner's morning report includes it. Task 12 ensures (2) and (3); Task 3 already provides (1).
- **Depends on**: [3, 7]
- **Complexity**: complex
- **Context**:
  - `fail_markers.py` is a stand-alone module; no dependencies on the scheduler package or the runner. The `since` filter lets the morning-report integration include only failures since the previous successful run, avoiding re-surfacing already-resolved markers across multiple morning reports.
  - State root: cortex sessions live under a known root (find via `state.py` or `cli_handler.py` — likely `_resolve_repo_path()/lifecycle/sessions/` or similar; confirm via existing `list_sessions` helper).
  - `report.py:95–204` already loads structured artifacts. Add a parallel call: `data["scheduled_fire_failures"] = fail_markers.scan_session_dirs(state_root, since=last_successful_run_ts)`. Add `render_scheduled_fire_failures(data)` to the renderer table; emit a section only when the list is non-empty.
  - `handle_status` JSON envelope at `cli_handler.py:383–389`: add `fire_failures` field (empty list when none, list of FailedFire-as-dict when present). Human output: emit a single "⚠ Recent scheduled-fire failures: N (run `cortex overnight logs` or see `<path>` for details)" line when non-empty. Suppress when empty.
  - `test_fail_marker_scanner.py`: covers parse-happy-path; multiple session dirs with mixed states; corrupt JSON in one of the markers (skip with warning, don't crash); the `since` filter; missing state root (returns empty list).
  - `test_report_fire_failures.py`: exercises `render_scheduled_fire_failures` with empty data (renders nothing), single failure (renders section header + entry), multiple failures (renders all). Verifies the section text contains absolute paths so the user can copy-paste to inspect.
- **Verification**: `pytest cortex_command/overnight/tests/test_fail_marker_scanner.py cortex_command/overnight/tests/test_report_fire_failures.py -v` — pass if exit 0.
- **Status**: [ ] pending

### Task 13: End-to-end smoke + plan completion
- **Files**:
  - `cortex_command/overnight/tests/test_scheduler_e2e.py` (new — single integration test)
- **What**: One end-to-end test that schedules 5 minutes out (with `launchctl` mocked but the rest real), asserts the sidecar entry, plist file, launcher.sh file, and `scheduled_start` state-file write all exist, then cancels and asserts all four (sidecar entry, plist, launcher, scheduled_start) are removed/cleared. **Also covers fail-marker → status surface end-to-end**: simulate a launcher fail-marker write (touch the JSON sentinel directly), then call `handle_status` and assert the `fire_failures` field is populated. This is the "everything wires together" check that the per-task tests don't catch in isolation.
- **Depends on**: [7, 8, 9, 10, 11, 12]
- **Complexity**: simple
- **Context**:
  - Use `pytest`'s `tmp_path` fixture for `$TMPDIR` and `~/.cache/cortex-command/`; monkeypatch `subprocess.run` to fake `launchctl bootstrap`/`bootout`/`print`.
  - This is the final "ship" gate before the plan is considered done.
- **Verification**: `pytest cortex_command/overnight/tests/test_scheduler_e2e.py -v` — pass if exit 0.
- **Status**: [ ] pending

## Verification Strategy

After all tasks land, the feature is verified end-to-end via:

1. **Unit suite**: `pytest cortex_command/overnight/tests/ -v` — all new tests pass plus existing suite stays green.
2. **MCP suite**: `pytest plugins/cortex-overnight-integration/tests/ -v` — pass.
3. **Parity check**: `bin/cortex-check-parity` — pass.
4. **Affected-tests suite** (revised after critical review): `pytest tests/test_runner_signal.py tests/test_runner_followup_commit.py tests/test_runner_pr_gating.py tests/test_cli_overnight_format_json.py tests/test_mcp_subprocess_contract.py -v` — pass; covers the in-repo callers of `cortex overnight start` blocking semantics that Task 6 affects.
5. **Live smoke (manual, this machine, ~5 minutes)**:
   - `cortex overnight schedule $(date -v+2M +%H:%M)` — prints session_id, label, scheduled_for_iso; `cortex overnight status` reports `Scheduled fire: <iso>`.
   - `launchctl print gui/$(id -u)/<label>` — exit 0, `state = waiting`.
   - Wait 2 minutes; runner spawns under launchd; `cortex overnight status` reports `phase: running`.
   - Or: `cortex overnight cancel <session_id>` immediately — `launchctl print` exits 113; `cortex overnight status` no longer shows `Scheduled fire`.
6. **Async start verification (manual)**: `time cortex overnight start --format json` returns within 5 seconds with `"started": true`. `cortex overnight status` reports `phase: running` shortly after.
7. **Fail-marker surface verification (manual)**: `touch <test_session_dir>/scheduled-fire-failed.json` with sample JSON; `cortex overnight status` shows the fail-marker; the next `cortex overnight start` produces a morning report with a "Scheduled-fire failures" section.

## Veto Surface

- **Launcher language is bash, not Python.** Considered Python (better JSON shape, integrates with scheduler module). Chose bash for shell-pattern fidelity and faster fire-time start. If you want Python, raise it now — Task 3 changes shape.
- **Launcher copied to `$TMPDIR` per schedule** rather than referenced from package-data via importlib.resources. Considered the latter (one canonical file, no copies). Chose per-schedule copy so the launcher and plist are paired ephemeral artifacts and survive venv updates between schedule and fire. If you want package-data reference, Task 3 simplifies but R19 GC has to handle a different lifecycle.
- **`Scheduler` protocol shape committed to in this plan** (4 methods, 2 dataclasses) — spec deferred this to plan phase. If the chosen shape doesn't match an as-yet-unbuilt second backend in your head, raise it now.
- **`--force` on `cortex overnight start` does NOT cancel the pending schedule** — lets both run, runner's existing concurrent-start guard handles collision. If you'd rather `--force` mean "cancel pending and proceed," Task 7 changes.
- **`phase: starting` is a new state value** in `cortex overnight status`. Callers that pattern-match on the existing phase enum will need to handle it. Considered keeping the existing `phase: pending`/`phase: running` pair; chose to add `starting` so the 5-second handshake window is observable rather than indeterminate.
- **Signal propagation breaks**: today, `^C` on a running `cortex overnight start` sends SIGINT to the runner because the parent shell, the cortex CLI, and the runner share a process group. After Task 6's `start_new_session=True` async-spawn, the runner is its own process group leader and the cortex CLI process exits within 5s. Operators who Ctrl-C the cortex command after Task 6 will find that nothing happens — the runner continues. The new operator pattern is `cortex overnight cancel <session_id>` (which sends SIGTERM via the pid lookup). Raise now if you want the shim to install a signal handler that propagates to the child during the 5-second handshake window — that is feasible but adds Popen lifecycle complexity to Task 6.
- **In-repo callers of blocking `cortex overnight start` semantics enumerated** (revised after critical review): `justfile:65-75` (`overnight-run` recipe), `README.md:125-126`, `tests/test_runner_signal.py:179-227`, `tests/test_runner_followup_commit.py:206-235`, `tests/test_runner_pr_gating.py` (11 tests using `--dry-run`), `tests/test_cli_overnight_format_json.py:245`. Task 6 pins `--dry-run` inline so the 11 PR-gating tests survive; Task 6 also rewrites the two signal-test files; Task 10 updates the `justfile` recipe and `README.md`. The format_json test depends on the pre-flight JSON refusal preceding async-spawn — Task 6's What pins this ordering. External-script users (`cortex overnight start && next-thing`) still break per spec; no `--wait` shim ships in this ticket.
- **Liveness probe in `wait_for_pid_file`** added in Task 6 in response to the critical review. Considered "appearance is enough" (simpler, faster handshake) — rejected because a transient pid file from a process that died in the first second would return `started: true` for a dead session. The liveness probe (`os.kill(pid, 0)` after reading the pid) catches this. If you want appearance-only semantics, Task 6's wait_for_pid_file changes shape.
- **Orphan-kill on timeout** added in Task 6 in response to the critical review. The `start_new_session=True` Popen child is reparented and would survive parent timeout; without explicit `os.killpg(SIGTERM)` the child can write `runner.pid` after the parent already returned `started: false`, contradicting the return value. Considered leaving the orphan alive (less aggressive) — rejected because the spec contract for `started: false` is incompatible with a runner materializing 100ms later.
- **`fcntl.flock` on `~/.cache/cortex-command/scheduled-launches.lock`** added in Task 4 in response to the critical review. The GC pass at `schedule()` start would otherwise race with concurrent `schedule()` invocations (one's GC removing the other's mid-flight plist before its sidecar entry lands). Considered mtime-grace-period in GC instead (lighter; doesn't serialize) — rejected because mtime skew on networked filesystems and concurrent same-second schedules make grace-period correctness fragile. The flock serializes only the schedule path, not status/cancel/list reads.
- **`scheduled_start` write step added to Task 5** in response to the critical review. Spec R7 references writing this field; the plan as drafted only had the cancel-side clear (Task 7), which would have been a no-op. Task 5 now writes it; Task 7 surfaces it in `handle_status`; Task 7's clear-on-cancel becomes meaningful.
- **Test file structure** — one test file per requirement cluster, not one per requirement. If the project's test-organization convention prefers smaller files (or a single `test_scheduler.py` with classes), say so.

## Scope Boundaries

Per spec Non-Requirements (verbatim):

- Reboot survival of pending schedules — `$TMPDIR` placement is deliberate; reboot drops the plist; user re-schedules after reboot.
- SSH/headless support — assumes a local logged-in macOS session; no `user/$UID` domain fallback; documented only.
- Cross-platform implementation — only `MacOSLaunchAgentBackend` ships; `Scheduler` protocol is in place but no second backend is built.
- Multiple concurrent schedules — one pending schedule at a time; CLI enforces single-pending; sidecar supports list semantics for future extensibility.
- Migration of `bin/overnight-status` and other overnight bin scripts — out of scope; only `bin/overnight-schedule` is retired.
- Auto-resume of in-flight runs after Mac sleep — `caffeinate` at fire time keeps Mac awake during the run; if Mac sleeps mid-run for other reasons, recovery is not in scope.
- Built-in TCC auto-grant — fire-time fail markers detect denial; user must grant manually via System Settings.
