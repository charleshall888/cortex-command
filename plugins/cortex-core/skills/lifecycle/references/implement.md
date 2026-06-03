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
- **Implement on feature branch with worktree** — creates an `interactive/{slug}` worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and auto-enters it via the platform `EnterWorktree` tool so the orchestrator session continues implementation from inside the worktree. **When to pick**: medium/many-task features where you want an isolated branch with worktree but still need live steering. Proceeds to §1a below.
- **Create feature branch** — create `feature/{lifecycle-slug}` for PR-based workflow. **When to pick**: you want a PR-based flow but cannot use a worktree (e.g., tooling that assumes a single checkout). NOTE: this runs `git checkout` on the main session and can corrupt parallel sessions in this repo.

**Branch-mode dispatch preflight**: Before the uncommitted-changes guard and the runtime probe below, consult the per-repo `branch-mode` config. The `cortex-lifecycle-branch-mode` CLI invocation here is the **structural marker** that the parity test (`tests/test_lifecycle_kept_pauses_parity.py`'s `conditional pause` sentinel) anchors against — its presence in this section is load-bearing for the documentation-parity test, in addition to gating the runtime dispatch.

Run two Bash calls (no compound commands):

1. Read the configured `branch-mode` value:

   ```bash
   cortex-lifecycle-branch-mode .
   ```

   The CLI calls `cortex_command.lifecycle_config.read_branch_mode` and prints the raw whitespace-stripped string from `cortex/lifecycle.config.md`'s YAML frontmatter, or empty (treated as `None`) when the file is missing, the field is absent, or the frontmatter is malformed. Caller-side closed-set validation is deferred to `should_fire_picker` below — invalid values fall through to the picker via the `branch_mode_unset_or_invalid` reason.

2. Decide whether the picker fires, given the value above and the current preflight state. The CLI emits a JSON object `{"fire": <bool>, "reason": "<closed-set-token>"}`; parse it with `jq` by capturing stdout once and then extracting each field via a separate `jq` invocation:

   ```bash
   DECISION=$(cortex-lifecycle-picker-decision . {slug} {branch_mode})
   FIRE=$(printf '%s' "$DECISION" | jq -r '.fire')
   REASON=$(printf '%s' "$DECISION" | jq -r '.reason')
   ```

   The third positional argument (`{branch_mode}`) is the value emitted by step 1; omit it when the branch-mode value is empty. `FIRE` holds the lowercase JSON literal `true` or `false` — branch on it with `[ "$FIRE" = "true" ]` (or, equivalently, use jq's exit-code semantics directly: `printf '%s' "$DECISION" | jq -e '.fire' >/dev/null && ... || ...`). `should_fire_picker` returns `(True, reason)` when any of these hold (first match wins): `branch_mode` is `None` or outside the closed set `{"worktree-interactive", "trunk", "feature-branch", "prompt"}`; `branch_mode == "prompt"`; `git status --porcelain` is non-empty (dirty-tree carve-out — the existing line 22 demote-and-warn guard handles the user-facing cue when the picker subsequently fires); `cortex/lifecycle/sessions/{slug}.interactive.pid` exists with a live PID (concurrent interactive worktree carve-out — defensively re-checked at §1a:78–82). Otherwise it returns `(False, "suppressed")`.

**Routing on the result.** Each of the four closed-set values has an explicit destination:

- `worktree-interactive` — when `should_fire_picker` returns `(False, "suppressed")`, **record entry mode `suppressed`**, skip the picker (the uncommitted-changes guard, runtime probe, and `AskUserQuestion` call below) and proceed directly to §1a (Interactive Worktree Creation). The §1a:78–82 liveness check is preserved in place as defensive redundancy. The `suppressed` marker is the carried control-flow value §1a step v branches on: it routes structurally to the cd-shim, skipping `EnterWorktree`.
- `trunk` — when `should_fire_picker` returns `(False, "suppressed")`, skip the picker and proceed on the current branch directly to §2 Task Dispatch, equivalent to the "Implement on current branch" selection path.
- `feature-branch` — when `should_fire_picker` returns `(False, "suppressed")`, skip the picker and proceed to §1b (Feature Branch Creation, equivalent to the "Create feature branch" selection path): create and check out `feature/{lifecycle-slug}` before dispatching any tasks, then proceed to §2.
- `prompt` — `should_fire_picker` returns `(True, "branch_mode_prompt")`, so the picker fires as today: fall through to the uncommitted-changes guard and `AskUserQuestion` call below.

When `should_fire_picker` returns `(True, reason)` for any reason (`branch_mode_unset_or_invalid`, `branch_mode_prompt`, `dirty_tree`, or `live_interactive_worktree_session`), do **not** short-circuit — fall through to the uncommitted-changes guard, the runtime probe, and the existing `AskUserQuestion` call site below (the picker fires as today). The line 22 `AskUserQuestion` site is the canonical picker invocation; the preflight here is additive routing, not a replacement.

**Uncommitted-changes guard**: Immediately before the `AskUserQuestion` call, run `git status --porcelain` (no path filter, no additional flags). If non-empty output is returned, the option that keeps the user on the current branch is demoted in place: (a) prepend the fixed warning `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` as a one-line prefix to that option's description, and (b) strip the `(recommended)` suffix from that option's label if present. The option remains selectable and stays at its existing position — no removal, no gating pre-question. If `git status --porcelain` exits non-zero (e.g., missing `.git`, corrupt index, bisect/rebase state), the guard does not fire — neither the demotion nor the warning prefix are applied — a single-line diagnostic `uncommitted-changes guard skipped: git status failed` is surfaced alongside the prompt, and the pre-flight continues normally as a fallback.

**Runtime probe**: After the uncommitted-changes guard and before assembling the prompt's options array, run a single Bash call that probes whether the `cortex-worktree-create` console-script is reachable on PATH:

```bash
command -v cortex-worktree-create >/dev/null 2>&1
```

Route by exit code into one of three menu dispositions:

- **exit 0** → the binary is reachable on PATH → all three options remain unchanged: `Implement on current branch`, `Implement on feature branch with worktree`, and `Create feature branch`.
- **exit 1** → the binary is not on PATH → remove `Implement on feature branch with worktree` from the options array; this is a silent hide, with no diagnostic surfaced. The post-degrade option set is `Implement on current branch` and `Create feature branch`.
- **Bash tool execution failure (sandbox rejection, missing /bin/sh, shell unavailable) OR `command -v` exit code other than 0 or 1** → fail open: all three options remain, and the literal diagnostic string `runtime probe skipped: console-script probe failed` is surfaced alongside the prompt.

After the probe completes and the options array has been resolved per the routing rules above, the resolved options array is then passed to `AskUserQuestion`.

Dispatch by selection:
- If the user selects **Implement on feature branch with worktree**, **record entry mode `selected`** and run the two interactive preflight guards below (Steps A and B) before proceeding to §1a. If either guard rejects, exit §1 without creating a worktree.

  **Step A — Overnight-active rejection mirror**: Source the overnight-probe sidecar and surface interactive-tailored wording on exit 1:

  ```
  cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (`cortex overnight status`), or open a different feature." "$(_resolve_user_project_root)"
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

This section runs in **two** entry modes: when the user **selected** "Implement on feature branch with worktree" in §1 (picker-fired), or when §1's branch-mode preflight **suppressed** the picker for `branch-mode: worktree-interactive` and routed here directly. In both modes the orchestrator session creates the `interactive/{slug}` worktree; it then either auto-enters via the platform `EnterWorktree` tool (the `selected` path) or routes structurally to the cd-shim (the `suppressed` path, which carries no `EnterWorktree` authorization — ADR-0008). The carried entry-mode marker recorded at §1 selects the branch at step v. Either way the orchestrator session does not exit `/cortex-core:lifecycle` — it continues into §2 task dispatch with CWD now resolved against the worktree path.

**i. Interactive worktree liveness check.** Two separate Bash calls (no compound commands):

1. Read the interactive PID file: `cat cortex/lifecycle/sessions/{slug}.interactive.pid 2>/dev/null`
2. If the file was non-empty, liveness check on the PID: `kill -0 $pid 2>/dev/null`

If `kill -0` exits 0 (process alive): reject with "An interactive worktree session is already live for `{slug}` (PID {pid}). Resolve it before creating a new worktree." and exit §1a without creating a worktree. If the exit code is non-zero or the file was absent/empty: proceed.

**ii. Overnight concurrent guard.** Run the overnight-active probe sidecar via `cat`-then-eval. The four-bash-call sequence (read `active-session.json`, parse `repo_path` and `session_dir`, read `{session_dir}/runner.pid`, parse `pid` from the JSON via `python3 -c "import json,sys; print(json.load(sys.stdin)['pid'])" < {session_dir}/runner.pid`) is extracted into the sidecar at `skills/lifecycle/references/_interactive_overnight_check.sh` and invoked as:

```
cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- "Overnight runner is active for this repo — wait for it to complete before creating an interactive worktree." "$(pwd)"
```

Sidecar exit codes: `0` = no overnight active, proceed normally; `1` = overnight live for this repo, surface the wording and exit §1a; `2` = stale runner detected (runner.pid absent or process dead), surface a warn-and-continue diagnostic and proceed.

**iii. Worktree creation.** Single Bash call invoking `cortex-worktree-create`:

```bash
worktree_path=$(cortex-worktree-create --feature interactive-{slug} --base-branch main)
```

The `interactive-` prefix causes `create_worktree` to resolve the branch as `interactive/{slug}` (via `_resolve_branch_name` with `prefix="interactive"`), and the worktree is materialized at `<repo>/.claude/worktrees/interactive-{slug}/`. The wrapper copies `.claude/settings.local.json` into the worktree and symlinks `.venv` as part of the standard post-creation steps. The wrapper prints exactly the absolute worktree path to stdout (captured via `$(...)`); all informational output is on stderr.

If creation fails: the wrapper writes `repr(exc)` to stderr and exits 1. Surface the stderr output to the user and exit §1a — do not proceed to handoff.

**iv. Pre-flight check.** Verify the resolved worktree path lives inside the repo root. Since #260 reverted same-repo worktrees to `<repo>/.claude/worktrees/<feature>`, the path is covered by the project's trust scope automatically — no per-shell `sandbox.filesystem.allowWrite` / `additionalDirectories` registration is required. Run as a single Bash call:

```bash
python3 - <<'EOF'
import subprocess, sys
from pathlib import Path

resolved = subprocess.run(
    ["cortex-worktree-resolve", "interactive-{slug}"],
    capture_output=True, text=True, check=False,
)
if resolved.returncode != 0:
    sys.stderr.write(
        "cortex-worktree-resolve failed; install cortex-core or set CORTEX_COMMAND_ROOT.\n"
    )
    sys.exit(2)
worktree_path = Path(resolved.stdout.strip()).resolve()

repo = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=False,
)
if repo.returncode != 0:
    sys.stderr.write("not inside a git repository.\n")
    sys.exit(2)
repo_root = Path(repo.stdout.strip()).resolve()

try:
    worktree_path.relative_to(repo_root)
except ValueError:
    sys.stderr.write(
        f"resolved worktree {worktree_path} is not inside repo root {repo_root}; "
        "expected <repo>/.claude/worktrees/<feature>.\n"
    )
    sys.exit(2)
sys.exit(0)
EOF
```

Exit-code contract: exit 0 = path is inside the repo, proceed; exit 2 = resolver failed, not in a git repo, or path escapes the repo root. On exit 2, halt §1a — do not cd or emit the event.

**Step v — Auto-enter sequence**

After the pre-flight check passes (exit 0), the operations below branch on the **entry mode** carried from the §1 branch-mode preflight — `selected` (the user picked the worktree option live; that selection is the user-direct "worktree" mention that authorizes `EnterWorktree` per ADR-0008) or `suppressed` (`should_fire_picker` returned `(False, "suppressed")` under `branch-mode: worktree-interactive`, so the picker never fired and there is no per-invocation authorization). Steps i–iv above already ran unconditionally, so the worktree exists in both modes. The order is load-bearing: `_origin_pwd` is captured first so we can restore CWD on fallback; on the `selected` path the cheap probe fast-fails before the platform tool call and `EnterWorktree` lands before the event; the event emission runs last so the row lands in the worktree's events.log via `_resolve_user_project_root_from_cwd()`.

1. **Capture origin pwd** — run a single Bash call: `_origin_pwd=$(pwd)`. Hold this value for the lifecycle session (it may be needed for restore at Complete phase or on fallback below).

2. **Suppressed-picker structural branch** — when the carried entry mode is `suppressed`, skip the `cortex-worktree-precondition` probe AND the auto-enter call entirely and route structurally to the cd-shim: run `cd $(cortex-worktree-resolve interactive/{slug})` to root the session in the already-created worktree, surface the stable literal diagnostic `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`, then jump to operation 5 (emit event). This path carries no authorization for the platform auto-enter tool by design (ADR-0008); the skip is a carried control-flow value threaded from §1, not a runtime decline. When the carried entry mode is `selected`, do not take this branch — continue to operation 3.

3. **Already-in-worktree probe** (entry mode `selected`) — run a single Bash call: `cortex-worktree-precondition`. Exit 0 means the current session is NOT already inside a worktree (proceed); exit 1 means the session IS already inside a worktree (skip operation 4 and route to the fallback path with a single-line diagnostic naming the detected worktree). The shim compares `git rev-parse --show-toplevel` against `git rev-parse --git-common-dir` to detect the case where the user launched Claude Code with `--worktree=<path>` and would otherwise hit `EnterWorktree`'s "Must not already be in a worktree" rejection.

4. **Auto-enter the worktree** (entry mode `selected`) — when the probe above returned exit 0, call the platform tool:

   ```
   EnterWorktree(path=<resolved-path>)
   ```

   where `<resolved-path>` is the value returned by `cortex-worktree-resolve interactive/{slug}` (never a hardcoded prefix per R3). This sets the orchestrator session's CWD to the interactive worktree for all subsequent Bash tool calls in this lifecycle session and clears CWD-dependent caches (system prompt sections, memory files, plans directory). If the tool errors (path not in `git worktree list`, schema rejection, or a "Must not already be in a worktree" race), route to the fallback path below.

5. **Emit event** — run a single Bash call once the session CWD is rooted in the worktree (via `EnterWorktree` on the `selected` path, or the cd-shim on the `suppressed` path):

   ```bash
   cortex-lifecycle-event log --event interactive_worktree_entered --feature {slug} --worktree-path "$(pwd)"
   ```

   The `cortex-lifecycle-event` CLI uses `_resolve_user_project_root_from_cwd()` (ignores `CORTEX_REPO_ROOT`), so the event row lands in the worktree's `cortex/lifecycle/{slug}/events.log` — not the main repo's.

**Fallback — `EnterWorktree skipped`.** On the `selected` path, if the `cortex-worktree-precondition` probe in operation 3 returns non-zero, OR the `EnterWorktree` call in operation 4 errors, OR the skill judges the gate unmet and declines to invoke the tool (silent non-invocation), fall back to the cd-shim handoff: run `cd $(cortex-worktree-resolve interactive/{slug})` and proceed to operation 5 to emit the event. Surface a single-line diagnostic naming the failure mode (e.g., `EnterWorktree skipped: already inside worktree at <path>`, `EnterWorktree skipped: tool rejected path <path>`). The diagnostic's specific failure-mode strings vary; the structural marker `EnterWorktree skipped` is the anchor R10 and R14 scan for. The `suppressed`-entry-mode cd-shim in operation 2 is a *planned* structural route, not a fallback — it emits its own `EnterWorktree skipped: suppressed-picker` marker on the same anchor family.

The auto-enter affects only orchestrator-session Bash tool calls; sub-agent dispatch via `Agent(isolation: "worktree")` in §2 is unaffected — each sub-agent is independently rooted at `<repo>/.claude/worktrees/{task-name}/`. The existing §2(e) Worktree Integration step (`implement.md:218-229`) runs `git merge worktree/{task-name}` from the feature-branch CWD (which under auto-enter is `interactive/{slug}` post-`EnterWorktree`) and then `git worktree remove` for each completed sub-agent worktree — auto-enter inherits this merge-back behavior unchanged.

**vi. Interactive worktree auto-entry.** After `EnterWorktree` returns (entry mode `selected`), the orchestrator session is rooted at `interactive/{slug}` for all subsequent Bash tool calls and sub-agent dispatch in this lifecycle session, and `EnterWorktree`'s cache-clear side effect (system prompt sections, memory files, plans directory) ensures the session state reflects the new working directory rather than the pre-entry repo root. On entry mode `suppressed` the operation-2 cd-shim roots the session in the worktree without `EnterWorktree`'s cache-clear (and without its session-exit keep/remove prompt), so the `ExitWorktree` cleanup below does not apply on that path — `cd $(git rev-parse --show-toplevel)` is the only restoration step needed. Surface the worktree path to the user along with a single-line warning that on session exit the harness will prompt to **keep or remove** the worktree as context — selecting "remove" discards any uncommitted work in the worktree, so commit or push before exiting. When the user wants to leave the worktree mid-session, two restoration paths are available: run `ExitWorktree action="keep"` to clear `EnterWorktree` session state cleanly (preferred while the session is live, since it dismisses the session-exit prompt), or run `cd $(git rev-parse --show-toplevel)` to navigate back to the repo root while leaving the keep/remove prompt deferred until session end. See ADR-0004 for the design rationale behind mid-session auto-entry over the fresh-session alternative.

**vii. Continue to §2 Task Dispatch.** Do not exit `/cortex-core:lifecycle`. The orchestrator session is now inside the interactive worktree and proceeds to dispatch implementation tasks from §2 onward.

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
4. **Cleanup**: After a successful merge, run `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`. The `cortex-worktree-resolve` console script returns the canonical worktree path (`<repo>/.claude/worktrees/{task-name}/`) via the single resolver chokepoint.
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

**Proceed automatically** — do not ask the user for confirmation before entering the next phase. The transition fires on the gate conditions (every task `[x]`, then the criticality matrix above), not on user input. Announce the transition briefly as plain text and continue. The Implement → Review/Complete boundary is not in the Kept user pauses inventory; see SKILL.md §Phase Transition for the umbrella reasoning.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should dispatch all tasks at once for maximum speed" | Batch ordering respects dependencies. Tasks in batch N+1 must wait for batch N to complete, even if some seem independent. The batch model keeps dispatch simple and checkpoint writes serialized. |
| "I'll just run `git add` and `git commit` directly" | Always use `/cortex-core:commit` for all commits — orchestrator checkpoints included. Never use raw git commands for staging or committing. Sub-agents in worktrees have full tool access including the Skill tool — uncertainty about this is not a reason to bypass it. |
