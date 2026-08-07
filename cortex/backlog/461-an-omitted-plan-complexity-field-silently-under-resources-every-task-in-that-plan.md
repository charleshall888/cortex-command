---
schema_version: "1"
uuid: 6ce97790-5385-4f95-8ef3-08cb55f0a0b8
title: An omitted plan Complexity field silently under-resources every task in that plan
status: complete
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-07
tags: ['overnight', 'pipeline', 'tiering']
areas: ['overnight-runner']
complexity: simple
---
## Why

`cortex_command/pipeline/parser.py:396` defaults a task's complexity to `simple` when the plan omits the field:

    complexity = _parse_field_string(task_body, "Complexity") or "simple"

Unlike the lifecycle tier seed — which is inert, since every phase fork tests only `tier == "complex"` — **this value drives real resource allocation**:

- `pipeline/dispatch.py:153-157` — `simple` gets `max_turns: 150, max_budget_usd: 5.00`; `moderate` gets `200 / $25.00`; `complex` gets `300 / $50.00`.
- `pipeline/dispatch.py:181-185` — `(simple, low)` and `(simple, medium)` resolve to `"low"` reasoning effort, where the same criticalities at `moderate` resolve to `"high"`.

Measured across 641 `plan.md` files with parseable task sections in `cortex-command`, `wild-light`, `pixel-art-generator`, and `gaggimate-barista`: **328 of 5,713 tasks (5.7%) carry no `Complexity` field.**

The distribution is what makes it matter. Omission is **clustered whole-plan**, not scattered: `weapon-compositing-implementation-overlay-registration-system` 17/17, `scale-research-fanout-by-complexity` 11/11, `migrate-personal-data-private-repo` 10/10, and several more at 9/9 and 10/10. When a plan omits the field, *every* task in that feature runs at the `simple` floor — a $5 budget, 150 turns, and `low` effort for work nobody classified as simple.

Note the contrast with the adjacent case: a present-but-out-of-vocabulary value normalizes to `complex` (safe over-provision) and is recorded for the caller to surface. An **absent** value fails the other way, silently, with no record.

Found while refining `#453`, which argued a placeholder tier seed was harmful. On the surface `#453` names, the seed turned out to be inert. On this surface the same defect is real.

## Role

Stop an omitted plan field from silently selecting the cheapest resource tier, so an unclassified task is not indistinguishable from one classified as trivial.

## Integration

The asymmetry is the lever: out-of-vocabulary already over-provisions and reports. Absent should plausibly do the same rather than under-provision in silence.

- Default absent to the safe direction (`moderate` or `complex`) and record it, matching the out-of-vocabulary branch's existing behavior.
- Or surface the omission to the caller the way `normalized_complexities` already does, and let the operator decide before dispatch.
- Or make the field required at plan-parse time and fail loudly — the plan is machine-generated, so a missing field is a producer bug worth catching at the source.

## Edges

- Only overnight-dispatched work reaches `dispatch.py`; interactive plans never consult `TIER_CONFIG`. The blast radius is the overnight path, and the ticket should not claim more.
- Do not raise the default without checking the cost direction — over-provisioning every unclassified task to `complex` moves the budget ceiling from $5 to $50 per task. `moderate` may be the honest middle; the out-of-vocabulary branch's choice of `complex` was made for a different case (a value that was *stated* and unrecognized) and does not automatically transfer.
- The producer side deserves a look: 641 plans and 5.7% omission suggests the plan template or the planning prompt does not always emit the field. Fixing the producer may be cheaper than defending the consumer, and the two are not exclusive.
- Deletion bias, efficiency prong: this removes no surface. Its expected effect is on 328 measured tasks whose dispatch was under-resourced, not on prose size.

## Touch points

- `cortex_command/pipeline/parser.py:396` — the default
- `cortex_command/pipeline/parser.py:397-401` — the out-of-vocabulary branch that already over-provisions and records
- `cortex_command/pipeline/dispatch.py:153-157` — `TIER_CONFIG`, turn and budget ceilings
- `cortex_command/pipeline/dispatch.py:177-190` — `_EFFORT_MATRIX`, reasoning effort
- `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md` — Open Question 5, where this was found
