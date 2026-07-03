# Review: sweep-provisional-tail-refine-cluster-transitive

## Stage 1: Spec Compliance

### Requirement 1: Candidate set is exactly the 42 filtered rows, keyed `(file, id)`
- **Expected**: `master_candidates.json` filter (`status=="unverified"` ∧ file ∈ 12-file set ∧ no `overlaps_ticket` ∧ no `reproposal_of`) yields 42 rows / 42 distinct `(file,id)` pairs / 23 distinct ids; `verify-outcomes.md` pair-set equals the filter exactly.
- **Actual**: Recomputed the filter — 42 rows, 42 distinct pairs, 23 distinct ids, zero duplicate pairs. `verify-outcomes.md` parses to 42 rows / 42 distinct pairs; symmetric difference against the filter is EMPTY (no missing, no extra).
- **Verdict**: PASS
- **Notes**: Composite keying confirmed (e.g. `s3`×5, `file-compress`×4 across distinct files).

### Requirement 2: Locate by heading + pinned token, never by ledger line number
- **Expected**: Every anchor names a section heading + distinctive token; no line-number-only anchors; each anchor heading exists verbatim post-trim.
- **Actual**: Scanned all 42 anchor fields — none is a bare ledger line number (all `## Heading::token` form). Spot-checked 9 anchor headings across all files (Step 1 Resolve Input, 2. Structured Interview, 1. Resolve Input, Disposition Framework, Count matrix, Output: JSON Envelope, pick, Decision rules, Empty/failed agent handling) — all grep present verbatim (count 1).
- **Verdict**: PASS

### Requirement 3: Every applied trim cites an independent checkable signal
- **Expected**: Each applied row names signal type a/b/c + enforcing/surviving location for a/c; refuted rows carry no bogus signal.
- **Actual**: All 38 `verified_survives` rows cite `signal:a` (6), `signal:b` (17), or `signal:c` (15); zero applied rows carry a bare/none signal. All 4 refuted rows carry `signal:none`. Integrity-gate section performs a removed-line normative-token scan (`git show -- <file>`) and resolves every multi-candidate hit to a signal:c/a row whose token survives elsewhere.
- **Verdict**: PASS

### Requirement 4: Preserve What/Why intent, weighting, and user-affordance prose
- **Expected**: Named high-risk items grep present after their file's trim; candidates whose only safe form removes such prose are REFUTED.
- **Actual**: All named survivors confirmed present: clarify.md `appropriate default for most skill` (1) + `do not ask the user to confirm` (1); specify.md §2b four sub-checks (4, incl. state ownership); adr/README.md `MUST automatic`/`MUST NOT automatic`/`SHOULD surface` (1/1/1); plan-synthesizer `## Untrusted Variant Data` (1) + `letter token` (1); interview loop `one at a time`/`soft-cap`/`stop-early` affordances present. The two candidates whose only safe form removed decision-criteria were REFUTED (specify.md s6 §2b four sub-checks; clarify.md s5 confidence rubric gating the §4 pause).
- **Verdict**: PASS

### Requirement 5: Kept-pauses parity — bump the anchor in-commit
- **Expected**: `kept-pauses.md` anchor bumped in the same commit as `refine/SKILL.md`; parity test exits 0; canonical + mirror staged together; s10c `AskUserQuestion` stays one line.
- **Actual**: Commit `6b3766e2` touches exactly `skills/refine/SKILL.md`, `skills/lifecycle/references/kept-pauses.md`, and both mirrors. Anchor bumped `refine/SKILL.md:166 → :147` in that commit (diff confirmed). `.venv/bin/pytest tests/test_lifecycle_kept_pauses_parity.py -q` → 2 passed. s10c row records single-line in-place recompression; integrity gate confirms the token is removed-and-re-added on one line.
- **Verdict**: PASS

### Requirement 6: Coordinated single edit for nested same-file spans; each inner candidate its own row
- **Expected**: `plan-synthesizer file-compress ⊃ s15` and `backlog file-compress ⊃ s11` each applied as one commit with two distinct outcomes rows; inner keep-list tokens grep present.
- **Actual**: `bafa4059` carries both plan-synthesizer `s15` + `file-compress` rows (single coordinated edit, one file). `4ec76922` carries both backlog `s11` + `file-compress` rows. Inner keep tokens present (plan-synth A/B/C letter-token rule; backlog top-4/priority label fields).
- **Verdict**: PASS

### Requirement 7: `adr/README.md` highest-risk; s3 refuted-or-surfaced
- **Expected**: s3 recorded `verified_refuted` with #304-citation reason (or applied only under confirmation).
- **Actual**: s3 is `verified_refuted` with reason citing `#304 cites README.md:11-17`. The s3 span (lines 11-17, the prose-only rationale) is byte-identical pre/post; #304's citation `cortex/adr/README.md:11-17` still resolves; the CLAUDE.md prose-only quote survives verbatim at L11 + L17. (The `## Purpose` section differs only at line 3, from the separate applied s2 three-criteria dedup, which is above the protected span.)
- **Verdict**: PASS

