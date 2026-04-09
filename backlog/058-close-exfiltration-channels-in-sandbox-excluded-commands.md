---
schema_version: "1"
uuid: e7b5a2c6-1f8b-4c3e-d0a5-b6c7d8e9f0a1
title: "Close exfiltration channels in sandbox-excluded commands"
status: complete
priority: high
type: task
tags: [permissions-audit, security]
created: 2026-04-09
updated: 2026-04-09
parent: 054
discovery_source: research/permissions-audit/research.md
session_id: null
lifecycle_phase: review
lifecycle_slug: close-exfiltration-channels-in-sandbox-excluded-commands
complexity: complex
criticality: high
spec: lifecycle/close-exfiltration-channels-in-sandbox-excluded-commands/spec.md
areas: [skills]
---

# Close exfiltration channels in sandbox-excluded commands

## Context from discovery

DR-8 identifies that `git:*`, `gh:*`, and `WebFetch` are all sandbox-excluded AND in the allow list, creating exfiltration channels with only one security layer (permissions). Unlike the escape hatch concern, these channels are confirmed — `excludedCommands` definitively bypasses sandbox enforcement.

## Changes to apply

**WebFetch — move from allow to prompt-based (Option A):**
- Remove `WebFetch` from the allow list (falls through to default prompt)
- Keep `WebFetch` in `excludedCommands` so sandbox doesn't block approved fetches
- Context7 and Perplexity MCP servers handle most research needs; direct WebFetch is rare

**GitHub CLI — narrow allow-list patterns:**
- Replace `Bash(gh *)` with safe read patterns:
  - `Bash(gh pr view *)`, `Bash(gh pr list *)`, `Bash(gh pr checks *)`
  - `Bash(gh pr create *)`, `Bash(gh pr merge *)`
  - `Bash(gh issue view *)`, `Bash(gh issue list *)`
  - `Bash(gh repo view *)`, `Bash(gh repo clone *)`
  - `Bash(gh api *)` — consider whether this should be allowed or prompted
- Add to deny list: `Bash(gh gist create *)`

**Git — add deny rules for exfiltration vectors:**
- Add to deny list: `Bash(git remote add *)` — prevents adding arbitrary remotes
- Consider: `Bash(git send-email *)`, `Bash(git archive *)` if not needed

## Acceptance criteria

- WebFetch removed from allow list; verified that Context7/Perplexity still work for research
- gh narrowed to specific subcommands; gh gist create denied
- git remote add denied
- No regression in interactive workflows (pr creation, issue viewing, etc.)
