# Plan: replace-daytime-log-sentinel-classification-with-structured-result-file

## Overview

Bottom-up implementation: first add the `DaytimeResult` dataclass and `save_daytime_result()` atomic-write helper in `state.py` (the shared foundation). Then refactor `run_daytime()` in `daytime_pipeline.py` to wrap its body in a top-level try/except/finally that emits a `daytime-result.json` in every exit path (classification, exception, startup-failure), with `flush=True` on the classification prints and a `DAYTIME_DISPATCH_ID` env-var freshness check. Update `.gitignore` for abandoned tempfiles. Then update the `implement.md §1b` skill instructions to mint a dispatch UUID, write `daytime-dispatch.json` pre-launch, pass the env var on launch, and replace the log-tail classifier with a 3-tier reader (result file + freshness check → `daytime-state.json` discrimination context → log-tail with `outcome: "unknown"`). Finally add test coverage for each exit path, freshness-mismatch, malformed JSON, schema-version mismatch, and tier-3 discriminated messages. Tasks 1 and 5 can run in parallel (pure additions). Task 2 depends on Task 1. Task 3 depends on Task 2. Tasks 4 and 6 depend on Tasks 2 and 3. Task 7 depends on all earlier tasks.

No prior recovery-log history exists for this feature; this is a first-pass implementation.

## Tasks

### Task 1: Add DaytimeResult dataclass and save_daytime_result() in state.py
- **Files**: `claude/overnight/state.py`
- **What**: Add a new `DaytimeResult` dataclass with the 10 fields per spec R2: `schema_version: int`, `dispatch_id: str`, `feature: str`, `start_ts: str`, `end_ts: str`, `outcome: str` (one of `"merged" | "deferred" | "paused" | "failed" | "unknown"`), `terminated_via: str` (one of `"classification" | "exception" | "startup_failure"`), `deferred_files: list[str]`, `error: Optional[str]`, `pr_url: Optional[str]`. Add `save_daytime_result(result: DaytimeResult, path: Path) -> None` that atomically writes the result to JSON. Implementation mirrors `save_batch_result()` at lines 390-437 verbatim: `tempfile.mkstemp(dir=path.parent, prefix=".daytime-result-", suffix=".tmp")` → `os.write(fd, payload)` → `durable_fsync(fd)` → `os.close(fd)` → `os.replace(tmp_path, path)`. Serialize via `dataclasses.asdict()` + `json.dumps(data, indent=2, sort_keys=False) + "\n"`. Wrap in `try/except BaseException` for tempfile cleanup on error per the existing pattern.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing reference at `claude/overnight/state.py:390-437` for `save_batch_result()` is the direct template — same file, same module, same `durable_fsync` from `claude.common`. Follow the existing fd-closed-flag pattern (`closed = False` → set to `True` after `os.close(fd)` → inspect in `except BaseException` handler). Place the new dataclass alongside other dataclasses in the module (near `BatchResult` import area). Place `save_daytime_result()` immediately after `save_batch_result()`. Field ordering in the dataclass must match the spec's 10-field list so `asdict()` produces the expected JSON key order. No changes to `BatchResult` or `OvernightState`. `schema_version` defaults to `1`; callers pass the rest explicitly.
- **Verification**: `just test` passes. `python -c "from claude.overnight.state import DaytimeResult, save_daytime_result; r = DaytimeResult(schema_version=1, dispatch_id='a'*32, feature='x', start_ts='t', end_ts='t', outcome='merged', terminated_via='classification', deferred_files=[], error=None, pr_url=None); import json, tempfile, pathlib; p = pathlib.Path(tempfile.mkdtemp()) / 'r.json'; save_daytime_result(r, p); print(json.load(open(p))['schema_version'])"` prints `1`.
- **Status**: [ ] pending

