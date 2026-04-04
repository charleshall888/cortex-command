# Plan: Fix next_question_id() race condition in deferral.py

## Overview

Fix four broken `_next_escalation_n()` TypeError call sites in batch_runner.py, then replace the TOCTOU-vulnerable scan-and-replace pattern in `write_deferral()` with an `O_EXCL` atomic-create loop, and update misleading documentation. TypeErrors first (high-confidence, real bug), O_EXCL second (defensive hardening).

## Tasks

### Task 1: Fix four TypeError call sites in batch_runner.py
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Add the missing `round` and `escalations_path` arguments to the four broken `_next_escalation_n()` calls at lines 707, 758, 1326, and 1645.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Each call currently passes only `feature` (or `name`). The correct 3-arg pattern is at lines 950-953: `_next_escalation_n(feature, config.batch_id, escalations_path)` where `escalations_path = Path("lifecycle/escalations.jsonl")`. At all four sites, `config.batch_id` is available — via the `config: BatchConfig` parameter at lines 707/758 (in `execute_feature`), line 1326 (in `_apply_feature_result`), and via closure at line 1645 (in `_accumulate_result` inside `run_batch`). `escalations_path` must be constructed locally as `Path("lifecycle/escalations.jsonl")` at each site, matching line 950.
- **Verification**: `python -c "import ast; tree = ast.parse(open('claude/overnight/batch_runner.py').read()); [print(n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n.func, 'id') and n.func.id == '_next_escalation_n' and len(n.args) < 3]"` — pass if no output (all calls have 3+ args)
- **Status**: [x] done

### Task 2: Replace write_deferral scan-and-replace with O_EXCL loop
- **Files**: `claude/overnight/deferral.py`
- **What**: Restructure `write_deferral()` to use `os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` with a retry loop on `FileExistsError`, replacing the current `next_question_id()` scan + `tempfile.mkstemp()` + `os.replace()` pattern. The scan remains as a starting-point hint (avoids unnecessary retries), but correctness no longer depends on it being accurate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current flow in `write_deferral()` (lines 150-204): (1) `next_question_id()` scans for max ID, (2) formats filename with that ID, (3) writes to temp file via `tempfile.mkstemp(dir=deferred_dir)`, (4) `os.replace(tmp_path, dest)`. New flow: (1) scan for starting ID via `next_question_id()`, (2) loop: format filename, attempt `os.open(dest, O_CREAT | O_EXCL | O_WRONLY)`, on `FileExistsError` increment and retry (cap at ~100 attempts), (3) on success write content directly to the fd via `os.write()` and `os.close()`. Remove the `tempfile.mkstemp` + `os.replace` pattern. Keep the `BaseException` cleanup pattern (close fd + unlink on failure). The `deferred_dir.mkdir(parents=True, exist_ok=True)` call at line 171 stays. Update `question.question_id` with the ID that succeeded.
- **Verification**: `grep -c 'O_EXCL' claude/overnight/deferral.py` — pass if count >= 1
- **Status**: [x] done

### Task 3: Update docstring and add TOCTOU comment
- **Files**: `claude/overnight/deferral.py`
- **What**: Replace the misleading "Thread-safe via filesystem — no in-memory counters" docstring in `next_question_id()` with accurate documentation of the O_EXCL mechanism. Add a code comment to `_next_escalation_n()` documenting the theoretical TOCTOU exposure and why it is safe under the current architecture.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `next_question_id()` docstring is at line 97 of `deferral.py`. The function is still used as a starting-point hint after Task 2, but correctness no longer depends on it — the docstring should reflect this (e.g., "Returns a hint for the next available ID; actual uniqueness is enforced by O_EXCL in write_deferral"). `_next_escalation_n()` at line 389 has no TOCTOU documentation — add a comment explaining: the race requires same feature+round concurrent execution, which the current single-coroutine-per-feature dispatch model prevents; the JSONL append pattern makes O_EXCL inapplicable here.
- **Verification**: `grep -c 'Thread-safe via filesystem' claude/overnight/deferral.py` — pass if count = 0; `grep -c 'TOCTOU' claude/overnight/deferral.py` — pass if count >= 1
- **Status**: [x] done

### Task 4: Run test suite
- **Files**: (none — verification only)
- **What**: Run the full test suite to verify no regressions from the changes in Tasks 1-3.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: Test command is `just test`. Deferral-specific tests are in `claude/overnight/tests/test_deferral.py`. The test file includes tests for `write_escalation()` and `_next_escalation_n()` (lines 208-265) as well as `write_deferral` tests.
- **Verification**: `just test` — pass if exit code = 0
- **Status**: [x] done

## Verification Strategy

After all tasks complete, run the full acceptance criteria from the spec:
1. `python -c "import ast; tree = ast.parse(open('claude/overnight/batch_runner.py').read()); [print(n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n.func, 'id') and n.func.id == '_next_escalation_n' and len(n.args) < 3]"` — no output
2. `grep -c 'O_EXCL' claude/overnight/deferral.py` >= 1
3. `grep -c 'TOCTOU' claude/overnight/deferral.py` >= 1
4. `grep -c 'Thread-safe via filesystem' claude/overnight/deferral.py` = 0
5. `just test` exits 0
