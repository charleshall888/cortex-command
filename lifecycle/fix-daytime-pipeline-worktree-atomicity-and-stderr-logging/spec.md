# Specification: fix-daytime-pipeline-worktree-atomicity-and-stderr-logging

## Problem Statement

`claude/pipeline/worktree.py::create_worktree` has two defects that hurt daytime-pipeline reliability. First, `git worktree add -b` creates the branch before performing checkout; if checkout fails, the branch persists as an orphan. `_resolve_branch_name`'s `-2`, `-3` fallback keeps retries moving, but accumulates orphan branches unboundedly across failures — lifecycle 69 (2026-04-17) required manual `git branch -D pipeline/{feature}` before retry could proceed. Second, `subprocess.run(..., check=True)` raises `CalledProcessError` whose `__str__` excludes stderr, so `daytime.log` captures only `returned non-zero exit status 128.` with no git error text. This is the barrier that made lifecycle 69 unreadable. The fix closes both defects without diagnosing lifecycle 69's underlying cause — surfacing stderr is what enables diagnosis on the next reproduction.

## Requirements

1. **Orphan-branch cleanup on failed `git worktree add -b`**: When `git worktree add -b` inside `create_worktree` returns non-zero, the function attempts to delete the resolved branch (`_resolve_branch_name(feature, repo)` return value) via `git branch -D <branch>` before raising. Acceptance: new test in `tests/test_worktree.py` pre-creates a **non-empty non-worktree directory** at the target `.claude/worktrees/{feature}` path (e.g., writes a sentinel file inside it), invokes `create_worktree(feature)`, asserts the call raises, and asserts `git branch --list pipeline/{feature}*` (run via `subprocess.run` in the test's temp repo) emits no output (exit 0 with empty stdout). `just test` exits 0. The non-empty requirement is load-bearing: git accepts an empty existing directory as a valid worktree target and the call succeeds, so an empty dir would not trigger the failure path the test is asserting about.

2. **Stderr surfaced in the raised exception message**: When `git worktree add -b` fails, the exception raised by `create_worktree` includes git's stderr verbatim in its message. Acceptance: the same test (or a paired test) asserts `str(exc)` matches `r"^worktree_creation_failed: .+"` where the `.+` portion is non-empty (contains the git stderr text). When stderr is empty, the message ends with `(no stderr)`. `just test` exits 0.

3. **Exception type**: `create_worktree` raises `ValueError` on git failure (matching `claude/pipeline/conflict.py:119-128` sibling-code precedent for this same `git worktree add -b` command). Acceptance: the test asserts `isinstance(exc, ValueError)` and `not isinstance(exc, subprocess.CalledProcessError)`. No caller in the current repo catches `CalledProcessError` from this function (`claude/overnight/daytime_pipeline.py:314` uses `except Exception`; `orchestrator.py:162` and `smoke_test.py:250` do not catch); the type change is safe.

4. **Silent best-effort cleanup**: If the cleanup `git branch -D` call itself returns non-zero, the error is swallowed and the original git-stderr-enriched `ValueError` is raised unchanged. Acceptance: a test patches `subprocess.run` so the cleanup call returns a non-zero `CompletedProcess`; asserts the original `ValueError` with `worktree_creation_failed:` prefix is still raised (no `cleanup` text added to the message). `just test` exits 0.

5. **Existing callers continue to work**: All current callers — `claude/overnight/daytime_pipeline.py:287`, `claude/overnight/orchestrator.py:162`, `claude/overnight/smoke_test.py:250` — handle the raised `ValueError` indistinguishably from the previous `CalledProcessError` (each catches `Exception` or allows the exception to propagate without type discrimination). Acceptance: `just test` exits 0 (existing caller tests, if any, pass unchanged).

## Non-Requirements

- **Root-cause diagnosis of lifecycle 69's exit 128**: the fix ships diagnosis-enabling infrastructure; diagnosis happens when the next reproduction produces readable stderr.
- **Changes to `_resolve_branch_name` fallback logic**: orphan-accumulation bound comes from the cleanup on failure, not from changes to suffix climbing.
- **Changes to `implement.md` pre-flight**: unrelated surface.
- **Partial worktree-directory cleanup (e.g., `git worktree remove --force`)**: the ticket's acceptance criterion names branch cleanup only. `git worktree add` failures that leave partial directory state will be caught by the existing idempotency check (lines 103-136) or by the next run's failure — not in scope.
- **Concurrent-writer safety for `_resolve_branch_name`**: the function is TOCTOU (no lock, no atomic check-and-create) and repairing it is scoped out of this ticket. The Edge Cases section documents how the new except-block interacts with this existing race; the residual risk is that the losing process's cleanup is a no-op when git refuses to delete the winner's checked-out branch.
- **SIGINT handling during `git worktree add`**: if the Python process is interrupted mid-subprocess, partial state (branch created, directory partially populated) may remain. Operator or next-run's idempotency check resolves this; not addressed here.
- **Structured-log emission to `daytime.log` or elsewhere**: stderr is surfaced in the exception message only (no separate log-file write, no external forwarding).
- **Custom exception class** (e.g., `WorktreeCreateError`): YAGNI — no caller discriminates `CalledProcessError` today and the sibling `conflict.py` pattern uses `ValueError`.

## Edge Cases

- **`_branch_exists` returns False in the except path**: happens when `git worktree add` fails before branch creation, e.g., `base_branch` is unresolvable. Cleanup is a no-op; the raised `ValueError` surfaces the git stderr explaining the pre-branch failure. No regression.
- **`git branch -D` fails because the branch is checked out by another worktree**: can happen under concurrent `create_worktree` races on `_resolve_branch_name`. Git's own protection refuses to delete a branch checked out in another worktree (error: `Cannot delete branch 'X' checked out at '/path/to/worktree'`), so the cleanup fails and is silently swallowed — the other worktree is not corrupted. The orphan persists on the caller's side; the losing process raises `ValueError` with the original "already exists" stderr from `git worktree add`; the operator can diagnose the race manually.
- **Empty `stderr`**: the ValueError message ends with `(no stderr)` sentinel rather than an empty trailing colon. Test asserts this.
- **Stderr containing paths with usernames / absolute paths**: inherited from prior behavior; stderr already reaches `daytime.log` today in some failure modes (this change just makes it the common case). No new exfiltration surface — `daytime.log` is not shipped off-host.
- **`_resolve_branch_name` climbs to `-2`/`-3` after this call's failure**: expected — `-D` deletes the exact branch this call resolved; next call resolves a fresh name if needed. Orphan accumulation is bounded at ≤1 per failed call (down from unbounded), assuming cleanup succeeds. If cleanup fails silently, orphans can still accumulate — treated as a degraded state the operator manually cleans; acceptable per the ticket's scope.
- **Idempotency-check fall-through (pre-existing stale worktree directory)**: when the idempotency check at lines 103-136 finds the target path but no registered worktree entry, `git worktree add` is run and fails. Git's observed ordering for this failure mode (empirically verified) is to create the branch first and fail on the path collision afterward — so `_branch_exists` returns True in the except path and the orphan branch is cleaned up by `git branch -D`. The raised `ValueError` surfaces the "already exists" git message; the stale directory itself persists (out of scope per Non-Requirements) for operator cleanup.

## Changes to Existing Behavior

- **MODIFIED**: `claude/pipeline/worktree.py::create_worktree` — call at lines 142-148 drops `check=True`, inspects `returncode`, cleans up the orphan branch on non-zero, raises `ValueError(f"worktree_creation_failed: {stderr.strip() or '(no stderr)'}")`. Previously raised `subprocess.CalledProcessError` whose message omitted stderr.
- **ADDED**: `tests/test_worktree.py` — new tests covering the failure-then-cleanup path (real-git trigger: pre-existing non-worktree dir at target path), the stderr-in-message assertion, and the cleanup-failure-silently-swallowed path (mocked subprocess).

## Technical Constraints

- Must match `claude/pipeline/conflict.py:119-128` in-module precedent for wrapping `git worktree add -b` failures: drop `check=True`, inspect `returncode`, raise `ValueError(f"{token}: {stderr.strip()}")`. An alternative in-repo precedent exists at `claude/overnight/plan.py:375-385, 461-475` (catch `CalledProcessError` and re-raise `RuntimeError`); this spec chooses the `conflict.py` pattern because it wraps this same `git worktree add -b` call and lives in the same package. Accept the pattern inconsistency with `plan.py` as a known trade-off; no generalization (e.g., a shared exception type across both call sites) is required by this ticket.
- Branch cleanup must use `git branch -D` (force), not `-d` — the branch was picked uniquely by `_resolve_branch_name` (line 51) before `git worktree add` ran, so provenance is known; `-d` could refuse deletion if the branch ended in an unexpected state.
- Cleanup subprocess call must use `capture_output=True` and NOT `check=True` — silent best-effort per Requirement 4.
- Python 3.10+ is acceptable; no 3.11-only features (`add_note`) required for this implementation.
- No new module imports beyond those already in `worktree.py` (`subprocess`, `shutil`, `os`).
- Real-git trigger for the failure-path test: pre-populate `worktree_path` with a **non-empty** non-worktree directory (e.g., write a sentinel file inside it); `git worktree add -b` deterministically fails with "fatal: `<path>` already exists" at exit 128. Empirically verified: git's ordering for this failure is (1) resolve base, (2) create the branch ref, (3) attempt directory checkout, (4) fail on the already-populated directory — so the branch IS created before the failure, which is precisely what the cleanup path must exercise. Using an empty directory would cause `git worktree add` to succeed (git reuses the empty dir), so the failure-path test is sensitive to this detail. Monkey-patching `subprocess.run` is not required for this test.
- Monkey-patching `subprocess.run` is permitted only for Requirement 4's cleanup-failure test, where deterministic real-git reproduction of "branch-created-then-checkout-failed + cleanup-also-fails" isn't practical.
- `daytime.log` is captured by the child-process stdout/stderr redirect at the overnight-launch site (`skills/lifecycle/references/implement.md:133`) — no logger configuration change required for stderr to reach the log.

## Open Decisions

None — all design decisions were resolved during the interview. Critical-review surfaced a precedent inconsistency between `conflict.py` (ValueError) and `plan.py` (RuntimeError) for wrapping the same git failure; this spec stays with the user's chosen `conflict.py` pattern and documents the inconsistency in Technical Constraints rather than opening it for reconsideration.
