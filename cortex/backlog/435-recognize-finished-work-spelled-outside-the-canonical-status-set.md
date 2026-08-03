---
schema_version: "1"
uuid: e5d142b1-9995-4927-a355-b0f5e5648045
title: Recognize finished work spelled outside the canonical status set
status: complete
priority: high
type: bug
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

In a consumer repo six finished tickets sit permanently in the active index because their status is spelled a way nothing recognizes — and they are that repo's entire active list. The index is the operator's statement of what remains, and it is wrong.

## Role

Makes a finished item read as finished regardless of which synonym its author wrote, so no repo's active index accumulates work that is already done.

## Integration

Extends the read-time status normalization that every index and dashboard consumer already routes through, so the correction reaches every repo retroactively without touching a stored file.

## Edges

- Must be read-time only. A write-time restriction cannot help: the offending values arrive from direct frontmatter edits rather than through the item-creation verb, which never ran in the affected repo.
- Must not narrow the terminal-status set in the same change. The parent-closing cascade reads raw unnormalized status, so narrowing before the affected values normalize would make finished work read as active.
- Non-goal: rewriting files in other repos. The fix is read-side precisely so it needs no migration to reach them.

## Touch points

- `cortex_command/common.py:1234-1244` — the alias map.
- Observed damage: `pixel-art-generator` carries 33 `complete` and 6 `completed`; the latter is in neither the alias map nor the terminal set.
