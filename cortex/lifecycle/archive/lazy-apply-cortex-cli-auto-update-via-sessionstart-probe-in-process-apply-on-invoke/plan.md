# Plan: lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke

## Overview

Add an inline check-and-apply auto-update gate to `cortex_command/cli.py::main()` that runs before subcommand dispatch. Five new module-level helpers (`_append_error_log`, `_should_skip_auto_update`, `_run_verification_probe`, `_check_and_apply_update`) plus a `--no-update-check` top-level argparse hook compose the gate; existing `_dispatch_upgrade()` (`cli.py:85-119`) is reused as the apply path. Tests in a new `tests/test_cli_auto_update.py` cover the named acceptance cases plus a grep-as-test guard. Implementation tasks all touch `cli.py` and chain sequentially; test tasks all touch the new test file and chain sequentially; the docs task is independent. The orchestrator `_check_and_apply_update` is split into 5a (skip/probe path) and 5b (lock/apply/exit path) to keep each task within sizing bounds.

## Tasks

### Task 1: Add `--no-update-check` top-level flag + `CORTEX_NO_UPDATE_CHECK` env wiring

- **Files**: `cortex_command/cli.py`
- **What**: Register a top-level `--no-update-check` flag on the root parser (sibling to `--help`), parsed before subparsers. The flag and `CORTEX_NO_UPDATE_CHECK=1` env var are read by the skip predicate in Task 3 to opt out of the gate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_build_parser()` lives at `cli.py:122-323`. Add `parser.add_argument("--no-update-check", action="store_true", default=False, help="Skip the inline auto-update gate for this invocation")` immediately after the `parser = argparse.ArgumentParser(...)` block (before `subparsers = parser.add_subparsers(...)` at `cli.py:130`). The flag attaches to `args.no_update_check` after `parser.parse_args()` in `main()`. The env var is consumed in Task 3 — this task only adds the flag.
- **Verification**: `python -c "from cortex_command.cli import _build_parser; ns = _build_parser().parse_args(['--no-update-check', 'overnight', 'status']); assert ns.no_update_check is True; print('ok')"` exits 0 and prints `ok` — pass if exit 0.
- **Status**: [ ] pending

### Task 2: Implement `_append_error_log()` NDJSON stage-logging helper

- **Files**: `cortex_command/cli.py`
- **What**: Add a module-level helper that appends one NDJSON line per error to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log`, with per-write `fcntl.flock(LOCK_EX)`, message truncation to 256 chars, the closed-enum stage list, and the 24-hour mtime-based dedup logic for `no_origin` and `not_a_git_repo` stages. Schema as specified in spec Technical Constraints.
- **Depends on**: none
- **Complexity**: simple
- **Context**: New module-level function `_append_error_log(stage: str, message: str, *, cortex_root: str | None = None, remote_url: str | None = None, local_sha: str | None = None, remote_sha: str | None = None) -> None`. Uses stdlib `fcntl`, `json`, `pathlib`, `os`, `datetime`. Stage enum (closed) — values: `ls_remote`, `ls_remote_timeout`, `lock`, `lock_contention_timeout`, `apply`, `verification`, `verification_timeout`, `half_applied`, `no_origin`, `not_a_git_repo`. Atomicity contract: each append takes `fcntl.flock(LOCK_EX)` on the log fd for the duration of one `os.write` syscall; fd opened with `O_WRONLY | O_APPEND | O_CREAT` (full mechanism in spec Technical Constraints). Log dir created via `pathlib.Path(parent).mkdir(parents=True, exist_ok=True)` before open. Dedup helper: read-only scan from EOF for last newline, parse trailing line as JSON, compare `stage` and timestamp; suppress when prior entry of same stage is within 24 hours (only for stages `no_origin` and `not_a_git_repo`). NDJSON schema (per spec Technical Constraints): `{ts, stage, message, cortex_root, remote_url, local_sha, remote_sha}`. Pattern reference: no precedent in repo for per-write flock — implementer follows spec Technical Constraints literally.
- **Verification**: `python -c "from cortex_command.cli import _append_error_log; _append_error_log('ls_remote', 'test'); print('ok')"` exits 0 — pass if exit 0 and the function imports without error. (Behavior verified by tests in Task 13.)
- **Status**: [ ] pending

### Task 3: Implement `_should_skip_auto_update()` skip-predicate helper

