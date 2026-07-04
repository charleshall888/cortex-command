# Implement Phase

Dispatch a fresh implementation sub-task per task — fresh context prevents stale assumptions.

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

- **Implement on current branch** (recommended) — trunk workflow; changes land on the current branch. For small, trunk-safe changes.
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters via `EnterWorktree`. Proceeds to §1a. For multi-task features wanting isolation with live steering.
- **Create feature branch** — create `feature/{lifecycle-slug}` for a PR flow. NOTE: runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Step A — Overnight-active rejection**: source the overnight-probe sidecar; on exit 1 surface interactive-tailored wording:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
```

Exit codes: `0` = none active, proceed to §1a; `1` = overnight live, surface the wording and exit §1 without creating a worktree; `2` = stale runner, warn-and-continue to §1a.

**Dependency graph**: parse `**Depends on**` from every pending task into an adjacency list. On a cycle, stop and surface the error — dispatch nothing.

### 1a. Interactive Worktree Creation (Alternate Path)

Two entry modes: `selected` (user picked the worktree option) or `suppressed` (`branch-mode: worktree-interactive` bypassed the picker). Step v branches on the carried marker; either way the orchestrator session continues into §2 — it does not exit `/cortex-core:lifecycle`.

**i. Overnight concurrent guard** — invoke the sidecar:

```
cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```

Same `0` proceed / `1` reject / `2` warn-and-continue semantics as Step A; exit `0` → ii, exit `1` → exit §1a.

**ii. Interactive lock** — acquire the per-feature lock (single source of truth for `cortex/lifecycle/{slug}/interactive.pid`) **unconditionally for both entry modes**, and only **after** guard i passes, so a rejecting guard can never orphan a held lock:

```bash
cortex-interactive-lock acquire {slug}
```

Exit 0 → iii. Non-zero → the script wrote its rejection to stderr (a live same-slug session holds the lock); surface it verbatim and exit §1a without creating a worktree.

**iii. Worktree creation**:

```bash
worktree_path=$(cortex-worktree-create --feature interactive-{slug} --base-branch main)
```

`create_worktree` resolves the branch as `interactive/{slug}`, materializes the worktree at `<repo>/.claude/worktrees/interactive-{slug}/` (containment enforced — an escaping path exits 1 with `worktree_escapes_repo`), and prints the absolute path. On failure it writes `repr(exc)` to stderr and exits 1 — before exiting §1a run `cortex-interactive-lock release-if-owner {slug}` to release the step-ii lock (`release-if-owner` unlinks only when this session's `CLAUDE_CODE_SESSION_ID` owns the on-disk lock, so it never deletes a co-passer's live lock), then surface the stderr and exit §1a.

**Step v — Auto-enter sequence**

After iii succeeds, run in this order — the event must be emitted from inside the worktree so `_resolve_user_project_root_from_cwd()` lands the row in the worktree's events.log:

1. **Capture origin pwd** — `_origin_pwd=$(pwd)`; hold it for the session (restore at Complete or on fallback).
2. **Suppressed-picker structural branch** — when the entry mode is `suppressed`, skip the `cortex-worktree-precondition` probe AND the auto-enter, and route structurally to the cd-shim: `cd $(cortex-worktree-resolve interactive-{slug})`, surface the stable literal `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, then jump to op 5 (no EnterWorktree authorization — ADR-0008). When `selected`, skip this branch and continue to op 3.
3. **Already-in-worktree probe** (`selected`) — `cortex-worktree-precondition`. Exit 0 = not inside a worktree (proceed); exit 1 = already inside (skip op 4, route to fallback with a one-line diagnostic naming the detected worktree).
4. **Auto-enter** (`selected`, probe returned 0) — call `EnterWorktree(path=<resolved-path>)` where `<resolved-path>` is `cortex-worktree-resolve interactive-{slug}`'s output (never a hardcoded prefix — R3). This sets session CWD to the worktree for all subsequent Bash calls and clears CWD-dependent caches. On error (path not in `git worktree list`, schema rejection, "Must not already be in a worktree" race) → fallback.
5. **Emit event** — once CWD is rooted in the worktree (via `EnterWorktree` on `selected`, or the cd-shim on `suppressed`):

   ```bash
   cortex-lifecycle-event log --event interactive_worktree_entered --feature {slug} --set worktree_path="$(pwd)"
   ```

   (`cortex-lifecycle-event` uses `_resolve_user_project_root_from_cwd()`, ignoring `CORTEX_REPO_ROOT`, so the row lands in the worktree's events.log.)

**Fallback — `EnterWorktree skipped`.** On the `selected` path, if the op-3 probe returns non-zero, the op-4 `EnterWorktree` errors, or the skill declines to invoke the tool, cd-shim handoff: `cd $(cortex-worktree-resolve interactive-{slug})` then op 5. Surface a one-line diagnostic beginning `EnterWorktree skipped` and naming the failure mode. Auto-enter affects only orchestrator-session Bash calls; sub-agent `Agent(isolation: "worktree")` dispatch in §2 is unaffected, and §2(e) merge-back applies unchanged.

**vi.** On `suppressed`, `cd $(git rev-parse --show-toplevel)` is the only restoration needed. Surface the worktree path with a one-line warning: on session exit the harness prompts to keep/remove — "remove" discards uncommitted work, so commit or push first. Mid-session, `ExitWorktree action="keep"` clears state cleanly, or `cd $(git rev-parse --show-toplevel)` navigates back deferring the prompt. See ADR-0004.

**vii.** Do not exit `/cortex-core:lifecycle` — the session is inside the worktree; proceed to §2.

### 2. Task Dispatch

Compute batches by topological level:
- **Batch 0**: pending tasks with `**Depends on**: none` (or deps already `[x]`).
- **Batch N**: tasks whose deps are all in batches 0..N-1.

Batching keys on full task identity, including letter-suffixed sub-tasks (`### Task 3a:`) — first-class units (see plan.md "Sub-task headings"). **Same-batch sub-task siblings must have disjoint `Files`** — rationale and the serialize-via-`Depends on` workaround live in that section.

Per batch, in order:

**a. Extract task texts** — copy each task's full block from plan.md (`### Task N:` to the next task heading).

**b. Dispatch** — launch all batch tasks concurrently as parallel sub-tasks. Use the builder template below **verbatim** per task (substitute variables; do not omit, reorder, or paraphrase). Add 2-3 sentences of architectural context from the plan's Overview.

**Model** — resolve at dispatch, never hardcode:

```bash
model=$(cortex-resolve-model --role builder --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Pass `$model` to each builder. On nonzero exit, halt and escalate rather than guessing. Then log the dispatch:

```bash
cortex-lifecycle-event log --event batch_dispatch --feature <name> --set-json batch=<N> --set-json tasks=[<task IDs>]
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
4. Surface: which task failed, the error, which downstream tasks are now blocked.
5. Ask the user: **retry**, **skip** (mark failed, continue non-dependents), or **abort**.

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

Re-entering from Review with CHANGES_REQUESTED — log the rework start:

```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set from=review --set to=implement-rework
```

1. Read `cortex/lifecycle/{feature}/review.md` for the reviewer's feedback.
2. For each flagged task, dispatch a fresh sub-task with the original task text + the reviewer's specific feedback + a fix instruction.
3. Non-flagged tasks keep their `[x]`.
4. Return to Review.

### 4. Transition

When all tasks are `[x]`, the next phase follows both tier and criticality (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state):

```bash
cortex-lifecycle-state --feature {feature} --field criticality
```

Next phase is **Review** when `criticality ∈ {high, critical}` OR `tier = complex`, else **Complete** — mirrors `cortex_command/common.py:requires_review`; do not re-derive.

```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set tier=<simple|complex> --set from=implement --set to=<review|complete>
```

**Proceed automatically** — no confirmation. The transition fires on the gate (every task `[x]`, then the review rule), not user input. Announce briefly and continue. This boundary is not a kept pause; see SKILL.md §Phase Transition.

## Constraints

- Batch N+1 waits for batch N.
- Always commit via `/cortex-core:commit` — orchestrator checkpoints included; never raw git. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty is not a reason to bypass it.
