# Review: auto-consolidation-pass-in-discovery-decompose

## Stage 1: Spec Compliance

### Requirement 1: §4 groups coupled pieces into tickets
- **Expected**: decompose.md §4 "Determine Grouping" rewritten so that for `piece_count ≥ 2`, tightly-coupled pieces group into a single ticket (M pieces → 1 ticket) instead of strict one-child-per-piece; grouping expressed as decision-criteria + output-shape, not an algorithm. `grep -nE "group"` ≥1 hit in §4 naming the criteria; a test asserts §4 documents piece-grouping criteria; `just test` exits 0.
- **Actual**: §4 (decompose.md:72–83) adds "First group the pieces into ticket units, then create one epic and one child per *group*" and a "Group tightly-coupled pieces into single tickets" block naming four inferred coupling indicators (shared connection seam, one integration cluster, near-identical role, value-only-when-shipped-together) — decision-criteria + output-shape, no token-matching algorithm. `test_grouping_criteria_named_in_section_4` asserts all four criteria appear in the §4 body. `just test` = 6/6 passed (exit 0).
- **Verdict**: PASS
- **Notes**: Grouping is framed as "opportunistic, never forced" with a 1:1 fallback when no coupling is evident — matches the spec's edge case.

### Requirement 2: Coupling signals inferred from the Architecture content decompose actually receives
- **Expected**: §4 reasons over the emitted `### Pieces` + `### How they connect` content plus dependencies, *inferring* coupling indicators; "value when shipped together" is an inferred judgment, not a literal field; §4 must not key on the non-emitted `### Integration shape`/`### Seam-level edges` headings. `grep` shows the inferred-signal framing; `grep -c "Seam-level edges"` of the §4 grouping prose = 0.
- **Actual**: §4 explicitly reasons over "the emitted Architecture content (`### Pieces` roles + `### How they connect` prose) plus the derived dependencies" (decompose.md:74) and uses "Infer the coupling from these indicators." The value-only-when-shipped-together bullet states "This is an inferred judgment from the roles and connections, not a literal field the template emits" (decompose.md:79). `grep -c "Seam-level edges" decompose.md` = 0 across the whole file. §1 input contract (line 9) and the §2 Dependencies bullet (line 46) were reconciled to the emitted headings; `test_grouping_section_1_input_contract_omits_non_emitted_headings` negatively asserts the non-emitted headings are absent from §1.
- **Verdict**: PASS
- **Notes**: The deferred upstream `research.md`-template heading drift is correctly left untouched per Non-Requirements; only decompose.md's own internal consistency was reconciled.

### Requirement 3: Grouped child-ticket bodies are coherent merged bodies; per-piece Architecture source retained
- **Expected**: §5 authors one merged body per grouped ticket (prose-merged Why/Role/Integration, unioned+deduped Edges/Touch points), mirroring the R15 `consolidate-pieces` convention; the `### Pieces` source in research.md is not modified and remains the record `split-piece` re-derives from. §4/§5 prose references the merge convention AND states the source is retained.
- **Actual**: §5 (decompose.md:95) authors "one merged body" mirroring "the R15 `consolidate-pieces` body-merge convention," with Why/Role/Integration prose-merged and Edges/Touch points "unioned and deduplicated," and states the `### Pieces` source "is **not** touched by this merge — it stays unchanged as the authoritative per-piece record." `test_grouping_notes_in_section_6_and_merge_convention_in_section_5` asserts §5 names both `consolidate-pieces` and `merge convention`.
- **Verdict**: PASS

### Requirement 4: §2/§3/Constraints reconciled — grouping is explicit packaging, not silent piece-set mutation
- **Expected**: §2, §3, and the Constraints "Architecture-section-driven" bullet updated so grouping is explicit/surfaced (never silent) and distinguished from re-deriving/mutating the piece-set (forbidden, research-owned); §3's return-to-research stance distinguishes a *wrong* set from a *right-but-over-split* set. `grep` finds the reconciliation wording in §2, §3, Constraints.
- **Actual**: §2 (decompose.md:15) reframes "each bullet ... is a piece" with "Grouping pieces into ticket units at §4 is a packaging decision over the *right* set, not a mutation." §3 (lines 52–55) explicitly splits the two outcomes: "The piece-set is *wrong* (research owns this)" → return to research, vs. "The piece-set is *right but over-split for ticketing* (§4 owns this)." The Constraints bullet (line 199) keeps the no-silent-mutation ban and adds that grouping is "an explicit, R15-surfaced packaging decision that coarsens ticket *count* without touching the `### Pieces` set." `test_grouping_section_3_distinguishes_wrong_set_from_over_split` asserts both cases. Old wording removed: `grep -c "becomes one ticket candidate"` = 0 and `grep -c "From the Integration shape and Seam-level edges"` = 0.
- **Verdict**: PASS

### Requirement 5: Groupings and surviving intra-group ordering recorded in decomposed.md
- **Expected**: §6 records groupings under a dedicated `## Grouping Notes` heading (parallel to `## Consolidation Notes`/`## Dropped Items`): which pieces grouped into which ticket, a per-group rationale, AND surviving intra-group `blocked-by` ordering preserved as an explicit sequence note. `grep -nE "Grouping Notes"` ≥1 in §6 and §6/§4 prose names intra-group ordering preservation.
- **Actual**: §6 (decompose.md:169–177) adds a `## Grouping Notes` template entry and prose stating it is "parallel to the R15-gate `## Consolidation Notes` / `## Dropped Items` headings," recording (i) which pieces grouped into which ticket, (ii) a one-sentence rationale, and (iii) "any **surviving intra-group ordering** ... preserved as an explicit intra-ticket sequence note (an internal phase boundary, mirroring the corpus precedent at swap-daytime-autonomous-for-worktree-interactive/decomposed.md), never silently dropped." §4 (line 83) "Preserve intra-group ordering" carries the same constraint. `test_grouping_notes_in_section_6_and_merge_convention_in_section_5` asserts `## Grouping Notes` in §6. Omit-when-no-grouping is correctly stated.
- **Verdict**: PASS

