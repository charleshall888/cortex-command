# Review: Replace concurrency cap with conflict-aware round scheduling

**Reviewer**: automated
**Cycle**: 1
**Date**: 2026-04-07

## Requirement Verification

### R1: Remove `BatchConfig.concurrency` field — PASS

- `BatchConfig` no longer has a `concurrency` field (verified at line 110-118 of `batch_runner.py`)
- `--concurrency` CLI argument removed from `build_parser()` (verified at line 2044-2068)
- `config.concurrency` reference in the `BATCH_ASSIGNED` log event removed; the event now logs only `features` (line 1519)
- `grep -rn 'concurrency' claude/overnight/batch_runner.py` returns only comments/docstrings referencing `ConcurrencyManager`, which is acceptable per spec

### R2: Remove `generate_batch_plan` concurrency parameter — PASS

- `concurrency: int` parameter removed from `generate_batch_plan()` signature (line 18-24 of `batch_plan.py`)
- `concurrency_limit` row no longer written to the markdown configuration table (line 100-104)
- `grep -n 'concurrency' claude/overnight/batch_plan.py` returns no matches

### R3: Remove `MasterPlanConfig.concurrency_limit` parsing — PASS

- `concurrency_limit: int = 3` field removed from `MasterPlanConfig` (line 32-36 of `parser.py`)
- Parsing branch for `concurrency_limit` removed from `_parse_config_table()` (line 214-226)
- Regression test `TestMasterPlanConcurrencyLimitBackwardCompat` added in `test_parser.py` (line 207-246) — parses a plan with a `concurrency_limit` config row and asserts success
- `grep -n 'concurrency_limit' claude/pipeline/parser.py` returns no matches
- Pipeline tests pass: 176 passed

### R4: Update `smoke_test.py` — PASS

- `concurrency=1` removed from `BatchConfig(...)` at line 253-257
- `grep -n 'concurrency' claude/overnight/smoke_test.py` returns no matches

### R5: Update `test_batch_plan.py` — PASS

- All `concurrency=` arguments removed from `generate_batch_plan()` calls (7 instances)
- `grep -n 'concurrency' claude/overnight/tests/test_batch_plan.py` returns no matches
- Overnight tests pass: 224 passed

### R6: Update `plan.py` session plan rendering — PASS

- `concurrency: int = 2` parameter removed from `render_session_plan()` (line 134-138)
- "Concurrency" line replaced with user-facing text at line 201: "Parallel dispatch: Tier-based adaptive throttle (1-3 workers depending on API subscription tier)"
- Does not use internal class names like `ConcurrencyManager` in user-facing output
- `grep -n 'concurrency' claude/overnight/plan.py` returns no matches

### R7: Update overnight skill docs — PASS

- All references to `concurrency` as a user-configurable parameter removed from `skills/overnight/SKILL.md`
- YAML frontmatter inputs section no longer lists `concurrency` (only `time-limit` remains)
- Code examples no longer pass `concurrency=N`
- Execution strategy description references "tier-based adaptive throttle" instead
- `grep -in 'concurrency' skills/overnight/SKILL.md` returns no matches

### R8: Update orchestrator round prompt — PASS

- `concurrency=2` removed from the `generate_batch_plan()` call example (line 272-279 of `orchestrator-round.md`)
- Line 202 updated from "understand batch assignments and concurrency configuration" to "understand batch assignments and the tier-based parallel dispatch limits"
- `grep -n 'concurrency=2' claude/overnight/prompts/orchestrator-round.md` returns no matches
- `grep -n 'concurrency configuration' claude/overnight/prompts/orchestrator-round.md` returns no matches

### R9: Update `docs/overnight.md` — PASS

- All references to concurrency as a user-configurable concept removed
- The conflict-interaction section (lines 376-409) rewritten to describe two orthogonal mechanisms:
  1. Area-separation in `group_into_batches()` for conflict avoidance
  2. Tier-based adaptive semaphore in `ConcurrencyManager` for resource protection
- References `backlog.py:group_into_batches()` for the area-separation mechanism (via `select_overnight_batch()`)
- Includes tier table (MAX_5=1, MAX_100=2, MAX_200=3)
- States "there is no user-configurable concurrency setting" explicitly
- `grep -in 'concurrency' docs/overnight.md` returns only references to the tier-based system and ConcurrencyManager

### R10: Update `requirements/multi-agent.md` — PASS

