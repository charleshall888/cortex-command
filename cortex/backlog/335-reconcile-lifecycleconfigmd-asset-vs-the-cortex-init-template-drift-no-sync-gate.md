---
schema_version: "1"
uuid: 35493faf-613f-425a-b469-016e78397922
title: Reconcile lifecycle.config.md asset vs the cortex-init template (drift, no sync gate)
status: backlog
priority: medium
type: bug
created: 2026-06-25
updated: 2026-06-25
---
## Why

`skills/lifecycle/assets/lifecycle.config.md` has **0 `backlog:` blocks**, while the real scaffold source `cortex init` uses (`cortex_command/init/templates/cortex/lifecycle.config.md`) carries the full #317 backend block. Two sources of truth, no sync gate — and docs point users at the stale asset as canonical. A user copying the asset gets a config missing the backend section. Surfaced in the 2026-06-25 lifecycle reference-file audit (correctness, not a trim).

## Role

Reconcile the asset to the init template (add the backlog backend block), OR collapse to a single source — make the asset a thin pointer to the init template, or generate one from the other — and add a **drift-gate test** so they can't silently diverge again (the repo already uses dual-source drift gates for skills/bin mirrors).

## Integration

Edits `skills/lifecycle/assets/lifecycle.config.md` (+ mirror) and/or `cortex_command/init/templates/cortex/lifecycle.config.md` + a new parity test → lifecycle-gated. Confirm which file the docs reference as canonical and point them at the chosen source.

## Edges

- The init template may carry init-time placeholders the static asset shouldn't — reconcile content semantics, not just bytes.
- A drift-gate must tolerate intended differences (placeholders) while catching the backend-block divergence.

## Touch-points

- `skills/lifecycle/assets/lifecycle.config.md` (+ mirror)
- `cortex_command/init/templates/cortex/lifecycle.config.md`
- new drift / parity test
- docs pointer to the canonical config source