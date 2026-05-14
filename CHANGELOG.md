# Changelog

All notable changes to cortex-command will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.0.0] - 2026-05-13

Closes the plugin/CLI auto-update gaps end-to-end (#213). This is a major release because the print-root JSON envelope's `version` field semantic changes (see BREAKING below) and the schema-version floor bumps 1.x → 2.0.

### Added

- **Gap A closed via auto-release workflow on push to main** — `.github/workflows/release.yml` (or equivalent) now auto-bumps the cortex-overnight plugin's `CLI_PIN` via a PAT-authenticated GitHub Actions job that tags and pushes on each merge to `main`; the existing release workflow fires on the new tag and publishes the wheel as a release asset. A defense-in-depth CI lint at `.github/workflows/release.yml` flags manual-tag emergencies where the auto-bump path was bypassed. Subsumes #212. PR-body marker convention (`release-bump: major|minor|patch`) drives the bump selection; this PR carries `release-bump: major` to land v2.0.0.
- **Gap C closed via R4 version-comparison branch** — `_ensure_cortex_installed` in `plugins/cortex-overnight/server.py` now reads `payload["version"]` (package version, PEP 440) from the print-root envelope and reinstalls when it diverges from `CLI_PIN[0]`. The branch honors the in-flight install guard via the vendored `install_guard.check_in_flight_install_core` and emits an NDJSON record with stage `version_mismatch_reinstall` on success or `version_mismatch_blocked_by_inflight_session` when an active overnight session blocks the reinstall.
- **`install_guard` vendored as a plugin sibling with dual-source parity** — `cortex_command/install_guard.py` is refactored to expose a stdlib-only `check_in_flight_install_core(active_session_path)` function; the same function is vendored byte-identically to `plugins/cortex-overnight/install_guard.py` so the plugin's PEP 723 venv can import it without depending on the installed CLI. Byte-level parity is enforced by `.githooks/pre-commit` (analogous to `BUILD_OUTPUT_PLUGINS` mirroring) and asserted by `tests/test_install_guard_parity.py` across a fixture matrix covering live-pid, dead-pid, recycled-pid, and each carve-out env var.
- **`schema_version` field on every JSON envelope** emitted by `cortex_command/` for MCP consumption — carries the M.m schema-floor semantic that the `version` field previously held; initial value `"2.0"`.

### Changed

- **Gap B closed via hatch-vcs dynamic versioning + envelope schema-major bump 1.x → 2.0** — the CLI wheel now sources its version from `hatch-vcs` (driven by the release tag), and `cortex_command/overnight/cli_handler.py:_JSON_SCHEMA_VERSION` is bumped from `"1.0"` to `"2.0"`. `docs/internals/mcp-contract.md` is rewritten to declare the envelope as carrying both `version` (package, PEP 440) and `schema_version` (schema-floor, M.m), with a new "Schema evolution log" subsection citing #213. All 17 `_emit_json` call sites in `cli_handler.py` now stamp `schema_version` instead of `version` for the schema-floor; consumer reads in `plugins/cortex-overnight/server.py` (`_check_version`, `_schema_floor_violated`) migrate to `payload.get("schema_version")`. The R13 silent short-circuit at `server.py:1499-1565` is replaced with a stderr remediation message (`Schema-floor violation: installed CLI schema_version=...`).

### Breaking

- **BREAKING: print-root envelope `version` field semantic changes from schema-major-minor (M.m) to PEP 440 package version**. `cortex --print-root --format json` previously emitted `"version": "1.1"` (the schema floor). It now emits `"version": "<package-version>"` (e.g. `"2.0.0"`, sourced from `importlib.metadata.version("cortex-command")`) and the M.m schema-floor moves to a new sibling field `"schema_version": "2.0"`. Consumers that previously parsed `version` as M.m must migrate to reading `schema_version`. The schema-major bump (1.x → 2.0) is a one-way change per `docs/internals/mcp-contract.md`'s forever-public-API rule that repurposing an existing field requires a major bump; pre-v2.0.0 plugin/CLI pairings hard-fail by design via `_check_version` and `_schema_floor_violated`. **Operator action**: bump both `cortex-command` CLI and the `cortex-overnight` plugin together to v2.0.0+ — running an older plugin against a v2.0.0+ CLI (or vice versa) is unsupported.

## [v1.0.0] - 2026-05-12

### Changed

- **cortex/ umbrella relocation** — All tool-managed paths (`lifecycle/`, `backlog/`, `requirements/`, `research/`, `retros/`, `debug/`, `.cortex-init`, `lifecycle.config.md`) have been relocated and consolidated under a single `cortex/` root directory. The repo root no longer contains scattered cortex state; everything lives under `cortex/`. This is a **breaking change** — skill prose, bin shims, the overnight runner, and the dashboard all reference the new `cortex/`-prefixed paths. Backlog YAML frontmatter fields and critical-review-residue artifacts have been bulk-migrated in the same atomic commit. `cortex init` now registers a single `cortex/` sandbox-allowWrite entry instead of the prior dual `lifecycle/sessions/` + `lifecycle/` entries.
  - **Required operator actions after pulling this commit**:
    1. Run `/plugin update cortex-core` (and `/plugin update cortex-overnight` if installed) inside Claude Code to load the updated skill prose and bin shims that reference `cortex/` paths.
    2. Run `cortex init --update` once from each project root to replace stale `lifecycle/` sandbox entries with the umbrella `cortex/` grant in `~/.claude/settings.local.json`.
  - Backlog YAML `discovery_source:`, `spec:`, `plan:`, and `research:` fields bulk-migrated to `cortex/`-prefixed paths in the same atomic relocation commit.

## [Unreleased]

### Migration note — v0.1.0 → v0.2.0

v0.1.0 users upgrading to v0.2.0 must run a full reinstall to pick up new console-script entries (R17):

```
uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v0.2.0
```

A plain `uv tool install` (without `--reinstall`) will not overwrite the existing v0.1.0 entry-points; the `--reinstall` flag is required to register the new `[project.scripts]` console-scripts added in this release.

**In-flight install-guard interaction**: the pre-install guard (`cortex/requirements/pipeline.md`, "Pre-install in-flight guard") aborts the reinstall when an active overnight session is detected (phase ≠ `complete` and `verify_runner_pid` succeeds). Do not run `uv tool install --reinstall` while an overnight session is in-flight. Carve-outs — pytest, runner-spawned children (`CORTEX_RUNNER_CHILD=1`), the dashboard process, and `cortex overnight cancel --force` — are unaffected. An emergency bypass (`CORTEX_ALLOW_INSTALL_DURING_RUN=1`) exists but should not be exported to the shell environment.

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
- **Audit-tier-divergence gate** (Phase 2 of the `read_tier` consolidation). The following contributor-tooling surfaces are retired: `bin/cortex-audit-tier-divergence`, `plugins/cortex-core/bin/cortex-audit-tier-divergence`, `tests/test_audit_tier_divergence.py`, `tests/fixtures/audit_tier/`, the pre-commit Phase 1.9 block in `.githooks/pre-commit`, and the `audit-tier-divergence` justfile recipe. **Replacement entry point**: the canonical-rule cases preserved in `tests/test_common_utils.py` pin the `read_tier` semantic; structural divergence is no longer possible because one canonical reader remains. **User-side cleanup**: none required — the gate was contributor-tooling only and had no user-facing install step.

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

[Unreleased]: https://github.com/charleshall888/cortex-command/compare/v2.0.0...HEAD
[v2.0.0]: https://github.com/charleshall888/cortex-command/releases/tag/v2.0.0
[v1.0.0]: https://github.com/charleshall888/cortex-command/releases/tag/v1.0.0
[v0.1.0]: https://github.com/charleshall888/cortex-command/releases/tag/v0.1.0
