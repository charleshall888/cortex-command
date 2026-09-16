# Review: remove-claude-agent-sdk-dependency (cycle 1)

Scope: `git diff 0112e5d8..HEAD` (22 commits, HEAD 657cb824). Test baseline was supplied by the orchestrator: 6 failures, all present before this change, and I did not re-run the suite. I also ran these checks myself:

- The R16–R21 acceptance greps.
- A wheel build plus `uv pip compile` for the bare, `[all]`, `[dashboard]` and `[overnight]` installs (R17).
- `uv pip compile` against the latest tag and `@v5.2.0` (R26).
- `sandbox_preflight` (R24).
- A fresh no-extras venv that imports every non-test `cortex_command` module.
- Seven targeted mutation checks in a scratch worktree, which has since been removed.

## Stage 1: Spec compliance

| Req | Rating | Evidence |
|---|---|---|
| R1 one spawn seam | PASS | `claude_agent_sdk` count is 0 in `dispatch.py` and `discovery.py`. Both files import `claude_stream.run_claude`. The only `query(` hits are `_run_brief_query`, which is not an SDK call. |
| R2 options reach CLI | PASS | `build_argv` emits every flag in the list. `test_argv_carries_every_dispatch_option` checks the flags against `TIER_CONFIG`. I checked the argv against the SDK 0.2.153 `_build_command`: no `--setting-sources` was ever sent by default, so settings, hooks and CLAUDE.md loading behave the same as before. |
| R3 prompt on stdin | PASS | `_write_prompt` runs as a separate task and closes stdin. There are two tests: the >128 KiB byte-identical test and the no-positional-prompt test. |
| R4 ≥1 MiB line cap | PASS | `STREAM_LIMIT` is 16 MiB, and an over-limit line is discarded with a warning. Mutation to 64 KiB made the 256 KiB test fail. |
| R5 concurrent stderr drain | PASS | The drain task runs for the life of the process. Redaction and the byte/line caps in `_on_stderr` are unchanged. |
| R6 env = parent − CLAUDECODE + overlay | PASS | `build_env` does this, and an overlay value of `""` is handled. Mutation (removing the empty-`CLAUDECODE` deletion) was caught. |
| R7 run ends at process exit | PASS | Stdout is read to EOF, then `wait()` runs, and the last `result` frame is kept. Mutation (breaking at the first `result`) was caught. |
| R8 unknown/non-JSON skipped | PASS | `_parse_frame` handles these cases, and a test covers them. |
| R9 only assistant text in corpus | PASS | Other frame types are ignored and rate-limit data is read only from structured fields. Mutation (appending non-assistant frames to `output_parts`) was caught. |
| R10 taxonomy preserved | PASS | `test_dispatch_spawn.py` drives every `ERROR_RECOVERY` key through `retry.retry_task` and checks the action taken. A set-equality test pins coverage. `effort_unsupported` checks that `--effort max` appears on the second argv. |
| R11 unspawnable → infrastructure_failure | PASS | Both the `cli is None` path and `ClaudeSpawnError` return `infrastructure_failure`. The detail names the path and says "install Claude Code". The test uses the real `run_claude` with a nonexistent path. |
| R12 API fault named and halts | PASS | `api_unavailable` was added to `ERROR_RECOVERY` and `_SESSION_HALT_ERROR_TYPES`. `runner.py` now imports that tuple instead of hardcoding the list, and there are new notify and report-banner branches. Tests (a), (b) and (c) exist. Test (c) runs dispatch → retry → `run_batch` → `state.paused_reason`, but proves the round-loop break by an AST check on `runner.run`, not by executing the loop. I accept that. |
| R13 turn limit | PASS | `_is_turn_limit_stop` and a `subtype == "error_max_turns"` check, with a test. |
| R14 diagnostics on every failure | PASS | Every failure return goes through `_fail`. Mutation (dropping diagnostics on the result-frame path) was caught. |
| R15 live verification | PASS | `live-verification.md` records the kernel deny, the byte-identical target, the success result, and a budget run whose subtype is `error_max_budget_usd`. |
| R16 dependency gone | PASS | `claude-agent-sdk` count is 0 in both `pyproject.toml` and `uv.lock`. |
| R17 dashboard in base | PASS | Checked by running it. All four compiles resolve fastapi, uvicorn, jinja2, markdown and starlette, and none prints a "does not have an extra" warning. A control with `[bogus]` does print the warning. |
| R18 dead guards gone, no app at init | PARTIAL | All three greps return 0, and `test_init_creates_no_app.py` fails when the `ensure_app()` call is restored (I checked). But `docs/dashboard.md:23` still says "`cortex init` and `cortex dashboard` add **Cortex Dashboard** to `~/Applications` when the dashboard extra is installed". Both halves of that are now false. `cortex_command/dashboard/projects.py:22-23` also still refers to "a base install that has no dashboard extra". |
| R19 non-PATH fallbacks kept | PASS | The SDK grep returns 0. `test_non_path_fallback_used_when_not_on_path` fails when the fallback loop is removed (I checked). |
| R20 no test touches the SDK | PASS | The git grep is empty and `_stubs.py` is deleted. One caveat: the repo `.venv` still has `claude_agent_sdk` 0.2.153 installed, because `uv run` does an inexact sync. So the local suite alone could not prove the code works without the SDK. I checked separately: every non-test module imports cleanly in a fresh venv built from the HEAD wheel with no extras. |
| R21 SDK surfaces corrected | PARTIAL | Both acceptance greps are empty. However, several surfaces still describe the SDK or its extras as the live mechanism: (1) Both `install_core.py` rationale docstrings, which R21 names, were reworded into a new false claim: `plugins/cortex-core/install_core.py:365-368` and `plugins/cortex-overnight/install_core.py:528-532` still say the dashboard and overnight stacks "live behind optional `pyproject.toml` extras (so a bare install stays lean)" and that a no-extra reinstall "would silently strip" them. Under ADR-0039 the extras are empty. (2) `cortex_command/overnight/sandbox_settings.py:10-11` says dispatch passes settings through `ClaudeAgentOptions(settings=...)`. (3) `cortex_command/overnight/runner.py:110` says "``max_budget_usd`` on ``ClaudeAgentOptions``". (4) `cortex_command/overnight/integration_recovery.py:186-189` is an operator-facing string, "(SDK not installed); cannot dispatch repair agent", behind a `_DISPATCH_AVAILABLE` import guard. The spec's "SDK import guards … REMOVED" says this should be gone. (5) `cortex_command/pipeline/dispatch.py:449-450` says "newer of system-vs-fallback, #313", but the resolver no longer compares versions. |
| R22 fresh-resolve guard | PASS | The step now runs `pip install . httpx packaging`, keeps the Starlette ≥1.0 assertion and the route smoke test, and has a rewritten comment. The stale sentence count is 0. |
| R23 install argv unchanged | PASS | The diff touches only docstrings in both `install_core.py` files. The three named tests are not among the 6 baseline failures. |
| R24 sandbox gate re-pointed | PASS | `claude_stream.py` is watched for `--settings` and `settings`. The dead patterns are gone. `uv run python3 -m cortex_command.sandbox_preflight` exits 0. `preflight.md` `commit_hash` is 840632b5, the parent of the commit that recorded it. |
| R25 opt-in live test | PARTIAL | The test is collected and skipped without the flag ("opt-in via --run-slow"). No record shows it passing with `--run-slow`: the 579542e4 commit body is empty, and `live-verification.md` covers only Task 9. |
| R26 scheduled resolve | PASS | Checked by running it. The `schedule:` and `workflow_dispatch:` triggers are present. `uv pip compile` against `@v5.3.0` (the latest tag) exits 0 and against `@v5.2.0` exits 1. The `scheduled resolve` registry entry is present in `project.md`. |

