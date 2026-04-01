---
name: tmux
description: Move the current Claude session into a tmux-backed terminal for persistence and mobile access. Use when user says "/tmux", "start a tmux session", "open in tmux", "persist this session", or wants tmux persistence.
disable-model-invocation: true
---

# tmux

Resume the current Claude conversation in a new Ghostty window running inside tmux.

## Invocation

- `/tmux` — auto-assign next available number
- `/tmux <name>` — use the given name

## Success Criteria

A successful `/tmux` invocation meets all of the following:

1. **Session created**: A new tmux session with the specified or auto-assigned name exists (`tmux list-sessions` includes it)
2. **Claude running**: Claude is actively resuming the conversation in the new window (user sees their prior context)
3. **Named correctly**: Session name matches user input or next available numeric ID (0, 1, 2…)
4. **Persistent**: User can detach (`C-b d`) and reattach (`mac <name>` or `tmux attach -t <name>`) without losing state
5. **Clean exit**: When Claude exits, the window and session close automatically (no zombie processes)

## Workflow

### 1. Get current Claude session ID

Find your own session ID from the most recently modified JSONL in the current project's session directory. Derive the project directory name from the working directory:

```bash
ls -t ~/.claude/projects/<project-dir-name>/*.jsonl
```

Where `<project-dir-name>` is the absolute working directory path with `/` replaced by `-` (e.g., `/Users/yourname/Workspaces/my-project` becomes `-Users-yourname-Workspaces-my-project`).

Do NOT pipe through `head` — read the first line of output yourself. Extract the UUID from the filename (strip the path and `.jsonl` extension).

### 2. Determine session name

Use this priority:
1. **Explicit argument** — if the user provided a name, use it as-is
2. **Next available number** — find the lowest unused integer starting from 0:

```bash
tmux list-sessions -F '#S' 2>/dev/null
```

Check which numbers (0, 1, 2...) are already taken and use the next available one.

### 2b. Input Validation

Before proceeding, validate the environment and inputs:

- **Session name**: If user provided a name, ensure it matches `[a-zA-Z0-9_-]+` (no spaces, special chars). If invalid, reject with error message.
- **Session doesn't exist**: Run `tmux list-sessions -F '#S'` and verify the target name is not already in use. If it exists, error: "Session '<name>' already exists. Use a different name or attach with `mac <name>`."
- **Claude binary**: Verify `which claude` returns a path. If not found, error: "Claude CLI not found in PATH. Install or check your installation."
- **Ghostty installed** (for non-tmux case): Verify `which ghostty` or `/Applications/Ghostty.app` exists. If not, error: "Ghostty not found. Install from https://github.com/mitchellh/ghostty or use `brew install ghostty`."
- **Working directory exists**: Verify `pwd` returns a valid path. If CWD is deleted or unreachable, error: "Current working directory is invalid or unreachable."

### 3. Check if already inside tmux

Run `printenv TMUX` to check. If it prints a value, you are inside tmux. If it returns exit code 1 with no output, you are not.

**If inside tmux** — create a new window and start Claude there:

```bash
tmux new-window -c "<cwd>"
tmux send-keys "claude --resume <session-id>" Enter
```

Then skip to step 6.

**If NOT inside tmux** — continue to step 4.

### 4. Create tmux session and start Claude

```bash
tmux new-session -d -s "<name>" -c "<cwd>" "claude --resume <session-id>"
```

By passing `claude --resume` as the session command (not send-keys), the session naturally cleans up: when Claude exits, the window closes, the session is destroyed, and Ghostty closes.

### 5. Open new Ghostty window

```bash
open -na Ghostty --args --command="/opt/homebrew/bin/tmux attach -t <name>" --quit-after-last-window-closed=true
```

### 6. Report

Tell the user:
- Session **<name>** is running in the new Ghostty window with their conversation resuming
- They can close this tab with **Cmd+W**
- From Termux: `mac <name>`

## Error Handling

Handle these failure points and recovery paths:

| Failure Point | Detection | Error Message | Recovery |
|---|---|---|---|
| **Session name already exists** | `tmux list-sessions` contains name | "Session '<name>' already exists. Use a different name or attach with `mac <name>`." | Suggest next numeric ID or ask for new name |
| **Invalid session name** | Name contains spaces or special chars | "Session name must be alphanumeric, underscore, or hyphen. Got: '<name>'" | Ask user for valid name |
| **Claude CLI not found** | `which claude` returns nothing | "Claude CLI not found. Check installation: `which claude`" | Advise user to reinstall or check PATH |
| **Session ID not found** | No `.jsonl` files in session directory or parsing fails | "Could not find session ID. Projects dir: `~/.claude/projects/`. Current: `<project-name>`" | Verify project name derivation, check session files exist |
| **Ghostty not installed** | `which ghostty` and `/Applications/Ghostty.app` both missing | "Ghostty not found. Install: `brew install ghostty` or download from https://github.com/mitchellh/ghostty" | Provide installation instructions |
| **tmux new-session fails** | Command exits non-zero | "Failed to create tmux session. Error: `<stderr>`" | Check for permission issues, disk space, or tmux config errors |
| **open command fails** (macOS only) | `open -na Ghostty` exits non-zero | "Failed to open Ghostty window. Error: `<stderr>`" | Suggest manual attach: `tmux attach -t <name>` |
| **Working directory invalid** | `pwd` fails or path doesn't exist | "Working directory is invalid or unreachable: `<cwd>`" | Verify directory exists, try from home directory |
| **Claude --resume fails** | Claude process exits immediately | "Claude failed to resume session. Check logs in new window." | Ask user to manually check Ghostty window for errors |

## Output Format Examples

### Example 1: Successful new session (not inside tmux)

```
✓ Created tmux session: dev-0
✓ Claude resuming conversation in Ghostty window
✓ Session name: dev-0
✓ To reattach from terminal: mac dev-0
✓ To quit: Cmd+W in this tab
```

### Example 2: Successful new window (inside tmux)

```
✓ Created tmux window in current session
✓ Claude resuming conversation in new window
✓ Window index: 2
✓ Current window remains open (use C-b n/p to switch)
```

### Example 3: Error case—session name conflict

```
✗ Session 'work' already exists
→ Use a different name: /tmux work-2
→ Or attach to existing: mac work
```

### Example 4: Error case—Ghostty not installed

```
✗ Ghostty not found at /Applications/Ghostty.app
→ Install: brew install ghostty
→ Or download: https://github.com/mitchellh/ghostty
```
