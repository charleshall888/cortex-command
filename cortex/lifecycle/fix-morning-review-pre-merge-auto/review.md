# Review: fix-morning-review-pre-merge-auto

## Stage 1: Spec Compliance

### Requirement 1 (Must): Remove the pre-merge auto-close from SKILL.md Step 4, collapse to a soft forward-pointer stub carrying no close literal
- **Expected**: Step 4 body collapsed to a soft breadcrumb; `grep -crEi "update[-_]item.*--status complete" skills/morning-review/SKILL.md` = 0.
- **Actual**: Step 4 (SKILL.md lines 95-97) is now a two-sentence soft breadcrumb pointing closure to the post-merge path; no close literal in either spelling, no `cortex-read-backlog-backend` routing prose. Acceptance grep returns `0`. Step-4-to-Step-5 span `grep -icE "update[-_]item|cortex-read-backlog-backend"` = `0`.
- **Verdict**: PASS
- **Notes**: The step heading still reads "Auto-Close Backlog Tickets" though the step no longer closes — deliberate collapse-to-pointer per the plan (not delete+renumber); spec did not require renaming. Cosmetic only.

### Requirement 2 (Must): Add the §6b closure reference at the post-merge position, referenced exactly once, after the merge step
- **Expected**: `grep -n "Section 6b" skills/morning-review/SKILL.md` returns exactly one line, after the `### Step 6` / "PR Merge" heading; no §6b reference before the merge step.
- **Actual**: Exactly one `Section 6b` reference (line 118), inside Step 6 (heading at line 114), stating §6b closes each completed feature's ticket once merge and post-merge sync are confirmed. The collapsed Step 4 stub carries no `Section 6b` token.
- **Verdict**: PASS

### Requirement 3 (Must): Migrate the Step-4-unique handling into §6b completely (exit-2 disambiguation + no-confirmation guardrail)
- **Expected**: §6b (i) enumeration admits exit-2, (ii) adds a third `ambiguous slug` report state, (iii) preserves the candidate-list surfacing + re-invoke action, (iv) carries a soft no-per-feature-confirmation equivalent. Over the §6b span, `grep -ic "ambiguous"` ≥ 1 and `grep -ic "candidate"` ≥ 1.
- **Actual**: Enumeration line (walkthrough.md ~575) now reads "exits 0 … exits 1 silently … and exits 2 when the slug is ambiguous (it writes the matching candidate list to stderr)" — admits exit-2. Report list gained a third `ambiguous slug` entry (~588) with the candidate-list + re-invoke action. Exit-2 action prose (~578) surfaces the stderr candidate list and asks the operator to re-invoke with a disambiguated slug. No-confirmation guardrail carried at ~562 ("No per-feature confirmation is needed before closing — the confirmed merge is authoritative"). Span greps: `ambiguous` = 2, `candidate` = 3, `ambiguous slug` entry = 1, no-confirmation = 1.
- **Verdict**: PASS

### Requirement 4 (Must): The cortex-overnight mirror matches canonical at feature completion
- **Expected**: `just test` passes `test_dual_source_reference_parity.py`; drift gate clean; mirror is `plugins/cortex-overnight/skills/morning-review/`.
- **Actual**: `diff` of both SKILL.md and walkthrough.md against their mirrors is empty (IDENTICAL). `test_dual_source_reference_parity.py` = 59 passed. Full `just test` = 7/7 suites passed. Working tree clean.
- **Verdict**: PASS

