---
schema_version: "1"
uuid: 79dc52ed-1d0b-4148-86cb-d0e015113892
title: "Reconcile discovery SKILL.md Architecture vocabulary with emitted research template"
status: backlog
priority: medium
type: bug
created: 2026-05-28
updated: 2026-05-28
areas: ['skills']
---
## Why

`/discovery`'s `SKILL.md` describes the research `## Architecture` section as having sub-sections named `### Integration shape` and `### Seam-level edges` (plus an optional `### Why N pieces` falsification gate) in two live operator paths — the GATE-2 brief-generation fallback that displays the dense Architecture section, and the `revise` option's "re-walk the Architecture write protocol" instruction. The research template actually emits only `### Pieces` and `### How they connect`, and expresses the piece-count concern as a soft inline comment ("if the piece count grows large, consider merging pieces") rather than a falsification gate. #268 reconciled `decompose.md` and `research.md` to the emitted vocabulary but deliberately scoped `SKILL.md` out (see its plan Risks, "Upstream heading drift left unfixed"). `SKILL.md` is now the lone straggler: when brief generation fails or a user picks `revise`, the agent is instructed to display or re-emit headings the template does not produce.

## Role

Bring `SKILL.md`'s GATE-2 fallback and `revise` re-walk into agreement with the actual emitted Architecture sub-sections, so all three discovery surfaces — the research template, `decompose.md`, and `SKILL.md` — describe the same artifact vocabulary.

## Integration

The emitted headings are the source of truth: `research.md` produces the artifact and #268 already aligned `decompose.md` to it, so `SKILL.md` must follow. Open question to resolve in clarify/research before editing: whether the `### Why N pieces` falsification gate that `SKILL.md` references is a deliberately-removed mechanic (softened to inline guidance in the template) or a real gate that drifted out — that is, whether the source of truth is the research template block or the Architecture write-protocol prose around it. Resolve this first, because a blind rename could delete a gate that should be preserved, or preserve one that was intentionally softened.

## Edges

- The `### Why N pieces` reference in the `revise` re-walk may name a mechanic the current template no longer implements — verify against the research Architecture write-protocol prose, not just the emitted template block, before deciding to drop, keep, or relocate it.
- Editing `SKILL.md` triggers the dual-source pre-commit mirror regeneration for the `cortex-core` plugin copy — the regenerated mirror must be staged in the same commit.
- Editing files under `skills/` is lifecycle-gated per `CLAUDE.md`; run this through `/cortex-core:lifecycle`.

## Touch points

- `skills/discovery/SKILL.md:82` — GATE-2 fallback Architecture sub-section list.
- `skills/discovery/SKILL.md:85` — `revise` re-walk vocabulary, including the `### Why N pieces` gate reference.
- `skills/discovery/references/research.md` `## Architecture` (~lines 111–124) and its §6 Architecture write protocol — read-only reference: the source-of-truth template plus the falsification-gate question.
- `plugins/cortex-core/skills/discovery/SKILL.md` — auto-regenerated mirror, staged at commit.
- `tests/test_discovery_module.py` — add coverage asserting `SKILL.md` names only the emitted sub-sections.

## References

- Follow-up to #268 (`auto-consolidation-pass-in-discovery-decompose`), deferred per its plan Risks section.
