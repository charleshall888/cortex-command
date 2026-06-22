# Review: post-discovery-brief-over-cap

## Stage 1: Spec Compliance

### Requirement 1: Word cap is advisory in `validate_brief`
- **Expected**: An anchor-valid, non-empty brief that exceeds `GATE_BRIEF_WORD_CAP + 25` words no longer fails validation; a new unit test feeds a >275-word three-anchor brief and asserts `validate_brief(brief) == (True, "")`.
- **Actual**: `validate_brief` (discovery.py:560-627) ends with `return True, ""` after the three anchor checks; the over-cap `return False` branch is gone, replaced by a comment naming the cap advisory. `test_validate_brief_over_cap_anchored_passes` (test:1141) asserts `result == (True, "")` for a >275-word three-anchor brief. The R1 one-liner prints `True True True`.
- **Verdict**: PASS
- **Notes**: Targeted suite green (77 passed, 2 auth-skips).

### Requirement 2: Overage exposed as a separate non-blocking signal
- **Expected**: A helper returns 0 within-cap and the positive words-over-`GATE_BRIEF_WORD_CAP+25` count over-cap.
- **Actual**: `brief_word_overage(brief: str) -> int` (discovery.py:630-646) returns `len(brief.split()) - (GATE_BRIEF_WORD_CAP + 25)` clamped at 0. `test_brief_word_overage` (test:1204) parametrizes 0/10/400 filler words and asserts the exact words-over count over-cap and 0 within-cap.
- **Verdict**: PASS
- **Notes**: Placed adjacent to `validate_brief` as planned.

### Requirement 3: Generator persists + posts the over-cap brief
- **Expected**: For a non-empty, anchor-valid, over-cap brief, `_cmd_generate_brief` writes `brief.md`, prints to stdout, exits 0; a stubbed test asserts exit 0 AND `brief.md` exists AND its content equals the generated brief.
- **Actual**: After Task 1, an over-cap brief passes `validate_brief`, so control reaches the success path (discovery.py:894-909): stdout write + persist + exit 0. `test_over_cap_brief_persists_and_posts_ok_over_cap` (test:616) stubs `_run_brief_query` (ignoring `retry_feedback` so the first validation passes, no retry) and asserts `rc == 0`, `brief.md` exists, and its content equals the stubbed brief.
- **Verdict**: PASS

### Requirement 4: Over-cap posts carry an `ok_over_cap` telemetry status
- **Expected**: The `gate_brief_generated` event for a posted over-cap brief carries `status: "ok_over_cap"` and the actual `brief_word_count`.
- **Actual**: discovery.py:897 sets `status = "ok_over_cap" if brief_word_overage(brief) > 0 else "ok"`, emitted with the real `brief_word_count`. The R3 test asserts an emitted event with `status == "ok_over_cap"` and `brief_word_count == expected_word_count`.
- **Verdict**: PASS

### Requirement 5: Unchanged fallback for real failures
- **Expected**: Empty, SDK/dispatch-failed, and missing-anchor briefs still exit non-zero, do not persist, and emit a failure status; the existing fallback and excerpt tests pass unchanged.
- **Actual**: Empty → `empty`/return 1 (discovery.py:849); SDK/dispatch failure → `validation_failed`/return 1 (838-844); anchor-missing → retry, then `validation_failed`/return 1 (886-892). The advisory branch sits AFTER the three anchor checks, so anchor-missing still fails. `test_brief_failure_falls_back_to_architecture` and `test_validation_failed_event_includes_brief_excerpt` pass in the targeted run.
- **Verdict**: PASS

### Requirement 6: `ok_over_cap` registered in the events registry
- **Expected**: `grep -c 'ok_over_cap' bin/.events-registry.md` ≥ 1 AND the events-registry gate passes.
- **Actual**: The `gate_brief_generated` row (bin/.events-registry.md:119) enumerates `ok_over_cap` ("anchor-valid brief posted despite exceeding the advisory word cap"); `grep -c` = 1. `cortex-check-events-registry --audit` exits 0 (only pre-existing, unrelated STALE_DEPRECATION warnings on other rows, none fatal).
- **Verdict**: PASS

### Requirement 7: Prose-driven gate posts the over-cap brief with a soft note
- **Expected**: In `skills/discovery/SKILL.md`, the gate section (a) enumerates exactly three Architecture-fallback triggers — generator non-zero exit, `brief.md` missing, anchor validation failure — with no word-count among them, and (b) contains an explicit instruction to display the brief plus a one-line overage note when over-cap.
- **Actual**: SKILL.md:88 keeps the verbatim three-trigger sentence (non-zero exit OR missing OR decision-content validation failure), then adds: "When `brief.md` is present, the generator exited 0, and the decision-content anchors pass — but the brief's word count exceeds the advisory cap — the gate still displays the brief ... followed by a one-line overage note such as '(summary ran N words over the 275-word advisory cap)'." No word-count appears in the fallback-trigger list. `grep -ic 'overage'` = 1. `test_discovery_gate_presentation.py` marker-phrase pins pass (4 passed).
- **Verdict**: PASS
- **Notes**: The lone "word count" occurrence is inside the new over-cap soft-note sentence, not the fallback-trigger list — exactly where the spec wants it. 275 is correctly called the "advisory cap", not the target.