### Requirement 8: `commit/SKILL.md` s6 recorded as refuted (moot)
- **Expected**: s6 `verified_refuted`, reason "section removed in 8c3a00b9"; no edit attempted.
- **Actual**: Row present as `verified_refuted` with that reason. `grep -c '## Validation'` = 0; file is 31 lines; `skills/commit/SKILL.md` not in any batch commit.
- **Verdict**: PASS

### Requirement 9: Two other-ticket spans left byte-unchanged, checked by content
- **Expected**: `clarify.md` #340 (`### 6. Research Sufficiency Criteria`) and `clarify-critic.md` #186 (`## Parent Epic Loading (orchestrator)`) byte-identical pre/post via content extraction.
- **Actual**: Extracted both spans from `6b3766e2^` and from HEAD (heading to next heading) — both IDENTICAL. Both protected headings exist verbatim post-trim.
- **Verdict**: PASS

### Requirement 10: Dual-source mirror parity per commit; `kept-pauses.md` authorized 13th file
- **Expected**: `git diff --quiet plugins/` clean; adr/README.md + plan-synthesizer.md have no mirror; anchor bump stages kept-pauses canonical + mirror.
- **Actual**: `git diff --quiet plugins/` clean. No mirror exists for `adr/README.md` or `plan-synthesizer.md` (find confirms). New `pr/references/template-filling.md` has a `plugins/cortex-core/` mirror. backlog mirror in `plugins/cortex-backlog/`. kept-pauses canonical+mirror both in `6b3766e2`. Pre-commit drift hook passing is implied by the commits landing.
- **Verdict**: PASS

### Requirement 11: Per-candidate test gating after risky files
- **Expected**: Pinned tests exit 0 after their file's commit.
- **Actual**: Ran the pinned trio now — `test_research_fanout_matrix.py`, `test_plan_synthesizer.py`, `test_lifecycle_kept_pauses_parity.py` → 12 passed. Commit bodies carry per-row test evidence.
- **Verdict**: PASS

### Requirement 12: Per-child `verify-outcomes.md`, `(file,id)`-keyed; ledger NOT written
- **Expected**: Exactly 42 `(file,id)` rows; every verdict ∈ {survives, refuted, deferred}; every survivor carries a 40-hex hash + signal; ledger untouched.
- **Actual**: 42 rows / 42 distinct pairs; verdicts are 38 survives + 4 refuted + 0 deferred. All 38 survivors carry a valid 40-hex `applied_in_commit` and an a/b/c signal; all 4 refuted carry `—`. `master_candidates.json` not in any batch commit (deferred per Non-Requirements).
- **Verdict**: PASS

### Requirement 13: Discharge mechanism for reconciliation debt — tracked follow-up
- **Expected**: Backlog item naming (a) this verify-outcomes.md as delta, (b) composite `(file,id)` keying, (c) #340/#186 anchor-drift re-locate note.
- **Actual**: `cortex/backlog/366-*.md` (parent #357) names `verify-outcomes.md` as delta source, scopes composite `(file,id)` keying with the 23-distinct-ids / ~19-overwrite hazard, and documents #340 s9 + #186 s3 heading-anchored re-location. All three elements present.
- **Verdict**: PASS

### Requirement 14: Savings tally + full-suite integration gate before Review
- **Expected**: `just test` green (pre-existing unrelated reds disclaimed); outcomes file + one-line savings figure recorded.
- **Actual**: Savings line records ~6920 weighted tokens over 38 applied; recomputed sum of `weighted_cost` over the 38 survivor pairs = 6920 (exact). Pinned at-risk suites green. Full `just test` not re-run here; per the task the only reds are 2 sandbox-only environmental failures (pypi DNS + /tmp) that pass off-sandbox.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Consistent. Commit subjects imperative/capitalized/≤72 chars; `verify-outcomes.md` follows the sibling-#358 `(file,id)`-keyed convention; backlog #366 uses the standard frontmatter + Why/Scope/Done-when shape.
- **Error handling (trim quality)**: No load-bearing prose removed. Every applied cut cites an independent signal and the removed-line normative-token scan resolves each hit to a token preserved/enforced elsewhere. The two genuine decision-criteria risks (specify.md s6, clarify.md s5) were correctly REFUTED rather than force-applied; adr/README.md s3 refuted to protect live #304. Signal:b classifications spot-checked against Req 4's exclusion (no weighting/affordance span reclassified informative-only).
- **Test coverage**: Pinned parity, fanout-matrix, and plan-synthesizer suites green post-batch (verified now: 12 passed). Per-commit test evidence carried in commit bodies.
- **Pattern consistency**: Dual-source mirror map honored (no mirror for adr/README.md + plan-synthesizer.md; kept-pauses treated as the authorized 13th file); LAZY_REF extraction (pr s3b → template-filling.md) got its own mirror and passed the skill-path lint (commit landed). Nested-span pairs applied as single coordinated edits.

## Requirements Drift
**State**: none
**Findings**:
- None. All changes are body-prose trims to skill/prompt files, one new per-child lifecycle record (`verify-outcomes.md`), and one tracked backlog follow-up. This is squarely within the existing requirements: "Maintainability through simplicity — complexity is managed by iteratively trimming skills/workflows" and the kept-pauses↔parity coupling already in project.md. No framework behavior is added or changed.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
