---
schema_version: "1"
uuid: a3e827af-79f9-4bbb-ac30-53c20fc4532e
title: "Tighten overnight sandbox from deny-list to narrower allowOnly"
status: deferred
priority: low
type: feature
parent: 162
tags: [overnight-runner, sandbox, hardening]
areas: [overnight-runner]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [163, 164]
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Tighten overnight sandbox from deny-list to narrower allowOnly

## Status: deferred

Defer until #164's observability data demonstrates a clear need to tighten beyond V1's deny-list. Filing as a placeholder per discovery's "sparse-allowlist evolution" follow-up category.

## Context from discovery

#163 ships V1a (deny-list main-only via `sandbox.filesystem.denyWrite`). The discovery's feasibility table (`research/sandbox-overnight-child-agents/research.md`) lists three candidate shapes for V1:

- **V1a (deny-list)**: shipped in #163. Tiny diff, zero migration risk for legitimate worktree commits, directly addresses session-1708. Doesn't constrain agent edits to non-`.git` working-tree files in the home repo.
- **V1b (full allowOnly)**: maximum constraint but brittle — every legitimate path must be enumerated; missing entries break commits silently.
- **V1c (hybrid)**: keeps allowOnly for worktree paths but adds explicit deny-list for high-risk home-repo paths.

V1c's tightening pays a real engineering cost (allowlist enumeration burden, edge-case discovery during legitimate sub-branch creation, ref-name patterns) and is only justified if observed escape attempts demonstrate the deny-list's gaps.

## Findings from discovery

- Per `git-worktree(1)` and empirical tracing, a normal worktree commit writes to a constrained set of paths (objects, refs/heads/<branch>, logs/refs/heads/<branch>, worktrees/<id>/* per-worktree state). An allowOnly enumeration is feasible but requires care for edge cases like sub-branch creation (`git switch -c pipeline/<sub>`), stash, tag creation.
- `git pack-refs`, `git fsck`, `git repack`, `git prune` are NOT invoked from agent context for a single feature commit, so an allowOnly that omits these is safe.
- `denyWrite > allowWrite` precedence is documented (per https://code.claude.com/docs/en/sandboxing) — V1c's hybrid shape works correctly with the merge.

## Value

If #164's telemetry shows escape attempts beyond the deny-list-protected paths (e.g., agents writing to non-`.git` home-repo files, or attempting refs other than `main`/`HEAD`/`packed-refs`), the deny-list is insufficient. This ticket is the planned hardening response. Citation: `research/sandbox-overnight-child-agents/research.md` Feasibility V1c row.

## Acceptance criteria (high-level — refined when activated)

- Empirical data from #164's telemetry justifies the tightening (or the user explicitly decides to harden without telemetry).
- Per-spawn settings JSON adds `sandbox.filesystem.allowWrite` for the worktree path + minimal git internals required for legitimate commits.
- `denyWrite` set is preserved (deny precedence over allow ensures the `main`/`HEAD` carve-outs hold).
- Acceptance test verifies a write to a non-allowlisted home-repo path (e.g., `<home_repo>/README.md`) returns EPERM at the kernel layer.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: Feasibility table V1a/V1b/V1c, RQ2 (git filesystem writes), DR-3 (V1 scope).
