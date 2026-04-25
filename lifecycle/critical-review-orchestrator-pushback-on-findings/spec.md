# Specification: Tighten A-class findings via reviewer-side `fix_invalidation_argument` and synthesizer rubric

## Problem Statement

When `/cortex:critical-review` returns "N A-class fix-invalidating findings" with confident framing, the main agent has been observed treating the synthesis as a decisive verdict and applying findings without re-examining whether each truly invalidates the fix. The user reported a concrete instance ("I rolled over") after a 6-finding A-class synthesis. Research confirmed the failure mode is real but the diagnosis is upstream, not at the consumer: per Anthropic's harness-design guidance, "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work." This spec addresses the upstream cause — loose A-class tagging — by requiring reviewers to justify A-class assignments and giving the synthesizer an explicit rubric to downgrade when justifications are weak.

## Requirements

All requirements R1–R9 are **Must-have**. This is a minimum-viable spec: every requirement is structurally load-bearing for the upstream-only intervention to land coherently. R1–R4 define the contract and prompt changes that produce the new behavior; R5–R7 verify it via tests (R5 fixture, R6 stochastic end-to-end, R7 deterministic synthesizer-rubric); R8–R9 protect existing behavior. Omitting any single requirement leaves either the mechanism incomplete (R1–R4), the new behavior unverified (R5–R7), or regression undetected (R8–R9). R7 was added during critical-review Step 4 to close a false-positive pathway in R6's stochastic-only verification: R7 isolates the synthesizer rubric from reviewer-side stochasticity by exercising it directly with a hand-crafted reviewer-output JSON.

1. **(Must) R1 — Add optional `fix_invalidation_argument` field to JSON envelope schema**: The per-reviewer JSON envelope at Step 2c.5 (line 178 of `skills/critical-review/SKILL.md`) accepts an optional string field `fix_invalidation_argument` on each finding. Field is additive-optional — its absence does NOT trigger envelope-malformed handling. Acceptance: `grep -E '"fix_invalidation_argument"' skills/critical-review/SKILL.md | wc -l` returns ≥ 3 (mention in reviewer prompt schema, mention in extraction validation, mention in synthesizer rubric).

2. **(Must) R2 — Update Step 2c reviewer prompt to instruct A-class justification**: The reviewer prompt (lines 76–132) instructs reviewers to include `fix_invalidation_argument` for any finding tagged class "A": a one-sentence argument explaining why the proposed change as written would fail to produce its stated outcome (NOT merely that an adjacent concern exists). The instruction must NOT use CRITICAL/MUST/NEVER imperatives (per ticket 053 softened-imperatives invariant). Acceptance: `awk '/Finding Classes/,/Straddle Protocol/' skills/critical-review/SKILL.md | grep -c 'fix_invalidation_argument'` returns ≥ 1.

3. **(Must) R3 — Add synthesizer rubric to Step 2d with few-shot calibration anchors**: Step 2d's synthesizer prompt (lines 181–220) gains rubric language directly adjacent to instruction #3 (existing evidence re-examination). The rubric defines specific downgrade triggers for A-class findings:
   - Field is absent or empty
   - Argument restates the finding text without adding a causal link from evidence to fix-failure
   - Argument identifies an adjacent issue (B-class material) rather than fix-invalidation — **except when the finding's `straddle_rationale` field is present**, in which case Straddle Protocol bias-up takes precedence and trigger 3 does NOT fire (the reviewer explicitly biased up to A on unsplittable grounds; the synthesizer respects that signal)
   - Argument is vague or speculative ("might cause", "could break") without a concrete failure path

   When any trigger fires, the synthesizer downgrades A→B using the existing reclassification-with-note pattern (`Synthesizer re-classified finding N from A→B: <rationale>`).

   **Each of the 4 triggers is paired with worked examples** in the synthesizer prompt — at minimum one positive case (concrete `fix_invalidation_argument` text the synthesizer ratifies as A) and one negative case (weak `fix_invalidation_argument` text the synthesizer downgrades A→B with reclassification rationale). Each example includes the argument text and the expected synthesizer disposition. This implements the "few-shot examples with detailed score breakdowns" pattern Anthropic's harness-design guidance recommends for calibrating evaluator skepticism.

   Acceptance: `grep -B1 -A4 'fix_invalidation_argument' skills/critical-review/SKILL.md | grep -E 'restates|adjacent|vague|absent'` returns at least one match per trigger; `grep -E 'straddle_rationale.*present|straddle_rationale.*field is present' skills/critical-review/SKILL.md | wc -l` returns ≥ 1 (Straddle exemption documented); `grep -cE 'Example.*A→B|Example.*ratify' skills/critical-review/SKILL.md` returns ≥ 8 (at least 2 examples — one positive, one negative — per each of the 4 triggers).

