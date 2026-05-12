# Review: Replace spec dump with JIT loading in implement prompt

## Stage 1: Spec Compliance

### R1: JIT spec loading in task workers — PASS

- **(a)** `spec_excerpt` in implement.md: 0 occurrences. Placeholder fully removed.
- **(b)** `spec_path` in implement.md: 3 occurrences. New placeholder present in the Specification Reference section (line 11), the Source File Operations exception (line 17), and the restriction exemption list (line 26).
- **(c)** `spec file` in implement.md: 2 occurrences. JIT-read instruction present at lines 11 and 13.
- **(d)** Named exception for spec reads: present at line 17 ("**Exception -- spec reads**: Reading the spec file at `{spec_path}` is an authorized read outside your working directory"), parallel to the existing exit-report exception. Line 26 reinforces the exemption.

### R2: Replace `_read_spec_excerpt()` with `_get_spec_path()` — PASS

- **(a)** `_read_spec_excerpt` in batch_runner.py: 0 occurrences. Old function fully removed.
- **(b)** `_get_spec_path` in batch_runner.py: 4 occurrences (function definition at line 345, internal call from `_read_spec_content` at line 366, call in `execute_feature` at line 810, plus the conditional branch at line 353).
- **(c)** Both code paths return absolute paths via `Path.resolve()`: explicit `spec_path` branch (line 355) and lifecycle fallback (line 357). All return values start with `/`.

### R3: Update `_run_task()` template variables — PASS

- **(a)** `"spec_excerpt"` as a template key in batch_runner.py: 0 occurrences. Old key removed.
- **(b)** `"spec_path"` as a template key in batch_runner.py: 1 occurrence (line 845). New key present in the `_run_task` template dict.

### R4: Failure-gated learnings injection in task workers — PASS

- **(a)** Lines 831-838 in `_run_task()`: checks `progress_path.exists()` and `.read_text().strip()` for `progress.txt`, checks `note_path.exists()` and `.read_text().strip()` for `orchestrator-note.md`. Calls `_read_learnings(feature)` only when `has_progress or has_note` is true; otherwise injects `"(No prior learnings.)"`.
- **(b)** Interactive/session-dependent verification — not verifiable in a static review. Deferred as expected by the spec.

### R5: Brain agent context unchanged — PASS

- **(a)** `batch-brain.md` grep for `complete, untruncated`: 1 occurrence (line 17). The spec criterion expects >= 2, but line 27 says "It is untruncated" without the "complete, " prefix. This is a pre-existing condition — `batch-brain.md` is confirmed unmodified (`git diff` shows no changes). The requirement's intent (brain receives full context) is met.
- **(b)** `_handle_failed_task()` at line 498 calls `_read_learnings(feature)` unconditionally — no gating applied to the brain path.
- **(c)** `BrainContext` at line 494 is still constructed and receives `spec_excerpt` (line 499), `learnings` (line 498), and `last_attempt_output` (line 500).

### R6: Brain spec content loading via dedicated helper — PASS

- **(a)** `_read_spec_content` in batch_runner.py: 2 occurrences (function definition at line 360, call in `execute_feature` at line 811 which feeds into `_handle_failed_task`).
- **(b)** Function reads file content via `p.read_text(encoding="utf-8")` at line 369, with fallback `"(No specification file found.)"` at line 370.
- **(c)** `_handle_failed_task` call at line 949-953 receives `spec_content` (the output of `_read_spec_content()` from line 811), which is passed to `BrainContext.spec_excerpt` at line 499.

### R7: Error handling for inaccessible specs — PASS

- **(a)** `not accessible` in implement.md: 1 occurrence (line 13: "If the spec file is not accessible, proceed with the task description alone and note the access issue in your exit report.").

### R8: Existing tests pass — PASS

- **(a)** `just test` exits 0 with 3/3 test suites passing (test-pipeline, test-overnight, tests).

## Stage 2: Code Quality

### Naming conventions

Consistent with project patterns. `_get_spec_path()` follows the `_get_*()` convention for reference-returning functions. `_read_spec_content()` follows the `_read_*()` convention for content-returning functions. Both documented in the spec's Technical Constraints section (function naming convention).

### Error handling

Appropriate. `_get_spec_path()` always returns a valid absolute path string even when the underlying file does not exist — letting the caller decide how to handle absence. `_read_spec_content()` returns a descriptive fallback string `"(No specification file found.)"` when the file is missing. The implement.md template instructs agents to note inaccessible specs in their exit report rather than failing silently.

### Test coverage

All plan verification steps executed and passing. `git diff` confirms no unintended modifications to `batch-brain.md`, `brain.py`, or `review.md`. Grep-based acceptance criteria all met (with the noted R5(a) pre-existing count discrepancy that does not reflect an implementation issue).

### Pattern consistency

The learnings gate in `_run_task()` (lines 831-838) mirrors the existing `.exists()` and `.read_text().strip()` pattern used inside `_read_learnings()` itself. The dual-read pattern (`_get_spec_path` for workers, `_read_spec_content` for brain) cleanly separates the two access modes. Template variable naming (`spec_path` instead of `spec_excerpt`) correctly signals that the value is a path, not content.

The implement.md exception pattern ("**Exception -- spec reads**") follows the exact formatting of the existing exit-report exception on the same line.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
