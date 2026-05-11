# Review: artifact-template-cleanups-architectural-pattern-optional-indexmd-body-trim-frontmatter-preserved-d4-open-decisions-optional

## Stage 1: Spec Compliance

### Requirement 1: D1 — Architectural Pattern field in §3 default plan.md template
- **Expected**: Insert `**Architectural Pattern**: {category}` field in §3 Overview block with adjacent annotation *"Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise."* §1b critical-tier prompt and orchestrator-review P8 row unchanged. Acceptance: `grep -c "Architectural Pattern" skills/lifecycle/references/plan.md` = 4 AND enum-annotation grep ≥ 1 AND orchestrator-review.md Architectural Pattern count unchanged.
- **Actual**: Commit `4c4229d` inserts L142–143 in `skills/lifecycle/references/plan.md` directly after the Overview placeholder:
  ```
  **Architectural Pattern**: {category}
  <!-- Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise. -->
  ```
  Greps: `Architectural Pattern` count = 4 (baseline 3 + 1), enum-annotation grep = 1, `orchestrator-review.md` count = 1 (matches main baseline 1).
- **Verdict**: PASS
- **Notes**: Annotation form uses an HTML comment (`<!-- … -->`) rather than emphasis prose. The exact substring required by the spec is present verbatim, and HTML comments are a recognized pattern for non-rendering authoring guidance in other reference docs; this strengthens the closed-enum signal at authoring time without inflating rendered template output. Placement is the spec/plan-preferred "below the Overview placeholder, above `## Tasks`" anchor.

### Requirement 2: D2 — Scope Boundaries no-op
- **Expected**: No edit to `## Scope Boundaries` in plan.md. Acceptance: `grep -c "Scope Boundaries" skills/lifecycle/references/plan.md` returns the same count post-change as pre-change.
- **Actual**: Post-change count = 1, main baseline = 1. No edits to the Scope Boundaries section in any commit on this branch.
- **Verdict**: PASS
- **Notes**: Strictly a no-op; #182 retains ownership of the Outline replacement.

### Requirement 3: D3a — index.md SKILL.md template body emission
- **Expected**: SKILL.md "Create index.md" emits H1 wikilink + `Feature lifecycle for [[…]].` intro line only (no per-artifact wikilinks); all seven frontmatter fields preserved. Acceptance: `grep -c "Feature lifecycle for" skills/lifecycle/SKILL.md` ≥ 1 AND no `- {Phase}: [[…]]` patterns inside the "Create index.md" block.
- **Actual**: `Feature lifecycle for` count = 1, heading-anchored sed scan of the "Create index.md"→"Backlog Write-Back" block returns 0 per-artifact wikilink patterns. Frontmatter at L133–143 retains all seven fields (`feature`, `parent_backlog_uuid`, `parent_backlog_id`, `artifacts`, `tags`, `created`, `updated`) with `artifacts: []` in inline notation.
- **Verdict**: PASS
- **Notes**: D3a was already in target B1+ shape on `main` (verified via `git show main:skills/lifecycle/SKILL.md`); this is the verification-only outcome the plan's Veto Surface item 2 explicitly anticipates. No SKILL.md edit was needed and none was made.

### Requirement 4: D3b — plan.md index.md update step (no wikilink-append)
- **Expected**: `Add wikilink` instruction removed from plan.md index.md update step; `artifacts` append + `updated` behavior preserved. Acceptance: `grep -A 10 'If "plan" is already in the' … | grep -c "Add wikilink"` = 0.
- **Actual**: Commit `85cd4de` deletes L240–241 (the `Add wikilink` bullet and its `{lifecycle-slug}` continuation). Post-change grep count = 0. Surviving update-step block retains skip-if-present, append-to-array, update `updated`, rewrite atomically.
- **Verdict**: PASS
- **Notes**: Clean removal; the surrounding block is well-formed.

### Requirement 5: D3c — review.md index.md update step (no wikilink-append)
- **Expected**: Same as Req 4 for review.md. Acceptance: `grep -A 10 'If "review" is already in the' … | grep -c "Add wikilink"` = 0.
- **Actual**: Commit `85cd4de` deletes L150–151 in `skills/lifecycle/references/review.md`. Post-change grep count = 0.
- **Verdict**: PASS
- **Notes**: Identical shape to Req 4 deletion; consistent.

### Requirement 6: D3d — refine/SKILL.md research-step (no wikilink-append)
- **Expected**: Same as Req 4 for refine research-step. Acceptance: `grep -A 10 'If "research" is already in the' … | grep -c "Add wikilink"` = 0.
- **Actual**: Commit `85cd4de` deletes L142–143 in `skills/refine/SKILL.md` (Research). Post-change grep count = 0.
- **Verdict**: PASS

### Requirement 7: D3e — refine/SKILL.md spec-step (no wikilink-append)
- **Expected**: Same as Req 4 for refine spec-step. Acceptance: `grep -A 10 'If "spec" is already in the' … | grep -c "Add wikilink"` = 0.
- **Actual**: Commit `85cd4de` deletes L171–172 in `skills/refine/SKILL.md` (Spec). Post-change grep count = 0.
- **Verdict**: PASS

