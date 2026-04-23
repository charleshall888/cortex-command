# Specification: investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks

> Research: [[investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks/research|research.md]]

## Problem Statement

The daytime pipeline (`claude/overnight/daytime_pipeline.py`) fails on every dispatch when launched from an interactive Claude Code session because it does not replicate `runner.sh`'s auth-resolution bootstrap. The SDK-spawned `claude` subprocess inherits an empty env (Claude Code's keychain auth is not env-exported; macOS Keychain ACLs prevent a child binary from reading the parent's OAuth token), returns "Not logged in · Please run /login", and the feature pauses. A related parser concern surfaced in research: `[x]` markers authors place in plan.md task headings bleed through `task.description` into the dispatched agent's prompt and can mislead the agent into believing the task is already done. Fixing both surfaces unblocks the daytime pipeline for interactive use (its only supported launch context per `skills/lifecycle/references/implement.md:71`) and hardens the plan parser against a small class of latent edit-mistake bugs.

## Requirements

1. **Shared auth module `claude/overnight/auth.py` — Python API**: New module with stdlib-only dependencies. Exports `ensure_sdk_auth(event_log_path: Path | None = None) -> dict` that (a) resolves an auth vector in priority order — existing `ANTHROPIC_API_KEY` → `apiKeyHelper` from `~/.claude/settings.json` or `settings.local.json` → `~/.claude/personal-oauth-token` file — (b) writes the resolved credential into `os.environ` (`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`), (c) emits a message sanitized via `re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', ...)` (no raw token, no full helper command), and (d) returns `{"vector": "env_preexisting" | "api_key_helper" | "oauth_file" | "none", "message": str}`. When `event_log_path` is provided and non-None, the function appends a single `auth_bootstrap` JSON line to that path. When `event_log_path` is None, the function still emits the message to `stderr` so runner.sh / any caller without an events log still gets the observability surface. **Acceptance**: unit test asserts returned `vector:` tag matches the resolved source across all four branches (env-preexisting, api-key-helper, oauth-file, none). Pass: `.venv/bin/pytest claude/overnight/tests/test_auth.py::test_vector_resolution` exits 0.

2. **Shared auth module — shell API**: Module additionally exports `resolve_auth_for_shell() -> int` (invoked as a main entry point via `python3 -m cortex_command.overnight.auth --shell` or equivalent CLI surface). Behavior: (a) resolves the same vector as `ensure_sdk_auth`; (b) on resolution, prints one `export VAR=VALUE` line to stdout with VALUE passed through `shlex.quote()` so opaque token content is shell-safe; (c) prints a human-readable warning message to stderr on the no-vector and helper-failure paths, preserving the user-facing text currently in `runner.sh:78,82`; (d) returns exit code `0` on resolution, `1` on no-vector, `2` on helper-internal failure (import error, stdlib regression, malformed settings.json). The three exit codes are a load-bearing contract. **Acceptance**: unit test covers all three exit codes (resolved case, no-vector with empty fixture home, helper-internal failure via forced-stdlib-regression monkey-patch). Pass: `.venv/bin/pytest claude/overnight/tests/test_auth.py::test_shell_exit_codes` exits 0. Additionally, `python3 -c "from cortex_command.overnight.auth import ensure_sdk_auth, resolve_auth_for_shell"` succeeds with `PYTHONPATH=$REPO_ROOT` with NO venv active.

3. **Stdlib-only regression guard**: A test dispatches a subprocess `python3 -I -c "import sys; sys.path.insert(0, REPO_ROOT); from cortex_command.overnight import auth; auth.resolve_auth_for_shell()"` with only stdlib modules available (Python isolated mode `-I` strips third-party sys.path entries and user site-packages). The subprocess must exit 0 or 1 (resolved or no-vector; never 2). Exit 2 indicates a non-stdlib import crept into the module and breaks the runner.sh pre-venv path. **Acceptance**: `.venv/bin/pytest claude/overnight/tests/test_auth.py::test_stdlib_only` exits 0. Pass: exit code 0.

