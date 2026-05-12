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

For upgrade paths and forker fork-install URLs, see [§ Upgrade & maintenance](#upgrade--maintenance) below.

#### Troubleshooting CLI install

- **`cortex: command not found`**: confirm `~/.local/bin/` is on your `PATH`. Add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc file, or run `uv tool update-shell` once.
- **`cortex --print-root` fails with "Run from your cortex project root..."**: you invoked `cortex` from a directory with no `cortex/` umbrella directory. Either `cd` into a cortex project, set `CORTEX_REPO_ROOT=/path/to/your/project`, or create a new project with `git init && cortex init`.
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
- **`cortex-core`** shell-side bin shims (`cortex-jcc` and the other `cortex-*` tools) need to be invoked from inside a cortex project directory (one containing a `cortex/` umbrella directory), or with `CORTEX_REPO_ROOT=/path/to/your/project` exported. The in-Claude skills work without setup. The shims error explicitly with the missing-project message when neither condition holds.
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

Run `cortex init` once in each repo where you want to use cortex. It scaffolds the `cortex/` umbrella directory containing subdirectories cortex skills and the overnight runner expect (`cortex/lifecycle/`, `cortex/backlog/`, `cortex/requirements/`) and registers the `cortex/` path in your Claude Code sandbox allowlist as a single grant — required for any cortex workflow (lifecycle, refine, backlog, overnight, dashboard).

```bash
cortex init
```

`cortex init` runs four phases in order:

**1. Pre-flight validation**
Resolves the git repo root via `git rev-parse --show-toplevel` (errors out if not in a git repo; refuses to run inside a submodule), checks the `cortex/` path does not resolve through a symlink (closing a TOCTOU gap with phase 4's sandbox write), and validates `~/.claude/settings.local.json` is well-formed JSON before any mutation. All read-only.

**2. Re-run guard**
Checks for a `.cortex-init` marker in the repo root. If present and neither `--update` nor `--force` is passed, init declines to re-scaffold so a second accidental `cortex init` does not overwrite local customizations. Pass `--update` for an additive (no-overwrite) re-run, or `--force` to back up and overwrite.

**3. Scaffold + `.gitignore` append**
Creates the `cortex/` umbrella directory and starter templates (`cortex/lifecycle/`, `cortex/backlog/`, `cortex/requirements/`), refreshes the `cortex/.cortex-init` marker, and idempotently appends cortex-specific ignore patterns to the repo's `.gitignore` — including an optional `cortex/` entry under a documented "uncomment to gitignore tool state" marker (running twice does not duplicate entries).

**4. Sandbox registration into `~/.claude/settings.local.json`**
Additively registers the repo's `cortex/` umbrella path under `sandbox.filesystem.allowWrite` as a single entry. This is the only write to `~/.claude/settings.local.json` that `cortex init` performs, replacing the prior dual-registration of `cortex/lifecycle/sessions/` + `cortex/lifecycle/`. Concurrent calls across repos are safe — the implementation uses `fcntl.flock` on a sibling lock file so concurrent processes serialize rather than corrupt the JSON.

#### cortex/lifecycle.config.md schema

`cortex init` scaffolds a `cortex/lifecycle.config.md` file with YAML frontmatter — project-specific overrides for the lifecycle skill and overnight runner. Six keys total, three active (consumed by code) and three advisory (scaffolded but not yet wired up):

```yaml
test-command: "just test"      # active: shell command for daytime_pipeline.py test step
commit-artifacts: true         # active: include lifecycle artifacts in staged commits
demo-commands:                 # active: morning-review demo offer (list takes precedence
  - label: "Dashboard"         #         over the legacy single-string demo-command:)
    command: "just dashboard"
type: other                    # advisory: repo classification (no consumer yet)
skip-specify: false            # advisory: skip the specify phase (not enforced yet)
skip-review: false             # advisory: skip the review phase (not enforced yet)
```

When a future ticket activates one of the advisory keys, the comment above must be updated to describe the consumer.

#### Worked example: `cortex init` + first lifecycle invocation

After installing the plugins, run `cortex init` once in your repo root:

```
cortex init
```

After `cortex init` completes, the following structure is created in your repo:

```
cortex/
cortex/lifecycle/
cortex/lifecycle/README.md
cortex/lifecycle.config.md
cortex/backlog/
cortex/backlog/README.md
cortex/requirements/
cortex/requirements/project.md
cortex/.cortex-init
cortex/README.md
.gitignore   ← updated with cortex ignore entries (optional gitignore-as-unit entry included)
```

The `cortex/.cortex-init` marker records the cortex version and timestamp of the run. `cortex/lifecycle.config.md` holds per-repo configuration overrides (see the schema section above). The repo's `cortex/` umbrella path is registered in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array as a single entry, covering all subdirectories so the overnight runner and interactive sessions can write under it without sandbox prompts.

Then run `/cortex-core:lifecycle <feature>` to begin a new feature, which produces a `cortex/lifecycle/<feature>/` directory containing the feature's lifecycle artifacts (research, spec, plan, implementation, events log). For example:

```
/cortex-core:lifecycle my-feature
```

This command initiates the research phase for `my-feature` and guides you through research → spec → plan → implementation → review. Running `/cortex-core:lifecycle my-feature` with no prior artifacts starts fresh; re-running it in a later session resumes from the current phase recorded in `cortex/lifecycle/my-feature/events.log`.

This sequence — `cortex init` followed by `/cortex-core:lifecycle <feature>` — is the end-to-end verification that both the CLI scaffold and the lifecycle skill are working in your environment.

#### Verify install

After completing the three steps above, run these two commands to confirm the cortex CLI and plugins are both wired correctly:

```bash
cortex --print-root
claude /plugin list
```

`cortex --print-root` should print a JSON object with five fields:

- **`version`** — the print-root JSON envelope schema version (currently `"1.1"`)
- **`root`** — the absolute path to your cortex project (the directory where you ran `cortex init`, resolved via `CORTEX_REPO_ROOT` env override or CWD with a `cortex/` directory sanity check)
- **`package_root`** — the absolute path to the cortex-command package install (under `uv` tool, this lives inside `~/.local/share/uv/tools/cortex-command/`); useful for diagnostic introspection
- **`remote_url`** — the git remote URL of your project, if it is a git repository (empty string otherwise)
- **`head_sha`** — the full SHA of your project's current HEAD commit (empty string if it is not a git repository)

`claude /plugin list` should list the plugins you installed from the `cortex-command` marketplace (e.g. `cortex-core`, `cortex-overnight`, etc.). If a plugin you installed is missing, run `/reload-plugins` inside Claude Code to refresh the plugin metadata cache.

---

## Upgrade & maintenance

Keeping up to date is easy as long as you turn on auto-update in the plugin marketplace.

From inside Claude Code make sure to turn on auto-updates for the cortex-command marketplace plugins. The plugin's MCP server detects the embedded `CLI_PIN` tag bump on its next tool call and updates to the matching cortex CLI tag automatically. 

The `cortex-overnight` plugin's MCP server embeds a `CLI_PIN` constant (a `(tag, schema_version)` tuple) that pairs the plugin with a specific cortex CLI tag — the upgrade arrow flows plugin → CLI, not the other way. With plugin auto-update enabled, Claude Code refreshes the plugin in the background; the next MCP tool call detects a `CLI_PIN[0]` bump and auto-installs the matching CLI tag. With auto-update disabled, the embedded `CLI_PIN` stays pinned to whatever tag was current when you installed the plugin — schema versions match between the embedded `CLI_PIN[1]` and the installed CLI's print-root envelope, so a stale-but-self-consistent plugin/CLI pair keeps working.


### `uv` foot-guns

Warning: do **not** run `uv tool uninstall uv`. Removing `uv` via itself breaks the tool environment that hosts cortex-command (and every other `uv tool`-installed CLI on your machine) — recovery requires reinstalling `uv` from scratch via `brew install uv` or the upstream installer. Use `brew uninstall uv` (or the upstream uninstall path matching your install method) if you genuinely need to remove `uv`.

When cortex internally invokes `uv run` (for example, the dashboard recipe or the daytime-pipeline test step), `uv run` operates on the user's current project venv, not cortex-command's tool venv. That means a `uv run` call inside a cortex flow uses your project's `pyproject.toml` / `uv.lock` and your project's dependencies — not anything from the cortex-command install.

After the first `uv tool install`, run `uv tool update-shell` once if `cortex` is not yet on your `PATH`.

### Commands

Once installed, the `cortex` CLI exposes these subcommands:

```
cortex overnight start     # Run overnight in detached tmux
cortex overnight status    # Print session status (use --format json for machine-readable)
cortex overnight cancel    # Cancel the active session
cortex overnight logs      # Read session logs
cortex init                # Scaffold a repo for cortex (run once per project)
cortex --print-root        # Verify install (prints {version, root, package_root, ...})
```

Run `cortex --help` to see all subcommands.

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




**`statusLine.command`** (optional, requires a clone)

```json
"statusLine": {
  "command": "/path/to/your/cortex-command/claude/statusline.sh"
}
```

This shows cortex-specific session state in the Claude Code statusline. The script ships in the cortex-command source tree at `claude/statusline.sh`, but the wheel-install path does not extract it onto disk anywhere a user can point at. To use this you need a clone of the repo (i.e., the forker path); point at the `claude/statusline.sh` inside your clone. Skip this entirely if you do not have a clone.

**`permissions.deny`**

A conservative deny list is a useful safety baseline: `sudo`, destructive `rm -rf` patterns, `git push --force` against protected branches, reads of secrets directories (`~/.ssh`, `~/.aws`, etc.). Cortex-command does not prescribe a specific list — compose your own. Do not paste any list blindly; review each rule against your own threat model.


## macOS Notifications

For desktop notifications when Claude Code needs attention:

1. Install terminal-notifier: `brew install terminal-notifier`
2. Enable in **System Settings > Notifications**:
   - **terminal-notifier**: Allow notifications
   - **Your terminal app**: Allow notifications + enable "Badge app icon"


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
