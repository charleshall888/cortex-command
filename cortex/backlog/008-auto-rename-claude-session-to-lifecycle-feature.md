---
id: 008
title: "Auto-rename Claude Code session to active lifecycle feature name"
type: feature
status: complete
priority: medium
tags: [lifecycle, session-naming, observability]
blocked-by: []
created: 2026-04-03
updated: 2026-07-17
discovery_source: cortex/research/session-window-naming/research.md
---

> **SHIPPED (2026-07-17).** Unblocked not by the upstream issue (anthropics/claude-code#34243 is still open — no CLI rename subcommand exists) but by the SessionStart hook contract growing `hookSpecificOutput.sessionTitle`: same effect as interactive `/rename`, honored on startup/resume sources, ignored on clear/compact. `cortex hooks scan-lifecycle` now stamps the active feature slug as the session title in the same envelope that injects lifecycle context — set only when a single active feature resolves (`.session` match or single-candidate claim), never on the multi-incomplete prompt. Tests pin both the positive and the no-active-feature case. The "overnight sessions may need separate handling" question stays moot: if a headless session runs the SessionStart chain it gets the same title, which is harmless-to-useful.

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