4. **runner.sh refactor — concrete bash pattern**: `claude/overnight/runner.sh` lines 42-87 are replaced with the following exact control-flow shape (formatted for clarity; implementation must preserve the three-branch exit-code handling):

   ```bash
   set +e
   _AUTH_STDOUT=$(python3 -m cortex_command.overnight.auth --shell)
   _AUTH_EXIT=$?
   set -e
   case "$_AUTH_EXIT" in
     0) eval "$_AUTH_STDOUT" ;;
     1) : ;;  # no-vector: helper already printed warning to stderr; runner.sh continues
     2) echo "Error: auth helper internal failure" >&2; exit 2 ;;
   esac
   unset _AUTH_STDOUT _AUTH_EXIT
   ```

   The pattern (a) captures stdout separately from exit code so `eval` is driven by the exit code not the stdout content, (b) temporarily relaxes `set -e` around the capture so the helper's exit-1 does not abort the script, (c) honors exit-2 as a hard-fail for helper-internal issues (distinct from no-vector), (d) emits no warning strings from bash — all user-facing warnings come from the helper via stderr. **Acceptance**: `bash -n claude/overnight/runner.sh` exits 0 AND a regression test `tests/test_runner_auth.sh` (or pytest-bash equivalent) runs the block with fixture env variants and asserts (i) success path sets `CLAUDE_CODE_OAUTH_TOKEN` in the subshell, (ii) no-vector path exits 0 and proceeds past the block (use `trap 'echo PAST_AUTH' DEBUG` or write a sentinel marker file in the line after the block), (iii) helper-internal failure path aborts with exit 2. Pass: test suite runs all three variants green.

5. **daytime_pipeline.py auth bootstrap — call-site ordering**: In `claude/overnight/daytime_pipeline.py::run_daytime`, the auth bootstrap runs in two phases:
   - **Phase A (startup)**: `ensure_sdk_auth(event_log_path=None)` is invoked as the first statement of `run_daytime`, before `_check_cwd`, plan-exists check, PID-file liveness, or `_write_pid`. The event is NOT written here (no path known); the message is written to stderr per R1. If `vector == "none"`, hard-fail per R6.
   - **Phase B (deferred event emit)**: After `pipeline_events_path` is computed (currently inside `_build_batch_config` at `daytime_pipeline.py:222`), the auth-bootstrap event is appended to it. The Phase A call returns the full event payload; the caller buffers it in `run_daytime`'s local scope and writes it once the path is known. This is a side requirement: `ensure_sdk_auth` returns the event payload along with `vector` and `message`, so the caller can emit it later.
   
   **Acceptance**: (a) `grep -n 'ensure_sdk_auth' claude/overnight/daytime_pipeline.py` returns at least one call in `run_daytime` before `_write_pid`; (b) integration-style unit test with a fixture oauth-file asserts `pipeline-events.log` contains exactly one `auth_bootstrap` event with matching `vector:` tag by the time `execute_feature` is called. Pass: both assertions pass.

6. **Hard fail on no auth vector — daytime path**: When `ensure_sdk_auth()` Phase A returns `vector: "none"`, `run_daytime` raises a startup-phase exception (or writes `daytime-result.json` with `outcome: "failed"`, `terminated_via: "startup_failure"`, error containing the substring `"no auth vector available"`) before any worktree creation. The classification is `startup_failure` regardless of the exact line where auth resolution is placed, so long as the failure occurs before `execute_feature`. **Acceptance**: unit test monkey-patches `os.environ` empty, patches `Path.home()` to an empty fixture directory (no settings.json, no personal-oauth-token), invokes `run_daytime` with a fixture feature, asserts `daytime-result.json["terminated_via"] == "startup_failure"` and `"no auth vector available"` in the error string. Pass: `.venv/bin/pytest claude/overnight/tests/test_daytime_auth.py::test_no_auth_vector_hard_fails` exits 0.

