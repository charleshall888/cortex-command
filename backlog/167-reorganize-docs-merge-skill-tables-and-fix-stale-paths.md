---
schema_version: "1"
uuid: 4da03d78-468d-4840-8161-b88b4f03727c
title: "Reorganize docs/, merge skill tables, and fix stale paths"
status: backlog
priority: medium
type: feature
tags: [repo-spring-cleaning, documentation, share-readiness, stale-paths]
areas: [docs]
created: 2026-05-05
updated: 2026-05-05
parent: "165"
blocks: []
blocked-by: []
discovery_source: research/repo-spring-cleaning/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: complex
criticality: medium
---

# Reorganize docs/, merge skill tables, and fix stale paths

## Context from discovery

`research/repo-spring-cleaning/research.md` doc inventory found three categories of work in `docs/` plus root-level `requirements/` and `CHANGELOG.md`:

1. **Surface clutter**: 14 files at `docs/` root mix installer-relevant and maintainer-internal content. Three are pure-internal (`pipeline.md` self-labels "Internal reference — not a user-facing skill" at `docs/pipeline.md:5`; `sdk.md` and `mcp-contract.md` similarly).
2. **Skill-table duplication**: `docs/agentic-layer.md` and `docs/skills-reference.md` both inventory the same skills in different formats.
3. **Stale-path drift**: small post-#117/#148 residuals and a renamed-runner terminology drift.

## Scope — `docs/internals/` move (DR-3 = Option B)

Move three pure-internal docs into a new `docs/internals/` subdirectory:
- `docs/pipeline.md` → `docs/internals/pipeline.md`
- `docs/sdk.md` → `docs/internals/sdk.md`
- `docs/mcp-contract.md` → `docs/internals/mcp-contract.md`

Leave `docs/plugin-development.md` and `docs/release-process.md` at `docs/` root (per DR-3 Option B — less deeply internal, useful for forkers and contributors who do read `docs/`). Update cross-references — including the `CLAUDE.md:34` doc-ownership rule which currently names these three docs by their old paths, and the README Documentation index in #166.

## Scope — Skill-table dedup (F-4)

`docs/skills-reference.md` is the canonical skill index (one row per skill, links to SKILL.md). `docs/agentic-layer.md` currently duplicates this. Merge: keep `skills-reference.md` as canonical; trim `agentic-layer.md` to diagrams + workflow narratives + lifecycle phase map; drop the skill-inventory tables.

## Scope — `docs/agentic-layer.md` terminology fixes

Update three occurrences of "bash runner" / "bash overnight runner" terminology to current Python CLI:
- `docs/agentic-layer.md:183`
- `docs/agentic-layer.md:187`
- `docs/agentic-layer.md:313`

## Scope — `docs/backlog.md` trim

Cut the "Global Deployment (Cross-Repo Use)" section at `docs/backlog.md:198-234` (37 lines of plugin-development content); migrate the substance to `docs/plugin-development.md` if not already there.

## Scope — Stale-path fixes (F-5)

- `requirements/pipeline.md:130` — references `claude/reference/output-floors.md` (directory retired in #117). Update to current location or remove the parenthetical.
- `CHANGELOG.md:21-22` — promises `docs/install.md` and `docs/migration-no-clone-install.md`, neither file exists. Rewrite the v0.1.0 entry to point at `docs/setup.md` (canonical).

## Scope — `docs/dashboard.md` policy (OQ §4)

Confirmed during research that no `cortex dashboard` subcommand exists in `cortex_command/cli.py:284-628`. `docs/dashboard.md:14` instructs `just dashboard`, which only works inside a clone. Pick one of three options during plan phase:

1. Ship a `cortex dashboard` verb that wraps the FastAPI server invocation (smallest installer-facing fix).
2. Flag dashboard as contributor-only-launchable; update `docs/dashboard.md` and remove from any installer-facing docs index.
3. Cut `docs/dashboard.md` from the installer-facing docs index entirely; keep file but mark contributor-tier.

## Out of scope

- README rewrite — child #166.
- Code/script junk deletion — child #168.
- Lifecycle/research archive sweep — child #169.

## Research

See `research/repo-spring-cleaning/research.md` — doc inventory tables, F-3, F-4, F-5, cross-cutting findings #2/#3/#7/#8, and OQ §4 dashboard verb policy.
