# Research: lifecycle-implement-worktree-dispatch

**Topic**: Add a third option "Implement in worktree" to /lifecycle's implement-phase pre-flight branch prompt (`skills/lifecycle/references/implement.md:11-18`) that, when selected, dispatches the remainder of the lifecycle (implement → review → complete + PR) to a single `Agent(isolation: "worktree")`. The main session stays on main so parallel Claude sessions in this repo are unaffected by branch switching.

**Stated motivation (verbatim from user)**: "when I use /lifecycle (not overnight) if i implement on a separate branch (not main) then it changes branches. This often leads to other work I have going on in separate claude sessions getting added onto the branch that we moved to."

## Codebase Analysis

### Files affected
- `skills/lifecycle/references/implement.md` §1 (lines 7-18) — primary change: add third option to AskUserQuestion + new Worktree Dispatch section.
- `skills/lifecycle/SKILL.md` (around lines 348-378) — possible note that single-feature worktree dispatch differs from existing multi-feature parallel dispatch.
- `complete.md`, `review.md` — no change required; both are branch-name-agnostic. `complete.md §4` binary check (`main|master` vs anything) handles `worktree/{slug}` correctly; `review.md` reads via plan.md and git log without branch assumptions.

### Existing worktree machinery
- `claude/hooks/cortex-worktree-create.sh` is the WorktreeCreate hook invoked by `Agent(isolation: "worktree")`:
  - Line 29: `WORKTREE_PATH="$CWD/.claude/worktrees/$NAME"`
  - Line 30: `BRANCH="worktree/$NAME"` — **hardcoded prefix; cannot be `feature/` without modifying the hook**
  - Line 33: fails fast on `if [ -e "$WORKTREE_PATH" ]` — **not idempotent**; orphaned dirs block re-creation
  - Line 45: `git worktree add "$WORKTREE_PATH" -b "$BRANCH" HEAD`
  - No nested-worktree detection; `$CWD` taken at face value from the hook input
- `hooks/cortex-cleanup-session.sh` lines 46, 59: cleanup filter is **hardcoded to `worktree/agent-*` and `.claude/worktrees/agent-*`** — branches and dirs without the `agent-` prefix are NOT swept on session crash. This is the source of failure mode FM-2 (see Adversarial section).
- `hooks/cortex-scan-lifecycle.sh` line 291: when a fresh session starts and exactly one incomplete lifecycle exists with no matching `.session`, the new session **auto-claims** the lifecycle by overwriting `.session`. This is the source of FM-1 (session hijack).

### Existing per-task worktree dispatch in implement.md §2
- §2d documents `Agent(isolation: "worktree")` per-task dispatch with branch `worktree/{task-name}` and path `.claude/worktrees/{task-name}`.
- §2e merges per-task worktree branches back to the feature branch, then runs `git worktree remove` + `git branch -d`.
- §2 also has a "Sequential dispatch" alternative branch (per §2d "Sequential dispatch" sub-bullet) that does not use isolation and runs `git log --oneline -N` to verify commits.
- **The key collision**: if the whole lifecycle runs in a worktree, per-task dispatches inside the inner agent are nested-worktrees-within-a-worktree.

### `/pr` and `/commit` skills
- `skills/pr/SKILL.md`: branch-agnostic. Uses `git branch --show-current` and `git push -u origin HEAD`. Creates PRs from any branch name. No assumptions about `feature/*` vs `worktree/*`.
- `skills/commit/SKILL.md`: branch-agnostic. Works correctly inside a git worktree. Sandbox GPG signing path is identical.

### Existing `Agent(isolation: "worktree")` call sites
1. `skills/lifecycle/SKILL.md` Parallel Execution section — multi-feature parallel dispatch (the conceptual cousin of this feature).
2. `skills/lifecycle/references/implement.md` §2d (referenced) — per-task dispatch.
3. `claude/reference/parallel-agents.md` — generic parallel pattern documentation.
4. `skills/research/SKILL.md` — explicit note that research dispatch does NOT use worktree isolation (read-only).

## Web Research

