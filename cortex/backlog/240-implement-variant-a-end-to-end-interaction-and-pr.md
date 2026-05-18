---
schema_version: "1"
uuid: cfc426e7-5325-4a05-b6a0-bc1a97ee50c3
title: "Implement Variant A end-to-end (interaction model + PR-creation hook)"
status: backlog
priority: high
type: feature
created: 2026-05-18
updated: 2026-05-18
parent: "237"
blocked-by: ["239"]
tags: [lifecycle, worktree-interactive, daytime-swap, refactor, pr]
areas: [skills, lifecycle, python]
discovery_source: cortex/research/swap-daytime-autonomous-for-worktree-interactive/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
---

## Role

Implement the Variant A interaction model end-to-end. Two coupled pieces: (a) After worktree creation, the lifecycle skill issues `cd $(cortex-worktree-resolve interactive/{slug})` mid-flight and continues task dispatch from the worktree CWD. Includes the supporting write-site refactor for the eight identified cwd-relative writer sites that currently land in main rather than the worktree, plus a per-tool-call CWD-refresh mechanism that re-evaluates `CORTEX_REPO_ROOT` after `cd`. (b) At the lifecycle complete phase, wire the PR-creation step: either teach `/cortex-core:pr` a `--worktree <slug>` flag OR issue `cd $(cortex-worktree-resolve interactive/{slug})` before invoking the existing pr skill. The PR opens with the existing pr-skill body conventions (title, summary, test plan).

## Integration

The interaction-model piece sits between the worktree-creation step and task dispatch. The `cd` happens after worktree creation and before any further skill operations. The write-site refactor is the largest piece: events.log writers, backlog frontmatter mutations, statusline path resolution, and morning-report path resolution must all route through an explicit worktree-root parameter or a refreshed `CORTEX_REPO_ROOT` env var. Established precedent for this class of fix is the home-vs-worktree drift work that landed under prior tickets `#126` and `#130`. The PR-creation piece fires in the lifecycle complete phase after the existing summary step but before lifecycle exit; detects the worktree state by reading the per-feature `interactive.pid` (created by the concurrency-guards ticket) or worktree-path marker. User merges manually — no auto-merge in the skill layer.

This ticket consolidates three operationally coupled pieces (cd-mid-session shape, write-site refactor, PR-creation hook), so it is not atomically deliverable in a single commit or PR. Refine should plan it as a multi-commit feature-branch sequence: the cd shape and per-tool-call CWD-refresh mechanism land first; the write-site refactor follows in commits scoped per writer site or small site cluster; the PR-creation hook lands last on the same branch. The branching itself is consistent with the new mode being shipped here, which provides a natural test bed for incremental landing.

## Edges

- Bound by the cwd-relative-writer contract: all lifecycle file writes must resolve to the worktree once the worktree is the active CWD, not to the home repo.
- Bound by the `CORTEX_REPO_ROOT` env-var refresh contract: a mechanism must re-fire the SessionStart-equivalent env injection on mid-session CWD change.
- Bound by the statusline and morning-report path-resolution contract: downstream consumers must see the worktree's view post-`cd`.
- Bound by the sandbox path-resolution contract: `.mcp.json` and other sandbox-sensitive files must resolve correctly under the worktree path.
- Bound by the pr-skill input contract: requires a feature branch with commits ahead of base; assumes current cwd is a checkout where `git push` resolves.
- Bound by the worktree-aware-checkout contract under Variant A: either `git -C <worktree>` plumbing OR skill-level `cd` before pr-skill invocation.
- Bound by the no-auto-merge invariant: the user merges the PR, not the lifecycle skill.

## Touch points

- `cortex_command/refine.py:117` — events.log writer.
- `cortex_command/critical_review.py` — events.log writer.
- `bin/cortex-complexity-escalator:296` — events.log path.
- `cortex_command/discovery.py:189-197` — events.log resolution helper.
- `cortex_command/backlog/update_item.py:445` — backlog dir resolution.
- `cortex_command/backlog/update_item.py:169` — sidecar events.jsonl path.
- `claude/statusline.sh:244-247` — lifecycle-dir lookup.
- `cortex_command/overnight/report.py:52,125` — morning report path resolution.
- `hooks/cortex-scan-lifecycle.sh:15-26` — SessionStart hook env injection (the staleness origin).
- `skills/lifecycle/references/implement.md` §1 — dispatch site for the `cd` and downstream task-dispatch flow.
- `skills/pr/SKILL.md` — pr-skill body; may gain a `--worktree` flag or stay unchanged depending on chosen approach.
- `skills/lifecycle/references/complete.md` §4 — git workflow section; routes by branch state.