### Task 2: Refactor run_daytime() with top-level try/except/finally and result-file emission
- **Files**: `claude/overnight/daytime_pipeline.py`
- **What**: Refactor `run_daytime()` (currently lines 247-351) so that everything after `_check_cwd()` is wrapped in a top-level `try: ... except Exception: ... finally: ...` block. Specifically:
  1. Before the top-level `try:`, capture `start_ts = datetime.now(timezone.utc).isoformat()` and call a new helper `_check_dispatch_id()` that reads `DAYTIME_DISPATCH_ID` from env, validates against regex `^[a-f0-9]{32}$`, and returns the env value on success or a freshly-generated `uuid.uuid4().hex` (with `sys.stderr.write` warning) on missing/malformed.
  2. The top-level `try:` begins *after* `_check_cwd()` but *before* the plan-existence check at line 258. All startup checks (plan check, PID guard, `_recover_stale`, `_write_pid`, `build_config`, `create_worktree`) are inside the top-level `try`.
  3. The existing inner `try/except/finally` at lines 307/314/317 is preserved verbatim — it continues to own `_orphan_task.cancel()`, `cleanup_worktree`, and `pid_path.unlink`.
  4. Add `flush=True` kwarg to each classification `print()` call at current lines 324, 329, 331, 337, 348, 350.
  5. Add the top-level `except Exception as e:` clause which records the exception (via `_top_exc = e` and a flag `_terminated_via = "exception"` — if the exception occurred *before* the inner try body entered, it is instead flagged `"startup_failure"`; use a `_startup_phase = True` flag set to `True` initially and flipped to `False` right before `_orphan_task = asyncio.create_task(...)` at line 305 to distinguish these cases).
  6. The top-level `finally:` writes the result file:
     - Compute `outcome` + `terminated_via` from either (a) classification branches in the success path (set `_terminated_via = "classification"` and determine outcome from `ctx.batch_result`), (b) exception-in-body path (`_terminated_via = "exception"`), or (c) startup-failure path (`_terminated_via = "startup_failure"`).
     - Populate `deferred_files` by globbing `lifecycle/{feature}/deferred/*.md` (absolute paths); empty list if directory missing.
     - Populate `pr_url` by calling a new helper `_scan_pr_url(daytime_log_path)` which line-iterates the log file with regex `https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+` and short-circuits on first match; returns the first match or `None`.
     - Populate `error` as `str(_top_exc)` when `_terminated_via ∈ {"exception", "startup_failure"}`, else `None`.
     - Wrap the `save_daytime_result` call in an inner `try/except Exception as write_err` that writes a warning to `sys.stderr` but does NOT re-raise (so the write failure doesn't mask the original exception).
  7. Move the classification branches (lines 322-351) *inside* the top-level `try` so that their prints execute before the outer finally sets up the result-file write. The classification code sets a local variable `_outcome` (e.g., `"merged"`, `"deferred"`, `"paused"`, `"failed"`) which the outer finally reads. Return values (`return 0`, `return 1`) must still flow through correctly — after a `return` statement, Python evaluates the outer `finally`, so the result file is written on every return path.
  8. Preserve the `_orphan_task.cancel()` as the FIRST statement in the inner finally (already the case — just verify in review).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: The current structure at `claude/overnight/daytime_pipeline.py:247-351` must be restructured while preserving all existing behavior. Critical invariants per spec R3: (a) `_check_cwd()` stays outside the top-level try (it calls `sys.exit(1)` which cannot be meaningfully caught); (b) the catch clause uses `except Exception` (broad) to catch both current `subprocess.CalledProcessError` from `create_worktree` AND the post-#094 `ValueError` per spec Edge Cases; (c) the inner try/finally at line 307/317 must survive intact for orphan-task-cancel / worktree-cleanup / pid-unlink. Imports needed: `uuid`, `re`, `datetime` (already imported), and `DaytimeResult`/`save_daytime_result` from `claude.overnight.state`. The helper `_check_dispatch_id()` and `_scan_pr_url()` should be module-level functions, not nested inside `run_daytime`. PR-URL regex: `https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+` — use `re.compile()` at module scope, iterate file line-by-line with `open(..., encoding="utf-8", errors="replace")`, short-circuit on first match. The daytime-log path for PR scan is `Path(f"lifecycle/{feature}/daytime.log")` — if the file doesn't exist or is unreadable, return `None` gracefully. Ensure `flush=True` is applied to all six classification print sites (spec R5 says ≥ 5; six exist in the source). Consider extracting the outcome-determination logic into a small helper `_classify_outcome(ctx, feature) -> tuple[str, str]` returning `(outcome, print_message)` — but this is optional if the inline branches are more readable. The startup_phase boolean is the simplest way to discriminate startup-failure from exception-in-body without restructuring the try into two nested tries.
- **Verification**: `just test` passes. `grep -nE 'except Exception' claude/overnight/daytime_pipeline.py` returns ≥ 1 hit inside `run_daytime`. `grep -c 'flush=True' claude/overnight/daytime_pipeline.py` returns ≥ 5. `grep -n 'DAYTIME_DISPATCH_ID' claude/overnight/daytime_pipeline.py` returns ≥ 1 hit. `grep -n '_check_dispatch_id\|_scan_pr_url' claude/overnight/daytime_pipeline.py` returns ≥ 2 hits. `grep -n 'save_daytime_result' claude/overnight/daytime_pipeline.py` returns ≥ 1 hit.
- **Status**: [ ] pending

### Task 3: Add .gitignore coverage for abandoned tempfiles
- **Files**: `.gitignore`
- **What**: Add two lines to the repo-root `.gitignore`: `lifecycle/*/.daytime-result-*.tmp` and `lifecycle/*/.daytime-dispatch-*.tmp`. These cover abandoned tempfiles from interrupted subprocess or skill atomic-write operations. Group them near any existing `lifecycle/` ignore rules if present, otherwise add a new section with a brief comment (`# Abandoned tempfiles from interrupted atomic writes in daytime pipeline`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Spec R8 explicitly calls out `lifecycle/*/.daytime-result-*.tmp` as required. The dispatch-file tempfile pattern `.daytime-dispatch-*.tmp` is also per the spec's Technical Constraints: "Same pattern for `daytime-dispatch.json` (skill-side)." Inspect the existing `.gitignore` to choose the correct section.
- **Verification**: `grep -n '\.daytime-result-' .gitignore` returns ≥ 1 match. `grep -n '\.daytime-dispatch-' .gitignore` returns ≥ 1 match.
- **Status**: [ ] pending

### Task 4: Update implement.md §1b to mint DAYTIME_DISPATCH_ID and replace classifier with 3-tier reader
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Modify §1b in three places:
  1. **§1b iv (launch protocol)** — before the subprocess launch Bash call, add two preparatory Bash calls: (a) mint a uuid: `python3 -c 'import uuid; print(uuid.uuid4().hex)'` (stash the value into conversation memory as the active `dispatch_id` for the current feature); (b) write `lifecycle/{slug}/daytime-dispatch.json` via a `python3 -c` one-liner that atomically writes `{"schema_version": 1, "dispatch_id": "<uuid>", "feature": "<slug>", "start_ts": "<ISO 8601>", "pid": null}` using `tempfile.mkstemp` + `os.replace` in the same directory as the target. Prefix the launch command with `DAYTIME_DISPATCH_ID={uuid}` env var. After the launch Bash call returns and the PID file has been written, issue a third Bash call that does a second atomic write updating the `pid` field in `daytime-dispatch.json` to the subprocess PID (re-read the JSON, mutate `pid`, write atomically). Do NOT add `PYTHONUNBUFFERED=1` to the launch command.
  2. **§1b vii (result surfacing)** — replace the entire log-tail classifier with a 3-tier reader:
     - **Tier 1 (`daytime-result.json`)**: `cat lifecycle/{slug}/daytime-result.json` → parse JSON. If missing, malformed, or `schema_version != 1` → fall to tier 2. Read `dispatch_id` from `daytime-dispatch.json` (via a separate Bash `cat` call) and compare to the result's `dispatch_id`. On mismatch → fall to tier 2 (stale prior-run file). On match: classify from `outcome` + `terminated_via` + `error` + `pr_url` + `deferred_files`. On success (tier-1 read passes validation and freshness check), delete `daytime-dispatch.json` to mark the dispatch consumed.
     - **Tier 2 (`daytime-state.json` as discrimination context)**: Does NOT classify the outcome — instead reads `phase` field to determine which discriminated tier-3 message to emit. `phase == "complete"` (terminal) → "subprocess likely completed but result file is missing or invalid"; `phase == "executing"` or other non-terminal → "subprocess did not complete"; file absent → "subprocess never started."
     - **Tier 3 (surface `outcome: "unknown"` with discriminated message)**: Display the appropriate tier-2-discriminated message to the user, then display the last 20 lines of `daytime.log`. Do NOT silently classify as `failed`. The classification that flows into §1b viii's `dispatch_complete` event is `outcome: "unknown"`.
     - Document the hard schema-version equality check (`schema_version == 1`; no "greater than" branch).
     - Document that if `daytime-dispatch.json` is missing at polling time, tier-1 cannot validate → falls to tier-2/tier-3.
  3. **§1b viii (dispatch_complete event)** — extend the `outcome` field's enumeration to include `"unknown"`. Map tier-1 outcomes directly (`merged` → `complete`, `deferred` → `deferred`, `paused` → `paused`, `failed` → `failed`), and tier-3's unknown → `unknown`.
  Keep the existing §1b i/ii/iii/v/vi content unchanged.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: The current §1b vii is at `skills/lifecycle/references/implement.md:157-164`; the `dispatch_complete` event template is at line ~169. Atomic-write pattern for the skill (Bash-invoked): use a `python3 -c` heredoc-safe one-liner, e.g., `python3 -c 'import json, os, sys, tempfile; d = sys.argv[1]; data = {"schema_version": 1, "dispatch_id": sys.argv[2], "feature": sys.argv[3], "start_ts": sys.argv[4], "pid": None}; fd, tmp = tempfile.mkstemp(dir=d, prefix=".daytime-dispatch-", suffix=".tmp"); os.write(fd, (json.dumps(data, indent=2) + "\n").encode()); os.fsync(fd); os.close(fd); os.replace(tmp, os.path.join(d, "daytime-dispatch.json"))'`. The Bash call template should avoid shell metacharacter ambiguity by passing UUID as a quoted positional arg. When the skill re-enters after compaction, it reads `daytime-dispatch.json` to recover `dispatch_id` — document this in §1b vii as "the skill MAY cache the UUID in conversation memory for speed, but the disk file is authoritative." Deletion of `daytime-dispatch.json` after tier-1 success is a single `rm lifecycle/{slug}/daytime-dispatch.json` Bash call. The three tier-3 discriminated messages per spec R6 must each appear verbatim in §1b vii. Acceptance requires `grep -c 'unknown' skills/lifecycle/references/implement.md` ≥ 3.
- **Verification**: `grep -c 'unknown' skills/lifecycle/references/implement.md` returns ≥ 3. `grep 'PYTHONUNBUFFERED' skills/lifecycle/references/implement.md` returns no match. `grep -n 'daytime-result.json' skills/lifecycle/references/implement.md` returns ≥ 2 hits (§1b vii). `grep -n 'daytime-dispatch.json' skills/lifecycle/references/implement.md` returns ≥ 3 hits (§1b iv, §1b vii). `grep -n 'DAYTIME_DISPATCH_ID' skills/lifecycle/references/implement.md` returns ≥ 1 hit (§1b iv). `grep -n 'schema_version' skills/lifecycle/references/implement.md` returns ≥ 1 hit.
- **Status**: [ ] pending

### Task 5: Add subprocess-side tests for every exit path in test_daytime_pipeline.py
- **Files**: `claude/overnight/tests/test_daytime_pipeline.py`
- **What**: Add a new test class `TestDaytimeResultFile` covering:
  - **merged** — mock `apply_feature_result` to populate `ctx.batch_result.features_merged` with the feature; assert `daytime-result.json` is written with `outcome="merged"`, `terminated_via="classification"`, `error=None`.
  - **deferred with file** — same mock pattern, populate `features_deferred`, pre-create a file under `deferred_dir/x.md`; assert `outcome="deferred"`, `deferred_files=[absolute_path]`, `terminated_via="classification"`.
  - **paused** — populate `features_paused`; assert `outcome="paused"`, `terminated_via="classification"`.
  - **failed with error** — populate `features_failed` with `{"name": feature, "error": "msg"}`; assert `outcome="failed"`, `error="msg"` (or the full formatted message), `terminated_via="classification"`.
  - **exception-in-body** — mock `execute_feature` to raise `RuntimeError("boom")`; assert `outcome="failed"`, `terminated_via="exception"`, `error` contains `"boom"`.
  - **startup-failure with post-#094 exception shape** — mock `create_worktree` to raise `ValueError("worktree_creation_failed: stderr")`; assert `outcome="failed"`, `terminated_via="startup_failure"`, `error` contains `"worktree_creation_failed"`.
  - **startup-failure with pre-#094 exception shape** — mock `create_worktree` to raise `subprocess.CalledProcessError(returncode=128, cmd=["git"])`; assert `outcome="failed"`, `terminated_via="startup_failure"`, result file still valid (pins R3's type-robustness across both exception types).
  - **PID-guard startup failure** — create a fake `daytime.pid` file pointing to a live PID before invoking `run_daytime`; assert startup exits with return 1, and note: per the current code path, PID-guard returns 1 without raising (so no result file is expected UNLESS the refactor moves this check inside the top-level try). Verify actual behavior against Task 2's implementation: if the PID-guard path writes a result file, assert `terminated_via="startup_failure"`; if it returns 1 without writing (existing behavior preserved via early-return before the try), assert no result file. Document whichever matches Task 2's code.
  - **DAYTIME_DISPATCH_ID missing** — unset env var (`monkeypatch.delenv("DAYTIME_DISPATCH_ID", raising=False)`); assert subprocess generates its own 32-hex-char `dispatch_id` and writes a valid result file; assert a warning was written to stderr (capsys capture).
  - **DAYTIME_DISPATCH_ID malformed** — set `DAYTIME_DISPATCH_ID="not-a-uuid!"`; assert subprocess rejects at regex, generates its own UUID, writes valid result; stderr contains warning.
  Each test uses `tmp_path` fixture, `monkeypatch.chdir(tmp_path)`, creates `lifecycle/{feature}/plan.md` and `deferred/` dir, and reads `lifecycle/{feature}/daytime-result.json` post-run via `json.load(path.open())` for assertions. Mock `create_worktree` and `cleanup_worktree` to avoid actual git operations (follow the existing pattern in `TestRunDaytimeRouting`).
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Existing test class `TestRunDaytimeRouting` at `claude/overnight/tests/test_daytime_pipeline.py` already demonstrates the mocking pattern for `execute_feature`, `apply_feature_result`, `create_worktree`, and `cleanup_worktree`. Use `asyncio.run(run_daytime(...))` or `pytest-asyncio` to invoke the coroutine. Use `monkeypatch.setenv("DAYTIME_DISPATCH_ID", "a" * 32)` for tests that want a deterministic dispatch id; capture stderr via `capsys`. For the PR-URL field, most tests can pass an empty or missing `daytime.log` (resulting in `pr_url=None`); optionally add one subtest that pre-creates a `daytime.log` containing a GitHub PR URL and asserts `pr_url` is populated. For the CalledProcessError test, import `subprocess` and construct `subprocess.CalledProcessError(128, ["git"])`. Wrap all tests in `pytest.mark.asyncio` as appropriate.
- **Verification**: `just test` passes. The new test class `TestDaytimeResultFile` exists in the test file. `python -m pytest claude/overnight/tests/test_daytime_pipeline.py::TestDaytimeResultFile -v` reports all subtests passing.
- **Status**: [ ] pending

### Task 6: Add skill-side reader tests for 3-tier fallback
- **Files**: `claude/overnight/tests/test_daytime_result_reader.py` (new)
- **What**: Create a new test module that validates the tier-1/tier-2/tier-3 fallback logic as pure-Python helpers. Since the 3-tier reader lives in skill markdown (not executable code), this task extracts its classification logic into testable Python helpers under `claude/overnight/` (e.g., `claude/overnight/daytime_result_reader.py` with a `classify_result(result_path, dispatch_path, state_path, log_path) -> tuple[str, str]` function returning `(outcome, message)`). The helper is the same logic the skill executes in Bash, implemented in Python for testability (the skill's `python3 -c` one-liners can call this module if desired, but this is not required for the MVP — the helper exists primarily as a testable surface).
  Tests cover:
  - **Tier-1 success** — write a valid `daytime-result.json` and matching `daytime-dispatch.json`; assert the helper returns `(outcome="merged", ...)` (or whatever the fixture encodes).
  - **Freshness mismatch** — `daytime-result.json` has `dispatch_id=Y`, `daytime-dispatch.json` has `dispatch_id=X`; assert helper falls to tier-2.
  - **`daytime-dispatch.json` missing** — only the result file exists; assert helper cannot validate and falls to tier-2.
  - **`schema_version != 1`** — fixture with `schema_version: 99`; assert helper falls to tier-2.
  - **Missing `schema_version`** — fixture without the field; assert helper falls to tier-2.
  - **Malformed JSON** — write a truncated result file (`"{"` alone); assert helper falls to tier-2 without raising.
  - **Tier-2 terminal phase** — result absent, `daytime-state.json` has `phase="complete"`; assert message is "Subprocess likely completed but its result file is missing or invalid..."
  - **Tier-2 non-terminal phase** — result absent, `daytime-state.json` has `phase="executing"`; assert message is "Subprocess did not complete..."
  - **Tier-2 state file absent** — no result, no state; assert message is "Subprocess never started (pre-flight failure)..."
  All three tier-3 discriminated messages must be asserted verbatim against the spec's R6 text so that implement.md and the helper stay in sync.
  If extracting the helper is not desirable (adds a module and cross-surface coupling), an alternative is to test the skill's `python3 -c` one-liner directly via `subprocess.run`, feeding fixtures through filesystem setup and parsing stdout. The helper-module approach is preferred because it tests classification logic in isolation.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: This task creates a small parallel surface (`daytime_result_reader.py`) that the skill's Bash in §1b vii may optionally invoke. The helper's purpose is to give the classification logic a unit-test boundary — otherwise the 3-tier design is only validated by integration, which is expensive and fragile. The helper signature: `def classify_result(feature_slug: str, lifecycle_root: Path = None) -> dict` returning `{"outcome": str, "terminated_via": Optional[str], "message": str, "source_tier": int, "pr_url": Optional[str], "deferred_files": list[str], "error": Optional[str], "log_tail": Optional[str]}`. The skill can call this via `python3 -m claude.overnight.daytime_result_reader --feature {slug}` in a Bash call during §1b vii, simplifying the skill markdown. Log-tail is read from `lifecycle/{slug}/daytime.log` when tier-3 is reached. Return-type is a dict (JSON-serializable) so the skill can `jq` or directly display fields. This helper consolidates the spec R6/R7 schema-version check, freshness-token validation, phase discrimination, and log-tail reading in one audit-point.
- **Verification**: `just test` passes. `python -m pytest claude/overnight/tests/test_daytime_result_reader.py -v` reports all subtests passing. `python -c "from claude.overnight.daytime_result_reader import classify_result; print('ok')"` succeeds.
- **Status**: [ ] pending

### Task 7: Update implement.md §1b vii to invoke the daytime_result_reader helper
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: If Task 6 chose the helper-module approach, update §1b vii to invoke `python3 -m claude.overnight.daytime_result_reader --feature {slug}` via a single Bash call, parse the JSON output, and surface to the user accordingly. This simplifies §1b vii from multiple Bash calls (cat + jq + cat + jq + tail) into one Python invocation that returns a structured result. Keep the ordered behavior description in §1b vii but replace the per-tier Bash calls with the single helper invocation. If Task 6 chose the Bash-one-liner approach instead, skip this task entirely (Task 4 already encoded the logic).
- **Depends on**: [4, 6]
- **Complexity**: simple
- **Context**: Adjust §1b vii's structure so the skill reads a single JSON blob from the helper rather than coordinating three tiers inline. The helper's dict output fields directly map to the user-surfaced message components: `outcome`, `message`, `pr_url`, `deferred_files`, `log_tail`. The skill still interprets `outcome` (for success / paused / deferred / failed / unknown) and formats the display. The `dispatch_complete` event's `outcome` field is populated from the helper's `outcome` field directly.
- **Verification**: `grep -n 'daytime_result_reader' skills/lifecycle/references/implement.md` returns ≥ 1 match (if the helper approach is used). `grep -n 'python3 -m claude.overnight.daytime_result_reader' skills/lifecycle/references/implement.md` returns ≥ 1 match. Skill markdown remains internally consistent with Task 4's §1b iv protocol (dispatch file written pre-launch; env var passed on launch).
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete:

1. **Automated test suite**: `just test` must pass with 0 failures. This exercises `TestDaytimeResultFile` (Task 5) covering every run_daytime exit path and freshness-token handling, plus `test_daytime_result_reader.py` (Task 6) covering the 3-tier fallback logic.

2. **Grep audits** — these all reference code the tasks produce but are checked against spec acceptance criteria:
   - `grep -c 'flush=True' claude/overnight/daytime_pipeline.py` returns ≥ 5 (spec R5).
   - `grep -nE 'except Exception' claude/overnight/daytime_pipeline.py` shows ≥ 1 hit inside `run_daytime` (spec R3).
   - `grep -n 'DAYTIME_DISPATCH_ID' claude/overnight/daytime_pipeline.py` shows ≥ 1 hit (spec R4).
   - `grep -n '\.daytime-result-' .gitignore` returns ≥ 1 match (spec R8).
   - `grep 'PYTHONUNBUFFERED' skills/lifecycle/references/implement.md` returns no match (spec R5).
   - `grep -c 'unknown' skills/lifecycle/references/implement.md` returns ≥ 3 (spec R6).

3. **Schema spot-check** — write a minimal Python one-liner that constructs a `DaytimeResult` with all 10 fields, saves it, reads it back with `jq 'keys | sort'`, and confirms the 10 keys match the spec's ordered list (`deferred_files`, `dispatch_id`, `end_ts`, `error`, `feature`, `outcome`, `pr_url`, `schema_version`, `start_ts`, `terminated_via`). This is a one-time manual check during plan execution.

4. **Integration smoke test** — after implementation, run `/lifecycle implement` on a trivially-complete feature (e.g., a feature whose plan has one no-op task) via the daytime path. Verify:
   - `lifecycle/{slug}/daytime-dispatch.json` appears during launch and is deleted after result surfacing.
   - `lifecycle/{slug}/daytime-result.json` is written with `schema_version=1`, matching `dispatch_id`, and the correct outcome.
   - The skill surfaces the outcome from the result file, not from log-tail substrings.
   - No `.tmp` orphans remain in `lifecycle/{slug}/`.

5. **Dispatch-completion event**: after the integration test above, confirm `lifecycle/{slug}/events.log` contains a `dispatch_complete` event whose `outcome` field is one of `"complete" | "deferred" | "paused" | "failed" | "unknown"` (per Task 4's enumeration extension).