### Requirement 5 (Must): Add a spelling-agnostic absence-based SKILL.md ordering regression test with durable positive controls
- **Expected**: (a) no close literal in either spelling anywhere in SKILL.md, matching both `update-item` and `update_item`; (b) exactly one `Section 6b` reference, after the "PR Merge" step (semantic anchor, never a step number, no `gh pr merge` literal). Demonstrated discriminating (fixed→green, reintroduced-console→red, reintroduced-module→red).
- **Actual**: `CLOSE_PATTERN = update[-_]item.*--status complete` (spelling-agnostic). Two guard tests (`test_skill_md_has_no_close_literal_in_either_spelling`, `test_skill_md_section_6b_single_and_post_merge`) plus two durable, CI-resident positive controls (`test_positive_control_close_pattern_matches_both_spellings`, `test_positive_control_ordering_check_flags_pre_merge_reference`). Ordering check anchors on the "PR Merge" heading text, not a step number or `gh pr merge`. Empirically verified discriminating: clean SKILL.md → not-present; module-form reintroduction → present; console-form reintroduction → present. All 7 tests in the file pass.
- **Verdict**: PASS

### Requirement 6 (Should): Add a soft "ticket remains open" note to the three genuinely-unmerged §6 exits (not the draft exits)
- **Expected**: Per-exit ticket-open clause at no-PR-found (§6 step 2 stop), declined-merge (§6 step 7), merge-failed (§6 step 6 failure); NOT the draft exits. Region-scoped, per-exit, requires the novel ticket-open clause.
- **Actual**: All three present — no-PR-found (~460 "backlog ticket remaining open — the work is on the integration branch, not main"), merge-failed (~507 "The feature's backlog ticket remains open …"), declined-merge (~510 same). Draft-PR sub-branch (~475-486) spot-check confirms no such note (correct). Soft declarative phrasing; no MUST tokens.
- **Verdict**: PASS

### Requirement 7 (Must): Add a verify-closure advisory to the "PR already merged" exit (§6 step 2)
- **Expected**: The already-merged exit prose contains a verify-tickets-closed advisory; `verify` (not `check`, to avoid false-green on the draft exit's pre-existing "check") + `ticket|complete`; no new close call.
- **Actual**: ~461-463: "PR already merged — main is up to date." Then stop. "Verify this session's completed-feature tickets are `complete` — the merge normally closes them, but a rare mid-session write failure could leave one open." Uses `verify`; references `tickets`/`complete`; no new close call added. Soft phrasing.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The new test constants/helpers (`SKILL` path constant, `CLOSE_PATTERN`, `_close_literal_present`, `_section_6b_ordering_violation`) follow the existing module's `WALKTHROUGH`/`MERGE_LITERAL`/`_first_occurrence` conventions. Skill prose keeps the established Section/Step vocabulary.
- **Error handling**: Appropriate for a prose-driven skill. §6 exit branches all use soft declarative language; no new imperative MUST/CRITICAL/REQUIRED tokens were introduced (verified by grep). The exit-2 path preserves the fail-loud candidate-list-surfacing action rather than silently dropping it.
- **Test coverage**: All plan verification steps executed and green. The Req-5 guard is proven discriminating durably (CI-resident positive controls) rather than via an ephemeral revert-demo, and I independently confirmed discrimination empirically (module-form and console-form reintroductions both flagged). Mirror parity (59 assertions) and the pre-existing walkthrough ordering tests stay green. Full `just test` 7/7.
- **Pattern consistency**: Follows project conventions — collapse-to-pointer (not delete+renumber), soft positive-routing phrasing per the MUST-escalation policy, canonical-only edits with the mirror regenerated and committed per-commit, structural test guard preferred over prose-only enforcement, and the change applies existing ADR-0004 (no new ADR) exactly as the spec's Technical Constraints require.
- **Minor observations (non-blocking)**: (1) The Step 4 heading text "Auto-Close Backlog Tickets" is now a slight misnomer since the step only breadcrumbs; the plan deliberately kept the heading, and no acceptance criterion is affected. (2) The Edge Cases table row "`update_item.py` exits non-zero for another reason → Report 'close failed (exit {N})'" also technically catches exit 2, which now has dedicated `ambiguous slug` handling in the §6b body — a minor summary-table overlap the spec did not scope. (3) Technical Constraints require filing the observed-merge auto-close follow-up ticket during Complete; that is a Complete-phase obligation still pending (expected at review), flagged here so it is not lost.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
