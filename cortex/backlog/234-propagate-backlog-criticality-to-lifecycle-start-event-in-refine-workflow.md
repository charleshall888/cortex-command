---
schema_version: "1"
uuid: 57aa1034-b590-4f84-ba13-ab37f95dbd8f
title: "Propagate backlog criticality to lifecycle_start event in refine workflow"
status: backlog
priority: medium
type: bug
created: 2026-05-17
updated: 2026-05-17
tags: [lifecycle, refine, criticality]
---

# Propagate backlog criticality to lifecycle_start event in refine workflow

## Problem

When a lifecycle originates from a backlog item with a non-default `criticality` field (e.g. `high`, `critical`), the value does not currently propagate into the lifecycle's `events.log` via a `lifecycle_start` event. The canonical state source `cortex-lifecycle-state --feature {feature} --field criticality` reads from `events.log` and returns the default `medium` when no event sets it, so the implement → next-phase gating matrix routes on the wrong value.

## Concrete observation

Feature `discovery-output-density-investigate-author-centric` (backlog #227):

- Backlog frontmatter: `criticality: high`
- `events.log` after refine→plan→implement→complete: contains `clarify_critic`, `spec_approved`, `batch_dispatch` events but **no `lifecycle_start` event**
- `cortex-lifecycle-state --feature {feature} --field criticality` returns `{}` → defaults to medium
- Implement→next-phase matrix with medium+simple routes to Complete; with high+simple it would force Review
- The feature auto-routed to Complete; the formal Review pass was silently skipped

## Why this matters

The criticality gating matrix exists to enforce reviewer-pass requirements on high-stakes work. Silent demotion to the default tier defeats the gate. Any future feature with backlog `criticality: high` that flows through the same refine path will hit the same demotion.

## Where the fix lives

`/cortex-core:refine` (or whichever skill emits `lifecycle_start`) should:

1. Read the originating backlog item's `criticality` frontmatter field.
2. Emit `lifecycle_start` with `"criticality": "<value-from-backlog>"` (or apply default `medium` explicitly when absent).
3. Emit BEFORE the `clarify_critic` event so the canonical state read is correct at every downstream phase boundary.

Currently `/cortex-core:lifecycle`'s SKILL.md §3 step 4 mentions logging `lifecycle_start` "After the full Clarify phase completes" with criticality from "the post-critic, post-Q&A values in context" — this implies criticality is set during clarify, but the values in context come from where? If from backlog frontmatter, the propagation gap is in the read path (clarify isn't reading the field) rather than the emit path.

## Acceptance

- A test that creates a backlog item with `criticality: high`, runs refine through a programmatic path, and asserts the resulting `events.log` contains a `lifecycle_start` event with `criticality: high`.
- Retrofit: a small helper that detects this discrepancy on already-running lifecycles (compares backlog frontmatter `criticality` against the value `cortex-lifecycle-state` returns) and surfaces a warning. Optional.

## Discovered during

`/cortex-core:lifecycle 227` (2026-05-17) — feature `discovery-output-density-investigate-author-centric` auto-routed to Complete when the backlog said high. Surfaced in the close-out summary.
