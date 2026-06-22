# Research: Make the overnight `WatchdogThread` activity-aware instead of a blind 30-min timer

**Backlog:** [[312-overnight-watchdogthread-is-a-blind-30-min-fixed-timer-not-the-documented-event-silence-stall-watchdog-kills-productive-orchestrator-batch-runner-subprocesses-no-feature-batch-30min-can-complete]] · tier: complex · criticality: high

**One-line problem:** `WatchdogThread.run()` is a pure `elapsed += poll_interval` countdown that reads no activity signal and never resets, so every orchestrator/batch_runner subprocess is hard-killed at exactly `STALL_TIMEOUT_SECONDS = 1800.0` regardless of how productively it is working.

> **Headline result of this research:** the bug is confirmed and the batch_runner half has a clean fix, but the two watched subprocesses are **asymmetric**, and the adversarial pass showed the naïve "reset on `pipeline-events.log` growth" prescription (a) does not honestly fix the orchestrator/planning site at all, and (b) keys batch liveness off a signal (`dispatch_progress`) that *inversely* correlates with progress under failure. The real design space is narrower and harder than the ticket implies. See **Open Questions** — several are blocking for Spec.

---

## Codebase Analysis

**Files that change**
- `cortex_command/overnight/runner_primitives.py` — the watchdog itself.
  - `WatchdogThread.__init__` (lines 95-113): current params `proc, timeout_seconds, coord, wctx, label, *, poll_interval_seconds=DEFAULT_WATCHDOG_POLL_INTERVAL_SECONDS, kill_escalation_seconds=DEFAULT_KILL_ESCALATION_SECONDS`. Needs a new activity-source param (and, per Adversarial #3/#7, likely an injectable clock + activity-probe seam for testability).
  - `WatchdogThread.run()` (lines 115-133): the core change. Today: `elapsed = 0.0` → `shutdown_event.wait(timeout=poll_interval)` (returns on shutdown) → `proc.poll()` early-return → `elapsed += poll_interval` → `_kill_for_stall()` when `elapsed > timeout_seconds`. **`time` is not imported in this module** (only `contextlib, os, signal, subprocess, threading`).
  - `_kill_for_stall()` (135-163): kill mechanism (SIGTERM→SIGKILL of PGID under `kill_lock`, re-check `poll()`) is **unchanged**; only its trigger condition moves. Class docstring (80-93) already *claims* "event-log silence" — update to match.
  - `WatchdogContext` (63-73): single field `stall_flag: threading.Event`. Concurrency agent says add **no** field here for the activity tuple; but Adversarial #4-assumption notes distinguishing *inactivity-kill vs ceiling-kill* may require a small main-thread-visible reason marker.
  - Tunables block (25-39): `DEFAULT_WATCHDOG_POLL_INTERVAL_SECONDS = 1.0`, `DEFAULT_KILL_ESCALATION_SECONDS = 5.0`. A new ceiling/poll constant belongs here.
- `cortex_command/overnight/runner.py` — both spawn sites + constant.
  - `STALL_TIMEOUT_SECONDS = 1800.0` (line 87; docstring already says "seconds of event-log silence"; in `__all__` at 3126). **Keep it 1800** (supervision invariant + ticket non-goal).
  - `_spawn_orchestrator` (1410-1512): builds `WatchdogContext` + `WatchdogThread(... timeout_seconds=STALL_TIMEOUT_SECONDS, label="orchestrator")` at 1503-1510. `session_dir` is a param (1416); `pipeline_events_path = session_dir / "pipeline-events.log"` is computed at the **call site** (line 2681), not inside the helper.
  - `_spawn_batch_runner` (1668-1723): builds the watchdog identically at 1714-1721. Already receives `events_path` (1674, overnight-events.log) but **not** `session_dir` — so threading `pipeline-events.log` in requires a signature change (call site ~2841/2847).
  - Downstream stall handling (logic unchanged, prose-only updates): orchestrator `o_wctx.stall_flag.is_set()` at 2755 → `ORCHESTRATOR_FAILED {reason: stall_timeout}` → `_transition_paused`; batch `b_wctx.stall_flag.is_set()` at 2856 → `BATCH_RUNNER_STALLED` → `_transition_paused`. Both warning strings already say "event log silence" — they become accurate after the fix.

**Patterns to reuse**
- **`cortex_command/common.py:209` `_stat_key(path) -> (exists, st_mtime_ns, st_size)`** — the canonical append-activity probe. Its docstring (210-217) explicitly includes **size** because "an append bumps file size even when mtime collides at filesystem resolution." Mirror this; catch `FileNotFoundError` (common.py:221).
- No-blocking-sleep loop shape (`shutdown_event.wait(timeout=...)`) mirrored from `RunnerHeartbeatThread` (runner.py:404-480).
- Best-effort error swallowing on the liveness side (`_emit_runner_heartbeat` swallows all exceptions, 393-401) — a stat must degrade gracefully, never crash the daemon thread.

**Tests:** `tests/test_runner_threading.py` is the home (`test_stall_flag_set_on_timeout` line 92; `sleep_proc` fixture line 66; `test_concurrent_cancel_and_stall_dont_double_kill` line 120; `test_shutdown_event_wakes_watchdog_sleep` line 186). The `_FakeWatchdog` patch at `tests/test_runner_sandbox.py:98` and any `__init__` signature change ripple here.

**Events registry:** no new event required for the core fix — the kill path reuses `ORCHESTRATOR_FAILED`/`BATCH_RUNNER_STALLED`/`STALL_TIMEOUT` (all in `events.py:EVENT_TYPES`, which fails closed on unregistered events). A *new* diagnostic event (e.g. `watchdog_reset`) would need an `EVENT_TYPES` constant **and** a `bin/.events-registry.md` row with a named consumer — add only if a real consumer exists.

## Web Research

**`gunicorn` worker timeout is the near-exact analog and the best reference implementation.** The *worker* (watched process) calls `notify()` → `os.utime(tmp.fileno())` to advance an mtime; the *arbiter* (supervisor) compares `time.monotonic() - worker.tmp.last_update()` against the timeout and `SIGABRT`→`SIGKILL`s on expiry. It is explicitly **not** a request-duration timeout — long work in background threads keeps the main loop calling `notify()`, so it fires only on genuine silence. (https://gunicorn.org/reference/settings/ + the "gunicorn timeout is not what you think" writeup.)

**The load-bearing rule across systemd / s6 / gunicorn / RTOS task-watchdogs: the keepalive must be emitted by the *watched* entity, never by the supervisor's own loop.** The classic failure is feeding the dog from the wrong context (a timer ISR / the supervisor's heartbeat) — the loop can be dead while the dog is fed, so it never fires. This **independently validates the ticket's rejection of the runner heartbeat** as the reset signal. systemd's `WatchdogSec`+`sd_notify(WATCHDOG=1)` (ping at 50 % of the window) and s6's readiness-notification model are the same principle.

**Contrast — the anti-pattern family:** Celery soft/hard time limits and pytest-timeout are wall-clock, reset-on-nothing deadlines; pytest-timeout's "paused 10 min → instant expire" footgun is a clean demonstration of why a wall-clock deadline mis-fires when the metric should be *work done*. supervisord restarts on death only (no stall detection) and notably "can only kill a process it created itself" — relevant because the cortex watchdog correctly kills the child **process group**.

**File-mtime/size race guidance (apenwarr "mtime comparison considered harmful" + NFS/inotify man pages):** don't trust mtime alone — granularity (multiple appends within one fs tick don't bump mtime → false stall), non-monotonic `utimes`, NFS attribute-cache lag, mmap/FUSE skipping mtime. **Prefer size advance as primary** for an append-only log; track `(size, mtime)` and treat *any* advance as activity; treat a size **decrease** (rotation/truncation) as activity, not silence; use `time.monotonic()` not wall-clock; polling `stat()` beats inotify for a same-host append-only log (inotify is unreliable on NFS/FUSE/Docker volumes and coalesces events). This matches the existing `_stat_key` helper.

