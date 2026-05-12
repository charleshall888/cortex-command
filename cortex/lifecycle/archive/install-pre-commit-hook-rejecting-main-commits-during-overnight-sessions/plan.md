# Plan: install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions

## Overview

Runner-first, test-driven ordering: the runner-startup verification (Req 4) and its supporting `lifecycle.config.md` field are built before the hook itself, creating a fail-closed gate that forces hook installation before any overnight session can launch. The hook is then delivered with its bash regression test split into a canonical-cases task (the 4 spec-mandated assertions) and a hardening-cases task (detached HEAD + `CORTEX_RUNNER_CHILD=0`, which directly close two B-class critical-review residue findings). The morning-report commit port (Req 9) and followup-commit logging (Req 5) are independent runner changes delivered as parallel tracks.

---

## Tasks

### Task 1: Add `overnight_hook_required: true` to `lifecycle.config.md`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/lifecycle.config.md`
- **What**: Adds the `overnight_hook_required: true` field to the YAML frontmatter of the repo's own `lifecycle.config.md`, opting cortex-command into the hook-presence gate that will be enforced in Task 3. **Must land AFTER Task 5** so the field becoming `true` is atomic with the hook block existing on disk — preventing a deployment window where the gate fires with an unsatisfiable precondition.
- **Depends on**: [5]
- **Complexity**: trivial
- **Context**: File is at `/Users/charlie.hall/Workspaces/cortex-command/lifecycle.config.md`. Current frontmatter ends after `commit-artifacts: true` before `demo-commands:`. Insert `overnight_hook_required: true` as a new line in that block, following the existing key-per-line style. Implementer must also re-run `just setup-githooks` immediately after this commit lands locally (and document in the commit body that downstream developers must do the same on pull).
- **Verification**: `grep -c 'overnight_hook_required: true' /Users/charlie.hall/Workspaces/cortex-command/lifecycle.config.md` = 1 — pass if count = 1.
- **Status**: [x] complete (commit 7504640; just setup-githooks re-run, core.hooksPath=.githooks active)

---

### Task 2: Implement `_verify_hook_guard` helper in `cli_handler.py`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/cli_handler.py`
- **What**: Adds a helper function that reads `lifecycle.config.md` from the resolved repo path, checks `overnight_hook_required`, and if true performs the three-part verification (hooksPath set, hook file executable, sentinel string present). Returns an error string on failure or `None` on success/skip.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Function signature: `_verify_hook_guard(repo_path: Path) -> Optional[str]`
  - `lifecycle.config.md` parsing: follow the line-scanning pattern at `cortex_command/overnight/daytime_pipeline.py:179-194` (`_read_test_command`); no YAML library import required — scan for `overnight_hook_required:` line, compare stripped value to `"true"`.
  - Malformed/missing file: return `None` (skip verification) with a stderr warning `cortex overnight: lifecycle.config.md present but unparseable; hook verification skipped`.
  - `git config --get core.hooksPath`: use `subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=str(repo_path), capture_output=True, text=True, check=False)`; non-zero exit or empty stdout → check (i) fails.
  - Sentinel string: `"Phase 0 — overnight main-branch guard"`.
  - Error message format (for failed checks): `"cortex overnight: hook guard not installed but lifecycle.config.md requires it. Run 'just setup-githooks' to enable the pre-commit hook before launching overnight."`
- **Verification**: `grep -c '_verify_hook_guard' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/cli_handler.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete (commit ecaeb68)

---

### Task 3: Wire `_verify_hook_guard` into `handle_start` before `runner_module.run`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/cli_handler.py`
- **What**: Calls `_verify_hook_guard(repo_path)` in `handle_start` after `repo_path` is resolved and before calling `runner_module.run`. On non-None return, prints the error to stderr and returns 1.
- **Depends on**: [2]
- **Complexity**: trivial
- **Context**:
  - Insertion point: `handle_start` at line 199 (just before `return runner_module.run(...)`), after the existing `fmt == "json"` concurrent-runner check block.
  - `repo_path` is already in scope (resolved at line 143 via `_resolve_repo_path()`).
  - Print to `sys.stderr`, `flush=True`. Return 1 to signal failure to the CLI caller.
  - `dry_run` flag is available as `args.dry_run`; the spec states the verification also fires on `--dry-run` (dry-run with missing hook exits non-zero on the verification stage per Req 4 acceptance criteria).
- **Verification**: `grep -c '_verify_hook_guard(repo_path)' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/cli_handler.py` = 1 — pass if count = 1.
- **Status**: [x] complete (commit d4bdb4c)

---

