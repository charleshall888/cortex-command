---
schema_version: "1"
uuid: 8689319e-cc16-4db9-ae47-5316d3eaddfc
title: "Restructure discovery: produce architecture, not tickets"
type: feature
status: closed
priority: high
blocked-by: []
tags: [discovery, skill-rewrite, superseded]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/discovery-architectural-posture-rewrite/research.md
superseded_by: 195
---

> **SUPERSEDED by #195** (closed 2026-05-11). This ticket landed DR-G (demote-decompose: tickets promoted on-demand instead of created at discovery time). Honest re-examination after creation showed DR-G was solving a hypothetical pain (stale-ticket accumulation in the backlog) that was NOT in the user's stated pain list, while DR-1 (#195) directly addresses all six stated pains. The user explicitly stated preference for "discovery should create the epic AND the tickets in the backlog all in the same flow" — that's DR-1, not DR-G. Reverted to #195. The DR-G exploration produced 9 concrete strengthenings that carry over into #195's edges and spec-phase deliverables; the empirical re-walk evidence transfers because the ticket-body shape (Role/Integration/Edges/Touch-points) is unchanged. See `research/discovery-architectural-posture-rewrite/research.md` revision note 4 for full audit trail of the swing-and-revert. Original body retained below for audit trail.

---

# Restructure discovery: produce architecture, not tickets

## Role

Restructure the discovery skill so its output is a high-level architectural artifact rather than a fan-out of per-piece backlog tickets. The user's reframe of discovery's correct posture — "high-level epic creation with rough ideas of what parts need to come together" — points at this shape directly. Discovery produces an epic ticket plus a load-bearing Architecture section in the research artifact; pieces become backlog tickets only when work is about to start, via a new on-demand promotion workflow. The over-decomposition pressure, the bundling pain, and the staleness of unworked piece-tickets are removed at the source rather than softened with gates downstream.

## Integration

- Modifies the clarify-phase output surface with an optional scope-envelope (in-scope / out-of-scope) — pre-research scope-lock when the topic has tractable boundaries
- Restructures the research-phase output template around a load-bearing Architecture section that names pieces by role, integration shape between pieces, and seam-level edges; richness must be sufficient to drive useful ticket creation at promotion time rather than just summarizing for a decompose step
- Adds a phase-boundary approval gate between research and decompose — single user-question gate locking in the architectural shape before any backlog state changes
- Aggressively simplifies the decompose phase to a single responsibility: create one epic ticket (or zero tickets via fold-into-existing-#N / no-tickets verdicts); per-piece ticket creation is removed entirely from the discovery phase
- Adds a new promote-piece workflow (skill or CLI command) — takes a named piece from the research artifact's Architecture section and produces a backlog ticket with the uniform Role/Integration/Edges/Touch-points body; runs at the moment work is about to start, with current implementer context
- Relocates the section-partitioned prescriptive-prose check from decompose-time-batch to promote-piece-time-per-piece — the gate runs at ticket creation, not at discovery completion
- Replaces the existing flagging-event surface with new gate-instrumentation events covering architecture authoring, approval-checkpoint response, and piece promotion — countable skip-rate evidence for future MUST-escalation per project policy
- Refine and lifecycle continue unchanged — they consume backlog tickets via existing contracts; the contracts are unchanged, only the timing of ticket creation differs

## Edges

- The Architecture section becomes the load-bearing artifact rather than a summary feeding decompose; richness must support useful ticket creation at promotion time, potentially six months after the discovery ran — spec phase must produce one worked example per piece-shape category plus anti-patterns to calibrate the right richness
- Pre-implementation re-walks from the predecessor ticket validated the per-piece ticket-body shape (Role/Integration/Edges/Touch-points) that promote-piece will produce; the empirical evidence transfers without re-walking
- Existing discovery-sourced backlog tickets (epic-82 children, epic-165 children, epic-187 children, epic-172 children) stay as-is under the prior shape; no retroactive migration; the new shape applies to discoveries running after this ticket lands
- Backlog visibility for not-yet-promoted pieces lives in the research artifact rather than the backlog index — at-a-glance "this epic has 9 pieces" requires opening the research artifact; the trade is accepted because the alternative (every piece materialized as a backlog row, many stale) is the failure mode this ticket exists to eliminate
- The previously-deferred refine-side over-prescription strengthening becomes structurally less important under this shape because per-piece tickets are authored with current implementer context rather than at decompose time; refine still serves its existing purpose
- Promote-piece's prescriptive-prose check is the primary defense against per-piece ticket mechanism leak; without it being implemented as actual code (not honor-system), the gate is unenforced
- The "Why N pieces" justification gate from the predecessor ticket is removed entirely — under this shape there is no decompose-time pressure to constrain piece count because pieces are not materialized as tickets at decompose; the architecture-section authoring agent is free to identify the right number of pieces without count pressure
- Approval-checkpoint single-question gate ("is this the right architecture?") is structurally stronger than its predecessor variant because it gates the load-bearing artifact rather than a fan-out of tickets that will mostly sit unworked
- Vague-mush risk on novel pieces persists at promote-piece time; the lexical scanner-as-code and the implementer's current context at promotion are the two defenses; refine-side strengthening remains the deferred backstop if vague-mush proves intractable empirically
- Sandbox-write paths and existing `discovery_source` field convention are reused; promote-piece tickets carry the same `discovery_source` link back to the research artifact

## Touch points

- `skills/discovery/references/clarify.md` §6 outputs — add optional scope-envelope surface (unchanged from #195's design)
- `skills/discovery/references/research.md` §6 output template — add `## Architecture` section between Codebase Analysis and Web & Documentation Research; richness target is "sufficient to drive useful ticket creation at promotion time" rather than the predecessor's "summary feeding decompose §2"; piece-count justification gate from #195 is removed
- `skills/discovery/references/decompose.md` — aggressive simplification: keep §3(a)/(b) consolidation guidance for pre-promotion piece-grouping intuition only; rewrite §2 to create one epic ticket (or zero via fold-into-#N / no-tickets exit); remove R2-R5 / surface-pattern helper / R3 ack flow / R4 cap / R5 propagation / R7 flag events / E9 / E10 / decompose.md:147 lexical-headers ban; uniform ticket template content moves to promote-piece's reference; §4 grouping simplified to "create epic, or exit"
- New skill at `skills/promote-piece/` (or equivalent CLI under `bin/cortex-promote-piece`) — reads named piece from research artifact's Architecture section; produces backlog ticket with uniform Role/Integration/Edges/Touch-points body; runs section-partitioned prescriptive-prose check at ticket-body authoring time
- `research/{topic}/events.log` — new events: `architecture_section_written` (piece_count, status), `approval_checkpoint_responded` (response, revision_round), `piece_promoted` (piece_name, ticket_id, prescriptive_check_flag_count)
- Section-partitioned prescriptive-prose check must be implemented as actual code (suggested `bin/cortex-check-prescriptive-prose` script) — runs at promote-piece time on the produced ticket body; flags any path:line / section-index / quoted-prose-patch in Role/Integration/Edges sections; Touch points permits freely
- All new soft gates ship as positive-routing form per CLAUDE.md MUST-escalation policy; no MUST language without effort=high evidence
- `research/discovery-architectural-posture-rewrite/research.md` — full DR-G specification including pre-implementation re-walks (which validated the ticket-body shape that promote-piece will produce); revision note 3 documents the direction change from #195's DR-1 shape
- Spec phase must resolve: promote-piece UX (slash command vs CLI), Architecture section richness calibration via worked examples, whether refine on the epic ticket is lightweight or skipped, transition signaling so users of the discovery skill know which shape they're running
