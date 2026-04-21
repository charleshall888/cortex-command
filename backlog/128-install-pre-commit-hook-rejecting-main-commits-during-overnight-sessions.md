---
schema_version: "1"
uuid: 9064c10e-38ba-494a-9783-3bf12aca8a6c
title: "Install pre-commit hook rejecting main commits during overnight sessions"
status: backlog
priority: critical
type: feature
parent: 126
tags: [overnight-runner, git-hook, enforcement, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/orchestrator-worktree-escape/research.md
---

# Install pre-commit hook rejecting main commits during overnight sessions

## Context from discovery

Session `overnight-2026-04-21-1708` landed plan commits on local `main` (commit `0e1c4b6`) instead of the integration branch because the orchestrator executed `cd /Users/charlie.hall/Workspaces/cortex-command && git commit` from within its worktree-launched Bash tool. `runner.sh:595` does `cd "$WORKTREE_PATH"` before spawning the orchestrator, but agents can always `cd` elsewhere; worktree isolation at the Bash-tool layer is cosmetic unless enforced.

Git worktrees share `.git/hooks/` with the main repo through gitdir indirection: `$WORKTREE/.git` is a file pointing to `$REPO_ROOT/.git/worktrees/<name>/`, and `core.hooksPath` defaults to `$GIT_DIR/hooks` which resolves to the shared hooks directory at `$REPO_ROOT/.git/hooks/`. A single `pre-commit` hook installed there fires for commits from *any* worktree against the repo.

`runner.sh` already exports `LIFECYCLE_SESSION_ID` before spawning agents (line 635 per research), so the enabling mechanism exists: reject commits to `main` when `LIFECYCLE_SESSION_ID` is non-empty.

## Value

A ~20-line shell hook catches the exact escape vector of session 1708 (Bash `cd && git commit`) plus every future Bash-based escape from any subagent. Research DR-3 selected this (Option E) over the previously-considered PreToolUse Edit/Write hook (Option D, which does NOT cover the observed Bash escape) and the postflight visibility check (Option C, which only catches plan-ENOENT symptoms). Single mechanism, smaller effort than the alternatives combined, directly enforces the invariant.

## Research context

- Full analysis: `research/orchestrator-worktree-escape/research.md` DR-3 and §Feasibility Assessment → Enforcement options
- The options table in the first draft of the research omitted this mechanism entirely; critical review surfaced it as strictly dominant over the C+D layered approach originally recommended

## Acceptance criteria

- A `pre-commit` hook is installed at `$REPO_ROOT/.git/hooks/pre-commit` (or wherever `core.hooksPath` resolves — decision lives with the implementation)
- The hook rejects commits that target `main` when `$LIFECYCLE_SESSION_ID` is set and non-empty
- The hook does not interfere with interactive commits where `$LIFECYCLE_SESSION_ID` is unset
- The hook's installation method is idempotent and survives `just setup` / repo reclone scenarios
- Integration test (or manual verification) confirms the hook fires for commits issued from worktrees, not only from `$REPO_ROOT` — worktree gitdir-sharing is the load-bearing mechanism
