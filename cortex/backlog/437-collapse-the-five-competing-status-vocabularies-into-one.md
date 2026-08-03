---
schema_version: "1"
uuid: 757293e2-4dd1-45ca-8e60-4e2b125732ed
title: Collapse the five competing status vocabularies into one
status: backlog
priority: medium
type: chore
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
blocked-by: []
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

Five separate declarations describe which statuses exist and they disagree. Three of them have no readers at all — including the one a published doc names as the canonical list. Nothing validates the field on write, so the corpus carries values no declaration mentions, and a reader cannot tell which list is authoritative.

## Role

Establishes one authoritative statement of the status vocabulary and removes the declarations that look authoritative but are read by nothing.

## Integration

Consolidates onto the terminal-status set that the readiness predicate, index generation, and the parent-closing cascade already consult, so every consumer resolves against one list rather than picking whichever declaration it happened to import.

## Edges

- Ordering is load-bearing. The corpus must normalize before the set narrows, because the parent-closing cascade reads raw unnormalized status while every other reader normalizes — narrowing first would make several finished items read as active.
- Must not perform the migration through the item-update verb. Its terminal-transition cascade rewrites other items' blocker arrays, so a bulk pass would mutate files it was never pointed at.
- Non-goal: write-time validation. It cannot catch values that arrive by direct frontmatter edit, which is how the observed drift arrived.
- Per-repo migration is out of reach from here; consumer repos carry their own out-of-vocabulary sets.

## Touch points

- `cortex_command/common.py:181-190` (terminal set) and `:1234-1244` (alias map) — the two live declarations.
- `cortex_command/overnight/backlog.py:38-44` — three constants with no readers, under a comment claiming they are for validation.
- `cortex_command/backlog/update_item.py:299`, `:333` (raw reads) and `:469-477` (the cascade that forbids bulk use of the verb).
- `docs/backlog.md:23` — points at the dead constants as the canonical list.
- Direct-rewrite precedent: `cortex_command/init/_relocation_migration.py:45`.
