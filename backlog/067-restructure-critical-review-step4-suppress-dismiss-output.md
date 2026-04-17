---
id: 67
title: "Restructure critical-review Step 4 to suppress Dismiss output"
type: feature
status: refined
priority: high
parent: 66
tags: [output-signal-noise, critical-review]
discovery_source: research/audit-interactive-phase-output-for-decision-signal/research.md
created: 2026-04-11
updated: 2026-04-17
session_id: 09713255-a17d-40cf-95b4-95d204e63d0c
lifecycle_phase: implement
lifecycle_slug: restructure-critical-review-step-4-to-suppress-dismiss-output
complexity: complex
criticality: high
spec: lifecycle/restructure-critical-review-step-4-to-suppress-dismiss-output/spec.md
areas: [skills]
---

Step 4 of `/critical-review` requires "what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items." The Dismiss requirement is the surface area that causes verbose disposition walkthroughs. The existing "compact summary" instruction already fails in practice — agents walk through every objection with reasoning and re-state the objection before giving the disposition.

The underlying structural issue: Apply items changed the artifact (done, no user action needed); Dismiss items are resolved internally; only Ask items require user attention. The current design surfaces all three classes, which is why format-tightening has not worked.

The fix removes the requirement to report Dismiss items entirely, and restricts Apply reporting to a bullet list of what changed — not the objections that triggered each change. Ask items remain as the only user-directed output when present.

This change applies to Step 4's compact summary in `critical-review/SKILL.md`. It automatically carries through to lifecycle specify §3b, which invokes `/critical-review` at spec approval time.

## Context from discovery

DR-2 in the research establishes the "eliminate Dismiss requirement" framing. DR-4 establishes the mechanism distinction: for in-context orchestrator work, removing the output *requirement* is more reliable than asking the agent to be briefer.
