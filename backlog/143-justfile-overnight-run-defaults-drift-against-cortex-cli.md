---
schema_version: "1"
uuid: 4a15e6ec-937e-4867-9625-c60225a0619e
title: "Justfile overnight-run defaults drift against cortex CLI"
status: backlog
priority: low
type: feature
tags: [overnight-runner, dx]
created: 2026-04-24
updated: 2026-04-24
blocks: []
blocked-by: []
---

# Justfile overnight-run defaults drift against cortex CLI

## Context

Surfaced during lifecycle 115 Task 15 (replace shim call sites with `cortex overnight`). The mandate for Task 15 was scope-limited to replacing shim call sites, so this drift is filed as a separate DX ticket rather than expanded into 115's scope.

## Problem

The `overnight-run` recipe in `justfile` still passes defaults that no longer match the cortex CLI contract:

- `tier="max_100"` — the cortex CLI accepts `simple` or `complex`, not `max_100`. `just overnight-run` fails or requires a manual `tier=...` override.
- `time-limit="6"` — historically the shim interpreted this as hours. The cortex CLI's `--time-limit` expects seconds (or needs an explicit unit). The default is off by 3600×.

Invoking `just overnight-run` with no overrides no longer works end-to-end.

## Scope

- Update the `overnight-run` recipe defaults (and `overnight-schedule` if it has matching drift) to pass valid cortex CLI values.
- Pick a unit convention for `time-limit` that matches the CLI and document it in the recipe comment header.
- Update the recipe usage comment (`Usage: just overnight-run ...`) to match the new defaults.

## Out of scope

- Changing the cortex CLI flag surface itself.
- Any other justfile recipes not touched by lifecycle 115.

## References

- `justfile` — `overnight-run` and `overnight-schedule` recipes
- Lifecycle 115 Task 15 follow-up finding
