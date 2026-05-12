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
| 080 | Add characterization tests for batch_runner pre-extraction                     | high     | S–M  | —          |
| 075 | Extract feature_executor module from batch_runner                              | high     | M    | 080        |
| 076 | Extract outcome_router module from batch_runner                                | high     | L    | 075        |
| 077 | Rename batch_runner to orchestrator and add integration tests                  | high     | S–M  | 076        |
| 078 | Build daytime pipeline module and CLI                                          | medium   | M    | 076        |
| 079 | Integrate autonomous worktree option into lifecycle pre-flight                 | medium   | M    | 078        |

## Dependency graph

```
080 → 075 → 076 → 077 ─┐
                └─ 078 → 079
```

#080 establishes the regression oracle (golden-master characterization
tests) before the first extraction lands. Without it the only
regression gate is a multi-hour stochastic overnight run, which is not
PR-reviewable.

After #076 lands, #077 (rename + CLI wrap + integration tests) and
#078 (daytime pipeline module + CLI) can run in parallel — #078 does
not depend on orchestrator.py existing, only on feature_executor +
outcome_router being importable.

## Suggested Implementation Order

1. #080 — characterization tests; pins current behavior of
   `execute_feature`, `_apply_feature_result`, `_accumulate_result`
   outcome routing, and conflict-recovery branching
2. #075 — feature_executor extraction; reviewer runs #080 fixtures as
   before/after oracle
3. #076 — outcome_router extraction; same oracle (larger than
   originally estimated — includes inline outcome-routing in
   `_accumulate_result`, not only `_apply_feature_result`)
4. #077 and #078 in parallel:
   - #077 — orchestrator rename + CLI wrap + integration tests
   - #078 — daytime pipeline module + CLI
5. #079 — lifecycle skill pre-flight integration (user-facing)

Recommended sequencing note: #073 (overnight docs) should land before
#080 if scheduling allows, so the architectural descriptions reference
the target module shape rather than being rewritten afterwards. Not a
hard blocker.

## Key Design Decisions (from research)

- **Modularization is the primary value driver** (DR-5). Daytime
  pipeline is a consumer of the decomposition, not its justification.
- **Co-exist, not replace** for worktree pre-flight options (DR-2).
  Single-agent "Implement in worktree" retains live-steerability
  property the subprocess path cannot replicate.

> **2026-04-22 (ticket #097) — DR-2 reversed.** Option 1 ("Implement in worktree") was removed from the implement-phase pre-flight in full; this reverses the co-exist stance recorded above. Thin usage evidence is now also in doubt: `anthropics/claude-code` issue #39886 describes `Agent(isolation: "worktree")` silently failing to create isolation, so the single observed success may not have delivered its intended behavior.

- **Events.log written to main repo CWD, not daytime worktree** (DR-3).
  Avoids the TC8 staleness pattern.
- **Per-feature `lifecycle/{feature}/deferred/`** (DR-4). Avoids
  collisions with overnight's morning report in shared
  `cortex/lifecycle/deferred/`.
- **3-way split chosen over 2-way or 4-way**: orchestrator /
  feature_executor / outcome_router. Each answers one question; 4-way
  fragments outcome dispatch across too many modules.

## Consolidation Review

No consolidation candidates found. #075–#077 all touch
`batch_runner.py` but each has a non-overlapping slice of responsibility
(feature-executor extract / outcome-router extract / rename + CLI wrap).
#078 can be manually tested via CLI without #079.

**Known same-file coordination points** (identified during critical
review):

- `_run_one` is edited by #075 (import swap for execute_feature),
  #076 (collapse inline outcome-routing), and #077 (relocate to
  orchestrator.py). Each edit is non-overlapping but all three tickets
  touch the same function; PR authors coordinate via reference to this
  document.
- Shared helpers (`_next_escalation_n`, `_get_changed_files`,
  `_classify_no_commit`, `_effective_base_branch`,
  `_effective_merge_repo_path`) stay in batch_runner.py /
  orchestrator.py and both new modules import from there.
- `FeatureResult` is treated as a frozen API between feature_executor
  and outcome_router; any restructuring lands before #075.
- The `status="repair_completed"` flow spans #075 (execute_feature
  produces the repair branch) and #076 (apply_feature_result
  fast-forward-merges it); coordinated via the frozen FeatureResult
  contract.
- `consecutive_pauses_ref` and `recovery_attempts_map` continue as
  mutable parameters across module boundaries; opportunistic
  conversion to dataclasses happens in #077 if desired.

## Created Files

- `cortex/backlog/075-extract-feature-executor-module-from-batch-runner.md`
- `cortex/backlog/076-extract-outcome-router-module-from-batch-runner.md`
- `cortex/backlog/077-rename-batch-runner-to-orchestrator-and-add-integration-tests.md`
- `cortex/backlog/078-build-daytime-pipeline-module-and-cli.md`
- `cortex/backlog/079-integrate-autonomous-worktree-option-into-lifecycle-pre-flight.md`
- `cortex/backlog/080-add-characterization-tests-for-batch-runner-pre-extraction.md`
  (added after critical review to close the regression-oracle gap
  before extraction begins)

## Updated Files

- `cortex/backlog/074-implement-in-autonomous-worktree-overnight-component-reuse.md` —
  title updated, framing reworked, children enumerated, priority
  raised to high (reflects the must-do refactor half)
