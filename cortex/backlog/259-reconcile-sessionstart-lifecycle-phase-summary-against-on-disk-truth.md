---
schema_version: "1"
uuid: 69a8b0fc-c833-42ba-a317-a597c6bbd79b
title: "Reconcile SessionStart lifecycle-phase summary against on-disk truth"
status: complete
priority: medium
type: chore
created: 2026-05-20
updated: 2026-05-25
tags: [harness, hook, observability, lifecycle]
discovery_source: cortex/research/harness-friction-triage/research.md
session_id: a34c9d97-2dfe-4bcc-a1ff-17308805fe4f
lifecycle_phase: complete
lifecycle_slug: reconcile-sessionstart-lifecycle-phase-summary-against
complexity: complex
criticality: high
spec: cortex/lifecycle/reconcile-sessionstart-lifecycle-phase-summary-against/spec.md
areas: [hooks]
---
## Why

The SessionStart additionalContext summary that lists incomplete lifecycles and their phases diverges from on-disk truth. Concrete evidence from the harness-friction-triage discovery session:

- Summary advertised `extract-feature-executor-module-from-batch-runner (Review)`. On-disk truth: feature shipped 2026-04-14 via commit `864b4a54`; backlog ticket #075 has `status: complete`; the lifecycle dir was stale planning artifacts only (we cleaned it).
- Summary advertised `lead-refine-4-complexity-value-gate (Review)`. On-disk truth: backlog #209 had `status: in_progress` (lying); the last event was `feature_paused` on 2026-05-16 with branch staleness error; tasks 1-5 had all hit Bash-sandbox-EPERM and lost work. Actually at paused-Implement, not Review.

Both divergences came from the same summary generator. Both led to operator decisions (the user asked me to 'just complete the ones in Review phase') made on stale state. Without the divergence, the operator would have known #075 was already done and #209 needed implementation recovery — different work paths.

## Role

Make the SessionStart summary derive lifecycle phase from on-disk truth: read the most recent `phase_transition` event in `cortex/lifecycle/{feature}/events.log` and cross-check against `cortex/backlog/{NNN}-*.md` `status:` field. When the two disagree, prefer the events-log truth and surface the discrepancy (`{feature} (Review/lifecycle, in_progress/backlog, mismatch)`) rather than picking one silently.

## Integration

Lives in whatever code generates the SessionStart additionalContext block (likely a Python helper invoked from a SessionStart hook). Reads events.log + backlog frontmatter; emits the corrected lifecycle list.

## Edges

- Breaks if the events-log schema changes shape for phase transitions.
- Depends on backlog frontmatter `status:` being kept in sync with lifecycle phase (today it isn't always — see #209).
- The mismatch-surfacing behavior is the load-bearing feature; without it, the summary silently picks one source and the operator can't see the divergence.

## Touch points

- The SessionStart additionalContext generator (likely under `plugins/cortex-core/hooks/` or `cortex_command/`)
- `cortex/lifecycle/*/events.log` schema (phase_transition events)
- `cortex/backlog/*.md` frontmatter (`status:` field)
- Companion to ticket 258 (`worker_no_exit_report` is another silent-failure surface)