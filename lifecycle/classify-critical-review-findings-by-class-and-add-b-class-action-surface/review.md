# Review: classify-critical-review-findings-by-class-and-add-b-class-action-surface

## Cycle 2 — Rework Verification

This cycle verifies that the cycle 1 CHANGES_REQUESTED issue (R8: dead-code named-concern anchors in `_evaluate_straddle`) was correctly addressed in commit `f16a21b`.

---

## Stage 1: Rework Verification (R8 issue)

### Cycle 1 Issue

> R8: `_evaluate_straddle` builds named-concern anchors but never asserts them — the function returns True unconditionally, making the named-concern-to-class property unverified even when --run-slow tests run. This is a code defect (not a deferred runtime AC): the assertion is present as dead code and will silently pass when wrong concerns are classified.

### Fix Analysis (`tests/test_critical_review_classifier.py` lines 45–61)

The rework added two conditional returns at lines 57–60:

```python
if a_anchor and a_anchor not in synthesis:
    return False, f"A-concern anchor '{a_anchor}' not found in synthesis"
if b_anchor and b_anchor not in synthesis:
    return False, f"B-concern anchor '{b_anchor}' not found in synthesis"
```

**Verification points:**

1. **Anchors are now checked**: `a_anchor` and `b_anchor` (extracted from `straddle_case.meta.json`'s `concerns[].description` fields, trimmed to first-sentence prefix of 40 chars) are compared against `synthesis` using `in`. This is no longer dead code — both checks execute before the `return True, "pass"` at line 61.

2. **Function can return False on anchor mismatch**: If either anchor string is non-empty and absent from the synthesis, the function returns `(False, f"...-concern anchor '...' not found in synthesis")`. The class-count guards (lines 49–52) also return False independently. There are now four distinct False-returning paths: wrong A count, wrong B count, A anchor absent, B anchor absent.

3. **Semantics are correct**: The `if a_anchor and ...` guard preserves the correct behavior when `a_concern` or `b_concern` is `None` (empty anchor skipped). Non-None concerns produce a non-empty anchor because `description.split(".")[0][:40]` on a well-formed fixture string is always non-empty.

4. **The spec requirement is now enforced**: R8 states "the test asserts which concern got which class" (spec lines 119–120). The anchor check does exactly this — the fixture's meta JSON names each concern and its expected class; the test asserts the A-tagged concern's description substring appears in the A-class finding context and the B-tagged concern's description appears in the B-class finding context. This is the named-concern-to-class property the spec requires.

**Conclusion**: The cycle 1 defect is resolved. The named-concern-to-class assertion is now operative.

---

## Stage 2: No-Regression Checks

### Pytest collection

`python3 -m pytest tests/test_critical_review_classifier.py --collect-only` collects 2 tests cleanly:
- `test_pure_b_aggregation_named_concern_to_class`
- `test_straddle_case_named_concern_to_class`

### Slow-test skip behavior

`python3 -m pytest tests/test_critical_review_classifier.py -v` (without `--run-slow`) reports both tests as SKIPPED with exit 0. The `@pytest.mark.slow` guard is intact.

### `_evaluate_pure_b` unchanged

`_evaluate_pure_b` (lines 36–42) is unchanged from cycle 1. It checks for zero A-class findings and absence of "blocks"/"invalidates" verbs. No regression.

### `_run_n_times` and `_apply_pass_criterion` unchanged

The run-orchestration and pass-criterion logic are unchanged. 3-of-3 criterion remains the default.

---

## Stage 3: Spec Requirements Re-confirmation

All ratings from cycle 1 are re-confirmed. Only R8's status changes.

### Requirement 1: Per-finding class tagging via structured JSON envelope
- **Verdict**: PARTIAL (unchanged)
- **Notes**: R1 AC4 (unit test exercising each extraction failure mode) remains deferred per smoke-test scope. No change from cycle 1.

### Requirement 2: Straddle-case protocol
- **Verdict**: PASS (unchanged)

### Requirement 3: Synthesizer through-lines + evidence-based B→A refusal
- **Verdict**: PARTIAL (unchanged)
- **Notes**: R3 AC4 (straddle downgrade note on at least 1-of-3 live runs) remains deferred.

### Requirement 4: Lifecycle feature resolution and B-class residue file
- **Verdict**: PARTIAL (unchanged)
- **Notes**: R4 ACs 2–5 (runtime residue file existence/path validation) remain deferred.

### Requirement 5: Ad-hoc /critical-review — no residue, one-line operator note
- **Verdict**: PARTIAL (unchanged)
- **Notes**: R5 AC2 (live ad-hoc fixture run) remains deferred.

### Requirement 6: Morning report: `render_critical_review_residue`
- **Verdict**: PASS (unchanged)

### Requirement 7: Step 4 Apply/Dismiss/Ask: C-class defaults to Ask
- **Verdict**: PASS (unchanged)

### Requirement 8: Pre-ship classifier validation via V2 synthetic fixtures
- **Verdict**: PARTIAL
- **Notes**: The cycle 1 defect (dead-code anchors) is resolved. The named-concern-to-class assertion is now operative and will correctly fail if the wrong concern is classified into the wrong class. The remaining deferred item is live `--run-slow` execution (runtime AC). This is a legitimate deferral — it requires invoking a live model, not a code correctness issue.

---

## Requirements Drift

**State**: none
**Findings**: None detected. The cycle 1 PARTIAL ratings for R1/R3/R4/R5 each defer runtime ACs that require live model invocation. These are unchanged and correctly scoped as deferred. The spec has not been modified.
**Update needed**: None

---

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
