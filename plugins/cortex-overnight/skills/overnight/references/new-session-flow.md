# New Session Flow (`/overnight`) — Detailed Steps

> **Python module note**: After `uv tool install git+<url>@<tag>`, the `cortex` console script is available globally and the `cortex_command.*` package is importable inside the tool venv — no `PYTHONPATH` manipulation required. Invoke planning helpers either through the CLI entry point (`cortex <subcommand>`) or, where subcommands are not yet wired, via `python3 -m cortex_command.<module>`.
>
> **Dev-clone install path (R16)**: When working from a local clone, use `uv pip install -e . --no-deps` against the active `.venv` to pick up edits (including F3 console-script promotions) without reinstalling the full tool. Do not use `uv tool install --reinstall` during active sessions: the in-flight install guard blocks reinstall while any partial session is running to prevent mid-session environment changes. The existing carve-outs — pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, and cancel-force — are unchanged; no new carve-out is added by this workflow.

## Step 1: Check for Existing Session

Call `load_state()` from `cortex_command.overnight.state` (no arguments — uses its default path at `$CORTEX_COMMAND_ROOT/cortex/lifecycle/overnight-state.json`).

- **If found with phase other than `complete`**: Warn the user that an active overnight session exists. Report the phase and feature count. Ask whether to resume the existing session (switch to the Resume Flow) or abandon it and start fresh.
- **If found with `complete` phase**: Treat as no active session. Proceed as new.
- **If not found (FileNotFoundError)**: Proceed as new.

## Step 2: Pre-selection Index Regeneration

Regenerate the backlog index so that feature selection in Step 3 operates on up-to-date metadata.

1. Run `cortex-generate-backlog-index` from the project root. If the command exits with a non-zero status, report: "Backlog index regeneration failed (exit {code}). Fix the issue and retry `/overnight`." → halt.
2. Stage the regenerated index files: `git add cortex/backlog/index.json cortex/backlog/index.md`.
3. If there are staged changes (i.e., the index actually changed), commit with message "Regenerate backlog index". If the commit fails, report: "Failed to commit regenerated backlog index: {error}." → halt.
4. If there are no staged changes, skip the commit — the index is already current.

## Step 3: Select Eligible Features

Run `select_overnight_batch()` from `cortex_command.overnight.backlog` on the project's backlog directory.

This function composes the full selection pipeline: parse backlog items, filter for readiness (status, blockers, research + spec + plan artifacts), score by weighted algorithm (dependency structure, priority, tag cohesion, type routing), and group into batches.

A feature is eligible only if the following exist on disk:
- `cortex/lifecycle/{slug}/research.md` exists on disk (slug = `item.lifecycle_slug` if set, else `slugify(item.title)`)
- `cortex/lifecycle/{slug}/spec.md` exists on disk (produced by `/refine` or `/lifecycle`)
- `type:` is not `epic` — epic items are non-implementable and excluded at step 4 (after blocked-by, before artifact checks); a blocked epic reports its blocking dependency, not the epic exclusion

If `cortex/lifecycle/{slug}/plan.md` is missing, it is generated automatically during the
overnight session before the feature executes — no pre-run `/lifecycle plan` needed.

**If no eligible items** (selection result has zero batches): Report "Nothing ready for overnight execution." List the ineligible items with their reasons from the selection result. Suggest running `/lifecycle` through the plan phase on the highest-priority ineligible items to produce the required lifecycle artifacts. Stop.

**Error**: If `select_overnight_batch()` raises an exception (e.g., malformed backlog frontmatter), report: "Failed to parse backlog: {error}. Check backlog file frontmatter for syntax errors." → stop.

## Step 4: Present Selection Summary

Present the selection result summary to the user. This includes:

- Number of eligible items and how many batches they form
- Per-batch breakdown: batch number, batch context (knowledge domain), and feature titles
- Ineligible items with reasons (missing research, missing spec, blocked, etc.)

The summary string is available as `selection.summary` on the `SelectionResult` object.

## Step 5: Render Session Plan

Call `render_session_plan()` from `cortex_command.overnight.plan` with the selection result and default configuration:

```python
render_session_plan(
    selection=selection,
    time_limit_hours=6,
)
```

This produces a formatted markdown session plan with:
- Selected features table (round, feature, backlog number, type, priority, pre-work status)
- Execution strategy (rounds, tier-based concurrency cap, feature count)
- Not-ready items with reasons
- Risk assessment (file overlap, dependency concerns)
- Stop conditions (zero progress in a round, time limit)

**Error**: If `render_session_plan()` raises an exception, report: "Failed to render session plan: {error}." → stop.

## Step 6: Unified Plan + Spec Review

