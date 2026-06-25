---
schema_version: "1"
uuid: 427d4c22-ea92-462e-a7c1-602342ef78cc
title: 'Offload lifecycle Step 2 backlog write-back + index.md creation into CLI verbs (lifecycle analog of #322)'
status: backlog
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

lifecycle Step 2's four sub-procedures — Backlog Status Check, Create index.md, Backlog Write-Back, Discovery Bootstrap (`references/backlog-writeback.md`, `references/discovery-bootstrap.md`) — narrate deterministic procedure for the agent to hand-execute: writing exact NDJSON events (`{"ts":...,"event":"feature_complete",...}`), running exact `cortex-update-item` calls with specific flags, the three-arm backend-routing branch (`cortex-backlog` / `none` / external) on every write, exit-2 disambiguation handling, and 7-field `index.md` frontmatter with inline-array + wikilink construction rules. This is the lifecycle analog of #322 (same shape, offloaded from refine). Surfaced in the 2026-06-25 lifecycle skill-trimming audit. Highest-leverage finding of that audit.

## Role

Move the mechanical write-backs behind one or two verbs — e.g. `cortex-lifecycle-start-sync {feature}` (status check + in_progress + lifecycle-slug write-back, backend-routed internally), and fold `index.md` creation into the `cortex-lifecycle-init-ensure` already called at the end of Step 2. The skill issues unconditional commands; backend routing, event shapes, exit-2 handling, and index templating live in code.

Residual that stays as prose (genuine model judgment — do NOT offload):

- The external-tracker backend arm ("compose a `gh issue` best-effort using config `backlog.instructions` and your judgment; surface content if it can't complete"). The verb handles `cortex-backlog`/`none` deterministically and returns a "needs-agent: <intent>" signal for the external case.
- The "already complete" Close/Continue prompt (needs the user) — though the deterministic branching *after* each choice can move into the verb.
- Discovery-bootstrap's epic-context guidance ("don't copy epic content; scope research/spec to this ticket"). That is What/Why for refine, not procedure. Keep it, terse.

## Integration

New `cortex_command` verbs + edits to `skills/lifecycle/references/{backlog-writeback,discovery-bootstrap}.md` and Step 2 (+ mirrors) → lifecycle-gated. Sibling to #322; share the backend-resolution approach (resolve-once, route `cortex-backlog`/`none`/external) so refine and lifecycle stop carrying parallel branches. Must preserve byte-identical `events.log` rows on the `cortex-backlog` arm and the `index.md` guard (skip if exists, never overwrite).

## Edges

- Resolver exit 3 (no backlog match) → lifecycle proceeds without a backlog item; all write-backs silent-skip.
- `phase != none` vs `phase = none` close-lifecycle paths differ (events.log append vs no-artifact exit) — preserve both exactly.
- `index.md` inline-array notation (`artifacts: []`) and wikilink prefix-padding rules must be reproduced exactly by the templating code.

## Touch-points

- new `cortex_command` verbs (start-sync; extend `init-ensure` for index.md)
- `skills/lifecycle/references/backlog-writeback.md`, `references/discovery-bootstrap.md`, `SKILL.md` Step 2 (+ mirrors)
- tests for the verbs + back-compat on the `cortex-backlog` arm