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

### 1. Architectural Pattern field — keep optional in default template (per epic-172-audit C3)

The `**Architectural Pattern**: {category}` field is currently in the plan.md template, but only **2 of 138 plans (1.4%)** populate it. Used by the synthesizer only on critical-tier (5 lifecycles in archive).

**Original ticket framing:** hide field from non-critical templates (gate to critical-tier-only). **Post-decomposition critical-review (C3) corrected this:** prior research at `lifecycle/archive/tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction/research.md:54,194` argued the *opposite* direction — make the field evaluated, not decorative. Hiding it silently reverses that.

**Fix:** keep the field in the default §3 template **as optional** (author writes a value when load-bearing for the plan; leaves blank otherwise). Critical-tier §1b template requires the field with closed-enum. Standard §3 template includes the field in the canonical format with a note "optional; populate when the plan's architectural shape warrants explicit naming."

This preserves the prior research's "evaluated, not decorative" intent while not forcing population on every plan.

Touch points:
- `skills/lifecycle/references/plan.md` §3 canonical template (remove field from default rendering)
- §1b critical-tier plan-agent prompt template (keep the field)
- `skills/lifecycle/references/orchestrator-review.md` P8 row (already correctly gated on `criticality = critical`; verify wording matches the new template behavior)

### 2. Delete `## Scope Boundaries` from plan template (deferred to ticket #182's Outline replacement)

53% of plans omit it; in the other 47%, content overlaps `## Non-Requirements` from the spec — 4 cases >60% literal text overlap, 18 more >30% overlap. **NO programmatic consumer** verified by grep.

**Per epic-172-audit Q-C / DR-1:** Scope Boundaries deletion happens via Candidate A in ticket #182 (vertical-planning adoption as REPLACEMENT, not addition). When `## Outline` lands in plan.md, the Scope Boundaries mirror is removed because spec.md's `## Non-Requirements` remains the canonical enumerative-excludes source. **Move this work item out of #180 and into #182** to avoid double-handling the plan.md template.

This step in #180: NO-OP after refactor; #182 owns the Scope Boundaries removal.

### 3. Compress index.md body — keep full frontmatter (per epic-172-audit C2)

**Original ticket framing:** strip body AND drop several frontmatter fields (`parent_backlog_uuid`, `created`, `updated`, `artifacts: [...]`). **Post-decomposition critical-review (C2) corrected this:**
- `artifacts: [...]` is appended by 4 reference files (`plan.md:259`, `review.md:148–149`, `refine/SKILL.md:188–189`); dropping the array leaves the append code orphaned
- `created` / `updated` are observability primitives — they're how a future audit reconstructs lifecycle timing; the audit itself depended on archive timestamps
- `parent_backlog_uuid` is the breadcrumb-resolution backstop when title-collision occurs

**Fix (revised):** drop only the H1 + intro prose + wikilink list (~10 lines per index.md). **Keep the full frontmatter:** `feature`, `tags`, `parent_backlog_id`, `parent_backlog_uuid`, `artifacts`, `created`, `updated`. Net per-file savings: ~8–10 lines (down from "frontmatter-only" estimate).

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

### 4. D4 — `## Open Decisions` made optional (UNBLOCKS per epic-172-audit Q-A)

Per Q-A partial reversal (DR-2): Gate 2 (Specify→Plan ≥3 Open Decisions) is being removed in ticket #183. With Gate 2 gone, the `## Open Decisions` section's only consumer is removed, and the audit's "D4 (Make Open Decisions optional)" item — previously BLOCKED on Gate 2 dependence — UNBLOCKS.

**Fix:** mark `## Open Decisions` as optional in `skills/lifecycle/references/specify.md §3` template. Spec author includes the section only when there's substantive content; absence is no longer a missing-section-flag concern. Authors may still emit "## Open Decisions: None" if they prefer; both forms become valid.

This is independent of D1–D3 (Architectural Pattern, Scope Boundaries, index.md) above and lands in the same ticket because all are spec/plan template changes.

## Verification

- A fresh non-critical plan (simple/medium/high) MAY contain `**Architectural Pattern**` field with author-discretion population (not gated)
- A fresh critical-tier plan still emits `**Architectural Pattern**` from a value in the closed enum
- Scope Boundaries removal is verified in ticket #182 (Outline replacement), not here
- A fresh `lifecycle/{feature}/index.md` body is ~3 lines (frontmatter unchanged in size; H1/intro/wikilinks removed)
- `lifecycle/{feature}/index.md` frontmatter retains `feature`, `tags`, `parent_backlog_id`, `parent_backlog_uuid`, `artifacts`, `created`, `updated`
- A fresh spec.md MAY omit `## Open Decisions` entirely (D4 unblocked); orchestrator-review S-checklist does not flag absence as failure
- `review.md §1.2` tag-based requirements loading still works on the new index.md format
- No regression in archived-feature compatibility
