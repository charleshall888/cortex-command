---
schema_version: "1"
uuid: 16d4061e-a90c-480e-947b-d08458d40e1a
title: "Adopt xhigh effort default for overnight lifecycle implement"
status: complete
priority: low
type: feature
created: 2026-04-18
updated: 2026-05-04
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: []
complexity: complex
criticality: high
spec: lifecycle/adopt-xhigh-effort-default-for-overnight-lifecycle-implement/spec.md
areas: [overnight-runner]
session_id: null
lifecycle_phase: implement
---

# Adopt xhigh effort default for overnight lifecycle implement

## Motivation

Wave 2 capability adoption from DR-3. Per Anthropic's migration guide, `xhigh` is "the best setting for most coding and agentic use cases." Decision is now driven by Anthropic docs + community research rather than on-our-stack measurement — see Research context below for why.

## Research context

From `research/opus-4-7-harness-adaptation/research.md` DR-3 Wave 2 and Open Question 2, plus the ticket-specific research at `lifecycle/archive/measure-xhigh-vs-high-effort-cost-delta-on-representative-task/research.md`. #089 was closed as wontfix on 2026-04-20: n=1 + a single synthetic task could not carry the decision weight; community research (third-party estimate of ~1.5× tokens, 5–6% quality boost on agentic coding) is consistent with ship. The #089 research artifact also verified:

- SDK wiring for `effort` is already complete — `ClaudeAgentOptions(effort="xhigh")` works end-to-end at runtime (the Python Literal missing `"xhigh"` is a type-checker warning only; `@dataclass` doesn't enforce it).
- `max_tokens` is **NOT wireable** through the harness — `ClaudeAgentOptions` has no such field and CLI v2.1.x has no `--max-tokens` flag. The correct mitigation for xhigh output-size risk is `stop_reason == "max_tokens"` monitoring in the dispatch path, not a config knob.
- Docstring at `cortex_command/pipeline/dispatch.py:371` lists valid effort values without `"xhigh"` — must be updated in the same commit as the adoption flip so the function contract matches the shipped behavior.

## Deliverable

- Configure `xhigh` effort as the default for overnight lifecycle implement-phase dispatches.
- Update the `dispatch_task` docstring at `cortex_command/pipeline/dispatch.py:371` to include `"xhigh"` in the documented list of valid `effort_override` values.
- Add detection for `stop_reason == "max_tokens"` in the dispatch event logging (not currently captured) so that silent truncations under xhigh surface in overnight reports rather than being masked.
- Document the choice rationale in the commit and in `docs/overnight-operations.md` (cite Anthropic migration guide + community estimates + the #089 closure rationale).
- Monitor the next 2–3 overnight rounds for regressions via the existing `cortex_command/pipeline/metrics.py` aggregator; roll back if cost or quality anomalies appear.

## Flip scope — decide before implementing

The implement phase can set `xhigh` in three ways; pick one explicitly:

1. **Global flip of `EFFORT_MAP`** (`cortex_command/pipeline/dispatch.py:126–130`): `"complex"` → `"xhigh"`. Simplest but affects every complex dispatch, not just lifecycle implement.
2. **Criticality-aware 2D effort matrix** analogous to `_MODEL_MATRIX`: xhigh only at (complex, high/critical); keep high at (complex, low/medium). More nuanced, adds a config surface.
3. **Per-phase override** threaded through the overnight runner: implement phase uses `effort_override="xhigh"` explicitly; other phases inherit EFFORT_MAP. Closest match to the ticket's stated scope ("overnight lifecycle implement phase").

DR-3 Wave 2's framing ("lifecycle implement phase") argues against option (1). Option (3) is the narrowest honest implementation of that framing but requires adding `effort_override` to `retry_task()`'s signature (it currently lacks it). Option (2) is a reasonable middle.

## Dependencies

- Originally blocked by #092 (scaffolding removal must complete so effort-level change isn't compounded). **Cleared 2026-04-29**: #092 was closed wontfix — DR-3 Wave 1 will not ship. With no scaffolding-removal change in flight, the "don't compound" ordering rationale no longer applies, and #090 ships on its own terms. The rollback trigger below continues to reference a local pre-flip baseline captured at flip time.

## Scope bounds

- Applies only to lifecycle implement phase, not every dispatch — per DR-3's scoping.
- Rollback trigger (post-ship): if the `metrics.py` aggregator shows complex-tier mean cost per dispatch jumping > 2× vs the last pre-flip baseline over 2–3 overnight rounds, revert. Community estimate (~1.5×) is the expected ceiling; > 2× signals a local anomaly worth investigating before continuing.
