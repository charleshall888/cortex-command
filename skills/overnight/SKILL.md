---
name: overnight
description: Plan and launch autonomous overnight development sessions. Selects eligible features from the backlog, presents a session plan for user approval, and hands off to the bash runner for unattended execution. Use when user says "/overnight", "/overnight resume", "/overnight status", "start overnight session", "overnight plan", "launch overnight", "overnight status", or wants to run multiple features autonomously overnight.
disable-model-invocation: true
inputs:
  - "time-limit: string (optional) — Maximum wall-clock duration for the overnight session (e.g. '6h'). Passed as --time-limit to the runner."
outputs:
  - "lifecycle/sessions/{SESSION_ID}/overnight-plan.md — selected session plan with feature list"
  - "lifecycle/sessions/{SESSION_ID}/overnight-state.json — execution state for the runner"
  - "lifecycle/sessions/{SESSION_ID}/session.json — session manifest (type, id, started, features)"
  - "lifecycle/sessions/{SESSION_ID}/overnight-events.log — session events log"
  - "lifecycle/sessions/{SESSION_ID}/morning-report.md — session morning report"
  - "lifecycle/sessions/latest-overnight — symlink to the current session directory"
preconditions:
  - "lifecycle/{slug}/spec.md exists for each candidate feature"
  - "backlog/NNN-slug.md files exist with status: refined"
  - "Run from project root"
---

# Overnight Session Planning

Interactive entry point for overnight autonomous orchestration. Guides the user through selecting features from the backlog, reviewing a session plan, and launching overnight execution. The skill itself handles planning and approval; execution is delegated to the bash runner.

## Invocation

- `/overnight` -- start a new overnight session (select features, build plan, launch)
- `/overnight resume` -- resume an interrupted overnight session or view results
- `/overnight status` -- check the status of a running or recent overnight session

## Input Validation

Validate inputs before entering any flow:

| Input | Type | Valid Values | Error Response |
|-------|------|-------------|----------------|
| `time-limit` | string | `\d+(\.\d+)?h` (e.g., `6h`, `8h`, `1.5h`) | "Invalid time-limit format '{value}'. Expected hours, e.g. '6h'." → stop |

**Precondition checks** (fail fast before any backlog reads):

- **Git repository**: `.git/` must exist in the current directory. If missing: "Not a git repository root. Run `/overnight` from the repository root." → stop.
- **Backlog directory**: `backlog/` must exist. If missing: "No backlog directory found. Run from the project root." → stop.
- **Command variant**: Only `overnight`, `overnight resume`, and `overnight status` are valid. Unknown variants (e.g., `/overnight foobar`) should report: "Unknown subcommand '{variant}'. Use `/overnight`, `/overnight resume`, or `/overnight status`." → stop.

## New Session Flow (`/overnight`)

> **Python binary note**: The `claude.overnight.*` modules are not installed globally — they live in the the cortex-command source tree. When invoking Python in any planning step, use `PYTHONPATH=$CORTEX_COMMAND_ROOT $CORTEX_COMMAND_ROOT/.venv/bin/python3` (or `source $CORTEX_COMMAND_ROOT/.venv/bin/activate && export PYTHONPATH=$CORTEX_COMMAND_ROOT` in the same shell) to ensure the modules are importable regardless of the current working directory.

### Step 1: Check for Existing Session

Call `load_state()` from `claude.overnight.state` (no arguments — uses its default path at `$CORTEX_COMMAND_ROOT/lifecycle/overnight-state.json`).

- **If found with phase other than `complete`**: Warn the user that an active overnight session exists. Report the phase and feature count. Ask whether to resume the existing session (switch to the Resume Flow) or abandon it and start fresh.
- **If found with `complete` phase**: Treat as no active session. Proceed as new.
- **If not found (FileNotFoundError)**: Proceed as new.

### Step 2: Pre-selection Index Regeneration

Regenerate the backlog index so that feature selection in Step 3 operates on up-to-date metadata.

1. Run `generate-backlog-index` from the project root. If the command exits with a non-zero status, report: "Backlog index regeneration failed (exit {code}). Fix the issue and retry `/overnight`." → halt.
2. Stage the regenerated index files: `git add backlog/index.json backlog/index.md`.
3. If there are staged changes (i.e., the index actually changed), commit with message "Regenerate backlog index". If the commit fails, report: "Failed to commit regenerated backlog index: {error}." → halt.
4. If there are no staged changes, skip the commit — the index is already current.

### Step 3: Select Eligible Features

Run `select_overnight_batch()` from `claude.overnight.backlog` on the project's backlog directory.

