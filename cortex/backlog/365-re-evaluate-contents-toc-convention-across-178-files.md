---
schema_version: "1"
uuid: 68677017-7c37-4469-8b5d-7d97ab27a4a8
title: 'Re-evaluate the ## Contents TOC convention across the four #178 files'
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: ['skills']
created: 2026-07-03
updated: 2026-07-03
---

## Why
#178 added a 4-item `## Contents` table-of-contents to a set of always-fully-loaded skill files. A token-audit candidate proposed deleting the critical-review one on the grounds that a TOC has no navigation value in a file that is always loaded whole. #360 **refuted** that deletion (kept the TOC) on the Solution-horizon principle: the argument applies *identically* to all four files #178 added TOCs to, so a unilateral single-file deletion in a trim chore would relitigate a corpus-wide convention and leave the other three asymmetric. This ticket is the spec-committed follow-up (#360 spec Non-Requirements) to make the call once, for the set.

## Role
Decide the convention for the four #178 TOC files as a set, then apply the decision uniformly (delete all, or keep all — not piecemeal). This is a low-value judgment call (~4 lines per file), so a legitimate outcome is **wontfix / keep** if the team judges the consistency + negligible cost outweighs the marginal token saving.

## Integration
If deletion is chosen: it touches multiple `skills/**/SKILL.md` files (lifecycle-gated per CLAUDE.md) plus their `plugins/cortex-core/` mirrors — do it under a lifecycle or a single coordinated commit with `just build-plugin`. Record the outcome so the convention question is not reopened.

## Edges
- Identify the exact four files from #178 before acting (do not assume the critical-review one is representative of all four's TOC shape).
- Frontmatter L1 ratchet is unaffected (TOCs are body content), but confirm no test pins a `## Contents` heading before removing.

## Touch points
- The four #178 TOC-bearing skill files (enumerate from #178) + their plugins/cortex-core mirrors
