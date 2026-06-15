---
schema_version: "1"
uuid: 42f6d9e8-d4cb-45c9-b59e-96ca8095e7fa
title: Hyperlink the spec column in the generated backlog index
status: in_progress
priority: low
type: chore
created: 2026-06-14
updated: 2026-06-14
parent: "303"
tags: ['cortex-core-tooling-gaps']
discovery_source: cortex/research/cortex-core-tooling-gaps/research.md
complexity: simple
criticality: medium
spec: cortex/lifecycle/hyperlink-the-spec-column-in-the/spec.md
areas: ['backlog']
lifecycle_phase: plan
---
## Why

The generated backlog index shows a bare checkmark in the spec column to mark that an item has a spec, but the checkmark is not clickable even though the index already holds the spec's path. A reader who wants to open an item's spec from the index has to go find the file by hand, despite the destination being one render away.

## Role

Make the spec column a navigable link, so the index becomes a jumping-off point to each item's spec rather than a flat status marker. After it lands, an operator scanning the index can click straight through to a spec.

## Integration

It is a rendering change inside the backlog index generator, which already parses each item's spec path into the per-item record and already emits the index as deterministic, byte-stable markdown. The change reuses the existing spec value; it adds no new field and no new input. The generator's byte-stability discipline — atomic write, sorted input — must be preserved so the regenerate-and-diff staleness check stays clean.

## Edges

- Must not break byte-stability: the link rendering has to be deterministic so the committed index does not churn between regenerations.
- Scope is the spec column only. Adjacent index polish (a tags section, relocating the event log) is explicitly out of scope — it is not friction-evidenced.
- Renders a link only when a spec path is present; the empty-spec case keeps its existing dash marker.
- Does not collide with the deferred/parked status rendering, which lives in a different column.

## Touch points

- `cortex_command/backlog/generate_index.py:234` — the spec-column checkmark render to convert to a link
- `cortex_command/backlog/generate_index.py:200` — where the item's spec path is populated into the record
