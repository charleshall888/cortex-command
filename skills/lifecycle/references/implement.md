# Implement Phase

Execute the plan by dispatching a fresh implementation sub-task per task. Each sub-task runs with fresh context to prevent stale assumptions.

## Protocol

### 1. Pre-Flight Check

Read `lifecycle/{feature}/plan.md` and identify pending tasks (those with `[ ]`).

**Branch selection**: If the current branch is `main` or `master`, prompt the user via AskUserQuestion with four options:

- **Implement in worktree** (recommended) — dispatch the remainder of the lifecycle (implement → review → complete) to an `Agent(isolation: "worktree")` so the main session stays on `main`. Other parallel Claude sessions in this repo are unaffected. PR-based workflow is preserved via the worktree branch `worktree/agent-{lifecycle-slug}`. **When to pick**: small/live-steerable features where you want to remain available to answer AskUserQuestion prompts and steer the single agent interactively.
- **Implement in autonomous worktree** — dispatch to the daytime pipeline (`python3 -m claude.overnight.daytime_pipeline`) which runs the full implement → review → complete cycle headlessly in the background without requiring live steering. **When to pick**: medium/many-task/no-live-steering-needed features where you want to kick off a longer autonomous run and move on. Proceeds to §1b below.
- **Implement on main** — trunk-based workflow, changes land directly on main. **When to pick**: tiny, trunk-safe changes where a branch would be overhead.
- **Create feature branch** — create `feature/{lifecycle-slug}` for PR-based workflow. **When to pick**: you want a PR-based flow but cannot use a worktree (e.g., tooling that assumes a single checkout). NOTE: this runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Worktree-agent context guard**: Immediately before the `AskUserQuestion` call, check the current branch with `git branch --show-current`. If it matches `^worktree/agent-` (the dispatcher is itself running inside a worktree agent context), exclude the **Implement in autonomous worktree** option from the list presented to the user and note "autonomous worktree unavailable from within a worktree agent context" alongside the prompt. The remaining three options (worktree, main, feature branch) are still presented.

Dispatch by selection:
- If the user selects **"Implement in worktree"**, proceed to §1a (the Worktree Dispatch alternate path below) — §1a replaces §2–§4 for the main session.
- If the user selects **Implement in autonomous worktree**, proceed to §1b (Daytime Dispatch alternate path below).
- If the user selects **"Implement on main"**, remain on the current branch and proceed to §2 Task Dispatch.
- If the user selects **"Create feature branch"**, create and check out `feature/{lifecycle-slug}` before dispatching any tasks. All lifecycle artifacts (research, spec, plan) are already committed to main at this point, so the feature branch starts with the full artifact trail and only implementation commits diverge. Then proceed to §2 Task Dispatch.

If the current branch is not `main`/`master` (already on a feature branch or resumed session), skip the prompt and proceed on the current branch.

**Dependency graph analysis**: Parse the `**Depends on**` field from every pending task. Build an adjacency list: for each task, record which tasks it depends on. If a cycle is detected, stop and surface the error to the user — do not dispatch any tasks.

### 1a. Worktree Dispatch (Alternate Path)

This section runs **only** when the user selected "Implement in worktree" in §1. It **replaces §2–§4 for the main session**: the main session does not run Task Dispatch, Rework, or Transition directly. Instead, it dispatches an `Agent(isolation: "worktree")` to run the full implement → review → complete cycle autonomously inside the worktree, waits for the agent to return, surfaces the result, and exits /lifecycle.

**i. Write `.dispatching` marker atomically.** Before dispatching, the main session creates `lifecycle/{feature}/.dispatching` using bash `set -C` (noclobber) so concurrent dispatchers cannot both claim the dispatch:

```bash
(set -C; printf '%s\n%s\n%s\n' "$$" "$LIFECYCLE_SESSION_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > lifecycle/{feature}/.dispatching) 2>/dev/null
```

