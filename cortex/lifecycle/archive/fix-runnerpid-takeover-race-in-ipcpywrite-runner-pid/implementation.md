# Implementation Log: fix-runnerpid-takeover-race-in-ipcpywrite-runner-pid

## Task 9: Backwards-compat unit test for pre-fix `runner.pid` files

**Test name**: `test_post_fix_detects_pre_fix_runner_pid`
(in `tests/test_runner_concurrent_start_race.py`)

**Expected outcome**: post-fix `_check_concurrent_start` invoked
against a synthesized pre-fix `runner.pid` (live payload, no sibling
`.runner.pid.takeover.lock`) returns `("session already running",
None)` AND `O_CREAT`s `.runner.pid.takeover.lock` on first acquire.

This is the post-Task 4 signature equivalent of the spec's pre-Task 4
"`ConcurrentRunnerError` is raised" wording — Task 4 (commit `49d21f8`)
restructured `_check_concurrent_start` to return `(error_message,
lock_fd)` with the live-runner collision reported via the tuple instead
of an exception. The on-disk-lockfile-creation assertion is unchanged.

**Actual pytest run result line**:

```
tests/test_runner_concurrent_start_race.py::test_post_fix_detects_pre_fix_runner_pid PASSED [100%]

============================== 1 passed in 0.28s ===============================
```

(Captured from `uv run pytest
tests/test_runner_concurrent_start_race.py::test_post_fix_detects_pre_fix_runner_pid
-x -v` on macOS, 2026-05-01.)

**Reverse-direction evidence** (pre-fix code reading post-fix on-disk
state — the lockfile is tautologically ignored because pre-fix source
does not reference it):

```
$ git show 7b913a4:cortex_command/overnight/ipc.py | grep -nE 'runner\.pid\.takeover\.lock'
ZERO MATCHES
```

Commit `7b913a4` is the last `cortex_command/overnight/ipc.py` revision
before `59e68c1` ("Add takeover-lock helper and lock_fd param to
write_runner_pid"), so it is the canonical pre-fix `ipc.py`. With zero
matches on the lockfile path, the pre-fix code path cannot interact
with the lockfile under any input — the source-level proof substitutes
for the previously-planned "deploy two installs side-by-side" rollback
verification (which is unrunnable under the project's non-editable
wheel distribution model).

## Task 8: One-shot 1000-iteration stress validation (macOS)

**Timestamp**: 2026-05-01T18:55:00Z

**Host**:

```
uname -srvm:  Darwin 25.4.0 Darwin Kernel Version 25.4.0: Thu Mar 19 19:31:17 PDT 2026; root:xnu-12377.101.15~1/RELEASE_ARM64_T6020 arm64
uv run python --version:  Python 3.13.8
```

**Command**:

```
uv run pytest tests/test_runner_concurrent_start_race.py::test_two_starters_with_stale_preexisting_lock --count=1000 -p no:cacheprovider
```

**Result**:

```
======================= 1000 passed in 81.18s (0:01:21) ========================
```

1000/1000 isolated runs passed. Pre-fix flake rate was ~20% (4 of 20
isolated runs failing), so a clean 1000/1000 is `0.8^1000 ≈ 1.2×10⁻⁹⁷`
under the null hypothesis of no fix — a strong signal that the race is
closed under the documented Thread A/B trace. Recurring detection
signal lives in Task 7's `--count=50` `just test` gate; this is the
deeper one-shot validation per spec R9.
