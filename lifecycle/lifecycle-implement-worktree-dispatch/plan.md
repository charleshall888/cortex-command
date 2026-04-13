# Plan: lifecycle-implement-worktree-dispatch

## Overview

Modify two skill reference files (`skills/lifecycle/SKILL.md`, `skills/lifecycle/references/implement.md`) and the repo `.gitignore` to add a new "Implement in worktree" option to /lifecycle's implement-phase pre-flight. Because `implement.md §1` routing references `implement.md §1a` (which this feature introduces), both edits happen in ONE atomic task to prevent a broken inter-batch window for any parallel `/lifecycle` session reading the file mid-implementation. Final verification runs the acceptance-criteria grep battery from every spec requirement against the modified files, with an additional scope-checked grep pass that extracts `§1a` specifically and confirms the load-bearing literal strings appear inside the intended section.

## Tasks

### Task 1: Add `.gitignore` entry for `.dispatching` marker

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/.gitignore`
- **What**: Append `lifecycle/*/.dispatching` to the project-root `.gitignore`. Satisfies R13.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Read the existing `.gitignore` first — it already has `lifecycle/`-related entries (e.g., for `.session`), so match the existing comment/grouping style. Use `lifecycle/*/.dispatching` (single-star) rather than `**/.dispatching` (too broad).
- **Verification**: (a) `grep -c 'lifecycle/.*/\.dispatching' /Users/charlie.hall/Workspaces/cortex-command/.gitignore` returns ≥ 1 — pass if count ≥ 1. AND (b) `cd /Users/charlie.hall/Workspaces/cortex-command && git check-ignore lifecycle/nonexistent-feature/.dispatching` exits 0 — pass if exit code = 0.
- **Status**: [x] complete

### Task 2: Update implement.md — add §1 third option AND §1a Worktree Dispatch section (single atomic edit)

- **Files**: `/Users/charlie.hall/.claude/skills/lifecycle/references/implement.md`
- **What**: In a SINGLE atomic edit to this file, (A) rewrite §1 Pre-Flight Check to offer three branch options with "Implement in worktree" as the first (recommended) option, and (B) insert a new `### 1a. Worktree Dispatch (Alternate Path)` section immediately after §1 and before §2 Task Dispatch. Both changes MUST land in the same commit — an intermediate state where §1 routes to a non-existent §1a would silently break any parallel `/lifecycle` session reading the file during the implementation window. Satisfies R1, R2, R3, R4, R5, R7 (main-session side), R8, R9, R10 (Report the PR URL), R11, R12.
- **Depends on**: none
- **Complexity**: complex
- **Context**: 
  - **Part A (§1 rewrite)**: Current §1 text is lines 7–18 (research.md "Codebase Analysis" Q1 has the exact current text). Rewrite to three options in this order: "Implement in worktree" (recommended), "Implement on main", "Create feature branch". Add a dispatch-by-selection block routing each option. Preserve the existing "If the current branch is not main/master, skip the prompt" behavior verbatim.
  - **Part B (§1a new section)**: Insert a new `### 1a. Worktree Dispatch (Alternate Path)` section containing twelve elements in this order: (i) an intro noting this section runs only when "Implement in worktree" was selected and replaces §2–§4 for the main session; (ii) `.dispatching` marker atomic write step with `set -C` syntax, content = three lines `$$\n$LIFECYCLE_SESSION_ID\n$(date -u +%Y-%m-%dT%H:%M:%SZ)`; on collision surface the error and exit; (iii) append `implementation_dispatch` event to `events.log` with JSON body `{"ts":...,"event":"implementation_dispatch","feature":...,"mode":"worktree"}`; (iv) the `Agent(isolation: "worktree", name: "agent-{lifecycle-slug}", model: <sonnet for low/medium, opus for high/critical>, prompt: <template from v>)` invocation with the model-selection rule in prose; (v) the verbatim prompt template enclosed in a SINGLE code fence (```...```) containing the required literal strings (see Verification list); (vi) wait for Agent return; (vii) surface the agent's summary (PR URL on success, escalation context on escalation); (viii) `rm -f` the `.dispatching` marker; (ix) append `dispatch_complete` event with JSON body including `"outcome": "complete|escalated"` and `"pr_url": "<url>|null"`; (x) "Exit /lifecycle entirely" instruction; (xi) Known Limitations subsection covering the AskUserQuestion sharp edge (edge case from spec) and TC8 events.log divergence; (xii) Cleanup note referencing `cortex-cleanup-session.sh` and explicitly stating "no manual cleanup" is performed — do NOT include `git worktree remove` or `git branch -d` as orchestrator instructions (those commands may appear only as documentation of what the cleanup hook does).
  - **Prompt template contents** (must appear INSIDE the single code fence from element v, not in surrounding prose): "skip SKILL.md Step 2 Register session and Step 2 Backlog Write-Back", "Do NOT call AskUserQuestion", "sequential inline per-task dispatch", "no nested `Agent(isolation: \"worktree\")`", "no per-task sub-branches" or an explicit `worktree/{task-name}` prohibition, "Skip §2e Worktree Integration" (or equivalent), "commit directly to `worktree/agent-{slug}`", "cycle 1 CHANGES_REQUESTED is normal flow", "cycle 2+ CHANGES_REQUESTED: STOP", "REJECTED: STOP", "test failure: STOP", "Report the PR URL in your final response".
  - **Cross-reference**: spec.md R2–R12 enumerates the required literal strings per requirement. When in doubt, the spec's acceptance greps are authoritative over this context.
