# Research: session-window-naming

## Research Questions

1. Does Claude Code expose any mechanism (hook, API, env var, config) to name or rename a running session? → **Yes: `/rename <name>` is a built-in interactive command (v2.0.64+). No programmatic/hook-based rename exists yet.**

2. Does Ghostty support window-level naming distinct from tab naming? → **No. The window title IS the active tab's title on macOS. No separate OS-window name concept exists in Ghostty.**

3. Can OSC escape sequences set a persistent window title in Ghostty? → **OSC 0/2 are supported but Ghostty shell integration overrides them. Workaround: disable the title sub-feature via `shell-integration-features = no-title`.**

4. What lifecycle state is available at runtime that could drive a naming hook? → **Feature name and phase are derivable from `lifecycle/{feature}/` directory structure. `LIFECYCLE_SESSION_ID` is injected into CLAUDE_ENV_FILE at SessionStart.**

5. What hook points exist to trigger a rename when lifecycle context changes? → **SessionStart is the only hook that fires on lifecycle context load. No hook fires on lifecycle transitions (those happen through manual skill invocations).**

6. Can `claude` CLI sessions be renamed after launch, or only at start? → **Only after launch via `/rename`. No `--session-name` flag at launch. No CLI subcommand for scripted rename.**

## Codebase Analysis

### Lifecycle State Available at Runtime

**Feature name detection** (`hooks/scan-lifecycle.sh`):
- Scans `lifecycle/{feature}/.session` files, matches by session ID
- Feature name is the directory name (e.g., `docs-audit`, `fix-permission-system-bugs`)
- Phase is derived from artifact presence: `research.md` → specify → `spec.md` → plan → `plan.md` → implement → `events.log` with `feature_complete`

**Environment injection**:
- `LIFECYCLE_SESSION_ID` is written to `$CLAUDE_ENV_FILE` at SessionStart
- This env var is available to all subsequent Bash tool calls within the session
- Feature name is NOT injected — only the session ID is

**Active feature detection** (from scan-lifecycle.sh):
- The hook outputs `additionalContext` with feature name and phase to Claude's context
- This happens once at SessionStart — no ongoing hook fires when lifecycle state changes

### Hook Points

| Hook | When | Relevant? |
|------|------|-----------|
| SessionStart | Session begins / `/clear` | YES — only opportunity for auto-detection |
| SessionEnd | Session terminates | NO — too late for naming |
| PreToolUse (Bash) | Before git commands | NO |
| PostToolUse | After edits/commands | NO — too noisy |
| Stop | Complete/abort | NO |

**No hooks fire on lifecycle transitions.** Lifecycle state changes (phase advances, feature start/complete) happen when the user invokes skills like `/lifecycle` — no event is emitted that hooks can listen to.

### Existing Terminal Title Patterns

- **No OSC sequences** used anywhere in cortex-command
- `statusline.sh` uses ANSI color codes only (`\033[%sm`)
- `runner.sh` sets tmux **session names** via `--title "Overnight session: $BRANCH_NAME"` (not OSC sequences, not Ghostty window titles)
- No shell prompt integration for window titles exists

### Integration Points for a Solution

- `hooks/scan-lifecycle.sh`: already detects feature name — could write to `/dev/tty` for interactive window titles
- Skills like `/lifecycle`: knows the feature being started — natural place to suggest `/rename`
- `CLAUDE_ENV_FILE`: mechanism to propagate values from hooks to the session environment

## Web & Documentation Research

### Claude Code Session Naming

**What exists today (v2.0.64+)**:
- `/rename <name>` — interactive built-in, renames current session from within the REPL
- `/resume <name>` — resume a named session
- `claude --resume <name>` — CLI flag to resume at launch
- Press `R` on the `/resume` screen to rename interactively

**What does NOT exist**:
- `--session-name` flag at launch (no way to name a new session before it starts)
- `claude session rename <id> <name>` CLI subcommand
- Hook-callable rename mechanism
- Any API or env var that a script can write to rename the session

**Open feature requests** (strong demand, no ship date):
- anthropics/claude-code#34243: Programmatic rename from skills/hooks/CLI subcommand (open March 2026, 9+ duplicates)
- anthropics/claude-code#33165: Allow Claude to rename its own session (open)
- anthropics/claude-code#15762: Smart Session Rename (open)

