---
schema_version: "1"
uuid: 47fde14d-e2a0-48e3-9a56-84d4cf6018ca
title: "Relocate cortex-command artifacts under cortex/ root"
status: done
priority: medium
type: feature
created: 2026-05-11
updated: 2026-05-12
tags: [installer-experience, repo-layout, consolidate-artifacts-under-cortex-root]
complexity: complex
criticality: medium
areas: []
session_id: null
parent: 200
blocked-by: []
discovery_source: cortex/research/consolidate-artifacts-under-cortex-root/research.md
spec: cortex/lifecycle/relocate-cortex-command-artifacts-under-cortex-root/spec.md
---

# Relocate cortex-command artifacts under cortex/ root

## Problem

The seven cortex-managed paths (`lifecycle/`, `research/`, `retros/`, `backlog/`, `requirements/`, `lifecycle.config.md`, `.cortex-init`) plus `debug/` are scattered at the repo root. The contract for what's tool-managed vs project-owned is encoded across `cortex_command/init/scaffold.py:56-61` (`_CONTENT_DECLINE_TARGETS`), `cortex_command/init/handler.py:125-153` (sandbox dual-registration), and 18+ other hardcoded path sites. Users who want to gitignore tool-managed state cannot do so cleanly.

## Value

Consolidating under a single visible `cortex/` root produces one gitignore-able tree for end-users who choose it, and one mental folder for navigation. Reduces visual root clutter from seven path-roots to one. Cortex-command's own repo eats its own dogfood — 38 active + 146 archived lifecycle dirs, 10 active + ~30 archived research dirs, 195 backlog items, 5 requirements docs all move together.

## Research Context

See `research/consolidate-artifacts-under-cortex-root/research.md` for the complete investigation. Key constraints from research:

- **DR-7 operational preconditions**: single atomic commit using `git add -A` (no partial staging — running pre-commit hooks read working-copy state); fresh sandbox preflight against pre-relocation HEAD (edits to `cortex_command/overnight/runner.py` and `cortex_command/pipeline/dispatch.py` will trigger the preflight gate at `bin/cortex-check-parity:988`); no overnight session active during the commit (worktree agents writing to `lifecycle/sessions/<id>/` would lose writes during the `git mv`).
- **DR-8**: post-commit, run `cortex init --update` to refresh `~/.claude/settings.local.json` sandbox grants to the umbrella `cortex/` path (per DR-5).
- **DR-9**: tag a major-version bump and document a `/plugin update cortex-core` cutover for any installer.

Touchpoint summary (full detail in research §Codebase Analysis):

- **Sandbox + init**: `cortex_command/init/{handler.py,scaffold.py,settings_merge.py}` — 5–8 line edits.
- **Central path-computation**: `cortex_command/overnight/state.py:321` — one line; this is the most load-bearing single change.
- **Runtime path rebases**: `common.py:79-80` (use #201's upward-walking helper), `backlog/{generate_index,update_item,create_item}.py`, `overnight/{daytime_pipeline,report,backlog,orchestrator,cli_handler,feature_executor}.py`, `dashboard/{app,seed,poller,data}.py`, `discovery.py` — ~16–18 files.
- **Hooks + bin**: `hooks/cortex-scan-lifecycle.sh` (8 line edits at 26, 50, 84, 114, 328, 349, 361, 381), `claude/hooks/cortex-tool-failure-tracker.sh:42`, `.githooks/pre-commit:81`, `bin/cortex-check-parity:75,112-113`, `bin/cortex-log-invocation:46`.
- **Plugin canonical not auto-mirrored**: `plugins/cortex-overnight/server.py:2164`.
- **Encoded data migration** (one-time script): 287 lines across 4 backlog YAML fields (`discovery_source:`, `spec:`, `plan:`, `research:`), 61 `critical-review-residue.json` `"artifact"` keys, prose cross-refs in `research/<topic>/decomposed.md`.
- **`git mv` storm**: 38 + 146 lifecycle dirs, 10 + ~30 research dirs, 195 backlog files, 5 requirements files, 5 debug files, `retros/archive/`, state files.
- **Docs**: CLAUDE.md (5 refs), README, `docs/setup.md` and `docs/agentic-layer.md` (operational documentation describing literal post-init filesystem state — not just prose).
- **Tests**: 11 fixture sites across `tests/test_lifecycle_phase_parity.py`, `tests/test_resolve_backlog_item.py`.

## Out of scope

- Upward-walking project-root detection (#201) — ships separately as the foundation.
- Path-hardcoding parity gate (#203) — follow-up to prevent post-relocation drift.
- Renaming `.cortex-init` → `init.json` or `lifecycle.config.md` → `config.md` inside `cortex/` — cosmetic, deferrable (Open Question).
- `bin/cortex-check-parity:112-113` `PREFLIGHT_PATH` data-driveness — slight follow-up improvement (Open Question).
- Audit of four unaudited `claude/hooks/` scripts (`cortex-worktree-create.sh`, `cortex-worktree-remove.sh`, `cortex-skill-edit-advisor.sh`, `cortex-permission-audit-log.sh`) — small pre-flight task that the lifecycle's research phase should confirm before plan.
- External installer migration (none exist today; first external installer triggers a separate ticket per DR-7).