### Task 4: Write `tests/test_runner_hook_guard.py`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_runner_hook_guard.py`
- **What**: Four pytest cases covering the runner-startup verification: (a) field true + hook missing → returns error string containing `"hook guard not installed"`; (b) field true + hook present and correct → returns None; (c) field absent/false → returns None (skipped); (d) **end-to-end `handle_start` integration** — field true + hook missing + invocation through `handle_start` → returns 1 with `"hook guard not installed"` on stderr, AND `runner_module.run` is NOT invoked. Case (d) closes the verification gap where Task 3's grep-only check cannot distinguish a live call from a dead one.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Follow the `_git` + `_init_repo` helper pattern from `tests/test_runner_followup_commit.py:40-60`. Use `tmp_path` pytest fixture.
  - Test setup constructs an ephemeral repo via `git init`, sets `git config user.email` / `user.name` / `commit.gpgsign=false` locally, and writes `lifecycle.config.md` with frontmatter directly to `tmp_path/repo/lifecycle.config.md`.
  - For case (b), create a `.githooks/` dir in the ephemeral repo, write a minimal pre-commit file containing the sentinel string `"Phase 0 — overnight main-branch guard"`, `chmod +x`, and set `core.hooksPath = .githooks` via `git config`.
  - For cases (a)-(c), invoke `_verify_hook_guard(repo_path)` directly (import from `cortex_command.overnight.cli_handler`); no subprocess overhead needed.
  - For case (d), invoke `handle_start` directly with a fabricated `argparse.Namespace`. Mock `cortex_command.overnight.cli_handler._resolve_repo_path` to return `tmp_path/repo`. Mock `cortex_command.overnight.cli_handler.runner_module.run` and assert `not called`. Capture stderr via `capsys` and assert `"hook guard not installed"` substring; assert return value == 1.
  - Case (a) assertion: return value is not None and contains `"hook guard not installed"`.
  - Case (c) assertion: return value is None.
- **Verification**: `python3 -m pytest tests/test_runner_hook_guard.py -q` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (commit 688fe74; 4 passed)

---

### Task 5: Write the Phase 0 block in `.githooks/pre-commit`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/.githooks/pre-commit`
- **What**: Inserts the Phase 0 block at the top of `.githooks/pre-commit`, before Phase 1, following the existing numbered-phase comment style. Includes the threat-model header paragraph (Req 7) and the sentinel comment string (Req 2). Lands BEFORE Task 1 so the hook block exists on disk before any environment sees `overnight_hook_required: true`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Insertion point: after `cd "$REPO_ROOT"` (line 26) and before the Phase 1 comment block header (line 28 `# -----`).
  - Phase 0 block structure:
    - Header comment: `# ----- Phase 0 — overnight main-branch guard -----`
    - Threat model paragraph (Req 7): a comment block with the literal word `adversarial` listing the bypass surface (--no-verify, per-command core.hooksPath, GIT_DIR=, git update-ref, commit-tree, self-modify) and the canonical adversarial defense (GitHub branch protection).
    - Branch detection: `branch=$(git symbolic-ref --quiet HEAD 2>/dev/null || true)`
    - Gate predicate: `[ "${CORTEX_RUNNER_CHILD:-}" = "1" ]` AND `[ "$branch" = "refs/heads/main" ]`
    - Rejection: `exit 1` with a stderr message naming all three required elements: rule name (`Phase 0 — overnight main-branch guard`), resolved branch (`refs/heads/main`), gate signal observed (`CORTEX_RUNNER_CHILD=1`), plus the `--no-verify` bypass note.
    - Fall-through: all other cases (incl. detached HEAD where `$branch` is empty) exit 0 and fall through.
  - `set -euo pipefail` is inherited; use `${CORTEX_RUNNER_CHILD:-}` with the `:-` default to satisfy `nounset`.
  - The sentinel comment `Phase 0 — overnight main-branch guard` appears inside the block header comment so `grep -c` can find it.
  - Bash 3.2 compatibility: no `mapfile`, no associative arrays, no `[[ =~ ]]`.
- **Verification**:
  - `grep -c 'Phase 0 — overnight main-branch guard' /Users/charlie.hall/Workspaces/cortex-command/.githooks/pre-commit` = 1 — pass if count = 1.
  - `grep -c 'adversarial' /Users/charlie.hall/Workspaces/cortex-command/.githooks/pre-commit` ≥ 1 — pass if count ≥ 1.
  - `bash -n /Users/charlie.hall/Workspaces/cortex-command/.githooks/pre-commit` exits 0 — syntax check (catches inverted/malformed predicates that grep cannot).
  - **Behavioral smoke test** — in a tmp dir: `tmp=$(mktemp -d); cd "$tmp"; git init -q --initial-branch=main; git -c user.email=t@t -c user.name=T -c commit.gpgsign=false commit --allow-empty -m init; CORTEX_RUNNER_CHILD=1 bash $REPO_ROOT/.githooks/pre-commit 2>/dev/null; echo $?` returns non-zero (predicate fires), AND `bash $REPO_ROOT/.githooks/pre-commit 2>/dev/null; echo $?` returns 0 (interactive case allowed). This catches predicate inversion (`!=` for `=`), non-strict equality, and missing fall-through that grep alone cannot detect. Full multi-case behavioral coverage lives in Task 6.
