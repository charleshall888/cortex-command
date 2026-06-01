# Review: reconcile-lifecycle-complete-phase-on-main

## Stage 1: Spec Compliance

### Requirement 1: Finalization-tail artifact commit runs on all paths, no branch gate
- **Expected**: After Steps 9–11, commit runs on trunk / worktree-interactive post-merge / feature-branch post-merge with no branch gate. `cortex-read-commit-artifacts` referenced inside the anchored region. `grep -c 'cortex-read-commit-artifacts' skills/lifecycle/references/complete.md` = 2.
- **Actual**: `grep -c` yields 2 (one in Step 2, one in Step 11a). Step 11a carries no branch-guard conditional — it runs unconditionally for all callers that reach it. The Step 2 on-main short-circuit skips Steps 2–5 and proceeds to Step 7 → Steps 9–12 → Step 11a: trunk is covered. The worktree-interactive post-merge and feature-branch post-merge paths both reach Step 11a via re-invocation. No branch-test gate (`if [[ $branch == main ]]`) exists in the region.
- **Verdict**: PASS
- **Notes**: The stage-first guard (R2) does the safety work that makes branch-gating unnecessary; R1's "no branch gate" property holds by inspection of the anchored region.

### Requirement 2: Stage-first idempotent guard
- **Expected**: `git diff --cached --quiet` present; exit 0 → skip commit silently; exit 1 → commit. `grep -c 'git diff --cached --quiet' skills/lifecycle/references/complete.md` ≥ 1.
- **Actual**: `grep -c` yields 1. The anchored region (lines 264–271) instructs staging first, then running `git diff --cached --quiet`, with exit-0 → skip silently, exit-1 → proceed to commit. Behavior description matches the precedent in `post-refine-commit.md`.
- **Verdict**: PASS

### Requirement 3: Halt on commit failure
- **Expected**: Non-zero exit from `/cortex-core:commit` → surface error and stop before Step 12 summary. Soft positive-routing phrasing (no new MUST).
- **Actual**: Line 279: "If `/cortex-core:commit` exits non-zero, surface the error and stop before the Step 12 summary — a summary implying the artifacts were committed should not be emitted until the commit succeeds." Halt is unambiguously encoded. No MUST token in the diff (confirmed: grep count = 0).
- **Verdict**: PASS

### Requirement 4: commit-artifacts=false → skip entirely
- **Expected**: False-branch skips commit entirely; inline note that artifacts are left in working tree for operator to commit deliberately.
- **Actual**: Lines 238–239: "**Flag is `false`**: skip the commit entirely. Note inline that lifecycle artifacts and any uncommitted source are left in the working tree for the operator to commit deliberately." Exact behavior match; consistent with `post-refine-commit.md` and `plan.md §5`.
- **Verdict**: PASS

### Requirement 5: Staging set — enumerated lifecycle paths + cortex/backlog/ directory-scoped add
- **Expected**: Lifecycle dir staged by enumerated filenames (research.md, spec.md, plan.md, review.md, index.md, events.log). No `git add cortex/lifecycle/{slug}/` glob. Backlog write-back via `git add cortex/backlog/`.
- **Actual**: Lines 246–252 stage exactly the six enumerated files. Lines 256–259 stage `cortex/backlog/`. No `git add cortex/lifecycle/` glob appears anywhere in the file (confirmed by grep: no matches). Rationale for each choice is documented inline.
- **Verdict**: PASS

### Requirement 6: Commit step never routes into PR creation
- **Expected**: The anchored region contains no `git push` / `gh pr create` / PR-creation instruction.
- **Actual**: Both `git push` and `gh pr create` are absent from the anchored region (lines 234–286). `git push` and `gh pr create` appear only in Steps 3 and associated prose outside the region, which is legitimate.
- **Verdict**: PASS

