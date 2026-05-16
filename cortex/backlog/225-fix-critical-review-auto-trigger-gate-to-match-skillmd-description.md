---
schema_version: "1"
uuid: b021eb2c-0354-4594-ad2e-e806762eb47b
title: "Fix critical-review auto-trigger gate to match SKILL.md description"
status: complete
priority: medium
type: bug
tags: [critical-review, lifecycle, skills]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/lifecycle/archive/reduce-critical-review-influence/research.md
---

## Problem

`skills/critical-review/SKILL.md:3` advertises that critical-review "auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval." The actual auto-trigger gates at `skills/lifecycle/references/specify.md:149` and `skills/lifecycle/references/plan.md:271` check `tier = complex` only — `criticality` is not consulted. Complex features with `criticality=low` therefore trigger critical-review unintentionally, against the documented contract.

This is a likely contributor to the perception that critical-review runs more aggressively than intended. Surfaced during research for the archived `reduce-critical-review-influence` lifecycle, which terminated without shipping because the rest of the proposed weighting tuning carried more risk than benefit (current rubric is already the prior "orchestrator pushback" lifecycle's output; further rubric expansion would double down on a path the user judged residual).

## Fix

Two-file edit in `skills/lifecycle/references/`:

- `specify.md:145–151` (§3b Critical Review)
- `plan.md:267–273` (§3b Critical Review)

Both gates currently read tier via `cortex-lifecycle-state --feature {feature} --field tier`. Extend each to also read `criticality` and gate on `tier == "complex" AND criticality IN ("medium", "high", "critical")`, matching the SKILL.md description.

When the gate skips because criticality is `low`, append a `lifecycle_critical_review_skipped` event to the lifecycle's events.log so the skip rate is observable. Register the new event in `bin/.events-registry.md` (`manual` scope; consumer: future per-tier compliance audit, mirroring the existing `sentinel_absence` / `synthesizer_drift` entries).

## Acceptance

- A complex feature with `criticality=low` does not auto-trigger critical-review at specify §3b or plan §3b.
- A complex feature with `criticality ∈ {medium, high, critical}` continues to trigger critical-review at both phases as today.
- The `lifecycle_critical_review_skipped` event row exists in `bin/.events-registry.md` and is emitted on the low-criticality skip path.
- `SKILL.md:3` frontmatter wording and the actual gate logic agree.

## Notes

- Higher-leverage broader weighting work (rubric expansion, voice anchor softening, Apply-bar tightening) is intentionally NOT bundled here. Revisit after ≥1 week of skip-rate data shows whether this gate fix moves the "critical-review listens too much" perception meaningfully; the archived research artifact carries the full alternatives analysis and adversarial counterpoints for that future decision.
- Do NOT soften the load-bearing voice anchors at `SKILL.md:97` (`Do not soften or editorialize`) or `synthesizer-prompt.md:50` (`Do not be balanced. Do not reassure.`) as part of this work — those were preserved deliberately against Opus 4.7 warmth regression per backlog #082 / #085.
