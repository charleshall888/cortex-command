# Review: fix-validate-brief-substring-anchors-that

## Stage 1: Spec Compliance

### Requirement 1: Rubric f-string substitution
- **Expected**: `GATE_BRIEF_RUBRIC` renders with the numeric word-cap value substituted from `GATE_BRIEF_WORD_CAP`, not the literal token. Acceptance: `python3 -c "from cortex_command.discovery import GATE_BRIEF_RUBRIC; assert '250' in GATE_BRIEF_RUBRIC and 'GATE_BRIEF_WORD_CAP' not in GATE_BRIEF_RUBRIC"` exits 0.
- **Actual**: `cortex_command/discovery.py:302` defines `GATE_BRIEF_RUBRIC` as an f-string; line 332 interpolates `{GATE_BRIEF_WORD_CAP}`. Acceptance command exits 0; the literal token `GATE_BRIEF_WORD_CAP` is absent and `250` is present.
- **Verdict**: PASS
- **Notes**: —

### Requirement 2: Brief-text observability on validation failure
- **Expected**: `gate_brief_generated` events with `status: "validation_failed"` include a `brief_excerpt` field (first 200 chars of the rejected brief). Successful events do not require it. Test `test_validation_failed_event_includes_brief_excerpt` asserts the field is present and non-empty.
- **Actual**: `_emit_event` (`discovery.py:891-922`) adds `payload["brief_excerpt"] = brief_text[:200]` only when `status == "validation_failed"` and `brief_text` is non-empty. The retry / first-validation / SDK-failure call sites at lines 952-981 thread the actual brief text into the event. `test_validation_failed_event_includes_brief_excerpt` (test file:409-511) stubs `_run_brief_query` with a deterministic failing brief and asserts `brief_excerpt == rejected_brief[:200]`. Test passes.
- **Verdict**: PASS
- **Notes**: The events-registry entry for `gate_brief_generated` already exists at `bin/.events-registry.md:121`, satisfying the spec's "entry already exists" precondition.

### Requirement 3: Broadened anchor set — decision
- **Expected**: `validate_brief()` accepts 12 decision tokens with word-boundary regex; parametrized test asserts each.
- **Actual**: `_VALIDATE_BRIEF_DECISION_TOKENS` (`discovery.py:593-606`) enumerates the exact 12 tokens (`decide`, `decided`, `decision`, `decisions`, `chose`, `chosen`, `concluded`, `settled`, `selected`, `picked`, `opted`, `agreed`). `_anchor_match` uses `re.search(r"\b" + re.escape(tok) + r"\b", brief, re.IGNORECASE)`. `test_validate_brief_decision_anchor_paraphrases` is parametrized over the 12 tokens; all 12 pass.
- **Verdict**: PASS

### Requirement 4: Broadened anchor set — alternatives
- **Expected**: `validate_brief()` accepts 9 alternatives tokens (with `considered` and `considerations` enumerated separately).
- **Actual**: `_VALIDATE_BRIEF_ALTERNATIVES_TOKENS` (`discovery.py:614-624`) enumerates the exact 9 tokens; both `considered` and `considerations` present. `test_validate_brief_alternatives_anchor_paraphrases` is parametrized over the 9 tokens; all pass.
- **Verdict**: PASS

### Requirement 5: Broadened anchor set — tradeoff
- **Expected**: `validate_brief()` accepts 9 tradeoff tokens including hyphenated `trade-off`.
- **Actual**: `_VALIDATE_BRIEF_TRADEOFF_TOKENS` (`discovery.py:633-643`) enumerates the exact 9 tokens. `test_validate_brief_tradeoff_anchor_paraphrases` parametrized over 9 tokens; all pass including `trade-off`.
- **Verdict**: PASS

### Requirement 6: Word-boundary matching prevents false positives
- **Expected**: Use `re.search(r"\bWORD\b", text, re.IGNORECASE)`. FP test covers 7 tokens.
- **Actual**: `_anchor_match` (`discovery.py:651-661`) uses word-boundary regex with `re.escape`. `test_validate_brief_word_boundary_false_positives` parametrized over the exact 7 tokens in the spec list (`optional`, `optionality`, `committee`, `unsettled`, `disagreed`, `costume`, `pickup`); all 7 pass and the failure reason names the target anchor.
- **Verdict**: PASS

### Requirement 7: Shared example-tokens constant
- **Expected**: Module-level `_GATE_BRIEF_EXAMPLE_TOKENS: dict[str, tuple[str, ...]]` mapping anchor names to example token tuples; `GATE_BRIEF_RUBRIC` references those tokens via f-string interpolation.
- **Actual**: `_GATE_BRIEF_EXAMPLE_TOKENS` (`discovery.py:285-289`) is the required dict with three anchors mapped to 4-tuples. `GATE_BRIEF_RUBRIC` (lines 311-330) interpolates from this dict at multiple sites. Acceptance command `python3 -c "...assert all(tok in GATE_BRIEF_RUBRIC for tokens in _GATE_BRIEF_EXAMPLE_TOKENS.values() for tok in tokens)"` exits 0.
- **Verdict**: PASS