Collect specs for all selected features, display the session plan with specs inline, and get a single approval covering both.

**Collect specs**: For each selected feature (in round-then-priority order), attempt to read `cortex/lifecycle/{slug}/spec.md`.

- **If a spec file is missing or unreadable**: Report "Cannot read spec for {feature_title}: {error}." Offer two choices: (a) remove the feature from the selection and continue, or (b) abort planning so the user can fix the spec. If the user chooses remove, update the selection and skip that feature in the display below.

**Display plan + specs**: Present the rendered session plan from Step 5, then immediately display each feature's spec content inline:

```
{rendered session plan}

─────────────────────────────────────────
Spec [1/{total}]: {feature_title}  (cortex/lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}

─────────────────────────────────────────
Spec [2/{total}]: {feature_title}  (cortex/lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}
```

**Approval prompt**: After all specs are shown, present a single approval. There is no recommended upper limit on session size — the runner scales well, so remove features only for substantive reasons (out of scope, not actually ready), not to keep the session small.

```
Approve this plan and specs?

  [A] Approve — proceed to launch
  [R] Remove a feature — specify which to exclude, then re-display
  [T] Adjust time limit — change from the default 6h
  [Q] Abort — stop planning
```

- **Approve (A)**: Proceed to Step 7.
- **Remove (R)**: Ask which feature to remove. Drop it from the selection, re-render the plan (repeat Step 5), reload specs for remaining features, and re-display everything before prompting again.
- **Adjust time limit (T)**: Ask for the new time limit. Re-render the plan with the new limit and re-display before prompting again.
- **Abort (Q)**: Stop immediately. Report "Planning aborted." Do not write any artifacts. Stop.

**Error**: If `cortex/lifecycle/{slug}/spec.md` exists but cannot be decoded (e.g., binary content, encoding error), treat it the same as a missing file and offer the remove-or-abort choice.

## Step 7: Launch

On user approval, execute these steps in order:

0. **Validate target repos**: Call `validate_target_repos(selection)` from `cortex_command.overnight.plan`. If the returned list is non-empty, report:
   ```
   Cannot start overnight session: the following repo: paths are not valid git repositories:
     - {path1}
     - {path2}
   Run `git clone <url> <path>` or correct the repo: field in the affected backlog items.
   ```
   Do not write any artifacts, create any worktrees, or mark the session `executing`. → stop.

1. **Pre-flight: uncommitted cortex/lifecycle/backlog files**: Run `git status --porcelain -- cortex/lifecycle/ cortex/backlog/` and capture the output.

   - **If output is non-empty** (any untracked files, staged, or modified-but-unstaged files in `cortex/lifecycle/` or `cortex/backlog/`): block launch with:
     ```
     Uncommitted lifecycle files detected. The overnight worktree is created from HEAD, so
     these files will not be visible to the runner. Commit or stash them before launching.

     Uncommitted paths:
       {lines from git status output}
     ```
     Then offer: "Would you like me to run `/commit` now?"

     - **If user accepts**: invoke `/commit`. After it returns, re-run `git status --porcelain -- cortex/lifecycle/ cortex/backlog/`. If the output is now empty, proceed to Launch sub-step 2. If the output is still non-empty, display the block message again with the remaining paths and stop — do not offer `/commit` a second time.
     - **If user declines**: stop with "Commit or stash the files above, then run `/overnight` again." Do not proceed to Launch sub-step 2.

   - **If output is empty**: proceed to Launch sub-step 2 without any message.

   **Error**: If `git status` fails (unexpected git error), report the error and stop. In practice this cannot occur — the git repository check in Input Validation (`.git/` exists) runs before Step 7.

2. **Bootstrap the session**: Call `bootstrap_session(selection, plan_content)` from `cortex_command.overnight.plan` with the approved selection and the rendered plan string from Step 5. Returns `(state, state_dir)` with `overnight-state.json`, `overnight-plan.md`, and `session.json` already written on disk.

   This performs all initialization atomically:
   - Creates a timestamp-based session ID (`overnight-{YYYY-MM-DD}-{HHmm}`) with collision-avoidance
   - Sets all selected features to `pending` status with round assignments matching batch numbers
   - Sets phase to `executing`
   - Creates a git worktree at `$TMPDIR/overnight-worktrees/{session_id}/` with a new `overnight/{session_id}` integration branch; the user's active branch is not changed
   - Writes `overnight-plan.md`, `session.json`, and `overnight-state.json` into the MC lifecycle session directory

   **Error**: If `bootstrap_session()` raises (worktree creation, disk write, or save failure), report the error and stop. Clean up any orphaned worktree: run `git worktree prune` and then `ls $TMPDIR/overnight-worktrees/` to identify and remove any leftover directory (`rm -rf $TMPDIR/overnight-worktrees/<session_id>`). The session ID is inside the directory name — check modification time to find the orphan.

