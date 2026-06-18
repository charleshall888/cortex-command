# Research: Out-of-process orchestrator-death detection & recovery for the run-now cortex-CLI overnight runner

**Lifecycle:** `overnight-run-now-runner-left-session` · **Backlog:** #308 · **Tier:** complex · **Criticality:** high

**Clarified intent:** Close the coverage gap that lets the run-now cortex-CLI overnight runner die silently — detect orchestrator/runner death (or hang) *out-of-process* (the in-process `WatchdogThread` dies with its host), and on detection recover cleanly: transition the session off `executing` → `paused`, write a partial morning report, reap orphaned worker agents, honor the #262 `worker_no_exit_report` halt, and make `runner.pid` liveness actionable.

> Research dispatched 8 agents (3 core + 4 chosen + adversarial). Several agent claims were **corrected by the adversarial pass against the code**; corrections are inline below and the live decisions are in `## Open Questions`.

---

## Codebase Analysis

### Process tree (run-now path) and who owns which state

```
cortex overnight start                          # parent CLI shim, exits after handshake
  └─ Popen(... --launchd, start_new_session=True)   [cli_handler.py:466-473]  → the RUNNER
       = runner.py run()  (SESSION LEADER; pid = os.getpid() written to runner.pid)
         ├─ caffeinate -i -w <runner_pid>            [runner.py:139]   # dies when runner dies
         ├─ per round: claude -p orchestrator subprocess (start_new_session=True)  [runner.py:1229]
         └─ per round: cortex-batch-runner subprocess (start_new_session=True)     [runner.py:1450]
              = run_batch()/execute_feature() → SDK leaf `claude` workers
                (SDK spawns via anyio.open_process with NO start_new_session → workers inherit
                 the batch_runner's pgid)   [installed SDK subprocess_cli.py:369-377]
```

- **WatchdogThread host = the runner process** (`runner_primitives.py:80-106`, `daemon=True`). Started per round in `_spawn_orchestrator` (`runner.py:1251`) and `_spawn_batch_runner` (`runner.py:1462`). It watches the *subprocess* via `proc.poll()` every 1s vs `STALL_TIMEOUT_SECONDS=1800` (`runner.py:87`) — it is a **process-aliveness** watchdog, NOT an event-silence watchdog despite docstrings/UI. Dies with the runner.
- **`overnight-events.log` writers = the runner + its batch_runner child.** **`pipeline-events.log` writer = the leaf workers** (`feature_executor.py` `pipeline_log_event`). This split explains symptom #1 (events frozen 19:00, pipeline advancing to 19:58 = runner stopped, workers orphaned).
- **State ownership:** `overnight-state.json` (authoritative `phase`/`paused_reason`/`features`) ← `state.py`; `~/.local/share/overnight-sessions/active-session.json` (host-global pointer + `phase`) ← `ipc.py`; `runner.pid` (`{schema_version, magic, pid, pgid, start_time, ...}`) ← `ipc.write_runner_pid` from `_start_session` (`runner.py:1002-1045`).

### The defect, located

Every recovery primitive lives **inside the runner** and fires only from its control flow:
- `WatchdogThread` (daemon thread), `_cleanup`/`_run_cleanup_on_shutdown` (signal-driven, `runner.py:808-914`), `_transition_paused` (`runner.py:410`), `_generate_morning_report` (`runner.py:441`), `_terminate_descendant_tree` (`runner.py:155-205`).
- There are **two** teardown paths: `_cleanup` (signal) **and** a `finally` block (`runner.py:2789-2798`) that kills `spawned_procs` on any normal/exception loop exit. Orphans + stuck-`executing` survive only when **neither** runs → **hard-kill (SIGKILL/OOM, no `finally`)** or **alive-but-wedged (loop never exits, `finally` never reached)**.

### Files that will change (with line regions)

