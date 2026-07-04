# Implement Phase

Execute the plan by dispatching a fresh implementation sub-task per task. Each sub-task runs with fresh context to prevent stale assumptions.

## Protocol

### 1. Pre-Flight Check

Read `cortex/lifecycle/{feature}/plan.md` and identify pending tasks (those with `[ ]`).

**Branch decision**: resolve how to dispatch with one read-only call — it composes the current-branch check, the plan-time `dispatch_choice`, the per-repo `branch-mode` config, and the picker-fire gate:

```bash
cortex-lifecycle-branch-decision --feature {slug}
```

Act on `state`:

- **`skip`** — not on `main`/`master`; proceed on the current branch to §2.
- **`resolved`** — a branch mode was determined without prompting; run the identical post-selection routing so every downstream guard still runs. `trunk` → §2 on the current branch. `feature-branch` → create and check out `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode`; on `selected` run Step A below then §1a, on `suppressed` go straight to §1a (its own overnight guard runs there, and step v routes structurally to the cd-shim).
- **`prompt`** — render the picker below via `AskUserQuestion`, applying the returned guards: when `uncommitted_changes`, demote the current-branch option in place (prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`, drop any `(recommended)` suffix); when `worktree_option_available` is false, drop the worktree option. On selection — **current branch** → §2; **feature branch** → create/checkout `feature/{lifecycle-slug}` → §2; **worktree** → record entry mode `selected`, run Step A, then §1a (a Step A rejection exits §1 without creating a worktree).

**Picker options**:

- **Implement on current branch** (recommended) — trunk workflow; changes land on the current branch. Pick for small, trunk-safe changes.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters it via the `EnterWorktree` tool. Proceeds to §1a. Pick for multi-task features wanting isolation with live steering.
- **Create feature branch** — create `feature/{lifecycle-slug}` for a PR-based flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Step A — Overnight-active rejection**: Source the overnight-probe sidecar and surface interactive-tailored wording on exit 1:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
```

Sidecar exit codes: `0` = no overnight active, proceed to §1a; `1` = overnight live for this repo, surface the wording above and exit §1 without creating a worktree; `2` = stale runner detected, surface a warn-and-continue diagnostic and proceed to §1a.

**Dependency graph analysis**: Parse the `**Depends on**` field from every pending task. Build an adjacency list: for each task, record which tasks it depends on. If a cycle is detected, stop and surface the error to the user — do not dispatch any tasks.

### 1a. Interactive Worktree Creation (Alternate Path)

This section runs in two entry modes: `selected` (user picked the worktree option in §1) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Step v branches on the carried entry-mode marker; either way the orchestrator session does not exit `/cortex-core:lifecycle` — it continues into §2 task dispatch.

**i. Overnight concurrent guard.** Invoke the sidecar:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```

Sidecar exit codes carry the same `0` = proceed / `1` = reject / `2` = warn-and-continue (stale runner) semantics as §1 Step A; on this path exit `0` proceeds to ii and exit `1` exits §1a.

**ii. Interactive lock (per-feature concurrency guard).** Acquire the real lock via the `cortex-interactive-lock` console script — the single source of truth for `cortex/lifecycle/{slug}/interactive.pid` — **unconditionally for both entry modes**, and only **after** the overnight guard (i) has passed, so a rejecting overnight guard can never orphan a held lock. Run a single Bash call:

```bash
cortex-interactive-lock acquire {slug}
```

Exit 0 → proceed to iii. Non-zero → the script has written its rejection to stderr (a live same-slug interactive session already holds the lock); surface that stderr verbatim and exit §1a without creating a worktree.

**iii. Worktree creation.** Single Bash call invoking `cortex-worktree-create`:

```bash
worktree_path=$(cortex-worktree-create --feature interactive-{slug} --base-branch main)
```

`create_worktree` resolves the branch as `interactive/{slug}`, materializes the worktree at `<repo>/.claude/worktrees/interactive-{slug}/` (containment enforced inside — a path escaping the repo root exits 1 with `worktree_escapes_repo`), and prints the absolute worktree path on stdout. On failure it writes `repr(exc)` to stderr and exits 1 — before exiting §1a, run `cortex-interactive-lock release-if-owner {slug}` to release the lock acquired at step ii so a failed create never orphans it. The `release-if-owner` variant only unlinks when this session's `CLAUDE_CODE_SESSION_ID` owns the on-disk lock, so it can never delete a co-passer's live lock (acquire is non-atomic). Then surface the stderr and exit §1a.

**Step v — Auto-enter sequence**

After worktree creation succeeds (step iii), run operations in this order — the event must be emitted from inside the worktree so `_resolve_user_project_root_from_cwd()` lands the row in the worktree's events.log, not the main repo's.

1. **Capture origin pwd** — `_origin_pwd=$(pwd)` (single Bash call); hold it for the session (needed for restore at Complete or on fallback).

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

   (`cortex-lifecycle-event` uses `_resolve_user_project_root_from_cwd()`, ignoring `CORTEX_REPO_ROOT`, so the row lands in the worktree's events.log.)

**Fallback — `EnterWorktree skipped`.** On the `selected` path, if the `cortex-worktree-precondition` probe in operation 3 returns non-zero, OR the `EnterWorktree` call in operation 4 errors, OR the skill judges the gate unmet and declines to invoke the tool (silent non-invocation), fall back to the cd-shim handoff: run `cd $(cortex-worktree-resolve interactive-{slug})` and proceed to operation 5 to emit the event. Surface a single-line diagnostic beginning with the stable literal `EnterWorktree skipped` and naming the failure mode (e.g., `EnterWorktree skipped: already inside worktree at <path>`, `EnterWorktree skipped: tool rejected path <path>`).

The auto-enter affects only orchestrator-session Bash tool calls; sub-agent `Agent(isolation: "worktree")` dispatch in §2 is unaffected, and §2(e) merge-back applies unchanged.

**vi. Interactive worktree auto-entry.** On entry mode `suppressed`, `cd $(git rev-parse --show-toplevel)` is the only restoration step needed. Surface the worktree path with a single-line warning: on session exit the harness prompts to **keep or remove** the worktree — "remove" discards any uncommitted work, so commit or push before exiting. Mid-session, `ExitWorktree action="keep"` clears session state cleanly, or `cd $(git rev-parse --show-toplevel)` navigates back while deferring the prompt. See ADR-0004.

**vii. Continue to §2 Task Dispatch.** Do not exit `/cortex-core:lifecycle` — the session is now inside the interactive worktree; proceed to dispatch tasks from §2 onward.

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

**e. Worktree Integration**: Skip this step entirely for sequential (non-worktree) dispatch. For worktree dispatch, read and follow the five-case merge-back procedure at `${CLAUDE_SKILL_DIR}/references/merge-back.md`.

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
2. File paths and artifact locations must match the spec exactly; if a spec path looks wrong, flag it rather than silently deviating
3. Verify your implementation works as described in the Verification field
4. Commit your work using the Skill tool: `skill: "commit"`. You have full tool access including the Skill tool — do not use raw `git commit` or `git -C` commands.
5. Report, per task: name, status (completed/partial/failed), files modified, verification outcome, and any issues or deviations from the spec.
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

When all tasks are `[x]`, determine the next phase using both complexity tier and criticality. Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state).

The next phase is **Review** when `criticality ∈ {high, critical}` OR `tier = complex`, else **Complete**. This mirrors `cortex_command/common.py:requires_review` — do not re-derive the cells.

Append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log`:
```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set tier=<simple|complex> --set from=implement --set to=<review|complete>
```
The `"to"` field follows the review rule above.

**Proceed automatically** — do not ask the user for confirmation before entering the next phase. The transition fires on the gate conditions (every task `[x]`, then the review rule above), not on user input. Announce the transition briefly as plain text and continue. The Implement → Review/Complete boundary is not in the Kept user pauses inventory; see SKILL.md §Phase Transition for the umbrella reasoning.

## Constraints

- Batch ordering respects dependencies. Tasks in batch N+1 must wait for batch N to complete.
- Always use `/cortex-core:commit` for all commits — orchestrator checkpoints included. Never use raw git commands for staging or committing. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty about this is not a reason to bypass it.