- **Verification**: run TWO passes of greps against `/Users/charlie.hall/.claude/skills/lifecycle/references/implement.md`:
  - **Pass 1 (file-wide)**: all of the following return the stated value — 
    - `grep -c "Implement in worktree"` ≥ 1
    - `grep -c "### 1a. Worktree Dispatch"` = 1
    - `grep -c 'name: "agent-{lifecycle-slug}"'` ≥ 1
    - `grep -c 'isolation: "worktree"'` ≥ 1
    - `grep -c "skip SKILL.md Step 2"` ≥ 1
    - `grep -c "Register session"` ≥ 1
    - `grep -c "Backlog Write-Back"` ≥ 1
    - `grep -c "Do NOT call AskUserQuestion"` ≥ 1
    - `grep -c "sequential inline per-task dispatch"` ≥ 1
    - `grep -c "no nested.*Agent.*isolation"` ≥ 1
    - `grep -c "Skip.*§2e"` ≥ 1 OR `grep -c "Skip Worktree Integration"` ≥ 1
    - `grep -c "commit.*directly to.*worktree/agent-"` ≥ 1
    - `grep -c "set -C"` ≥ 1
    - `grep -c "cycle 1 CHANGES_REQUESTED"` ≥ 1
    - `grep -c "cycle 2"` ≥ 1
    - `grep -c "REJECTED"` ≥ 1
    - `grep -c "test failure"` ≥ 1
    - `grep -c "Report the PR URL"` ≥ 1
    - `grep -c "implementation_dispatch"` ≥ 1
    - `grep -c "dispatch_complete"` ≥ 1
    - `grep -c '"outcome"'` ≥ 1
    - `grep -c '"pr_url"'` ≥ 1
    - `grep -c "Exit /lifecycle entirely"` ≥ 1
    - `grep -c "remove the \.dispatching marker"` ≥ 1
    - `grep -c "cortex-cleanup-session.sh"` ≥ 1
    - `grep -c "no manual cleanup"` ≥ 1
    - `grep -c "worktree/agent-"` ≥ 1
    - §1 bullet-list visual order check: the first option after the `AskUserQuestion` prompt is "Implement in worktree", the second is "Implement on main", the third is "Create feature branch" (verifiable by reading §1).
  - **Pass 2 (§1a-scoped)**: extract the §1a block using `awk '/^### 1a\. Worktree Dispatch/,/^### [^1]/' /Users/charlie.hall/.claude/skills/lifecycle/references/implement.md > /tmp/claude/wt-dispatch-section.md` (or equivalent sed/awk), then run the following greps AGAINST the extracted block only — every check below must return the stated value:
    - `grep -c 'isolation: "worktree"' /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c 'name: "agent-' /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c "set -C" /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c "Do NOT call AskUserQuestion" /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c "sequential inline per-task dispatch" /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c "cycle 1 CHANGES_REQUESTED" /tmp/claude/wt-dispatch-section.md` ≥ 1
    - `grep -c '"outcome"' /tmp/claude/wt-dispatch-section.md` ≥ 1
    - The load-bearing literal strings appear inside the section, not only in prose outside it. This pass passes if every extracted-block grep matches.
