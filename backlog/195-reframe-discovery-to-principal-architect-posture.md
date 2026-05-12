---
schema_version: "1"
uuid: ce49fbc8-a968-48ed-b1e7-de59ef6f171e
title: "Reframe discovery to principal-architect posture"
type: feature
status: complete
priority: high
blocked-by: []
tags: [discovery, skill-rewrite]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/discovery-architectural-posture-rewrite/research.md
complexity: complex
criticality: high
spec: lifecycle/reframe-discovery-to-principal-architect-posture/spec.md
areas: [skills]
lifecycle_phase: implement
session_id: null
---

> **Direction history**: This ticket landed DR-1 from the discovery_source. A subsequent reconsideration shifted to DR-G (demote-decompose: tickets promoted on-demand instead of created at discovery time) as #196 — that direction was reverted when honest re-examination showed it was solving a hypothetical pain (stale-ticket accumulation) not in the user's stated pain list, while DR-1 directly addresses all six stated pains. #196 is closed superseded by this ticket. The DR-G exploration produced 9 concrete strengthenings folded into this ticket's edges and spec-phase deliverables below. See `research/discovery-architectural-posture-rewrite/research.md` revision note 4 for the full audit trail.

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

### Edges from DR-G exploration (carryover)

- The section-partitioned prescriptive-prose check runs on BOTH the architecture-section at research-write time AND on ticket bodies at decompose-ticket-creation time — defense-in-depth catches mechanism leaks before they propagate from architecture to tickets (a single agent typically writes both, so catching upstream means one revision pass instead of N+1)
- The "Why N pieces" justification gate uses falsification framing, not justification — "for each adjacent pair of pieces, attempt to merge them and record what specifically blocks the merge; if nothing blocks, merge" — converts the gate from defensive (rationalizes count) to falsificationist (constrains count)
- Architecture-section authoring guidance accommodates non-constructive topic shapes (diagnostic, policy, migration) via a single permissive paragraph rather than branching sub-templates — the zero-piece exit handles diagnostic; policy and migration may author pieces as rule/scope/exceptions or sequence steps within the same Role/Integration/Edges shape
- The approval checkpoint offers a fourth option beyond approve/revise/drop: "Promote sub-topic to its own discovery" — when a piece is too speculative for child-ticket creation, route it into its own discovery flow instead of forcing it into the current epic
- Multi-epic discovery is constrained to 1 epic per discovery; if pieces span >1 logical grouping the discovery must split at clarify time before research, not produce multiple epics at decompose
- Re-running discovery on an existing topic produces a new research-dir slug (e.g., `vertical-planning-2`); existing tickets from the prior run stay open under their original epic; reconciliation between the two architectures is a manual decision at the user's discretion, not automated
- Dropping a piece without creating a ticket uses existing `cortex-update-item NNN status: closed` with a closing note — no new workflow surface for "rejected piece audit trail"; the closed-with-rationale convention is the audit trail

### Spec-phase MUST deliverables (load-bearing, not deferrable)

- **Worked examples + anti-patterns for architecture-section authoring**: one worked example per piece-shape category (surface-anchored, structural-novel) plus a 2-3 bullet anti-patterns list — both re-walks and user confusion confirmed that abstract "name pieces by role" is insufficient scaffolding without concrete examples
- **Lexical scanner shipped as actual code** (suggested `bin/cortex-check-prescriptive-prose`): runs at decompose ticket-creation time AND at research architecture-write time; flags any path:line / section-index / quoted-prose-patch in body sections (Role/Integration/Edges); Touch points exempted; pure prose-discipline gate is honor-system and confirmed inadequate by both pre-implementation re-walks
- **Concrete piece definition with worked examples** in the architecture-section authoring template — the user's confusion about "what is a piece" demonstrates the protocol must ground the abstraction concretely; combine with the worked-examples deliverable above

## Touch points

- `skills/discovery/references/clarify.md` §6 outputs — add the optional scope-envelope surface
- `skills/discovery/references/research.md` §6 output template — add the `## Architecture` section between Codebase Analysis and Web & Documentation Research; conditional bundling-justification surface fires when piece count exceeds threshold (current draft: >5)
- `skills/discovery/references/decompose.md` §2 (rewrite to consume the architecture-summary, specify the uniform body template, fold in authoring-time positive routing), §3(a)/(b) (keep — empirically validated by prior-session sampling), §4 (augment with single-piece and zero-piece branches), §5 (uniform ticket creation under the new template), `:147` (replace lexical-headers ban with section-partitioned check)
- `skills/discovery/references/decompose.md` removed surfaces: R2(a)/R2(b)/E9 at `:24-27`, surface-pattern helper at `:27`, R3 per-item ack at `:37-42`, R4 cap at `:35`, R5 flag propagation at `:70`, R7 flag-specific event types at `:46-52`, E10 invariant
- `research/{topic}/events.log` — three new events: `architecture_section_written` (piece_count, has_why_n_justification, status), `approval_checkpoint_responded` (response, revision_round), `prescriptive_check_run` (tickets_checked, flagged_count, flag_locations)
- New soft gates ship as positive-routing form per CLAUDE.md MUST-escalation policy; no MUST language without effort=high evidence
- `research/discovery-architectural-posture-rewrite/research.md` — full DR-1 specification including the spec-phase re-walk obligation
