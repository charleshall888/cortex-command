---
schema_version: "1"
uuid: 4badee5f-3e18-401e-ae82-e1f1d69d6cd9
title: "Add project glossary at cortex/requirements/glossary.md"
status: complete
priority: high
type: feature
parent: 221
tags: [requirements, vocabulary, grill-me-with-docs-learnings]
created: 2026-05-15
updated: 2026-05-16
discovery_source: cortex/research/grill-me-with-docs-learnings/research.md
spec: cortex/lifecycle/add-project-glossary-at-cortex-requirements/spec.md
areas: [skills]
lifecycle_phase: plan
session_id: null
---

## Role

A canonical-terms file at the requirements layer. Each entry is a project-specific term with a one-sentence definition that says what the term IS rather than what it does, plus aliases-to-avoid where there is real drift risk. The glossary is small, opinionated, and consulted at session start so subagents and humans stop re-learning the same vocabulary every time they cold-load. Per Pocock's CONTEXT-FORMAT discipline rules, an entry only earns its place if it survives a tight-definition test; terms that cannot be defined in one sentence without paragraphs of context are author-scaffolding and get cut from the source skill rather than catalogued. Following Pocock's producer-consumer separation, the file has one write rule (inline at the cadence-uplifted interview when a term resolves) and many readers (every skill that loads requirements via the tag-based protocol).

## Integration

A new file sits alongside the existing project requirements doc and area docs at the requirements layer. It is loaded conditionally via the existing tag-based loading protocol in load-requirements.md, extended with an always-load sentinel or a global-context tag so the glossary is consulted at session start regardless of which area tags fire. It is read by every skill that already loads requirements via the tag protocol, and by the critical-review reviewer-prompt context block. It is written inline at both producer surfaces (the cadence-uplifted requirements interview and the cadence-uplifted spec interview) when a term resolves; the file is created lazily on the first term resolved and does not exist before that. Consumer skills that read the glossary carry a one-line prose rule analogous to Pocock's domain.md template: use the glossary's vocabulary; if a concept you need is not yet defined, treat the absence as a signal to surface the term in the next requirements or spec interview.

## Edges

- Glossary loading contract in load-requirements.md must be extended without breaking the existing tag-based selection logic for area docs.
- Reviewer-prompt context block in critical-review must read the glossary as a project-context input on the same path it currently reads the project requirements overview.
- Per-entry discipline gate: each candidate term passes through a four-bucket classifier (contract, compressing reference, author scaffolding, genuine domain term) before admission. Author-scaffolding terms get cut from their source skill instead of admitted.
- Producer-consumer separation contract: only the cadence-uplifted interview surfaces write; all other skills read. No deferred-write Q&A item path; no separate /requirements-write commit step for glossary entries; no pre-commit hook scanning for new terms in v1.
- Lazy file creation contract: the file does not exist until the first term resolves. Consumer skills that read the glossary must proceed silently when the file is absent.

## Touch points

- cortex/requirements/glossary.md (new file, lazily created on first term resolved)
- skills/lifecycle/references/load-requirements.md (extend tag protocol with always-load or global-context wiring)
- skills/critical-review/SKILL.md:34-41 (Step 2a Project Context block — add glossary read)
- skills/requirements-gather/SKILL.md (interview body — add inline-write rule and per-entry classifier prose)
- skills/lifecycle/references/specify.md §2 (interview body — same inline-write rule and classifier prose; consumer-rule prose for skills that read but do not write)
