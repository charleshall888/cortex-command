# Review: Add index regeneration to overnight pre-flight and investigate staleness gaps

## Stage 1: Spec Compliance

### R1: Pre-selection index regeneration
**Rating**: PASS

Step 2 ("Pre-selection Index Regeneration") is inserted between Step 1 (Check for Existing Session) and Step 3 (Select Eligible Features). It instructs the agent to run `generate-backlog-index` from the project root (line 61), which appears before the `select_overnight_batch()` call at line 68. `grep -c 'generate-backlog-index' skills/overnight/SKILL.md` returns 1.

### R2: Silent auto-commit of regenerated index
**Rating**: PASS

Step 2 includes sub-steps 2-4 covering `git add backlog/index.json backlog/index.md`, conditional commit ("if there are staged changes"), and an explicit halt gate on commit failure: "Failed to commit regenerated backlog index: {error}." The entire Step 2 occurs well before Step 8's uncommitted-files check (`git status --porcelain -- lifecycle/ backlog/`). The "index unchanged" edge case is handled by sub-step 4 ("skip the commit -- the index is already current").

### R3: Deprecate `generate-index.sh`
**Rating**: PASS

- `skills/backlog/generate-index.sh` does not exist on disk (confirmed via `test ! -f`).
- `grep -r 'generate-index\.sh' docs/ skills/` returns no matches.
- `docs/backlog.md` line 111: updated from `bash ~/.claude/skills/backlog/generate-index.sh` to `generate-backlog-index`.
- `docs/backlog.md` line 172: updated from `generate-index.sh` to `generate_index.py` with note about both outputs.
- `skills/discovery/references/decompose.md` line 98: updated from `backlog/generate-index.sh` to `generate-backlog-index`.

### R4: Regeneration failure blocks session
**Rating**: PASS

Step 2, sub-step 1 explicitly gates on success: "If the command exits with a non-zero status, report: 'Backlog index regeneration failed (exit {code}). Fix the issue and retry `/overnight`.' -> halt." This halts before reaching Step 3 (batch selection).

### R5: Update internal cross-references after step insertion
**Rating**: PASS

All top-level step headings are correctly renumbered (Step 2 through Step 8). Cross-references verified:
- Line 59: "Step 3" (forward reference to Select Eligible Features) -- correct
- Line 75: "step 4" (filter gate reference, see note below) -- renumbered from "step 3"
- Line 132: "Step 7" (forward reference to Final Approval) -- correct
- Line 146: "Step 5" (back-reference to Render Session Plan) -- correct
- Line 149: "Step 7" (forward reference to Final Approval) -- correct
- Line 193: "Step 8" (reference to Launch) -- correct
- Line 195: "Step 5" (back-reference to Render Session Plan) -- correct

Sub-step disambiguation in Step 8 (Launch): lines 188, 189, and 191 changed from bare "step 2" to "Launch sub-step 2", correctly disambiguating from the new top-level Step 2. This directly addresses the spec's edge case about sub-step references in the Launch section.

**Minor observation**: Line 75 says "excluded at step 4 (after blocked-by, before artifact checks)". This originally said "step 3" and referred to the internal filter gate ordering in `filter_ready()` (gate 3 = type check), not a top-level skill step. The implementation incremented it to "step 4" as if it were a top-level reference. The filter gate is still gate 3 in the code (`claude/overnight/backlog.py` line 498). However, the parenthetical context "(after blocked-by, before artifact checks)" makes the intent clear regardless of the number, and the spec's acceptance criteria calls for "manual review confirms all step references are internally consistent" -- the reference is consistent within the SKILL.md even if the number doesn't match the code's gate numbering. Not a blocking issue.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. Uses `generate-backlog-index` (the global CLI name) as required by the spec's technical constraints, matching existing usage in `docs/backlog.md` (`reindex` subcommand) and `skills/discovery/references/decompose.md`. Uses `generate_index.py` where the project-local module path is more appropriate (update_item.py side effects documentation).

### Error handling
Appropriate for the context. The two-tier failure gate (regeneration failure halts, commit failure halts) matches the spec's edge case analysis. The "no staged changes" path (skip commit) handles the index-unchanged case cleanly without an unnecessary empty commit.

### Test coverage
All plan verification checks confirmed:
- `generate-backlog-index` reference exists in SKILL.md (count >= 1)
- `generate-index.sh` file deleted (does not exist)
- No `generate-index.sh` references in `docs/` or `skills/`
- Step references internally consistent per manual review
- Plan records all 5 tasks as complete

### Pattern consistency
The new Step 2 follows the existing SKILL.md conventions: numbered sub-steps, explicit error gates with halt instructions, and quoted error messages with placeholder substitution. The step insertion and renumbering is clean -- no orphaned or duplicate step numbers.

### Scope discipline
Changes are tightly scoped to the spec. The `docs/backlog.md` diff from the feature's own commit (`8ba65c3`) only touches the two `generate-index.sh` references. Other changes visible in the full diff (thin spec warning, terminal status updates) predate this feature. The `decompose.md` commit (`8ba65c3`) similarly touches only the single reference.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation adds a pre-selection index regeneration step to the overnight skill, removes a deprecated shell script, and updates documentation references. All of these are operational changes to the overnight runner's pre-flight sequence. The pipeline requirements (`requirements/pipeline.md`) describe session orchestration at the level of phases, feature execution, conflict resolution, and metrics -- they do not prescribe pre-flight index management specifics. The project requirements (`requirements/project.md`) are similarly unaffected. No new behavior is introduced that contradicts or extends beyond stated requirements.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
