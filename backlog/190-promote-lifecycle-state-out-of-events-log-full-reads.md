---
schema_version: "1"
uuid: 72260d5f-c01b-4600-8b84-0b3b5f4f3a15
title: "Promote lifecycle state out of events.log full-reads"
type: feature
status: complete
priority: high
parent: 187
blocked-by: []
tags: [lifecycle, state-storage, events-log, data-model]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
spec: lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/spec.md
areas: [skills]
lifecycle_phase: implement
plan: lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/plan.md
session_id: null
---

# Promote lifecycle state out of events.log full-reads

## Problem

Lifecycle state — `criticality`, `tier`, `tasks_total`, `tasks_checked`, `rework_cycles` — is currently extracted at read-time from append-only files (`events.log`, `plan.md`, `review.md`) via full-file reads:

- `cortex_command/common.py:197` (`detect_lifecycle_phase`), `:303` (`read_criticality`), `:344` (`read_tier`) — each does `read_text().splitlines()` against the full events.log to find the most-recent matching line.
- 5+ phase-reference files (`skills/lifecycle/references/{plan,specify,orchestrator-review,implement,review}.md`, plus `refine/SKILL.md`, `dev/SKILL.md`) each instruct Claude to "read events.log for the most recent lifecycle_start/criticality_override/criticality_override event" — meaning every lifecycle entry full-reads events.log inline.
- `skills/lifecycle/references/complete.md:25-26` reads full `plan.md` + `review.md` to extract two integers (`tasks_total`, `rework_cycles`).

This is wrong-layer storage: write-once-or-rarely state, read many times, currently buried in append-only logs and prose artifacts.

## Why it matters

- Per-call cost grows linearly with events.log size and is paid by every consumer in every lifecycle phase.
- Adding bin helpers (the audit's initial proposal) caches the wrong-layer choice without fixing it.
- The current model splits canonical state across multiple files (events.log for criticality/tier; plan.md for task count; review.md for rework cycles); each consumer must re-derive. State and audit-trail are conflated.

## Constraints

- **Multi-writer safety**: concurrent overnight runs can race against the same lifecycle's state writes. Whatever mechanism lands must handle this without locking.
- **File-based state convention** (per `requirements/project.md:27`): no databases, no servers. Markdown for narrative; JSON for structured state is the existing pattern (see `overnight-state.json`, `preconditions.json`, `critical-review-residue.json`).
- **Migration must be incremental**: in-flight lifecycles at merge time must continue to read correctly. A fall-through to today's events.log scan is the safest pattern.
- **Schema versioning**: any new state file must carry an explicit `schema_version` from day one.
- **Human-skimmability** of `events.log` must be preserved — phase transitions and other auditable events should remain greppable. The state promotion must not destroy the historical record.
- **`phase` should probably stay derived** (it's cheap: `Path.is_file()` + small regex over `plan.md`/`review.md`), not promoted. Confirm during research.

## Out of scope

- Replacing events.log entirely (separate concern; see #189).
- Changing the live-event consumers' parsing logic.
- Migrating archived lifecycles to the new state shape.
- Promoting derived values (e.g., `phase`) that aren't actually logged.

## Acceptance signal

- Lifecycle state lookups no longer require full-reading `events.log`.
- `complete.md`'s plan+review full-reads for two integers are gone (or justified by a clear reason to keep).
- A new lifecycle started after this lands writes its state via the new mechanism at the right phase boundaries.
- An existing in-flight lifecycle (no new-state-file present) continues to read correctly via fallback.
- Concurrent writers don't corrupt the state under stress (test required).
- Schema version is present and validated.

## Research hooks

The audit's initial proposal was to promote state to `lifecycle/<feature>/index.md` YAML frontmatter; alternative-exploration challenged this on grounds that index.md is a passive wikilink hub, YAML-RMW races under concurrent writers, and the project's existing pattern for structured state is JSON files (`overnight-state.json` etc.).

Research-phase questions:

- Where should state live? Candidate options surfaced during analysis: `lifecycle/<feature>/state.json` (mirrors existing JSON pattern); `lifecycle/<feature>/index.md` frontmatter (mutates a currently-static file); a centralized state index keyed by feature slug; or a thin reader wrapper that keeps the storage in events.log but caches the lookup. Each has tradeoffs across simplicity, blast radius, migration, multi-writer safety, observability — research should evaluate.
- Which fields get promoted? Audit listed `criticality`, `tier`, `tasks_total`, `rework_cycles`. Is `phase` in or out? Are there others (e.g., `complexity_override`, `criticality_override` reasons) that belong here too?
- What's the right reader surface? A bin helper (`cortex-lifecycle-state`)? Direct file reads at every callsite? A Python helper imported by `common.py`?
- How are writes coordinated across the multiple emit sites (`runner.py`, `outcome_router.py`, `feature_executor.py`, plus skill-prompt instructions)?
- How does the chosen mechanism interact with #189's events.log cleanup? Sequencing requires #189 to settle the events.log emission shape first so this ticket designs against a stable baseline.

The audit's DR-1 area and the alternative-exploration outputs commit to specific recommendations; treat those as inputs to your own evaluation.
