---
schema_version: "1"
uuid: a2356508-a71f-42c1-81a0-2f9d32954c85
title: "Scheduled overnight runs fire but the runner is silently killed (no setsid on macOS) + launch-flow observability gaps"
status: complete
priority: high
type: bug
created: 2026-06-01
updated: 2026-06-02
complexity: complex
criticality: high
spec: cortex/lifecycle/scheduled-overnight-runs-fire-but-the/spec.md
areas: ['overnight-runner']
---
**Why:** During a live `/overnight` launch (session `overnight-2026-06-01-1518`, 2026-06-01) a run scheduled for 12:55 **fired but did no work and left no error**: launchd recorded `runs=1, last exit=0`, yet the runner logs were empty, no runner process was alive, and `cortex overnight status` stayed frozen at `session_start`. Root cause: the launchd launcher template detaches via `setsid nohup caffeinate -i cortex overnight start …`, but **stock macOS ships no `setsid`**, so it falls back to `nohup … & disown`. Under launchd, when the launcher exits 0 the whole job process group is reaped — `nohup`/`disown` defeats SIGHUP + shell job-control but does NOT create a new session, so the runner is killed before it starts. (The launcher's own comment, "reparents to PID 1 once the parent exits," is wrong for the launchd context.) Starting the same session via the run-now path (`cortex overnight start`) instead produced a proper session leader (`STAT Ss`) that survived — confirming detachment is the difference. Net: **scheduled overnight runs are unreliable and fail silently on any Mac without `setsid`** (the headline defect), and several adjacent issues hid the failure and confused the surrounding flow.

**Role:** Make scheduled overnight runs actually run — and fail *loudly* when they can't — and remove the launch-flow rough edges that masked this. Today, scheduling a run yields nothing at fire time with zero signal that anything broke.

**Integration:** Prioritized fixes (could be decomposed into an epic + children):

- **P0 — runner detachment (bug).** Stop reimplementing detach in bash around a `setsid` binary that may be absent. Reuse the daemonization that demonstrably works: have the launcher simply invoke `cortex overnight start` and let cortex `os.setsid()` itself (it already does on the run-now path → `STAT Ss`), or exec a `python -c 'import os; os.setsid(); os.execvp(...)'` shim (Python is already a dependency). Must be verified on stock macOS (no util-linux).
- **P0b — silent failure, no diagnostic (bug).** The launcher writes `scheduled-fire-failed.json` only on cortex-binary exec failure *before* backgrounding; a post-background teardown writes nothing, so the morning-report scanner and status see no error. Add a fire-time liveness check — the runner writes `runner.pid`/a heartbeat at startup and the schedule path verifies it appeared within N s — and surface "fired but runner never came up" in status + morning report.
- **P1 — schedule verifier false-failure (bug).** `cortex overnight schedule` polls `launchctl print` for the literal `state = waiting` within 1.0 s; Darwin 25 / macOS 26 reports `state = not running` for an armed-but-dormant `StartCalendarInterval` agent, so the command exits non-zero although the job is correctly armed. Accept `not running` (and `waiting`) as armed, or verify by parsing the registered calendar block + enabled state rather than the volatile `state` string. Critically, the early abort **skips bookkeeping** → `scheduled_start` stays `null` and the schedule is never recorded in the session registry; ensure bookkeeping completes regardless of the liveness probe.
- **P1b — `session_start` logged at prep time, not fire time (skill flow).** The `/overnight` flow logs `session_start` *before* the run-now/schedule branch (step 7.5), so a scheduled run's `session_start` lands ~1h40m early. `cortex overnight status` then shows an alarming "Elapsed 1h40m / watchdog 1h37m since last event (fires at 30m)" while merely waiting, and the runner re-logs a second `session_start` at fire time (the prep one tagged `session_id:"manual"` because `LIFECYCLE_SESSION_ID` is unset). Don't pre-log `session_start` on the schedule path (let the runner log it at fire), or anchor elapsed/watchdog to `scheduled_start`.
- **P2 — status has no scheduled/dormant state.** `cortex overnight status` always renders executing-with-watchdog even when no runner is alive and a fire is pending; it should distinguish scheduled-dormant vs executing vs stalled (by checking `runner.pid` liveness). Downstream of P1/P1b.
- **P2 — doc / DX footguns.** (a) The skill's launch command uses `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/…`, but session paths resolve via `_resolve_user_project_root()` (cwd/git); `CORTEX_COMMAND_ROOT` was stale (pointing at the dev clone), so following the doc literally targets the *wrong repo*. Use `cortex --print-root`'s root or `bootstrap_session`'s returned `state_dir`. (b) The planning helpers (`select_overnight_batch`, `render_session_plan`, `bootstrap_session`, `extract_batch_specs`, `log_event`, `validate_target_repos`) have no CLI subcommands; the skill must shell into the uv tool-venv python (system `python3` can't import `cortex_command`, and `python3 -m cortex_command.<module>` fails outside the venv). Consider a stable `cortex overnight prepare/bootstrap` (or one `cortex overnight launch`) so the flow calls a CLI, not internal APIs. (c) `bootstrap_session` does not create the top-level `cortex/lifecycle/overnight-state.json` symlink (the runner does, at startup), so `load_state()` with no args raises `FileNotFoundError` between bootstrap and fire — document the explicit-path contract or have bootstrap create the symlink.

**Edges:**
- `caffeinate -i` only prevents idle sleep *during* the run; it does not wake the Mac to fire the calendar job (asleep at fire → runs on next wake). Orthogonal to P0 but worth a status/docs note.
- Whatever replaces the bash detach must still redirect std streams to the per-session logs, keep `caffeinate`, write `runner.pid`, and not double-launch if a run-now already holds the runner lock (respect the cross-cancel guard / `--force`).
- The one-shot `StartCalendarInterval` (full Y/M/D/H/M) won't re-fire; after a spent fire, `launchctl bootout gui/$(id -u)/<label>` cleans it — the GC pass should also reap stale plists/launchers under `$TMPDIR/cortex-overnight-launch/`.
- **Repro requires a Mac without `setsid`** (no util-linux). Linux CI *has* setsid and will NOT reproduce P0 — add a macOS-specific test or a detach unit test asserting a new session id (`os.getsid`), not merely "process backgrounded."
- Out of scope (consuming-repo / environment, not cortex-command): the gaggimate-barista damage-control hook's substring false-positives (`os.environ`→`.env`, `.keys()`→`.key`, `~/.gnupg`) and signed-commit-under-sandbox friction during the pre-flight commit. Optional: the skill could warn when the consuming repo signs commits and the sandbox blocks `~/.gnupg`.

**Touch-points:**
- Launcher template + schedule backend (`MacOSLaunchAgentBackend._install_launcher_script` and the `state = waiting` verifier) under `cortex_command/overnight/`.
- Run-now daemonization to reuse: `cortex overnight start` (`cortex_command/cli.py` / `cortex_command/overnight/runner.py` — the path that yields `STAT Ss`).
- Observability: `cortex overnight status` renderer; `cortex_command/overnight/report.py` morning-report scanner (`scheduled-fire-failed.json`); `cortex_command/overnight/events.py`.
- Skill flow: `skills/overnight/SKILL.md` + `skills/overnight/references/new-session-flow.md` (steps 7.5–7.7 and the `$CORTEX_COMMAND_ROOT` references).
- Planning helpers & CLI wiring: `cortex_command/overnight/{backlog,plan,state}.py`; `docs/overnight-operations.md`.