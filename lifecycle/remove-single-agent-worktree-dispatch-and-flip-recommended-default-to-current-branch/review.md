# Review: remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch

## Stage 1: Spec Compliance

### Requirement R1: Three-option pre-flight prompt
- **Expected**: §1 presents exactly three options ("Implement on current branch" recommended, "Implement in autonomous worktree", "Create feature branch"); no "Implement in worktree"; no "four options".
- **Actual**: implement.md lines 13–15 show exactly three options in the prescribed order; "Implement on current branch" carries `(recommended)` suffix; "Implement in worktree" string is absent; "four options" is absent.
- **Verdict**: PASS
- **Notes**: The literal acceptance check `grep -cE '^- \*\*Implement' = 3` returns 2 because the third option ("Create feature branch") does not start with `**Implement`. This is a spec-criterion drafting bug (the original four-option menu had three options starting with "Implement" — after removal, only two remain). Implementation correctly delivers the spec's intent (three total options).

### Requirement R2: Option 3 rename in lock-step with routing match
- **Expected**: "Implement on main" → "Implement on current branch" in option text AND routing match. Acceptance: `grep -c 'Implement on main' = 0`; `grep -c 'Implement on current branch' >= 2`.
- **Actual**: `Implement on main` count = 0; `Implement on current branch` count = 2 (option label at line 13 + routing match at line 21).
- **Verdict**: PASS

### Requirement R3: §1 prompt text reflects three options
- **Expected**: `three options` >= 1; `four options` = 0.
- **Actual**: `three options` count = 1 (line 11); `four options` count = 0.
- **Verdict**: PASS

### Requirement R4: §1a (Worktree Dispatch) deleted in full
- **Expected**: No `### 1a. Worktree Dispatch` heading; no "Worktree Dispatch (Alternate Path)" string.
- **Actual**: Both grep counts = 0. Section is absent; the only `### 1a.` heading present is `### 1a. Daytime Dispatch`.
- **Verdict**: PASS

### Requirement R5: §1b renumbered to §1a
- **Expected**: `### 1a. Daytime Dispatch` exists; no `### 1b.` headings; no `§1b` references.
- **Actual**: `### 1a. Daytime Dispatch` count = 1; `### 1b.` count = 0; `§1b` count = 0.
- **Verdict**: PASS

### Requirement R6: implement.md §1 routing references updated
- **Expected**: "Worktree Dispatch alternate path" string removed; routing block has exactly three bullets matching the three options.
- **Actual**: "Worktree Dispatch alternate path" count = 0. Routing block at lines 19–22 has exactly three bullets, one per option in R1, all using "§1a (Daytime Dispatch alternate path below)" for autonomous worktree.
- **Verdict**: PASS

