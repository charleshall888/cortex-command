# Implement Phase

Execute the plan by dispatching a fresh implementation sub-task per task. Each sub-task runs with fresh context to prevent stale assumptions.

## Contents

1. [Protocol](#protocol)
2. [Constraints](#constraints)

## Protocol

### 1. Pre-Flight Check

Read `cortex/lifecycle/{feature}/plan.md` and identify pending tasks (those with `[ ]`).

**Branch selection**: If the current branch is `main` or `master`, prompt the user via AskUserQuestion with three options:

- **Implement on current branch** (recommended) — trunk-based workflow, changes land directly on the current branch. **When to pick**: tiny, trunk-safe changes where a branch would be overhead.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `$TMPDIR/cortex-worktrees/interactive-{slug}/` and returns the path; the user then manually cd's into the worktree OR opens a fresh `claude --worktree=<path>` session to continue the implement phase there (Variant A vs Variant B dispatch is owned by epic #240; T10 ships only the create + handoff step). **When to pick**: medium/many-task features where you want an isolated branch with worktree but still need live steering. Proceeds to §1a below.
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

- **exit 0** → the `cortex_command` module is present → all three options remain unchanged: `Implement on current branch`, `Implement on feature branch with worktree`, and `Create feature branch`.
- **exit 1** → the module is absent → remove `Implement on feature branch with worktree` from the options array; this is a silent hide, with no diagnostic surfaced. The post-degrade option set is `Implement on current branch` and `Create feature branch`.
- **any other exit** (including 2 and 127) → the probe failed → fail open: all three options remain, and the literal diagnostic string `runtime probe skipped: import probe failed` is surfaced alongside the prompt.

After the probe completes and the options array has been resolved per the routing rules above, the resolved options array is then passed to `AskUserQuestion`.

Dispatch by selection:
- If the user selects **Implement on feature branch with worktree**, run the two interactive preflight guards below (Steps A and B) before proceeding to §1a. If either guard rejects, exit §1 without creating a worktree.

  **Step A — Overnight-active rejection mirror**: Source the overnight-probe sidecar and surface interactive-tailored wording on exit 1:

  ```
  cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to work to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
  ```

  Sidecar exit codes: `0` = no overnight active, proceed to Step B; `1` = overnight live for this repo, surface the wording above and exit §1 without creating a worktree; `2` = stale runner detected, surface a warn-and-continue diagnostic and proceed to Step B.

  **Step B — Interactive lock acquisition**: Run a single Bash call to acquire the per-feature interactive lock:

  ```
  cortex-interactive-lock acquire {slug}
  ```

  On exit 0: proceed to §1a. On non-zero exit: the console-script has already written R5's rejection wording to stderr — surface stderr verbatim and exit §1 without creating a worktree:

  > Interactive session already active on this feature (session {session_id}, acquired {acquired_at}). Wait for it to exit, or work on a different feature, or run `cortex-interactive-lock inspect {slug}` for details.

- If the user selects **"Implement on current branch"**, remain on the current branch and proceed to §2 Task Dispatch.
- If the user selects **"Create feature branch"**, create and check out `feature/{lifecycle-slug}` before dispatching any tasks. All lifecycle artifacts (research, spec, plan) are already committed to main at this point, so the feature branch starts with the full artifact trail and only implementation commits diverge. Then proceed to §2 Task Dispatch.

If the current branch is not `main`/`master` (already on a feature branch or resumed session), skip the prompt and proceed on the current branch.

**Dependency graph analysis**: Parse the `**Depends on**` field from every pending task. Build an adjacency list: for each task, record which tasks it depends on. If a cycle is detected, stop and surface the error to the user — do not dispatch any tasks.

### 1a. Interactive Worktree Creation (Alternate Path)

This section runs **only** when the user selected "Implement on feature branch with worktree" in §1. It **replaces §2–§4 for the main session**: the main session creates the worktree, returns the path to the user, and exits `/cortex-core:lifecycle`. The user then continues implementation inside the worktree (Variant A: `cd` into it; Variant B: open a fresh `claude --worktree=<path>` session) — that handoff dispatch is owned by epic #240 and is out of scope here.

**i. Interactive worktree liveness check.** Two separate Bash calls (no compound commands):

1. Read the interactive PID file: `cat cortex/lifecycle/sessions/{slug}.interactive.pid 2>/dev/null`
2. If the file was non-empty, liveness check on the PID: `kill -0 $pid 2>/dev/null`

If `kill -0` exits 0 (process alive): reject with "An interactive worktree session is already live for `{slug}` (PID {pid}). Resolve it before creating a new worktree." and exit §1a without creating a worktree. If the exit code is non-zero or the file was absent/empty: proceed.

**ii. Overnight concurrent guard.** Run the overnight-active probe sidecar via `cat`-then-eval. The four-bash-call sequence (read `active-session.json`, parse `repo_path` and `session_dir`, read `{session_dir}/runner.pid`, parse `pid` from the JSON via `python3 -c "import json,sys; print(json.load(sys.stdin)['pid'])" < {session_dir}/runner.pid`) is extracted into the sidecar at `skills/lifecycle/references/_interactive_overnight_check.sh` and invoked as:

```
cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```

Sidecar exit codes: `0` = no overnight active, proceed normally; `1` = overnight live for this repo, surface the wording and exit §1a; `2` = stale runner detected (runner.pid absent or process dead), surface a warn-and-continue diagnostic and proceed.

**iii. Worktree creation.** Single Bash call invoking `create_worktree` from `cortex_command.pipeline.worktree`:

```python
from cortex_command.pipeline.worktree import create_worktree
info = create_worktree(feature="interactive-{slug}", base_branch="main")
```

The `interactive-` prefix causes `create_worktree` to resolve the branch as `interactive/{slug}` (via `_resolve_branch_name` with `prefix="interactive"`), and the worktree is materialized at `$TMPDIR/cortex-worktrees/interactive-{slug}/`. The function copies `.claude/settings.local.json` into the worktree and symlinks `.venv` as part of the standard post-creation steps.

If creation fails (raises `ValueError`): surface the error to the user and exit §1a — do not proceed to handoff.

**iv. Handoff.** Surface the worktree path to the user with the following message (substituting the actual resolved path from `info.path`):

```
Interactive worktree created at: {info.path}
Branch: interactive/{slug}

To continue implementation:
  Variant A — cd into the worktree and resume in this session:
    cd {info.path}
  Variant B — open a fresh Claude Code session inside the worktree:
    claude --worktree={info.path}

(Variant A vs Variant B dispatch is owned by epic #240. This step — worktree creation — is complete.)
```

**v. Exit /cortex-core:lifecycle entirely.** Do not transition to any further phase. The worktree has been created; the user's next action is inside the worktree.

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

After launching, append a `batch_dispatch` event to `cortex/lifecycle/{feature}/events.log`:
```
{"ts": "<ISO 8601>", "event": "batch_dispatch", "feature": "<name>", "batch": <N>, "tasks": [<task IDs in this batch>]}
```

**c. Wait for batch completion**: All tasks in the batch must finish before proceeding.

**d. Checkpoint**: Verify each successful task produced a commit:

- **Worktree dispatch** (`Agent(isolation: "worktree")`): For each task, run `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD, where `{task-name}` is the `name` passed to `Agent(isolation: "worktree")`. Zero lines of output means the sub-agent produced no new commits — mark the task as failed. The orchestrator must NOT commit from its own branch on the sub-agent's behalf.
- **Sequential dispatch**: Run `git log --oneline -N` (where N = number of tasks in the batch) to verify commits are present.

Then update plan.md to change `[ ]` to `[x]` for every task that completed successfully in the batch.

**e. Worktree Integration**: Skip this step entirely for sequential (non-worktree) dispatch.

After checkpoint, merge each completed task's worktree branch back into the feature branch and clean up. This ensures subsequent batches' worktrees, created via `claude/hooks/cortex-worktree-create.sh`, branch from the updated HEAD and see prior batches' changes.

For each task in the batch (in task order):

1. **No-changes case**: If the task's Agent result shows no changes were made, the worktree was already auto-cleaned by the Agent tool. Skip merge and cleanup for that task.
2. **Failed-commit case**: If `git log HEAD..worktree/{task-name} --oneline` showed zero lines (the task failed to produce a commit), skip the merge but still run cleanup: `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`.
3. **Merge**: For tasks that passed the checkpoint (produced commits), run `git merge worktree/{task-name}` from the feature branch.
4. **Cleanup**: After a successful merge, run `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`. The `cortex-worktree-resolve` console script returns the canonical worktree path (`$TMPDIR/cortex-worktrees/{task-name}/`) via the single resolver chokepoint.
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

If this task references the specification, read cortex/lifecycle/{feature}/spec.md.
Do not implement other tasks. Do not modify files not listed in this task.
Do not add features beyond what is specified.
```

### 3. Rework (Review Re-Entry)

If re-entering from a Review phase with CHANGES_REQUESTED:

Append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log` to capture the rework cycle start:
```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "implement-rework"}
```

1. Read `cortex/lifecycle/{feature}/review.md` for the reviewer's feedback
2. Identify which tasks were flagged
3. For each flagged task, dispatch a fresh sub-task with:
   - The original task text
   - The reviewer's specific feedback for that task
   - Instruction to fix the identified issues
4. Non-flagged tasks retain their `[x]` status
5. After rework, return to Review

### 4. Transition

When all tasks are `[x]`, determine the next phase using both complexity tier and criticality. Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (emits JSON; defaults to `medium` when the key is absent or events.log is missing).

**Review gating matrix:**

| Criticality | simple | complex |
|-------------|--------|---------|
| low         | Complete | Review |
| medium      | Complete | Review |
| high        | **Review** | Review |
| critical    | **Review** | Review |

High and critical criticality forces Review regardless of complexity tier. Low and medium criticality proceeds to Complete for simple tier, and to Review for complex tier.

Append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log`:
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
