[← Back to README](../README.md)

# Setup Guide

**For:** Users setting up cortex-command on a new machine.  **Assumes:** Claude Code is installed and working; basic git and terminal familiarity.

> **Machine-level config** (shell, terminal, git, starship, tmux, caffeinate) lives in the [machine-config](https://github.com/charleshall888/machine-config) repo. This guide covers only cortex-command — the agentic layer.

---

## Prerequisites

Before installing cortex-command, make sure you have:

- **[uv](https://docs.astral.sh/uv/)** — Python package manager. Install with `brew install uv`.
- **[Claude Code CLI](https://docs.claude.com/en/docs/claude-code/overview)** — the `claude` binary on your `PATH`.

---

## Install

Cortex-command ships as a Python CLI plus a set of Claude Code plugins. Installation has three steps: install the CLI from a tag-pinned git URL, install the plugins from inside Claude, and run `cortex init` once per repo.

### 1. Install the `cortex` CLI

```bash
uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0
```

This installs the CLI as a non-editable `uv tool` directly from the tagged git URL — no clone is required. The `cortex` binary lands on your `PATH` (run `uv tool update-shell` once if it does not).

If you do not have `uv` available yet, the `install.sh` bootstrap script installs `uv` first and runs the same command:

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

The cortex-overnight MCP server also auto-installs the CLI on first tool call when `cortex` is missing from `PATH`. Users who only interact with cortex through Claude Code never need an explicit install step. Set `CORTEX_AUTO_INSTALL=0` to opt out of the auto-install behavior (the MCP will then surface a notice instead of running `uv tool install`).

#### Upgrading

To upgrade later: run `/plugin update cortex-overnight@cortex-command` from inside Claude (MCP-driven), or `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<new-tag>` from a bare shell. `cortex upgrade` itself is an advisory printer — the wheel for any version `vN` can only declare "I am vN" and has no way to know about newer tags. See [docs/release-process.md](release-process.md) for the tag-before-coupling discipline.

The `cortex-overnight` plugin's MCP server embeds a `CLI_PIN` constant — a tuple `(tag, schema_version)` — that pairs the plugin with a specific cortex CLI tag. The plugin drives CLI auto-update via tag bump on first MCP tool call (the upgrade arrow flows plugin → CLI, not the other way).

- **Plugin auto-update enabled (default)**: Claude Code refreshes the plugin in the background; the next MCP tool call detects a `CLI_PIN[0]` bump and auto-installs the matching CLI tag.
- **Plugin auto-update disabled**: the embedded `CLI_PIN` stays pinned to whatever tag was current when you installed the plugin — a stable plugin/CLI pair until you explicitly run `/plugin update cortex-overnight@cortex-command`. A stale plugin is the intended state under disabled auto-update; schema versions match between the embedded `CLI_PIN[1]` and the installed CLI's print-root envelope, so everything works.

#### Troubleshooting CLI install

- **`cortex: command not found`**: confirm `~/.local/bin/` is on your `PATH`. Add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc file, or run `uv tool update-shell` once.
- **`cortex --print-root` fails with "Run from your cortex project root..."**: you invoked `cortex` from a directory with no `lifecycle/` AND no `backlog/`. Either `cd` into a cortex project, set `CORTEX_REPO_ROOT=/path/to/your/project`, or create a new project with `git init && cortex init`.
- **macOS GUI-app launches Claude Code; `uv` not on PATH**: see the macOS GUI-launch caveat in the `cortex-overnight` plugin-specific prerequisites below.

### 2. Add and install the plugins from inside Claude Code

Launch `claude`, then add the marketplace once and install whichever plugins you want:

```
/plugin marketplace add charleshall888/cortex-command
/plugin install cortex-core@cortex-command
/plugin install cortex-overnight@cortex-command
/plugin install cortex-ui-extras@cortex-command
/plugin install cortex-pr-review@cortex-command
```

The six available plugins are:

| Plugin | Description |
|--------|-------------|
| android-dev-extras | Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration |
| cortex-dev-extras | Devil's advocate inline challenge for solo deliberation |
| cortex-core | Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows |
| cortex-overnight | Integrates the cortex MCP server and overnight skill runner hooks to drive autonomous lifecycle execution |
| cortex-pr-review | Multi-agent GitHub pull request review pipeline for Claude Code |
| cortex-ui-extras | Experimental UI design skills for Claude Code interactive workflows |

#### Plugin-specific prerequisites

- **`cortex-overnight`** requires `uv` and the `cortex` CLI on your `PATH`. The MCP server auto-installs `cortex` on first tool call when it is missing (set `CORTEX_AUTO_INSTALL=0` to opt out and receive a notice instead). It also probes for `uv` at startup and refuses to run if `uv` is not on `PATH`. macOS GUI-launched Claude Code processes do not inherit the same `PATH` as a Terminal session — if `uv` is on `PATH` in your shell but the MCP server still reports it missing, see the auto-install error message and add `uv`'s install directory to `~/.zshenv` (or `~/.bash_profile`) so GUI-launched processes pick it up.
- **`cortex-core`** shell-side bin shims (`cortex-jcc` and the other `cortex-*` tools) need to be invoked from inside a cortex project directory (one containing `lifecycle/` or `backlog/`), or with `CORTEX_REPO_ROOT=/path/to/your/project` exported. The in-Claude skills work without setup. The shims error explicitly with the missing-project message when neither condition holds.
- **`cortex-ui-extras`** has no extra prerequisites.
- **`cortex-pr-review`** has no extra prerequisites.

#### Do not add via direct `marketplace.json` URL

Use the `owner/repo` git form (`/plugin marketplace add charleshall888/cortex-command`). Do **not** add the marketplace by passing a raw `marketplace.json` URL — relative-path `source` fields only resolve against a git checkout, so the URL form silently breaks plugin installs.

#### Troubleshooting plugin install

1. Run `/plugin list` to confirm the plugins you installed are listed.
2. If a skill is missing after install, run `/reload-plugins` to refresh the plugin metadata cache.
3. As a last resort, nuke the plugin cache and re-run `/reload-plugins`:

   ```bash
   rm -rf ~/.claude/plugins/cache
   ```

### 3. Per-repo setup

Run `cortex init` once in each repo where you want to use cortex. It scaffolds the directories cortex skills and the overnight runner expect (`lifecycle/`, `backlog/`, `retros/`, `requirements/`) and registers the repo's `lifecycle/` path in your Claude Code sandbox allowlist — required for any cortex workflow (lifecycle, refine, backlog, overnight, dashboard).

```bash
cortex init
```

`cortex init` runs seven side effects in order:

**1. Git repo root resolution / submodule refusal**
Resolves the git repo root via `git rev-parse --show-toplevel`. If the current directory is not inside a git repository, init exits with an error. If it is inside a submodule (detected via `git rev-parse --show-superproject-working-tree`), init refuses and tells you to run at the top-level repo instead.

**2. Symlink-safety gate**
Checks that the `lifecycle/` path inside the repo does not resolve through a symlink. This validation captures the canonical path used for sandbox registration in step 7, eliminating a TOCTOU gap between path-resolution and write.

**3. `~/.claude/settings.local.json` validation**
Validates `~/.claude/settings.local.json` before any mutation. If the file exists but is malformed JSON, init stops here rather than corrupting it. This is a read-only pre-flight — no changes are made at this step.

**4. `.cortex-init` marker check**
Checks for a `.cortex-init` marker file in the repo root. If the marker is present and neither `--update` nor `--force` is passed, init declines to re-scaffold so a second accidental `cortex init` does not overwrite local customizations. Pass `--update` for an additive (no-overwrite) re-run, or `--force` to back up and overwrite.

**5. Scaffold dispatch**
Creates the directory structure and starter templates: `lifecycle/`, `backlog/`, `retros/`, and `requirements/`. Behavior depends on the flag combination and whether the `.cortex-init` marker is present (see step 4). After scaffolding, `cortex init` writes or refreshes the `.cortex-init` marker file to record the timestamp of the last successful run.

**6. Idempotent `.gitignore` append**
Appends cortex-specific ignore patterns to the repo's `.gitignore`. This step always runs regardless of which scaffold branch was taken above. It is idempotent — running `cortex init` a second time will not duplicate entries.

**7. Sandbox registration into `~/.claude/settings.local.json`**
This step additively registers the repo's `lifecycle/` path in `~/.claude/settings.local.json` under `sandbox.filesystem.allowWrite`. This is the only write to `~/.claude/settings.local.json` that `cortex init` performs (validation in step 3 is read-only). Concurrent calls to `cortex init` across multiple repos are safe: the implementation uses `fcntl.flock` on a sibling lock file so concurrent processes serialize rather than corrupt the JSON.

#### lifecycle.config.md schema

`cortex init` scaffolds a `lifecycle/lifecycle.config.md` file in your repo with project-specific overrides for the lifecycle skill and overnight runner. The file uses YAML frontmatter with 6 keys, split into 3 active (consumed by code today) and 3 advisory (present in the scaffold but not yet enforced by any code path):

**Active keys** — consumed by code or skill prose today:

- **`test-command`** — Read by `cortex_command/overnight/daytime_pipeline.py`. Specifies the shell command used to run the repo's test suite during a daytime pipeline run. Defaults to `just test` when the key is missing or empty.

- **`commit-artifacts`** — Read by the lifecycle skill's commit step (`skills/lifecycle/references/{complete,research,plan,specify}.md`). Controls whether lifecycle artifacts (research, spec, plan, etc.) are included in the staged commit. Set `commit-artifacts: false` to exclude lifecycle artifacts from staging.

- **`demo-commands`** — Read by the morning-review skill (`skills/morning-review/SKILL.md` and `skills/morning-review/references/walkthrough.md`). Used for the post-overnight demo offer shown during morning review. Accepts a list of `{label, command}` entries:

  ```yaml
  demo-commands:
    - label: "Dashboard"
      command: "just dashboard"
    - label: "Run tests"
      command: "just test"
  ```

  When both `demo-commands:` (list) and the legacy `demo-command:` (single-string) keys are present, `demo-commands:` takes precedence.

**Advisory keys** — present in the scaffold template but not consumed by any code path or skill prose at present:

- **`type`** — Currently advisory. Intended to classify the repo type (e.g., `other`, `library`, `service`). No code reads this key today.

- **`skip-specify`** — Currently advisory. Intended to skip the specify phase in the lifecycle flow when set to `true`. No code enforces this today.

- **`skip-review`** — Currently advisory. Intended to skip the review phase in the lifecycle flow when set to `true`. No code enforces this today.

> **Note:** If a future ticket activates one of the advisory keys by adding a code consumer, the description above must be updated from `Currently advisory` to describe the consumer. That update is the responsibility of whichever ticket adds the consumer.

#### Worked example: `cortex init` + first lifecycle invocation

After installing the plugins, run `cortex init` once in your repo root:

```
cortex init
```

After `cortex init` completes, the following structure is created in your repo:

```
lifecycle/
lifecycle/README.md
lifecycle.config.md
backlog/
backlog/README.md
retros/
retros/README.md
requirements/
requirements/project.md
.cortex-init
.gitignore   ← updated with cortex ignore entries
```

The `.cortex-init` marker records the cortex version and timestamp of the run. `lifecycle.config.md` in the repo root holds per-repo configuration overrides (see the schema section above). The repo's `lifecycle/` path is also registered in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array so the overnight runner and interactive sessions can write under it without sandbox prompts.

Then run `/cortex-core:lifecycle <feature>` to begin a new feature, which produces a `lifecycle/<feature>/` directory containing the feature's lifecycle artifacts (research, spec, plan, implementation, events log). For example:

```
/cortex-core:lifecycle my-feature
```

This command initiates the research phase for `my-feature` and guides you through research → spec → plan → implementation → review. Running `/cortex-core:lifecycle my-feature` with no prior artifacts starts fresh; re-running it in a later session resumes from the current phase recorded in `lifecycle/my-feature/events.log`.

This sequence — `cortex init` followed by `/cortex-core:lifecycle <feature>` — is the end-to-end verification that both the CLI scaffold and the lifecycle skill are working in your environment.

#### Verify install

After completing the three steps above, run these two commands to confirm the cortex CLI and plugins are both wired correctly:

```bash
cortex --print-root
claude /plugin list
```

`cortex --print-root` should print a JSON object with five fields:

- **`version`** — the print-root JSON envelope schema version (currently `"1.1"`)
- **`root`** — the absolute path to your cortex project (the directory where you ran `cortex init`, resolved via `CORTEX_REPO_ROOT` env override or CWD with a `lifecycle/`+`backlog/` sanity check)
- **`package_root`** — the absolute path to the cortex-command package install (under `uv` tool, this lives inside `~/.local/share/uv/tools/cortex-command/`); useful for diagnostic introspection
- **`remote_url`** — the git remote URL of your project, if it is a git repository (empty string otherwise)
- **`head_sha`** — the full SHA of your project's current HEAD commit (empty string if it is not a git repository)

`claude /plugin list` should list the plugins you installed from the `cortex-command` marketplace (e.g. `cortex-core`, `cortex-overnight`, etc.). If a plugin you installed is missing, run `/reload-plugins` inside Claude Code to refresh the plugin metadata cache.

---

## Authentication

The overnight runner and some CLI utilities need API credentials. There are two modes depending on your account type.

### Option A: API Key (Console / Organization billing)

For work repos billed through the Anthropic Console:

1. Create an API key at [platform.claude.com](https://platform.claude.com)
2. Store it securely:
   ```bash
   printf '%s' 'sk-ant-api03-...' > ~/.claude/work-api-key
   chmod 600 ~/.claude/work-api-key
   ```
3. Add `apiKeyHelper` to `~/.claude/settings.local.json`:
   ```json
   {
     "apiKeyHelper": "cat ~/.claude/work-api-key"
   }
   ```

This path also enables `cortex-count-tokens` and `cortex-audit-doc`, which call the Anthropic API directly.

### Option B: OAuth Token (Claude Pro / Max subscription)

For personal repos using your Claude subscription:

1. Generate a long-lived token (valid 1 year):
   ```bash
   claude setup-token
   ```
   This opens a browser for OAuth authentication and prints the token.

2. Store the token:
   ```bash
   printf '%s' 'sk-ant-oat01-...' > ~/.claude/personal-oauth-token
   chmod 600 ~/.claude/personal-oauth-token
   ```

The overnight runner reads this file automatically when no `apiKeyHelper` is configured. No settings.json changes needed.

> **Note:** `CLAUDE_CODE_OAUTH_TOKEN` is recognized by Claude Code CLI (`claude -p`, Agent SDK) but **not** by the Anthropic Python SDK. Standalone utilities like `cortex-count-tokens` and `cortex-audit-doc` require an API key (Option A).

### Using Both

If you work on both personal and work repos, configure both:
- Set `apiKeyHelper` in the work repo's `.claude/settings.local.json`
- Store the OAuth token at `~/.claude/personal-oauth-token`

The runner uses `apiKeyHelper` when present (work), and falls back to the OAuth token file when not (personal). See [docs/overnight-operations.md](overnight-operations.md#auth-resolution-apikeyhelper-and-env-var-fallback-order) for the full precedence chain.

---

## Customization

### Recommended `~/.claude/settings.json` entries

Cortex-command no longer ships a `settings.json` into your user scope — you own that file. The maintainer's personal template (allow list, model, env vars, attribution, etc.) is opinionated and not a good default for others. The entries below are the load-bearing generic pieces cortex-command actually depends on; everything else (the `permissions.allow` list, `env`, `model`, `effortLevel`, `attribution`, `enableAllProjectMcpServers`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt`) is personal preference — compose your own.

**`sandbox.excludedCommands`**

```json
"sandbox": {
  "excludedCommands": ["gh:*", "git:*", "WebFetch", "WebSearch"]
}
```

Critical. `git` and `gh` need to run unsandboxed so GPG signing works and so commit hooks can spawn child processes (e.g., `gpg-agent`) without hitting sandbox denials. Changing this list breaks the sandbox-excluded command contract that cortex-command's git integration relies on.

**`sandbox.autoAllowBashIfSandboxed`**

```json
"sandbox": {
  "autoAllowBashIfSandboxed": true
}
```

Required for the overnight runner. Without it, every sandboxed Bash call requires interactive approval, which defeats unattended execution.

**`sandbox.network.allowedDomains`**

```json
"sandbox": {
  "network": {
    "allowedDomains": [
      "api.github.com",
      "raw.githubusercontent.com",
      "registry.npmjs.org",
      "*.anthropic.com"
    ]
  }
}
```

The minimum set cortex-command needs: GitHub API for `gh` operations, raw.githubusercontent.com for the install bootstrap, npm registry for plugin installs, and Anthropic endpoints for the SDK. Add more domains as your own workflows require.

**`sandbox.filesystem.allowWrite`**

You do not need to hand-edit this. Run `cortex init` in each repo where you want cortex-command active — it appends the per-repo overnight-session write paths automatically. Hand-editing is error-prone because the paths are repo-scoped and resolve relative to each project.

**`statusLine.command`** (optional, requires a clone)

```json
"statusLine": {
  "command": "/path/to/your/cortex-command/claude/statusline.sh"
}
```

This shows cortex-specific session state in the Claude Code statusline. The script ships in the cortex-command source tree at `claude/statusline.sh`, but the wheel-install path does not extract it onto disk anywhere a user can point at. To use this you need a clone of the repo (i.e., the forker path); point at the `claude/statusline.sh` inside your clone. Skip this entirely if you do not have a clone.

**`permissions.deny`**

A conservative deny list is a useful safety baseline: `sudo`, destructive `rm -rf` patterns, `git push --force` against protected branches, reads of secrets directories (`~/.ssh`, `~/.aws`, etc.). Cortex-command does not prescribe a specific list — compose your own. Do not paste any list blindly; review each rule against your own threat model.

### Adding an MCP Server

Add a `mcpServers` block to `claude/settings.json`:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@scope/server-package"]
    }
  }
}
```

Then add `"mcp__server-name__*"` to the `permissions.allow` list.

---

## Per-repo permission scoping

Claude Code's settings merge is strictly additive: `permissions.allow` arrays concatenate across all scopes, `permissions.deny` is monotonic, and there is no subtraction mechanism. If you want a repo to ignore your global allow list, layering alone cannot deliver it. The supported workaround is `CLAUDE_CONFIG_DIR`, an alternate user-scope directory Claude Code reads at launch — by launching from a repo with `CLAUDE_CONFIG_DIR` set to a shadow copy of `~/.claude`, that repo gets its own user scope. Watch upstream issues [#12962](https://github.com/anthropics/claude-code/issues/12962) and [#26489](https://github.com/anthropics/claude-code/issues/26489) for a first-class per-project permissions feature; until one of those lands, this is the recommended workaround.

### How it works

`CLAUDE_CONFIG_DIR` points Claude Code at an alternate user-scope directory instead of `~/.claude`. The value is read at launch time, so a relaunch is required to pick up a new value — direnv loading on `cd` does not affect an already-running session.

### Setup with direnv

1. Copy `~/.claude` to a shadow location: `cp -R ~/.claude ~/.claude-shadow`.
2. Write `.envrc` in your repo root:

   ```
   export CLAUDE_CONFIG_DIR=$HOME/.claude-shadow
   ```

3. Run `direnv allow` once in the repo.
4. Quit and relaunch Claude Code from the repo. direnv reloads `.envrc` on each `cd`, but Claude Code only reads `CLAUDE_CONFIG_DIR` at launch.

If you don't use direnv, a shell alias (`alias cc-shadow='CLAUDE_CONFIG_DIR=$HOME/.claude-shadow claude'`) or a `./bin/claude` wrapper script work equivalently.

### Limitations and foot-guns

**Cortex-command foot-guns.** Each of the following is a known failure mode this pattern surfaces. None of them are managed automatically — treat each as a rule to follow, not a problem the shadow resolves for you:

- **Evolve, auto-memory, cortex-audit-doc, and cortex-count-tokens walk from host**: these tools fall back to `~/.claude` rather than `$CLAUDE_CONFIG_DIR`. Auto-memory under a shadow writes to the host scope. Treat their output as host-scoped.
- **Concurrent sessions and scope confusion**: Claude Code's `/context` (an upstream bug) shows the host path even when a shadow is active, so you cannot verify the live scope from inside a session. Run `echo $CLAUDE_CONFIG_DIR` in your shell before launching each session.

**Upstream Claude Code partial-support bugs.** Even with `CLAUDE_CONFIG_DIR` set, several Claude Code subsystems do not fully honor it:

- [#36172](https://github.com/anthropics/claude-code/issues/36172) — skills in `$CLAUDE_CONFIG_DIR/skills/` are not reliably resolved. Most consequential for cortex-command because it undermines the "swap the entire user scope" mental model.
- [#38641](https://github.com/anthropics/claude-code/issues/38641) — `/context` displays the host path regardless of `CLAUDE_CONFIG_DIR`.
- [#42217](https://github.com/anthropics/claude-code/issues/42217) — MCP servers from `.mcp.json` are not loaded under a shadow.
- [#34800](https://github.com/anthropics/claude-code/issues/34800) — IDE lock files always write to `~/.claude/ide/` regardless of the env var.

For the full decision record and failure-mode inventory, see `research/user-configurable-setup/research.md`.

---

## macOS Notifications

For desktop notifications when Claude Code needs attention:

1. Install terminal-notifier: `brew install terminal-notifier`
2. Enable in **System Settings > Notifications**:
   - **terminal-notifier**: Allow notifications
   - **Your terminal app**: Allow notifications + enable "Badge app icon"

---

### Maintaining duplicated surfaces

Some content in this guide is intentionally duplicated across files and must be kept in sync manually. When any of the following surfaces changes, update **both files atomically** in the same commit:

1. **plugin roster** — the table of available plugins appears in both `README.md` and `docs/setup.md` (the Install section above). Adding, removing, or renaming a plugin requires edits to both files.
2. **CLI utilities list** — the list of `cortex-*` bin utilities is documented in `README.md`. When a new utility is added to the `cortex-core` plugin's `bin/`, update the README entry in the same commit.
3. **auth pointer** — `README.md` contains a short pointer to the authentication options; `docs/setup.md` carries the canonical auth content (Option A / Option B / Using Both). If the auth mechanics change, update the canonical content in `docs/setup.md` and refresh the README pointer to match.

---

## Dependencies

Commands shown use Homebrew (macOS); the project is primarily developed and tested on macOS.

### Required for end users

| Tool | Install |
|------|---------|
| [uv](https://docs.astral.sh/uv/) | `brew install uv` (or installed by `install.sh`) |
| Python 3.12+ | Pre-installed / `brew install python` |
| [gh](https://cli.github.com/) (GitHub CLI) | `brew install gh` (used by overnight + PR workflows) |

### Optional

| Tool | When you need it |
|------|------------------|
| terminal-notifier | macOS desktop notifications (`brew install terminal-notifier`) |
| jq | nicer JSON output (`brew install jq`) |

### Contributor-only (require a clone of cortex-command)

| Tool | Used by |
|------|---------|
| [just](https://just.systems/) | `just test`, `just dashboard`, `just validate-commit`, etc. |
| tmux | `just dashboard` and the overnight runner's detached-session model |
