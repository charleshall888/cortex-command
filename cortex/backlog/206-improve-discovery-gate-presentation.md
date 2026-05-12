---
schema_version: "1"
uuid: 310f9146-0267-46ab-8e6d-f5cf8bbe50bd
title: "Improve discovery gate presentation and add no-tickets terminus"
status: complete
priority: medium
type: feature
created: 2026-05-12
updated: 2026-05-12
tags: [discovery, skills, agentic-layer]
complexity: complex
criticality: high
areas: [skills]
session_id: null
lifecycle_phase: research
lifecycle_slug: improve-discovery-gate-presentation
spec: cortex/lifecycle/improve-discovery-gate-presentation/spec.md
---

# Improve discovery gate presentation and add no-tickets terminus

## Problem

Two friction points surfaced on a real discovery run (`cortex/research/artifact-format-evaluation/`) that #195's principal-architect reframe didn't anticipate:

1. **Gate surfaces decompose scaffolding, not findings.** At the Research→Decompose user-blocking gate, the skill presents the Architecture section (`### Pieces` / `### Integration shape` / `### Seam-level edges`). For posture-check topics whose honest output is "verdict + reasoning + small action," this buries WHAT and WHY behind engineering vocabulary. User reaction during the friction run: *"that architecture thing doesn't say much to me — summarize your findings."* Findings only surfaced when prompted, not at the gate.

2. **No clean terminus for "research did its job, no tickets needed."** Gate options are `approve` / `revise` / `drop` / `promote-sub-topic`. Posture-check topics that legitimately conclude with "no tickets" must exit via `drop`, which carries failure semantics. The decompose phase's existing zero-piece `## Verdict` path exists but requires first approving an Architecture section you know will produce zero pieces — awkward ceremony.

## Constraint

Layer on top of #195 — don't undo it. The decompose pathway must stay valid for ticket-producing topics. #196's "decompose-on-demand" reframe was already reverted because the user wants discovery to "create the epic AND the tickets in the backlog all in the same flow."

## Approach

Research evaluates 5+ candidate approaches at comparable depth (not anchored on the first one), per-option additive-vs-replacing trade-off, and recommends a direction in the spec. Critical-review pressure-tests whichever direction the spec lands on.

Candidates (research input — not prescription):
- Add a `## Findings` section to research.md (verdict + key findings with WHY + recommended actions + honest gaps) and lead the gate with it; Architecture stays as decompose input but is no longer the user-facing headline
- Restructure existing Architecture vocabulary to read more like findings, less like CS scaffolding
- Topic-shape branching (posture-check vs ticket-decomposition vs audit) with different output surfaces per shape
- A separate `## Recommend` or `## Conclude` phase between Research and Decompose
- Remove/relocate Architecture from the gate so something else is the surface
- Reach the existing decompose-phase zero-piece `## Verdict` path more directly from the gate
- A new gate-level exit (e.g., `findings-accepted`) that skips decompose entirely
- Other options surfaced during research

## Acceptance signal

Re-running discovery on a posture-check topic (such as artifact-format-evaluation) and not reacting with "summarize your findings" at the gate. Structural tests verify template/header conformance; subjective re-run is the experiential validation.

## Reference materials

- Current skill: `skills/discovery/SKILL.md` + `skills/discovery/references/{clarify,research,decompose,orchestrator-review}.md`
- Helper module: `cortex_command/discovery.py` (new gate option requires updating it)
- #195 lifecycle: `cortex/lifecycle/reframe-discovery-to-principal-architect-posture/`
- #195 source research: `cortex/research/discovery-architectural-posture-rewrite/research.md`
- #196 superseded context: `cortex/backlog/196-restructure-discovery-produce-architecture-not-tickets.md`
- Friction run: `cortex/research/artifact-format-evaluation/research.md` + `events.log`
