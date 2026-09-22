# Implement Phase

Give each task a fresh sub-agent, so no stale assumptions carry over.

### 1. Pre-flight

Read `{roots.artifacts.path}/plan.md` and find the pending tasks (`[ ]`).

**Short road (no plan.md)** — the feature arrived via `spec.approved-direct`, so Plan was skipped on purpose. Derive tasks from spec.md's acceptance criteria and do them in this session: no batches, no sub-agents, no batch events. Run the branch decision, do the work, exit via §4.

**Branch decision.** If you came from plan §4's `branch-mode-approved` in this session, skip the call: treat that `dispatch_choice` as a `resolved` state below, with `entry_mode` `selected`. Otherwise one call checks the current branch, the plan-time `dispatch_choice`, the per-repo `branch-mode`, and whether to show the picker:

```bash
cortex-lifecycle-branch-decision --feature {slug}
```

- `skip` — not on `main`/`master`; continue on the current branch to §2.
- `resolved` — a mode was set without asking. Route as if the user had picked it, so every later guard still runs. `trunk` → §2. `feature-branch` → create/checkout `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode` (`selected` or `suppressed`), follow `${CLAUDE_SKILL_DIR}/references/worktree-entry.md` to completion, then §2.
<!-- pause: implement-branch-pick config-conditional -->
- `prompt` — show the picker, applying the returned guards. On `uncommitted_changes`, keep the current-branch option in place but prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` and drop `(recommended)`. When `worktree_option_available` is false, drop the worktree option.

**Picker**:

- **Implement on current branch** (recommended) — same-file tasks run one after another, so the plan must carry write-serialization edges.
- **Implement on feature branch with worktree** — creates `interactive/{slug}` at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters. Record `selected` and follow worktree-entry.md before §2.
- **Create feature branch** — `feature/{lifecycle-slug}` for a PR flow. Runs `git checkout` on the main session and can corrupt parallel sessions.

**Dependency graph** — parse `**Depends on**` from every pending task. A cycle stops the phase; start nothing.

### 2. Task dispatch

Batch by dependency level: **batch 0** = pending tasks with `**Depends on**: none` (or deps already `[x]`); **batch N** = tasks whose deps sit in earlier batches. Use the full task ID, letter suffix included. Tasks in one batch must have separate `Files`.

**a. Extract** each task's full block (`### Task N:` to the next task heading).

**b. Dispatch** all batch tasks at once. Give each the builder brief below word for word, plus 2–3 sentences of architectural context from the plan's Overview. Choose each builder's model from the task's `Complexity` and the feature's criticality. Record the dispatch (safe to repeat per batch):

```bash
cortex-lifecycle-advance implement-transition --mode batch --feature <name> --batch <N> --tasks '[<task IDs>]'
```

**c. Wait** for every task. Send no "send your report" follow-ups — the git checkpoint shows completion, not the report.

**d. Checkpoint** — verify each task produced a commit. Worktree dispatch: `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD; zero lines → mark failed, and **never commit on its behalf**. Sequential: `git log --oneline -N`. Flip `[ ]` → `[x] done (<short-sha> <commit-ts>)` per success (`git log -1 --format=%cI <sha>`); after rework, update to the newest sha.

**e. Merge back** — worktree dispatch only, before the next batch so later worktrees branch from an updated HEAD. Per task:

- No changes → already auto-cleaned.
- Failed → skip the merge, then `git worktree remove "$(cortex-worktree-resolve {task-name})"` and `git branch -d worktree/{task-name}`.
- Passed → `git merge worktree/{task-name}` from the feature branch, then the same cleanup.
- Conflict → report an integration error naming the branch; continue the rest, don't roll back merged branches.

**f. Report** the batch before starting the next.

### Failure handling

Let in-flight tasks finish. Checkpoint the successes. Find every task that depends on the failure, directly or not. Report which task failed, the error, and what's blocked.

<!-- pause: implement-batch-failure question -->
Then ask: **retry**, **skip** (mark failed, continue non-dependents), or **abort**.

### Builder brief

The task's full block, 2–3 sentences of Overview context, and these standing instructions:

- Implement exactly what the task specifies and nothing else.
- Use the task's file paths as given; flag one that looks wrong rather than quietly changing it.
- Verify per the Verification field only, never a broader suite it doesn't name.
- Commit via the Skill tool (`skill: "commit"`), never raw `git commit` or `git -C`.
- Read `{roots.artifacts.path}/spec.md` only if the task references it.
- If a check can only pass, say so in the final message rather than counting it as verified.

Final message: task name, status (completed/partial/failed), files modified, verification outcome, commit hash, deviations.

### 3. Rework (review re-entry)

The review verdict already recorded the rework transition; record nothing here. Read `review.md`. For each flagged task, start a fresh sub-agent with the original task text, the reviewer's feedback, and an instruction to fix. Leave other tasks `[x]`. Return to Review through §4.

### 4. Transition

When all tasks are `[x]` (short road: every acceptance criterion met):

```bash
cortex-lifecycle-advance implement-transition --mode transition --feature {feature}
```

The verb picks the next phase from the current state, tier, and criticality, and is safe to run again. Route per SKILL.md § Advance-verb routing — `review`, `complete`, or `rework-review` → go there.

Every commit — your checkpoints and worktree sub-agents included — uses `git commit --only -- <staged paths>`, never a bare `git commit`.
