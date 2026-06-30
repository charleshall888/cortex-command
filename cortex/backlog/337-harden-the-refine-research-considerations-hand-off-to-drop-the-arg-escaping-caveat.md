---
schema_version: "1"
uuid: 78434a7c-8871-4aeb-ad0f-cb620363d0b7
title: Harden the refine->research considerations hand-off to drop the arg-escaping caveat
status: backlog
priority: low
type: chore
created: 2026-06-29
updated: 2026-06-29
---
## Why

`/cortex-core:refine` hands alignment findings to `/cortex-core:research` through a research-considerations key="value" argument. Because the value rides inside the research skill's $ARGUMENTS string — which the model parses by prose — it cannot safely contain `=` or `"`, forcing BOTH skills to carry character-stripping prose (refine's Alignment-Considerations Propagation block; research Step 1's "not supported" caveat). The prose exists only because the channel is fragile. Split out of #322, which scoped itself to the resume-point offload and the backend structural guard.

## Role

Carry the alignment considerations over a channel that handles arbitrary multi-line text without escaping, so neither skill needs the character-stripping caveat. The fragility is model-parsing of key="value" from free text (Skill invocations run inline — same model, same conversation — so there is no subprocess: stdin and env vars are unavailable). Two directions surfaced during #322 research: a file in the lifecycle directory that research reads by the slug it already holds (it derives research.md from the same slug), or an explicit file-path argument. Choosing between the implicit slug-derived file and an explicit path, and resolving the stale-file edge below, is the work of this ticket.

## Integration

Consistent with the operator principle that deterministic string-handling belongs out of the model. Touches the refine->research hand-off only; no dependency on the #322 CLI changes. Subject to the skill-path-resolution invariant (SP001/SP002): if a path is passed, inject file content into composed subagent prompts rather than a bare path.

## Edges

- A persisted file must preserve the current channel's absence=no-findings semantics: on a run with no Apply'd findings (or a specify.md section 2a loop-back), research must not read stale findings from a prior run; the writer overwrites or clears each run.
- Research standalone mode (no lifecycle slug) continues to see no considerations.
- The considerations value format (newline-delimited bullets) and the per-angle injection points are unchanged in behavior.

## Touch-points

- skills/refine/SKILL.md — the Alignment-Considerations Propagation block (composition plus the escaping caveat) and the research dispatch
- skills/research/SKILL.md Step 1 — the considerations arg-parsing, the "not supported" caveat, and the injection points
- the auto-generated plugins/cortex-core mirror
- tests for the hand-off and the absence/stale-file semantics