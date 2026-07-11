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
- **`resolved`** — a branch mode was fixed without prompting; run the same post-selection routing so every downstream guard runs. `trunk` → §2 on the current branch. `feature-branch` → create/checkout `feature/{lifecycle-slug}`, then §2. `worktree-interactive` → record the returned `entry_mode` (`selected` or `suppressed`), then read `${CLAUDE_SKILL_DIR}/references/worktree-entry.md` and follow it to completion before returning to §2.
<!-- pause: implement-branch-pick config-conditional -->
- **`prompt`** — render the picker below via `AskUserQuestion`, applying the returned guards: on `uncommitted_changes`, demote the current-branch option in place (prepend `Warning: uncommitted changes in working tree — this will mix them into the commit on main.`, drop any `(recommended)`); when `worktree_option_available` is false, drop the worktree option. On selection — **current branch** → §2; **feature branch** → create/checkout `feature/{lifecycle-slug}` → §2; **worktree** → record entry mode `selected`, then read `${CLAUDE_SKILL_DIR}/references/worktree-entry.md` and follow it to completion before returning to §2.

**Picker options**:

- **Implement on current branch** (recommended) — trunk workflow; changes land on the current branch.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters via `EnterWorktree`. Proceeds to worktree entry.
- **Create feature branch** — create `feature/{lifecycle-slug}` for a PR flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Dependency graph**: parse `**Depends on**` from every pending task into an adjacency list; a cycle stops the phase — dispatch nothing.

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

Pass `$model` to each builder. On nonzero exit, halt and escalate rather than guessing. Then record the dispatch via advance's implement-transition arm (it owns the `batch_dispatch` emission, idempotent per batch number):

```bash
cortex-lifecycle-advance implement-transition --mode batch --feature <name> --batch <N> --tasks '[<task IDs>]'
```

**Command not found** (`cortex-lifecycle-advance` not on `PATH`) → halt and instruct the operator to install/upgrade the cortex-command CLI, then re-invoke. Do NOT record the dispatch by hand. <!-- Halt-arm convention: this arm names ONLY the verb and the install remedy — never a raw event-emission surface, which would defeat the per-file zero-sweep (tests/test_lifecycle_event_roundtrip.py) that keeps this cluster's emissions inside the verb. -->

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
<!-- pause: implement-batch-failure question -->
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

Re-entering from Review with CHANGES_REQUESTED — the rework-re-entry transition was already recorded by advance's review-verdict arm when the review returned CHANGES_REQUESTED (it owns that emission), so this re-entry records nothing itself.

1. Read `cortex/lifecycle/{feature}/review.md` for the reviewer's feedback.
2. For each flagged task, dispatch a fresh sub-task with the original task text + the reviewer's specific feedback + a fix instruction.
3. Non-flagged tasks keep their `[x]`.
4. Return to Review.

### 4. Transition

When all tasks are `[x]`, hand off to advance's implement-transition arm in transition mode. It reads tier/criticality through the shared reducer, applies the implement→{review|complete} routing rule (owned there, not restated here — `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state), and records the `phase_transition` idempotently. Route on the returned `state`; do not re-derive it:

```bash
cortex-lifecycle-advance implement-transition --mode transition --feature {feature}
```

Act on the returned `state`:

- **`review`** — the implement→review transition is recorded; proceed to Review.
- **`complete`** — the implement→complete transition is recorded; proceed to Complete.
- **`error`** — surface the verb's `message` and halt without advancing.

**Command not found** (`cortex-lifecycle-advance` not on `PATH`) → halt and instruct the operator to install/upgrade the cortex-command CLI, then re-invoke. Do NOT record the transition by hand. <!-- Halt-arm convention: this arm names ONLY the verb and the install remedy — never a raw event-emission surface (see the §2b note). -->

**Proceed automatically** — no confirmation. The transition fires on the gate (every task `[x]`, then the verb's route), not user input. Announce briefly and continue. This boundary is not a kept pause; see SKILL.md §Phase Transition.

## Constraints

- Batch N+1 waits for batch N.
- Always commit via `/cortex-core:commit` — orchestrator checkpoints and worktree sub-agents included; never raw git.
