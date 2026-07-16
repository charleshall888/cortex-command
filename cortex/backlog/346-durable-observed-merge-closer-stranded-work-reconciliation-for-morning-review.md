---
schema_version: "1"
uuid: 6eb2c913-9f89-41d4-8404-38ef1d8ecc1e
title: Durable observed-merge closer + stranded-work reconciliation for morning-review
status: in_progress
priority: low
type: feature
created: 2026-07-02
updated: 2026-07-16
lifecycle_phase: research
lifecycle_slug: durable-observed-merge-closer-stranded-work
complexity: complex
criticality: high
spec: cortex/lifecycle/durable-observed-merge-closer-stranded-work/spec.md
areas: ['overnight-runner']
---
## Why
This ticket was filed on a premise that does not hold, and the premise has already re-seeded the wrong design twice. The original claim — that the post-merge sync is skipped on the "PR already merged" exit, leaving the local checkout behind main — is false: the skill's Step 5 runs a fetch and a rebase onto main before the PR merge section ever inspects PR state, and has since `428e54ea`. On that false footing, #345 researched, specced, and shipped an advisory onto a branch that cannot execute, and this ticket then proposed a remote-authoritative on-main read that is redundant with a rebase already running.

The two real defects are smaller and independently verified. First, the merged and closed exits are unreachable: the walkthrough's PR query asks for pull requests on the integration branch without an explicit `--state` argument, and `gh` defaults to open — so those branches are dead code, and a genuinely already-merged PR instead falls into the empty-result branch, which advises creating a PR manually for work that already landed. Second, the post-merge closer's ticket writes are never committed or pushed: the closer section ends with the review complete and the close verb makes no git calls, so a close written to repair a failed overnight write-back never reaches main.

## Role
Repair the post-merge path against what it actually does. Give the PR query an explicit state filter so the merged and closed exits can execute for the first time, and make their behavior honest and report-only — they surface what happened and never decide that this session's work landed. Add a commit-and-push step after the post-merge closer whose push outcome is observed directly rather than inferred from another binary's exit code, so a repaired close either reaches main or says plainly that it did not. Alongside those, repair the supporting machinery the same path leans on: the sync allowlist whose patterns all predate the `cortex/` umbrella relocation and match nothing, the behind-count helper that reports "up to date" on any git failure, and the overnight write-back's item lookup that silently returns the first numeric-prefix match.

## Integration
Builds on #345's advisory at the merged exit, which this work replaces with something reachable, and on #342's single-source post-merge closure, whose idempotence and merge-is-terminal convention stay intact. The walkthrough's ordering guard is satisfied, not amended, and canonical skill edits regenerate the dual-source mirror in the same commit. The pieces this ticket originally promised leave with corrected framing and become their own tickets: auto-closing on the merged exit (it needs an ancestry check against main plus a multi-PR disambiguation rule, and is gated on the exit becoming reachable first), the orphan reconciler for declined or abandoned integration branches, worktrees, and pull requests (no orphans exist today and none are recorded), and re-pick suppression for stranded features (the obvious design makes reset and destroying the recovery pointer the same gesture).

## Edges
- A widened state filter can return more than one PR for a reused head-branch name, since session ids are minute-granular and deduped only against a gitignored directory — surface the candidates rather than taking the first.
- A PR merged and then reverted keeps its merged state permanently, so the exit reports the merge that occurred and asserts nothing about current main.
- A close committed locally but never pushed inverts the bug — the ticket reads complete locally while still open on main — so a close counts as durable only on an observed post-push state.
- Re-closing a ticket already complete on main is a safe no-op but not inert; the commit step tolerates an empty or timestamp-only diff without failing.
- An ambiguous or renumbered backlog id refuses rather than guessing.

## Touch points
- `skills/morning-review/references/walkthrough.md` — the PR-state query, the merged/closed exits, and the post-merge closer (§6b).
- `cortex_command/overnight/close_tickets.py` — the closer's ticket writes, which need a commit-and-push path.
- `cortex_command/git/sync_rebase.py`, `cortex_command/overnight/sync-allowlist.conf` — the dead allowlist patterns and the fail-open behind count.
- `cortex_command/overnight/outcome_router.py` — the session write-back's `_find_backlog_item_path` first-match.
- `cortex/lifecycle/durable-observed-merge-closer-stranded-work/spec.md` — the narrowed scope and the deferrals.