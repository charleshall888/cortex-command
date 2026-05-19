# Review: swap-implement-phase-preflight-option-2

## Stage 1: Spec Compliance

### Requirement 1: Rename option-2 label at the option-declaration site
- **Expected**: Line 19 of `skills/lifecycle/references/implement.md` bolded label reads `Implement on feature branch with worktree`; `grep -n '^- \*\*Implement on feature branch with worktree\*\* —' …` returns exactly one line near L19.
- **Actual**: L19 reads `- **Implement on feature branch with worktree** — …` (single match). Grep returns 1 line at position 19, exit 0.
- **Verdict**: PASS
- **Notes**: Landed by sibling #240 commit `92bbb434`. Spec compliance is satisfied regardless of which lifecycle commit produced the state.

### Requirement 2: Rewrite option-2 description body
- **Expected**: New description names worktree-interactive flow; "When to pick" clause variant-agnostic; no `.claude/` path; no MUST/REQUIRED/CRITICAL/MANDATORY tokens. All three grep acceptance checks pass.
- **Actual**: `grep -c 'When to pick'` returns 3; the option-2 block contains 0 MUST/REQUIRED/CRITICAL/MANDATORY tokens; 0 references to `.claude/`. The description references `$TMPDIR/cortex-worktrees/interactive-{slug}/` (sandbox-safe) and explicitly mentions Variant A vs Variant B with the note that dispatch is owned by epic #240.
- **Verdict**: PASS
- **Notes**: All three hard acceptance criteria pass. The "When to pick" clause ("medium/many-task features where you want an isolated branch with worktree but still need live steering") is variant-agnostic in substance. The description does name both Variants A and B, which marginally exposes implementation detail the spec's illustrative shape avoided — but this is documentation-style commentary, not a compliance failure against the acceptance criteria as written.

### Requirement 3: Update probe-routing prose at the exit-0 enumeration
- **Expected**: L39 bullet reads `all three options remain unchanged: …` with the new label string; `find_spec('cortex_command')` continues to appear in probe block.
- **Actual**: L39 reads `- **exit 0** → the cortex_command module is present → all three options remain unchanged: \`Implement on current branch\`, \`Implement on feature branch with worktree\`, and \`Create feature branch\`.` `grep -c "find_spec('cortex_command')"` returns 1.
- **Verdict**: PASS
- **Notes**: Both acceptance conditions hold.

### Requirement 4: Update probe-routing prose at the exit-1 rule
- **Expected**: L40 contains `remove \`Implement on feature branch with worktree\` from the options array`; silent-hide semantics preserved.
- **Actual**: L40 reads `- **exit 1** → the module is absent → remove \`Implement on feature branch with worktree\` from the options array; this is a silent hide …`. `grep -c 'silent hide'` returns 1.
- **Verdict**: PASS
- **Notes**: Both conditions hold.

### Requirement 5: Rewrite dispatch-by-selection branch as a prose anchor
- **Expected**: L46 reads `proceed to the worktree-interactive dispatch path (defined by ticket #240)` instead of `proceed to §1a`; `grep -cF 'proceed to §1b' …` returns 0.
- **Actual**: L46 reads `If the user selects **Implement on feature branch with worktree**, run the two interactive preflight guards below (Steps A and B) before proceeding to §1a. If either guard rejects, exit §1 without creating a worktree.` `grep -cF 'proceed to the worktree-interactive dispatch path'` returns 0. `grep -cF 'proceed to §1b'` returns 0.
- **Verdict**: PASS
- **Notes**: STALE per reviewer instructions. Sibling #240 retitled §1a (from "Daytime Dispatch" to "Interactive Worktree Creation") rather than leaving it untouched, so `§1a` is now an accurate citation rather than a dangling reference. The underlying intent of Requirement 5 — "avoid a dangling/incorrect section citation both pre- and post-#246 sweep" — is satisfied by #240's repurposing of §1a. The literal acceptance grep for `proceed to the worktree-interactive dispatch path` does not match, but the spec rationale (no dangling reference, no merge-collision risk) is met via a different mechanism. The plan annotates this honestly as "spec-Requirement-5-stale." Rating PASS against underlying intent per the reviewer's stale-requirement instruction.

### Requirement 6: Explicitly skip line 56 (§1a body opening sentence)
- **Expected**: After Phase 1 edits, exactly 1 literal `Implement in autonomous worktree` remains in `implement.md` (the surviving L56 reference).
- **Actual**: `grep -c 'Implement in autonomous worktree' skills/lifecycle/references/implement.md` returns 0. The literal `Implement in autonomous worktree` is gone entirely because #240 rewrote §1a wholesale (the old daytime-dispatch body was replaced with the interactive-worktree creation steps).
- **Verdict**: PASS
- **Notes**: STALE per reviewer instructions. The acceptance criterion (count == 1) is not met (count == 0), but the underlying intent — "do not waste effort renaming a line #246 will delete; do not create a merge conflict with #246's deletion sweep" — is satisfied via a different mechanism. #240 deleted/rewrote the body that contained the L56 reference, removing the merge-collision surface entirely (the deletion is now owned by #240's commit instead of #246's). The plan annotates this as "done-by-#240." Rating PASS against underlying intent.