The marker contains exactly three lines: the dispatching shell's PID (`$$`), the dispatching session's `LIFECYCLE_SESSION_ID`, and an ISO 8601 UTC timestamp. **On collision** (the redirect fails because the file already exists): surface the error to the user ("another session claimed this dispatch first; aborting") and exit /lifecycle without dispatching.

**ii. Log `implementation_dispatch` event.** Append to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "implementation_dispatch", "feature": "<name>", "mode": "worktree"}
```

**iii. Dispatch the Agent.** Invoke:

```
Agent(isolation: "worktree", name: "agent-{lifecycle-slug}", model: <sonnet|opus>, prompt: <template below>)
```

**Model selection**: use `sonnet` for `low` and `medium` criticality, `opus` for `high` and `critical` criticality. Read criticality from the most recent `lifecycle_start` or `criticality_override` event in `events.log` (default `medium` if absent).

**iv. Verbatim prompt template** (pass this string as the `prompt` parameter with `{feature}` and `{lifecycle-slug}` substituted):

```
You are the dispatched lifecycle agent for feature {feature}. The main session has dispatched you via Agent(isolation: "worktree") to run the full implement → review → complete cycle autonomously inside worktree branch worktree/agent-{lifecycle-slug}. The main session remains on main and will not act on this feature again until you return.

State-write boundaries:
- You MUST skip SKILL.md Step 2 "Register session" and Step 2 "Backlog Write-Back". The main session that dispatched you owns those state writes for this feature. SKILL.md Step 2 detects your branch prefix (`worktree/agent-`) and skips both automatically; do not override that behavior.

Interactivity boundary:
- Do NOT call AskUserQuestion at any point. Use the documented non-interactive fallback at every decision point in the lifecycle phase references. If no fallback is documented for a specific decision, STOP and return the escalation context to the main session — do not prompt the user.

Task dispatch mechanics (when you reach implement.md §2 Task Dispatch):
- Use sequential inline per-task dispatch. Each task is implemented inline in YOUR OWN context using Read/Write/Edit/Bash directly.
- There are no nested `Agent(isolation: "worktree")` calls per task. Do NOT launch per-task sub-Agents at all — every task runs in your own conversation.
- Do NOT create per-task sub-branches (no `worktree/{task-name}` branches). After implementing each task, invoke the `/commit` skill to commit directly to worktree/agent-{lifecycle-slug} — your outer worktree branch.
- Tasks within a batch run one at a time (within-batch concurrency from §2b is forfeited). Batches still respect the dependency-graph topological grouping from §2 — batch N waits for batch N-1's commits to land before batch N starts.
- skip §2e Worktree Integration entirely — you have no per-task sub-branches to merge back. §2d's "Sequential dispatch" checkpoint (`git log --oneline -N`) is your verification path.
- The builder prompt template at implement.md lines 83-103 still applies per-task (read the task, implement what it specifies, commit via /commit, report), but each task is executed by you directly rather than dispatched as a sub-Agent.

Review/complete autonomy:
- Run implement → review → complete autonomously. cycle 1 CHANGES_REQUESTED from review is normal flow — re-enter implement and address the feedback.
- STOP and return escalation context (do not prompt the user) on any of: cycle 2+ CHANGES_REQUESTED, REJECTED verdict, test failure in complete.md, PR creation failure, or any other non-recoverable state.

Completion:
- On success, complete.md §4 Git Workflow pushes worktree/agent-{lifecycle-slug} and opens a PR (the branch is not main/master, so the existing binary check routes to the push+PR path automatically).
- Report the PR URL in your final response so the main session can surface it to the user.
```

**v. Wait for the Agent to return.** The main session blocks on the Agent call. Do not dispatch further work while waiting.

**vi. Surface the agent's summary.** When the Agent returns:
- **On success**: display the agent's final summary including the PR URL to the user.
- **On escalation**: display the agent's escalation context (which cycle, which phase, what failed) to the user so they can decide whether to continue the work manually from the worktree.

**vii. Remove the `.dispatching` marker.** Run `rm -f lifecycle/{feature}/.dispatching` to remove the .dispatching marker regardless of outcome (success or escalation).

**viii. Log `dispatch_complete` event.** Append to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "dispatch_complete", "feature": "<name>", "outcome": "complete|escalated", "pr_url": "<url>|null"}
```

