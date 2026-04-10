---
schema_version: "1"
uuid: 9598763c-dc24-4089-a182-073f83182d91
title: "Apply Anthropic migration rewrite table to skill prompts"
status: draft
priority: low
type: chore
created: 2026-04-10
updated: 2026-04-10
parent: "49"
tags: [output-efficiency,skills]
blocked-by: []
---

## Problem

The #052 audit removed verbose-by-default instructions from skill prompts, but the DR-6 stress-test gate on Opus 4.6 showed that instruction removal alone is not sufficient to control output volume. Skills still leak prose because the remaining instructions are written in a tone that invites elaboration rather than terse action.

The Anthropic `claude-opus-4-5-migration` plugin ships a rewrite table that maps weak/suggestive phrasings to stronger imperative forms (the imperative-intensity axis). Applying that table systematically to our skill prompts is an orthogonal improvement to the #052 verbose-instruction audit and is expected to tighten output without further content removal.

## Scope

Apply the Anthropic migration rewrite table to all 9 skills audited under #052:

- `skills/lifecycle`
- `skills/discovery`
- `skills/critical-review`
- `skills/research`
- `skills/pr-review`
- `skills/overnight`
- `skills/dev`
- `skills/backlog`
- `skills/diagnose`

The rewrite axis is imperative-intensity: convert hedged, descriptive, or suggestive phrasings into direct imperatives per the migration table's guidance.

## Notes

- This ticket is orthogonal to #050 output floor compliance and to #052 verbose-instruction removal. It targets a different failure mode (tone / imperative strength) on the same surface area.
- The `dev` skill's DV1/DV2 sections are bonus candidates for consideration during this ticket's refine phase — they were not in scope for #052 but may benefit from the same rewrite pass.
- Verification strategy to be resolved during refine: the DR-6 stress-test harness from #052 is one candidate, but a lighter-weight diff-based or review-based check may be appropriate given the edit is prompt-tone-only. Decide during refine.

## Acceptance (draft — to firm up in refine)

- All 9 skill prompts edited per the Anthropic migration rewrite table imperative-intensity guidance.
- Verification approach chosen and executed during refine/implement.
- No regressions in skill behavior on representative inputs.
