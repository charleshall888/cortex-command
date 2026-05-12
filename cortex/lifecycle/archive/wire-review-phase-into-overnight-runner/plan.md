# Plan: Wire review phase into overnight runner

## Overview

Add post-merge review dispatch to the overnight batch runner by creating a `review_dispatch.py` module in `claude/pipeline/` that encapsulates the gating check, review agent dispatch, 2-cycle rework loop, and deferral handling. Wire this into both batch_runner post-merge success paths via a single `dispatch_review()` call, and update the morning review walkthrough to gate synthetic events on the review matrix.

## Tasks

### Task 1: Add read_tier() and requires_review() to claude/common.py
- **Files**: `claude/common.py`
- **What**: Add two utility functions: `read_tier()` mirroring `read_criticality()` (scans events.log for last `"tier"` field, defaults to `"simple"`), and `requires_review(tier, criticality)` encoding the gating matrix (returns True for complex-tier at any criticality, or any tier at high/critical criticality).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `read_criticality(feature: str, lifecycle_base: Path = Path("lifecycle")) -> str` at line 161 of `claude/common.py` — mirror its pattern (open events.log, scan for last JSON line with target field, return value or default). The gating matrix: simple/low → skip, simple/medium → skip, complex/low → review, complex/medium → review, high/any → review, critical/any → review. Simplified: `return tier == "complex" or criticality in ("high", "critical")`.
- **Verification**: `python -c "from cortex_command.common import read_tier, requires_review; assert read_tier('nonexistent') == 'simple'; assert requires_review('complex', 'low') == True; assert requires_review('simple', 'medium') == False; print('ok')"` — pass if prints "ok" and exits 0.
- **Status**: [x] done

