# Plan: cortex-auto-ensure0-cannot-be-honoured

## Overview

Delete both copies of `_check_not_attached_worktree` and their call sites, let the case (iii) uninitialized-repo refusal be the sole guard, replace the two tests that pinned the deleted behavior with a CWD-independence regression test, and record the supersede in `cortex/requirements/project.md`. Four independent single-file edits land in one wave; two verification tasks then prove the behavioral acceptance criteria against a real attached worktree.

## Outline

### Phase 1: Remove the attached-worktree refusal (tasks: 1, 2, 3, 4, 5, 6, 7)
**Goal**: `cortex init --ensure` and `cortex-lifecycle-init-ensure` succeed from an attached worktree of an initialized repo, `CORTEX_AUTO_ENSURE=0` is honoured there, and both test modules pass when pytest is launched from inside a worktree.
**Checkpoint**: from an attached worktree, `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/init/tests/test_handler_ensure.py cortex_command/lifecycle/tests/test_init_ensure.py -q` exits 0, and `cortex/.cortex-init` is the only path the ensure run makes newly present.

## Tasks

### Task 1: Remove the probe from the lifecycle skill-helper
- **Files**: `cortex_command/lifecycle/init_ensure.py`
- **What**: Delete `_check_not_attached_worktree` and its call site so the helper delegates straight to `handler.main`, and strip every worktree/R11 claim from the module docstring and the argparse `description` (spec R1, R9).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Caller enumeration (repo-wide `grep -rn "_check_not_attached_worktree"`, run during planning): the symbol has exactly four live sites — the definition and call in this file, and the definition and call in `handler.py` (Task 2). No consumer exists in `skills/`, `hooks/`, `docs/`, `bin/`, `cortex_command/pipeline/`, or `cortex_command/overnight/`; the only other hits are two historical `cortex/lifecycle/*/review.md` records, which are archival and must not be edited. The function body is `init_ensure.py:30-85`; the call site plus its `R11:` comment is `:114-118`. `import subprocess` (`:24`) and `from pathlib import Path` (`:26`) become unused — the probe is their only consumer (`:40,50,56,66,67`) — so both imports go; `argparse`, `sys`, and `typing.List/Optional` stay. Worktree/R11 prose to rewrite: the docstring paragraph at `:3-8` (which cites the refusal as the example of "structural separation"), the exit-code line `:17` ("worktree-attached, foreign-content, etc."), and the argparse `description` at `:101-105`. Exit-2 causes after this change are foreign-content, marker-corruption, install-lock, and uninitialized-repo — use those in the `:17` line.
- **Verification**: `grep -c "_check_not_attached_worktree" cortex_command/lifecycle/init_ensure.py` = `0` and `grep -ci "worktree" cortex_command/lifecycle/init_ensure.py` = `0` (note `-i`: zero *lines* may mention worktree in any case), and `CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -c "import cortex_command.lifecycle.init_ensure"` exits `0`.
- **Status**: [x] done (f7af30d2 2026-08-08T15:26:10-04:00)

### Task 2: Remove the probe from the `cortex init --ensure` CLI surface
- **Files**: `cortex_command/init/handler.py`; `cortex_command/init/tests/test_handler_ensure.py` (read-only — the Verification runs this module but must not edit it; Task 4 owns its one edit)
- **What**: Delete the duplicate `_check_not_attached_worktree` and its call in `_run_ensure`, leaving the opt-out check (a) followed directly by the install-lock check (c) (spec R2).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Caller enumeration is shared with Task 1 — the repo-wide sweep found four live sites total and no consumer outside these two modules. **The spec's line numbers for this file are stale; these are measured against HEAD.** Function body is `handler.py:265-313` (the spec says `243-291`); the call site is `:148` (the spec says `:150`), preceded by the `# (b) Worktree-attached refusal (R11 CLI-surface mirror).` comment block at `:144-147` which goes with it. Re-locate by symbol, not by the spec's offsets. Keep `import subprocess` — `_resolve_repo_root` still uses it at `:64,74` — and keep `Path`, used throughout. Renumbering the surviving `# (a)`/`# (c)`/`# (d)`/`# (e)` dispatch comments is optional; do not renumber the five-case dispatch labels (i)–(v), which are spec-referenced. `_run_ensure`'s own docstring describes the dispatch, not the probe, so it needs no change beyond removing any worktree sentence it carries.
- **Verification**: `grep -c "_check_not_attached_worktree" cortex_command/init/handler.py` = `0`, and `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/init/tests/test_handler_ensure.py -q` from the primary checkout exits `0` with `22 passed` (matching the measured pre-change primary baseline, so the deletion regresses nothing).
- **Status**: [x] done (f7af30d2 2026-08-08T15:26:10-04:00)

