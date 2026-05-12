---
schema_version: "1"
uuid: 8c6f0f95-2773-4e8a-adb3-4efff532a56b
title: "Document overnight pipeline operations and architecture"
status: complete
priority: medium
type: task
created: 2026-04-13
updated: 2026-04-13
tags: [overnight-runner, docs, observability]
areas: [docs]
session_id: null
lifecycle_phase: complete
lifecycle_slug: document-overnight-pipeline-operations-and-architecture
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/document-overnight-pipeline-operations-and-architecture/spec.md
---

A docs audit surfaced 13 gaps in overnight pipeline documentation. A
contributor (or future-me debugging at 2am) cannot understand how
overnight actually works without code-diving through `batch_runner.py`,
`review_dispatch.py`, `merge.py`, and the orchestrator prompt.

The gaps cluster into three layers:

## Architectural mechanics not documented

- Post-merge review architecture (`review_dispatch.py`): how the
  feature-level review agent is dispatched, how verdicts gate the
  workflow, how the rework cycle (CHANGES_REQUESTED → fix agent →
  re-merge → cycle 2) works
- Per-task agent capability constraints: agents have no `Agent` tool,
  no `AskUserQuestion`, no Task tools. Only conveyed by absence in
  prompt templates and `dispatch.py`'s `allowed_tools` list
- Split between `cortex_command/pipeline/` and `cortex_command/overnight/` — two
  `prompts/` directories with no doc explaining which does what
- Escalation system (`lifecycle/escalations.jsonl`): the channel
  pipeline workers use to raise design questions for orchestrator
  resolution. Implemented but not user-documented
- Strategy file (`overnight-strategy.json`): tracks `hot_files`,
  `integration_health`, round history. Not mentioned anywhere in docs
- Conflict recovery policy (orchestrator-round.md §1b): two-level flow
  (trivial fast-path → repair agent), only documented inside an
  orchestrator prompt

## Operational mechanics affecting debugging

- Escalation cycle-breaking when workers ask the same question twice
- Test gate + integration health degradation flow
- `--tier` parameter for concurrency tuning (max_5, max_100, max_200)
- Repair agent SKIP/DEFER/PAUSE decision logic in `brain.py`

## Configuration and integration points

- `lifecycle.config.md` field defaults and absence behavior beyond
  what's already in `docs/overnight.md`
- Environment variable fallback order (apiKeyHelper → env →
  OAuth token → Keychain) — currently only discoverable by reading
  `runner.sh`
- `orchestrator_io` module: sanctioned API for orchestrator-prompt
  code (load_state, save_state, update_feature_status, write_escalation)

## Deliverable

Add `docs/overnight-operations.md` covering:

1. **Architecture** — orchestrator round loop, per-task dispatch model,
   post-merge review and rework, escalation system, strategy file,
   conflict recovery policy
2. **Tuning** — tier selection, test-command behavior, concurrency,
   model selection matrix
3. **Observability** — state file locations, escalations.jsonl,
   strategy.json, morning report interpretation, where logs go,
   how to debug a stuck/failed feature

`docs/overnight.md` becomes the user-facing "how to use" doc; the new
file becomes the "how it actually works + how to debug it" doc. Add a
cross-link from `docs/overnight.md`.
