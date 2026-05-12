---
schema_version: "1"
uuid: acb70ac0-3581-40bf-acb3-e09577f050b5
title: "Trim cortex-log-invocation shim cost (per-call ~21ms)"
status: complete
priority: medium
type: chore
created: 2026-05-11
updated: 2026-05-11
tags: [bin, performance, shim]
complexity: complex
criticality: high
spec: cortex/lifecycle/trim-cortex-log-invocation-shim-cost-per-call-21ms/spec.md
areas: []
session_id: null
---

# Trim cortex-log-invocation shim cost (per-call ~21ms)

## Problem

The `bin/cortex-log-invocation` shim adds ~21ms to every `bin/cortex-*` invocation per measurements taken during #190 Task 5. Concretely:

- `bin/cortex-lifecycle-state --field tier` against an 8.6 KB `events.log`: total ~30ms wall time.
- jq pipeline alone (without shim): ~9ms.
- Shim contribution: ~21ms (dominated by `git rev-parse --show-toplevel`, `mkdir -p`, and JSON-line write).

The #190 spec set a 15ms target for `cortex-lifecycle-state` per-call cost; the script's own work is well within budget, but the shim pushes total cost over.

## Why it matters

The dashboard hot path polls per-feature state every 2s; lifecycle skill prompts invoke these scripts on every phase entry; overnight runner dispatches them inside loops. ~21ms × N invocations per round × N rounds compounds.

## Constraints

- Shim must remain fail-open (current `trap 'exit 0' EXIT`).
- Shim must continue to record per-invocation JSONL records to `lifecycle/sessions/<LIFECYCLE_SESSION_ID>/bin-invocations.jsonl` so the existing observability surface (cortex-invocation-report) isn't broken.

## Hooks for research

- Cache `git rev-parse --show-toplevel` per-shell? Currently spawned per-invocation.
- Use `printf` directly instead of a `python3 -c` JSON emitter, if applicable.
- Defer the mkdir to first-write rather than every invocation.
- Profile each operation in the shim to identify the hottest segment.

## Source

Surfaced during #190 implementation. See `lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/spec.md` Post-Implementation Spec Corrections section.