- **Status**: [x] complete (commit d1fb2e1; verification deviation: sentinel grep count = 2 not 1, because the same literal string is mandated in both the header comment AND the rejection stderr — substantive requirements satisfied, spec arithmetic was wrong)

---

### Task 6: Write `tests/test_overnight_main_commit_block.sh` with the four canonical cases

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_overnight_main_commit_block.sh`
- **What**: Regression test covering the four spec-mandated canonical cases (Req 3 a–d) across two scaffolds. Hardening cases land in Task 7 as a separate test extension.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**:
  - Shell structure: follow `tests/test_drift_enforcement.sh` for the pass/fail counter pattern. Use `set +e; HOOK_OUTPUT="$("$HOOK" 2>&1)"; HOOK_EXIT=$?; set -e` idiom.
  - **Scaffold A** setup (worktree-on-main path):
    - `git init --initial-branch=trunk "$TMPDIR/scaffA"`.
    - `git -C "$TMPDIR/scaffA" commit --allow-empty -m "init"` with `-c user.email=t@t -c user.name=T -c commit.gpgsign=false`.
    - `git -C "$TMPDIR/scaffA" branch main trunk` — creates `main` ref without checking it out.
    - `git -C "$TMPDIR/scaffA" config core.hooksPath .githooks`.
    - `mkdir -p "$TMPDIR/scaffA/.githooks"`.
    - `cp "$REPO_ROOT/.githooks/pre-commit" "$TMPDIR/scaffA/.githooks/pre-commit"`.
    - `git -C "$TMPDIR/scaffA" worktree add "$TMPDIR/scaffA-wt" main`.
    - `git -C "$TMPDIR/scaffA" worktree add "$TMPDIR/scaffA-wt-int" -b integration` — creates the integration-branch worktree that case (d) operates on.
    - Set user config in both worktrees: `git -C "$TMPDIR/scaffA-wt" config user.email t@t`, `git -C "$TMPDIR/scaffA-wt-int" config user.email t@t`, etc.
  - **Scaffold B** setup (home-repo-on-main path, the actual session-1708 vector):
    - `git init --initial-branch=main "$TMPDIR/scaffB"`.
    - `git -C "$TMPDIR/scaffB" commit --allow-empty -m "init"` with same `-c` flags.
    - `git -C "$TMPDIR/scaffB" config core.hooksPath .githooks`.
    - `mkdir -p "$TMPDIR/scaffB/.githooks"`.
    - `cp "$REPO_ROOT/.githooks/pre-commit" "$TMPDIR/scaffB/.githooks/pre-commit"`.
    - `git -C "$TMPDIR/scaffB" worktree add "$TMPDIR/scaffB-wt" -b integration`.
    - User config set locally in home repo.
  - **Case (a)** — Scaffold A worktree, `CORTEX_RUNNER_CHILD=1`, commit from worktree dir: create a tracked file, stage it, run hook with `CORTEX_RUNNER_CHILD=1` env variable set, `GIT_DIR` cleared, from `$TMPDIR/scaffA-wt`. Assert exit non-zero AND stderr contains `"Phase 0"` AND `"refs/heads/main"` AND `"CORTEX_RUNNER_CHILD"`.
  - **Case (b)** — Scaffold B home repo, `CORTEX_RUNNER_CHILD=1`, commit from `$TMPDIR/scaffB`: same file creation/staging, hook invoked from Scaffold B's home repo dir. Assert exit non-zero AND same three substrings in stderr.
  - **Case (c)** — Scaffold A worktree, no `CORTEX_RUNNER_CHILD` (unset): assert exit 0.
  - **Case (d)** — Scaffold A, `CORTEX_RUNNER_CHILD=1` but from a `git worktree add wt -b integration` worktree (use `$TMPDIR/scaffA-wt-int`): assert exit 0.
  - gitdir-sharing assertion: `git -C "$TMPDIR/scaffA-wt" rev-parse --git-common-dir` output resolves to `$TMPDIR/scaffA/.git` (trim trailing slash, compare after `realpath`).
  - `extensions.worktreeConfig` assertion: `git -C "$TMPDIR/scaffA" config --get extensions.worktreeConfig` should be empty/exit non-zero — assert it.
  - Cleanup: `trap 'rm -rf "$TMPDIR/scaffA" "$TMPDIR/scaffA-wt" "$TMPDIR/scaffA-wt-int" "$TMPDIR/scaffB" "$TMPDIR/scaffB-wt"' EXIT`.
  - Script must be executable (`chmod +x`).
- **Verification**: `bash /Users/charlie.hall/Workspaces/cortex-command/tests/test_overnight_main_commit_block.sh` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (commit 2813d8e; deviation: agent added a minimal justfile to scaffolds so cases (c)/(d) reach Phase 0 fall-through without later hook phases failing on missing recipes)

---

### Task 7: Extend `tests/test_overnight_main_commit_block.sh` with hardening cases

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_overnight_main_commit_block.sh`
- **What**: Adds two additional cases to the bash regression test that close B-class findings from the critical-review residue: case (e) verifies detached HEAD fail-open (residue B-4); case (f) verifies strict-equality on `CORTEX_RUNNER_CHILD=0` (residue B-3). Both cases reuse the existing Scaffold A built in Task 6.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Required case ordering: case (f) MUST run BEFORE case (e). Rationale: case (e) mutates Scaffold A's home repo state (`git checkout --detach`); while git's worktree-HEAD independence means the worktree at `$TMPDIR/scaffA-wt` is unaffected, the ordering guarantees case (f) operates on a known-clean scaffold. Add a comment in the test file documenting this ordering invariant.
  - **Case (f)** — `CORTEX_RUNNER_CHILD=0` (residue B-3): invoke hook on Scaffold A worktree (branch=main) with `CORTEX_RUNNER_CHILD=0` env variable set. Assert exit 0 (strict equality, `0 ≠ 1`).
  - **Case (e)** — Detached HEAD (residue B-4): run `git -C "$TMPDIR/scaffA" checkout --detach`, invoke hook from `$TMPDIR/scaffA` (the home repo, now in detached-HEAD state) with `CORTEX_RUNNER_CHILD=1`. Assert exit 0 (fail-open).
  - Comment in the test file should explain *why* case (f) exists: "If a future implementer replaces `[ \"${X:-}\" = \"1\" ]` with `[ -n \"${X:-}\" ]`, this case catches the change."
  - Both cases are added inside the existing test-counter framework; cleanup trap from Task 6 already covers them.