### Task 2: Update pipeline review prompt template
- **Files**: `claude/pipeline/prompts/review.md`
- **What**: Rewrite the pipeline review prompt to instruct the review agent to: (a) write its review to `lifecycle/{feature}/review.md` on disk, (b) include a verdict JSON block with `verdict`, `cycle`, `issues`, and `requirements_drift` fields, (c) include a `## Requirements Drift` section. Align output format with the interactive review protocol at `skills/lifecycle/references/review.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current pipeline prompt (`claude/pipeline/prompts/review.md`) uses placeholders `{feature}`, `{spec_excerpt}`, `{worktree_path}`, `{branch_name}`. Currently says "Produce your review as structured output" with plaintext `VERDICT:` format. Must change to JSON verdict block: `{"verdict": "APPROVED|CHANGES_REQUESTED|REJECTED", "cycle": 1, "issues": [...], "requirements_drift": "none|detected"}`. Interactive protocol at `skills/lifecycle/references/review.md` lines 113-117 shows the expected JSON format. Keep the same 4 placeholders.
- **Verification**: `grep -c 'review.md' claude/pipeline/prompts/review.md` >= 1 (file write instruction present). `grep -c '"cycle"' claude/pipeline/prompts/review.md` >= 1 (cycle field in verdict template). `grep -c 'requirements_drift' claude/pipeline/prompts/review.md` >= 1.
- **Status**: [x] done

### Task 3: Create review_dispatch.py with types and verdict parsing
- **Files**: `claude/pipeline/review_dispatch.py` (NEW)
- **What**: Create the review dispatch module with: `ReviewResult` dataclass (fields: `approved: bool`, `deferred: bool`, `verdict: str`, `cycle: int`, `issues: list[str]`), and `parse_verdict(review_path: Path) -> dict` function that reads `lifecycle/{feature}/review.md`, extracts the JSON verdict block via regex, and returns the parsed dict. Returns `{"verdict": "ERROR", "cycle": 0, "issues": []}` if the file doesn't exist or the JSON block is malformed.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The verdict JSON block in review.md is a fenced code block (` ```json ... ``` `) containing `{"verdict": "...", "cycle": N, "issues": [...], "requirements_drift": "..."}`. Use `re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)` to extract. Follow the pattern in `claude/pipeline/state.py` `log_event()` (lines 288-304) for JSON handling conventions.
- **Verification**: `python -c "from cortex_command.pipeline.review_dispatch import ReviewResult, parse_verdict; r = ReviewResult(approved=True, deferred=False, verdict='APPROVED', cycle=1, issues=[]); print(r.verdict)"` — pass if prints "APPROVED" and exits 0.
- **Status**: [x] done

### Task 4: Add dispatch_review() — single cycle + APPROVED/ERROR handling
- **Files**: `claude/pipeline/review_dispatch.py`
- **What**: Add the main `async def dispatch_review(...)` function that: (1) writes phase_transition implement→review to events.log, (2) reads spec for excerpt, (3) dispatches review agent via `dispatch_task()`, (4) parses verdict from review.md, (5) handles APPROVED (writes review_verdict + phase_transition review→complete + feature_complete to events.log, returns ReviewResult(approved=True)), (6) handles ERROR (writes review_verdict ERROR, returns ReviewResult(deferred=True)), (7) handles REJECTED at any cycle (writes deferral file, returns ReviewResult(deferred=True)). CHANGES_REQUESTED is stubbed as a pass-through to the deferral path — Task 5 adds the rework loop.
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**: Function signature: `async def dispatch_review(feature: str, worktree_path: Path, branch: str, spec_path: Path, complexity: str, criticality: str, lifecycle_base: Path = Path("lifecycle"), deferred_dir: Path = Path("lifecycle/deferred"), integration_branch: str = "", base_branch: str = "main", test_command: str | None = None, repo_path: Path | None = None, log_path: Path | None = None) -> ReviewResult`. The `branch` param is the actual git branch name (e.g. `pipeline/my-feature`), passed directly from the batch_runner caller which already knows `actual_branch`. The `repo_path` param receives the pre-computed effective merge repo path from the caller (via `_effective_merge_repo_path()`). The `log_path` param is the pipeline events log path for merge event logging. Use `dispatch_task()` from `claude.pipeline.dispatch` (accepts `task: str, system_prompt: str, complexity: str, criticality: str, worktree_path: Path`). Use `log_event()` from `claude.pipeline.state` (accepts `log_path: Path, event_dict: dict`) for per-feature events.log writes. Use `write_deferral()` from `claude.overnight.deferral` for deferral files. Read prompt template from `claude/pipeline/prompts/review.md` and substitute placeholders — Task 2 must complete first to ensure the template produces the JSON verdict format that `parse_verdict()` expects.
- **Verification**: `python -c "from cortex_command.pipeline.review_dispatch import dispatch_review; import inspect; sig = inspect.signature(dispatch_review); assert 'feature' in sig.parameters; assert 'branch' in sig.parameters; assert 'log_path' in sig.parameters; print('ok')"` — pass if prints "ok" and exits 0.
- **Status**: [x] done

### Task 5: Add rework loop — CHANGES_REQUESTED handling
- **Files**: `claude/pipeline/review_dispatch.py`
- **What**: Replace the CHANGES_REQUESTED stub in dispatch_review() with the full rework flow: (1) write review feedback to `lifecycle/{feature}/learnings/orchestrator-note.md`, (2) dispatch a fresh fix agent with review findings + spec excerpt + worktree path, (3) SHA circuit breaker — if before_sha == after_sha, defer immediately, (4) re-merge via `merge_feature()`, (5) dispatch cycle 2 review using the same prompt template, (6) parse cycle 2 verdict, (7) if APPROVED return success, (8) if non-APPROVED write deferral and return deferred. Also handle fix agent failure (defer with cycle 1 feedback + failure reason) and re-merge failure (defer with merge failure reason).
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: `merge_feature()` from `claude.pipeline.merge` — full signature: `merge_feature(feature: str, base_branch: str = "main", test_command: str = None, log_path: Path = None, ci_check: bool = True, branch: str | None = None, repo_path: Path | None = None) -> MergeResult`. For re-merge after rework, call with: `merge_feature(feature, base_branch=base_branch, test_command=test_command, log_path=log_path, ci_check=False, branch=branch, repo_path=repo_path)`. Note `ci_check=False` — re-merging after a fix should not re-gate on CI (matches `merge_recovery.py` pattern at lines 268, 370). All parameters are available from `dispatch_review()`'s own signature. For SHA circuit breaker: `subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, cwd=worktree_path)` before and after fix agent dispatch. Learnings path: `lifecycle/{feature}/learnings/orchestrator-note.md` — create `learnings/` dir if needed. Fix agent prompt should include: `## Review Feedback\n{issues from review.md}\n\n## Spec\n{spec_excerpt}\n\nFix only the flagged issues in the worktree at {worktree_path}.` Use `dispatch_task()` for fix agent dispatch. Deferral file at `lifecycle/deferred/{feature}-review.md` — use `write_deferral()` with `severity="blocking"`.
- **Verification**: `grep -c 'orchestrator-note' claude/pipeline/review_dispatch.py` >= 1. `grep -c 'merge_feature\|before_sha\|after_sha' claude/pipeline/review_dispatch.py` >= 2.
- **Status**: [x] done

