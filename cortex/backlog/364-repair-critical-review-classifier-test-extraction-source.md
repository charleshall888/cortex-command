---
schema_version: "1"
uuid: 2ba2a001-15f1-4ce7-aa08-3de3c05062ec
title: 'Repair test_critical_review_classifier extraction source (pre-existing break)'
status: complete
priority: medium
type: chore
tags: ['skill-value-scorecard', 'test-debt']
areas: ['skills']
created: 2026-07-03
updated: 2026-07-03
---

## Why
`tests/test_critical_review_classifier.py` fails at baseline on `main` (7 failed, 1 passed under `--run-slow`) — independent of any recent change. Its helper `_extract_synthesizer_template()` reads `skills/critical-review/SKILL.md` and asserts ≥2 `---` delimiters after the `### Step 2d: Opus Synthesis` header, but Step 2d was refactored (pre-#360) to *reference* `references/synthesizer-prompt.md` instead of embedding an inline `---`-delimited template, so the extraction finds 0 delimiters and every rubric test errors out. Discovered during #360 (verified pre-existing: delimiter count is 0 at both the pre-#360 baseline and HEAD; #360 touched no `---` line). Because these seven tests are the only automated validation of the A→B downgrade rubric — a mechanism the critical-review synthesizer actively depends on — the rubric is currently unverified.

## Role
Repoint `_extract_synthesizer_template()` (and any `SKILL_MD_PATH`-based assumption) at the real current sources: the prompt body now lives in `skills/critical-review/references/synthesizer-prompt.md`, and the A→B rubric + its 8 worked examples live in `skills/critical-review/references/a-to-b-downgrade-rubric.md` (inlined into the synthesizer prompt at dispatch via the `{a_to_b_rubric}` placeholder, so it is NOT statically present in synthesizer-prompt.md). The seven tests (`test_synthesizer_rubric_deterministic`, `test_synthesizer_trigger_2_restates`, `test_synthesizer_trigger_3_adjacent_no_straddle`, `test_synthesizer_trigger_3_adjacent_with_straddle`, `test_synthesizer_trigger_4_vague`, plus the two named-concern classifier tests) must validate meaningfully against the reassembled template.

## Integration
Verify under `uv run pytest --run-slow tests/test_critical_review_classifier.py` (the tests are `@pytest.mark.slow`; the default `just test` suite skips them, which is why the break went unnoticed). Consider whether the extraction should assemble prompt + rubric the same way the dispatch path does, so the test tracks the real rendered artifact rather than a stale inline copy.

## Edges
- The rubric substitution is a placeholder (`{a_to_b_rubric}`) — the test must read `a-to-b-downgrade-rubric.md` for the rubric content, not expect it inline in synthesizer-prompt.md.
- Don't reintroduce an inline Step-2d template in SKILL.md to satisfy the test — that would undo the deliberate extraction.

## Touch points
- tests/test_critical_review_classifier.py
- skills/critical-review/references/synthesizer-prompt.md, a-to-b-downgrade-rubric.md (read-only references for the fix)
