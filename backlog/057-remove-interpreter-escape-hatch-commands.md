---
schema_version: "1"
uuid: d6a4f1b5-0e7a-4b2d-c9f4-a5b6c7d8e9f0
title: "Remove interpreter escape hatch commands"
status: backlog
priority: medium
type: task
tags: [permissions-audit, security]
created: 2026-04-09
updated: 2026-04-09
parent: 054
blocked-by: [055]
discovery_source: research/permissions-audit/research.md
---

# Remove interpreter escape hatch commands

## Context from discovery

DR-2 recommends removing `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`, `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)` from the allow list. These potentially allow arbitrary code execution that bypasses deny-list patterns. However, this bypass mechanism is unverified (ticket 055 must resolve first).

These changes only affect interactive sessions — the overnight runner bypasses permissions entirely via `--dangerously-skip-permissions`.

## Changes to apply (if spike confirms bypass)

**Remove from allow list:**
- `Bash(bash *)`, `Bash(sh *)`, `Bash(source *)`
- `Bash(python *)`, `Bash(python3 *)`, `Bash(node *)`

**Add replacement patterns:**
- `Bash(python3 -m claude.*)` — overnight/pipeline modules (convenience, not required for overnight)
- `Bash(python3 -m json.tool *)` — JSON formatting
- `Bash(uv run *)` — venv-managed execution
- `Bash(uv sync *)` — dependency installation

## If spike shows Claude Code already inspects interpreter arguments

Lower priority. May still remove for defense-in-depth, but urgency drops significantly. The no-usage-in-codebase argument alone may justify removal regardless.

## Acceptance criteria

- Spike 055 completed with definitive results
- If bypass confirmed: all 6 entries removed, replacements added
- If bypass not confirmed: decision documented, ticket closed or adjusted
- No regression in interactive workflows