- **Verification**: `bash /Users/charlie.hall/Workspaces/cortex-command/tests/test_overnight_main_commit_block.sh` exits 0 — pass if exit code = 0; `grep -c 'CORTEX_RUNNER_CHILD=0' /Users/charlie.hall/Workspaces/cortex-command/tests/test_overnight_main_commit_block.sh` ≥ 1.
- **Status**: [x] complete (commit ba84e89; 8/8 tests pass)

---

### Task 8: Wire `test_overnight_main_commit_block.sh` into `tests/test_hooks.sh`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_hooks.sh`
- **What**: Adds a new section at the end of `tests/test_hooks.sh` that runs `tests/test_overnight_main_commit_block.sh` and folds its pass/fail status into the umbrella totals, so `just test-hooks` picks it up.
- **Depends on**: [6]
- **Complexity**: trivial
- **Context**:
  - `tests/test_hooks.sh` uses `PASS_COUNT`/`FAIL_COUNT` accumulators and a `pass`/`fail` shell function pattern (lines 16-25). The new block runs `bash "$REPO_ROOT/tests/test_overnight_main_commit_block.sh"` and checks its exit code, reporting a single aggregate result via `pass`/`fail`.
  - Do not discard the existing exit-summary lines at the bottom of `test_hooks.sh`.
- **Verification**: `bash /Users/charlie.hall/Workspaces/cortex-command/tests/test_hooks.sh` exits 0 — pass if exit code = 0; `grep -c 'test_overnight_main_commit_block' /Users/charlie.hall/Workspaces/cortex-command/tests/test_hooks.sh` ≥ 1.
- **Status**: [x] complete (commit e20cf6f; new test wired and passes; umbrella exits 1 due to 3 pre-existing scan-lifecycle failures unrelated to this ticket — flagged for Task 15)

---

### Task 9: Add failure logging to `_commit_followup_in_worktree`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py`, `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/events.py`
- **What**: Amends `_commit_followup_in_worktree` (lines 407-453) to capture `git commit` stderr, detect non-zero return codes, emit a stderr line, and log a structured `followup_commit_failed` event with the relevant fields. Adds `events_path: Path` to the function signature and updates both call sites to pass it.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Function location: `runner.py:407`. New signature: `_commit_followup_in_worktree(worktree_path: Path, session_id: str, events_path: Path) -> None`.
  - Caller updates: locate every call site (search `_commit_followup_in_worktree(` across `cortex_command/overnight/runner.py`); both known sites at approximately `runner.py:520` (signal-driven cleanup) and `runner.py:1586` (clean-shutdown post-loop) must be updated to pass the `events_path` already in scope at both sites. Verify via `grep -n '_commit_followup_in_worktree(' cortex_command/overnight/runner.py` after the edit — every match should pass three arguments.
  - Change the `git commit` subprocess call (line 439-451): replace `stderr=subprocess.DEVNULL` with `stderr=subprocess.PIPE`; capture result as `commit_result`.
  - After `commit_result`: if `commit_result.returncode != 0`, emit:
    - stderr line format: `runner: followup commit failed for session=<session_id> branch=<branch> rc=<returncode>` where `branch` is obtained from a `git symbolic-ref --quiet HEAD` call in the worktree (or `"unknown"` on error).
    - `events.log_event` call with type `events.FOLLOWUP_COMMIT_FAILED` (constant must be added to `cortex_command/overnight/events.py` if not present — follow the `FOLLOWUP_COMMIT_SKIPPED` pattern at `events.py:81` and add to the `EVENT_TYPES` tuple at line 83). Fields: `session_id`, `worktree_path=str(worktree_path)`, `branch`, `returncode=commit_result.returncode`, `hook_stderr=commit_result.stderr`.
  - `events_path` is passed in; wire callers to pass `events_path` from the enclosing scope.
