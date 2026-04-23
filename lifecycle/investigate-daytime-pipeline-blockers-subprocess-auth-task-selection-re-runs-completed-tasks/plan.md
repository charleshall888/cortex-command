# Plan: investigate-daytime-pipeline-blockers-subprocess-auth-task-selection-re-runs-completed-tasks

## Overview

Two-track decomposition of the spec's 15 requirements. **Auth track** (Tasks 1–6, 11): introduce a stdlib-only `claude/overnight/auth.py` shared by `runner.sh` (pre-venv) and `daytime_pipeline.py` (in-process), refactor both call sites to use it, add the `auth_bootstrap` observability event with `sk-ant-*` redaction, and harden the daytime path with a startup-classified hard-fail when no vector resolves. **Parser/observability track** (Tasks 7–10): add `sk-ant-*` redaction to `dispatch._on_stderr`, narrow parser regexes (E1 strips trailing `[xX]` from heading description, E2 anchors `_parse_field_status`), codify writer idempotency in tests-only, and add a round-trip integration test. Tracks are independent and parallelizable. The auth helper is built source-first (Task 1) so all dependent tasks (runner refactor, daytime wiring, tests, docs) can fan out from it.

## Tasks

### Task 1: Implement `claude/overnight/auth.py` shared module
- **Files**: `claude/overnight/auth.py`
- **What**: Create the stdlib-only auth-resolution module with both Python and shell entry points. Implements four-vector resolution (env-preexisting → apiKeyHelper → personal-oauth-token → none), `os.environ` write, `sk-ant-*` sanitization, and the `auth_bootstrap` event payload return.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - **First module line must be `from __future__ import annotations`** — defers annotation evaluation so PEP 604 union syntax (`X | None`) does not crash on Python 3.9. The helper is invokable pre-venv (spec R2: "succeeds with `PYTHONPATH=$REPO_ROOT` with NO venv active"); stock macOS `/usr/bin/python3` is 3.9, so runtime annotation evaluation must not fail there.
  - Public API: `def ensure_sdk_auth(event_log_path: pathlib.Path | None = None) -> dict` returning `{"vector": str, "message": str, "event": dict}`. Vector values: `"env_preexisting" | "api_key_helper" | "oauth_file" | "none"`.
  - Public API: `def resolve_auth_for_shell() -> int` invoked via `python3 -m claude.overnight.auth --shell`; prints `export VAR=VALUE` to stdout (VALUE through `shlex.quote()`), warning to stderr; exit codes 0=resolved, 1=no-vector, 2=helper-internal-failure.
  - Stdlib-only imports allowed: `json`, `os`, `pathlib`, `re`, `shlex`, `subprocess`, `sys`, `datetime`, `time`. No `claude_agent_sdk`, no `requests`, no third-party deps (R3 enforces this).
  - **Home-directory lookup must use `pathlib.Path.home()`** — NOT `os.path.expanduser`, NOT direct `$HOME` reads. This pins a single API surface so test fixtures using `monkeypatch.setattr(pathlib.Path, "home", ...)` cover every lookup site.
  - Sanitization: `re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', text)` applied to all message content, including helper subprocess stderr and exception `repr()`.
  - Event format must byte-match `claude/pipeline/state.py::log_event` output: UTF-8, single line, trailing newline, `ts` field first. **Timestamp source contract**: import and call `claude.pipeline.state._now_iso` (or, if circular-import risk forbids that, define a module-private `_now_iso()` whose implementation is byte-identical and whose call site is monkey-patchable from tests). The byte-equivalence test in Task 2 monkey-patches this single source so both event-emission paths return the same string.
  - Resolution order mirrors `claude/overnight/runner.sh:50-87` exactly (currently inlined as a Python heredoc in bash).
  - Module entry point: include `if __name__ == "__main__":` with `--shell` arg dispatch to `resolve_auth_for_shell()`.
  - Writes resolved credential to `os.environ["ANTHROPIC_API_KEY"]` or `os.environ["CLAUDE_CODE_OAUTH_TOKEN"]` depending on vector.
  - When `event_log_path` is None, writes the message to `stderr`. When provided, appends one JSON line via append-only open (O_APPEND).
  - apiKeyHelper subprocess call: `subprocess.run(parts, capture_output=True, text=True, timeout=5)` wrapped in `try/except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError)` per Edge Cases. Timeout/empty/non-zero falls through to oauth-file branch (NOT exit 2).
  - Malformed `~/.claude/settings.json` → exit 2 (helper-internal failure) per Edge Cases.
  - No side effects at import time — all work happens inside the two entry-point functions.