### Git worktree mechanics
- Nested worktrees are mechanically supported by git but discouraged in practice; tools (lazygit, vscode extensions) break with nested layouts. Canonical layout is sibling worktrees, not nested.
- The same branch cannot be checked out in two worktrees simultaneously (hard constraint).
- Cleanup order matters: `git worktree remove <path>` before `git branch -d <branch>` (the latter refuses while branch is checked out anywhere).
- **microsoft/vscode-pull-request-github#8519**: when a worktree branch is deleted on remote (PR merged) but the local worktree directory isn't removed, the worktree re-associates with `main`, producing weird state. Requires manual recovery via `git worktree prune -v`.

### Claude Code Agent isolation
- `Agent(isolation: "worktree")` triggers the WorktreeCreate hook (`cortex-worktree-create.sh` in this repo).
- Standard upstream Claude Code uses `worktree-<name>` (hyphen) prefix; this repo's hook overrides to `worktree/<name>` (slash).
- **Worktrees with commits are NEVER auto-swept** by Claude Code's background GC (only clean ones are).
- **Issue #33045**: `isolation: "worktree"` is silently ignored when spawning team agents via `TeamCreate` (irrelevant to our case since we use standalone `Agent`).
- An adjacent finding: when a subagent **manually** creates a worktree, Read/Edit/Glob/Grep tools resolve relative paths against the parent project root, not the manual worktree. **Whether this also applies to standalone `Agent(isolation: "worktree")` is unverified — see Open Question OQ-3.**

