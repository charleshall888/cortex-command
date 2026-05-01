# Plan: fix-runnerpid-takeover-race-in-ipcpywrite-runner-pid

## Overview

Adopt `fcntl.flock` on a sibling `.runner.pid.takeover.lock` to serialize the read-verify-claim critical section across `_check_concurrent_start`, `write_runner_pid`, and `handle_cancel`. Re-verify under the held lock is the load-bearing CAS that closes the documented unlink-then-recreate TOCTOU. To close the residual race surface where a displaced owner's unlocked `clear_runner_pid` could clobber a new owner's just-written claim during a takeover transition, also make `clear_runner_pid` session-aware: it accepts the caller's expected `session_id` and only unlinks when the on-disk file's `session_id` matches. The `_exclusive_create_runner_pid` happy path and the `runner.pid` JSON IPC contract are unchanged.

## Tasks

### Task 1: Add `pytest-repeat` dev dependency

- **Files**: `pyproject.toml`
- **What**: Add `pytest-repeat>=0.9.3` to dev/test extras so `--count=N` is available to pytest. Hard precondition for Task 7 (`--count=50` recurring gate) and Task 8 (`--count=1000` one-shot validation); both fail with `unrecognized arguments: --count` until this lands.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Add the entry under `[project.optional-dependencies] dev` (or the equivalent dev/test extras section in `pyproject.toml`) in the same alphabetical/grouped position as adjacent test deps. After `uv sync` the import name is `pytest_repeat`.
- **Verification**: `grep -nE 'pytest-repeat' pyproject.toml` returns at least one match AND `uv run python -c "import pytest_repeat; print(pytest_repeat.__version__)"` exits 0.
- **Status**: [x] complete

### Task 2: Add `_acquire_takeover_lock` helper, `ConcurrentRunnerLockTimeoutError`, and `lock_fd` parameter on `write_runner_pid`

