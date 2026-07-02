# Implement Phase

Execute the plan by dispatching a fresh implementation sub-task per task. Each sub-task runs with fresh context to prevent stale assumptions.

## Protocol

### 1. Pre-Flight Check

Read `cortex/lifecycle/{feature}/plan.md` and identify pending tasks (those with `[ ]`).

**Consume a plan-time recorded branch choice (primary path)**: The merged Plan §4 approval surface records the operator's branch/dispatch choice on the `plan_approved` event, so the operator is not asked twice. When the current branch is `main`/`master`, before assembling the fallback picker, read any recorded choice:

```bash
cortex-lifecycle-dispatch-choice --feature {slug}
```

Routing on the output (the read is gated on `main`/`master` so it runs in the main-repo CWD — an interactive worktree carries its own events.log):

- A valid branch mode (`trunk` / `worktree-interactive` / `feature-branch`) — **do not render the picker**. Treat the value exactly as if the operator had selected that option in the picker and run the identical post-selection routing (so every guard still runs): `trunk` → remain on the current branch → §2; `worktree-interactive` → **record entry mode `selected`**, run Step A (overnight-active rejection) and Step B (interactive-lock acquisition) below, then §1a; `feature-branch` → create and check out `feature/{lifecycle-slug}`, then §2.
- Empty output, `wait`, or command-not-found (the console-script not yet installed) — no recorded branch mode; **fall through to the fallback picker below**.

**Branch selection**: When the current branch is `main` or `master` AND no branch mode was consumed above (this is the fallback picker — it fires only when no plan-time `dispatch_choice` was recorded), prompt the user via AskUserQuestion with three options:

- **Implement on current branch** (recommended) — trunk workflow; changes land on the current branch. Pick for small, trunk-safe changes.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters it via the `EnterWorktree` tool (continues from inside the worktree). Proceeds to §1a. Pick for multi-task features wanting isolation with live steering.
- **Create feature branch** — create `feature/{lifecycle-slug}` for a PR-based flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Branch-mode dispatch preflight**: Before the uncommitted-changes guard and the runtime probe below, consult the per-repo `branch-mode` config via `cortex-lifecycle-branch-mode`.

