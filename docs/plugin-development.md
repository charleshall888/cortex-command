# Plugin Development: Local Dogfooding Workflow

[← Back to README](../README.md)

This guide covers the steady-state maintainer workflow for developing,
building, and installing plugins directly from this checkout.

## Plugin classification

Every `plugins/*/` directory is classified as one of two kinds:

- **Build-output plugins** (`cortex-core`, `cortex-overnight`)
  — assembled from top-level sources (`skills/`, `bin/cortex-*`,
  `hooks/cortex-*.sh`, `claude/hooks/cortex-*.sh`) by `just build-plugin`.
  The assembled tree is committed; never edit it by hand.

- **Hand-maintained plugins** (`cortex-pr-review`, `cortex-ui-extras`)
  — edited in place inside `plugins/*/`; `just build-plugin` leaves them
  untouched.

The classification lives in `justfile` as `BUILD_OUTPUT_PLUGINS` and
`HAND_MAINTAINED_PLUGINS`. Every `plugins/*/` directory must appear in one
list or the pre-commit hook will reject the commit.

## Prerequisites

- The repo is checked out locally (commands below use `$PWD`; run them from
  the repo root, or substitute the absolute path).
- Python 3 and `uv` are installed (required by hooks and build tooling).
- `just` is installed (`brew install just`).
- You are in an active Claude Code session for the slash-command steps.

## Setting up the dual-source drift hook

Run once after clone (or when `.githooks/` changes):

    just setup-githooks

This sets `core.hooksPath` to `.githooks/` so the pre-commit hook activates.
The hook runs four phases on every commit — see `.githooks/pre-commit` for
the full logic.

## Building plugins

To regenerate all build-output plugin trees from top-level sources:

    just build-plugin

`build-plugin` copies skills, hooks, and `bin/cortex-*` entries into each
build-output plugin's `plugins/<name>/` tree. Hand-maintained plugin trees
are not touched. Run this after editing any file under `skills/`,
`bin/cortex-*`, or the relevant hook scripts.

## Registering the local marketplace

Claude Code reads `.claude-plugin/marketplace.json` at a repo root and
registers the plugins listed there. To point Claude Code at this checkout,
run inside a Claude Code session:

    /plugin marketplace add $PWD

After registration, install any plugin the manifest lists with:

    /plugin install <plugin-name>@cortex-command

For example, to install the overnight integration plugin:

    /plugin install cortex-overnight@cortex-command

## Drift detection and the pre-commit hook

The `.githooks/pre-commit` hook enforces that build-output plugin trees
stay in sync with top-level sources. Its four phases:

1. **Name validation** — every `plugins/*/.claude-plugin/plugin.json` must
   have a non-empty `.name` field, and every plugin directory must be
   classified in `BUILD_OUTPUT_PLUGINS` or `HAND_MAINTAINED_PLUGINS`.
2. **Short-circuit decision** — checks staged paths to decide whether a build
   is needed (triggered by changes under `skills/`, `bin/cortex-*`,
   `hooks/cortex-validate-commit.sh`, or any build-output plugin tree).
3. **Conditional build** — if a build is needed, runs `just build-plugin`.
4. **Drift loop** — runs `git diff` on each build-output plugin tree; fails
   if the freshly-built working tree differs from the index.

### Fixing a drift failure

If the hook reports drift, the built output does not match what is staged.
The fix is always the same:

1. Edit the top-level source (`skills/`, `bin/cortex-*`, or
   `hooks/cortex-validate-commit.sh`) — not the plugin tree directly.
2. Run `just build-plugin` to regenerate the assembled trees.
3. Stage the regenerated plugin files (`git add plugins/<name>/...`).
4. Retry the commit.

## Iterating on plugin source

- For **build-output plugins**: edit under `skills/`, `bin/cortex-*`, or the
  relevant hook scripts, then run `just build-plugin`. The pre-commit hook
  will verify the trees match before the commit lands.
- For **hand-maintained plugins**: edit directly inside `plugins/<name>/`;
  no build step is required.

To pick up changes in a running Claude Code session after rebuilding, either
reinstall the plugin (`/plugin install`) or restart the session.
