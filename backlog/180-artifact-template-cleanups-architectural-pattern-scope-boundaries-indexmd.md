---
schema_version: "1"
uuid: a5e3d90f-7e20-49ab-8be8-c9fd6bbe45b6
title: "Artifact template cleanups (Architectural Pattern critical-only + Scope Boundaries deletion + index.md frontmatter-only)"
type: chore
status: backlog
priority: medium
parent: 172
blocked-by: []
tags: [lifecycle, plan-template, spec-template, indexmd, artifact-densification, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Artifact template cleanups (Architectural Pattern critical-only + Scope Boundaries deletion + index.md frontmatter-only)

Three independent template/artifact changes that reduce per-feature artifact bloat going forward without touching the skill instruction docs. Bundled because all three are template edits with similar low-risk profiles.

## Context from discovery

The artifact audit pass identified per-feature sections that are written by tradition but have weak or no consumers, costing tokens both in artifact storage and in reviewer/dispatch prompts that read full specs/plans. Audit § *"Top artifact-side cuts"* + pressure-test corrections.

## What to land

### 1. Architectural Pattern field gated to critical-tier-only

The `**Architectural Pattern**: {category}` field is currently in the plan.md template, but only **2 of 138 plans (1.4%)** populate it. Used by the synthesizer only on critical-tier (5 lifecycles in archive). For non-critical plans the orchestrator-review checklist explicitly marks P8 as "N/A for non-critical plans" — but the plan template still includes it in the format block, leaking presence-bias.

**Fix**: emit the field only in plans produced via §1b (Competing Plans), which is the critical-tier dual-plan flow. The standard §3 template should NOT include it.

Touch points:
- `skills/lifecycle/references/plan.md` §3 canonical template (remove field from default rendering)
- §1b critical-tier plan-agent prompt template (keep the field)
- `skills/lifecycle/references/orchestrator-review.md` P8 row (already correctly gated on `criticality = critical`; verify wording matches the new template behavior)

### 2. Delete `## Scope Boundaries` from plan template

53% of plans omit it; in the other 47%, content overlaps `## Non-Requirements` from the spec — 4 cases >60% literal text overlap, 18 more >30% overlap. **NO programmatic consumer** verified by grep across `cortex_command/`, `hooks/`, `claude/hooks/`, `.py`, `.sh` files.

**Fix**: delete from `skills/lifecycle/references/plan.md §3` template. Specs continue to carry `## Non-Requirements` as the canonical scope boundary surface. If a plan needs adjacent-but-out-of-scope notes, they can live as a single optional bullet at the end of spec's Non-Requirements (no template change needed for that).

### 3. Compress index.md to frontmatter-only

The `lifecycle/{feature}/index.md` body wikilinks have **NO programmatic consumers** beyond the YAML `tags:` array (read by `review.md §1.2` for tag-based requirements loading). The H1 title, "Feature lifecycle for…" intro, and bulleted artifact wikilinks serve only Obsidian-vault navigation for humans — but `lifecycle/{feature}/` directory structure already provides that navigation natively.

**Fix**: reduce index.md template to frontmatter-only:
- Keep: `feature`, `tags`, `parent_backlog_id` (for breadcrumb resolution)
- Drop: H1 title, intro prose, artifact wikilinks, `parent_backlog_uuid`, `created`, `updated`, `artifacts: [...]` array (no consumers found)

Touch points:
- `skills/lifecycle/SKILL.md` "Create index.md" section (lines 108–143)
- `skills/lifecycle/references/plan.md` index.md update step (lines 258–264)
- `skills/lifecycle/references/review.md` index.md update step (lines 147–153)
- `skills/refine/SKILL.md` index.md update step (lines 187–193)

## Risks

- **Architectural Pattern**: gating may regress orchestrator-review P8 if the wording is mismatched. Verify P8 still asserts "critical-tier only" and that simple/medium/high plans skip the check.
- **Scope Boundaries**: any reviewer or dispatch prompt that *implicitly* relied on this section's text (e.g., for context-setting) may behave slightly differently. Audit found no programmatic consumers but reviewer prompts include the full plan body.
- **index.md compression**: any Obsidian user navigating via wikilinks will lose those breadcrumbs. The `tags:` field is preserved, but humans relying on the H1 title for quick scanning will be affected. Consider whether to keep the H1 title only.

## Touch points

- `skills/lifecycle/references/plan.md` (Architectural Pattern + Scope Boundaries)
- `skills/lifecycle/references/orchestrator-review.md` (P8 wording verify)
- `skills/lifecycle/SKILL.md` (index.md template)
- `skills/lifecycle/references/plan.md` (index.md update step)
- `skills/lifecycle/references/review.md` (index.md update step)
- `skills/refine/SKILL.md` (index.md update step)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- A fresh non-critical plan (simple/medium/high) does NOT contain `**Architectural Pattern**` field
- A fresh critical-tier plan still emits `**Architectural Pattern**` from a value in the closed enum
- A fresh plan does NOT contain `## Scope Boundaries` section
- A fresh `lifecycle/{feature}/index.md` is ≤8 lines (frontmatter only) with `feature`, `tags`, `parent_backlog_id`
- `review.md §1.2` tag-based requirements loading still works on the new index.md format
- No regression in archived-feature compatibility (archived plans/specs/index.md files with old sections still parse correctly)
