# Resume Flow (`/overnight resume`)

## Step 1: Load Existing State

Scan `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/*/overnight-state.json` (sorted by modification time, most recent first) and load the first file whose `phase` is not `complete` via `load_state(state_path=<path>)` from `cortex_command.overnight.state` — pass the explicit `state_path`; the default path points elsewhere.

- **No matching file** (no results, or all `phase: complete`): report "No active overnight session found. Use `/overnight` to start a new session." Stop.
- **Error**: a candidate that fails to parse (corrupted JSON) is skipped in favor of the next candidate. If all fail: "All overnight state files under $CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/ are corrupted. Inspect and repair manually, or start a new session with `/overnight`." → stop.

## Step 2: Report Session State

Present to the user: session ID and start time; phase (planning, executing, complete, paused); per-feature statuses (merged, running, paused, pending, failed, deferred); rounds completed (`round_history` length); current round.

When phase is `paused` and `state.paused_reason` is non-None, include `Session paused — reason: {paused_reason}` with contextual guidance:
- `budget_exhausted` → "Resume when Anthropic budget resets, then run: `cortex overnight start --state <path> --time-limit <seconds>`"
- `stall_timeout` → "Session stalled; investigate logs before resuming."
- `signal` → "Session received a kill signal; resume when ready."
- Unknown value → display the reason string with no additional guidance.

## Step 3: Check for Deferred Questions

Read deferred questions from `deferred/` via `read_deferrals()` from `cortex_command.overnight.deferral`; present any with `summarize_deferrals()`. For blocking questions, highlight that the affected features are paused awaiting a human decision.

**Error**: `read_deferrals()` failure (e.g., permission error) → "Could not read deferred questions from deferred/: {error}." Continue as if there are none.

## Step 4: Determine Next Action

Ask the user what to do, based on phase:

| Phase | Options |
|-------|---------|
| `executing` | Resume execution (print runner command), or view current progress |
| `paused` | Address the cause of the pause (deferred questions, failures), then resume execution |
| `complete` | View the morning report at `cortex/lifecycle/morning-report.md` |
| `planning` | Should not normally occur (planning happens interactively). Offer to restart the session. |

## Step 5: Act on User Choice

- **Resume execution**: run via Bash with `dangerouslyDisableSandbox: true` (substitute the actual `{session_id}` from the loaded state):

  ```
  cortex overnight start --state $CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/{session_id}/overnight-state.json --time-limit 21600
  ```

  The runner resumes where it left off, skipping already-merged features. Report: "Overnight session resumed. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`."

- **View morning report**: direct the user to `cortex/lifecycle/morning-report.md` for what was accomplished, what failed, and any deferred questions.

- **Address deferred questions**: present each blocking question from `deferred/` and collect the user's answers; then resume execution.
