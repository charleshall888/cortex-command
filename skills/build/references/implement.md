# Implement Phase

Dispatch a fresh sub-task per task — a clean context prevents stale assumptions.

### 1. Pre-Flight Check

Read `{roots.artifacts.path}/plan.md`; identify pending tasks (`[ ]`).

**Short road (no plan.md)** — the feature arrived via `spec.approved-direct`, so Plan was skipped by the state machine rather than the artifact going missing. Derive tasks from spec.md's acceptance criteria and implement in-session: no batching, no sub-task dispatch, no batch emissions. Run the branch decision, do the work, exit via §4.

**Branch decision** — one call composes the current-branch check, plan-time `dispatch_choice`, per-repo `branch-mode`, and picker-fire gate:

```bash
cortex-lifecycle-branch-decision --feature {slug}
```

- **`skip`** — not on `main`/`master`; proceed on the current branch to §2.
- **`resolved`** — a mode was fixed without prompting; run the same post-selection routing so every downstream guard still fires. `trunk` → §2. `feature-branch` → create/checkout `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode` (`selected` or `suppressed`), then follow `${CLAUDE_SKILL_DIR}/references/worktree-entry.md` to completion before returning to §2.
<!-- pause: implement-branch-pick config-conditional -->
- **`prompt`** — render the picker via `AskUserQuestion` with the returned guards: on `uncommitted_changes` demote the current-branch option in place (prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`, drop any `(recommended)`); when `worktree_option_available` is false, drop the worktree option.

**Picker options**:

- **Implement on current branch** (recommended) — trunk workflow. Trunk cost: no isolation, so same-file tasks serialize; the plan must carry write-serialization edges.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters via `EnterWorktree`. Record entry mode `selected`, then follow worktree-entry.md to completion before §2.
- **Create feature branch** — creates `feature/{lifecycle-slug}` for a PR flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Dependency graph**: parse `**Depends on**` from every pending task into an adjacency list. A cycle stops the phase — dispatch nothing.

### 2. Task Dispatch

Batch by topological level: **batch 0** is pending tasks with `**Depends on**: none` (or deps already `[x]`); **batch N** is tasks whose deps all sit in earlier batches. Batching keys on full task identity including letter-suffixed sub-tasks; same-batch siblings must have disjoint `Files`.

**a. Extract** each task's full block from plan.md (`### Task N:` to the next task heading).

**b. Dispatch** all batch tasks concurrently, using the builder template below **verbatim** (substitute variables only) plus 2–3 sentences of architectural context from the plan's Overview. Choose each builder's model yourself from the task's `Complexity` and the feature's criticality. Then record the dispatch (idempotent per batch):

```bash
cortex-lifecycle-advance implement-transition --mode batch --feature <name> --batch <N> --tasks '[<task IDs>]'
```

**c. Wait** for every batch task, sending no "send your report" follow-ups — completion derives from the §2d git checkpoint, never from the report's delivery shape.

**d. Checkpoint** — verify each task produced a commit. Worktree dispatch: `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD; zero lines means no commits → mark failed, and **the orchestrator must NOT commit on its behalf**. Sequential: `git log --oneline -N`. Flip `[ ]` → `[x] done (<short-sha> <commit-ts>)` per success, using the verified sha plus `git log -1 --format=%cI <sha>`. Rework re-checkpoints update to the newest verifying sha.

**e. Merge back** — worktree dispatch only, before the next batch so later worktrees branch from an updated HEAD. Per task in order: no changes → already auto-cleaned. Failed commit → skip the merge, then `git worktree remove "$(cortex-worktree-resolve {task-name})"` and `git branch -d worktree/{task-name}`. Passed → `git merge worktree/{task-name}` from the feature branch, then the same cleanup. Conflict → surface as an integration error naming the branch, continue remaining tasks, don't roll back merged branches.

**f. Report** the batch before dispatching the next.

### Failure handling

Let in-flight tasks finish. Checkpoint the successes, identify downstream tasks transitively blocked, and surface which task failed, the error, and what's blocked.

<!-- pause: implement-batch-failure question -->
Then ask the user via `AskUserQuestion`: **retry**, **skip** (mark failed, continue non-dependents), or **abort**.

### Builder brief

Each builder gets the task's full block from plan.md, 2–3 sentences of architectural context from the plan's Overview, and these standing instructions:

- Implement exactly what the task specifies and nothing else.
- Treat the task's file paths as authoritative; flag a wrong-looking one rather than silently deviating.
- Verify per the Verification field and only that, never a broader suite it doesn't name.
- Commit via the Skill tool (`skill: "commit"`), never raw `git commit` or `git -C`.
- Read `{roots.artifacts.path}/spec.md` only if the task references it.
- Flag any self-sealing check in the exit report rather than self-certifying.

Its final message reports task name, status (completed/partial/failed), files modified, verification outcome, commit hash, and deviations.

### 3. Rework (Review Re-Entry)

The review-verdict arm already recorded the rework transition, so this re-entry records nothing. Read `review.md`, dispatch a fresh sub-task per flagged task with the original task text plus the reviewer's feedback and a fix instruction, leave non-flagged tasks `[x]`, return to Review through §4.

### 4. Transition

When all tasks are `[x]` (short road: when every acceptance criterion is met):

```bash
cortex-lifecycle-advance implement-transition --mode transition --feature {feature}
```

The verb reads departure state, tier and criticality through the reducer, applies the routing it owns, and records the transition idempotently. Route on the returned `state` per SKILL.md § Advance-verb routing — **`review`**, **`complete`** or **`rework-review`** → proceed there.

Every commit goes through `/cortex-core:commit` — orchestrator checkpoints and worktree sub-agents included, never raw git.
