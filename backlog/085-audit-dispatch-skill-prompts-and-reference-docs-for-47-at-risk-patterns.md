---
schema_version: "1"
uuid: f3b4b249-b40c-4d70-a06c-f3e95030ba21
title: "Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns"
status: backlog
priority: high
type: feature
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, skills]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: [83, 84]
---

# Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns

## Motivation

DR-2 in the research artifact scopes this audit to the 7 skills that dispatch subagents via the Agent tool — these are the surface where Anthropic's own 4.7 guidance names regressions ("fewer subagents by default", "fewer tool calls") and where all five observed failures (F1–F5) occurred.

## Research context

Prior art: backlog #053 (complete) softened aggressive imperatives (`CRITICAL:`, `MUST`, `ALWAYS`, `NEVER`, `IMPORTANT:`, `make sure to`, etc.) for the 4.5/4.6 migration. This ticket audits six *additional* at-risk patterns that 4.7's stricter literalism exposes — patterns #053 did not cover.

See `research/opus-4-7-harness-adaptation/research.md` §"Six at-risk patterns not covered by #053" for the full pattern table and example sites.

## Audit surface (DR-2)

- **7 dispatch skills**: `critical-review`, `research`, `pr-review`, `discovery`, `lifecycle`, `diagnose`, `overnight` (SKILL.md + `references/*.md`)
- **5 reference files**: `claude/reference/claude-skills.md`, `context-file-authoring.md`, `output-floors.md`, `parallel-agents.md`, `verification-mindset.md`

## At-risk patterns to audit

- **P1**: Double-negation suppression (`omit X entirely — do not emit empty header`)
- **P2**: Ambiguous conditional bypass (`Only X satisfies this check ... If Y, always run Z`)
- **P3**: Negation-only prohibition (`Do not be balanced. Do not cover other angles.`)
- **P4**: Multi-condition gates with implicit short-circuit
- **P5**: Procedural order dependency (`do not omit, reorder, or paraphrase`)
- **P6**: Examples-as-exhaustive lists (`Select from this menu`, `such as`)
- **P7 (from Ask-2 fold-in)**: `consider` / `try to` / `if possible` hedges — three-category classification (conditional-requirement / genuinely-optional / polite-imperative)

## Dependencies

- #083 (claude-api migrate results) may contract this audit's scope if the built-in migration already covers prompts
- #084 (reference loading verification) may expand scope to include additional reference-file patterns

## Scope exclusions

- Preservation rules from #053 (security strings, output-channel directives, control-flow gates, output-floor field names, quoted source, example code blocks, section headers) are out of scope per DR-1 unless #084 surfaces new evidence against them
- Non-dispatch skills (`backlog`, `commit`, `retro`, etc.) are excluded per DR-2's scoping
