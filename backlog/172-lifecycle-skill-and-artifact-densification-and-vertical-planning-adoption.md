---
schema_version: "1"
uuid: 96bf798d-0181-4c3f-bae8-6a8b87777610
title: "Lifecycle skill + artifact densification + vertical-planning adoption"
type: epic
status: complete
priority: high
blocked-by: []
tags: [lifecycle, refine, critical-review, discovery, densification, vertical-planning, token-efficiency]
created: 2026-05-06
updated: 2026-05-11
discovery_source: cortex/research/vertical-planning/research.md
---

# Lifecycle skill + artifact densification + vertical-planning adoption

Discovery research on Dexter Horthy's CRISPY/QRSPI vertical-planning framework + a four-agent value audit + pressure-test pass + skill-creator-lens audit identified that cortex's lifecycle skill family (lifecycle + refine + critical-review + discovery, 4,214 lines across 24 files) has accumulated significant duplication, ceremony, and content-locality mistakes — eating substantial token context per feature. The audit found ~24–25% of the corpus reducible without behavior change, plus ~325 lines of hot-path-context reduction available via conditional content extraction.

The original goal — adopt vertical-planning patterns from CRISPY into plan.md and spec.md templates — remains, but lands AFTER the cross-skill duplication collapses so the new sections live in one canonical home rather than getting added to duplicated copies.

## Context from discovery

Two artifacts capture the full analysis:

- `research/vertical-planning/research.md` — discovery research on the CRISPY framework, comparison with cortex's current plan/spec templates, design alternatives, and decision records. Key finding: the empirical case for "outlines force better agent reasoning" is practitioner-grade (1/5 evidence quality), but the human-skim case is well-supported.
- `research/vertical-planning/audit.md` — value audit of the entire skill corpus, with pressure-test corrections and skill-creator-lens additions. Key findings: ~700 lines of cross-skill duplication between `skills/refine/references/` and `skills/lifecycle/references/`; 21-line literal copy-paste bug in `refine/SKILL.md`; 5 stale references; ~115 lines of harness-level logic in `implement.md §1a` mostly duplicating `cortex_command/overnight/daytime_pipeline.py`; per-feature artifact bloat (`Open Decisions` 88% ceremony, `Scope Boundaries` no programmatic consumer, `Architectural Pattern` field 1.4% populated).

## Scope

11 child tickets organized into 7 streams. The streams sequence as: zero-risk first (Z), low-risk cross-skill collapse (A), parallel skill-side trims and improvements (B/C/D/E/H), then vertical-planning adoption (F) which depends on A.

## Child tickets

- 173 (Z) — Fix duplicated-block bug in refine/SKILL.md + 5 stale skill references
- 174 (A) — Collapse byte-identical refine/references files (orchestrator-review.md + specify.md → lifecycle canonical)
- 175 (A) — Promote refine/references/clarify-critic.md to canonical with schema-aware migration
- 176 (A) — Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md
- 177 (B) — Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate-description compression)
- 178 (C) — Apply skill-creator-lens improvements (TOCs + descriptions + sibling disambiguators + OQ3 softening + frontmatter symmetry)
- 179 (C) — Extract conditional content blocks to references/ (state-init split, plan-competing, research-parallel, implement-daytime, a-b-downgrade-rubric, parallel-execution)
- 180 (D) — Artifact template cleanups (Architectural Pattern critical-only + Scope Boundaries deletion + index.md frontmatter-only)
- 181 (E) — Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)
- 182 (F) — Vertical-planning adoption: `## Outline` in plan.md + `## Phases` in spec.md + P9/S7 orchestrator-review gates + parser regression test
- 183 (H) — Migrate complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`)

## Deferred / future work (not in this epic)

- **Optional `cortex plan-outline` topological-sort renderer**: a Mermaid + critical-path viewer derived from existing `Depends on:` graph. Defer until vertical-planning outline ships and we see whether outline-only is sufficient for skim. Pick up as a standalone backlog item when prioritized.
- **events.log per-event consumer audit + 2-tier scheme**: split `events.log` into spine + `events-detail.log` for `clarify_critic` / `critical_review*` blocks. Acceptance precondition: per-event verdict table for all ~71 emitted event types (Python + skill-md + dashboard + report + tests + hooks + bin/). Defer until the audit work is sized and prioritized.

## Realistic reduction estimate

- Skill corpus: ~1,025 lines (~24%) reduced via cross-skill collapse + content trims + skill-design improvements
- Hot-path context: ~325 additional lines reduced via conditional content extraction
- Plus ~25 lines from gate-description compression
- D4 (Open Decisions optional) blocked by design — both escalation gates are kept per Hold 1 resolution
