# Reconciliation Verdicts — #360 critical-review provisional-tail sweep

Per-candidate verify outcomes for the 26 provisional trim candidates under `skills/critical-review/`, plus the `cortex-resolve-model` parity residual. This is the child-lifecycle handoff record that #357's reconciliation close folds into `master_candidates.json` (child `verdicts.md` → `master_candidates.json`); this file does **not** write the master ledger itself.

**Disposition legend**: `verified_survives` = trim applied and all keep-list/pin/behavioral gates held; `verified_refuted` = candidate rejected, not applied; `correction` = a factual fix (not a trim). Each entry names the candidate id and its file, its disposition, a one-line evidence note, and — for applied candidates — the trim-commit short-SHA in square brackets.

## SKILL.md (Task 1, commit fb0beed3)

- s5(SKILL.md) → verified_survives — Step 2a Load Domain Context How-narration trimmed; pinned literals + fast pins (24 passed) held. [fb0beed3]
- s6(SKILL.md) → verified_survives — Requirements-exempt blockquote trimmed; the assertion pinned by test_load_requirements_protocol.py:134 preserved byte-exact. [fb0beed3]
- s3(SKILL.md) → verified_refuted — Contents-TOC KEPT (Req 12). The "no nav value in an always-loaded file" argument applies identically to all four files #178 added TOCs to, so per Solution-horizon a unilateral single-file deletion is out of scope; corpus-wide re-eval filed as a follow-up in Non-Requirements. `grep -c "^## Contents"` ≥ 1 confirmed unchanged.
- s8(SKILL.md) → verified_survives — Step 2b Derive Angles redundant How-narration trimmed; operative angle-derivation instruction + distinctness/specificity criteria preserved (behavioral-necessity read confirmed). [fb0beed3]
- s9(SKILL.md) → verified_survives — Step 2c dispatch summary trimmed; READ_OK literal preserved byte-exact. [fb0beed3]
- s12(SKILL.md) → verified_survives — Step 2d narrowed to preserve line-78 "8 worked examples (4 ratify / 4 downgrade …)" enumeration; SYNTH_READ_OK + placeholder counts unchanged. Note: spec's classifier-test gate premise was stale (test reads an inline Step-2d template that was extracted to synthesizer-prompt.md pre-#360; pre-existing failure, not a regression). [fb0beed3]
- s14(SKILL.md) → verified_survives — Step 2e conservative prose-tighten; ALL mech-pin tokens (os.replace, .session/residue paths) kept byte-exact per explicit directive, so a modest tighten rather than the claim's ~60-token deferral. [fb0beed3]
- s16(SKILL.md) → verified_survives — Step 4 Apply Feedback NARROWED: the six-verb Apply-summary list + "Dismiss: N" format preserved (the list is a documented, regex-pinned design decision in the archived restructure-critical-review-step-4-to-suppress-dismiss-output lifecycle, so full removal was unsafe); only bullet-framing prose trimmed. [fb0beed3]

## angle-menu.md (Task 2, commit a092737d)

- s1(angle-menu.md) → verified_survives — intro trimmed; `## Acceptance Criteria` pointer target preserved; mirror parity held. [a092737d]
- s2(angle-menu.md) → verified_survives — example section trimmed; mirror-parity pins held. [a092737d]
- s3(angle-menu.md) → verified_survives — example section trimmed; file shrank; mirror clean. [a092737d]
- s4(angle-menu.md) → verified_survives — example section trimmed; mirror clean. [a092737d]
- s5(angle-menu.md) → verified_survives — example section trimmed; mirror clean. [a092737d]
- s7(angle-menu.md) → verified_survives — example section trimmed; `Acceptance Criteria` pointer resolves. [a092737d]

## residue-write.md (Task 3, commit 310db782)

- s2(residue-write.md) → verified_survives — Feature Resolution prose replaced with a bash invocation block; resolver script `cortex-critical-review-resolve-feature` + exit-code routing preserved (plan keep-token `resolve_feature_cli.py` was mis-specified — that filename never existed; real referents are the console-script names). [310db782]
- s3(residue-write.md) → verified_survives — Atomic Write narration trimmed; writer script `cortex-critical-review-write-residue` + R4 payload schema + `critical-review-residue.json` target preserved. [310db782]

## reviewer-prompt.md (Task 4, commit c648a1ed)

