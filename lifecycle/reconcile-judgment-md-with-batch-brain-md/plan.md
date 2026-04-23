# Plan: reconcile-judgment-md-with-batch-brain-md

## Overview

Three-task dead-code removal: delete the orphaned `judgment.md` prompt, clean the two associated dead symbols from `events.py` (two Edit replacements, no intermediate commit), then add a `tests/test_events.py` regression file that enforces all three removals are complete and correct.

## Tasks

### Task 1: Delete claude/overnight/prompts/judgment.md
- **Files**: `claude/overnight/prompts/judgment.md` (delete)
- **What**: Remove the orphaned prompt file from the repository. It has zero call sites, action vocabulary incompatible with the current `BrainAction` enum, and was superseded by `batch-brain.md` when `brain.py` was written.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The file to delete is `claude/overnight/prompts/judgment.md`. Before deleting, run `grep -rn "judgment\.md" claude/ --include="*.py" --include="*.sh"` — if any matches are returned, stop and investigate. If the grep is clean, proceed with deletion. The `claude/overnight/prompts/` directory should still contain `batch-brain.md`, `orchestrator-round.md`, and `repair-agent.md` after this task.
- **Verification**: `judgment.md` does not exist at `claude/overnight/prompts/judgment.md`; `grep -rn "judgment\.md" claude/ --include="*.py" --include="*.sh"` returns no matches. Commit using `/commit`.
- **Status**: [x] complete

### Task 2: Remove JUDGMENT_FAILED dead code from events.py
- **Files**: `claude/overnight/events.py`
- **What**: Remove the `JUDGMENT_FAILED = "judgment_failed"` constant definition and its entry in the `EVENT_TYPES` tuple. Both removals must be applied before committing — do not commit after only one of the two edits.
- **Depends on**: none
- **Complexity**: simple
- **Context**: In `claude/overnight/events.py`, apply two Edit tool replacements in sequence within this task: (1) find and remove the line `JUDGMENT_FAILED = "judgment_failed"` from the constants block (it appears between `SESSION_COMPLETE` and `HEARTBEAT`); (2) find and remove the entry `JUDGMENT_FAILED,` from the `EVENT_TYPES` tuple. Navigate to each by searching for the symbol name `JUDGMENT_FAILED`, not by line number. Do not commit between the two replacements — commit only after both are applied. After both edits, `JUDGMENT_FAILED` must not appear anywhere in `events.py`.
- **Verification**: `grep "JUDGMENT_FAILED" claude/overnight/events.py` returns no matches; `python3 -c "from cortex_command.overnight import events; assert not hasattr(events, 'JUDGMENT_FAILED')"` exits 0. Commit using `/commit` (may be combined with Task 1's commit if not yet committed).
- **Status**: [x] complete

### Task 3: Add regression tests for dead-code cleanup
- **Files**: `tests/test_events.py` (create new)
- **What**: Write a new pytest test file with three tests: one asserting `judgment.md` no longer exists in the repository, one asserting `JUDGMENT_FAILED` is no longer an attribute of the `events` module, and one asserting `log_event("judgment_failed", round=1)` raises `ValueError`. This machine-checks all three cleanup deliverables via `just test`.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Follow the pattern in `tests/test_select_overnight_batch.py` — use `REPO_ROOT = Path(__file__).parent.parent` to get the repo root. The `log_event` function signature is `log_event(event: str, round: int, feature: Optional[str] = None, details: Optional[dict] = None, log_path: Path = DEFAULT_LOG_PATH) -> None`. It raises `ValueError` when `event not in EVENT_TYPES`. For the `log_path` in `test_judgment_failed_raises_value_error`, use `tmp_path / "test-events.log"` (pytest's `tmp_path` fixture) so the test does not write to the live lifecycle directory. `log_event` raises `ValueError` before any file write, so `tmp_path` may not be strictly necessary for the ValueError to surface, but using it is correct practice. Write three test functions: `test_judgment_md_deleted()`, `test_judgment_failed_constant_removed()`, and `test_judgment_failed_raises_value_error(tmp_path)`. For `test_judgment_md_deleted`, assert `not (REPO_ROOT / "claude/overnight/prompts/judgment.md").exists()`.
- **Verification**: `tests/test_events.py` exists; `just test` exits 0 and includes `tests/test_events.py` in the collected tests; all three test functions pass when run with `python3 -m pytest tests/test_events.py -v`. Commit using `/commit`.
- **Status**: [x] complete

## Verification Strategy

After all three tasks are complete:

1. Confirm file deletion: `ls claude/overnight/prompts/` lists `batch-brain.md`, `orchestrator-round.md`, and `repair-agent.md` — `judgment.md` is absent.
2. Confirm events.py clean: `grep "JUDGMENT_FAILED" claude/overnight/events.py` returns no matches; `python3 -c "from cortex_command.overnight import events; assert not hasattr(events, 'JUDGMENT_FAILED')"` exits 0.
3. Confirm test coverage: `just test` exits 0; output shows `tests/test_events.py` collected and all three new tests passing.
4. Confirm no dead file references: `grep -rn "judgment\.md" claude/ --include="*.py" --include="*.sh"` returns no matches.