Two Bash calls (no compound commands): `read_branch_mode` prints the configured value — empty when unset/malformed, which routes to the picker as `branch_mode_unset_or_invalid` — then the picker-decision verb emits `{"fire": <bool>, "reason": "<closed-set-token>"}` (third positional `{branch_mode}` is step 1's value, omitted when empty):

```bash
cortex-lifecycle-branch-mode .
cortex-lifecycle-picker-decision . {slug} {branch_mode}
```

**Routing on the result.** When `should_fire_picker` returns `(False, "suppressed")`, skip the picker (the uncommitted-changes guard, runtime probe, and `AskUserQuestion` call below) and route by value:

- `worktree-interactive` — **record entry mode `suppressed`** and proceed directly to §1a (Interactive Worktree Creation). The `suppressed` marker is the carried control-flow value §1a step v branches on: it routes structurally to the cd-shim, skipping `EnterWorktree`.
- `trunk` — proceed on the current branch directly to §2 Task Dispatch.
- `feature-branch` — create and check out `feature/{lifecycle-slug}` before dispatching any tasks, then proceed to §2.
- `prompt` — the picker fires: covered by the fall-through rule below.

When `should_fire_picker` returns `(True, reason)` for any reason (`branch_mode_unset_or_invalid`, `branch_mode_prompt`, `dirty_tree`, or `live_interactive_worktree_session`), do **not** short-circuit — fall through to the uncommitted-changes guard, the runtime probe, and the existing `AskUserQuestion` call site below.

**Uncommitted-changes guard**: Immediately before the `AskUserQuestion` call, run `git status --porcelain`. On non-empty output, demote the current-branch option in place (keep it selectable at its existing position): prepend the fixed warning `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` to its description and drop any `(recommended)` suffix from its label. If `git status --porcelain` exits non-zero (missing `.git`, corrupt index, bisect/rebase state), fail open — the guard does not fire; surface the single-line diagnostic `uncommitted-changes guard skipped: git status failed` alongside the prompt and continue.

**Runtime probe**: After the uncommitted-changes guard and before assembling the prompt's options array, run a single Bash call that probes whether the `cortex-worktree-create` console-script is reachable on PATH:

```bash
command -v cortex-worktree-create >/dev/null 2>&1
```

Route by `command -v` exit code:

- **exit 0** (reachable) → keep all three options unchanged.
- **exit 1** (not on PATH) → silently drop `Implement on feature branch with worktree` (no diagnostic), leaving `Implement on current branch` and `Create feature branch`.
- **Bash execution failure or any exit code other than 0/1** → fail open: keep all three options and surface the literal diagnostic `runtime probe skipped: console-script probe failed`.

Pass the resolved options array to `AskUserQuestion`.

Dispatch by selection:
- If the user selects **Implement on feature branch with worktree**, **record entry mode `selected`** and run the two interactive preflight guards below (Steps A and B) before proceeding to §1a. If either guard rejects, exit §1 without creating a worktree.

  **Step A — Overnight-active rejection mirror**: Source the overnight-probe sidecar and surface interactive-tailored wording on exit 1:

  ```
  cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
  ```

  Substitute the body-resolved absolute sidecar path (SKILL.md, Reference-path propagation).

  Sidecar exit codes: `0` = no overnight active, proceed to Step B; `1` = overnight live for this repo, surface the wording above and exit §1 without creating a worktree; `2` = stale runner detected, surface a warn-and-continue diagnostic and proceed to Step B.

  **Step B — Interactive lock acquisition**: Run a single Bash call to acquire the per-feature interactive lock:

  ```
  cortex-interactive-lock acquire {slug}
  ```

  On exit 0: proceed to §1a. On non-zero exit: the console-script has already written R5's rejection wording to stderr — surface stderr verbatim and exit §1 without creating a worktree.

- **Implement on current branch** → proceed to §2 Task Dispatch on the current branch.
- **Create feature branch** → create and check out `feature/{lifecycle-slug}`, then proceed to §2 Task Dispatch.

If the current branch is not `main`/`master` (already on a feature branch or resumed session), skip the prompt and proceed on the current branch.

**Dependency graph analysis**: Parse the `**Depends on**` field from every pending task. Build an adjacency list: for each task, record which tasks it depends on. If a cycle is detected, stop and surface the error to the user — do not dispatch any tasks.

### 1a. Interactive Worktree Creation (Alternate Path)

This section runs in two entry modes: `selected` (user picked the worktree option in §1) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Step v branches on the carried entry-mode marker; either way the orchestrator session does not exit `/cortex-core:lifecycle` — it continues into §2 task dispatch.

**i. Overnight concurrent guard.** Invoke the sidecar at the body-resolved absolute path (SKILL.md, Reference-path propagation):

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```

Sidecar exit codes carry the same `0` = proceed / `1` = reject / `2` = warn-and-continue (stale runner) semantics as §1 Step A; on this path exit `0` proceeds to ii and exit `1` exits §1a.

**ii. Interactive lock (per-feature concurrency guard).** Acquire the real lock via the `cortex-interactive-lock` console script — the single source of truth for `cortex/lifecycle/{slug}/interactive.pid` — conditioned on the carried entry mode, and only **after** the overnight guard (i) has passed, so a rejecting overnight guard can never orphan a held lock:

- Entry mode `selected`: §1 Step B already acquired the lock for `{slug}` this session — do **not** acquire again (a second same-session acquire self-rejects on the session-id-match row). Proceed to iii.
- Entry mode `suppressed`: run a single Bash call `cortex-interactive-lock acquire {slug}`. Exit 0 → proceed to iii. Non-zero → the script has written its rejection to stderr (a live same-slug interactive session already holds the lock); surface that stderr verbatim and exit §1a without creating a worktree.

**iii. Worktree creation.** Single Bash call invoking `cortex-worktree-create`:

```bash
worktree_path=$(cortex-worktree-create --feature interactive-{slug} --base-branch main)
```

`create_worktree` resolves the branch as `interactive/{slug}` and materializes the worktree at `<repo>/.claude/worktrees/interactive-{slug}/`. The wrapper copies `.claude/settings.local.json` and symlinks `.venv`. Stdout = absolute worktree path; stderr = informational.

If creation fails: the wrapper writes `repr(exc)` to stderr and exits 1. Surface the stderr output to the user and exit §1a — do not proceed to handoff.

The inside-repo containment check is no longer a separate pre-flight step here: `cortex-worktree-create` (step iii) now performs it inside `create_worktree` and exits 1 with a `worktree_escapes_repo` message if the resolved worktree path escapes the repo root, so a successful step-iii create already guarantees containment.

**Step v — Auto-enter sequence**

After worktree creation succeeds (step iii), run operations in this order — the event must be emitted from inside the worktree so `_resolve_user_project_root_from_cwd()` lands the row in the worktree's events.log, not the main repo's.

1. **Capture origin pwd** — run a single Bash call: `_origin_pwd=$(pwd)`. Hold this value for the lifecycle session (it may be needed for restore at Complete phase or on fallback below).

2. **Suppressed-picker structural branch** — when the carried entry mode is `suppressed`, skip the `cortex-worktree-precondition` probe AND the auto-enter call entirely and route structurally to the cd-shim: run `cd $(cortex-worktree-resolve interactive-{slug})` to root the session in the already-created worktree, surface the stable literal diagnostic `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, then jump to operation 5 (emit event) (no EnterWorktree authorization — ADR-0008). When the carried entry mode is `selected`, do not take this branch — continue to operation 3.

3. **Already-in-worktree probe** (entry mode `selected`) — run a single Bash call: `cortex-worktree-precondition`. Exit 0 means the current session is NOT already inside a worktree (proceed); exit 1 means the session IS already inside a worktree (skip operation 4 and route to the fallback path with a single-line diagnostic naming the detected worktree).

4. **Auto-enter the worktree** (entry mode `selected`) — when the probe above returned exit 0, call the platform tool:

   ```
   EnterWorktree(path=<resolved-path>)
   ```

   where `<resolved-path>` is the value returned by `cortex-worktree-resolve interactive-{slug}` (never a hardcoded prefix per R3). This sets the orchestrator session's CWD to the interactive worktree for all subsequent Bash tool calls in this lifecycle session and clears CWD-dependent caches (system prompt sections, memory files, plans directory). If the tool errors (path not in `git worktree list`, schema rejection, or a "Must not already be in a worktree" race), route to the fallback path below.

5. **Emit event** — run a single Bash call once the session CWD is rooted in the worktree (via `EnterWorktree` on the `selected` path, or the cd-shim on the `suppressed` path):

   ```bash
   cortex-lifecycle-event log --event interactive_worktree_entered --feature {slug} --set worktree_path="$(pwd)"
   ```

   The `cortex-lifecycle-event` CLI uses `_resolve_user_project_root_from_cwd()` (ignores `CORTEX_REPO_ROOT`), so the event row lands in the worktree's `cortex/lifecycle/{slug}/events.log` — not the main repo's.

**Fallback — `EnterWorktree skipped`.** On the `selected` path, if the `cortex-worktree-precondition` probe in operation 3 returns non-zero, OR the `EnterWorktree` call in operation 4 errors, OR the skill judges the gate unmet and declines to invoke the tool (silent non-invocation), fall back to the cd-shim handoff: run `cd $(cortex-worktree-resolve interactive-{slug})` and proceed to operation 5 to emit the event. Surface a single-line diagnostic beginning with the stable literal `EnterWorktree skipped` and naming the failure mode (e.g., `EnterWorktree skipped: already inside worktree at <path>`, `EnterWorktree skipped: tool rejected path <path>`).

The auto-enter affects only orchestrator-session Bash tool calls; sub-agent `Agent(isolation: "worktree")` dispatch in §2 is unaffected, and §2(e) merge-back applies unchanged.

**vi. Interactive worktree auto-entry.** On entry mode `suppressed` the operation-2 cd-shim roots the session without `EnterWorktree`'s cache-clear (and without its session-exit keep/remove prompt) — `cd $(git rev-parse --show-toplevel)` is the only restoration step needed on that path. Surface the worktree path to the user along with a single-line warning that on session exit the harness will prompt to **keep or remove** the worktree — selecting "remove" discards any uncommitted work, so commit or push before exiting. Mid-session restoration: run `ExitWorktree action="keep"` to clear session state cleanly (dismisses the exit prompt), or `cd $(git rev-parse --show-toplevel)` to navigate back while deferring the prompt. See ADR-0004 for the design rationale.

**vii. Continue to §2 Task Dispatch.** Do not exit `/cortex-core:lifecycle`. The orchestrator session is now inside the interactive worktree and proceeds to dispatch implementation tasks from §2 onward.

### 2. Task Dispatch

Compute batches from the dependency graph using topological level grouping:
- **Batch 0**: All pending tasks with `**Depends on**: none` (or whose dependencies are already `[x]`).
- **Batch 1**: Tasks whose dependencies are all in batch 0.
- **Batch N**: Tasks whose dependencies are all in batches 0 through N-1.

Batching keys on each task's full identity, including letter-suffixed sub-task headings (`### Task 3a:`, `### Task 3b:`) which are first-class units (see plan.md's "Sub-task headings" section). **Sub-task siblings that co-schedule in the same batch must have disjoint `Files`** — the rationale and the serialize-via-`Depends on` workaround live in that canonical "Sub-task headings" section.

