---
schema_version: "1"
uuid: 69035ea8-a484-4490-b86c-51a5bd54c187
title: "Apply post-113 audit follow-ups: stale-doc cleanup, lifecycle-archive run, MCP hardening"
status: complete
priority: high
type: feature
tags: [post-113-repo-state, mcp, documentation, lifecycle, hardening]
areas: []
created: 2026-04-27
updated: 2026-04-27
lifecycle_slug: apply-post-113-audit-follow-ups-stale-doc-cleanup-lifecycle-archive-run-mcp-hardening
lifecycle_phase: complete
session_id: null
blocks: []
blocked-by: []
discovery_source: research/post-113-repo-state/research.md
complexity: complex
criticality: high
spec: lifecycle/apply-post-113-audit-follow-ups-stale-doc-cleanup-lifecycle-archive-run-mcp-hardening/spec.md
---

# Apply post-113 audit follow-ups: stale-doc cleanup, lifecycle-archive run, MCP hardening

## Context from discovery

`research/post-113-repo-state/research.md` audited the cortex-command repo state after epic #113 (CLI + plugin marketplace rebuild) closed. This ticket bundles the residual findings that don't belong to the cortex-command-plugins sunset (#147): four stale-doc cleanups, one housekeeping recipe run, and two MCP-server hardening items.

Bundled because each item is small and they share the post-113 audit context. Lifecycle plan phase should sequence the items individually; the MCP changes are the highest-value subset and should be prioritized within the ticket.

## Scope

### A. Stale post-113 path references (N3, N4, N8, N9)

Four locations still reference paths/recipes that #117 retired (symlink-based deploy into `~/.claude/`):

- **N3** — `skills/lifecycle/SKILL.md:3` (canonical source; built copy at `plugins/cortex-interactive/skills/lifecycle/SKILL.md:3` mirrors and will be regenerated). The skill description currently says *"Required before editing any file in `~/.claude/skills/` or `~/.claude/hooks/`"*. That guardrail is consumed by Claude itself when deciding whether to enter the lifecycle flow — pointing it at a non-existent post-113 path effectively disables the guardrail. Fix the canonical path; pre-commit drift will reject any fix landed only at the plugin copy.
- **N4** — `skills/diagnose/SKILL.md:148` references `~/.claude/hooks/` as illustrative context. Same dual-source caveat.
- **N8** — `README.md:152` lists `claude/reference/` in the "What's Inside" table; `docs/overnight-operations.md:11` cites `claude/reference/claude-skills.md` as the source of its progressive-disclosure model. Directory was retired in #117.
- **N9** — `justfile:62` (in the `setup-github-pat` recipe) prints `ln -s $(pwd)/claude/hooks/setup-github-pat.sh ~/.claude/hooks/setup-github-pat.sh` as a follow-up step. Symlink-based deploy is retired per `CLAUDE.md` post-113 invariant.

### B. lifecycle-archive recipe run (N6, DR-2 = A)

`justfile:229-248` defines `lifecycle-archive` but it has never been run. `lifecycle/` contains 130 directories at top level; `lifecycle/archive/` doesn't exist. Per DR-2 Option A, run the recipe once on completed-and-stale lifecycles to surface whether it works as designed; defer automation (DR-2 Option B) until pain manifests. Verify behavior on a small sample before running across the full set.

### C. MCP discovery-cache stale-on-CLI-upgrade (S1)

`plugins/cortex-overnight-integration/server.py:30-32` populates a discovery cache from `cortex --print-root` on first tool call and never expires it for the MCP-server lifetime. If the MCP server runs continuously across a `cortex` CLI upgrade (e.g., `uv tool install --reinstall`), the cached `cortex_root` may point at a removed binary. The risk window IS the project's primary use case (multi-hour autonomous overnight runs, per project north star). Promoted from second-order to high priority.

The plugin's architectural invariant ("zero `cortex_command.*` imports; sole contract is subprocess.run + versioned JSON" per `server.py:12-14`) bounds blast radius — a stale root produces a clean subprocess error, not corrupt state. But mid-overnight subprocess failures kill tool calls the orchestrator depends on, with no human to triage. Plan phase to consider: path-existence check on cached `cortex_root` before reuse, or invalidate cache on subprocess `FileNotFoundError`.

### D. MCP graceful-degrade for missing CLI tier (S5)

`cortex-overnight-integration` ships via the public marketplace; install path is one slash command. There is no "advanced user" gate. If the user installs the plugin without `uv tool install -e .`, the MCP server's subprocess calls fail with "command not found" and no install-docs pointer.

Decision: graceful with clear error. Plan phase to consider: startup check in `server.py` that detects missing `cortex` on PATH and emits a clear error pointing to install docs. Plugin should install cleanly even without the CLI tier; runtime should fail informatively when invoked.

## Out of scope

- DR-1 sunset of cortex-command-plugins (covered in #147).
- Plugin marketplace versioning (S4) — separate concern.
- Plugin-bin PATH ordering (S2) — cosmetic, no current collision risk.
- Cross-repo issue triage docs (S3) — moot post-#147 (single repo).

## Why now

A and B are documentation/housekeeping debt that misdirects users (and in N3's case, the autonomous agent itself) away from current paths. C is the highest-impact finding for the project's primary use case (multi-hour overnight) and should not wait. D is a public-marketplace contract gap that bites any non-maintainer user attempting overnight integration.

## Research

See `research/post-113-repo-state/research.md` — Net-new inconsistencies §N3/N4/N8/N9, §N6 + DR-2, Second-order effects §S1/S5, and Feasibility Assessment table for severity calibration and effort estimates.
