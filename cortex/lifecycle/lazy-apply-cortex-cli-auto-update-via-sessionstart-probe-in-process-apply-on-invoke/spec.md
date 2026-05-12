# Specification: Lazy-apply cortex CLI auto-update

> Epic context: this lifecycle is scoped from epic 113 (CLI + plugin marketplace distribution). Epic research at `research/overnight-layer-distribution/research.md` Q7 chose explicit upgrade verbs and acknowledged plugin auto-update as Claude Code's responsibility. **This spec extends the CLI upgrade story** by adding a lazy-apply gate that calls the existing `cortex upgrade` verb automatically — it does not replace the explicit verb.

## Problem Statement

Post-epic-113, `cortex upgrade` is a manual verb that users forget to run. They open Claude daily, accumulate stale cortex CLI behavior, and miss bug fixes they would want. The original ticket proposed a SessionStart hook + flag-file + in-process apply design. During the spec interview, that design was simplified: the SessionStart hook adds no decoupling benefit (the cheap check can run inline at the same low cost), the throttle solves a non-problem, and the user-global state directory introduces a sandbox-policy precedent the project has not yet established. The accepted shape is a single inline check-and-apply gate in `cortex` itself, gated by dev-mode predicates and a `--no-update-check` flag, that **only engages from a bare shell** — never from inside a Claude Code session, where sandbox writes would fail anyway.

## Requirements

Classification: requirements 1–12 are **Must-Have** (1–6 and 8 are correctness preconditions; 7, 9, and 11 are safety preconditions; 10 enforces code-reuse hygiene; 12 is the quality bar). Requirement 13 is **Should-Have** — the feature works without docs, but discoverability degrades; a follow-up PR can add docs without rework. Won't-Do is captured in the Non-Requirements section.

### Must-Have

1. **Inline check-and-apply gate in `cortex_command/cli.py::main()`**: before `args.func(args)` is dispatched (currently `cli.py:317`), run a check-and-apply step that fetches upstream HEAD via `git ls-remote`, compares to local HEAD, and if the upstream advanced — invokes `_dispatch_upgrade()` (the existing function at `cli.py:71-105`).
   - Acceptance (A1.a): `pytest tests/test_cli_auto_update.py::test_gate_runs_before_dispatch -v` exits 0.
   - Acceptance (A1.b): with the install at a SHA behind upstream and dev-mode predicates not tripped, running any `cortex` subcommand triggers `_dispatch_upgrade()` exactly once. Verifiable: `pytest tests/test_cli_auto_update.py::test_upstream_drift_triggers_upgrade -v` exits 0.

