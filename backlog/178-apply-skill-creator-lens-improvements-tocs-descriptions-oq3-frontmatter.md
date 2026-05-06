---
schema_version: "1"
uuid: a978360e-228a-4b86-b9c5-bf059ab8c5a2
title: "Apply skill-creator-lens improvements (TOCs, descriptions + disambiguators, OQ3 softening, frontmatter symmetry)"
type: chore
status: backlog
priority: medium
parent: 172
blocked-by: []
tags: [lifecycle, refine, critical-review, discovery, skill-design, descriptions, oq3, vertical-planning]
created: 2026-05-06
updated: 2026-05-06
discovery_source: research/vertical-planning/research.md
---

# Apply skill-creator-lens improvements (TOCs, descriptions + disambiguators, OQ3 softening, frontmatter symmetry)

Four classes of skill-design quality improvements identified by the skill-creator-lens audit pass, bundled because they're all small mechanical edits across the four skill SKILL.md files. None depend on cross-skill collapse (Stream A) — can run in parallel.

## Context from discovery

The skill-creator-lens audit pass identified concerns the prior content-density audits missed because they focused on what's redundant rather than skill-design quality. Audit § *"Skill-creator-lens additions (new findings)"*.

## What to land

### 1. Add Tables of Contents to >300-line files

Skill-creator framework requires TOCs on >300-line reference files. Four files are over the threshold:

- `skills/lifecycle/SKILL.md` (380 lines)
- `skills/lifecycle/references/plan.md` (309 lines)
- `skills/lifecycle/references/implement.md` (301 lines)
- `skills/critical-review/SKILL.md` (365 lines)

Use `skills/discovery/references/research.md` (the only file currently with a TOC) as the template.

### 2. Description-trigger fixes + sibling disambiguators

All four SKILL.md `description` fields have measurable trigger gaps and sibling-disambiguation gaps:

- **lifecycle**: missing casual phrasings ("start a feature", "build this properly"); convert path-required clause from MUST-shape to soft routing; add "Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
- **refine**: missing intent phrasings ("spec this out", "tighten the requirements", "lock in the spec"); add "Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement."
- **critical-review**: missing phrasings ("poke holes in the plan", "stress test the spec", "is this actually a good idea", "review before I commit"). Already has `/devils-advocate` differentiator (keep).
- **discovery**: add "Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets."

### 3. OQ3 softening (or evidence-document)

Per cortex's CLAUDE.md OQ3 policy: MUST escalations require evidence trail. The skill-creator-lens audit sampled 10 instruction blocks and found 4 OQ3 violations:

- `skills/lifecycle/references/review.md:64,72,78,80` — 4 MUST/CRITICAL instances on the verdict JSON format. **Defensible escalation IF the OQ3 evidence trail (events.log F-row + effort=high failure) is added; otherwise soften to "the parser requires exactly this format — alternative names will fail to parse."**
- `skills/refine/references/clarify-critic.md:26,155,159` — 3 MUST instances, marginal. Soften with WHY explanations.

For each instance: either document the evidence trail per OQ3 OR soften to positive-routing per OQ3 default. Make the per-instance call based on whether soft form has been tested and shown to fail (per OQ3's effort=high rule).

### 4. Frontmatter symmetry

`skills/critical-review/SKILL.md` is invoked with `<artifact-path>` argument per `plan.md:330` but declares no input. All other three SKILL.md files have most of these fields. Add to critical-review:
- `argument-hint: "[<artifact-path>]"`
- `inputs:` (artifact path)
- `outputs:` (synthesis prose + optional residue write)
- `preconditions:` (artifact exists)
- Optionally `precondition_checks:` to short-circuit at load time

## Touch points

- `skills/lifecycle/SKILL.md` (TOC + description)
- `skills/lifecycle/references/plan.md` (TOC)
- `skills/lifecycle/references/implement.md` (TOC)
- `skills/lifecycle/references/review.md` (OQ3 softening)
- `skills/refine/SKILL.md` (description + disambiguator)
- `skills/refine/references/clarify-critic.md` (OQ3 softening) — note: ticket 175 may consolidate this into lifecycle's canonical
- `skills/critical-review/SKILL.md` (TOC + description + frontmatter symmetry)
- `skills/discovery/SKILL.md` (description disambiguator)
- All `plugins/cortex-core/skills/*` mirrors auto-regenerated

## Verification

- Each of the 4 large files has a `## Contents` or `## Table of Contents` section near the top
- `grep "Different from /cortex-core" skills/{lifecycle,refine,critical-review,discovery}/SKILL.md` returns matches in each file
- OQ3-violating lines in `review.md` and `clarify-critic.md` either have evidence-trail documentation comments OR are softened to positive-routing per OQ3
- `skills/critical-review/SKILL.md` frontmatter has `argument-hint`, `inputs`, `outputs`, `preconditions`
- Pre-commit dual-source drift hook passes
