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

Cortex-command ships as a Python CLI plus a set of Claude Code plugins. Installation is three steps: clone the repo, install the CLI, and enable the plugins from inside Claude.

### 1. Install the `cortex` CLI

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

This puts the `cortex` binary on your `PATH`. It clones the repo to `$HOME/.cortex` (or wherever `install.sh` places it), and is the surface you use for per-repo setup (see step 3).

### 2. Add and install the plugins from inside Claude Code

Launch `claude`, then add the marketplace once and install whichever of the four plugins you want:

```
/plugin marketplace add charleshall888/cortex-command
/plugin install cortex-interactive@cortex-command
/plugin install cortex-overnight-integration@cortex-command
/plugin install cortex-ui-extras@cortex-command
/plugin install cortex-pr-review@cortex-command
```

The four plugins are:

- **`cortex-interactive`** — core plugin: skills, hooks, statusline.
- **`cortex-overnight-integration`** — overnight runner MCP server and the `/cortex-overnight-integration:overnight` and `/cortex-overnight-integration:morning-review` skills.
- **`cortex-ui-extras`** — opt-in UI design stack.
- **`cortex-pr-review`** — opt-in PR review tooling.

#### Plugin-specific prerequisites

- **`cortex-overnight-integration`** requires the `${CORTEX_COMMAND_ROOT}` environment variable exported and pointing at your cortex-command checkout, plus the `cortex` CLI on your `PATH` (the MCP server resolves the CLI from there). Export it in your shell rc file, e.g. `export CORTEX_COMMAND_ROOT=$HOME/.cortex`.
- **`cortex-interactive`** shell-side bin shims (`cortex-jcc` and the other `cortex-*` tools) require `${CORTEX_COMMAND_ROOT}` exported as well; the in-Claude skills work without it, but the bin shims will error explicitly if it is unset.
- **`cortex-ui-extras`** has no extra prerequisites.
- **`cortex-pr-review`** has no extra prerequisites.

#### Do not add via direct `marketplace.json` URL

Use the `owner/repo` git form (`/plugin marketplace add charleshall888/cortex-command`). Do **not** add the marketplace by passing a raw `marketplace.json` URL — relative-path `source` fields only resolve against a git checkout, so the URL form silently breaks plugin installs.

#### Verify install

1. Run `/plugin list` to confirm the plugins you installed are listed.
2. If a skill is missing after install, run `/reload-plugins` to refresh the plugin metadata cache.
3. As a last resort, nuke the plugin cache and re-run `/reload-plugins`:

   ```bash
   rm -rf ~/.claude/plugins/cache
   ```

### 3. Per-repo setup

Run `cortex init` once in each repo where you want to use the overnight runner or interactive dashboard:

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

The `.cortex-init` marker records the cortex version and timestamp of the run. `lifecycle.config.md` in the repo root holds per-repo configuration overrides (see the schema section above). The `lifecycle/sessions/` write path is also registered in `~/.claude/settings.local.json` so the overnight runner can write session logs without a sandbox prompt.

Then run `/cortex-interactive:lifecycle <feature>` to begin a new feature, which produces a `lifecycle/<feature>/` directory containing the feature's lifecycle artifacts (research, spec, plan, implementation, events log). For example:

```
/cortex-interactive:lifecycle my-feature
```

This command initiates the research phase for `my-feature` and guides you through research → spec → plan → implementation → review. Running `/cortex-interactive:lifecycle my-feature` with no prior artifacts starts fresh; re-running it in a later session resumes from the current phase recorded in `lifecycle/my-feature/events.log`.

This sequence — `cortex init` followed by `/cortex-interactive:lifecycle <feature>` — is the end-to-end verification that both the CLI scaffold and the lifecycle skill are working in your environment.

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

**`statusLine.command`** (optional)

```json
"statusLine": {
  "command": "$HOME/.cortex/claude/statusline.sh"
}
```

Point to the `statusline.sh` inside your cortex-command clone (adjust the absolute path if you cloned somewhere other than `$HOME/.cortex`). This is optional — it shows cortex-specific session state in the Claude Code statusline. Skip it if you don't want that coupling.

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

## Dependencies

| Tool | Install |
|------|---------|
| [just](https://just.systems/) | `brew install just` |
| Python 3.12+ | Pre-installed / `brew install python` |
| [uv](https://docs.astral.sh/uv/) | `brew install uv` |
| [gh](https://cli.github.com/) (GitHub CLI) | `brew install gh` |
| tmux | `brew install tmux` |
| terminal-notifier (macOS) | `brew install terminal-notifier` |
| jq (optional) | `brew install jq` |