- Line 40-41 updated: "subject to the tier-based concurrency limit managed by `ConcurrencyManager`" and "tier-based concurrency limit (from `ConcurrencyManager`)"
- Line 73 updated: "The tier-based concurrency limit (1-3 workers) is a hard limit enforced by `ConcurrencyManager`; it is not overridable at runtime by agents"
- All concurrency references now describe the tier-based semaphore system, not a user-configurable parameter

### R11: Update `requirements/pipeline.md` — PASS

- Line 29 updated from "concurrency configuration" to "tier-based concurrency limit (from `ConcurrencyManager`)"
- `grep -in 'concurrency configuration' requirements/pipeline.md` returns no matches

### R12: Update remaining references — PASS

- `docs/agentic-layer.md`: `grep -in 'concurrency' docs/agentic-layer.md` returns no matches
- `skills/skill-creator/references/contract-patterns.md`: concurrency input block removed; `grep -in 'concurrency' skills/skill-creator/references/contract-patterns.md` returns no matches

### R13: Investigate inner-task parallelism — PASS

- Investigation note exists at `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md`
- Data point A (typical task counts per dependency batch): documents `compute_dependency_batches()` in `claude/common.py`, examines 36 plan.md files, reports typical max batch size of 3-4 tasks with an outlier at 8
- Data point B (rate limit events in overnight logs): searched 3 historical sessions, found zero rate limit events
- Data point C (what `throttled_dispatch` does and whether code calls it): traces callers, documents it as dead code — `run_batch()` uses manual `manager.acquire()/release()` instead; `brain.py` calls `dispatch_task()` directly
- Recommendation: "(a) Not a problem in practice" with clear rationale

### Codebase-wide sweep — PASS

Ran `grep -rn 'concurrency' --include='*.py' --include='*.md' . | grep -v throttle | grep -v node_modules | grep -v lifecycle/replace`. Remaining references fall into acceptable categories:

- **Backlog item 037 title/description**: historical artifact describing the problem this lifecycle solved
- **`test_parser.py`**: regression test for backward compatibility with `concurrency_limit` rows — required by R3
- **`batch_runner.py` comments/docstrings**: describe ConcurrencyManager behavior, not user-configurable concurrency
- **Historical lifecycle artifacts** (`docs-audit/`, `remove-task-limit-docs/`, `fix-next-question-id-race-condition/`, `fix-non-atomic-state-writes/`, `fix-overnight-runner-silent-crash/`): refer to concurrency in context of their own investigations/specs; these are frozen records
- **Historical session batch plans** (`lifecycle/sessions/*/batch-plan-round-*.md`): contain `concurrency_limit` rows from before removal — R3's regression test protects parsing of these
- **`requirements/pipeline.md` and `requirements/multi-agent.md`**: reference tier-based ConcurrencyManager (updated by R10/R11)
- **`docs/overnight.md`**: references tier-based system (updated by R9)
- **`skills/requirements/references/gather.md`**: generic requirements template mentioning "concurrency requirements" as a category — unrelated to overnight runner

No remaining references describe concurrency as a user-configurable parameter.

## Code Quality

### Naming conventions
Consistent with project patterns. Replacement text uses "tier-based adaptive throttle" in user-facing contexts and "ConcurrencyManager" in technical contexts. Field names and parameter signatures follow existing conventions.

### Error handling
No new error paths introduced — this is a removal-only change. The parser's `if/elif` fallthrough on unknown config keys is the correct existing behavior, now protected by a regression test.

### Test coverage
- R3: Backward compatibility regression test added (`TestMasterPlanConcurrencyLimitBackwardCompat`) — verifies historical plans with `concurrency_limit` rows parse without error
- R4: `smoke_test.py` updated (concurrency arg removed)
- R5: All 7 test calls in `test_batch_plan.py` updated
- Pipeline tests: 176 passed
- Overnight tests: 224 passed
- `just test` partial failure is a sandbox permission issue with `uv` cache, unrelated to this change

### Pattern consistency
Follows project conventions: dead code removed cleanly, docstrings preserved where they describe remaining behavior, user-facing text avoids internal class names, requirements docs updated to reflect actual system behavior.

## Requirements Drift

**State**: none

**Findings**:
- None

**Update needed**: None

The implementation updated `requirements/multi-agent.md` (R10) and `requirements/pipeline.md` (R11) as part of the spec requirements, bringing them into alignment with the actual tier-based ConcurrencyManager system. No new behavior was introduced that isn't reflected in the requirements docs.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
