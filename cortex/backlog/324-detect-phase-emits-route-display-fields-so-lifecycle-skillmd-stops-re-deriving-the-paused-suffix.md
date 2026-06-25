---
schema_version: "1"
uuid: 87524876-635b-4681-9600-e94dd573086f
title: detect-phase emits route + display fields so lifecycle SKILL.md stops re-deriving the -paused suffix
status: complete
priority: low
type: chore
created: 2026-06-25
updated: 2026-06-25
---
## Why

`cortex-common detect-phase` already applies the `-paused` suffix (`common.py` `_result`), and `cortex_command.phase_labels.phase_label()` already computes the human display string (reused by the dashboard and the scan_lifecycle hook). But lifecycle `SKILL.md` §"Paused suffix" makes the agent re-derive both at runtime — strip `-paused` for routing-table lookup, reconstruct the display label — and additionally restates the marker's set/clear semantics, which are pure CLI internals the agent never acts on. Deterministic work narrated for the model, surfaced in the 2026-06-25 lifecycle skill-trimming audit.

## Role

Extend `detect-phase`'s JSON to emit two additive fields alongside the existing `phase`:

- `route` — base phase with the `-paused` marker (and any `:n/m` payload) stripped, for routing-table lookup.
- `display` — the human label via the existing `phase_label()`.

Then the SKILL.md routing step keys off `route`, shows `display`, and the entire "Paused suffix" paragraph plus the marker-semantics explanation is deleted. The model stops doing string surgery and stops learning CLI internals it doesn't act on.

## Integration

Edits `cortex_command/common.py` (`detect_lifecycle_phase` / `_result`) → lifecycle-gated. Reuse `phase_labels.phase_label` rather than forking label logic. `phase`/`checked`/`total`/`cycle` stay unchanged for back-compat; `route`/`display` are purely additive.

## Edges

- Terminal phases (`complete`, `escalated`) are never suffixed — `route` == `phase` there.
- `:n/m` task-progress payloads (`implement-paused:3/5`) must round-trip: `route` is the bare phase, `display` is the full label including ` — paused`.
- Confirm other `detect-phase` consumers (statusline, scan_lifecycle) ignore unknown fields, or migrate them too.

## Touch-points

- `cortex_command/common.py` (`_result` / `detect_lifecycle_phase`)
- `cortex_command/phase_labels.py` (reuse; possibly expose a base/`route` helper)
- `skills/lifecycle/SKILL.md` Step 2 routing + "Paused suffix" paragraph (+ mirror)
- test for the new output shape