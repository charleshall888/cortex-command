---
schema_version: "1"
uuid: afb7fd7b-d127-46d1-a126-34c77e33b3da
title: "No-clone install for cortex CLI via MCP auto-install"
status: complete
priority: medium
type: feature
tags: [distribution, packaging, mcp, install]
created: 2026-04-24
updated: 2026-04-29
blocks: []
blocked-by: []
lifecycle_slug: non-editable-wheel-install-support-for-cortex-command
complexity: complex
criticality: high
spec: lifecycle/non-editable-wheel-install-support-for-cortex-command/spec.md
areas: [install,overnight-runner,mcp-server,docs]
session_id: null
lifecycle_phase: implement
---

# No-clone install for cortex CLI via MCP auto-install

## Context

This ticket originated as the R27 follow-up from lifecycle 115 (rebuild overnight runner under cortex CLI). 115 replaced `$_SCRIPT_DIR/../..` and `REPO_ROOT`-style path assumptions with explicit CLI path injection and `importlib.resources.files()` lookups so packages and prompt resources are now package-internal. R21 accepted the editable-install assumption for 115's scope, deferring non-editable wheel correctness to this ticket.

Refined 2026-04-29 — scope expanded beyond defensive correctness validation. The decision pulled in here: cortex CLI moves to a no-clone install path, and the cortex-overnight-integration plugin's MCP server auto-installs the CLI on first call when missing. Forkability-primary stance (project.md) is deprecated in favor of CLI-first; advanced users who fork still install via `uv tool install git+<their-fork>` but that is no longer the default path. The original 141 deliverables (importlib.resources verification, smoke test, Path(__file__) audit) become the validation gate for the new install mechanism rather than standalone deliverables — they verify that the CLI actually works under the auto-install path.

Today's install path (per epic 113, complete): `curl -fsSL https://cortex.sh/install | sh` → clones repo to `~/.cortex` → `uv tool install -e ~/.cortex`. `cortex upgrade` does `git pull` + editable reinstall. No-clone replaces this with `uv tool install git+https://github.com/charleshall888/cortex-command.git` (non-editable) and `cortex upgrade` becomes `uv tool upgrade cortex-command`. The cortex-overnight-integration plugin's MCP server, on first tool call when `cortex` is missing, runs the install command itself — so users who only interact with cortex through Claude never see an explicit install step.

## Problem

1. **Onboarding friction.** Today's flow requires installing `uv`, running the curl bootstrap, waiting for the clone, then registering the plugin marketplace, then installing plugins. Five steps for the casual case. The MCP-primary user (per ticket 146) only needs the plugin install — the CLI is an implementation detail Claude shells out to.
2. **No-clone is a prerequisite for casual / non-developer users.** Cloning a repo as a precondition for using a tool is unusual outside developer-native projects. The personal-tooling-primary stance in project.md no longer matches the long-term goal of expanding cortex to other users.
3. **Editable-install path-resolution risks.** 115's `Path(__file__)` refactor was validated under editable install only. Under non-editable wheel install (which the no-clone path requires), some `Path(__file__)` patterns silently break — e.g., `Path(__file__).parents[2]` walks into `site-packages/` instead of the user's repo root. Today there are 19 `Path(__file__)` references in `cortex_command/`; some target package-internal resources (must convert to `importlib.resources`), some target user-data paths (must continue using CWD/env, not be converted).

## Scope

### Install path migration

- Rewrite `cortex upgrade` (`cortex_command/cli.py:251-296`) to drop git-pull-and-reinstall in favor of `uv tool upgrade cortex-command`. Preserve the `--force` shim-regeneration behavior if `uv tool upgrade` does not re-emit console scripts.
- Audit and remove `cortex_root` / `~/.cortex` assumptions from the CLI. Sites: `_resolve_cortex_root()` in `cli.py`, `cortex_command/install_guard.py`, anywhere else `CORTEX_COMMAND_ROOT` is referenced for filesystem traversal.
- Convert remaining package-internal `Path(__file__)` lookups to `importlib.resources` (the original 141 audit deliverable, scoped). User-data lookups (`parents[2] / "lifecycle"`, `REPO_ROOT`-style) are explicitly preserved; they must come from CWD or explicit CLI arguments, not the package install location.
- Update `pyproject.toml` if needed to ensure `cortex_command/overnight/prompts/*.md` ships in the wheel (likely already correct per 115 spec note on hatchling defaults).

