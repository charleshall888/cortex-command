# Plan: Replace spec dump with JIT loading in implement prompt

## Overview

Replace deterministic full-content spec injection with a dual-read pattern: `_get_spec_path()` returns an absolute path for task workers (JIT loading via implement.md), while `_read_spec_content()` returns file content for the brain agent (unchanged behavior). Gate learnings injection on both `progress.txt` and `orchestrator-note.md` emptiness.

## Tasks

### Task 1: Replace _read_spec_excerpt() with dual-read helpers and migrate all call sites
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Delete `_read_spec_excerpt()` and replace it with two new functions: `_get_spec_path(feature, spec_path)` returning an absolute path string, and `_read_spec_content(feature, spec_path)` returning file content. Migrate all call sites in one pass: `execute_feature` line ~793 splits into two calls (path for workers, content for brain), `_run_task` template dict changes `"spec_excerpt"` key to `"spec_path"`, and `_handle_failed_task` call passes content from `_read_spec_content()`.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Current function at lines 345-355: `_read_spec_excerpt(feature, spec_path)` tries explicit spec_path first, falls back to `lifecycle/{feature}/spec.md`, returns content or `"(No specification file found.)"`. New `_get_spec_path()` follows same resolution order but returns `str(Path(...).resolve())` — always absolute. New `_read_spec_content()` calls `_get_spec_path()` internally, reads the file, returns content or the fallback string. Call sites to update: (1) line ~793: replace `spec_excerpt = _read_spec_excerpt(feature, spec_path)` with `spec_path_resolved = _get_spec_path(feature, spec_path)` and `spec_content = _read_spec_content(feature, spec_path)`. (2) line ~820 in `_run_task` template dict: change `"spec_excerpt": spec_excerpt` to `"spec_path": spec_path_resolved`. (3) line ~926 in `_handle_failed_task` call: pass `spec_content` where `spec_excerpt` was passed. The `_handle_failed_task` parameter name `spec_excerpt` at line ~457 stays unchanged — it receives content, just from a new source. `BrainContext.spec_excerpt` field (brain.py:77) and brain template rendering (brain.py:219) are NOT modified. Note: `claude/pipeline/prompts/review.md` also uses `{spec_excerpt}` but is rendered by a different code path — do NOT modify it. `_read_spec_excerpt` is NOT exported from `claude/overnight/__init__.py` and NOT imported by any test file.
- **Verification**: `grep -c '_read_spec_excerpt' claude/overnight/batch_runner.py` = 0 — pass if count = 0 (old function fully removed). `grep -c '_get_spec_path' claude/overnight/batch_runner.py` >= 2 — pass if count >= 2 (definition + call). `grep -c '_read_spec_content' claude/overnight/batch_runner.py` >= 3 — pass if count >= 3 (definition + call in execute_feature + call in _handle_failed_task path). `grep -c '"spec_path"' claude/overnight/batch_runner.py` >= 1 — pass if count >= 1 (template dict key).
- **Status**: [ ] pending

### Task 2: Update implement.md for JIT spec loading
- **Files**: `claude/pipeline/prompts/implement.md`
- **What**: Replace the `{spec_excerpt}` placeholder with `{spec_path}` and add a JIT-read instruction, a working-directory exception for spec reads, and fallback guidance for inaccessible specs.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current template structure: line 9 has `## Specification Context`, line 11 has `{spec_excerpt}` (full content). Lines 14-15 have the working-directory restriction: "All source file reads and writes must stay within this directory. **Exception**: Exit reports must be written to `{integration_worktree_path}`..." — add a parallel exception for spec reads. The `{spec_path}` variable will contain an absolute path. Replace the "## Specification Context" section with a "## Specification Reference" section containing `{spec_path}` and an instruction to read it when task context is insufficient for disambiguation. Add a second named exception for spec reads parallel to the exit-report exception. Add fallback text: "If the spec file is not accessible, proceed with the task description alone and note the access issue in your exit report." Note: `claude/pipeline/prompts/review.md` also uses `{spec_excerpt}` but is rendered by a different code path — do NOT modify it.
- **Verification**: `grep -c 'spec_excerpt' claude/pipeline/prompts/implement.md` = 0 — pass if count = 0. `grep -c 'spec_path' claude/pipeline/prompts/implement.md` >= 1 — pass if count >= 1. `grep -c 'spec file' claude/pipeline/prompts/implement.md` >= 1 — pass if count >= 1. `grep -c 'not accessible' claude/pipeline/prompts/implement.md` >= 1 — pass if count >= 1.
- **Status**: [ ] pending

### Task 3: Add learnings gating in _run_task()
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Gate the `_read_learnings(feature)` call inside `_run_task()`. Check if both `lifecycle/{feature}/learnings/progress.txt` and `lifecycle/{feature}/learnings/orchestrator-note.md` are absent or empty. If both are absent/empty, use the fallback stub `"(No prior learnings.)"` instead of calling `_read_learnings()`. If either has content, call `_read_learnings()` normally.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Current code in `_run_task()`: `learnings = _read_learnings(feature)`. The gate checks two files: `Path(f"lifecycle/{feature}/learnings/progress.txt")` and `Path(f"lifecycle/{feature}/learnings/orchestrator-note.md")`. Use `.exists()` and `.read_text().strip()` pattern (consistent with `_read_learnings()` internal checks). Important: the gate applies ONLY in `_run_task()`. The brain path in `_handle_failed_task` continues to call `_read_learnings(feature)` unconditionally — do NOT add gating there (R5).
- **Verification**: `grep -c 'progress.txt' claude/overnight/batch_runner.py` >= 2 — pass if count >= 2 (existing usage in `_read_learnings` + new gate check in `_run_task`). `grep -c 'orchestrator-note.md' claude/overnight/batch_runner.py` >= 2 — pass if count >= 2 (existing usage in `_read_learnings` + new gate check in `_run_task`).
- **Status**: [ ] pending

### Task 4: Run full test suite and verify acceptance criteria
- **Files**: (none — verification only)
- **What**: Run `just test` and verify all grep-based acceptance criteria from the spec.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: Run `just test` — must exit 0. Then verify all grep-based criteria: `grep -c '_read_spec_excerpt' claude/overnight/batch_runner.py` = 0. `grep -c '_get_spec_path' claude/overnight/batch_runner.py` >= 2. `grep -c '_read_spec_content' claude/overnight/batch_runner.py` >= 3. `grep -c 'spec_excerpt' claude/pipeline/prompts/implement.md` = 0. `grep -c 'spec_path' claude/pipeline/prompts/implement.md` >= 1. `grep -c 'complete, untruncated' claude/overnight/prompts/batch-brain.md` >= 2. Confirm `batch-brain.md`, `brain.py`, and `review.md` are unmodified via `git diff`.
- **Verification**: `just test` exits 0 — pass if exit code = 0
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete:
1. `just test` exits 0 — regression gate
2. `grep -c '_read_spec_content' claude/overnight/batch_runner.py` >= 3 — confirms brain path is wired (definition + execute_feature + _handle_failed_task)
3. `grep -c '_read_spec_excerpt' claude/overnight/batch_runner.py` = 0 — confirms old function fully removed
4. Confirm `batch-brain.md` is unmodified (`git diff claude/overnight/prompts/batch-brain.md` shows no changes)
5. Confirm `brain.py` is unmodified (`git diff claude/overnight/brain.py` shows no changes)
6. Confirm `review.md` is unmodified (`git diff claude/pipeline/prompts/review.md` shows no changes)
