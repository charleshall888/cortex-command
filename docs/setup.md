[← Back to README](../README.md)

# Setup Guide

**For:** Users setting up cortex-command on a new machine.  **Assumes:** Claude Code is installed and working; basic git and terminal familiarity.

> **Machine-level config** (shell, terminal, git, starship, tmux, caffeinate) lives in the [machine-config](https://github.com/charleshall888/machine-config) repo. This guide covers only cortex-command — the agentic layer.

---

## Quickstart

cortex-command ships as a set of Claude Code plugins (with a bundled `cortex` CLI). For most users, setup is two commands inside Claude Code.

**Prerequisites:** the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/overview) on your `PATH`, plus [uv](https://docs.astral.sh/uv/) (`brew install uv`) for the bundled CLI.

**1. Add the marketplace** — run inside Claude Code:

```
/plugin marketplace add charleshall888/cortex-command
```

**2. Install the plugins you want** — run `/plugin` and pick from the list, or paste:

```
/plugin install cortex-core@cortex-command
/plugin install cortex-overnight@cortex-command
```

**That's it** — the skills are live in your session. `cortex-core` is the interactive lifecycle; `cortex-overnight` adds autonomous overnight runs and auto-bundles the `cortex` CLI + an MCP server. (You never need an explicit CLI install — the overnight MCP server installs it on first use.)

**3. Set up each repo (recommended)** — in each repo you work in, run `cortex init` to scaffold the `cortex/` workspace and register its sandbox path, so the core skills (lifecycle, refine, backlog) and overnight all run cleanly:

```
cortex init
```

Then tune per-repo preferences in `cortex/lifecycle.config.md`.

---

The rest of this guide is reference material — the section titles below stay visible; expand only the ones you need.

## Plugins & advanced install

<details>
<summary>The full plugin roster, per-plugin prerequisites, and installing the <code>cortex</code> CLI directly.</summary>

The seven available plugins are:

| Plugin | Description |
|--------|-------------|
| android-dev-extras | Android development skills vendored from Google's Android Skills (Apache 2.0): R8 analyzer, edge-to-edge migration, and Android CLI orchestration |
| cortex-dev-extras | Devil's advocate inline challenge for solo deliberation |
| cortex-core | Interactive Claude Code skills, hooks, and CLI utilities from cortex-command for day-to-day development workflows |
| cortex-backlog | Interactive backlog management skill — local `cortex/backlog/` ticket files with YAML frontmatter, extracted from cortex-core so repos that track work in an external tracker can omit it |
| cortex-overnight | Integrates the cortex MCP server and overnight skill runner hooks to drive autonomous lifecycle execution |
| cortex-pr-review | Multi-agent GitHub pull request review pipeline for Claude Code |
| cortex-ui-extras | Experimental UI design skills for Claude Code interactive workflows |

Install any of them with `/plugin install <name>@cortex-command`.

**Plugin-specific prerequisites:**

- **`cortex-overnight`** requires `uv` and the `cortex` CLI on your `PATH`. The MCP server auto-installs `cortex` on first tool call when it is missing (set `CORTEX_AUTO_INSTALL=0` to opt out and receive a notice instead). It also probes for `uv` at startup and refuses to run if `uv` is not on `PATH`. macOS GUI-launched Claude Code processes do not inherit the same `PATH` as a Terminal session — if `uv` is on `PATH` in your shell but the MCP server still reports it missing, see the auto-install error message and add `uv`'s install directory to `~/.zshenv` (or `~/.bash_profile`) so GUI-launched processes pick it up.
- **`cortex-core`** shell-side bin shims (`cortex-jcc` and the other `cortex-*` tools) need to be invoked from inside a cortex project directory (one containing a `cortex/` umbrella directory), or with `CORTEX_REPO_ROOT=/path/to/your/project` exported. The in-Claude skills work without setup. The shims error explicitly with the missing-project message when neither condition holds.
- **`cortex-backlog`** is optional — install it to get the local `cortex/backlog/` interactive surface (the `/cortex-backlog:backlog` skill). It depends on `cortex-core` (the moved backlog skill resolves `backlog-author` from core); without it the backlog engine and `backlog-author` still ship in `cortex-core`.
- **`cortex-ui-extras`** and **`cortex-pr-review`** have no extra prerequisites.

**Do not add via a direct `marketplace.json` URL.** Use the `owner/repo` git form (`/plugin marketplace add charleshall888/cortex-command`). Do **not** add the marketplace by passing a raw `marketplace.json` URL — relative-path `source` fields only resolve against a git checkout, so the URL form silently breaks plugin installs.

**Installing the `cortex` CLI directly.** Most users never need this — the `cortex-overnight` MCP server auto-installs the CLI on first tool call when `cortex` is missing from `PATH`. To install it explicitly anyway:

```bash
LATEST_TAG=$(git ls-remote --tags --refs https://github.com/charleshall888/cortex-command.git \
  | awk -F/ '{print $NF}' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
uv tool install "cortex-command[all] @ git+https://github.com/charleshall888/cortex-command.git@$LATEST_TAG"
```

This installs the CLI as a non-editable `uv tool` directly from the tagged git URL — no clone is required. The `cortex` binary lands on your `PATH` (run `uv tool update-shell` once if it does not). To pin to a specific tag, replace `$LATEST_TAG` with the tag literal (for example, `v1.0.2`). If you do not have `uv` yet, the `install.sh` bootstrap installs `uv` first and runs the same resolve-then-install command:

> **Optional-dependency extras.** The base package is a lean CLI (just `pyyaml` + `psutil`); the heavier stacks are opt-in. `[all]` (used above and by the auto-installer) pulls everything. For a subset, use `[dashboard]` (the `cortex dashboard` web app) or `[overnight]` (the `cortex overnight` runner + pipeline dispatch, which pulls the Claude Agent SDK). A bare `uv tool install git+…@<tag>` with **no** extra installs only the base CLI — `cortex dashboard`/`cortex overnight` will then print an install hint rather than run.

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

Set `CORTEX_AUTO_INSTALL=0` to opt out of the MCP auto-install behavior. For upgrade paths and forker fork-install URLs, see [Upgrade & maintenance](#upgrade--maintenance) below.

</details>

## Per-repo setup (`cortex init`)

<details>
<summary>What the four <code>cortex init</code> phases do, the scaffold layout, and the <code>lifecycle.config.md</code> schema.</summary>

Run `cortex init` once in each repo where you want to use cortex. It scaffolds the `cortex/` umbrella directory that cortex skills and the overnight runner expect (`cortex/lifecycle/`, `cortex/backlog/`, `cortex/requirements/`) and registers the `cortex/` path in your Claude Code sandbox allowlist as a single grant — required for any cortex workflow (lifecycle, refine, backlog, overnight, dashboard).

`cortex init` runs four phases in order:

1. **Pre-flight validation** — resolves the git repo root via `git rev-parse --show-toplevel` (errors out if not in a git repo; refuses to run inside a submodule), checks the `cortex/` path does not resolve through a symlink (closing a TOCTOU gap with phase 4's sandbox write), and validates `~/.claude/settings.local.json` is well-formed JSON before any mutation. All read-only.
2. **Re-run guard** — checks for a `.cortex-init` marker in the repo root. If present and neither `--update` nor `--force` is passed, init declines to re-scaffold so a second accidental `cortex init` does not overwrite local customizations. Pass `--update` for an additive (no-overwrite) re-run, or `--force` to back up and overwrite.
3. **Scaffold + `.gitignore` append** — creates the `cortex/` umbrella directory and starter templates, refreshes the `cortex/.cortex-init` marker (which records the cortex version + timestamp), and idempotently appends cortex-specific ignore patterns to the repo's `.gitignore` — including an optional `cortex/` entry under a documented "uncomment to gitignore tool state" marker.
4. **Sandbox registration** — additively registers the repo's `cortex/` umbrella path under `sandbox.filesystem.allowWrite` in `~/.claude/settings.local.json` as a single entry, covering all subdirectories. Concurrent calls across repos are safe (`fcntl.flock` on a sibling lock file serializes them).

After `cortex init`, the repo contains:

```
cortex/
cortex/lifecycle/         cortex/lifecycle/README.md
cortex/lifecycle.config.md
cortex/backlog/           cortex/backlog/README.md
cortex/requirements/      cortex/requirements/project.md
cortex/.cortex-init       cortex/README.md
.gitignore   ← updated with cortex ignore entries
```

Then run `/cortex-core:lifecycle <feature>` to begin a feature — this produces `cortex/lifecycle/<feature>/` and guides you through research → spec → plan → implementation → review. Re-running it in a later session resumes from the current phase recorded in that feature's `events.log`. This sequence — `cortex init` then `/cortex-core:lifecycle <feature>` — is the end-to-end verification that both the CLI scaffold and the lifecycle skill work in your environment.

**`cortex/lifecycle.config.md` schema** — `cortex init` scaffolds this file with YAML frontmatter for project-specific overrides. The annotated, canonical field list lives in the cortex-core plugin asset `skills/lifecycle/assets/lifecycle.config.md` — a parity test (developer-run `just test`, and a blocking `validate.yml` CI step) checks its frontmatter stays byte-identical to what `cortex init` scaffolds (see ADR-0017), so that asset is the single place to read the scaffolded schema rather than re-listing it here.

Of the scaffolded keys, the ones consumed by code today are `test-command` (overnight runner test step), `commit-artifacts` (lifecycle-artifact staging), `demo-commands` (morning-review demo offer), `backlog.backend` (ticketing backend — default `cortex-backlog`, see ADR-0016), and `synthesizer_overnight_enabled` (gate for the overnight critical-tier dual-plan synthesizer). `type` is consumed too, but by skill prose rather than a parser.

The other four scaffolded keys are dormant: set in configs and read by nothing today. See the asset's inline comments for the current consumer inventory.

</details>

## Verify install

<details>
<summary>Two commands to confirm the CLI and plugins are both wired.</summary>

```bash
cortex --print-root
claude /plugin list
```

`cortex --print-root` should print a JSON object with five fields:

- **`version`** — the print-root JSON envelope schema version (currently `"1.1"`)
- **`root`** — the absolute path to your cortex project (where you ran `cortex init`, resolved via `CORTEX_REPO_ROOT` override or CWD with a `cortex/` directory sanity check)
- **`package_root`** — the absolute path to the cortex-command package install (under `uv` tool, this lives inside `~/.local/share/uv/tools/cortex-command/`)
- **`remote_url`** — the git remote URL of your project, if it is a git repository (empty string otherwise)
- **`head_sha`** — the full SHA of your project's current HEAD commit (empty string if not a git repository)

`claude /plugin list` should list the plugins you installed. If one is missing, run `/reload-plugins` inside Claude Code to refresh the plugin metadata cache.

</details>

## Troubleshooting

<details>
<summary>CLI-install and plugin-install fixes (PATH, missing project root, plugin cache).</summary>

**CLI install:**

- **`cortex: command not found`** (or `cortex --print-root` returns `command not found`): confirm `~/.local/bin/` is on your `PATH`. Add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc file, or run `uv tool update-shell` once and reload your shell. The installer prints the same `uv tool update-shell` hint in-flight (see `install.sh:48`) when it detects a missing PATH entry.
- **`cortex --print-root` fails with "Run from your cortex project root..."**: you invoked `cortex` from a directory with no `cortex/` umbrella directory. Either `cd` into a cortex project, set `CORTEX_REPO_ROOT=/path/to/your/project`, or create a new project with `git init && cortex init`.
- **macOS GUI-app launches Claude Code; `uv` not on PATH**: see the macOS GUI-launch caveat under **Plugins & advanced install** (the `cortex-overnight` prerequisites).

**Plugin install:**

1. Run `/plugin list` to confirm the plugins you installed are listed.
2. If a skill is missing after install, run `/reload-plugins` to refresh the plugin metadata cache.
3. As a last resort, nuke the plugin cache and re-run `/reload-plugins`:

   ```bash
   rm -rf ~/.claude/plugins/cache
   ```

</details>

## Authentication

<details>
<summary>API key (work / Console billing), OAuth token (personal / subscription), using both, and the one-shot bootstrap.</summary>

The overnight runner and some CLI utilities need API credentials. There are two modes depending on your account type.

**Option A: API Key (Console / Organization billing)** — for work repos billed through the Anthropic Console:

1. Create an API key at [platform.claude.com](https://platform.claude.com)
2. Store it securely:
   ```bash
   printf '%s' 'sk-ant-api03-...' > ~/.claude/work-api-key
   chmod 600 ~/.claude/work-api-key
   ```
3. Add `apiKeyHelper` to `~/.claude/settings.local.json`:
   ```json
   { "apiKeyHelper": "cat ~/.claude/work-api-key" }
   ```

This path also enables `cortex-count-tokens` and `cortex-audit-doc`, which call the Anthropic API directly.

**Option B: OAuth Token (Claude Pro / Max subscription)** — for personal repos using your Claude subscription:

1. Generate a long-lived token (valid 1 year): `claude setup-token` (opens a browser for OAuth and prints the token).
2. Store it:
   ```bash
   printf '%s' 'sk-ant-oat01-...' > ~/.claude/personal-oauth-token
   chmod 600 ~/.claude/personal-oauth-token
   ```

The overnight runner reads this file automatically when no `apiKeyHelper` is configured.

> **Note:** `CLAUDE_CODE_OAUTH_TOKEN` is recognized by Claude Code CLI (`claude -p`, Agent SDK) but **not** by the Anthropic Python SDK. Standalone utilities like `cortex-count-tokens` and `cortex-audit-doc` require an API key (Option A).

**Using both** — set `apiKeyHelper` in the work repo's `.claude/settings.local.json` and store the OAuth token at `~/.claude/personal-oauth-token`. The runner uses `apiKeyHelper` when present (work) and falls back to the OAuth token file when not (personal). See [docs/overnight-operations.md](overnight-operations.md#auth-resolution-apikeyhelper-and-env-var-fallback-order) for the full precedence chain.

**One-shot subscription bootstrap** — Pro/Max users without a Console API key can populate the OAuth token file automatically:

```bash
cortex auth bootstrap
```

This wraps `claude setup-token` (opens a browser for OAuth), captures the printed one-year token, and writes it atomically to `~/.claude/personal-oauth-token` with mode `0600`. Re-run yearly when the token expires. `ANTHROPIC_API_KEY` and `apiKeyHelper` both take precedence over the token file — run `cortex auth status` to see the resolved vector and any shadowed alternatives. Bootstrap requires an interactive terminal and a browser; for CI/headless hosts, copy a token file bootstrapped elsewhere (mode `0600`) or set `ANTHROPIC_API_KEY`. It pins Anthropic's `claude setup-token` verb via a regex and surfaces a clear error pointing at `claude --help` if a future release renames the verb.

</details>

## Upgrade & maintenance

<details>
<summary>Auto-update, the in-flight install guard, <code>uv</code> foot-guns, and the full <code>cortex</code> command list.</summary>

Turn on auto-update for the cortex-command marketplace plugins from inside Claude Code. With auto-update enabled, Claude Code refreshes the plugin in the background and the next MCP tool call detects the embedded `CLI_PIN` bump and auto-installs the matching `cortex` CLI tag via `uv tool install --reinstall`. With auto-update disabled, the plugin and CLI stay pinned to whatever pair you installed — schema versions still match, so the stale pair keeps working.

For the full design — two-layer architecture, component map, release ritual, the wheel-vs-editable and Bash-tool subprocess carve-outs, and the intent-vs-currently-wired audit — see [`docs/internals/auto-update.md`](internals/auto-update.md).

**In-flight install guard (`CORTEX_ALLOW_INSTALL_DURING_RUN`).** `cortex` aborts when an active overnight session is detected (phase != `complete` AND `verify_runner_pid` succeeds); bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). Carve-outs honored automatically: pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), dashboard, cancel-force invocation. Invoke the bypass inline, as a one-shot prefix on the install command:

```bash
CORTEX_ALLOW_INSTALL_DURING_RUN=1 uv tool install --reinstall git+<url>@<tag>
```

The inline form scopes the bypass to a single command, which is the contract — do **not** `export` it.

**`uv` foot-guns.** Do **not** run `uv tool uninstall uv` — removing `uv` via itself breaks the tool environment that hosts cortex-command (and every other `uv tool`-installed CLI). Use `brew uninstall uv` (or the upstream uninstall path) if you genuinely need to remove it. Note that `uv run` (used by the dashboard recipe and the overnight runner test step) operates on your current project venv, not cortex-command's tool venv. After the first `uv tool install`, run `uv tool update-shell` once if `cortex` is not yet on your `PATH`.

**Commands.** Once installed, the `cortex` CLI exposes:

```
cortex overnight start           # Run overnight as a detached Python process (no tmux)
cortex overnight status          # Print session status (use --format json for machine-readable)
cortex overnight cancel          # Cancel the active session
cortex overnight logs            # Read session logs
cortex overnight list-sessions   # List recent overnight session directories
cortex overnight schedule        # Schedule a future overnight run
cortex auth bootstrap            # One-shot OAuth token bootstrap (Pro/Max subscription)
cortex auth status               # Show resolved auth vector and shadowed alternatives
cortex mcp-server                # DEPRECATED — stub retained for backward compatibility
cortex dashboard                 # Launch the web dashboard for monitoring sessions
cortex upgrade                   # Reinstall the cortex CLI at the latest published tag
cortex init                      # Scaffold a repo for cortex (run once per project)
cortex --print-root              # Verify install (prints {version, root, package_root, ...})
```

Run `cortex --help` to see all subcommands.

</details>

## Optional Claude Code settings

<details>
<summary>Statusline integration (clone-only) and a <code>permissions.deny</code> safety baseline.</summary>

The following entries in `~/.claude/settings.local.json` are optional but recommended for cortex-command users.

**`statusLine.command`** (requires a clone) — shows cortex-specific session state in the Claude Code statusline:

```json
"statusLine": { "command": "/path/to/your/cortex-command/claude/statusline.sh" }
```

The script ships in the cortex-command source tree at `claude/statusline.sh`, but the wheel-install path does not extract it onto disk. To use it you need a clone of the repo (the forker path); point at the `claude/statusline.sh` inside your clone. Skip this entirely if you do not have a clone.

**`permissions.deny`** — a conservative deny list is a useful safety baseline: `sudo`, destructive `rm -rf` patterns, `git push --force` against protected branches, reads of secrets directories (`~/.ssh`, `~/.aws`, etc.). Cortex-command does not prescribe a specific list — compose your own and review each rule against your own threat model.

</details>

## macOS notifications & dependencies

<details>
<summary>Desktop notifications setup and the end-user / optional / contributor dependency tables.</summary>

**macOS notifications** — for desktop notifications when Claude Code needs attention:

1. Install terminal-notifier: `brew install terminal-notifier`
2. Enable in **System Settings > Notifications**: allow notifications for **terminal-notifier** and for **your terminal app** (plus enable "Badge app icon").

**Dependencies** — commands use Homebrew (macOS); the project is primarily developed and tested on macOS.

*Required for end users:*

| Tool | Install |
|------|---------|
| [uv](https://docs.astral.sh/uv/) | `brew install uv` (or installed by `install.sh`) |
| Python 3.12+ | Pre-installed / `brew install python` |
| [gh](https://cli.github.com/) (GitHub CLI) | `brew install gh` (used by overnight + PR workflows) |

*Optional:*

| Tool | When you need it |
|------|------------------|
| terminal-notifier | macOS desktop notifications (`brew install terminal-notifier`) |
| jq | nicer JSON output (`brew install jq`) |

*Contributor-only (require a clone of cortex-command):*

| Tool | Used by |
|------|---------|
| [just](https://just.systems/) | `just test`, `just dashboard`, `just validate-commit`, etc. |
| tmux | `just dashboard` and the overnight runner's detached-session model |

</details>
