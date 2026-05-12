# Specification: replace-daytime-log-sentinel-classification-with-structured-result-file

## Problem Statement

The daytime pipeline's end-of-run classifier reads the last line of `daytime.log` that begins with `"Feature "` and matches substrings (`merged successfully` / `deferred` / `paused` / `failed`). This is brittle against SIGKILL/OOM (unflushed stdout lost), log rotation, subprocess-own crash in the print path (the `finally` block runs *before* the final print, so cleanup happens and then the print is lost), and main-session crash + restart (the next invocation reads a prior run's line as current). The one observed daytime dispatch in repo history (lifecycle-69, 2026-04-17) failed during `create_worktree()` startup — *before* the classifier block could execute — and the exit-128 traceback was misclassified as a generic failure with no actionable detail. Replace the log-sentinel classifier with an atomically-written structured result file (`lifecycle/{slug}/daytime-result.json`) stamped with a per-dispatch freshness token, consumed by the skill via a 3-tier fallback, where the startup-failure path also produces a valid result file. Benefit: correct classification under every failure mode the current design loses data on; file-presence + freshness-token semantics let the skill distinguish stale prior-run results from current ones; the enhanced tier-3 discriminates "subprocess completed but result-write failed" from "subprocess didn't complete" using `daytime-state.json` as a disambiguation signal rather than a parallel classification tier.

## Requirements

1. **Atomic result-file write at end-of-run.**
   - **Acceptance**: After any completed `run_daytime()` execution (merged, deferred, paused, failed, or exception-in-body), `lifecycle/{slug}/daytime-result.json` exists and is valid JSON. Binary check: `test -f lifecycle/{slug}/daytime-result.json && python3 -m json.tool < lifecycle/{slug}/daytime-result.json > /dev/null` exits 0.
   - **Atomicity primitive**: tempfile in the same directory → `os.write` → `durable_fsync(fd)` → `os.close` → `os.replace(tmp, final)`. Follows `save_batch_result()` at `claude/overnight/state.py:390–437` verbatim; new helper `save_daytime_result()` lives alongside it.

2. **Result-file schema (v1), 10 fields.**
   - `schema_version: 1` (int, required)
   - `dispatch_id: str` (32-char lowercase hex, uuid4 — from the `DAYTIME_DISPATCH_ID` env var per R6)
   - `feature: str` (the feature slug)
   - `start_ts: str` (ISO 8601, captured in the subprocess at `run_daytime` entry)
   - `end_ts: str` (ISO 8601, captured at write time)
   - `outcome: "merged" | "deferred" | "paused" | "failed" | "unknown"`
   - `terminated_via: "classification" | "exception" | "startup_failure"`
   - `deferred_files: list[str]` (absolute paths under `lifecycle/{slug}/deferred/`, empty if none)
   - `error: str | null` (populated when `terminated_via ∈ {exception, startup_failure}`, else null)
   - `pr_url: str | null` (first match of `https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+` scanned over full `daytime.log`; null if none)
   - **Acceptance**: `jq 'keys | sort' lifecycle/{slug}/daytime-result.json` lists the 10 keys verbatim. `jq -e '.schema_version == 1 and (.dispatch_id | test("^[a-f0-9]{32}$")) and (.outcome as $o | ["merged","deferred","paused","failed","unknown"] | index($o))' lifecycle/{slug}/daytime-result.json` exits 0.

