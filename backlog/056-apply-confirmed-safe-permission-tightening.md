---
schema_version: "1"
uuid: c5f3e0a4-9d6f-4a1c-b8e3-f4a5b6c7d8e9
title: "Apply confirmed-safe permission tightening"
status: backlog
priority: high
type: task
tags: [permissions-audit, security, shareability]
created: 2026-04-09
updated: 2026-04-09
parent: 054
discovery_source: research/permissions-audit/research.md
---

# Apply confirmed-safe permission tightening

## Context from discovery

Consolidates all confirmed-safe changes to `claude/settings.json` that have no dependencies on the escape hatch spike. Each change has clear rationale from the research and critical review. Subsumes backlog 047.

## Changes to apply

**Remove from allow list** (DR-1, DR-3, unused entries):
- `Read(~/**)` — fragile allowlist-everything pattern; not needed for any workflow
- `Bash(* --version)` — leading wildcard matches any executable
- `Bash(* --help *)` — same issue
- `Bash(open -na *)` — macOS convenience, not required
- `Bash(pbcopy *)`, `Bash(pbcopy)` — macOS convenience, not required
- `Bash(env *)`, `Bash(env)` — debugging only
- `Bash(printenv *)`, `Bash(printenv)` — debugging only

**Move to ask** (DR-4):
- `Bash(git restore *)` — destructive (discards uncommitted changes, no reflog)

**Remove setting** (DR-5):
- `skipDangerousModePermissionPrompt: true` — contradicts defense-in-depth; power users add locally

**Add to deny list** (DR-6, subsumes backlog 047):
- `Read(~/.config/gh/hosts.yml)` — GitHub CLI auth token
- `Read(**/*.p12)` — certificate/key bundles
- `WebFetch(domain:0.0.0.0)` — loopback alias
- `Bash(crontab *)` — persistence mechanism
- `Bash(eval *)` — arbitrary command execution
- `Bash(xargs *rm*)` — deletion via xargs
- `Bash(find * -delete*)`, `Bash(find * -exec rm*)`, `Bash(find * -exec shred*)` — bulk deletion

**Move to settings.local.json** (DR-7):
- `mcp__perplexity__*`, `mcp__jetbrains__*`, `mcp__atlassian__*` — owner-specific MCP integrations

## Acceptance criteria

- All changes applied to `claude/settings.json`
- `just setup` still works (settings deploy correctly)
- No regression in interactive session workflows (git, lifecycle, backlog skills)
- Backlog 047 marked as subsumed/archived
