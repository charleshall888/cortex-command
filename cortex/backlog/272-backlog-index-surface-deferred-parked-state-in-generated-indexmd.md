---
schema_version: "1"
uuid: 4ebe5d4c-49f3-4b48-860f-3f29ccfaa8fe
title: "Backlog index: surface deferred/parked state in generated index.md"
status: complete
priority: low
type: chore
created: 2026-05-28
updated: 2026-05-29
complexity: complex
criticality: medium
spec: cortex/lifecycle/backlog-index-surface-deferred-parked-state/spec.md
areas: ['backlog']
---
## Why

The generated backlog index (`cortex/backlog/index.md`, produced by
`cortex-generate-backlog-index` / `cortex_command/backlog/generate_index.py`)
renders `ID | Title | Status | Priority | Type | Blocked By | Parent | Spec`. It
does **not** render `tags`, and the backlog `status` enum has no `deferred` /
`parked` value (`backlog | refined | in_progress | implementing | review |
complete | abandoned`). An item that is deferred/parked in its body but left at
`status: backlog` is therefore indistinguishable from a genuinely-ready item —
both in the rendered table and in any "what's ready" scan that reads it.

Motivating case (from the downstream wild-light project): an item carrying a full
`## Deferred` body section ("refine deferred", with a concrete reactivation
trigger) plus a `deferred` tag, while its frontmatter stays `status: backlog,
priority: high`. In the index it reads as a ready high-priority feature — the
deferral is invisible without opening the file.

## Role

Make a deferred/parked item distinguishable as such in the generated `index.md`
without opening the item file, so backlog grooming and "what's ready" scans do
not surface parked work as actionable.

## Integration

`generate_index.py` is the source of truth for the rendered table and the
`## <status>` groupings. Whatever signal is chosen (status-cell annotation, a
tags column, or a first-class status) must round-trip through the generator's
status normalization / terminal-status handling and its `index.json` emission,
with no regression to existing columns or `index.json` consumers.

## Edges

- The status enum has no `deferred` value today — a first-class status (approach 3)
  touches the enum, `normalize_status`, and `TERMINAL_STATUSES` semantics (whether
  deferred counts as "active").
- The generator ignores `tags` entirely — a tags column (approach 2) is the
  lowest-semantics change but widens the table.
- "Deferred in body" vs "deferred tag": decide whether the signal keys off a
  frontmatter tag/field (cheap, explicit) or a body-section marker (implicit,
  brittle).
- `index.json` consumers must not regress regardless of approach.

## Touch points

- `cortex_command/backlog/generate_index.py` — table column set, status grouping,
  any derived-signal logic.
- Status normalization / terminal-status handling (if approach 3).
- `index.json` emission path + any consumers.
- Tests covering index generation.

## Proposed approaches (pick during refine)

1. **Render a derived "Deferred" signal in the table** — detect a `deferred`
   frontmatter tag (or body marker) and surface it, e.g. `backlog (deferred)` in
   the Status cell or a dedicated column.
2. **Render a tags column** — lowest-semantics change; makes the existing
   `deferred` tag visible without interpreting state.
3. **Add a first-class `deferred` status** — largest change (enum +
   status-driven tooling + terminal-status handling); likely overkill.

## Acceptance criteria

- An item deferred in its body (deferred tag / body marker) is distinguishable as
  deferred in the rendered `index.md` without opening the item file.
- No regression to existing index columns or to `index.json` consumers.
- (If approach 3) the new status round-trips through `normalize_status` and is
  included in / excluded from `TERMINAL_STATUSES` per intended semantics.

## References

- Relocated from the downstream **wild-light** project, where it was originally
  filed as backlog #181 ("Backlog index: surface deferred/parked state in
  generated index.md (external cortex-command tooling)"). That ticket noted the
  generator is owned by cortex-command and is not implementable from within
  wild-light; the wild-light item has been deleted in favour of this one.