### Requirement 8: Canonical-floor-pinned parity test (validator side)
- **Expected**: Test file declares a frozen literal canonical token set (30 tokens) NOT imported from `cortex_command/discovery.py`; for every token in the floor, build a minimal brief and assert `validate_brief()` returns `(True, "")`.
- **Actual**: `tests/test_discovery_gate_brief.py:843-880` declares `_CANONICAL_FLOOR_DECISION_TOKENS`, `_CANONICAL_FLOOR_ALTERNATIVES_TOKENS`, `_CANONICAL_FLOOR_TRADEOFF_TOKENS` as frozen literals (no import from `discovery`). `test_validate_brief_canonical_floor` is parametrized over all 30 cases; all pass with `result == (True, "")`.
- **Verdict**: PASS

### Requirement 9: Retry-feedback as bound module constant
- **Expected**: Retry-feedback prose extracted to a module-level f-string constant interpolating from `_GATE_BRIEF_EXAMPLE_TOKENS`; includes every token from each anchor's full example set; instructs model to include at least one token per anchor.
- **Actual**: `_GATE_BRIEF_RETRY_TEMPLATE` (`discovery.py:364-379`) is built from f-string segments that interpolate `_GATE_BRIEF_EXAMPLE_TOKENS['decision']`, `['alternatives']`, and `['tradeoff']` via `', '.join(...)`. Uses `{reason}` as a `str.format` placeholder for dynamic content. Includes the directive "Include at least one token from each anchor." Call site (line 952) renders with `.format(reason=reason)`. `test_retry_feedback_covers_example_tokens` confirms every token appears in the rendered output.
- **Verdict**: PASS

### Requirement 10: Validate_brief error messages name the broadened anchors
- **Expected**: Anchor-missing failure reasons enumerate at least three representative tokens per failed anchor; test asserts reason contains "chose" and "settled" for decision-missing.
- **Actual**: Error reasons in `validate_brief` (`discovery.py:706-725`):
  - decision: `"one of: decided, chose, settled, ..."`
  - alternatives: `"one of: alternatives, options, considered, weighed, evaluated, rejected, ..."`
  - tradeoff: `"one of: tradeoff, cost, drawback, downside, compromise, risk, ..."`
  `test_validate_brief_error_messages_name_broadened_anchors` asserts decision reason contains `chose` and `settled`, alternatives reason enumerates ≥2 of `{considered, weighed, evaluated, rejected}`, tradeoff reason enumerates ≥2 of `{drawback, downside, compromise, risk}`. All assertions pass.
- **Verdict**: PASS

### Requirement 11: Cross-cutting Phase 2 acceptance gate
- **Expected**: A `just` recipe (or equivalent) runs Req 1 python3 check + combined `pytest -k "validate_brief or retry_feedback or validation_failed or canonical_floor"` and exits 0 only if all pass.
- **Actual**: `justfile:398-403` defines `brief-gate-acceptance` recipe with `set -euo pipefail`. It runs (a) Req 1 rubric f-string assertion, (b) Req 7 example-tokens-present assertion, and (c) `uv run pytest tests/test_discovery_gate_brief.py -v -k "validate_brief or retry_feedback or validation_failed or canonical_floor"`. `just brief-gate-acceptance` executes successfully with 70 passed.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None — the implementation lives entirely inside `cortex_command/discovery.py`, `tests/test_discovery_gate_brief.py`, and `justfile`. It does not introduce new architectural patterns or change project-level constraints. The `gate_brief_generated` event schema change is additive/backward-compatible (the new `brief_excerpt` field is optional), matching the `parent_epic_loaded` precedent referenced in the spec. The shared `_GATE_BRIEF_EXAMPLE_TOKENS`/`_GATE_BRIEF_RETRY_TEMPLATE` module constants are an example of the "skill-helper modules" pattern already enumerated in `project.md:35`.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the file. Underscore-prefixed module-private constants (`_GATE_BRIEF_EXAMPLE_TOKENS`, `_GATE_BRIEF_RETRY_TEMPLATE`, `_VALIDATE_BRIEF_*_TOKENS`) follow the existing convention (e.g. `_CHECKPOINT_VALUES`, `_RESPONSE_VALUES`). Public constants (`GATE_BRIEF_WORD_CAP`, `GATE_BRIEF_RUBRIC`) keep their public naming. Test function names follow the existing `test_validate_brief_*` pattern.
- **Error handling**: Appropriate. `validate_brief` returns `(bool, str)` tuples; `_emit_event` swallows `OSError` as best-effort (consistent with the existing emitters in the file). The retry-feedback `.format()` placeholder discipline (using `{reason}` as the only non-f-string interpolation point) is explicitly documented in the constant's docstring, which both prevents accidental use of `_GATE_BRIEF_RETRY_TEMPLATE.format(...)` with unrelated keys and explains the asymmetry between agent-facing examples and validator-accepted vocabulary.
- **Test coverage**: Strong. The 71-test suite (38 new tests across Reqs 2-10) covers each anchor's full vocabulary (37 parametrized cases), 7 word-boundary FPs, every-anchor error-message enumeration, retry-feedback token coverage, and a 30-case canonical-floor parity. The independent literal in the test file (not imported from `discovery.py`) closes the lockstep-shrinkage regression mode the spec called out. The brief-excerpt observability test uses `monkeypatch` to stub the SDK so it runs without auth.
- **Pattern consistency**: Matches existing project conventions. The canonical-floor docstrings cross-reference the spec ID and the parity test, mirroring the existing `GATE_BRIEF_WORD_CAP` docstring's style of citing derivation. The justfile recipe uses the existing `#!/usr/bin/env bash` + `set -euo pipefail` pattern visible in adjacent recipes. The `brief_excerpt` field-presence asymmetry (only on `validation_failed`) follows the same backward-compat shape as `parent_epic_loaded` referenced in the spec.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