4. **(Must) R4 — Step 2c.5 schema validation accepts the field**: Step 2c.5 envelope extraction (lines 173–179) updates its asserted schema description to include the optional `fix_invalidation_argument` field. Validation behavior is unchanged for findings without the field — they remain valid. Acceptance: `python3 -c "import json; data = json.loads(open('tests/fixtures/critical-review/straddle_case.meta.json').read()); print('schema-compatible')"` succeeds (existing fixtures continue to validate).

5. **(Must) R5 — Add test fixture for weak-argument A-class downgrade**: Create `tests/fixtures/critical-review/weak_argument_downgrade.md` (artifact) and `tests/fixtures/critical-review/weak_argument_downgrade.meta.json` (expected behavior). The artifact must contain content that plausibly elicits an A-class tag from at least one reviewer angle but with weak/missing/restating argument material. The meta.json's expected behavior is: synthesizer downgrades the A-finding to B with reclassification note; no `## Objections` section emitted (B→A refusal gate); B-class residue file written for the downgraded finding. Acceptance: `ls tests/fixtures/critical-review/weak_argument_downgrade.{md,meta.json}` returns both files; `python3 -c "import json; d=json.loads(open('tests/fixtures/critical-review/weak_argument_downgrade.meta.json').read()); assert 'expected_downgrades' in d or 'expected_class_distribution' in d"` succeeds.

