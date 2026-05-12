---
schema_version: "1"
uuid: 7dedb72c-5931-4792-a9ae-efcc4afbac17
title: "Auto-derive lifecycle slug from prose-style invocation args"
status: ready
priority: low
type: enhancement
created: 2026-05-12
updated: 2026-05-12
tags: [skills, lifecycle, clarify, dx]
complexity: simple
criticality: low
areas: [skills]
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

# Auto-derive lifecycle slug from prose-style invocation args

## Problem

`/cortex-core:lifecycle` (and by extension the clarify phase inside `/cortex-core:refine`) assumes the first argument is a kebab-case slug. When invoked with descriptive prose like `/cortex-core:lifecycle let's update CLAUDE.md to favor long-term solutions...`, the skill currently leads to a slug-confirmation `AskUserQuestion` round-trip. The user finds this gratuitous: the agent has enough signal in the prose to pick a slug.

## Value

Removes one full Q&A round-trip per lifecycle started from a prose description. Lifecycle invocations from `/cortex-core:dev` routing and from user-typed prose both benefit.

## Desired behavior

When the lifecycle arg is not a valid kebab-case slug, the skill should:

1. Auto-derive a 3–6 word positive-framed kebab-case slug from the prose.
2. Announce the chosen slug as it creates `cortex/lifecycle/{slug}/`.
3. Allow the user to correct it inline (e.g. by re-invoking with the corrected slug or replying "rename to X") rather than blocking on a multi-choice prompt up front.

## Out of scope

- Renaming existing lifecycle directories — only governs new-lifecycle slug derivation.
- Slug derivation for backlog items (covered by existing `slugify()`).