**Critical constraint**: The `/rename` command is a CLI meta-command. It cannot be invoked via the Bash tool, cannot be called from a skill, and cannot be scripted. The agent running inside the session has no tool to call it.

### Ghostty Window Naming

**What "window" means in Ghostty**:
- On macOS, the OS-level window title comes from the active tab's surface title
- There is no separate, persistent "window name" concept independent of the tab system
- Ghostty does not expose a per-window label that survives tab switches

**OSC sequences**:
- OSC 0 (`\033]0;title\007`), OSC 1, OSC 2 are all recognized by Ghostty
- **Problem**: Ghostty's shell integration includes an automatic `title` feature that continuously overrides the surface title based on the running command
- **Workaround**: Set `shell-integration-features = no-title` in `~/.config/ghostty/config` to disable the override
- With that disabled, `printf "\033]0;my-title\007"` sets the surface title, which becomes the window title (for the active tab) and the tab title
- This title is NOT persistent — any new command can reset it; shell integration normally resets it on each prompt

**1.3.0 persistent tab titles** (released early 2025):
- Right-click context menu or command palette: "Change Tab Title..."
- A `change_title` keybind action exists
- These set a persistent per-tab override that shells and OSC sequences cannot override
- **No programmatic equivalent** — cannot be set via script or config

**The `title` config option**:
- Forces a static title globally on all windows
- Cannot be set per-window at launch (no `--window-title` flag)
- Cannot be changed per-session without editing config

**Bottom line**: Ghostty does not have a window-level name separate from the tab title. The visual effect of a named window is achievable via OSC sequences (with shell integration title disabled), but it requires active maintenance — the shell prompt must re-emit the sequence, or any new command may reset it.

## Domain & Prior Art

### How others name terminal sessions

- **tmux**: Window/session naming is first-class (`tmux rename-window`, `-t` flag). This repo already uses tmux session names for overnight sessions.
- **Wezterm**: Per-tab titles, per-pane titles via OSC, pane user vars via OSC 1337. No OS-level window name distinct from tab.
- **iTerm2**: Supports profile-level window names, user-defined variables via OSC 1337, AppleScript control. More extensible than Ghostty.
- **VS Code terminals**: Named via `terminal.integrated.tabs.title` template (env var interpolation). Session naming is a VS Code API concern.

Common pattern for terminal window titles: **the shell prompt is the correct integration point**. Tools like Starship, oh-my-zsh, and `precmd` hooks in zsh emit OSC sequences on each prompt redraw, which means the title stays current without a one-shot hook. The OSC approach only works reliably when the prompt maintains it continuously.

### How Claude Code sessions are named in practice

- Sessions are identified by a UUID-like ID, not by name
- Overnight sessions use the naming format `overnight-YYYY-MM-DD-HHmm` (set as session ID, not session name)
- The `/rename` feature was shipped in response to user demand; programmatic rename is the natural next step

## Feasibility Assessment

**Important distinction**: Claude Code session naming (visible in `/resume` screen, session list) and Ghostty window/tab title (visible in the OS window switcher and Ghostty tab bar) solve *different problems* and are *independent mechanisms*. They should not be treated as alternatives.