### Requirement 6: `split-piece` is a valid R15 response value
- **Expected**: `split-piece` added to `_RESPONSE_VALUES`; `--response` choices and validation auto-derive. `grep -c '"split-piece"' cortex_command/discovery.py` = 1; invoking checkpoint-response emission with `--response split-piece --checkpoint decompose-commit` exits 0; `just test` exits 0.
- **Actual**: `"split-piece"` added to the frozenset at discovery.py:412 (`grep -c` = 1). `choices=sorted(_RESPONSE_VALUES)` (line 1325) and validation (lines 459–463) auto-derive — confirmed `'split-piece' in _RESPONSE_VALUES` is True and present in the sorted choices list. Direct `emit_checkpoint_response(checkpoint='decompose-commit', response='split-piece', ...)` invocation exited 0 and wrote the events.log entry.
- **Verdict**: PASS

### Requirement 7: R15 gate documents `split-piece <N>` as re-derivation from the retained Architecture source
- **Expected**: R15 prose in decompose.md and the SKILL.md inventory document `split-piece <N>` as re-deriving a grouped ticket N back into constituent pieces by re-authoring each body from the retained `### Pieces` source (not the merged body), restoring recorded intra-group ordering, re-presenting the FULL renumbered batch, non-destructive, and re-prompting naturally on a non-grouped/single-index target. Each file ≥1 hit; the R15-options test includes `split-piece`.
- **Actual**: decompose.md:130 documents `split-piece <N>` as re-authoring "**from the retained Architecture `### Pieces` source** ... **not** by reconstructing them from the lossy merged body," restoring "intra-group ordering recorded under `## Grouping Notes`," re-presenting "the FULL renumbered batch," being "non-destructive ... nothing commits ... until `approve-all`," and re-prompting naturally ("piece N wasn't grouped — nothing to split"). SKILL.md:102 documents the same in the gate inventory. `test_r15_batch_review_gate_options_documented` asserts `split-piece`, `### Pieces`, `re-deriv`, and `user-blocking` all appear; `grep -c "split-piece"` = 6 (decompose.md) and 1 (SKILL.md).
- **Verdict**: PASS

### Requirement 8: R15 responses (incl. `split-piece`) emit the existing event; no new event type
- **Expected**: Each R15 response emits one `approval_checkpoint_responded` event with `checkpoint: decompose-commit` and the chosen response; no new event literal added. No new `"event":` literal in discovery prose; `just test` exits 0 and the events-registry check exits 0.
- **Actual**: The only `"event":` literal in decompose.md is `"approval_checkpoint_responded"` (no new literal). The events-registry row for `approval_checkpoint_responded` (bin/.events-registry.md:116) covers the decompose-commit gate via the checkpoint field and enumerates no response values, so `split-piece` needs no registry change. `test_emit_checkpoint_response_accepts_split_piece_at_decompose_commit` asserts the emitted event is `approval_checkpoint_responded` (existing literal). `just test` = 6/6 passed.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `split-piece` follows the existing hyphenated R15 response-value convention (`approve-all`, `revise-piece`, `drop-piece`, `consolidate-pieces`). The `## Grouping Notes` heading parallels the established `## Consolidation Notes` / `## Dropped Items` decomposed.md headings exactly as the spec directs. The ADR filename and heading slug match the sibling ADR pattern.
- **Error handling**: Appropriate. The single frozenset addition reuses the existing validator path (`_validate_checkpoint_payload`) and argparse `choices` auto-derivation — no bespoke branching, so the invalid-response `ValueError` path continues to cover the new value for free. The skill prose handles the degenerate cases (single-piece/non-grouped `split-piece`, all-N-into-one collapse, no-coupling fallback) by re-prompting naturally rather than erroring, mirroring `consolidate-pieces`.
- **Test coverage**: Substantive, not keyword-only. `test_decompose_rules.py` adds five §1–§6 grouping tests that assert semantic content and use the negative-assertion idiom for the rewrite-landed checks (`"becomes one ticket candidate" not in §2`, non-emitted headings absent from §1) section-scoped so a missing edit cannot be masked by a pre-existing occurrence elsewhere. The R15-options test asserts `split-piece` plus the re-derivation-source semantics (`### Pieces`, `re-deriv`), not bare presence. `test_discovery_module.py` adds a positive-path test exercising both the validator and the emit path, asserting the event literal is unchanged (R8). The behavior is prose/skill-instruction, so string/semantic assertions plus the validator test are the right surface; the assertions check the load-bearing semantics rather than mere keyword presence. Full suite green (6/6).
- **Pattern consistency**: Strong. ADR 0007 matches the sibling 0006 format (`status: accepted` frontmatter, Context/Decision/Trade-off/Three-criteria-gate/Alternatives/Cross-references) and cross-references #268/#247. R15 `split-piece` option mirrors the `consolidate-pieces` entry format. Dual-source mirrors are byte-identical (`diff -q` clean for both decompose.md and SKILL.md). No new event literal, no new `bin/cortex-*` script — `cortex-check-parity` and the events-registry gate are correctly untouched. The new §4 grouping prose uses soft positive-routing phrasing with no MUST/CRITICAL/REQUIRED escalation, complying with the MUST-escalation policy.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