### Requirement R7: Worktree-agent context guard deleted
- **Expected**: `Worktree-agent context guard` count = 0.
- **Actual**: `Worktree-agent context guard` count = 0. Only the Uncommitted-changes guard remains at line 17 (#096 scope, intentional).
- **Verdict**: PASS

### Requirement R8: "Unlike §1a" reworded; no-marker explanation retained
- **Expected**: `Unlike §1a` count = 0; the `no .dispatching marker` explanation preserved.
- **Actual**: `Unlike §1a` count = 0; the renamed §1a opener at line 32 reads "There is **no `.dispatching` noclobber marker** on this path…" (matches `grep -cE 'no `?\.dispatching`? (noclobber )?marker' >= 1`), and the detached-background subprocess PID rationale follows.
- **Verdict**: PASS

### Requirement R9: SKILL.md "Dispatching Marker Check" sub-section deleted
- **Expected**: `Dispatching Marker Check` count = 0; `.dispatching` count = 0 in SKILL.md.
- **Actual**: Both counts = 0.
- **Verdict**: PASS

### Requirement R10: SKILL.md "Worktree-Aware Phase Detection" sub-section deleted
- **Expected**: `Worktree-Aware Phase Detection` count = 0.
- **Actual**: Count = 0. The `### Artifact-Based Phase Detection` heading at line 41 is the canonical detection path and is preserved as required by spec.
- **Verdict**: PASS

### Requirement R11: SKILL.md Register-Session worktree-agent skip condition deleted
- **Expected**: `Skip condition.*worktree/agent` count = 0.
- **Actual**: Count = 0.
- **Verdict**: PASS

### Requirement R12: SKILL.md Backlog-Write-Back worktree-agent skip condition deleted
- **Expected**: Combined with R11, `worktree/agent` count = 0 in SKILL.md.
- **Actual**: `worktree/agent` count = 0 in SKILL.md.
- **Verdict**: PASS

### Requirement R13: Cleanup-session hook worktree-prune block deleted
- **Expected**: `worktree/agent` count = 0; `Prune stale agent isolation` count = 0; `bash -n` exits 0.
- **Actual**: All counts = 0; `bash -n hooks/cortex-cleanup-session.sh` exits 0. The `.session` cleanup loop and trailing `exit 0` are preserved.
- **Verdict**: PASS

### Requirement R14: DR-2 reversal drift annotation in decomposed.md
- **Expected**: dated-blockquote annotation citing ticket #097 and issue #39886 inserted between DR-2 and DR-3 bullets.
- **Actual**: Annotation present at line 69 of decomposed.md, between DR-2 bullet (lines 65–67) and DR-3 bullet (line 71). All four greps pass: `ticket #097` = 1, `39886` = 1, `DR-2 reversed` = 1, `^> \*\*2026-04-22` = 1. Wording matches the spec verbatim.
- **Verdict**: PASS

### Requirement R15: Ticket 110 scope amendment note
- **Expected**: dated-blockquote annotation appended at the bottom of `## Out of scope` section.
- **Actual**: Annotation present at line 50 of backlog/110, immediately following the last `## Out of scope` bullet at line 48. `^> \*\*2026-04-22 \(ticket #097\)` count = 1. Annotation correctly cites both invalidated lines (41 and 48).
- **Verdict**: PASS

### Requirement R16: Ticket 123 scope amendment note
- **Expected**: dated-blockquote annotation; `three options` >= 1; `two options` >= 1.
- **Actual**: Annotation present at line 42. `^> \*\*2026-04-22 \(ticket #097\)` count = 1. `three options` count = 1. `two options` literal count = 0 BUT the annotation contains `**two** options` (markdown bold around "two") and `two-option graceful-degrade`. The semantic intent — naming the post-degrade two-option state — is satisfied.
- **Verdict**: PARTIAL
- **Notes**: The literal `grep -c 'two options'` acceptance criterion fails because the annotation wraps "two" in `**…**` markdown bold, splitting the literal substring. The semantic content (the post-degrade two-option state is named explicitly: "leaves **two** options ('Implement on current branch' / 'Create feature branch')") fully meets the spec's intent and the binding R14-shape requirements. Recommend either dropping the bold to satisfy the acceptance string verbatim or treating this as a known acceptance-criterion drafting nit (similar in class to R1's grep miscount). No code-correctness impact.

### Requirement R17: No code writer remains for worktree-mode dispatch events
- **Expected**: `grep -rnE '"mode"[[:space:]]*:[[:space:]]*"worktree"' skills/ hooks/ claude/ | wc -l` = 0.
- **Actual**: Count = 0.
- **Verdict**: PASS

### Requirement R18: Test file §1b regex updated in lock-step with R5
- **Expected**: `### 1b\.` count = 0; `### 1a\.` count >= 1; `Locate §1a section` count >= 1; pytest exits 0.
- **Actual**: `### 1b\.` = 0; `### 1a\.` = 1; `Locate §1a section` = 1; `pytest tests/test_daytime_preflight.py` reports `8 passed`.
- **Verdict**: PASS

### Requirement R19: Historical events.log feature_complete backfill
- **Expected**: backfilled `feature_complete` event in `lifecycle/archive/devils-advocate-smart-feedback-application/events.log`; `detect_lifecycle_phase()` returns "complete"; cross-file sweep returns no other cases.
- **Actual**: Line 13 of the events.log contains `{"ts":"2026-04-12T20:09:01Z","event":"feature_complete","feature":"devils-advocate-smart-feedback-application"}` — matches the no-space NDJSON convention used elsewhere in the file, uses dispatch_complete ts + 1s, and omits `tasks_total`/`rework_cycles` per spec. `python3 -c 'from cortex_command.common import detect_lifecycle_phase; ...'` returns `"complete"` (assertion passes). Cross-file sweep `for f in lifecycle/*/events.log; ... && echo` returns empty — no additional historical cases needing backfill.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- `requirements/multi-agent.md` lists "Multi-agent orchestration: parallel dispatch, worktree isolation, Haiku/Sonnet/Opus model selection matrix" in `requirements/project.md` In Scope and contains a "Worktree Isolation" functional requirement referencing `Agent(isolation: "worktree")` semantics. The multi-agent doc does not call out the (now removed) single-agent full-lifecycle `Agent(isolation: "worktree")` dispatch surface specifically — the surviving callers (per-feature parallel dispatch in SKILL.md Parallel Execution; per-task batch isolation in implement.md §2b) match the document's existing language ("Each feature executes in an isolated git worktree…", "feature branch naming follows `pipeline/{feature}` convention"). The removed surface used `worktree/agent-*` branches and a `.dispatching` marker — neither is named in multi-agent.md. So the removal does NOT contradict any currently documented behavior.
- However, there is a thin drift: project.md lists "worktree isolation" as in-scope generically without enumerating which dispatch paths use it, and the spec's Non-Requirements explicitly carve out that surviving `Agent(isolation: "worktree")` callers (SKILL.md Parallel Execution block; implement.md §2b per-task batch isolation) remain susceptible to issue #39886's silent-isolation-failure class. Neither requirements doc captures this risk surface. The change does not introduce new behavior; it removes one (undocumented at requirements level) caller and leaves a known-risk class on the survivors that the requirements docs do not acknowledge.
**Update needed**: `requirements/multi-agent.md` — optional add to "Edge Cases" or "Architectural Constraints" naming the silent-isolation-failure susceptibility for `Agent(isolation: "worktree")` callers.