Set `"outcome"` to `"complete"` if the agent finished cleanly with a PR URL, or `"escalated"` if it stopped at a non-recoverable state. Set `"pr_url"` to the PR URL string on success, or the JSON literal `null` on escalation.

**ix. Exit /lifecycle entirely.** Do not transition to any further phase. The worktree agent has already run the full lifecycle; the main session's role is done.

**Known Limitations:**
- **AskUserQuestion sharp edge**: The inner agent is technically able to call `AskUserQuestion` despite the prompt instruction forbidding it. If it does, the prompt MAY surface in the main session's terminal (the Agent tool may propagate inner-agent prompts to the parent). The prompt explicitly forbids this and Claude is expected to follow, but the tool boundary does not enforce it.
- **Events.log divergence (TC8)**: Main's `events.log` captures only `implementation_dispatch` and `dispatch_complete` for this feature. The inner agent's `phase_transition`, `task_complete`, `review_verdict`, and `feature_complete` events live in the worktree's copy of `events.log` and land on main only when the PR merges. Tooling that inspects "recent feature_complete events" from main's checkout may under-count completed features during the window between dispatch and PR merge.

**Cleanup:** The main session does **no manual cleanup** of the dispatched worktree. Do not remove the worktree or delete the branch as part of this dispatch flow. The existing `hooks/cortex-cleanup-session.sh` handles the `worktree/agent-*` branches and `.claude/worktrees/agent-*` directories on session exit (the hook internally runs git worktree removal and branch deletion — those are cleanup-hook implementation details, not orchestrator instructions).

### 1b. Daytime Dispatch (Alternate Path)

This section runs **only** when the user selected "Implement in autonomous worktree" in §1. It **replaces §2–§4 for the main session**: the main session does not run Task Dispatch, Rework, or Transition directly. Instead, it launches the daytime pipeline as a background subprocess, polls for progress, surfaces the final outcome, and exits /lifecycle.

