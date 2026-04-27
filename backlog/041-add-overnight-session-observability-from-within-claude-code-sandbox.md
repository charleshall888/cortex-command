---
schema_version: "1"
uuid: d26a53bb-6dc0-4fb3-aad9-da6b153ba149
title: "Add overnight session observability from within Claude Code sandbox"
status: complete
priority: medium
type: chore
tags: [overnight, observability, sandbox]
areas: [overnight-runner,observability]
blocked-by: []
created: 2026-04-08
updated: 2026-04-08
session_id: null
lifecycle_phase: implement
lifecycle_slug: add-overnight-session-observability-from-within-claude-code-sandbox
complexity: complex
criticality: high
spec: lifecycle/archive/add-overnight-session-observability-from-within-claude-code-sandbox/spec.md
---

When checking overnight session status from a sandboxed Claude Code session, the only visibility is reading state files and event logs. The sandbox blocks tmux socket access (`/private/tmp/tmux-503/default` — "Operation not permitted"), so `tmux has-session`, `tmux list-sessions`, and `tmux attach` are all unavailable. This makes it impossible to check if the runner is alive, view its output, or diagnose crashes without leaving the Claude Code session.

**Investigate:**
- Add tmux unix socket to sandbox allowlist (`~/.claude/settings.json` or `settings.local.json`)
- Whether a `/overnight status` subcommand could provide a one-shot status view by reading state + events + checking the runner PID from .runner.lock — no tmux needed
- Whether the dashboard (when running) already provides sufficient visibility and just needs to be easier to check from within a session