### Task 3: Delete the two tests that pinned the refusal
- **Files**: `cortex_command/lifecycle/tests/test_init_ensure.py`
- **What**: Remove `test_r11a_worktree_attached_refusal` and `test_r11b_regular_checkout_baseline` along with their section-banner comments, and drop the R11 clauses from the module docstring so no test or docstring asserts an exit-2 worktree refusal (spec R8).
- **Depends on**: none
- **Complexity**: simple
- **Context**: `test_r11a_worktree_attached_refusal` spans `:296-368` (banner at `:296-298`); `test_r11b_regular_checkout_baseline` spans `:371-434` (banner at `:371-373`) and runs to end of file. The module docstring's R11 description is at `:1,15,17-18`. R9/R10 tests (`:74,115,175,242,260,278`) stay. Check whether `sys` and `subprocess` remain used by the surviving tests before touching imports — the R10c dual-source test at `:278` uses `subprocess`, so it stays; confirm `sys` the same way rather than assuming.
- **Verification**: `grep -c "test_r11a_worktree_attached_refusal" cortex_command/lifecycle/tests/test_init_ensure.py` = `0` and `grep -c "test_r11b_regular_checkout_baseline" ...` = `0`; `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/lifecycle/tests/test_init_ensure.py -q` from the primary checkout exits `0`.
- **Status**: [x] done (f7af30d2 2026-08-08T15:26:10-04:00)