- **Verification**: `python3 -c "from claude.overnight import auth; assert callable(auth.ensure_sdk_auth) and callable(auth.resolve_auth_for_shell)"` — pass if exit 0. AND `grep -E '^(import|from) ' claude/overnight/auth.py | grep -Ev '^(import|from) (__future__|json|os|pathlib|re|shlex|subprocess|sys|datetime|time|argparse|typing|claude\.pipeline\.state)( |$)'` — pass if exit code = 1 (grep finds nothing matching the disallowed pattern). The allow-list enumerates every module the helper may import; any unlisted import surfaces as a non-empty grep match (exit 0), which fails verification.
- **Status**: [x] complete

### Task 2: Comprehensive `test_auth.py` suite
- **Files**: `claude/overnight/tests/test_auth.py`
- **What**: Add the full test suite that exercises Task 1's contract: vector resolution across all four branches (R1), three exit codes for shell entry (R2), stdlib-only regression guard (R3), `os.environ` write (R8), `sk-ant-*` redaction + byte-equivalence with `log_event` (R7).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Test module path: `claude/overnight/tests/test_auth.py`. Follow the conftest pattern in `claude/overnight/tests/conftest.py` for fixtures.
  - Required test functions (names exact, per spec acceptance criteria):
    - `test_vector_resolution` — four parametrized cases: env-preexisting, api-key-helper (mocked subprocess), oauth-file (fixture file), none. Asserts `result["vector"]` matches expected. Each case uses `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` and `monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)` first so prior-test state cannot leak.
    - `test_shell_exit_codes` — three cases: resolved (exit 0), no-vector with empty fixture home (exit 1), helper-internal failure via monkey-patched `json.loads` raising `JSONDecodeError` on settings.json (exit 2).
    - `test_stdlib_only` — dispatches `subprocess.run([sys.executable, "-I", "-c", code], env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": REPO_ROOT}, capture_output=True)`. The empty-vector env (no `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`) and `tmp_path`-rooted `HOME` (no `.claude/settings.json`, no `.claude/personal-oauth-token`) deterministically produces vector=`"none"` → exit code 1. **Oracle is `assert proc.returncode == 1`**, NOT `in {0, 1}` — exit 1 must come from no-vector resolution, not from `ImportError` (which also exits 1 but with stderr containing `"ModuleNotFoundError"` or `"ImportError"`). Test must additionally assert `b"ImportError" not in proc.stderr` and `b"ModuleNotFoundError" not in proc.stderr` to disambiguate.
    - `test_redaction_and_byte_equivalence` — (i) feeds synthetic helper emitting `sk-ant-secret123` on stderr through `ensure_sdk_auth`, asserts captured event line contains `sk-ant-<redacted>` and not `sk-ant-secret123`. (ii) Byte-equivalence MUST use a frozen clock — monkey-patch the timestamp source on BOTH emission paths to return one fixed string: `monkeypatch.setattr("claude.pipeline.state._now_iso", lambda: "2026-04-23T12:00:00+00:00")` AND (if auth.py uses its own private `_now_iso`) `monkeypatch.setattr("claude.overnight.auth._now_iso", lambda: "2026-04-23T12:00:00+00:00")`. Then write one event via `ensure_sdk_auth(event_log_path=tmp_path/'a.log')` and a synthetic equivalent via `claude.pipeline.state.log_event(tmp_path/'b.log', payload)`. Assert `(tmp_path/'a.log').read_bytes() == (tmp_path/'b.log').read_bytes()`. Without the frozen clock, microsecond drift makes the assertion impossible.
    - `test_environ_write` — fixture oauth-file path; invoke `ensure_sdk_auth()`; assert `os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == fixture_value`. Use `monkeypatch.setenv` / `monkeypatch.delenv` to isolate.
  - Use `monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)` to redirect `~/.claude/...` lookups into pytest's `tmp_path`. This monkeypatch is sufficient because Task 1 pins `pathlib.Path.home()` as the only home-lookup API in auth.py.
  - Use `tests/_stubs.py::install_sdk_stub` if SDK module needs stubbing — not strictly required since auth.py has no SDK dependency.
