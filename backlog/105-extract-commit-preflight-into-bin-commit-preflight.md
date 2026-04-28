---
schema_version: "1"
uuid: 7670916c-a5ed-472d-8d8d-80dd9dc0f70c
title: "Extract /commit preflight into bin/commit-preflight"
status: backlog
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, commit]
created: 2026-04-21
updated: 2026-04-28
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
---

# Extract /commit preflight into bin/commit-preflight (C1)

## Context from discovery

`/commit` Step 1 currently runs `git status`, `git diff HEAD`, `git log --oneline -10` as three parallel Bash calls (`skills/commit/SKILL.md:12-14`). Collapsing to one script invocation saves ~1 agent turn per commit (3 parallel → 1 serial), removes the prompt-level three-step instruction, and makes the preflight shape verifiable and testable.

Steps 3–5 (stage / compose / commit) stay inline — Step 3 is judgment (which files are "relevant"), Step 4 reads the diff. The diff must be emitted in full by the script; any summary forces the agent to re-read.

## Research context

- C1 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Determinism: MECHANICAL-PARSE, judgment downstream.
- Heat: hot (every session with staged changes; ~30–60 commits/month per user).
- Savings quantified: ~1 turn + $0.01–0.02 per commit on Sonnet.

## Scope

- New `bin/cortex-commit-preflight` emitting `{status, diff, recent_log}`. Diff in full, not summarized.
- Top-level `bin/cortex-commit-preflight` is source-of-truth; `just build-plugin` syncs it into `plugins/cortex-interactive/bin/` (drift-checked by `.githooks/pre-commit`). The `cortex-` prefix is structural — `build-plugin` filters with `--include='cortex-*' --exclude='*'`.
- Update `skills/commit/SKILL.md` Step 1 to invoke the script directly; remove the three parallel Bash calls.
- Verify 102 (parity linter) passes post-change; verify 103 (runtime telemetry) records the invocation.

## Out of scope

- Changes to stage/compose/commit steps (they remain agent-driven).
