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

- **Hand-maintained plugins** (`cortex-pr-review`, `cortex-ui-extras`,
  `android-dev-extras`, `cortex-dev-extras`)
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

## Setting up the dual-source hooks

Run once after clone (or when `.githooks/` changes):

    just setup-githooks

This sets `core.hooksPath` to `.githooks/`, activating both the `pre-commit`
hook and its `post-commit` companion. The pre-commit hook runs three conceptual
phases on every commit (Phase 1 contains multiple sub-phases at runtime for
source-of-truth gates); see `.githooks/pre-commit` for the full logic.

Skipping this step does not merely cost you a check — your commits will land
their canonical source edits **without** the regenerated plugin mirrors, because
the reconciliation described below is what puts those mirrors in the commit.

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

## Mirror reconciliation and the pre-commit hook

The `.githooks/pre-commit` hook keeps build-output plugin trees in sync with
top-level sources. It organizes its work into three conceptual phases (Phase 1
contains multiple sub-phases at runtime that enforce additional source-of-truth
gates; consult `.githooks/pre-commit` for the full breakdown):

1. **Name validation and source-of-truth gates** — every
   `plugins/*/.claude-plugin/plugin.json` must have a non-empty `.name`
   field, and every plugin directory must be classified in
   `BUILD_OUTPUT_PLUGINS` or `HAND_MAINTAINED_PLUGINS`. The sub-phases enforce
   additional canonical-source invariants before any build runs. This is the
   only phase that can reject a commit outright.
2. **Short-circuit decision** — checks staged paths to decide whether a rebuild
   is needed (triggered by changes under `skills/`, `bin/cortex-*`,
   `hooks/cortex-*`, `claude/hooks/cortex-*`, or any build-output plugin tree —
   deletions included).
3. **Staged-blob mirror reconciliation** — materializes the *staged* tree into a
   temp directory, runs `just build-plugin` there, and folds any mirror that
   differs into the commit, adding and removing paths as the rebuild dictates.

`.githooks/post-commit` then resyncs the real index for those paths. It exists
because `git commit --only` holds `.git/index.lock` for the whole pre-commit
hook, so only git's temporary index is writable there; without the companion,
`git status` would keep a stale mirror blob that reads as a staged reversion.

### What this means day to day

**There is no drift failure to fix.** Edit the canonical source, commit it, and
the regenerated mirrors ride along automatically — you do not run
`just build-plugin` or stage `plugins/` by hand. The hook prints the paths it
reconciled, so expect your commit to contain files you did not name in the
pathspec.

Two consequences worth knowing:

- Because the rebuild reads the **staged** blobs rather than the working tree, a
  concurrent session's uncommitted edits cannot reach your commit. This is what
  makes two sessions in one checkout safe; it is also why the hook never writes
  a source file in the shared working tree.
- If you hand-edit a file inside a build-output plugin tree, the rebuild
  regenerates it from the unchanged canonical source and your edit is discarded.
  The canonical side always wins — edit under `skills/`, `bin/cortex-*`, or the
  hook scripts instead.

## Iterating on plugin source

- For **build-output plugins**: edit under `skills/`, `bin/cortex-*`, or the
  relevant hook scripts. The pre-commit hook rebuilds the mirrors from your
  staged blobs and folds them into the commit, so a manual `just build-plugin`
  is only needed when you want the regenerated tree on disk before committing.
- For **hand-maintained plugins**: edit directly inside `plugins/<name>/`;
  no build step is required.

To pick up changes in a running Claude Code session after rebuilding, either
reinstall the plugin (`/plugin install`) or restart the session.

## Adding a deployable bin script

Some scripts (e.g. `update-item`, `create-backlog-item`,
`generate-backlog-index`) need to be available as commands from any working
directory, not just when invoked via `python3 cortex/backlog/...` from the repo
root. These are deployed via the `cortex-core` plugin's `bin/` directory.

### Per-script deployment mechanism

1. **Add the script source to the canonical top-level location** (e.g.
   `cortex/backlog/my_script.py`). Build-output plugins are assembled from these
   top-level sources by `just build-plugin`.
2. **Expose it via the `cortex-core` plugin's `bin/` directory.** The
   plugin loader adds `plugins/cortex-core/bin/` to PATH automatically, so
   the script becomes available as a command in any working directory with
   no shell configuration. Wrappers and entry points in
   `plugins/cortex-core/bin/` are the canonical surface; do not rely on
   adding scripts to a user's PATH manually.
3. **Commit the canonical source.** The pre-commit hook regenerates the
   assembled tree under `plugins/cortex-core/` from your staged blobs and
   includes it in the commit; run `just build-plugin` yourself only if you want
   to inspect the regenerated tree first.

### `Path.cwd()` vs `Path(__file__).parent` — the repo-local rule

When a script in the `cortex-core` plugin's `bin/` directory runs, `__file__`
resolves to the **real script path inside the plugin tree**. That makes
`Path(__file__).resolve().parent` safe for things like Python import-path
setup, because it correctly locates the script's own source regardless of
how the script was invoked:

```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

But `Path(__file__).parent` does **not** know which repo the user is
currently working in. If the user runs `generate-backlog-index` from a
different project, `Path(__file__).parent` still resolves to the
cortex-command repo — the wrong project's `cortex/backlog/` directory.

**Rule:** any directory that should be relative to the user's current
project (not the cortex-command checkout) must use `Path.cwd()`:

```python
BACKLOG_DIR = Path.cwd() / "backlog"
```

Use `Path(__file__).resolve().parent` only for resources that genuinely
live alongside the script in the plugin tree (e.g. sibling Python modules
imported via `sys.path`). Use `Path.cwd()` for everything that belongs to
the user's working project.
