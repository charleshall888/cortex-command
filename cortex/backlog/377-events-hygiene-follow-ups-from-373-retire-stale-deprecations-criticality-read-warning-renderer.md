---
schema_version: "1"
uuid: e7b601f2-d152-4d14-8c03-e8c500be7e93
title: 'Events hygiene follow-ups from #373: retire stale deprecations + criticality-read warning renderer'
status: complete
priority: medium
type: chore
created: 2026-07-10
updated: 2026-07-13
tags: ['events-registry', 'observability']
areas: ['overnight', 'lifecycle']
---
Two small hygiene follow-ups spun off from #373 (Phase B of epic 371). Both live in the events-registry / overnight-observability surface and are independently shippable, but bundled because they touch the same files and neither warrants its own epic.

## Why

- `bin/cortex-check-events-registry --audit` exits 1 on 12 pre-existing `STALE_DEPRECATION` rows whose grace windows lapsed before 2026-07-10 — every feature touching the registry (e.g. #373) inherits a red-gate caveat on its acceptance checks. The `--staged` pre-commit gate still passes, so this is friction, not a blocker.
- The #373 overnight criticality-read fallback (Task 13) surfaces its "corrupted / possibly-stale criticality" warning by reusing the `SYNTHESIZER_ERROR` event with `details.stage="criticality_read"`. It reaches `events.log` (and `report.collect`) but has no dedicated `report.py` renderer, so the warning is not distinctly visible in the morning report.

## Item A — Retire the 12 stale deprecated-pending-removal registry rows

The rows (deprecation_date 2026-06-10, owner charliemhall@gmail.com): `confidence_check`, `discovery_reference`, `implementation_dispatch`, `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`, `requirements_updated`, `task_complete`, `decompose_flag`, `decompose_ack`, `decompose_drop`; plus `seatbelt_probe` (2026-06-28). Per the checker, each needs either (a) completion of the cleanup — confirm no live producer/consumer remains, delete the emission/read code and the row; or (b) a deprecation_date bump with a rationale update. **Requires an owner triage pass** deciding per-row which events are truly dead vs. still needed. Acceptance: `bin/cortex-check-events-registry --audit` exits 0 (no STALE_DEPRECATION rows); no orphaned producer/consumer references to any removed event.

## Item B — Dedicated criticality-read warning event + renderer

Replace the `SYNTHESIZER_ERROR` reuse in `cortex_command/overnight/prompts/orchestrator-round.md` (Step 3b.1) with a purpose-named event (new constant in `cortex_command/overnight/events.py`, a registry row) and add a `report.py` renderer so the corrupted/stale-criticality warning surfaces as a distinct morning-report line. Additive-only (ADR-0020). Acceptance: a corrupted overnight criticality read emits the dedicated event; the morning report renders it under a clear heading; the prompt-render test asserts the new event name.

## Touch-points

- Item A: `bin/.events-registry.md`; per-event producer/consumer code under `cortex_command/overnight/`, `cortex_command/pipeline/` (grep each event name first).
- Item B: `cortex_command/overnight/prompts/orchestrator-round.md`, `cortex_command/overnight/events.py`, `cortex_command/overnight/report.py`, `bin/.events-registry.md`, `tests/test_orchestrator_prompt_render.py`.

## Edges

- Item A removals take a same-commit code+row deletion (no new deprecation window needed — the windows already lapsed); a row that turns out to still have a live consumer stays and gets a dated bump instead.
- Item B: keep the fallback behavior identical (single-agent, never defer) — this only changes the *surfacing* of the warning, not the routing.