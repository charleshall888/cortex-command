---
schema_version: "1"
uuid: db742018-cb3e-488d-8084-688cd575e241
title: "Ship curl | sh bootstrap installer for cortex-command"
status: in_progress
priority: high
type: feature
parent: 113
tags: [distribution, install, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-24
lifecycle_slug: ship-curl-sh-bootstrap-installer-for-cortex-command
lifecycle_phase: implement
session_id: 37184ff2-e25d-4c76-80bd-3d42c986e6d3
blocks: []
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
complexity: complex
criticality: high
spec: lifecycle/ship-curl-sh-bootstrap-installer-for-cortex-command/spec.md
---

# Ship curl | sh bootstrap installer for cortex-command

## Context from discovery

The prior-art scan showed that `curl | bash` is the dominant terminal install pattern for AI coding frameworks in 2026: opencode, Goose, aider (alternate path), plus `rustup`, `nvm`, `uv`, `ollama`, `fnm` in the broader ecosystem. DR-4 recommends wrapping `uv tool install -e .` in a bootstrap so new users run one command instead of five (install prereqs, clone, install, setup).

The clone still happens — the bootstrap does it for the user at `~/.cortex` (or a path they configure). `uv tool install -e ~/.cortex` preserves editability so the clone/fork model still works.

## Scope

- Install script hosted at a stable URL (`https://cortex.sh/install` or similar) — GitHub Pages or a static asset is fine
- Script does: install `uv` if absent → `git clone ${CORTEX_REPO_URL:-github.com/charleshall888/cortex-command} ~/.cortex` → `uv tool install -e ~/.cortex` (installs the `cortex` CLI entry point to `~/.local/bin/`). **No post-install subcommand exists to call** — 117 was pure retirement, there is no `cortex setup` (see 117's spec scope-inversion note). See Open Decisions below for what the script does after `uv tool install`.
- Honors `CORTEX_REPO_URL` env var so forkers can point at their own remote before running
- Adds `cortex upgrade` subcommand to the CLI: `git -C ~/.cortex pull` — 118's author finalizes upgrade semantics
- Emits clear output on each step; exits non-zero with a useful message on failure
- Safe to re-run (idempotent)

## Open Decisions

- **What happens after `uv tool install -e ~/.cortex`?** Options: (a) script exits with a message directing the user to open Claude Code and run `/plugin marketplace add charleshall888/cortex-command` + `/plugin install cortex-interactive@cortex-command`; (b) script invokes `claude` CLI non-interactively to perform the plugin registration if `claude` is installed and a login exists; (c) script prints per-repo `cortex init` (ticket 119) instructions since per-repo setup is needed for overnight. Pick one in the spec phase. Note: cortex-command no longer ships a `cortex setup` subcommand, so there's no single command to wrap here.

## Out of scope

- Homebrew tap (ticket 125) — separate optional follow-up
- npm-global distribution (explicitly rejected in research — claude-code ships this way but the Python+bash stack doesn't warrant it)
- `dangerouslyDisableSandbox: true` handling for the bootstrap (the bootstrap runs outside Claude Code)

## Research

See `research/overnight-layer-distribution/research.md` DR-4 (install path), Setup walkthrough comparison (today vs. recommended), and `_cli-packaging-report.md`. Prior-art precedents: aider (Jan 2025 uv transition), opencode, Goose.
