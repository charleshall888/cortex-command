---
schema_version: "1"
uuid: c95205c0-a3cf-4c9c-a60d-792c7c8b2a81
title: "Rewrite README aggressively and migrate content to docs/setup.md"
status: backlog
priority: high
type: feature
tags: [repo-spring-cleaning, readme, setup, documentation, share-readiness]
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
criticality: high
---

# Rewrite README aggressively and migrate content to docs/setup.md

## Context from discovery

`research/repo-spring-cleaning/research.md` (DR-1 ratified Option B) recommends cutting `README.md` from 132 lines to ~80, optimized for end-user installers. The cut supersedes #150's restructure, which dropped Customization/Distribution/Commands moves from its scope — those H2s are the user's currently perceived "still bloated" residual.

The audience is **end-user installers** running `cortex init` to use cortex-command in their own projects, not forkers. Installer evaluation needs (value-prop, workflow shape, plugins, docs index) are met without a repo-structure tour. Benchmark tools (uv, mise, gh) at 220–280 lines do not include Distribution/Customization/Auth sections in their READMEs.

## Scope — README cuts (target ~80 lines)

Cut from current `README.md`:
- L11–29: ASCII pipeline diagram + tier/criticality legend (concept-encyclopedia content; lives in `docs/agentic-layer.md`)
- L52–54: Plugin auto-update mechanics paragraph + extras-tier callout (move to setup.md)
- L73–75: Authentication H2 (fold into Documentation index as a row)
- L77–88: What's Inside table (per OQ §6 ratified — repo-structure tour is a forker concern; CLI-bin row is a recurring drift vector unenforced by the parity check)
- L89–91: Customization H2 (move to setup.md — #150 OE-1 target, dropped)
- L93–100: Distribution H2 (move to setup.md — #150 OE-1 target, dropped)
- L102–115: Commands H2 (move to setup.md — #150 OE-1 target, dropped)

Keep (with minor trim):
- Title + 1-paragraph pitch (~6 lines; drop distribution-mechanics blur in current paragraph 3)
- Workflow narrative prose at L9 (~5 lines, link to `docs/agentic-layer.md`)
- Prerequisites (L31–35)
- Quickstart 3-step block (L36–50)
- Plugin roster table (L58–71; trim header/footer prose, keep table)
- Verification pointer (L56)
- Documentation index (L117–128; expand by 1 row to absorb Authentication pointer)
- License (L130–132)

## Scope — `docs/setup.md` migration (HARD PREREQUISITE)

Critical-review surfaced that DR-1's "content moved, not lost" claim is currently false: setup.md does not contain three operational notes from README L93–100. **Setup.md must gain the following BEFORE the README cut commit lands**, or the cut deletes content rather than relocating it:

- `uv run` operates-on-user-project semantics note (currently `README.md:97`)
- `uv tool uninstall uv` foot-gun warning (currently `README.md:98`)
- Forker fork-install URL pattern (currently `README.md:100`): `uv tool install git+https://github.com/<your-fork>/cortex-command.git@<branch-or-tag>`
- "Upgrade & maintenance" subsection covering the upgrade paths currently above-fold at `README.md:93-100`
- Customization content from current README L89–91 (settings.json ownership rule)
- Commands subsection (cortex CLI subcommand listing; backed by `cortex --help` for installers whose binary works, but reachable in setup.md for stalled-install recovery)

Verify `docs/setup.md` Troubleshooting section at L49-53 covers `cortex: command not found` AND surfaces `cortex --print-root` as the verify-install command before cutting Commands H2.

## Scope — `docs/setup.md` trim

Per F-2: collapse the 7-step `cortex init` explainer (L107-128) to a shorter form; push `lifecycle.config.md` schema (L130-160) to a reference card or compress; decide whether `CLAUDE_CONFIG_DIR` § (L352-388) stays or moves to a forker-tier section.

## Out of scope

- `docs/dashboard.md` decision (`cortex dashboard` verb policy) — child #167.
- Stale-path fixes in `docs/` and `requirements/` — child #167.
- `requirements/project.md:7` audience language — F-12 dropped post-critical-review (line already balanced).

## Acceptance signals

- README ≤ 90 lines.
- Every cut README section has its content present in `docs/setup.md` (or explicitly moved to a different doc) at the time of the README-cut commit. No content lost from the repo.
- README Documentation index has a row for Authentication and a row for Upgrade & maintenance.
- `cortex --print-root` verification command reachable from `docs/setup.md` Troubleshooting.
- Plugin roster table preserved.

## Research

See `research/repo-spring-cleaning/research.md` — DR-1, F-1, F-2, README anatomy table, #150 residual analysis, README target shape benchmarks (uv/mise/gh), and OQ §6 What's Inside resolution.
