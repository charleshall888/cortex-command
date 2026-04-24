---
schema_version: "1"
uuid: d07b577f-e72f-4246-b0bd-19a9e36f1f08
title: "Build cortex setup subcommand and retire shareable-install scaffolding"
status: in_progress
priority: high
type: feature
parent: 113
tags: [distribution, cli, install, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-23
lifecycle_slug: build-cortex-setup-subcommand-and-retire-shareable-install-scaffolding
lifecycle_phase: research
session_id: 8810190a-9f11-494c-b526-f70dc34deb7c
blocks: []
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
complexity: complex
criticality: high
---

# Build cortex setup subcommand and retire shareable-install scaffolding

## Context from discovery

`just setup` today deploys `~/.claude/{hooks,rules,reference,notify.sh,statusline.sh}` + `~/.local/bin/*` via symlinks. DR-5 moves that deployment into an explicit `cortex setup` CLI subcommand, separating *install the tool* (package manager's job) from *deploy config into my home* (explicit user action). No package manager on the shortlist can reliably write to `$HOME` without stomping on user customizations on upgrade.

The already-shipped shareable-install epic (#003–#007) built additive install on top of `just setup` + a `/setup-merge` Claude-session skill. This ticket supersedes #006 (additive `just setup`) and #007 (`/setup-merge` skill) — their code retires as part of this epic rather than running both surfaces in parallel. #004's `cortex-` hook prefix rename and #005's `~/.claude/rules/` strategy are both still relevant and already landed.

## Scope

- `cortex setup` subcommand — deploys `~/.claude/{hooks,rules,reference,notify.sh,statusline.sh}` + `~/.local/bin/*` with the same additive semantics as today's #006 work
- `cortex setup --verify-symlinks` — idempotent re-check used by `cortex upgrade`
- `cortex setup --with-extras` — optional flag that also registers the `cortex-command-plugins` marketplace as a convenience (DR-9)
- Retire `/setup-merge` skill (#007) — behavior folds into `cortex setup`, or into a `cortex setup --merge-settings` flag that handles the `~/.claude/settings.json` deep-merge
- Retire the `just deploy-*` recipes and `just setup-force` / `just setup` modes — `justfile` can keep a `just setup` recipe that delegates to `cortex setup` for one transition release, then drop entirely
- Preserve `apiKeyHelper` stub semantics (runner reads `~/.claude/settings.json` directly — see codebase report)

## Out of scope

- Plugin install itself (tickets 120, 121, 122) — `cortex setup` does not install plugins, users run `/plugin install` themselves (or see ticket 124 migration guide)
- Bootstrap script (ticket 118) — `cortex setup` is what the bootstrap calls at the end

## Research

See `research/overnight-layer-distribution/research.md` DR-5 (canonical `~/.claude/` deployment), Risks Acknowledged ("Plugin tier depends on CLI tier", "#003–#007 is complete"), and `_codebase-report.md` for the install footprint today.