- **Detection signal source** — `cortex_command/overnight/status.py`: `render_status` (317) already computes both the staleness string (`_read_last_event_ts` 202 vs `WATCHDOG_TIMEOUT_MINUTES=30`, 76) and `_is_runner_pid_live` (141). Today purely display; the executing render (`:401-409`) prints "fires at 30m" with **no actor**.
- **Closest existing analogue** — `cortex_command/overnight/fail_markers.py`: `_advisory_is_stale` (266) + `scan_advisory_dirs` (374) already implement a read-time liveness predicate (age + `verify_runner_pid` + phase) but **read-only** and only for the *pre-round-loop* window. The fix is the symmetric *mid-round-loop* predicate made **write-back**.
- **Halt wiring (#262)** — `feature_executor.py:75` `_SESSION_HALT_ERROR_TYPES=("budget_exhausted","api_rate_limit")` (no `worker_no_exit_report`); no-exit branch `:857-865` sets `silent_worker_error`→`FeatureResult.error`; gate `:872` `total_commits==0`. `constants.py:22-24` `_SYSTEMIC_ERROR_TYPES` includes `worker_no_exit_report`; systemic check `feature_executor.py:783` reads `DispatchResult.error_type`. Halt propagation: `orchestrator.py:406-429`, `:508-522`, transition `:556-574`.
- **Transition/report/reap** — `state.py:transition` (494; `PHASES` 40; `paused_reason` 238), `save_state` (394 atomic), `ipc.update_active_session_phase` (465); `report.generate_and_write_report` (`report.py:2343`); reaping via recorded pgids.

### Conventions
- Event logging via `events.overnight_log_event(...)`; every `"event"` literal must be in `bin/.events-registry.md` (`cortex-check-events-registry` gate). New recovery event(s) need registration.
- `runner.pid` schema change ⇒ bump `schema_version` and `MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION` together (`ipc.py:82-84`, `verify_runner_pid:410-415`).
- Atomic writes (tempfile + `durable_fsync` + `os.replace`); best-effort recovery (swallow exceptions so one failure doesn't block the rest).
- Docs: `docs/overnight-operations.md` owns the round loop/orchestrator behavior — update it; link from `docs/internals/pipeline.md`.

---

## Web Research

- **The core problem is canonical:** an in-process watchdog cannot detect its own host's death/freeze; a bare process-existence check sees a running-but-stuck process and does nothing. Remedy is always an **external** owner the process must affirmatively reach (heartbeat) or that owns it as a child (launchd/systemd).
- **systemd `WatchdogSec` + `sd_notify("WATCHDOG=1")`** — reference design for "alive-but-stuck": daemon pings at ½ interval; PID 1 declares it hung if no ping within `WatchdogSec`. Rule of thumb: **timeout ≈ 3× heartbeat interval**.
- **launchd (macOS):** `KeepAlive` (restart on death; can't run recovery logic), `StartInterval` (periodic poller cadence — the viable primitive), `WatchPaths`/`QueueDirectories` (fire on **change**, not absence → cannot detect staleness), `ThrottleInterval` (default **10s**, crash-loop guard). **StartInterval jobs do not run while the machine sleeps.**
- **PID-file done right:** store pid + `create_time()`; re-verify create_time before signalling (PID-reuse defense). psutil ≥6.0 `process_iter()` no longer auto-checks reuse, but `kill()`/`terminate()` still pre-check — do the create_time compare yourself. This is exactly the existing `verify_runner_pid` (±2s) contract.
- **macOS reaping:** **no `PR_SET_PDEATHSIG`, no `PR_SET_CHILD_SUBREAPER`**; orphans reparent to launchd (PID 1). The `setsid`+controlling-pty SIGHUP trick is unreliable on macOS. Need an **explicit reaper**: track child pids / use a process group (`killpg`) for well-behaved children, and/or scan `PPID==1` for escapees — each kill `create_time`-verified, skipping pids 0/1/2.
- **Split-brain / fencing literature:** external recovery must not kill an alive-but-unreachable peer. Mitigations: grace periods before fencing, generous timeouts, **idempotent** recovery. Directly applicable: don't pause/reap a session that's actually still progressing.
- **Reference implementations:** `proc-janitor` (macOS/Linux orphan reaper: 5s scan, start_time-verified kill, 30s grace, SIGTERM→SIGKILL), `sdlogwatchdog` (staleness keyed on log recency), k8s liveness-probe-on-heartbeat-file (`find -mmin`).

**Anti-patterns:** in-process watchdog as sole liveness; naive pidfile check; too-aggressive staleness timeout (false positives under load/GC pauses); relying on `killpg` alone when children `setsid`/double-fork escape the group.

---

## Requirements & Constraints

- **Session-phase model is exactly four values:** `planning | executing | paused | complete` (`pipeline.md:156`; `state.py:40` `PHASES` adds transient `starting`). **No `failed` session phase** — `failed` is only a *feature* status (`pipeline.md:37`). Forward-only `planning→executing→complete`; the **only** non-complete escape is `→ paused` (`pipeline.md:19-20`). ⇒ the ticket's "paused/failed" resolves to **`paused`** at the session level; any session `failed` phase would be a new enum addition to flag.
- **Budget exhaustion is the documented precedent** for "stop without aborting in-flight work" → `paused` (`pipeline.md:25`).
- **runner.pid IPC contract** (`pipeline.md:155`, `:28`): JSON `{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, mode 0o600, atomic; **cleared on clean shutdown**; cancel verifies magic + schema bound + psutil `create_time` ±2s before signalling. Consumers: `cancel`, `status` (`observability.md:64-68`), pre-install in-flight guard (`pipeline.md:158`), MCP control plane. Edge case `observability.md:117`: "Runner died but lock not cleaned up; `kill -0` non-zero; status reports 'dead (stale PID)'" — the exact behavior the detector must act on.
- **Morning report two paths** (`pipeline.md:24`): `cortex/lifecycle/sessions/{id}/morning-report.md` (gitignored archive) + `cortex/lifecycle/morning-report.md` (tracked latest, committed to local `main` by the runner). Philosophy: **"Surface failures in the morning report; keep working unless blocked"** (`project.md:15`), **"Graceful partial failure"** (`project.md:52`). ⇒ a partial report on the death path is required.
- **active-session.json** (`pipeline.md:156`): shares runner.pid schema + `phase`; **retained on `paused`** (preserves dashboard/statusline visibility), cleared on `complete`. ⇒ recovery must keep the pointer present, not clear it.
- **Observability surfaces are READ-ONLY w.r.t. session state** (`observability.md:93`, `:99`; MCP "stateless" `pipeline.md:157`; status is a "single-screen snapshot" `overnight-operations.md:95`). ⇒ recovery *writes* must originate from a writer-authorized surface, **not** the `status`/dashboard read path.
- **Destructive ops preserve uncommitted state** (`project.md:56`): cleanup removing worktrees/branches/sessions SKIPs on uncommitted state. ⇒ reaping must SIGTERM-with-grace and route reaped features through `handle_interrupted_features` rather than discarding worktrees; never auto-delete integration branches (`pipeline.md:22`).
- **Atomicity/concurrency:** all state writes atomic tempfile+`os.replace` (permanent constraint `pipeline.md:138`); readers unlocked, made safe by forward-only/idempotent transitions.
- **File-based state, no database** (ADR-0001): ground the detector in existing file artifacts + an out-of-process liveness check. **Correction (adversarial):** ADR-0001 is *"no database"*; "no daemon" is an incidental virtue, **not** a binding prohibition — there is no no-daemon ADR. The guardian-vs-no-guardian call must be made on its own merits.
- **No ADR governs the process/runner model** — a hard-to-reverse process-model decision here is a candidate for a new ADR under the three-criteria gate.

---

## Prior Coverage & Regression Archaeology

**The deletion timeline explains the whole gap:**

| Date | Event | Commit |
|---|---|---|
| 2026-04-01 | #001 patched `runner.sh` (bash) watchdog | `f228f2fb` |
| 2026-04-07 | #039 patched `runner.sh` (bash): SIGHUP trap, PGID kill, events | `21f42f34` etc. |
| 2026-04-24 09:20 | `runner.py` **created from scratch** | `c2a09f62` |
| 2026-04-24 10:38 | `runner.sh` **deleted (same day)** | `3cbf00ed` |

#001/#039 fixed a file deleted ~17 days later; `runner.py` re-implemented their *concepts* (R12/R14) **only for signaled death**.

- **#001** (process-group kill): concept survives — `start_new_session=True` on spawns, `os.killpg` in `_kill_subprocess_group`, SIGTERM tree-walker `_terminate_descendant_tree`. But the WatchdogThread that drives it is an **in-process daemon thread** on a flat 1800s subprocess timeout; dies with the runner.
- **#039** (silent crash / signals): concept survives as `_run_cleanup_on_shutdown` (transition→paused, partial report, reap, clear pid) — **but only when a signal is delivered** (`shutdown_event` set). #308 is *signal-less* death → none of it runs.
- **#262** (systemic breaker): the ticket said "add `worker_no_exit_report` to `_SESSION_HALT_ERROR_TYPES`" — **that is not what landed.** It went into a separate `_SYSTEMIC_ERROR_TYPES` + `systemic_pauses_in_batch` counter (threshold 3). Two reasons it can't fire here: (1) the no-exit branch sets `FeatureResult.error`, but the systemic check reads `DispatchResult.error_type` — **different fields, never connected** (the ticket's own unfixed caveat); (2) escalation gated on `total_commits==0`; commit `ca89f643` documents "commits>0 ⇒ bookkeeping-only." Systemic counter is per-feature-result (5 events → ≤2 results, 2<3).
- **#277** (scheduled-path silent kill): P0 fixed the **scheduled/launchd** detach only. It built `_is_runner_pid_live` — **but it's dead code on the executing path**: `_is_scheduled_dormant` returns early when `phase in ("executing","complete")` (`status.py:179`), so liveness is never consulted while executing. The primitive exists, unused for the case that matters.
- **#278** (unknown tier): tangential; did not touch the transition/report/reap paths.

**Extend vs net-new:** liveness *probe* (`verify_runner_pid`) = **extend**; the *supervisor actor* that runs it periodically + acts = **net-new**. Reaping/transition/report *bodies* exist (extend); their **external trigger** is net-new. runner.pid = **mostly already correct** (flag the 28888 claim). The #277 dead-code fix (consult the primitive on the executing path) is **small**.

---

## Root-Cause Forensics

**Ranked contributing causes:**

1. **In-process-only liveness architecture** — no out-of-process actor; the WatchdogThread watches subprocesses, not the runner; the "fires at 30m" line is a passive log-derived display computed at query time, not gated on runner liveness. This is why the failure was silent and unrecoverable. (HIGH confidence — pure code fact.)
2. **Systemic breaker counts feature-results not events, and `worker_no_exit_report` never reaches the field the halt-check reads** — so #262 under-counted (2<3) and there was no immediate-halt path. (HIGH.)
3. **The runner stopped driving the round loop ~19:00 without a clean `_post_loop` or signal** — exact trigger undetermined from code alone. `plan commit failed rc=1` is logged-and-swallowed (`runner.py:700-708`), so **not** the direct raiser. (LOW–MEDIUM — needs runner-stderr tail / batch-results presence.)
4. **`start_new_session=True` orchestrator/batch_runner are reaped only on the SIGTERM tree-walk** — a runner dying without SIGTERM orphans the live worker subtree (explains pipeline-events advancing to 19:58).
5. **External trigger (out of scope):** the wild-light pre-commit gate blocked all commits — the upstream cause; the harness non-response is the tracked defect.

**Most-likely incident mode (adversarial refinement):** *alive-but-wedged* or *hard-killed*. The orchestrator runs a **5-minute HEARTBEAT loop** writing to the event log (`orchestrator.py:462-486`); that heartbeat **also** stopped at 19:00 ⇒ the orchestrator's asyncio event loop hung. **If alive-but-wedged, `verify_runner_pid` reads ALIVE** — so a pid-liveness detector is blind to it; only **heartbeat/event-log staleness** catches it.

**runner.pid "28888 dead immediately" — corrected:** `runner.pid` records the runner's own `os.getpid()` (the `start_new_session=True` session leader); `_build_async_spawn_argv` execs the CLI module directly — **there is no intermediate launcher process.** The handshake reads `pid` *from* runner.pid and returns it to the user, after an `os.kill(pid,0)` check (~5s) that 28888 passed. So 28888 was the **real runner**, alive at handshake, that died shortly after. The genuine defect: silent death leaves runner.pid **stale** (the `finally` at `runner.py:2789` doesn't clear it) while state stays `executing` — and nothing acts on the correctly-"dead" reading.

---

## Tradeoffs & Alternatives

**The recovery *action* is identical across all triggers** → build it once: `recover_session(session)` = verify-dead → transition→`paused` (set `paused_reason`) → partial report → reap orphans → clear stale runner.pid, mirroring the `_cleanup` ordering but from disk.

| Mechanism | Fires when runner dies? | Catches alive-but-wedged? | Complexity / alignment | Verdict |
|---|---|---|---|---|
| **A. Long-lived sibling guardian** (per session) | Yes | Yes (if log-keyed) | Highest new surface; who-watches-the-watchman; no codebase precedent | **Reject** as per-session daemon |
| **B. Lazy recovery in `cortex overnight status`** | Only when a human runs `status` | Yes (log-keyed) | Smallest, but **violates read-only `status`** → must be a separate writer verb; then it's a **manual button, not a detector** | Keep as the **manual recovery verb** |
| **C/D. launchd `StartInterval` guardian, log-staleness-keyed** | Yes, next tick — **but** caffeinate dies with runner → Mac sleeps → may not fire until wake; **and run-now installs no plist / no GC** | Yes (still awake while wedged) | Reuses launchd backend; macOS-only | The **only automatic** option — but install/GC + sleep problems are unsolved (see Open Questions) |

**Primary detection signal = event/heartbeat staleness, not pid-liveness** (it's the only signal that catches the wedged case and literally "moves the 30-min watchdog out-of-process"). Use the **5-min HEARTBEAT event** as the freshness source (healthy long work refreshes it; a hung loop stops it) rather than a flat file-mtime check. pid-liveness is a **secondary, corroborating** signal.

---

## Recovery & Cleanup Design

- **Transition→paused:** `state.transition(state,"paused")` (pure) + atomic `save_state` + set `state.paused_reason` manually (transition takes no reason arg) + `ipc.update_active_session_phase(id,"paused")` (retain the pointer). Only legal exit from stuck `executing`; idempotent (re-pause no-ops / `transition` rejects illegal moves).
- **Crash-vs-clean auto-resume is UNSAFE today.** `recovery_attempts`/`recovery_depth` are **per-feature** only (`state.py:105-106`); there is **no session-level crash counter** and **no cross-run breaker**. A silent crash leaves `executing` with **no `paused_reason`**. Re-running `cortex overnight start` resumes (`_count_pending` counts pending+running+paused; `handle_interrupted_features` resets running→pending preserving counters; loop re-dispatches with no `phase=='paused'` guard). For a **deterministic** environmental failure (the 308 pre-commit gate) this **crash-loops**. ⇒ add a session-level discriminator (`paused_reason="orchestrator_crash"` + a `crash_recovery_attempts` counter) and a resume-side guard (refuse / require `--force` above a small bound). Distinct from a clean budget pause (always safe to resume).
- **Partial morning report — already external-callable & partial-safe.** `report.generate_and_write_report(...)` reads only disk paths (all optional, degrade gracefully), no `phase=='complete'` guard, fully decoupled from runner memory; `--interrupted` mode exists (prepends a banner). Not yet wired to any external recovery path. A crash report should additionally convey: death timestamp (last overnight-event vs last pipeline-event = the 58-min gap), N features still running/pending, orphan-reap outcome.
- **Reaping — simpler than the divergent-pgid story suggested.** Leaf SDK workers inherit the **batch_runner's pgid** (SDK `anyio.open_process`, no `start_new_session`). Divergence is only runner ↔ orchestrator/batch_runner. ⇒ **record the orchestrator + batch_runner pgids into a session sidecar at spawn**, then `os.killpg(pgid, SIGTERM)`→grace→SIGKILL after a `create_time` check. This is narrower than env-enumeration and avoids the enumerate-then-kill TOCTOU window. Keep env-match (`CORTEX_RUNNER_CHILD=1` + `LIFECYCLE_SESSION_ID`, session-filtered) only as a **fallback** for the brain-path `claude -p` Task-tool subagents (verify that path's grouping). Never broad-match all `claude` (would kill the operator's interactive sessions). Honor SKIP-on-uncommitted: SIGTERM grace lets workers finish an in-flight commit; route reaped features through `handle_interrupted_features` on resume.
- **runner.pid fix = clear-on-crash, not record-the-right-pid.** The leader pid is already recorded correctly; the fix is to ensure a crash doesn't leave a stale-but-"dead"-verifiable pid masking the executing leak (broaden the `finally`/`atexit`, or have the recoverer own clearing it). A meaningful runner.pid is the prerequisite for the **pid-based corroborating** signal and for the reaper's create_time checks.
- **Idempotency / race safety:** gate every destructive step on a fresh `verify_runner_pid == False`; run the whole verify→pause→reap→report→clear sequence under the existing `.runner.pid.takeover.lock` (`ipc._acquire_takeover_lock`). **But the takeover lock does NOT serialize `save_state`** — an alive-but-wedged runner that unwedges can overwrite `paused`→`executing` (its in-memory `state_lock` gives no cross-process exclusion). ⇒ **SIGKILL the confirmed-stale runner pid before transitioning** so no live writer can revert. Add a "recovery already done" marker (`recovery-complete.json` or `paused_reason="orchestrator_crash_recovered"`) so a second pass and the resume-side guard detect handled crashes. The runner's `_transition_paused`/`_generate_morning_report` are **not** externally reusable (in-process `threading.Lock`); re-implement from the pure primitives.

---

## Adversarial Review

- **Detection by runner.pid liveness is half-blind.** The likely incident mode is *alive-but-wedged* (heartbeat stopped at 19:00, workers to 19:58), where `verify_runner_pid` reads **alive**. Only event/heartbeat staleness catches it. Spec the detector on **missed 5-min HEARTBEAT events**, not pid-liveness or flat file-mtime.
- **Reaping premise corrected:** leaf workers share the batch_runner pgid (SDK spawn has no `start_new_session`) → recorded-pgid `killpg` reaches them; env-match is the fragile fallback (coupled to SDK env-merge; `LIFECYCLE_SESSION_ID` added only conditionally in `dispatch.py:553-554`).
- **Recovery primitives not cleanly reusable** (in-process locks); recoverer must use raw `state.transition` + `save_state` + `report.generate_and_write_report --interrupted` under the fcntl lock.
- **Last-writer-wins race:** wedged runner can revert `paused`→`executing` → SIGKILL-before-transition.
- **caffeinate dies with the runner** (`-w <runner_pid>`) → Mac sleeps after death → `StartInterval` guardian won't fire promptly when most needed (dead runner). It *can* fire while wedged (caffeinate still up) — reinforcing the heartbeat-staleness signal over pid-liveness.
- **No installer/GC for a run-now guardian plist** (run-now self-detaches via Popen; `--launchd` is just an internal discriminator). Per-session `StartInterval` is unviable; either a single persistent guardian scanning all `executing` sessions (accept the long-lived process + its watch story) or accept a manual recovery verb for run-now.
- **Breaker facet likely NOT load-bearing for THIS incident:** round-2 results were never consumed by the dead/wedged runner, so even a correctly-wired halt (which surfaces *to the runner*) wouldn't have fired. Fixing it addresses a real latent bug but gives false confidence about 308. **Recommend decoupling into its own ticket.**
- **ADR citation correction:** ADR-0001 doesn't prohibit daemons; argue the guardian on its merits.
- **MUST-escalation note:** halting the *session* on `worker_no_exit_report` (vs pausing the one feature, the current behavior) needs an evidence artifact per CLAUDE.md's policy before escalating.

---

## Open Questions

1. **[SCOPE — resolve at Spec §4] Decouple the `worker_no_exit_report` breaker fix?** The adversarial pass confirms it is a genuine latent bug but **not the cause of #308** (the dead/wedged runner never consumed round-2 results). The user chose full scope at Clarify; this finding is new. Decide: keep it bundled (fix the `FeatureResult.error` vs `DispatchResult.error_type` disconnect + the `total_commits==0` gate, and decide pause-feature vs halt-session) **or** split it to a sibling ticket so #308 stays focused on out-of-process detection+recovery.
2. **[DESIGN — central] Automatic trigger for the run-now path.** Per-session `StartInterval` guardian is unviable (no installer/GC; caffeinate-death → sleep). Choose: **(a)** a single **persistent guardian** LaunchAgent that scans all `executing` sessions (accept a long-lived process; define its own liveness/restart story), or **(b)** **manual recovery verb only** for run-now (operator runs `cortex overnight recover`), or **(c)** a hybrid (manual verb now; persistent guardian later). This is the load-bearing architecture decision for the spec.
3. **[DESIGN] Primary detection signal + threshold.** Confirm the recommendation to key on **missed 5-min HEARTBEAT events** (not pid-liveness, not flat 30-min mtime). Verify **which process emits the heartbeat during the batch_runner phase** (`orchestrator.py:462-486`) — if the brain-path orchestrator isn't active then, a heartbeat-only signal could miss the batch_runner-only window.
4. **[DIAGNOSIS — needs session logs] `total_commits` at the time of the no-exit-reports.** Forensics inferred `==0` (gate blocked all commits → 2 paused results, 2<3 undercount); archaeology inferred `!=0` (no-exit-report swallowed entirely). The precise breaker fix differs. Resolve by inspecting the session's `overnight-events.log` (count `worker_no_exit_report` rows vs `feature_paused`/systemic rows). If logs are unrecoverable, the breaker fix must handle **both** paths.
5. **[VERIFY] runner.pid "28888 dead immediately" reproduction.** The standard run-now path records the live leader pid; the observation is explained as *stale-after-silent-death*. Confirm no path records a transient pid (a genuine early-crash-in-cold-start-window bug would be separate). If unreproducible, the runner.pid facet reduces to **clear-on-crash**.
6. **[VERIFY] Brain-path `claude -p` subagent grouping.** Confirm whether the orchestrator's Task-tool subagents share a reapable pgid or need env-match, so the reaper covers that path too.
7. **[DESIGN] Crash-loop guard bound.** Decide the `crash_recovery_attempts` threshold and whether exceeding it pauses-and-stops vs requires `--force`, given a deterministic environmental failure (the #308 pre-commit gate) would otherwise re-trigger every resume.
8. **[CONTRACT] Does any new `runner.pid` field (e.g., recorded child pgids sidecar) require a schema bump?** If the pgids sidecar is a separate file, no runner.pid bump is needed; if folded into runner.pid, bump `schema_version` + `MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION` together and register any new event in `bin/.events-registry.md`.