This function composes the full selection pipeline: parse backlog items, filter for readiness (status, blockers, research + spec + plan artifacts), score by weighted algorithm (dependency structure, priority, tag cohesion, type routing), and group into batches.

A feature is eligible only if the following exist on disk:
- `lifecycle/{slug}/research.md` exists on disk (slug = `item.lifecycle_slug` if set, else `slugify(item.title)`)
- `lifecycle/{slug}/spec.md` exists on disk (produced by `/refine` or `/lifecycle`)
- `type:` is not `epic` — epic items are non-implementable and excluded at step 4 (after blocked-by, before artifact checks); a blocked epic reports its blocking dependency, not the epic exclusion

If `lifecycle/{slug}/plan.md` is missing, it is generated automatically during the
overnight session before the feature executes — no pre-run `/lifecycle plan` needed.

**If no eligible items** (selection result has zero batches): Report "Nothing ready for overnight execution." List the ineligible items with their reasons from the selection result. Suggest running `/lifecycle` through the plan phase on the highest-priority ineligible items to produce the required lifecycle artifacts. Stop.

**Error**: If `select_overnight_batch()` raises an exception (e.g., malformed backlog frontmatter), report: "Failed to parse backlog: {error}. Check backlog file frontmatter for syntax errors." → stop.

### Step 4: Present Selection Summary

Present the selection result summary to the user. This includes:

- Number of eligible items and how many batches they form
- Per-batch breakdown: batch number, batch context (knowledge domain), and feature titles
- Ineligible items with reasons (missing research, missing spec, blocked, etc.)

The summary string is available as `selection.summary` on the `SelectionResult` object.

### Step 5: Render Session Plan

Call `render_session_plan()` from `claude.overnight.plan` with the selection result and default configuration:

```python
render_session_plan(
    selection=selection,
    time_limit_hours=6,
)
```

This produces a formatted markdown session plan with:
- Selected features table (round, feature, backlog number, type, priority, pre-work status)
- Execution strategy (rounds, tier-based adaptive throttle, feature count)
- Not-ready items with reasons
- Risk assessment (file overlap, dependency concerns)
- Stop conditions (zero progress in a round, time limit)

**Error**: If `render_session_plan()` raises an exception, report: "Failed to render session plan: {error}." → stop.

### Step 6: Unified Plan + Spec Review

Collect specs for all selected features, display the session plan with specs inline, and get a single approval covering both.

**Collect specs**: For each selected feature (in round-then-priority order), attempt to read `lifecycle/{slug}/spec.md`.

- **If a spec file is missing or unreadable**: Report "Cannot read spec for {feature_title}: {error}." Offer two choices: (a) remove the feature from the selection and continue, or (b) abort planning so the user can fix the spec. If the user chooses remove, update the selection and skip that feature in the display below.

**Display plan + specs**: Present the rendered session plan from Step 5, then immediately display each feature's spec content inline:

```
{rendered session plan}

─────────────────────────────────────────
Spec [1/{total}]: {feature_title}  (lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}

─────────────────────────────────────────
Spec [2/{total}]: {feature_title}  (lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}
```

**Approval prompt**: After all specs are shown, present a single approval:

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

**Error**: If `lifecycle/{slug}/spec.md` exists but cannot be decoded (e.g., binary content, encoding error), treat it the same as a missing file and offer the remove-or-abort choice.

### Step 8: Launch

On user approval, execute these steps in order:

0. **Validate target repos**: Call `validate_target_repos(selection)` from `claude.overnight.plan`. If the returned list is non-empty, report:
   ```
   Cannot start overnight session: the following repo: paths are not valid git repositories:
     - {path1}
     - {path2}
   Run `git clone <url> <path>` or correct the repo: field in the affected backlog items.
   ```
   Do not write any artifacts, create any worktrees, or mark the session `executing`. → stop.

1. **Pre-flight: uncommitted lifecycle/backlog files**: Run `git status --porcelain -- lifecycle/ backlog/` and capture the output.

   - **If output is non-empty** (any untracked files, staged, or modified-but-unstaged files in `lifecycle/` or `backlog/`): block launch with:
     ```
     Uncommitted lifecycle files detected. The overnight worktree is created from HEAD, so
     these files will not be visible to the runner. Commit or stash them before launching.

     Uncommitted paths:
       {lines from git status output}
     ```
     Then offer: "Would you like me to run `/commit` now?"

     - **If user accepts**: invoke `/commit`. After it returns, re-run `git status --porcelain -- lifecycle/ backlog/`. If the output is now empty, proceed to Launch sub-step 2. If the output is still non-empty, display the block message again with the remaining paths and stop — do not offer `/commit` a second time.
     - **If user declines**: stop with "Commit or stash the files above, then run `/overnight` again." Do not proceed to Launch sub-step 2.

   - **If output is empty**: proceed to Launch sub-step 2 without any message.

   **Error**: If `git status` fails (unexpected git error), report the error and stop. In practice this cannot occur — the git repository check in Input Validation (`.git/` exists) runs before Step 8.

