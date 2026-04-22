---
schema_version: "1"
uuid: 2cbcf121-190a-468a-b8d3-3fb38dec6be6
title: "Eliminate home-repo-vs-worktree context drift in overnight runner"
status: complete
priority: critical
type: epic
tags: [overnight-runner, worktree, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-22
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/orchestrator-worktree-escape/research.md
---

# Eliminate home-repo-vs-worktree context drift in overnight runner

## Context from discovery

Session `overnight-2026-04-21-1708` failed all 3 features at `feature_start` with `Plan parse error: No such file or directory: 'lifecycle/{slug}/plan.md'` (literal `{slug}` — a substitution bug). Investigation surfaced a broader invariant that has been silently violated across the overnight runner's full history: *operations meant for the per-session worktree/integration branch have been executing against the home repo and `main` instead, OR vanishing into gitignored paths*.

Verified failure modes within this epic's scope:

1. **Orchestrator prompt lexical priming** — `orchestrator-round.md:258-285` uses per-feature tokens (`{slug}`, `{spec_path}`, per-feature `{plan_path}`) with the same syntax as pre-filled session-level absolute-path tokens, causing the orchestrator agent to non-deterministically mis-substitute.
2. **Morning-report silent no-op** — `.gitignore:41` lists `lifecycle/sessions/`; `runner.sh:1223-1225` uses `git add` (not `-f`) which silently skips ignored files, making the morning-report commit step a no-op. 4 of 4 sessions in this machine's history lost their morning reports — that is the population, not a sample.
3. **Python-layer backlog writes target home-repo** — `report.py:272-360` (followup items) and `backlog.py:321,365` (`session_id` frontmatter) write via the home-repo path. The runner's `git add` at `runner.sh:1002-1008` only stages worktree files, leaving home-repo writes untracked and later clobbered.

PR-gating surfaced in the same session but does not share this invariant — it is tracked as a separate ticket.

Full research at `research/orchestrator-worktree-escape/research.md`.

## Scope

This epic lands 4 fixes that together restore the invariant *"overnight runner operations land where they're intended — worktree/integration branch for per-feature work, main only for the explicitly documented exceptions."*

## Child tickets

- **#127** Disambiguate orchestrator prompt tokens to stop lexical-priming escape
- **~~#128~~** ~~Install `pre-commit` hook rejecting main commits during overnight sessions~~ — closed `wontfix` 2026-04-21. DR-3 under-priced costs (session-id predicate leaks into interactive sessions, morning-report commit conflict, new git-hook install infrastructure) surfaced during `/lifecycle` clarify. Rely on #127 as the upstream cause fix; reassess defense-in-depth only if residual escape classes appear after #127 lands. See ticket body for full rationale.
- **#129** Un-silence morning-report commit and backfill 4 historical reports
- **#130** Route Python-layer backlog writes (followup + frontmatter) through worktree checkout

## Not in scope

- PR-gating on zero-merge sessions (see standalone ticket #131)
- Worktree/subagent-transcript garbage collection (hygiene; not a worktree-escape bug)
- `{worktree_root}` token sweep (speculative clarity play — no observed failure it would prevent)
- Substitution-step instrumentation (speculative observability)
- Postflight plan-visibility check at Step 3e (redundant once #127 + #128 land)
