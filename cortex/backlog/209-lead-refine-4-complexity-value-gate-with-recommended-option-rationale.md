---
schema_version: "1"
uuid: b0545923-2dac-42f3-977e-6b6307a816f7
title: "Lead refine §4 complexity-value gate with recommended option + rationale"
status: refined
priority: medium
type: chore
tags: [skills, refine, lifecycle, ux]
created: 2026-05-12
updated: 2026-05-12
complexity: simple
criticality: high
spec: cortex/lifecycle/lead-refine-4-complexity-value-gate/spec.md
areas: [skills]
---

# Lead refine §4 complexity-value gate with recommended option + rationale

## Context

The `/cortex-core:refine` skill's §4 complexity-value gate (defined in `skills/refine/SKILL.md`) currently fires when a spec introduces 3+ new state surfaces, a new persistent format, or ongoing per-feature upkeep. When it fires, it presents the value case + complexity cost + 2-3 concrete alternatives as a neutral menu and waits for the user to pick.

User feedback (2026-05-12 during refine of backlog #208): "I almost always just default to full scope." Presenting the alternatives as a neutral menu wastes the user's time and signals agent uncertainty when the analysis usually supports full scope.

## Proposed change

Amend `skills/refine/SKILL.md` §4 (the "Complexity/value gate" adaptation under Step 5) to:

1. Require the recommendation: when the gate fires, the orchestrator MUST decide which of the alternatives is the recommended option for *this specific feature* and state it explicitly with a one-sentence rationale before listing the alternatives.
2. Format the AskUserQuestion: the recommended option appears first with a `(Recommended)` suffix on the label; the question body opens with the recommendation and rationale, then lists "Confirm" + downsize options.
3. Soft-form phrasing: "I recommend X because Y. Confirm or downsize?" rather than "Which scope do you want?"

## Acceptance

- `skills/refine/SKILL.md` §4 prose specifies the recommendation-first format with a worked example.
- `tests/test_refine_skill.py` (or equivalent existing test surface) asserts the §4 prose contains the "(Recommended)" suffix expectation and the rationale-first ordering.
- The cortex-core plugin mirror at `plugins/cortex-core/skills/refine/SKILL.md` regenerates via pre-commit.

## Out of scope

- Touching the orchestrator-review §4 surface (different skill, different gate).
- Touching the lifecycle's "drop / minimum viable / hardened" presentation in `/cortex-core:lifecycle` (covered by analogous pattern but a separate change set if user wants it propagated).
- Auto-skipping the gate when the recommendation is obviously full scope — keeping the explicit recommendation is the point; the user wants to see the rationale even when they accept.

## References

- `skills/refine/SKILL.md` §4 complexity-value gate adaptation under Step 5
- Memory: `feedback_scope_recommendations.md`, `user_defaults_full_scope.md`
- Triggering session: refine of backlog #208 on 2026-05-12