### MCP auto-install of the CLI

- `plugins/cortex-overnight-integration/server.py` learns to detect `cortex` is missing on startup or first tool call, and runs `uv tool install git+https://github.com/charleshall888/cortex-command.git` itself.
- Reuse 146's flock + skip predicates (`CORTEX_DEV_MODE=1`, dirty tree if a checkout exists at `~/.cortex` from prior install) to avoid double-installs across concurrent Claude Code sessions and to respect dev-mode escapes.
- After install, verify `cortex --help` returns 0 before delegating the user's intended tool call.
- Failure surface: structured NDJSON to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log` plus stderr line via MCP logging (mirrors 146's pattern).

### Bootstrap installer (118) treatment

- Decide in spec phase: deprecate `https://cortex.sh/install` entirely (users now install via the plugin or `uv tool install git+<url>` directly), OR keep it as a fallback for users who want bare-shell access without going through Claude Code first.
- Update `docs/install.md` and the README to lead with the plugin-install flow and document the bare-shell `uv tool install git+<url>` path as secondary.

### Validation gate (original 141 deliverables, rescoped)

- Smoke test: build the wheel via `uv build`, install via `uv tool install <wheel>` in a temp directory, invoke the MCP server in that environment, assert auto-install + `cortex overnight start --dry-run` reaches the prompt-loading code path without error.
- Verify `importlib.resources.files("cortex_command.overnight.prompts")` returns a `Traversable` and `.read_text()` works on each prompt template under non-editable install.
- Run the existing test suite under the wheel-installed CLI (not the editable source tree) at least once to catch any other path-resolution surprises.

### Documentation / project.md update

- Update `requirements/project.md` to remove the "shared publicly for others to clone or fork" framing as the primary identity. New framing: cortex ships as an installable CLI; cloning remains supported for forkers but is not the default path.
- Update the architectural-constraints section to reference the new install model and remove the editable-only assumption.

## Out of scope

- **PyPI publication** (still deferred). Once the no-clone path lands via git URL, PyPI is purely additive — anyone can `pip install cortex-command` from PyPI without breaking the git URL path. File a follow-up ticket if/when version-pinning becomes a real requirement.
- **Homebrew tap** (125 stays wontfix). macOS-only reach + sandbox-hostile post_install behavior + thin wrapper over the curl installer that this ticket deprecates.
- **Migration script for existing `~/.cortex` clones.** Existing maintainer install (the only known consumer today) can be migrated by hand: `uv tool uninstall cortex-command && uv tool install git+<url>`. If the user base grows before this lands, file a migration ticket.

## References

- Lifecycle 115 review.md (R21 deferral, R27 follow-up filing — verifies this ticket's provenance)
- Lifecycle 115 spec.md (R21: "Editable install only (documented). Non-editable wheel support is out of scope for 115; a follow-up backlog item is filed before 115 merges per R27.")
- Ticket 146 spec.md (MCP-orchestrated CLI auto-update; flock pattern at `$cortex_root/.git/cortex-update.lock` extends naturally to first-install)
- Ticket 118 spec.md (current bootstrap; clone retained intentionally for forkability — that constraint is being deprecated here)
- `cortex_command/overnight/prompts/` — primary package-resource surface that must stay resolvable under non-editable install
- `cortex_command/cli.py:251-296` — current `cortex upgrade` implementation that this ticket rewrites
- `plugins/cortex-overnight-integration/server.py` — MCP server gaining the auto-install capability
- `requirements/project.md` — forkability-primary stance being updated