- **Verification**: `.venv/bin/pytest claude/overnight/tests/test_auth.py -v` — pass if exit 0 and all five test functions pass.
- **Status**: [x] complete

### Task 3: Refactor `runner.sh` auth block to delegate to helper
- **Files**: `claude/overnight/runner.sh`
- **What**: Replace `runner.sh:42-87` (current auth resolution heredoc) with the capture + case-statement pattern from spec R4, delegating all resolution logic to `python3 -m claude.overnight.auth --shell`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Replacement pattern (per R4 verbatim):
    ```bash
    set +e
    _AUTH_STDOUT=$(python3 -m claude.overnight.auth --shell)
    _AUTH_EXIT=$?
    set -e
    case "$_AUTH_EXIT" in
      0) eval "$_AUTH_STDOUT" ;;
      1) : ;;
      2) echo "Error: auth helper internal failure" >&2; exit 2 ;;
    esac
    unset _AUTH_STDOUT _AUTH_EXIT
    ```
  - Preserve `set -euo pipefail` at line 18 unchanged.
  - All warning strings currently at `runner.sh:78` and `runner.sh:82` are removed from bash — they re-emit from `auth.py` via stderr per R1.
  - `python3 -m claude.overnight.auth` must work pre-venv; `runner.sh` exports `PYTHONPATH=$REPO_ROOT` at line 40 before this block, so the module is importable.
- **Verification**: `bash -n claude/overnight/runner.sh` — pass if exit 0 (syntax valid). AND `grep -c 'python3 -m claude.overnight.auth --shell' claude/overnight/runner.sh` — pass if count = 1. AND `grep -c '_API_KEY=$(python3' claude/overnight/runner.sh` — pass if count = 0 (old heredoc removed).
- **Status**: [x] complete

