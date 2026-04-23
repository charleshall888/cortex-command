# Plan: Replace concurrency cap with conflict-aware round scheduling

## Overview

Parallel-first dead-code removal across ~12 files, removing the vestigial `BatchConfig.concurrency` field and all downstream references. Independent file changes run in parallel, with dependent tasks (test updates, regression test, codebase sweep) following. One substantive documentation rewrite (overnight docs conflict section) and one investigation (inner-task parallelism) complement the mechanical cleanup.

## Tasks

### Task 1: Remove BatchConfig.concurrency from batch_runner.py
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Delete the `concurrency: int = 3` field from `BatchConfig` dataclass (line 113), remove the `--concurrency` CLI argument from argparse (line 2053), and remove `"concurrency": config.concurrency` from the BATCH_ASSIGNED log event details dict (line 1521). The log event's `details` dict should retain `"features": feature_names` but drop the concurrency key entirely (the `ConcurrencyManager` is not yet created at that point in `run_batch()`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `BatchConfig` is a `@dataclass` at lines 95-119. The concurrency field is at line 113. The argparse setup is in `main()` starting at line 2047; `--concurrency` is at line 2053 and feeds into `BatchConfig(concurrency=args.concurrency)` at line 2083. The log event at line 1521 is called before `ConcurrencyManager` is created (line 1566), so `manager` is not in scope — remove the field rather than replacing.
- **Verification**: `python3 -c "from cortex_command.overnight.batch_runner import BatchConfig; assert not hasattr(BatchConfig, 'concurrency')"` — pass if no assertion error; `python3 -m cortex_command.overnight.batch_runner --help 2>&1 | grep -c 'concurrency'` — pass if count is 0 (the `--concurrency` flag is gone). Note: `batch_runner.py` contains many references to `ConcurrencyManager` (imports, type annotations, docstrings) which must remain — do not use a bare `grep 'concurrency'` as verification since those legitimate references will match.
- **Status**: [x] complete

### Task 2: Remove generate_batch_plan concurrency parameter
- **Files**: `claude/overnight/batch_plan.py`
- **What**: Delete the `concurrency: int` parameter from `generate_batch_plan()` function signature (line 20) and the `concurrency_limit` row from the markdown table it writes (line 105).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `generate_batch_plan(features, concurrency, ...)` at line 20. The table row at line 105 is `f"| concurrency_limit | {concurrency} |"`. After removal, the function should still generate the rest of the batch plan markdown table without the concurrency_limit row.
- **Verification**: `grep -n 'concurrency' claude/overnight/batch_plan.py` — pass if no matches found
- **Status**: [x] complete

### Task 3: Remove MasterPlanConfig.concurrency_limit from parser.py
- **Files**: `claude/pipeline/parser.py`
- **What**: Delete the `concurrency_limit: int = 3` field from `MasterPlanConfig` dataclass (line 35) and the `if key == "concurrency_limit"` branch in `_parse_config_table()` (lines 223-225). The remaining `if/elif` chain has no `else` clause, so unknown keys (including `concurrency_limit` in historical plans) fall through silently — no new handling needed.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `MasterPlanConfig` is a `@dataclass` at lines 30-40. `_parse_config_table()` at lines 215-234 uses an `if/elif/elif` chain to parse config keys. The `concurrency_limit` branch is first. After removal, the chain starts with `test_command`. Historical batch plan files in `lifecycle/sessions/` contain `concurrency_limit` rows — they must continue parsing successfully.
- **Verification**: `grep -n 'concurrency_limit' claude/pipeline/parser.py` — pass if no matches found
- **Status**: [x] complete

### Task 4: Add parser backward compatibility regression test
- **Files**: `claude/pipeline/tests/test_parser.py` (or `claude/overnight/tests/test_parser.py` — use whichever test directory exists for parser tests)
- **What**: Add a test that creates a batch plan markdown string containing a `concurrency_limit` config row and asserts `parse_master_plan()` parses it successfully without error. This protects the 4 historical plans in `lifecycle/sessions/` that `map_results.py:154` processes.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `parse_master_plan(path)` is the entry point in `parser.py`. It reads a markdown file and returns a `MasterPlanConfig` plus feature list. The config table format is `| key | value |` rows. The test should include a `| concurrency_limit | 2 |` row alongside valid keys like `| test_command | just test |` and verify the result has correct values for the known keys while not failing on the unknown one. Existing parser tests are in files matching `test_*parser*` or `test_map_results*`.
- **Verification**: `just test` — pass if exit 0 and the new test appears in output
- **Status**: [x] complete

### Task 5: Update smoke_test.py
- **Files**: `claude/overnight/smoke_test.py`
- **What**: Remove the `concurrency=1` keyword argument from the `BatchConfig(...)` constructor call at line 256.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Line 256 constructs `BatchConfig(concurrency=1, ...)`. After Task 1 removes the field, this line will fail. Remove only the `concurrency=1` argument; keep all other arguments.
- **Verification**: `grep -n 'concurrency' claude/overnight/smoke_test.py` — pass if no matches found
- **Status**: [x] complete

