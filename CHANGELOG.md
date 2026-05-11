# Changelog

All notable changes to cortex-command will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`bin/cortex-check-events-registry` gate** and `bin/.events-registry.md` allowlist (R5/R6 of the events.log emission-discipline work). The static gate validates that every skill-prompt-emitted event name is registered with a documented consumer. Runs in `--staged` mode from `.githooks/pre-commit` Phase 1.8 (triggers only on `skills/*`, `cortex_command/overnight/prompts/*`, and the gate/registry files themselves — never on `cortex_command/**/*.py`) and in `--audit` mode via `just check-events-registry-audit` for off-critical-path deprecation-date review. Schema, scope split (`gate-enforced` vs `manual`), two-mode design, and stale-row recovery path are documented in `docs/internals/events-registry.md`.

### Changed

- **`clarify_critic` event row schema bumped v2 → v3** at `skills/refine/references/clarify-critic.md`. Row now contains only count fields (`findings_count`, `dispositions`, `applied_fixes_count`, `dismissals_count`); the `findings[]`, `dismissals[]`, and `applied_fixes[]` arrays are removed from the JSONL payload. Average row size drops from ~1,961 chars to ~250 chars. Readers tolerate v1, v1+dismissals, v2, v3, and YAML-block shapes indefinitely; archives are not rewritten.
- **`aggregate_round_context` payload schema bumped v1 → v2** at `cortex_command/overnight/orchestrator_context.py`. The `escalations.all_entries` re-inline is replaced by `escalations.prior_resolutions_by_feature: dict[str, list[dict]]` matched to the consumer's read shape. `cortex_command/overnight/prompts/orchestrator-round.md` consumes the precomputed dict via `.get(entry["feature"], [])` instead of filtering `all_entries`. **Operators: do not upgrade the CLI mid-overnight-session** — the strict-equality schema-version guard at `orchestrator_context.py` raises on producer/consumer drift; the runner's existing pre-install in-flight guard blocks the upgrade path when an overnight session is detected, but split-revert scenarios still require both files to revert together.

### Removed

- **11 dead-event emission instructions in skill prompts** (R1 of the events.log discipline work): `task_complete`, `confidence_check`, `decompose_flag`, `decompose_ack`, `decompose_drop`, `discovery_reference`, `implementation_dispatch`, `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`, `requirements_updated`. Each had zero non-test consumers in `cortex_command/`, `bin/`, `hooks/`, `claude/`, `tests/`, and skill prompts. Already-archived events.log rows containing these names remain parseable — all consumers tolerate unknown event names. The `requirements_updated` consumer scan at `skills/morning-review/references/walkthrough.md` Section 2c was removed in the same pass.
- `claude/hooks/cortex-output-filter.sh`, `claude/hooks/output-filters.conf`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/bell.ps1`. Maintainers who installed these via the retired `cortex setup` flow should grep `~/.claude/settings.json` for these script names and remove the bindings; cortex no longer deploys them.
- **`/cortex-core:fresh`, `/cortex-core:evolve`, `/cortex-core:retro` slash commands and the session-feedback loop they implemented** (formerly invoked as `/fresh`, `/evolve`, `/retro`).
  - The marker-file resume mechanism (`lifecycle/.fresh-resume`), the `/clear`-recovery prose injection, the `retro:N` statusline indicator, the `cortex init` retros/ scaffolding, the `CLAUDE_AUTOMATED_SESSION` env var, and the CLAUDE.md OQ3/OQ6 retros-citation policy clauses are all removed.
  - **This is a breaking change** — invoking `/fresh`, `/evolve`, or `/retro` post-merge produces a "skill not found" error.
  - **Replacement workflows**: use `/cortex-core:backlog add` to file an "I noticed a problem and want a ticket" item directly, or `/cortex-core:discovery` for problems with unknown root causes that need investigation.
  - **User-side cleanup for already-initialized repos** — `cortex init --update` does not auto-prune the orphaned scaffolded template, so run these once after upgrading: `rm -f lifecycle/.fresh-resume retros/.session-lessons.md retros/.retro-written-* retros/.evolve-state.json` and `rm -f retros/README.md && rmdir retros 2>/dev/null || true` (the `rmdir` is a safe no-op if the directory still has user-written content).
  - **Plugin/CLI bump timing**: per `docs/release-process.md` tag-before-coupling, the cortex-overnight plugin's `CLI_PIN` is bumped after the cortex CLI tag is pushed — running `/plugin update` between the two commits leaves you on the post-deletion plugin against pre-deletion CLI; update plugin and CLI together to avoid mid-bump skew.
- **`/cortex-core:discovery` no-topic auto-scan branch** (#193 Sub-item 3). `skills/discovery/references/auto-scan.md` is hard-deleted; the no-topic invocation path is removed from `skills/discovery/SKILL.md` description, inputs, Invocation table, and Step 1. The orphan reference in `docs/interactive-phases.md` and the `"find gaps in requirements"` pinned trigger phrase in `tests/fixtures/skill_trigger_phrases.yaml` are removed. **Replacement entry point**: use `/cortex-core:dev` for "what should I work on" / "next task" routing, or read `requirements/*.md` directly for area gap exploration. **Recovery affordance**: git tag `deprecated-auto-scan-2026-05-11` (pushed to origin) points to the pre-deletion commit and contains pre-scrub copies of `skills/discovery/references/auto-scan.md`, `skills/discovery/SKILL.md`, `tests/fixtures/skill_trigger_phrases.yaml`, and `docs/interactive-phases.md`. Restore with `git fetch --tags && git checkout deprecated-auto-scan-2026-05-11 -- <files>`. **User-side cleanup**: none required — invoking `/cortex-core:discovery` without a topic argument now halts with a routing message pointing at `/cortex-core:dev`.

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
