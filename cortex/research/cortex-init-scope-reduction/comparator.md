# Neutral comparator survey

Survey of how comparable tools handle host-state integration at install or first-run, with focus on the specific decision Cortex-command is reconsidering: writing the repo's `cortex/` path into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array during `cortex init`. This document describes; it does not advocate.

## Claude Code plugin install patterns

When a user runs `/plugin install <name>@<marketplace>` inside Claude Code, the harness performs a managed install that the user observes through the `/plugin` tabbed UI. The Discover tab exposes a "Will install" section (v2.1.145+) listing the plugin's commands, agents, skills, hooks, and MCP/LSP servers before the user confirms, and a Context cost estimate (v2.1.143+) showing how many tokens it adds per turn. The user then picks an installation scope: **User** (across all projects), **Project** (`.claude/settings.json`, shared via VCS), or **Local** (gitignored, this repo only). Source: [Discover and install prebuilt plugins through marketplaces — Claude Code Docs](https://code.claude.com/docs/en/discover-plugins).

What hits the filesystem: the plugin is cloned to `~/.claude/plugins/cache/`, and a reference is written to whichever settings file matches the chosen scope (most commonly `~/.claude/settings.json` for user scope). The plugin's `.mcp.json` or inline `mcpServers` config is read by Claude Code at session start but is not copied out to user settings — plugin MCP servers are bound through the plugin manifest. Plugins do not, in the normal install path, mutate the user's `sandbox.filesystem.allowWrite` array; sandbox boundaries are controlled separately via `/sandbox` or by hand-editing settings. Source: [Connect Claude Code to tools via MCP — Claude Code Docs](https://code.claude.com/docs/en/mcp).

The marketplace docs are explicit that plugins are highly trusted code: *"Plugins and marketplaces are highly trusted components that can execute arbitrary code on your machine with your user privileges. Only install plugins and add marketplaces from sources you trust."* The trust gate is the install confirmation itself, not per-file consent.

## MCP server install patterns

For MCP servers added outside the plugin system, Claude Code provides `claude mcp add` as the supported entry point — it writes the user's settings on behalf of the user, with the user choosing scope (`--scope local|project|user`). Local and user scopes write to `~/.claude.json`; project scope writes a `.mcp.json` at the project root. Source: [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp).

For project-scoped servers checked into a repo's `.mcp.json`, Claude Code does **not** auto-trust on session start. It prompts the user for approval the first time the project is opened; the docs note these appear in `claude mcp list` as `⏸ Pending approval`. Users can reset via `claude mcp reset-project-choices`. This is the same trust-on-first-encounter pattern as the workspace trust dialog ("Do you trust this folder?") that Claude Code shows when opening a new directory. Source: [Issue #6797 — "Claude asks 'Do you trust the files in this folder?' every launch"](https://github.com/anthropics/claude-code/issues/6797).

Claude Desktop's MCP install flow is more manual: users open Settings → Developer → Edit Config, which opens `claude_desktop_config.json` (paths vary by OS). They paste a server block and restart Claude Desktop. Trust is implicit in the act of pasting. Source: [github-mcp-server install-claude.md](https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-claude.md).

Trust model summary: MCP servers are treated as code-running endpoints. The accepted patterns are (a) a first-party CLI (`claude mcp add`) that writes settings on behalf of the user, or (b) manual user-edited JSON. Third-party CLIs writing into `~/.claude.json` to register MCP servers without going through `claude mcp add` is not a documented pattern.

## Comparable terminal tools that write to ~/.claude/

The Claude Code helper ecosystem has converged on a few patterns:

**ccstatusline** (`sirmalloc/ccstatusline`) runs a TUI installer that asks the user to choose Pinned global install vs. follow `@latest`, then writes a `statusLine` entry into `~/.claude/settings.json` and copies `statusline.sh` into `CLAUDE_CONFIG_DIR` (default `~/.claude`). Trust is established via npm provenance and the TUI showing what will be written before confirmation. Settings are backed up to `~/.config/ccstatusline/settings.json` and persisted across reinstalls. Source: [ccstatusline README](https://github.com/sirmalloc/ccstatusline); [ccstatusline analysis via WebFetch].

**cc-statusline** (`chongdashu/cc-statusline`) runs an `init` command that "generates an optimized bash script tailored to your needs and integrates with Claude Code settings," writing the `statusLine` property pointing at `.claude/statusline.sh`. Source: [cc-statusline](https://github.com/chongdashu/cc-statusline).

**ccusage** (`ryoppippi/ccusage`) reads `~/.claude/` JSONL usage data and does not modify settings by default; its statusline integration writes to `~/.claude/settings.json` only when the user opts in. Source: [ccusage statusline guide](https://ccusage.com/guide/statusline). The WebFetch on its README found no evidence of install-time writes to user settings.

**Superpowers** (`obra/superpowers`) installs as an official Claude Code plugin via `/plugin install superpowers@claude-plugins-official`, routing through the plugin marketplace's permission and trust model rather than touching user settings directly. The author explicitly recommends installing to user scope. Source: [Superpowers plugin](https://claude.com/plugins/superpowers).

Pattern: helper CLIs that need to register a `statusLine` (a single, scoped key) generally write it themselves with an interactive confirmation. Tools that need broader integration (skills, hooks, MCP servers) increasingly distribute via the official plugin marketplace rather than direct settings writes.

`NOT_FOUND(query="comparable CLI tool writing to sandbox.filesystem.allowWrite without using /plugin")`. No documented third-party tool that writes to `sandbox.filesystem.allowWrite` in `~/.claude/settings.local.json` during install surfaced in the searches.

## Current Claude Code prompt UX (filesystem writes)

The sandbox model determines what happens when a write target is outside the working directory. Source: [Configure the sandboxed Bash tool — Claude Code Docs](https://code.claude.com/docs/en/sandboxing).

- **Default:** sandboxed Bash commands can write only to the current working directory and its subdirectories. Writes outside that fall back to the regular permission flow (a prompt).
- **First-encounter prompts:** the first time a new network domain is needed, Claude Code prompts for approval. Filesystem prompts on out-of-sandbox writes are similar — per-path, surfaced inline.
- **Session-scope consent:** approving "Yes, and don't ask again" writes the rule into `.claude/settings.local.json`. Settings reload on file change without restart, so the approval applies to the current and future sessions.
- **Cross-session consent:** persisted via `permissions.allow` arrays and `sandbox.filesystem.allowWrite`. Arrays are concatenated across scopes, not replaced.
- **Sandbox modes:** Auto-allow mode runs sandboxed commands without prompting; Regular permissions mode keeps prompts. Internal testing found sandboxing reduces prompts by 84%. Source: [making Claude Code more secure and autonomous — Anthropic](https://www.anthropic.com/engineering/claude-code-sandboxing).

Version trajectory: Claude Code 2.1.x has actively reduced per-write prompts. Recent changes: read-only bash globs (`ls *.ts`) and `cd <project-dir> &&` prefixes no longer trigger permission prompts. A `/less-permission-prompts` skill scans transcripts for safe read-only operations and proposes an allowlist. Source: [Claude Code changelog: Opus 4.7 xhigh, /tui fullscreen — allthings.how](https://allthings.how/claude-code-changelog/).

The sandbox docs explicitly note: *"the sandbox automatically denies write access to Claude Code's `settings.json` files at every scope and to the managed settings directory, so a sandboxed command cannot modify its own policy."* This means an in-session Claude Code instance cannot itself write to `~/.claude/settings.local.json` — that write has to come from an out-of-sandbox process (which is what `cortex init` running outside Claude Code is). Source: [Sandboxing — Security limitations](https://code.claude.com/docs/en/sandboxing#security-limitations).

User reception of the prompt model is mixed: developers report running in `--dangerously-skip-permissions` mode at least 90% of the time, and accept 93% of prompts when shown them. Sources: [Run Claude Code Without Permission Prompts](https://daveswift.com/claude-without-permission/); [YOLO Mode — DEV Community](https://dev.to/rajeshroyal/yolo-mode-when-youre-tired-of-claude-asking-permission-for-everything-2daf).

## Industry install-time-trust patterns

**Homebrew formulae** that need to modify user shell config (`.zshrc`, `.bashrc`) have two patterns, and Homebrew core explicitly *lacks* a standardized convention. Some print a `caveats` message asking the user to manually add `source` lines; others write to dotfiles in `post_install`. A Homebrew issue ([#13609](https://github.com/Homebrew/brew/issues/13609)) acknowledges this and proposes a DSL function to standardize, citing that "every formula does it differently." The `caveats`-and-ask-the-user pattern is treated as the safer default in Homebrew/homebrew-core review; auto-modification of user config files is allowed but not endorsed.

**npm postinstall scripts** run arbitrary code with developer privileges at install time. This is a documented attack surface — the Shai-Hulud, Nx, and event-stream attacks all leveraged postinstall to exfiltrate credentials. The community recommendation is `npm install --ignore-scripts` by default and per-package allowlists for legitimate native-binary installers. Sources: [The npm Supply Chain Problem — linuxsecurity.com](https://linuxsecurity.com/features/npm-install-security-risk); [NPM Ignore Scripts Best Practices — nodejs-security.com](https://www.nodejs-security.com/blog/npm-ignore-scripts-best-practices-as-security-mitigation-for-malicious-packages); [Mitigating supply chain attacks — pnpm](https://pnpm.io/supply-chain-security). The reception is broadly negative: postinstall is treated as a necessary evil for some packages but a red flag in others.

**VS Code extensions** use Publisher Trust (since v1.97): first install from a third-party publisher shows an explicit "do you trust this publisher" dialog. Extensions inherit VS Code's permissions (can read/write files, run processes, modify workspace settings). The Workspace Trust feature centralizes per-folder consent: extensions that haven't opted into Workspace Trust are disabled in Restricted Mode. Source: [Workspace Trust — VS Code Docs](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust); [Extension runtime security](https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security). The pattern: trust is established at the publisher and folder boundaries, not per-file.

**gh CLI extensions** run with user permissions. The official guidance: *"You shouldn't need to grant any permissions to run an extension. If the extension needs additional permissions to operate properly it should list them in their readme/usage docs."* GitHub does not verify, sign, or endorse extensions; the user takes on review responsibility at install. Source: [gh extension permissions discussion #6433](https://github.com/cli/cli/discussions/6433); [Using GitHub CLI extensions — GitHub Docs](https://docs.github.com/en/github-cli/github-cli/using-github-cli-extensions).

**uv tool install** (Python tools): installs an isolated venv per tool, links executables onto PATH, and reads user-level `~/.config/uv/uv.toml` for tool config. It does not run arbitrary install-time scripts (Python's `pyproject.toml` does not have the equivalent of npm postinstall in the same form). Source: [Tools — uv](https://docs.astral.sh/uv/concepts/tools/). The PATH-add is surfaced as a warning, not a silent modification — the user runs `uv tool update-shell` to actually modify their shell rc.

Cross-tool synthesis: the durable conventions are (a) declare what will be written before doing it (VS Code's "will install" dialog, ccstatusline's TUI preview, Homebrew's `caveats`); (b) place writes behind an explicit user-initiated command (`gh extension install`, `claude mcp add`, `cortex init`) rather than a silent step buried in `pip install`; (c) keep writes additive and reversible; (d) document them.

## Empirical user reception

Documented user reactions to Claude Code tooling touching host state cluster into several patterns:

**Friction with repeated trust prompts.** Multiple GitHub issues ([#3366](https://github.com/anthropics/claude-code/issues/3366), [#9256](https://github.com/anthropics/claude-code/issues/9256), [#6797](https://github.com/anthropics/claude-code/issues/6797), [#29285](https://github.com/anthropics/claude-code/issues/29285)) complain about the "Do you trust this folder?" dialog re-prompting on every launch when it should remember the choice. Users want `trustedDirectories` config in `~/.claude/settings.json` to pre-approve folders. This is the canonical example of users *asking* for less host-state friction — not complaining about being asked at all.

**CLAUDE.md and .gitignore modifications.** A blog post by Andy Jakubowski ([Keeping CLAUDE.md out of shared Git repos](https://andyjakubowski.com/engineering/keeping-claude-md-out-of-shared-git-repos)) flags that users in shared codebases don't want Claude Code's `/init` to drop CLAUDE.md into their tracked repo. Workaround offered: use `$GIT_DIR/info/exclude` instead of touching the tracked `.gitignore`. This is a documented case where modification of repo-tracked files (not host-state) generated friction.

**Security vulnerability through settings hooks.** Check Point research ([Claude Code Flaws Exposed Developer Devices — SecurityWeek](https://www.securityweek.com/claude-code-flaws-exposed-developer-devices-to-silent-hacking/); [The Hacker News, Feb 2026](https://thehackernews.com/2026/02/claude-code-flaws-allow-remote-code.html)) identified that an attacker who controls a repo's `.claude/settings.json` can register hooks that execute arbitrary commands when the repo is cloned. This shaped subsequent Anthropic guidance: settings files are now treated as an execution surface, and the sandbox explicitly denies write access to them from in-session bash. This is the strongest *failure pattern* for accepting filesystem writes into Claude Code config files from any source.

**Acceptance of plugin marketplace writes.** The plugin marketplace install pattern — confirmation dialog, "Will install" preview, scope selection, then write to `~/.claude/settings.json` — is broadly accepted across the ecosystem (Superpowers, GitHub plugin, Sentry plugin, etc.). No issues surfaced in searches complaining that `/plugin install` writes to settings.

**Acceptance of `claude mcp add` writes.** Similar acceptance: `claude mcp add` writes to `~/.claude.json` on the user's behalf and is the standard documented entry point. No "this tool modified my settings without permission" complaints surfaced.

**Acceptance of statusline tool writes.** ccstatusline's TUI install (which writes to `~/.claude/settings.json`) has not generated trust complaints in the searches, likely because (a) the TUI shows what it's writing, (b) the scope is narrow — a single `statusLine` key — and (c) it's user-initiated via npm/Bun install of a known package.

`NOT_FOUND(query="Claude Code modified my settings without consent uninstall removed sketchy")`. No direct evidence of users uninstalling Claude Code helpers specifically because of unexpected `~/.claude/` writes surfaced in searches. The complaint pattern that does exist is *under-permissioning* (re-prompting, permissions not respected) far more than *over-reaching writes*.

## Summary table

| Pattern | Tool example | What it writes | Trust mechanism | Reception |
|---|---|---|---|---|
| Plugin marketplace install | `/plugin install github@claude-plugins-official` | `~/.claude/settings.json` (scope-dependent), plugin cached to `~/.claude/plugins/cache/` | Marketplace curation + "Will install" preview + scope picker + explicit confirm | Accepted; no documented backlash |
| First-party MCP CLI | `claude mcp add` | `~/.claude.json` (user/local scope) or `.mcp.json` (project) | User-invoked command + `--scope` flag + project-scoped servers re-prompt on first open | Accepted; standard pattern |
| Manual MCP config edit | Claude Desktop Edit Config button | `claude_desktop_config.json` | User pastes server block themselves | Accepted; no automation, no surprise |
| Helper CLI with TUI install | ccstatusline | `~/.claude/settings.json` (`statusLine` key) + `~/.claude/statusline.sh` | npm provenance + TUI preview + version pinning | Accepted; backup in `~/.config/ccstatusline/` |
| Helper CLI plugin distribution | Superpowers, cortex-core plugin | Routes through `/plugin install` | Marketplace trust + plugin-scope confirm | Accepted |
| Workspace trust prompt | Claude Code session open | `~/.claude/.claude.json` (trusted folder list) | First-encounter prompt on new directory | Mixed: users want persistence, not removal |
| npm postinstall script | Arbitrary npm packages | Anything (developer privileges) | None — runs automatically | Strongly contested; documented attack vector |
| VS Code extension install | Any marketplace extension | Inherits VS Code permissions (read/write files, run procs) | Publisher Trust dialog + Workspace Trust dialog | Accepted with caveats; Restricted Mode default for un-opted extensions |
| gh CLI extension install | `gh extension install owner/repo` | Tool's own files under user privileges | "Extensions not verified, signed, or endorsed" — review responsibility on user | Accepted; sandbox-blind |
| Homebrew formula `post_install` | rbenv, nvm, jenv | Optionally `.zshrc`, `.bashrc` | No standard convention; `caveats` ask-the-user is the safer pattern | Inconsistent; no convention exists |
| uv tool install | `uv tool install <pkg>` | Isolated venv + PATH link; warning if shell rc needs update | User runs `uv tool update-shell` to commit | Accepted; PATH change is surfaced, not silent |
| Hook execution from cloned repo | Malicious `.claude/settings.json` | Arbitrary code via hooks | Was implicit on repo open; now sandbox blocks writes to settings | Failure pattern — drove security fix |

## Cross-cutting observations

1. Strongest convergent convention: declare what will be written, place the write behind an explicit user command, and make it reversible. VS Code's "will install" dialog, Claude Code's `/plugin` preview, ccstatusline's TUI, Homebrew's `caveats`, and uv's `update-shell` warning are all instances.

2. The pattern that consistently generates blowback is the silent automatic write at install time — npm postinstall is the canonical example, and Anthropic's security posture on `.claude/settings.json` shifted because hooks can be triggered without explicit user action.

3. For Claude Code specifically, writing to `~/.claude/settings.local.json` from a third-party tool is not a documented standard pattern. Standard patterns are (a) `claude mcp add`, (b) `/plugin install`, (c) manual user edit, or (d) Claude Code itself writes when prompting in-session.

4. Empirical reception data points more strongly to friction-from-prompts than friction-from-writes. Where users complained about host-state modification, the complaint was usually about repo-tracked files (`.gitignore`, `CLAUDE.md`) rather than user-home files (`~/.claude/`).
