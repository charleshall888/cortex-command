# Implement Phase

Execute the plan by dispatching a fresh implementation sub-task per task. Each sub-task runs with fresh context to prevent stale assumptions.

## Contents

1. [Protocol](#protocol)
2. [Constraints](#constraints)

## Protocol

### 1. Pre-Flight Check

Read `lifecycle/{feature}/plan.md` and identify pending tasks (those with `[ ]`).

**Branch selection**: If the current branch is `main` or `master`, prompt the user via AskUserQuestion with three options:

- **Implement on current branch** (recommended) — trunk-based workflow, changes land directly on the current branch. **When to pick**: tiny, trunk-safe changes where a branch would be overhead.
- **Implement in autonomous worktree** — dispatch to the daytime pipeline (`python3 -m cortex_command.overnight.daytime_pipeline`) which runs the full implement → review → complete cycle headlessly in the background without requiring live steering; note that uncommitted changes remain on main and do not travel to the worktree. **When to pick**: medium/many-task/no-live-steering-needed features where you want to kick off a longer autonomous run and move on. Proceeds to §1a below.
- **Create feature branch** — create `feature/{lifecycle-slug}` for PR-based workflow. **When to pick**: you want a PR-based flow but cannot use a worktree (e.g., tooling that assumes a single checkout). NOTE: this runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Uncommitted-changes guard**: Immediately before the `AskUserQuestion` call, run `git status --porcelain` (no path filter, no additional flags). If non-empty output is returned, the option that keeps the user on the current branch is demoted in place: (a) prepend the fixed warning `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` as a one-line prefix to that option's description, and (b) strip the `(recommended)` suffix from that option's label if present. The option remains selectable and stays at its existing position — no removal, no gating pre-question. If `git status --porcelain` exits non-zero (e.g., missing `.git`, corrupt index, bisect/rebase state), the guard does not fire — neither the demotion nor the warning prefix are applied — a single-line diagnostic `uncommitted-changes guard skipped: git status failed` is surfaced alongside the prompt, and the pre-flight continues normally as a fallback.

**Runtime probe**: After the uncommitted-changes guard and before assembling the prompt's options array, run a single Bash call that probes for the top-level `cortex_command` package via `importlib.util.find_spec` against that top-level module name. The probe is wrapped in an explicit `try/except` so that an exception inside the import machinery cannot collide with the absence-signaling exit 1:

```
python3 -c "
import sys
try:
    import importlib.util
    sys.exit(0 if importlib.util.find_spec('cortex_command') is not None else 1)
except Exception:
    sys.exit(2)
"
```

Route by exit code into one of three menu dispositions:

- **exit 0** → the `cortex_command` module is present → all three options remain unchanged: `Implement on current branch`, `Implement in autonomous worktree`, and `Create feature branch`.
- **exit 1** → the module is absent → remove `Implement in autonomous worktree` from the options array; this is a silent hide, with no diagnostic surfaced. The post-degrade option set is `Implement on current branch` and `Create feature branch`.
- **any other exit** (including 2 and 127) → the probe failed → fail open: all three options remain, and the literal diagnostic string `runtime probe skipped: import probe failed` is surfaced alongside the prompt.

After the probe completes and the options array has been resolved per the routing rules above, the resolved options array is then passed to `AskUserQuestion`.

Dispatch by selection:
- If the user selects **Implement in autonomous worktree**, proceed to §1a (Daytime Dispatch alternate path below).
- If the user selects **"Implement on current branch"**, remain on the current branch and proceed to §2 Task Dispatch.
- If the user selects **"Create feature branch"**, create and check out `feature/{lifecycle-slug}` before dispatching any tasks. All lifecycle artifacts (research, spec, plan) are already committed to main at this point, so the feature branch starts with the full artifact trail and only implementation commits diverge. Then proceed to §2 Task Dispatch.

If the current branch is not `main`/`master` (already on a feature branch or resumed session), skip the prompt and proceed on the current branch.

**Dependency graph analysis**: Parse the `**Depends on**` field from every pending task. Build an adjacency list: for each task, record which tasks it depends on. If a cycle is detected, stop and surface the error to the user — do not dispatch any tasks.

### 1a. Daytime Dispatch (Alternate Path)

This section runs **only** when the user selected "Implement in autonomous worktree" in §1. It **replaces §2–§4 for the main session**: the main session does not run Task Dispatch, Rework, or Transition directly. Instead, it launches the daytime pipeline as a background subprocess, polls for progress, surfaces the final outcome, and exits /cortex-core:lifecycle.

There is **no `.dispatching` noclobber marker** on this path — the `$$`-based mechanism is unsuitable for a detached background subprocess (the dispatching shell's PID `$$` dies milliseconds after the Bash call returns). The `daytime.pid` guard below is sufficient to prevent double-dispatch.

**i. Plan.md prerequisite check.** Before any guards or subprocess launch, verify `lifecycle/{feature}/plan.md` exists. If absent: surface to the user "plan.md not found — cannot launch autonomous worktree. Run /cortex-core:lifecycle plan first." and exit §1a. Do NOT proceed to the guards or the subprocess launch.

**ii. Double-dispatch guard.** Two separate Bash calls (no compound commands):

1. Read PID file: `cat lifecycle/{feature}/daytime.pid 2>/dev/null`
2. Liveness check on the PID (if the file was non-empty): `kill -0 $pid 2>/dev/null`

If `kill -0` exits 0 (process alive): reject with "Autonomous daytime run already in progress (PID {pid}) — wait for it to complete or check events.log" and exit §1a. If the exit code is non-zero or the file was empty/absent: proceed.

**iii. Overnight concurrent guard.** Four separate Bash calls (no compound commands):

1. Read active session descriptor: `cat ~/.local/share/overnight-sessions/active-session.json 2>/dev/null`. If absent or empty: proceed normally (no overnight session active).
2. Parse `repo_path`, `phase`, and `state_path` fields from the JSON. If `repo_path` does not equal the current working directory, **or** `phase` is not `"executing"`: proceed normally.
3. Derive the session directory as the parent directory of `state_path` (i.e., `Path(state_path).parent`). `state_path` is the full path to the session's state JSON file (e.g., `lifecycle/sessions/{id}/overnight-state.json`); the session directory is the containing directory. Read the runner lock file: `cat {session_dir}/.runner.lock 2>/dev/null` and extract the runner PID.
4. Liveness check: `kill -0 $runner_pid 2>/dev/null`. If the runner is alive (exit 0): reject with "Overnight runner is active (PID {pid}) — wait for it to complete before launching a daytime run." and exit §1a. If the runner is dead (non-zero exit): emit warning "overnight state shows executing but no live runner found — may be stale; proceeding" and continue.

**iv. Background subprocess launch.** Three preparatory Bash calls before the launch, then one launch call, then one post-launch update call — five calls total (no compound commands):

**Step 1 — Mint dispatch UUID.** Single Bash call:

```
python3 -c 'import uuid; print(uuid.uuid4().hex)'
```

Stash the printed 32-char lowercase hex string into conversation memory as the active `dispatch_id` for the current feature.

**Step 2 — Write `daytime-dispatch.json` atomically.** Single Bash call (before the subprocess launch):

```
python3 -m cortex_command.overnight.daytime_dispatch_writer --feature {slug} --dispatch-id {uuid} --mode init
```

This writes `lifecycle/{feature}/daytime-dispatch.json` with `pid: null` via the canonical atomic-write helper. The dispatch file is the on-disk authoritative source for `dispatch_id` — it survives main-session compaction and allows a re-entered skill to recover the active dispatch identity without trusting in-memory state.

**Step 3 — Launch background subprocess.** Single Bash call with `run_in_background: true`, with `DAYTIME_DISPATCH_ID` prefixed:

```
DAYTIME_DISPATCH_ID={uuid} python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > lifecycle/{feature}/daytime.log 2>&1
```

The subprocess is responsible for writing `lifecycle/{feature}/daytime.pid` at its own startup. The skill does not write the PID file — it only reads it.

**Step 4 — Update `daytime-dispatch.json` with subprocess PID.** After the PID file has been written (following the initial-wait in §vi), update the `pid` field via the canonical helper:

```
python3 -m cortex_command.overnight.daytime_dispatch_writer --feature {slug} --mode update-pid --pid {pid}
```

This ensures the on-disk dispatch file reflects the actual subprocess PID for liveness monitoring.

**v. Log `implementation_dispatch` event.** Immediately after the background launch, a separate Bash call appends to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "implementation_dispatch", "feature": "<name>", "mode": "daytime"}
```

**vi. Polling loop.** Sequential Bash calls only — no compound commands.

**Initial wait**: issue a `sleep 10` Bash call with `timeout: 15000` (15 seconds — ample margin over the 10-second sleep). This follows a background launch, so it is not a blocking subprocess wait; it gives the subprocess time to write its PID file.

**After initial wait**: read the PID file with `cat lifecycle/{feature}/daytime.pid 2>/dev/null`. If the file is absent: this is a startup failure — skip the polling loop and go directly to result surfacing (§vii) using the content of `daytime.log`.

**Per-iteration steps** (each a separate Bash call):
- (a) Liveness: `kill -0 $pid 2>/dev/null`. Non-zero exit means the process has exited — break out of the polling loop and proceed to result surfacing.
- (b) Inter-iteration sleep: `sleep 120` Bash call with `timeout: 130000` (130 seconds — ample margin over the 120-second sleep).

**Termination bound**: 120 iterations (~4 hours). Context window exhaustion — not iteration count — is the practical binding constraint for long runs. At **30 iterations (~1 hour)**, pause and offer the user the option to suspend polling: "Subprocess still running after 30 iterations (~1 hour). Continue polling or stop? (The process continues in background — monitor `lifecycle/{feature}/daytime.log` and `events.log` directly.)" If the user chooses to stop, exit the polling loop (the subprocess keeps running; skip result surfacing and log `dispatch_complete` with outcome `"paused"` only if the subprocess is still alive — otherwise surface results normally). On reaching 120 iterations without the subprocess exiting: surface "Polling timeout — subprocess may still be running (PID {pid}). Check `lifecycle/{feature}/daytime.log` directly for status." and exit the polling loop.

**vii. Result surfacing.** Invoke the `daytime_result_reader` helper module — the canonical classification logic — via a single Bash call:

```
python3 -m cortex_command.overnight.daytime_result_reader --feature {slug}
```

The helper implements the full 3-tier fallback (Tier 1: `daytime-result.json` + freshness check against `daytime-dispatch.json`; Tier 2: `daytime-state.json` phase discrimination; Tier 3: `outcome: "unknown"` with discriminated message) and prints a JSON dict to stdout. The skill MAY cache the dispatch UUID in conversation memory for speed, but `daytime-dispatch.json` on disk is authoritative — the helper reads it directly, so a re-entered skill after compaction or process restart recovers the active dispatch identity without trusting in-memory state.

Parse the JSON output. The returned dict has fields: `outcome`, `terminated_via`, `message`, `source_tier`, `pr_url`, `deferred_files`, `error`, `log_tail`.

Surface the result to the user based on `source_tier` + `outcome`:

**Tier 1 success** (`source_tier == 1`): the helper validated `schema_version == 1` (hard equality — no "greater than" branch; missing, null, or any value other than `1` falls to tier 2), matched `dispatch_id` against `daytime-dispatch.json` (stale prior-run files with mismatched `dispatch_id` fall to tier 2), and classified from the result file. Map `outcome`:

- `outcome: "merged"` → display the `message` field; surface `pr_url` if non-null.
- `outcome: "deferred"` → display the `message` field; list each path in `deferred_files`; display content of the most recently modified deferred file.
- `outcome: "paused"` → display the `message` field; instruct the user to check `events.log` for details and re-run when ready.
- `outcome: "failed"` → display the `message` field; show the `error` field if non-null.

After displaying a tier-1 result, issue a separate Bash call to delete `daytime-dispatch.json` and mark the dispatch as consumed:

```
rm lifecycle/{feature}/daytime-dispatch.json
```

**Tier 3 surface** (`source_tier == 3`, `outcome: "unknown"`): the helper fell through tiers 1 and 2 and produced a discriminated message. Display the `message` field (one of three verbatim messages per spec R6: "Subprocess likely completed but its result file is missing or invalid…", "Subprocess did not complete…", or "Subprocess never started…") and display the `log_tail` field (last 20 lines of `daytime.log`). The classification that flows into §1a viii's `dispatch_complete` event is `outcome: "unknown"`. Do NOT silently classify as `"failed"`.

**viii. Log `dispatch_complete` event.** After result surfacing, a separate Bash call appends to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "dispatch_complete", "feature": "<name>", "mode": "daytime", "outcome": "complete|deferred|paused|failed|unknown", "pr_url": "<url>|null"}
```

The `outcome` field maps from the result-surfacing classification:

- Tier-1 `outcome: "merged"` → `"complete"`
- Tier-1 `outcome: "deferred"` → `"deferred"`
- Tier-1 `outcome: "paused"` → `"paused"`
- Tier-1 `outcome: "failed"` → `"failed"`
- Tier-3 surface (all discrimination variants) → `"unknown"`

The `pr_url` field is the PR URL string if one was surfaced from the result file during Tier-1 success (merged outcome), or the JSON literal `null` otherwise.

**ix. Exit /cortex-core:lifecycle entirely.** Do not transition to any further phase. The daytime pipeline has already run the full lifecycle; the main session's role is done.

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

After checkpoint, merge each completed task's worktree branch back into the feature branch and clean up. This ensures subsequent batches' worktrees, created via `claude/hooks/cortex-worktree-create.sh`, branch from the updated HEAD and see prior batches' changes.

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
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "implement-rework"}
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
| "I should dispatch all tasks at once for maximum speed" | Batch ordering respects dependencies. Tasks in batch N+1 must wait for batch N to complete, even if some seem independent. The batch model keeps dispatch simple and checkpoint writes serialized. |
| "I'll just run `git add` and `git commit` directly" | Always use `/cortex-core:commit` for all commits — orchestrator checkpoints included. Never use raw git commands for staging or committing. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty about this is not a reason to bypass it. |
