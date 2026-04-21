# Plan: fix-daytime-pipeline-worktree-atomicity-and-stderr-logging

## Overview

Close two defects in `claude/pipeline/worktree.py::create_worktree` that currently make daytime-pipeline failures both accumulate orphan branches and be unreadable in `daytime.log`:

1. The call `git worktree add -b` at lines 142-148 uses `check=True`; on failure it creates an orphan branch (because `git worktree add -b` creates the branch before attempting checkout) and raises `subprocess.CalledProcessError` whose `__str__` omits `stderr`, so `daytime.log` captures only `returned non-zero exit status 128.` with no git error text.
2. `_resolve_branch_name`'s `-2`, `-3` fallback keeps retries moving but leaves orphan branches unbounded across failures (lifecycle 69 required manual `git branch -D pipeline/{feature}` before retry could proceed).

The fix follows the `claude/pipeline/conflict.py:119-128` in-module precedent: drop `check=True`, inspect `returncode`, on non-zero attempt a best-effort `git branch -D <resolved_branch>` to delete the orphan, then raise `ValueError(f"worktree_creation_failed: {stderr.strip() or '(no stderr)'}")`. Cleanup failures are silently swallowed so they never shadow the enriched git-stderr message.

The plan adds three tests to `tests/test_worktree.py`: a real-git failure trigger (pre-existing non-empty non-worktree directory at the target path) that asserts both the ValueError-with-stderr contract and post-failure branch cleanup; a paired assertion that the empty-stderr case yields the `(no stderr)` sentinel; and a monkey-patched cleanup-failure test that verifies cleanup errors are swallowed without shadowing the original exception.

No recovery history exists for this feature (no `learnings/recovery-log.md` directory present) — this is a first-attempt plan.

## Tasks

### Task 1: Rewrite `create_worktree` failure path to clean up orphan branch and surface stderr

**Files:**
- `/Users/charlie.hall/Workspaces/cortex-command/claude/pipeline/worktree.py`

**What:**
Replace the `subprocess.run(..., check=True)` call at lines 142-148 with a capture-without-check call that inspects `returncode`. On non-zero:
1. Attempt `git branch -D <branch>` (using the `branch` variable already resolved at line 138 by `_resolve_branch_name`) via a `subprocess.run` with `capture_output=True` and NO `check=True`. Swallow any failure — do not inspect the returncode, do not append anything to the exception message.
2. Compute `stderr_text = (result.stderr or "").strip() or "(no stderr)"`.
3. Raise `ValueError(f"worktree_creation_failed: {stderr_text}")`.

The cleanup call uses `-D` (force), matching `hooks/cortex-cleanup-session.sh:55` / `claude/overnight/runner.sh:1335` / operator docs (`skills/overnight/SKILL.md:403`). It uses the branch name from `branch` (the `_resolve_branch_name` return value at line 138) so it deletes the exact branch this call attempted to create. It runs with `cwd=str(repo)` so it targets the right repository for cross-repo worktrees.

No new imports. `subprocess` is already imported.

The happy path (returncode == 0) falls through to the existing `.venv` symlink / `settings.local.json` copy logic at lines 150-162, unchanged.

Match the `conflict.py:119-128` style precisely (capture_output=True, text=True, no check=True, returncode check, f-string with `worktree_creation_failed:` token).

**Depends on:** none.

**Context:**
- Current failing call: `claude/pipeline/worktree.py:142-148`
- In-module precedent for wrapping this exact `git worktree add -b` command: `claude/pipeline/conflict.py:119-128`
- Spec Requirements 1-4, Technical Constraints lines 44-50
- Branch-delete flag `-D` rationale: spec Technical Constraints line 47 (provenance known because `_resolve_branch_name` picked it; `-d` could refuse deletion if the branch ended in an unexpected state)
- `_branch_exists` check is NOT required before the cleanup — `git branch -D` of a non-existent branch returns non-zero, and non-zero cleanup results are swallowed per Requirement 4. Adding the check would be redundant.

**Verification:**
- `just test` exits 0 (all three new tests in Task 2 pass; existing three venv-symlink tests continue to pass).
- Run `python3 -c 'from claude.pipeline import worktree; import inspect; print("check=True" in inspect.getsource(worktree.create_worktree))'` and confirm output is `False` — `check=True` no longer appears in `create_worktree`.
- Run `grep -n 'worktree_creation_failed' /Users/charlie.hall/Workspaces/cortex-command/claude/pipeline/worktree.py` and confirm exactly one match on the new `ValueError` raise line.

**Status:** completed (commit `25c3ea0`)

---

### Task 2: Add three failure-path tests to `tests/test_worktree.py`

**Files:**
- `/Users/charlie.hall/Workspaces/cortex-command/tests/test_worktree.py`

**What:**
Append a new `TestWorktreeCreateFailure` test class (beside the existing `TestWorktreeVenvSymlink`) with three test methods:

