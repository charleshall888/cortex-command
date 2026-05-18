---
feature: propagate-backlog-criticality-to-lifecycle-start
backlog: 234-propagate-backlog-criticality-to-lifecycle-start-event-in-refine-workflow
title: "Propagate backlog criticality to lifecycle_start event in refine workflow"
created: 2026-05-18
updated: 2026-05-18
tags: [lifecycle, refine, criticality]
artifacts: ["research", "spec", "plan", "review"]
---

# propagate-backlog-criticality-to-lifecycle-start

Refine lifecycle directory for backlog item 234.

## Clarify outputs (2026-05-18)

- **Clarified intent**: When `/cortex-core:refine` runs from a backlog item, emit a `lifecycle_start` event into `cortex/lifecycle/{feature}/events.log` as the first event in the log (before `clarify_critic`), with `criticality` populated from the backlog item's `criticality` frontmatter field (default `medium` if absent), so the canonical state read returns the user-curated value at every downstream phase gate.
- **Complexity**: complex
- **Criticality**: high
- **Requirements alignment**: Aligned with `cortex/requirements/project.md` philosophy (gating-matrix integrity, no conflict). No `Conditional Loading` area docs matched tags `[lifecycle, refine, criticality]`. `cortex/requirements/glossary.md` (skipped: file absent).
- **Design decisions resolved during Clarify**:
  - Emit site: `/cortex-core:refine` clarify orchestrator (not lifecycle SKILL.md). Refine already owns `clarify_critic` emission; same module pairs both events reliably.
  - Criticality source: backlog frontmatter `criticality` field, read at refine entry.
  - Timing: `lifecycle_start` is the first event in `events.log`, written before `clarify_critic`.
  - Clarify §5 / §7 are NOT modified — clarify continues to rederive and write back independently.
  - Retrofit helper (Optional in ticket): out of scope for this lifecycle. File as follow-up if needed.
