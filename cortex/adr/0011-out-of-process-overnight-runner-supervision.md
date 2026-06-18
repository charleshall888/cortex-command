---
status: accepted
---

# Out-of-process supervision for the overnight runner

## Context

Every liveness and recovery primitive in the overnight runner lives **inside the runner process**: the in-process `WatchdogThread` (watches subprocesses, dies with its host), the signal-driven `_cleanup` teardown (fires only on a delivered SIGTERM/SIGINT), and the descendant-tree reaper (walks the runner's own children at signal time). When the runner dies hard (SIGKILL/OOM, no signal handler runs) or wedges (its event loop hangs, `finally` never reached), none of these fire. The session is left stuck in `phase: executing` with orphaned worker processes reparented to launchd (PID 1) and no morning report — the operator wakes to a silently-hung machine. This is a recurring failure class (#039/#278, then #308 on the run-now cortex-CLI path) that **no in-process mechanism can fix, because a supervisor cannot detect its own host's death.**

## Decision

Introduce an **out-of-process supervision model**: a single persistent host-level launchd guardian (`cortex overnight guardian install`) plus a manual `cortex overnight recover [--session <id>]` verb, both of which invoke a writer-authorized recovery core (`cortex_command/overnight/recovery.py:recover_session`). The recovery core, under the existing takeover flock, runs: transition→`paused` (`paused_reason="orchestrator_crash"`, increment `crash_recovery_attempts`) → update the active-session pointer → write a partial morning report (with an `orchestrator_crash` interrupted banner) → reap session-marked orphans → clear the stale `runner.pid` → write a standalone atomic `recovery-complete.json` idempotency sidecar.

- **Detection is keyed primarily on the false-positive-free runner-pid-death signal** (`ipc.verify_runner_pid` reads dead — a live runner's pid is always alive, so this cannot false-positive on healthy work). Event/heartbeat **staleness** for the alive-but-wedged case is a deliberately later, lower-priority signal: it required first closing the planning-phase heartbeat blind window (a runner-level `HEARTBEAT` covering every `executing` sub-phase) and using a threshold (`WEDGED_STALENESS_SECONDS = 2700`) **strictly greater** than the in-process watchdog's `STALL_TIMEOUT_SECONDS = 1800` so the runner's own watchdog gets first crack and false positives under load are avoided.
- Because a wedged runner is still alive and could overwrite `paused`→`executing`, the wedged path **SIGKILLs the create_time-verified runner before transitioning**. The pid-death path needs no kill (no live runner).
- Recovery is **re-implemented from the pure `state`/`ipc`/`report` primitives** — the runner's `_transition_paused`/`_generate_morning_report` require an in-process `RunnerCoordination` (threading locks) and are not externally reusable.
- Orphan reaping uses **session-marker enumeration** (`CORTEX_RUNNER_CHILD=1` AND `LIFECYCLE_SESSION_ID == session_id`, via `psutil`, with a bounded fixpoint re-scan and a per-signal create_time TOCTOU guard); `CORTEX_RUNNER_CHILD` is the load-bearing discriminator since `LIFECYCLE_SESSION_ID` is also present in interactive sessions.
- A **crash-loop resume guard** refuses to auto-resume an over-bound `orchestrator_crash`-paused session without `--force`, because the #308 trigger class (e.g. a pre-commit gate blocking every commit) is deterministic and would otherwise crash-loop. The guard acquires the takeover lock and reads the sidecar/counter **before** `handle_interrupted_features` mutates state, since the takeover lock does not serialize `save_state` cross-process.

## Three-criteria gate clearance

- **Hard to reverse** — adds a long-lived process model (a persistent launchd agent), a second recovery code path, and new writer surfaces (`recover`/`guardian` verbs); unwinding would touch the process model, the launchd integration, and the recovery module across many call sites.
- **Surprising without context** — a fresh contributor would not predict why detection keys on pid-death rather than the more general staleness signal, why recovery is re-implemented rather than reusing the runner's helpers, why reaping uses env-match enumeration rather than `killpg`, or why the completion marker is a standalone sidecar rather than a `paused_reason` value.
- **Real trade-off** — automatic, human-free detection is bought at the cost of simplicity (a daemon + a duplicated recovery path) and, on macOS, a hard-dead detection latency bounded to machine-wake (see below). At least one credible alternative was considered and rejected for each axis (next section).

## Rejected alternatives

- **In-process watchdog only** — structurally incapable of detecting its own host's death or freeze; the status quo that produced the failure.
- **Per-session launchd guardian** — no installer/GC for the run-now path, and per-session agents multiply the install/teardown surface; a single host-level agent scanning all `executing` sessions avoids it.
- **Lazy recovery folded into `cortex overnight status`** — `status` is a read-only observability surface (`observability.md`); recovery writes must originate from a writer-authorized verb. Kept as the manual `recover` verb instead, with the guardian as the automatic trigger.
- **Recorded child-PGID `killpg`** — explicitly rejected in the codebase (`runner.py:_terminate_descendant_tree` docstring): the runner does not know in advance which PGIDs `batch_runner` workers will use, and a dead runner's children reparent to launchd. Session-marker enumeration is used instead.
- **`paused_reason` flip as the completion marker** — lives inside `overnight-state.json` and is clobberable by a concurrent resume's unlocked `save_state`; a standalone atomic `recovery-complete.json` sidecar is the race-authoritative marker instead.
- **`KeepAlive` on the `StartInterval` guardian job** — launchd-incoherent: a `StartInterval` job exits each tick and unconditional `KeepAlive` would relaunch it continuously (throttled only to `ThrottleInterval`). `StartInterval`'s own periodic re-fire is the restart-on-crash supervision; the guardian omits `KeepAlive` and uses `ThrottleInterval` as the crash-loop floor.
- **Migrating off file-based state** — out of scope; recovery is grounded in existing file artifacts. ADR-0001 is "no database," not "no daemon," so the guardian does not conflict with it.

## Consequences and residual hazard

- A long-lived guardian process now exists; its who-watches-the-watchman story is launchd's own periodic re-fire plus the `ThrottleInterval` floor, backed by the manual `recover` verb.
- There are two recovery code paths (the runner's in-process teardown and the out-of-process recovery core); they are intentionally not shared because the in-process helpers require threading locks.
- **macOS caffeinate-sleep ceiling**: `caffeinate -i -w <runner_pid>` dies with the runner, so a hard-dead runner lets the host idle-sleep and the `StartInterval` guardian fires only on next wake. The guardian catches the alive-but-wedged case promptly (caffeinate still up) and the hard-dead case on next wake — still strictly better than the status-quo "stuck forever"; the manual verb is the immediate path. Documented in `docs/overnight-operations.md`.
- Whether the brain-path `claude -p` internal Task-tool subagents carry the env markers is runtime-unconfirmed; the reaper's fallback surfaces any unmatched worker class as un-reaped in the report rather than broad-matching all `claude` processes.

Background and the full operational model live in `docs/overnight-operations.md` (§ Out-of-Process Supervision); this ADR is the canonical home for the decision and its rejected alternatives.