- **Status**: [x] complete

### Task 3: Update SKILL.md Step 2 with marker check, worktree-aware phase detection, and branch-based skip conditions

- **Files**: `/Users/charlie.hall/.claude/skills/lifecycle/SKILL.md`
- **What**: Modify Step 2 in three places, all in a single atomic edit: (i) add a `.dispatching` marker check as the FIRST action inside Step 2 (after the directory-existence check, before any artifact-based phase detection). The check reads PID from line 1, runs `ps -p $PID`: alive → refuse to proceed with a message naming the PID and telling the user to wait or manually `rm` the marker; dead → prompt via AskUserQuestion (default: clean + proceed). (ii) Add worktree-aware phase detection that triggers when main's events.log has `dispatch_complete` as the most recent terminal event (no subsequent `feature_complete`). This block uses `git show-ref --verify --quiet refs/heads/worktree/agent-{slug}` to check the branch exists, then `git show worktree/agent-{slug}:lifecycle/{feature}/{artifact}` to read events.log/plan.md/review.md and apply phase detection against those values instead of main's stale on-disk copies. The three presented options via AskUserQuestion: continue-in-worktree (recommended; tells the user to `cd .claude/worktrees/agent-{slug}/` and re-invoke /lifecycle there), dispatch-fresh (surfaces the manual cleanup command block for the user to run), exit. The block runs BEFORE the artifact-based phase detection. (iii) Add a precondition to both the "Register session" sub-section AND the "Backlog Write-Back" sub-section: skip the respective write if the current branch matches `^worktree/agent-`. Include inline rationale that the dispatching main session owns these writes. Satisfies R6, R7 (Step 2 side), R14.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Current SKILL.md Step 2 layout is documented in `lifecycle/lifecycle-implement-worktree-dispatch/research.md` §"Codebase Analysis". The marker-check block MUST be the first action inside Step 2 — ordering is load-bearing because any downstream state detection otherwise runs on a stale view AND because the existing `hooks/cortex-scan-lifecycle.sh:285-291` has an auto-claim path that could overwrite `.session` files in ways the marker check is meant to prevent (see Scope Boundaries below). The branch-skip precondition specifically targets `^worktree/agent-` (the prefix produced by our dispatched agents — per TC2, this prefix is what makes cleanup work). Do NOT touch Step 3 or any later step.
- **Verification**: run all of the following grep checks against `/Users/charlie.hall/.claude/skills/lifecycle/SKILL.md` — every check must return the stated value:
  - `grep -c "\.dispatching"` ≥ 1
  - `grep -c "ps -p"` ≥ 1
  - `grep -c "dispatch_complete"` ≥ 1
  - `grep -cE "git show (worktree/)?agent-|git show worktree/agent-"` ≥ 1 AND `grep -c ":lifecycle/"` ≥ 1 (both required — confirms the `git show` is reading lifecycle artifacts from the worktree branch)
  - `grep -c "git show-ref"` ≥ 1
  - `grep -c "cd.*\.claude/worktrees/agent-"` ≥ 1
  - `grep -c "worktree/agent-"` in Step 2 text ≥ 2 (at minimum: one occurrence in the skip-condition for Register session, one in the skip-condition for Backlog Write-Back)
  - `grep -cn "^## Step 2"` = 1 (sanity: Step 2 heading still intact)
  - Visual ordering: the marker check appears before the artifact-based phase detection block (the reverse-order `if no lifecycle.*directory exists` prose). Verifiable by running `grep -n "\.dispatching" SKILL.md` vs `grep -n "if no lifecycle" SKILL.md` — the former's line number must be less than the latter's.
  - Skip-condition placement: the `^worktree/agent-` skip appears in both "Register session" and "Backlog Write-Back" sub-sections (verifiable by extracting each sub-section and grepping within).
- **Status**: [x] complete

### Task 4: Run acceptance verification against all 14 requirements