1. **`test_failure_cleans_up_orphan_branch_and_raises_valueerror_with_stderr`** (real-git trigger, covers Requirements 1, 2, 3):
   - Use `tempfile.TemporaryDirectory` + `_init_git_repo(tmppath)` (existing helper at lines 21-55).
   - Pre-create the target worktree directory as a non-empty non-worktree dir: `(tmppath / ".claude" / "worktrees" / "orphan-test").mkdir(parents=True)` then write a sentinel file `(tmppath / ".claude" / "worktrees" / "orphan-test" / "sentinel.txt").write_text("block")`. The non-empty requirement is load-bearing per spec Requirements line 9 and Technical Constraints line 51 — git accepts an empty existing directory as a valid worktree target, so an empty dir would not trigger the failure path.
   - With `patch("claude.pipeline.worktree._repo_root", return_value=tmppath)`, call `create_worktree("orphan-test", base_branch=branch)` inside `self.assertRaises(ValueError) as ctx`.
   - Assert `isinstance(ctx.exception, ValueError)` AND `not isinstance(ctx.exception, subprocess.CalledProcessError)` (matches spec Requirement 3).
   - Assert `re.match(r"^worktree_creation_failed: .+", str(ctx.exception))` and that the captured group after `worktree_creation_failed: ` is non-empty (the git stderr text; for "fatal: … already exists" this will not be empty — spec Requirements line 11).
   - Assert `git branch --list pipeline/orphan-test*` run via `subprocess.run([... ], capture_output=True, text=True, cwd=str(tmppath))` exits 0 with empty stdout (spec Requirements line 9 acceptance criterion: orphan branch was cleaned up).
   - Import `re` at the top of the file if not already present.

