# Plan: remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch

## Overview

Remove the single-agent `Agent(isolation: "worktree")` implement-phase dispatch path in a single atomic PR by rewriting `implement.md` §1 (three options, "Implement on current branch" recommended, §1a deleted, §1b renumbered to §1a), deleting the four orphaned SKILL.md sub-sections that exist only to support it, pruning the `worktree/agent-*` block from the cleanup hook, lock-step updating the one test file whose regex pins the §1b anchor, backfilling the one historical events.log entry that would otherwise misclassify post-deletion, and recording the DR-2 reversal as a dated blockquote at the single canonical location (the epic's `decomposed.md` DR-2 bullet) plus scope-amendment notes on the two downstream tickets (#110, #123) whose frontmatter and scope language are invalidated by the change.

## Tasks

### Task 1: Rewrite implement.md §1 pre-flight and §1a/§1b restructure
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Rewrite §1 to present three options ("Implement on current branch" recommended, "Implement in autonomous worktree", "Create feature branch"), delete §1a (the Worktree Dispatch alternate path, current lines 32–108), renumber former §1b to §1a, update all in-file cross-references and the post-selection routing block, delete the worktree-agent context guard (current line 18), and reword the opening paragraph of the renamed §1a to drop the "Unlike §1a" cross-reference while preserving the "no `.dispatching` marker" explanation.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Current `skills/lifecycle/references/implement.md` at the tip of `main`. Relevant regions:
        - Lines 11–16: four-option `AskUserQuestion` menu. Option at line 13 ("Implement in worktree") must be removed. Option at line 15 ("Implement on main") must rename to "Implement on current branch" AND lose `(recommended)` in favor of that suffix migrating to the new "Implement on current branch" option. Option at line 14 ("Implement in autonomous worktree") and line 16 ("Create feature branch") retain intent; their `When to pick` narrative survives.
        - Line 18: `**Worktree-agent context guard**:` paragraph — delete in full.
        - Line 20: `**Uncommitted-changes guard**:` paragraph — leave intact (option-3 guard, #096 scope).
        - Lines 22–26: post-selection dispatch block. Remove bullet routing to §1a. Update bullet for "Implement in autonomous worktree" to point to §1a (was §1b). Update bullet for "Implement on current branch" (formerly "Implement on main") to stay on current branch and proceed to §2.
        - Lines 32–108: entire `### 1a. Worktree Dispatch (Alternate Path)` section — delete.
        - Lines 110–228: `### 1b. Daytime Dispatch (Alternate Path)` — rename heading to `### 1a. Daytime Dispatch (Alternate Path)`. Reword opening paragraph (line 114: "Unlike §1a, there is **no `.dispatching` noclobber marker**…") to remove the §1a cross-reference while preserving the substantive explanation — the renamed section must still state there is no `.dispatching` marker and explain why (detached-background subprocess PID semantics). Proposed opener: "There is **no `.dispatching` noclobber marker** on this path — the `$$`-based mechanism is unsuitable for a detached background subprocess (the dispatching shell's PID `$$` dies milliseconds after the Bash call returns). The `daytime.pid` guard below is sufficient to prevent double-dispatch."
    - Spec R1–R8 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` lines 13–27.
    - Intro text change (R3): the `**Branch selection**:` line currently begins "If the current branch is `main` or `master`, prompt the user via AskUserQuestion with four options". Change `four` to `three`.
    - Lock-step rename (R2): option label "Implement on main" appears at line 15 AND in the routing match substring at line 25. Both must rename to "Implement on current branch" in one edit — either miss leaves selection dispatch broken.
    - §1b renumber (R5, R6-right): only heading line 110 changes; substantive §1b body is otherwise unchanged (Plan.md prerequisite check, Double-dispatch guard, Background subprocess launch, Polling loop, Result surfacing, Log events, Exit — all survive verbatim).
- **Verification**:
    - `grep -cE '^- \*\*Implement' skills/lifecycle/references/implement.md` = 3
    - `grep -c 'Implement in worktree' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Implement on main' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Implement on current branch' skills/lifecycle/references/implement.md` ≥ 2
    - `grep -c 'three options' skills/lifecycle/references/implement.md` ≥ 1
    - `grep -c 'four options' skills/lifecycle/references/implement.md` = 0
    - `grep -cE '^### 1a\. Worktree Dispatch' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Worktree Dispatch (Alternate Path)' skills/lifecycle/references/implement.md` = 0
    - `grep -cE '^### 1a\. Daytime Dispatch' skills/lifecycle/references/implement.md` = 1
    - `grep -cE '^### 1b\.' skills/lifecycle/references/implement.md` = 0
    - `grep -c '§1b' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Worktree Dispatch alternate path' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Worktree-agent context guard' skills/lifecycle/references/implement.md` = 0
    - `grep -c 'Unlike §1a' skills/lifecycle/references/implement.md` = 0
    - `grep -cE 'no `?\.dispatching`? (noclobber )?marker' skills/lifecycle/references/implement.md` ≥ 1
- **Status**: [x] done

### Task 2: Clean up SKILL.md worktree scaffolding (four deletions)
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Delete four blocks that exist solely to support the removed §1a path — Dispatching Marker Check sub-section, Worktree-Aware Phase Detection sub-section, the Register-Session worktree-agent skip condition, and the Backlog-Write-Back worktree-agent skip condition.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**:
    - Current `skills/lifecycle/SKILL.md`. Relevant regions:
        - Lines 41–51 (`### Dispatching Marker Check` heading through the "fall through to the rest of Step 2" bullet) — delete sub-section and heading in full. Rationale: the `.dispatching` marker is only written by §1a; with §1a gone, the check is reading a file no code writes.
        - Lines 53–73 (`### Worktree-Aware Phase Detection` heading through the "main's on-disk state is now authoritative" line) — delete sub-section and heading in full. Rationale: the override fires only when a `dispatch_complete` event exists without a subsequent `feature_complete` on a lifecycle whose `implementation_dispatch` used `mode: "worktree"`; with §1a removed, no new events of this shape are written. Historical events.log entries that WOULD still fire this detection logic are handled by R19 (Task 7). **Ordering constraint with Task 7**: This task must commit AFTER Task 7 — see `Depends on: [7]`. If Task 2 committed before Task 7 on the feature branch, the interval between the two commits would be a state where the override is deleted AND the `feature_complete` backfill is not yet present. In that interval, artifact-based phase detection would misclassify `lifecycle/devils-advocate-smart-feedback-application/` as `implement 0/4 tasks`, which any consumer running against feature-branch HEAD mid-PR would observe. By forcing Task 7 first, every feature-branch commit boundary sees a consistent state: before Task 7, the override masks the missing `feature_complete`; after Task 7, the backfill makes the override redundant; after Task 2, artifact-based detection is authoritative and correctly returns `complete`.
        - Line 112 (`**Skip condition**: if the current branch (via \`git branch --show-current\`) matches \`^worktree/agent-\`, skip this write. Rationale: the dispatching main session owns the `.session` file; a worktree agent running `/lifecycle` inside its own branch must not overwrite main's session registration.`) — delete entire paragraph. Rationale: no code path creates a worktree agent running `/lifecycle` post-#097.
        - Line 186 (`**Skip condition**: if the current branch (via \`git branch --show-current\`) matches \`^worktree/agent-\`, skip this entire sub-section. Rationale: the dispatching main session owns backlog write-backs; a worktree agent must not double-write \`status\`, \`session_id\`, or \`lifecycle_slug\` onto the backlog item.`) — delete entire paragraph. Same rationale.
    - The `### Artifact-Based Phase Detection` heading at line 75 must remain — it is the canonical detection path. It may need minor surrounding whitespace cleanup after R10 deletes the preceding sub-section.
    - Spec R9–R12 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` lines 29–35.
- **Verification**:
    - `grep -c 'Dispatching Marker Check' skills/lifecycle/SKILL.md` = 0
    - `grep -c '\.dispatching' skills/lifecycle/SKILL.md` = 0
    - `grep -c 'Worktree-Aware Phase Detection' skills/lifecycle/SKILL.md` = 0
    - `grep -c 'Skip condition.*worktree/agent' skills/lifecycle/SKILL.md` = 0
    - `grep -c 'worktree/agent' skills/lifecycle/SKILL.md` = 0
- **Status**: [x] done

### Task 3: Remove cleanup-session.sh worktree-prune block
- **Files**: `hooks/cortex-cleanup-session.sh`
- **What**: Delete the `# --- Prune stale agent isolation worktrees and branches ---` subshell block (current lines 36–60, including the closing `) || true`), preserving the preceding `.session` cleanup loop and the trailing `exit 0`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Current `hooks/cortex-cleanup-session.sh`. Relevant regions:
        - Lines 26–34: `.session` and `.session-owner` cleanup loop — unchanged.
        - Lines 36–60: the worktree-prune subshell block (starts with `# --- Prune stale agent isolation worktrees and branches ---` comment; ends with `) || true`). Delete in full.
        - Line 62: `exit 0` — unchanged.
    - The script remains valid bash after the block deletion; no other helpers reference the deleted state.
    - Spec R13 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` line 37.
- **Verification**:
    - `grep -c 'worktree/agent' hooks/cortex-cleanup-session.sh` = 0
    - `grep -c 'Prune stale agent isolation' hooks/cortex-cleanup-session.sh` = 0
    - `bash -n hooks/cortex-cleanup-session.sh` exits 0
- **Status**: [x] done

### Task 4: Annotate DR-2 reversal in decomposed.md
- **Files**: `research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md`
- **What**: Insert a dated blockquote annotation immediately after line 67 (the closing line of the DR-2 bullet `property the subprocess path cannot replicate.`) that records the ticket-#097 reversal and cites issue #39886 as the silent-isolation-failure reframing lens.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Current `research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md`. Relevant region:
        - Lines 65–67: the DR-2 bullet (`- **Co-exist, not replace** for worktree pre-flight options (DR-2). / Single-agent "Implement in worktree" retains live-steerability / property the subprocess path cannot replicate.`).
        - Line 68: blank line before DR-3 bullet.
    - Insertion point: between line 67 and line 68. Prefix with one blank line separating the bullet text from the blockquote; follow with one blank line before the DR-3 bullet.
    - Annotation text (verbatim from spec R14):

        ```
        > **2026-04-22 (ticket #097) — DR-2 reversed.** Option 1 ("Implement in worktree") was removed from the implement-phase pre-flight in full; this reverses the co-exist stance recorded above. Thin usage evidence is now also in doubt: `anthropics/claude-code` issue #39886 describes `Agent(isolation: "worktree")` silently failing to create isolation, so the single observed success may not have delivered its intended behavior.
        ```

    - The annotation is inserted **only** in `decomposed.md`; the sibling `research.md` is **not** modified (7+ downstream tickets cite it; their decomposition scope is unaffected by DR-2 reversal).
    - Spec R14 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` lines 39–45.
- **Verification**:
    - `grep -c 'ticket #097' research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md` ≥ 1
    - `grep -c '39886' research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md` ≥ 1
    - `grep -c 'DR-2 reversed' research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md` ≥ 1
    - `grep -cE '^> \*\*2026-04-22' research/implement-in-autonomous-worktree-overnight-component-reuse/decomposed.md` ≥ 1
    - Confirm by file read: the annotation appears between the DR-2 bullet (lines 65–67 pre-edit) and the DR-3 bullet.
- **Status**: [x] done

### Task 5: Annotate scope amendment on backlog/110
- **Files**: `backlog/110-unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception.md`
- **What**: Append a dated blockquote annotation at the bottom of the `## Out of scope` section recording that #097 has deleted the `.dispatching` marker check and Worktree-Aware Phase Detection override entirely, invalidating the ticket's "retain `.dispatching` marker check and worktree-aware override" language (line 41) and the "Overhaul of `.dispatching` or worktree-override logic" out-of-scope entry (line 48).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Current `backlog/110-unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception.md`. Relevant region:
        - Lines 45–49: `## Out of scope` section (2 bullets).
    - Insertion point: after line 48 (the last bullet `- Overhaul of \`.dispatching\` or worktree-override logic (they are override signals, not phase detection).`), as the final content in the `## Out of scope` section. Prefix with one blank line.
    - Annotation text (uses the R14 shape, draft below; structural elements — dated blockquote, `> **2026-04-22 (ticket #097) — ...`, ticket citation — are binding per spec constraint "Amendment-note shape pinned across R14/R15/R16"):

        ```
        > **2026-04-22 (ticket #097) — scope amendment.** The `.dispatching` marker check and Worktree-Aware Phase Detection override have been deleted in full from SKILL.md Step 2. The "retain `.dispatching` marker check and worktree-aware override" language above (line 41) and the "Overhaul of `.dispatching` or worktree-override logic" out-of-scope entry (line 48) no longer apply — neither override exists in post-#097 SKILL.md. `/refine` should re-evaluate scope against the reduced surface before planning.
        ```

    - Spec R15 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` line 47.
- **Verification**:
    - `grep -cE '^> \*\*2026-04-22 \(ticket #097\)' backlog/110-unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception.md` ≥ 1
    - Confirm by file read: the annotation appears inside or immediately below the `## Out of scope` section.
- **Status**: [x] done

### Task 6: Annotate scope amendment on backlog/123
- **Files**: `backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md`
- **What**: Append a dated blockquote annotation at the bottom of the `## Out of scope` section recording that the implement-phase menu has been reduced to three options (post-#097: "Implement on current branch" / "Implement in autonomous worktree" / "Create feature branch"), invalidating the ticket's "four execution modes" wording (line 25) and "show all four options as today" wording (line 33). The annotation must also note the semantic change on the degrade path: post-#097, a failed probe hiding "Implement in autonomous worktree" leaves **two** options not three.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Current `backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md`. Relevant region:
        - Lines 37–40: `## Out of scope` section (2 bullets).
    - Insertion point: after line 40 (last bullet `- Re-probing mid-session...`), as the final content in the `## Out of scope` section. Prefix with one blank line.
    - Annotation text (uses the R14 shape, draft below; structural elements binding per spec constraint):

        ```
        > **2026-04-22 (ticket #097) — scope amendment.** The lifecycle implement-phase menu is now three options (post-#097: "Implement on current branch" / "Implement in autonomous worktree" / "Create feature branch"), not four. The "four execution modes" framing above (line 25) and the "show all four options as today" probe-success branch (line 33) are superseded — the post-probe-success state shows three options. On the degrade path, hiding "Implement in autonomous worktree" now leaves **two** options ("Implement on current branch" / "Create feature branch"), not three. `/refine` must re-evaluate whether the two-option graceful-degrade still meets the UX intent of this ticket.
        ```

    - Spec R16 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` line 49.
- **Verification**:
    - `grep -cE '^> \*\*2026-04-22 \(ticket #097\)' backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md` ≥ 1
    - `grep -c 'three options' backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md` ≥ 1
    - `grep -c 'two options' backlog/123-lifecycle-autonomous-worktree-graceful-degrade.md` ≥ 1
- **Status**: [x] done

### Task 7: Backfill feature_complete event in devils-advocate events.log
- **Files**: `lifecycle/devils-advocate-smart-feedback-application/events.log`
- **What**: Append one NDJSON `feature_complete` event to the file so that `claude.common.detect_lifecycle_phase()` classifies this historical feature as `complete` via the artifact-ladder rule after Task 2 deletes the Worktree-Aware Phase Detection override. Without this backfill, artifact-based phase detection would misclassify the feature as `implement, 0/4 tasks` (reproduced against current tree: `detect_lifecycle_phase(Path("lifecycle/devils-advocate-smart-feedback-application"))` returns `'implement'` pre-backfill).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
    - Target file: `lifecycle/devils-advocate-smart-feedback-application/events.log`. Current tail as of spec approval: line 11 is `implementation_dispatch` with `"mode":"worktree"` at ts `2026-04-12T20:01:00Z`; line 12 is `dispatch_complete` with `"outcome":"complete"` and `"pr_url":"https://github.com/charleshall888/cortex-command/pull/3"` at ts `2026-04-12T20:09:00Z`. The `dispatch_complete` event has NO `mode` field — the worktree-mode indicator lives on `implementation_dispatch`, not `dispatch_complete`. (Spec R19's narrative is slightly misleading on this point; see Veto Surface note below.)
    - Event shape (append as one line — **no-space NDJSON style** to match the file's existing convention at all 12 prior lines):

        ```
        {"ts":"2026-04-12T20:09:01Z","event":"feature_complete","feature":"devils-advocate-smart-feedback-application"}
        ```

    - Timestamp: 1 second after the `dispatch_complete` event for narrative consistency. Do NOT fabricate `tasks_total` or `rework_cycles` fields — they are unknown for this historical case; `SKILL.md` Step 2's `feature_complete`-writing sections explicitly permit omitting them.
    - Pre-merge sanity sweep (belongs to the final Verification Strategy sweep via Task 9, not this task): enumerate every lifecycle whose `events.log` carries an `implementation_dispatch (mode: "worktree")` event AND lacks a `feature_complete` event. Use:

        ```
        for f in lifecycle/*/events.log; do
          grep -qE '"event":"implementation_dispatch"' "$f" \
            && grep -qE '"mode":"worktree"' "$f" \
            && ! grep -qE '"event":"feature_complete"' "$f" \
            && echo "$f"
        done
        ```

        Pre-Task-7 expected output: exactly one line — `lifecycle/devils-advocate-smart-feedback-application/events.log`. Post-Task-7 expected output: empty (no lines). If pre-Task-7 the loop surfaces additional files beyond devils-advocate, Task 7 scope expands to backfill each surfaced file before merge (see Veto Surface).
    - Spec R19 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` line 55.
- **Verification**:
    - `grep -c '"event":"feature_complete"' lifecycle/devils-advocate-smart-feedback-application/events.log` ≥ 1 (matches no-space NDJSON convention used throughout the file)
    - `python3 -c 'from pathlib import Path; from claude.common import detect_lifecycle_phase; p = detect_lifecycle_phase(Path("lifecycle/devils-advocate-smart-feedback-application")); assert p == "complete", p'` exits 0 (Path argument required: `detect_lifecycle_phase` signature is `(feature_dir: Path) -> str`; passing `str` raises `TypeError: unsupported operand type(s) for /: 'str' and 'str'` at `claude/common.py:113`)
- **Status**: [x] done

### Task 8: Update tests/test_daytime_preflight.py §1b regex to §1a
- **Files**: `tests/test_daytime_preflight.py`
- **What**: Update the hard-coded `### 1b\.` regex at line 334 to `### 1a\.` and the preceding comment at line 333 (`# Locate §1b section: ...`) to `# Locate §1a section: ...` so the test anchors the renamed Daytime Dispatch section after Task 1's R5 renumber.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
    - Current `tests/test_daytime_preflight.py` line 333–335:
        - Line 333: `# Locate §1b section: text between "### 1b." and the next "### " heading.`
        - Line 334: `match = re.search(r"### 1b\..*?(?=\n### )", text, flags=re.DOTALL)`
        - Line 335: `assert match is not None, "could not locate §1b section in implement.md"`
    - All three references to `1b` on lines 333, 334, and 335 update to `1a`. The test's structural assertions (invocation string present; no extra flags; plan.md before daytime.pid; result-reader invocation) are unaffected — only the section-anchor string changes.
    - Dependency: Task 1 must land first so that `### 1a. Daytime Dispatch` exists in implement.md; running pytest before Task 1 lands would fail the "could not locate §1a section" assertion.
    - Spec R18 in `lifecycle/remove-single-agent-worktree-dispatch-and-flip-recommended-default-to-current-branch/spec.md` line 53.
- **Verification**:
    - `grep -c '### 1b\\.' tests/test_daytime_preflight.py` = 0
    - `grep -c '### 1a\\.' tests/test_daytime_preflight.py` ≥ 1
    - `grep -c 'Locate §1a section' tests/test_daytime_preflight.py` ≥ 1
    - `pytest tests/test_daytime_preflight.py` exits 0
- **Status**: [x] done

### Task 9: Run cross-file verification sweep (final gate)
- **Files**: none (read-only verification task — no file modifications; no commit)
- **What**: Execute the six cross-cutting acceptance checks enumerated below as the pre-phase-transition gate. All six must pass before this task is marked `[x]`. Exists to convert the otherwise-advisory `## Verification Strategy` checks into an enforced `[ ]`-gated step that the implement-phase orchestrator recognizes — three of the six checks (#1, #2, #5) have no per-task coverage elsewhere and would silently skip without this task.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8]
- **Complexity**: simple
- **Context**:
    - The implement-phase transition (`skills/lifecycle/references/implement.md` §4, line 333: "When all tasks are `[x]`, determine the next phase...") fires automatically when the last task flips to `[x]`, with no step for executing cross-cutting checks and no prompt for user confirmation ("Proceed automatically — do not ask the user for confirmation before entering the next phase", line 352). Placing the checks under a `[ ]`-gated task forces the orchestrator to dispatch a builder that runs them; without this task, the checks are prose-only advisory and the review phase is read-only / Stage 2 advisory (`review.md` does not block on cross-file grep coverage).
    - The task performs no file modifications — builder reports success/failure per check. If the `/commit` skill errors on "no changes to commit," the builder reports that in its exit envelope and marks the task complete based on the successful check outputs alone. Do NOT create a throwaway file solely to satisfy `/commit`; that would be self-sealing verification.
    - Check specifics are below in Verification. The earlier `## Verification Strategy` section has been folded into this task's Verification.
- **Verification**: Run all six checks in order. Every check must pass before marking `[x]`.
    1. **R17 no-worktree-mode-writer sweep**: `grep -rnE '"mode"[[:space:]]*:[[:space:]]*"worktree"' skills/ hooks/ claude/ 2>/dev/null | wc -l` → output `0`. Matches both no-space (`"mode":"worktree"`) and space-after-colon (`"mode": "worktree"`) NDJSON styles via `[[:space:]]*`. Confirms R17: no surviving code writes `implementation_dispatch` or `dispatch_complete` with worktree mode.
    2. **R19 pre-merge historical sweep**: the loop `for f in lifecycle/*/events.log; do grep -qE '"event":"implementation_dispatch"' "$f" && grep -qE '"mode":"worktree"' "$f" && ! grep -qE '"event":"feature_complete"' "$f" && echo "$f"; done` → empty output (zero lines). Confirms no lifecycle has a worktree-mode `implementation_dispatch` trace without a `feature_complete` terminator. Post-Task-7, the one known case (devils-advocate-smart-feedback-application) now has `feature_complete`. If the loop emits any file, scope expansion applies and Task 7 must re-open to backfill each surfaced file (see Veto Surface).
    3. **Phase-detection runtime check**: `python3 -c 'from pathlib import Path; from claude.common import detect_lifecycle_phase; p = detect_lifecycle_phase(Path("lifecycle/devils-advocate-smart-feedback-application")); assert p == "complete", p'` → exit 0. Confirms `claude.common.detect_lifecycle_phase()` — used directly by `claude/dashboard/data.py:40` — classifies the backfilled feature as `complete`. The two bash reimplementations (`claude/statusline.sh` phase-detection block, `hooks/cortex-scan-lifecycle.sh:170-207` plus the resume-prompt injection block at lines 305-337) mirror the same reverse-order algorithm (scan for `feature_complete` event); their semantic equivalence is guaranteed by the `# Mirrors claude.common.detect_lifecycle_phase — keep in sync if phase model changes` contract at `cortex-scan-lifecycle.sh:168`. Unifying the three implementations is ticket #110's scope, not #097's.
    4. **Full test suite**: `just test` → exit 0. Covers Task 8's pytest plus any adjacent tests that observe implement.md / SKILL.md / cleanup-session.sh changes.
    5. **Symlink health**: `just check-symlinks` → exit 0. Confirms the deployed `skills/*` and `hooks/*` symlinks resolve correctly after the file rewrites.
    6. **Bash lint on cleanup hook**: `bash -n hooks/cortex-cleanup-session.sh` → exit 0. Redundant with Task 3's verification; final seatbelt.
- **Status**: [x] done

## Verification Strategy

End-to-end verification for this feature is implemented as **Task 9** above — a status-gated cross-file sweep that runs six cross-cutting checks (R17 writer-surface grep; R19 pre-merge historical sweep; `detect_lifecycle_phase()` runtime check; `just test`; `just check-symlinks`; `bash -n` on the cleanup hook). Task 9 depends on all of Tasks 1–8, so the implement-phase orchestrator cannot transition to review/complete until the sweep has executed and its checks have passed. Task ordering (Batch 0: 1, 3, 4, 5, 6, 7; Batch 1: 2 and 8; Batch 2: 9) keeps the feature branch in a consistent state at every commit boundary: Task 7's `feature_complete` backfill commits before Task 2's override deletion (see Task 2's Context note on "Ordering constraint with Task 7").

## Veto Surface

- **Drift-note location** is settled at `decomposed.md` (Task 4 only) — not the sibling `research.md`. Rationale: `research.md` is cited by 7+ downstream tickets (074, 075, 076, 077, 078, 079, 080) whose modularization decomposition is unaffected by DR-2 reversal; a top-level "Superseded-by" banner there would incorrectly imply the whole epic is reversed. The user confirmed this during /refine (decision T). Reopen only if new evidence shows downstream readers are missing the reversal context.
- **Single-PR atomic rollout** is settled (decision M). Two-PR staging (routing change → destructive cleanup) would create an intermediate state where routing is gone but §1a body and SKILL.md overrides are still live — a reachable "broken but present" state during rollout. Commit-graph granularity within the PR is handled by Task 2's `Depends on: [7]` and Task 9's final gate; merge strategy is not pinned (this is a single-developer repo with per-task-commit convention per recent `git log` — squash-merge would collapse further, standard merge preserves the ordered commit chain). Reopen only if a CI or review-process constraint forces staging.
- **R14 annotation naming issue #39886** is settled (decision: two-sentence reframe). Reopen only if the issue reference is later found to describe a distinct class of failure from the one observed here.
- **R19 backfill scope** is settled at one file (devils-advocate-smart-feedback-application). The pre-merge loop in Task 9 Verification check #2 is the expansion tripwire — if it emits any additional file, Task 7 re-opens to include each surfaced file before PR merge.
- **Annotation exact wording for R15/R16** is proposed but not verbatim-locked by the spec (only the shape is binding). The implementer may refine wording within the dated-blockquote shape, as long as the invalidated lines (line 41/48 for #110; line 25/33 for #123) are named and `/refine` re-evaluation is flagged.
- **Spec-level grep/Python verification bugs flagged during plan-phase critical review**: spec R19 acceptance (`spec.md` line 55) and spec Technical Constraints line 112 carry the same class of defects this plan fixes — the pre-merge grep targets `dispatch_complete` rather than `implementation_dispatch` (wrong event type for the `mode` field; reproduced against `devils-advocate-smart-feedback-application/events.log`), and the Python assertion passes a `str` where `detect_lifecycle_phase` requires `Path` (raises `TypeError` at `claude/common.py:113`). The plan's Task 7 Verification and Task 9 Verification supersede for execution purposes; the spec artifact itself is not amended in-scope for #097 (would require re-approval). The implementer should verify the plan's commands pass and NOT copy-paste the spec's commands when running acceptance. A follow-up spec amendment can land opportunistically in a subsequent ticket.

## Scope Boundaries

Maps to spec Non-Requirements (`spec.md` lines 58–71):

- Option 2 (autonomous worktree / daytime pipeline) behavior is unchanged — only the section number changes (R5 renumber).
- Option 3's `#096` uncommitted-changes guard is unchanged. Gaps in porcelain's default behavior (gitignored, stashes, local overrides) remain #096's scope.
- Option 4 ("Create feature branch") behavior is unchanged.
- Per-task `worktree/{task-name}` branches (from `cortex-worktree-create.sh` during §2b concurrent per-task dispatch) are unaffected — Task 3's regex targets only `worktree/agent-*`.
- `Agent(isolation: "worktree")` usage in SKILL.md Parallel Execution block and implement.md §2b (per-task batch isolation) is unaffected — only the single-agent full-lifecycle use from §1a is removed.
- No ADR directory or drift-log file creation — inline DR bullets remain the repo convention.
- Criticality-aware demotion of "Implement on current branch" is deferred.
- Cleanup of `outer-probe` / `env-probe-outer` worktrees currently on disk is out of scope (no tracking ticket filed).
- Issue #39886's silent-isolation-failure affects surviving `Agent(isolation: "worktree")` callers (SKILL.md Parallel Execution; implement.md §2b) — out of scope for #097.
- Existing `.dispatching` marker files on disk are not swept — post-Task 2 no code reads them.
- `claude/pipeline/metrics.py::_DAYTIME_DISPATCH_FIELDS` docstring cosmetic drift is not corrected.
- Future-drift tripwire for option-3's label is not added beyond R2/R6 lock-step check.
- Historical `dispatch_complete (mode: "worktree")` events other than the one backfilled by Task 7 remain on disk as read-only history — no rewrite.