### Requirement 8: D4 — `## Open Decisions` optional in specify.md §3
- **Expected**: `## Open Decisions` heading in specify.md §3 carries an annotation containing `"Optional — omit when empty"` AND §2b Pre-Write "Open Decision Resolution" prose unchanged.
- **Actual**: `skills/lifecycle/references/specify.md` is untouched on this branch (`git log --oneline main..HEAD -- skills/lifecycle/references/specify.md` returns empty). `grep -c "Optional — omit when empty" skills/lifecycle/references/specify.md` = 0. Per plan Task 3 status `[-] deferred — Gate 2 prose still present on main (#183 not merged); strict-sequencing per plan Veto Surface item 1` and events.log batch 0 `defer_reason`, Task 3 was explicitly deferred to a #180-followup ticket and the user-approved plan committed to this strict-sequencing position.
- **Verdict**: N/A — T3 deferred to #180-followup
- **Notes**: Deferral verified live — `grep -c "Specify → Plan complexity escalation check" skills/lifecycle/SKILL.md` = 1 confirms #183 has not merged its Gate 2 deletion, validating the deferral rationale. This is a documented partial-scope marker, not a defect.

### Requirement 9: D4-sequencing — `blocked-by: [183]`
- **Expected**: backlog/180-… frontmatter contains `blocked-by: [183]`. Acceptance: `grep -E "^blocked-by:" backlog/180-… | grep "[183]"` matches.
- **Actual**: `grep -E "^blocked-by:" backlog/180-artifact-template-cleanups-architectural-pattern-scope-boundaries-indexmd.md` returns `blocked-by: [183]`.
- **Verdict**: PASS
- **Notes**: Frontmatter gate is in place; the runtime gate (Gate 2 prose absence check) is correctly recorded as N/A under the T3 deferral.

### Requirement 10: Mirror regeneration
- **Expected**: After canonical-source edits land, `plugins/cortex-core/skills/*` mirrors are clean. Acceptance: `just build-plugin && git diff --exit-code plugins/cortex-core/skills/` exits 0.
- **Actual**: Local invocation of `just build-plugin && git diff --exit-code plugins/cortex-core/skills/` exits 0. `diff -q` against each canonical/mirror pair (`skills/lifecycle/references/plan.md`, `…/review.md`, `skills/refine/SKILL.md`, `skills/lifecycle/SKILL.md`) confirms zero drift. Commits 4c4229d and 85cd4de each include matching mirror-side diffs (2 ins / 2 ins / 2 del × multiple files).
- **Verdict**: PASS
- **Notes**: Dual-source enforcement is functioning correctly; the pre-commit hook also exercised this on each commit.

### Requirement 11: Scope Boundaries 47.1% audit-number correction
- **Expected**: `grep -c "47.1%" lifecycle/.../spec.md` ≥ 1 AND no body-line edits to backlog/180-*.md or backlog/172-*.md (only frontmatter diffs allowed).
- **Actual**: `grep -c "47.1%" lifecycle/.../spec.md` = 1. `git diff main -- backlog/180-*.md backlog/172-*.md` shows a single change: `lifecycle_phase: implement → review` on backlog/180; backlog/172 unchanged. No body-line edits.
- **Verdict**: PASS
- **Notes**: Frontmatter `lifecycle_phase` advance is expected lifecycle-state mechanics, not a body-content edit.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

**Naming conventions**: Consistent with project patterns. The HTML-comment annotation form (`<!-- … -->`) introduced by Task 1 is a non-rendering authoring-guidance pattern; the comment text uses the exact closed-enum phrasing required by the spec.

**Error handling**: Not applicable — these are markdown template/instruction edits with no executable surface. The inserted lines and removed bullets are well-formed markdown that preserve the surrounding list structure (the surviving update-step bullets at the four D3 sites still parse as a cohesive list with skip-if-present / append-to-array / update-`updated` / rewrite-atomically steps).

**Test coverage**: Task 4 (`f261ded`) executed the spec's eleven-grep acceptance battery as the test surface, per the plan's Verification Strategy. All applicable greps were exercised and recorded in plan.md Task 4 status; Req 8 and the Gate 2 absence check are marked N/A under the T3 deferral. The plan-defect note in Task 4 status (the original `/^### 6\./` Gate-2 absence regex was structurally wrong because Step 6 is a numbered list item rather than a `###` heading) is constructively recorded for the #180-followup to use the corrected `grep -c "Specify → Plan complexity escalation check"` form — this is good post-implementation hygiene rather than a defect.

**Pattern consistency**: The HTML-comment annotation in Task 1 is consistent with how non-rendering authoring guidance is commonly carried in markdown templates; the alternative (italicized prose) would render in the produced plan.md and inflate authored artifacts, which contradicts the ticket's spirit. The four D3 deletions follow an identical shape across plan.md, review.md, and refine/SKILL.md, producing structurally uniform update-step blocks at every phase-write site. Mirror parity is maintained through the established dual-source enforcement; no edits were made to `plugins/cortex-core/skills/` directly.

**SKILL.md size cap**: All touched skill files are well under the 500-line cap — `skills/lifecycle/SKILL.md` (374), `skills/lifecycle/references/plan.md` (286), `skills/lifecycle/references/review.md` (215), `skills/refine/SKILL.md` (210), `skills/lifecycle/references/specify.md` (179, unchanged on this branch).

**MUST-escalation policy**: Confirmed not applicable — all changes are de-escalations (added field is optional; removed bullets are deletions; D4 deferral is also a de-escalation). No new MUST/CRITICAL/REQUIRED authoring on this branch.

**Workflow trimming hard-deletion preference**: Honored. The four `Add wikilink` instructions were hard-deleted (not deprecated or env-var-gated), and the post-deletion update-step blocks parse cleanly.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Requirement 8 (D4) deferred to #180-followup pending #183 Gate 2 deletion — strict-sequencing per plan Veto Surface item 1"], "requirements_drift": "none"}
```
