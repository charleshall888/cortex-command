---
schema_version: "1"
uuid: 88ed3e3d-5025-40f4-94a5-0b1fadb20d44
title: "Auto-consolidation pass in /discovery decompose phase"
status: refined
priority: medium
type: discovery
created: 2026-05-28
updated: 2026-05-28
lifecycle_phase: research
lifecycle_slug: auto-consolidation-pass-in-discovery-decompose
complexity: complex
criticality: high
spec: cortex/lifecycle/auto-consolidation-pass-in-discovery-decompose/spec.md
areas: ['skills']
---
## Why

Discovery's decompose phase surfaces consolidation as a user-facing option only — the post-decompose batch-review gate exposes a `consolidate-pieces N,M` choice the user can invoke after seeing the drafted ticket bodies. The agent does not proactively run a consolidation pass. In practice this lands wrong-sized decompositions in front of the user: in the palette-editor-design-surface discovery (2026-05-27) the agent drafted four child tickets where two were the right cut — importers and exporters shared format-dispatch and round-trip-parity surfaces, and authoring and visualisations only deliver value when shipped together as the educational design loop. The user had to read four bodies, spot the false boundaries, and direct the consolidation manually. The decompose Consolidation Review step explicitly says not to re-run the falsification gate, leaving the agent without a mechanism to propose mergers — but the architecture-section falsification gate runs at research time when piece bodies do not yet exist, so the strongest coupling signals (shared touch-points, shared test surface, value-only-when-shipped-together) are unavailable at the moment the gate fires.

## Desired outcome

Decompose runs an automatic consolidation pass during ticket authoring — after each piece's body is drafted but before the R15 batch-review gate fires — that scans for tight-coupling signals across drafted bodies and proposes consolidations to the user with rationale rather than waiting for the user to call them out. The R15 manual `consolidate-pieces` affordance remains as a fallback for cases the auto-pass misses, but the typical decomposition lands at the gate already at the right cardinality. Open exploration: what coupling signals warrant an auto-consolidation proposal (shared touch-points, identical Role lead, shared edge contracts, dependency-only stub pieces); how the auto-pass interacts with the existing piece-count falsification gate from research; whether the auto-pass proposes consolidations one-by-one or batches them; what model size / context the auto-pass needs to read piece bodies critically.

## Acceptance

A research artifact at `cortex/research/{slug}/research.md` that answers: which coupling signals are detectable from drafted ticket bodies; where in the decompose flow the auto-pass runs (before R15? as a hidden step inside R15?); whether the pass replaces or augments the existing `consolidate-pieces` option; and a recommended shape for the pass (heuristic vs LLM-driven, single-pass vs iterative, user-confirmation model). The artifact decomposes into one or more implementation backlog tickets under the standard Role/Integration/Edges/Touch-points template.

## References

- `skills/discovery/references/decompose.md` §3 (Consolidation Review) — the current "do not re-run falsification" stance.
- `skills/discovery/references/decompose.md` §5 (Post-decompose batch-review gate R15) — the existing manual `consolidate-pieces` affordance.
- `skills/discovery/references/research.md` §6 / Architecture write protocol — the existing piece-count falsification gate that runs at research time.
- `cortex/research/palette-editor-design-surface/decomposed.md` — Consolidation Notes section documenting the 4 → 2 manual consolidation that motivated this ticket.