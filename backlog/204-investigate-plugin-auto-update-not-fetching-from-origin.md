---
schema_version: "1"
uuid: 2f968fc7-982b-4748-934a-7d8febd4122d
title: "Investigate plugin auto-update not fetching from origin"
status: ready
priority: medium
type: spike
created: 2026-05-11
updated: 2026-05-11
tags: [plugin-system, claude-code, investigation]
complexity: simple
criticality: medium
areas: [plugin-distribution]
session_id: null
---

# Investigate plugin auto-update not fetching from origin

## Problem

With `autoUpdate: true` set in both `~/.claude/settings.json` and `~/.claude/plugins/known_marketplaces.json`'s cortex-command entry, the cortex-core plugin cache fell ~30 commits behind `origin/main`. Explicit invocation of `/plugin update cortex-core` updated the `lastUpdated` timestamp in `known_marketplaces.json` but did NOT advance the marketplace clone's `origin/main` ref — it stayed at `16eb3cc` (May 6) while origin had `5342192` (current).

Empirically observed during a discovery run on 2026-05-11: the discovery skill executed against the cached version `199fe13e3247`, missing several substantive overhauls that had already landed on `origin/main` (`faf7f30` R13 slug-collision, `0266152` R4 approval gate + helper module, `7338a2e` Architecture section + R15 batch-review gate, `9cc1489` decompose reframe, `a1cf28e` LEX-1 prescriptive-prose scanner).

## Value

The plugin auto-update mechanism is load-bearing for any change to skill prose, hooks, or bin scripts shipped via the cortex-core plugin. If the updater doesn't fetch from origin, then iterating on skill content during active development requires manual `git fetch` + checkout in the marketplace clone to actually exercise the latest version — which is invisible to anyone who doesn't know to do it. This also undermines the "tag a major-version bump + `/plugin update`" cutover strategy documented in `research/consolidate-artifacts-under-cortex-root/research.md` DR-9.

## Investigation Context

Empirical findings during this session:

- **Marketplace clone source**: `~/.claude/plugins/marketplaces/cortex-command/` is a `git clone` of `github.com:charleshall888/cortex-command.git`. Confirmed via `git remote -v`.
- **Cache dir naming**: `~/.claude/plugins/cache/cortex-command/cortex-core/<short-sha>/` — the SHA matches the marketplace working-tree HEAD, not `origin/main`.
- **Install record**: `installed_plugins.json` has both `version` (= cache dir name = working-tree HEAD) and `gitCommitSha` (= marketplace's `origin/main` at install time). For cortex-core: `version: "199fe13e3247"`, `gitCommitSha: "16eb3ccb3f9b..."`.
- **No version field on plugin.json**: `plugins/cortex-core/.claude-plugin/plugin.json` has only `name`, `description`, `author` — no `version`. `marketplace.json` has `"version": "1.0.0"` unchanged since install.
- **Manual fetch shows backlog**: `git -C ~/.claude/plugins/marketplaces/cortex-command/ fetch origin` produced `16eb3cc..5342192 main -> origin/main` — 30+ commits were sitting on the remote, waiting.

## Questions to Resolve

- Does `autoUpdate: true` actually poll origin on any cadence, or is it purely reactive to user commands?
- Does `/plugin update <name>` run `git fetch` in the marketplace clone, or only `git pull` against a previously-fetched state?
- Is the absence of a version-bump signal (no version change in `marketplace.json` or `plugin.json`) what's gating the updater, or is the fetch path broken regardless?
- Is this a Claude Code bug to report upstream, a config option we're missing, or expected behavior we're misunderstanding?

## Out of scope

- Fixing Claude Code internals (if a bug is identified, file upstream).
- Bumping `marketplace.json` version as a workaround — only do that after we understand whether it actually triggers a fetch (otherwise we churn the version field for no effect).