2. **Bootstrap the session**: Call `bootstrap_session(selection, plan_content)` from `claude.overnight.plan` with the approved selection and the rendered plan string from Step 5. Returns `(state, state_dir)` with `overnight-state.json`, `overnight-plan.md`, and `session.json` already written on disk.

   This performs all initialization atomically:
   - Creates a timestamp-based session ID (`overnight-{YYYY-MM-DD}-{HHmm}`) with collision-avoidance
   - Sets all selected features to `pending` status with round assignments matching batch numbers
   - Sets phase to `executing`
   - Creates a git worktree at `$TMPDIR/overnight-worktrees/{session_id}/` with a new `overnight/{session_id}` integration branch; the user's active branch is not changed
   - Writes `overnight-plan.md`, `session.json`, and `overnight-state.json` into the MC lifecycle session directory

   **Error**: If `bootstrap_session()` raises (worktree creation, disk write, or save failure), report the error and stop. Clean up any orphaned worktree: run `git worktree prune` and then `ls $TMPDIR/overnight-worktrees/` to identify and remove any leftover directory (`rm -rf $TMPDIR/overnight-worktrees/<session_id>`). The session ID is inside the directory name — check modification time to find the orphan.

3. **latest-overnight symlink**: Handled by the runner on startup (line 179 of `runner.sh`). The skill does not create this symlink — it writes to the repo root which is outside the sandbox's write allowlist in sandboxed projects.

4. **Extract batch spec sections**: Read the worktree path from the initialized state (`state.worktree_path`). Call `extract_batch_specs(state, Path(worktree_path))` from `claude.overnight.plan`, passing the worktree path instead of the repository root so that extracted specs are written into the worktree's `lifecycle/` directory. If the returned list is non-empty, `cd` to the worktree directory, stage each returned path with `git add` (paths are relative to the worktree, not the repo root), and commit using `/commit` with message `"Extract batch spec sections for overnight session {session_id}"` (substituting the actual session ID). This commits the specs on the integration branch, not on main. If the list is empty, skip the commit — no batch-spec items were selected.

   **Error**: If `git add` or `git commit` fails, report: "Batch spec commit failed: {error}. Proceeding without committing batch spec sections — they may be extracted during runner startup." Continue — the runner can still function without the pre-commit.

5. **Log session start**: Call `log_event()` from `claude.overnight.events` with `event='session_start'`, `round=1`, and `details` including the session ID, feature count, and time limit. Pass `log_path=state_dir / "overnight-events.log"` so the event log lands in the MC lifecycle session directory alongside the other session artifacts. Note: the parameter is `event` (not `event_type`) and event names are lowercase strings (e.g., `'session_start'`, not `'SESSION_START'`).

   **Error**: If `log_event()` fails, report: "Failed to log session start event: {error}." Continue — logging failure is non-fatal.

6. **Launch the dashboard** (if not already running): Check whether the dashboard is live by reading `claude/dashboard/.pid`. If the file exists and the stored PID is alive (`kill -0 $(cat claude/dashboard/.pid)` exits 0), the dashboard is already running — note the URL and skip launch. Otherwise, instruct the user to run `just dashboard` in a separate terminal before starting the runner, or explain that they can launch it at any time during the session. Poll `GET http://localhost:8080/health` for a 200 response (up to 5 seconds, 1-second intervals); if successful, note "Dashboard available at http://localhost:8080" in the session start message.

    **Error**: If the dashboard health check times out or the `.pid` file is unreadable, continue without failing — the dashboard is optional. Report: "Dashboard not detected at http://localhost:8080. Run `just dashboard` in a separate terminal to enable live progress monitoring."

