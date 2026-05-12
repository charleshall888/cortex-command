# Review: lifecycle-implement-worktree-dispatch (cycle 1)

## Stage 1: Spec Compliance

### R1 — Third option present in pre-flight prompt: **PASS**
- `grep -c "Implement in worktree"` = 3 (≥ 1).
- Three options appear in documented order at `skills/lifecycle/references/implement.md:13-15`: "Implement in worktree" (recommended, first), "Implement on main", "Create feature branch". Dispatch-by-selection follows same order at lines 18-20.

### R2 — §1a documents Agent invocation verbatim: **PASS**
- `grep -c "### 1a. Worktree Dispatch"` = 1.
- Contains `name: "agent-{lifecycle-slug}"` (line 47), `isolation: "worktree"` (multiple, confirmed ≥ 1), and a verbatim prompt template in a fenced code block (lines 54-78).
- Model rule documented at line 50: sonnet for low/medium, opus for high/critical.

### R3 — Prompt instructs inner agent to skip session/backlog writes: **PASS**
- `grep -c "skip SKILL.md Step 2"` = 1 (line 58).
- Prompt names both "Register session" and "Backlog Write-Back" explicitly (line 58).

### R4 — Prompt forbids AskUserQuestion: **PASS**
- `grep -c "AskUserQuestion"` = 3 overall; appears within §1a prompt at line 61.
- Literal phrase "Do NOT call AskUserQuestion" present = 1.
- Fallback instruction and STOP-and-return for undocumented cases included (line 61).

### R5 — Sequential inline per-task dispatch with explicit commit mechanics: **PASS**
- (a) `grep -c "sequential inline per-task dispatch"` = 1 (line 64).
- (b) `grep -cE "no nested.*Agent.*isolation"` = 1 (line 65).
- (c) `grep -cE "no per-task.*sub-branches"` = 1 (line 66).
- (d) `grep -cE "skip.*§2e"` = 1 (line 68).
- (e) `grep -cE "commit.*directly to.*worktree/agent-"` = 1 (line 66).
- All five required mechanics present. Within-batch concurrency forfeit noted (line 67); batch-level dep ordering preserved; §2d `git log --oneline -N` checkpoint referenced as verification path.

### R6 — SKILL.md Step 2 detects dispatched-mode and skips session/backlog writes: **PASS**
- `grep -c "worktree/agent-"` in SKILL.md = 6 (≥ 1 in Step 2).
- Register session skip at `skills/lifecycle/SKILL.md:112` with rationale.
- Backlog Write-Back skip at line 186 with rationale. Both reference `^worktree/agent-` regex.

### R7 — `.dispatching` marker (atomic create + PID liveness): **PASS**
- (a) `grep -c "set -C"` in implement.md = 2 (≥ 1).
- (b) `grep -c "ps -p"` in SKILL.md = 1.
- (c) `grep -c "\.dispatching"` in implement.md = 3 (≥ 2: write before dispatch at line 33, remove after at line 86).
- (d) `grep -c "\.dispatching"` in SKILL.md = 3 (≥ 1).
- (e) Marker check at SKILL.md line 45 appears before artifact-based phase detection block (line 75+). Ordering confirmed.
- Liveness-based alive/dead branching with AskUserQuestion default-clean-and-proceed path documented at lines 49-51.

### R8 — Main session logs `implementation_dispatch` and `dispatch_complete`: **PASS**
- `grep -c "implementation_dispatch"` = 3 (≥ 1).
- `grep -c "dispatch_complete"` = 3 (≥ 1).
- `grep -c '"outcome"'` = 2 (≥ 1, values `complete|escalated`).
- `grep -c '"pr_url"'` = 2 (≥ 1, URL string or JSON `null`).

### R9 — Autonomous run, escalate on non-recoverable: **PASS**
- `grep -c "cycle 1 CHANGES_REQUESTED"` = 1 (line 72).
- `grep -c "cycle 2"` = 1 (line 73).
- `grep -c "REJECTED"` = 1 (line 73).
- `grep -c "test failure"` = 1 (line 73).

### R10 — Complete phase pushes worktree branch and creates PR: **PASS**
- `git diff main -- skills/lifecycle/references/complete.md` returns empty.
- `grep -c "Report the PR URL"` in implement.md = 1 (line 77).

### R11 — Main surfaces outcome and exits /lifecycle: **PASS**
- `grep -c "Exit /lifecycle entirely"` = 1 (line 96).
- `grep -c "remove the \.dispatching marker"` = 1 (line 86).

### R12 — Cleanup deferred to existing machinery: **PASS**
- Positive: `cortex-cleanup-session.sh` = 1; `no manual cleanup` = 1; `worktree/agent-` = 6 (all ≥ 1).
- Negative: within §1a block (lines 26 to next `###`), `git worktree remove` and `git branch -d` appear 0 times as orchestrator instructions. The only mention is the hook-implementation-detail parenthetical at line 102 (allowed per spec).

### R13 — `.dispatching` gitignored: **PASS**
- `grep -c "lifecycle/.*/\.dispatching"` in .gitignore = 1 (line 8: `lifecycle/*/.dispatching`).
- `git check-ignore lifecycle/foo/.dispatching` returns match, exit 0.

### R14 — Worktree-aware phase detection after dispatch_complete: **PASS**
- (a) `grep -c "dispatch_complete"` in SKILL.md = 1.
- (b) `grep -c "git show worktree/agent-"` = 3 (≥ 1).
- (c) `grep -c "git show-ref"` = 1.
- (d) `grep -cE "cd.*\.claude/worktrees/agent-"` = 1.
- Detection block at SKILL.md lines 53-73 appears BEFORE the artifact-based phase detection block (line 75+). Three-option AskUserQuestion present (continue-in-worktree, dispatch-fresh with manual cleanup, exit).

## Stage 2: Code Quality

- **Naming conventions**: Consistent with existing patterns. Event names (`implementation_dispatch`, `dispatch_complete`) align with the events.log vocabulary style. The `^worktree/agent-` regex reuses the hook-established convention.
- **Error handling**: Atomic create-or-fail via `set -C` plus PID liveness check handles the race and orphan cases specified. Collision path exits cleanly; dead-PID path prompts via AskUserQuestion with a default.
- **Test coverage**: No automated tests were required per the plan — the feature is documentation + gitignore edits. The acceptance-grep checks in the spec serve as the verification surface, and all pass.
- **Pattern consistency**: §1a sits alongside the existing §1 pre-flight using the same markdown structure (heading + numbered sub-steps with bold prefixes) used elsewhere in implement.md. Skip conditions in SKILL.md follow the same "Skip condition:" inline-precondition pattern already used in backlog status checks.

Minor observations (not blockers):
- §1a uses both "skip §2e" (lowercase) at line 68 — acceptance grep matches, style is fine.
- Cleanup parenthetical at line 102 is clear enough to satisfy the R12 negative check (mention of `git worktree remove` framed as hook behavior, not an orchestrator instruction).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