2. **Cheap-check budget ≤ 1 second via Python-side timeout**: the network probe is `subprocess.run(["git", "ls-remote", "--quiet", remote_url, "main"], timeout=1, check=False, env=env_with_GIT_TERMINAL_PROMPT_0)`. On `subprocess.TimeoutExpired` or non-zero exit, treat as "no update available" and log to the error surface (req 9), then continue with the user's command. **Do not** wrap with shell `timeout(1)` — Python-side `timeout=1` is mockable cleanly via `subprocess.TimeoutExpired` in tests; the shell-wrapper variant is bypassed by `subprocess.run` mocks.
   - Acceptance: `pytest tests/test_cli_auto_update.py::test_lsremote_timeout_continues_command -v` exits 0 (mocks `subprocess.run` to raise `subprocess.TimeoutExpired`; verifies `_dispatch_upgrade` is not called, the error log contains a `ls_remote_timeout` entry, and the user's command continues to dispatch).

3. **Source upstream URL from `git remote get-url origin`** at runtime, not a hardcoded constant. This protects fork users from being silently auto-updated to upstream.
   - Acceptance: `pytest tests/test_cli_auto_update.py::test_remote_url_sourced_from_origin -v` exits 0. **Test style**: mock-only, consistent with `tests/test_cli_upgrade.py`. The test mocks `subprocess.run`'s `git remote get-url origin` call to return a fork URL string, then mocks the subsequent `git ls-remote` call and asserts the URL argument matches the mocked fork URL. No real `git init` fixture.

4. **Skip the gate in dev mode or under Claude Code**. Skip when ANY of the following is true:
   - `os.environ.get("CORTEX_DEV_MODE") == "1"`
   - `os.environ.get("CLAUDECODE") == "1"` OR `os.environ.get("CLAUDE_CODE_ENTRYPOINT")` is set (auto-update never engages from inside a Claude Code session — the sandbox would block writes to `$cortex_root/.git/` anyway, and the user can run `cortex` from a bare shell to update)
   - `git -C $cortex_root status --porcelain` is non-empty (dirty tree)
   - `git -C $cortex_root rev-parse --abbrev-ref HEAD` is not `main`
   - On dirty-tree or non-main-branch skip, print `auto-update skipped: <reason> (set CORTEX_DEV_MODE=1 to silence)` to stderr **on every invocation** that would skip — no once-per-session suppression (a single-shot CLI cannot meaningfully track session state without persistent storage, and persistent storage was rejected during spec design).
   - Acceptance (A4.a): `pytest tests/test_cli_auto_update.py::test_dev_mode_env_skips_gate -v` exits 0.
   - Acceptance (A4.b): `pytest tests/test_cli_auto_update.py::test_claudecode_env_skips_gate -v` exits 0 (mocks `os.environ` with `CLAUDECODE=1`; verifies `_dispatch_upgrade` is not called and no error log entry is written).
   - Acceptance (A4.c): `pytest tests/test_cli_auto_update.py::test_dirty_tree_skips_gate -v` exits 0; the test also asserts (via `capsys`) that stderr contains `auto-update skipped: working tree dirty (set CORTEX_DEV_MODE=1 to silence)`.
   - Acceptance (A4.d): `pytest tests/test_cli_auto_update.py::test_non_main_branch_skips_gate -v` exits 0; the test also asserts stderr contains `auto-update skipped: branch is not main (set CORTEX_DEV_MODE=1 to silence)`.

5. **Skip on bare-help and version paths**. Skip when `sys.argv[1:]` is exactly one of `["--help"]`, `["-h"]`, `["--version"]`, or empty (`["cortex"]` with no args), to avoid a 1s stall on commands the user expects to be instant.
   - Acceptance: `pytest tests/test_cli_auto_update.py::test_help_paths_skip_gate -v` exits 0.

6. **Skip on `--no-update-check` flag and `CORTEX_NO_UPDATE_CHECK=1` env var**. The flag is parsed by the top-level argparser (at the same level as `--help`); the env var is checked alongside it. Either suppresses the gate. The overnight runner sets one of these to avoid 1s of latency at session start.
   - Acceptance (A6.a): `pytest tests/test_cli_auto_update.py::test_no_update_check_flag_skips_gate -v` exits 0.
   - Acceptance (A6.b): `pytest tests/test_cli_auto_update.py::test_no_update_check_env_skips_gate -v` exits 0.

7. **Concurrent-safe via blocking flock at `$cortex_root/.git/cortex-update.lock`** with a 30-second timeout. First invocation wins; second waits up to 30s; if the lock is still held after 30s, the second invocation logs to the error surface (stage `lock_contention_timeout`) and continues with the user's command (no upgrade attempt).
   - Acceptance: `pytest tests/test_cli_auto_update.py::test_concurrent_invocations_serialize -v` exits 0. **Test mechanism**: spawns two `multiprocessing.Process` children pointing at a wrapper that imports `cortex_command.cli` and runs the gate. The wrapper, when it reaches `_dispatch_upgrade`, writes a sentinel file `<tmp_path>/dispatch-called.<os.getpid()>` BEFORE calling the real upgrade. After both processes complete, the test asserts (a) exactly one sentinel file exists in `<tmp_path>/` (only one child invoked the dispatch path), AND (b) the second child's behavior is one of the two specified outcomes (waited-then-acquired-after-first-released, or logged `lock_contention_timeout` after 30s — but this test artificially shortens the timeout to 2s via a fixture-injected constant). The test verifies BOTH behaviors via two parametrized variants: one where child A holds the lock briefly and child B successfully waits-then-acquires; another where child A holds the lock past the (shortened) timeout and child B logs `lock_contention_timeout`.

8. **C3 exit-and-rerun UX after a successful upgrade**: print to stdout (or stderr if stdout is not a TTY) `cortex updated to <new-sha-prefix-7>; rerun your command` and `sys.exit(0)`. The SHA prefix is sourced from `git rev-parse HEAD` AFTER `_dispatch_upgrade` completes (post-pull HEAD), NOT the ls-remote-captured value — to handle the case where upstream advanced between ls-remote and pull. Do NOT call `os.execv` — research established that `uv tool install --force` rewrites the shim in place, creating a TOCTOU race for `execve(2)`, and that lazy imports during the rewrite can fail with `ImportError`.
   - Acceptance (A8.a): `pytest tests/test_cli_auto_update.py::test_post_upgrade_exits_with_rerun_message -v` exits 0.
   - Acceptance (A8.b): `pytest tests/test_cli_auto_update.py::test_success_message_uses_post_pull_sha -v` exits 0. **Test mechanism**: mocks `git ls-remote` to return SHA-X (`'a' * 40`), `_dispatch_upgrade` to return 0, and `git rev-parse HEAD` (post-dispatch) to return SHA-Y (`'b' * 40`). Verifies the printed message contains `cortex updated to bbbbbbb` (SHA-Y prefix), NOT `aaaaaaa` (SHA-X prefix).

9. **Failure surface: stderr + `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log`**. Errors at any stage (`ls_remote`, `ls_remote_timeout`, `lock`, `lock_contention_timeout`, `apply`, `verification`, `half_applied`, `no_origin`, `not_a_git_repo`) print one line to stderr in real time AND append a structured NDJSON line to the log. **Atomicity**: each log append acquires a `fcntl.flock(LOCK_EX)` on the log file itself for the duration of a single `os.write(fd, line.encode() + b"\n")` call (single syscall, fd opened with `O_WRONLY | O_APPEND | O_CREAT`). The `message` field is truncated to 256 ASCII characters before serialization to bound line length. The log directory is created on first write via `pathlib.Path.mkdir(parents=True, exist_ok=True)`. **Dedup**: stages `no_origin` and `not_a_git_repo` are suppressed if the LAST line in the log file matches the same stage AND was written within the last 24 hours (stat-based mtime check). Other stages are always logged.
   - Acceptance (A9.a): `pytest tests/test_cli_auto_update.py::test_lsremote_failure_logs_to_both -v` exits 0 (mocks `subprocess.run` to raise `CalledProcessError`; verifies stderr contains the error AND the log file contains a parseable NDJSON line with `stage: ls_remote`).
   - Acceptance (A9.b): `pytest tests/test_cli_auto_update.py::test_log_directory_created -v` exits 0.
   - Acceptance (A9.c): `pytest tests/test_cli_auto_update.py::test_no_origin_dedup_suppresses_within_24h -v` exits 0. Test logs a `no_origin` event, then triggers a second `no_origin` immediately, then asserts the log contains exactly 1 line with that stage.
   - Acceptance (A9.d): `pytest tests/test_cli_auto_update.py::test_no_origin_dedup_expires_after_24h -v` exits 0. Test logs a `no_origin` event, manipulates the log's mtime to >24h ago via `os.utime`, triggers a second `no_origin`, then asserts the log contains 2 lines with that stage.
   - Acceptance (A9.e): `pytest tests/test_cli_auto_update.py::test_message_truncated_to_256_chars -v` exits 0. Test triggers an error path with a synthetic 1024-char `message`; asserts the logged JSON's `message` field is exactly 256 chars.
   - Acceptance (A9.f): `pytest tests/test_cli_auto_update.py::test_concurrent_log_appends_serialize -v` exits 0 (spawns two child processes that both append to the log via the helper; verifies all written lines are parseable as JSON, with no interleaved bytes).

10. **Reuse `_dispatch_upgrade()` for the apply path**. Do not duplicate the upgrade routine. The existing function's dirty-tree refusal (cli.py:85-90) is intentional and remains in force.
    - Acceptance: `grep -c "subprocess.run.*git pull" cortex_command/cli.py` returns the same count after this feature is implemented as before (no new git-pull call site).

11. **Post-upgrade verification probe via named seam `_run_verification_probe(cortex_root)`**. After `_dispatch_upgrade()` returns exit 0, call `_run_verification_probe(cortex_root)` — a new module-level function in `cortex_command/cli.py` that runs `subprocess.run([sys.argv[0], "--help"], capture_output=True, timeout=10)` and returns the exit code. If non-zero, treat the upgrade as half-applied: log a `half_applied` error to the error surface (req 9), do NOT print the success message, and `sys.exit(1)`.
    - Acceptance: `pytest tests/test_cli_auto_update.py::test_half_applied_state_detected -v` exits 0. Test patches `_dispatch_upgrade` to return 0 AND patches `_run_verification_probe` to return 1 (two distinct patch targets — no side-effect ordering across a single mock). Verifies the error log contains a `half_applied` entry, the success message is NOT printed, and the exit code is 1.

12. **Tests live at `tests/test_cli_auto_update.py`**. The file uses pytest with subprocess mocking via `unittest.mock.patch`, plus the following infrastructure beyond what `tests/test_cli_upgrade.py` provides: (a) `multiprocessing.Process` fixtures for the concurrency tests (req 7, 9.f) — sentinel-file pattern as specified in req 7's acceptance; (b) NDJSON log-parsing helper that reads `last-error.log` and asserts on `stage` field values via `json.loads` per line (used by req 9 acceptance tests); (c) `os.utime` manipulation for time-based dedup tests (req 9.c, 9.d); (d) `capsys` for stderr message assertions (req 4.c, 4.d, 9.a). The file will be substantially larger than `test_cli_upgrade.py` (167 lines) — expect 400–600 lines given the 18 named acceptance tests across 12 numbered requirements.
    - Acceptance: `python -m pytest tests/test_cli_auto_update.py -v` exits 0; the file contains tests for every named acceptance criterion (A1.a/b, A2, A3, A4.a/b/c/d, A5, A6.a/b, A7, A8.a/b, A9.a/b/c/d/e/f, A10 [grep, not pytest], A11, A12). Total: 18 pytest tests + 1 grep check = 19 acceptance gates.

### Should-Have

13. **`docs/setup.md` update**: a section titled `Auto-update` (≤200 words) explains: (a) the gate runs on every `cortex` invocation; (b) it skips on `--help`/`-h`/`--version`/no-args, dev-mode (CORTEX_DEV_MODE=1), inside Claude Code (CLAUDECODE=1 / CLAUDE_CODE_ENTRYPOINT set), dirty tree, non-main branch, and `--no-update-check` / `CORTEX_NO_UPDATE_CHECK=1`; (c) failures are logged to `${XDG_STATE_HOME}/cortex-command/last-error.log`; (d) to disable entirely, set `CORTEX_DEV_MODE=1` or pass `--no-update-check`.
    - Acceptance: `grep -c "Auto-update" docs/setup.md` returns at least 1.

## Non-Requirements

- **No SessionStart hook**. Decided during the spec interview: the SessionStart hook in the original ticket added no decoupling benefit (the check is cheap and only matters at user-initiated `cortex` invocation time).
- **No XDG state directory for the apply flag**. The error log lives at `${XDG_STATE_HOME}/cortex-command/last-error.log` (one file, written only on failure), but no flag file is needed — every invocation runs a live ls-remote.
- **No daily throttle**. ~165ms ls-remote per `cortex` invocation is acceptable; users invoke `cortex` a handful of times per day.
- **No `os.execv` re-exec on the same invocation**. Rejected during spec interview due to TOCTOU race during `uv tool install --force` shim rewrite.
- **No plugin `hooks.json` change**. The cortex-interactive plugin's `hooks.json` is not modified by this feature.
- **No `settings_merge.py` user-global allowWrite policy precedent**. The simplified design eliminates the need for a user-global sandbox entry; the per-repo philosophy in `requirements/project.md` remains intact.
- **No statusline indicator for pending updates**. Redundant with the in-process apply.
- **No cross-platform daemon install** (systemd / launchd).
- **No `--version` subcommand**. Separate concern; useful for `brew test do` but not in this ticket. The C3 message uses the truncated SHA, not a version number.
- **No migration of existing stranded `~/.claude/hooks/cortex-{sync-permissions.py,scan-lifecycle.sh}` hooks**. Out of scope per clarify discussion.
- **No automatic plugin update**. Per epic 113 Q7, plugin auto-update is Claude Code's job; out of scope here.
- **No automatic `cortex init --update` for project scaffolding**. Orthogonal; user-triggered.
- **No `CORTEX_REPO_URL` env var override**. The upstream URL is sourced exclusively from `git remote get-url origin` (req 3); there is no env-var override. A user who wants to track a different remote should `git remote set-url origin <url>` in their cortex install. Rationale: env-var overrides bypass git's existing remote configuration and create a second source of truth that can drift.
- **No once-per-session suppression of dev-mode skip stderr notes**. A single-shot CLI cannot meaningfully track session state without persistent storage, and persistent storage was rejected. Every invocation that skips for dirty-tree or non-main-branch reasons prints the stderr note. If the note becomes annoying, the user sets `CORTEX_DEV_MODE=1`.
- **No auto-update inside Claude Code sessions**. The gate detects `CLAUDECODE=1` / `CLAUDE_CODE_ENTRYPOINT` and skips entirely. Sandbox writes to `$cortex_root/.git/` would fail anyway; the user can update from a bare shell. This is a deliberate UX choice, not a workaround.

## Edge Cases

- **Network offline**: Python-side `subprocess.TimeoutExpired` after 1s; the gate logs to the error surface (stage `ls_remote_timeout`) and continues with the user's command. The user does not pay more than 1s of latency.
- **Upstream URL unreachable but DNS resolves**: same as offline — 1s timeout, log, continue.
- **`$cortex_root` is not a git repo (e.g., user installed via wheel or release tarball)**: the gate detects via `Path(cortex_root, ".git").is_dir()` and silently skips. No error logged in this case (this is a normal install path; logging would spam every invocation).
- **`$cortex_root` has no `origin` remote**: `git remote get-url origin` exits non-zero; gate logs once to the error surface (with stage `no_origin`) and skips. Subsequent `no_origin` events within 24 hours are suppressed via the dedup heuristic in req 9.
- **Dirty tree (the dogfooding user's normal state)**: `_dispatch_upgrade()` already refuses (cli.py:85-90), and the gate's req-4 dev-mode predicate skips before even calling it. Stderr note printed on every such skip; no suppression.
- **Branch is not main**: same skip, stderr note printed on every invocation.
- **Concurrent `cortex` invocations**: blocking flock at `$cortex_root/.git/cortex-update.lock` serializes them. First wins; second waits up to 30s; if still held after 30s, second logs `lock_contention_timeout` to the error surface and continues with the user's command (no upgrade attempt; will retry on next invocation).
- **Half-applied state (git pull ok, uv tool install fails)**: req-11 `_run_verification_probe` catches this. Error log entry has stage `half_applied`. The user sees a clear failure (stderr + exit 1) and can manually re-run `cortex upgrade` from a bare shell.
- **Inside Claude Code session**: gate skipped entirely via `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` env-var predicate (req 4). No latency, no error log, no failure surface — auto-update is simply not active in this context.
- **User has forked the repo**: `git remote get-url origin` returns the fork's URL; gate ls-remotes the fork. If the fork has not advanced, no update; if it has, `git pull --ff-only` against the fork. Upstream is never silently pulled.
- **Upstream advances between ls-remote and apply**: `git pull --ff-only` lands at SHA-Y but the gate's earlier ls-remote saw SHA-X. The success message uses `git rev-parse HEAD` post-pull (the actual installed SHA) per req 8, not the ls-remote-captured value.
- **Concurrent error logging** (two `cortex` processes both fail ls-remote and append to last-error.log): per-write `fcntl.flock(LOCK_EX)` on the log file (req 9) ensures appends are serialized; no interleaved bytes; resulting file is parseable NDJSON.

## Changes to Existing Behavior

- **ADDED**: `cortex_command/cli.py::main()` runs an auto-update check-and-apply step before `args.func(args)` dispatch.
- **ADDED**: `cortex --no-update-check` (top-level flag) and `CORTEX_NO_UPDATE_CHECK=1` env var suppress the gate.
- **ADDED**: `CORTEX_DEV_MODE=1` env var disables auto-update.
- **ADDED**: gate skip predicate for `CLAUDECODE=1` / `CLAUDE_CODE_ENTRYPOINT` environment variables (auto-update never engages from inside Claude Code sessions).
- **ADDED**: error log file at `${XDG_STATE_HOME}/cortex-command/last-error.log`, NDJSON, written only on failure.
- **ADDED**: lock file at `$cortex_root/.git/cortex-update.lock` (untracked by git per `.git/` semantics).
- **ADDED**: `_run_verification_probe(cortex_root)` module-level function in `cortex_command/cli.py`.
- **MODIFIED**: `_dispatch_upgrade()` is now invoked from two call sites (the new gate and the existing explicit `cortex upgrade` subcommand). Function semantics unchanged.

## Technical Constraints

- **Python-side subprocess timeouts only**. The gate uses `subprocess.run(..., timeout=N)` with Python's stdlib timeout, not shell-wrapped `timeout(1)`. Rationale: `subprocess.run` mocks bypass shell wrappers, making the shell-wrapped form untestable as written.
- **Lock-file path must be inside `$cortex_root/.git/`** — survives `git pull --ff-only` (`.git/` is preserved) and is implicitly per-install. Auto-update is skipped inside Claude Code (req 4), so sandbox-blocking of `$cortex_root/.git/` writes is not on the active path.
- **`git ls-remote` invocation must use `GIT_TERMINAL_PROMPT=0`** in the environment to prevent credential-prompt hangs on private forks (per web research).
- **Error-log atomicity**: each append acquires `fcntl.flock(LOCK_EX)` on the log file's fd, performs a single `os.write(fd, line_bytes)` with the line ending in `\n`, then releases the lock. This is the only correct atomicity mechanism for cross-process appends to a regular file on macOS APFS — POSIX's PIPE_BUF guarantee applies to pipes/FIFOs, not regular files. Lock acquisition is fast (microseconds) and the error path is infrequent.
- **Error-log message field**: truncated to 256 ASCII characters before serialization to bound line length and prevent runaway log entries from verbose git stderr.
- **Test framework**: pytest (existing project convention). Subprocess mocking via `unittest.mock.patch`. Test file at `tests/test_cli_auto_update.py`. New infrastructure required (per req 12): multiprocessing fixtures with sentinel-file IPC, NDJSON parsing helper, `os.utime` manipulation, `capsys` stderr assertions, two-stage two-target patches.
- **No new top-level dependencies**. Use only Python stdlib (`subprocess`, `pathlib`, `os`, `fcntl`, `json`, `datetime`) and existing `cortex_command.common` helpers.
- **Verification probe budget**: 10s `subprocess.run` timeout on the post-upgrade `cortex --help` probe. If it times out, log `verification_timeout` and exit 1.
- **Error-log format**: NDJSON, one object per line. Schema: `{"ts": "<ISO 8601>", "stage": "<ls_remote|ls_remote_timeout|lock|lock_contention_timeout|apply|verification|verification_timeout|half_applied|no_origin|not_a_git_repo>", "message": "<≤256 chars>", "cortex_root": "<path>", "remote_url": "<url or null>", "local_sha": "<full sha or null>", "remote_sha": "<full sha or null>"}`. Stage is a closed enum (no open `...` extension); morning-report ingestion via `jq -c '.stage'` is reliable. Compatible with future morning-report consumers if desired.
- **Dedup mechanism**: for stages `no_origin` and `not_a_git_repo`, the helper opens the log file (read-only, no lock needed for read), reads the last NDJSON line via `seek(-N) → read → split('\n')[-2]` (or scans backwards from EOF for the last newline), parses it, checks `stage` and `ts` fields. Suppresses the new entry if `stage` matches AND parsed `ts` is within 24 hours. The lock-protected appends from req 9 ensure the last line is always parseable.

## Open Decisions

None at spec time. The original five secondary research questions all have defaults locked in:

- Upstream URL source: `git remote get-url origin` at runtime; no env-var override (req 3, Non-Requirements).
- Help/version carve-out: `--help`, `-h`, `--version`, no-args (req 5).
- Disable mechanism: `CORTEX_DEV_MODE=1` env var or `--no-update-check` flag (req 4, req 6).
- Error logging: stderr + `${XDG_STATE_HOME}/cortex-command/last-error.log` NDJSON with per-write flock (req 9).
- Lock location: `$cortex_root/.git/cortex-update.lock` (Technical Constraints).

The simplified design moots the four hook-related research questions (Q2 user-global-vs-per-repo flag path, Q4 hook discovery, Q6 hook disable mechanism, Q9 SessionStart hooks.json shape).