No requirement failed, so Stage 2 ran.

## Stage 2: Code quality

- **Pattern consistency**: good.
  - `claude_stream.py` is a stdlib-only leaf, like `cli_resolver.py`.
  - Frame reads use `.get` throughout.
  - Cleanup kills the child in steps: terminate, wait 5 s, kill. It does not use `start_new_session`, as the plan specified.
  - The frame-level double takes the place of the `sys.modules` stub.
  - `runner.py` now imports `_SESSION_HALT_ERROR_TYPES` instead of repeating the list, so the halt list cannot drift apart again.
- **Error handling**:
  - A spawn failure and a missing binary are handled separately.
  - `CancelledError` is not swallowed, because the `unknown` arm catches `Exception` only.
  - `discovery._run_brief_query` now raises on a non-zero exit instead of returning an empty brief.
- **Classifier order widens session halts (recommendation, not a blocker)**:
  - `classify_failure` now checks the corpus for rate-limit phrases ("rate limit", "too many requests") before the timeout, test, refusal and confused keyword checks. The old `classify_error` checked rate limits last.
  - The corpus includes assistant text. So a failing feature whose agent mentions rate limiting now pauses the whole session as `api_rate_limit`. Example: a ticket that implements rate-limit handling.
  - The plan specified this order, but the structured signals (`api_error_status == 429` and the `rate_limit_event` status) already cover real rate limits.
  - Fix: limit the phrase check to stderr, or move it back after the keyword checks.
