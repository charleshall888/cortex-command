# Review: lead-refine-4-complexity-value-gate

## Stage 1: Spec Compliance

### Requirement 1: §4 bullet rewritten (single logical bullet at the Complexity/value gate anchor)
- **Expected**: `grep -c "Complexity/value gate" skills/refine/SKILL.md` = 1 AND `grep -c "I recommend\|recommend " skills/refine/SKILL.md` ≥ 1 AND `grep -c "AskUserQuestion" skills/refine/SKILL.md` ≥ 1. The rewrite must preserve the trigger conditions, introduce per-feature recommendation, announce with one-sentence rationale, and conditionally call AskUserQuestion.
- **Actual**: `grep -c "Complexity/value gate" skills/refine/SKILL.md` = 2. The anchor appears at line 166 (the §4 bullet) and again at line 170 (the Hard Gate cross-reference: "...interacts with refine's existing **§4 (User Approval) — Complexity/value gate** adaptation above..."). The line 170 occurrence is a back-reference in the Hard Gate bullet that pre-existed the edit — it was present in the file before the §4 rewrite and is not a second gate definition. The semantic intent of the acceptance criterion (anchor preserved, single logical gate definition) holds. `recommend ` = 2 (passes ≥ 1). `AskUserQuestion` = 2 (passes ≥ 1). The §4 prose correctly contains all four required sub-elements: (a) identical trigger conditions, (b) recommendation step, (c) one-sentence rationale phrased as "I recommend X because Y.", (d) conditional AskUserQuestion.
- **Verdict**: PASS
- **Notes**: The `grep -c` = 1 literal acceptance check fails (actual = 2), but the spec author acknowledged this counting artifact and identified it as a miscounted pre-existing cross-reference. The semantic anchor — a single logical gate definition — is preserved. The second occurrence is a back-reference inside an adjacent bullet (Hard Gate), not a duplicate gate definition. The implementation satisfies the requirement's intent, and the dispatch brief explicitly asks whether this deviation is FAIL or PASS. It is PASS: the back-reference was present before the edit (it references "the adaptation above"), anchor preservation holds, and the prose shape is correct.

### Requirement 2: `(Recommended)` capital-R label suffix specified in §4 prose
- **Expected**: `grep -c "(Recommended)" skills/refine/SKILL.md` ≥ 1, located within the §4 bullet.
- **Actual**: `grep -c "(Recommended)" skills/refine/SKILL.md` = 2. Both occurrences are on lines 166 and 168, both inside the §4 bullet block (line 166 = prose instruction, line 168 = worked example). The suffix is specified with the literal text ` (Recommended)` (single leading space, capital R), with explicit instructions that lead option labels end with this suffix.
- **Verdict**: PASS
- **Notes**: Count of 2 (≥ 1) satisfies the acceptance check. Both occurrences are within §4.

### Requirement 3: Conditional fire encoded in prose
- **Expected**: `grep -E "only when|unless|when the recommendation" skills/refine/SKILL.md` returns a match inside the §4 bullet.
- **Actual**: The §4 bullet at line 166 contains: "Call `AskUserQuestion` only when the recommendation is not full scope OR when confidence is low." Both "only when" and "when the recommendation" appear within that sentence, inside the §4 bullet. Grep returns a match.
- **Verdict**: PASS

### Requirement 4: Downsize-option labels carried through
- **Expected**: `grep -c "drop entirely"` ≥ 1, `grep -c "bugs-only"` ≥ 1, `grep -c "minimum viable"` ≥ 1, `grep -c "Confirm current scope"` ≥ 1.
- **Actual**: `drop entirely` = 2, `bugs-only` = 1, `minimum viable` = 2, `Confirm current scope` = 2. All four labels present. `Confirm current scope` is introduced as the lead option for the AskUserQuestion pick-menu when the gate fires. The three downsize candidates are explicitly enumerated in §4 with descriptions matching the spec.
- **Verdict**: PASS

### Requirement 5: Kept-user-pauses inventory updated in skills/lifecycle/SKILL.md
- **Expected**: A new bullet under `### Kept user pauses` pointing to the AskUserQuestion call site in `skills/refine/SKILL.md` with the format `- \`skills/refine/SKILL.md:<line>\` — <rationale>`. Rationale notes conditional nature. `pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0.
- **Actual**: Line 202 of `skills/lifecycle/SKILL.md` reads: `- \`skills/refine/SKILL.md:166\` — refine §4 complexity-value gate pick-menu — renders only when the orchestrator's recommendation diverges from full scope or confidence is low; otherwise the announcement folds into the regular approval surface.` The rationale correctly notes the conditional nature. Both parity tests pass (2/2, exit 0).
- **Verdict**: PASS
- **Notes**: The inventory references line 166 — the §4 bullet itself. The actual `AskUserQuestion` keyword appears on lines 166 and 168 (both in the §4 bullet block). Line 166 is within ±35 lines of both occurrences (diff = 0 and 2 respectively). Parity test passes.

