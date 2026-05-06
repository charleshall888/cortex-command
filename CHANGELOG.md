# Changelog

All notable changes to cortex-command will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed

- `claude/hooks/cortex-output-filter.sh`, `claude/hooks/output-filters.conf`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/bell.ps1`. Maintainers who installed these via the retired `cortex setup` flow should grep `~/.claude/settings.json` for these script names and remove the bindings; cortex no longer deploys them.
- **`/cortex-core:fresh`, `/cortex-core:evolve`, `/cortex-core:retro` slash commands and the session-feedback loop they implemented** (formerly invoked as `/fresh`, `/evolve`, `/retro`).
  - The marker-file resume mechanism (`lifecycle/.fresh-resume`), the `/clear`-recovery prose injection, the `retro:N` statusline indicator, the `cortex init` retros/ scaffolding, the `CLAUDE_AUTOMATED_SESSION` env var, and the CLAUDE.md OQ3/OQ6 retros-citation policy clauses are all removed.
  - **This is a breaking change** — invoking `/fresh`, `/evolve`, or `/retro` post-merge produces a "skill not found" error.
  - **Replacement workflows**: use `/cortex-core:backlog add` to file an "I noticed a problem and want a ticket" item directly, or `/cortex-core:discovery` for problems with unknown root causes that need investigation.
  - **User-side cleanup for already-initialized repos** — `cortex init --update` does not auto-prune the orphaned scaffolded template, so run these once after upgrading: `rm -f lifecycle/.fresh-resume retros/.session-lessons.md retros/.retro-written-* retros/.evolve-state.json` and `rm -f retros/README.md && rmdir retros 2>/dev/null || true` (the `rmdir` is a safe no-op if the directory still has user-written content).
  - **Plugin/CLI bump timing**: per `docs/release-process.md` tag-before-coupling, the cortex-overnight plugin's `CLI_PIN` is bumped after the cortex CLI tag is pushed — running `/plugin update` between the two commits leaves you on the post-deletion plugin against pre-deletion CLI; update plugin and CLI together to avoid mid-bump skew.

## [v0.1.0] - 2026-04-29

The first tagged release of cortex-command. Establishes the no-clone install path and the tag-pinned wheel distribution model.

### Added

- **No-clone install path**: `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0` is the primary install command. Cloning the repo is no longer required for the CLI to work; cloning remains supported as the developer/forker secondary path.
- **MCP first-install hook**: the `cortex-overnight` plugin's MCP server auto-installs the cortex CLI on first tool call when missing. Reuses the flock + NDJSON failure-log + sentinel patterns from earlier upgrade-orchestration work, adapted for the pre-install context.
- **`CLI_PIN` constant**: the plugin's `server.py` embeds a `CLI_PIN = (tag, schema_version)` tuple that pairs the plugin with a specific cortex CLI tag. Plugin auto-update drives CLI auto-update via tag bump.
- **`_resolve_user_project_root()` helper**: a single source of truth for "where does the user's cortex project live?" — returns `Path(CORTEX_REPO_ROOT)` when set, else `Path.cwd()` after a sanity check that the directory contains `lifecycle/` or `backlog/`.
- **`package_root` field in `cortex --print-root --format json`**: a new field reporting the package install location, separated from the `root` field (which is now the user's project root). JSON envelope `version` bumped from `"1.0"` to `"1.1"` (additive — `1.0` consumers ignore the new field).
- **`.github/workflows/release.yml`**: tag-on-push workflow that builds the wheel via `uv build` and publishes a GitHub Release with the wheel as a release asset.
- **`docs/setup.md`**: canonical install/upgrade reference covering the `uv tool install git+<url>@<tag>` path and migration from the legacy `~/.cortex` editable install.
- **`docs/release-process.md`**: documentation of the version-bump, tag-push, and tag-before-coupling discipline.
- **`tests/test_no_clone_install.py`**: target-state test (wheel-install + `importlib.resources` smoke) and transition-mechanism test (`_ensure_cortex_installed` end-to-end with mocked subprocess).

### Changed

- **`Path(__file__)` audit**: all 6 package-internal lookups converted to `importlib.resources.files()`; all 7 user-data lookups converted to call-time `_resolve_user_project_root()` invocation. Module-level binding of user-data paths is now prohibited (enforced via AST gate in tests).
- **`cortex upgrade` is now an advisory wrapper**: the CLI cannot self-upgrade (architectural — the wheel for any version `vN` can only declare "I am vN"). `cortex upgrade` now prints two paths (MCP-driven via `/plugin update`, and manual via `uv tool install --reinstall`) and exits 0. No `git pull`, no install attempt.
- **`cortex --print-root` JSON envelope**: `root` field now consistently reports the user's project root via `_resolve_user_project_root()`. The package install location moved to a new `package_root` field. Envelope `version` bumped to `"1.1"`.
- **`install.sh`**: simplified to ensure `uv` is installed and run `uv tool install git+<url>@<tag>`. No longer clones the repo; no longer runs `uv tool install -e`.
- **`requirements/project.md`**: forkability-primary stance deprecated in favor of CLI-first identity. Cloning remains a documented secondary path for developers and forkers.
- **`CLAUDE.md`**: install command no longer references `-e` flag.

### Removed

- **`cortex_command/cli.py:_resolve_cortex_root()`** and all `CORTEX_COMMAND_ROOT` consumers in `cli.py` and `install_guard.py`.
- **`cortex_command/overnight/outcome_router.py:307-309`** — vestigial `sys.path.insert(0, str(_PROJECT_ROOT))` block. Under wheel install, `site-packages/` is on `sys.path` and the qualified imports resolve correctly without the manual insert.
- **`cortex_command/cli.py:_dispatch_upgrade`** install-mutation logic (subprocess + git operations). The function is retained as an advisory printer only.

[Unreleased]: https://github.com/charleshall888/cortex-command/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/charleshall888/cortex-command/releases/tag/v0.1.0
