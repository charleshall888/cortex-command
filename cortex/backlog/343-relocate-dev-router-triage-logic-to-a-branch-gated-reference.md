---
schema_version: "1"
uuid: 69e763a3-e55d-49cb-8c94-cff16aa124b1
title: Relocate dev-router triage logic to a branch-gated reference
status: complete
priority: medium
type: chore
created: 2026-06-30
updated: 2026-07-01
parent: "340"
tags: ['skill-efficiency-remaining-work']
discovery_source: cortex/research/skill-efficiency-remaining-work/research.md
lifecycle_phase: research
lifecycle_slug: relocate-dev-router-triage-logic-to
complexity: complex
criticality: high
spec: cortex/lifecycle/relocate-dev-router-triage-logic-to/spec.md
areas: ['skills']
---
## Why
The dev router classifies a request into five first-match branches, but only one — backlog triage — uses the triage logic and the criticality heuristic table that currently sit inline in the router body. That block loads on all five branches and is pure dilution on the four that never execute it. Relocating it to a reference the triage branch reads on demand removes that dilution from the common routing paths without losing the criteria the triage branch needs. The recommendation logic stays prose, not a verb: it is presentation and routing judgment over a child map the existing epic-map verb already produces, so there is nothing deterministic to offload.

## Role
Move the backlog-triage block — the per-epic recommendation rendering, the flat-list dedup presentation, and the criticality heuristic table — out of the router body into a reference that the triage branch reads when it fires. Keep the exit-code routing for the epic-map verb (the non-zero fallback and halt) and the criticality criteria themselves intact as model-judgment guidance, loaded on demand rather than always resident.

## Integration
The triage branch already invokes the epic-map verb and renders its child map; the relocated reference holds the rendering and recommendation rules the branch applies to that output. The other four routing branches stop carrying the triage block in context. The epic-map verb's contract is unchanged — it still emits the deterministic child map; only the presentation prose moves.

## Edges
- Breaks the triage branch if the relocated reference is not read when the branch fires — the read must be wired into the branch entry.
- The exit-code fallback and halt for the epic-map verb is a safety routing decision and must stay with the branch, not move into the reference as narration.
- Must not turn the recommendation tree into a deterministic verb — it is judgment; a verb would mingle routing policy into the map generator.

## Touch points
- skills/dev/SKILL.md (the five-branch classifier; the triage block to relocate; the criticality heuristic table)
- new skills/dev/references/ triage reference (relocation target)
- cortex_command/backlog/build_epic_map.py:159 (child-map producer — contract unchanged)
- plugins/cortex-core/skills/dev/ (auto-generated mirror)