6. **(Must) R6 — Extend `tests/test_critical_review_classifier.py` with weak-argument case (stochastic end-to-end)**: Add a test function exercising the new fixture under the existing stochastic 3-of-3 harness pattern. Test asserts that across 3 runs, the synthesizer downgrades the A-class finding to B in at least 2 runs (matching the existing fixture pattern's tolerance for stochasticity). Acceptance: `just test` exits 0 with the new test included; `pytest tests/test_critical_review_classifier.py::test_weak_argument_downgrade -v` passes (function name TBD during implementation but must be addressable).

7. **(Must) R7 — Add deterministic synthesizer-rubric unit test**: Add a test that exercises the synthesizer-rubric in isolation, eliminating reviewer-side stochasticity. The test constructs a hand-crafted reviewer-output JSON envelope containing one A-class finding with weak `fix_invalidation_argument` content (e.g., a finding that restates without causal link, or has empty argument). The test invokes the synthesizer prompt directly with this fixed input and asserts the synthesizer emits an `A→B` reclassification note for the weak-argument finding. This decouples rubric verification from reviewer elicitation, closing the false-positive pathway where R6 passes due to reviewer non-tagging rather than rubric firing. The deterministic test pairs with R6's stochastic test as belt-and-suspenders. Acceptance: `pytest tests/test_critical_review_classifier.py::test_synthesizer_rubric_deterministic -v` passes (function name TBD; must be addressable). Test must run with the synthesizer in isolation — no reviewer dispatch, no stochastic 2-of-3 tolerance applied to this specific test.

8. **(Must) R8 — Existing fixtures continue to pass**: `pure_b_aggregation.md` and `straddle_case.md` fixtures must continue to pass with the schema change (since field is optional and existing fixtures don't exercise A-class with weak arguments). Acceptance: `pytest tests/test_critical_review_classifier.py -v` shows the existing fixture tests passing as before.

9. **(Must) R9 — `just test` exits 0**: Project-wide test command passes after implementation. Acceptance: `just test` exits with code 0.

## Non-Requirements

- **No Step 4 changes.** No orchestrator-side pushback discipline. No new disposition. No anchor check on A→B reclassification. The pivot to upstream-only intentionally excludes this surface.
- **No `critical-review-residue.json` schema changes.** No new `reclassified_from` field. The existing morning-report consumer renders downgraded findings as standard B-class residue; that is acceptable since downgrades are themselves legitimate B-class findings.
- **No `events.log` schema additions.** No new event types. The schema invariant (consumed by `report.py` and `metrics.py`) is preserved.
- **No clarify-critic.md changes.** The "reproduced from /cortex:critical-review Step 4 to avoid silent drift" comment in `skills/refine/references/clarify-critic.md` line 69 is left intact. The upstream-side mechanisms in this spec (Step 2c reviewer prompt, Step 2d synthesizer rubric, Step 2c.5 envelope schema) have no clarify-critic analogue (clarify-critic uses prose-only Finding/Concern format with no class taxonomy or evidence_quote field), so propagation is not applicable. The comment refers specifically to Step 4 disposition framework, which is unchanged here.
- **No A-class definition tightening.** Option (g) from research deferred. The `fix_invalidation_argument` + rubric mechanism produces the desired discrimination at synthesis time without revising the Step 2c definition prose or Straddle Protocol.
- **No new fixture for the existing pure_b/straddle cases.** Those continue to function unchanged; the new fixture exercises only the new behavior.
- **No Step 4 telemetry / observability work.** Was contingent on (d) shipping; obviated.
- **No instrumentation of the existing Step 2d:203 anti-verdict opener.** Optional follow-on; not blocking this lifecycle.

## Edge Cases

- **Reviewer omits the field on an A-class finding**: Synthesizer rubric (R3) treats absence as the first downgrade trigger. Result: A→B with reclassification note "Synthesizer re-classified finding N from A→B: no fix-invalidation argument provided". Envelope is still valid; reviewer's other findings (B/C, or A with arguments) remain intact.

- **Reviewer provides a strong-sounding but vacuous argument** ("This breaks the system" when the finding is "the system is broken"): Synthesizer rubric trigger 2 (restating without causal link) fires; A→B downgrade with note.

- **Reviewer provides a vague hedged argument** ("might cause issues under load"): Synthesizer rubric trigger 4 (vague/speculative) fires; A→B downgrade with note.

- **Reviewer provides a concrete fix-invalidation argument** ("the refactor removes the null check the caller depends on; the caller will dereference null after this change"): Synthesizer ratifies A-class.

- **Multiple reviewers tag overlapping concerns at A with mixed argument quality**: Synthesizer applies rubric per finding (existing Step 2d #3 per-finding behavior). Strong-argument findings remain A; weak-argument findings downgrade to B.

- **Reviewer applies Straddle Protocol (bias-up to A) and includes `straddle_rationale` field**: R3 trigger 3 (adjacent-issue downgrade) does NOT fire on these findings, because the reviewer explicitly used Straddle Protocol bias-up. The synthesizer respects the `straddle_rationale` signal as authoritative and retains A-class. Other triggers (1, 2, 4) still apply normally. This preserves the existing Straddle Protocol contract while still allowing A→B downgrade on legitimately weak arguments outside the straddle case.

- **All A-class findings downgrade to B**: Existing B→A refusal gate (line 199) fires. Synthesis omits `## Objections`; opens with "No fix-invalidating objections after evidence re-examination..." preamble. Downgraded findings appear under `## Concerns`.

- **Stochastic test variance**: Reviewer agents may or may not include the field on any given run. R6's test allows 2-of-3 tolerance to accommodate this — tighter than 1-of-3 (which would mask regression) but looser than 3-of-3 (which would flake on legitimate variance).

- **Fixture exercising weak-argument case is itself stochastic**: The fixture must contain content where reviewers ARE likely to tag A-class but where the strongest plausible argument is still weak (e.g., a finding that's clearly an adjacent gap dressed up as "fix-invalidating"). Implementation may iterate on the fixture content to achieve reliable elicitation.

## Changes to Existing Behavior

- **MODIFIED: Step 2c reviewer prompt** — adds instruction for A-class findings to include `fix_invalidation_argument`. Other class tagging behavior unchanged.
- **MODIFIED: Step 2c.5 envelope schema description** — lists `fix_invalidation_argument` as optional field. Validation logic unchanged.
- **MODIFIED: Step 2d synthesizer prompt** — adds rubric language adjacent to instruction #3 specifying downgrade triggers based on argument quality. Existing A→B downgrade pattern (reclassification note) is reused, not modified.
- **ADDED: New test fixture** at `tests/fixtures/critical-review/weak_argument_downgrade.{md,meta.json}` exercising the new downgrade behavior.
- **ADDED: New stochastic end-to-end test function** in `tests/test_critical_review_classifier.py` covering the new fixture (R6).
- **ADDED: New deterministic synthesizer-rubric unit test** in `tests/test_critical_review_classifier.py` exercising the synthesizer in isolation with hand-crafted reviewer-output JSON (R7).

## Technical Constraints

- **JSON envelope class enum** is preserved as A/B/C only. No new classes (Step 2c.5 schema invariant).
- **Schema is additive-optional only** for the JSON envelope. The new field MUST NOT be required at the envelope-validation layer (would invert intent: a real A-class finding with omitted argument would get full reviewer-exclusion rather than A→B downgrade).
- **Step 4 compact summary format** (ticket 067) is unchanged. No Dismiss verbosity reintroduction.
- **Softened imperatives** (ticket 053) are observed — no CRITICAL/MUST/NEVER framing in new prompt prose.
- **`critical-review-residue.json` payload schema** is unchanged. Existing `findings[]` array continues to carry B-class findings (now including downgrades from A) without distinguishing reclassification source.
- **Stochastic 3-of-3 test pattern** from ticket 132 is the test harness model. Tolerance loosened to 2-of-3 for the new test to accommodate reviewer-side field-inclusion variance.
- **Auto-trigger blast radius** is unchanged: `skills/lifecycle/references/specify.md §3b` and `plan.md §3b` continue to invoke critical-review with no integration changes required at the call sites.

## Open Decisions

None. All Spec-level decisions resolved during the §2 interview (field contract: optional + synthesizer enforcement; A-class definition tightening: skip).
