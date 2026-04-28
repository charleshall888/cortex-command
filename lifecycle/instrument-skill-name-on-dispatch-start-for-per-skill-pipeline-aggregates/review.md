# Review: instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates (cycle 2)

## Summary

The cycle-1 blocker is fixed. The rework commit `4dedef4` adds `"skill": start.get("skill"), "cycle": start.get("cycle")` to both matched-start branches of `pair_dispatch_events()` (metrics.py:400–401 for `dispatch_complete`, and metrics.py:434–435 for `dispatch_error`), leaving the orphan branches deliberately untouched per the cycle-1 prescription. The docstring at metrics.py:340–361 now documents the two new optional keys and explains the matched-only-not-orphan rule. The new `TestPairAggregatorEndToEnd` class in test_metrics.py:812–902 exercises the production data path end-to-end (raw events → `pair_dispatch_events` → `compute_skill_tier_dispatch_aggregates`) for both `skill="implement"` (non-review-fix bucket) and `skill="review-fix", cycle=2` (three-dimensional bucket). Both tests assert the new bucket key is present and the legacy bucket is absent — so any future regression that breaks propagation will be caught at the integration boundary, not just at the unit-test boundary.

I empirically re-ran the cycle-1 repro against current main:

```
paired skill key: implement
Aggregator keys: ['implement,simple']
Review-fix aggregator keys: ['review-fix,simple,2']
```

Before the rework, the same fixture produced `['legacy,simple']`. The aggregator now operates on real production data flow as the spec intends — per-skill cost analysis is unblocked, and the parent epic's ROI/ranking gate can proceed.

`pytest cortex_command/pipeline/tests/test_metrics.py::TestPairAggregatorEndToEnd -v` passes (2/2). Full pipeline test suite passes (231/231). The full `test_metrics.py` file passes 36/36. No regressions introduced by the rework.

## Stage 1: Spec Compliance

| Req | Verdict | Notes |
|-----|---------|-------|
| R1 — `Skill` Literal | PASS | (cycle 1 PASS, unaffected) dispatch.py declares the 7-element Literal. |
| R2 — `dispatch_task` signature | PASS | (cycle 1 PASS, unaffected) All 5 new params keyword-only with the spec'd defaults. |
| R3 — Runtime guard rejects unregistered skill | PASS | (cycle 1 PASS, unaffected) `ValueError` raised; test exists. |
| R4 — `dispatch_start` key order | PASS | (cycle 1 PASS, unaffected) Keys emitted in spec'd order; cycle conditional. |
| R5 — All 7 caller files pass `skill=` | PASS | (cycle 1 PASS, unaffected) Verified by line-by-line inspection of all 9 call sites. |
| R6 — retry.py threads attempt/escalated/escalation_event | PASS | (cycle 1 PASS, unaffected) test_retry.py covers the 4-attempt sequence. |
| R7 — `compute_skill_tier_dispatch_aggregates()` | PASS | The cycle-1 PARTIAL is resolved. metrics.py:400–401 (dispatch_complete matched-start) and metrics.py:434–435 (dispatch_error matched-start) now propagate `skill` and `cycle` from the start event; orphan branches at metrics.py:408–418 and :442–452 deliberately omit these keys (no start to read from), so orphans bucket via the existing `rec.get("skill") or "legacy"` fallback. The `TestPairAggregatorEndToEnd` class adds two end-to-end tests covering both `skill="implement"` and `skill="review-fix", cycle=2` propagation. Aggregator now produces correct buckets against synthetic production-shape events: `['implement,simple']` and `['review-fix,simple,2']`. |
| R8 — Missing-skill historical events bucket as legacy | PASS | (cycle 1 PASS, unaffected) The orphan-branch behavior preserves this — orphans omit `skill` so the aggregator's `rec.get("skill") or "legacy"` fallback fires. |
| R9 — `--report skill-tier-dispatch` CLI mode | PASS | (cycle 1 PASS, unaffected) argparse choice extended; conditional formatter branch wired. |
| R10 — Both aggregators in metrics.json | PASS | (cycle 1 PASS, unaffected) `skill_tier_dispatch_aggregates` emitted alongside `model_tier_dispatch_aggregates`. |
| R11 — Report header documents idempotency-skip + orphan | PASS | (cycle 1 PASS, unaffected) Both caveat sentences emitted unconditionally. |
| R12 — All existing tests pass | PASS | Re-verified: 231/231 pipeline tests pass; 36/36 test_metrics.py pass; the 2 new TestPairAggregatorEndToEnd tests pass. No regressions. |
| R13 — `cycle` threaded at both review-fix sites | PASS | (cycle 1 PASS, unaffected) review_dispatch.py:393 (cycle=1) and :508 (cycle=2). |
| R14 — Symmetric runtime guard rejects cycle for non-review-fix | PASS | (cycle 1 PASS, unaffected) `ValueError` raised; test exists. |