7. **Auth observability event — schema and field sanitization**: The `auth_bootstrap` event has exactly this shape, written as a single JSON line:
   ```json
   {"ts": "<ISO 8601 UTC>", "event": "auth_bootstrap", "vector": "env_preexisting|api_key_helper|oauth_file|none", "message": "<human-readable, sanitized>"}
   ```
   `message` content contract: (a) no raw token value; (b) no full helper command with arguments (name-only OK, e.g., `"apiKeyHelper failed"` not `"/usr/bin/security find-generic-password -a user -s 'Claude Code-credentials' -w failed"`); (c) `sk-ant-[a-zA-Z0-9_-]+` is substituted with `sk-ant-<redacted>` before inclusion; (d) any helper subprocess stderr or exception `repr()` included in message first passes through the same sanitization. The byte format must match existing `log_event` output (UTF-8, single line, trailing newline, `ts` field first). **Acceptance**: (i) unit test feeds a synthetic helper that emits `sk-ant-secret123` on stderr into `ensure_sdk_auth`, asserts `not re.search(r'sk-ant-[a-zA-Z0-9_-]+', event_line)` AND `'sk-ant-<redacted>' in event_line`; (ii) byte-equivalence test writes an `auth_bootstrap` event via `ensure_sdk_auth` and a synthetic equivalent via `log_event`, asserts line-for-line equality (`ts` format, field order, newline). Pass: both assertions pass.

8. **`os.environ` write**: `ensure_sdk_auth()` writes resolved credentials to `os.environ` directly, so they inherit to every child process. `dispatch.py:401-405` already forwards `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from `os.environ` — no change needed there; this requirement is about the helper's write target. **Acceptance**: unit test invokes `ensure_sdk_auth()` with a fixture oauth-file path and asserts `os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == fixture_value` immediately after the call. Pass: pytest assertion passes.

9. **stderr token redaction in dispatch.py**: The `_on_stderr` callback at `claude/pipeline/dispatch.py:424-426` applies `line = re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', line)` before appending to `_stderr_lines`. **Acceptance**: unit test feeds a synthetic stderr line containing `sk-ant-abc123def` to `_on_stderr`, asserts the captured `_stderr_lines[-1]` contains `sk-ant-<redacted>` and does NOT contain `sk-ant-abc123def`. Pass: pytest assertion passes.

10. **Parser E1 — heading marker strip (narrowed class)**: `_parse_tasks` in `claude/pipeline/parser.py` strips a trailing `[x]` or `[X]` marker from the captured task description after line 301's `description = match.group(2).strip()`. Regex: `description = re.sub(r'\s*\[[xX]\]\s*$', '', description).strip()`. The character class does NOT include literal space — trailing `[ ]` in a heading is left intact because `[ ]` is an author signal for *pending*, not completion, and stripping it would suppress a legitimate marker. **Acceptance**: unit test asserts (i) `### Task 2: Do the thing [x]` parses to `description == "Do the thing"`; (ii) `### Task 3: Other [X]` parses to `description == "Other"`; (iii) `### Task 5: Reserve slot [ ]` parses to `description == "Reserve slot [ ]"` (trailing `[ ]` preserved). Pass: all three pytest assertions pass.

11. **Parser E2 — regex anchor in `_parse_field_status`**: `_parse_field_status` at `claude/pipeline/parser.py:394` changes the detection from `re.search(r"\[x\]", raw, re.IGNORECASE)` to `re.match(r"\[[xX]\]", raw)`. The `\s*` prefix that appeared in earlier drafts is dropped — `raw` is already `.strip()`ed at `parser.py:393`, so leading whitespace cannot occur. **Acceptance**: unit test asserts (i) Status remainder `"[x] complete"` returns `"done"`; (ii) Status remainder `"[X] complete"` returns `"done"`; (iii) Status remainder `"see [x]y.txt pending"` returns `"pending"` (mid-line `[x]` no longer false-positive); (iv) Status remainder `"[ ] pending"` returns `"pending"`. Pass: all four assertions pass.

