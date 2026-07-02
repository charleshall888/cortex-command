---
schema_version: "1"
uuid: a37d35f0-a59f-4c0b-b1b0-8ea3c337ac91
title: Compress project.md sections that restate ADRs, CLAUDE.md, and tests
status: complete
priority: medium
type: chore
tags: ['skill-value-scorecard']
areas: ['docs']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
lifecycle_phase: research
lifecycle_slug: compress-projectmd-sections-that-restate-adrs
complexity: complex
criticality: high
spec: cortex/lifecycle/compress-projectmd-sections-that-restate-adrs/spec.md
---
## Why
cortex/requirements/project.md loads into lifecycle, refine, and discovery context on the load-requirements path, and the audit verified eight of its sections as compressible (s4, s6, s7, s8, s9, s10, s11, s15 — seven at high confidence, s6 at medium): they restate, sometimes clause-for-clause, content that already lives in always-loaded CLAUDE.md, in ADR bodies (which the ADR README explicitly forbids project.md from restating), in test docstrings, or in enforcement-site documentation.

## Role
Compress the eight verified sections per their keep-lists in master_candidates.json. Each verdict names exactly which clauses have no other home and must survive: the cluster-exemption and re-cap rules of the L1 ratchet, the retention policy and FORCE_SOURCE escape hatch whose main prose home is here (otherwise surfacing only in bin wrapper header comments), the same-repo-overnight-not-exempt containment clause, the merge-terminal and pause-taxonomy conventions, the deliberately-incomplete redaction design rationale. Also fix the stale pointer at line 27 — the kept-pauses inventory moved to references/kept-pauses.md.

## Integration
This is the user-authored project constitution, so the compression is an editorial pass the user reviews at spec or PR time — the audit established what is duplicated, not what the user wants to keep saying in their own voice.

## Edges
- CLAUDE.md points into this file by name for specific rules; keep those headings and the named rules verbatim.
- The contract lint scans this file — keep passing token forms.
- The requirements-write schema pins H2 structure, convention line, and bold-led bullets.

## Touch points
- cortex/requirements/project.md
- cortex/research/skill-value-scorecard/master_candidates.json (verdict source, per-section keep-lists)