### Task 6: Update test_batch_plan.py
- **Files**: `claude/overnight/tests/test_batch_plan.py`
- **What**: Remove all `concurrency=` keyword arguments from `generate_batch_plan()` calls (7 instances across the file).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The test file calls `generate_batch_plan(features=[...], concurrency=N, ...)` in 7 test functions. After Task 2 removes the parameter, these calls will fail. Remove only the `concurrency=N` argument from each call; keep all other arguments.
- **Verification**: `grep -n 'concurrency' claude/overnight/tests/test_batch_plan.py` — pass if no matches found
- **Status**: [x] complete

### Task 7: Update plan.py session plan rendering
- **Files**: `claude/overnight/plan.py`
- **What**: Remove the `concurrency: int = 2` parameter from `render_session_plan()` at line 136 and replace the "Concurrency" output line at line 203 with user-facing text about the tier-based system. Do not use internal class names like `ConcurrencyManager` — the session plan is shown to the user for approval.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `render_session_plan(selection, concurrency=2, time_limit_hours=6, ...)` at line 136. Line 203 writes `f"- **Concurrency**: {concurrency} features per round"`. Replace with a line like `- **Parallel dispatch**: Tier-based adaptive throttle (1-3 workers depending on API subscription tier)`. The function also has a docstring at line 144 mentioning the concurrency parameter — update it. Callers: `skills/overnight/SKILL.md` line 92 passes `concurrency=2` — that caller is updated in Task 8.
- **Verification**: `grep -n 'concurrency' claude/overnight/plan.py` — pass if only matches are in the replacement text describing the tier system, not as a parameter or variable name
- **Status**: [x] complete

### Task 8: Update overnight skill SKILL.md
- **Files**: `skills/overnight/SKILL.md`
- **What**: Remove all references to `concurrency` as a user-configurable parameter. Line 7 (YAML input definition): delete the concurrency input entry. Line 37 (validation table row): delete the row. Line 92 (code example): remove `concurrency=2` from the `render_session_plan()` call. Line 99 (prose): remove "concurrency limit" from plan contents description. Line 203 (log event detail): remove concurrency from the details description. Line 322 (example plan header): remove "Max concurrency: 2". Where deletion leaves a gap, replace with brief reference to tier-based throttling.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: The SKILL.md is the prompt template for the `/overnight` skill that orchestrates overnight sessions. It instructs the agent how to call `render_session_plan()` and `generate_batch_plan()`. After Tasks 2 and 7 remove the concurrency parameters, the SKILL.md must stop telling the agent to pass them. Six specific locations need updating (lines 7, 37, 92, 99, 203, 322).
- **Verification**: `grep -in 'concurrency' skills/overnight/SKILL.md` — pass if remaining matches only reference the tier-based system (e.g., "tier-based adaptive throttle"), not a user-configurable concurrency parameter
- **Status**: [x] complete

### Task 9: Update orchestrator round prompt
- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Update line 202 from "understand batch assignments and concurrency configuration" to "understand batch assignments and the tier-based parallel dispatch limits". Remove `concurrency=2` from the `generate_batch_plan()` call example at line 275.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: This markdown file is a prompt template read by the orchestrator agent at runtime. Line 202 is an instruction telling the agent what to look for in the plan file. Line 275 is inside a code example showing how to call `generate_batch_plan()`. After Task 2, the function no longer accepts a concurrency parameter.
- **Verification**: `grep -n 'concurrency' claude/overnight/prompts/orchestrator-round.md` — pass if no matches found
- **Status**: [x] complete

### Task 10: Rewrite docs/overnight.md concurrency sections
- **Files**: `docs/overnight.md`
- **What**: Remove or replace all references to concurrency as a user-configurable concept. Key locations: line 123 (prose about concurrency limit), line 137 (execution strategy mention), line 191 (enforces concurrency limit), lines 248-252 (`### Concurrency` section), line 265 (batch_runner description), lines 385-392 (concurrency advice), lines 394-402 (concurrency-conflict interaction). The conflict-interaction section must be rewritten to describe two orthogonal mechanisms: (1) area-separation in `group_into_batches()` prevents features sharing areas from running in the same round (conflict avoidance), (2) tier-based adaptive semaphore in `ConcurrencyManager` limits parallel features based on API subscription tier (resource protection).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Read `claude/overnight/backlog.py` function `group_into_batches()` (area-separation logic at lines 946-954) to understand and accurately describe the conflict-avoidance mechanism. Read `claude/overnight/throttle.py` class `ConcurrencyManager` and `ThrottleConfig` to understand the resource-protection mechanism (tier defaults: MAX_5=1, MAX_100=2, MAX_200=3 workers). The replacement text must be accurate — this is user-facing documentation. Remove the `### Concurrency` section header and fold relevant content into the rewritten conflict section.
- **Verification**: `grep -in 'concurrency' docs/overnight.md` — pass if no matches describe user-configurable concurrency (matches referencing `ConcurrencyManager` or the tier system are acceptable); `grep -in '\-\-concurrency' docs/overnight.md` — pass if no matches found
- **Status**: [x] complete

