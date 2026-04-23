# Specification: schedule-overnight-runs

## Problem Statement

The overnight runner launches immediately when the user runs `overnight-start`. There is no way to delay launch until a specific time — such as 11:01 PM when the Claude Code subscription usage window resets at 11:00 PM. The user must either stay awake until the target time or launch early and waste budget from the current window. A one-shot scheduling mechanism integrated into the `/overnight` skill lets the user set a target launch time and walk away, maximizing available token budget for the overnight session.

## Requirements

### /overnight Skill Integration

1. **Scheduling prompt at Step 8.7**: After plan approval and session bootstrap, the `/overnight` skill asks the user whether to run now or schedule for later. If "now," the existing `overnight-start` command is presented (unchanged). If "schedule," the skill prompts for a target time and presents an `overnight-schedule` command instead. Acceptance criteria: Interactive/session-dependent — the skill presents a scheduling choice via AskUserQuestion after plan approval and before presenting the runner command.

2. **Usage context (future)**: No programmatic access to Claude Code's subscription usage data (remaining tokens, reset time) currently exists from within an agent context. When such access becomes available (e.g., a `/usage` API, a `usage-cache.json` file, or an environment variable), the scheduling prompt should auto-display it alongside the time prompt. Until then, this requirement is dormant — no implementation work is needed. Acceptance criteria: N/A — dormant until a data source exists.

3. **Time input format**: The skill accepts either `HH:MM` (24-hour local time) or `YYYY-MM-DDTHH:MM` (ISO 8601 date + time with `T` separator, no space). Acceptance criteria: `overnight-schedule 23:01` and `overnight-schedule 2026-04-10T23:01` both parse successfully as the target time.

### bin/overnight-schedule Script

4. **New `bin/overnight-schedule` script**: A standalone bash script that accepts a target time as the first positional argument and forwards remaining arguments to `overnight-start`. Acceptance criteria: `ls -la ~/.local/bin/overnight-schedule` shows a symlink to `bin/overnight-schedule`; invocation with no args prints usage.

5. **Delay computation**: Computes seconds until the target time using BSD `date -j -f`. For `HH:MM` input: today if future, tomorrow if past (with a note: "Target time has passed today — scheduling for tomorrow"). For `YYYY-MM-DDTHH:MM`: exact date. Validates the target is in the future and within 7 days. Acceptance criteria: `overnight-schedule 23:01` at 22:00 produces ~3660s delay; at 23:02 wraps to tomorrow; `overnight-schedule 2026-04-01T23:01` (past date) exits with code 1; `overnight-schedule 2026-04-20T23:01` (>7 days) exits with code 1.

6. **Input validation**: Target time validated with pattern matching before use. `HH:MM` must have hours 00-23 and minutes 00-59. `YYYY-MM-DDTHH:MM` must parse successfully with `date -j -f`. Invalid formats exit with code 1 and print usage. Acceptance criteria: `overnight-schedule 25:99` exits 1 with format error; `overnight-schedule abc` exits 1 with format error.

7. **Mac sleep prevention**: Wraps the sleep period in `caffeinate -i` to prevent the Mac from system-sleeping and suspending the timer. Acceptance criteria: `ps aux | grep caffeinate` shows a caffeinate process while overnight-schedule is waiting.

8. **Confirmation output**: On launch, prints: local target time, UTC equivalent, countdown duration (Xh Ym), tmux session name, attach command, and cancel command. Acceptance criteria: output includes lines matching patterns "Scheduled for HH:MM local (HH:MM UTC)", "Starting in Xh Ym", "Attach: tmux attach -t <session>", and "Cancel: tmux kill-session -t <session>".

9. **tmux session**: The sleep + caffeinate + launch sequence runs inside a detached tmux session. Session naming follows `overnight-start`'s collision-avoidance pattern: try `overnight-scheduled`, then `overnight-scheduled-2`, etc. The session exists only during the wait period — after sleep completes and `overnight-start` is called, the `overnight-scheduled` session exits (this is expected behavior, not an error). Acceptance criteria: during the wait period, `tmux list-sessions | grep overnight-scheduled` shows the session; closing the user's terminal does not kill the waiting process.

10. **Delegation to overnight-start**: After the sleep period completes, execs `overnight-start` with all forwarded arguments (state-path, time-limit, max-rounds, tier). `overnight-start` creates the `overnight-runner` tmux session and exits; the runner continues inside `overnight-runner`. Acceptance criteria: after the delay, `tmux list-sessions | grep overnight-runner` shows the runner session; `runner.sh` is running inside it with correct arguments.

### Observability

11. **`scheduled_start` field in overnight-state.json**: Before sleeping, `overnight-schedule` writes a `scheduled_start` field (ISO 8601 timestamp of the target launch time) into the state file at the provided state path using atomic writes (tempfile + mv). Clears it (sets to `null`) just before calling `overnight-start`, also via atomic write. Acceptance criteria: `jq .scheduled_start <state-path>` shows a valid ISO 8601 timestamp while waiting; shows `null` after launch.

12. **State schema backward compatibility**: The `scheduled_start` field is added as `Optional[str] = None` in the `OvernightState` dataclass, loaded via `raw.get("scheduled_start")`. Existing sessions without the field are unaffected. Acceptance criteria: `python3 -c "from cortex_command.overnight.state import load_state; s = load_state('<old-state-path>'); print(s.scheduled_start)"` prints `None` for pre-existing state files.