### `gh pr create` from a worktree
- No known issues. `gh` resolves the current branch via shared `.git` and pushes/creates normally.
- Base detection: `--base` flag > `branch.<current>.gh-merge-base` git config > repository default branch.
- Pitfall (cli/cli#588): `gh pr create` may push to `upstream` instead of `origin` in fork scenarios — not relevant to a single-fork repo.

### Branch naming for ephemeral worktrees
- Industry pattern: use a distinct prefix (`wt-`, `worktree-`, `agent/`) to mark machine-managed branches as throwaway. This repo's `worktree/` prefix already follows this pattern.

## Requirements & Constraints

### `requirements/multi-agent.md`
- **§Worktree Isolation, line 29**: "branch `pipeline/{feature}` (with collision suffix `-2`, `-3` if needed)" — **scoped to the overnight runner**, not a global rule. Daytime `Agent(isolation: "worktree")` uses `worktree/{name}` per the hook.
- **§Architectural Constraints, line 72**: "Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents." Adjacent constraints reference `ConcurrencyManager` and overnight orchestration. **Literal text does not scope to overnight, but context is overnight-runner.** A daytime interactive `/lifecycle` session dispatching ONE worktree agent is at the boundary of this constraint — the inner agent then spawning per-task sub-agents may cross it.
- **§Agent Spawning, line 22**: "Permission mode is always `bypassPermissions` for overnight agents." Daytime is unspecified.

### `requirements/project.md`
- **§Quality Attributes**: defense-in-depth permissions; daytime uses minimal allow + comprehensive deny + sandbox; overnight uses `bypassPermissions`. Daytime worktree-dispatched agents inherit the parent session's permission set.
- **§Architectural Constraints**: file-based state — lifecycle artifacts must remain plain files.
- **In Scope**: "Multi-agent orchestration: parallel dispatch, worktree isolation, Haiku/Sonnet/Opus model selection matrix". Daytime worktree dispatch is a natural extension of this.

### `requirements/multi-agent.md` is silent on
- Whether daytime interactive sessions can dispatch worktree agents
- Daytime agent permission posture
- Branch naming convention for daytime worktree dispatch
- Cleanup semantics for worktree branches that are PR sources

## Tradeoffs & Alternatives

### Decision 1: Dispatch scope
- **A** (whole-lifecycle: implement → review → complete + PR all in agent) — **recommended**. Only option that actually keeps main on main. Review needs disk reads; complete runs tests against the integrated tree. B and C either force main to checkout the branch (defeats purpose) or require invasive rewrites.
- B (only implement in agent): main needs to read implementation files for review — can't without checkout.
- C (three separate dispatches): no infrastructure for "attach to existing branch", and no clear benefit over A.

### Decision 2: Branch naming
- A `worktree/{slug}-impl` — needs custom hook invocation; "impl" suffix bleeds into PR name.
- B `worktree/{slug}` — matches hook hardcode, zero infrastructure changes. **But: not swept by cleanup hook (FM-2).**
- C `feature/{slug}` — clean PR aesthetic, but cortex-worktree-create.sh hardcodes `worktree/$NAME`. Would need hook change or post-create rename.
- D `worktree/{slug}` locally, push as `feature/{slug}` to remote — split naming, confusing.
- **E (NEW, from adversarial mitigation #2): `agent-{slug}` → branch `worktree/agent-{slug}`** — matches existing cleanup hook filter, FREE WIN for crash recovery. Recommended over B.

### Decision 3: Cleanup semantics for worktree-as-PR-source
- A (leave worktree+branch alive until user cleans up): accumulates orphans; blocks re-runs of same slug.
- B (sentinel + auto-clean on next /lifecycle): adds new subsystem.
- C (push then immediately remove worktree, branch survives on remote): simple, clean, but **vscode-pull-request-github#8519 documents the re-association bug — adversarial finding FM-11**.
- **Recommendation revised**: leave worktree directory in place until PR merges; cleanup happens manually or on next `/lifecycle resume` after the cleanup hook is taught about the new naming.

### Decision 4: Per-task dispatch inside worktree agent
- A (allow nested dispatch): mechanically supported by git but fragile; nesting creates `<wt>/.claude/worktrees/<task>` paths inside a tracked directory.
- B (detect "I am in a worktree" and force sequential): adds runtime detection logic.
- C (force sequential always via dispatching prompt): simplest, but **adversarial FM-4 surfaces that "sequential" is under-specified — does it mean (a) Agent calls without isolation, or (b) inline work without sub-agents at all?** Either choice loses the "fresh context per task" property that implement.md §2 was designed for.
- **No clean recommendation; this is a quality regression that must be explicitly accepted in the spec.**

### Decision 5: Default vs opt-in
- A (recommended default, first in AskUserQuestion list): pushes user toward parallel-safe option.
- B (opt-in third option): backward compatible, lower regression risk.
- **Recommendation: B (opt-in), restricted to simple/low-medium criticality only per adversarial mitigation #4. Promote to default in a follow-up after validation.**

## Adversarial Review

The adversarial agent surfaced 12 failure modes and 4 security concerns. The most critical, with empirical verification:

### Critical (verified against repo state)
- **FM-1: `.session` file hijack** — `hooks/cortex-scan-lifecycle.sh:291` auto-claims orphaned `.session` files when a fresh session sees exactly one incomplete lifecycle. The dispatched worktree agent writes its own session ID to `.session` (overwriting main's), and a third concurrent session would then steal it from the dispatched agent.
- **FM-2: cleanup hook prefix mismatch** — `hooks/cortex-cleanup-session.sh:46,59` only sweep `worktree/agent-*` branches and `.claude/worktrees/agent-*` paths. A `worktree/{slug}` orphan from a crashed dispatch will NEVER be cleaned up, especially since worktrees-with-commits are not GC'd by upstream Claude Code either.
- **FM-9: events.log divergence** — main and worktree have separate `lifecycle/{feature}/events.log` copies. Main is stale until PR merge. If user runs `/lifecycle resume {feature}` on main during dispatch (nothing prevents this), main re-enters implement and dispatches a SECOND parallel lifecycle. Two concurrent completions racing.
- **FM-3: per-task name collisions** with the outer worktree (if names overlap), and nested worktree paths created at `<outer-worktree>/.claude/worktrees/{task-name}/`.

### Significant
- **FM-4: "force sequential" is under-specified** — implement.md §2 has rich worktree-specific logic in §2d/§2e. Telling the inner agent to "use sequential" doesn't map cleanly to the existing "Sequential dispatch" branch. Whichever interpretation is chosen, the per-task fresh-context isolation is lost — a quality regression that must be acknowledged.
- **FM-5: AskUserQuestion sites the inner agent will hit silently** — branch prompt (handled by branch check), backlog status check (SKILL.md Step 2), task failure retry/skip/abort (implement.md), reviewer re-dispatch (review.md), test command discovery (complete.md). Generic "escalate up" is insufficient; each site needs explicit non-interactive fallback in the wrapper prompt, OR the inner agent's behavior is undefined.
- **FM-6: nested Agent calls inside the worktree agent** — review.md dispatches a reviewer sub-agent (no isolation) from inside the layer-1 worktree. Whether layer-2 inherits layer-1's CWD is unverified — if not, reviewer reads files from main (unchanged), silently approving implementations it never saw.
- **FM-10: catastrophic failure leaves no main-side trace** — all state lives in the worktree; user has no recovery path because `cd <worktree> && git ...` is blocked by Claude Code's security check.
- **FM-11: vscode-pull-request-github#8519 cleanup race** — Decision 3 Option C (push-then-remove) hits exactly this documented failure mode.

### Security concerns
- **SC-1**: `bypassPermissions` inheritance — daytime worktree agents inherit the parent's interactive permission set, which assumes a user is present to approve. Inner agent has no user; permission prompts deadlock or auto-deny.
- **SC-3**: violates the spirit of `requirements/multi-agent.md:72` ("agents do not spawn peer agents") — doubles down on agents-spawning-agents at every layer.
- **SC-4**: no audit trail of inner agent's tool calls in main's session log.

### Adversarial recommendation #11 (the big one)
> "Consider scrapping this feature entirely in favor of the much simpler fix: change 'Create feature branch' to use `git stash --include-untracked + checkout -b + stash pop`. ... If the user's other sessions are in other worktrees (likely), they are ALREADY isolated from main's branch switches. The 'bleed-into-other-sessions' problem may not actually exist at the scale the proposed fix addresses."

This is the most important finding: **the entire premise depends on whether the user's parallel sessions are in the same git checkout or in separate worktrees.** If separate worktrees, branch switching in one doesn't affect another, and the proposed fix is solving a non-problem at high complexity cost.

## Open Questions

### OQ-1 (USER, RESOLVED): Are your parallel Claude sessions in the same checkout, or in separate worktrees?
**Resolved**: User confirmed "same checkout (one clone)" — the original problem is real and the proposed fix is correct in principle.

### OQ-2 (USER, RESOLVED): Direction given the failure modes?
**Resolved**: User chose "do the fix that will be the most resilient and work best long term." Spec proceeds with the heavily-mitigated dispatched-agent design (Option B from the AskUserQuestion). Rationale: the smaller fix (drop checkout) doesn't actually solve the problem because review and complete need disk access to the implementation files, which only the dispatched-agent path can provide without forcing a branch switch. The heavily-mitigated design accepts bounded complexity in exchange for a stable long-term protocol.

### OQ-3 (RESEARCH-RESOLVABLE, DEFERRED to implementation): Does `Agent(isolation: "worktree")` set the inner agent's tool resolution root to the worktree path?
**Deferred**: Will be resolved as task #1 in the plan via an empirical probe — write a file in the worktree, read it back via Read with a relative path, confirm isolation works. If the probe shows tool resolution against main rather than the worktree, abort the implementation and revisit OQ-2.

### OQ-4 (RESEARCH-RESOLVABLE, DEFERRED to implementation): Does the `.session`/`events.log` divergence change shape if OQ-3 reveals tools resolve against main?
**Deferred**: Conditional on OQ-3 outcome. If OQ-3 confirms worktree isolation, this question is moot.

### OQ-5 (USER, RESOLVED by orchestrator): Branch naming?
**Resolved**: Use `agent-{slug}` as the Agent `name` parameter, producing branch `worktree/agent-{slug}`. This matches the existing `hooks/cortex-cleanup-session.sh` filter (`worktree/agent-*` and `.claude/worktrees/agent-*`), giving free crash-recovery cleanup. PR branch aesthetic (`worktree/agent-feature-name`) is the accepted cost — PR branch names are seen once per feature on the GitHub UI and have no functional impact.

## Epic Reference

None — this is an ad-hoc topic with no backlog item or epic context.
