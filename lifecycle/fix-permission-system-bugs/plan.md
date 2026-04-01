# Plan: fix-permission-system-bugs

## Overview

Three targeted file edits: fix the event-type check and field extraction in `permission-audit-log.sh`, add a content-identity check to `sync-permissions.py` before writing, and correct the payload documentation in `agentic-layer.md`. All three changes are independent and can execute in any order.

## Tasks

### Task 1: Fix permission-audit-log.sh — event check, field extraction, and format
- **Files**: `claude/hooks/permission-audit-log.sh`
- **What**: Replace the broken event-type check (`hook_event_name`) with the correct field (`notification_type`), update field extraction from `tool_name`/`tool_input.command` to `message`/`title`, update the log format string, and update the header comment to document the new format.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Header comment (lines 7-12): Documents the current log format as `{ISO8601} REQUESTED tool={tool_name} input={truncated_input}`. Update to: `{ISO8601} REQUESTED type={notification_type} title={title} message={truncated_message}`.
  - Event check (lines 62-65): Currently extracts `.event // .hook_event_name // empty` and exits if value ≠ `"permission_prompt"`. Change to extract `.notification_type // empty`. Keep the same exit condition logic.
  - Field extraction (lines 68-79): Currently extracts `tool_name` (`.tool_name // "unknown"`) and `tool_input` (`.tool_input.command // (.tool_input | tostring) // ""`). Replace with `title` (`.title // "unknown"`) and `message` (`.message // ""`). Keep the 200-character truncation on `message` (same as existing `TRUNCATED_INPUT`).
  - Log write (lines 82-86): The existing two-branch structure (one branch when input is non-empty, one when empty) must be collapsed into a single unconditional `printf` that always emits all three fields: `REQUESTED type=%s title=%s message=%s`. Both `$TITLE` and `$TRUNCATED_MESSAGE` already use `"unknown"` fallbacks (per Req 4), so there is no case where message is absent — the conditional branch is dead code after the rename and produces an inconsistent format if kept.
  - Variable names: rename `TOOL_NAME` → `NOTIF_TYPE`, `TOOL_INPUT` → `MESSAGE`, `TRUNCATED_INPUT` → `TRUNCATED_MESSAGE` to match the new semantics.
  - Evidence for `notification_type`: All 51 existing audit log files are 0 bytes. The current code checks `.event // .hook_event_name // empty`. If `.event` were `"permission_prompt"`, the exit condition would never fire and logs would have content. The empty logs prove `.event` is not the discriminator. `notification_type` is confirmed in the official Claude Code hook documentation (Notification hook payload).
- **Verification**: Run `just test` to confirm existing tests pass. Then manually verify: open a new Claude Code session in this project, trigger a permission prompt (deny an auto-allowed tool once), check that `$TMPDIR/claude-permissions-{session_id}.log` is non-empty and contains a line matching the new format with `type=permission_prompt`.
- **Status**: [x] complete

### Task 2: Fix sync-permissions.py — add content-identity check before write
- **Files**: `claude/hooks/sync-permissions.py`
- **What**: Before the `local_path.write_text(...)` call at line 97, serialize the new content using `json.dumps(local_settings, indent=2) + "\n"` and compare it to `local_path.read_text()`. If they are identical, return early without writing.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Write path in `main()` (lines 95-97):
    ```
    local_settings["permissions"] = local_perms
    local_settings["_globalPermissionsHash"] = current_hash
    try:
        local_path.write_text(json.dumps(local_settings, indent=2) + "\n")
    ```
  - Insert the check between the in-memory update (line 96 `local_settings["_globalPermissionsHash"] = current_hash`) and the `write_text` call. The check serializes `new_content = json.dumps(local_settings, indent=2) + "\n"`, reads `current_content = local_path.read_text()`, and if `new_content == current_content`, returns immediately. If they differ, falls through to the existing write.
  - The `read_text()` call should be wrapped in the existing `except OSError` pattern to avoid crashing if the file becomes unreadable between the earlier existence check and the comparison.
  - Preserve the existing `except OSError` wrapping around `write_text`.
- **Verification**: Run `just test` to confirm existing tests pass. Manual verification: with no changes to `settings.json` permissions rules since last sync (hash mismatch but identical content), confirm `settings.local.json` modification timestamp does not update after starting a new session.
- **Status**: [x] complete

### Task 3: Update agentic-layer.md — correct Notification payload documentation
- **Files**: `docs/agentic-layer.md`
- **What**: Update line 273 from the incorrect `{"event": "permission_prompt", ...}` to the actual payload structure `{"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "...", "title": "..."}`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current line 273: `- **`Notification`** — `{"event": "permission_prompt", ...}`. Used by `permission-audit-log.sh` to log the prompt.`
  - Replace with: `- **`Notification`** — `{"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "...", "title": "..."}`. Used by `permission-audit-log.sh` to log the prompt. Note: `hook_event_name` is always `"Notification"` for all notification events; `notification_type` discriminates between event subtypes.`
- **Verification**: Visually confirm the updated line matches the payload structure confirmed in research. Run `just test` to ensure no test failures.
- **Status**: [x] complete

## Verification Strategy

After all three tasks complete:
1. Run `just test` — all existing tests must pass.
2. Start a fresh Claude Code session in this project and intentionally trigger a permission prompt (e.g., temporarily remove `Read(~/**)` from settings, trigger a read, then restore).
3. Confirm `$TMPDIR/claude-permissions-{session_id}.log` (in the real TMPDIR, not the sandbox `/tmp/claude`) contains at least one entry with the new format `REQUESTED type=permission_prompt title=... message=...`.
4. Confirm `settings.local.json` modification timestamp is unchanged after steps 1-3 (no unnecessary write from sync-permissions.py).