### Session Naming (Claude Code `/resume` screen visibility)

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **Semi-automatic: skill suggests `/rename`** — `/lifecycle start` detects feature name and outputs the `/rename` command for the user to run | S | Low adoption: depends on user discipline; will be done inconsistently. **Fatal gap: does not work in overnight/pipeline contexts.** | None — works today |
| **Fully automatic: programmatic rename** — script or hook calls `claude session rename` | XL / blocked | Requires Anthropic to ship CLI subcommand (anthropics/claude-code#34243). No ship date. | Claude Code feature not yet released |

**Honest accounting of the semi-automatic approach**: This is a reminder mechanism, not session naming. The user must read the output, decide to act, and run a command — every time. It will be done inconsistently. It does not address the highest-value use case (unattended overnight sessions), where naming would be most valuable for morning review. Until Claude Code ships programmatic rename, overnight sessions cannot be automatically named.

### Window/Tab Title (Ghostty tab bar and OS window switcher visibility)

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **Shell prompt segment** — zsh `precmd` hook reads active lifecycle feature and emits OSC 0 on each prompt | M | Requires `shell-integration-features = no-title`; most reliable approach — prompt re-emits on every redraw; owned by machine-config | machine-config changes |
| **OSC from SessionStart hook via `/dev/tty`** — hook writes `printf "\033]0;feature\007" > /dev/tty` | S | Works for interactive sessions (controlling terminal is the user's Ghostty window). Fails for overnight runner (no interactive terminal) and may fail in sandbox mode. Title set once at session start; not maintained through subsequent commands. | `shell-integration-features = no-title` must be set |
| **OSC from SessionStart hook via stdout** | Not viable | Hook stdout goes to Claude Code as the hook response, not to the terminal emulator | N/A |

**On the `/dev/tty` approach**: For interactive Claude Code sessions launched in Ghostty, the hook process inherits the controlling terminal. Writing `printf "\033]0;feature\007" > /dev/tty` in the SessionStart hook *should* reach Ghostty and set the title for that session. This is how tools like `direnv` interact with the terminal without going through stdout. The limitation is that the title is set once at SessionStart and will be overridden when subsequent commands run (unless shell integration title is disabled). For the common case of "launch Claude in a Ghostty tab → work on a lifecycle feature," this would work. It would not work for overnight/automated sessions.

**On the shell prompt approach**: This is the most technically reliable mechanism. The prompt re-emits the OSC sequence on every prompt redraw, maintaining the title continuously. It is how virtually every other tool in this space handles persistent window titles. The trade-off is that it belongs in machine-config, not here.

## Decision Records

### DR-1: OSC via `/dev/tty` is viable for interactive sessions only

- **Context**: Whether a SessionStart hook can set the Ghostty window title via OSC sequences.
- **Options considered**: Hook stdout → not viable (consumed by Claude Code). Hook `/dev/tty` → viable for interactive sessions. Shell prompt component → most reliable, but machine-config.
- **Recommendation**: The `/dev/tty` approach works for interactive sessions. It is a reasonable first implementation — low effort, available today. The title resets when commands run (shell integration keeps overriding it), so the practical effect is "title is set when Claude starts, may drift as the session progresses." The shell prompt approach in machine-config is more robust but requires a separate repo change.
- **Trade-offs**: `/dev/tty` gives a one-shot title at SessionStart. Shell prompt gives a maintained title. Overnight runner gets neither — it has no interactive terminal.

### DR-2: Semi-automatic session rename is a partial solution with real gaps

- **Context**: The user wants sessions named automatically to lifecycle features.
- **Honest assessment**: Having `/lifecycle` output the `/rename feature-name` command is not automatic — it's a reminder. It will be used inconsistently. It does not address overnight/pipeline sessions (the use case where session naming would have the highest value for morning review).
- **Recommendation**: Implement it as a low-effort improvement over nothing. Be explicit in the ticket that this is a bridge until Claude Code ships programmatic rename. Do not frame it as solving the problem — it partially solves the interactive case.
- **What actually solves it**: anthropics/claude-code#34243 shipping. When that exists, the SessionStart hook can auto-rename the session using the detected feature name. This is the right end state.

### DR-3: Scope split — cortex-command vs. machine-config

- **Context**: Session renaming from within Claude Code is cortex-command's domain. Ghostty window titles via shell prompt are machine-config's domain.
- **Important nuance**: The shell prompt approach is the *most technically reliable* solution for the window title problem. Scoping it to machine-config is the correct architectural choice, but it means acknowledging that the best solution requires a different repo. The `/dev/tty` hook approach is a weaker alternative that cortex-command can own today.
- **Recommendation**: Cortex-command owns (a) the `/lifecycle` rename suggestion and (b) the `/dev/tty` window title in SessionStart hook. Machine-config owns the shell prompt segment if the user wants persistent title maintenance. These are independent.

## Open Questions

- Should the `/dev/tty` OSC approach be implemented in the SessionStart hook, given that it sets the title once at session start (not maintained)? Or should implementation wait for the shell prompt approach in machine-config?
- Is the Ghostty window title problem worth pursuing at all, given that it is fundamentally limited to tab-level naming (no true OS-window name)?
- Should the `/lifecycle` skill suggest `/rename` only at feature start, or also when resuming an existing lifecycle feature?
- If Claude Code ships `claude session rename`, should the SessionStart hook auto-rename sessions on startup when a lifecycle feature is detected, or should it be opt-in?