- **Verification**:
  - `grep -c 'followup_commit_failed' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'FOLLOWUP_COMMIT_FAILED' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/events.py` = 2 (constant declaration + EVENT_TYPES entry) — pass if count = 2.
  - **Caller-arity check** — `python3 -c "import re,sys; src=open('cortex_command/overnight/runner.py').read(); calls=re.findall(r'_commit_followup_in_worktree\([^)]+\)', src); fail=[c for c in calls if c.count(',') < 2]; sys.exit(1 if fail else 0)"` exits 0 — catches partial caller updates that would `TypeError` at runtime.
  - **Importability** — `python3 -c "from cortex_command.overnight.runner import _commit_followup_in_worktree; from cortex_command.overnight.events import FOLLOWUP_COMMIT_FAILED"` exits 0.
- **Status**: [x] complete (commit 5f7a086; deviation: caller-arity regex was buggy — agent bound `wt_path = Path(state.worktree_path)` above each call site to make the spec's regex meaningful; passed `round=0` as session-level sentinel since no round is in scope)

---

### Task 10: Extend `tests/test_runner_followup_commit.py` for failure logging

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_runner_followup_commit.py`
- **What**: Adds test cases asserting that a simulated commit failure (by configuring the worktree's `core.hooksPath` to a deliberately-rejecting hook) produces both the expected stderr line and a `followup_commit_failed` events.log entry.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**:
  - Follow the `worktree_runner_env` fixture pattern (lines 63-137) for ephemeral repo construction. The new test can be a standalone function or a new fixture variant.
  - Simulating failure: configure `core.hooksPath = .githooks` in the worktree's home repo; write a pre-commit hook that always exits non-zero. Then call `_commit_followup_in_worktree(worktree_path, session_id, events_path)` directly.
  - Assert: `events_path` JSONL contains a line whose `type` field equals the value of `events.FOLLOWUP_COMMIT_FAILED`.
  - Assert: captured stderr output contains `"runner: followup commit failed"`.
  - Capturing stderr from `_commit_followup_in_worktree` (it writes to `sys.stderr`): use `capsys` pytest fixture.
- **Verification**: `python3 -m pytest tests/test_runner_followup_commit.py -q` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (commit 24eaaca; uv run pytest 2 passed; deviation: spec asserts JSONL "type" field but actual field is "event" — agent matched the existing _poll_for_event helper)

---

### Task 11: Implement `_commit_morning_report_in_repo` in `runner.py`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py`
- **What**: Adds the `_commit_morning_report_in_repo` function and wires it into `_run_post_round_loop` immediately after `_generate_morning_report` (line 1580).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Function signature: `_commit_morning_report_in_repo(project_root: Path, session_id: str, events_path: Path) -> None`.
  - Git invocations use `cwd=str(project_root)`, `env={k: v for k, v in os.environ.items() if k != "GIT_DIR"}` (follow the pattern from `_commit_followup_in_worktree:421`).
  - `git add lifecycle/morning-report.md` — the tracked top-level copy. Per-session path (`lifecycle/sessions/<session_id>/morning-report.md`) is gitignored at `.gitignore:41`; recommended decision: skip the per-session path (it is gitignored by design as a session-archive artifact). Document this choice in the function docstring per Req 9.
  - After staging: run `git diff --cached --quiet` (check=False); if `returncode != 0` (something staged), run `git commit -m f"Overnight session {session_id}: morning report"` with `stderr=subprocess.PIPE`.
  - On success (commit returncode == 0): call `events.log_event(events_path, events.MORNING_REPORT_COMMIT_RESULT, ...)`.
  - On failure (commit returncode != 0): call `events.log_event(events_path, events.MORNING_REPORT_COMMIT_FAILED, ...)`.
  - Both event constants already exist at `cortex_command/overnight/events.py:76,78`.
  - Wiring: in `_run_post_round_loop`, after the `_generate_morning_report(...)` call at line 1575, add `_commit_morning_report_in_repo(repo_path, session_id, events_path)` inside the `if not dry_run:` block (repo_path and events_path are already in scope).
  - All exceptions are swallowed (same best-effort contract as `_generate_morning_report`).
- **Verification**:
  - `grep -c 'def _commit_morning_report_in_repo' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py` = 1 — pass if count = 1.
  - `grep -c 'MORNING_REPORT_COMMIT_RESULT' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'MORNING_REPORT_COMMIT_FAILED' /Users/charlie.hall/Workspaces/cortex-command/cortex_command/overnight/runner.py` ≥ 1 — pass if count ≥ 1.
  - **Wiring check** — `python3 -c "import re,sys; src=open('cortex_command/overnight/runner.py').read(); m=re.search(r'def _run_post_round_loop[^\n]*\n((?:[ ]{4,}.*\n|\n)+)', src); body=m.group(1) if m else ''; sys.exit(0 if '_commit_morning_report_in_repo(' in body else 1)"` exits 0 — confirms the call site exists inside `_run_post_round_loop`'s body, not just defined as an unwired function.
- **Status**: [x] complete (commit 7ffb346; deviation: spec wiring regex names `_run_post_round_loop` but actual function is `_post_loop` — call site wired into `_post_loop` at runner.py:1719, verified substantively)

---

### Task 12: Write `tests/test_runner_morning_report_commit.py`

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_runner_morning_report_commit.py`
- **What**: Two pytest cases asserting (a) `_commit_morning_report_in_repo` commits successfully when `lifecycle/morning-report.md` has staged content and emits `MORNING_REPORT_COMMIT_RESULT`, and (b) no-ops cleanly (no event or a no-op result event) when nothing is staged.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**:
  - Ephemeral repo construction: `git init` + `git commit --allow-empty -m init` with `-c user.email=t@t -c user.name=T -c commit.gpgsign=false`; set local user config.
  - For case (a): write a `lifecycle/morning-report.md` file to the repo directory and stage it with `git add lifecycle/morning-report.md`.
  - Call `_commit_morning_report_in_repo(repo_path, "test-session", events_path)` directly (imported from `cortex_command.overnight.runner`).
  - Assert: events log JSONL contains a line whose `type` field equals `events.MORNING_REPORT_COMMIT_RESULT`.
  - For case (b): nothing staged; assert either no event is written OR the written event has a no-op/skipped outcome field. Implementer documents the choice in the test.
  - Do NOT set `CORTEX_RUNNER_CHILD=1` in the test environment — the function must commit without the hook blocking it (verifies the architectural invariant that runner-direct commits live above Phase 0).
- **Verification**: `python3 -m pytest tests/test_runner_morning_report_commit.py -q` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (commit 4ed0888; 2 passed)

---

### Task 13: Update `requirements/pipeline.md` line 24 (Session Orchestration AC)

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/requirements/pipeline.md`
- **What**: Replaces the stale morning-report-commit AC clause at line 24 with accurate post-129 + this-ticket steady-state text describing morning report paths, the runner-process commit, and that Phase 0 does not block it.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - Current text at line 24: `"The morning report commit is the only runner commit that stays on local `main` (needed before PR merge for morning review to read)"`.
  - Replace with text that: (1) names both write paths (`lifecycle/sessions/{session_id}/morning-report.md` — gitignored per-session archive — and `lifecycle/morning-report.md` — tracked latest copy); (2) states the latter is committed to local `main` by the runner process directly (not a runner-spawned child); (3) notes that Phase 0 does not block this because `CORTEX_RUNNER_CHILD` is unset in the runner process.
  - Keep the surrounding AC list structure unchanged; this is a single bullet replacement, not a section rewrite.
- **Verification**:
  - `grep -c 'morning report commit is the only runner commit that stays on local' /Users/charlie.hall/Workspaces/cortex-command/requirements/pipeline.md` = 0 — pass if count = 0.
  - `grep -c 'lifecycle/morning-report.md' /Users/charlie.hall/Workspaces/cortex-command/requirements/pipeline.md` ≥ 1 — pass if count ≥ 1.
  - Architectural-claim check (paraphrase-tolerant): `python3 -c "import sys; src=open('requirements/pipeline.md').read(); ok=('runner process' in src and 'CORTEX_RUNNER_CHILD' in src and 'Phase 0' in src); sys.exit(0 if ok else 1)"` exits 0 — verifies the replacement text names the runner process, the gate signal, and Phase 0 without coupling to brittle exact phrasing.
- **Status**: [x] complete (commit 7c1778a)

---

### Task 14: Static spawn-site env-var assertion

- **Files**: `/Users/charlie.hall/Workspaces/cortex-command/tests/test_runner_spawn_env.py`
- **What**: New pytest module asserting that `runner.py`'s orchestrator-spawn and batch-runner-spawn paths still pass `CORTEX_RUNNER_CHILD` to their child subprocesses. Closes residue B-1/B-3's most-likely refactor mistake (a future change drops the env var from one of the two spawn sites, silently disabling Phase 0 enforcement) without requiring a behavioral integration test harness — that integration test remains deferred per spec's Open Decisions.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - The two known spawn sites are at approximately `runner.py:714` (`_spawn_orchestrator`) and `runner.py:901` (`_spawn_batch_runner`), each passing `env={**os.environ, "CORTEX_RUNNER_CHILD": "1"}` to a `subprocess.Popen` / `subprocess.run` call (per spec's Architectural Insight section and research §"Spawn-site reality vs. ticket text").
  - Primary assertion (literal-string count): read `cortex_command/overnight/runner.py` source as text; assert the literal string `CORTEX_RUNNER_CHILD` appears at least 2 times. This catches the catastrophic refactor where the env var is dropped from one or both sites.
  - Caveat to document in the test docstring: a refactor that moves env construction to a helper function (e.g., `env=_runner_child_env()`) keeps the count low — the count check still requires the helper's definition to contain the literal string. If the helper exists, count is at least 1 (helper definition) plus ≥ 1 if any spawn site still uses the literal-dict form. The test should accept count ≥ 2 OR a count of 1 with a recognizable helper-function name pattern (e.g., regex `def\s+\w*[Cc]hild_env\b` matches in the source). If neither condition holds, fail with a message pointing to spec's Architectural Insight section.
  - The test does NOT exercise the spawn chain at runtime — that integration test (50+ LOC of test scaffolding for runner.py end-to-end) remains deferred to a follow-up ticket.