### Task 4: Bash regression test for runner.sh auth block
- **Files**: `tests/test_runner_auth.sh`
- **What**: Add a bash-driven regression test asserting all three exit-code branches of the runner.sh auth block: success path exports a token in the subshell, no-vector path proceeds past the block, helper-internal failure aborts with exit 2.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Test file location: `tests/test_runner_auth.sh` (project root, alongside `tests/test_hook_commit.sh`).
  - Pattern: `tests/test_hook_commit.sh` for shell-test layout (conftest-free, executable, exits 0/non-zero based on assertions).
  - Three scenarios (each runs the auth block in a subshell with controlled fixture env):
    1. Success: stub `python3 -m claude.overnight.auth --shell` to print `export CLAUDE_CODE_OAUTH_TOKEN='abc'` and exit 0; after the block, assert `[[ "${CLAUDE_CODE_OAUTH_TOKEN}" == "abc" ]]`.
    2. No-vector: stub the helper to exit 1 with empty stdout; assert subshell continues past the block (write a sentinel marker after the block, assert it's reached).
    3. Helper-internal failure: stub the helper to exit 2; assert the subshell aborts with exit 2 and prints "Error: auth helper internal failure" to stderr.
  - Helper stubbing pattern: prepend a fake `python3` script to PATH inside the subshell (`PATH=$tmpdir:$PATH`).
  - Make the file executable (`chmod +x`).
- **Verification**: `bash tests/test_runner_auth.sh` — pass if exit 0 and all three scenarios assert green.
- **Status**: [x] complete

### Task 5: Wire `daytime_pipeline.py::run_daytime` Phase A + Phase B auth bootstrap
- **Files**: `claude/overnight/daytime_pipeline.py`
- **What**: Add Phase A `ensure_sdk_auth(event_log_path=None)` as the FIRST STATEMENT INSIDE THE TRY-BLOCK of `run_daytime` (current line 333, immediately before the plan-exists check at lines 333-343); buffer the returned event payload; emit it as Phase B once `pipeline_events_path` is computed. Hard-fail at startup if `vector == "none"` per R6 by following the **exact pattern of the existing plan-exists check at lines 334-343** — set `_top_exc`, `_terminated_via = "startup_failure"`, `_outcome = "failed"`, `return 1`. Do NOT raise; the existing finally block at lines 466-524 writes `daytime-result.json` with the correct classification.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Import: `from claude.overnight.auth import ensure_sdk_auth` at top of file.
  - **Phase A placement (load-bearing)**: Phase A is the first statement INSIDE the try-block at line 332 — i.e., the new line 333, displacing the existing plan-exists check to line 334+. Placement BEFORE the try-block is wrong: the only `except` handler that translates exceptions into `_terminated_via = "startup_failure"` lives at lines 456-464, and only fires for raises INSIDE the try; the only frame that writes `daytime-result.json` is the finally at lines 466-524, also bound to that try. Position-zero placement bypasses both. Placement AFTER the plan-exists check is also wrong — auth resolution must precede I/O so a missing auth vector is reported even when `plan.md` is also missing.
  - **State variables already exist**: `_top_exc` (line 323), `_terminated_via` (line 324), `_outcome` (line 325), `_startup_phase` (line 326) are all initialized BEFORE the try at line 332. Phase A inside the try sees them in scope. `start_ts` (line 319) and `dispatch_id` (line 320) are also bound BEFORE the try, so the finally's `DaytimeResult` constructor (lines 505-516) has everything it needs.
  - **Hard-fail control flow** (mirror lines 334-343 verbatim in shape):
    - Call `auth_event = ensure_sdk_auth(event_log_path=None)`; capture the returned dict.
    - If `auth_event["vector"] == "none"`: `sys.stderr.write(...)`; `_top_exc = RuntimeError("no auth vector available: " + auth_event["message"])`; `_terminated_via = "startup_failure"`; `_outcome = "failed"`; `return 1`. The outer finally writes `daytime-result.json` at line 518 (path: `Path(f"lifecycle/{feature}/daytime-result.json")` — cwd-relative; Task 6's test must control cwd via `monkeypatch.chdir(tmp_path)`).
    - Otherwise (vector resolved): proceed to plan-exists check unchanged. Buffer `auth_event` in a local variable for Phase B emit.
  - **Phase B emit site**: after the existing `build_config(...)` call at line 369, derive the `pipeline_events_path` (per `claude/pipeline/state.py` conventions; the implementer reads `state.py` to confirm the path it logs to — likely `Path(f"lifecycle/{feature}/pipeline-events.log")`). Append the buffered `auth_event["event"]` JSON line to that path using the same byte format `log_event` produces. The `auth_bootstrap` event must appear exactly once in `pipeline-events.log` per dispatch.
  - The "raise OR write" disjunction in spec R6 is collapsed to the "set state + return" form above — same observable outcome (terminated_via=startup_failure, daytime-result.json written) without bypassing the existing classifier.
- **Verification**: `grep -c 'ensure_sdk_auth' claude/overnight/daytime_pipeline.py` — pass if count ≥ 2 (one import, one call inside `run_daytime`). The structural correctness (placement INSIDE the try-block, before the plan-exists check) is verified end-to-end by Task 6 — if Phase A is placed wrong (outside the try, or AFTER the plan-exists check), Task 6's read-back of `daytime-result.json` fails for an observable reason (file missing, or wrong classification). AST inspection is dropped here because (a) `run_daytime` is `async def` (`ast.AsyncFunctionDef`, not `ast.FunctionDef`), (b) idiomatic Python places a docstring at `body[0]`, and (c) the right placement is INSIDE a try-block at `body[N].body[0]` where N depends on docstring presence — too brittle to encode as a one-liner.
- **Status**: [x] complete

### Task 6: Daytime hard-fail integration test
- **Files**: `claude/overnight/tests/test_daytime_auth.py`
- **What**: Add `test_no_auth_vector_hard_fails` per R6 acceptance: monkey-patch `os.environ` empty + `Path.home()` to empty fixture (no settings.json, no personal-oauth-token), invoke `run_daytime` with a fixture feature, assert `daytime-result.json["terminated_via"] == "startup_failure"` and error string contains `"no auth vector available"`.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - Test module path: `claude/overnight/tests/test_daytime_auth.py` (new file).
  - Existing pattern: `claude/overnight/tests/test_daytime_pipeline.py` for fixture invocation pattern of `run_daytime`.
  - Use `monkeypatch.setenv` / `monkeypatch.delenv` to ensure `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are unset before calling `run_daytime`.
  - Use `monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)` to redirect `~/.claude/...` lookups to an empty fixture dir.
  - **Pin cwd**: use `monkeypatch.chdir(tmp_path)` before calling `run_daytime`. The existing finally writes `daytime-result.json` to `Path(f"lifecycle/{feature}/daytime-result.json")` — a cwd-relative path. Without `chdir`, the file lands in the real working directory and pollutes other tests.
  - The fixture feature can be minimal — create `tmp_path/lifecycle/<slug>/plan.md` with one task before invoking `run_daytime`; the hard-fail must occur before `execute_feature` runs anyway.
  - Read-back: parse `tmp_path/lifecycle/<slug>/daytime-result.json`; assert `result["terminated_via"] == "startup_failure"` AND `"no auth vector available" in (result["error"] or "")` per R6.
- **Verification**: `.venv/bin/pytest claude/overnight/tests/test_daytime_auth.py::test_no_auth_vector_hard_fails -v` — pass if exit 0.
- **Status**: [x] complete

### Task 7: `sk-ant-*` redaction in `dispatch._on_stderr` + unit test
- **Files**: `claude/pipeline/dispatch.py`, `claude/pipeline/tests/test_dispatch.py`
- **What**: Apply `re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', line)` inside `_on_stderr` at `dispatch.py:424-426` before appending to `_stderr_lines`. Add unit test asserting redaction.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Source change: in the `_on_stderr` closure at `claude/pipeline/dispatch.py:424-426`, transform `line` through the redaction regex BEFORE the existing length check + append. Read the file at those lines to see the current closure body. Modification is a single `line = re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', line)` statement at the top of the function body. `re` is already imported in dispatch.py.
  - Test extends existing `claude/pipeline/tests/test_dispatch.py`. Test name candidate: `test_on_stderr_redacts_sk_ant_tokens`. Pattern: import `dispatch` module-internal helpers via the existing test file's imports; if `_on_stderr` is closure-bound (it is — defined inside `dispatch_task`), test the redaction by exercising the dispatch path with a stub SDK that emits `sk-ant-abc123def` on stderr, then assert captured `_stderr_lines[-1]` (or the final result envelope's stderr field) contains `sk-ant-<redacted>` and not `sk-ant-abc123def`.
  - Note: `_on_stderr` is a closure inside `dispatch_task` (per dispatch.py:424). The test must exercise it through `dispatch_task` rather than calling the closure directly. Use `tests/_stubs.py::install_sdk_stub` to feed synthetic stderr.
- **Verification**: `.venv/bin/pytest claude/pipeline/tests/test_dispatch.py -v -k stderr_redact` — pass if exit 0 and the new redaction test passes. The test exercises `dispatch_task` with a stub SDK that emits `sk-ant-abc123def` on stderr and asserts the captured stderr contains `sk-ant-<redacted>` and not `sk-ant-abc123def`. A grep on `dispatch.py` is intentionally NOT used as a verification gate because the literal string `sk-ant-<redacted>` could appear in a comment, unused constant, or unrelated function and pass the gate without wiring redaction into `_on_stderr`.
- **Status**: [x] complete

### Task 8: Parser E1 + E2 — heading strip and Status anchor + unit tests
- **Files**: `claude/pipeline/parser.py`, `claude/pipeline/tests/test_parser.py`
- **What**: Apply two narrowed-scope regex changes to `claude/pipeline/parser.py`: (E1) strip trailing `[xX]` from `task.description` after `_parse_tasks` line 301; (E2) anchor `_parse_field_status` at parser.py:394 from `re.search` to `re.match(r"\[[xX]\]", raw)`. Add unit tests covering all assertion cases from R10 + R11.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - E1 change: in `_parse_tasks` (`claude/pipeline/parser.py:299-326`), after the existing `description = match.group(2).strip()` at line 301, add:
    ```python
    description = re.sub(r'\s*\[[xX]\]\s*$', '', description).strip()
    ```
    Character class is `[xX]` ONLY — literal space `[ ]` is intentionally preserved (author signal for pending; see spec Edge Cases and R10).
  - E2 change: in `_parse_field_status` at `claude/pipeline/parser.py:394`, replace:
    ```python
    if re.search(r"\[x\]", raw, re.IGNORECASE):
    ```
    with:
    ```python
    if re.match(r"\[[xX]\]", raw):
    ```
    The `\s*` prefix that appeared in earlier drafts is dropped — `raw` is already `.strip()`ed at parser.py:393 so leading whitespace cannot occur.
  - Test additions to `claude/pipeline/tests/test_parser.py`:
    - E1 cases: `### Task 2: Do the thing [x]` → `description == "Do the thing"`; `### Task 3: Other [X]` → `description == "Other"`; `### Task 5: Reserve slot [ ]` → `description == "Reserve slot [ ]"` (preserved).
    - E2 cases: Status remainder `"[x] complete"` → `"done"`; `"[X] complete"` → `"done"`; `"see [x]y.txt pending"` → `"pending"` (mid-line `[x]` no longer false-positive); `"[ ] pending"` → `"pending"`.
  - Test names suggested: `test_parse_tasks_strips_trailing_xX_from_heading`, `test_parse_field_status_anchored_match`. Co-locate in `test_parser.py` next to existing tests.