7. **Execute the runner command**: Ask the user whether to run now or schedule for later using AskUserQuestion:

    ```
    Run now or schedule for later?

      [1] Run now — launch the overnight session immediately
      [2] Schedule for specific time — delay launch until a target time
    ```

    > **Usage context (dormant)**: No programmatic access to Claude Code's subscription usage data (remaining tokens, reset time) currently exists from within an agent context. When such access becomes available (e.g., a `/usage` API, a `usage-cache.json` file, or an environment variable), auto-display it alongside the scheduling prompt to help the user choose a launch time. Until then, no usage information is shown.

    **Run now (option 1)**: Execute via Bash tool (substitute actual `{session_id}` and time limit):

    ```
    overnight-start $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h
    ```

    Args are positional — do not use `--flag=value` syntax. `overnight-start` creates a detached tmux session named `overnight-runner` and returns immediately.

    **Schedule for specific time (option 2)**: Prompt the user for a target time. Accept either `HH:MM` (24-hour local time) or `YYYY-MM-DDTHH:MM` (ISO 8601 date + time with `T` separator). Execute via Bash tool (substitute actual `{session_id}`, target time, and time limit):

    ```
    overnight-schedule <target-time> $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h
    ```

    `overnight-schedule` creates a waiting tmux session that launches the runner at the target time and returns immediately.

8. **Inform the user**: After the Bash tool returns successfully, report the outcome:
    - **Run now**: "Overnight session launched. Attach with `tmux attach -t overnight-runner` to monitor progress."
    - **Scheduled**: Report the scheduled time and tmux session name from the command output. The user can attach before that time to monitor the countdown.

    The runner operates autonomously and tracks progress in the state file and event log. Resume at any time with `/overnight resume`.

## Resume Flow (`/overnight resume`)

### Step 1: Load Existing State

Scan `$CORTEX_COMMAND_ROOT/lifecycle/sessions/*/overnight-state.json` (sorted by modification time, most recent first) and load the first file whose `phase` is not `complete` using `load_state(state_path=<path>)` from `claude.overnight.state`. You should pass the explicit `state_path` argument — the default path points to a different location. This mirrors the runner's own auto-discovery logic and works correctly whether state was written by a sandboxed or non-sandboxed session.

- **If no matching file is found** (glob returns no results, or all found files have `phase: complete`): Report "No active overnight session found. Use `/overnight` to start a new session." Stop.
- **Error**: If a candidate file exists but cannot be parsed (corrupted JSON), skip it and try the next candidate. If all candidates fail to parse, report: "All overnight state files under $CORTEX_COMMAND_ROOT/lifecycle/sessions/ are corrupted. Inspect and repair manually, or start a new session with `/overnight`." → stop.

### Step 2: Report Session State

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

### Step 3: Check for Deferred Questions

Read deferred questions from the `deferred/` directory using `read_deferrals()` from `claude.overnight.deferral`.

If there are deferred questions, present them using `summarize_deferrals()` from `claude.overnight.deferral`. For blocking questions, highlight that the affected features are paused and waiting for a human decision.

**Error**: If `read_deferrals()` fails (e.g., directory permission error), report: "Could not read deferred questions from deferred/: {error}." Continue — proceed as if there are no deferred questions.

### Step 4: Determine Next Action

Based on the session phase, ask the user what to do:

| Phase | Options |
|-------|---------|
| `executing` | Resume execution (print runner command), or view current progress |
| `paused` | Address the cause of the pause (deferred questions, failures), then resume execution |
| `complete` | View the morning report at `lifecycle/morning-report.md` |
| `planning` | This should not normally occur (planning happens interactively). Offer to restart the session. |

### Step 5: Act on User Choice

- **Resume execution**: Execute via Bash tool (substitute actual `{session_id}` from the loaded state):

  ```
  overnight-start $CORTEX_COMMAND_ROOT/lifecycle/sessions/{session_id}/overnight-state.json 6h
  ```

  The runner resumes from where it left off, skipping already-merged features. After the Bash tool returns, report: "Overnight session resumed. Attach with `tmux attach -t overnight-runner` to monitor progress."

- **View morning report**: Direct the user to read `lifecycle/morning-report.md` for a summary of what was accomplished, what failed, and any deferred questions.

- **Address deferred questions**: Present each blocking question from `deferred/` and collect the user's answers. After answering, the user can resume execution.

## Status Flow (`/overnight status`)

Run `overnight-status` (the deployed script) and present its output to the user. If the command is not found, instruct the user to run `just deploy-bin` first.

## Success Criteria

A successful `/overnight` invocation satisfies all of the following:

1. **Session plan written**: `lifecycle/sessions/{session_id}/overnight-plan.md` exists and contains the approved feature list with round assignments.
2. **State initialized**: `lifecycle/sessions/{session_id}/overnight-state.json` exists with `phase: executing` and all selected features in `pending` status.
3. **Session manifest written**: `lifecycle/sessions/{session_id}/session.json` exists with correct `session_id`, `type: overnight`, and feature slugs.
4. **Integration branch created**: `git branch overnight/{session_id}` exists in the repository.
5. **Symlink deferred to runner**: The `latest-overnight` symlink is updated by the runner on startup, not by the skill.
6. **Runner command executed**: Either `overnight-start` (run now) or `overnight-schedule` (scheduled) was executed via Bash tool with an absolute state path using `$CORTEX_COMMAND_ROOT` and the correct time limit.
7. **Session start event logged**: `overnight-events.log` has a `SESSION_START` entry.

