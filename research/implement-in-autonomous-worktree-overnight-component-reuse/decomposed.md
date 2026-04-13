# Decomposition: implement-in-autonomous-worktree (overnight-component reuse)

## Epic

- **Backlog ID**: 074 (existing; repurposed)
- **Title**: Decompose batch_runner and enable daytime autonomous-worktree pipeline

The epic was updated post-discovery to reflect the modularization-first
framing. Original scope (daytime autonomous worktree) is preserved as
the final two phases; earlier phases decompose `batch_runner.py` along
its natural seams for overnight's own maintainability.

## Work Items

| ID  | Title                                                                          | Priority | Size | Depends On |
|-----|--------------------------------------------------------------------------------|----------|------|------------|
| 075 | Extract feature_executor module from batch_runner                              | high     | M    | —          |
| 076 | Extract outcome_router module from batch_runner                                | high     | M–L  | 075        |
| 077 | Rename batch_runner to orchestrator and add integration tests                  | high     | S–M  | 076        |
| 078 | Build daytime pipeline module and CLI                                          | medium   | M    | 077        |
| 079 | Integrate autonomous worktree option into lifecycle pre-flight                 | medium   | M    | 078        |

## Suggested Implementation Order

Sequential (each blocks the next). Recommended sequencing note: #073
(overnight docs) should land before #075 if scheduling allows, so the
architectural descriptions reference the target module shape rather
than being rewritten afterwards. Not a hard blocker.

1. #075 — feature_executor extraction (tests land alongside)
2. #076 — outcome_router extraction (tests land alongside)
3. #077 — orchestrator rename + CLI wrap + integration tests (final
   regression gate for the three-phase refactor)
4. #078 — daytime pipeline module + CLI (standalone CLI works)
5. #079 — lifecycle skill pre-flight integration (user-facing)

## Key Design Decisions (from research)

- **Modularization is the primary value driver** (DR-5). Daytime
  pipeline is a consumer of the decomposition, not its justification.
- **Co-exist, not replace** for worktree pre-flight options (DR-2).
  Single-agent "Implement in worktree" retains live-steerability
  property the subprocess path cannot replicate.
- **Events.log written to main repo CWD, not daytime worktree** (DR-3).
  Avoids the TC8 staleness pattern.
- **Per-feature `lifecycle/{feature}/deferred/`** (DR-4). Avoids
  collisions with overnight's morning report in shared
  `lifecycle/deferred/`.
- **3-way split chosen over 2-way or 4-way**: orchestrator /
  feature_executor / outcome_router. Each answers one question; 4-way
  fragments outcome dispatch across too many modules.

## Consolidation Review

No consolidation candidates found. WI1–WI3 all touch `batch_runner.py`
but each has independent deliverable value (own module, own test
surface, own regression gate). WI4 can be manually tested via CLI
without WI5. No same-file S+S merges, no no-standalone-value
prerequisites.

## Created Files

- `backlog/075-extract-feature-executor-module-from-batch-runner.md`
- `backlog/076-extract-outcome-router-module-from-batch-runner.md`
- `backlog/077-rename-batch-runner-to-orchestrator-and-add-integration-tests.md`
- `backlog/078-build-daytime-pipeline-module-and-cli.md`
- `backlog/079-integrate-autonomous-worktree-option-into-lifecycle-pre-flight.md`

## Updated Files

- `backlog/074-implement-in-autonomous-worktree-overnight-component-reuse.md` —
  title updated, framing reworked, children enumerated
