---
schema_version: "1"
uuid: 8e7f4c78-1ce2-4a63-8309-a3727730598c
title: "Add bidirectional concurrency guards for interactive worktree mode"
status: backlog
priority: medium
type: feature
created: 2026-05-18
updated: 2026-05-18
parent: "237"
blocked-by: []
tags: [lifecycle, worktree-interactive, daytime-swap, concurrency]
areas: [skills, lifecycle, overnight-runner]
discovery_source: cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

## Role

Provide bidirectional concurrency safety for the interactive worktree mode via three guards that ship together: (a) Per-feature single-owner lock — writes `cortex/lifecycle/{slug}/interactive.pid` at dispatch time; preflight reads the file and runs `kill -0` liveness before proceeding. Prevents two interactive sessions from both running implement on the same feature. (b) Overnight-active rejection (mirror) — when the user selects the worktree-interactive option, the preflight reads the overnight active-session descriptor, verifies repo match and "executing" phase, and checks runner liveness; rejects with the same wording as the existing daytime mirror. (c) Inverse-direction overnight guard — the overnight startup sequence scans `cortex/lifecycle/*/interactive.pid` files and runs liveness checks; if any are alive, overnight skips those features or rejects startup. The three guards form a single coherent concurrency contract and share liveness-check semantics; shipping them as one ticket keeps the matrix of test cases together.

## Integration

The per-feature lock and overnight-active rejection both fire in the interactive preflight ordering — lock check after worktree creation but before task dispatch, overnight-active rejection before worktree creation. They read from common sources: the active-session descriptor file under the user's local share directory for overnight state, and `cortex/lifecycle/{slug}/interactive.pid` for per-feature ownership. The inverse-direction guard lives in the overnight startup sequence, reading the same `interactive.pid` files that the lock writes — the consumer side of the lock-file convention. Together they enforce that at most one interactive owner and one overnight runner are live for any given feature at any given time.

## Edges

- Bound by the lifecycle-feature-lock contract: at most one live interactive owner per feature.
- Bound by the liveness-check contract: `kill -0` semantics on recorded PIDs; stale-PID detection emits warnings and proceeds.
- Bound by the active-session-descriptor schema: `repo_path`, `phase`, `state_path` fields plus the runner-lock-file convention.
- Bound by the "no concurrent dispatch into same repo" invariant the existing daytime rejection enforces.
- Bound by the overnight feature-selection contract: the feature list passed to the orchestrator excludes features with live interactive owners.
- Bound by the uncommitted-state preservation contract: lock-release on session exit must not destroy worktree state.

## Touch points

- `cortex/lifecycle/{slug}/interactive.pid` — per-feature lock file (new).
- `skills/lifecycle/references/implement.md` §1 — preflight ordering; new lock check after worktree creation, new overnight-active rejection before worktree creation; mirrors the existing daytime check at §1a.iii.
- `~/.local/share/overnight-sessions/active-session.json` — descriptor read site.
- `cortex_command/overnight/runner.py` — overnight startup; new preflight scan site for inverse-direction guard.
- `cortex_command/overnight/orchestrator.py` — feature-list filter, if the scan operates at orchestration level instead.