## Requirements & Constraints

- **The watchdog's *contract* is "event-log silence"** (kill strings at runner.py:2757/2858; docstring at runner_primitives.py:80) — the fix makes the implementation honor the contract it already advertises. Must-have shape from the ticket: reset on a **worker-written** signal; **hard non-goal: "do not merely raise the timeout."**
- **Supervision division of duties (ADR-0011, `project.md:49`) is the central constraint.** In-process `WatchdogThread` owns *child-stall* detection; the out-of-process guardian + `recover` verb own *dead/wedged-host* detection and are "the only session-state writers outside the runner itself." Observability stays read-only.
- **Binding margin invariant:** `recovery.py:103` `assert WEDGED_STALENESS_SECONDS (2700) > STALL_TIMEOUT_SECONDS (1800)`, pinned by `tests/test_recovery_wedged.py:141-148`. The in-process watchdog is the *first responder* below the guardian's wedged threshold. **Keeping `STALL_TIMEOUT_SECONDS = 1800` keeps the assert satisfied** — an independent reason not to raise the cap. Note the semantic shift: `STALL_TIMEOUT_SECONDS` moves from "absolute deadline" to "silence window"; the two layers key off **different files** (watchdog→child progress; guardian→`overnight-events.log` runner-heartbeat staleness), so they do not collide — *except* at the orchestrator site, where they collide on the same file (see Open Questions).
- **Atomicity:** the watchdog is a pure reader of worker-written, atomically-appended logs; it introduces no new write surface.
- **Solution horizon:** the ticket names a durable fix shape, so the durable version is in-scope, not a stop-gap; but "simpler wins" bounds gold-plating (don't build a pluggable-signal framework).
- **Spawn-site duplication:** both call sites + the `_FakeWatchdog` test fake change together on any `__init__` signature change.

## Tradeoffs & Alternatives

Confirmed code facts gating every option: `WatchdogThread.run()` has no reset path and no clock seam; batch_runner emits `dispatch_progress` to `pipeline-events.log` per assistant turn; the orchestrator `claude -p` child writes **nothing** to `pipeline-events.log` mid-planning; both heartbeat producers write `overnight-events.log`, never `pipeline-events.log`.

- **A. Activity-reset on worker-written `pipeline-events.log` mtime/size (the ticket's approach).** ~10 lines + an activity-path. Cheap, self-contained, matches the module's own docstring. **Works for batch_runner; fails for the orchestrator** (no growth during planning → degrades to today's flat kill there). Caveat from Adversarial: `dispatch_progress` correlates with *turn count*, which inversely correlates with progress under failure.
- **B. Just raise `STALL_TIMEOUT_SECONDS`.** Trivial; **rejected by the ticket and on the merits** — a flat cap can't separate "alive and slow" from "hung"; any value is simultaneously too short for the longest healthy batch and too long for fast stall detection. Also trips the `recovery.py:103` assert if raised past 2700.
- **C. Larger cap + reuse #308's `overnight-events.log` staleness.** Same mtime mechanism pointed at `events_path`. **Fatal for the batch site:** `overnight-events.log` is advanced by the *parent* `RunnerHeartbeatThread` every 300 s regardless of child progress → resets the watchdog forever → a hung child lives forever. This is the #308 trap the ticket names. (It is, however, the *only* file that advances during orchestrator planning — see the asymmetry.)
- **D. Two-tier: short inactivity timeout (reset on per-site activity) + long never-reset absolute ceiling.** The Tradeoffs agent's recommendation. The ceiling backstops the pathological cases (a tight-loop that emits forever; a wedged planning child whose parent heartbeat resets the inactivity tier). **But the Adversarial pass shows the ceiling, at the orchestrator site, *is* the forbidden flat timeout** — and the ceiling value is currently a guess (no batch-duration data).
- **E. Poll child CPU/`/proc`.** `psutil` available, but CPU is **anti-correlated** with the dominant healthy wait (a `claude -p` agent blocked on a model round-trip burns ~0 CPU yet is alive) → would kill healthy agents. Reject.
- **F. Explicit child→parent liveness over a pipe/fd.** **Impossible at the orchestrator site** (the `claude -p` child is not our code; we can't make it emit on a custom fd without a wrapper); redundant where we control the code. Reject.

**Tradeoffs agent's recommendation:** D with a per-site signal (batch→`pipeline-events.log`, orchestrator→`overnight-events.log` + ceiling). **The Adversarial pass partially refutes this** (see below) — the orchestrator half is not an honest fix.

## Activity-Signal Data-Flow

The decisive per-site map (writer × file × cadence × child-driven?):

| Site | Candidate signal | Writer | File | Cadence | Child-driven? |
|---|---|---|---|---|---|
| batch_runner | `dispatch_progress` | **worker** (dispatch.py:808-826) | `pipeline-events.log` | per AssistantMessage (many/min) | **YES** (rich; not a floor — a deep turn can be quiet minutes) |
| batch_runner | `HEARTBEAT` (`_heartbeat_loop`) | **batch_runner child** (orchestrator.py:462) | `overnight-events.log` | 300 s unconditional | **YES** (floor) — payload carries `features_pending/running` |
| orchestrator | round telemetry (`dispatch_start`/`dispatch_complete`) | **parent runner** (runner.py:2698, `_emit_orchestrator_round_telemetry`) | `pipeline-events.log` | once before/after child | **NO** |
| orchestrator | `PLAN_GEN_DISPATCHED`, plan files, per-feature events.log | **orchestrator child** | `overnight-events.log` + scattered | only on plan-generating rounds; **zero** on re-plan/selection rounds | YES but **conditional** (absent in the blind window) |
| orchestrator | stdout JSON envelope | orchestrator child | `orchestrator-round-N.stdout.json` | single terminal write (`--output-format=json`) | YES but **unusable** (no mid-flight mtime advance) |
| both | `HEARTBEAT` (`RunnerHeartbeatThread`) | **parent runner** (runner.py:404) | `overnight-events.log` | 300 s across whole span | **NO** — payload carries `source:"runner"` |

**Batch_runner has a solid child signal** (rich `dispatch_progress` + a 300 s child-heartbeat floor) — but the two live in *different files*, so a robust batch fix must watch both, or watch `overnight-events.log` **filtered to the child's own emits** (which a stat-only watchdog cannot do — see Adversarial #5).

**Orchestrator has NO reliable child-driven progress signal during healthy planning.** The only thing advancing any log in the blind window is the **parent** `RunnerHeartbeatThread`. The two `HEARTBEAT` emitters are indistinguishable by mtime — only by parsing the `details` payload (`source:"runner"` vs `features_*`).

## Concurrency & Thread-Safety

- **All new state stays watchdog-thread-local.** `elapsed` is already a local; the new `last_seen=(size, mtime_ns)` tuple must be too. Add **nothing** to `WatchdogContext`/`RunnerCoordination`; the main thread only consumes the *outcome* (`stall_flag`), not the running bookkeeping. (Caveat: distinguishing inactivity-kill vs ceiling-kill for telemetry reintroduces a *small* main-thread-visible reason marker — see Open Questions.)
- **Ordering:** keep the existing `shutdown_event.wait()` return and `proc.poll()` early-return **first**; do stat+reset only in the block that owns `elapsed`. Reset = "set `elapsed = 0` instead of incrementing when activity advanced." This preserves "shutdown always wins" and "reset never extends a child past a shutdown request" for free.
- **No new locks.** The reset path never kills, so never touches `kill_lock`; `state_lock` stays untouched. The kill escalation contract (re-check `poll()` under `kill_lock`) is unchanged.
- **Robust stat:** wrap in `except OSError` (missing file = "no activity yet" — do **not** crash, do **not** reset); reset on **first appearance** via a `last_seen=None` sentinel (a child that writes its first event at minute 25 must not die at 30); reset when `size > last_size` **or** `mtime_ns > last_mtime_ns`; a size **decrease** re-baselines. Stat-only (never read contents) is what avoids torn-read hazards.
- **Daemon lifecycle:** thread is `daemon=True`, never joined; the `proc.poll()` early-return must stay ahead of the stat so a dead-child watchdog exits within one poll interval instead of stat-ing a stale log forever. An unhandled stat exception silently kills the daemon → child runs unwatched; the `except OSError` is load-bearing.

## Integration & Regression Surface

- **The fix *tightens* the documented contract, it does not perturb it.** Today the "watchdog self-heals first" guarantee the guardian's `2700 > 1800` margin assumes is vacuous on real stalls and harmful on healthy work; the fix makes the code behave as the margin already assumes.
- **Guardian / ADR-0011: no overlap for the batch site** (watchdog=in-process child stall on `pipeline-events.log`; guardian=dead/wedged host on `overnight-events.log`). **Overlap *exists* at the orchestrator site** if it watches `overnight-events.log` — both reset on the same parent heartbeat (the double-blind; Open Questions).
- **Two independent "stall" mechanisms** — the watchdog stall-kill (touched) and the zero-progress circuit breaker (runner.py:3014, driven by per-round `merged_delta`, **not** touched). A watchdog that fires *less often* is net-positive for the breaker (productive batches now merge instead of being killed at 30:00).
- **Tests:** `tests/test_runner_threading.py` is the primary surface (style: real `subprocess.Popen` + injected `timeout_seconds`/`poll_interval_seconds`, no fake clock). New tests must prove reset-on-growth (survives past timeout while file grows) and still-fires-on-silence. `tests/test_runner_heartbeat.py::test_run_is_wired_to_start_the_runner_heartbeat` AST-walks `runner.run` — confirm any `run()` refactor doesn't break it. `tests/test_recovery_wedged.py:141` + `recovery.py:103` pin the margin (pass iff `STALL_TIMEOUT_SECONDS` unchanged).
- **Docs:** `docs/overnight-operations.md` **owns** the watchdog description — fix line ~43 (the "No event written to events log for 30 minutes" circuit-breaker row) to be precise about *which* log + that `elapsed` resets on activity; line ~301's margin prose premise changes from aspirational to real. No `docs/internals/pipeline.md` change.

## Adversarial Review

The adversarial pass materially changed the recommendation. Code-grounded objections:

1. **Orchestrator-site "fix" is theater / a double-blind.** Parent `RunnerHeartbeatThread` (300 s) keeps `overnight-events.log` fresh, so an orchestrator watchdog watching that file *never* trips its inactivity tier — only the ceiling fires. The guardian's wedged-check reads the **same file** (recovery.py:142-144), also kept fresh by the parent heartbeat → **a wedged planning child with a live parent is invisible to the watchdog AND the guardian simultaneously.** For the orchestrator, the two-tier design delivers exactly the "merely raise the timeout" outcome the ticket forbids.
2. **The scoped fix doesn't fix the orchestrator at all.** The only honest fix is a **child-emitted** progress signal — `--output-format=stream-json` parsed from the orchestrator stdout, or a child self-heartbeat the orchestrator writes itself. That is either in scope (the ticket is bigger than a watchdog-reset change) or must be **explicitly split/deferred** — not silently ceiling-papered and called done.
3. **`dispatch_progress` is a false-liveness proxy** (dispatch.py:808-826 fires on *every* AssistantMessage, incl. tool calls / apologetic retries). A worker in a tool-retry loop emits it forever → inactivity never trips → the fix turns "kill stuck batch at 30 min" into "burn budget until the 4-6 h ceiling," an **8-12× cost regression on the exact failure the watchdog exists to catch.** It inverts the safety property: the loops most needing a kill emit the most signal. A meaningful signal would be bounded-rate and progress-correlated (distinct files changed / commits / phase transitions), not raw turn output.
4. **`elapsed` counts poll-ticks, not wall time** (`elapsed += poll_interval`, no `time.monotonic()`). Tolerable for a flat timer; **unbounded drift for a multi-hour ceiling** under host contention. An honest fix switches to monotonic-clock snapshots — a larger change to the loop the supervision invariants are pinned against — and must re-validate `recovery.py:103` under wall-time semantics.
5. **Stat-only and source-filtering are mutually exclusive.** Distinguishing parent vs child heartbeats needs content parsing (JSONL tail → `JSONDecodeError` torn-read handling), forfeiting the stat-only safety property. Cleanest resolution: **don't watch `overnight-events.log` for the orchestrator at all.**
6. **Size-rotation heuristic conflates three events** — true rotation, atomic-`os.replace` compaction, and inode swap can all shrink/jump size without being a stall; naive re-baseline can spuriously reset (mask a real stall).
7. **Safety inversion / new coupling.** The blind timer's one virtue is that nothing the child does extends its leash; the fix hands the child that power. And it couples a *safety* device to the correctness of the log path it supervises (path-resolution drift → watches the wrong file → kills healthy work or never fires).
8. **Testability requires seams.** `WatchdogThread.__init__` has neither a clock seam nor an activity-probe seam (runner_primitives.py:95-113); without them the reset path is only testable via flaky wall-clock subprocess timing. Adding injectable clock + activity-probe is part of the change, not optional.

## Open Questions

These are unresolved design decisions the Spec phase must settle (several with the user); the first four are **blocking** — they change scope.

1. **[BLOCKING] Orchestrator-site scope.** The orchestrator/planning subprocess has no honest child-driven progress signal, and watching `overnight-events.log` is a double-blind (Adversarial #1). Choose one: **(a)** bring a child-emitted orchestrator signal into scope (`--output-format=stream-json` parsed from stdout, or a child self-heartbeat) — larger change; **(b)** explicitly **defer the orchestrator site** to a follow-up ticket and scope this change to batch_runner only, stating plainly that the orchestrator 30-min kill is unaddressed; or **(c)** accept a never-reset absolute ceiling for the orchestrator as a deliberate, documented "bounded flat timeout" backstop (acknowledging it is the ticket's named non-goal, justified only as a last-resort safety net for a wedged planning child neither layer can otherwise catch).
2. **[BLOCKING] Is the absolute ceiling in or out, and at what value?** A never-reset ceiling is the only backstop against (i) a tight-loop that emits `dispatch_progress` forever and (ii) the orchestrator double-blind. But it is a flat raised timeout, and no batch-duration data exists to set it. **Decide whether to measure the legitimate batch/planning-duration distribution from existing `pipeline-events.log`/`overnight-events.log` history (p99 + margin) before picking a value** — or whether the ceiling is omitted (accepting the tight-loop budget regression) in v1.
3. **[BLOCKING] Batch liveness signal — `dispatch_progress` is a false-liveness proxy** (Adversarial #3). Decide the signal: raw `dispatch_progress` mtime (cheap, but lets a retry-loop live to the ceiling) vs a bounded-rate progress-correlated signal (distinct files changed / commit count / phase transition) which requires content parsing or a new emit. This directly trades off against Q2 (a weak signal makes the ceiling load-bearing).
4. **[BLOCKING] Clock + testability.** Adopt `time.monotonic()` snapshots and inject a clock + activity-probe seam into `WatchdogThread.__init__` (required for an accurate multi-hour ceiling *and* deterministic tests), or keep tick-counting and accept flaky wall-clock tests + ceiling drift? Recommendation from research: adopt the seams.
5. **Kill-reason telemetry.** Inactivity-kill vs ceiling-kill have different operator meanings (one says "the worker stalled," the other "tune the ceiling"). Decide whether `stall_flag` gains a reason marker (a small main-thread-visible field) so the morning report/recovery can distinguish them — vs keeping the single bit.
6. **Stat-only vs content-parsing.** If any site must filter parent-vs-child heartbeats, the watchdog must parse JSONL (with torn-read tolerance), forfeiting the stat-only safety property. Confirm the design keeps stat-only by *never* needing source-filtering (i.e. the batch site watches `pipeline-events.log` directly and the orchestrator question is resolved by Q1 (b)/(c), not by watching a filtered `overnight-events.log`).
7. **`_spawn_batch_runner` signature.** It has `events_path` but not `session_dir`; threading `pipeline-events.log` in requires a signature + call-site change (~2841). Mechanical, but pin it in the plan.
8. **Rotation handling.** `pipeline-events.log` / `overnight-events.log` are not rotated today, but the size-decrease re-baseline interacts with `os.replace`-style atomic rewrites (Adversarial #6). Decide whether to handle rotation at all or document the no-rotation assumption.

**Contradiction noted for Spec:** the Tradeoffs agent recommends the two-tier design with the orchestrator watching `overnight-events.log`; the Adversarial agent shows that exact choice is theater (a double-blind equal to the forbidden flat timeout). These do not reconcile without a scope decision on Q1.

## Resolution (Research Exit Gate — operator decisions 2026-06-22)

The blocking open questions were settled by the operator at the gate:

1. **Q1 (orchestrator scope) → FULL FIX.** Both sites get true activity-reset. The orchestrator/planning site must emit a **child-driven** progress signal so its watchdog resets on the child's own output, not the parent heartbeat. Leading mechanism (to confirm in Spec): switch the orchestrator invocation from `--output-format=json` to **`--output-format=stream-json`** so its `stdout_path` file grows incrementally as the agent streams — a genuine, **stat-only** child-progress signal — and update the runner's result-parsing to read the stream-json NDJSON terminal `result` object. (Avoids the double-blind; keeps the watchdog stat-only; does not require modifying the un-owned `claude` child beyond its CLI flags.) This enlarges scope to the orchestrator output-format + result-parsing path, accepted deliberately.
2. **Q2 (ceiling) → INCLUDED, fixed conservative value now.** A single never-reset absolute ceiling covers both sites as a budget-bound backstop (catches a chatty-stuck batch worker and any residual wedge). Set a generous fixed value (≈4 h, exact value finalized in Spec), **documented explicitly as a guess to revisit** once session-duration data accumulates — no measurement task in v1.
3. **Q3 (batch signal) → `pipeline-events.log` (`dispatch_progress`), stat-only**, with the ceiling backstopping the false-liveness/chatty-stuck-worker regression. Bounded-rate "meaningful progress" signals were considered and deferred — the ceiling is the agreed mitigation, not a richer signal.
4. **Q4 → adopt `time.monotonic()` + injectable clock & activity-probe seams** in `WatchdogThread.__init__`.
5. **Q5 → kill-reason marker** distinguishing inactivity-kill vs ceiling-kill (a ceiling ships).
6. **Q6 → stat-only, never source-filter** (resolved by Q1's stream-json signal, not by parsing `overnight-events.log`).
7. **Q7 → mechanical** signature threading for `_spawn_batch_runner`.
8. **Q8 → document the no-rotation assumption**; handle size-decrease defensively (re-baseline), no rotation support.

`STALL_TIMEOUT_SECONDS` stays `1800` (the silence-window for the inactivity tier), preserving the `recovery.py:103` `WEDGED(2700) > STALL(1800)` invariant.
