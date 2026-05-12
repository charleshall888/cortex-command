# Specification: Rebuild overnight runner under cortex CLI

> Epic reference: scoped from `research/overnight-layer-distribution/research.md`. Epic content is background only; this spec scopes the ticket-115 rebuild.

## Problem Statement

The overnight execution framework — 1,694 lines of bash in `cortex_command/overnight/runner.sh` plus 50 inline `python3 -c` snippets — is architecturally incompatible with `uv tool install -e .` distribution (the target Ticket 113 established). Ships as a Python entry point require a Python-owned orchestration layer. Beyond packaging, the bash runner couples to 23 `REPO_ROOT` sites and a `.venv` activation that only resolves under the cortex-command repo itself, so the tool silently breaks the moment it is installed against any other project — the exact use case Ticket 113 exists to enable. Ticket 116 (MCP control-plane) is `blocked_by: [115]` because 116 requires a stable, versioned IPC contract that the current bash runner does not expose.

115 replaces `runner.sh` with a pure-Python orchestration layer under `cortex overnight` (subcommands `start`, `status`, `cancel`, `logs`), preserves every load-bearing guarantee enumerated in `requirements/pipeline.md`, ships an explicit versioned IPC contract that 116 can build on, and retires the `bin/` shim scripts.

## Requirements

> **Priority**: All R1–R26 are **must-have**. This is a critical-path rebuild of the autonomous-execution core; there is no partial-ship mode — either the runner works end-to-end or the overnight layer is broken. R27 (follow-up tickets filed) is **must-have for ticket closure** — process hygiene required for handoff to tickets 116 and 112. Non-Requirements (below) captures **won't-have** boundaries with owning-ticket references. No items are classified as should-have.

### Command-line surface

**R1. `cortex overnight start`** replaces `runner.sh` as the primary entry point. Accepts `--state <path>`, `--time-limit <duration>`, `--max-rounds <int>`, `--tier <simple|complex>`, `--dry-run`. Discovers session directory from the state file path or auto-discovers via cwd (same algorithm `runner.sh:122-163` uses today, ported verbatim).

Acceptance: `cortex overnight start --help` exits 0 and stdout contains `--state`, `--time-limit`, `--max-rounds`, `--tier`, `--dry-run`. Command runnable after `uv tool install -e .`: `command -v cortex` exits 0 AND `cortex overnight start --help` exits 0.

**R2. `cortex overnight status`** prints session state. `--format json` emits a machine-readable object; default format is human-readable. Reads active-session pointer at `~/.local/share/overnight-sessions/active-session.json`; falls back to most recent `lifecycle/sessions/*/` when pointer is absent or points at a complete session.

Acceptance: With an active session, `cortex overnight status --format json` exits 0 and stdout parses as JSON containing keys `session_id`, `phase`, `current_round`, `features`. With no active session, exits 0 and prints a non-empty message (human format) or `{"active": false}` (JSON format).

**R3. `cortex overnight cancel`** reads the active-session pointer (or a `--session-dir <path>` override), validates the session-id against `^[a-zA-Z0-9._-]{1,128}$`, resolves the session directory and asserts `os.path.realpath(session_dir).startswith(os.path.realpath(lifecycle_sessions_root))` before any file access, reads the per-session `runner.pid` file, verifies `magic` and `start_time` still match the running process (via `psutil.Process(pid).create_time()` within ±2s), then calls `os.killpg(pgid, SIGTERM)`. If no valid live session is found, exits nonzero with a clear message; never signals unverified PIDs.

Acceptance: Shell-metachar input triggers rejection — `cortex overnight cancel "; rm -rf ~"` exits nonzero, stderr contains `invalid session id`. Path-traversal input rejected — `cortex overnight cancel ../../../etc` exits nonzero, stderr contains `invalid session id`. Cancel of a stale lock (PID dead or start-time mismatch) exits nonzero with a specific message and does NOT signal any process (test: mock `runner.pid` with a PID that exists but has a different start_time; assert `os.killpg` is not called).