### Requirement 7: Update kept-pauses inventory rationale at SKILL.md:199
- **Expected**: SKILL.md L199 rationale prose reads `branch selection on main: trunk vs feature-branch-with-worktree vs feature branch.`; `grep -c 'autonomous worktree' skills/lifecycle/SKILL.md` returns 0; `grep -c 'feature-branch-with-worktree'` returns ≥ 1.
- **Actual**: L199 reads `- \`skills/lifecycle/references/implement.md:22\` — branch selection on main: trunk vs feature-branch-with-worktree vs feature branch.` `grep -c 'autonomous worktree'` returns 0; `grep -c 'feature-branch-with-worktree'` returns 1.
- **Verdict**: PASS
- **Notes**: This is the actual residual work landed by commit `823a6e9f` in this lifecycle.

### Requirement 8: Write `blocked-by: ["239", "240"]` to backlog frontmatter
- **Expected**: `cortex/backlog/238-…md` frontmatter `blocked-by` parses to the canonical list `["239", "240"]`.
- **Actual**: Frontmatter contains `blocked-by: [240]` — only `"240"`, not `["239", "240"]`. The strict acceptance check (`uv run python3 -c "… sys.exit(0 if fm['blocked-by']==['239','240'] else 1)"`) exits 1.
- **Verdict**: PARTIAL
- **Notes**: The spec's strict acceptance criterion does not pass. However, sibling #239 has since reached `status: complete` (verified in `cortex/backlog/239-manage-interactive-feature-worktree-lifecycle.md`), so the original purpose of listing `"239"` in `blocked-by` (landing-gate defense-in-depth so the overnight runner skipped #238 until #239 was merge-ready) is moot — #239 is already merged. Retaining only `"240"` in `blocked-by` preserves the still-relevant landing gate and elides the now-stale `"239"` entry. The underlying intent (overnight runner skips #238 until dependencies are merge-ready) is satisfied. Strictly noting this as PARTIAL rather than PASS because the spec was explicit and the discrepancy was not annotated in the plan the way Requirements 5 and 6 are.

### Requirement 9: Plugin mirror regenerates from canonical without manual edits
- **Expected**: `diff skills/lifecycle/references/implement.md plugins/cortex-core/skills/lifecycle/references/implement.md` produces no output (exit 0).
- **Actual**: `diff` produces no output, exit 0. SKILL.md mirror also matches (exit 0).
- **Verdict**: PASS
- **Notes**: Pre-commit hook regenerated both mirrors correctly.

### Requirement 10: Existing tests pass without modification
- **Expected**: `tests/test_lifecycle_kept_pauses_parity.py` exits 0 AND `tests/test_daytime_preflight.py` exits 0.
- **Actual**: `uv run pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_daytime_preflight.py` collected 11 tests, all 11 passed.
- **Verdict**: PASS
- **Notes**: Output: `tests/test_lifecycle_kept_pauses_parity.py .. [ 18%]; tests/test_daytime_preflight.py ......... [100%]; 11 passed in 0.05s`.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: N/A — this lifecycle's commits only updated prose. The new label `Implement on feature branch with worktree` (landed by #240) is consistent with the other two option labels in shape: `Implement on current branch`, `Create feature branch`. The kept-pauses rationale rewrite preserves the existing `trunk vs … vs feature branch` triplet structure.
- **Error handling**: N/A — prose-only change.
- **Test coverage**: Both verification commands from the plan executed and pass. `uv run pytest tests/test_lifecycle_kept_pauses_parity.py tests/test_daytime_preflight.py` returned `11 passed in 0.05s`. The kept-pauses parity test verifies the file:line anchor at `skills/lifecycle/references/implement.md:22` still resolves (±35-line tolerance) — it passes despite Requirement 7's rationale prose change. The daytime preflight contract test still passes because §1a's invariants it asserts (`cortex-daytime-pipeline --feature`, mode tokens, helper script names) were preserved through #240's §1a rewrite, or the test has since been updated alongside #240 — either way, the contract holds in current HEAD.
- **Pattern consistency**: The actual residual landed by this lifecycle (SKILL.md:199 rationale refresh) is a single-line prose update inside an existing bullet, preserving the file:line anchor format used by the other 8 entries in the kept-pauses inventory. Consistent with project conventions.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Requirement 8: backlog frontmatter blocked-by is [240] instead of the spec's strict expected [\"239\", \"240\"]; #239 has since reached status:complete so retaining only \"240\" is semantically correct, but the discrepancy was not annotated in the plan the way Requirements 5 and 6 are."], "requirements_drift": "none"}
```
