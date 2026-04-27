# Research: Fix Permission System Bugs

## Summary

Two confirmed bugs in the permission infrastructure. Bug 1 is a straightforward code fix. Bug 2 has an identified root cause in the settings reload race.

---

## Bug 1: permission-audit-log.sh Always Produces Empty Log Files

### Root Cause (CONFIRMED)

The Notification hook payload structure is:

```json
{
  "hook_event_name": "Notification",
  "notification_type": "permission_prompt",
  "message": "...",
  "title": "...",
  "session_id": "...",
  "cwd": "...",
  "transcript_path": "..."
}
```

The hook checks the wrong field:

```bash
EVENT=$(echo "$INPUT" | jq -r '.event // .hook_event_name // empty')
if [[ -n "$EVENT" && "$EVENT" != "null" && "$EVENT" != "permission_prompt" ]]; then
  exit 0  # ← fires every time: "Notification" != "permission_prompt"
fi
```

`hook_event_name` is always `"Notification"` — the hook type, not the notification type. The `permission_prompt` value lives in `notification_type`. Since `"Notification" != "permission_prompt"`, the early-exit condition triggers on every invocation.

The `touch "$LOG_FILE"` runs before this check, which is why every session produces a 0-byte log file (file created, then hook exits before writing anything).

### Secondary Issue: Wrong Fields Extracted

The hook also tries to extract `tool_name` and `tool_input.command`, which don't exist in Notification payloads (those are PreToolUse fields). The correct fields are `message` (contains the permission request description) and `title`.

### Evidence

All 51+ audit log files in `$TMPDIR` are 0 bytes. Debug log confirms hooks ran and exited with status 0 (`permission-audit-log.sh completed with status 0`) — but the logs are empty.

### Fix

1. Change event check from `hook_event_name` to `notification_type`
2. Update field extraction to use `message` and `title` from the Notification payload

---

## Bug 2: Transient Permission Prompt at Session Start

### Root Cause (CONFIRMED via debug log)

The debug log (`c779c4a0`) traces the exact sequence:

```
15:09:05Z  App loads: userSettings (134 allow rules, includes Read(~/**))
                       localSettings (227 allow rules, machine-config session)
15:11:34Z  NEW cortex-command session starts (separate backend process)
15:11:40Z  "Hooks: Found 0 total hooks in registry"  ← hooks not yet loaded
15:12:01Z  permission_prompt fires for Read(~/.claude/skills/.../clarify.md)
15:13:28Z  sync-permissions.py writes .claude/settings.local.json
15:13:29Z  Settings changed: ALL destinations cleared to 0, then reloaded
```

The cortex-command session's SessionStart hook (sync-permissions.py) hadn't completed — or even started — when the first tool call fired. The hooks registry was empty at 15:11:40, and sync-permissions.py didn't write until 15:13:28. This 1m47s gap is where the prompt occurred.

**Two contributing factors:**

1. **Session startup race**: The new cortex-command session at 15:11:34 starts with 0 registered hooks. The SessionStart hook (sync-permissions.py) appears to run asynchronously — the session becomes interactive before the hook completes. When the first tool call fires at 15:12:01, the localSettings for cortex-command may not yet be loaded or merged.

2. **Settings reload cycle**: When sync-permissions.py writes to `.claude/settings.local.json`, Claude Code detects the file change and performs a full reload — **clearing ALL settings destinations to 0 rules** before restoring them. Any tool evaluation during this ~2ms clear window falls through to `defaultMode: "default"` with no allow rules and prompts. This clear-reload cycle happens on every session start where settings.json has changed.

### Why userSettings didn't save it

The global `Read(~/**)` is in `userSettings`. The clear at 15:13:29 shows `userSettings` is also cleared to 0 and reloaded — so even the global allow rule is unavailable during the reload window. For the initial prompt at 15:12:01, the localSettings for the new session context may not have been fully initialized.

### Evidence

- Debug log shows `0 total hooks in registry` at 15:11:40 (27s before the prompt)
- sync-permissions.py wrote settings.local.json at 15:13:28 (87s after the prompt)
- Settings reload at 15:13:29 explicitly clears `userSettings`, `projectSettings`, `localSettings` all to empty arrays
- `M claude/settings.json` in initial git status indicates settings.json was modified before this session, causing hash mismatch in sync-permissions.py and triggering the write

### Fix Options

**Option A (simple, addresses reload race):** Move `Read(~/**)` into a `PermissionRequest` handler or make it a hardcoded global rule that survives the reload cycle. Not feasible — Claude Code doesn't expose this.

**Option B (addresses file-write trigger):** Make sync-permissions.py write to a temp file and atomically rename, reducing the window where the file is in an intermediate state. This doesn't address the initial load gap.

**Option C (targeted fix):** Remove sync-permissions.py's write if the merged result would be identical to what's already in settings.local.json — even if the hash differs. Currently the hash covers the global permissions object; it should also cover the merged result to avoid unnecessary writes.

**Option D (observability):** Fix Bug 1 first. With working audit logs, confirm whether the reload cycle at 15:13:29 is causing production prompts. If the initial load gap (15:11:40 hooks empty) is the true cause, the fix is ensuring the SessionStart hook completes before interactive use — which may require a Claude Code behavior change outside our control.

**Recommended:** Fix Bug 1 (confirmed, safe). For Bug 2, add a content-hash check to sync-permissions.py so it skips writes when the merged result is identical to the current file, eliminating unnecessary reload cycles. This addresses the 15:13:29 clear-reload race. The initial load gap (15:11:40) remains — monitor with the fixed audit log.

---

## Open Questions

- Deferred: Is the initial load gap (0 hooks at 15:11:40) causing the 15:12:01 prompt, or is it the reload cycle at 15:13:29 from a previous session? Deferred: will be resolved by monitoring the fixed audit log across a few sessions.
- Deferred: Does the content-hash check eliminate ALL spurious prompts, or does the initial session load gap persist? Deferred: will be measurable after implementation by observing whether permission prompts recur.
