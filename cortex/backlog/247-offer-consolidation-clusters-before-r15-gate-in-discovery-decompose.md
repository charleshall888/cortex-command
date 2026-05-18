---
schema_version: "1"
uuid: fafa9ddc-f2b3-4a7f-9401-c92932e2d367
title: "Offer consolidation clusters before R15 gate in discovery decompose"
status: backlog
priority: low
type: feature
created: 2026-05-18
updated: 2026-05-18
tags: [discovery, skills, decompose]
areas: [skills, discovery]
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

## Context

When the discovery skill's decompose phase produces N tickets (one per Architecture piece) and presents the R15 batch-review gate, the user sometimes notices natural consolidation opportunities and asks "can we combine some of these?" — at which point the agent backtracks, identifies clusters, and presents a separate consolidation question before re-presenting the gate.

Observed in the `swap-daytime-autonomous-for-worktree-interactive` discovery (2026-05-18): authored 10 tickets, user asked to consolidate, agent identified three plausible merge clusters (same-shape concurrency guards, create+cleanup pairs, interaction-model + dependent hook), user picked all three, final count was 6 tickets. Two round trips at the R15 gate when one would have sufficed.

## Proposed change

In `skills/discovery/references/decompose.md`, add a pre-R15 step between §4 (Determine Grouping) and §5 (Create Backlog Tickets), OR between §5's ticket authoring and §5's R15 gate, that:

1. Scans the authored ticket bodies for natural consolidation clusters using lightweight heuristics:
   - **Same-shape clusters**: multiple tickets whose Role paragraphs share a common verb-frame (e.g., three "Add ... guard ..." tickets)
   - **Lifecycle pairs**: a create/initialize ticket and its corresponding cleanup/teardown ticket
   - **End-to-end pairs**: an interaction-shape ticket and its dependent hook ticket
2. Presents detected clusters via `AskUserQuestion` with `multiSelect: true` BEFORE the R15 gate, with options describing each cluster and its trade-off (one-PR-shape vs. dependency-boundary cleanliness)
3. Applies user-selected merges, then proceeds to the R15 gate with the consolidated set

If no clusters are detected, skip the consolidation-offer step silently and go straight to R15.

## Acceptance

- A discovery topic that produces 6+ tickets fires the consolidation-offer step before R15
- Each detected cluster surfaces with a clear trade-off in the option description
- User-selected merges happen before R15 — the gate sees only the consolidated set
- A discovery topic with no natural clusters skips the offer step (no false-positive questions)
- The LEX-1 scanner still passes on merged ticket bodies

## Out of scope

- Auto-merging without user confirmation
- Defining a comprehensive cluster taxonomy beyond the three named heuristics
- Retroactive consolidation of already-committed tickets
