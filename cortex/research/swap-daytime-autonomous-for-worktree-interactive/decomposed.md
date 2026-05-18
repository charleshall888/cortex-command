# Decomposition: swap-daytime-autonomous-for-worktree-interactive

## Epic

- **Backlog ID**: 237
- **Title**: Swap daytime autonomous for worktree-interactive implement mode

## Work Items

| ID  | Title                                                                     | Priority | Size | Depends On  |
|-----|---------------------------------------------------------------------------|----------|------|-------------|
| 238 | Swap implement-phase preflight option 2 to worktree-interactive           | high     | S    | —           |
| 239 | Manage interactive feature worktree lifecycle (creation + cleanup)        | high     | M    | —           |
| 240 | Implement Variant A end-to-end (interaction model + PR-creation hook)     | high     | L    | 239         |
| 241 | Add bidirectional concurrency guards for interactive worktree mode        | medium   | M    | —           |
| 246 | Remove daytime autonomous pipeline and cancel #228/#230                   | high     | L    | 238, 240    |

## Suggested Implementation Order

Parallelizable kickoff: **238, 239, 241** can all land independently — preflight menu swap, worktree lifecycle primitive, and bidirectional concurrency guards have no inter-dependencies.

Then **240** (Variant A end-to-end) — blocked by 239 (needs the worktree-creation primitive); this is the heaviest piece because of the 8-site cwd-relative writer refactor and the per-tool-call CWD-refresh mechanism.

Finally **246** (daytime removal sweep) — blocked by 238 (menu must already swap option 2) and 240 (new interactive mode must be functional before the autonomous path is removed). Includes the cancellation of `#228` and `#230` per DR-7's user resolution.

## Created Files

- `cortex/backlog/237-swap-daytime-autonomous-for-worktree-interactive-implement-mode.md` — Epic.
- `cortex/backlog/238-swap-implement-phase-preflight-option-2-to-worktree-interactive.md` — Preflight menu swap.
- `cortex/backlog/239-manage-interactive-feature-worktree-lifecycle.md` — Worktree creation + cleanup (consolidates original pieces 2 and 8).
- `cortex/backlog/240-implement-variant-a-end-to-end-interaction-and-pr.md` — Variant A interaction model + PR-creation hook (consolidates original pieces 3 and 7).
- `cortex/backlog/241-add-bidirectional-concurrency-guards-for-interactive-worktree-mode.md` — Three concurrency guards as one ticket (consolidates original pieces 4, 5, and 6).
- `cortex/backlog/246-remove-daytime-autonomous-pipeline-and-cancel-228-230.md` — Daytime removal sweep + #228/#230 cancellation.

## Consolidation Notes

The Architecture section's `### Pieces` list named 9 pieces; the user approved three consolidations at the R15 gate (round 1), reducing the child-ticket count from 9 to 5:

1. **239 absorbed original "Worktree cleanup contract"** (was a separate piece). The two pieces share the worktree-lifecycle concept and ship as one PR; the dependency chain remains coherent because 245's original dependency on 244 (PR-creation) is now internal to 240+239's pair (the cleanup half of 239 still depends on the PR-creation half of 240, but as an internal phase boundary rather than a cross-ticket dependency).
2. **240 absorbed original "PR-creation hook for Variant A"**. Both pieces are Variant-A-specific and operationally coupled (PR-hook needs the `cd`-mid-session shape to be defined); shipping them together avoids a half-implemented Variant A.
3. **241 absorbed original "Overnight-active rejection mirror" and "Inverse-direction overnight guard"**. All three concurrency guards form a single bidirectional safety contract; their test matrix lands together more naturally than across three separate PRs.

No other consolidations were taken; the remaining tickets (238 menu, 240 Variant A, 246 removal) retained their original boundaries.