### Requirement 7: No new event type
- **Expected**: `bin/.events-registry.md` gains no new event row. No `commit_authored`/`artifacts_committed`/`commit_failed` event introduced.
- **Actual**: `git diff 839f563c~1..839f563c -- bin/.events-registry.md` produces no output (zero lines). No new event type in the anchored region; commit observability is delegated to `git log` and `/cortex-core:commit`'s own error path, matching `post-refine-commit.md`'s discipline.
- **Verdict**: PASS

### Requirement 8: Structural guard test, scoped to the anchored step
- **Expected**: Test exists under `tests/`, extracts the anchored region, asserts positive tokens (cortex-read-commit-artifacts, /cortex-core:commit, git diff --cached --quiet, enumerated filenames, cortex/backlog/, halt-on-failure clause, main/master advisory), and negative tokens (git push, gh pr create, git add cortex/lifecycle/). Test is non-vacuous — missing anchor → AssertionError.
- **Actual**: `tests/test_complete_md_finalization_commit.py` implements exactly this structure. `_extract_region()` raises `AssertionError` if either anchor marker is absent (non-vacuous). Positive-token assertions cover all six enumerated filenames individually, the binstub, the commit skill, the guard, `cortex/backlog/`, a halt-tokens set ("stop", "halt", "do not"), and both "main" and "master". Negative assertions cover `git push`, `gh pr create`, and `git add cortex/lifecycle/`. Both tests pass (`just test` / `uv run python -m pytest tests/test_complete_md_finalization_commit.py` exits 0).
- **Verdict**: PASS
- **Notes**: One minor observation: the halt-token check uses a tuple `("stop", "halt", "do not")` and tests `any(t in region_lower ...)`, meaning any one of the three suffices. This is permissive but not vacuous — the region does contain "stop" (line 279), so the assertion binds correctly. A change removing the halt clause but leaving an unrelated "stop" word could silently pass, but that failure mode is low-probability for this specific region.

