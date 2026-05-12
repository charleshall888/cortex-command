---
schema_version: "1"
uuid: 38c23f6f-3126-484a-9143-4ca176f801b7
title: "Add runtime adoption telemetry via per-script invocation shim (DR-7)"
status: complete
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, discoverability, observability]
created: 2026-04-21
updated: 2026-04-28
discovery_source: cortex/research/extract-scripts-from-agent-tool-sequences/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/spec.md
areas: []
---

# Add runtime adoption telemetry via per-script invocation shim (DR-7)

## Context from discovery

Static parity lint (ticket 102) catches "SKILL.md doesn't reference the script." It cannot catch the third failure mode: SKILL.md references the script and the agent still chooses Read+Grep or another tool at runtime. Interactive sessions have no tool-call log today, so this mode is undetectable without new instrumentation.

The original 2026-04-21 mechanism — a PreToolUse hook inspecting tool-call command strings via a Bash matcher — was rejected during the lifecycle research phase (Adversarial F7, sandbox-incompatibility) in favor of a per-script invocation shim. The shim ships inside each `bin/cortex-*` script as a one-line invocation of a fail-open helper, side-stepping the hook-payload sandbox issues entirely.

## Research context

- DR-7 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Lifecycle research: `lifecycle/archive/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/research.md` (M2 sandbox-friendly write target, Alt 5 + DR-5 composition).
- Script inventory extracted from `bin/cortex-*` glob (matches `just build-plugin`'s plugin distribution set).
- Weekly or on-demand aggregator reports per-script invocation count. Wired-but-never-invoked script = DR-7-detectable failure.

## Scope

- New `bin/cortex-log-invocation` invocation shim helper (bash, fail-open, ≤4KB JSONL records).
- New `bin/cortex-invocation-report` aggregator CLI with four flags: default (human-readable report), `--json`, `--check-shims`, `--self-test`.
- Per-script shim insertion across all 11 `bin/cortex-*` inventory items (5 bash, 4 plain Python, 2 PEP 723 uv-script).
- Pre-commit gate (`.githooks/pre-commit` Phase 1.5) that fires `--check-shims` on staged `bin/cortex-*` paths.
- Sixth observability subsystem section in `requirements/observability.md` documenting the shim + aggregator subsystem.

## Out of scope

- Agent-intent classification (Read+Grep substitution detection — Alt 3, rejected).
- Pipeline `agent-activity.jsonl` / `pipeline-events.log` integration (separate observability channel).
- Non-`bin/cortex-*` Bash invocation tracking.
- Log rotation policy (≈70 KB/day max across retained sessions; deferrable for years).
- Historical backfill from existing Claude Code session JSONL.

> **2026-04-28 — alternative-mechanism pivot.** During lifecycle research, the originally-proposed PreToolUse hook approach (Bash command-string matching) was eliminated by Adversarial F7: hooks fire in the host shell where Claude Code's sandbox excludes write paths the hook would need to log into, breaking fail-open semantics. Alt 5 (per-script invocation shim) composes cleanly with DR-5 (static parity lint, ticket 102) — the shim provides runtime adoption telemetry that DR-5 cannot reach, and DR-5 catches missing wiring that the shim cannot infer. The pivot keeps the ticket's intent (detect runtime non-adoption of agent-facing scripts) but replaces the mechanism end-to-end. The original hook-host references to `claude/settings.json:252-267` and `plugins/cortex-interactive/hooks/hooks.json` are no longer relevant; the new mechanism touches `bin/cortex-*`, the existing dual-source plugin distribution, `.githooks/pre-commit`, and `requirements/observability.md`.
