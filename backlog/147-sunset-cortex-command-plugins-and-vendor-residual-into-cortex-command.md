---
schema_version: "1"
uuid: 098f8bb5-b6ea-46fb-95d8-14359543613e
title: "Sunset cortex-command-plugins and vendor residual plugins into cortex-command"
status: backlog
priority: medium
type: feature
tags: [distribution, plugin, marketplace, post-113-repo-state]
areas: [skills]
created: 2026-04-27
updated: 2026-04-27
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/post-113-repo-state/research.md
---

# Sunset cortex-command-plugins and vendor residual plugins into cortex-command

## Context from discovery

Discovery `research/post-113-repo-state/research.md` (DR-1, decided Option C) re-examined DR-9's premise from the original distribution research. DR-9 kept `cortex-command-plugins` separate to avoid "forcing global install of truly orthogonal skills" — but Claude Code plugins install per-plugin via `/plugin install <name>@<marketplace>`, not per-marketplace. The premise no longer carries.

Post-#144, `cortex-command-plugins` hosts only `android-dev-extras` (Android-team upstream sync) and `cortex-dev-extras` (cortex-command's own meta-tools). Cortex-command does not currently contain either plugin — vendoring is genuine work.

Findings N1, N2, N5 from the discovery (orphan marketplace entries, CI workflow validating deleted dirs, schema drift between two marketplace.json files) are recurring costs of staying split. They dissolve permanently when the sibling repo is archived rather than being individually patched.

## Scope

This ticket captures the full sunset trajectory in one place. Lifecycle plan phase should sequence the work; rough scope:

- Bring `android-dev-extras` into `cortex-command/plugins/android-dev-extras/`. Preserve the upstream sync procedure (`HOW-TO-SYNC.md`) — this is a hand-maintained plugin syncing from a Google upstream.
- Bring `cortex-dev-extras` into `cortex-command/plugins/cortex-dev-extras/` (skills: `devils-advocate`, `skill-creator`).
- Register both in `cortex-command/.claude-plugin/marketplace.json` with modern schema fields (`description`, `category`).
- Add both to the appropriate plugin classification array in `justfile` (`HAND_MAINTAINED_PLUGINS` or `BUILD_OUTPUT_PLUGINS`) so `.githooks/pre-commit` drift detection treats them correctly.
- Update `cortex-command-plugins/README.md` with a redirect notice pointing existing users to the unified marketplace.
- Update `cortex-command/README.md` plugin list to reflect the four → six plugin reality.
- Archive (or delete) the `cortex-command-plugins` repo on GitHub once parity is verified end-to-end.

## Out of scope

- Re-homing `android-dev-extras` to a Google-team upstream repo. Considered as Option D in DR-1 but rejected in favor of vendoring; can be revisited later as an independent decision.
- Plugin marketplace versioning (S4 from discovery) — separate concern, not blocking the sunset.

## Why now

DR-1's recurring cost of staying split (recurring marketplace orphans on every vendor; recurring CI drift on every directory move; schema drift between two marketplaces) accumulates indefinitely under the status quo. Each vendor pass repeats the N1+N2+N5 cleanup; sunset replaces forever-recurring sync with a one-time migration.

## Research

See `research/post-113-repo-state/research.md` DR-1 for premise re-examination, options A–E considered, quantified cost-of-split using the audit's own findings, and the decision rationale.
