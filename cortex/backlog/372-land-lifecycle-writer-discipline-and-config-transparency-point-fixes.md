---
schema_version: "1"
uuid: e50765ba-013e-4ba1-8c44-3d05bd592478
title: Land lifecycle writer-discipline and config-transparency point fixes
status: complete
priority: high
type: chore
created: 2026-07-10
updated: 2026-07-10
parent: "371"
tags: ['cli-served-lifecycle-state-machine']
discovery_source: cortex/research/cli-served-lifecycle-state-machine/research.md
lifecycle_phase: complete
---
## Why

The machine-independent hygiene the state-machine research surfaced falls into two symptom clusters. First, per-feature lifecycle events are written by three paths under different disciplines — one bypasses the locking writer entirely with a plain unlocked append while duplicating event shapes owned by the canonical emission table, another emits telemetry without the shared lock, and a terminal-status set has drifted from the shared constant so a wont-do item passes one filter and fails another; dead event names and a dormant pipeline state machine muddy audits. Second, several lifecycle config fields are documented in the scaffolded asset, set in live project configs, and parsed by nothing — the day any consumer starts honoring them, every repo that copied the asset gets a silent workflow change it never opted into, and the reader's silent-ignore posture toward unknown keys is exactly how the fields went dormant unnoticed.

## Role

After this lands, every per-feature events.log write goes through the single locking writer with registry-owned schemas, the terminal-status vocabulary has one source of truth, the dormant pipeline state machine is pruned or explicitly fenced as a separate aggregate, and there is an audited inventory of live-versus-dormant lifecycle config fields backed by a reader that warns loudly on dormant or unknown workflow-shaping keys instead of silently ignoring them. Together these form the writer-discipline and config-transparency floor that any future single-writer status projection or transition-parameter machine would stand on — and both are worth having if neither ever funds.

## Integration

Touches the review-dispatch verdict writes (the only pipeline module writing feature events), the interactive-lock telemetry emitter, the overnight session-plan Not-Ready filter, and the lifecycle-config readers with their per-field parser functions. Feeds two acceptance surfaces the phase-gate ticket carries: the writer census and the dormant-config activation guard. Respects the two-copy parity contract between the plugin asset and the init template.

## Edges

- Read-side behavior is unchanged — tolerant readers keep skipping unknown shapes; historical logs are never rewritten.
- No new event names and no new hand-written schema exceptions; the emission contract's exception class stays closed.
- Review-verdict semantics must not change — only the write channel moves.
- Config work is audit-and-warn only: no field semantics change, warnings not errors (fail-open), and no third hand-maintained copy of the config schema.

## Touch points

- `cortex_command/pipeline/review_dispatch.py:214-334` — feature events.log writes (phase_transition, review_verdict, feature_complete) via `pipeline/state.py:log_event`
- `cortex_command/pipeline/state.py:288-304` — the unlocked bare append those writes ride on
- `cortex_command/interactive_lock.py:221-231` — `_emit_event` bare `open("a")` append, no flock
- `cortex_command/overnight/plan.py:145-151` — `_TERMINAL` frozenset missing the wont-do variants; replace with shared import
- `cortex_command/common.py:175-176` — stale comment describing a divergence already fixed in overnight/backlog.py (deferred: common.py edits are lifecycle-gated; fold into the next gated common.py change)
- `cortex_command/overnight/events.py:85-86` — vestigial `SYNTHESIZER_VALIDATED_{INTERACTIVE,OVERNIGHT}` constants with no emitters
- `cortex_command/pipeline/state.py:20-28` + `cortex/lifecycle/pipeline-state.json` — dormant pipeline FSM; prune under workflow trimming or fence by name
- `cortex_command/lifecycle_config.py` — field parsers accreted one per ticket
- `cortex_command/overnight/cli_handler.py:73` — separate inline parser for synthesizer_overnight_enabled
- `skills/lifecycle/assets/lifecycle.config.md:10-13` — skip-specify, skip-review, default-tier, default-criticality: documented, never parsed
- `cortex/lifecycle.config.md:4-5` — dormant fields set in this repo's live config
- `cortex/research/archive/user-configurable-setup/research.md:112-113` — prior confirmation the fields are unimplemented