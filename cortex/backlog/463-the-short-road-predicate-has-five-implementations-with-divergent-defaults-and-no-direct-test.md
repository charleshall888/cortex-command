---
schema_version: "1"
uuid: 9682402f-f8a0-4d23-9dbb-e126dac144eb
title: The short-road predicate has five implementations with divergent defaults and no direct test
status: backlog
priority: medium
type: chore
created: 2026-08-06
updated: 2026-08-06
tags: ['lifecycle', 'predicate', 'tests', 'refactor']
areas: ['lifecycle']
---
## Why

Measured 2026-08-06 while researching #452. The short-road predicate `criticality in {high, critical} OR tier == complex` is reimplemented **five times**, none importing a shared constant:

| Site | What it gates |
|---|---|
| `cortex_command/common.py:1084` — `requires_review()` | the shared helper, imported by exactly one module |
| `cortex_command/lifecycle/spec_approve.py:153` | spec exit: Plan vs direct-to-implement |
| `cortex_command/lifecycle/implement_transition.py:175` | implement exit: Review vs complete |
| `cortex_command/lifecycle/next_verb.py:245` | served-loop escalation |
| `cortex_command/overnight/advance_lifecycle.py:265` | morning-review gate before machine-marking complete |

Two concrete hazards, both verified:

**The defaults already disagree.** `spec_approve.py:126` defaults tier to `"simple"`; `implement_transition.py:99` and `advance_lifecycle.py:254` default it to `"moderate"`. Benign while the predicate is `== "complex"`, and latent the moment anyone adds a band or converts it to a rank comparison.

**No test can catch a missed edit.** `common.requires_review` has **zero direct unit tests**, and `cortex_command/overnight/tests/test_outcome_router.py` patches it at 38 sites rather than exercising it — so that suite validates routing *given* a result, never the predicate's logic. `advance_lifecycle.py:265`'s inline copy has no direct test of its criticality branch either. A change to the predicate that misses one or more copies passes CI green.

The duplication is already known and already unenforced: `advance_lifecycle.py:256-263` carries the comment *"Any future edit to either rule must change both"* — a prose instruction with nothing behind it.

## Role

Collapse the five copies behind `common.requires_review` and give it real tests, so a later predicate change has one site and a test that fails when it is wrong.

## Integration

`common.requires_review(tier, criticality)` already exists and already has the right signature; four call sites need to adopt it. `advance_lifecycle.py` and `next_verb.py` additionally OR in `reduction.corrupted`, so the helper either grows a `corrupted` parameter or callers keep that clause locally — decide during refine.

## Edges

- **Ship as a standalone provable no-op, never bundled with a behavior change.** All five currently reduce to the same boolean on the current vocabulary, so the refactor is diff-verifiable today. That property disappears the moment any band or predicate change lands — which is exactly why this goes first.
- Reconcile the divergent tier defaults deliberately, not incidentally: pick one and state why. `"moderate"` is the documented default (`skills/build/SKILL.md:71`), so `spec_approve.py:126`'s `"simple"` is the outlier.
- `cortex_command/lifecycle/transition_table.py:385,409,465,482` carry the predicate as **advisory prose** inside `Guard(precondition=...)`; nothing parses it. Tests only diff the table against its generated doc, never against the code — so stale guard prose is invisible. Consider whether this refactor can close that gap.
- Unmocking `test_outcome_router.py`'s 38 patch sites wholesale is a much larger change than adding direct `requires_review` tests. Prefer the latter; leave the mocks.
- The criticality vocabulary is separately redeclared at eight sites (`refine.py:43,72`, `discovery.py:1000`, `lifecycle_event.py:255`, `pipeline/dispatch.py:203`, `transition_table.py:130`, `advance_lifecycle.py:111`; `common.CRITICALITY_VOCABULARY:836` is imported nowhere). Related but separable — do not fold it in without scoping it.

## Touch points

- `cortex_command/common.py:1068-1084` — the helper to consolidate behind
- `cortex_command/lifecycle/spec_approve.py:126,153` — copy + outlier default
- `cortex_command/lifecycle/implement_transition.py:99,175` — copy + default
- `cortex_command/lifecycle/next_verb.py:245` — copy
- `cortex_command/overnight/advance_lifecycle.py:254,256-263,265` — copy, default, and the unenforced comment
- `cortex_command/overnight/tests/test_outcome_router.py` — the 38 patch sites
- `cortex/lifecycle/criticality-pins-the-corpus-to-the/research.md` — where it was measured
