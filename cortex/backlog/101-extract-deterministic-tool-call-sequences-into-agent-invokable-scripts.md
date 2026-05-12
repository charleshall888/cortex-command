---
schema_version: "1"
uuid: df196f7b-b9c6-4206-bb04-0866cbe25643
title: "Extract deterministic tool-call sequences into agent-invokable scripts"
status: complete
priority: medium
type: epic
blocked-by: []
tags: [harness, scripts, discoverability]
created: 2026-04-21
updated: 2026-04-29
discovery_source: cortex/research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract deterministic tool-call sequences into agent-invokable scripts

Discovery research identified 15 candidates (C1–C15) where the agent runs sequences of deterministic tool calls that could collapse into single script invocations — saving tokens and latency, and reducing nondeterminism where logic has no model judgment between steps.

## Context from discovery

Three failure modes for adoption exist: day-one wiring failure (deployed without SKILL.md reference), drift (reference removed/replaced over time), and runtime non-invocation (SKILL.md references the script but the agent uses other tools at runtime). Round-2 root-cause analysis found 3 day-one failures and 2 hidden-behind-abstraction cases among 5 under-used scripts in `bin/`, plus one confirmed drift replacement (`skills/backlog/generate-index.sh`). Static lint (DR-5) covers day-one + drift; a PreToolUse runtime hook matcher (DR-7) is needed for runtime non-invocation.

Full research at `research/extract-scripts-from-agent-tool-sequences/research.md`.

## Child tickets

- 102 — Ship DR-5 SKILL.md-to-bin parity linter (includes retrofit of existing under-used scripts)
- 103 — Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7)
- 104 — Instrument skill-name on `dispatch_start` for per-skill pipeline aggregates
- 105 — Extract `/commit` preflight into `bin/commit-preflight` (C1)
- 106 — Extract morning-review deterministic sequences (C11–C15 bundle)
- 107 — Extract `/dev` epic-map parse into `bin/build-epic-map` (C4)
- 108 — Extract `/backlog pick` ready-set into `bin/backlog-ready` (C7)
- 109 — Extract `/refine` resolution into `bin/resolve-backlog-item` with bailout (C5)
- 110 — Unify lifecycle phase detection around `claude.common` with statusline exception (C2+C3)
- 111 — Extract overnight orchestrator-round state read into `bin/orchestrator-context` (C8)

## Suggested implementation order

1. **102 + 103 + 104** in parallel (S-effort, no predecessors; together cover all three adoption-failure modes + pipeline observability).
2. **105** — fastest visible win (`/commit` is hot path).
3. **106, 107, 108, 109** — S-wave interactive extractions.
4. **110** — L refactor depending on 102+103 for safety signals.
5. **111** — pipeline-side extraction, gated on 104 data review.

## Out of scope / deferred

- C6 (daytime polling) — blocked on ticket #94.
- C9 (plan-gen dispatch) — revisit after 104 pipeline data.
- C10 (merge-conflict repair) — judgment-interleaved, not a collapse candidate.