- **Files**: `cortex_command/cli.py`
- **What**: Add a module-level helper that returns a tuple `(skip: bool, reason: str | None)` indicating whether to skip the auto-update gate. Encodes all of req 4 (env vars + dirty tree + non-main branch), req 5 (bare-help/version/no-args paths), and req 6 (`--no-update-check` flag and `CORTEX_NO_UPDATE_CHECK` env var). Prints stderr note `auto-update skipped: <reason> (set CORTEX_DEV_MODE=1 to silence)` for dirty-tree and non-main-branch reasons only.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: New module-level function `_should_skip_auto_update(args: argparse.Namespace, *, argv: list[str], cortex_root: str) -> tuple[bool, str | None]`. Skip predicates and their full contracts are defined in spec req 4 (env vars: `CORTEX_DEV_MODE`, `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`; git-state: dirty tree, non-main branch), req 5 (bare argv shapes: `["--help"]`, `["-h"]`, `["--version"]`, `[]`), req 6 (`args.no_update_check` and `CORTEX_NO_UPDATE_CHECK`). Stderr emission only for dirty-tree and non-main-branch reasons (the literal stderr strings are quoted in spec acceptance A4.c and A4.d); env-var skips are silent. Git-state predicates use `subprocess.run` with `cwd=cortex_root` and `check=False`, matching `_dispatch_upgrade()`'s subprocess style at `cli.py:91-98`. Returns `(True, "<reason>")` on first matched skip with the matching reason string keyed by the spec acceptance text, or `(False, None)` if no predicate matches.
- **Verification**: `python -c "import argparse, os; os.environ.pop('CORTEX_DEV_MODE', None); os.environ.pop('CLAUDECODE', None); os.environ.pop('CLAUDE_CODE_ENTRYPOINT', None); os.environ.pop('CORTEX_NO_UPDATE_CHECK', None); from cortex_command.cli import _should_skip_auto_update; ns_a = argparse.Namespace(no_update_check=True); skip_a, _ = _should_skip_auto_update(ns_a, argv=['overnight', 'status'], cortex_root='/nonexistent'); assert skip_a is True; ns_b = argparse.Namespace(no_update_check=False); os.environ['CORTEX_DEV_MODE'] = '1'; skip_b, _ = _should_skip_auto_update(ns_b, argv=['overnight', 'status'], cortex_root='/nonexistent'); assert skip_b is True; print('ok')"` exits 0 and prints `ok` — pass if exit 0. (Verifies both flag-driven and env-driven skip branches; behavioral coverage of the remaining branches comes from Task 8.)
- **Status**: [ ] pending

### Task 4: Implement `_run_verification_probe()` helper

- **Files**: `cortex_command/cli.py`
- **What**: Add a module-level helper that runs the post-upgrade `cortex --help` probe to detect half-applied state. Returns the subprocess exit code, or a non-zero sentinel on timeout (`124`, conventional shell-timeout code) for the caller to interpret as `verification_timeout`. Per spec req 11 + Technical Constraints (10s budget). On timeout, calls `_append_error_log("verification_timeout", ...)`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: New module-level function `_run_verification_probe(cortex_root: str) -> int`. Spec req 11 specifies the subprocess shape (`subprocess.run([sys.argv[0], "--help"], capture_output=True, timeout=10)`). Pattern reference: `_dispatch_upgrade()` at `cli.py:85-119` for subprocess + error-handling style.
- **Verification**: `python -c "from cortex_command.cli import _run_verification_probe; print('ok')"` exits 0 and prints `ok` — pass if exit 0. (Behavior verified by tests in Task 14.)
- **Status**: [ ] pending

### Task 5a: Implement `_check_and_apply_update()` skeleton — skip/discovery/probe path

- **Files**: `cortex_command/cli.py`
- **What**: Add the gate function with the no-apply portion of the flow: skip-predicate dispatch, `.git/` existence guard, `git remote get-url origin` sourcing (with `no_origin` dedup logging), `git ls-remote main` with 1s Python-side timeout (logging `ls_remote_timeout` / `ls_remote` on failures), local HEAD parsing, and same-SHA early return. No lock acquisition, no apply, no exit-with-message yet — those land in Task 5b. Expose `_LOCK_TIMEOUT_SECONDS = 30` as a module-level constant AND read the effective timeout via env-var override at call time (see Context).
- **Depends on**: [3, 4]
- **Complexity**: complex
- **Context**: New module-level function signature: `_check_and_apply_update(args: argparse.Namespace, *, argv: list[str]) -> None`. New module-level constant `_LOCK_TIMEOUT_SECONDS: int = 30`. **Effective lock-timeout read at call time** — the gate computes its lock-acquisition budget as `int(os.environ.get("_CORTEX_LOCK_TIMEOUT_OVERRIDE", str(_LOCK_TIMEOUT_SECONDS)))`. The override is private (underscore prefix) and exists solely to let `multiprocessing.Process` children in concurrency tests inherit a shorter timeout via env-var propagation; production callers never set it. This pattern is required because `monkeypatch.setattr` on a module attribute does NOT propagate to spawn-method `multiprocessing.Process` children on macOS — env vars do. Spec req 1, 2, 3 specify the network-probe shape; spec req 9 + Technical Constraints specify error-log routing; spec Edge Cases specify the "not a git repo → silent skip, no log" rule. `cortex_root` discovery: `os.environ.get("CORTEX_COMMAND_ROOT") or str(Path.home() / ".cortex")` — matching `_dispatch_upgrade()`'s convention at `cli.py:90`. Helpers from Tasks 2-4 are imported from the same module. After this task, the gate runs end-to-end for the no-update case and for all error cases that don't reach apply; same-SHA returns silently.
- **Verification**: `python -c "import os; os.environ['_CORTEX_LOCK_TIMEOUT_OVERRIDE'] = '7'; from cortex_command.cli import _check_and_apply_update, _LOCK_TIMEOUT_SECONDS; assert _LOCK_TIMEOUT_SECONDS == 30; effective = int(os.environ.get('_CORTEX_LOCK_TIMEOUT_OVERRIDE', str(_LOCK_TIMEOUT_SECONDS))); assert effective == 7; print('ok')"` exits 0 and prints `ok` — pass if exit 0. (Asserts both the default constant and the env-var override mechanism are in place.)
- **Status**: [ ] pending