### Requirement 9: Parity tests stay green (post mirror-regen)
- **Expected**: `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0.
- **Actual**: 2 passed. The new step is in the finalization tail (after Step 11), downstream of all pause anchors (Steps 5/6). No pause anchor shifted; `AskUserQuestion` inventory unchanged. The new step also adds no `AskUserQuestion` call site (confirmed: no new entry needed in SKILL.md kept-pauses inventory).
- **Verdict**: PASS

### Requirement 10: MUST-escalation compliance
- **Expected**: `git diff skills/lifecycle/references/complete.md | grep -E '^\+' | grep -cE '\b(MUST|CRITICAL|REQUIRED)\b'` = 0.
- **Actual**: Running against the implement commit (839f563c): result = 0. No new MUST/CRITICAL/REQUIRED tokens introduced.
- **Verdict**: PASS

### Requirement 11: Stable structural anchor
- **Expected**: `<!-- finalization-commit-step -->` … `<!-- /finalization-commit-step -->` delimiters present. `grep -c 'finalization-commit-step' skills/lifecycle/references/complete.md` ≥ 1.
- **Actual**: `grep -c` yields 2 (opening and closing marker). Lines 234 and 286. The guard test (R8) binds to these exact strings — missing either marker produces an AssertionError. Anchor naming matches the spec's specified marker strings exactly.
- **Verdict**: PASS

### Requirement 12: Regenerate the cortex-core mirror before test verification
- **Expected**: `python3 -m pytest tests/test_dual_source_reference_parity.py` exits 0.
- **Actual**: 56 passed. The canonical `skills/lifecycle/references/complete.md` and mirror `plugins/cortex-core/skills/lifecycle/references/complete.md` are byte-identical (confirmed via `diff`). The commit message (839f563c) confirms both files were updated in the same commit.
- **Verdict**: PASS

### Requirement 13: Non-default-branch advisory
- **Expected**: After successful commit, if branch is not main/master, surface a one-line advisory referencing both `main` and `master`. No auto-checkout. Soft advisory phrasing.
- **Actual**: Lines 281–285: "After a successful commit, if the current branch is not `main` or `master`, surface a one-line advisory: `Artifacts committed on <branch> rather than the default branch — move them to main if appropriate.`" Both "main" and "master" present in the condition clause. Explicitly states "No automatic branch switch — branch normalization is deferred." No MUST token. Advisory is quoted as soft prose.
- **Verdict**: PASS

---

## Requirements Drift

**State**: detected

**Findings**:
- The `project.md` Multi-step lifecycle phases paragraph describes the Complete phase as creating a PR, exiting with a handoff message, and finalizing on re-invocation. It names `feature_complete` with `merge_anchor: "merge"` as the terminal event. It does not mention that all three completion paths (trunk, worktree-interactive post-merge, feature-branch post-merge) now commit lifecycle artifacts and backlog write-back at the finalization tail, or that a stage-first idempotent guard makes this safe across paths. This all-paths finalization commit is a new invariant that peers of the Complete phase description (e.g. someone reading project.md to understand what Complete does) cannot infer from the current text.

**Update needed**: `/Users/charlie.hall/Workspaces/cortex-command/cortex/requirements/project.md`

## Suggested Requirements Update

**File**: `cortex/requirements/project.md`

**Section**: Multi-step lifecycle phases (line 25)

**Content**:
```
Append to the Multi-step lifecycle phases bullet, after "Re-invocation routing is state-aware and idempotent":
"; the finalization tail (Steps 9–11a) commits lifecycle artifacts and the backlog write-back via a flag-gated, stage-first step on all completion paths (trunk, worktree-interactive post-merge, feature-branch post-merge)"
```

---

## Stage 2: Code Quality

- **Naming conventions**: The test file is named `tests/test_complete_md_finalization_commit.py` and the test functions are `test_finalization_commit_region_positive_tokens` / `test_finalization_commit_region_negative_tokens`. The precedent file is `tests/test_post_refine_commit_wired.py` with `test_post_refine_commit_*` names. The new names are slightly different in style (`_region_` infix vs no structural infix in precedent), but they are descriptive and unambiguous. The step label `Step 11a` is a clear interpolation of the existing `Step 11`/`Step 12` sequence without renumbering. The anchor name `finalization-commit-step` is stable and specific. Acceptable.

- **Error handling**: The halt-on-failure clause (line 279) is clearly worded and stops before the Step 12 summary, which is the correct gate. The false-branch skip (line 238–239) is explicit. The stage-first guard with exit-0/exit-1 branching is well-specified and idempotent. On commit failure the text instructs the operator to resolve and re-invoke, and names the specific Step 7 Branch 2 behavior on retry — giving the model enough context to narrate the recovery path to the user. The pattern is consistent with `post-refine-commit.md`'s Halt-Before-Plan Gate section.

- **Test coverage**: Both positive and negative test functions extract the anchored region via `_extract_region()`, which fails loudly on a missing or empty anchor (non-vacuous). Positive tokens cover the full required set: binstub, commit skill, guard command, all six enumerated filenames, `cortex/backlog/`, halt clause, and both branch names. Negative tokens guard against the three forbidden patterns (push, PR creation, lifecycle glob). The region-scoped checks correctly distinguish between Step 11a content and the legitimate PR-creation prose in Steps 3–5. The one gap noted in R8: the halt-token check with `any()` could in theory pass on an unrelated "stop" occurrence, but this is low-risk given the specificity of the region and the actual content.

- **Pattern consistency**: Step 11a follows `post-refine-commit.md`'s flag-check → staging → no-op guard → commit → halt-on-failure sequence exactly. The staging enumeration matches the precedent's "do not use a directory glob" discipline. The commit subject example (`Complete {slug}: lifecycle artifacts and backlog write-back`) follows the imperative-capitalized-≤72-char form in `post-refine-commit.md`. The "What and Why, not How" authoring principle is respected — the step names the decision points (flag check, staging set, guard outcome, halt) and explains intent without prescribing shell scripting verbatim beyond the two literal commands (`git add` and `git diff --cached --quiet`) that must be exact. MUST-escalation policy compliance is clean.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
