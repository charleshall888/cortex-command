---
schema_version: "1"
uuid: bf914d38-1079-454f-b3dc-3ce680e5a7b6
title: "Extract overnight orchestrator-round state read into bin/orchestrator-context"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: ["104"]
tags: [harness, scripts, overnight, pipeline]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract overnight orchestrator-round state read into bin/orchestrator-context (C8)

## Context from discovery

The overnight orchestrator-round prompt (`claude/overnight/prompts/orchestrator-round.md:22-176`) reads 6–8 files per round: `escalations.jsonl`, per-feature `spec.md` and `plan.md`, `overnight-state.json`, `overnight-strategy.json`, session plan markdown.

Round-2 quantification (the only data-rankable candidate): ~500–800 tokens of inline file reads per round, reducible to ~200 tokens via aggregated `bin/orchestrator-context` output. Savings: ~300–500 tokens + ~1 turn per round × 50–100 rounds/year.

Gated on ticket 104 (pipeline skill-name instrumentation) so the data-driven ROI claim can be confirmed post-ship, not just asserted.

## Research context

- C8 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Data-rankable — the only interactive/pipeline candidate with existing observability.
- Heat: warm (50–100 orchestrator rounds/year).

## Scope

- Extend `claude/overnight/map_results.py` as a library with an aggregation function.
- New CLI `bin/orchestrator-context <state-path>` emitting merged-context JSON.
- Rewrite `claude/overnight/prompts/orchestrator-round.md` to invoke the CLI in place of the inline file reads.
- Validate: mid-round resume behavior unchanged (no regression).
- Confirm ROI using 104's aggregator on at least one full overnight session before closing.

## Out of scope

- Plan-gen dispatch (C9) — separate candidate, revisit after post-ship data.
- Orchestrator prompt simplification beyond the state-read extraction.
