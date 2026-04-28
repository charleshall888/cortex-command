---
schema_version: "1"
uuid: 38c23f6f-3126-484a-9143-4ca176f801b7
title: "Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7)"
status: in_progress
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, discoverability, observability]
created: 2026-04-21
updated: 2026-04-28
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
session_id: b0ac6fb6-c263-4e72-9f6d-dba48e1a448e
lifecycle_phase: implement
lifecycle_slug: add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7
complexity: complex
criticality: high
spec: lifecycle/add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7/spec.md
areas: []
---

# Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7)

## Context from discovery

Static parity lint (ticket 102) catches "SKILL.md doesn't reference the script." It cannot catch the third failure mode: SKILL.md references the script and the agent still chooses Read+Grep or another tool at runtime. Interactive sessions have no tool-call log today, so this mode is undetectable without new instrumentation.

Infrastructure already exists: `claude/settings.json:252-267` wires PreToolUse Bash hooks receiving `{"tool_name": "Bash", "tool_input": {"command": "..."}}`. A third matcher grepping for known `bin/*` script names and appending to a rolling JSONL gives real interactive-session adoption telemetry at trivial cost.

## Research context

- DR-7 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Script inventory extracted from `just deploy-bin` parsing (share code with ticket 102).
- Weekly or on-demand aggregator reports per-script invocation count. Wired-but-never-invoked script = DR-7-detectable failure.

## Scope

- New PreToolUse Bash matcher hook referenced in `claude/settings.json`.
- Rolling JSONL log (e.g., `~/.claude/bin-invocations.jsonl`).
- Log rotation / size cap policy.
- Aggregator CLI (e.g., `bin/bin-invocation-report`) with weekly summary output.

## Out of scope

- Capturing non-Bash tool calls (Read, Grep, etc.).
- Integration with pipeline `agent-activity.jsonl` (separate observability channel for pipeline).

> **2026-04-27 (epic #113 complete) — scope amendment.** The hook-host file referenced in the original Scope is gone post-113.
>
> **Hook host (L22, L32):** `claude/settings.json:252-267` no longer exists. The new PreToolUse Bash matcher hook ships as a new entry inside `plugins/cortex-interactive/hooks/hooks.json`, alongside the existing Bash matcher entry for `cortex-validate-commit.sh`. Both entries share the same matcher.
>
> **Script inventory source (L27):** "extracted from `just deploy-bin` parsing" replaced by: glob top-level `bin/cortex-*` (the same set `just build-plugin` ships into the interactive plugin per `justfile:447`).
>
> **Aggregator script (L35):** `bin/bin-invocation-report` → `bin/cortex-invocation-report` so the `cortex-*` filter picks it up for plugin distribution.
>
> **Log location:** the originally-proposed `~/.claude/bin-invocations.jsonl` still works as a user-scoped path (it's a runtime write target, not a deploy target — no symlink involved).
