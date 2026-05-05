---
schema_version: "1"
uuid: 0aac4173-e024-454b-a9c2-71bd06947190
title: "Sandbox overnight agents at the OS layer"
status: ready
priority: critical
type: epic
tags: [overnight-runner, sandbox, os-enforcement, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Sandbox overnight agents at the OS layer

## Context from discovery

Session `overnight-2026-04-21-1708` landed plan commits on local `main` because the orchestrator did `cd $REPO_ROOT && git commit` from its Bash tool — worktree isolation at the Bash-tool layer is cosmetic without OS-level enforcement. Ticket #128's git-pre-commit-hook approach (now reverted, commit `76a4730`) was selected as the original mitigation but had infrastructure-distribution costs that proved larger than expected (per-repo install, hook clobber against husky/lefthook, no fit through the cortex-overnight plugin's distribution channel).

This epic replaces ticket-128 with **per-spawn sandbox.filesystem.denyWrite at OS level** as the primary enforcement mechanism for the Bash-subprocess subset of the threat model. Discovery established documentary verification that the `@anthropic-ai/sandbox-runtime` (used by Claude Code) consumes the simplified-shape input, that the `--settings` per-spawn merge is documented to combine with discovered settings, and that `denyWrite` takes precedence over `allowWrite`. cortex's existing `dispatch.py:546` granular-shape pattern is structurally a silent no-op (V4 ticket); the orchestrator spawn at `runner.py:905` has no per-spawn sandbox today (V1 ticket, load-bearing).

## Threat-model boundary

V1 catches **Bash-tool-routed escapes only**. The following accidental-escape paths remain UNCOVERED by this epic and may be addressed by separate-track follow-ups:

- **Write/Edit tool calls** to home-repo paths execute in-process and bypass sandbox in `bypassPermissions` mode (per [anthropics/claude-code#29048])
- **MCP-server-routed subprocess writes** — MCP servers run unsandboxed at hook trust level
- **Plumbing-level commit construction** routed via the Write tool

Within this boundary, V1 directly addresses the historical session-1708 vector and extends to per-cross-repo main branches via `state.features[*].repo_path` enumeration.

## Children

- **#163** Apply per-spawn `sandbox.filesystem.denyWrite` at all overnight spawn sites (load-bearing). Covers: orchestrator spawn at `runner.py:905`, conversion of `dispatch.py:546`'s silent-no-op granular shape to documented simplified shape, fix for `feature_executor.py:603` cross-repo allowlist inversion, cross-repo deny-set enumeration via `state.features[*].repo_path`, and threat-model + design documentation in `docs/overnight-operations.md` and `docs/pipeline.md`.
- **#164** Add sandbox-violation tracker hook for PostToolUse(Bash) (observability). Includes its own docs subsection in `docs/overnight-operations.md`.

## Out of scope (post-restructure)

The original decomposition included three additional tickets that were dropped or folded:
- **Linux/bwrap preflight** — dropped (no Linux/WSL2 user base for overnight today).
- **Standalone docs ticket** — folded into #163 and #164 (each updates its own doc surface).
- **Allowlist tightening (V1c)** — dropped as a pre-filed placeholder; re-discover from #164's telemetry if data shows the deny-list is insufficient.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Notable decision records:
- DR-1 — schema shape (simplified `filesystem.denyWrite`, NOT granular `write.denyWithinAllow`)
- DR-3 — V1 scope (deny-list main + cross-repo mains via state.features enumeration)
- DR-7 (revision 3) — V1 acceptance test for `--settings` end-to-end enforcement

Reverted ticket: #128 (`wontfix` 2026-05-04). Sibling ticket: #126 (parent epic for orchestrator-worktree-escape, complete).
