---
schema_version: "1"
uuid: 824e3022-3287-4634-b771-1560ef67cc9d
title: "Manage interactive feature worktree lifecycle (creation + cleanup)"
status: backlog
priority: high
type: feature
created: 2026-05-18
updated: 2026-05-18
parent: "237"
blocked-by: []
tags: [lifecycle, worktree-interactive, daytime-swap]
areas: [skills, lifecycle, pipeline, hooks]
discovery_source: cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

## Role

Provide both ends of the long-lived interactive feature worktree lifecycle: creation when the user selects the new preflight option, and cleanup after the PR merges and the worktree is clean. Creation uses the existing `cortex-worktree-resolve` helper for canonical sandbox-safe path resolution; adopts a new prefix `interactive/{slug}` distinct from short-lived sub-agent (`worktree/agent-*`) and autonomous-daytime (`pipeline/{feature}`) worktrees; copies `.claude/settings.local.json`, symlinks `.venv`. Cleanup gates on PR-merged-and-clean state, preserves uncommitted state per the project's destructive-operations invariant, and uses `git worktree remove` for atomic directory + metadata cleanup.

## Integration

Creation is invoked by the preflight menu when option 2 is selected. Returns the canonical worktree path for downstream use by the Variant A interaction-model step. Reuses the `create_worktree` primitive's sandbox-friendly default location under `$TMPDIR` to avoid the Seatbelt `.mcp.json` deny that lives under `.claude/`. Cleanup is triggered after PR merge — candidate triggers include lifecycle complete-phase auto-cleanup (verifies merge state via `gh pr view`), a manual `cortex-cleanup-feature-worktree <slug>` recipe, or a periodic sweep. The chosen prefix `interactive/{slug}` is read by the cleanup contract to scope which worktrees it touches, and by the overnight inverse-direction guard inside the concurrency-guards ticket.

## Edges

- Bound by the sandbox-safe worktree-path contract: same-repo default lives outside the Seatbelt `.mcp.json` mandatory-deny range.
- Bound by the worktree-prefix-uniqueness contract: `interactive/{slug}` must not collide with `worktree/agent-*` or `pipeline/{feature}` namespaces.
- Bound by the `.claude/settings.local.json` and `.venv` propagation contract: a feature worktree must inherit auth and python-env config.
- Bound by the `WorktreeCreate` hook contract: manual `git worktree add` bypasses the existing notification hooks; the new step either reuses the existing hook plumbing or documents the bypass explicitly.
- Bound by the destructive-operations-preserve-uncommitted-state invariant: cleanup never destroys uncommitted work; dirty-state worktrees skip removal and surface a warning.
- Bound by the worktree-removal contract: `git worktree remove` for both directory and admin-metadata cleanup; never `rm -rf`.
- Bound by the PR-merge-state-read contract: cleanup gates on PR merged state via the github CLI.

## Touch points

- `cortex_command/pipeline/worktree.py` — `resolve_worktree_root`, `create_worktree`.
- `claude/hooks/cortex-worktree-create.sh` — existing notification hook; check whether it applies to `interactive/{slug}` prefix or needs extension.
- `claude/hooks/cortex-cleanup-session.sh` — existing SessionEnd handler; may extend or stay unchanged depending on trigger choice.
- `bin/cortex-cleanup-feature-worktree` — possible new manual-trigger recipe.
- `skills/lifecycle/references/implement.md` §1 — dispatch site for worktree creation.
- `skills/lifecycle/references/complete.md` — possible auto-trigger site for cleanup.