### Task 5b: Add lock + apply + verification + exit-with-rerun to `_check_and_apply_update()`

- **Files**: `cortex_command/cli.py`
- **What**: Extend the gate from Task 5a with the apply path: blocking flock on `$cortex_root/.git/cortex-update.lock` with the env-var-aware effective lock-timeout (logging `lock_contention_timeout` on timeout), `_dispatch_upgrade(args)` call (logging `apply` on non-zero return), `_run_verification_probe(cortex_root)` call (logging `half_applied` and `sys.exit(1)` on non-zero return), post-pull `git rev-parse HEAD` for the user-facing SHA, a context-aware success message (per-subcommand customization — see Context), and `sys.exit(0)`.
- **Depends on**: [5a]
- **Complexity**: complex
- **Context**: Spec req 7 specifies the lock contract; req 8 specifies the C3 message format and post-pull SHA sourcing; req 10 specifies dispatch-reuse (call `_dispatch_upgrade()` — do NOT duplicate git-pull / uv-tool-install logic from `cli.py:105-113`); req 11 specifies the half-applied detection. Spec Technical Constraints specify the lock file path is inside `$cortex_root/.git/`. Implementer's choice: use `signal.alarm` or a threading-based watchdog for the timeout — both are acceptable; the only contract is that the budget honors `int(os.environ.get("_CORTEX_LOCK_TIMEOUT_OVERRIDE", str(_LOCK_TIMEOUT_SECONDS)))` (the env-var override path established in Task 5a, which test fixtures use to inject a shorter timeout for spawn-method children). **Per-subcommand C3 message customization**: for long-init commands, the generic `rerun your command` message is too vague — a user typing `cortex overnight start ...` needs to see explicitly that the overnight session was NOT started. Build the success message based on `args.command`/`args.overnight_command`: (a) for `args.command == "overnight"` AND `args.overnight_command == "start"`: `cortex updated to <sha7>; the overnight session was NOT started — re-run: cortex overnight start ...` (echo back the original argv for clarity); (b) for `args.command == "init"`: `cortex updated to <sha7>; init was NOT run — re-run: cortex init ...`; (c) for any other subcommand: the original generic `cortex updated to <sha7>; rerun your command`. Build the per-subcommand `re-run:` echo from `sys.argv[1:]` so the user sees their exact original invocation. Spec req 8 acceptance text is unchanged (it specifies the `cortex updated to <sha7>` prefix and `sys.exit(0)`, both honored); the suffix is an additive UX improvement adopted during plan-phase critical review.
- **Verification**: `python -c "import os, sys, subprocess, tempfile; tmp = tempfile.mkdtemp(); subprocess.run(['git', 'init', tmp], check=True, capture_output=True); env = {**os.environ, 'CORTEX_COMMAND_ROOT': tmp, 'CLAUDECODE': '1'}; r = subprocess.run([sys.executable, '-c', 'import argparse; from cortex_command.cli import _check_and_apply_update; _check_and_apply_update(argparse.Namespace(no_update_check=False), argv=[\"overnight\", \"status\"])'], env=env, capture_output=True, timeout=10); assert r.returncode == 0; print('ok')"` exits 0 and prints `ok` — pass if exit 0. (Behavioral check: invokes the gate end-to-end with `CLAUDECODE=1` set so the skip predicate fires, asserting the function returns rather than raising. A stub that does nothing also returns 0, but combined with Tasks 8-14's behavioral suite this gate confirms the function is callable with the documented arguments.)
- **Status**: [ ] pending

### Task 6: Wire `_check_and_apply_update()` into `main()`

- **Files**: `cortex_command/cli.py`
- **What**: Insert the gate call in `main()` after `parser.parse_args()` and before `args.func(args)` dispatch, passing `args` and `sys.argv[1:]`. The gate either runs to completion (returning to the dispatch path) or `sys.exit()`s mid-flight; `main()`'s control flow continues only when the gate is a no-op or a soft skip.
- **Depends on**: [5b]
- **Complexity**: simple
- **Context**: `main()` is at `cli.py:326-336`. Insert `_check_and_apply_update(args, argv=sys.argv[1:])` between the existing `args = parser.parse_args(...)` (line 330) and `if not getattr(args, "func", None):` (line 332). The gate must come AFTER parse_args (it needs `args.no_update_check`) but BEFORE the func-dispatch path. Note: argparse `--help` exits before reaching the gate, which is correct — the help-path skip in req 5 is insurance for the no-args case (`sys.argv[1:] == []`) where parse_args succeeds and main() prints help.
- **Verification**: `grep -c "_check_and_apply_update(args" cortex_command/cli.py` returns at least 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 7: Set up test scaffolding and shared helpers in `tests/test_cli_auto_update.py`

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Create the new test file with imports, the NDJSON log-parsing helper, the cross-process worker helpers used by concurrency tests (req 7, req 9.f), the sentinel-file utilities, and a `_StubArgs` factory for argparse.Namespace stubs. No actual test functions yet — those land in Tasks 8-14.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: New file at `tests/test_cli_auto_update.py`. Top of file: `from __future__ import annotations`, then stdlib imports (`json`, `os`, `subprocess`, `multiprocessing`, `pathlib`, `typing`, `unittest.mock`, `pytest`). Helpers required: (a) `_parse_ndjson_log(path: pathlib.Path) -> list[dict]` — opens the log, splits on `\n`, calls `json.loads` per non-empty line, returns the list; (b) `_gate_worker(env_overrides: dict[str, str], sentinel_dir: str, dispatch_behavior: typing.Literal["sleep_short_then_zero", "sleep_long_then_zero", "real"], dispatch_sleep_seconds: float) -> None` — top-level (picklable) function used as `multiprocessing.Process` target on macOS spawn. The worker (i) updates `os.environ` from `env_overrides` BEFORE importing `cortex_command.cli` (so the `_CORTEX_LOCK_TIMEOUT_OVERRIDE` env-var branch in Task 5a is honored), (ii) imports `cortex_command.cli`, (iii) applies its own `unittest.mock.patch.object(cortex_command.cli, "_dispatch_upgrade", side_effect=lambda *a, **kw: (time.sleep(dispatch_sleep_seconds), 0)[1])` (or no-op for `dispatch_behavior == "real"`), (iv) writes a sentinel `<sentinel_dir>/dispatch-called.<os.getpid()>` BEFORE invoking the gate, (v) calls `_check_and_apply_update(argparse.Namespace(no_update_check=False), argv=["overnight","status"])`. Spawn-safe contract: all state needed by the worker (env, behavior selector, sleep duration, sentinel dir path) flows in via the Process `args` tuple — no closure capture, no parent-side `monkeypatch` reliance. (c) `_log_appender_worker(log_path: str, count: int, stage: str) -> None` — top-level worker for Task 13c; sets `XDG_STATE_HOME` env so `_append_error_log` writes to the test path, imports lazily, calls `_append_error_log(stage, "x")` `count` times. (d) `_make_stub_args(**overrides) -> argparse.Namespace` — builds `argparse.Namespace(no_update_check=False, **overrides)`. Reference style: `tests/test_cli_upgrade.py` (167 lines). The existing tests use mock-only style for in-process subprocess.run mocks; the cross-process tests in Tasks 11 and 13c necessarily use real Process workers because spawn-boundary patches are not propagatable — this is an explicit deviation from "mock-only" for the concurrency cases only.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py --collect-only 2>&1` exits 0 — pass if exit 0 (no collection errors; helpers compile cleanly; no tests collected yet is acceptable).
- **Status**: [ ] pending

### Task 8: Tests for skip predicates (req 4, req 5)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_dev_mode_env_skips_gate` (A4.a), `test_claudecode_env_skips_gate` (A4.b), `test_dirty_tree_skips_gate` (A4.c), `test_non_main_branch_skips_gate` (A4.d), `test_help_paths_skip_gate` (A5). The dirty-tree and non-main-branch tests use `capsys` to assert the stderr note is emitted on every invocation that would skip. The CLAUDECODE test asserts no error log is written.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: All five tests mock `subprocess.run` to control git output, patch `os.environ` via `monkeypatch.setenv` / `monkeypatch.delenv`, and assert that `_dispatch_upgrade` is never called (use `unittest.mock.patch("cortex_command.cli._dispatch_upgrade")`). For A4.c the assertion is `"auto-update skipped: working tree dirty (set CORTEX_DEV_MODE=1 to silence)" in capsys.readouterr().err`. For A4.d the assertion uses the `branch is not main` literal. For A5 each of the four `argv` shapes (`["--help"]`, `["-h"]`, `["--version"]`, `[]`) runs as a parametrized `pytest.mark.parametrize` case.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_dev_mode_env_skips_gate tests/test_cli_auto_update.py::test_claudecode_env_skips_gate tests/test_cli_auto_update.py::test_dirty_tree_skips_gate tests/test_cli_auto_update.py::test_non_main_branch_skips_gate tests/test_cli_auto_update.py::test_help_paths_skip_gate -v` exits 0 — pass if exit 0 and all five pytest tests pass.
- **Status**: [ ] pending

### Task 9: Tests for opt-out flag/env (req 6)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_no_update_check_flag_skips_gate` (A6.a) and `test_no_update_check_env_skips_gate` (A6.b). Verify that either the `--no-update-check` flag or `CORTEX_NO_UPDATE_CHECK=1` env var causes the gate to short-circuit before any network call.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A6.a builds a stub args via `_make_stub_args(no_update_check=True)` and asserts `_dispatch_upgrade` and the `subprocess.run` for `git ls-remote` are never called. A6.b sets `CORTEX_NO_UPDATE_CHECK=1` via `monkeypatch.setenv` with `_make_stub_args(no_update_check=False)`. Both use `unittest.mock.patch("subprocess.run")` to assert no ls-remote call.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_no_update_check_flag_skips_gate tests/test_cli_auto_update.py::test_no_update_check_env_skips_gate -v` exits 0 — pass if exit 0 and both tests pass.
- **Status**: [ ] pending

### Task 10: Tests for gate execution + ls-remote + URL sourcing (req 1, 2, 3)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_gate_runs_before_dispatch` (A1.a), `test_upstream_drift_triggers_upgrade` (A1.b), `test_lsremote_timeout_continues_command` (A2), `test_remote_url_sourced_from_origin` (A3). Verify that the gate runs before `args.func`, that ls-remote drift triggers `_dispatch_upgrade` exactly once, that `subprocess.TimeoutExpired` raises a logged `ls_remote_timeout` and the user's command still dispatches, and that the URL passed to `git ls-remote` is whatever `git remote get-url origin` returns (mock-only, fork URL).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A1.a patches `_check_and_apply_update` to record its call order vs. the dispatched func via a shared list; verifies the gate's first-call sentinel precedes the func's. A1.b mocks `git ls-remote` to return SHA-X, `git rev-parse HEAD` to return SHA-Y (different), and asserts `_dispatch_upgrade` was called exactly once via `mock.assert_called_once()`. A2 raises `subprocess.TimeoutExpired(cmd=..., timeout=1)` from the ls-remote mock and asserts (i) `_dispatch_upgrade` was NOT called, (ii) the log contains an `ls_remote_timeout` entry parsed via `_parse_ndjson_log`, (iii) the user's `args.func` was reached (use a sentinel mock `args.func`). A3 mocks `git remote get-url origin` to return `https://github.com/forkuser/cortex-command.git\n`, then mocks `git ls-remote` and asserts `subprocess.run.call_args_list` contains a call whose first positional arg list includes that fork URL string.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_gate_runs_before_dispatch tests/test_cli_auto_update.py::test_upstream_drift_triggers_upgrade tests/test_cli_auto_update.py::test_lsremote_timeout_continues_command tests/test_cli_auto_update.py::test_remote_url_sourced_from_origin -v` exits 0 — pass if exit 0 and all four pytest tests pass.
- **Status**: [ ] pending

### Task 11: Tests for concurrent invocations + lock semantics (req 7)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_concurrent_invocations_serialize` (A7) as a parametrized test with two variants: (a) child A holds the lock briefly and child B successfully waits-then-acquires (exactly one sentinel file exists in tmp_path); (b) child A holds past the (shortened) timeout and child B logs `lock_contention_timeout`. Inject the shortened lock timeout via env var (NOT `monkeypatch.setattr` — that does not propagate to spawn-method children on macOS).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Uses `multiprocessing.Process(target=_gate_worker, args=(...))` with the spawn-safe worker from Task 7. Both children receive `env_overrides={"_CORTEX_LOCK_TIMEOUT_OVERRIDE": "2", "CORTEX_COMMAND_ROOT": str(tmp_cortex_root), "XDG_STATE_HOME": str(tmp_state_dir)}` so the gate inside each child reads a 2-second lock-timeout via the env-var path established in Task 5a, and writes the error log under the test directory. The worker applies its own `unittest.mock.patch.object(cortex_command.cli, "_dispatch_upgrade", ...)` inside the child interpreter — parent-side `unittest.mock.patch` does NOT propagate across spawn. Variant (a): both children invoke the worker with `dispatch_behavior="sleep_short_then_zero", dispatch_sleep_seconds=0.5`; one acquires immediately, one waits ~0.5s then acquires; both succeed but only the first reaches `_dispatch_upgrade` (the second sees same-SHA after the first's apply, OR — more cleanly — the test arranges that only one child is set up to see drift, via `git ls-remote` mocking applied inside the worker). Variant (b): child A invokes worker with `dispatch_behavior="sleep_long_then_zero", dispatch_sleep_seconds=5` (>2s timeout); child B sees lock contention, waits 2s, logs `lock_contention_timeout`. After both `proc.join()`, the test asserts: variant (a) — `len(list(tmp_path.glob("dispatch-called.*")))` (sentinel files written before each worker's gate invocation) reflects the expected acquisition pattern; variant (b) — `_parse_ndjson_log(state_dir / "cortex-command/last-error.log")` contains exactly one entry with `stage == "lock_contention_timeout"`. Both children point at the same `cortex_root` so they share the lock file at `$cortex_root/.git/cortex-update.lock` (the worker creates `$cortex_root/.git/` via `mkdir(parents=True, exist_ok=True)` if missing). Note: the test cannot rely on `monkeypatch.setattr` for `_LOCK_TIMEOUT_SECONDS`, `unittest.mock.patch` for `_dispatch_upgrade`, or any other parent-side state injection — all configuration crosses the spawn boundary via env vars in `env_overrides` or via `args` passed to the worker.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_concurrent_invocations_serialize -v` exits 0 — pass if exit 0 and both parametrized variants pass.
- **Status**: [ ] pending

### Task 12: Tests for post-pull SHA + exit-with-rerun message (req 8)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_post_upgrade_exits_with_rerun_message` (A8.a), `test_success_message_uses_post_pull_sha` (A8.b), and `test_overnight_start_message_calls_out_session_not_started` (per-subcommand customization, plan-phase addition). Verify the success path emits `cortex updated to <sha7>` and `sys.exit(0)`, that the SHA comes from post-pull HEAD, and that long-init subcommands get a sharper message.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A8.a patches `_dispatch_upgrade` to return 0, mocks ls-remote and rev-parse to return distinct SHAs (so the gate proceeds to apply), then asserts `pytest.raises(SystemExit) as exc_info; assert exc_info.value.code == 0` AND `"cortex updated to" in capsys.readouterr().out`. A8.b mocks `git ls-remote` to return SHA-X (`'a' * 40`), `_dispatch_upgrade` to return 0, and the post-dispatch `git rev-parse HEAD` to return SHA-Y (`'b' * 40`); asserts the captured stdout contains `cortex updated to bbbbbbb` and does NOT contain `aaaaaaa`. The new `test_overnight_start_message_calls_out_session_not_started` test invokes the gate with `args.command == "overnight"`, `args.overnight_command == "start"`, and a synthetic `sys.argv` like `["cortex", "overnight", "start", "--time-limit", "36000"]`; asserts the captured stdout contains `the overnight session was NOT started` AND echoes back the original invocation text (e.g., `re-run: cortex overnight start --time-limit 36000`). Multiple `subprocess.run` mocks: implementer should use `mock.side_effect = [...]` to return the right value for the right call (ls-remote, rev-parse-pre, rev-parse-post). Patch `_run_verification_probe` to return 0 so the half-applied path is not taken.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_post_upgrade_exits_with_rerun_message tests/test_cli_auto_update.py::test_success_message_uses_post_pull_sha tests/test_cli_auto_update.py::test_overnight_start_message_calls_out_session_not_started -v` exits 0 — pass if exit 0 and all three tests pass.
- **Status**: [ ] pending

### Task 13a: Tests for error log basic write + dir creation + truncation (req 9 a/b/e)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_lsremote_failure_logs_to_both` (A9.a), `test_log_directory_created` (A9.b), `test_message_truncated_to_256_chars` (A9.e). The simple non-time-based, non-concurrent error-log tests.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A9.a mocks ls-remote to raise `subprocess.CalledProcessError`, asserts stderr has the error AND the log file has a parseable NDJSON line with `stage == "ls_remote"` (use `_parse_ndjson_log` from Task 7). A9.b deletes the log dir before the test, triggers an error, asserts the dir was created via `pathlib.Path(...).exists()`. A9.e calls `_append_error_log("ls_remote", "x" * 1024)` and asserts the parsed JSON's `message` field has length exactly 256.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_lsremote_failure_logs_to_both tests/test_cli_auto_update.py::test_log_directory_created tests/test_cli_auto_update.py::test_message_truncated_to_256_chars -v` exits 0 — pass if exit 0 and all three tests pass.
- **Status**: [ ] pending

### Task 13b: Tests for error-log dedup time-based behavior (req 9 c/d)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_no_origin_dedup_suppresses_within_24h` (A9.c) and `test_no_origin_dedup_expires_after_24h` (A9.d). Verify the 24-hour mtime-based dedup for `no_origin` and `not_a_git_repo` stages.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A9.c calls `_append_error_log("no_origin", ...)` twice in a row and asserts `len(_parse_ndjson_log(log_path)) == 1`. A9.d calls once, manipulates the log's mtime via `os.utime(log_path, (now - 25*3600, now - 25*3600))`, then calls again, and asserts `len == 2`. Use `pathlib.Path` and `time.time()` for `now`. Pattern reference: spec req 9 + Technical Constraints define the dedup helper's read-only scan-from-EOF behavior.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_no_origin_dedup_suppresses_within_24h tests/test_cli_auto_update.py::test_no_origin_dedup_expires_after_24h -v` exits 0 — pass if exit 0 and both tests pass.
- **Status**: [ ] pending

### Task 13c: Test for concurrent error-log appends (req 9 f)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_concurrent_log_appends_serialize` (A9.f). Verify per-write `fcntl.flock(LOCK_EX)` serializes appends from multiple processes; resulting log is parseable NDJSON with no interleaved bytes.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Spawns two `multiprocessing.Process(target=_log_appender_worker, args=(str(log_path), 50, "ls_remote"))` children. Each child sets `XDG_STATE_HOME` via `os.environ` (set inside the worker before importing `cortex_command.cli`) so `_append_error_log` writes to `<tmp>/cortex-command/last-error.log`, then loops 50 times calling `_append_error_log("ls_remote", "x")` (non-deduped stage to avoid the 24h short-circuit). After both `proc.join()`, the parent calls `_parse_ndjson_log(log_path)` and asserts (i) every line parses as JSON without raising, (ii) total line count == 100, (iii) all `stage` fields are `ls_remote`. Like Task 11, this test cannot rely on parent-side state injection — the worker is a top-level function with all configuration passed via `args` so it works under macOS spawn.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_concurrent_log_appends_serialize -v` exits 0 — pass if exit 0 and the test passes.
- **Status**: [ ] pending

### Task 14: Tests for half-applied + dispatch-reuse guard (req 10, req 11)

- **Files**: `tests/test_cli_auto_update.py`
- **What**: Add `test_half_applied_state_detected` (A11) and `test_no_new_git_pull_call_site` (A10 AST-as-test). The AST test reads `cortex_command/cli.py` from disk but does NOT modify it.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: A11 patches `_dispatch_upgrade` to return 0 AND patches `_run_verification_probe` to return 1 (two distinct `unittest.mock.patch` targets — no side-effect ordering). Asserts (i) `with pytest.raises(SystemExit) as exc: ...; exc.value.code == 1`, (ii) `_parse_ndjson_log(...)` contains one entry with `stage == "half_applied"`, (iii) the success message is NOT in `capsys.readouterr().out`. The dispatch-reuse guard test uses `ast.parse` instead of grep to count actual `subprocess.run([..., "pull", ...])` call sites — protects against false positives in docstrings, comments, or string literals. Implementation: resolve the cli.py path via `pathlib.Path(__file__).resolve().parent.parent / "cortex_command/cli.py"`; parse via `ast.parse(path.read_text())`; walk the tree counting `ast.Call` nodes whose function is `subprocess.run` (matched by `ast.Attribute` with `attr == "run"` and `value.id == "subprocess"`) AND whose first positional arg is an `ast.List` containing an `ast.Constant` with value `"pull"`; assert the count is exactly 1 (the existing call inside `_dispatch_upgrade` at `cli.py:105-108`). This rejects stub implementations that put `"git pull"` in a docstring, comment, or unreachable branch.
- **Verification**: `python -m pytest tests/test_cli_auto_update.py::test_half_applied_state_detected tests/test_cli_auto_update.py::test_no_new_git_pull_call_site -v` exits 0 — pass if exit 0 and both tests pass.
- **Status**: [ ] pending

### Task 15: Update `docs/setup.md` with Auto-update section (req 13)

- **Files**: `docs/setup.md`
- **What**: Append (or insert into the appropriate location) a section titled `Auto-update` (≤200 words) explaining: gate runs on every `cortex` invocation; skip conditions (`--help`, `-h`, `--version`, no-args, `CORTEX_DEV_MODE=1`, `CLAUDECODE=1`/`CLAUDE_CODE_ENTRYPOINT`, dirty tree, non-main branch, `--no-update-check`, `CORTEX_NO_UPDATE_CHECK=1`); failure log location (`${XDG_STATE_HOME}/cortex-command/last-error.log`); disable mechanism (`CORTEX_DEV_MODE=1` or `--no-update-check`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `docs/setup.md` is at the repo root under `docs/`. Use a top-level `## Auto-update` heading. Keep prose concise — the spec caps at 200 words. No need to reproduce all req-4/5/6/9 details verbatim; a user-facing summary plus the disable mechanisms suffices.
- **Verification**: `grep -c "Auto-update" docs/setup.md` returns at least 1 — pass if count ≥ 1.
- **Status**: [ ] pending

## Verification Strategy

The plan distinguishes **per-task smoke gates** (intermediate `python -c` and pytest invocations declared on each task) from **end-to-end behavioral gates** (the suite-level checks below). Per-task smoke gates cannot fully constrain behavior — they catch syntax errors, missing symbols, and obvious regressions, but a malicious or lazy implementer could pass them with no-op stubs. The orchestrator's per-task diff review against the task's What/Context is the primary behavioral gate during the implement loop. The end-to-end gates below are the final acceptance criteria.

End-to-end gates (each runnable independently):

1. **Test suite passes**: `python -m pytest tests/test_cli_auto_update.py -v` exits 0 with all named acceptance tests passing (the spec's req 12 names every test individually). This is the primary behavioral verification surface — it catches stubs at Tasks 1-6 the moment Tasks 8-14 start failing.
2. **Existing test suite still passes**: `python -m pytest tests/test_cli_upgrade.py -v` exits 0. The new gate must not regress `_dispatch_upgrade()` behavior — Task 5b's reuse of `_dispatch_upgrade()` is the only change to its call graph.
3. **Static guards**: Task 14's AST-based check confirms exactly one `subprocess.run([..., "pull", ...])` call in `cortex_command/cli.py` (req 10 dispatch-reuse guard, robust to docstring/comment false positives); `grep -c "Auto-update" docs/setup.md` returns ≥ 1 (req 13 docs).

Manual smoke (cannot be unit-tested): in a clean clone of cortex-command at a SHA behind upstream, with no skip predicates tripped, running any `cortex` subcommand should print the C3 message and exit 0. Re-running should be a no-op (now at HEAD). This requires a real `uv tool install` and is excluded from the automated suite per spec's mock-only conventions for the simple paths.

## Veto Surface

- **Gate placement: inside `cortex_command/cli.py::main()`**. The spec accepted this over a SessionStart hook + flag-file design; see spec Problem Statement and Non-Requirements. Revisiting would invalidate the spec's "single inline check-and-apply" axis.
- **Test count of 18 pytest functions**. The spec enumerates each acceptance test individually (req 12). If lighter coverage is acceptable, the user could collapse some A9.x error-log dedup variants. Default: keep all 18; the file is large but each test is independently small.
- **Test style: mock-only**. Consistent with `tests/test_cli_upgrade.py`. The user could opt for real `git init` fixtures for higher fidelity at the cost of test runtime; the spec explicitly chose mock-only (req 3 acceptance language).
- **Tasks that touch the same file run sequentially**. All implementation tasks (1, 2, 3, 4, 5a, 5b, 6) edit `cortex_command/cli.py`; all test tasks (7, 8, 9, 10, 11, 12, 13a, 13b, 13c, 14) edit `tests/test_cli_auto_update.py`. Implementer dispatch parallelism is therefore limited; tasks within each chain serialize. This is a property of the file decomposition, not a design choice — alternative: split the gate into a new `cortex_command/auto_update.py` module to enable parallel implementation, at the cost of an extra import surface. Default: keep co-location with `cli.py` per the spec's structure.
- **Lock timeout configured via module constant + private env-var override**. `_LOCK_TIMEOUT_SECONDS = 30` is the production default; the gate reads `_CORTEX_LOCK_TIMEOUT_OVERRIDE` (private env var, underscore-prefixed) at call time as the spawn-safe injection mechanism for `multiprocessing.Process` children in Task 11's concurrency tests. The override is private and undocumented for end users; production callers never set it. Alternative considered: rely on `monkeypatch.setattr` for the constant — REJECTED because spawn-method `multiprocessing.Process` children on macOS re-import the module from disk and never see parent monkeypatches. Alternative: expose a public env var (e.g., `CORTEX_AUTO_UPDATE_LOCK_TIMEOUT`) — REJECTED because it expands the production configuration surface for a test-only need.
- **No `cortex --version` subcommand added**. Per spec Non-Requirements. The req 5 skip on `["--version"]` is insurance for a future `--version` flag that may never be added; the empty-argv case (`["cortex"]`) is the load-bearing skip path today.

## Scope Boundaries

Per spec Non-Requirements (excluded from this plan):

- No SessionStart hook in `plugins/cortex-interactive/hooks/hooks.json` (the original ticket's design was simplified during spec).
- No XDG state directory for an `update-available` flag file. The error log at `${XDG_STATE_HOME}/cortex-command/last-error.log` is the only filesystem state outside `$cortex_root/.git/`.
- No daily throttle — every invocation runs a live ls-remote (~165ms).
- No `os.execv` re-exec on the same invocation. The C3 exit-and-rerun message is the chosen UX.
- No plugin `hooks.json` change.
- No `settings_merge.py` user-global allowWrite policy precedent. The simplified design eliminated the need.
- No statusline indicator for pending updates.
- No cross-platform daemon install.
- No `--version` subcommand.
- No migration of existing stranded `~/.claude/hooks/cortex-{sync-permissions.py,scan-lifecycle.sh}` hooks.
- No automatic plugin update.
- No automatic `cortex init --update` for project scaffolding.
- No `CORTEX_REPO_URL` env-var override (origin URL only).
- No once-per-session suppression of dev-mode skip stderr notes.
- No auto-update inside Claude Code sessions (`CLAUDECODE=1` / `CLAUDE_CODE_ENTRYPOINT` skip predicate).
