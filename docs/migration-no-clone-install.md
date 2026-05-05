[← Back to README](../README.md)

# Migration Runbook: Editable Clone Install → No-Clone Wheel Install

**For:** Existing maintainers who installed cortex-command via the legacy clone-and-`uv tool install -e` path (typically with the repo at `~/.cortex`). **Audience:** effectively the single maintainer of cortex-command, plus any early adopters who installed before the no-clone migration landed.

This runbook walks you through replacing your editable install with a wheel install pinned to a specific git tag. Your cloned repo at `~/.cortex` (or wherever you put it) is no longer required for the CLI to work — you may keep it for development or delete it.

If you are installing for the first time, follow [install.md](install.md) instead.

---

## Pre-migration checks

Before migrating, confirm the state of your existing install:

```bash
# Check the current cortex install
cortex --version
cortex --print-root --format json

# Check the uv tool list
uv tool list | grep cortex
```

The output of `uv tool list` should show `cortex-command` in editable mode (`(editable: /path/to/clone)`) if you used the legacy install. The migration uninstalls this entry and reinstalls from the git URL.

---

## Migration steps

### 1. Uninstall the editable install

```bash
uv tool uninstall cortex-command
```

This removes the editable install metadata under `~/.local/share/uv/tools/cortex-command/`. It does **not** delete your cloned repo at `~/.cortex` — that directory is unaffected.

### 2. Install from the tag-pinned git URL

```bash
uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0
```

Replace `v0.1.0` with the tag you want. Use the latest tag from https://github.com/charleshall888/cortex-command/releases unless you have a reason to pin to an older release.

### 3. Verify the install

```bash
cortex --version
cortex --print-root --format json
```

`cortex --version` should match the tag you installed (e.g., `0.1.0` for tag `v0.1.0`).

`cortex --print-root --format json` should exit 0 and emit a JSON envelope shaped like:

```json
{
  "version": "1.1",
  "root": "/path/to/your/my_cortex_project",
  "package_root": "/Users/you/.local/share/uv/tools/cortex-command/lib/python3.12/site-packages/cortex_command",
  "remote_url": "git@github.com:you/your-my_cortex_project.git",
  "head_sha": "abc123..."
}
```

The `root` field is the **user's project root** — typically `Path.cwd()` or the value of `CORTEX_REPO_ROOT` if set. The `package_root` field is the package install location, separated out for diagnostic introspection. Note: under the legacy editable install, `root` and `package_root` resolved to the same path (your clone). Under the wheel install, they are distinct — that is the intended new shape.

### 4. (Optional) Clean up the legacy clone

If you no longer need your `~/.cortex` clone for development, you may delete it:

```bash
rm -rf ~/.cortex
```

If you keep the clone for development (e.g., to make changes and re-tag), it no longer needs to be at `~/.cortex` specifically — any path works, since the CLI is now installed independently of the clone.

You may also want to remove the legacy `CORTEX_COMMAND_ROOT` env-var export from your shell rc files. The CLI no longer consults that variable; under the wheel install, the relevant override is `CORTEX_REPO_ROOT`, which points at your *user's project root*, not the cortex-command source clone.

---

## Rollback

If something goes wrong, you can roll back to the editable install:

```bash
uv tool uninstall cortex-command
cd ~/.cortex   # or wherever your clone lives
uv tool install -e .
```

The legacy install path remains functional for users who prefer it; the no-clone path is now the primary documented path but does not displace the editable install.

---

## What changed under the hood

- The CLI is now installed as a non-editable wheel, not an editable install pointing at a clone.
- `cortex upgrade` is now an **advisory wrapper**: it prints instructions and exits 0. The CLI cannot self-upgrade because the wheel for any version `vN` can only declare "I am vN" and has no way to discover newer tags. The actual upgrade arrow flows plugin → CLI via the MCP first-install hook in the `cortex-overnight` plugin.
- `cortex --print-root` JSON envelope bumped from `version: "1.0"` to `"1.1"` — additive: a new `package_root` field was added, and `root` now consistently means "user's project root" (no longer "package install location, which equaled the clone under editable mode").
- All package-internal data lookups (prompts, templates) now use `importlib.resources.files(...)` so they resolve under both editable and non-editable installs.
- All user-data lookups (lifecycle/, backlog/, sessions/) now resolve at call time via `_resolve_user_project_root()`, which respects `CORTEX_REPO_ROOT` or falls back to `Path.cwd()`.

If you hit any issue, the `cortex --print-root --format json` output is the diagnostic of record — it shows the resolved `root`, `package_root`, and any git metadata the CLI could probe.

---

## Future upgrades

After this migration completes, your normal upgrade path is one of:

- **MCP-driven (recommended)**: keep `cortex-overnight` plugin's auto-update enabled in Claude Code; the plugin's embedded `CLI_PIN[0]` tag bump triggers the MCP first-install hook on the next tool call, which auto-runs `uv tool install --reinstall git+...@<new-tag>`.
- **Manual**: run `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>` whenever you want to bump.

`cortex upgrade` from a bare shell will print these two paths as advisory output and exit 0.
