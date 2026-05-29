# Review: reconcile-discovery-skillmd-architecture-vocabulary-with

## Stage 1: Spec Compliance

### Requirement 1: GATE-2 fallback sub-section list (`SKILL.md:82`) names only the emitted Architecture sub-sections
- **Expected**: Replace the parenthetical naming `### Pieces`, `### Integration shape`, `### Seam-level edges`, optional `### Why N pieces` with one naming only `### Pieces` and `### How they connect`. Acceptance: `grep -c "Integration shape"` = 0 AND `grep -c "Seam-level edges"` = 0 in SKILL.md, line still names `### Pieces` and `### How they connect`.
- **Actual**: `SKILL.md:82` now reads "sub-sections `### Pieces` and `### How they connect`". `grep -c "Integration shape" skills/discovery/SKILL.md` = 0; `grep -c "Seam-level edges" skills/discovery/SKILL.md` = 0. The line names both emitted headings.
- **Verdict**: PASS
- **Notes**: Minimal, targeted edit on the single GATE-2 fallback line.

### Requirement 2: `revise` re-walk (`SKILL.md:85`) conforms to the emitted template, drops the superseded spec pointer and orphaned gate, and points at the live template
- **Expected**: Replace the "spec R4 GATE-2 (iii) … re-run `### Why N pieces` falsification gate" prose with language that (a) points at the live template in `references/research.md` §6, (b) names the emitted headings (`### Pieces`, then `### How they connect`), (c) carries the piece-count concern as the template's soft "consider merging" guidance. Acceptance: `grep -c "Why N pieces"` = 0 AND `grep -c "spec R4 GATE-2"` = 0; positive content enforced by the Req 5 marker-phrase assertion, not a bare file-wide token check.
- **Actual**: `SKILL.md:85` now reads "The agent re-walks the Architecture section against the live template in `references/research.md` §6, re-emitting `### Pieces` (named by role, per the role-naming convention) then `### How they connect`, and applying the template's soft \"consider merging\" guidance when the piece count grows large." `grep -c "Why N pieces"` = 0; `grep -c "spec R4 GATE-2"` = 0. The `references/research.md` §6 pointer, `### Pieces`, and `### How they connect` are all present **on the `revise` bullet line specifically** (line 85), not merely file-wide (the token also appears at line 67's phase-reference table). Verified the pointer points at real prose: `references/research.md` §6 (`### 6. Write Research Artifact`) emits `## Architecture` → `### Pieces` (line 120) + `### How they connect` (line 123) with the soft "consider merging pieces" hint at line 116. The pointer is live and accurate, not pointing at prose that no longer exists.
- **Verdict**: PASS
- **Notes**: Edge Case 2 (revise under-specification) is closed: the replacement points the agent at a real, live template rather than at deleted prose.

### Requirement 3: Reconcile the dangling gate reference at `decompose.md:50`
- **Expected**: Drop the removed-gate naming ("falsification gate (research-phase R3)") while preserving the behavioral instruction — the analytical piece-set delivered by research is final; do not re-derive or re-merge it at decompose. Do not re-open §1/§2/§4. Acceptance: `grep -c "research-phase R3" decompose.md` = 0, while §3 still instructs the agent not to re-derive/re-merge the piece-set.
- **Actual**: `decompose.md:50` now reads "The research phase has already settled the structural-coherence merge question and delivered a final `### Pieces` set. Do not re-derive or re-merge it here. The analytical piece-set at decompose entry is the merged set." `grep -c "research-phase R3"` = 0. The behavioral guard survives verbatim ("Do not re-derive or re-merge it here. The analytical piece-set at decompose entry is the merged set"). This is a reword, not a degenerate deletion — the don't-re-run intent is intact (Edge Case 3 satisfied). The diff confirms §3 line 50 is the only change in decompose.md; §1/§2/§4 untouched.
- **Verdict**: PASS
- **Notes**: Reword strengthens the prose slightly by naming research as the owner of the piece-set, consistent with §3's distinct-outcomes framing below it.

### Requirement 4: Both plugin mirrors regenerated and staged in the same commit
- **Expected**: After editing canonical sources, regenerate via `just build-plugin` and stage both mirrors. Acceptance: `diff -q skills/discovery/SKILL.md plugins/cortex-core/skills/discovery/SKILL.md` exits 0 AND `diff -q skills/discovery/references/decompose.md plugins/cortex-core/skills/discovery/references/decompose.md` exits 0.
- **Actual**: Both `diff -q` invocations exit 0 (mirrors identical to canonical). The commit stat shows both canonical and both mirror files changed in the same impl-commit range, with matching diffs.
- **Verdict**: PASS
- **Notes**: Pre-commit dual-source drift hook would pass.

### Requirement 5: Regression tests pin the reconciliation so it cannot silently re-drift
- **Expected**: (a) In `test_discovery_gate_presentation.py` (raw-text, `read_text` on `DISCOVERY_SKILL`, marker-phrase idiom): assert all four drifted tokens absent AND a positive marker phrase pinning the `revise` bullet's replacement (a stable substring including its `references/research.md` §6 pointer) so a degenerate stub fails. (b) In `test_decompose_rules.py`: assert `"research-phase R3" not in` the decompose body, leaving the existing intentional non-emitted-heading failure-message strings untouched. Acceptance: assertions exist as described and `just test` exits 0.
- **Actual**: (a) `test_revise_bullet_vocabulary_conformed_to_emitted_template` (line 133) asserts all four `DRIFTED_VOCAB_TOKENS` (`Integration shape`, `Seam-level edges`, `Why N pieces`, `spec R4 GATE-2`) absent file-wide, then locates the `revise` bullet line and asserts `references/research.md`, `### Pieces`, and `### How they connect` are present **on that line specifically**. I verified the scoped assertion has teeth: a simulated degenerate stub of the `revise` bullet fails all three required-token checks while the real edit passes. (b) `test_decompose_body_omits_removed_research_phase_r3_gate` (line 398) uses the `raw_text` negative-assertion idiom: `assert "research-phase R3" not in raw_text`. The existing intentional non-emitted-heading strings (`Integration shape`, `Seam-level edges` in `test_grouping_section_1_input_contract_omits_non_emitted_headings`) remain present and untouched (6 occurrences confirmed). `just test` exits 0 (6/6 suites pass).
- **Verdict**: PASS
- **Notes**: Both tests follow the existing idioms of their respective files (marker-phrase / scoped-assertion in the gate-presentation file; `raw_text` negative-assertion in the decompose-rules file).

**Non-Requirement scope check (verified clean):** The 4 impl commits changed exactly 6 files — the 2 canonical sources, 2 mirrors, and 2 test files. `git diff --stat` over the impl-commit range confirms `research.md` (the template), `cortex/adr/0007`, `cortex_command/discovery.py`, `bin/.events-registry.md`, `tests/test_discovery_module.py`, and the `tests/fixtures/discovery-brief/` fixtures were NOT touched. `decompose.md` §1/§2/§4 untouched (only §3:50 reworded). No scope breach.

**MUST-escalation policy check (verified clean):** No new `MUST`/`CRITICAL`/`REQUIRED` tokens in the diff additions (grep on `^+` lines returns none). The replacement prose uses soft positive-routing phrasing ("re-walks … against the live template", "applying the template's soft 'consider merging' guidance") describing output shape and intent, not step-by-step method.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. The new test names follow the file's existing descriptive `test_<subject>_<assertion>` convention (`test_revise_bullet_vocabulary_conformed_to_emitted_template`, `test_decompose_body_omits_removed_research_phase_r3_gate`). The module-level `DRIFTED_VOCAB_TOKENS` constant mirrors the file's existing marker-phrase constant idiom (`R3_DROP_DUAL_USE_MARKER_PHRASE`, etc.).
- **Error handling**: N/A for prose edits. Test robustness is sound: each assertion carries a descriptive failure message pointing reviewers at the contract, matching both files' existing style. The `revise`-bullet locator uses `next(..., None)` with an explicit not-None guard before the scoped checks, so a missing bullet produces a clear "bullet was stubbed or deleted" message rather than an opaque error.
- **Test coverage**: The two new tests pin exactly what the spec claims. The gate-presentation test's scoped positive assertion has demonstrable teeth — a degenerate revise-bullet edit that fixes the GATE-2 fallback in isolation but stubs/deletes the `revise` bullet fails (verified by simulation: all three required tokens absent from the stubbed line). The decompose test's `raw_text` negative assertion catches re-drift of the dead-gate naming. Both close their respective spec edge cases (Edge Case 2 and Edge Case 3).
- **Pattern consistency**: Matches existing idioms precisely. `test_discovery_gate_presentation.py` uses the scoped-assertion idiom (locate the bullet line, assert tokens on it) already established by `test_r3_drop_description_has_dual_use_marker`. `test_decompose_rules.py` uses the `raw_text` negative-assertion idiom already established by `test_grouping_section_2_no_longer_says_becomes_one_ticket_candidate`. The existing intentional non-emitted-heading failure-message strings are left untouched.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
