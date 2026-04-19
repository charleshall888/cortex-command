---
schema_version: "1"
uuid: abd4c43c-02dc-4f12-86e5-dc80b56cf02e
title: "Harden cortex-notify-remote.sh curl invocation against exfiltration"
status: abandoned
priority: medium
type: task
tags: [permissions-audit, security, hooks, notifications]
created: 2026-04-10
updated: 2026-04-17
parent: null
discovery_source: "Spec #060 Non-Requirements — notify-hook curl channel flagged for follow-up"
---

# Harden cortex-notify-remote.sh curl invocation against exfiltration

## Context

`hooks/cortex-notify-remote.sh:56` invokes:

```bash
curl -s --max-time 5 -d "$MESSAGE" -H "Title: $TITLE" "https://ntfy.sh/$NTFY_TOPIC"
```

This runs on every `permission_prompt`, `complete`, and similar session-level events via the hooks wiring in `claude/settings.json`. Hooks execute under the shell directly — Claude Code's permission matcher does NOT gate hook commands. Therefore:

1. `Bash(curl *)` being in the allow list (or in ask after #060) is IRRELEVANT to this invocation. The matcher is not consulted.
2. `$MESSAGE` and `$TITLE` are derived from session-level event data. For `permission_prompt` events, these contain the prompt text — which may include strings derived from the model's session context. A compromised session could influence these strings and potentially exfiltrate session data (or command output) through the notification body/title fields.
3. `ntfy.sh` is an open public notification service; messages sent there can be received by anyone with the topic.

This is not a hypothetical — it's an open curl channel that the permission-tightening in #060 does NOT cover.

## Proposed mitigations

Pick one or more:

1. **Argument quoting audit + length limits**: ensure `$MESSAGE` and `$TITLE` are quoted correctly (they are), AND enforce a hard length limit (e.g., 200 chars for title, 500 for body) via `"${MESSAGE:0:500}"` parameter substitution. Prevents large command output from being exfiltrated in a single notification.
2. **Content allowlisting**: instead of passing session data to curl, construct notification bodies from a fixed template (e.g., "Claude session needs permission approval" with no dynamic content). Loses notification richness but eliminates the exfiltration channel entirely.
3. **Switch notification transport**: replace ntfy.sh with a first-party system that requires authentication (e.g., Pushover with API key, or a private webhook). Prevents eavesdropping on notifications even if the content is exfiltrated.
4. **Hook-side validation**: filter `$MESSAGE` through a regex or sanitizer before passing to curl. Strips anything that looks like base64, URLs, or secret-shaped tokens.

## Acceptance criteria

- `hooks/cortex-notify-remote.sh` implements one of the proposed mitigations (spec phase of this ticket chooses).
- The notification path no longer passes session-derived data directly to curl without length/content constraints.
- Existing notification behavior (prompt → phone alert) still works for the sanitized content.
- Documented in the hook file header what the mitigation is and why.

## Out of scope

- Hardening other hook files in `hooks/` — each hook is a separate audit; this ticket is scoped to `cortex-notify-remote.sh` specifically.
- Replacing the hook system itself.
- Sandbox-layer enforcement on hooks (hooks are intentionally outside the permission matcher per Claude Code design).

## Context from #060 spec

Flagged during critical review of #060 spec. Quoted from #060 spec Non-Requirements:

> `hooks/cortex-notify-remote.sh` curl channel: Line 56 invokes `curl -s --max-time 5 -d "$MESSAGE" -H "Title: $TITLE" "https://ntfy.sh/$NTFY_TOPIC"`. Hooks execute under the shell directly — Claude Code's permission matcher does NOT gate hook commands. R1 does NOT close this channel, even though `$MESSAGE` and `$TITLE` are derived from session-level event data that may be influenced by an adversarial session.

See `lifecycle/permissions-audit-round-2-cfa-android-learnings/spec.md` for the full discussion.
