# Implement Phase

Dispatch a fresh sub-task per task — a clean context prevents stale assumptions.

## Protocol

### 1. Pre-Flight Check

Read `cortex/lifecycle/{feature}/plan.md`; identify pending tasks (`[ ]`).

**Branch decision** — one read-only call composes the current-branch check, plan-time `dispatch_choice`, per-repo `branch-mode`, and picker-fire gate:

```bash
cortex-lifecycle-branch-decision --feature {slug}
```

Act on `state`:

- **`skip`** — not on `main`/`master`; proceed on the current branch to §2.
- **`resolved`** — a branch mode was fixed without prompting; run the same post-selection routing so every downstream guard runs. `trunk` → §2 on the current branch. `feature-branch` → create/checkout `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode`; `selected` runs Step A then §1a, `suppressed` goes straight to §1a (its own overnight guard runs there, step v routes to the cd-shim).
- **`prompt`** — render the picker below via `AskUserQuestion`, applying the returned guards: on `uncommitted_changes`, demote the current-branch option in place (prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`, drop any `(recommended)`); when `worktree_option_available` is false, drop the worktree option. On selection — **current branch** → §2; **feature branch** → create/checkout `feature/{lifecycle-slug}` → §2; **worktree** → record entry mode `selected`, run Step A, then §1a (a Step A rejection exits §1 without creating a worktree).

**Picker options**:

- **Implement on current branch** (recommended) — trunk workflow; changes land on the current branch.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters via `EnterWorktree`. Proceeds to §1a.
- **Create feature branch** — create `feature/{lifecycle-slug}` for a PR flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Step A — Overnight-active rejection**: source the overnight-probe sidecar; on exit 1 surface interactive-tailored wording:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
```

Exit codes: `0` = none active, proceed to §1a; `1` = overnight live, surface the wording and exit §1 without creating a worktree; `2` = stale runner, warn-and-continue to §1a.

**Dependency graph**: parse `**Depends on**` from every pending task into an adjacency list; a cycle stops the phase — dispatch nothing.

### 1a. Interactive Worktree Creation (Alternate Path)

Two entry modes: `selected` (user picked the worktree option) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Step v branches on the carried marker; either way the orchestrator session continues into §2.

**i. Prepare** — one call composes the overnight guard, `cortex-interactive-lock acquire`, and `create_worktree`, running unconditionally for both entry modes:

```bash
cortex-lifecycle-prepare-worktree --feature {slug}
```

Act on `state`:

- **`overnight-active`** — surface `message` verbatim and exit §1a without creating a worktree.
- **`lock-held`** — a live same-slug session holds the lock; surface `message` verbatim and exit §1a without creating a worktree.
- **`create-failed`** — surface `message` (`repr(exc)`) and exit §1a; the verb already released the lock if this session owned it.
- **`ok`** — `worktree_path` is set; relay any `warning` (a stale runner.pid) as a one-line diagnostic, then continue to Step v.

**Step v — Auto-enter sequence** (steps ii–iv were absorbed into `cortex-lifecycle-prepare-worktree`; the i→v gap is intentional — do not renumber, tests and cross-refs anchor on these labels)

After `state: ok`, run in this order — the event must be emitted from inside the worktree so `_resolve_user_project_root_from_cwd()` lands the row in the worktree's events.log:

1. **Capture origin pwd** — `_origin_pwd=$(pwd)`; hold it for the session (restore at Complete or on fallback).
2. **Suppressed-picker structural branch** — `suppressed` skips the `cortex-worktree-precondition` probe AND the auto-enter, routing structurally to the cd-shim: `cd $(cortex-worktree-resolve interactive-{slug})`, surfacing the stable literal `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, then jumping to op 5. `selected` skips this branch and continues to op 3.
3. **Already-in-worktree probe** (`selected`) — `cortex-worktree-precondition`. Exit 0 = not inside a worktree (proceed); exit 1 = already inside (skip op 4, route to fallback naming the detected worktree).
4. **Auto-enter** (`selected`, probe returned 0) — `EnterWorktree(path=<resolved-path>)` where `<resolved-path>` is `cortex-worktree-resolve interactive-{slug}`'s output (never a hardcoded prefix — R3). Sets session CWD to the worktree for all subsequent Bash calls and clears CWD-dependent caches. Error (path not in `git worktree list`, schema rejection, "Must not already be in a worktree" race) → fallback.
5. **Emit event** — once CWD is rooted in the worktree (via `EnterWorktree` on `selected`, or the cd-shim on `suppressed`):

   ```bash
   cortex-lifecycle-event interactive-worktree-entered --feature {slug} --worktree-path "$(pwd)"
   ```

**Fallback — `EnterWorktree skipped`.** On the `selected` path (op-3 probe non-zero, op-4 `EnterWorktree` error, or the skill declines the tool): cd-shim handoff `cd $(cortex-worktree-resolve interactive-{slug})` then op 5, with a one-line diagnostic beginning `EnterWorktree skipped` naming the failure mode. Auto-enter affects only orchestrator-session Bash calls; §2 sub-agent `Agent(isolation: "worktree")` dispatch and §2(e) merge-back are unaffected.

**vi.** On `suppressed`, `cd $(git rev-parse --show-toplevel)` is the only restoration needed. Surface the worktree path with a one-line warning: on session exit the harness prompts to keep/remove — "remove" discards uncommitted work, so commit or push first. Mid-session, `ExitWorktree action="keep"` clears state cleanly, or `cd $(git rev-parse --show-toplevel)` navigates back deferring the prompt.

**vii.** Do not exit `/cortex-core:lifecycle` — the session is inside the worktree; proceed to §2.

### 2. Task Dispatch

Compute batches by topological level:
- **Batch 0**: pending tasks with `**Depends on**: none` (or deps already `[x]`).
- **Batch N**: tasks whose deps are all in batches 0..N-1.

Batching keys on full task identity, including letter-suffixed sub-tasks (`### Task 3a:`) — first-class units (see plan.md "Sub-task headings"). **Same-batch sub-task siblings must have disjoint `Files`** — rationale and the serialize-via-`Depends on` workaround live in that section.

Per batch, in order:

**a. Extract task texts** — copy each task's full block from plan.md (`### Task N:` to the next task heading).

**b. Dispatch** — launch all batch tasks concurrently as parallel sub-tasks. Use the builder template below **verbatim** per task (substitute variables only), adding 2-3 sentences of architectural context from the plan's Overview.

**Model** — resolve at dispatch, never hardcode:

```bash
model=$(cortex-resolve-model --role builder --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Pass `$model` to each builder. On nonzero exit, halt and escalate rather than guessing. Then log the dispatch:

```bash
cortex-lifecycle-event batch-dispatch --feature <name> --batch <N> --tasks '[<task IDs>]'
```

**c. Wait** — all batch tasks finish before proceeding.

**d. Checkpoint** — verify each task produced a commit:
- **Worktree dispatch**: `git log HEAD..worktree/{task-name} --oneline` from the main repo CWD (`{task-name}` = the `name` passed to `Agent(isolation: "worktree")`). Zero lines → the sub-agent made no commits → mark failed. The orchestrator must NOT commit on the sub-agent's behalf.
- **Sequential dispatch**: `git log --oneline -N` (N = batch task count) to confirm commits.

Then flip `[ ]` → `[x]` for every task that succeeded.

**e. Worktree Integration** — skip entirely for sequential dispatch. For worktree dispatch, follow the five-case merge-back at `${CLAUDE_SKILL_DIR}/references/merge-back.md`.

**f. Report** — summarize the batch before dispatching the next.

### Failure Handling

When a batch task fails:
1. Let other in-flight batch tasks finish — do not abort them.
2. Checkpoint successful tasks as `[x]`.
3. Identify downstream tasks transitively depending on the failed one — these are blocked.
4. Surface which task failed, the error, and which downstream tasks are now blocked.
5. Ask the user: **retry**, **skip** (mark failed, continue non-dependents), or **abort**.

### Builder Prompt Template

```
You are implementing a single task for the {feature} feature.

## Task
{full task text from plan.md}

## Architectural Context
{2-3 sentences from plan Overview section}

## Instructions
1. Implement exactly what the task specifies.
2. File paths must match the spec exactly — flag a wrong-looking path rather than silently deviating.
3. Verify your implementation per the Verification field.
4. Commit via the Skill tool (`skill: "commit"`) — never raw `git commit` or `git -C`.
5. Report per task: name, status (completed/partial/failed), files modified, verification outcome, deviations.
6. Do not create files solely to satisfy your own verification — flag self-sealing checks (an artifact this task created being used to verify itself) in your exit report rather than self-certifying.

If this task references the specification, read cortex/lifecycle/{feature}/spec.md. Do not implement other tasks, modify unlisted files, or add unspecified features.
```

### 3. Rework (Review Re-Entry)

Re-entering from Review with CHANGES_REQUESTED — log the rework start: `cortex-lifecycle-event phase-transition --feature <name> --from review --to implement-rework`

1. Read `cortex/lifecycle/{feature}/review.md` for the reviewer's feedback.
2. For each flagged task, dispatch a fresh sub-task with the original task text + the reviewer's specific feedback + a fix instruction.
3. Non-flagged tasks keep their `[x]`.
4. Return to Review.

### 4. Transition

When all tasks are `[x]`, the next phase follows both tier and criticality (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state):

```bash
cortex-lifecycle-state --feature {feature} --field criticality
```

Next phase is **Review** when `criticality ∈ {high, critical}` OR `tier = complex`, else **Complete**.

```bash
cortex-lifecycle-event phase-transition --feature <name> --from implement --to <review|complete> --tier <simple|complex>
```

**Proceed automatically** — no confirmation. The transition fires on the gate (every task `[x]`, then the review rule), not user input. Announce briefly and continue. This boundary is not a kept pause; see SKILL.md §Phase Transition.

## Constraints

- Batch N+1 waits for batch N.
- Always commit via `/cortex-core:commit` — orchestrator checkpoints and worktree sub-agents included; never raw git.
