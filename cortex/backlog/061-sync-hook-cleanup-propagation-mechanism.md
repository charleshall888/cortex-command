---
schema_version: "1"
uuid: c564f51c-494a-4071-b02e-6885c8fe5cc6
title: "Sync-hook cleanup propagation mechanism"
status: abandoned
priority: medium
type: task
tags: [permissions-audit, security, hooks]
created: 2026-04-10
updated: 2026-04-18
parent: null
discovery_source: "Spec #060 Non-Requirements — sync-hook propagation ratchet flagged for follow-up"
---

# Sync-hook cleanup propagation mechanism

## Context

`claude/hooks/cortex-sync-permissions.py` performs a pure union merge of `allow`/`deny`/`ask` arrays between global `~/.claude/settings.json` and project `.claude/settings.local.json`. Removing an entry from global does NOT propagate — the local copy persists forever unless manually cleaned.

Each permissions-tightening round accumulates divergence. Round 1 (054-058 epic) removed 6 entries (`bash *`, `sh *`, `source *`, `python *`, `python3 *`, `node *`). Round 2 (#060) removes 3 more (`docker *`, `make *`, `pip3 *`) plus moves 3 catch-alls (`curl *`, `npm *`, `brew *`, `tee *`) to ask. For adopters who synced any of these entries before the template tightened, the old broad allows remain effective — the "template is secure" claim is a lie for existing installs.

The 056 epic and #060 both explicitly accepted removal non-propagation as out-of-scope. This ticket is the promised follow-up to fix the ratchet.

## Proposed mechanism

Add two fields to the template + sync hook:

1. **`_globalPermissionsVersion`** in `claude/settings.json`: integer version marker. Incremented each time the template removes an entry.
2. **`_cleanupEntries`** in `claude/settings.json`: list of entries that should be removed from local `settings.local.json` at sync time. Example: `["Bash(docker *)", "Bash(make *)", "Bash(pip3 *)", "Bash(bash *)", "Bash(sh *)", ...]`.

Sync hook behavior changes:

- On SessionStart, read `_globalPermissionsVersion` from global and compare to `_localPermissionsVersion` stored in `settings.local.json`.
- If local version < global version: iterate `_cleanupEntries` and subtract each from local `allow`/`deny`/`ask` arrays. Update `_localPermissionsVersion` to match.
- If versions match: skip cleanup (idempotent).

## Acceptance criteria

- `claude/settings.json` contains `_globalPermissionsVersion` and `_cleanupEntries` fields at the top level (outside `permissions`).
- `claude/hooks/cortex-sync-permissions.py` reads both fields and performs subtraction-at-version-bump logic on top of the existing union merge.
- Test fixture: a mock `settings.local.json` containing `Bash(docker *)` and a bumped `_globalPermissionsVersion` → after hook runs, local file no longer contains `Bash(docker *)` and `_localPermissionsVersion` matches global.
- Idempotency: second hook run against the same file is a no-op.
- Backwards compatibility: existing installs that have no `_localPermissionsVersion` field are treated as version 0 → full cleanup list applied on first run.
- No regression in existing union-merge behavior for entries NOT in `_cleanupEntries`.

## Out of scope

- Cleanup of entries that were added to `settings.local.json` manually by the user (outside the template's removal intent). `_cleanupEntries` only subtracts the specific strings listed — user-added customizations survive as long as they don't string-match a cleanup entry.
- Cleanup of `~/.claude/settings.json` itself. `/setup-merge` remains additive-only; users who want to propagate removals to their global file run `just setup-force`.
- UI notification when cleanup runs. The hook is silent by design.