12. **Parser E3 — writer idempotency verification (test-only)**: `claude/common.py::mark_task_done_in_plan` is ALREADY idempotent over `[X]` and `[x]` status fields because its current regex (`\[ \]` — literal empty brackets) does not match already-marked tasks; `pattern.sub` returns unchanged text and no file write occurs. No source change is required. This requirement adds test coverage codifying the existing behavior so a future refactor cannot silently regress it. **Acceptance**: unit test asserts (i) calling `mark_task_done_in_plan` on a plan.md containing `- **Status**: [X] complete` leaves file contents byte-identical (idempotent); (ii) calling on `- **Status**: [x] complete` leaves contents byte-identical; (iii) calling on `- **Status**: [ ] pending` updates to `- **Status**: [x] complete` as before. Pass: all three assertions pass.

13. **Parser round-trip test**: A new integration-style test uses a fixture plan.md with a task whose heading contains trailing `[x]` AND whose Status field is `[x] complete`. Parsed output must show `status == "done"` AND a clean `description` (no trailing bracket). A second fixture task has heading trailing `[x]` but Status `[ ] pending` (the exact pattern in `lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/plan.md` Task 2). Parsed output: `status == "pending"`, clean description. **Acceptance**: `.venv/bin/pytest claude/pipeline/tests/test_parser.py::test_heading_and_status_round_trip` exits 0. Pass: exit code 0.

14. **Documentation update**: `docs/overnight-operations.md` auth-resolution section (currently around lines 512-523) is updated to reflect both `runner.sh` and `daytime_pipeline.py` participating in the same shared `claude/overnight/auth.py` module, including the three-exit-code contract and the deferred-event-emit pattern for daytime startup. **Acceptance**: `grep -c 'daytime_pipeline' docs/overnight-operations.md` is ≥ 1 AND `grep -c 'claude/overnight/auth.py' docs/overnight-operations.md` is ≥ 1 AND `grep -c 'exit code 2' docs/overnight-operations.md` is ≥ 1 (exit-code contract documented). Pass: all three greps return ≥ 1.

15. **Problem 2 literal close-out in PR body**: The PR description for this work includes a paragraph documenting that Ticket 140's literal Problem 2 claim was user-error on the reproducer. Task 2's Status field in `lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/plan.md:70` is genuinely `[ ] pending`; the pipeline behaved correctly. The hardening in R10–R13 addresses the related-but-different surface (heading-bleed-through into agent prompts). **Acceptance**: PR description (markdown) contains the phrase "user-error on the reproducer" or equivalent within a Problem 2 section. Pass: grep of PR body finds the narrative.

## Non-Requirements

- **No full rewrite of runner.sh into Python**. Venv activation is inherently shell-level; rewriting it would require replicating activate semantics — out of scope.
- **No concurrency guard** (`fcntl.flock` on a bootstrap lock file). No evidence of concurrent daytime invocations causing helper-double-invocation today; simplicity doctrine applies.
- **No `--api-key` / `options.api_key` SDK passthrough**. `ClaudeAgentOptions` has no such field; `extra_args=["--api-key", ...]` would put credentials in argv (`ps`-visible) — strictly worse than env.
- **No bypass flag** for startup-failure. Hard fail on no-vector is deliberate; an override would mask misconfiguration.
- **No interactive prompt for auth fallback**. Breaks LaunchAgent / non-TTY contexts.
- **No migration away from `~/.claude/personal-oauth-token`** file-based fallback.
- **No task-level idempotency contract change**. `_make_idempotency_token` continues to hash `feature:task_number:plan_hash`.
- **No ingest of `~/.claude/.credentials.json`**. Not present on this machine (macOS Keychain only); no documented SDK-side read path.
- **No retrospective cleanup of heading `[x]` markers in existing plan.md files**. R10 strips them at parse time; existing authored-`[x]` in titles are harmless after that.
- **No stripping of trailing `[ ]` from headings** (intentional — empty brackets are a pending signal the author meant to preserve).
- **No change to runner.sh's `set -euo pipefail` line**. Only the auth block changes; the pipefail guard stays.