2. **`test_failure_with_empty_stderr_yields_no_stderr_sentinel`** (covers spec Edge Cases line 34 / Requirement 2's empty-stderr branch):
   - Monkey-patch `subprocess.run` so the `git worktree add` call returns a `CompletedProcess` with `returncode=128` and `stderr=""`. Other subprocess calls (via `_repo_root`, `_resolve_branch_name`'s `_branch_exists`, the cleanup `git branch -D`) must be passed through or returned as appropriate `CompletedProcess` stubs. Simplest implementation: use `patch("claude.pipeline.worktree.subprocess.run", side_effect=fake_run)` where `fake_run(cmd, **kwargs)` inspects `cmd` and returns a stub for the `git worktree add` call (returncode=128, stderr=""), returns a CompletedProcess(returncode=0, stdout="", stderr="") for `git branch -D` cleanup, and uses `patch.stopall` / delegates to the real subprocess.run for the `_branch_exists` lookup (or stubs that too as returncode=1, empty stdout to pretend no suffix collision).
   - Assert the raised ValueError's `str()` equals exactly `"worktree_creation_failed: (no stderr)"`.
   - Alternative lower-risk implementation (preferred): monkey-patch only the one problematic call using a side_effect list that mirrors the call order `create_worktree` makes (this assumes `_branch_exists` is called once for the `_resolve_branch_name` first check; inspect worktree.py to confirm and list stubs in exact order). If ordering coupling is brittle, fall back to the command-matching approach above.

3. **`test_cleanup_failure_silently_swallowed_original_raised_unchanged`** (covers spec Requirement 4):
   - Monkey-patch `subprocess.run` so the `git worktree add` call returns a `CompletedProcess` with `returncode=128` and `stderr="fatal: simulated"`, and the subsequent `git branch -D` cleanup call returns a `CompletedProcess` with `returncode=1` and `stderr="error: branch deletion failed"`.
   - Call `create_worktree("cleanup-fail-test", base_branch=branch)` inside `self.assertRaises(ValueError) as ctx`.
   - Assert `str(ctx.exception) == "worktree_creation_failed: fatal: simulated"` (exact string — NO mention of "cleanup" anywhere in the message; spec Requirement 4 acceptance criterion line 15).

All three tests follow the existing module's style at lines 21-105 (tempfile.TemporaryDirectory, `_init_git_repo`, `patch("claude.pipeline.worktree._repo_root", ...)`). Use `unittest.mock.patch` and `unittest.mock.MagicMock` where monkey-patching is needed.

**Depends on:** Task 1 (the tests will fail with the current code because the raised exception type is `CalledProcessError`, not `ValueError`, and the message lacks the `worktree_creation_failed:` prefix — Task 1's implementation is the system under test).

**Context:**
- Existing test patterns: `tests/test_worktree.py:21-105`
- `_make_subprocess_result` / `_make_proc` pattern for CompletedProcess stubs: research line 37 — `claude/pipeline/tests/test_trivial_conflict.py:63-68, 184-195` and `claude/pipeline/tests/test_merge_recovery.py:26-31`
- Real-git failure trigger rationale: spec Technical Constraints line 51 (git's ordering is resolve-base → create-branch → attempt-checkout → fail-on-populated-dir, so the branch IS created before the failure, which is what the cleanup path must exercise)
- Spec Requirements 1 (cleanup assertion), 2 (stderr-in-message), 3 (ValueError type), 4 (silent cleanup swallow)
- `git branch --list pipeline/orphan-test*` in an empty repo with no matching branches returns exit 0 with empty stdout — this is the assertion shape the spec mandates.

**Verification:**
- Run `/Users/charlie.hall/Workspaces/cortex-command/.venv/bin/python -m unittest tests.test_worktree -v` and confirm all six tests pass (three existing venv-symlink tests + three new failure-path tests).
- Run `just test` and confirm it exits 0.
- Manually inspect test 1's assertion output by temporarily reverting Task 1 and running the test: it must fail with a message indicating `CalledProcessError` was raised instead of `ValueError` (confirms the test actually exercises the new behavior, not a no-op). Then re-apply Task 1.

**Status:** completed (commit `8a975bc`; 6/6 tests pass; manual revert step skipped to avoid corrupting main mid-lifecycle)

---

### Task 3: Verify caller sites remain correct after exception-type change

**Files:**
- `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/daytime_pipeline.py` (inspection only, near line 287 and line 314 `except Exception`)
- `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/orchestrator.py` (inspection only, near line 162)
- `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/smoke_test.py` (inspection only, near line 250)

**What:**
Inspection-only pass to confirm spec Requirement 5: no caller discriminates on `subprocess.CalledProcessError`. Use `grep -n 'CalledProcessError' <file>` on each of the three caller files. For each, confirm either (a) there is no `except CalledProcessError` catching output from `create_worktree`, or (b) the catching code only uses `except Exception`.

If a catch of `CalledProcessError` is found that wraps `create_worktree` — STOP and escalate; spec Requirement 5 would be violated. Otherwise, no code change is needed here; this task is a sanity sweep that the spec's behavioral invariant holds.

This task exists because the spec's Requirement 5 is an assertion about the current repo state, not about new code; verifying it with real inspection (rather than trusting the spec's file:line quote) is fast insurance.

**Depends on:** none (can run in parallel with Task 1).

**Context:**
- Spec Requirements 5 (line 17), Requirement 3 (line 13) — both reference these three call sites.
- Research file lines 12-14 walks through each.

**Verification:**
- `grep -rn 'CalledProcessError' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/` output, manually reviewed, shows no `except CalledProcessError` that catches exceptions from `create_worktree`. (Matches within `plan.py` that catch `CalledProcessError` from other subprocess calls — e.g., `git branch -D` in `plan.py:381,472` — are unrelated and do not block.)
- `grep -n 'create_worktree' /Users/charlie.hall/Workspaces/cortex-command/claude/overnight/daytime_pipeline.py` and cross-reference the surrounding exception-handling block; the existing `except Exception` at line 314 catches `ValueError` indistinguishably.

**Status:** completed (inspection-only; no commit; Requirement 5 holds)

---

## Verification Strategy

End-to-end, we have three orthogonal verification surfaces:

1. **Automated test suite — the primary gate.** Task 2 adds three new unit tests to `tests/test_worktree.py`. They exercise all four of spec's functional requirements:
   - Real-git failure-then-cleanup (Requirements 1, 2 non-empty-stderr, 3): pre-populated non-worktree directory forces `git worktree add` to fail after branch creation; test asserts ValueError, stderr-in-message, no orphan branch.
   - Empty-stderr sentinel (Requirement 2 empty-stderr branch / Edge Cases line 34): monkey-patched empty stderr asserts exact `(no stderr)` message.
   - Silent cleanup failure (Requirement 4): monkey-patched cleanup returncode=1 asserts original ValueError is raised unchanged.
   - All three existing venv-symlink tests (lines 61-105) continue to pass — the happy path is untouched.
   Pass criterion: `just test` exits 0. This is independently observable state (test output), not self-sealing — the tests verify behavior of Task 1's code edits.

2. **Static-contract verification.** Task 1's verification step runs a `grep` and an `inspect.getsource` check to confirm `check=True` is removed from `create_worktree` and the `worktree_creation_failed:` token appears exactly once. These are artifacts of the pre-existing source file after Task 1's edit — independently observable, not produced to satisfy verification.

3. **Caller-compatibility spot-check.** Task 3 is a read-only `grep` pass against the three caller files (`daytime_pipeline.py`, `orchestrator.py`, `smoke_test.py`) to confirm no caller discriminates on `CalledProcessError`. Verification references existing file contents, not new artifacts.

Manual-run fallback: if `just test` cannot be run in the execution environment, `python -m unittest tests.test_worktree -v` produces equivalent output.

There is NO verification step that asks the task to write something and then check it was written. All verifications reference either test-runner output, pre-existing caller files, or grep matches against the source file modified by Task 1 (whose modification IS the behavior under test — this is standard test-then-code dependence, not self-sealing).
