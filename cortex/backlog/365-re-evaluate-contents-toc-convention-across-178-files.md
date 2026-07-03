---
schema_version: "1"
uuid: 68677017-7c37-4469-8b5d-7d97ab27a4a8
title: 'Re-evaluate the ## Contents TOC convention across the four #178 files'
status: complete
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

## Resolution (2026-07-03) — delete all
The four #178 files are `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/plan.md`, `skills/lifecycle/references/implement.md`, `skills/critical-review/SKILL.md`. By the time this ticket was actioned, three of the four had already shed their TOCs — each was trimmed below the 300-line skill-creator threshold that justified a TOC, so the de facto convention across the set was already "no TOC." Only `critical-review/SKILL.md` still carried one, and it too had fallen to 112 lines (well under 300).

This inverts #360's consistency argument: the corpus was already asymmetric, so deleting the last TOC **restores** symmetry rather than relitigating a live convention. Decision: **delete all** (uniformly satisfied by removing the sole survivor). Removed the 4-item `## Contents` block from `skills/critical-review/SKILL.md`; regenerated the `plugins/cortex-core` mirror via `just build-plugin`. No test pinned a `## Contents` heading; no file references the removed anchors; L1 surface ratchet unaffected (TOCs are body content). Convention question is closed — these always-fully-loaded skill files do not carry TOCs.