Unlike §1a, there is **no `.dispatching` noclobber marker** — the existing `$$`-based mechanism is unsuitable for a detached background subprocess (the dispatching shell's PID `$$` dies milliseconds after the Bash call returns). The `daytime.pid` guard below is sufficient to prevent double-dispatch.

**i. Plan.md prerequisite check.** Before any guards or subprocess launch, verify `lifecycle/{feature}/plan.md` exists. If absent: surface to the user "plan.md not found — cannot launch autonomous worktree. Run /lifecycle plan first." and exit §1b. Do NOT proceed to the guards or the subprocess launch.

**ii. Double-dispatch guard.** Two separate Bash calls (no compound commands):

1. Read PID file: `cat lifecycle/{feature}/daytime.pid 2>/dev/null`
2. Liveness check on the PID (if the file was non-empty): `kill -0 $pid 2>/dev/null`

If `kill -0` exits 0 (process alive): reject with "Autonomous daytime run already in progress (PID {pid}) — wait for it to complete or check events.log" and exit §1b. If the exit code is non-zero or the file was empty/absent: proceed.

**iii. Overnight concurrent guard.** Four separate Bash calls (no compound commands):

1. Read active session descriptor: `cat ~/.local/share/overnight-sessions/active-session.json 2>/dev/null`. If absent or empty: proceed normally (no overnight session active).
2. Parse `repo_path`, `phase`, and `state_path` fields from the JSON. If `repo_path` does not equal the current working directory, **or** `phase` is not `"executing"`: proceed normally.
3. Derive the session directory as the parent directory of `state_path` (i.e., `Path(state_path).parent`). `state_path` is the full path to the session's state JSON file (e.g., `lifecycle/sessions/{id}/overnight-state.json`); the session directory is the containing directory. This matches the detection pattern used by `bin/overnight-status`. Read the runner lock file: `cat {session_dir}/.runner.lock 2>/dev/null` and extract the runner PID.
4. Liveness check: `kill -0 $runner_pid 2>/dev/null`. If the runner is alive (exit 0): reject with "Overnight runner is active (PID {pid}) — wait for it to complete before launching a daytime run." and exit §1b. If the runner is dead (non-zero exit): emit warning "overnight state shows executing but no live runner found — may be stale; proceeding" and continue.

**iv. Background subprocess launch.** Single Bash call with `run_in_background: true`:

```
python3 -m claude.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1
```

The subprocess is responsible for writing `lifecycle/{feature}/daytime.pid` at its own startup. The skill does not write the PID file — it only reads it.

**v. Log `implementation_dispatch` event.** Immediately after the background launch, a separate Bash call appends to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "implementation_dispatch", "feature": "<name>", "mode": "daytime"}
```

**vi. Polling loop.** Sequential Bash calls only — no compound commands.

**Initial wait**: issue a `sleep 10` Bash call with `timeout: 15000` (15 seconds — ample margin over the 10-second sleep). This follows a background launch, so it is not a blocking subprocess wait; it gives the subprocess time to write its PID file.

**After initial wait**: read the PID file with `cat lifecycle/{feature}/daytime.pid 2>/dev/null`. If the file is absent: this is a startup failure — skip the polling loop and go directly to result surfacing (§vii) using the content of `daytime.log`.

**Per-iteration steps** (each a separate Bash call):
- (a) Liveness: `kill -0 $pid 2>/dev/null`. Non-zero exit means the process has exited — break out of the polling loop and proceed to result surfacing.
- (b) Progress tail: `tail -n 5 lifecycle/{feature}/events.log` and surface a brief summary of the 5 most recent events to the user. The tail is capped at 5 (not 20) to limit context accumulation over long runs.
- (c) Inter-iteration sleep: `sleep 120` Bash call with `timeout: 130000` (130 seconds — ample margin over the 120-second sleep).

**Termination bound**: 120 iterations (~4 hours). Context window exhaustion — not iteration count — is the practical binding constraint for long runs. At **30 iterations (~1 hour)**, pause and offer the user the option to suspend polling: "Subprocess still running after 30 iterations (~1 hour). Continue polling or stop? (The process continues in background — monitor `lifecycle/{feature}/daytime.log` and `events.log` directly.)" If the user chooses to stop, exit the polling loop (the subprocess keeps running; skip result surfacing and log `dispatch_complete` with outcome `"paused"` only if the subprocess is still alive — otherwise surface results normally). On reaching 120 iterations without the subprocess exiting: surface "Polling timeout — subprocess may still be running (PID {pid}). Check `lifecycle/{feature}/daytime.log` directly for status." and exit the polling loop.

**vii. Result surfacing.** Read the last non-empty line of `lifecycle/{feature}/daytime.log` that begins with `"Feature "`. Apply first-match-wins in this exact order:

1. Line contains `"merged successfully"` → **success**: display the line to the user; scan the full `daytime.log` for a GitHub PR URL matching the pattern `https://github.com/[^/]+/[^/]+/pull/[0-9]+` and display it if found.
2. Line contains `"deferred"` → **deferred**: display the line; read the most recently modified file in `lifecycle/{feature}/deferred/` (by modification time) and display its content; if multiple files exist, note the count.
3. Line contains `"paused"` → **paused**: display the line; instruct the user to check `events.log` for details and re-run when ready.
4. No `"Feature "` line is found, or the line matches none of the above → **failed**: display the last 20 lines of `daytime.log`; instruct the user to check `lifecycle/{feature}/daytime.log` for full details.

This ordered detection is intentional: a failure message containing "paused" as a substring (e.g. `"Feature X failed: subprocess paused unexpectedly"`) still classifies as failed because "merged successfully" and "deferred" are checked first, and "paused" would only match at step 3, which is reached only if steps 1 and 2 did not match. The ordering ensures substring accidents do not misclassify.

