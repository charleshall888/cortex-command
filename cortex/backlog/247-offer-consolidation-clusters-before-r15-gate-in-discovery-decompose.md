---
schema_version: "1"
uuid: fafa9ddc-f2b3-4a7f-9401-c92932e2d367
title: "Offer consolidation clusters before R15 gate in discovery decompose"
status: complete
priority: low
type: feature
created: 2026-05-18
updated: 2026-05-26
tags: [discovery, skills, decompose]
areas: [skills,discovery]
session_id: a9ac483c-9938-4cd8-97ff-10007f5d9962
lifecycle_phase: research
lifecycle_slug: offer-consolidation-clusters-before-r15-gate
complexity: complex
criticality: high
spec: cortex/lifecycle/offer-consolidation-clusters-before-r15-gate/spec.md
---

## Problem

The discovery decompose skill produces one ticket per Architecture piece and presents the full set at the R15 batch-review gate. When the resulting set has tickets that would naturally ship as one PR (e.g., several small same-shape pieces, or a primitive paired with its consumer), the user has to notice the over-decomposition and ask "can we combine some of these?" — which kicks off a separate round of identification, an out-of-band consolidation question, and a re-presentation of R15. Two round trips at the gate where one would have done.

Observed in the `swap-daytime-autonomous-for-worktree-interactive` discovery (2026-05-18): authored 10 tickets, user asked to consolidate, agent surfaced merge clusters reactively, final count was 6 tickets.

## Why it matters

The R15 gate exists to give the user a pre-commit affordance — a place to redirect or reshape. When the agent presents an obvious-in-retrospect over-decomposition, the user spends that affordance on consolidation cleanup instead of substantive review. The skill should be the proactive party here: detect the consolidation question is likely, raise it explicitly before R15, and let the user answer it once.

## Desired behavior

After authoring the ticket bodies but before invoking R15, the skill considers whether any subsets of the tickets are likely candidates for the user to want merged. If so, surface that question to the user — describe the candidate merges and the trade-off (one-PR-shape vs. dependency-boundary cleanliness), let the user pick which (if any) to apply, then proceed to R15 with the consolidated set. If no candidates surface, skip the pre-step silently — the gate is the right place to land.

The specific signals worth treating as candidates are left to the plan phase, since the right detection shape probably won't be a fixed taxonomy — it's more like "tickets whose Roles describe the same verb-frame applied to parallel objects" or "tickets where one's Touch points are a strict subset of another's." Whatever the implementation, the principle is: the agent should generalize from "these N tickets look like they'd ship together," not match a closed enumeration of cluster types.

## Acceptance

- A discovery producing 6+ tickets fires the pre-R15 consolidation-offer step when natural merge candidates exist.
- The offer surfaces candidate merges with their trade-offs visible to the user.
- User-selected merges happen before R15 — the gate sees the consolidated set.
- A discovery with no candidate merges skips the pre-step (no false-positive questions).
- The LEX-1 scanner still passes on merged ticket bodies.

## Out of scope

- Auto-merging without user confirmation.
- Retroactive consolidation of already-committed tickets.
