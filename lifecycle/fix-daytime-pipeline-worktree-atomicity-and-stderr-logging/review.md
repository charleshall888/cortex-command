# Review: fix-daytime-pipeline-worktree-atomicity-and-stderr-logging

## Stage 1: Spec Compliance

### Requirement 1: Orphan-branch cleanup on failed `git worktree add -b`
- **Expected**: On non-zero return from `git worktree add -b`, `create_worktree` attempts `git branch -D <resolved_branch>` before raising; test pre-creates a non-empty non-worktree dir at the target path, asserts the call raises, and asserts `git branch --list pipeline/{feature}*` has empty stdout.
- **Actual**: `claude/pipeline/worktree.py:148-156` inspects `result.returncode` and runs `subprocess.run(["git", "branch", "-D", branch], capture_output=True, text=True, cwd=str(repo))` before raising. Test `test_failure_cleans_up_orphan_branch_and_raises_valueerror_with_stderr` at `tests/test_worktree.py:120-159` creates `target_dir` with `sentinel.txt` (non-empty), invokes `create_worktree("orphan-test", base_branch=branch)`, and asserts both `returncode == 0` and empty stdout on the post-failure `git branch --list pipeline/orphan-test*`. The test passes.
- **Verdict**: PASS

### Requirement 2: Stderr surfaced in the raised exception message
- **Expected**: Message matches `r"^worktree_creation_failed: .+"` with non-empty stderr text; empty stderr yields `(no stderr)` sentinel.
- **Actual**: `worktree.py:155-156` computes `stderr_text = (result.stderr or "").strip() or "(no stderr)"` and raises `ValueError(f"worktree_creation_failed: {stderr_text}")`. Test 1 asserts `re.match(r"^worktree_creation_failed: (.+)", str(exc))` is not None and that `match.group(1).strip()` is truthy; test `test_failure_with_empty_stderr_yields_no_stderr_sentinel` (lines 161-200) asserts the exact string `"worktree_creation_failed: (no stderr)"`. Both pass.
- **Verdict**: PASS

### Requirement 3: Exception type
- **Expected**: `ValueError`, not `subprocess.CalledProcessError`; test asserts both `isinstance` and `not isinstance`.
- **Actual**: `worktree.py:156` raises `ValueError(...)`. `tests/test_worktree.py:138-139` asserts `isinstance(exc, ValueError)` and `not isinstance(exc, subprocess.CalledProcessError)`. Test passes.
- **Verdict**: PASS

### Requirement 4: Silent best-effort cleanup
- **Expected**: If the cleanup `git branch -D` returns non-zero, swallow silently; original `ValueError` with `worktree_creation_failed:` prefix is raised unchanged.
- **Actual**: `worktree.py:149-154` makes a `subprocess.run` cleanup call with no return-value inspection or conditional logic after it — the result is discarded. Test `test_cleanup_failure_silently_swallowed_original_raised_unchanged` (lines 202-241) asserts the exact string `"worktree_creation_failed: fatal: simulated"` despite the mocked cleanup returning `returncode=1` with `stderr="error: branch deletion failed"`. No "cleanup" text leaks into the message. Test passes.
- **Verdict**: PASS

### Requirement 5: Existing callers continue to work
- **Expected**: `daytime_pipeline.py:287`, `orchestrator.py:162`, and `smoke_test.py:250` do not discriminate on `CalledProcessError`; `just test` exits 0.
- **Actual**: Verified via read:
  - `daytime_pipeline.py:287` calls `create_worktree(feature)`; the surrounding try/except at line 307-316 uses `except Exception as e` — catches `ValueError` indistinguishably.
  - `orchestrator.py:162` calls `create_worktree(...)` with no local try/except — propagates up, callers also don't discriminate.
  - `smoke_test.py:250` calls `create_worktree(...)` with no try/except.
  - `grep CalledProcessError` across `claude/overnight/` shows two hits only in `plan.py` (lines 381, 472) for unrelated `git branch -D` / `git worktree prune` calls, not `create_worktree`. All 6 worktree tests pass (`.venv/bin/python -m unittest tests.test_worktree -v`).
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None — the spec's behavior map cleanly to `requirements/pipeline.md` ("Graceful partial failure" and "Atomicity") and `requirements/multi-agent.md` Worktree Isolation (branch naming with collision suffix, idempotent behavior). The fix tightens orphan-branch accumulation bounds (≤1 per failed call) and makes stderr surface in raised exceptions; both behaviors are consistent with stated quality attributes rather than introducing new functional capabilities. No requirements file needs updating.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `worktree_creation_failed:` token matches the exact string used at `conflict.py:127`. The variable `stderr_text` and `(no stderr)` sentinel are clear. Test method names follow the existing module's descriptive-snake-case style (`test_failure_cleans_up_orphan_branch_and_raises_valueerror_with_stderr`). New test class `TestWorktreeCreateFailure` parallels the existing `TestWorktreeVenvSymlink`.

- **Error handling**: Appropriate. The cleanup call is genuinely silent-best-effort (return value discarded, no bare `try/except` noise). The `(no stderr)` sentinel prevents a trailing-colon malformed message in the edge case. Exception type change is safe — spec Requirement 5 verification confirms no caller catches `CalledProcessError` from this function.

- **Test coverage**: All three plan verification surfaces executed. The three new tests cover the four functional requirements (1, 2-nonempty, 2-empty, 3, 4) as enumerated in plan.md. `just test`/`unittest` all six tests in `tests/test_worktree.py` pass. Test 1 uses a real-git trigger (non-empty pre-existing dir) as the spec mandates — git empirically fails *after* creating the branch, so the cleanup path is actually exercised. Tests 2 and 3 use command-dispatching `fake_run` (a cleaner pattern than a brittle call-order `side_effect` list), so they survive minor implementation reshuffles.

- **Pattern consistency**: Implementation follows `claude/pipeline/conflict.py:119-128` precedent precisely — same `capture_output=True, text=True`, no `check=True`, `returncode` inspection, f-string with `worktree_creation_failed:` token, `ValueError` raise. The only deliberate divergence is the `(no stderr)` sentinel, which is a spec-required enhancement to handle empty-stderr edge cases (conflict.py would emit a trailing colon; worktree.py now does not).

- **Plan verification command observation** (per orchestrator note): The plan.md verification step `"check=True" in inspect.getsource(worktree.create_worktree)` returns `True`, but this is because of an unrelated pre-existing `check=True` at `worktree.py:108` on the `git worktree list --porcelain` call inside the idempotency branch — fully out of scope for this ticket. The scoped intent — no `check=True` on the `git worktree add -b` call at lines 142-147 — does hold (verified by reading the source; the `result = subprocess.run(...)` at lines 142-147 has no `check=True`, and the single remaining `check=True` in the function body is on the earlier `git worktree list` call). This is a plan-verification-spec inconsistency, not an implementation defect. No penalty.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