- **Verification**: `.venv/bin/pytest claude/pipeline/tests/test_parser.py -v -k "strips_trailing or anchored_match"` — pass if exit 0 and both new tests pass.
- **Status**: [x] complete

### Task 9: Parser round-trip integration test
- **Files**: `claude/pipeline/tests/test_parser.py`
- **What**: Add `test_heading_and_status_round_trip` per R13: fixture plan.md with two task headings each containing trailing `[x]`, one with Status `[x] complete` (parses to `done`, clean description), one with Status `[ ] pending` (parses to `pending`, clean description — the exact pattern from `lifecycle/rewrite-verification-mindsetmd-to-positive-routing-structure-under-47-literalism/plan.md` Task 2).
- **Depends on**: [8]
- **Complexity**: simple
- **Context**:
  - Test name (exact, per spec R13): `test_heading_and_status_round_trip`.
  - Fixture plan.md inline-string or in `claude/pipeline/tests/fixtures/`. Two tasks with mismatched heading marker vs Status field per R13.
  - Use `parse_feature_plan(fixture_path)` to drive the parser end-to-end; assert on the resulting `Task` objects' `description` and `status` fields.
  - This test exercises both E1 (heading strip) and E2 (Status anchor) in combination — the round-trip cases are the integration of the two unit tests in Task 8.
