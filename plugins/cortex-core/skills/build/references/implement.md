# Implement Phase

A fresh sub-task per task — clean context prevents stale assumptions.

### 1. Pre-flight

Read `{roots.artifacts.path}/plan.md`; identify pending tasks (`[ ]`).

**Short road (no plan.md)** — the feature arrived via `spec.approved-direct`, so Plan was skipped by design. Derive tasks from spec.md's acceptance criteria and implement in-session: no batching, no sub-task dispatch, no batch emissions. Run the branch decision, do the work, exit via §4.

**Branch decision** — one call composes the current-branch check, plan-time `dispatch_choice`, per-repo `branch-mode`, and the picker gate:

```bash
cortex-lifecycle-branch-decision --feature {slug}
```

- `skip` — not on `main`/`master`; continue on the current branch to §2.
- `resolved` — a mode was fixed without prompting; run the same post-selection routing so every downstream guard fires. `trunk` → §2. `feature-branch` → create/checkout `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode` (`selected` or `suppressed`), follow `${CLAUDE_SKILL_DIR}/references/worktree-entry.md` to completion, then §2.
<!-- pause: implement-branch-pick config-conditional -->
- `prompt` — render the picker with the returned guards: on `uncommitted_changes` demote the current-branch option in place (prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`, drop `(recommended)`); when `worktree_option_available` is false, drop the worktree option.

**Picker**: **Implement on current branch** (recommended; same-file tasks serialize, so the plan must carry write-serialization edges) · **Implement on feature branch with worktree** (creates `interactive/{slug}` at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters; record `selected`, follow worktree-entry.md before §2) · **Create feature branch** (`feature/{lifecycle-slug}` for a PR flow; runs `git checkout` on the main session and can corrupt parallel sessions).

**Dependency graph** — parse `**Depends on**` from every pending task. A cycle stops the phase; dispatch nothing.

### 2. Task dispatch

Batch by topological level: **batch 0** = pending tasks with `**Depends on**: none` (or deps already `[x]`); **batch N** = tasks whose deps sit in earlier batches. Batching keys on full task identity including letter-suffixed sub-tasks; same-batch siblings must have disjoint `Files`.

**a. Extract** each task's full block (`### Task N:` to the next task heading).

**b. Dispatch** all batch tasks concurrently with the builder brief below **verbatim** plus 2–3 sentences of architectural context from the plan's Overview; choose each builder's model from the task's `Complexity` and the feature's criticality. Record the dispatch (idempotent per batch):

```bash
cortex-lifecycle-advance implement-transition --mode batch --feature <name> --batch <N> --tasks '[<task IDs>]'
```

**c. Wait** for every task, sending no "send your report" follow-ups — completion derives from the git checkpoint, not the report.

**d. Checkpoint** — verify each task produced a commit. Worktree dispatch: `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD; zero lines → mark failed, and **never commit on its behalf**. Sequential: `git log --oneline -N`. Flip `[ ]` → `[x] done (<short-sha> <commit-ts>)` per success (`git log -1 --format=%cI <sha>`); rework re-checkpoints update to the newest sha.

**e. Merge back** — worktree dispatch only, before the next batch so later worktrees branch from an updated HEAD. Per task: no changes → already auto-cleaned. Failed → skip the merge, then `git worktree remove "$(cortex-worktree-resolve {task-name})"` and `git branch -d worktree/{task-name}`. Passed → `git merge worktree/{task-name}` from the feature branch, then the same cleanup. Conflict → surface as an integration error naming the branch; continue the rest, don't roll back merged branches.

**f. Report** the batch before dispatching the next.

### Failure handling

Let in-flight tasks finish. Checkpoint the successes, identify transitively blocked tasks, surface which task failed, the error, and what's blocked.

<!-- pause: implement-batch-failure question -->
Then ask: **retry**, **skip** (mark failed, continue non-dependents), or **abort**.

### Builder brief

The task's full block, 2–3 sentences of Overview context, and these standing instructions:

- Implement exactly what the task specifies and nothing else.
- The task's file paths are authoritative; flag a wrong-looking one rather than silently deviating.
- Verify per the Verification field only, never a broader suite it doesn't name.
- Commit via the Skill tool (`skill: "commit"`), never raw `git commit` or `git -C`.
- Read `{roots.artifacts.path}/spec.md` only if the task references it.
- Flag any self-sealing check in the exit report rather than self-certifying.

Final message: task name, status (completed/partial/failed), files modified, verification outcome, commit hash, deviations.

### 3. Rework (review re-entry)

The review-verdict arm already recorded the rework transition; record nothing here. Read `review.md`, dispatch a fresh sub-task per flagged task with the original task text plus the reviewer's feedback and a fix instruction, leave non-flagged tasks `[x]`, return to Review through §4.

### 4. Transition

When all tasks are `[x]` (short road: every acceptance criterion met):

```bash
cortex-lifecycle-advance implement-transition --mode transition --feature {feature}
```

The verb reads departure state, tier, and criticality, applies the routing it owns, and records idempotently. Route per SKILL.md § Advance-verb routing — `review`, `complete`, or `rework-review` → proceed there.

Every commit — orchestrator checkpoints and worktree sub-agents included — uses `git commit --only -- <staged paths>`, never a bare `git commit`.
