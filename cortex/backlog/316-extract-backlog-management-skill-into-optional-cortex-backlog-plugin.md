---
schema_version: "1"
uuid: d6eeff6d-f9d2-4beb-9d4c-2f54bc39c610
title: Extract backlog management skill into optional cortex-backlog plugin
status: backlog
priority: high
type: feature
created: 2026-06-23
updated: 2026-06-23
parent: "315"
tags: ['backlog-optional-plugin']
discovery_source: cortex/research/backlog-optional-plugin/research.md
---
## Why

The backlog management skills ship inside cortex-core, so installing the harness forces the local backlog on every user — including those who track work in GitHub Issues or Jira and want nothing to do with a local `cortex/backlog/` tree.

## Role

Make the interactive backlog management surface opt-in: the `backlog` skill moves into a new `cortex-backlog` plugin that a user installs only if they want the local backlog UI. The `backlog-author` body composer stays in cortex-core because it is backend-agnostic and the external-tracker create path depends on it even when the local plugin is absent. After this lands, a user can install cortex-core without the local management commands, while the backlog engine still ships in the wheel for the consumers that need it.

## Integration

The extraction follows the established optional-plugin pattern used by the overnight plugin: canonical skill sources stay top-level and are mirrored into the plugin by the dual-source build, the plugin registers in the build-output plugin list and the marketplace manifest, and the parity linter's plugin-name set is updated so the new name is recognized. The dual-source drift gate and the plugin-list self-test bind these edits together into one commit.

## Edges

- The move is atomic: the build-output plugin list, the parity plugin-name set, the marketplace manifest, the dual-source reference map, and the plugin scaffold must all land in one commit, or the pre-commit classification guard, the plugin-list self-test, or the drift gate fails.
- The `backlog-author` composer must not move — discovery and morning-review compose ticket bodies through it on the external path even when the local plugin is absent.
- The new plugin name must not be mis-classified against the existing backlog console scripts that share its prefix; a regression guard must confirm those stay recognized as bin scripts.
- Packaging only: no behavior change to the backlog engine or to how consumers read it — that is the next ticket's scope.

## Touch points

- justfile:575 (BUILD_OUTPUT_PLUGINS), justfile:596-609 (per-plugin case arrays; remove backlog from the cortex-core array, add a cortex-backlog arm)
- cortex_command/parity_check.py:34-43 (PLUGIN_NAMES), cortex_command/parity_check.py:62-66 (RESERVED_NON_BIN_NAMES placeholder to migrate out)
- .claude-plugin/marketplace.json:12-49 (add the cortex-backlog entry — co-lands with PLUGIN_NAMES)
- tests/test_dual_source_reference_parity.py:44-58 (PLUGINS dict entry)
- plugins/cortex-overnight/.claude-plugin/plugin.json (scaffold template for the new plugin.json)
- docs/setup.md:49-60 (plugin table six to seven, OPTIONAL row), CLAUDE.md, cortex/requirements/project.md:64