For each batch, in order:

**a. Extract task texts**: For every task in the batch, copy its full task block from plan.md (everything between `### Task N:` and the next task heading).

**b. Dispatch batch**: Launch all tasks in the batch concurrently as parallel sub-tasks. Use the builder prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions. Provide the full task text plus 2-3 sentences of architectural context from the plan's Overview section.

**Model**: resolve the builder sub-task model at dispatch by running the verb against the feature criticality — never hardcode a model literal:

```bash
model=$(cortex-resolve-model --role builder --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Pass the captured `$model` as each builder sub-task's model. On nonzero exit from `cortex-resolve-model` — the verb rejected the input or the `cortex-lifecycle-state` read returned corrupt/absent criticality — halt and escalate rather than guessing or substituting a model.

After launching, append a `batch_dispatch` event to `cortex/lifecycle/{feature}/events.log`:
```bash
cortex-lifecycle-event log --event batch_dispatch --feature <name> --set-json batch=<N> --set-json tasks=[<task IDs in this batch>]
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
4. **Cleanup**: After a successful merge, run `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`.
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
```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set from=review --set to=implement-rework
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

When all tasks are `[x]`, determine the next phase using both complexity tier and criticality. Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (rules: criticality-matrix.md §Reading lifecycle state).

**Review gating matrix:**

| Criticality | simple | complex |
|-------------|--------|---------|
| low         | Complete | Review |
| medium      | Complete | Review |
| high        | **Review** | Review |
| critical    | **Review** | Review |

Append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log`:
```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set tier=<simple|complex> --set from=implement --set to=<review|complete>
```
The `"to"` field is determined by the gating matrix above.

**Proceed automatically** — do not ask the user for confirmation before entering the next phase. The transition fires on the gate conditions (every task `[x]`, then the criticality matrix above), not on user input. Announce the transition briefly as plain text and continue. The Implement → Review/Complete boundary is not in the Kept user pauses inventory; see SKILL.md §Phase Transition for the umbrella reasoning.

## Constraints

- Batch ordering respects dependencies. Tasks in batch N+1 must wait for batch N to complete.
- Always use `/cortex-core:commit` for all commits — orchestrator checkpoints included. Never use raw git commands for staging or committing. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty about this is not a reason to bypass it.