## Suggested Requirements Update
**File**: `requirements/multi-agent.md`
**Section**: `## Edge Cases`
**Content**:
- **Silent isolation failure of `Agent(isolation: "worktree")`**: `anthropics/claude-code` issue #39886 reports that `Agent(isolation: "worktree")` may silently fail to create the isolated worktree, returning "success" while the agent in fact runs against the parent CWD. Surviving callers (SKILL.md Parallel Execution block per-feature dispatch; `skills/lifecycle/references/implement.md` §2b per-task batch isolation) remain susceptible. No mitigation is in place; tracking ticket TBD.

## Stage 2: Code Quality

- **Naming conventions**: All edits follow existing project conventions. The renamed `### 1a. Daytime Dispatch (Alternate Path)` heading mirrors the prior `### 1b.` heading style. The dated-blockquote annotation shape `> **2026-04-22 (ticket #097) — …** …` is consistent across all three drift annotations (R14/R15/R16) per the spec's pinned amendment-note shape.
- **Error handling**: No new error paths introduced. `cortex-cleanup-session.sh` continues to use `set -euo pipefail` and the surviving `.session` cleanup loop preserves the `|| continue` resilience pattern. The renamed §1a Daytime Dispatch retains all prior guards (plan.md prerequisite check, double-dispatch guard, overnight-concurrent guard).
- **Test coverage**: Task 8's pytest suite passes (8 tests). Task 9's six cross-file checks executed — R17 writer-surface grep returned 0; R19 pre-merge sweep returned empty; phase-detection runtime check returned `"complete"`; bash lint on cleanup hook exited 0. The plan-level pivot from spec's broken Python assertion (`detect_lifecycle_phase("string")`) to plan's corrected Path-typed call was caught and applied.
- **Pattern consistency**: The events.log backfill uses no-space NDJSON style (`{"ts":"..."}`) matching the other 12 lines of the file — consistent with the file-level convention. The annotation-shape consistency across decomposed.md, backlog/110, and backlog/123 follows the spec's "Amendment-note shape pinned across R14/R15/R16" technical constraint.
- **Commit hygiene**: Multiple commit-message-to-content misalignments occurred during parallel implementation sessions. Confirmed by inspection: commit `d553b04` ("Annotate DR-2 reversal in epic #074 decomposed.md") actually contains backlog/110's content; commit `9d8389b` ("Annotate scope amendment on backlog/123") swept Task 7's events.log backfill alongside; commit `053ef22` ("Land lifecycle 127") actually contains lifecycle 097's plan.md and events.log state-tracking changes. All required deliverables ARE in git history and on disk; the misalignment is a message-hygiene concern, not a content-correctness concern. Recommend in future overnight runs: serialize commits-per-feature within a session, or have the commit skill verify the staged-files-vs-message alignment before signing. The retry commit `5cb4afe` ("Annotate DR-2 reversal in decomposed.md (Task 4 retry)") indicates the issue was noticed and worked around but message-content drift persists in the historical record.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R16: literal grep acceptance for 'two options' fails because annotation wraps 'two' in markdown bold (`**two** options`); semantic intent is met via 'two-option graceful-degrade' phrase. Recommend dropping the bold to satisfy literal acceptance string. No functional impact.", "R1: spec acceptance criterion `grep -cE '^- \\*\\*Implement' = 3` is a spec-drafting defect — only two of the three options start with 'Implement' ('Create feature branch' is the third). Implementation correctly delivers three total options as required by spec text. Acceptance criterion should be amended in a future spec touch-up.", "Commit-message-to-content misalignments produced during parallel implementation sessions (commits d553b04, 9d8389b, 053ef22). All deliverables are present on disk and in git; only the message labels are wrong."], "requirements_drift": "detected"}
```
