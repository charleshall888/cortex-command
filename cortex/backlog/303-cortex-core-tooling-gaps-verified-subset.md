---
schema_version: "1"
uuid: cda99005-e1bb-4c34-8d34-9c6c7f84f1b3
title: cortex-core tooling gaps (verified subset)
status: complete
priority: medium
type: epic
created: 2026-06-14
updated: 2026-06-15
tags: ['cortex-core-tooling-gaps']
discovery_source: cortex/research/cortex-core-tooling-gaps/research.md
---
## Summary

Umbrella for the verified, hard-filtered subset of the cortex-core tooling-gaps discovery. The discovery verified ten candidate tooling gaps against current source; all ten were confirmed absent, but a value triage narrowed the filed set to the three with real, current friction evidence and low build cost. See the research artifact for the full verification, decision records, and the rationale behind each cut.

## Filed children

- Report-only ADR citation auditor — confirms every ADR reference resolves to a real decision record (a consumer repo accumulated dozens of dangling ADR references plus a duplicate number). Folds in deleting the README's never-honored area-backfill defer-note.
- Hyperlink the spec column in the generated backlog index — a one-render fix to make the existing spec path clickable.
- Cross-lifecycle phase index wired to morning-review — a generated, queryable view of every lifecycle and its phase, reusing the existing phase-inference reducer.

These three are independent (no shared seam); the epic groups them only by discovery provenance.

## Not filed (this discovery)

Seven candidates were dropped or deferred at the gate, recorded with rationale in the decomposition trail: ADR area-backfill (folded into the auditor as a README correction), requirements file-to-section index (generalize-from-one-consumer), consumer always-loaded ratchet (deferred, maintainer-confirm ownership), opt-in lifecycle archive (the index solves the navigation pain without moving anything), research-doc status convention + stale-status detector (scaffolding for a deferred, semantically hard feature), and overnight per-run exclude (deferred — friction evidence weakened on verification).