## Edge Cases

- **apiKeyHelper timeout (>5s)**: Python wraps `subprocess.run(..., timeout=5)` in `try/except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError)`. On any exception, fall through to the oauth-file branch; this is NOT classified as helper-internal failure (exit 2) because the helper-command timing out is a user environment issue, not a module defect.
- **apiKeyHelper returns non-zero exit code**: treat as "no vector from helper"; fall through to oauth-file branch without raising.
- **apiKeyHelper returns empty stdout**: treat as "no vector from helper"; fall through. Never export `ANTHROPIC_API_KEY=""`.
- **Malformed `~/.claude/settings.json`** (`json.JSONDecodeError`): classified as helper-internal failure; `resolve_auth_for_shell` returns exit 2, `ensure_sdk_auth` raises. Reason: a malformed settings file is a deterministic defect the caller must see.
- **`~/.claude/personal-oauth-token` exists but whitespace-only**: emit warning message, `vector: "none"`; exit 1 in shell path.
- **`~/.claude/personal-oauth-token` missing**: `vector: "none"`; exit 1 in shell path; R6 hard-fails on daytime side.
- **Both `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` set pre-call**: `vector: "env_preexisting"` returns immediately; helper and oauth-file are not consulted (matches runner.sh `if [[ -z "${ANTHROPIC_API_KEY:-}" ]]` intent).
- **Non-TTY / LaunchAgent context**: apiKeyHelper may attempt interactive Keychain prompt; 5s timeout bounds it.
- **Concurrent daytime_pipeline invocations**: each resolves independently. Acceptable risk; no lock added.
- **Stdlib regression in auth.py** (future `import yaml` added): R3 guard test fails, caught in CI before merge. In production without the guard: `resolve_auth_for_shell` returns exit 2, runner.sh aborts per R4 case statement.
- **Helper-subprocess stderr containing token fragment**: sanitization regex in R7 applies to message content; byte-equivalence test in R7 covers the leak path.
- **OAuth token containing shell-special characters** (`$`, backtick, `;`, newline, space): R2's `shlex.quote()` on VALUE produces a shell-safe literal that `eval` handles correctly.
- **Plan.md heading with `[X]` (capital) trailing**: R10 strips it (`[xX]` class).
- **Plan.md heading with `[x]` mid-title** (not trailing): R10 anchors to `$`; mid-title `[x]` is preserved.
- **Plan.md heading with `[ ]` trailing**: R10's class is `[xX]` only; the `[ ]` is preserved (intentional — pending signal).
- **Mid-Status-field-remainder `[x]`**: R11's anchored match returns `"pending"` (correct).
- **Status field with `[X]` (capital)**: R11's match accepts `[xX]`. Parser returns `"done"`.
- **dispatch.py stderr line contains `sk-ant-api03-abc-def-123`**: R9's regex substitutes `sk-ant-<redacted>`.

## Changes to Existing Behavior

