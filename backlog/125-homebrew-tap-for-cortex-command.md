---
schema_version: "1"
uuid: 8ca55836-e562-400e-952b-1d91b23fe2f8
title: "Homebrew tap as thin wrapper around the curl installer"
status: backlog
priority: low
type: feature
parent: 113
tags: [distribution, homebrew, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [118]
discovery_source: research/overnight-layer-distribution/research.md
---

# Homebrew tap as thin wrapper around the curl installer

## Context from discovery

Homebrew is a familiar discovery surface for macOS users but is sandbox-hostile for writing to `$HOME` (formula `post_install` re-runs on every `brew upgrade` and would clobber user customizations). DR-4 recommends a Homebrew tap that wraps the bootstrap installer from ticket 118 — the formula doesn't own `~/.claude/` deployment, it just runs the curl script once and prints `caveats` telling the user to run `cortex setup`. This gives brew users the familiar `brew install` entry without the sandbox-hostile `post_install` pitfall.

Low priority because the bootstrap installer already covers macOS via `curl | sh`; brew is discoverability, not a functional win.

## Scope

- Separate GitHub repo `charleshall888/homebrew-cortex-command` (or similar) — Homebrew requires the tap to be in a repo named `homebrew-<tapname>`
- Formula that runs `curl -fsSL https://cortex.sh/install | sh` in `install do system "..."` block
- `caveats` block directing users to run `cortex setup` after install
- Upgrade path: `brew upgrade` re-runs the curl script; `cortex upgrade` continues to be the in-CLI upgrade verb
- README pointing users at `cortex-command` as the source of truth

## Out of scope

- Formula that handles `~/.claude/` deployment directly (explicitly rejected — see DR-4 sharp edges)
- Linux package managers (apt/deb/rpm) — no prior art in this space; cortex-command user base doesn't justify
- Shipping cortex-command as a Python formula with `virtualenv_install_with_resources` — more complexity than a curl wrapper, no added value

## Research

See `research/overnight-layer-distribution/research.md` DR-4 trade-offs (Homebrew tap as thin wrapper), `_cli-packaging-report.md` Homebrew section (specifically the `post_install` runs on every `brew upgrade` problem), and the prior-art scan ("no surveyed project ships primarily via Homebrew").