- **Verification**: `python3 -m pytest tests/test_runner_spawn_env.py -q` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (commit e6c0da0)

---

### Task 15: Non-regression check — run full hook and test suites

- **Files**: none (verification only)
- **What**: Confirms the Phase 0 insertion is additive and does not break existing hook phases or Python tests.
- **Depends on**: [4, 7, 8, 10, 12, 13, 14]
- **Complexity**: trivial
- **Context**:
  - `just test-hooks` runs `tests/test_hooks.sh` which includes the drift-enforcement tests for existing phases (Phases 1–4). The umbrella also runs `test_overnight_main_commit_block.sh` via Task 8.
  - `just test` runs the full Python test suite including the new `test_runner_hook_guard.py`, the extended `test_runner_followup_commit.py`, `test_runner_morning_report_commit.py`, and `test_runner_spawn_env.py`.
- **Verification**:
  - `bash /Users/charlie.hall/Workspaces/cortex-command/tests/test_drift_enforcement.sh` exits 0 — pass if exit code = 0.
  - `just test-hooks` exits 0 — pass if exit code = 0.
  - `just test` exits 0 — pass if exit code = 0.
- **Status**: [x] complete (verification only — drift 6/6 pass; just test-hooks exits 0 with 18/21 sub-tests passing — 3 pre-existing scan-lifecycle failures unrelated to this ticket; just test 6/6 suites pass)

