---
schema_version: "1"
uuid: 6eebd147-4dfe-4c69-b410-55dedd5535e8
title: Generate a cross-lifecycle phase index wired to morning-review
status: abandoned
priority: medium
type: feature
created: 2026-06-14
updated: 2026-06-15
parent: "303"
tags: ['cortex-core-tooling-gaps']
discovery_source: cortex/research/cortex-core-tooling-gaps/research.md
complexity: complex
criticality: high
---
## Why

The repo carries well over a hundred lifecycle directories, and there is no way to answer "what lifecycles exist and what phase is each in" without scanning thousands of files by hand. The per-slug state and counter tools each answer about one named feature; nothing gives the cross-cutting view, and the session-start summary surfaces only incomplete features and does so ephemerally.

## Role

Provide a generated, queryable index of every lifecycle and its current phase — inferred from which artifacts are present and grouped by phase. After it lands, an operator or the morning report can see the whole lifecycle landscape at a glance instead of reconstructing it directory by directory.

## Integration

It reuses the existing phase-inference reducer that already maps artifact presence to a phase and is already consumed by the backlog index generator, and it follows the same deterministic, byte-stable, atomic-write index-generation discipline as the backlog index. Its output is wired into the morning report as a named consumer, so the index is not an orphan artifact — the morning report reads the generated index rather than re-scanning. The archive convention — the directories the lifecycle scanner already skips — is respected so archived lifecycles are excluded or segregated consistently.

## Edges

- Must be byte-deterministic: stable ordering and serialization so the committed index does not churn and a regenerate-and-diff check can gate staleness.
- Breaks if the phase-inference contract changes shape (a new phase value, a renamed artifact-to-phase mapping); it must consume that reducer rather than re-implement phase detection, so the two cannot drift.
- Requires a named consumer to justify its existence — the morning report. It is explicitly not a standalone artifact nobody reads.
- Does not replace the per-slug state tool or the session-start scanner; it is the aggregate view, not a per-feature lookup.
- Pairs with an opt-in archive capability but does not depend on it; archiving is deferred and out of scope here.

## Touch points

- `cortex_command/common.py` — the artifact-to-phase reducer (`detect_lifecycle_phase`) to reuse
- `cortex_command/backlog/generate_index.py:176-184` — precedent for reusing that reducer in a deterministic generator
- `cortex_command/backlog/generate_index.py:327-331` — the atomic-write / byte-stable index pattern to mirror
- `cortex_command/overnight/report.py` — the morning report, the named consumer to wire the index into
- `cortex_command/hooks/scan_lifecycle.py:907` — the archive/sessions skip convention to respect

## Closed — won't-do (2026-06-15)

Closed during refine (Clarify→Research) after a value pressure-test. Decided not to build. Rationale:

- **No broken root to fix.** The "125 lifecycle dirs" pain is *intentional* history retention, not neglect: `complete.md:274` explicitly says completed lifecycle dirs are "preserved as project history. Do not delete or archive." Measured: 115 of 125 active dirs already carry a `feature_complete` event; only ~10 are in-flight. The index would mostly catalog deliberately-retained history.
- **Thin ROI / zero consumers.** `report.py` reads no cross-lifecycle view; the dashboard scans per-feature on demand; nobody queries completed dirs by phase. Live work (~10 dirs) is already surfaced by the SessionStart scanner (by phase, stale-filtered) and dashboard swim-lanes. The ticket had to *manufacture* a consumer ("requires a named consumer … the morning report"), which has no existing seam and conflicts with epic 303's standalone-navigation framing.
- **Premise contradicts a prior decision.** The Edges ask for a *committed* index + regenerate-and-diff gate, but `untrack-backlog-index-cache` (commit `9875226c`, `.gitignore:38-39`) deliberately **gitignored** the analogous backlog index because committed aggregates rewritten by every writer cause divergent-copy conflicts across parallel sessions. A cross-lifecycle index has higher write fan-out.
- **The only true root fix (archiving completed lifecycles, candidate B4) was deliberately deferred** and carries a real blast radius: 106 backlog items reference ~125 live lifecycle paths that a move would break (hence `cortex-archive-rewrite-paths`).

If revived: build the minimal form only — a gitignored, regenerate-on-demand, standalone index (slug + base phase, `-paused` stripped per `generate_index.py:179`; exclude stale/phantom = "every live lifecycle"), no morning-report wiring — and reconsider it jointly with B4 (archive verb), since "keep history + index it" vs "archive it" is one design decision, not two.