- **Files**: none modified (read-only verification task producing a report)
- **What**: Run the acceptance grep battery from each of R1–R14 in `lifecycle/lifecycle-implement-worktree-dispatch/spec.md` against the modified files. Produce a PASS/FAIL report per requirement. This task is the implementation-level gate before Review phase.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: The exact grep commands are listed verbatim in each requirement's Acceptance block in `lifecycle/lifecycle-implement-worktree-dispatch/spec.md` (R1 through R14). For R10's diff check, run `cd /Users/charlie.hall/Workspaces/cortex-command && git diff HEAD -- skills/lifecycle/references/complete.md` — expected output is empty. For R13's check, run `cd /Users/charlie.hall/Workspaces/cortex-command && git check-ignore lifecycle/test-feature/.dispatching` — expected exit 0. For the R14 ordering check, use `grep -n` to locate the marker-check and artifact-based phase detection blocks in SKILL.md and confirm the former's line number is less. For Task 2's scope-checked pass, extract §1a using `awk '/^### 1a\. Worktree Dispatch/,/^### [^1]/' skills/lifecycle/references/implement.md` and run the Pass-2 greps from Task 2's verification block against the extracted content. Report format: one row per requirement: `Rn: PASS|FAIL — <actual grep output if FAIL>`. Pass criterion: all 14 rows report PASS. Exit with FAIL status if any row fails and do NOT mark this task's plan checkbox `[x]` until all pass.
- **Verification**: Report has explicit PASS/FAIL per requirement. Pass if all 14 rows report PASS. Verification output is written to stdout only — do not create a report file in the repo.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification has three levels:

1. **Static (grep-based) verification — Task 4**: Runs each requirement's acceptance grep battery against the modified files. Passes if every R1–R14 grep matches.
2. **Structural scope check — embedded in Task 2**: Uses `awk` to extract the §1a section specifically and runs a narrower grep battery against the extracted block, catching the "string present somewhere in file but not inside §1a" false-positive that the bare file-wide greps allow.
3. **Runtime smoke test — deferred to Review phase**: The review phase will dispatch a real `/lifecycle` → "Implement in worktree" for a trivial feature, confirm the main session's branch stays on `main` (via `git branch --show-current` before and after), confirm the `.dispatching` marker is written/removed at the correct points, confirm the `worktree/agent-*` branch is created with commits, and confirm a PR URL appears in the `dispatch_complete` event. The spec's OQ-3 probe (Agent tool isolation) was run and resolved ISOLATED during Spec phase — no additional isolation probe needed.

## Veto Surface

- **Prompt template size inside §1a**: If the verbatim prompt template exceeds ~60 lines or becomes hard to read in a single code fence during implementation, flag it and consider splitting to a "skeleton in §1a, full template in a dedicated reference file" split. The spec does not lock this shape.
- **Sequential inline dispatch quality regression (TC4)**: Runtime smoke testing in Review phase may surface that inner-agent context runs out of room on features with >10 tasks. If so, the decision may need to change to non-isolated `Agent()` per-task calls — re-opens a design choice currently closed in the spec.
- **PID-based liveness false positives**: Rare PID reuse could falsely flag a marker as fresh. If smoke testing surfaces this, a time-based fallback may be needed as a second-order check.

## Scope Boundaries

Per spec Non-Requirements:

- `review.md` and `complete.md` are NOT modified.
- Per-task `Agent(isolation: "worktree")` behavior in §2 for the "Implement on main" and "Create feature branch" paths is NOT changed.
- No new branch-naming convention — `worktree/agent-{slug}` is dictated by `cortex-worktree-create.sh:30`.
- No events.log sync from worktree back to main (TC8).
- No budget/time/kill-switch for the dispatched agent.
- `hooks/cortex-cleanup-session.sh` is NOT modified.
- `hooks/cortex-scan-lifecycle.sh` is NOT modified. Note: its existing auto-claim behavior at lines 285–291 (when exactly one incomplete lifecycle exists and the fresh session's ID doesn't match) has historically been the source of FM-1 (session hijack). Our new `.dispatching` marker check in SKILL.md Step 2 runs BEFORE any auto-claim-adjacent behavior — this ordering is the invariant that protects against the hijack. The plan does not modify the hook because the ordering invariant is sufficient.
- "Implement in worktree" is not auto-promoted to default position; re-ordering is a future two-line edit.
- No tier or criticality restriction on the new option.