**R4. `cortex overnight logs`** reads `lifecycle/sessions/{id}/overnight-events.log` and (when `--files <stream>` is passed) `lifecycle/sessions/{id}/agent-activity.jsonl` and `lifecycle/escalations.jsonl`. Supports `--tail <N>` (default 20), `--since <cursor>` where the cursor is either an RFC3339 timestamp (applied to each line's `ts` field) or a byte-offset (`@<int>` syntax) for idempotent resumption across restarts, and `--limit <N>` (default 500) for bounded output. Session-id resolved via active-session pointer or `--session-dir` override; same validation as R3.

Acceptance: `cortex overnight logs --tail 5` exits 0, emits ≤ 5 lines. `cortex overnight logs --since 2099-01-01T00:00:00Z` exits 0, no output. `cortex overnight logs --since @0 --limit 10` emits at most 10 lines starting from byte offset 0. `cortex overnight logs --since @<large-int>` past end-of-file returns empty output with a `# cursor-beyond-eof` trailer line on stderr for observer debugging.

### Architecture

**R5. Pure-Python orchestration.** A new module (`cortex_command/overnight/runner.py`) owns the round-dispatch loop. It imports `cortex_command.overnight.{state, events, plan, orchestrator, batch_runner, map_results, interrupt, integration_recovery, smoke_test, auth, report, ...}` directly — no `python3 -c` heredocs, no `python3 -m cortex_command.*` subprocess calls for in-process module invocation. External-process spawns (`claude -p` for the orchestrator agent; the Claude Code CLI for feature agents) use `subprocess.Popen(..., start_new_session=True)`.

Acceptance: `grep -rn 'python3 -c\|python3 -m cortex_command' cortex_command/overnight/*.py` returns exit code 1 (no matches). `grep -c 'import cortex_command\|from cortex_command' cortex_command/overnight/runner.py` ≥ 5.

**R6. `runner.sh` retired.** File `cortex_command/overnight/runner.sh` is deleted. All tests previously invoking it are rewired to exercise `cortex_command.overnight.runner` via direct Python import (preferred) or `cortex overnight start` subprocess.

Acceptance: `test -f cortex_command/overnight/runner.sh` exits 1. `grep -rn 'runner\.sh' tests/ cortex_command/` returns only references in historical documentation/changelog comments, not in test code or live imports. `just test` exits 0.

**R7. Sync + threading concurrency model with explicit coordination primitives.** The Python runner uses synchronous subprocess calls on the main thread + one stall-detection watchdog thread per spawned subprocess (orchestrator, batch_runner). **Rationale**: runner.sh's actual shape is sequential — main blocks on `wait $CLAUDE_PID` (runner.sh:648), then later on `wait $BATCH_PID` (runner.sh:724); only one foreground subprocess runs at a time, each paired with one sibling watchdog. This shape maps cleanly to sync+threading. The `requirements/multi-agent.md` "1–3 concurrent agents" figure refers to feature agents inside `batch_runner.py`, not inside `runner.py` — batch_runner's concurrency model is preserved unchanged.

**R7 mandates these coordination primitives** (spec-level, not implementation hints):

- `shutdown_event: threading.Event` — set by signal handlers to trigger clean shutdown. Shared across main and all watchdog threads. Watchdog sleep loops use `shutdown_event.wait(timeout=N)` (not `time.sleep`), so SIGHUP can interrupt their sleep.
- `stall_flag: threading.Event` per watchdog — set by watchdog when it decides to kill its subprocess. Main thread checks after `Popen.wait()` returns to distinguish "subprocess exited normally with nonzero code" from "watchdog killed PGID due to stall" — replaces `STALL_FLAG` tmpfile at runner.sh:657.
- `state_lock: threading.Lock` — serializes state-file writes between main thread and watchdog threads. All mutations route through `state.save_state(...)` which acquires the lock; unlocked reads remain safe because forward-only transitions keep re-reads idempotent (`requirements/pipeline.md:133-134` applies within the new threading topology because the lock protects the write side).
- `kill_lock: threading.Lock` — serializes PGID termination between watchdog's stall-kill and main handler's cleanup-kill to prevent the double-killpg-on-recycled-PID race.

Acceptance: `grep -c 'threading\.Event\|threading\.Lock' cortex_command/overnight/runner.py` ≥ 3. `grep -c '\.wait(.*timeout' cortex_command/overnight/runner.py` ≥ 1 (watchdog sleep pattern present). No `time\.sleep(` in watchdog functions (check via code review). `pytest tests/test_runner_threading.py` (new) exits 0 — verifies stall_flag distinguishes stall-kill from normal exit, verifies concurrent cancel+stall doesn't double-kill, verifies SIGHUP during watchdog sleep wakes it.

### IPC contract (for 116)

**R8. Per-session PID file schema.** On session start, atomically write `lifecycle/sessions/{id}/runner.pid` (no leading dot, matching 116's contract expectation) with `0o600` permissions containing:

```json
{
  "schema_version": 1,
  "magic": "cortex-runner-v1",
  "pid": 12345,
  "pgid": 12345,
  "start_time": "2026-04-23T18:00:00Z",
  "session_id": "2026-04-23-18-00-00",
  "session_dir": "/abs/path/to/lifecycle/sessions/2026-04-23-18-00-00",
  "repo_path": "/abs/path/to/repo"
}
```

**Versioning rule**: `schema_version` is the single version axis for this contract. It is an integer. Additive field changes that are backward-compatible (new optional fields with documented defaults) do NOT require a bump. Breaking changes (field renames, removed fields, type changes, semantic changes to an existing field) require `schema_version: 2` and a read-side compat note documenting how 115-written files are upgraded or rejected.

Cleared atomically on clean shutdown; left in place on uncleaned exits (cancel detects stale-ness via `magic` + `start_time` re-verification).

Acceptance: After `cortex overnight start`, file exists at `lifecycle/sessions/{id}/runner.pid` with mode `0o600` and parses as JSON containing all keys above. `stat -f '%Lp' <path>` (macOS) or `stat -c '%a' <path>` (Linux) outputs `600`. `grep -n 'cortex_version' cortex_command/overnight/*.py` returns exit code 1 (no dual-version axis).

**R9. Active-session pointer enhanced schema.** `~/.local/share/overnight-sessions/active-session.json` atomically rewritten on start/transitions with the same schema as R8 plus `phase: "planning|executing|paused|complete"`. Cleared on session `complete` transition — NOT cleared on `paused` transition (so dashboard/statusline can still read the paused session).

Acceptance: After `cortex overnight start`, file exists and parses as JSON containing `schema_version`, `magic`, `pid`, `pgid`, `start_time`, `session_id`, `session_dir`, `repo_path`, `phase`. After session transitions to `paused`, file still exists and `phase == "paused"`. After session transitions to `complete`, file is absent.

**R10. State file `schema_version`.** `cortex_command/overnight/state.py::OvernightState` gains a `schema_version: int = 1` field, included in all JSON writes. Read path tolerates absence (legacy state files pre-115 treated as `schema_version = 0` and upgraded to 1 on next write). Future `1 → 2` upgrades follow the same pattern: on-disk mismatch is upgraded in-place on next write; R18's cancel-time check uses `schema_version >= 1` (not `==`).

Acceptance: After a round runs, `jq -r '.schema_version' lifecycle/sessions/{id}/overnight-state.json` outputs `1`. Loading a test fixture without `schema_version` does not raise; `jq` output after next save is `1`.

**R11. Log cursor protocol — timestamp + byte-offset.** Cursors are dual-form. Timestamp cursors (`--since <RFC3339>`) filter on each line's `ts` field — convenient but not idempotent across lines with identical millisecond timestamps. Byte-offset cursors (`--since @<int>`) are exact and idempotent across retries; used by programmatic consumers (116's MCP tools). Each log query returns a trailer line on stderr containing `next_cursor: @<int>` for chaining. `--files` flag selects among `events.log` (default), `agent-activity.jsonl`, `escalations.jsonl`. Log rotation is not supported in 115; files are single-per-session append-only, per `requirements/pipeline.md:128`.

Acceptance: All events.log lines match `^{"ts":"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.*Z"`. `cortex overnight logs --since @0 --limit 10` stderr last line matches `^next_cursor: @[0-9]+$`. `cortex overnight logs --since @<next_cursor> --limit 10` is idempotent with `cortex overnight logs --since @<next_cursor_of_same_second_invocation> --limit 10` — advancing the cursor by exactly one page.

### Preservation surface — load-bearing guarantees

**R12. Atomic state writes preserved at all 25+ sites.** Every state mutation uses `tempfile.NamedTemporaryFile(dir=target_dir, delete=False)` + `f.write()` + `f.flush()` + `os.fsync()` + `os.replace(tmp, dest)`. Existing call sites in `state.py`, `plan.py`, `orchestrator.py`, `outcome_router.py`, `feature_executor.py`, `map_results.py`, `daytime_pipeline.py`, `interrupt.py`, `deferral.py` keep their current implementation. The ~15 inline-Python state-write sites in runner.sh migrate to Python functions in `runner.py` or peer modules.

Acceptance: `pytest cortex_command/overnight/tests/test_state.py` exits 0. `grep -rn 'os\.replace\|\.replace(tmp' cortex_command/overnight/*.py` count ≥ 20.

**R13. Process-group management preserved.** Every subprocess spawned by `runner.py` for long-running agents (orchestrator, batch_runner) is spawned with `start_new_session=True` so it lives in its own PGID. Watchdog threads monitor stall timeouts and call `os.killpg(os.getpgid(pid), signal.SIGTERM)` inside a `with kill_lock:` block (R7 coordination primitive) to terminate the group; SIGKILL escalation follows on timeout.

Acceptance: `grep -c 'start_new_session=True' cortex_command/overnight/runner.py` ≥ 2. `grep -c 'os\.killpg' cortex_command/overnight/runner.py` ≥ 1. `pytest tests/test_runner_threading.py::test_watchdog_and_cancel_dont_double_kill` exits 0 — verifies kill_lock serialization.

**R14. Signal-based graceful shutdown preserved — flag+main-loop pattern.** The Python runner installs handlers for `SIGINT`, `SIGTERM`, `SIGHUP` that do the minimum-safe work: set `shutdown_event`, record the triggering signal in `_received_signal`, and return. The main loop checks `shutdown_event.is_set()` at safe points (after each `Popen.wait()`, after each state transition, between rounds) and, when set, invokes a full `cleanup()` function on the main thread:

1. Log a `circuit_breaker` event (runner.sh:489 contract) with `{"reason": "signal"}` into `overnight-events.log` via existing `events.log_event(...)`.
2. Atomically rewrite `active-session.json` with `phase: "paused"` — do NOT clear it; dashboard/statusline must still read the paused session (preserves runner.sh:472-488 behavior).
3. Compose and write the partial morning report via the existing 4-call sequence: `report.collect_report_data(...)` → `report.create_followup_backlog_items(...)` → `report.generate_report(...)` → `report.write_report(...)`. (There is no single `report.generate_morning_report` function; the spec names the real API.)
4. Acquire `kill_lock`; terminate all spawned subprocess PGIDs; release.
5. `os.kill(os.getpid(), 130)` to exit with SIGINT's canonical exit code 130.

Critical-section shielding is scoped to individual `os.replace` call sites inside `state.save_state` and `events.log_event` — NOT the full cleanup. A helper `with deferred_signals(): ...` wraps each atomic write; signals arriving during the write are stashed and re-raised after `os.replace` returns. The cleanup function itself runs in the main thread post-wait(), so async-signal-safety is not a concern.

Acceptance: `pytest tests/test_runner_signal.py` exits 0 (after port). The ported test verifies: (a) SIGHUP during mid-round main-thread wait triggers cleanup and exits 130; (b) `overnight-events.log` last event is `circuit_breaker` with `reason: signal`; (c) `active-session.json` phase is `paused` (file exists, not cleared); (d) no backlog file under `backlog/` is left half-written (crash mid-`create_followup_backlog_items`); (e) watchdog thread stops cleanly after `shutdown_event` set.

**R15. `--dry-run` mode preserved with byte-identical stdout contract.** `cortex overnight start --dry-run` produces DRY-RUN output matching today's `bash runner.sh --dry-run` format exactly — not a loose superstring match. PR-side-effect calls (`gh pr create`, `gh pr ready`, `git push`, `notify.sh`) are echoed as `DRY-RUN <label> <args...>` lines on stdout with the same label strings bash uses today (grep runner.sh for `dry_run_echo` call sites and preserve each label verbatim); state writes proceed as real writes; rejects invocation when any feature is `pending`. `DRY_RUN_GH_READY_SIMULATE` env var retained for test-only failure simulation.

Acceptance: `pytest tests/test_runner_pr_gating.py` exits 0 (all 11 subtests pass after port). `cortex overnight start --dry-run --state <tmp-with-pending>` exits nonzero, stderr contains `--dry-run requires a state file with all features in terminal states`. **Byte-identical check**: capture a reference DRY-RUN stdout from the pre-port `bash runner.sh --dry-run` (checked into `tests/fixtures/dry_run_reference.txt` during ticket implementation); the ported test asserts `assert actual_stdout.splitlines() == reference.splitlines()` — full-line equality, not substring — for every line with a `DRY-RUN ` prefix. Format drift is caught.

**R16. Pipeline.md must-have preservation — audit and coverage tiers.** The following 22 must-have acceptance criteria from `requirements/pipeline.md` remain satisfied after the rebuild. Each is tagged with its verification tier — **[T]** = covered by test, **[M]** = manual/convention, no algorithmic test:

- **[T]** Forward-only phase transitions (planning → executing → complete; any → paused); paused auto-resume — covered by `cortex_command/overnight/tests/test_state.py::test_phase_transitions`
- **[T]** Budget exhaustion pauses session (no crash) — covered by `cortex_command/overnight/tests/test_throttle.py`
- **[T]** Zero-merge home-repo PR draft with `[ZERO PROGRESS]` title prefix — covered by `tests/test_runner_pr_gating.py` (migrated per R25)
- **[T]** `integration_pr_flipped_once` session-scoped marker and one-shot flip semantics — covered by `tests/test_runner_pr_gating.py` (migrated per R25)
- **[T]** Feature status lifecycle (pending/running/merged/paused/deferred/failed) — covered by `cortex_command/overnight/tests/test_feature_executor.py`
- **[M]** Paused auto-retry on resume — convention across `interrupt.py`, `feature_executor.py`; no dedicated test exists today. **R16 requires adding `tests/test_runner_resume_semantics.py` (new) covering the paused-feature auto-retry path**.
- **[M]** Deferred (human decision) awaits — convention; no dedicated test exists today. **R16 requires adding a test case for deferred-skip-on-resume** in the new `test_runner_resume_semantics.py`.
- **[M]** Fail-forward (one feature's failure doesn't abort round siblings) — no dedicated test. **R16 requires adding `tests/test_runner_fail_forward.py` (new)** that spawns a feature destined to fail plus a sibling; asserts sibling reaches `merged`.
- **[T]** `recovery_attempts` + `recovery_depth` counters per feature — covered by `cortex_command/overnight/tests/test_integration_recovery.py`
- **[T]** Conflict resolution fast-path (≤3 files, no hot files, `git checkout --theirs`) — covered by `cortex_command/pipeline/tests/test_conflict.py` / `test_trivial_conflict.py`
- **[T]** Sonnet → Opus repair escalation (single escalation for merge conflicts; max 2 attempts for test failures) — covered by `cortex_command/pipeline/tests/test_merge_recovery.py` / `test_repair_escalation.py`
- **[T]** Test gate after any resolution; cleanup on gate failure — covered by `cortex_command/overnight/tests/test_smoke_test.py`
- **[T]** Post-merge review gating matrix — covered by `cortex_command/pipeline/tests/test_review_dispatch.py`
- **[T]** `dispatch_review()` dispatch; batch_runner owns events.log writes — covered by `cortex_command/pipeline/tests/test_review_dispatch.py`
- **[T]** 2-cycle rework loop with `orchestrator-note.md` + SHA circuit breaker — covered by `cortex_command/pipeline/tests/test_review_rework.py`
- **[T]** Non-APPROVED → `deferred`; APPROVED → events — covered by `cortex_command/pipeline/tests/test_review_dispatch.py`
- **[T]** Flaky guard re-merge; SHA circuit breaker on no-new-commits — covered by `cortex_command/pipeline/tests/test_flaky_guard.py`
- **[T]** Learnings log + recovery-log — covered by `cortex_command/overnight/tests/test_integration_recovery.py`
- **[T]** Deferral files atomic with full schema — covered by `cortex_command/overnight/tests/test_deferral.py`
- **[M]** Post-session sync via `bin/git-sync-rebase.sh` + `sync-allowlist.conf` — script-level; no pytest today. **R16 requires adding `tests/test_git_sync_rebase.sh` bats-style shell test OR a Python test invoking the script with fixture state**.
- **[M]** `--merge` PR strategy as load-bearing rebase semantics — convention in `bin/git-sync-rebase.sh`; no test. **Add to the new sync-rebase test**.
- **[M]** Integration branch persistence (not auto-deleted) — no test; existing `test_plan.py::test_stale_branch_deleted_before_worktree_add` tests the *opposite* case. **R16 requires adding a test asserting `git show-ref refs/heads/overnight/<session_id>` succeeds after session complete**.
- **[M]** Orchestrator rationale convention — operator discipline; not algorithmically verifiable. No new test; noted as a convention preserved by prompt text in `prompts/orchestrator-round.md`.

Acceptance: `just test` exits 0. Every `[T]` test file named above exists and passes before and after 115's implementation. Every `[M]` item either has its new test added per the bullets above, or (for `orchestrator rationale convention`) a note in the prompt confirming the convention is preserved. **Verification of preservation is file-by-file review during implementation**, not a structurally-broken pre/post diff — the prior version of R16's acceptance contained a `git stash`-based diff that cannot work because R6 deletes `runner.sh` and R25 rewires tests; removed.

### Security + robustness

**R17. Session-id validation and path containment.** `cortex overnight cancel`, `status`, and `logs` validate input session-ids against `^[a-zA-Z0-9._-]{1,128}$` and assert `os.path.realpath(session_dir).startswith(os.path.realpath(lifecycle_sessions_root))` before any file read. Malformed input rejected with exit nonzero and stderr containing `invalid session id`.

Acceptance: `pytest tests/test_cortex_overnight_security.py` (new) exits 0 — tests cover regex rejection (shell metachars, unicode, oversized, traversal attempts) and realpath containment (symlink-to-outside traversal).

**R18. PID file verification before signalling.** `cortex overnight cancel` reads the PID file, verifies `magic == "cortex-runner-v1"`, verifies `schema_version >= 1`, verifies `start_time` matches the running process (`psutil.Process(pid).create_time()` within ±2 seconds of the file's recorded `start_time`). Any mismatch → abort with a specific error; never call `os.killpg`. This closes the PID-reuse race.

Acceptance: `pytest tests/test_cortex_overnight_security.py::test_cancel_rejects_stale_pid` exits 0 — fixture writes `runner.pid` with the test process's PID but a 1000-second-old `start_time`; cancel refuses to signal.

### Distribution-related behavior

**R19. Package-internal resources via `importlib.resources`.** Prompt templates (`cortex_command/overnight/prompts/orchestrator-round.md`, `batch-brain.md`, `repair-agent.md`) are loaded via `importlib.resources.files('cortex_command.overnight.prompts') / '<name>.md'`. User-repo paths (state, plan, events, session_dir, repo_path) are received as arguments from the CLI — never resolved via `importlib.resources`.

Acceptance: `grep -n 'importlib.resources\|importlib_resources' cortex_command/overnight/*.py` produces ≥ 3 matches. `grep -n "os\.environ\['REPO_ROOT'\]\|\$REPO_ROOT" cortex_command/overnight/*.py` returns exit code 1 (no matches).

**R20. CLI owns all user-repo path resolution.** The `cortex overnight start` entry point is the single site that discovers `repo_path`, `session_dir`, `state_path`, `plan_path`, `events_path`. It passes these as arguments to `runner.run(...)` — downstream Python code does not re-derive them. This eliminates the 23 `REPO_ROOT` / `CORTEX_COMMAND_ROOT` / `$PYTHONPATH` sites in runner.sh.

Acceptance: `grep -n 'Path(__file__)\.parent' cortex_command/overnight/runner.py` returns at most 1 match (module-location only, never for user-repo discovery). Functions in `runner.py` accept paths as arguments, confirmed by signature review in code review.

**R21. Editable install only (documented).** `docs/setup-guide.md` explicitly documents `uv tool install -e .` as the supported install mode. Non-editable wheel support is out of scope for 115; a follow-up backlog item is filed before 115 merges (per R27).

Acceptance: `grep -c 'uv tool install -e' docs/setup-guide.md` ≥ 1.

### Cross-cutting behavioral decisions

**R22. `notify.sh` graceful fallback.** When `~/.claude/notify.sh` is absent, notifications print to stderr with a `NOTIFY: ` prefix (stderr, not stdout — stdout is the orchestrator agent's input channel and must not be polluted). Existing `|| true` fallback for notify-failures is preserved. Machine-config remains responsible for deploying notify.sh.

Acceptance: With `~/.claude/notify.sh` absent, `cortex overnight start` → session-complete notification emits a line on **stderr** matching `^NOTIFY: `. `stdout` of `cortex overnight start` does NOT contain any `NOTIFY: ` prefix.

**R23. `apiKeyHelper` literal read preserved.** `auth.py::get_api_key_helper()` continues to read `~/.claude/settings.json` and `~/.claude/settings.local.json` at literal paths. Routing through a cortex-CLI config lookup is explicitly not done in 115 — 117 made these user/machine-config-owned; adding indirection now would churn.

Acceptance: `pytest cortex_command/overnight/tests/test_auth.py` exits 0. `grep -c '\.claude.*settings\.json' cortex_command/overnight/auth.py` ≥ 2.

### Retirement

**R24. `bin/` shims retired.** `bin/overnight-start` and `bin/overnight-status` are deleted. `bin/overnight-schedule` is **not touched** (owned by ticket 112). Any `just` recipes referencing the deleted shims are removed from `justfile`.

Acceptance: `test -f bin/overnight-start` exits 1. `test -f bin/overnight-status` exits 1. `test -f bin/overnight-schedule` exits 0 (preserved). `grep -n 'overnight-start\|overnight-status' justfile` exits 1 (no references).

**R25. Test migration.** The 5 runner.sh-coupled test files are rewired:

- `tests/test_runner_pr_gating.py` (625 LOC, 11 subtests) → port to exercise `cortex_command.overnight.runner.run(dry_run=True, ...)` directly (primary) with one wrapper test that invokes `cortex overnight start --dry-run` via subprocess to verify CLI wiring. Includes the byte-identical snapshot fixture per R15.
- `tests/test_runner_signal.py` (207 LOC) → port to exercise the Python runner in a subprocess (`cortex overnight start` with `SIGHUP` sent to its PID via `os.kill`). Asserts per R14's updated behavior: `circuit_breaker` event, `phase: paused` in active-session.json (not cleared), exit code 130, watchdog thread joined cleanly.
- `tests/test_runner_resume.py` (91 LOC) → rewrite the structural grep-on-source assertion (line 82) to assert a behavioral property (call the Python function, verify return value). The grep-on-source idiom is invalid post-R6 (runner.sh deleted).
- `tests/test_runner_followup_commit.py` (282 LOC) → port subprocess invocations to `cortex overnight start` or Python API.
- `tests/test_runner_auth.sh` → rewrite as Python pytest exercising `auth.py` directly.
- `tests/test_fill_prompt.py` (106 LOC) → rewrite to test the Python `fill_prompt()` function that replaces `runner.sh:362-376`'s inline helper.

Acceptance: `pytest tests/test_runner_pr_gating.py tests/test_runner_signal.py tests/test_runner_resume.py tests/test_runner_followup_commit.py tests/test_fill_prompt.py` exits 0. `grep -rn 'bash runner\.sh\|runner\.sh"' tests/` returns exit code 1. `test_runner_auth.sh` deleted or replaced with `.py` equivalent.

**R26. New tests added for preservation gaps identified in R16.** R16's `[M]`-tagged items that have no current test coverage require new tests before 115 merges:

- `tests/test_runner_resume_semantics.py` — paused auto-retry on resume + deferred-skip-on-resume
- `tests/test_runner_fail_forward.py` — sibling features continue after one fails
- Sync-rebase test (new, bats-style or Python) covering `bin/git-sync-rebase.sh` + `--merge` semantics
- Integration-branch-persistence test asserting `git show-ref refs/heads/overnight/<session_id>` succeeds after session complete

Acceptance: Each test file exists and `pytest <file>` (or `bats <file>`) exits 0.

### Follow-up tickets filed during 115

**R27. Follow-up backlog items filed.** Before 115 merges, file backlog tickets for:
- "Non-editable wheel install support" (R21 deferral)
- "Multi-session host concurrency" (Non-Requirements deferral) — only if the host-wide enumeration need becomes concrete; otherwise this item is explicitly a future-contingency with no owner yet.
- Any other scope explicitly deferred during implementation

Acceptance: `ls backlog/*.md | xargs grep -l 'wheel install support' | wc -l` ≥ 1. Any explicit scope deferral mentioned in plan.md or review.md has a matching backlog item.

## Non-Requirements

- **MCP server / IPC implementation** — owned by ticket 116, blocked on 115. 115 defines the contract surface (R8/R9/R10/R11 with explicit versioning rule); 116 builds MCP tooling on top. 115 does not implement any MCP server.
- **`overnight_list_sessions` enumeration contract** — 116 can scan `lifecycle/sessions/*/` and parse each `runner.pid` (using 115's R8 schema) to enumerate historical/concurrent sessions. 115 commits to R8's schema being stable for this purpose but does not implement an enumeration helper — 116 adds that if/when needed.
- **LaunchAgent scheduling migration** — owned by ticket 112. 115 does not touch `bin/overnight-schedule` or LaunchAgent plists.
- **Dashboard migration** — dashboard stays in place, invoked from the same codebase. 115 ensures dashboard-read state-file fields are unchanged; does not modify dashboard code.
- **Plugin distribution changes** — owned by ticket 120 (if active). 115 ships a CLI, not a plugin.
- **Non-editable wheel install support** — 115 is editable-only per `requirements/project.md`. Filed as follow-up (R27).
- **Multi-session host concurrency** — runner is single-active-session today (via global active-session pointer). 115 preserves that. Multi-session support is future-contingent.
- **Log rotation within a session** — events.log is append-only, single-file per session. No size limit or rotation.
- **Full async rewrite** — sync + threading is the chosen concurrency model (R7). Async is explicitly rejected.
- **Scope-creep refactors in downstream modules** — `report.py`, `outcome_router.py`, `integration_recovery.py`, etc. are not rewritten. 115 imports them as-is.

## Edge Cases

- **Stale `runner.pid` after crash**: PID still in file, but process is dead (or PID reused by unrelated process). Cancel reads file, checks `magic` + `psutil.Process(pid).create_time()` ≈ `start_time` (±2s tolerance). On mismatch or NoSuchProcess, emit "no active session" and exit 1 — never signal. Clears the stale `runner.pid` file.
- **Stale active-session pointer**: points at a session whose phase is `complete` or whose PID file is stale. `cortex overnight status` falls back to the most recent `lifecycle/sessions/*/` per `requirements/observability.md:64`.
- **Session-id with shell metachars**: R17 regex + `os.path.realpath` containment before any file operation. Invalid input exits nonzero with `invalid session id`.
- **Signal during atomic state write**: the `with deferred_signals(): os.replace(...)` helper stashes signals during the `os.replace` call only. The main loop checks `shutdown_event.is_set()` after each state transition; cleanup runs on the main thread in bounded time.
- **Signal while main thread is blocked in `Popen.wait()`**: SIGHUP/SIGTERM delivery to main thread interrupts `wait()` on both macOS and Linux (standard POSIX behavior with `subprocess.Popen.wait()`). On PEP-475-affected paths (e.g., `os.read` on subprocess stdout), if the signal handler returns without raising, the main loop still reaches its `shutdown_event.is_set()` check at the next safe point and initiates cleanup. No read-retry loops are used without a shutdown check between iterations.
- **Signal during watchdog thread sleep**: watchdog uses `shutdown_event.wait(timeout=N)` (R7 primitive); on `shutdown_event.set()`, the wait returns early and the watchdog exits its loop cleanly.
- **Watchdog and cancel race**: `kill_lock` serializes PGID termination. If watchdog acquires first (stall-kill), cancel sees `Popen.poll()` return non-None and exits with "session already terminating". If cancel acquires first, watchdog notices `shutdown_event` set and exits without killing.
- **Python runner killed uncleanly (SIGKILL / OOM)**: `cleanup()` does not run. `runner.pid` and `active-session.json` remain. Next `cortex overnight start` detects stale pointer and offers resume; next `cortex overnight cancel` sees stale PID (magic match + start_time mismatch or NoSuchProcess) and refuses to signal, clears the stale files.
- **Concurrent `cortex overnight start` invocations**: second invocation detects existing `runner.pid` with live PID + matching magic + start_time; exits nonzero with "session already running". No race on the active-session pointer — writes are atomic.
- **Cross-filesystem session directory**: if `$TMPDIR` is on a different filesystem than the user repo, `tempfile.NamedTemporaryFile(dir=target_dir)` + `os.replace` remains atomic because tempfile is created in the same directory as the destination.
- **`~/.claude/notify.sh` absent**: R22 stderr-prefixed fallback; session continues without crashing; stdout remains clean for `claude -p`.
- **`~/.claude/settings.json` malformed**: existing `auth.py` error handling raises `_HelperInternalError`; runner logs and falls back to OAuth token or refuses to start with a clear message.
- **`logs --since <future-timestamp>`**: returns empty output, exit 0, not an error.
- **`logs --since <malformed>`**: rejects with exit nonzero, stderr contains `invalid cursor`; valid RFC3339 parses with `datetime.fromisoformat()` (Python 3.11+).
- **`logs --since @<large-int>` past EOF**: returns empty output with a `# cursor-beyond-eof` trailer on stderr; exit 0.
- **Budget exhausted mid-round**: runner transitions session to `paused`, writes `paused_reason="budget_exhausted"`, invokes notify.sh hook, exits cleanly — preserves `runner.sh:1615` behavior.
- **Orchestrator agent timeout (stall detection)**: watchdog sets `stall_flag`, acquires `kill_lock`, kills orchestrator PGID; main thread returns from `wait()`, checks `stall_flag`, transitions session → `paused` with `paused_reason="orchestrator_stalled"`; preserves `runner.sh:645-670` semantics.
- **`--dry-run` with pending features**: rejects with stderr containing `--dry-run requires a state file with all features in terminal states` and exit 1 — preserves `runner.sh:593-594`.
- **Zero-merge session**: all features either failed or deferred; home-repo integration PR opened as draft with `[ZERO PROGRESS]` title prefix; `integration_pr_flipped_once = true` on success; preserves `runner.sh:1179,1227-1343`.

## Changes to Existing Behavior

- **ADDED**: `cortex overnight start|status|cancel|logs` command surface under the existing `cortex` CLI (scaffolded in ticket 114).
- **ADDED**: `runner.pid` file per session with explicit schema (magic, pid, pgid, start_time, schema_version, session_id, session_dir, repo_path). Supersedes `.runner.lock`'s bare-PID format. Note: filename moved from `.runner.lock` (hidden) to `runner.pid` (visible) to match ticket 116's stated contract expectation and allow `ls` visibility for operator debugging.
- **ADDED**: `schema_version` field on `OvernightState` and `active-session.json`. Read path tolerates absence (upgrades legacy state on next write).
- **ADDED**: `NOTIFY:`-prefixed stderr fallback when `~/.claude/notify.sh` is absent. (Stderr, not stdout — R22.)
- **ADDED**: `threading.Event` / `threading.Lock` coordination primitives in `runner.py` — `shutdown_event`, `stall_flag` (per watchdog), `state_lock`, `kill_lock`. (R7.)
- **ADDED**: `--since @<byte-offset>` cursor semantics for `cortex overnight logs` (alongside RFC3339 timestamp). (R11.)
- **ADDED**: `--files` flag on `cortex overnight logs` for selecting among `events.log` / `agent-activity.jsonl` / `escalations.jsonl`. (R11.)
- **ADDED**: `--limit` flag on `cortex overnight logs` for bounded output. (R11.)
- **ADDED**: Formalized `schema_version` evolution rule (additive → no bump; breaking → bump + upgrade policy). (R8, R10.)
- **ADDED**: Byte-identical DRY-RUN stdout reference fixture at `tests/fixtures/dry_run_reference.txt`. (R15.)
- **ADDED**: New test files per R26 for pipeline.md must-haves not currently covered (resume semantics, fail-forward, sync-rebase, integration-branch persistence).
- **MODIFIED**: `~/.local/share/overnight-sessions/active-session.json` schema — adds magic/pid/pgid/start_time/schema_version/session_dir/repo_path fields. Dashboard and statusline read fields already present today; new fields additive. Cleared only on `complete` transition; retained on `paused` (preserves paused-session visibility).
- **MODIFIED**: All path resolution moves out of bash (`$REPO_ROOT`, `$PYTHONPATH`, `$CORTEX_COMMAND_ROOT`) and into the Python CLI entry. Python modules receive paths as arguments rather than reading from env vars.
- **MODIFIED**: Signal handler idiom — from bash's synchronous trap to Python's flag+main-loop pattern. Handler body is minimal (set event, return); cleanup runs on the main thread at a safe point.
- **REMOVED**: `cortex_command/overnight/runner.sh` — deleted. 1,694 lines of bash + 50 inline Python snippets retired.
- **REMOVED**: `bin/overnight-start`, `bin/overnight-status` — deleted.
- **REMOVED**: `.runner.lock` (bare-PID, superseded by R8's `runner.pid`).
- **REMOVED**: `REPO_ROOT`, `PYTHONPATH`, `CORTEX_COMMAND_ROOT` env-var handoff between bash and inline Python.
- **REMOVED**: The 50 inline `python3 -c` snippets in `runner.sh` (migrated to Python functions in `runner.py` or peer modules).
- **REMOVED**: `cortex_version` field from the PID schema (earlier spec draft had dual versioning; resolved to single `schema_version` axis).

## Technical Constraints

- **Python version**: target Python 3.11+ (uses `datetime.fromisoformat` for RFC3339 parsing; `subprocess.Popen` `process_group` param; stdlib `signal.raise_signal`; context-manager-based `contextlib.contextmanager` for deferred_signals).
- **Dependencies**: prefer stdlib. `psutil` is acceptable for cross-platform process-start-time retrieval. No new heavy dependencies (no asyncio, no click, no typer — stay on argparse to match ticket 114's pattern).
- **Platform**: macOS + Linux. Windows is out of scope (`start_new_session=True` is POSIX; cortex-command does not ship Windows per `requirements/project.md`). PEP 475 syscall-restart semantics apply on both; main loop always checks `shutdown_event` between blocking calls.
- **Concurrency safety**: state-file writes are serialized by `state_lock` (R7 primitive); unlocked reads remain safe because forward-only transitions are idempotent (`requirements/pipeline.md:133-134`). The lock is a necessary addition for the bash→threading topology shift — bash's watchdog was a separate process communicating via tmpfile; in Python, watchdog and main share process memory, so writes need mutual exclusion.
- **Repair attempt cap**: single Sonnet → Opus escalation for merge conflicts; max 2 attempts for test failures. Permanent architectural constraint — rebuild preserves without change.
- **Integration branch persistence**: branches `overnight/{session_id}` persist after completion. Rebuild does not change.
- **Dashboard state-file schema compatibility**: `overnight-state.json` adds `schema_version` additively; all existing field names and nesting preserved. Dashboard remains unchanged.
- **Dispatch-template substitution contract** (`requirements/multi-agent.md:50`): dual-layer session-level `{token}` / per-feature `{{feature_X}}` preserved. `fill_prompt()` becomes a Python function but substitution semantics are byte-identical.
- **Pre-deploy no-active-runner check** (`requirements/multi-agent.md:51`): operator discipline convention. Rebuild commits to a single `runner.py` + prompt template pair — deploy both in one commit.
- **Hatchling build backend**: `pyproject.toml` `[tool.hatch.build.targets.wheel] packages = ["cortex_command"]` already captures everything under `cortex_command/`, including `overnight/prompts/*.md`. No additional `package-data` or `shared-data` config needed for editable install.
- **IPC contract evolution**: `schema_version` is the single version axis. Additive changes do not bump; breaking changes bump and ship a read-side compat policy. 115 ships `schema_version: 1`; 116 may extend the PID/state schemas additively (new optional fields) without a bump. The `cortex_version` axis was removed from the earlier draft to avoid dual-versioning incoherence.

## Open Decisions

None. All scope decisions resolved in research, Clarify, Spec-entry questions, and the critical-review revision pass.
