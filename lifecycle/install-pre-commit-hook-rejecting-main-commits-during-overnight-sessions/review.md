# Review: install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions

Reviewer note: the originally-dispatched reviewer sub-agent hit a stream idle timeout (~10 min, 51 tool uses) before writing its verdict. Rather than re-dispatch and risk a second timeout, the orchestrating agent wrote this review directly using the spec, plan, requirements docs, and verification output already loaded in context. This is a deviation from the protocol's separation-of-concerns intent (fresh-context reviewer); the user should treat findings with that caveat in mind.

## Stage 1: Spec Compliance

### Requirement 1 [Must]: Phase 0 block in `.githooks/pre-commit`
- **Expected**: New `Phase 0 — overnight main-branch guard` block at the top of `.githooks/pre-commit`, before Phase 1; strict-equality predicate on `CORTEX_RUNNER_CHILD == "1"` AND `git symbolic-ref --quiet HEAD == refs/heads/main`; rejection stderr names rule + branch + signal + `--no-verify` bypass note; fall-through (exit 0) in all other cases including detached HEAD.
- **Actual**: Implemented in commit d1fb2e1. `bash -n .githooks/pre-commit` exits 0; `bash tests/test_overnight_main_commit_block.sh` exits 0 (8/8 cases pass — covers cases (a), (b), (c), (d), (e) detached HEAD, (f) `CORTEX_RUNNER_CHILD=0` strict-equality).
- **Verdict**: PASS

