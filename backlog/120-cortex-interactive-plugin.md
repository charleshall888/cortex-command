---
schema_version: "1"
uuid: 4d7e4c7d-fbd9-41ad-8df9-205c55ffe429
title: "Publish cortex-interactive plugin (non-runner skills + hooks + bin utilities)"
status: in_progress
priority: high
type: feature
parent: 113
tags: [distribution, plugin, skills, overnight-layer-distribution]
areas: [skills]
created: 2026-04-21
updated: 2026-04-23
lifecycle_slug: publish-cortex-interactive-plugin-non-runner-skills-hooks-bin-utilities
lifecycle_phase: research
session_id: 4154e3b3-6da9-4274-8053-e1113a05263c
blocks: []
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
---

# Publish cortex-interactive plugin (non-runner skills + hooks + bin utilities)

## Context from discovery

DR-2 splits the system's plugin-shippable content into two plugins at the runner boundary. This ticket is the first plugin — `cortex-interactive` — containing everything a user needs for interactive cortex-command workflows without the overnight runner. Claude Code plugins are GA and the `bin/` directory is auto-added to the Bash tool's PATH, replacing the pre-117 `just deploy-skills` + `just deploy-hooks` + `just deploy-bin` symlink architecture for this surface (117 retired those recipes; nothing auto-deploys cortex content into `~/.claude/` or `~/.local/bin/` anymore).

Dependency matrix in DR-2 identifies which skills and hooks belong in this plugin vs. `cortex-overnight-integration`. One open codebase check gates this ticket: whether `critical-review` and `morning-review` import `claude.overnight.*` at module load (→ they move to `cortex-overnight-integration`) or only when invoked through specific paths (→ stay here).

**Hook ownership post-117** (load-bearing guidance from 117's plan Task 11 Non-Req note): cortex-command's hooks split across four destinations, not just plugins:
- **Project scope (`cortex-command/.claude/settings.json`, already wired in 117)**: `cortex-validate-commit.sh`, `cortex-skill-edit-advisor.sh`. These enforce cortex-command-specific conventions and must NOT fire in unrelated repos. **Exclude from `cortex-interactive`.**
- **`cortex-overnight-integration` (ticket 121)**: `cortex-scan-lifecycle.sh`, `cortex-cleanup-session.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh`. **Exclude from `cortex-interactive`.**
- **Machine-config (not a plugin)**: `cortex-notify.sh` — machine-personal notification helper. **Exclude from any plugin.**
- **Universal utility**: `cortex-output-filter.sh` may live here or in machine-config; decide during spec phase.
- **Worktree hooks** (`cortex-worktree-create.sh`, `cortex-worktree-remove.sh`): keep their CWD-from-stdin pattern; not plugin-scoped.

## Scope

- Plugin layout under `plugins/cortex-interactive/` in this repo with `.claude-plugin/plugin.json`
- Skills included (renamed to `/cortex:*`): `commit`, `pr`, `lifecycle`, `backlog`, `requirements`, `research`, `discovery`, `refine`, `retro`, `dev`, `fresh`, `diagnose`, `evolve`
- `critical-review` and `morning-review` placement — perform the module-import check during authoring; land them here iff imports are lazy/conditional, otherwise include in ticket 121
- Hooks included (`hooks/hooks.json` manifest): per the Hook ownership post-117 split above, the plausible candidate is `cortex-output-filter.sh` (universal utility). `cortex-validate-commit.sh`, `cortex-skill-edit-advisor.sh`, `cortex-scan-lifecycle.sh`, and `cortex-tool-failure-tracker.sh` are explicitly NOT in this plugin (see the split). Spec phase resolves whether the plugin has any hooks at all or just skills+bin.
- Plugin `bin/` directory with utilities that don't require the runner: `jcc`, `update-item`, `create-backlog-item`, `generate-backlog-index`, `audit-doc`, `count-tokens`, `git-sync-rebase.sh`
- Namespace migration: every invocation path that previously used `/commit`, `/lifecycle`, etc. now uses `/cortex:commit`, `/cortex:lifecycle`
- Uses `${CLAUDE_PLUGIN_ROOT}` for hook script paths; `${CLAUDE_PLUGIN_DATA}` for any cache/venv state that must survive plugin updates

## Out of scope

- Overnight skill + runner-required hooks (ticket 121)
- Plugin marketplace manifest (ticket 122)
- Retirement of the old symlink-based deploy — completed in #117

## Research

See `research/overnight-layer-distribution/research.md` DR-2 (split shape + dependency matrix), Risks Acknowledged (import verification prereq), and `_plugin-mcp-report.md` for the full plugin component catalog. Upstream gap #9444 (no plugin dependency sharing) is acknowledged — this plugin is self-contained; any Python code it needs lives in the CLI tier.
