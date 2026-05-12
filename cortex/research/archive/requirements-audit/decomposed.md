# Decomposition: requirements-audit

## Epic
- **Backlog ID**: 009
- **Title**: Requirements management overhaul

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 010 | Fix skill sub-file path bug across all skills | high | S | — |
| 011 | Redesign /requirements skill and rewrite project.md | high | M | 010 |
| 012 | Gather area requirements docs for four missing areas | medium | M | 011 |
| 013 | Wire requirements drift check into lifecycle review | medium | S | 011 |

## Suggested Implementation Order

010 first (path bug blocks skill execution outside cortex-command). 011 next (skill format must be established before content work). 012 and 013 can run in parallel after 011 — they're independent of each other but both depend on the redesigned skill being in place.

010 and 011 are good overnight candidates run back-to-back in a single session. 012 is interactive (requires codebase reconnaissance per area). 013 is a focused lifecycle skill edit.

## Created Files
- `cortex/backlog/009-requirements-management-overhaul.md` — Epic
- `cortex/backlog/010-fix-skill-subfile-path-bug.md` — Fix skill sub-file path bug across all skills
- `cortex/backlog/011-redesign-requirements-skill-and-rewrite-project-md.md` — Redesign /requirements skill and rewrite project.md
- `cortex/backlog/012-gather-area-requirements-docs.md` — Gather area requirements docs for four missing areas
- `cortex/backlog/013-wire-requirements-drift-check-into-lifecycle-review.md` — Wire requirements drift check into lifecycle review
