# Specification: Fix Permission System Bugs

## Problem Statement

Two hooks in the permission system have been silently broken since they were created. `permission-audit-log.sh` checks the wrong JSON field for the event type and exits early on every invocation, producing 0-byte log files for every session — all 51 existing audit log files are empty. `sync-permissions.py` writes `settings.local.json` even when the merged result is identical to what is already on disk, triggering a full Claude Code settings reload that briefly clears all permission rules to zero and is implicated in transient permission prompts at session start. Fixing Bug 1 restores the observability that was intended from day one. Fixing Bug 2 eliminates unnecessary reload cycles that contribute to the transient prompt behavior.

## Requirements

All requirements are **must-have**. This is a targeted bug fix with no optional enhancements — every item below is necessary for the fix to work correctly.

1. **`permission-audit-log.sh` logs correct event data**: When a `permission_prompt` Notification hook fires, the hook appends a line to the session log containing an ISO 8601 timestamp and the permission request message. Acceptance: after the fix, triggering a permission prompt in any session produces a non-empty log file entry.

2. **Event type check uses the correct field**: The hook evaluates `notification_type` (not `hook_event_name`) to determine the event type. `hook_event_name` is always `"Notification"` and is not the discriminator. Acceptance: the early-exit condition no longer fires for valid `permission_prompt` notifications.

3. **Logged fields match the Notification payload**: The hook extracts `message` and `title` from the payload (these exist in Notification payloads). It does not reference `tool_name` or `tool_input.command` (these are PreToolUse fields, not present in Notification payloads). The new log format is: `{ISO8601} REQUESTED type={notification_type} title={title} message={truncated_message}` where `message` is truncated to 200 characters (same limit as the existing `tool_input` truncation). Acceptance: log lines contain the permission request message rather than empty/null fields.

4. **`permission-audit-log.sh` handles absent fields gracefully**: If `notification_type`, `message`, or `title` are absent from the payload, the hook falls back to `"unknown"` rather than exiting without logging. Acceptance: hook writes a log entry even with a minimal/incomplete payload.

5. **`sync-permissions.py` skips writes when merged output is identical to current file**: Before writing the merged settings, the script serializes the new content and compares it byte-for-byte to the current file. If identical, the write is skipped. Acceptance: when the global `settings.json` changes in a way that doesn't affect any rules (e.g., adding a non-permissions key), no file write occurs and no Claude Code reload is triggered.

6. **Hash marker updated without file write when content is identical**: When the merged content is identical but the stored `_globalPermissionsHash` differs, the script still skips the write entirely (no partial update). The hash will update on the next genuine content change. Acceptance: the file modification timestamp does not change when a skip occurs. Note: this means sync-permissions.py will re-run the merge on every subsequent session start until a genuine content change occurs — this is an accepted trade-off. The merge is fast (< 100ms) and no reload is triggered, which is strictly better than writing the hash-only and triggering a reload.

7. **`docs/agentic-layer.md` updated to reflect correct Notification payload structure**: Line 273 currently documents `{"event": "permission_prompt", ...}` which is incorrect — the actual payload has `notification_type: "permission_prompt"` and `hook_event_name: "Notification"`. This was the original source of the misdiagnosis. Acceptance: `docs/agentic-layer.md` line 273 shows the correct payload fields so future hook authors use the right field names.

## Non-Requirements

- Not changing any permission rules in `settings.json` or `settings.local.json`
- Not removing `sync-permissions.py` — the bug #17017 workaround remains in place
- Not fixing Claude Code's internal clear/reload behavior on file change detection
- Not diagnosing the initial session load gap (0 hooks at startup) — that requires post-fix monitoring data from the now-working audit log
- Not migrating other hooks to the corrected Notification payload field names

## Edge Cases

- **Notification payload missing `notification_type`**: The event check becomes `[[ -n "" ]] → false`, so the hook does NOT exit early — it continues and logs what it can. This is correct: an absent `notification_type` means we can't confirm it's not a `permission_prompt`, so we log anyway.
- **`message` or `title` absent**: Fall back to `"unknown"` in the log line so the entry is still written.
- **Log file not writable**: Existing behavior: exit silently (non-blocking advisory). Keep this.
- **`settings.local.json` has stale/missing `_globalPermissionsHash`**: sync-permissions.py already handles this correctly via the hash mismatch path — the content comparison happens AFTER the merge, so it catches cases where the merge would produce no actual change.
- **JSON key ordering in content comparison**: Use the same `json.dumps(content, indent=2) + "\n"` serialization for both comparison and write to avoid false "different" results from key ordering differences.
- **`settings.local.json` does not exist**: sync-permissions.py already returns early in this case (line 66). No change needed.

## Technical Constraints

- `claude/hooks/permission-audit-log.sh` (symlinked to `~/.claude/hooks/permission-audit-log.sh`)
- `claude/hooks/sync-permissions.py` (symlinked to `~/.claude/hooks/sync-permissions.py`)
- Both files must remain executable after edit (`chmod +x` not needed — permissions preserved by editing in place)
- `settings.json` must remain valid JSON (no changes to it in this fix)
- The content comparison in sync-permissions.py must use the same serialization format as the write (`json.dumps(new_content, indent=2) + "\n"`) to ensure deterministic comparison

## Open Decisions

_(none — all decisions resolved at spec time)_
