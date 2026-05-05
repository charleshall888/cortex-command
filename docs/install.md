[← Back to README](../README.md)

# Install Guide

**For:** Users installing the `cortex` CLI for the first time. **Assumes:** Claude Code is installed and working; basic terminal familiarity.

This guide covers the **no-clone install path**: a non-editable wheel install of the `cortex` CLI from a tag-pinned git URL. You do not need to clone the repository.

If you are an existing maintainer migrating from the old `~/.cortex` editable-install layout, see [migration-no-clone-install.md](migration-no-clone-install.md) instead.

---

## Quick install

The primary install path uses [`uv`](https://docs.astral.sh/uv/) to install the `cortex` CLI from a tag-pinned git URL:

```bash
uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0
```

This downloads the wheel built for tag `v0.1.0`, installs it under `~/.local/share/uv/tools/cortex-command/`, and puts the `cortex` console script on your `PATH` (typically `~/.local/bin/cortex`).

Verify the install:

```bash
cortex --version
cortex --print-root --format json
```

`cortex --print-root --format json` prints a JSON envelope with `version`, `root`, `package_root`, `remote_url`, and `head_sha` fields. The `root` field is the user's project root (resolved via `CORTEX_REPO_ROOT` or `Path.cwd()`); the `package_root` field is the package install location for diagnostic introspection.

---

## Post-install: per-repo registration

For each cortex project you work in, register the project's `lifecycle/sessions/` directory with Claude Code's sandbox so interactive sessions can write to it:

```bash
cd ~/path/to/your/project
cortex init
```

`cortex init` writes one entry per repo into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array. The project must be a git repository — `cortex init` requires `git init` to have been run first.

---

## Fallback install (no `uv` available)

If you do not have `uv` on your system, use the bootstrap script — it ensures `uv` is installed first, then runs the same `uv tool install` command:

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

The script:

1. Detects `uv` on `PATH`; if missing, installs it via the official `astral.sh/uv` curl installer.
2. Runs `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`.

After the script completes, `cortex` is on your `PATH` exactly as if you had run the `uv tool install` command directly.

---

## Bare-shell `cortex` access

The `cortex` CLI works from any shell context — there is no need to `cd` into a cloned repo. Common patterns:

- `cortex --print-root --format json` from any directory inside a cortex project: prints the project root.
- `cortex upgrade`: prints an advisory message pointing at the MCP-driven upgrade path (see below) and the manual `uv tool install --reinstall` command for the bare-shell path. The CLI itself does **not** self-upgrade — the wheel for any version `vN` can only declare "I am vN" and has no way to know about newer tags.
- `cortex --help`: lists subcommands.

To upgrade manually from a bare shell, run:

```bash
uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v0.1.0
```

Replace `v0.1.0` with the tag you want. See https://github.com/charleshall888/cortex-command/releases for the current tag list.

---

## Plugin auto-update and stale-plugin behavior

The `cortex-overnight` plugin's MCP server embeds a `CLI_PIN` constant — a tuple `(tag, schema_version)` — that pairs the plugin with a specific cortex CLI tag. The plugin drives CLI auto-update via tag bump on first MCP tool call (the upgrade arrow flows plugin → CLI, not the other way).

If you have **plugin auto-update enabled** (the default), Claude Code refreshes the plugin in the background; the next MCP tool call detects a `CLI_PIN[0]` bump and auto-installs the matching CLI tag.

If you have **plugin auto-update disabled**, the plugin's embedded `CLI_PIN` stays pinned to whatever tag was current when you installed the plugin. You get a stable plugin/CLI pair until you explicitly run:

```
/plugin update cortex-overnight@cortex-command
```

A stale plugin is the intended state under disabled auto-update — schema versions match between the embedded `CLI_PIN[1]` and the installed CLI's print-root envelope, so everything works. When you eventually update the plugin manually, the next MCP tool call will detect the new `CLI_PIN[0]` and re-install the CLI.

If you prefer to upgrade the CLI directly without going through the plugin, use the manual `uv tool install --reinstall` command from the previous section.

---

## Troubleshooting

- **`cortex: command not found`**: confirm `~/.local/bin/` is on your `PATH`. Add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc file.
- **macOS GUI-app launches Claude Code; `uv` not on PATH**: the `cortex-overnight` MCP server probes `shutil.which("uv")` at startup and refuses to start if `uv` is missing from PATH. Fix by exporting `uv`'s install location in `~/.zshenv` (which GUI apps inherit), not `~/.zshrc` (interactive shells only).
- **`cortex --print-root` fails with "Run from your cortex project root..."**: you invoked `cortex` from a directory with no `lifecycle/` AND no `backlog/`. Either `cd` into a cortex project, set `CORTEX_REPO_ROOT=/path/to/your/project`, or create a new project with `git init && cortex init`.

For the existing-maintainer migration path (existing `~/.cortex` editable install → wheel install), see [migration-no-clone-install.md](migration-no-clone-install.md).

For the release process and how new tags are cut, see [release-process.md](release-process.md).