### Task 4: Add the CWD-independence regression test
- **Files**: `cortex_command/init/tests/test_handler_ensure.py`; `cortex_command/init/handler.py` (mutation-check only — the Verification temporarily re-adds a probe here and must revert it; this task leaves the file byte-identical to Task 2's output)
- **What**: Add a test that creates an attached git worktree, `chdir`s the process into it, and asserts `_run_ensure` against an unrelated initialized `tmp_path` repo exits `0` — so a future reintroduction of an ambient-CWD probe fails loudly instead of silently refusing (spec R7).
- **Depends on**: [2]
- **Complexity**: moderate
- **Context**: Two repos are needed and must stay distinct: a throwaway git repo whose attached worktree supplies the hostile CWD, and the `tmp_path` target repo the ensure actually operates on. Existing helpers in this file: `_git_init` (`:53`, `git init` only — no commit, so the worktree-host repo needs its own `git add`/`git commit` with `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env and `commit.gpgsign=false`, per the setup at `test_init_ensure.py:308-346`), `_isolate_home` (`:58`), `_make_ensure_args` (`:68`), `_make_update_args` (`:79`, plants a real marker via the terminal `--update` path). Follow the shape of `test_r7_cortex_auto_ensure_0_no_op` (`:571`) for the `_isolate_home` + `XDG_STATE_HOME` monkeypatch preamble. Use `monkeypatch.chdir(worktree)` so the CWD is restored on teardown; do **not** leave a bare `os.chdir`. Plant the marker on the target repo with `init_main(_make_update_args(repo)) == 0` first so the run selects case (i), then assert `_run_ensure(_make_ensure_args(repo))` returns `0`. Name the test so its intent survives a grep — e.g. `test_ensure_is_cwd_independent_from_attached_worktree` — and state in the docstring that it is the anti-revert pin for the deleted probe.
- **Verification**: `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/init/tests/test_handler_ensure.py -q` exits `0`; then mutation-check the pin — temporarily re-add a `_check_not_attached_worktree()`-equivalent refusal at the top of `_run_ensure`, confirm the new test **fails**, revert the mutation, and confirm `git diff --stat cortex_command/init/handler.py` shows the file back at Task 2's output. A test that passes both with and against the mutation is not pinning anything.
- **Status**: [x] done (f88852bf 2026-08-08T15:27:26-04:00)

### Task 5: Record the supersede in project.md
- **Files**: `cortex/requirements/project.md`
- **What**: Extend the `CORTEX_AUTO_ENSURE=0 opt-out` bullet so it records that the attached-worktree refusal was removed and why — #273 turned the bootstrap arm into a refusal, killing the F9 data-loss harm the guard existed for — so a future contributor does not re-add it on the original reasoning (spec R10).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The bullet is the `**\`CORTEX_AUTO_ENSURE=0\` opt-out**` line in `cortex/requirements/project.md` (currently `:52`). Its existing final sentence already covers the R19 adoption carve-out (#387) — append after it, don't restructure. Facts the sentence must carry: the refusal read ambient process CWD, never the target repo; the case (iii) "not yet initialized" refusal (`handler.py:217-225`) is now the sole guard and runs before any write; in an initialized repo the only write a worktree `--ensure` makes is the gitignored `cortex/.cortex-init` marker, which the next primary-checkout `--ensure` re-derives. Match the file's existing bullet register — dense, declarative, `#NNN`-referenced. This supersedes `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md:44` (R11), which is spec text rather than drift, so name that too.
- **Verification**: `grep -c "attached worktree" cortex/requirements/project.md` ≥ `1` and `grep -c '#273' cortex/requirements/project.md` ≥ `1` (both print `0` on unmodified HEAD, confirmed).
- **Status**: [x] done (f7af30d2 2026-08-08T15:26:10-04:00)

### Task 6: Prove the behavioral acceptance criteria from an attached worktree
- **Files**: `cortex_command/lifecycle/init_ensure.py`, `cortex_command/init/handler.py` (read-only — this task edits no source; it fixes any failure by reporting back, not by widening scope)
- **What**: Run spec requirements 3, 4, and 5 against real rigs: ensure succeeds from a worktree of this initialized repo writing only the marker, still refuses on an uninitialized repo from a worktree, and honours `CORTEX_AUTO_ENSURE=0` there.
- **Depends on**: [1, 2, 4] (write-serialization: cortex_command/init/handler.py)
- **Complexity**: moderate
- **Context**: Build the worktree under the session scratchpad, never inside the repo, and enter it in a subshell — a removed worktree you `cd`'d into leaves a deleted CWD that later-spawned subagents inherit. A verification worktree may already exist at `<scratchpad>/wt-475-verify`; it is detached at the pre-change commit, so **recreate it** rather than reusing it, or the run tests unmodified code. Because a worktree checks out a commit and cannot see the primary checkout's uncommitted edits, run the modified source explicitly: with CWD inside the worktree, invoke `PYTHONPATH=<primary> CORTEX_COMMAND_FORCE_SOURCE=1 uv run --project <primary> …`. That recipe was validated at HEAD and reproduced the 19-failure signature, so it genuinely exercises primary-checkout source under a worktree CWD. R4's rig is a separate scratch `git init` repo with no `cortex/` directory plus an attached worktree of it. R3's status snapshots must be written outside the worktree so they cannot appear in their own scan, and need `--ignored` because `cortex/.cortex-init` is gitignored (`.gitignore:39`).
- **Verification**: three checks, all from inside an attached worktree. (R3) `git status --porcelain --ignored > <scratch>/before.txt; CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -m cortex_command.lifecycle.init_ensure; echo "exit=$?"; git status --porcelain --ignored > <scratch>/after.txt; diff <scratch>/before.txt <scratch>/after.txt` → prints `exit=0` and the diff's only added line is `> !! cortex/.cortex-init`. (R4) from a worktree of a scratch repo with no `cortex/`, the verb exits `2` and stderr contains `not yet initialized`. (R5) `CORTEX_AUTO_ENSURE=0 CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -m cortex_command.lifecycle.init_ensure` exits `0` and `git status --porcelain` in that worktree prints nothing.
- **Status**: [x] done (verification-only, no commit; verified against f88852bf 2026-08-08T15:27:26-04:00)

### Task 7: Prove both test modules pass with pytest launched from inside a worktree
- **Files**: `cortex_command/init/tests/test_handler_ensure.py`, `cortex_command/lifecycle/tests/test_init_ensure.py` (read-only — verification task; a failure is reported, not patched here)
- **What**: Run spec requirement 6, the executable form of symptom 2, and confirm the measured worktree failure signature is gone.
- **Depends on**: [1, 2, 3, 4]
- **Complexity**: simple
- **Context**: Measured pre-change baselines to compare against, all re-verified against HEAD in this planning pass: `test_handler_ensure.py` is **19 failed / 3 passed** from a worktree and **22 passed** from the primary checkout; `test_init_ensure.py` is **1 failed / 7 passed** from a worktree (`test_r9c_namespace_shape_equivalence`, which the spec's baseline does not name but requirement 6 covers) and fully green from the primary checkout. Post-change the worktree run must be green with the two deleted R11 tests absent and the new regression test present. Reuse Task 6's scratchpad worktree and the same `PYTHONPATH`/`--project` recipe if verifying before commit; a worktree created after the implementation commit needs neither.
- **Verification**: from an attached worktree, `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/init/tests/test_handler_ensure.py cortex_command/lifecycle/tests/test_init_ensure.py -q` exits `0`. Then `just test` from the primary checkout exits `0`, catching any consumer of the deleted symbols outside these two modules.
- **Status**: [x] done (verification-only, no commit; verified against f88852bf 2026-08-08T15:27:26-04:00)

## Risks

- **The deletion is one-way in spirit, not in fact.** It contradicts `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md:44` (R11, "Before any other check"). Task 5 records the supersede; if you would rather keep a scoped guard, the fallback research named is to move a probe *below* the dispatch where it can see whether a write would create a new `cortex/` — but that is redundant with case (iii), which is why the spec resolved against it.
- **Worktree users of an uninitialized repo lose a courtesy diagnostic.** Case (iii) tells them to run `cortex init` but no longer names the primary checkout's path. The spec declined to add it under Deletion bias, with no observed instance of that combination. If you disagree, that is a one-line addition to `handler.py:217-225`, not a reason to keep the probe.
- **`enter`'s half-applied phase survives.** `enter.py:321-322` still writes `index.md` and syncs the backlog before `:330` decides the state, so any remaining `ensure_code != 0` (case (iii), R19) still leaves a partial phase. The spec files this separately; this plan does not touch it, and no task should widen into it.
- **Task 6 and 7 verify pre-commit through a `PYTHONPATH` shim.** It reproduced the failure signature at HEAD, so it is sound, but it is not the shape a user runs. If anything reads ambiguous, re-run both after the commit against a worktree created at the new HEAD — that path has no shim.
- **Task 6 sits alone in the middle level, which is normally a restructure signal.** The shape is 4-1-2 (`{1,2,3,5}` → `{4}` → `{6,7}`). It is accepted deliberately: Task 4's mutation check transiently re-adds a probe to `handler.py`, so a concurrent Task 6 could read a mutated tree. The only restructure that would widen the level is merging tasks, which the authoring rules forbid. Under worktree isolation the annotated edge relaxes to not-before and the width returns — so the cost is trunk-only.
- **The spec's `handler.py` line numbers are stale.** Measured against HEAD the probe is `:265-313` and its call `:148`, not the spec's `243-291`/`:150`. Task 2 carries the correction; if any other task's offsets look off, re-locate by symbol rather than trusting the spec's grounding lines.