### Requirement 8: Plugin mirror regenerated with the SKILL.md edit
- **Expected**: `plugins/cortex-core/skills/discovery/SKILL.md` matches the edited canonical file; the drift gate passes.
- **Actual**: `diff skills/discovery/SKILL.md plugins/cortex-core/skills/discovery/SKILL.md` reports byte-identical; the mirror carries the same `overage` soft-note (`grep -ic 'overage'` = 1).
- **Verdict**: PASS

### Requirement 9: Gate-render contract test covers the over-cap path
- **Expected**: A test renders an over-cap anchored `brief.md` as the brief — NOT the Architecture fallback — asserting the rendered output contains the brief text and does NOT contain the Architecture body.
- **Actual**: `_render_gate` (test:289) appends the soft note when `brief_word_overage > 0` and returns the brief (not the fallback). Scenario C in `test_gate_renders_brief_not_architecture` (test:423) writes a >275-word three-anchor `brief.md` and asserts the rendered output contains the brief content AND the "advisory cap"/"over" soft-note marker AND does NOT contain `## Architecture` or `### Pieces`.
- **Verdict**: PASS

### Requirement 10: Reconcile every stale soft-cap wording surface
- **Expected**: `GATE_BRIEF_WORD_CAP` docstring no longer states over-cap causes fallback; `validate_brief` docstring reflects advisory cap; retry template drops the "hard ceiling"/posting-gate framing while preserving its word-target clause, per-anchor example tokens, and `{reason}`. `grep -c 'hard ceiling'` = 0 AND `test_retry_feedback_covers_example_tokens` passes AND the docstring no longer asserts an enforced maximum.
- **Actual**: `GATE_BRIEF_WORD_CAP` docstring (273-294) reframes the cap as a generation-time target + soft advisory signal and drops the retry-on-overflow pairing (`grep -c 'retry-on-overflow'` = 0). `validate_brief` docstring (587-590) states "Word cap is advisory, not enforced" (`grep -c 'must be at most'` = 0). `_GATE_BRIEF_RETRY_TEMPLATE` (381-396) has no "hard ceiling" (`grep -c` = 0) and retains "Rewrite at no more than {GATE_BRIEF_WORD_CAP} words", all three anchor token enumerations, and `{reason}`. `test_retry_feedback_covers_example_tokens` passes.
- **Verdict**: PASS

### Requirement 11: Generation-time word target retained deliberately
- **Expected**: The rubric keeps "write no more than `{GATE_BRIEF_WORD_CAP}` words" (`grep -c 'no more than'` ≥ 1) AND the docstring documents the target-vs-acceptance split as intentional.
- **Actual**: The rubric (discovery.py:343) keeps "Word target: write no more than {GATE_BRIEF_WORD_CAP} words"; `grep -c 'no more than'` = 4. The rubric docstring (373-377) and the `GATE_BRIEF_WORD_CAP` docstring (291-293) document the target-vs-acceptance decoupling as intentional (spec Req 11).
- **Verdict**: PASS

### Requirement 12: Pin R5's fallback guarantee against a cap-branch reorder + clarify the fixture test
- **Expected**: (a) A test asserts an over-cap AND anchor-missing brief still fails with the anchor reason; (b) the `word_count <= cap` assertion in `test_brief_passes_all_fixtures` is documented as a corpus/fixture-quality check, NOT a production contract.
- **Actual**: `test_validate_brief_over_cap_anchor_missing_still_fails` (test:1156) feeds a >275-word brief missing the tradeoff anchor and asserts `not ok` AND `"tradeoff" in reason` — non-tautological; it trips if Task 1 short-circuits over-cap before the anchor checks. The fixture assertion (test:158-170) carries a comment naming it a "CORPUS-QUALITY check ... NOT a production-contract assertion" and the failure message says "corpus-quality check on canonical fixtures -- not a production contract".
- **Verdict**: PASS

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `brief_word_overage` mirrors the existing `validate_brief` public-helper shape (snake_case, `(arg) -> int`), placed adjacent to it. The `ok_over_cap` status follows the existing `ok`/`empty`/`validation_failed` status vocabulary. Test names follow the file's `test_<behavior>` convention.
- **Error handling**: Appropriate and unchanged on the failure paths. The over-cap case is routed through the existing success path (persist guarded by try/except OSError, event emission best-effort with OSError swallowed) — no new error surface introduced. The advisory branch is purely additive logic on top of validated-true control flow.
- **Test coverage**: Every plan verification step executed and green. Targeted suite `tests/test_discovery_gate_brief.py` = 77 passed, 2 skipped (auth-gated fixtures); `tests/test_discovery_gate_presentation.py` = 4 passed (marker-phrase + Architecture-vocab pins). All grep acceptance checks confirmed (R1 one-liner `True True True`; `ok_over_cap` registered =1; `hard ceiling`/`must be at most`/`retry-on-overflow` =0; `no more than` =4; `overage` in both SKILL.md and mirror =1). Mirror byte-identical. Events-registry `--audit` exits 0. The two environmental pre-existing failures (mcp subprocess DNS, resolve_backlog drift baseline) are out-of-scope and correctly excluded.
- **Pattern consistency**: Follows existing project conventions — new event status registered in `bin/.events-registry.md` (per the skill-helper-module constraint), canonical SKILL.md edited with auto-regenerated mirror committed together, docstring-and-code changed atomically (the plan's Phase-1 docstring sequencing). The `ok_over_cap` status is produced (discovery.py:897) but never consumed/switched-on, matching the spec's "inert telemetry" technical constraint.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