### Task 6: Wire dispatch_review into batch_runner post-merge paths
- **Files**: `claude/overnight/batch_runner.py`
- **What**: In both post-merge success paths, insert review dispatch logic between the merge success check and the existing `FEATURE_COMPLETE` log. If `requires_review()` returns False, fall through to existing flow. If True, call `dispatch_review()` and branch on result.
- **Depends on**: [1, 4, 5]
- **Complexity**: complex
- **Context**: **Critical sync/async constraint**: `_apply_feature_result` (line ~1200) is a **sync** function (`def`, not `async def`) — it was deliberately extracted as sync for unit testability (docstring: "directly unit-testable without driving the full async run_batch() call chain"). It CANNOT `await` the async `dispatch_review()`. The two insertion points require different approaches:
  - **`_accumulate_result`** (line ~1569, async inner function): Can directly `await dispatch_review(...)` at line ~1654 after `merge_result.success`. Pass `branch=actual_branch`, `repo_path=_effective_merge_repo_path(...)`, `log_path=config.pipeline_events_path` from the closure scope.
  - **`_apply_feature_result`** (line ~1200, sync function): The async **caller** of `_apply_feature_result` must call `dispatch_review()` BEFORE invoking `_apply_feature_result`, then pass the `ReviewResult` (or `None` if review not required) as a new parameter. Add `review_result: ReviewResult | None = None` to `_apply_feature_result`'s signature. The caller computes: `review_result = await dispatch_review(...) if requires_review(tier, criticality) else None`, then passes it. Inside `_apply_feature_result`, branch on `review_result`: if `None` (no review needed) or `review_result.approved`, continue to existing FEATURE_COMPLETE flow; if `review_result.deferred`, set feature status to deferred, write back to backlog as in_progress, cleanup worktree, and return.
  Import `requires_review` from `claude.common`, `dispatch_review` and `ReviewResult` from `claude.pipeline.review_dispatch`. Update all 4 existing call sites of `_apply_feature_result` (lines ~1584, ~1631, ~1725, ~1740) to pass the new `review_result` parameter (compute it in the async caller before the call).
- **Verification**: `grep -c 'requires_review' claude/overnight/batch_runner.py` >= 2. `grep -c 'dispatch_review' claude/overnight/batch_runner.py` >= 2. `grep -c 'review_result' claude/overnight/batch_runner.py` >= 4 (parameter in signature + usage in 4 call sites).
- **Status**: [x] done

### Task 7: Update morning review walkthrough for conditional synthetic events
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: In section 2b, add a gating check before writing synthetic events for each merged feature: (1) read tier and criticality from events.log, (2) call `requires_review(tier, criticality)`, (3) if feature should NOT have been reviewed: write synthetic events as today, (4) if feature SHOULD have been reviewed: check for real review_verdict (cycle >= 1) and feature_complete — if both present skip synthetics, if review_verdict present but feature_complete missing write remaining events (crash recovery), if neither present note the error in walkthrough output.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Section 2b currently starts at line ~84 of `walkthrough.md`. The existing guard checks for `"event": "feature_complete"` in events.log content. Add the tier/criticality check BEFORE the existing guard. Reference `requires_review()` from `claude.common` — the walkthrough is a skill reference doc that instructs an agent, so reference the function by name (the agent will import and call it, or replicate the logic). The `cycle: 0` marker must remain in the synthetic events for features that legitimately skip review.
- **Verification**: `grep -c 'requires_review\|read_tier\|read_criticality' skills/morning-review/references/walkthrough.md` >= 2. `grep -c 'cycle.*0' skills/morning-review/references/walkthrough.md` >= 1.
- **Status**: [x] done

### Task 8: Add tests for utility functions
- **Files**: `tests/test_common_utils.py` (NEW), `claude/pipeline/tests/test_review_dispatch.py` (NEW)
- **What**: Add unit tests for: (1) `read_tier()` — test with existing events.log containing tier field, test with empty file, test with missing file (defaults to "simple"), test with complexity_override event. (2) `requires_review()` — test all 8 cells of the gating matrix. (3) `parse_verdict()` — test with valid JSON block, test with malformed JSON, test with missing file. Create test fixtures with temporary lifecycle directories.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**: Existing test pattern: `claude/pipeline/tests/test_dispatch.py` uses `pytest` with `tmp_path` fixture for temporary directories. Follow the same pattern. For `read_tier` tests, create temporary `lifecycle/{feature}/events.log` files with known content. For `parse_verdict` tests, create temporary `review.md` files with known verdict blocks. Test command: `just test` (from lifecycle.config.md).
- **Verification**: `just test` — pass if exit 0, all tests pass.
- **Status**: [x] done

## Verification Strategy

After all tasks complete:
1. Run `just test` — all existing and new tests must pass
2. Verify the full integration: `grep -c 'dispatch_review' claude/overnight/batch_runner.py` >= 2 AND `grep -c 'requires_review' claude/overnight/batch_runner.py` >= 2 AND `grep -c 'def requires_review' claude/common.py` = 1 AND `grep -c 'async def dispatch_review' claude/pipeline/review_dispatch.py` = 1
3. End-to-end verification is session-dependent: requires running an overnight batch with a complex/high feature to confirm the review dispatch path executes correctly
