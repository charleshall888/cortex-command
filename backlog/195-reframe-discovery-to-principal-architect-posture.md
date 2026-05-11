---
schema_version: "1"
uuid: ce49fbc8-a968-48ed-b1e7-de59ef6f171e
title: "Reframe discovery to principal-architect posture"
type: feature
status: closed
priority: high
blocked-by: []
tags: [discovery, skill-rewrite, superseded]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/discovery-architectural-posture-rewrite/research.md
superseded_by: 196
---

> **SUPERSEDED by #196** (closed 2026-05-11). This ticket landed DR-1 from the discovery_source — the "discovery produces 1 epic + N piece-tickets" shape. Following a devil's advocate pass and critical re-examination, the structural direction shifted to DR-G (demote-decompose): discovery produces 1 epic + the research artifact's Architecture section as the load-bearing fragmentation reference; pieces promote to tickets on demand via a new promote-piece workflow. The user's stated framing ("high-level epic creation with rough ideas of what parts need to come together") points at DR-G, not DR-1. See `research/discovery-architectural-posture-rewrite/research.md` revision note 3 for the direction-change reasoning. The empirical re-walk evidence from this ticket's scope transfers to #196 — the ticket-body shape (Role/Integration/Edges/Touch-points) is what promote-piece will produce. Original body retained below for audit trail.

---

# Reframe discovery to principal-architect posture

## Role

Reframe the discovery skill's posture from finding-mirroring to architectural distillation, landing the principal-architect operationalization documented in `discovery_source`. The current protocol produces over-decomposed, undersized, prescriptive tickets that pigeonhole the downstream refine phase; the reframe replaces value-grounding-and-per-item-ack machinery with an architecture-summary surface, a phase-boundary approval gate, a uniform piece-shaped ticket template, and a section-partitioned prescriptive-prose check.

## Integration

- Modifies the clarify-phase output surface to include an optional scope-envelope (in-scope / out-of-scope) — pre-research scope-lock when the topic has tractable boundaries
- Adds an architecture-summary section and bundling-justification surface to the research-phase output template — names the pieces by role, the integration shape between them, and seam-level edges; bundling-justification fires when piece count exceeds the configured threshold
- Adds a phase-boundary approval gate between research and decompose — a single user-question gate ("are these the right pieces?") presenting the architecture-summary; supports approve / revise / drop outcomes
- Aggressively trims the decompose protocol — removes the value-grounding stack and per-item-ack flow, rewrites the work-item-identification step to consume the approved architecture-summary, augments the grouping logic with explicit branches for single-piece and zero-piece outcomes
- Replaces the existing lexical-headers ban with a section-partitioned prescriptive-prose check — the body-section partition is the gate, no threshold, no piece-type branching
- Specifies a uniform ticket-body template across all pieces (no defect-vs-novel binary): role / integration / edges plus an optional touch-points section that is the sole permitted location for path:line and section-index citations
- Replaces the removed flagging-event surface with three new gate-instrumentation events covering architecture-section authoring, approval-checkpoint response, and prescriptive-check run — enables countable skip-rate evidence for future MUST-escalation per project policy
- Downstream consumers (refine, lifecycle) read tickets via existing contracts; the refined template is backward-compatible with existing reads

## Edges

- The spec phase MUST re-walk the refined shape against `research/vertical-planning/` plus one alternative corpus before implementation lands — the load-bearing empirical validation step; this ticket's spec.md codifies the re-walk as a required step with pass/revise outcomes blocking implementation
- Single-piece architecture exits to a no-epic single-ticket path; zero-piece architecture exits to a fold-into-existing-#N or no-tickets verdict; the decomposition record (decomposed.md) is still written as audit trail in both cases
- Meta-tickets (those that modify skill prose) write surface citations to the touch-points section like any other ticket; the uniform rule does not branch on ticket type — section indices on a skill-modifying ticket are treated identically to path:line citations and live in touch-points
- The initial-draft defect-vs-novel binary annotation was cut at critical review for circularity (rubric restated the conclusion as the criterion, the lexical scan inverts under mis-annotation); this ticket lands the uniform-template shape, not the binary
- Vague-mush risk on novel pieces is partially-mitigated by the required edges surface plus authoring-time positive routing during body writing; the remainder is the spec-phase re-walk obligation acting as the empirical safety net before implementation
- Cumulative skip risk on the three new soft gates is countable via the events surface — if any gate is later observed to be routinely skipped under representative cases, the evidence supports MUST-escalation per the project's escalation policy
- Refine-side strengthening (extending refine's clarify-critic Parent Epic Alignment sub-rubric with an over-prescription check) is deferred — file as follow-up only if novel-piece vagueness persists after this ticket lands

## Touch points

- `skills/discovery/references/clarify.md` §6 outputs — add the optional scope-envelope surface
- `skills/discovery/references/research.md` §6 output template — add the `## Architecture` section between Codebase Analysis and Web & Documentation Research; conditional bundling-justification surface fires when piece count exceeds threshold (current draft: >5)
- `skills/discovery/references/decompose.md` §2 (rewrite to consume the architecture-summary, specify the uniform body template, fold in authoring-time positive routing), §3(a)/(b) (keep — empirically validated by prior-session sampling), §4 (augment with single-piece and zero-piece branches), §5 (uniform ticket creation under the new template), `:147` (replace lexical-headers ban with section-partitioned check)
- `skills/discovery/references/decompose.md` removed surfaces: R2(a)/R2(b)/E9 at `:24-27`, surface-pattern helper at `:27`, R3 per-item ack at `:37-42`, R4 cap at `:35`, R5 flag propagation at `:70`, R7 flag-specific event types at `:46-52`, E10 invariant
- `research/{topic}/events.log` — three new events: `architecture_section_written` (piece_count, has_why_n_justification, status), `approval_checkpoint_responded` (response, revision_round), `prescriptive_check_run` (tickets_checked, flagged_count, flag_locations)
- New soft gates ship as positive-routing form per CLAUDE.md MUST-escalation policy; no MUST language without effort=high evidence
- `research/discovery-architectural-posture-rewrite/research.md` — full DR-1 specification including the spec-phase re-walk obligation
