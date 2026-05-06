# Decomposition: vertical-planning

## Epic

- **Backlog ID**: 172
- **Title**: Lifecycle skill + artifact densification + vertical-planning adoption

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 173 | Fix duplicated-block bug in refine/SKILL.md + 5 stale skill references | high | S | — |
| 174 | Collapse byte-identical refine/references files (orchestrator-review.md + specify.md → lifecycle canonical) | high | S | — |
| 175 | Promote refine/references/clarify-critic.md to canonical with schema-aware migration | high | M | — |
| 176 | Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md | high | M | — |
| 177 | Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression) | high | M | — |
| 178 | Apply skill-creator-lens improvements (TOCs + descriptions + sibling disambiguators + OQ3 softening + frontmatter symmetry) | medium | M | — |
| 179 | Extract conditional content blocks to references/ | medium | M | 174, 175, 176, 177 |
| 180 | Artifact template cleanups (Architectural Pattern critical-only + Scope Boundaries deletion + index.md frontmatter-only) | medium | S | — |
| 181 | Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget) | medium | M | — |
| 182 | Vertical-planning adoption: `## Outline` in plan.md + `## Phases` in spec.md + P9/S7 gates + parser regression test | high | L | 174, 175, 176 |
| 183 | Migrate complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`) | medium | M | 174, 177 |

## Suggested Implementation Order

**Wave 1** (parallel, no dependencies — safe to dispatch concurrently):
- 173 (zero-risk bug + stale-ref fixes)
- 174 (byte-identical collapses, low-risk)
- 175 (clarify-critic schema-aware promote)
- 176 (cortex-resolve-backlog-item adoption)
- 177 (skill-side content trims)
- 178 (skill-creator-lens improvements)
- 180 (artifact template cleanups)
- 181 (test infrastructure)

**Wave 2** (depends on Wave 1's cross-skill collapse and content trims being settled):
- 179 (conditional content extraction — depends on 174/175/176/177)
- 182 (vertical-planning adoption — depends on 174/175/176)
- 183 (deterministic hook migration — depends on 174/177)

## Key Design Decisions

### Consolidation rationale

Original decomposition was 29 children across 7 streams. Consolidated to 11 children + epic by merging same-stream tickets that share files and risk profiles:

- **Stream Z merged into 173** — bug fix + stale refs are both zero-risk mechanical edits
- **Stream A kept as 4 tickets (174–176 plus the byte-identical pair as 174)** — different risk profiles preserved (byte-identical collapse vs schema-aware vs predicate-test)
- **Stream B merged into 177** — three independent content trims, all in-skill, similar risk
- **Stream C merged into 178 + 179** — skill-creator-lens improvements bundled (TOCs/descriptions/OQ3/frontmatter); conditional extraction kept separate (depends on Stream A)
- **Stream D merged into 180** — three artifact template cleanups, all template edits
- **Stream E merged into 181** — four test classes, all test-infrastructure adds
- **Stream F merged into 182** — outline + phases + gates + parser test bundled as one cohesive vertical-planning adoption ticket
- **Stream H kept as 183** — hook migration is its own infrastructure concern

### Holds resolved (post-critical-review)

- **Hold 1 — escalation gates**: keep both gates (user explicit). D4 (make Open Decisions optional) remains BLOCKED in the decomposition because both gates are kept consumers. Compression direction: Tier 1 in-skill compression (folded into 177) + Tier 3 hook migration (183).
- **Hold 2 — Stream C scope**: accept as scoped. The critical-review's "imported heuristics may not transfer" concern was specific to the runtime-fallback issue #5, which was already dropped during the critical-review apply step. The remaining Stream C items (TOCs, descriptions, OQ3 softening, frontmatter symmetry, conditional extraction) all have local cortex justification.

### Deferred / future work (not in this epic)

- **Optional `cortex plan-outline` topological-sort renderer**: deferred. Pick up as a standalone backlog item if outline-only proves insufficient for skim.
- **events.log per-event consumer audit + 2-tier scheme**: deferred. Acceptance precondition is a per-event verdict table for all ~71 emitted event types; the audit's pressure-test pass identified at least 4 events the original audit miscategorized as dead, including routing-primitive `complexity_override` and `criticality_override`. Stream G is treated as starting hypothesis, not verified truth — create standalone tickets when the consumer audit is sized and prioritized.

### Critical-review corrections applied to audit before decomposition

The audit's pressure-test pass and skill-creator-lens pass led to inline corrections to `research/vertical-planning/audit.md`:

- Worked-examples double-book between per-file cut #3 and S2 resolved in favor of S2 extraction
- Cross-skill issue #5 (skill-failed-to-load runtime fallback) DROPPED — targeted a non-existent runtime failure mode in cortex's plugin-only deployment
- S2 risk re-rated from Low-medium to Medium (6-file maintenance burden + trigger-prose requirement)
- state-init.md extraction split — re-entrant logic stays resident, only first-invocation logic extracts
- events.log overconfidence elevated to NEAR-MISS RUNTIME RISK severity
- Realistic reduction estimate revised from 43–52% to ~24–25% (~1,000–1,050 lines), plus ~300 hot-path-context lines from S2

## Created Files

- `backlog/172-lifecycle-skill-and-artifact-densification-and-vertical-planning-adoption.md` — Epic
- `backlog/173-fix-duplicated-block-bug-in-refine-skillmd-and-5-stale-skill-references.md`
- `backlog/174-collapse-byte-identical-refine-references-files-orchestrator-review-and-specify.md`
- `backlog/175-promote-refine-clarify-critic-to-canonical-with-schema-aware-migration.md`
- `backlog/176-lifecycle-adopts-cortex-resolve-backlog-item-and-delete-refine-clarify.md`
- `backlog/177-trim-verbose-lifecycle-skill-content-implementmd-1a-planmd-1b-and-skill-gate-compression.md`
- `backlog/178-apply-skill-creator-lens-improvements-tocs-descriptions-oq3-frontmatter.md`
- `backlog/179-extract-conditional-content-blocks-to-references.md`
- `backlog/180-artifact-template-cleanups-architectural-pattern-scope-boundaries-indexmd.md`
- `backlog/181-skill-design-test-infrastructure-descriptions-handoff-paths-budget.md`
- `backlog/182-vertical-planning-adoption-outline-and-phases-and-p9-s7-gates-and-parser-test.md`
- `backlog/183-migrate-complexity-escalation-gates-to-deterministic-python-hook.md`
