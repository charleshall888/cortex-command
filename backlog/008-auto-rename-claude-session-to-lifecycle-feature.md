---
id: 008
title: "Auto-rename Claude Code session to active lifecycle feature name"
type: feature
status: blocked
priority: medium
tags: [lifecycle, session-naming, observability]
blocked-by: [anthropics/claude-code#34243]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/session-window-naming/research.md
---

# Auto-rename Claude Code session to active lifecycle feature name

## Goal

When a lifecycle feature is active, the Claude Code session should automatically be named to match (e.g., `fix-permission-system-bugs` or `docs-audit`). This makes sessions identifiable in the `/resume` screen and session list without manual intervention.

## Blocked On

**anthropics/claude-code#34243** — Programmatic session rename from hooks/CLI subcommand. No ship date as of April 2026. The `/rename` built-in command exists interactively but cannot be invoked via the Bash tool, from a hook, or from a skill.

## Intended Implementation (when unblocked)

The `SessionStart` hook (`hooks/scan-lifecycle.sh`) already detects the active lifecycle feature and phase. When the CLI subcommand ships (e.g., `claude session rename <id> <name>`), add a call in the hook after feature detection:

```bash
claude session rename "$SESSION_ID" "$FEATURE_NAME"
```

The `session_id` is already available in the hook's JSON input. The feature name is already derived from `lifecycle/{feature}/.session` matching.

## Scope

- Applies to interactive sessions only at first (overnight sessions have no interactive terminal — may need separate handling)
- Rename should happen at SessionStart, not on lifecycle phase transitions
- No user prompt or confirmation needed — the feature name is the right name for the session
