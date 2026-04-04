# Specification: Replace spec dump with JIT loading in implement prompt

## Problem Statement

The overnight runner front-loads large context into every task worker and brain agent invocation. `_read_spec_excerpt()` injects the full spec (2,000-4,200 tokens) into every task's system prompt regardless of whether the task needs it. `_read_learnings()` injects full accumulated learnings into every task including those in clean-run features with no failures. This wastes 24,000-50,000 tokens per batch round across parallel workers, pollutes the attention window with irrelevant content, and violates Anthropic's context engineering principle of passing identifiers and letting agents retrieve what they need.

## Requirements

### R1: JIT spec loading in task workers

Replace the `{spec_excerpt}` template variable in `claude/pipeline/prompts/implement.md` with a `{spec_path}` variable containing the absolute filesystem path to the spec file. Add an instruction directing the agent to read the spec on demand when task context is insufficient. Add a spec-read exception to the working-directory restriction (following the existing exit-report exception pattern at line 15).

**Acceptance criteria**:
- (a) `grep -c 'spec_excerpt' claude/pipeline/prompts/implement.md` = 0 (placeholder removed)
- (b) `grep -c 'spec_path' claude/pipeline/prompts/implement.md` >= 1 (new placeholder present)
- (c) `grep -c 'spec file' claude/pipeline/prompts/implement.md` >= 1 (JIT-read instruction present referencing the spec file)
- (d) implement.md contains a named exception for spec reads from the working-directory restriction, parallel to the existing exit-report exception ("Exception: Exit reports must be written to...")

### R2: Replace `_read_spec_excerpt()` with `_get_spec_path()`

Replace the function in `claude/overnight/batch_runner.py` to return the resolved absolute filesystem path (string) instead of file content. The function must resolve to an absolute path using the batch runner's CWD so the path is valid from any agent working directory (including worktrees under `$TMPDIR`).

**Acceptance criteria**:
- (a) `grep -c '_read_spec_excerpt' claude/overnight/batch_runner.py` = 0 (old function removed)
- (b) `grep -c '_get_spec_path' claude/overnight/batch_runner.py` >= 2 (function definition + at least one call site)
- (c) The function returns an absolute path string (verified by: the return value starts with `/` in all code paths, including the fallback to `lifecycle/{feature}/spec.md`)

### R3: Update `_run_task()` template variables

Change the template variable dictionary in `_run_task()` to pass `spec_path` (the resolved absolute path string) instead of `spec_excerpt` (file content).

**Acceptance criteria**:
- (a) `grep -c '"spec_excerpt"' claude/overnight/batch_runner.py` = 0 in the `_run_task` template variables dict
- (b) `grep -c '"spec_path"' claude/overnight/batch_runner.py` >= 1 in the `_run_task` template variables dict

### R4: Failure-gated learnings injection in task workers

In `_run_task()`, gate the learnings injection on learnings file content. If both `lifecycle/{feature}/learnings/progress.txt` AND `lifecycle/{feature}/learnings/orchestrator-note.md` are absent or empty, inject the fallback stub `"(No prior learnings.)"` instead of calling `_read_learnings()`. If either file has content, call `_read_learnings()` normally (it reads both files and returns whatever has content).

**Acceptance criteria**:
- (a) In `batch_runner.py`, `_run_task()` checks for existence and non-emptiness of both `progress.txt` and `orchestrator-note.md` before calling `_read_learnings()`, injecting the stub only when both are absent/empty
- (b) Interactive/session-dependent: Verify that a task in a clean-run feature (no prior failures, no orchestrator notes) receives `"(No prior learnings.)"` instead of full learnings content. Rationale: requires a running overnight session to observe actual prompt content.

### R5: Brain agent context unchanged

The brain agent (`_handle_failed_task()` → `BrainContext` → `batch-brain.md`) must continue to receive full, untruncated learnings, spec excerpt, and last attempt output. No changes to `batch-brain.md`, `brain.py`, or the brain-related code paths in `batch_runner.py`.

**Acceptance criteria**:
- (a) `grep -c 'complete, untruncated' claude/overnight/prompts/batch-brain.md` >= 2 (labels preserved)
- (b) `_handle_failed_task()` in `batch_runner.py` still calls `_read_learnings(feature)` without gating or truncation
- (c) `grep -c 'BrainContext' claude/overnight/batch_runner.py` >= 1 in `_handle_failed_task()`, confirming BrainContext is still constructed

### R6: Brain spec content loading via dedicated helper