### Task 11: Update requirements docs
- **Files**: `requirements/multi-agent.md`, `requirements/pipeline.md`
- **What**: In `multi-agent.md`: update line 73 ("The concurrency cap (1-3) is a hard limit enforced by semaphore") to clarify it refers to the tier-based `ConcurrencyManager` semaphore, not a user-configurable cap. Update lines 40-41 ("concurrency configuration" as input) to describe the tier-based system. In `pipeline.md`: update line 29 ("concurrency configuration" as Feature Execution input) to reference the tier-based system.
- **Depends on**: none
- **Complexity**: simple
- **Context**: These are authoritative requirements documents. The semaphore IS a hard architectural constraint — it's just not user-configurable. The update clarifies the constraint, not removes it. Line 73 should read something like "The tier-based concurrency limit (1-3 workers) is a hard limit enforced by `ConcurrencyManager`; it is not overridable at runtime by agents."
- **Verification**: `grep -in 'concurrency configuration' requirements/multi-agent.md requirements/pipeline.md` — pass if no matches found; `grep -in 'concurrency' requirements/multi-agent.md` — pass if matches only reference the tier-based semaphore system
- **Status**: [x] complete

### Task 12: Update remaining references
- **Files**: `docs/agentic-layer.md`, `skills/skill-creator/references/contract-patterns.md`
- **What**: In `agentic-layer.md`: update line 196 ("a concurrency limit to avoid resource contention") to reference the tier-based system. In `contract-patterns.md`: delete the `concurrency` input definition block (lines 199-202) from the overnight skill contract example.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `contract-patterns.md` has a YAML block defining `name: concurrency`, `type: integer`, `required: false`, `description: "Maximum number of features executing in parallel per round. Defaults to 2."` — this teaches the skill-creator to emit a parameter that no longer exists. Delete the entire 4-line block.
- **Verification**: `grep -in 'concurrency' docs/agentic-layer.md` — pass if no matches for user-configurable concurrency; `grep -in 'concurrency' skills/skill-creator/references/contract-patterns.md` — pass if no matches for the overnight skill concurrency input
- **Status**: [x] complete

### Task 13: Investigate inner-task parallelism
- **Files**: `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md`
- **What**: Research whether unbounded inner-task parallelism is a problem in practice. The investigation must include three specific data points: (a) typical task counts per dependency batch (examine plan.md files and code that determines batch sizes), (b) whether rate limit events from inner-task bursts appear in overnight event logs (search `lifecycle/sessions/*/overnight-events.log` and `lifecycle/*/events.log` for rate_limit events), (c) what `throttled_dispatch` in `throttle.py` actually does and whether any code path calls it (trace callers with grep). Produce a recommendation: (a) not a problem, (b) minor concern — file backlog item, or (c) significant concern.
- **Depends on**: none
- **Complexity**: complex
- **Context**: `ConcurrencyManager` in `throttle.py` (lines 107-200) gates feature-level parallelism. Within each feature, `execute_feature` runs dependency batches where tasks fire via `asyncio.gather()` without semaphore gating. The `throttled_dispatch` function exists in `throttle.py` but may be unused by the primary execution path. Check `batch_runner.py` for `throttled_dispatch` imports/calls. Check `brain.py` line 194-196 for notes about avoiding deadlock.
- **Verification**: file exists at `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md` with all three data points documented and a clear recommendation — `test -f lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md` exits 0
- **Status**: [x] complete

### Task 14: Codebase-wide sweep and final test
- **Files**: none (read-only validation)
- **What**: Run a codebase-wide grep to verify no remaining references describe concurrency as a user-configurable parameter. Run `just test` to verify all changes pass. Report any straggling references for manual review.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
- **Complexity**: simple
- **Context**: Run `grep -rn 'concurrency' --include='*.py' --include='*.md' . | grep -v throttle | grep -v node_modules | grep -v lifecycle/replace | grep -v __pycache__` and inspect results. References to `ConcurrencyManager`, the tier system, or unrelated uses of "concurrency" (e.g., asyncio patterns) are acceptable. References to `--concurrency`, `concurrency=N`, `concurrency_limit`, or prose describing user-configurable concurrency are failures.
- **Verification**: `just test` — pass if exit 0; codebase grep returns no user-configurable concurrency references
- **Status**: [x] complete

## Verification Strategy

After all tasks complete:
1. `just test` exits 0 — all existing and new tests pass
2. `grep -rn 'concurrency' --include='*.py' --include='*.md' . | grep -v throttle | grep -v node_modules | grep -v lifecycle/replace | grep -v __pycache__` returns only acceptable references (tier system, ConcurrencyManager, unrelated asyncio patterns)
3. `python3 -c "from cortex_command.overnight.batch_runner import BatchConfig; print(BatchConfig.__dataclass_fields__.keys())"` does not include `concurrency`
4. `python3 -m cortex_command.overnight.batch_runner --help` does not list `--concurrency`
5. The parser backward compatibility test passes (historical plans with `concurrency_limit` rows parse without error)
6. `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md` exists with a clear recommendation
