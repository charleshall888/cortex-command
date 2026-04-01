---
name: lesson
description: Capture a mid-session correction or lesson immediately. Use when user says "/lesson <text>", "add a lesson", "capture this lesson", "remember this for the retro", or provides inline text to record as a lesson learned. Writes to both MEMORY.md (for immediate durability) and the session scratch file (for retro inclusion).
disable-model-invocation: true
argument-hint: "<text>"
inputs:
  - "text: string (optional) — the lesson sentence to capture; prompted if not provided. Must be non-empty after trimming whitespace."
outputs:
  - "~/.claude/projects/<slug>/memory/MEMORY.md — auto-memory file (path derived at runtime from working directory)"
  - "retros/.session-lessons.md — session scratch file for retro inclusion"
preconditions:
  - "Auto-memory MEMORY.md path must exist and be writable (path derived at runtime from working directory)"
  - "Git repository must be accessible from current directory (fallback to cwd if unavailable)"
  - "Write permissions required on MEMORY.md and retros/ directory"
---

# Lesson

Lesson text: $ARGUMENTS (If $ARGUMENTS is empty, prompt the user for the lesson text before proceeding — do not write anything until non-empty text is provided.)

Capture `{{text}}` immediately to two places: MEMORY.md for durability and the session scratch file for retro inclusion.

## Steps

1. If no inline text was provided, ask for it before writing anything
2. Derive the MEMORY.md path: get the current working directory as an absolute path, replace every `/` with `-`, strip the leading `-` to produce the project slug. The memory file is `~/.claude/projects/<slug>/memory/MEMORY.md`. Append one concise sentence to that file under `## Recent Lessons` (create the section if absent — add it before the final newline)
3. Resolve the repo root: run `git rev-parse --git-common-dir` in the current directory. If the result is non-empty and does not start with `/`, prepend the current directory to make it absolute. Set `REPO_ROOT` to the `dirname` of that result. Fall back to the current directory if git is unavailable.
4. Create `$REPO_ROOT/retros/` if it does not exist
5. Append the same sentence to `$REPO_ROOT/retros/.session-lessons.md` (create the file if absent)
6. Confirm briefly: "Lesson captured."

## Append behavior

Both files use append-only writes — never overwrite existing content. Multiple `/lesson` calls in one session accumulate in both files.

For MEMORY.md: add a bullet under `## Recent Lessons`:
```
- <lesson sentence>
```

For `$REPO_ROOT/retros/.session-lessons.md`: add a plain line:
```
- <lesson sentence>
```

## Input Validation

1. **Text parameter**: If provided, must be a non-empty string after trimming whitespace. Reject empty or whitespace-only input with: "Lesson text cannot be empty. Please provide a non-empty lesson sentence."
2. **Encoding**: Text should be valid UTF-8. If non-UTF-8 is detected, reject with: "Lesson text contains invalid characters. Please use standard text encoding."
3. **Length**: Recommended max 500 characters; warn if longer with: "Warning: lesson exceeds recommended length (500 chars). Consider splitting into multiple lessons."

## Success Criteria

The skill succeeds when:
- ✓ Text is validated (non-empty, valid encoding)
- ✓ MEMORY.md is appended with the lesson as a new bullet under `## Recent Lessons` section
- ✓ Repo root is resolved via git or cwd fallback
- ✓ `$REPO_ROOT/retros/` directory exists (created if missing)
- ✓ `$REPO_ROOT/retros/.session-lessons.md` is appended with the lesson as a new line
- ✓ User receives confirmation message: "Lesson captured."
- ✓ Both files remain valid and readable after append

## Output Format Examples

### Example 1: Successful capture in standard project

**Input:**
```
/lesson Avoid using grep in loops; prefer Glob tool for file searches
```

**Output:**
```
MEMORY.md (appended under ## Recent Lessons):
- Avoid using grep in loops; prefer Glob tool for file searches

retros/.session-lessons.md (created if missing):
- Avoid using grep in loops; prefer Glob tool for file searches

User message:
Lesson captured.
```

### Example 2: Successful capture with prompt when text omitted

**Input:**
```
/lesson
```

**Prompt to user:**
```
Enter the lesson to capture:
```

**User responds:**
```
Use Task tool for multi-step research, not sequential Bash commands
```

**Output:**
```
MEMORY.md (appended):
- Use Task tool for multi-step research, not sequential Bash commands

retros/.session-lessons.md (appended):
- Use Task tool for multi-step research, not sequential Bash commands

User message:
Lesson captured.
```

### Example 3: Multiple lessons in one session accumulate

**After two /lesson calls:**

```
MEMORY.md (## Recent Lessons section):
- First lesson captured
- Second lesson captured

retros/.session-lessons.md:
- First lesson captured
- Second lesson captured
```

## Error Handling

### Error 1: Empty text provided
**Condition:** User provides `/lesson` with empty string or whitespace-only text
**Action:** Reject with: "Lesson text cannot be empty. Please provide a non-empty lesson sentence."
**Recovery:** Re-prompt for non-empty text
**Outcome:** No files modified

### Error 2: MEMORY.md not writable
**Condition:** Write to MEMORY.md fails (permission denied, disk full, path invalid)
**Action:** Log error: "Failed to write to MEMORY.md: [error details]"
**Recovery:** Attempt to write session-lessons.md anyway; if that succeeds, report partial success: "Lesson saved to session file but MEMORY.md write failed. Admin may need to check MEMORY.md path."
**Outcome:** Session file updated, MEMORY.md unchanged; user is notified

### Error 3: Git command fails
**Condition:** `git rev-parse --git-common-dir` fails (not a git repo, git not installed)
**Action:** Fall back to current working directory for REPO_ROOT
**Recovery:** Automatic fallback; no user action needed
**Outcome:** retros/ directory created relative to cwd; operation succeeds

### Error 4: retros/ directory cannot be created
**Condition:** Permission denied creating `$REPO_ROOT/retros/` directory
**Action:** Log error: "Failed to create retros/ directory: [error details]"
**Recovery:** Attempt to use existing directory or skip if missing; user sees: "Warning: Could not ensure retros/ directory exists. Lesson may not be available for retro."
**Outcome:** Partial success; MEMORY.md succeeds, session file may be skipped

### Error 5: Session lessons file not writable
**Condition:** Write to `.session-lessons.md` fails
**Action:** Log error: "Failed to write to session-lessons.md: [error details]"
**Recovery:** Report partial success: "Lesson saved to MEMORY.md but session file write failed."
**Outcome:** MEMORY.md updated, session file unchanged; user is notified of partial success

### Error 6: Text encoding invalid
**Condition:** Input text contains non-UTF-8 characters
**Action:** Reject with: "Lesson text contains invalid characters. Please use standard text encoding."
**Recovery:** Ask user to provide corrected text
**Outcome:** No files modified

### Error 7: Text exceeds length recommendation
**Condition:** Text length > 500 characters
**Action:** Proceed but warn: "Warning: lesson exceeds recommended length (500 chars). Consider splitting into multiple lessons."
**Recovery:** User may choose to split and re-call, or accept the long lesson
**Outcome:** Long lesson is written as provided