Since `_read_spec_excerpt()` is being replaced with a path-returning function, introduce a `_read_spec_content()` helper that reads the spec file content at the resolved path. This helper is used exclusively by the brain code path in `_handle_failed_task()`. It must follow the same resolution order as the current `_read_spec_excerpt()`: try explicit `spec_path` first, fall back to `lifecycle/{feature}/spec.md`, return `"(No specification file found.)"` if neither exists.

**Acceptance criteria**:
- (a) `grep -c '_read_spec_content' claude/overnight/batch_runner.py` >= 2 (function definition + at least one call site in `_handle_failed_task`)
- (b) The function reads the spec file and returns its text content (not a path string)
- (c) `_handle_failed_task()` passes the output of `_read_spec_content()` to `BrainContext.spec_excerpt`

### R7: Error handling for inaccessible specs

If the spec file does not exist at the resolved path, the implement.md template must include a clear instruction for the agent to report the issue in its exit report rather than failing silently.

**Acceptance criteria**:
- (a) `grep -c 'not accessible' claude/pipeline/prompts/implement.md` >= 1 (fallback instruction present)

### R8: Existing tests pass

All existing tests must continue to pass after the changes.

**Acceptance criteria**:
- (a) `just test` exits 0

## Non-Requirements

- **Brain agent truncation**: No changes to brain context volume. Brain keeps full learnings, spec, and last_attempt_output. This is a deliberate scope exclusion based on the finding that brain decisions are irreversible and high-stakes.
- **Spec content summarization or section extraction**: No smart parsing of spec content. The approach is path-based JIT, not content-aware filtering.
- **Token measurement instrumentation**: No logging of before/after token counts. The token math is well-supported by measured spec sizes (2,000-4,200 tokens across existing lifecycle directories).
- **Per-task learnings filtering**: No parsing of learnings content to extract task-specific entries. The gate is binary (has content / no content), not content-aware.
- **Spec versioning or freezing**: No spec hash stored in completion tokens. Spec drift on session resume is an edge case handled by the existing orchestrator's plan hash mismatch detection.
- **Changes to retry.py or merge_recovery.py**: Learnings injection in recovery code paths is out of scope. Only `_run_task()` in batch_runner.py is modified.

## Edge Cases

- **Missing spec file**: If the spec file does not exist at the absolute path AND the fallback `lifecycle/{feature}/spec.md` also does not exist, the implement.md prompt should contain the path and the agent should proceed with the task description alone, noting the access issue in its exit report.
- **Empty progress.txt**: If `progress.txt` exists but contains only whitespace, treat it as absent — inject the fallback stub. The `.strip()` check already exists in `_read_learnings()`.
- **Spec path with special characters**: Feature names may contain hyphens and numbers. The path string passed to the template must be properly formed. The current path construction via `Path()` and f-strings already handles this.

## Technical Constraints

- **Template variable type**: All template variables in `_render_template()` must be strings. `spec_path` must be a string, not a Path object.
- **Absolute paths for cross-CWD access**: `_get_spec_path()` must return absolute paths because task agents run in worktrees (`$TMPDIR/overnight-worktrees/...`) with a different CWD than the batch runner. Relative paths like `lifecycle/{feature}/spec.md` resolve against the agent's worktree where no `lifecycle/` directory exists. Use `Path.cwd() / relative_path` or equivalent in the batch runner process to produce absolute paths.
- **Dual-read pattern**: The spec file is accessed in two distinct ways after this change: (1) `_get_spec_path()` returns the absolute path for task workers (JIT reading), and (2) `_read_spec_content()` returns file content for the brain agent (deterministic injection). Both functions share the same resolution order (explicit spec_path → fallback to `lifecycle/{feature}/spec.md`) but return different types. This is the core architectural consequence of exempting the brain from JIT loading.
- **Sandbox allowlist**: Task agents can read from `integration_base_path` (passed at batch_runner.py:851 as `Path.cwd()`). The spec file at `lifecycle/{feature}/spec.md` is within this allowlist, so JIT reading is accessible from sandboxed worktrees when using absolute paths.
- **Function naming convention**: `_read_*()` functions return file content; `_get_*()` functions return references/identifiers. `_read_spec_content()` follows the content-returning convention; `_get_spec_path()` follows the reference-returning convention.
- **Fallback stub convention**: The existing fallback string `"(No prior learnings.)"` is used when learnings are absent. This convention must be preserved for the gated learnings path.

## Open Decisions

None.
