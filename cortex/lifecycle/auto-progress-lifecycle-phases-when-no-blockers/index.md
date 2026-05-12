---
feature: auto-progress-lifecycle-phases-when-no-blockers
title: Auto-progress lifecycle phases when no blockers
backlog_item: null
status: in_progress
tier: complex
criticality: high
created: 2026-05-11
updated: 2026-05-11
artifacts: [research, spec, plan, review]
---

# Auto-progress lifecycle phases when no blockers

Audit `skills/lifecycle/` and `skills/refine/` and remove ceremonial "proceed to next phase?" pauses at phase boundaries — preserving substantive decision surfaces (open decisions in spec, complexity/value gate, REJECTED reviewer verdicts, unresolved clarify-critic Asks).

## Scope

- Lifecycle: Plan → Implement → Review → Complete transitions
- Refine: Clarify → Research → Specify transitions
- Verdict routing: APPROVED auto-progresses to Complete; CHANGES_REQUESTED auto-loops to Implement; REJECTED pauses for user direction