**viii. Log `dispatch_complete` event.** After result surfacing, a separate Bash call appends to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "dispatch_complete", "feature": "<name>", "mode": "daytime", "outcome": "complete|deferred|paused|failed", "pr_url": "<url>|null"}
```

The `outcome` field maps from the result-surfacing classification: "merged successfully" → `"complete"`, "deferred" → `"deferred"`, "paused" → `"paused"`, other / no-match → `"failed"`. The `pr_url` field is the PR URL string if one was found during success surfacing, or the JSON literal `null` otherwise.

**ix. Exit /lifecycle entirely.** Do not transition to any further phase. The daytime pipeline has already run the full lifecycle; the main session's role is done.

### 2. Task Dispatch

Compute batches from the dependency graph using topological level grouping:
- **Batch 0**: All pending tasks with `**Depends on**: none` (or whose dependencies are already `[x]`).
- **Batch 1**: Tasks whose dependencies are all in batch 0.
- **Batch N**: Tasks whose dependencies are all in batches 0 through N-1.

If all tasks are linearly dependent, this naturally produces one task per batch (sequential execution).

For each batch, in order:

**a. Extract task texts**: For every task in the batch, copy its full task block from plan.md (everything between `### Task N:` and the next task heading).

**b. Dispatch batch**: Launch all tasks in the batch concurrently as parallel sub-tasks. Use the builder prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions. Provide the full task text plus 2-3 sentences of architectural context from the plan's Overview section.

**Model**: `sonnet` for low/medium criticality, `opus` for high/critical (read criticality from events.log).

After launching, append a `batch_dispatch` event to `lifecycle/{feature}/events.log`:
```
{"ts": "<ISO 8601>", "event": "batch_dispatch", "feature": "<name>", "batch": <N>, "tasks": [<task IDs in this batch>]}
```

**c. Wait for batch completion**: All tasks in the batch must finish before proceeding.

**d. Checkpoint**: Verify each successful task produced a commit:

- **Worktree dispatch** (`Agent(isolation: "worktree")`): For each task, run `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD, where `{task-name}` is the `name` passed to `Agent(isolation: "worktree")`. Zero lines of output means the sub-agent produced no new commits — mark the task as failed. The orchestrator must NOT commit from its own branch on the sub-agent's behalf.
- **Sequential dispatch**: Run `git log --oneline -N` (where N = number of tasks in the batch) to verify commits are present.

Then update plan.md to change `[ ]` to `[x]` for every task that completed successfully in the batch.

For each task in the batch (whether it succeeded or failed), append a `task_complete` event to `lifecycle/{feature}/events.log`:
```
{"ts": "<ISO 8601>", "event": "task_complete", "feature": "<name>", "task": <task ID>, "batch": <N>, "status": "success|failed"}
```

**e. Worktree Integration**: Skip this step entirely for sequential (non-worktree) dispatch.

After checkpoint, merge each completed task's worktree branch back into the feature branch and clean up. This ensures subsequent batches' worktrees, created via `cortex-worktree-create.sh`, branch from the updated HEAD and see prior batches' changes.

For each task in the batch (in task order):

1. **No-changes case**: If the task's Agent result shows no changes were made, the worktree was already auto-cleaned by the Agent tool. Skip merge and cleanup for that task.
2. **Failed-commit case**: If `git log HEAD..worktree/{task-name} --oneline` showed zero lines (the task failed to produce a commit), skip the merge but still run cleanup: `git worktree remove .claude/worktrees/{task-name}` then `git branch -d worktree/{task-name}`.
3. **Merge**: For tasks that passed the checkpoint (produced commits), run `git merge worktree/{task-name}` from the feature branch.
4. **Cleanup**: After a successful merge, run `git worktree remove .claude/worktrees/{task-name}` then `git branch -d worktree/{task-name}`.
5. **Partial integration failure**: If `git merge worktree/{task-name}` produces a conflict, surface it as an integration error including the branch name `worktree/{task-name}`. Continue processing remaining tasks in the batch — do not roll back already-merged branches.

**f. Report**: Summarize what the batch accomplished and any issues before dispatching the next batch.

### Failure Handling

When a task in a batch fails:
1. Let other in-flight tasks in the same batch finish — do not abort them.
2. Checkpoint successful tasks from the batch as `[x]`.
3. Identify downstream tasks that transitively depend on the failed task — these are blocked.
4. Surface the failure with context: which task failed, what error occurred, and which downstream tasks are now blocked.
5. Ask the user: **retry** (re-dispatch the failed task), **skip** (mark it failed, continue with non-dependent tasks), or **abort** (stop implementing).

### Builder Prompt Template

```
You are implementing a single task for the {feature} feature.

