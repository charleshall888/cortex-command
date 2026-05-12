# Specification: integrate-autonomous-worktree-option-into-lifecycle-pre-flight

## Problem Statement

Users invoking `/lifecycle implement` currently see three execution paths: single-agent worktree (live-steerable, short features), implement on main (trunk-based), and feature branch (PR-flow). There is no option to submit a feature to the daytime autonomous pipeline (#078), which can handle multi-task features without occupying the user's session. This ticket adds a fourth pre-flight option — "Implement in autonomous worktree" — that invokes the #078 CLI in the background, polls for progress, and surfaces results (merged/deferred/paused/failed) when the subprocess exits. Guards prevent double-dispatch and concurrent overnight+daytime execution. The work involves updating `skills/lifecycle/references/implement.md`, adding a `§1b Daytime Dispatch` alternate path, and adding skill-level tests.

## Requirements

1. **(Must) Four pre-flight options**: `implement.md §1 Branch Selection` presents four options via `AskUserQuestion`: (1) Implement in worktree, (2) Implement in autonomous worktree, (3) Implement on main, (4) Create feature branch.
   Acceptance: `grep -c "autonomous worktree" skills/lifecycle/references/implement.md` ≥ 1 AND `grep -c "AskUserQuestion" skills/lifecycle/references/implement.md` ≥ 1 (existing check, verifies the prompt surface exists).

2. **(Must) Option guidance text**: The pre-flight prompt includes decision guidance distinguishing when to pick each option: small/live-steerable → single-agent worktree; medium/many-task/no-live-steering-needed → autonomous worktree; trunk-based → main; PR-flow → feature branch.
   Acceptance: `grep -i "live.steer\|many.task\|no.live" skills/lifecycle/references/implement.md` ≥ 1 (at least one guidance phrase present in the pre-flight section).

3. **(Must) plan.md prerequisite check**: Before running any daytime guards or launching the subprocess, the skill verifies `lifecycle/{feature}/plan.md` exists. If missing, surface a clear error and do not proceed to guards or subprocess invocation.
   Acceptance: Interactive/session-dependent — selecting "autonomous worktree" when `plan.md` is absent produces an error message containing "plan.md" and does not invoke `daytime_pipeline`.

4. **(Must) Double-dispatch guard**: Before launching the subprocess, the skill checks whether `lifecycle/{feature}/daytime.pid` exists. If the file exists and the recorded PID is alive (`kill -0 $PID 2>/dev/null` succeeds), reject with "Autonomous daytime run already in progress (PID {pid}) — wait for it to complete or check events.log".
   Acceptance: Interactive/session-dependent — if a live `daytime.pid` exists for the feature, selecting "autonomous worktree" prints the rejection message without launching a new subprocess.

5. **(Must) Concurrent overnight guard**: Before launching the subprocess, the skill checks whether overnight is running on this repo:
   - Read `~/.local/share/overnight-sessions/active-session.json`
   - Verify `repo_path` matches current CWD (exact path match)
   - Verify `phase == "executing"`
   - Derive session dir from `state_path`; read `{session_dir}/.runner.lock`; check `kill -0 $runner_pid 2>/dev/null`
   - All four conditions must be true to reject. If the pointer is absent, stale, or repo path doesn't match: proceed normally.
   On rejection: "Overnight runner is active (PID {pid}) — wait for it to complete before launching a daytime run."
   Acceptance: Interactive/session-dependent — if a live overnight runner is detected for this repo, selecting "autonomous worktree" prints the rejection message without launching a subprocess.

6. **(Must) Worktree-branch guard**: If the current branch matches `^worktree/agent-`, the "Implement in autonomous worktree" option must not be available (the pre-flight prompt should not include it, or selecting it must produce an immediate rejection). This prevents daytime dispatch from within a single-agent worktree context.
   Acceptance: `grep -A5 "worktree.*agent\|agent.*worktree" skills/lifecycle/references/implement.md` shows a branch-prefix guard for the daytime option.

7. **(Must) Background subprocess launch**: After all guards pass, launch `python3 -m cortex_command.overnight.daytime_pipeline --feature {slug}` in the background with stdout and stderr redirected to `lifecycle/{feature}/daytime.log`:
   ```
   python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1
   ```
   Launched via Bash `run_in_background=true`. Subprocess writes `lifecycle/{feature}/daytime.pid` at startup.
   Acceptance: `ls lifecycle/{feature}/daytime.log` exits 0 after the option is selected AND a live PID appears in `lifecycle/{feature}/daytime.pid` within 5 seconds of launch (acceptance test expectation — not a runtime wait enforced by the skill).

8. **(Must) `implementation_dispatch` event**: Immediately after launching the background subprocess, append to `lifecycle/{feature}/events.log`:
   ```json
   {"ts": "<ISO 8601>", "event": "implementation_dispatch", "feature": "<name>", "mode": "daytime"}
   ```
   Acceptance: `grep '"mode": "daytime"' lifecycle/{feature}/events.log | grep "implementation_dispatch"` exits 0 after launch.

9. **(Must) Progress polling**: The skill polls the subprocess status until exit. Polling sequence:
   - **Initial wait**: after launch, wait ~10 seconds before the first poll iteration to allow the subprocess to write `lifecycle/{feature}/daytime.pid`. This is a separate Bash call (`sleep 10` is acceptable here since it follows a background launch, not a blocking wait on subprocess completion).
   - **PID acquisition**: at each poll iteration, read the PID file as a separate Bash call (`cat lifecycle/{feature}/daytime.pid 2>/dev/null`). If the file does not exist after the initial wait, treat as crash/startup failure and transition to result surfacing using `daytime.log` content.
   - **Liveness check**: use the PID obtained above in a separate Bash call (`kill -0 $pid 2>/dev/null`; exit 0 = alive, non-0 = dead).
   - **Progress display**: on each live iteration, read the tail of events.log (last ~20 events) as a separate Bash call; surface a brief human-readable summary of new events since last poll.
   - **Cadence**: approximately every 2 minutes between iterations.
   - **Termination bound**: poll for at most 120 iterations (~4 hours). After the bound is reached, surface "Polling timeout — subprocess may still be running (PID {pid}). Check `lifecycle/{feature}/daytime.log` directly for status." and exit the polling loop.
   Polling continues until the subprocess exits (liveness check fails) or the termination bound is reached.
   Acceptance: Interactive/session-dependent — while the subprocess is running, the skill surfaces at least one progress line showing new events before detecting completion.

10. **(Must) Result surfacing**: When the subprocess exits (PID is no longer alive or polling timeout is reached), determine the outcome using this two-step detection:

    **Step 1 — Exit code as primary signal** (unavailable when using `run_in_background=true`; skip to Step 2). Since the Bash background launch does not capture exit code, proceed directly to Step 2.

    **Step 2 — Last stdout line matching** (primary detection for background launches): Read the last non-empty line of `lifecycle/{feature}/daytime.log` that begins with `"Feature "` — this is the terminal output line written by `daytime_pipeline.py` immediately before exit. Apply these checks **in order** (first match wins):
    - If the line contains `"merged successfully"` → **success**: display the message; if a GitHub PR URL appears anywhere in the log, display it.
    - If the line contains `"deferred"` → **deferred**: display the message AND read the most recent file in `lifecycle/{feature}/deferred/*.md` by modification time and display its content so the user can answer the deferral question without leaving the session.
    - If the line contains `"paused"` → **paused**: display the message; instruct user to check `events.log` for details and re-run when ready.
    - Any other content, or no `"Feature "` line found → **failed**: display the last 20 lines of `daytime.log`; instruct user to check `lifecycle/{feature}/daytime.log` for full details.

    This ordered, anchored detection prevents "paused" appearing as a substring in a failure error message from misclassifying the outcome.
    Acceptance: Interactive/session-dependent — each of the four outcome paths produces distinct output matching the pattern described above.

11. **(Must) `dispatch_complete` event**: After result surfacing, append to `lifecycle/{feature}/events.log`:
    ```json
    {"ts": "<ISO 8601>", "event": "dispatch_complete", "feature": "<name>", "mode": "daytime", "outcome": "complete|deferred|paused|failed", "pr_url": "<url>|null"}
    ```
    - `outcome` = determined by the same ordered, anchored detection from Req 10 (last `"Feature "` line in daytime.log, first-match-wins order: merged → `"complete"`; deferred → `"deferred"`; paused → `"paused"`; anything else → `"failed"`)
    - `pr_url` = parsed PR URL from daytime.log if present; JSON literal `null` otherwise
    Acceptance: `grep '"mode": "daytime"' lifecycle/{feature}/events.log | grep "dispatch_complete"` exits 0 after result surfacing.

12. **(Must) Skill-level behavior tests**: Add tests covering the four-option decision tree and guard logic:
    - Guard fires correctly when `daytime.pid` is live (rejects with expected message)
    - Guard fires correctly when overnight is running for this repo (rejects with expected message)
    - Guard does NOT fire on stale `daytime.pid` (dead PID)
    - Guard does NOT fire on overnight session from a different repo
    - Guard does NOT fire when no `active-session.json` exists
    - Polling fallback triggered when `daytime.pid` does not appear within initial wait (startup failure / crash before PID write)
    - Outcome detection uses last `"Feature "` line: "paused" substring in a failure message does not misclassify as paused outcome
    Acceptance: `just test` exits 0 after the tests are added; `grep -r "daytime_preflight\|autonomous_worktree\|daytime.*guard\|daytime.*pid" tests/` shows at least one test file referencing the new behavior.

13. **(Should) Integration test for CLI invocation**: Add a test verifying that the skill correctly invokes `python3 -m cortex_command.overnight.daytime_pipeline --feature {slug}` with the expected command shape (no extra CLI flags beyond `--feature`).
    Acceptance: `just test` exits 0; `grep -r "daytime_pipeline.*feature\|feature.*daytime_pipeline" tests/` shows at least one test.

## Non-Requirements

- Changes to `claude/overnight/daytime_pipeline.py` or `claude/overnight/batch_runner.py` / `orchestrator.py` / `feature_executor.py` / `outcome_router.py` — those are #078 / #075–#077
- Changes to the morning report or overnight session orchestration
- Resume/re-entry for a paused daytime run (daytime V1 always cleans up on exit; no re-entry path)
- Model or budget customization for the daytime pipeline V1 (uses overnight defaults)
- `worktree/daytime-*` prefix introduction — the daytime pipeline uses `pipeline/{feature}` branch naming via `create_worktree()`; this is fixed by #078. The skill references the existing branch naming; no hook update is needed.
- Fix for `cleanup_worktree()` hardcoded `pipeline/{feature}` branch name (doesn't handle `-2` collision suffix) — this is a bug in `claude/pipeline/worktree.py`; fixing it requires modifying pipeline internals and is deferred to a follow-on ticket.
- Interactive merge approval — the daytime pipeline auto-merges on success (same as overnight)
- `.dispatching` mechanism for the daytime path — the existing `.dispatching` (shell noclobber + `$$` PID) is unsuitable because `$$` dies milliseconds after the Bash call. The `daytime.pid` file from #078 is the correct guard signal, though it is best-effort (probabilistic) rather than atomic — see the Concurrent double-dispatch edge case.
- Atomic OS-level locking (flock/fcntl mutex) for double-dispatch prevention — the `daytime.pid` liveness check is sufficient for a single-user machine; flock adds complexity without materially improving the guarantee.

## Edge Cases

- **Stale `daytime.pid` (dead PID from prior crash)**: PID file exists but `kill -0 $pid` fails → skip the guard (treat as no active run) and proceed to launch. The subprocess's own `_recover_stale()` will clean up the stale worktree.
- **Concurrent double-dispatch within startup window**: The Req 4 guard is probabilistic, not atomic. Two sessions both reading an absent `daytime.pid` within the subprocess startup window (~1–5 seconds after launch, before `_write_pid()` runs) will both proceed to launch. On a single-user machine this window is narrow and acceptable. The subprocess's own `_is_alive()` guard in `daytime_pipeline.py` will catch the second invocation at startup and exit with error code 1 before creating a second worktree. Document as a known limitation; no atomic lock is implemented in V1.
- **`active-session.json` absent or malformed**: Treat as no active overnight session; proceed normally.
- **`active-session.json` repo_path mismatch** (different repo's overnight session): Treat as no active overnight session; proceed normally.
- **`active-session.json` shows executing but `.runner.lock` is absent or dead**: Treat as stale/crashed overnight; emit a warning ("overnight state shows executing but no live runner found — may be stale; proceeding") and do not block.
- **plan.md absent**: Fail fast before any guards; surface "plan.md not found — cannot launch autonomous worktree. Run /lifecycle plan first."
- **Subprocess crashes before writing `daytime.pid`**: `daytime.log` will show the startup error; the PID-polling loop will detect no PID file and fall back to polling `daytime.log` for completion indicators.
- **User kills the parent Claude session while daytime subprocess is running**: Subprocess continues in background (it is disowned). PID file and worktree persist until the subprocess exits normally (which it will — the orphan-prevention guard in `daytime_pipeline.py` handles parent-death detection within ~2 seconds).
- **Daytime subprocess times out or runs indefinitely**: No automatic kill from the skill layer (daytime doesn't implement a wall-clock timeout in V1). User must interrupt manually; document as known limitation.
- **Invoked from `worktree/agent-*` branch**: The autonomous worktree option must not be presented or must be immediately rejected if the current branch matches `^worktree/agent-`. Prevents dispatching daytime from within an already-dispatched single-agent context.
- **`lifecycle/{feature}/deferred/` contains multiple files**: Display the most recent file by modification time. If more than one file exists, note the count and show the most recent.

## Changes to Existing Behavior

- **MODIFIED**: `implement.md §1 Branch Selection` — from 3 options (worktree / main / feature-branch) to 4 options (worktree / autonomous-worktree / main / feature-branch). Users invoking `/lifecycle implement` will see the additional option.
- **ADDED**: `implement.md §1b Daytime Dispatch` — new alternate path (analogous to §1a Worktree Dispatch) that runs when user selects "Implement in autonomous worktree". Includes guards, background launch, polling, result surfacing, and event logging.
- **MODIFIED**: `lifecycle/{feature}/events.log` — `implementation_dispatch` and `dispatch_complete` events for the new daytime path include `"mode": "daytime"` to distinguish from the existing worktree path's `"mode": "worktree"`.

## Technical Constraints

- **No synchronous Bash blocking**: The Bash tool has a 10-minute maximum timeout. The subprocess MUST be launched with `run_in_background=true`; result detection uses polling via `kill -0` + file reads.
- **CWD must be repo root**: `daytime_pipeline.py`'s `_check_cwd()` enforces this; the skill already runs from repo root by convention. No `cd` is needed.
- **No compound bash commands**: Each Bash call must be a single command (sandbox rule — `claude/rules/sandbox-behaviors.md`). Pre-flight checks (plan.md existence, PID liveness, overnight guard), subprocess launch, and event logging must be separate Bash tool calls.
- **No `git -C`**: All git calls must be direct from repo root CWD.
- **`active-session.json` path is global**: `~/.local/share/overnight-sessions/active-session.json`. Must filter by `repo_path` field before using as an overnight indicator.
- **`daytime.pid` is per-feature**: `lifecycle/{feature}/daytime.pid`. Not per-session — a new daytime run for a different feature does not affect this guard.
- **stdout redirect path**: `lifecycle/{feature}/daytime.log` — created/overwritten at subprocess launch. If the feature was previously run and a `daytime.log` exists, it is overwritten.
- **`pipeline/{feature}` branch lifecycle**: Created and cleaned by `daytime_pipeline.py`'s internal `create_worktree()` / `cleanup_worktree()`. The skill does not manage branches or worktrees — it only invokes the CLI and reads output files.

## Open Decisions

- **Whether to add `daytime.pid` check to SKILL.md Step 2 (Dispatching Marker Check)** alongside the existing `.dispatching` check: adding it there would catch an active daytime run before showing any pre-flight prompt; keeping it only in §1b catches it only when the user selects the autonomous option. Deferred: requires a judgment call about whether to modify the global SKILL.md dispatch guard or keep the guard isolated to the new §1b path. The §1b-only approach is simpler and is sufficient to prevent double-dispatch.
