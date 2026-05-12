# Resume Flow (`/overnight resume`) — Detailed Steps

## Step 1: Load Existing State

Scan `$CORTEX_COMMAND_ROOT/lifecycle/sessions/*/overnight-state.json` (sorted by modification time, most recent first) and load the first file whose `phase` is not `complete` using `load_state(state_path=<path>)` from `cortex_command.overnight.state`. You should pass the explicit `state_path` argument — the default path points to a different location. This mirrors the runner's own auto-discovery logic and works correctly whether state was written by a sandboxed or non-sandboxed session.

- **If no matching file is found** (glob returns no results, or all found files have `phase: complete`): Report "No active overnight session found. Use `/overnight` to start a new session." Stop.
- **Error**: If a candidate file exists but cannot be parsed (corrupted JSON), skip it and try the next candidate. If all candidates fail to parse, report: "All overnight state files under $CORTEX_COMMAND_ROOT/lifecycle/sessions/ are corrupted. Inspect and repair manually, or start a new session with `/overnight`." → stop.

## Step 2: Report Session State

Present the current session state to the user:

- **Session ID** and when it started
- **Phase**: planning, executing, complete, or paused. When phase is `paused` and `state.paused_reason` is non-None, include:
  ```
  Session paused — reason: {paused_reason}
  ```
  With contextual guidance based on the value:
  - `budget_exhausted` → "Resume when Anthropic budget resets, then run: `overnight-start ...`"
  - `stall_timeout` → "Session stalled; investigate logs before resuming."
  - `signal` → "Session received a kill signal; resume when ready."
  - Unknown value → display the reason string with no additional guidance.
- **Per-feature statuses**: List each feature with its status (merged, running, paused, pending, failed, deferred)
- **Rounds completed**: Number of round summaries in `round_history`
- **Current round**: The active round number

## Step 3: Check for Deferred Questions

Read deferred questions from the `deferred/` directory using `read_deferrals()` from `cortex_command.overnight.deferral`.

If there are deferred questions, present them using `summarize_deferrals()` from `cortex_command.overnight.deferral`. For blocking questions, highlight that the affected features are paused and waiting for a human decision.

**Error**: If `read_deferrals()` fails (e.g., directory permission error), report: "Could not read deferred questions from deferred/: {error}." Continue — proceed as if there are no deferred questions.

## Step 4: Determine Next Action

Based on the session phase, ask the user what to do:

| Phase | Options |
|-------|---------|
| `executing` | Resume execution (print runner command), or view current progress |
| `paused` | Address the cause of the pause (deferred questions, failures), then resume execution |
| `complete` | View the morning report at `cortex/lifecycle/morning-report.md` |
| `planning` | This should not normally occur (planning happens interactively). Offer to restart the session. |

## Step 5: Act on User Choice

- **Resume execution**: Execute via Bash tool with `dangerouslyDisableSandbox: true` (substitute actual `{session_id}` from the loaded state):

  ```
  overnight-start $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h
  ```

  The runner resumes from where it left off, skipping already-merged features. After the Bash tool returns, report: "Overnight session resumed. Attach with `tmux attach -t overnight-runner` to monitor progress."

- **View morning report**: Direct the user to read `cortex/lifecycle/morning-report.md` for a summary of what was accomplished, what failed, and any deferred questions.

- **Address deferred questions**: Present each blocking question from `deferred/` and collect the user's answers. After answering, the user can resume execution.