- **Naming and docs consistency**: the `cli_resolver.py` module docstring says the path is "memoized for the process lifetime once found". The code also memoizes `None`, so a runner that starts before `claude` is installed never looks again. The old code behaved the same way, so this is not a regression, but the docstring should say so.
- **Were the plan's verification steps executed?**
  - Task 7's mutation check is recorded in the 7fa049f7 commit body.
  - Task 11's mutation check is not recorded anywhere. I ran it and it was caught.
  - Task 19's passing run with `--run-slow` is not recorded.
  - Task 17's fresh-venv smoke test and the python-multipart fix (ccccb4dd) match the orchestrator's note. My fresh no-extras venv resolved python-multipart 0.0.32 and imported every module.
- **Out-of-plan commit ccccb4dd**: justified. mcp used to pull in python-multipart transitively, and the Docs view's `Form(...)` route needs it. The new pyproject comment gives the reason.

## Requirements Drift

**State**: detected

**Findings**:
- The change adds `api_unavailable` as a third session-halting error type. `cortex/requirements/multi-agent.md` "Model Selection Matrix" still lists only `budget_exhausted` or `api_rate_limit` as pausing the entire session (line 64).
- `cortex/requirements/pipeline.md` "Non-Functional Requirements" (line 148, Graceful degradation) names only budget exhaustion and rate limits as the causes that pause the session. It does not cover an API-wide auth or provider fault.

**Update needed**: cortex/requirements/multi-agent.md, cortex/requirements/pipeline.md

## Suggested Requirements Update

- **File**: cortex/requirements/multi-agent.md
- **Section**: Model Selection Matrix
- **Content**:
  ```
    - On `api_unavailable` (auth failure, `terminal_reason: "api_error"`, or API status 401/403/5xx on the result frame): pause the entire session (no new dispatches), with the cause named in the notification and the morning-report banner
  ```

- **File**: cortex/requirements/pipeline.md
- **Section**: Non-Functional Requirements
- **Content**:
  ```
  - **API-fault halt**: An API-wide fault (expired auth, provider error) classifies as `api_unavailable` and halts the session once via `_SESSION_HALT_ERROR_TYPES`, rather than retrying every feature against a dead API
  ```

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["R21 PARTIAL: both install_core.py rationale docstrings (plugins/cortex-core/install_core.py:365-368, plugins/cortex-overnight/install_core.py:528-532) were reworded into a new false claim that dashboard/overnight stacks live behind extras and a no-extra reinstall strips them; the extras are empty (ADR-0039)", "R21 PARTIAL: remaining surfaces still describe the SDK as the live mechanism: overnight/sandbox_settings.py:10-11 (ClaudeAgentOptions(settings=...)), overnight/runner.py:110 (max_budget_usd on ClaudeAgentOptions), pipeline/dispatch.py:449-450 (newer of system-vs-fallback), and the operator-facing '(SDK not installed)' string behind the dead _DISPATCH_AVAILABLE guard in overnight/integration_recovery.py:186-189", "R18 PARTIAL: docs/dashboard.md:23 still says cortex init adds the app 'when the dashboard extra is installed' (both halves now false); dashboard/projects.py:22-23 docstring still says 'no dashboard extra'", "R25 PARTIAL: no recorded passing run of tests/test_claude_stream_live.py with --run-slow on an authenticated machine", "Recommendation: classify_failure now checks the corpus for rate-limit phrases before the other keyword checks, so assistant text mentioning 'rate limit' on a failing feature halts the whole session; limit the phrase check to stderr or move it after the keyword checks"], "requirements_drift": "detected"}
```
