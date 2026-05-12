# Decomposition: orchestrator-worktree-escape

## Epic

- **Backlog ID**: 126
- **Title**: Eliminate home-repo-vs-worktree context drift in overnight runner

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 127 | Disambiguate orchestrator prompt tokens to stop lexical-priming escape | critical | S | — |
| 128 | Install `pre-commit` hook rejecting main commits during overnight sessions | critical | S | — |
| 129 | Un-silence morning-report commit and backfill 4 historical reports | critical | S | — |
| 130 | Route Python-layer backlog writes (followup + frontmatter) through worktree checkout | high | S–M | — |
| 131 | Gate overnight PR creation on merged>0 (draft on zero-merge) *(standalone — not in epic)* | medium | S | — |

## Suggested Implementation Order

All four epic children are independent and have no blocking dependencies on each other — they can land in any order, in parallel, or interleaved with other work.

Pragmatic sequence when stacking into overnight rounds:

1. **#127 (prompt disambiguation)** and **#129 (morning-report un-silence)** are the smallest and highest-leverage. Either makes a good standalone first round.
2. **#128 (pre-commit hook)** is the enforcement layer. Once it lands, regressions on the invariant become loud instead of silent — worth landing early so the other fixes accumulate under protection.
3. **#130 (Python write path routing)** is the largest of the four and touches two Python modules. Can land after any combination of the others.
4. **#131 (PR gating)** is the standalone ticket outside the epic. Cheapest of all five; drop it into any round.

## Key Design Decisions

**Consolidation: #4 "Followup-item persistence" + #5 "Frontmatter rollback on failure" → #130.** The original post-research ticket list had these as two items. User-directed value audit surfaced that both share a single root cause (Python helpers writing via the home-repo path instead of the active worktree). The fix is the same — route writes through the worktree — and the "rollback" framing becomes unnecessary once mutations are scoped to the integration branch. Consolidation rationale follows Decompose Phase §3(a) (same-file overlap across `report.py` and `backlog.py` both writing to `backlog/*.md`) and §3(b) (the rollback has no standalone deliverable once writes are correctly scoped).

**Cuts: 5 tickets dropped from the initial post-research list of 11.**
- *Postflight plan-visibility check at Step 3e* — redundant once #127 fixes the root cause and #128 enforces the invariant; research itself framed it as "supplementary detector"
- *Orphaned-worktree + subagent-transcript GC* — hygiene only, no operational impact
- *`{worktree_root}` token sweep* — speculative clarity play; no observed failure it would prevent
- *Substitution-step instrumentation* — speculative observability; defer until after #127 is operationally proven
- *Postflight worktree-plan-visibility check (Option C)* — research's critical-review synthesis flagged it as covering a proper subset of violations that Option E (git pre-commit hook, #128) covers more directly

**Absorbed: retroactive publication of the 4 historical morning reports** is scoped inside #129 as a one-shot backfill — not a separate ticket. Implementation is a single `git add -f` (or equivalent per the storage decision) plus commit once the forward-path fix lands.

**Scope split: PR-gating (#131) is intentionally NOT part of epic #126.** `MC_MERGED_COUNT` is computed and ignored — the PR would have been created identically even if every worktree-invariant bug were fixed. Grouping it under the worktree-escape epic would be a category error. Tracked separately.

## Created Files

- `cortex/backlog/126-eliminate-home-repo-vs-worktree-context-drift-in-overnight-runner.md` — Epic
- `cortex/backlog/127-disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape.md`
- `cortex/backlog/128-install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions.md`
- `cortex/backlog/129-un-silence-morning-report-commit-and-backfill-4-historical-reports.md`
- `cortex/backlog/130-route-python-layer-backlog-writes-through-worktree-checkout.md`
- `cortex/backlog/131-gate-overnight-pr-creation-on-merged-over-zero.md` — Standalone (not in epic)