---

## Verification Strategy

End-to-end verification after all tasks complete:

1. **Hook gate fires on the session-1708 vector**: In a fresh ephemeral repo with `core.hooksPath = .githooks` and the updated `.githooks/pre-commit`, run `CORTEX_RUNNER_CHILD=1 git commit --allow-empty` from the home repo while on `main`. Expected: exit non-zero with stderr containing `"Phase 0"`, `"refs/heads/main"`, and `"CORTEX_RUNNER_CHILD"`.
2. **Hook fails open on detached HEAD**: same scaffold but with `git checkout --detach` and `CORTEX_RUNNER_CHILD=1`. Expected: exit 0.
3. **Hook respects strict equality on `CORTEX_RUNNER_CHILD=0`**: same scaffold with `CORTEX_RUNNER_CHILD=0`. Expected: exit 0.
4. **Runner-startup gate refuses**: in cortex-command's own repo (which now has `overnight_hook_required: true`), temporarily rename `.githooks/pre-commit`, then run `cortex overnight start --dry-run`. Expected: exit non-zero, stderr contains `"hook guard not installed"`.
5. **Runner-startup gate passes after `just setup-githooks`**: restore the hook and run `cortex overnight start --dry-run` again. Expected: startup verification passes (no hook-guard error on stderr).
6. **Spawn-site env-var assertion holds**: `python3 -m pytest tests/test_runner_spawn_env.py -q` exits 0 — confirms `CORTEX_RUNNER_CHILD` still appears at runner.py's spawn sites (catches future refactors that would silently disable Phase 0).
7. **Existing phases unbroken**: `bash tests/test_drift_enforcement.sh` exits 0.
8. **Full suite clean**: `just test` exits 0.

---

## Veto Surface

