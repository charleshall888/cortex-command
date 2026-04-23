---
schema_version: "1"
uuid: 72f5acad-4544-46b2-8070-dfd1257d69b9
id: "138"
title: "Codify citation norm and premise-as-verification in /discovery research phase"
type: chore
status: complete
priority: medium
parent: "137"
blocked-by: []
tags: [discovery, rigor, skills]
areas: [skills]
created: 2026-04-22
updated: 2026-04-22
discovery_source: research/audit-and-improve-discovery-skill-rigor/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: codify-citation-norm-and-premise-as-verification-in-discovery-research-phase
complexity: complex
criticality: high
---

# Codify citation norm and premise-as-verification in /discovery research phase

Close two specific gaps in `skills/discovery/references/research.md` that let #092's projected-locator failure propagate into the artifact.

## Context from discovery

From `research/audit-and-improve-discovery-skill-rigor/research.md` §Feasibility, Approach A:

- **Citation norm is empirically ~85–95% but not codified as a rule.** `research.md:35-42` (§2 Codebase Analysis) describes investigation scope without requiring that codebase-pointing findings carry file:line citations or that search-negative results be reported explicitly. An agent can return "no relevant patterns found" silently, or return a paraphrase the orchestrator cannot verify. The failing opus-4-7 artifact sat at ~83% — the bottom of the observed distribution.
- **Prerequisites are framed as implementation sequencing, not premise verification.** In `research.md:67-73` (§5 Feasibility Assessment) and the template at `research.md:104-107`, a prerequisite like "Identify which prompts have 'summarize every N' scaffolding" reads as a downstream step the implementer will do. In #092's chain, this framing allowed a codebase check that should have gated ticket creation to slide to the implementer — who then found the empty corpus only after the lifecycle was already dispatched.

## Findings

Two protocol weaknesses, both anchored in `skills/discovery/references/research.md`:

1. Codebase-pointing claims can enter the artifact without a codebase-agent citation and without any signal when a search returned empty.
2. The Feasibility template's Prerequisites column does not distinguish "prerequisites that verify the premise" from "prerequisites that sequence the implementation."

## Success criteria

- Every codebase-pointing recommendation in a completed research.md carries either (a) a file:line citation traceable to codebase-agent output, or (b) an explicit `premise-unverified` mark.
- Empty-corpus searches are reported in the artifact as a distinct outcome, not omitted.
- Feasibility Prerequisites entries describing codebase-state checks are resolved during research, not deferred as implementation work.
- The orchestrator-review checklist (`orchestrator-review.md`) can be left unchanged — the rule is enforced at the synthesis-writing surface, not post-hoc.

## Dependencies

- None. This is a standalone rule edit in a single file.
- Blocks #139 by convention: #139's vendor-endorsement gating reads the `premise-unverified` signal this ticket introduces.
