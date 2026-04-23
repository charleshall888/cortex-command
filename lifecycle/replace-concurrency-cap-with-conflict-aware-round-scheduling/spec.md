# Specification: Replace concurrency cap with conflict-aware round scheduling

## Problem Statement

The overnight runner has a vestigial `BatchConfig.concurrency` field (default 3) and `--concurrency` CLI argument that appear to control parallel feature execution but have no effect on runtime behavior. Actual concurrency is controlled by `ConcurrencyManager` in `throttle.py`, which uses tier-based adaptive semaphoring. The dead field's existence creates confusion about how concurrency works — it prompted this investigation. Additionally, documentation and prompts disagree on the default value (2 vs 3), and inner-task parallelism within features is architecturally unbounded.

## Requirements

Requirements 1–12 are **must-have**: they form one atomic cleanup — removing the dead field without updating all references, tests, docs, and prompts leaves broken references and misleading documentation. Requirement 13 is **should-have**: it is a separate investigation deliverable that could be deferred without blocking the cleanup.

1. **[must-have] Remove `BatchConfig.concurrency` field**: Delete the `concurrency: int = 3` field from `BatchConfig` in `batch_runner.py:113` and the `--concurrency` CLI argument at `batch_runner.py:2053`. Remove the `config.concurrency` reference in the log event at `batch_runner.py:1521` — replace with `manager.current_concurrency` or remove the field from the log event entirely. Acceptance criteria: `grep -rn 'concurrency' claude/overnight/batch_runner.py` returns no matches except in comments or the ConcurrencyManager import; `python3 -m cortex_command.overnight.batch_runner --help` does not list `--concurrency`.

2. **[must-have] Remove `generate_batch_plan` concurrency parameter**: Delete the `concurrency: int` parameter from `generate_batch_plan()` in `batch_plan.py:20` and the `concurrency_limit` row it writes to the markdown table at line 105. Acceptance criteria: `grep -n 'concurrency' claude/overnight/batch_plan.py` returns no matches.

3. **[must-have] Remove `MasterPlanConfig.concurrency_limit` parsing**: Delete the `concurrency_limit: int = 3` field from `MasterPlanConfig` in `parser.py:35` and the parsing logic at `parser.py:223-225`. The current parser's `if/elif` chain already falls through silently on unknown keys, so no new handling is needed — just delete the `concurrency_limit` branch. Add a regression test that parses a batch plan markdown containing a `concurrency_limit` row and asserts it succeeds without error (protecting backward compatibility for the 4 historical plans in `lifecycle/sessions/` that `map_results.py:154` processes). Acceptance criteria: `grep -n 'concurrency_limit' claude/pipeline/parser.py` returns no matches; a test exists that parses a plan with a `concurrency_limit` config row and passes; `just test` exits 0.

4. **[must-have] Update `smoke_test.py`**: Remove the `concurrency=1` argument from `BatchConfig(...)` at `smoke_test.py:256`. Acceptance criteria: `grep -n 'concurrency' claude/overnight/smoke_test.py` returns no matches; `just test` exits 0.

5. **[must-have] Update `test_batch_plan.py`**: Remove all `concurrency=` arguments from `generate_batch_plan()` calls (7 instances). Acceptance criteria: `grep -n 'concurrency' claude/overnight/tests/test_batch_plan.py` returns no matches; `just test` exits 0.

6. **[must-have] Update `plan.py` session plan rendering**: Remove the `concurrency: int = 2` parameter from `render_session_plan()` at `plan.py:136` and the "Concurrency" line it writes at line 203. Replace with user-facing text suitable for the session plan (which is shown to the user for approval): e.g., "Parallel features per round are managed by the tier-based adaptive throttle (1-3 workers depending on API subscription tier)." Do not use internal class names like `ConcurrencyManager` in user-facing plan output. Acceptance criteria: `grep -n 'concurrency' claude/overnight/plan.py` returns at most references to the replacement documentation text; `just test` exits 0.

7. **[must-have] Update overnight skill docs**: In `skills/overnight/SKILL.md`, remove all references to `concurrency` as a user-configurable parameter (lines 7, 37, 92, 99, 203, 322). For each location: if it's YAML frontmatter or a validation table row defining `concurrency` as an input, delete the entry entirely. If it's a code example passing `concurrency=N`, remove the argument. If it's prose describing user-configurable concurrency, replace with: "Parallel feature execution is throttled by the tier-based adaptive semaphore (1-3 workers depending on API subscription tier)." Acceptance criteria: `grep -in 'concurrency' skills/overnight/SKILL.md` returns only references to the tier-based system, not to a user-configurable concurrency parameter; `just test` exits 0.

8. **[must-have] Update orchestrator round prompt**: In `orchestrator-round.md`, remove `concurrency=2` from the `generate_batch_plan()` call example at line 275 (remove the parameter entirely from the function call). Update line 202 from "understand batch assignments and concurrency configuration" to "understand batch assignments and the tier-based parallel dispatch limits" — this is a prompt that an LLM orchestrator reads at runtime, so the replacement must accurately describe what the plan file contains. Acceptance criteria: `grep -n 'concurrency=2' claude/overnight/prompts/orchestrator-round.md` returns no matches; `grep -n 'concurrency configuration' claude/overnight/prompts/orchestrator-round.md` returns no matches.