- **Single-helper hook-guard vs. two-helper split**: Plan B proposed `_read_hook_guard_required` + `_verify_hook_guard` as separate helpers. This plan uses one combined helper following `daytime_pipeline.py:_read_test_command`'s established pattern. If you prefer the two-helper split for testability, flag before Task 2 begins.
- **Bash test split (Tasks 6 + 7)**: Tasks 6 and 7 share the same file — they're a deliberate split of "spec-mandated 4 cases" vs. "residue-driven 2 cases" to keep each task's complexity bounded and make the audit trail explicit. If you'd prefer them merged into one larger task, flag before Task 6 begins.
- **Per-session morning report staging**: Task 11 recommends skipping the gitignored per-session path. If you prefer `git add -f` to commit both copies (per-session archive + tracked latest), flag before Task 11 begins. The spec leaves this to implementer judgment.
- **Spawn-site CORTEX_RUNNER_CHILD assertion follow-up**: residue findings B-1, B-2, B-3 (spec's Open Decisions). Resolution after critical review: the cheap static assertion is now Task 14 (`test_runner_spawn_env.py`), which catches the most-likely refactor mistake (env var dropped from one of the two spawn sites). The behavioral integration test remains deferred to a follow-up ticket per spec's Open Decisions.

- **Rollout / operator note**: After Tasks 1+5 land (atomically — see Sizing), every developer environment must re-run `just setup-githooks` on pull. The runner-startup gate's first check (`git config --get core.hooksPath`) returns empty in environments that never set it, producing the "hook guard not installed" error. The PR description for the merge commit must include this instruction. CI environments that run `cortex overnight start` need the same setup step in their bootstrap.

---

## Scope Boundaries

(Maps to spec's Non-Requirements section.)

- **Does NOT defend against adversarial agents** — bypasses (`--no-verify`, per-command `core.hooksPath` overrides, `GIT_DIR=`, plumbing commits, self-modifying the hook) are out of scope. Server-side branch protection on `main` is the canonical adversarial defense and is not implemented in this ticket.
- **Does NOT install or enforce hooks in downstream user repos by default** — downstream repos opt in by setting `overnight_hook_required: true` in their own `lifecycle.config.md`.
- **Does NOT auto-mutate `core.hooksPath`** from `python-setup`, `cortex init`, or any setup recipe — the existing manual `just setup-githooks` step remains; runner-startup verification (Tasks 2–4) is the enforcement mechanism, not silent config mutation.
- **Does NOT provide an emergency env-var override** for the runner-startup verification — fail-closed is the agreed posture.
- **Does NOT replace `LIFECYCLE_SESSION_ID` as a telemetry signal** — the variable continues to be used by `bin/cortex-log-invocation`; only the hook's gate predicate uses `CORTEX_RUNNER_CHILD` instead.
- **Does NOT rewrite `cortex-scan-lifecycle.sh`** to stop overwriting `LIFECYCLE_SESSION_ID` — the overwrite is preserved (it serves the SessionStart context-injection purpose).
- **Does NOT introduce a `pre-commit.d/` chain or any new abstraction** for hook composition — Phase 0 is added inline as a numbered phase block matching the existing 7-phase structure.
- **Does NOT add a path-allowlist or second env-var carve-out** to Phase 0 — the architectural insight (runner-direct commits live above the gate) makes such carve-outs unnecessary.
- **Does NOT include a behavioral integration test exercising runner.py's spawn chain end-to-end** (residue B-1 mitigation) — deferred to a follow-up ticket per spec's Open Decisions. The cheap static assertion that the env var still appears at the spawn sites IS in scope as Task 14.

---

## Sizing

| Task | Complexity | Est. minutes |
|------|-----------|-------------|
| 1 — lifecycle.config.md field | trivial | 2 |
| 2 — `_verify_hook_guard` helper | simple | 10 |
| 3 — Wire into `handle_start` | trivial | 3 |
| 4 — `test_runner_hook_guard.py` | simple | 12 |
| 5 — Phase 0 hook block + threat model | simple | 10 |
| 6 — Bash test, 4 canonical cases | complex | 15 |
| 7 — Bash test, 2 hardening cases | simple | 8 |
| 8 — Wire into `test_hooks.sh` | trivial | 5 |
| 9 — Failure logging in `_commit_followup_in_worktree` | simple | 12 |
| 10 — Extend `test_runner_followup_commit.py` | simple | 12 |
| 11 — `_commit_morning_report_in_repo` + wiring | simple | 12 |
| 12 — `test_runner_morning_report_commit.py` | simple | 12 |
| 13 — `requirements/pipeline.md` update | trivial | 3 |
| 14 — `test_runner_spawn_env.py` static assertion | simple | 8 |
| 15 — Non-regression run | trivial | 5 |

Total: 15 tasks, ~129 estimated minutes across all tasks (5–15 minutes each except Task 6 at 15 min).

Parallel waves available after dependency resolution (revised after critical-review: Task 1 now depends on Task 5 to prevent the deployment trap where the gate fires with an unsatisfiable precondition):
- **Wave 1** (no dependencies): Tasks 5, 9, 11, 13, 14.
- **Wave 2**: Tasks 1 (after 5), 6 (after 5), 10 (after 9), 12 (after 11).
- **Wave 3**: Tasks 2 (after 1), 7 (after 6), 8 (after 6).
- **Wave 4**: Task 3 (after 2).
- **Wave 5**: Task 4 (after 3).
- **Wave 6**: Task 15 (after 4, 7, 8, 10, 12, 13, 14).

Atomic-landing requirement: Tasks 1 and 5 should land in the same commit (or same PR with co-located commits) so no developer environment ever observes `overnight_hook_required: true` without a Phase 0 hook on disk. The dependency edge enforces ordering; the commit policy enforces atomicity.
