# Verification: Pre-merge Baseline Capture (R11)

## Aggregator Run Results

Ran ticket 104's `compute_skill_tier_dispatch_aggregates` pipeline aggregator against all
available overnight sessions (`overnight-2026-04-01-2112`, `overnight-2026-04-07-0008`,
`overnight-2026-04-11-1443`). All sessions produced only `legacy,*` skill buckets — no
`orchestrator-round` or `orchestrator` skill bucket appeared.

**Root cause of missing aggregator data**: The orchestrator-round runs as a `claude -p`
subprocess spawned by `cortex_command/overnight/runner.py` and is not instrumented as a
pipeline dispatch event (`dispatch_start` / `dispatch_complete`). The pipeline aggregator
tracks feature-level tasks (implement, review, review-fix, brain, etc.) but not the
orchestrator process itself. Additionally, the `skill` field was not yet present in the
dispatch events of these sessions (the vocabulary was added in a later code revision).
The `Skill` literal in `cortex_command/pipeline/dispatch.py` does not include an
`orchestrator-round` entry.

## Prompt-Size Measurement (Static, Round 1)

Because the aggregator cannot surface orchestrator dispatch records, the input-token
baseline is derived from the actual content sent to the orchestrator agent at round
startup. This measurement is repeatable and tied to the pre-merge (inline-read) prompt.

**Session**: `overnight-2026-04-07-0008`, round 1  
**Prompt rendered via** `fill_prompt(round_number=1, tier='sonnet', ...)` from
`cortex_command/overnight/fill_prompt.py`  
**Token estimation**: 1 token ≈ 4 characters (Anthropic mixed code/text approximation)

| Component | Characters | Estimated tokens |
|-----------|------------|-----------------|
| Filled orchestrator-round.md prompt | 19,107 | 4,776 |
| overnight-state.json (inline Read at Step 1) | 5,785 | 1,446 |
| overnight-strategy.json (inline load_strategy at Step 1a) | 779 | 194 |
| overnight-plan.md (inline Read at Step 2) | 2,583 | 645 |
| escalations.jsonl | 0 (absent) | 0 |
| **Total round-startup input tokens** | **28,254** | **7,063** |

The prompt template itself is constant across all rounds (only path strings differ).
The state/strategy/plan component varies per round; round 1 values are used as the
representative measurement.

## Baseline Record

```yaml
baseline_tokens: 7063
session_id: overnight-2026-04-07-0008
captured_at: 2026-04-29T00:00:00Z
```

## Notes

- `baseline_tokens` is the estimated total input-token cost per orchestrator-round
  startup: prompt template (4,776) + inline file reads (2,285). This covers the
  round-startup pseudocode regions targeted by Task 5's rewrite (Step 0b, Step 1a,
  Step 2). The prompt-template component (4,776 tokens) does not shrink appreciably
  from the rewrite; the savings come from eliminating the ~2,285 tokens of inline
  Python pseudocode that the aggregator function replaces.
- The aggregator-based measurement (ticket 104's `compute_skill_tier_dispatch_aggregates`)
  is not available for this measurement because: (a) the orchestrator is not dispatched
  via the pipeline's `dispatch_task` machinery, and (b) no session in the repo has
  `skill`-tagged dispatch events predating the current `orchestrator-round.md` prompt.
- R12 (post-merge note) will append `post_merge_tokens`, `ratio`, and `notes` to this
  file after the first overnight session running the rewritten prompt.
