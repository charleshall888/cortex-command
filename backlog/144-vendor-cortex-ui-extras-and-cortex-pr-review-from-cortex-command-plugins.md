---
schema_version: "1"
uuid: c6fb710e-139a-4eb2-9c36-4ce3a86e990f
title: "Vendor cortex-ui-extras and cortex-pr-review from cortex-command-plugins"
status: backlog
priority: high
type: feature
parent: 113
tags: [distribution, plugin, vendor, overnight-layer-distribution]
areas: [install, plugins]
created: 2026-04-24
updated: 2026-04-24
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: [122]
blocked-by: []
discovery_source: research/overnight-layer-distribution/research.md
---

# Vendor cortex-ui-extras and cortex-pr-review from cortex-command-plugins

## Context

The separate `cortex-command-plugins` repo (github.com/charleshall888/cortex-command-plugins) currently hosts three plugins: `cortex-ui-extras`, `cortex-pr-review`, and `android-dev-extras`. Folding the first two into this repo collapses the "core vs optional" marketplace split, leaving only android-dev-extras in the external repo (it stays there for now — its sync-from-upstream procedure and out-of-scope Android tooling don't fit cortex-command's framing). After this ticket, cortex-command's `plugins/` directory holds four shippable plugins and the external repo is effectively an android-only archive.

## Scope

- Copy `plugins/cortex-ui-extras/` from cortex-command-plugins into this repo at `plugins/cortex-ui-extras/`, preserving file-mode bits and `.claude-plugin/plugin.json` metadata.
- Copy `plugins/cortex-pr-review/` similarly into `plugins/cortex-pr-review/`.
- Classify both as **hand-maintained** plugins (not build-output from top-level sources). No corresponding `skills/cortex-ui-extras/` top-level source directory — the plugin tree IS the source of truth for these two.
- Update `just build-plugin` recipe (currently hardcoded to `cortex-interactive`) to use an explicit per-plugin policy: `cortex-interactive` stays build-output (rsync from top-level), `cortex-ui-extras` and `cortex-pr-review` are left untouched (no rsync, already the source of truth). Future `cortex-overnight-integration` (ticket 121) joins the build-output set when it lands.
- Update `.githooks/pre-commit` drift enforcement to match: only the build-output plugins are checked for drift; hand-maintained plugins are excluded from the diff scope (otherwise hand-edits to `plugins/cortex-ui-extras/` would falsely trip the drift check).
- Update `tests/test_drift_enforcement.sh` subtests: verify drift is detected for `cortex-interactive` edits AND verify drift is NOT detected for `cortex-ui-extras` hand-edits (positive + negative cases).
- Preserve commit authorship/attribution: copy with `git log --follow` in mind. If full history preservation matters, use `git subtree add` instead of raw copy — otherwise a single vendoring commit with a clear message referencing the source repo suffices.
- Update `README.md` to mention the four shippable plugins and which are core (cortex-interactive, cortex-overnight-integration) vs extras (cortex-ui-extras, cortex-pr-review), if the core/extras distinction is retained.

## Out of scope

- Marketplace manifest publishing (ticket 122 — depends on this ticket landing first so the manifest can list plugins that exist in the tree).
- Vendoring `android-dev-extras` (stays in cortex-command-plugins; future decision).
- Retirement of cortex-command-plugins repo (does NOT happen — the repo keeps android-dev-extras).
- `cortex-overnight-integration` plugin (ticket 121).
- Migration guide for users who had `/plugin marketplace add cortex-command-plugins` in their config (ticket 124 — they keep the old marketplace for android-dev-extras; add the new cortex-command marketplace alongside).

## Research

See `research/overnight-layer-distribution/research.md` DR-9 (originally proposed keeping the extras repo separate — this ticket supersedes that decision for the ui-extras + pr-review subset). The hand-maintained vs build-output policy is a new distinction introduced here; downstream drift enforcement (from ticket 120 Task 15) must be parameterized rather than hard-coded.