- **ADDED**: `claude/overnight/auth.py` shared stdlib-only module with `ensure_sdk_auth()` and `resolve_auth_for_shell()` entry points.
- **ADDED**: three-exit-code contract for `resolve_auth_for_shell` (0 resolved, 1 no-vector, 2 helper-internal failure).
- **ADDED**: `auth_bootstrap` event in pipeline-events.log on daytime path (via Phase-B deferred emit).
- **ADDED**: `claude/overnight/tests/test_auth.py` — vector resolution, exit codes, stdlib-only regression guard, byte-format equivalence.
- **ADDED**: `claude/overnight/tests/test_daytime_auth.py` — hard-fail classification test.
- **ADDED**: runner.sh bash regression test covering all three exit-code branches.
- **ADDED**: `claude/pipeline/tests/test_parser.py::test_heading_and_status_round_trip` integration test.
- **ADDED**: test coverage codifying `mark_task_done_in_plan` existing idempotency (no source change to the writer).
- **MODIFIED**: `claude/overnight/runner.sh` auth block (lines 42-87) replaced with explicit capture + case-statement pattern per R4; warning strings currently at lines 78 and 82 move to `auth.py` stderr emission so they still fire for the user but no longer live in the deleted bash.
- **MODIFIED**: `claude/overnight/daytime_pipeline.py::run_daytime` gains Phase A auth bootstrap at startup; Phase B deferred event emit after `pipeline_events_path` is computed.
- **MODIFIED**: `claude/pipeline/dispatch.py::_on_stderr` applies `sk-ant-*` redaction before appending to captured stderr.
- **MODIFIED**: `claude/pipeline/parser.py::_parse_tasks` strips trailing `[xX]` from `task.description` (class narrowed — `[ ]` preserved).
- **MODIFIED**: `claude/pipeline/parser.py::_parse_field_status` uses anchored regex without dead `\s*` prefix.
- **MODIFIED**: `docs/overnight-operations.md` auth-resolution section reflects shared module, three-exit-code contract, and deferred-event-emit pattern.
- **REMOVED**: the two warning strings at `runner.sh:78` and `runner.sh:82` are moved to `auth.py` stderr emission — same user-visible output, different emission site.

## Technical Constraints

- `claude/overnight/auth.py` must be stdlib-only (no `claude_agent_sdk`, no `requests`, no third-party deps) so `runner.sh` can invoke it via `python3 -m` BEFORE venv activation. Allowed stdlib imports: `json`, `os`, `pathlib`, `re`, `shlex`, `subprocess`, `sys`, `datetime`, `time`. Enforced by R3 regression guard.
- File-based state preserved (no DB, no server) per `requirements/project.md:25`.
- Event log writes use append-only open (O_APPEND). POSIX atomicity is bounded by PIPE_BUF (~4KB); in practice all auth_bootstrap messages are well under this bound because tokens and helper commands are not included. If helper stderr or traceback inclusion pushes a message over that bound in pathological cases, truncate to 1KB before writing rather than risk interleave. Not an "atomic replace" — this is the existing `log_event` contract.
- Forward-only session transitions preserved per `requirements/pipeline.md:125-133`.
- Simplicity doctrine per `requirements/project.md:19` — no speculative generalization beyond the 4 vectors runner.sh already handles.
- Auth precedence order mirrors runner.sh exactly (`ANTHROPIC_API_KEY` pre-existing → `apiKeyHelper` → `personal-oauth-token`).
- Token values never appear in logs or stdout. `auth_bootstrap` event `message` is sanitized. `resolve_auth_for_shell` passes values through `shlex.quote` before printing.
- New module has no side effects at import time — all work happens inside `ensure_sdk_auth()` / `resolve_auth_for_shell()` calls.
- Runner.sh change preserves its current exit-on-error semantics (`set -euo pipefail` at line 18 unchanged). The auth block uses a scoped `set +e` / `set -e` bracket around the helper capture so the helper's exit code becomes explicit data consumed by a `case` statement.
- The byte-format of `auth_bootstrap` events written by `ensure_sdk_auth` must match `log_event` output (UTF-8, single line, trailing newline, `ts` field first, `_now_iso()` timestamp format). Enforced by R7 byte-equivalence test.

## Open Decisions

- None. Deferred items from research (Q2 observability, Q3 concurrency, Q4 env-export, Q5 stderr redaction) resolved in Requirements (R5/R7, Non-Requirement, R8, R9 respectively). Q1 (Problem 2 scope) resolved via AskUserQuestion before Specify. Q-SPEC1 (shared helper extraction) and Q-SPEC2 (hard-fail behavior) resolved via second AskUserQuestion pass. Critical review A-class and B-class findings applied above.
