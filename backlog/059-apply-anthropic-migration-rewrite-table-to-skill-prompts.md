---
schema_version: "1"
uuid: 9598763c-dc24-4089-a182-073f83182d91
title: "Apply Anthropic migration rewrite table to skill prompts"
status: abandoned
priority: low
type: chore
created: 2026-04-10
updated: 2026-04-10
parent: "49"
tags: [output-efficiency,skills]
blocked-by: []
---

# Apply Anthropic migration rewrite table to skill prompts

## Status: absorbed into #053

This ticket has been absorbed into **#053** ("Add subagent output formats and apply imperative-intensity rewrites"). See `backlog/053-add-subagent-output-formats-compress-synthesis.md` — the Axis B section contains the full scope originally intended for this ticket, with corrected direction.

**Why absorbed**: Both this ticket and #053 touch the same 9 SKILL.md files and share #052's research context. Bundling avoids double-editing the same files and duplicated verification work.

**Important correction**: The original body of this ticket (written during #052's implementation phase) described the rewrite direction **backwards** — it said the rewrites map "weak/suggestive phrasings to stronger imperative forms." This is wrong. Anthropic's actual guidance is the opposite: **soften aggressive imperatives** (CRITICAL, You MUST, ALWAYS, NEVER) to milder forms, because aggressive imperatives cause Opus 4.5/4.6 to **overtrigger**. See #053's Axis B section for the correct direction and the full rewrite table.

If future work ever splits this axis back out of #053, use #053's Axis B section as the source of truth — not this ticket's original body.