## Task
{full task text from plan.md}

## Architectural Context
{2-3 sentences from plan Overview section}

## Instructions
1. Implement exactly what the task specifies
2. File paths and artifact locations must match the specification exactly. If you believe a spec path is wrong, flag it as an issue rather than silently deviating
3. Verify your implementation works as described in the Verification field
4. Commit your work using the Skill tool: `skill: "commit"`. You have full tool access including the Skill tool — do not use raw `git commit` or `git -C` commands.
5. Report what you did and any issues encountered. For each task completed, report: task name, status (completed/partial/failed), files modified, verification outcome, issues or deviations from the spec.
6. Do not write files or artifacts solely to satisfy your own verification check. If a verification step requires checking something you created in this task for the purpose of satisfying verification (not as the task's primary deliverable), flag it as self-sealing in your exit report rather than self-certifying.

If this task references the specification, read lifecycle/{feature}/spec.md.
Do not implement other tasks. Do not modify files not listed in this task.
Do not add features beyond what is specified.
```

### 3. Rework (Review Re-Entry)

If re-entering from a Review phase with CHANGES_REQUESTED:

Append a `phase_transition` event to `lifecycle/{feature}/events.log` to capture the rework cycle start:
```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "implement"}
```

1. Read `lifecycle/{feature}/review.md` for the reviewer's feedback
2. Identify which tasks were flagged
3. For each flagged task, dispatch a fresh sub-task with:
   - The original task text
   - The reviewer's specific feedback for that task
   - Instruction to fix the identified issues
4. Non-flagged tasks retain their `[x]` status
5. After rework, return to Review

### 4. Transition

When all tasks are `[x]`, determine the next phase using both complexity tier and criticality. Read criticality from `events.log` (most recent `lifecycle_start` or `criticality_override` event; default `medium` if absent).

**Review gating matrix:**

| Criticality | simple | complex |
|-------------|--------|---------|
| low         | Complete | Review |
| medium      | Complete | Review |
| high        | **Review** | Review |
| critical    | **Review** | Review |

High and critical criticality forces Review regardless of complexity tier. Low and medium criticality proceeds to Complete for simple tier, and to Review for complex tier.

Append a `phase_transition` event to `lifecycle/{feature}/events.log`:
```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "tier": "simple|complex", "from": "implement", "to": "review|complete"}
```
The `"to"` field is determined by the gating matrix above.

**Proceed automatically** — do not ask the user for confirmation before entering the next phase. Announce the transition briefly and continue.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should look at other tasks too to understand the full picture" | Each task is self-contained by design. The plan already decomposed the work so each task has everything it needs. Reading other tasks risks scope creep. |
| "I can optimize by combining tasks" | Combined tasks are harder to verify, harder to revert, and harder to review. One task, one commit, one concern. |
| "This task is too small, let me do more" | Small tasks with clear scope succeed reliably. Large tasks with vague scope fail unpredictably. Trust the plan's sizing. |
| "I should dispatch all tasks at once for maximum speed" | Batch ordering respects dependencies. Tasks in batch N+1 must wait for batch N to complete, even if some seem independent. The batch model keeps dispatch simple and checkpoint writes serialized. |
| "This path would be better organized as X" | Deviating from spec paths breaks traceability between phases. If the spec path is wrong, flag it — don't fix it silently. |
| "I'll just run `git add` and `git commit` directly" | Always use `/commit` for all commits — orchestrator checkpoints included. Never use raw git commands for staging or committing. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty about this is not a reason to bypass it. |