### Deployment

13. **Justfile recipe**: A `just overnight-schedule` recipe that mirrors the bin script's interface. Acceptance criteria: `just --list | grep overnight-schedule` shows the recipe.

14. **Deploy and symlink integration**: `just deploy-bin` creates the `~/.local/bin/overnight-schedule` symlink. `just setup-force` includes the corresponding `ln -sf` line. `just check-symlinks` validates the symlink. Acceptance criteria: `just deploy-bin` succeeds; `just check-symlinks` passes with no missing entries for `overnight-schedule`.

## Non-Requirements

- **Recurring scheduling**: One-shot only. No cron, no persistent schedule. Users schedule each run individually.
- **Reboot survivability**: Does not survive a full machine reboot. The user is present when scheduling and the machine stays on.
- **Remote trigger integration**: Does not extend or interact with the `/schedule` skill's remote agent infrastructure.
- **New state machine phases**: No new session phase (like `scheduled`). `scheduled_start` is metadata only; the forward-only phase transition model is unchanged.
- **Automated subscription reset detection**: There is no programmatic API for Claude Code's 5-hour rolling usage window. The tool does not attempt to detect reset times automatically. The user provides their known reset time.
- **Wake-from-sleep**: No `pmset` integration. `caffeinate -i` prevents sleep during the wait; it does not wake the machine.
- **Justfile recipe for `overnight-start`**: The existing `just overnight-start` recipe is not modified.

## Edge Cases

- **Target time already passed today (HH:MM only)**: Schedule for tomorrow. Print: "Target time has passed today — scheduling for tomorrow."
- **Target date in the past (ISO format)**: Exit with code 1: "Scheduled time is in the past."
- **Target more than 7 days out**: Exit with code 1: "Scheduled time is more than 7 days away."
- **Invalid time format**: Exit with code 1 and print usage.
- **No state path provided**: Forward to `overnight-start` without writing `scheduled_start`. Scheduling still works; just no state-file observability.
- **State file doesn't exist at provided path**: Print warning ("State file not found — scheduled_start observability disabled") but proceed with scheduling.
- **State file write failure**: If the atomic write (tempfile + mv) fails, print warning and proceed. Scheduling still works; observability is degraded.
- **Multiple scheduled runs**: tmux session name collision avoidance: `overnight-scheduled`, `overnight-scheduled-2`, etc.
- **User cancels during wait**: `tmux kill-session -t <session>` kills the caffeinate + sleep chain. The `scheduled_start` field in the state file becomes stale but is overwritten when the session is re-planned or re-scheduled.
- **Session ID vs launch time**: Session ID encodes planning time (from `bootstrap_session`), not launch time. A session planned at 10 PM and launched at 11:01 PM has ID `overnight-2026-04-08-2200`. This is cosmetically expected — the session was created at planning time.
- **Stale worktree during sleep**: `bootstrap_session` creates the worktree at planning time. For scheduled runs, it sits idle until launch. If main gets new commits, the runner handles rebase on start. Acceptable for typical overnight gaps.
- **Timezone display**: Confirmation shows both local and UTC times. The script uses system local time for scheduling and converts to UTC for display.

## Changes to Existing Behavior

- [ADDED: `bin/overnight-schedule`] New CLI utility in the `bin/` → `~/.local/bin/` deployment path
- [ADDED: `scheduled_start` field in `overnight-state.json`] New optional metadata field. Existing consumers unaffected (additive JSON field).
- [ADDED: `OvernightState.scheduled_start`] New optional field in the state dataclass with backward-compatible loading.
- [MODIFIED: `skills/overnight/SKILL.md`] Step 8.7 gains a scheduling prompt — asks "run now or schedule?" with optional usage context display (dormant until data source exists), then presents the appropriate command.
- [MODIFIED: `justfile` deploy-bin recipe] Adds `overnight-schedule` to deployed binaries list
- [MODIFIED: `justfile` setup-force recipe] Adds `ln -sf` for `overnight-schedule`
- [MODIFIED: `justfile` check-symlinks recipe] Adds validation for `overnight-schedule` symlink
- [ADDED: `justfile` overnight-schedule recipe] New recipe mirroring the bin script interface

## Technical Constraints

- **Positional args only**: First arg is target time (`HH:MM` or `YYYY-MM-DDTHH:MM` — the `T` separator avoids shell tokenization issues with spaces). Remaining args forward to `overnight-start`. No `--flag=value` syntax.
- **BSD date on macOS**: Time parsing uses `date -j -f` (not GNU `date -d`). BSD `sleep` takes integer seconds only.
- **Input validation**: Target time validated with pattern matching before any shell interpolation.
- **Atomic state file writes required**: All writes to `overnight-state.json` must use the tempfile + mv pattern (write to a temp file, then `mv` to the target path). This matches the pipeline's architectural constraint. Do not use `jq '...' file > file` (truncates before reading) or any in-place write pattern.
- **deploy-bin / setup-force / check-symlinks symmetry**: All three recipe lists must be updated together.
- **Skill modification scope**: Only Step 8.7 changes — the scheduling prompt is additive after plan approval. No changes to planning, approval, or bootstrap logic.

## Open Decisions

None — all decisions resolved during the interview.
