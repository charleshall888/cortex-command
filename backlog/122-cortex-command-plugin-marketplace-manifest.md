---
schema_version: "1"
uuid: 7a291fcc-a9c8-4df2-97e2-81e0c01c5016
title: "Publish plugin marketplace manifest for cortex-command"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, plugin, marketplace, overnight-layer-distribution]
areas: [install]
created: 2026-04-21
updated: 2026-04-25
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [121]
discovery_source: research/overnight-layer-distribution/research.md
---

# Publish plugin marketplace manifest for cortex-command

## Context from discovery

Claude Code plugin marketplaces are git repos with a `.claude-plugin/marketplace.json`. This ticket wires up cortex-command as a single marketplace hosting four plugins — the two core plugins (`cortex-interactive`, `cortex-overnight-integration`) plus the two hand-maintained extras (`cortex-ui-extras`, `cortex-pr-review`) vendored from the old cortex-command-plugins repo in ticket 144. Users add the marketplace once with `/plugin marketplace add charleshall888/cortex-command` and install any subset with `/plugin install <name>@cortex-command`.

Supersedes DR-9: the separate extras marketplace is folded in for ui-extras and pr-review. `android-dev-extras` continues to live in the old cortex-command-plugins repo (its upstream-sync procedure and Android-specific scope don't fit here — separate decision, not this ticket). Users who want it still add `cortex-command-plugins` as a second marketplace; users who only want cortex-command content add only the one.

## Scope

- Author `.claude-plugin/marketplace.json` at this repo's root listing the four in-repo plugins with names, descriptions, and source paths: `plugins/cortex-interactive`, `plugins/cortex-overnight-integration`, `plugins/cortex-ui-extras`, `plugins/cortex-pr-review`.
- No `version` field — plugins use git-SHA versioning per research DR-4.
- Installation docs: README section covering how to add the marketplace, which plugins are core vs extras, and a one-line pointer to cortex-command-plugins for android-dev-extras.
- `docs/install.md` (or equivalent): end-to-end install walkthrough for each plugin, covering `${CORTEX_COMMAND_ROOT}` requirement for cortex-overnight-integration.
- Consider (but don't block on) submission to `anthropics/claude-plugins-official` for the core plugins so users can skip the `marketplace add` step for cortex-interactive.

## Out of scope

- Vendoring the extras plugins themselves (ticket 144 — must land first; this ticket's frontmatter reflects that via `blocked-by: [144]`).
- `cortex-overnight-integration` plugin content (ticket 121).
- Retirement or archival of cortex-command-plugins repo (does NOT happen — keeps android-dev-extras).
- Migration guide for pre-117 symlinked users or users with the old marketplace already added (ticket 124).

## Research

See `research/overnight-layer-distribution/research.md` DR-9 (partially superseded — extras folded for ui-extras/pr-review, separate for android-dev-extras), `_plugin-mcp-report.md` (marketplace + `marketplace.json` reference), and the prior-art report's note that "marketplace = git repo with a manifest" is the dominant content-distribution shape.