- **Verification**: `.venv/bin/pytest claude/pipeline/tests/test_parser.py::test_heading_and_status_round_trip -v` — pass if exit 0.
- **Status**: [x] complete

### Task 10: Writer idempotency test (test-only, no source change)
- **Files**: `tests/test_common_utils.py`
- **What**: Add tests codifying the existing idempotency of `claude/common.py::mark_task_done_in_plan` per R12: calling on an already-`[X]` or `[x]` Status field is a no-op (file bytes unchanged); calling on `[ ] pending` Status field updates to `[x] complete`. This adds test coverage to a behavior the current source already exhibits — no source change to `common.py`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Test module location: `tests/test_common_utils.py` (project root, existing file).
  - Existing source: `claude/common.py:327-331` — `mark_task_done_in_plan` regex is `\[ \]` (literal empty brackets); `pattern.sub` returns unchanged text when no match. R12 verifies this behavior persists.
  - Test name candidate: `test_mark_task_done_in_plan_idempotent_over_existing_marks`.
  - Three assertions (per R12):
    1. Plan content with `- **Status**: [X] complete` → call `mark_task_done_in_plan` → file bytes byte-identical (use `bytes.read()` or hash comparison).
    2. Plan content with `- **Status**: [x] complete` → file bytes byte-identical after call.
    3. Plan content with `- **Status**: [ ] pending` → file updated to `- **Status**: [x] complete`.
  - Use `tmp_path` fixture for plan.md write.
