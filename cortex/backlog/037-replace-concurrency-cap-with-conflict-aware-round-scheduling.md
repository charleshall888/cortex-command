---
schema_version: "1"
uuid: a22cc91a-dffd-4dc9-b46e-79232d085226
title: "Replace concurrency cap with conflict-aware round scheduling"
status: complete
priority: medium
type: chore
tags: [overnight, scheduling]
areas: [overnight-runner]
blocked-by: []
created: 2026-04-06
updated: 2026-04-07
session_id: null
lifecycle_phase: implement
lifecycle_slug: replace-concurrency-cap-with-conflict-aware-round-scheduling
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/replace-concurrency-cap-with-conflict-aware-round-scheduling/spec.md
---

The overnight runner uses a static concurrency cap (default 2) to limit parallel feature execution per round. This is a blunt instrument — it doesn't consider whether features actually conflict. Two features touching completely different files could safely run in parallel, while two features editing the same template should be serialized regardless of the cap.

The batch grouping already does area-separation (items sharing an area go to different rounds), but this is coarse-grained. Investigate whether file-level overlap analysis (from specs, plan.md touched-files lists, or static analysis of the lifecycle directory) can replace the concurrency cap entirely with smarter round assignment that maximizes parallelism while preventing merge conflicts.