- s1(reviewer-prompt.md) → verified_survives — meta-header compressed; all load-bearing tokens byte-exact. [c648a1ed]
- s8(reviewer-prompt.md) → verified_survives — Instructions compressed; A/B/C defs, fix_invalidation_argument, Straddle "bias up to A", "Do not cover other angles. Do not be balanced.", envelope field names + `<!--findings-json-->` + READ_OK/READ_FAILED all byte-exact. [c648a1ed]
- file-compress(reviewer-prompt.md) → verified_survives — intra-file dedup; behavioral run-and-observe PASS (dispatched reviewer emitted READ_OK, class-tagged A/A/B/B/B findings, well-formed JSON envelope with working straddle-split). [c648a1ed]

## synthesizer-prompt.md (Task 5, commit a00ad0bc; dup-group realign 7f4cd082)

- s1(synthesizer-prompt.md) → verified_survives — meta-header collapsed to a 2-line placeholder list; {artifact_path}/{artifact_sha256}/{a_to_b_rubric} preserved. [a00ad0bc]
- s3(synthesizer-prompt.md) → verified_survives — Artifact read-once prose compressed; SYNTH_READ_OK/SYNTH_READ_FAILED untouched. [a00ad0bc]
- s5(synthesizer-prompt.md) → verified_survives — Instructions item 1 dropped + item-3 restatement removed; item-4 A-class tally gate ("count A-class from well-formed envelopes only" / zero → no `## Objections`) preserved byte-exact. Deviation: list left numbered 2–8 (no renumber, to keep tally-gate tokens byte-exact); no behavioral impact. [a00ad0bc]
- s8(synthesizer-prompt.md) → verified_survives — Output Format trimmed; four section headers + reclassify-note format preserved. Behavioral run-and-observe PASS (both cases): with-A input renders `## Objections`; zero-A input opens with the "No fix-invalidating objections…" line and emits no `## Objections`. Dup-group note: s8 initially relocated "Do not be balanced." into the shared "Use bullets…" paragraph, breaking byte-alignment with fallback-reviewer; realigned in 7f4cd082 (shared paragraph now byte-identical, sha 551d3596…). [a00ad0bc]

## fallback-reviewer-prompt.md (Task 6, commit 69642846)

- file-compress(fallback-reviewer-prompt.md) → verified_survives — preamble (lines 3–6) + closing note trimmed; frozen sentinel/instructions/output-format block (lines 9–42) byte-unchanged; READ_FAILED sentinel + shared Output-Format block byte-identical to reviewer/synthesizer counterparts (after 7f4cd082). [69642846]

## verification-gates.md (Task 7, commit cd48c762)

- s2(verification-gates.md) → verified_survives — line-17 pin-free `<artifact-path>` restatement cut only; the adjacent `--feature`/`$LIFECYCLE_SESSION_ID` line KEPT intact per the prior lifecycle's lean-refute (`$LIFECYCLE_SESSION_ID` count 2 unchanged). Excluded exit-3/4 + write/tempfile guard prose re-grep present byte-exact. [cd48c762]
- s3(verification-gates.md) → correction — NOT a trim: the Step 2c.5 line wrongly naming `check-synth-stable` as the canonical SHA-computation path corrected to `prepare-dispatch` (prepare_dispatch computes via sha256_of_path at __init__.py:37,41; check_synth_stable only compares at :382). check-synth-stable legitimately survives on 3 other lines. [cd48c762]

## Parity residual (Task 1, not one of the 26 scored candidates)

- cortex-resolve-model parity: deleted the gloss `(the verb is absent or broken)` at SKILL.md:76 to harmonize down with the bare lifecycle siblings (review.md:22, orchestrator-review.md:45, competing-plans.md:16). Did NOT touch implement.md:165 (owned by #348). [fb0beed3]

## Summary

26 candidates: 24 `verified_survives`, 1 `verified_refuted` (SKILL.md Contents-TOC), 1 `correction` (vgates s3). 25 applied across 7 trim commits (fb0beed3, a092737d, 310db782, c648a1ed, a00ad0bc, 69642846, cd48c762) + 1 dup-group realignment (7f4cd082). No candidate silently skipped; the two narrowings (s16, s14) and the mis-specified-keep-token correction (residue s2) are recorded above for #357's fold-in.