- **Verification**: `.venv/bin/pytest tests/test_common_utils.py -v -k mark_task_done_in_plan_idempotent` — pass if exit 0.
- **Status**: [x] complete

### Task 11: Update `docs/overnight-operations.md` auth-resolution section
- **Files**: `docs/overnight-operations.md`
- **What**: Update the Auth Resolution section (currently around lines 512-523) to document that both `runner.sh` and `daytime_pipeline.py` participate in the shared `claude/overnight/auth.py` module. Cover the three-exit-code contract (R2) and the deferred-event-emit pattern for daytime startup (R5 Phase A/B).
- **Depends on**: [1, 3, 5]
- **Complexity**: simple
- **Context**:
  - Per CLAUDE.md: `docs/overnight-operations.md` owns auth-resolution narrative; do not duplicate into `docs/pipeline.md` or `docs/sdk.md` — link from those if cross-reference is needed.
  - Required content additions (per R14 acceptance):
    1. Mention `daytime_pipeline.py` participation (≥1 occurrence).
    2. Mention `claude/overnight/auth.py` shared module (≥1 occurrence).
    3. Document the three-exit-code contract: `exit code 2` (helper-internal failure) explicitly named (≥1 occurrence).
  - Existing auth section is around lines 512-523 — read it first to preserve correct surrounding context (e.g., `~/.claude/personal-oauth-token` mention, apiKeyHelper precedence).
  - Mention the deferred-event-emit pattern (Phase A at startup with no log path; Phase B once `pipeline_events_path` resolves).
- **Verification**: `grep -c 'daytime_pipeline' docs/overnight-operations.md` — pass if count ≥ 1. AND `grep -c 'claude/overnight/auth.py' docs/overnight-operations.md` — pass if count ≥ 1. AND `grep -c 'exit code 2' docs/overnight-operations.md` — pass if count ≥ 1.
- **Status**: [x] complete

## Verification Strategy

**Phase 1 (per-task)**: each task's Verification field runs at task-completion gate. Tests live alongside source in `claude/overnight/tests/`, `claude/pipeline/tests/`, and `tests/` per the existing layout.

**Phase 2 (integration)**: full-suite green via `.venv/bin/pytest` (project root) — exit 0. Validates that no parser/dispatch/auth changes broke an unrelated test.

**Phase 3 (smoke, manual at end of Implement)**: launch one daytime_pipeline run from an interactive Claude Code session against a small fixture feature; confirm (a) `pipeline-events.log` contains exactly one `auth_bootstrap` event with non-`none` vector, (b) no `sk-ant-*` token text appears anywhere in the log, (c) the SDK subprocess does NOT return "Not logged in · Please run /login". Phase 3 is interactive/session-dependent; not a CI gate but the final user-visible proof the bug is fixed.

**Phase 4 (Complete-phase deliverable, R15)**: PR description must include a paragraph documenting that Ticket 140's literal Problem 2 premise was user-error on the reproducer. Verification: `gh pr view <PR#> --json body --jq .body | grep -ic 'user-error on the reproducer'` returns ≥ 1. This is a Complete-phase responsibility (not a Plan task) — the `/pr` skill drafts the body during Complete; this requirement constrains its content.

## Veto Surface