9. **[must-have] Update `docs/overnight.md`**: Remove or replace all references to concurrency as a user-configurable concept. The acceptance criteria must catch all forms — not just `--concurrency` but also plain "concurrency" references at lines 123, 137, 248-252, 251, 265. The section about "how concurrency interacts with git conflict detection" (lines 394-402) should be rewritten to describe the two orthogonal mechanisms: (1) area-separation in `group_into_batches()` prevents features sharing areas from running in the same round (conflict avoidance), and (2) the tier-based adaptive semaphore in `ConcurrencyManager` limits parallel features based on API subscription tier (resource protection). Reference `backlog.py:group_into_batches()` for the area-separation mechanism — the agent must read this function to write an accurate description. Acceptance criteria: `grep -in 'concurrency' docs/overnight.md` returns no matches for user-configurable concurrency concepts (references to the tier-based system or ConcurrencyManager are acceptable); the conflict-interaction section describes both area-separation and the tier semaphore as distinct mechanisms.

10. **[must-have] Update `requirements/multi-agent.md`**: Update line 73 ("The concurrency cap (1-3) is a hard limit enforced by semaphore; it is not overridable at runtime by agents") to clarify this refers to the tier-based `ConcurrencyManager` semaphore, not a user-configurable cap. Update lines 40-41 ("concurrency configuration" as an input) to describe the tier-based system. Acceptance criteria: `grep -in 'concurrency' requirements/multi-agent.md` returns only references to the tier-based semaphore system, not to a user-configurable concurrency parameter.

11. **[must-have] Update `requirements/pipeline.md`**: Update line 29 ("concurrency configuration" as a Feature Execution input) to describe the tier-based system. Acceptance criteria: `grep -in 'concurrency configuration' requirements/pipeline.md` returns no matches.

12. **[must-have] Update remaining references**: Update `docs/agentic-layer.md` line 196 ("a concurrency limit to avoid resource contention") and `skills/skill-creator/references/contract-patterns.md` lines 199-202 (the `concurrency` input contract definition for the overnight skill — remove entirely). Acceptance criteria: `grep -in 'concurrency' docs/agentic-layer.md` returns no matches for user-configurable concurrency; `grep -in 'concurrency' skills/skill-creator/references/contract-patterns.md` returns no matches for the overnight skill's concurrency input definition.

13. **[should-have] Investigate inner-task parallelism**: Research whether unbounded inner-task parallelism (tasks within a feature firing via `asyncio.gather()` without semaphore gating) is a problem in practice. The investigation note must include: (a) typical task counts per dependency batch (cite specific plan.md files or code that determines batch size), (b) whether rate limit events from inner-task bursts appear in overnight event logs (cite specific log entries or their absence), (c) what `throttled_dispatch` in `throttle.py` actually does and whether any code path calls it (trace callers, don't infer intent). Produce a recommendation section with one of: (a) "not a problem in practice — no action needed", (b) "minor concern — file a backlog item for future work", or (c) "significant concern — implement bounds in this lifecycle". Acceptance criteria: Investigation note exists at `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md` with all three data points above and a clear recommendation; `just test` exits 0.

**Codebase-wide sweep**: After all requirements are implemented, run `grep -rn 'concurrency' --include='*.py' --include='*.md' . | grep -v throttle | grep -v node_modules | grep -v lifecycle/replace` and verify no remaining references describe concurrency as a user-configurable parameter. References to `ConcurrencyManager`, the tier-based system, or the term "concurrency" in unrelated contexts (e.g., asyncio concurrency patterns) are acceptable.

## Non-Requirements

- **NOT replacing `ConcurrencyManager`**: The tier-based adaptive semaphore in `throttle.py` is the correct runtime concurrency mechanism. It stays unchanged.
- **NOT adding file-level overlap analysis**: File-level overlap in `group_into_batches()` was assessed as high cost / moderate benefit. Area-separation remains the conflict-avoidance mechanism.
- **NOT implementing inner-task parallelism bounds**: This lifecycle only investigates and recommends. Implementation of bounds (if recommended) would be a separate backlog item.
- **NOT changing `group_into_batches()` or area-separation**: The round assignment algorithm is not being modified.

## Edge Cases

- **Existing batch plan files**: Historical batch plan markdown files in `lifecycle/sessions/` contain `concurrency_limit` rows. The parser's `if/elif` chain already falls through silently on unknown keys — removing the `concurrency_limit` branch preserves this behavior. A regression test (R3) protects against future parser changes that might add strict key validation.
- **`runner.sh` invocation**: `runner.sh:670-677` does not pass `--concurrency` — it passes `--tier`. Removing the CLI arg does not affect the primary execution path.
- **External scripts**: If any custom script passes `--concurrency` to `batch_runner.py`, it will get an argparse error after removal. This is acceptable — the flag had no runtime effect anyway.
- **Log consumers**: The `BATCH_ASSIGNED` log event currently includes `concurrency` in its details. Any log parsing that depends on this field will need updating. Replace with the tier-based concurrency value or remove the field.
- **`map_results.py` processing**: `map_results.py:154` calls `parse_master_plan()` on historical batch plan files — the regression test in R3 ensures this path remains functional.

## Technical Constraints

- `ConcurrencyManager` from `throttle.py` is the canonical runtime semaphore — must not be modified.
- `requirements/multi-agent.md` classifies the semaphore as a "hard architectural constraint" — removal is not permitted (this spec updates the requirements to clarify the constraint refers to the tier-based system, not a user-configurable cap).
- All changes must pass `just test`.
- Commit using `/commit` skill.

## Open Decisions

- None — all decisions resolved during interview.