### R7 fix verification (the cycle-1 blocker)

The rework is precisely targeted:

- metrics.py:400–401: `"skill": start.get("skill"), "cycle": start.get("cycle")` added to the `dispatch_complete` matched-start `results.append({...})` block (after `untiered: False`).
- metrics.py:434–435: same addition to the `dispatch_error` matched-start block.
- metrics.py:340–361: docstring updated with two new optional keys and an explicit explanation that orphans omit them.
- Orphan branches at metrics.py:408–418 (orphan complete) and :442–452 (orphan error) are unchanged — no `skill`/`cycle` keys, so the aggregator's existing legacy fallback is the only path that fires for orphans. This preserves R8's contract.
- test_metrics.py:812–902 (TestPairAggregatorEndToEnd): two integration-boundary tests, one per code branch (matched complete + non-review-fix; matched complete + review-fix with cycle).

All four tests-of-the-fix pass; the cycle-1 repro against the fixed code now produces the expected `implement,simple` and `review-fix,simple,2` buckets.

## Stage 2: Code Quality

- The fix is the minimal-correct-change for the cycle-1 issue: 4 added lines in two matched-start branches plus a docstring update. No incidental refactoring, no parameter shuffling, no widening of the function's surface.
- The orphan-branch carve-out is correctly preserved: if `skill`/`cycle` were propagated through orphans, they would always be `None`, which would require a more complex aggregator branch. Leaving the keys absent on orphans lets the existing `rec.get("skill") or "legacy"` fallback handle them uniformly with historical-data orphans, matching R8.
- The docstring update is materially helpful: it explicitly states the matched-vs-orphan asymmetry, so future maintainers have an in-source explanation for why the orphan branches look different.
- The `TestPairAggregatorEndToEnd` class is well-scoped: it deliberately constructs raw events (not paired records) to exercise the integration boundary that `TestSkillTierDispatchAggregates` bypasses by design. The class docstring makes this scope split explicit, which is the right way to document a class whose purpose is to catch a regression class that the unit tests cannot. The `_start` and `_complete` helpers are simple and parametrized minimally — `_start` only adds the `cycle` key when non-None, mirroring the production emission contract.
- Naming is consistent with the existing test-class conventions in the file (`TestPairDispatchEvents`, `TestSkillTierDispatchAggregates`, `TestReportTierDispatch`).
- No dead code, no test-only helpers leaking out of the test file, no shadowing of the module-level helpers.

No quality concerns.

## Requirements Drift

State: none

The cycle-1 review found no drift; the cycle-2 rework is a localized fix to data propagation in a single function and adds two end-to-end tests in the same suite. It does not introduce new behavior surface, modify `requirements/project.md`-, `requirements/observability.md`-, or `requirements/pipeline.md`-governed contracts. The append-only JSONL constraint (pipeline.md:129) remains honored — no fields are removed or renamed in `pair_dispatch_events`'s output shape; the two new keys are additive. The orphan-branch carve-out preserves R8's legacy-bucketing contract. The dashboard pipeline (observability.md:30–34) is unaffected.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 2,
  "issues": [],
  "requirements_drift": "none"
}
```
