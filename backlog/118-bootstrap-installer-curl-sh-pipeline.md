---
schema_version: "1"
uuid: db742018-cb3e-488d-8084-688cd575e241
title: "Ship curl | sh bootstrap installer for cortex-command"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, install, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [114, 117]
discovery_source: research/overnight-layer-distribution/research.md
---

# Ship curl | sh bootstrap installer for cortex-command

## Context from discovery

The prior-art scan showed that `curl | bash` is the dominant terminal install pattern for AI coding frameworks in 2026: opencode, Goose, aider (alternate path), plus `rustup`, `nvm`, `uv`, `ollama`, `fnm` in the broader ecosystem. DR-4 recommends wrapping `uv tool install -e .` in a bootstrap so new users run one command instead of five (install prereqs, clone, install, setup).

The clone still happens — the bootstrap does it for the user at `~/.cortex` (or a path they configure). `uv tool install -e ~/.cortex` preserves editability so the clone/fork model still works.

## Scope

- Install script hosted at a stable URL (`https://cortex.sh/install` or similar) — GitHub Pages or a static asset is fine
- Script does: install `uv` if absent → `git clone ${CORTEX_REPO_URL:-github.com/charleshall888/cortex-command} ~/.cortex` → `uv tool install -e ~/.cortex` → `~/.cortex/bin/cortex setup` (or whatever the installed entry point resolves to)
- Honors `CORTEX_REPO_URL` env var so forkers can point at their own remote before running
- Adds `cortex upgrade` subcommand to the CLI: `git -C ~/.cortex pull && cortex setup --verify-symlinks`
- Emits clear output on each step; exits non-zero with a useful message on failure
- Safe to re-run (idempotent)

## Out of scope

- Homebrew tap (ticket 125) — separate optional follow-up
- npm-global distribution (explicitly rejected in research — claude-code ships this way but the Python+bash stack doesn't warrant it)
- `dangerouslyDisableSandbox: true` handling for the bootstrap (the bootstrap runs outside Claude Code)

## Research

See `research/overnight-layer-distribution/research.md` DR-4 (install path), Setup walkthrough comparison (today vs. recommended), and `_cli-packaging-report.md`. Prior-art precedents: aider (Jan 2025 uv transition), opencode, Goose.