- **Task granularity (11 tasks vs more split)**: Tasks 1+2 (auth.py source + tests) and Tasks 5+6 (daytime wiring + test) could each be merged into a single complex-tier task. The split is deliberate — separating source from tests reduces the autonomous executor's anchor on its own implementation when writing the test, and lets each task have a clearer "what's the deliverable" answer for verification non-self-sealing. If the user prefers fewer, larger tasks, merge 1↔2 and 5↔6 → 9 tasks.
- **R15 not represented as a Plan task**: PR-body content (Problem 2 close-out paragraph) is captured in Verification Strategy Phase 4 rather than as Task 12. Rationale: PR body is generated by `/pr` in Complete phase, not by an Implement-phase agent. If the user wants it as an explicit task, add Task 12: "Draft Problem 2 close-out paragraph in `lifecycle/<slug>/pr-snippet.md`" with verification `grep -c 'user-error on the reproducer' lifecycle/<slug>/pr-snippet.md` ≥ 1, then Complete-phase `/pr` includes that snippet.
- **runner.sh stays bash**: spec R4 commits to refactoring (not rewriting) the auth block; Non-Requirement #1 explicitly excludes a full Python rewrite of runner.sh. The task scope honors this. If the user wants a runner.sh → Python rewrite, that becomes a separate (out-of-scope) lifecycle.
- **Test file paths are committed in the plan**: `tests/test_runner_auth.sh`, `claude/overnight/tests/test_auth.py`, `claude/overnight/tests/test_daytime_auth.py` are all new files. Existing files extended: `claude/pipeline/tests/test_parser.py`, `claude/pipeline/tests/test_dispatch.py`, `tests/test_common_utils.py`. If the user prefers a different layout (e.g., colocate the runner-bash test into `claude/overnight/tests/`), adjust before Implement.
- **Phase B emit mechanism in Task 5**: the plan leaves the exact wiring of "buffer event in `run_daytime` local scope, emit after `pipeline_events_path` resolves" as an implementation choice (derive path from `state.py` conventions inline in `run_daytime`, OR thread it through `build_config`'s return). Both satisfy R5; the implementer picks. The Phase A placement (inside try-block, before plan-exists check) IS now locked in; the Phase B emit site is not.

- **Critical review residue (post-revision)**: the critical review surfaced 15 A-class findings and 3 B-class concerns. All A-class issues have been applied to the plan. B-class items written to `lifecycle/<slug>/critical-review-residue.json` for the morning report: (1) daytime-result.json path-pinning addressed via Task 6's `monkeypatch.chdir`; (2) home-API pinning addressed via Task 1 explicit `pathlib.Path.home()` constraint; (3) pytest-xdist concern dismissed pending evidence that the test suite uses parallel workers (no current evidence in `just test`).
- **Task 7 closure-bound test**: `_on_stderr` is a closure inside `dispatch_task`. The test must exercise it through the dispatch path with a stub SDK rather than calling the closure directly. If the user prefers extracting `_on_stderr` to a module-level helper for direct testability, that's a refactor beyond R9's scope.

## Scope Boundaries

Maps to spec's Non-Requirements (no work in this lifecycle):

- No full rewrite of `runner.sh` into Python (venv activation stays in shell).
- No concurrency guard / `fcntl.flock` on auth bootstrap.
- No `--api-key` / `options.api_key` SDK passthrough (would put credentials in argv).
- No bypass flag for startup-failure on no-vector (deliberate hard fail).
- No interactive auth fallback prompt (breaks LaunchAgent contexts).
- No migration away from `~/.claude/personal-oauth-token` file fallback.
- No task-level idempotency contract change (`_make_idempotency_token` continues `feature:task_number:plan_hash`).
- No ingest of `~/.claude/.credentials.json` (not present on this machine).
- No retrospective cleanup of authored-`[x]` markers in existing plan.md files (R10 strips at parse time; existing markers become harmless).
- No stripping of trailing `[ ]` from headings (intentional pending signal preservation).
- No change to `runner.sh`'s `set -euo pipefail` line (unchanged).