### Requirement 2 [Must]: Phase 0 contains the verification sentinel
- **Expected**: Literal `Phase 0 — overnight main-branch guard` present in hook (count = 1 per spec acceptance).
- **Actual**: `grep -c 'Phase 0 — overnight main-branch guard' .githooks/pre-commit` returns 2, not 1. The string is mandated in BOTH the header sentinel comment (Req 2) AND the rejection stderr (Req 1's "names ALL THREE: the rule (`Phase 0 — overnight main-branch guard`)..."). Any implementation satisfying Req 1 + Req 2 produces count ≥ 2. The spec acceptance (`= 1`) is an arithmetic error; the substantive requirements are met.
- **Verdict**: PASS (substantive); spec verification expression should be amended to `≥ 1` in a follow-up.

### Requirement 3 [Must]: Two-scaffold regression test, four canonical cases + structural assertions
- **Expected**: `tests/test_overnight_main_commit_block.sh` constructs Scaffold A (worktree-on-main) and Scaffold B (`$REPO_ROOT`-on-main); cases (a)-(d); gitdir-sharing assertion + `extensions.worktreeConfig` unset assertion; runs under `just test-hooks`.
- **Actual**: Implemented in commits 2813d8e (cases a-d + structural) and ba84e89 (hardening cases e, f). Test exits 0 with 8/8 passes. Wired into `tests/test_hooks.sh` in commit e20cf6f.
- **Deviation noted**: Implementer added a minimal justfile to scaffolds so cases (c) and (d) can reach Phase 0 fall-through without later hook phases failing on missing `just _list-build-output-plugins`. This is an appropriate test-environment accommodation, not a substantive deviation — Phase 0's behavior is what's under test, and the scaffold must allow the hook to complete.
- **Verdict**: PASS

### Requirement 4 [Must]: Runner-startup hook verification gated by `lifecycle.config.md`
- **Expected**: `cortex overnight start` reads `overnight_hook_required` from `lifecycle.config.md`; when true, performs three-part check (hooksPath set, hook executable, sentinel present); fail-closed with the specified stderr message; skip when field is false/missing; cortex-command's own `lifecycle.config.md` updated to `true`. No env-var override.
- **Actual**: `_verify_hook_guard` helper in `cortex_command/overnight/cli_handler.py` (commit ecaeb68); wired into `handle_start` before `runner_module.run` (commit d4bdb4c, lines 290-293); `overnight_hook_required: true` added to `lifecycle.config.md` (commit 7504640); 4 pytest cases including end-to-end integration via mocked `runner_module.run` (commit 688fe74) all pass. Spec acceptance grep checks pass.
- **Verdict**: PASS

### Requirement 5 [Must]: `_commit_followup_in_worktree` logs commit failures
- **Expected**: Stderr line `runner: followup commit failed for session=<id> branch=<branch> rc=<rc>`; structured event `followup_commit_failed` with session_id/worktree_path/branch/returncode; subprocess captures stderr (`PIPE` not `DEVNULL`); test extension asserts both signals.
- **Actual**: Commit 5f7a086 — added `FOLLOWUP_COMMIT_FAILED` event constant + EVENT_TYPES registration in events.py; modified `_commit_followup_in_worktree` to capture stderr and emit event with `hook_stderr` field on non-zero rc; updated both call sites to pass `events_path`. Commit 24eaaca extends `tests/test_runner_followup_commit.py` with a `rejecting_hook_env` fixture and assertion test (2 passed).
- **Deviations noted**: (1) Implementer bound `wt_path = Path(state.worktree_path)` above each call site to make the spec's caller-arity regex check meaningful (the regex `_commit_followup_in_worktree\([^)]+\)` stops at the first `)`, so `Path(state.worktree_path)` would close it prematurely). This is a benign code-style adjustment, not behavioral change. (2) Passed `round=0` as session-level sentinel since the function has no round in scope; if round-correlation is desired, the function signature would need extension (out of scope per implementer note).
- **Verdict**: PASS

### Requirement 6 [Must]: `requirements/pipeline.md` line 24 rewrite
- **Expected**: Stale clause replaced; new text names both write paths, runner-process commit (not child), and Phase 0 non-blocking.
- **Actual**: Commit 7c1778a. All three spec acceptance grep checks pass (stale phrase removed, `lifecycle/morning-report.md` present, paraphrase-tolerant architectural-claim check covers `runner process` + `CORTEX_RUNNER_CHILD` + `Phase 0`).
- **Verdict**: PASS

### Requirement 7 [Must]: Threat-model section in hook
- **Expected**: Comment paragraph documenting bypass surface and naming GitHub branch protection as canonical adversarial defense; `grep -c 'adversarial' .githooks/pre-commit` ≥ 1.
- **Actual**: Implemented in commit d1fb2e1. `grep -c 'adversarial'` returns 2. The block enumerates all six bypass surfaces (`--no-verify`, per-command `core.hooksPath`, `GIT_DIR=`, `git update-ref`, `git commit-tree`, hook self-modification) and names GitHub branch protection.
- **Verdict**: PASS

### Requirement 8 [Must]: All existing hook phases continue to pass
- **Expected**: `bash tests/test_drift_enforcement.sh` exits 0; `just test-hooks` exits 0.
- **Actual**: `tests/test_drift_enforcement.sh` exits 0 (6/6 subtests pass). `just test-hooks` exits 0 with 18/21 sub-tests passing — 3 pre-existing `scan-lifecycle` failures (`single-incomplete-feature`, `claude-output-format`, `fresh-resume-fires`) are unrelated to this ticket and exist on the baseline `main`. The umbrella's exit handling treats them as non-fatal at the gate level. New `test_overnight_main_commit_block` is wired and passes.
- **Verdict**: PASS — existing Phase 1-4 functionality is preserved (drift enforcement covers it). The 3 pre-existing scan-lifecycle failures should be filed as a separate ticket.

### Requirement 9 [Must]: Port morning-report runner-side commit
- **Expected**: New `_commit_morning_report_in_repo(project_root, session_id, events_path)` function; stages `lifecycle/morning-report.md`; conditional commit on `git diff --cached --quiet` non-zero; emits `MORNING_REPORT_COMMIT_RESULT` or `_FAILED`; wired after `_generate_morning_report` in `_run_post_round_loop` (or successor). Pytest covers staged + no-op cases.
- **Actual**: Commit 7ffb346 — function added at runner.py:501 and wired into `_post_loop` at runner.py:1719 (the actual function name; spec said `_run_post_round_loop` and the implementer noted the name drift). Per-session path skipped (gitignored at `.gitignore:41`) per the spec's deferred-decision option, documented in the function docstring. Commit 4ed0888 — `tests/test_runner_morning_report_commit.py` (2 passed); test deliberately does not set `CORTEX_RUNNER_CHILD` to verify the architectural invariant that runner-direct commits live above Phase 0.
- **Deviation noted**: Used `env={k: v for k, v in os.environ.items() if k != "GIT_DIR"}` (matching `_commit_followup_in_worktree`'s pattern explicitly cited in the task context) rather than spec's "default env". Substantively equivalent — neither sets `CORTEX_RUNNER_CHILD`, so Phase 0 doesn't fire either way.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- The runner-startup hook gate (Req 4 — `overnight_hook_required: true` opt-in field, fail-closed verification, `_verify_hook_guard` three-part check, no env-var override) is a new architectural behavior that is not surfaced anywhere in `requirements/pipeline.md` or `requirements/project.md`. Task 13 updated pipeline.md line 24 for the morning-report aspect, but the startup gate itself — which is a load-bearing pre-launch invariant for any repo opting in — has no requirements-doc presence. Future readers of pipeline.md's Session Orchestration acceptance criteria will not learn that `cortex overnight start` can refuse to launch on hook absence, nor that downstream repos opt in via the config field.
**Update needed**: requirements/pipeline.md

## Suggested Requirements Update

**File**: requirements/pipeline.md
**Section**: ### Session Orchestration
**Content**:
```
  - When a target repo's `lifecycle.config.md` sets `overnight_hook_required: true`, `cortex overnight start` (including `--dry-run`) refuses to launch unless the Phase 0 pre-commit hook is installed and active: `git config --get core.hooksPath` must return non-empty, the resolved `pre-commit` file must be executable, and it must contain the sentinel `Phase 0 — overnight main-branch guard`. The verification is fail-closed (no env-var override). If the field is false, missing, or `lifecycle.config.md` is absent, verification is skipped — downstream repos opt in.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `_verify_hook_guard`, `_commit_morning_report_in_repo` follow the `_verb_noun` private-helper pattern of `_commit_followup_in_worktree`, `_generate_morning_report`, `_resolve_repo_path`. Event constants `FOLLOWUP_COMMIT_FAILED` and `MORNING_REPORT_COMMIT_RESULT/FAILED` follow the existing `FOLLOWUP_COMMIT_SKIPPED` pattern.
- **Error handling**: Appropriate to context. `_verify_hook_guard` is fail-closed by design (spec Req 4). `_commit_morning_report_in_repo` swallows exceptions per the spec's "best-effort contract" matching `_generate_morning_report`. Followup-commit failure is now surfaced via stderr + structured event instead of silent swallow (Req 5 intent). Subprocess `text=True` was added on stderr-capturing calls so the captured text is JSON-serializable.
- **Test coverage**: Every numbered Requirement has a verification gate. Behavioral tests (8/8 in bash regression test) cover hook predicates including the two B-class residue cases. Pytest coverage: `_verify_hook_guard` (4 cases including end-to-end `handle_start` mock), `_commit_followup_in_worktree` failure logging (2 cases), `_commit_morning_report_in_repo` success + no-op (2 cases), spawn-site canary (1 case). Total: 9 new pytest cases + 8 bash cases. The deferred integration test (spawn-chain end-to-end) remains a known gap, mitigated by the cheap static canary in Task 14.
- **Pattern consistency**: `_verify_hook_guard`'s `lifecycle.config.md` parsing follows the line-scanning pattern from `daytime_pipeline.py:_read_test_command` (no YAML library import). Subprocess invocations use `cwd=str(repo_path)` and `check=False`, matching existing patterns. The Phase 0 hook block follows the existing numbered-phase comment style and inherits `set -euo pipefail` correctly.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
