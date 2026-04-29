---
schema_version: "1"
uuid: bf914d38-1079-454f-b3dc-3ce680e5a7b6
title: "Extract overnight orchestrator-round state read into bin/orchestrator-context"
status: complete
priority: medium
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, overnight, pipeline]
created: 2026-04-21
updated: 2026-04-29
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
complexity: complex
criticality: high
spec: lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/spec.md
areas: [overnight-runner]
session_id: null
lifecycle_phase: complete
---

# Extract overnight orchestrator-round state read into bin/orchestrator-context (C8)

## Context from discovery

The overnight orchestrator-round prompt (`cortex_command/overnight/prompts/orchestrator-round.md:22-176`) reads 6–8 files per round: `escalations.jsonl`, per-feature `spec.md` and `plan.md`, `overnight-state.json`, `overnight-strategy.json`, session plan markdown.

Round-2 quantification (the only data-rankable candidate): ~500–800 tokens of inline file reads per round, reducible to ~200 tokens via aggregated `bin/orchestrator-context` output. Savings: ~300–500 tokens + ~1 turn per round × 50–100 rounds/year.

Gated on ticket 104 (pipeline skill-name instrumentation) so the data-driven ROI claim can be confirmed post-ship, not just asserted.

## Research context

- C8 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Data-rankable — the only interactive/pipeline candidate with existing observability.
- Heat: warm (50–100 orchestrator rounds/year).

## Scope

- Extend `cortex_command/overnight/map_results.py` as a library with an aggregation function.
- New CLI `bin/orchestrator-context <state-path>` emitting merged-context JSON.
- Rewrite `cortex_command/overnight/prompts/orchestrator-round.md` to invoke the CLI in place of the inline file reads.
- Validate: mid-round resume behavior unchanged (no regression).
- Confirm ROI using 104's aggregator on at least one full overnight session before closing.

## Out of scope

- Plan-gen dispatch (C9) — separate candidate, revisit after post-ship data.
- Orchestrator prompt simplification beyond the state-read extraction.

> **2026-04-27 (epic #113 complete) — scope amendment.** A new distribution question opened up post-113 that has to be resolved at refine time.
>
> **Naming:** `bin/orchestrator-context` → `bin/cortex-orchestrator-context` if it ships through the plugin system (the `cortex-*` prefix is a structural filter in `just build-plugin`).
>
> **Distribution gap (new, no prior precedent):** the `cortex-overnight-integration` plugin's `build-plugin` arm (`justfile:430`) has `BIN=()` — empty. `bin/cortex-*` scripts are only included by `cortex-interactive`. But the orchestrator-round prompt is read by the overnight runner (the `cortex` CLI's `overnight` subcommand), not by interactive Claude Code. This means a user who installs *only* `cortex-overnight-integration` would not have `cortex-orchestrator-context` on PATH. Three options for `/refine` to choose between:
>
> 1. Ship the script as part of the `cortex` CLI itself (lives in `cortex_command/`, exposed as a subcommand or module entrypoint, not under `bin/`).
> 2. Add `BIN=(cortex-)` to the overnight plugin's recipe arm in `justfile:430` so plugin-bin distribution covers both plugins.
> 3. Declare `cortex-overnight-integration` as hard-requiring `cortex-interactive` and rely on the latter's bin/ being on PATH.
>
> Option 1 is most consistent with 113's "runner ships in the CLI" framing; Option 2 is the smallest mechanical change. Refine to decide.
>
> **Paths verified:** `cortex_command/overnight/prompts/orchestrator-round.md` and `cortex_command/overnight/map_results.py` (L20, L34, L36) still exist at the cited paths.