### Requirement 6: New test file at tests/test_refine_skill.py with four regex assertions
- **Expected**: (a) `\(Recommended\)` within 35 lines of anchor, (b) `I recommend`/`recommend ` inside §4 bullet, (c) `rationale`/`because` between anchor and `(Recommended)`, (d) `MUST decide` NOT in §4 bullet. `pytest tests/test_refine_skill.py` exits 0 AND `grep -c "def test_" tests/test_refine_skill.py` ≥ 4.
- **Actual**: File exists at `tests/test_refine_skill.py` with exactly 4 test functions (`test_recommended_suffix_within_35_lines_of_anchor`, `test_recommend_trigger_inside_section_4_bullet`, `test_rationale_or_because_precedes_recommended`, `test_no_must_decide_regression`). All 4 tests pass (exit 0). `grep -c "def test_"` = 4, satisfying ≥ 4. Assertions match the spec's four-point description precisely.
- **Verdict**: PASS

### Requirement 7: No new MUST/REQUIRED/CRITICAL in §4 amendment
- **Expected**: Amendment text uses declarative verbs ("Decide", "Announce", "Call") rather than `MUST decide` / `MUST announce`. Covered by Req 6(d) negative assertion.
- **Actual**: `grep -n "MUST\|REQUIRED\|CRITICAL" skills/refine/SKILL.md` returns no matches. The §4 bullet uses declarative verbs: "check", "decide", "Announce", "Call", "fold", "Carry through". No MUST-escalated language present. `test_no_must_decide_regression` passes.
- **Verdict**: PASS

### Requirement 8: Plugin mirror regenerates
- **Expected**: `plugins/cortex-core/skills/refine/SKILL.md` overwrites to match canonical `skills/refine/SKILL.md` after `just build-plugin`. `diff` of the §4 section exits 0.
- **Actual**: `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` exits 0 (files are byte-identical). `diff skills/lifecycle/SKILL.md plugins/cortex-core/skills/lifecycle/SKILL.md` exits 0. Both mirrors are fully in sync with canonical sources. The events.log records a sandbox EPERM during implementation (Bash tool blocked `just build-plugin`), so the implementer used the Write tool to sync the mirrors manually — the end state is identical.
- **Verdict**: PASS
- **Notes**: The mechanism of sync (Write tool vs `just build-plugin`) is an implementation detail forced by the sandbox constraint documented in events.log. The observable gate condition — parity between canonical and mirror — is satisfied.

## Requirements Drift
**State**: none
**Findings**:
- None. The implementation is strictly within the scope defined by the spec. No new state files, config flags, events, or SKILL.md surface changes outside the specified files were introduced. The project.md Philosophy of Work principles (complexity earns its place, simplicity wins, prose-before-implementation) are respected: the change is minimal, adds no persistence, and encodes the gate as skill control-flow prose rather than a separate module. The MUST-escalation policy (CLAUDE.md §72–84) is observed — no new escalations were introduced.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the codebase. The `(Recommended)` label suffix uses the same capitalization style as existing `AskUserQuestion` option labels in the lifecycle skill family. The inventory bullet follows the exact `\`file:line\` — rationale` format used by the nine existing entries. Test function names are snake_case with descriptive verbs matching the project test style.
- **Error handling**: Not applicable for this change — no new executable code was introduced; the change is entirely prose-in-SKILL.md. The test file has appropriate `pytest.fail` calls in helpers to surface locator failures with actionable messages rather than silent assertion errors.
- **Test coverage**: The four assertions cover the four behavioral properties required by the spec: proximity (anchor → label), trigger presence (recommend phrase), ordering invariant (rationale before label), and regression guard (no MUST drift). The `_slice_section_4` helper correctly bounds the §4 block by the next top-level bullet (`- **`), preventing false negatives from matches in later sections. The `_line_of` helper is clean. One minor gap: the worked example on line 168 is inside the §4 slice and contains `(Recommended)` — so test (a) and (c) would pass even if the normative prose on line 166 were stripped and only the example remained. This is acceptable given the spec's intent (example is also normative guidance) and the parity test provides the line-anchor enforcement backstop.
- **Pattern consistency**: The kept-pauses inventory entry at `skills/lifecycle/SKILL.md:202` matches the format and level of detail of the nine existing entries. The §4 prose uses the same instruction style as the adjacent §3b and §5 bullets (imperative-light, declarative verbs, tabular worked example). The test file matches the module-docstring + REPO_ROOT pattern used in `tests/test_lifecycle_kept_pauses_parity.py` and peers.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
