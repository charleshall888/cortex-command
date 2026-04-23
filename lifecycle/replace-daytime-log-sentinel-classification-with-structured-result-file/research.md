# Research: Replace daytime log-sentinel classification with structured result file

> Backlog: [backlog/095](../../backlog/095-replace-daytime-log-sentinel-classification-with-structured-result-file.md) · Parent epic: [#093](../../backlog/093-modernize-lifecycle-implement-phase-preflight-options.md)
>
> Replace the daytime pipeline's last-`"Feature "`-line substring-match classifier with a structured `lifecycle/{slug}/daytime-result.json` file — written atomically by the subprocess, consumed by `implement.md §1b vii` with a graceful-degradation fallback chain, stamped with a freshness token to reject stale prior-run results, and made durable against stdout-buffering loss.

## Summary of findings

1. **The freshness-token proposal in the backlog ticket is fundamentally broken as written.** `LIFECYCLE_SESSION_ID` is not a per-dispatch identifier — it is the Claude CLI *session* identifier (injected by `hooks/cortex-scan-lifecycle.sh:10` on `SessionStart`), stable across every dispatch inside one conversation. Using it as a freshness token is a no-op within a single CLI session. A new per-dispatch identifier must be minted by the skill and passed as a distinct env var (e.g., `DAYTIME_DISPATCH_ID`). The skill must persist it across bash-call boundaries via conversation memory, since persisting it to a file on disk recreates the stale-file problem the token exists to solve.
2. **The backlog's "three-tier fallback" is actually two tiers.** `daytime-state.json` is written exactly once at startup (`build_config` at line 218) with `status: "running"` and is never updated at terminal transitions — `save_state()` has no caller in the end-of-run path. Tier 2 therefore carries no outcome information; it always reports "running." Either the spec adds terminal state writes (real refactor, not trivial) or tier 2 must be dropped from the design as dead weight.
3. **The backlog's "write at end-of-run" placement misses the live-observed failure mode.** Lifecycle-69 failed *in* `create_worktree()` at line 287, *before* the `try/except` at line 307. A result-file write placed in the inner `try/finally` block (the shape the backlog ticket implies) would never execute for startup failures. The write must wrap the **entire** `run_daytime` body, including `create_worktree`, in a top-level `try/finally`. This single observed failure is also the entire justification for this ticket; the design must cover its shape.
4. **The orphan guard bypasses `finally`.** `_orphan_guard` calls `os._exit(1)` directly (line 243), skipping every `finally` in the coroutine. If the result-file write lives in `finally`, it does not run on orphan. The orphan-guard code path must itself write a result file with `terminated_via: "orphan"` before exiting, or the skill's "file exists = terminated" semantics collapse for that outcome.
5. **`Alternative A (separate `daytime-result.json`) is the right shape**, but with a stronger schema than the backlog ticket proposes — specifically, a `terminated_via` enum that distinguishes `classification | exception | startup_failure | orphan`. Without this field, the move-to-finally design creates indistinguishable "file exists with empty ctx" states for (a) "dispatch crashed before execution populated anything" vs. (b) "dispatch classified as failed normally." The two need different UX.
6. **Four of the nine schema fields the backlog ticket lists are not available in the current data model** (`pr_url`, `rework_cycles`, `tasks_completed`, `commits`). Populating them today silently yields `None`. The spec must decide MVP-vs-deferred; the reasonable MVP is `outcome`, `dispatch_id`, `start_ts`, `end_ts`, `terminated_via`, `schema_version`, `deferred_files`, and `error` (when applicable) — the arithmetic fields deferred behind new instrumentation in `execute_feature` / `apply_feature_result`.
7. **`PYTHONUNBUFFERED=1` is redundant once the result file exists.** The ticket's buffering fix targets durability of the final `print` line. If the result file is authoritative and print lines are no longer classified, per-line stdout flushing is no longer load-bearing. Applying `PYTHONUNBUFFERED=1` to a 4-hour dispatch with verbose `execute_feature` chatter imposes measurable syscall overhead for no correctness win. Targeted `flush=True` on the 5 classification prints is the proportionate defense for humans reading `daytime.log`.
8. **Log-tail classification is an industry-recognized anti-pattern** (AWS Observability, Dash0, Sawmills, ACM TOPS) and the backlog's direction to replace it is correct. But the backlog's tier-3 ("fall back to log tail (current behavior) as last resort") preserves the anti-pattern. The spec should make tier-3 produce `outcome: "unknown"` and prompt the user to investigate, not silently classify as `failed`. "Silent fallbacks are lies" (elegantsoftwaresolutions.com) and stateful task-processing systems cannot afford them.

## Codebase Analysis

### End-of-run flow in `run_daytime()` (claude/overnight/daytime_pipeline.py)

Current structure (lines 247–351):

```python
async def run_daytime(feature: str) -> int:
    _check_cwd()
    # ... startup: plan check, PID guard, recover_stale, build_config, create_worktree ...

    worktree_info = create_worktree(feature)   # line 287 — can raise before try/except

    ctx = OutcomeContext(...)
    _orphan_task = asyncio.create_task(_orphan_guard(feature, pid_path))  # line 305

    try:                                          # line 307
        result = await execute_feature(...)
        await apply_feature_result(...)
    except Exception as e:                        # line 314
        sys.stderr.write(f"error: daytime pipeline failed: {e}\n")
        return 1
    finally:                                      # line 317
        _orphan_task.cancel()
        cleanup_worktree(feature)
        pid_path.unlink(missing_ok=True)

    # Classification (lines 322–351) runs AFTER finally
    br = ctx.batch_result
    if feature in br.features_merged:
        print(f"Feature {feature} merged successfully.")   # line 324
        return 0
    # ... deferred, paused, failed branches, each with a print-sentinel ...
```

### Exhaustive outcome set at return paths (lines 322–351)

| # | Outcome | Current sentinel | Return |
|---|---------|------------------|--------|
| 1 | merged | `Feature {name} merged successfully.` | 0 |
| 2 | deferred (with file) | `{deferral_file_path}` (raw path) | 1 |
| 3 | deferred (no file) | `Feature {name} deferred — check lifecycle/{name}/deferred/...` | 1 |
| 4 | paused | `Feature {name} paused — worktree cleaned; check events.log...` | 1 |
| 5 | failed (with error) | `Feature {name} failed: {error}` | 1 |
| 6 | failed (fall-through) | `Feature {name} did not complete successfully.` | 1 |
| 7 | exception-in-except | `error: daytime pipeline failed: {e}` (stderr) | 1 |
| 8 | startup-failure | `create_worktree` etc. raise before line 307; Python traceback to daytime.log | subprocess exit code |
| 9 | orphan | `_orphan_guard` at `os.getppid() == 1` → `cleanup_worktree` → `os._exit(1)` — no sentinel | 1 |

Note that outcomes 2 (raw deferral path, line 329) and 3 (`"deferred"` string, lines 331–333) don't share a prefix; outcome 2 prints a filesystem path that does NOT begin with `"Feature "`, so the skill's current `"last Feature line"` classifier **already** misclassifies case 2 as tier-4 (failed). This is a latent bug inherited by tier-3 if the ticket keeps the current log-tail matcher.

### Atomic-write primitive (claude/overnight/state.py)

`save_state()` at lines 346–387 and `save_batch_result()` at lines 390–437 both implement:

```python
state_path.parent.mkdir(parents=True, exist_ok=True)
fd, tmp_path = tempfile.mkstemp(
    dir=state_path.parent,
    prefix=".overnight-state-",
    suffix=".tmp",
)
try:
    os.write(fd, payload.encode("utf-8"))
    durable_fsync(fd)                # fsync for durability
    os.close(fd)
    os.replace(tmp_path, state_path) # metadata-atomic rename
except BaseException:
    # close fd if not closed; unlink tmp
    raise
```

A new `save_daytime_result()` should be added following `save_batch_result()` as its direct template — same file, same module. Reusable without modification; only the `prefix` and `suffix` differ.

### Skill-side launch and identity plumbing (skills/lifecycle/references/implement.md §1b)

**Launch command (§1b iv, line ~130):**
```
python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1
```
No `PYTHONUNBUFFERED=1` today. No env var passed to communicate a freshness token.

**Subprocess session_id (daytime_pipeline.py:281–283):**
```python
session_id = os.environ.get("LIFECYCLE_SESSION_ID") or (
    f"daytime-{feature}-{int(time.time())}"
)
```
`LIFECYCLE_SESSION_ID` is populated by `hooks/cortex-scan-lifecycle.sh:10` on `SessionStart` with the Claude CLI's *session_id*. Stable per Claude CLI process. Not unique per `/lifecycle` dispatch.

**Current classifier (§1b vii, lines 157–164):**
```
Read the last non-empty line of lifecycle/{feature}/daytime.log that begins with "Feature ".
Apply first-match-wins: merged successfully → success; deferred → deferred; paused → paused;
otherwise → failed (show last 20 lines).
```

**Identity available at launch vs. at result-surfacing:**

| Field | At skill launch | In result file (proposed) |
|-------|-----------------|----------------------------|
| PID | Written by subprocess to `daytime.pid`, read by skill | Not needed in result file |
| `session_id` | Claude CLI session id; reused across dispatches | Insufficient — not unique per dispatch |
| `DAYTIME_DISPATCH_ID` | Must be **minted by the skill** pre-launch | Required — unique-per-dispatch freshness token |
| `start_ts` | Skill must capture pre-launch | Required — human-readable diagnosis + ordering |

### Consumers of `daytime-state.json`

Grep confirms one in-tree consumer: `claude/overnight/daytime_pipeline.py` itself (written at line 218 via `build_config`). No dashboard, no `bin/overnight-status`, no statusline, no tests read it directly. `bin/overnight-status` reads session-level `overnight-state.json` via `jq`, not `daytime-state.json`. Schema-extension risk on `daytime-state.json` is therefore low *for this file*, but the research recommendation is to use a separate `daytime-result.json` file anyway — not because of consumer breakage but because `daytime-state.json` is written only at startup today and has no terminal-write plumbing. See Tradeoffs & Alternatives below.

### Orphan guard (daytime_pipeline.py:225–244)

```python
async def _orphan_guard(feature: str, pid_path: Path) -> None:
    while True:
        await asyncio.sleep(1)
        if os.getppid() == 1:
            try:
                cleanup_worktree(feature)
            finally:
                pid_path.unlink(missing_ok=True)
                os._exit(1)
```

Fires when parent process dies and the child is reparented to init (PPID=1). Bypasses every `finally` in `run_daytime` via `os._exit(1)`. Writes no state, no events, no result file. Detects its triggering condition within 1 second. False-positive risk: on macOS/Linux a process-tree reparenting transition is one-way (PPID=1 is terminal), so a ~1s false-trigger window during a normal process-tree transient is highly unlikely but not impossible (e.g., briefly ps-reparented processes under some exotic tooling).

### Stdout buffering

- Subprocess stdout redirected to `daytime.log` via shell (`> daytime.log 2>&1`); POSIX behavior is block-buffered for redirected stdout.
- No `flush=True` in any `print()` in `daytime_pipeline.py` classification block.
- No `PYTHONUNBUFFERED` set anywhere in the codebase.
- Classification `print()` calls (lines 324, 329, 331, 337, 348, 350) execute **after** the `finally` at line 317 — so the `print` line is the very last data written before subprocess exit. SIGKILL between `print()` and kernel commit loses the sentinel.

### Lifecycle-69 (the ticket's origin incident)

From `research/revisit-lifecycle-implement-preflight-options/research.md` DR-4 and the recorded lifecycle-69 failure: `dispatch failed at startup on git worktree add (exit 128)`. The failure occurred in `create_worktree()` *before* `run_daytime`'s `try/except`. `check=True` + `capture_output=True` in `worktree.py:142-148` swallowed stderr into a `CalledProcessError` that propagated up; the user saw only `returned non-zero exit status 128`. The classification block never executed — there was no `"Feature "` line in the log. The skill's log-tail classifier returned `failed` (correct coarse-grained outcome) but with no useful detail. **A result file written in the inner `try/finally` would NOT have fixed this** — only one wrapping the entire `run_daytime` body could.

### Tests

- `claude/overnight/tests/test_daytime_pipeline.py::TestRunDaytimeStartupGuards` tests CWD / plan / PID / stale-recovery startup guards by calling `run_daytime` with mocks.
- `TestRunDaytimeRouting` tests three outcomes (success, deferred, paused) by mocking `apply_feature_result` with side effects that mutate `ctx.batch_result`. Does NOT assert anything about the classification prints or state-file writes.
- `tests/test_daytime_preflight.py` tests the outcome-detection Bash helpers as pure-python functions — this is where skill-side classifier logic would be validated.
- No test currently inspects files in `lifecycle/{feature}/` post-run.

For the new design: unit tests must cover `outcome: merged|deferred|paused|failed|unknown`, `terminated_via` transitions, freshness-token mismatch, missing-file fallback, malformed-JSON recovery, and an orphan-path write. Some of these require mocking `os.getppid()` or the orphan task — non-trivial but tractable.

## Web Research

Summarized from agent 2; sources inline.

### Atomic file replace (Python 2025 best practice)

- Canonical: `tempfile.NamedTemporaryFile(dir=target_dir, delete=False)` → `write` → `flush` → `os.fsync(fd)` → `os.replace(tmp, final)`. Temp MUST live in the same filesystem (same directory is the safe way to guarantee this).
- `os.replace` wraps POSIX `rename(2)`, metadata-atomic. Metadata-atomic ≠ durable-across-crash; durability requires `fsync` before rename (LWN 323067, ext4 2009). On macOS APFS, `fcntl.F_FULLFSYNC` is stronger than `fsync`; 2025 empirical study (arxiv 2511.18323) measured fsync overhead at 56–108% for checkpoint writes, dir-fsync at 84–570%. For the daytime-pipeline use case (reader is the skill, running on the same machine, typically within seconds), `flush + fsync + os.replace` is proportionate; directory fsync is optional.
- The `save_state()` primitive in this repo already uses `durable_fsync`, which adapts to the host filesystem.

### Freshness / idempotency tokens

- Stripe's idempotency-key pattern: caller pre-mints a high-entropy token, passes it to callee, callee echoes it in the result, caller rejects mismatches.
- UUIDv4 is collision-resistant but unordered; UUIDv7 is timestamp-prefixed and sortable. Either works for this use case; UUIDv7 is preferable if the token is ever used for ordering. Pure-random `uuid4().hex` is sufficient and simpler.
- **"Session" and "dispatch" are different concepts.** Reusing a stable session id (e.g., Claude CLI's `session_id`) as a freshness token collapses them — every dispatch from the same CLI session shares the token, defeating rejection of stale prior-run results from within the same session.

### Stdout buffering under SIGKILL

- `PYTHONUNBUFFERED=1` / `python -u`: strongest — no Python-level buffer to lose. Byte-level writes hit the pipe immediately. But every `print` becomes a syscall, which is measurable overhead for long verbose runs.
- `flush=True` on every `print`: weaker — must reach the `print` call; SIGKILL between format-and-write is still a loss window (microsecond-scale).
- `sys.stdout.reconfigure(line_buffering=True)`: weakest — only flushes on newlines; pipe capture forces full buffering anyway.
- **Residual window:** Even under `PYTHONUNBUFFERED=1`, a SIGKILL delivered between userspace-format-prep and kernel `write(2)` still loses the byte. Window is microseconds, not eliminated.
- **Key framing correction:** The buffering fix is a durability improvement for *humans reading daytime.log*, not a correctness fix for the classifier — once the result file is authoritative, classification no longer depends on the print line.

### Three-tier fallback patterns

- Industry consensus (elegantsoftwaresolutions.com "Silent Fallbacks Are Lies"; AWS REL05-BP01; OpenTelemetry; Dash0): graceful-degradation fallbacks are acceptable only with observability on fallback frequency. Silent cascades hide failures in stateful systems.
- Applied: tier-2 must be either (a) functional or (b) removed — a tier that always says "running" is worse than absent. Tier-3 must produce an *explicit* unknown-outcome rather than silently classify as `failed`.

### Log-tail classification anti-pattern

Strong industry consensus:
- Sawmills.ai: "Log parsing based on regular expressions is very sensitive to changes in log formats."
- ACM TOPS 10.1145/3568020: manual-regex parsers systematically risk classification bugs during postmortems.
- Dash0: "extracting meaningful data often requires brittle parsing logic that can easily break with minor changes."
- The specific shape — "last line starting with Feature, first-match substring" — depends on exact substring, line ordering, absence of later matches, AND subprocess flushing. Four independent failure modes.

### Key takeaways

1. Atomic-write recipe: `tempfile + flush + fsync + os.replace`. Reuse `save_state()`'s `durable_fsync` + `os.replace` pattern via a sibling `save_daytime_result`.
2. Freshness token: skill pre-mints a UUID, passes via env (`DAYTIME_DISPATCH_ID`), subprocess echoes in result, skill rejects mismatch. Do NOT reuse `LIFECYCLE_SESSION_ID`.
3. Buffering: `flush=True` on the 5 classification prints is proportionate defense-in-depth for humans; `PYTHONUNBUFFERED=1` is redundant once classification is file-based and imposes measurable cost on verbose runs.
4. Fallback chain must be observable; tier-2 must be real or removed; tier-3 must surface `unknown` not `failed`.

## Requirements & Constraints

### Atomic writes

- `requirements/pipeline.md` Non-Functional: "All session state writes use tempfile + `os.replace()` — no partial-write corruption." Direct match to the proposed primitive.
- `requirements/pipeline.md` §Session Orchestration: "All state writes are atomic (tempfile + `os.replace()`) — partial-write corruption is not possible."

### Graceful partial failure

- `requirements/project.md` Quality Attributes: "Graceful partial failure: Individual tasks in an autonomous plan may fail. The system should retry... and fail that task gracefully if unresolvable — while completing the rest."

### File-based state

- `requirements/project.md` Architectural Constraints: "File-based state: Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files. No database or server."
- `lifecycle/{slug}/daytime-result.json` fits this constraint directly.

### Observability implications

- `requirements/observability.md` §In-Session Status CLI mandates `bin/overnight-status` reads structured state, not log tails. Adding a sibling `bin/daytime-status` that consumes `daytime-result.json` is congruent with this pattern but is explicitly *optional* per the backlog's "Out of scope" (decide in spec).
- `requirements/observability.md` §Dashboard: "Missing or malformed session files are silently ignored (last-good state retained)." The skill's reader should follow the same posture — missing result file triggers fallback rather than erroring out.

### Scope boundaries

- Pipeline subsystem change (`claude/overnight/daytime_pipeline.py`) + shared skill (`skills/lifecycle/references/implement.md`). Touches shared infrastructure per pipeline.md's "Dependencies" list. Other downstream consumers (dashboard, bin/overnight-status, statusline) are **not** affected — they read session-level state, not per-feature daytime state.

### Summary: alignment with requirements

The proposed change directly implements and extends the atomic-write and file-based-state architectural constraints, with no conflicts detected. The failure modes the ticket addresses (SIGKILL/OOM/buffering/rotation/crash-restart misclassification) are the exact shapes that `requirements/project.md §Graceful partial failure` calls out as needing to be handled gracefully. The one requirements-adjacent concern surfaced by research is that the fallback chain must be observable — "silent fallbacks are lies" is consistent with `requirements/observability.md`'s dashboard mandate to surface state changes within 7s.

## Tradeoffs & Alternatives

### Alternative A — separate `daytime-result.json` (backlog's proposal, **recommended with modifications**)

- **Shape.** Subprocess writes `lifecycle/{slug}/daytime-result.json` via tempfile + `os.replace` at end-of-run. Skill reads result → state → log (tier chain as the backlog proposes).
- **Footprint.** ~80–120 lines total — new `save_daytime_result()` in `state.py` mirroring `save_batch_result()`; end-of-run write hook in `run_daytime` in a top-level try/finally (not the inner one); orphan-guard write before `os._exit(1)`; result-reader in `implement.md §1b vii`; test additions.
- **Freshness.** Skill pre-mints a UUID (`DAYTIME_DISPATCH_ID`), passes via env, subprocess echoes. Skill persists the UUID in conversation memory across polling iterations; see Open Questions on the persistence mechanism.
- **Backward compat.** Strictly additive. No existing reader consumes `daytime-result.json`.
- **Observability.** No side effects on dashboard, statusline, `bin/overnight-status`.
- **Failure envelope.** SIGKILL mid-write → tempfile orphan, real path absent → skill falls back. Parent crash + restart → freshness-token mismatch rejects prior-run file. Orphan guard → explicit `terminated_via: "orphan"` write before `os._exit(1)` preserves file-as-signal.
- **Pros.** File-presence = "terminated" signal; clean dataclass isolation from `OvernightState`; minimal blast radius; mirrors prior art (`save_batch_result`).
- **Cons.** One more file in `lifecycle/{slug}/`. Some field duplication with state.json (but the fields don't overlap 1:1 — state tracks *operational* status; result tracks *terminal* outcome).

### Alternative B — extend `daytime-state.json` schema

- **Shape.** Add terminal fields (`outcome`, `end_ts`, `pr_url`, `rework_cycles`, `terminated_via`) to `OvernightState`; write at end-of-run via `save_state()`.
- **Pros.** No new file; one less artifact in the directory.
- **Cons (decisive).**
  1. `OvernightState` is shared across orchestrator, batch_runner, outcome_router, map_results, smoke_test, and dashboard deserializers. Every overnight session's state file would carry `null` terminal fields forever. Schema-hygiene regression on a hot file.
  2. `daytime-state.json` is currently written once at startup and never updated. File-as-"run-finished" signal-by-presence is lost; consumers must parse `outcome` to distinguish in-progress from done.
  3. Blast radius of future schema changes increases.
- **Research DR-2 already rejected this.** Finding confirmed by agent 4's survey of `OvernightState` consumers.

### Alternative C — sentinel + structured state hybrid

- **Shape.** Keep `print` sentinels in `daytime.log` for humans; classify authoritatively from structured state (Alternative B schema).
- **Pros.** Log retains human-readability for manual debugging.
- **Cons.** Inherits all of B's coupling cost plus maintenance of a decorative sentinel that no code depends on. The "human readability" benefit is preserved anyway by keeping the prints (with `flush=True`) even under Alternative A; C contributes nothing beyond that.
- **Verdict.** Strictly dominated by A with prints retained.

### Alternative D — `events.log` as canonical

- **Shape.** Subprocess appends a terminal event (`daytime_complete` or reuses `feature_complete`) to `lifecycle/{slug}/events.log`. Skill reads last matching event.
- **Pros.** Reuses existing JSONL audit stream. Pipeline.md already calls events.log the "system of record."
- **Cons (decisive).**
  1. **Semantic collision if reusing `feature_complete`.** That event is written today ONLY on APPROVED review by `claude/pipeline/review_dispatch.py:285,529`. `claude/statusline.sh:322,379` and `claude/common.py:116` grep for it to flip a feature to the "complete" phase. Reusing the event for paused/failed/deferred daytime outcomes would misclassify them as complete in the statusline and dashboard.
  2. Introducing a new event name (`daytime_complete`) avoids the collision but eliminates the "reuse existing infrastructure" argument — no existing consumer reads the new event type.
  3. JSONL append-atomicity is per-line and bounded by `PIPE_BUF` (~4KB on Linux/macOS). A fat terminal event with long `deferred_files` arrays or error strings could exceed `PIPE_BUF`. `os.replace` of a fully-written tempfile is strictly stronger.
- **Verdict.** Rejected on semantic-collision grounds alone; the atomicity concern is secondary.

### Recommended approach

**Alternative A with structural adjustments surfaced by the adversarial review:**

1. Write `daytime-result.json` in a **top-level** `try/finally` wrapping the entire `run_daytime` body, including `create_worktree` (lines 287–351). The inner `try/except` at line 307 is insufficient — it misses startup failures like lifecycle-69.
2. Extend the schema with a `terminated_via: "classification" | "exception" | "startup_failure" | "orphan"` field so the skill can distinguish "dispatch crashed mid-startup" from "dispatch classified as failed" — both produce `outcome: "failed"` under the ticket's current schema.
3. Update `_orphan_guard` to write a result file with `terminated_via: "orphan"` before `os._exit(1)`.
4. Skill pre-mints a `DAYTIME_DISPATCH_ID` UUID and passes it via a dedicated env var. **Do not reuse `LIFECYCLE_SESSION_ID`** — it is per Claude CLI session, not per dispatch.
5. Drop `PYTHONUNBUFFERED=1` from the launch. Apply `flush=True` on the 5 classification prints only. The result file makes print durability non-load-bearing.
6. Make tier-3 produce `outcome: "unknown"` not `outcome: "failed"`. Silent classification of missing data as failure is the exact UX this ticket is replacing.
7. Add `schema_version: 1` to the result file from day one.
8. MVP schema fields: `schema_version`, `dispatch_id`, `feature`, `start_ts`, `end_ts`, `outcome`, `terminated_via`, `deferred_files: []`, `error: null | str`. Defer `pr_url`, `rework_cycles`, `tasks_completed`, `commits` behind a separate instrumentation ticket — they require threading new fields through `BatchResult` / `FeatureResult`.
9. Extend `.gitignore` to cover `lifecycle/*/.daytime-result-*.tmp`; add startup sweep for stale tempfiles (mirror `_recover_stale` for worktrees).

## Adversarial Review

Dispatched after agents 1–4 completed; summarized findings were injected into its prompt.

### Failure modes and edge cases

- **[Freshness token]** `LIFECYCLE_SESSION_ID` is not per-dispatch. Every `/lifecycle` invocation within one Claude CLI session reuses the same value (`hooks/cortex-scan-lifecycle.sh:10`). A crashed dispatch restarted within the same session cannot be distinguished from its successor by this token. Must introduce a new `DAYTIME_DISPATCH_ID`.
- **[Tier-2 is dead]** `daytime-state.json` is written ONCE at startup (line 218) with `status: "running"` and never updated at terminal transitions. The "three-tier" fallback is actually two-tier. Spec must either (a) add terminal state-writes throughout `execute_feature`/`apply_feature_result` (significant refactor) or (b) remove tier-2 from the design.
- **[Move-to-finally creates ambiguous exists-states]** Placing the write in finally means the exception-in-except case writes a result file with empty `ctx.batch_result`. "File exists with empty outcome" becomes indistinguishable from "file exists from a normal failure classification." Requires `terminated_via` field to disambiguate.
- **[Orphan guard bypasses all finally]** `os._exit(1)` at line 243 skips every `finally`. Orphan-path must write its own result file with `terminated_via: "orphan"` before exiting, or file-presence semantics collapse for that outcome. False-positive risk of the PPID=1 check is low but non-zero (exotic process-tree transients).
- **[Startup failure is where lifecycle-69 actually died]** `create_worktree` at line 287 raises before line 307's try/except. Inner try/finally cannot write a result file. Must wrap the ENTIRE body.
- **[Tempfile accumulation]** `tempfile.mkstemp(prefix=".daytime-result-", suffix=".tmp")` creates files git *will* show in `git status` (dot-prefix hides from ls but not git). `.gitignore` has no coverage for `lifecycle/*/*.tmp` or `.daytime-result-*.tmp`. Repeated SIGKILL-during-write accumulates orphans.
- **[PYTHONUNBUFFERED cost]** Setting PYTHONUNBUFFERED for a 4-hour run with verbose `execute_feature` chatter imposes per-line syscalls that were previously coalesced. Redundant once the result file is authoritative; the targeted `flush=True` on 5 classification prints achieves the same human-readable-log durability at near-zero cost.
- **[Four schema fields don't exist in the data model]** `pr_url`, `rework_cycles`, `tasks_completed`, `commits` are not fields on `BatchResult` or `FeatureResult`. Populating at end-of-run yields silent `None`. Either instrument upstream or drop from MVP.
- **[Latent bug in current tier-3]** The deferred-with-file path at line 329 prints a filesystem path, NOT a line starting with `"Feature "`. The skill's current "last Feature line" classifier already misclassifies this case as tier-4 (failed). If the spec retains the current log-tail matcher as tier-3, it inherits this bug.
- **[tier-3 should produce `unknown` not `failed`]** Silently classifying missing authoritative data as failure is the exact UX regression this ticket is replacing.
- **[PYTHONUNBUFFERED does not eliminate the SIGKILL window]** Even unbuffered, kernel `write(2)` is distinct from userspace format-and-prepare; a SIGKILL in between is a microsecond-scale loss window. The ticket's "PYTHONUNBUFFERED makes prints SIGKILL-safe" framing is overstated.

### Security / corruption concerns

- **Token-format validation.** If the freshness token is ever interpolated into a shell command in the skill's polling loop (likely — Bash reads files and constructs commands), a malformed token with metacharacters enables injection. The subprocess today generates `daytime-{feature}-{int(time.time())}` when `LIFECYCLE_SESSION_ID` is unset; `{feature}` is CLI-supplied. Mitigation: validate the UUID format at the subprocess entrypoint and at the skill reader (`^[a-zA-Z0-9-]{36}$`); the skill must generate the UUID via a safe mechanism (`uuidgen` or `python -c 'import uuid; print(uuid.uuid4())'`).
- **Cross-filesystem atomic rename.** `os.replace` across different filesystems loses atomicity. Project runs on local APFS today; no concern. Flagged for future-proofing if `lifecycle/` ever moves to an NFS mount.

### Assumptions that may not hold

- "LIFECYCLE_SESSION_ID is unique per dispatch" — **false**, it's per Claude CLI session.
- "tier-2 daytime-state.json provides useful terminal info" — **false**, written once at startup, never updated.
- "Moving the result-file write to finally preserves authoritative-file semantics" — **false** without a `terminated_via` discriminator.
- "Three-tier fallback gracefully degrades" — **false** as designed; tier-2 is dead, tier-3 silently misclassifies.
- "PYTHONUNBUFFERED + flush=True closes the SIGKILL window on the final print" — **partially false**, residual microsecond window remains.
- "Current log-tail behavior as tier-3 is a safety net" — **partially false**, already contains a latent misclassification for the deferred-with-file case.

### Recommended mitigations

1. Dispatch-scoped UUID minted by the skill, passed via `DAYTIME_DISPATCH_ID` env var; skill persists it in conversation memory across polling iterations.
2. Top-level try/finally wrapping the ENTIRE `run_daytime` body.
3. `terminated_via` enum in the schema.
4. Orphan guard writes a result file before `os._exit(1)`.
5. `schema_version: 1` from day one.
6. `.gitignore` addition for `lifecycle/*/.daytime-result-*.tmp`; startup sweep for stale tempfiles.
7. MVP schema fields are explicitly listed; growth fields deferred to an instrumentation follow-up ticket.
8. Drop `PYTHONUNBUFFERED=1`. Apply `flush=True` on the 5 classification prints.
9. Tier-3 produces `outcome: "unknown"` with an explicit "investigate" prompt; does not silently classify as failed.
10. Token format validation at both entrypoints.
11. Tests cover each tier transition including orphan, startup-failure, exception, freshness-mismatch, malformed-JSON recovery.

## Open Questions

All items below are scope-within-intent spec-phase decisions — resolved by `/refine`'s structured-interview step (`specify.md §2–3`), not by additional research. Each is annotated with the research-backed recommendation so the spec has a default to validate or reject.

- **Skill-side `DAYTIME_DISPATCH_ID` persistence across polling iterations.** Deferred: will be resolved in Spec by the user. The polling loop uses sequential Bash calls and has no file-of-record for per-dispatch state; the skill must retain the UUID in the Claude conversation context across `Bash(sleep 120)` boundaries. Research recommendation: minted pre-launch, held in conversation memory as a skill-internal variable, passed to the subprocess via env and read back from the result file for equality check. File-based persistence recreates the stale-file problem.
- **Scope of tier-2 in the fallback chain.** Deferred: will be resolved in Spec. Current `daytime-state.json` has no terminal state — it's a startup-only artifact. Research recommendation: remove tier-2 from the fallback chain. If the spec instead chooses to populate tier-2 with terminal info, it must add `save_state()` calls throughout `execute_feature` / `apply_feature_result` (non-trivial refactor).
- **Buffering discipline: `PYTHONUNBUFFERED=1` vs. targeted `flush=True`.** Deferred: will be resolved in Spec. Research recommendation: targeted `flush=True` on the 5 classification prints; drop `PYTHONUNBUFFERED=1` from the launch (redundant once classification is file-based; imposes per-syscall cost on long verbose runs).
- **MVP schema field set.** Deferred: will be resolved in Spec. Research recommendation MVP: `schema_version`, `dispatch_id`, `feature`, `start_ts`, `end_ts`, `outcome`, `terminated_via`, `deferred_files`, `error`. Deferred to a follow-up instrumentation ticket: `pr_url`, `rework_cycles`, `tasks_completed`, `commits` — these require threading new fields through `BatchResult` / `FeatureResult`.
- **`bin/daytime-status` CLI vs. inline skill renderer.** Deferred: will be resolved in Spec. Research recommendation: inline skill renderer for the MVP (smaller blast radius; mirrors existing `§1b vii` pattern). A dedicated CLI is congruent with `bin/overnight-status` prior art and can be added as a follow-up ticket if a pattern of external consumers emerges.
- **Freshness-token algorithm.** Deferred: will be resolved in Spec. Research recommendation: `uuid.uuid4().hex` (32 hex chars) for simplicity; UUIDv7 is preferable if the token is ever used for temporal ordering. Comparison is the only property required.
- **Tier-3 behavior when reached.** Deferred: will be resolved in Spec. Research recommendation: produce `outcome: "unknown"` with an explicit "investigate" prompt and surface last 20 lines of `daytime.log` for context; do NOT silently classify as `failed`.
- **Orphan-guard result-file write.** Deferred: will be resolved in Spec. Research recommendation: add a best-effort write with `terminated_via: "orphan"` before `os._exit(1)`; wrap in try/except so a write failure doesn't prevent cleanup.
- **Tempfile sweep on startup.** Deferred: will be resolved in Spec. Research recommendation: add a cheap glob-and-unlink sweep in `run_daytime`'s startup phase (alongside existing stale-PID recovery) for orphaned `.daytime-result-*.tmp` files whose age exceeds one hour.