3. **Top-level try/finally wraps `run_daytime` body including all startup checks except `_check_cwd`.**
   - The `try:` boundary begins *after* `_check_cwd` (which calls `sys.exit(1)` and cannot be meaningfully caught) but *before* the plan-existence check, PID guard, `_recover_stale`, `_write_pid`, `build_config`, and `create_worktree`. Any exception from these produces a result file with `terminated_via: "startup_failure"` and `error` populated from the exception.
   - Catch clause: `except Exception` (broad, type-robust). This guards against a sibling ticket (#094) changing `create_worktree`'s raised exception type from `subprocess.CalledProcessError` to `ValueError`.
   - The inner try/except/finally at current lines 307/314/317 is preserved for its orphan-task-cancel / worktree-cleanup / pid-unlink responsibilities; it no longer owns result-file semantics.
   - The outer finally writes the result file, wrapped in its own inner try/except so a write failure logs to stderr but does not mask the original exception.
   - **Acceptance**: Read `run_daytime()` — the outermost `try:` precedes the plan-existence check. `grep -E 'except Exception' claude/overnight/daytime_pipeline.py` returns ≥ 1 hit in `run_daytime`. The outer `finally:` block contains the result-file write.

4. **`DAYTIME_DISPATCH_ID` freshness-token plumbing with on-disk persistence.**
   - Skill mints a uuid4 hex (32 chars) pre-launch via `python3 -c 'import uuid; print(uuid.uuid4().hex)'`.
   - Skill writes `lifecycle/{slug}/daytime-dispatch.json` immediately before launching the subprocess, via the same atomic-write primitive (tempfile + `os.replace`). Contents: `{"schema_version": 1, "dispatch_id": "<uuid>", "feature": "<slug>", "start_ts": "<ISO 8601>", "pid": null}`. After subprocess launch, skill updates `pid` to the subprocess PID via a second atomic write (the PID is not known until post-launch).
   - Skill's launch command: `DAYTIME_DISPATCH_ID={uuid} python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > lifecycle/{slug}/daytime.log 2>&1`.
   - Subprocess reads `DAYTIME_DISPATCH_ID` from environment at `run_daytime` entry; validates against regex `^[a-f0-9]{32}$`; on malformed or missing value, generates its own uuid4 (preserves direct-CLI-invocation debugging) and logs a warning to stderr.
   - Subprocess's classification / exception / startup_failure code paths echo `dispatch_id` into the result file.
   - At result-surfacing time the skill reads `daytime-dispatch.json` (the on-disk authoritative source) to recover the active `dispatch_id`. The skill MAY cache the UUID in conversation memory for speed, but the disk file is authoritative. This closes the conversation-compaction / skill-restart hole — a re-entered skill polls by reading `daytime-dispatch.json` first, not by trusting in-memory state.
   - After the skill successfully reads and validates the result file (tier-1 success), the skill deletes `daytime-dispatch.json` to mark the dispatch as consumed.
   - **Acceptance**: `implement.md §1b` documents the dispatch-file write (pre-launch), the env-var-prefixed launch command, and the dispatch-file read on polling. Subprocess code: `grep -n 'DAYTIME_DISPATCH_ID' claude/overnight/daytime_pipeline.py` returns ≥ 1 hit; the validation regex `^[a-f0-9]{32}$` appears in code. The presence of `lifecycle/{slug}/daytime-dispatch.json` after launch and its absence after successful tier-1 read are both observable.

5. **Targeted `flush=True` on classification prints; no `PYTHONUNBUFFERED`.**
   - Add `flush=True` to the classification `print()` call sites (currently lines 324, 329, 331, 337, 348, 350).
   - Do NOT add `PYTHONUNBUFFERED=1` to the skill's launch command. Rationale: once the result file is authoritative, print durability is decorative; PYTHONUNBUFFERED imposes per-line syscall overhead on verbose multi-hour runs and provides no correctness benefit.
   - **Acceptance**: `grep -c 'flush=True' claude/overnight/daytime_pipeline.py` ≥ 5. `grep 'PYTHONUNBUFFERED' skills/lifecycle/references/implement.md` returns no match.

6. **Skill-side 3-tier fallback in `implement.md §1b vii` with enhanced tier-3 discrimination.**
   - **Tier 1 — `daytime-result.json`**: parse JSON; if `schema_version` ≠ 1, fall to tier 2. Compare `dispatch_id` to the `dispatch_id` read from `daytime-dispatch.json`. On match: classify from `outcome` + `terminated_via` + `error` + `pr_url` + `deferred_files`. On mismatch: treat as stale, fall to tier 2.
   - **Tier 2 — discrimination context from `daytime-state.json`**: does NOT classify outcome; instead provides disambiguation for tier-3's message to the user. Read top-level `phase` field:
     - `phase == "complete"` (or otherwise terminal): the subprocess reached terminal state; result file was likely lost in-flight.
     - `phase == "executing"` or non-terminal: the subprocess did not reach terminal state.
     - file absent: the subprocess never reached `build_config` (pre-try startup failure excluded by R3, or directory never created).
   - **Tier 3 — surface `outcome: "unknown"` with discriminated message**: the skill's final surface to the user. Presentation depends on the tier-2 context:
     - tier-2 terminal → "Subprocess likely completed but its result file is missing or invalid. Check `lifecycle/{slug}/daytime.log` for the final outcome."
     - tier-2 non-terminal → "Subprocess did not complete (still running, killed, or crashed mid-execution). Check `lifecycle/{slug}/daytime.log`."
     - tier-2 absent → "Subprocess never started (pre-flight failure). Check `lifecycle/{slug}/daytime.log`."
   - Tier-3 displays the last 20 lines of `daytime.log` in all three cases and does NOT silently classify as `failed`.
   - `dispatch_complete` event's `outcome` field enumeration extends to include `"unknown"` for tier-3 surfaces.
   - **Acceptance**: `implement.md §1b vii` documents all three tiers with the behaviors above. `grep -c 'unknown' skills/lifecycle/references/implement.md` ≥ 3 (tier-3 outcome, dispatch_complete enumeration, and at least one of the three discriminated messages).

7. **Schema-version check.**
   - Reader checks `schema_version` exactly equals `1`. Any other value (including missing, null, or a future version) falls to tier-2. No future-proofing branch in this version of the spec.
   - **Acceptance**: `implement.md §1b vii` documents the hard equality check. Reader code does not have a "greater than" branch.

8. **`.gitignore` coverage for abandoned tempfiles.**
   - `.gitignore` at repo root adds the line: `lifecycle/*/.daytime-result-*.tmp`.
   - No runtime sweep of stale tempfiles in this MVP. Rationale: the atomic-write window is sub-millisecond and the single observed daytime dispatch in repo history does not justify sweep code. `.gitignore` is sufficient hygiene.
   - **Acceptance**: `grep -n '\.daytime-result-' .gitignore` returns ≥ 1 match.

9. **Test coverage.**
   - New tests (`claude/overnight/tests/test_daytime_pipeline.py` or a new `test_daytime_result_file.py` module):
     - merged → result file has `outcome: "merged"`, `terminated_via: "classification"`
     - deferred with file → `outcome: "deferred"`, `deferred_files: [path]`
     - paused → `outcome: "paused"`, `terminated_via: "classification"`
     - failed with error → `outcome: "failed"`, `terminated_via: "classification"`, `error` populated
     - exception in try body → `outcome: "failed"`, `terminated_via: "exception"`, `error` contains exception text
     - startup_failure with post-#094 exception shape — mock `create_worktree` to raise `ValueError("worktree_creation_failed: stderr text")` → result file has `outcome: "failed"`, `terminated_via: "startup_failure"`, `error` contains the formatted message
     - startup_failure with the current exception shape — mock `create_worktree` to raise `subprocess.CalledProcessError` → still classified as `startup_failure` because `except Exception` catches both (this test pins R3's type-robustness)
     - PID-guard startup failure — mock `recover_stale` or PID-guard to reject → result file has `terminated_via: "startup_failure"`
     - `DAYTIME_DISPATCH_ID` missing in env → subprocess generates its own uuid4, logs warning, result file still valid
     - `DAYTIME_DISPATCH_ID` malformed (contains shell metacharacters or wrong length) → subprocess rejects at validation regex, generates fresh uuid4, logs error
     - Freshness mismatch — skill-side test: `daytime-dispatch.json` says dispatch_id X; `daytime-result.json` has dispatch_id Y; tier-1 rejects and falls to tier-2
     - `daytime-dispatch.json` missing at polling time (compaction / restart before write completed) — skill-side test: reader falls to tier-3 with appropriate discrimination message
     - `schema_version` ≠ 1 — fixture with `schema_version: 99` or missing → reader falls to tier-2
     - Malformed JSON — fixture with truncated or invalid JSON → reader falls to tier-2
     - Tier-3 discrimination — three fixtures matching the three tier-2 states; verify three discriminated messages
     - Atomicity — kill subprocess mid-tempfile-write; verify no partial `daytime-result.json` visible to reader (only the tempfile exists, then gets cleaned on next subprocess launch by git's `-unpack` or is invisible to the skill since it's ignored)
   - **Acceptance**: `just test` exits 0. The new tests exist and run.

## Non-Requirements

- **`bin/daytime-status` CLI is not built in this ticket.** Inline rendering in the skill's §1b vii is the MVP. A dedicated CLI mirroring `bin/overnight-status` is deferred to a follow-up ticket.
- **`rework_cycles`, `tasks_completed`, and `commits` are not fields in the v1 schema.** Their primary consumer is `bin/daytime-status` (deferred) and the morning report; no skill surface displays them in this ticket. They are deferred to the same follow-up that introduces the CLI.
- **Terminal `save_state()` call in `run_daytime` is not added.** The tier-3 discrimination built from `phase` reads state as it exists today (written only at startup, so non-terminal throughout); tier-3's "subprocess did not complete" message covers this correctly. Adding a terminal state-write adds a new mutation path with its own failure modes and is deferred.
- **Best-effort orphan-guard result-file write is not added.** Orphan-guard firing is unobserved in repo history; tier-3's "subprocess did not complete" message handles the orphan case adequately via absent-file + non-terminal state. Deferred to the follow-up that introduces `bin/daytime-status`.
- **Runtime sweep of stale `.daytime-result-*.tmp` files is not added.** `.gitignore` is sufficient hygiene for the observed failure rate.
- **Schema-version forward-compatibility is not added.** `schema_version == 1` is a hard check; any other value routes to tier-2. The system has no v2 roadmap; future-proofing is YAGNI.
- **`PYTHONUNBUFFERED=1` is not added to the launch.** Explicitly rejected per R5.
- **`LIFECYCLE_SESSION_ID` is not reused as the freshness token.** Explicitly rejected — it is per Claude CLI session, not per dispatch. R4 introduces the per-dispatch replacement.
- **No new fields on `BatchResult` or `FeatureResult` dataclasses.** The 10 schema fields are populated from existing data (env var, ctx.batch_result, glob of deferred_dir, regex scan of daytime.log). The shared pipeline data model is not modified.
- **No changes to `execute_feature` or `apply_feature_result`.** Scope is confined to `run_daytime`.
- **No changes to the `implement.md §1` pre-flight.** That is the scope of sibling ticket #096, not this one.
- **No log-rotation handling.** No rotation exists for `daytime.log` today.
- **No `dispatch_id` field added to `implementation_dispatch` or `dispatch_complete` events.** Recovery of the active dispatch_id is via `daytime-dispatch.json` on disk, not via parsing events.log. This avoids cross-skill event-schema coupling and the multi-dispatch ambiguity that tail-reading events would introduce. The `dispatch_complete` event's `outcome` enumeration extension to include `"unknown"` is the only cross-skill schema change, and it is backwards-compatible.
- **No changes to the orphan guard's trigger condition or action.** Its `os.getppid() == 1` check and `cleanup_worktree` + `os._exit(1)` behavior are unchanged.
- **No backwards-compatibility layer for consumers of a pre-existing `daytime-result.json`.** Brand-new file; no prior version exists.

## Edge Cases

- **SIGKILL before the result-file write begins**: no `daytime-result.json` exists; `daytime-dispatch.json` still exists on disk. Skill's tier-1 sees absent file → tier-2 reads `daytime-state.json` → tier-3 reports "subprocess did not complete" with log tail.
- **SIGKILL during tempfile write**: `.daytime-result-*.tmp` orphaned in the directory (ignored by git per R8); real path absent. Skill's next read: tier-1 absent → tier-2 → tier-3 "subprocess did not complete."
- **Exception raised by the result-file write itself (disk full, permission error)**: wrapped in try/except inside the outer finally; the original exception from the body is preserved via Python's implicit exception chaining; inner-finally cleanup (`cleanup_worktree`, `pid_path.unlink`) still completes. Result-write failure logged to stderr (captured in `daytime.log`). Skill sees absent file → tier-2 → tier-3 "subprocess likely completed but result file is missing or invalid" (tier-2 reports non-terminal phase because R5's terminal save_state is explicitly deferred, so this message is as specific as tier-3 can be — which is adequate).
- **Startup failure with post-#094 exception shape** (`create_worktree` raises `ValueError("worktree_creation_failed: {stderr}")`): outer `except Exception` catches; result file written with `terminated_via: "startup_failure"`, `outcome: "failed"`, `error` = `str(exc)` (which embeds stderr per #094's format). No separate "surfaceable stderr" handling is needed — #094's exception message is the single source.
- **Startup failure with pre-#094 exception shape** (`create_worktree` raises `subprocess.CalledProcessError`): outer `except Exception` catches; result file written with `terminated_via: "startup_failure"`, `outcome: "failed"`, `error` = `str(exc)` (which, pre-#094, is the misleading "returned non-zero exit status 128" — accepted; this is the bug #094 will fix).
- **Pre-try startup failure** (plan-missing, PID guard rejects, `_recover_stale` raises, `_write_pid` raises, `build_config` raises): the outer try boundary per R3 includes these, so the outer `except Exception` catches and produces a result file with `terminated_via: "startup_failure"`.
- **`_check_cwd` failure**: this is outside the outer try (it calls `sys.exit(1)` and cannot be meaningfully caught); no result file is produced. Skill's tier-1 absent → tier-2 (state file also likely absent since `build_config` never ran) → tier-3 "subprocess never started."
- **Main session crash during polling + user restart**: subprocess A is still running; user restarts `/lifecycle`. Skill B reads `daytime-dispatch.json` from disk and recovers A's `dispatch_id` — this is the central benefit of persisting the dispatch identity to disk rather than conversation memory. Skill B then polls normally; when A completes, tier-1 reads A's result with matching `dispatch_id` and classifies correctly.
- **`daytime-dispatch.json` missing at polling time**: the skill never launched the subprocess, OR the skill launched but the dispatch-file write failed, OR the file was prematurely deleted. In all three cases, the skill has no authoritative dispatch_id → tier-1 cannot validate → tier-2 → tier-3 reports subprocess state based on `daytime-state.json`.
- **`daytime-result.json` present but `dispatch_id` doesn't match `daytime-dispatch.json`'s dispatch_id**: prior-run file that wasn't cleaned up. Skill treats as stale, falls to tier-2.
- **Concurrent dispatches for different features** (two different slugs): each has its own `daytime-dispatch.json` and `daytime-result.json`; no contention.
- **Concurrent dispatches for the same feature**: prevented by the existing subprocess-level PID guard at `daytime_pipeline.py:274` — the second dispatch fails at startup with `terminated_via: "startup_failure"`, `error: "another dispatch is already running (pid N)"`.
- **Deferred case with deferral file**: tier-1 surfaces `outcome: "deferred"`, `deferred_files: [path]`; skill displays the file content.
- **No PR URL in daytime.log**: `pr_url` is `null`. Normal for non-merged outcomes.
- **`DAYTIME_DISPATCH_ID` contains shell metacharacters**: subprocess rejects at the validation regex; logs error; generates a fresh uuid4 for internal tracking. Skill-side freshness check fails (result has subprocess-generated uuid, skill has its minted uuid) → tier-1 rejects → tier-2 → tier-3. Acceptable degraded path.
- **`ctx.batch_result` empty at classification time** (exception path before `apply_feature_result` populated it): result-file schema's `outcome` is `"failed"` and `terminated_via` is `"exception"`; `deferred_files: []`, `pr_url: null`, `error` populated from the exception. The classification branches (merged/deferred/paused/failed) are skipped — the exception path writes directly to the result file in the outer finally.
- **Very long `daytime.log`**: `pr_url` scan uses a line-by-line Python scan, short-circuiting on the first match. Bounded-memory. No full-file load.
- **Orphan guard fires mid-run**: `_orphan_guard` runs `cleanup_worktree` + `os._exit(1)` per current behavior (unchanged by this ticket). No result file is written. Skill's next read: tier-1 absent → tier-2 → tier-3. Discrimination message depends on `daytime-state.json`'s last-known phase, which will be whatever `build_config` wrote (non-terminal). Message: "Subprocess did not complete. Check daytime.log." Acceptable; the orphan case is rare and the message is actionable.
- **Outer finally's orphan-task cancellation**: the first statement in the outer finally is `_orphan_task.cancel()`. This ensures the orphan guard cannot fire after the outer finally begins executing. Combined with the outer finally's single-writer result-file semantics, there is no possibility of two writers racing on `daytime-result.json` — either orphan fires *before* outer-finally begins (no result file; tier-3 handles) or the outer finally runs (orphan cancelled; result file written).

## Changes to Existing Behavior

- **MODIFIED: `skills/lifecycle/references/implement.md §1b` (launch protocol)** — skill mints a `dispatch_id` UUID pre-launch, writes `lifecycle/{slug}/daytime-dispatch.json` atomically, then launches the subprocess with `DAYTIME_DISPATCH_ID={uuid}` in the env. After launch returns a PID, the skill updates `daytime-dispatch.json` with the PID via a second atomic write.
- **MODIFIED: `skills/lifecycle/references/implement.md §1b vii`** — log-tail substring classifier replaced with 3-tier reader (result file + dispatch-file freshness check → state file as discrimination context → log-tail with discriminated `outcome: "unknown"` message). `PYTHONUNBUFFERED=1` is NOT added.
- **MODIFIED: `skills/lifecycle/references/implement.md §1b viii`** — `dispatch_complete` event's `outcome` field enumeration extends to include `"unknown"`.
- **MODIFIED: `claude/overnight/daytime_pipeline.py::run_daytime()`** — top-level try/finally wraps the body starting after `_check_cwd`; catch is `except Exception`; outer finally's first statement is `_orphan_task.cancel()`; result-file write follows, wrapped in inner try/except.
- **MODIFIED: `claude/overnight/daytime_pipeline.py` classification prints** — `flush=True` added.
- **MODIFIED: `claude/overnight/daytime_pipeline.py::_check_dispatch_id()` (new helper)** — reads `DAYTIME_DISPATCH_ID`, validates against `^[a-f0-9]{32}$`, falls back to uuid4 generation with stderr warning on malformed/missing.
- **ADDED: `claude/overnight/state.py::save_daytime_result()`** — atomic-write helper mirroring `save_batch_result()`; new `DaytimeResult` dataclass defining the 10-field schema.
- **ADDED: `lifecycle/{slug}/daytime-result.json`** — new per-dispatch terminal artifact.
- **ADDED: `lifecycle/{slug}/daytime-dispatch.json`** — new per-dispatch identity artifact written by the skill pre-launch; consumed by the skill during polling; deleted after successful tier-1 read.
- **ADDED: `.gitignore` entries** — `lifecycle/*/.daytime-result-*.tmp` and `lifecycle/*/.daytime-dispatch-*.tmp`.
- **ADDED: tests** per R9.

## Technical Constraints

- **Atomic write primitive**: `tempfile.mkstemp(dir=target_dir, prefix=".daytime-result-", suffix=".tmp")` → `os.write(fd, payload)` → `durable_fsync(fd)` → `os.close(fd)` → `os.replace(tmp, final)`. Same pattern for `daytime-dispatch.json` (skill-side) using a shell-implementable equivalent (`python3 -c` one-liner invoked from Bash that performs the atomic write, or a small helper binary). Tempfile MUST live in the same directory as the target.
- **`dispatch_id` format**: uuid4 hex (32 chars lowercase), regex `^[a-f0-9]{32}$`. Enforced at subprocess entry AND skill-side read of both `daytime-dispatch.json` and `daytime-result.json`.
- **Outer try boundary**: begins *after* `_check_cwd()` (which calls `sys.exit(1)` and cannot be caught) but *before* every other startup check. The outer `except Exception` catches both the current `subprocess.CalledProcessError` (thrown by the un-fixed `create_worktree`) and the post-#094 `ValueError` (the new type per sibling ticket #094's R2). This is how R3 achieves type-robustness across the sibling ticket's type change.
- **Orphan-guard cancellation**: outer finally's first action is `_orphan_task.cancel()`. After this, `_orphan_guard` cannot fire. This closes the race window between the orphan path's `os._exit(1)` and the outer finally's `os.replace`.
- **`pr_url` regex**: `https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+` — streamed line-by-line over `daytime.log` with first-match-wins. Implementation: Python line iterator, not subprocess `grep`, to avoid a subprocess hop and to keep the logic in `save_daytime_result()`.
- **Skill-side UUID persistence**: the skill's in-memory UUID is a cache; `daytime-dispatch.json` is authoritative. A skill re-entered after conversation compaction or process restart reads the dispatch file to recover the `dispatch_id` for its tier-1 freshness check. The dispatch file is deleted only after tier-1 succeeds.
- **No changes to `BatchResult` or `FeatureResult` dataclasses**. Schema fields are populated from existing data: `outcome`/`terminated_via` from ctx.batch_result and the write-path code; `deferred_files` from glob of `deferred_dir`; `pr_url` from regex scan of `daytime.log`; `error` from `str(exc)` in except paths.
- **Event schema: `dispatch_complete` outcome enumeration extends to include `"unknown"`**. No `dispatch_id` field is added to `implementation_dispatch` or `dispatch_complete` (replaced by the dispatch-file mechanism). This is the only cross-skill event-schema change and is backwards-compatible (old consumers ignore the new enum value or see it as a classifier-reported unknown).
- **Test harness**: new tests mock `create_worktree` to raise specific exception types (both `subprocess.CalledProcessError` and `ValueError("worktree_creation_failed: ...")`) to pin the type-robustness property. `os.getppid()` is not mocked in this ticket's tests (orphan-path coverage is deferred with the orphan-guard result-file write).
- **No external-service or package-version changes.** Pure stdlib + existing `state.py` primitives.

## Open Decisions

None. All open items from research are resolved in the spec body.