- **Files**: `cortex_command/overnight/ipc.py`
- **What**: (a) Add a new exception subclass `ConcurrentRunnerLockTimeoutError(ConcurrentRunnerError)` so the lock-timeout failure mode is distinguishable from the existing `ConcurrentRunnerError(existing_pid=-1)` "third party beat us on recreate path" signal. (b) Add a module-level `_acquire_takeover_lock(session_dir: Path) -> int` that opens `session_dir / ".runner.pid.takeover.lock"` with `O_RDWR | O_CREAT | 0o600`, then performs polling `fcntl.flock(fd, LOCK_EX | LOCK_NB)` with a 5-second total budget and 50 ms sleep cadence. On budget exhaustion, raise `ConcurrentRunnerLockTimeoutError(session_id="<unknown>", existing_pid=-1)` with the explicit timeout message. (c) Add `lock_fd: int | None = None` to `write_runner_pid`'s signature; when `lock_fd is None`, the function acquires its own takeover lock for the entire claim sequence (initial `O_EXCL` AND retry path) and releases it via `try: fcntl.flock(fd, LOCK_UN); finally: os.close(fd)` — the nested form so `os.close` runs unconditionally even if `LOCK_UN` raises (which would otherwise leak the FD until process exit). When `lock_fd is not None`, the function operates inside the caller's critical section and does NOT acquire its own lock. The retry path (currently `ipc.py:186–212`) MUST run under the held lock so the re-verify step is the CAS detecting any third-party live claim.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Existing `ConcurrentRunnerError` at `ipc.py:39–45` with signature `(session_id: str, existing_pid: int)`. Existing `write_runner_pid` at `ipc.py:140`. Existing `_exclusive_create_runner_pid` at `ipc.py:107`. Pattern references: `cortex_command/init/settings_merge.py:_acquire_lock` (sibling-lockfile rationale — lockfile inode survives `os.replace()` of the target) and `plugins/cortex-overnight-integration/server.py:_acquire_update_flock` (polling-with-budget shape — closer template; `settings_merge.py`'s blocking `LOCK_EX` is NOT acceptable here because PEP 475 EINTR retry would block SIGTERM indefinitely). The lockfile is never written, never unlinked by production code, never `durable_fsync`'d. Timeout message must contain the literal substring `takeover lock acquire timed out after 5s; another starter holds .runner.pid.takeover.lock`. Release pattern (used in this task and propagated to Tasks 4 and 5):
  ```
  fd = _acquire_takeover_lock(...)
  try:
      ...work...
  finally:
      try:
          fcntl.flock(fd, fcntl.LOCK_UN)
      finally:
          os.close(fd)
  ```
- **Verification**: `grep -nE 'def _acquire_takeover_lock' cortex_command/overnight/ipc.py` returns exactly one match AND `grep -nE 'class ConcurrentRunnerLockTimeoutError\b' cortex_command/overnight/ipc.py` returns exactly one match AND `grep -nE 'fcntl\.flock\(.*LOCK_EX *\| *LOCK_NB' cortex_command/overnight/ipc.py` returns exactly one match AND `grep -nE 'takeover lock acquire timed out' cortex_command/overnight/ipc.py` returns at least one match AND `grep -E 'lock_fd: int \| None = None' cortex_command/overnight/ipc.py` returns at least one match AND `grep -nE 'write|unlink|fsync|f_fullfsync' cortex_command/overnight/ipc.py | grep -i 'takeover\.lock'` returns zero matches.
- **Status**: [x] complete

### Task 3: Make `clear_runner_pid` session-aware (CAS); thread `expected_session_id` through every caller

- **Files**: `cortex_command/overnight/ipc.py`, `cortex_command/overnight/runner.py`, `cortex_command/overnight/cli_handler.py`
- **What**: (a) Modify `clear_runner_pid` (`ipc.py:215`) to accept `expected_session_id: str | None = None`. Behavior: when `expected_session_id is None`, current unconditional unlink behavior is preserved (used by lock-covered call sites that have already verified ownership under lock). When `expected_session_id` is provided, read the on-disk `runner.pid` first and only unlink if the JSON's `session_id` field equals the caller's `expected_session_id`; otherwise no-op silently. This compare-and-swap closes the residual race where a displaced owner's unlocked clear unlinks the new owner's just-written claim during a takeover transition. (b) Update every `clear_runner_pid` call site to pass the caller's `session_id`:
  - `runner.py:540` (`_cleanup`) — pass the running session's `session_id`
  - `runner.py:581` (inside `_check_concurrent_start`, lock-covered) — may stay session-unaware (lock provides serialization) or may pass session_id for defense-in-depth; either is acceptable; choose session_id for consistency
  - `runner.py:1536` (clean-exit) — pass the running session's `session_id`
  - `cli_handler.py:434` (post-stale-verify self-heal) — pass the stale `pid_data["session_id"]` we just verified-stale; if a takeover wrote a new claim between verify and clear, our CAS rejects and no-ops
  - `cli_handler.py:456` (post-`ProcessLookupError` self-heal) — pass the verified `pid_data["session_id"]`
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Existing `clear_runner_pid` at `ipc.py:215–217` is an unconditional unlink with `FileNotFoundError` rescue. Adding the CAS path requires a `read_runner_pid` call before unlink; the existing `read_runner_pid` at `ipc.py:220` already returns `None` on missing/corrupt — match that semantics by no-op'ing when read returns `None` or session_id mismatches. The signature stays backwards-compatible: `clear_runner_pid(session_dir: Path, expected_session_id: str | None = None) -> None`. Caller-site search confirmed sites enumerated above; no other callers exist in production code (`grep -rn "clear_runner_pid" cortex_command/ tests/` is the way to confirm before editing).
- **Verification**: `grep -nE 'def clear_runner_pid' cortex_command/overnight/ipc.py` returns exactly one match AND `grep -E 'expected_session_id' cortex_command/overnight/ipc.py` returns at least two matches (signature + body) AND `grep -nE 'clear_runner_pid\(session_dir, expected_session_id=' cortex_command/overnight/runner.py cortex_command/overnight/cli_handler.py` returns at least four matches (covering 540, 1536, 434, 456) AND `uv run pytest tests/test_runner_concurrent_start_race.py -x` exits 0 AND `uv run pytest tests/test_ipc_verify_runner_pid.py -x` exits 0 (regression coverage).
- **Status**: [x] complete

### Task 4: Wire takeover lock through `_check_concurrent_start`

- **Files**: `cortex_command/overnight/runner.py`
- **What**: `_check_concurrent_start` (currently `runner.py:570`) acquires `ipc._acquire_takeover_lock(session_dir)` before its read-verify-clear sequence, performs the read of `runner.pid` + verify-stale + `clear_runner_pid` calls inside the held lock, and propagates the FD into the subsequent `write_runner_pid` call (Task 2's `lock_fd` parameter) so the entire critical section runs under one lock. Release via the nested `try: LOCK_UN ... finally: os.close(fd)` pattern from Task 2 (close must run unconditionally). The `write_runner_pid` invocation at `runner.py:630` must be passed `lock_fd=lock_fd`.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: Existing `_check_concurrent_start` at `runner.py:570`. The `write_runner_pid` call site at `runner.py:630` is wrapped in `with deferred_signals(coord)` (line 629); the lock acquire and release must live inside that `with` block so SIGTERM during the polling loop is stashed and replayed on exit. PEP 475 means `time.sleep(0.05)` retries to completion across signals — the 50 ms cadence (not EINTR) is what bounds signal-response latency. With Task 3 in place, the `clear_runner_pid` call inside `_check_concurrent_start` (line 581) passes `expected_session_id` either as defense-in-depth or as `None` (the caller is already lock-covered).
- **Verification**: `grep -nE '_acquire_takeover_lock' cortex_command/overnight/runner.py` returns at least one match AND `grep -nE 'lock_fd=lock_fd|lock_fd=' cortex_command/overnight/runner.py` returns at least one match AND `uv run pytest tests/test_runner_concurrent_start_race.py -x` exits 0.
- **Status**: [x] complete

### Task 5: Add `--force` to cancel CLI; wire takeover lock through `handle_cancel` non-force path; map JSON error code

- **Files**: `cortex_command/cli.py`, `cortex_command/overnight/cli_handler.py`
- **What**: (a) Add `cancel.add_argument("--force", action="store_true", default=False, help="Skip the 5s takeover-lock acquire (escape hatch for wedged-holder scenarios; accepts <100ms 'no active session' race window during a concurrent takeover).")` to the `overnight cancel` parser at `cli.py:382–406` so `args.force` exists at runtime. `--force` does not change session-id resolution — positional `session_id` → `--session-dir` → active-session pointer fallback is unchanged; `--force` only skips the lock acquire. (b) In `handle_cancel` (`cli_handler.py:378`), acquire `ipc._acquire_takeover_lock(session_dir)` before reading `runner.pid` and hold through the verify-and-act sequence (verify magic + start_time, decide live-vs-stale, send `os.killpg(SIGTERM)` for live or call `clear_runner_pid` for stale). Release via the nested `try: LOCK_UN ... finally: os.close(fd)` pattern. The `--force` path explicitly SKIPS the lock acquire via an explicit conditional `lock_fd = None if args.force else _acquire_takeover_lock(session_dir)`. (c) Map `ConcurrentRunnerLockTimeoutError` (Task 2) to a distinct JSON error code in the `--format json` output: success path unchanged; lock-timeout failure emits `{"version":"1.0","error":"lock_timeout","message":"<full timeout message from Task 2>"}`. The pre-existing `concurrent_runner_alive` error code path for live-runner detection is unchanged.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: `handle_cancel` exists at `cli_handler.py:378`. `args.force` does NOT currently exist on the cancel parser — Task 5 adds it. The two `clear_runner_pid` call sites in `handle_cancel` (`cli_handler.py:434, 456`) are updated by Task 3 to pass `expected_session_id`; this task only wraps the surrounding region with the lock for the non-force path. Pre-flight unlocked read at `cli_handler.py:178` (inside `handle_start`) is intentionally NOT modified — pre-flight is advisory; the authoritative serialization lives in Task 4's lock-covered `_check_concurrent_start`. `install_guard.py:74–104` runs a separate argparse instance that pre-parses argv to detect the `cancel ... --force` invocation form before `cli.py` imports — it is intentionally independent. After Task 5 lands, verify `install_guard.py`'s shadow parser still recognizes `--force` (it was authored with `cancel.add_argument("--force", action="store_true", default=False)` at `install_guard.py:88`; the canonical parser change here matches that shape, so no install_guard edit is required, but the parity should be confirmed).
- **Verification**: `grep -B5 'add_argument.*"--force"' cortex_command/cli.py | grep -E 'cancel = overnight_sub.add_parser'` returns at least one match (confirms the new `--force` is in the cancel parser block, not elsewhere) AND `grep -nE '_acquire_takeover_lock' cortex_command/overnight/cli_handler.py` returns at least one match AND `grep -nE 'args\.force' cortex_command/overnight/cli_handler.py` returns at least one match AND `grep -nE '"lock_timeout"' cortex_command/overnight/cli_handler.py` returns at least one match AND `grep -nE 'add_argument\("--force"' cortex_command/install_guard.py` returns at least one match (confirms the shadow parser still has its `--force` definition, no inadvertent regression).
- **Status**: [x] complete

### Task 6: Replace `pid=0` stale fixture with portable spawn-and-kill

- **Files**: `tests/test_runner_concurrent_start_race.py`
- **What**: Replace the `pid: 0` payload in `_stale_pid_payload` (currently around `tests/test_runner_concurrent_start_race.py:64–80`) and update the misleading comment at line 187 ("pid=0 is guaranteed dead per psutil") with a fixture that obtains a guaranteed-never-existed PID by: (a) spawning a short-lived subprocess via `subprocess.Popen([sys.executable, "-c", "pass"])`, (b) capturing its PID, (c) calling `proc.wait()` to ensure the kernel reaps it, (d) immediately asserting `psutil.Process(pid)` raises `psutil.NoSuchProcess` to defend against PID recycle on busy hosts. On assertion failure (PID was already recycled to a live process), retry up to 3 times before failing the test with a clear test-side message. Stale `start_time` payload value: `"1970-01-01T00:00:00+00:00"` (definitionally outside the ±2 s tolerance window).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing `_stale_pid_payload` helper at `tests/test_runner_concurrent_start_race.py:64`. Existing misleading comment at line 187 inside `test_two_starters_with_stale_preexisting_lock`. The fixture must work identically on macOS and Linux without conditional branches. `subprocess`, `sys`, and `psutil` are already imported in this test module — confirm by reading the top of the file before editing.
- **Verification**: `grep -nE '"pid": 0|pid=0' tests/test_runner_concurrent_start_race.py` returns zero matches AND `grep -nE 'NoSuchProcess' tests/test_runner_concurrent_start_race.py` returns at least one match AND `uv run pytest tests/test_runner_concurrent_start_race.py -x` exits 0.
- **Status**: [x] complete

### Task 7: Remove `xfail`; wire `--count=50` recurring gate into `just test`

- **Files**: `tests/test_runner_concurrent_start_race.py`, `justfile`
- **What**: (a) Remove the `@pytest.mark.xfail(...)` decorator block from `test_two_starters_with_stale_preexisting_lock` (currently `tests/test_runner_concurrent_start_race.py:155–158`); the test must pass deterministically post-fix. (b) Update the `test` recipe in `justfile` so the takeover test runs with `--count=50 -p no:cacheprovider` — either inline as a separate pytest invocation in the recipe, or via a `stress` marker. At a 20% per-run failure rate (the pre-fix baseline), `--count=50` drives the false-pass rate to `0.8^50 ≈ 1.4×10⁻⁵` — strong recurring signal at ~5–10 s incremental runtime.
- **Depends on**: [1, 2, 3, 4, 6]
- **Complexity**: simple
- **Context**: Decorator location is the function-scoped block immediately above `def test_two_starters_with_stale_preexisting_lock` (lines 155–158). `justfile` `test` recipe currently runs `uv run pytest`; the `--count=50` invocation can be a second pytest line in the same recipe targeting the takeover test specifically, or a `pytest -m stress` if a `stress` marker is added to the test file. Either approach satisfies the spec; keep the rest of the suite at default count to avoid blowing up overall runtime. Task 5 is intentionally NOT a dependency — the takeover test exercises start (`_check_concurrent_start`), not cancel.
- **Verification**: `grep -nE '@pytest\.mark\.xfail' -A1 tests/test_runner_concurrent_start_race.py | grep -E 'test_two_starters_with_stale_preexisting_lock'` returns zero matches AND `grep -nE 'count=50|--count 50' justfile` returns at least one match AND `uv run just test` exits 0.
- **Status**: [x] complete

### Task 8: One-shot 1000-iteration stress validation (macOS only)

- **Files**: `lifecycle/fix-runnerpid-takeover-race-in-ipcpywrite-runner-pid/implementation.md`
- **What**: Run `uv run pytest tests/test_runner_concurrent_start_race.py::test_two_starters_with_stale_preexisting_lock --count=1000 -p no:cacheprovider` once on macOS. The run must pass (1000/1000). Append entries to `implementation.md` recording: (a) `uname -srvm` output verbatim, (b) `python --version`, (c) the literal `1000 passed in Xs` summary line from the pytest output, (d) ISO 8601 timestamp. Linux validation is dropped from this task — the system does not currently run pytest on Linux in CI (`.github/workflows/validate.yml` only runs skill validation and callgraph guard) and the implementer typically lacks Linux host access; if Linux pytest CI is added later (separate ticket), the stress gate gains Linux coverage automatically through Task 7's `--count=50` invocation.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: This is the deeper one-shot validation; the recurring detection signal lives in Task 7's `--count=50` `just test` gate. macOS is the implementer's primary host (per `requirements/remote-access.md:41`) and the host the original ~20% flake was characterized on, so the 1000-iteration run on macOS is the highest-value single validation.
- **Verification**: Interactive/session-dependent: the 1000-iteration run is a manual implementer-driven validation; the implementation.md log entry is the audit trail (per the spec's R9 acceptance which classifies the gate as session-dependent). Programmatic verification of the recurring signal is enforced by Task 7's `uv run just test` gate.
- **Status**: [x] complete

### Task 9: Backwards-compat unit test for pre-fix `runner.pid` files

- **Files**: `tests/test_runner_concurrent_start_race.py`, `lifecycle/fix-runnerpid-takeover-race-in-ipcpywrite-runner-pid/implementation.md`
- **What**: Add a unit test `test_post_fix_detects_pre_fix_runner_pid` that synthesizes the pre-fix on-disk state and verifies post-fix code handles it correctly. The test (a) writes a `runner.pid` file with the pre-fix payload format (no `.runner.pid.takeover.lock` exists in the session dir — pre-fix code never created one), (b) populates the payload with the current process's `os.getpid()` and `psutil.Process().create_time()` so verify_runner_pid returns True, (c) invokes post-fix `_check_concurrent_start` against that session_dir, (d) asserts `ConcurrentRunnerError` is raised AND the new `.runner.pid.takeover.lock` file is created (post-fix `_acquire_takeover_lock` `O_CREAT`s it on first acquire). Reverse direction (pre-fix code reading post-fix state): pre-fix code does not reference `.runner.pid.takeover.lock` in source, so it is tautologically ignored; verify by `grep -nE 'runner\.pid\.takeover\.lock' $(git show HEAD~1:cortex_command/overnight/ipc.py)` returning zero matches (or equivalent — see Context). Append to `implementation.md` the test name, the expected outcome, and the actual pytest run result line. This task replaces the previously-planned "deploy two installs side-by-side" approach (which is unrunnable under the project's non-editable wheel distribution model) with a unit test that produces the same backwards-compat evidence in a single test invocation.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Pre-fix payload format is unchanged from the spec's R10 description (JSON with `schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path`). The test fixture creates a tmp_path session_dir, writes the synthesized pre-fix `runner.pid` directly via `(session_dir / "runner.pid").write_text(json.dumps(payload))` (NOT via the new `write_runner_pid` which would acquire the lock and `O_CREAT` the lockfile prematurely), and confirms post-fix code does the right thing on first encounter. The reverse-direction grep substitutes for the previously-planned "rollback to pre-fix while new-fix runner is alive" deploy verification — the source-level proof (pre-fix source doesn't reference the lockfile) is sufficient and runs in a single command.
- **Verification**: `grep -nE 'def test_post_fix_detects_pre_fix_runner_pid' tests/test_runner_concurrent_start_race.py` returns exactly one match AND `uv run pytest tests/test_runner_concurrent_start_race.py::test_post_fix_detects_pre_fix_runner_pid -x` exits 0.
- **Status**: [x] complete

### Task 10: Document `.runner.pid.takeover.lock` in `docs/overnight-operations.md`

- **Files**: `docs/overnight-operations.md`
- **What**: Add a section adjacent to the existing `.runner.lock` documentation (currently `docs/overnight-operations.md:212`) that (a) names the takeover lockfile path `{session_dir}/.runner.pid.takeover.lock`, (b) states its purpose (serializing the read-verify-claim critical section across `_check_concurrent_start`, `write_runner_pid`, and `handle_cancel` non-force path), (c) states the discipline obligations on every future glob caller (production code other than `ipc.py:_acquire_takeover_lock` must NOT write to, unlink, `durable_fsync`, or include this lockfile in any `*.lock` glob auto-cleanup — the static gate at Task 11 enforces this), (d) notes that the file persists indefinitely under current archival policy. The existing `.runner.lock` documentation at line 212 is doc-rot from the retired `runner.sh` (per `requirements/pipeline.md:28`); correct or remove the stale reference in the same edit.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Existing doc location at `docs/overnight-operations.md:212`. The discipline rules describe an obligation each future code site must honor (a passive doc paragraph cannot prevent a `*.lock` glob from matching the lockfile — only the glob caller's exclusion logic can); the rule's framing in this doc is "every production module other than `ipc.py` MUST NOT do X to this path", and Task 11 is the gate that enforces it. Audit at `cortex_command/overnight/daytime_pipeline.py:152` shows the existing `*.lock` rglob targets per-feature `worktree_path`, not session_dir, so the two paths do not currently overlap.
- **Verification**: `grep -nE 'runner\.pid\.takeover\.lock' docs/overnight-operations.md` returns at least one match AND `grep -cE 'never written|never unlinked|never durable_fsync|never.*\*\.lock' docs/overnight-operations.md` returns at least 3 (one per discipline obligation).
- **Status**: [x] complete

### Task 11: Static gate test for `.runner.pid.takeover.lock` discipline

- **Files**: `tests/test_takeover_lock_discipline.py`
- **What**: Add a new pytest test module that statically asserts the lockfile discipline. The test (a) walks all `.py` files under `cortex_command/`, (b) finds any string literal containing the substring `"runner.pid.takeover.lock"` (use `pathlib` walk + line-level scan; no need for full AST), (c) asserts every match's containing file is `cortex_command/overnight/ipc.py` — any other file mentioning the path fails the test with the violating file path. This is the project's enforcement convention (per `requirements/project.md:27`, "drift between deployed scripts and references is a pre-commit-blocking failure mode"; per `bin/cortex-check-parity` precedent for static gates on load-bearing invariants). The gate catches regressions at `just test` time (which runs in pre-commit hook contexts), not at runtime where a misuse might silently corrupt state.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Pattern reference: `tests/test_check_parity.py` (existing static gate for SKILL.md-to-bin parity). Implementation shape: walk `cortex_command/` recursively, read each `.py` file, scan lines for the literal substring `runner.pid.takeover.lock`, collect violations; assert empty violations list with a clear message naming each violating file:line. The test is fast (<1s) and runs as part of the default `just test` gate via the existing pytest collection.
- **Verification**: `grep -nE 'def test_takeover_lock_discipline' tests/test_takeover_lock_discipline.py` returns at least one match AND `uv run pytest tests/test_takeover_lock_discipline.py -x` exits 0 (passes when only `cortex_command/overnight/ipc.py` references the path) AND introducing a synthetic violation (e.g., temporarily adding the substring to `cortex_command/overnight/runner.py`) causes the test to fail with a violation-naming message — restore the file before committing.
- **Status**: [x] complete

## Verification Strategy

Post-implementation end-to-end verification (in order):

1. `uv run just test` exits 0 — exercises the full suite including the de-xfailed takeover test under `--count=50` (Task 7), the backwards-compat unit test (Task 9), and the static discipline gate (Task 11).
2. `uv run pytest tests/test_runner_concurrent_start_race.py::test_two_starters_with_stale_preexisting_lock --count=1000 -p no:cacheprovider` exits 0 on macOS (Task 8 one-shot stress gate; manual).
3. `verify_runner_pid` contract is unchanged — no regression in `tests/test_ipc_verify_runner_pid.py` and `tests/test_cortex_overnight_security.py:123–182`.
4. The MCP control plane and pre-install in-flight guard (`install_guard.py:209`) continue to work unchanged — no schema bump, no payload format change.

## Veto Surface

- **V1 (`ConcurrentRunnerLockTimeoutError` is a public-API addition)**: Task 2 introduces a new exception subclass that downstream MCP consumers may want to catch separately from `ConcurrentRunnerError`. The plan exposes it via the existing `ipc` module without explicit changelog or schema-version handling. If MCP consumers depend on catching all `ConcurrentRunnerError` instances generically (which subclassing supports — the new class IS-A `ConcurrentRunnerError`), this is transparent. If consumers `isinstance`-check, they get the new discrimination. The choice to subclass rather than introduce a separate exception type is a long-term-cleanliness call; revisit if downstream callers need different semantics.

- **V2 (Session-aware `clear_runner_pid` is a behavior change)**: Task 3 changes `clear_runner_pid` from "always unlink" to "unlink only when `expected_session_id` matches" when the new parameter is provided. Callers that pass `None` (or omit the new param) get unchanged behavior. The lock-covered path inside `_check_concurrent_start` (line 581) doesn't strictly need the CAS (the lock already serializes), but threading session_id through for consistency is the long-term cleaner posture. If any future caller is added without considering the session-id semantics, the default `None` path is the unconditional unlink — which is the legacy behavior and safe under lock-covered call sites.

- **V3 (`--count=50` runtime impact)**: Task 7 adds `--count=50` for the takeover test in `just test`. At ~5–10 s incremental runtime per `just test` run, frequent local invocations pay this cost cumulatively. If developer pre-push runtime becomes a problem, an alternative is to gate the stress run behind a `just test-stress` recipe and remove it from the default `test` recipe.

- **V4 (Lockfile inode accumulation)**: `.runner.pid.takeover.lock` is `O_CREAT`ed per session_dir and never unlinked by production code; under current archival policy session directories accumulate indefinitely (45+ on the maintainer's tree at writing). The file is ~0 bytes; inode count grows linearly with session count. Worth surfacing if session_dir count crosses an inode-pressure threshold.

## Scope Boundaries

Per the spec's Non-Requirements section, this ticket explicitly does NOT:

- Switch all `runner.pid` access to `fcntl.flock`. `_exclusive_create_runner_pid` (single-shot create), `read_runner_pid`, and `verify_runner_pid` retain their current primitives. The locking happens in `_check_concurrent_start`, `write_runner_pid`, and `handle_cancel` only; `clear_runner_pid` is closed via session-id CAS rather than lock acquisition (avoids 5s blocking in shutdown paths).
- Acquire the takeover lock for read-only verifies. `install_guard.py:201` (direct `read_text`) and `install_guard.py:209` (`verify_runner_pid` call) do NOT acquire the lock. **Note**: post-fix the file-absent window during a takeover changes shape — pre-fix the unlink-then-recreate window inside `write_runner_pid` was tightly synchronous; post-fix the file-absent window now spans flock-acquire → unlink → `_exclusive_create_runner_pid` (`durable_fsync` inclusive). install_guard's existing `read_text → OSError → None` handler tolerates either window-shape, so observable behavior is unchanged, but if install_guard's handling is ever tightened, the wider window must be re-evaluated. Closing install_guard's transient "stale-active-session" warning is a separate backlog item.
- Modify `cli_handler.py:178` (the JSON-mode collision pre-flight read in `handle_start`). Pre-flight is advisory; the authoritative check inside `_check_concurrent_start` (Task 4, lock-covered) produces the correct verdict.
- Add cross-platform test harness infrastructure beyond the portable stale-PID fixture in Task 6.
- Add NFS / SMB / non-local-FS support. The fix assumes `lifecycle/sessions/` is on a local filesystem.
- Bump `_SCHEMA_VERSION`. The `runner.pid` payload format is unchanged; the lockfile is a sibling artifact, not part of the IPC contract. `ConcurrentRunnerLockTimeoutError` is a Python-API addition, not a wire-format change.
- Add a lockfile cleanup helper. The lockfile is `O_CREAT`ed once per session and persists for the lifetime of the session directory.
- Add Linux pytest to `.github/workflows/validate.yml`. The recurring detection signal is local-only (developers run `just test` before pushing). Task 8 drops the previously-planned Linux 1000-iteration validation because the system does not currently run pytest on Linux in CI; if a Linux pytest CI job is added later (separate ticket), the stress gate gains Linux coverage automatically through Task 7's `--count=50` invocation in that CI job.
- Modify `install_guard.py:74-104`'s shadow argparse instance for `--force` detection. The shadow parser was authored with `cancel.add_argument("--force", action="store_true", default=False)` at `install_guard.py:88`; the canonical parser change in Task 5 matches that shape, so no install_guard edit is required. Task 5's verification grep confirms the shadow parser still has its `--force` definition as a regression check.