A successful `/overnight resume` satisfies:

1. **Session state reported**: Current phase, per-feature statuses, and completed rounds are shown to the user.
2. **Deferred questions surfaced**: Any blocking deferred questions are presented before offering resume options.
3. **Correct action offered**: Runner command (executing/paused), morning report link (complete), or restart option (planning) is presented based on phase.

## Output Format Examples

### overnight-plan.md

```markdown
# Overnight Session Plan

**Session ID**: overnight-2025-11-14-2230
**Generated**: 2025-11-14 22:30:15
**Throttle**: tier-based adaptive
**Time Limit**: 6h

## Selected Features

| Round | Feature | Backlog | Type | Priority | Pre-work |
|-------|---------|---------|------|----------|----------|
| 1 | Add user authentication | #042 | feature | high | plan needed |
| 1 | Fix pagination bug | #051 | bug | high | plan ready |
| 2 | Add export to CSV | #038 | feature | medium | plan ready |

## Execution Strategy

- **Rounds**: 2
- **Throttle**: tier-based adaptive (round size determined by conflict tiers)
- **Features**: 3 (2 in Round 1, 1 in Round 2)

## Not Ready

| Feature | Reason |
|---------|--------|
| Add dark mode | Missing spec (lifecycle/add-dark-mode/spec.md) |

## Risk Assessment

- No file overlap detected between Round 1 features
- Round 2 depends on Round 1 completing successfully

## Stop Conditions

- Zero progress in a round (all features fail or defer)
- Time limit reached (6h)
```

### session.json

```json
{
  "session_id": "overnight-2025-11-14-2230",
  "type": "overnight",
  "started": "2025-11-14T22:30:15Z",
  "features": [
    "add-user-authentication",
    "fix-pagination-bug",
    "add-export-to-csv"
  ]
}
```

## Overnight vs Pipeline vs Lifecycle

The three orchestration skills are complementary:

- **Lifecycle** (`/lifecycle`): Interactive single-feature development. User present throughout all phases.
- **Pipeline** (`/pipeline`): Batch multi-feature orchestration with an interactive front-end (research, spec, plan) and an execution back-end. User participates in planning, then execution runs autonomously.
- **Overnight** (`/overnight`): Fully autonomous overnight execution of features that already have research and spec artifacts. No interactive research or spec phases -- features must be ready (have completed discovery) before selection. The skill handles plan approval, then hands off entirely to the bash runner.

The key difference: pipeline creates research and specs interactively during the session; overnight requires them to already exist (produced by `/discovery` or `/lifecycle` earlier).

## Constraints

- **Do not contain implementation code.** This skill is a protocol that the agent follows. It references functions by their module paths (`claude.overnight.backlog`, `claude.overnight.plan`, `claude.overnight.state`, `claude.overnight.events`, `claude.overnight.deferral`).
- **One overnight session at a time.** If a session is active (non-complete state file), the user must resume or abandon it before starting a new one.
- **Features must have `lifecycle/{slug}/research.md` and `lifecycle/{slug}/spec.md` on disk, and must not be `type: epic` (checked after blocked-by, before artifact checks).** The readiness gate in `select_overnight_batch()` enforces this. Features without all required artifacts are reported as ineligible with a reason. `plan.md` is generated during the session if missing — a plan generation sub-agent runs before dispatch and defers the feature (with a captured reason) if it cannot produce a valid plan.
- **The skill does not execute features.** It creates the plan and state, then hands off to the bash runner. The runner and batch runner handle actual execution.
- **Overnight features do not merge directly to main.** They merge to the session's integration branch (`overnight/{session_id}`). The bash runner opens a single PR from the integration branch to main at session end, containing all overnight changes for review.
- **Session plan is immutable after approval.** Once written to the session directory (`lifecycle/sessions/{session_id}/overnight-plan.md`), the plan does not change. Runtime state lives in `lifecycle/sessions/{session_id}/overnight-state.json`.
- **Parallel agent dispatch uses `Agent isolation: "worktree"`.** When launching features in parallel, always use the `Agent` tool with `isolation: "worktree"`. Do not call `git worktree add` manually — in sandboxed sessions this fails because `.claude/worktrees/` is Seatbelt-restricted, and a failed checkout leaves an orphaned branch requiring `git branch -d <name>` cleanup before retrying.
