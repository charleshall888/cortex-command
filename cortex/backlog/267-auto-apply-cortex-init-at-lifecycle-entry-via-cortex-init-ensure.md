---
schema_version: "1"
uuid: 0d2e27e0-5977-4c7e-a55a-524f117c1d3e
title: "Auto-apply cortex init at /lifecycle entry via cortex init --ensure"
status: complete
priority: medium
type: feature
created: 2026-05-26
updated: 2026-05-27
discovery_source: cortex/research/auto-init-and-update/research.md
tags: [auto-init-and-update, install, lifecycle]
areas: ['install', 'lifecycle']
complexity: complex
criticality: high
spec: cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md
---
## Why

Users currently must manually run `cortex init` to bootstrap a new repo and `cortex init --update` to refresh per-repo init artifacts after the CLI bumps its template inventory, gitignore targets, CLAUDE.md fence version, or allowWrite shape. The existing 3-layer CLI/plugin auto-update story covers the CLI binary and the plugin clone but leaves per-repo init artifacts unhandled — users on previously-initialized repos stay drifted indefinitely until they remember the manual verb. Historical churn shows roughly one schema-level change every two months over the past sixteen months that would have required users to re-run the update verb; bundling that knowledge into the user's existing engagement with cortex eliminates the manual verb from the user's mental model. Concurrently, the existing CLAUDE.md authorization-fence read-splice-write sequence lacks the flock that its sibling settings-merge writer uses; the race is latent today but is amplified by any auto-apply path that introduces concurrent-write pressure.

## Role

Make per-repo init state self-maintaining at /lifecycle entry. The user's invocation of /lifecycle becomes the trigger that bootstraps the repo if uninitialized or refreshes its artifacts if drifted, without the user having to know either init verb. The work also tightens the consumer CLAUDE.md write path against concurrent invocations so auto-apply pressure does not surface a latent race.

## Integration

A new `cortex init --ensure` flag composes the existing `cortex init` and `cortex init --update` code paths, dispatching on a hash compare between an in-process-computed installed `init_artifacts_hash` (derived from the shipped template inventory, the gitignore-targets set, the CLAUDE.md fence version constant, and the allowWrite entry shape) and the per-repo `init_artifacts_hash` newly persisted in `cortex/.cortex-init`. The /cortex-core:lifecycle skill adds a single entry-time directive at phase 1 instructing the skill to invoke `cortex init --ensure` before phase 1 work begins. The CLAUDE.md authorization-fence writer gets the same sibling-lockfile coordination the settings-merge writer already uses, so concurrent writes serialize cleanly.

## Edges

- The `init_artifacts_hash` derivation must include every input that affects user-visible init outputs; any newly-added init input that affects user-visible artifacts must be added to the hash inputs or auto-update silently misses that drift class.
- The `--ensure` flag must exit zero on hash match (no-op) and on successful apply; must exit non-zero on gate failure matching existing init verbs' exit-code contract; must not modify the repo unless a dispatch is required.
- The lifecycle wiring fires at phase 1 entry only — not mid-phase, not post-phase.
- Skills other than /lifecycle (discovery, refine, backlog, requirements-gather, requirements-write, critical-review, research) are intentionally NOT wired in this scope. The existing `cortex init --update` manual verb remains for users who hit drift via those paths. Widening the wiring is a follow-up decision once steady-state schema-bump cadence is observed.
- The CLAUDE.md flock must use the same sibling-lockfile pattern the settings-merge writer uses; must not block indefinitely under contention; must release on exception.
- Non-goal: a SessionStart probe or any blanket auto-detection surface. The user's invocation of /lifecycle is the consent signal; other repos opened in Claude Code are not touched.
- Non-goal: a manually-bumped schema-version integer constant. The content hash is mechanically derived to avoid the silent-rot failure mode of forgotten-bump releases.
- Known follow-up out of scope for this ticket: surface the installed `init_artifacts_hash` in the `cortex --print-root --format json` envelope for future external consumers (a doctor drift check, a status-line indicator, an external CI probe).

## Touch points

- `cortex_command/init/scaffold.py:367-425` — drift_files() and write_marker(); extend with init_artifacts_hash derivation and persistence, add the marker field.
- `cortex_command/init/scaffold.py:554-633` — ensure_claude_md_authorization; wrap the read-splice-write sequence in a sibling-lockfile flock matching settings_merge.py:63-88.
- `cortex_command/init/handler.py:228-298` — argparse handler; add the --ensure flag and the branch that dispatches to existing init / update paths based on hash compare.
- `cortex_command/init/settings_merge.py:63-88` — existing sibling-lockfile flock pattern to mirror in the CLAUDE.md fix.
- `skills/lifecycle/SKILL.md` — canonical source; add the one-line directive near phase 1 entry instructing the skill to invoke cortex init --ensure.
- `cortex/research/auto-init-and-update/research.md` — full design, decisions, and rejected alternatives.