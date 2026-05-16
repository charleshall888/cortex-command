---
schema_version: "1"
uuid: 3704a6a7-056c-4783-8fa2-b33c91a0026f
title: "Add docs/adr/ with 3 seed ADRs and emission rule"
status: complete
priority: high
type: feature
parent: 221
tags: [requirements, decisions, grill-me-with-docs-learnings]
created: 2026-05-15
updated: 2026-05-16
discovery_source: cortex/research/grill-me-with-docs-learnings/research.md
spec: cortex/lifecycle/add-docs-adr-with-3-seed/spec.md
areas: [lifecycle]
session_id: null
---

## Role

A sequentially-numbered architectural decision log under a new top-level docs directory. Each entry is one paragraph capturing what was decided and why, in one to three sentences per Pocock's stripped ADR format. Each ADR carries status frontmatter so deprecated and superseded decisions are visibly marked, and area frontmatter so the corresponding area requirements doc can list the ADRs relevant to it. The ADR log fills the why gap that the existing project requirements doc cannot carry under its 1200-token cap: the project doc keeps the rule terse and always-loaded; the ADR carries the paragraph-long rationale, loaded on-demand. Three seed ADRs ship with the directory so it is born content-bearing rather than as an empty gesture, synthesized from rationale that already exists in CLAUDE.md prose.

## Integration

A new directory sits at the repo top level alongside the existing skills, hooks, and cortex umbrella. A short policy doc inside the directory codifies the three-criteria emission gate (hard-to-reverse and surprising-without-context and result-of-real-trade-off), the status frontmatter convention, the area frontmatter convention, the no-content-duplication-across-layers discipline rule, and consumer-rule prose for skills that read the ADR log (analogous to Pocock's domain.md template — "use ADR vocabulary in narrative; if a candidate change contradicts an existing ADR, flag the conflict explicitly rather than silently overriding; grep the area frontmatter for area-scoped decisions when working in a specific subsystem"). Three seed ADRs are written from existing CLAUDE.md prose with no new analysis required. The spec-phase Open Decision Resolution gains a fourth resolution path: when a decision matches the three-criteria gate, propose an ADR alongside the spec.

## Edges

- ADR file naming contract: sequentially numbered with kebab-case slugs; the next available number is computed by scanning the existing ADR directory.
- ADR frontmatter contract: status enum (proposed, accepted, deprecated, superseded by ADR-NNNN) and area enum (project, pipeline, multi-agent, observability, remote-access, skills, plus new areas as added by future requirements docs).
- Three-criteria emission gate: a decision admitted to the log must satisfy all three criteria; any one missing means skip the ADR.
- No-duplication discipline rule: project requirements doc remains normative for the rule; the ADR is historical for the why; the glossary is terminological for what the words mean. Same sentence in two layers means one is wrong.
- Consumer-rule contract: skills that read ADRs do so via the policy doc's prose rule (use vocabulary, flag conflicts, grep area frontmatter for area-scoped decisions). No hand-maintained per-area indices in area requirements docs — discoverability relies on the consumer-rule prose plus area frontmatter, per Pocock's domain.md posture.
- Spec-phase emission rule contract: the Open Decision Resolution path that proposes an ADR must not bypass the existing user-approval flow; ADR proposal is a fourth resolution path peer to the existing three, not an automatic side-effect.

## Touch points

- docs/adr/README.md (new file — policy doc with three-criteria gate, frontmatter conventions, discipline rules)
- docs/adr/0001-file-based-state-no-database.md (new seed — synthesize from CLAUDE.md and cortex/requirements/project.md:27)
- docs/adr/0002-cli-wheel-plus-plugin-distribution.md (new seed — synthesize from CLAUDE.md Distribution section and cortex/requirements/project.md:7)
- docs/adr/0003-must-escalation-requires-effort-high-evidence.md (new seed — synthesize from CLAUDE.md MUST-escalation policy section)
- skills/lifecycle/references/specify.md §2b (Open Decision Resolution — add fourth resolution path for ADR proposal)