3. **latest-overnight symlink**: Handled by the runner on startup. The skill does not create this symlink — it writes to the repo root which is outside the sandbox's write allowlist in sandboxed projects.

4. **Extract batch spec sections**: Read the worktree path from the initialized state (`state.worktree_path`). Call `extract_batch_specs(state, Path(worktree_path))` from `cortex_command.overnight.plan`, passing the worktree path instead of the repository root so that extracted specs are written into the worktree's `cortex/lifecycle/` directory. If the returned list is non-empty, `cd` to the worktree directory, stage each returned path with `git add` (paths are relative to the worktree, not the repo root), and commit using `/commit` with message `"Extract batch spec sections for overnight session {session_id}"` (substituting the actual session ID). This commits the specs on the integration branch, not on main. If the list is empty, skip the commit — no batch-spec items were selected.

   **Error**: If `git add` or `git commit` fails, report: "Batch spec commit failed: {error}. Proceeding without committing batch spec sections — they may be extracted during runner startup." Continue — the runner can still function without the pre-commit.

5. **Log session start**: Call `log_event()` from `cortex_command.overnight.events` with `event='session_start'`, `round=1`, and `details` including the session ID, feature count, and time limit. Pass `log_path=state_dir / "overnight-events.log"` so the event log lands in the MC lifecycle session directory alongside the other session artifacts. Note: the parameter is `event` (not `event_type`) and event names are lowercase strings (e.g., `'session_start'`, not `'SESSION_START'`).

   **Error**: If `log_event()` fails, report: "Failed to log session start event: {error}." Continue — logging failure is non-fatal.

6. **Launch the dashboard** (if not already running): Check whether the dashboard is live by reading `${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid`. If the file exists and the stored PID is alive (`kill -0 $(cat "${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid")` exits 0), the dashboard is already running — note the URL and skip launch. Otherwise, instruct the user to run `cortex dashboard` (installer-tier) or `just dashboard` (clone-only) in a separate terminal before starting the runner, or explain that they can launch it at any time during the session. Poll `GET http://localhost:8080/health` for a 200 response (up to 5 seconds, 1-second intervals); if successful, note "Dashboard available at http://localhost:8080" in the session start message.

    **Error**: If the dashboard health check times out or the PID file is unreadable, continue without failing — the dashboard is optional. Report: "Dashboard not detected at http://localhost:8080. Run `cortex dashboard` in a separate terminal to enable live progress monitoring."

7. **Execute the runner command**: Ask the user whether to run now or schedule for later using AskUserQuestion:

    ```
    Run now or schedule for later?

      [1] Run now — launch the overnight session immediately
      [2] Schedule for specific time — delay launch until a target time
    ```

    > **Usage context (dormant)**: No programmatic access to Claude Code's subscription usage data (remaining tokens, reset time) currently exists from within an agent context. When such access becomes available (e.g., a `/usage` API, a `usage-cache.json` file, or an environment variable), auto-display it alongside the scheduling prompt to help the user choose a launch time. Until then, no usage information is shown.

    **Run now (option 1)**: Execute via Bash tool with `dangerouslyDisableSandbox: true` (substitute actual `{session_id}` and time limit):

    ```
    overnight-start $CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/{session_id}/overnight-state.json 6h
    ```

    Args are positional — do not use `--flag=value` syntax. `overnight-start` creates a detached tmux session named `overnight-runner` and returns immediately.

    **Schedule for specific time (option 2)**: Prompt the user for a target time. Accept either `HH:MM` (24-hour local time) or `YYYY-MM-DDTHH:MM` (ISO 8601 date + time with `T` separator). Execute via Bash tool with `dangerouslyDisableSandbox: true` (substitute actual `{session_id}` and target time):

    ```
    cortex overnight schedule <target-time> --state $CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/{session_id}/overnight-state.json
    ```

    `cortex overnight schedule` registers a one-shot LaunchAgent (no tmux) that fires the runner at the target time and returns immediately. The Bash tool call MUST set `dangerouslyDisableSandbox: true` so the harness can reach `launchctl`.

8. **Inform the user**: After the Bash tool returns successfully, report the outcome:
    - **Run now**: "Overnight session launched. Attach with `tmux attach -t overnight-runner` to monitor progress."
    - **Scheduled**: Report the scheduled time and tmux session name from the command output. The user can attach before that time to monitor the countdown.

    The runner operates autonomously and tracks progress in the state file and event log. Resume at any time with `/overnight resume`.
