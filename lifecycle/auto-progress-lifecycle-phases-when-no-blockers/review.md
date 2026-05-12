# Review: auto-progress-lifecycle-phases-when-no-blockers

## Summary

All 12 requirements from spec.md are implemented and verified. Phase-detector
test suite (`test_lifecycle_auto_advance.py`, 8 cases) passes. Kept-pauses
parity test (`test_lifecycle_kept_pauses_parity.py`, 2 cases) passes. Full
lifecycle test suite (`test_lifecycle_state.py`, `test_lifecycle_phase_parity.py`,
`test_common_utils.py`) all pass — 87 lifecycle-related tests. Full repo test
suite passes 764 tests.

## Per-requirement verification

| # | Requirement | Acceptance status |
|---|-------------|-------------------|
| R1 | Fix review-cycle counter to read from events.log | ✅ `common.py:185–217` counts `review_verdict` events; both positive and negative fixtures pass |
| R2 | Register `spec_approved`/`plan_approved` event types | ✅ `bin/.events-registry.md` adds three rows (spec_approved, plan_approved, lifecycle_cancelled) with full schema, producer, and one-line description |
| R3 | Phase detector reads approval events with migration sentinel | ✅ `common.py:264–296` applies the spec_approved/transitioned_out lookup; in-flight lifecycles with prior `phase_transition: specify→plan` pass through (verified via test_lifecycle_auto_advance.py) |
| R4 | Disambiguate "completing a phase artifact" | ✅ `skills/lifecycle/SKILL.md:169–183` adds per-phase completion rule covering all 5 phases |
| R5 | Rewrite specify.md §4 + emit spec_approved | ✅ `skills/lifecycle/references/specify.md:155–172` enumerates Approve/Request changes/Cancel, emits event on Approve, removes "must approve before proceeding" |
| R6 | Rewrite plan.md §4 + emit plan_approved | ✅ `skills/lifecycle/references/plan.md:277–296` enumerates options, emits event on Approve, removes "must approve before implementation begins" |
| R7 | Enrich resume-staleness prompt | ✅ `skills/lifecycle/SKILL.md:106–112` directs `os.path.getmtime`/`stat` AND `git log --since` invocations |
| R8 | Auto-skip refine when both artifacts exist | ✅ `skills/refine/SKILL.md:46–64` replaces "offer to re-run or exit" with auto-skip-to-Step-6; no CLI flag added |
| R9 | Per-phase canonical auto-advance phrasing | ✅ plan.md, implement.md, review.md, complete.md all contain "Proceed automatically" + "do not ask the user for confirmation" |
| R10 | Kept-pauses inventory in SKILL.md | ✅ `skills/lifecycle/SKILL.md:189–215` enumerates 19 sites with file:line + rationale; parity-enforced by R12 |
| R11 | Phase-detector regression tests | ✅ `tests/test_lifecycle_auto_advance.py` — 8 tests passing covering happy-path, approval gates, migration sentinels, cycle counter |
| R12 | Kept-pauses parity check | ✅ `tests/test_lifecycle_kept_pauses_parity.py` — 2 tests passing (inventory→source and source→inventory directions) |

## Requirements Drift

No drift detected. All requirements bear on the lifecycle skill itself (the auditing surface) — they do not modify behavior outside the lifecycle/refine skill prose and the `common.py` phase detector. No new requirements emerged that need to be back-propagated to `requirements/*.md`.

## Code-quality observations

- `cortex_command/common.py` change is additive and preserves the return shape (`phase`, `checked`, `total`, `cycle`). Existing consumers (dashboard, statusline ladder, backlog/generate_index.py) continue to work; the statusline ladder was updated in lockstep with the canonical Python (mirror enforced via `test_lifecycle_phase_parity.py`).
- The migration sentinel covers in-flight lifecycles authored before approval events existed. Spot-checked against 4 existing `lifecycle/*/events.log` files in the repo — all of them have `phase_transition: specify→plan` and `phase_transition: plan→implement` events, so the sentinel correctly classifies them as already-approved.
- Test fixtures (`tests/fixtures/state/plan|implement|review/events.log` and `tests/fixtures/lifecycle_phase_parity/*/events.log`) updated to include `spec_approved`/`plan_approved` events, matching the new contract.
- Dual-source plugin mirror (`plugins/cortex-core/skills/...`) regenerated via `just build-plugin` — byte-parity test passes.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "requirements_drift": "none"}
```

Auto-advance to Complete.
