---
schema_version: "1"
uuid: 5307b13a-e41e-47b0-ac6c-06417fa26a18
title: "Repo spring cleaning: share-readiness for installer audience"
status: complete
priority: high
type: epic
tags: [repo-spring-cleaning, share-readiness, documentation, cleanup]
areas: [docs]
created: 2026-05-05
updated: 2026-05-11
blocks: []
blocked-by: []
discovery_source: cortex/research/repo-spring-cleaning/research.md
---

# Repo spring cleaning: share-readiness for installer audience

## Context

`research/repo-spring-cleaning/research.md` audited the cortex-command repo for post-plugin-shift junk, stale documentation, and a bloated README. Goal: streamlined share-ready state optimized for **end-user installers** (people running `cortex init` to use the agentic layer in their own projects), not forkers. The README rewrite supersedes #150 and is more aggressive than that ticket attempted.

Active development surfaces (overnight runner, MCP plugin, sandbox stack) verified settled. No items in `status: refined`/`in_progress`/`ready` — cleanup is collision-safe.

## Scope

Three children (166, 168, 169) cover:

- **#166**: README rewrite + `docs/setup.md` content migration + `docs/` reorganization + skill-table dedup + stale-path fixes. Aggressive README cut to ~80 lines (down from 132); move Customization, Distribution, Commands H2s out; cut What's Inside table and ASCII tier/criticality legend. Move `pipeline.md`/`sdk.md`/`mcp-contract.md` to `docs/internals/`; merge `agentic-layer.md` skill table into `skills-reference.md`. Fix `requirements/pipeline.md:130` (retired `claude/reference/`), `CHANGELOG.md:21-22` (non-existent doc references), and `docs/agentic-layer.md:183,187,313` (stale "bash runner" terminology). Hard prerequisite: setup.md must gain `uv run` semantics, uv-self-uninstall foot-gun, fork-install URL, Upgrade & maintenance subsection, Customization content, and Commands subsection BEFORE the README cut commit lands. Originally split across #166+#167; consolidated to one ticket because all changes share the docs/ domain and the README Documentation index needs the new `docs/internals/` paths in the same commit as the README rewrite (atomic landing).
- **#168**: Code/script/hook deletion. Remove stale `plugins/cortex-overnight-integration/`, completed-migration scripts under `scripts/`, post-`cortex setup`-retirement hooks (`cortex-output-filter.sh`, `cortex-sync-permissions.py`, `setup-github-pat.sh`, `bell.ps1`). Includes parallel retirement of `requirements/project.md:36` (`output-filters.conf` mention) to prevent spec/code drift.
- **#169**: Lifecycle + research archive sweep. Fix `justfile:212` archive predicate (anchored alternation regex covering YAML-form events.log entries); produce per-dir disposition table; archive ~30 lifecycle dirs and ~30 research dirs; correctly route 3 mis-classified delete candidates (#029/#035/#083 cited backlog tickets) to archive rather than delete.

## Decisions ratified during discovery (post-critical-review)

- **DR-1 = Option B** (aggressive README cut). What's Inside cut entirely.
- **DR-2 = Option C** (leave lifecycle/research dir top-level visibility alone post-archive-run). Earlier `.gitignore`-only proposal was mechanically inert on tracked files.
- **DR-3 = Option B** (move `pipeline.md`/`sdk.md`/`mcp-contract.md` into `docs/internals/`; leave `plugin-development.md` + `release-process.md` at `docs/` root).
- **DR-4 = Option A with parallel requirements retirement** (delete unwired hooks AND retire `requirements/project.md:36`).
- **OQ §6 = cut What's Inside**.
- **OQ §7 = P-A** (forker affordances stay unless they cause user-facing noise; maintainer's own development workflow is forker-tier and stays).

## Open questions deferred to lifecycle plan phases

These are user-decision items the implementing tickets resolve, not research gaps:

1. `landing-page/` disposition (keep/move/delete) — child #168.
2. `bin/cortex-validate-spec` keep-and-allowlist vs delete — child #168.
3. `cortex dashboard` verb policy: ship verb / flag contributor-only / cut `docs/dashboard.md` from installer index — child #166.

## Why now

`requirements/project.md:7` describes cortex-command as "shared publicly for others to clone or fork." User wants the repo in a state ready to share with installer audiences. Prior tickets #147/#148/#150 landed substantial cleanup but #150's plan dropped Customization/Distribution/Commands README moves; these residuals plus newly-surfaced post-shift drift produce the "still bloated" perception.

## Suggested implementation order

#166 (consolidated docs cleanup) and #168 (junk deletion) can run in parallel — different file domains. #169 (archive sweep) lands last to minimize churn from `cortex-archive-rewrite-paths` rewriting `*.md` across in-flight cleanup ticket artifacts.

## Research

See `research/repo-spring-cleaning/research.md` for: junk inventory, doc inventory + duplication analysis, README target shape (vs uv/mise/gh benchmarks), lifecycle/research archive disposition, active-vs-done verification, feasibility table, decision records, and resolved/open questions.
