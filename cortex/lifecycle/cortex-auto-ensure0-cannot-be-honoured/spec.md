# Specification: cortex-auto-ensure0-cannot-be-honoured

## Problem Statement

`cortex-lifecycle-init-ensure` refuses with exit 2 inside any attached git worktree, which makes `cortex-lifecycle-enter` return `{"state":"blocked"}` with `.session` unwritten and halts every lifecycle phase run from a worktree — the sanctioned steady-state path for build phases (ADR-0008) and the path every overnight/parallel builder takes (`skills/build/references/parallel-execution.md:3-7`). The documented `CORTEX_AUTO_ENSURE=0` escape hatch cannot rescue it, because the helper's probe runs before the opt-out check is ever reached, making `cortex/requirements/project.md:52` false as written. The same probe fails 19 tests in `cortex_command/init/tests/test_handler_ensure.py` for any pytest run launched from inside a worktree. Research established that the guard's justification is dead: F9's named harm — "first-init via `--ensure` writes into the feature worktree; worktree removal silently destroys the cortex/ data" — became structurally impossible when #273 turned the bootstrap arm into a refusal (`cortex_command/init/handler.py:217-225`), and `cortex-lifecycle-enter` writes into the worktree at `enter.py:321-322` *before* the guard runs at `:330` anyway. Removing the guard restores worktree lifecycle work, makes the documented opt-out true, and fixes the test suite in one deletion.

## Phases

- **Phase 1: Remove the attached-worktree refusal** — delete both probe copies, replace the tests that pinned them, and record the supersede.

## Requirements

1. **The helper's attached-worktree probe is removed.** `_check_not_attached_worktree` no longer exists in `cortex_command/lifecycle/init_ensure.py`, and nothing in the module calls it. Acceptance: `grep -c "_check_not_attached_worktree" cortex_command/lifecycle/init_ensure.py` prints `0`. Grounding file: `cortex_command/lifecycle/init_ensure.py:29-84,115`. **Phase**: Remove the attached-worktree refusal

2. **The CLI-surface probe is removed.** The duplicate `_check_not_attached_worktree` in `cortex_command/init/handler.py` and its call in `_run_ensure` are gone. Removing only the helper's copy would leave all 19 test failures in place, since `test_handler_ensure.py` exercises `handler.main` in-process. Acceptance: `grep -c "_check_not_attached_worktree" cortex_command/init/handler.py` prints `0`. Grounding file: `cortex_command/init/handler.py:150,243-291`. **Phase**: Remove the attached-worktree refusal

3. **`cortex init --ensure` succeeds from an attached worktree of an initialized repo.** Acceptance: from a `git worktree add` worktree of this repo, `CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -m cortex_command.lifecycle.init_ensure` exits `0`, and `cortex/.cortex-init` is the sole path the run makes newly present. Check, run inside that worktree: `git status --porcelain --ignored > /tmp/wt-before.txt; CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -m cortex_command.lifecycle.init_ensure; echo "exit=$?"; git status --porcelain --ignored > /tmp/wt-after.txt; diff /tmp/wt-before.txt /tmp/wt-after.txt` (snapshots land outside the worktree so they cannot appear in their own scan). Passes when the echo prints `exit=0` and the diff's only added line is `> !! cortex/.cortex-init` — `--ignored` is required because that path is gitignored (`.gitignore:39`) and so never appears in plain `git status --porcelain`. **Phase**: Remove the attached-worktree refusal

4. **`--ensure` still refuses on an uninitialized repo, including from a worktree.** The case (iii) refusal is now the sole guard against writing a `cortex/` tree somewhere it will be lost. Acceptance: in a scratch git repo with no `cortex/` directory, invoked from an attached worktree of it, the verb exits `2` and stderr contains the substring `not yet initialized`. Grounding file: `cortex_command/init/handler.py:217-225`. **Phase**: Remove the attached-worktree refusal

5. **`CORTEX_AUTO_ENSURE=0` silences the helper inside a worktree**, making `cortex/requirements/project.md:52` true as written. Acceptance: from an attached worktree, `CORTEX_AUTO_ENSURE=0 CORTEX_COMMAND_FORCE_SOURCE=1 uv run python -m cortex_command.lifecycle.init_ensure` exits `0` and `git status --porcelain` in that worktree prints nothing. **Phase**: Remove the attached-worktree refusal

6. **The init and lifecycle test modules pass when pytest is launched from inside a worktree.** Acceptance: from an attached worktree, `CORTEX_COMMAND_FORCE_SOURCE=1 uv run pytest cortex_command/init/tests/test_handler_ensure.py cortex_command/lifecycle/tests/test_init_ensure.py -q` exits `0`. Baseline for comparison: `test_handler_ensure.py` alone is 19 failed / 3 passed from a worktree and 22 passed from the primary checkout. **Phase**: Remove the attached-worktree refusal

7. **A regression test pins CWD-independence.** A new test in `cortex_command/init/tests/test_handler_ensure.py` creates an attached worktree, `chdir`s the process into it, and asserts `_run_ensure` against an unrelated initialized `tmp_path` repo exits `0` — so a future reintroduction of an ambient-CWD probe fails a test rather than silently returning. Acceptance: the new test exists and passes; reverting Requirement 2's deletion makes it fail. **Phase**: Remove the attached-worktree refusal

8. **The tests that pinned the deleted behavior are removed, not left asserting it.** `test_r11a_worktree_attached_refusal` and `test_r11b_regular_checkout_baseline` are deleted or rewritten to assert the new contract; no test asserts an exit-2 worktree refusal. Acceptance: `grep -c "test_r11a_worktree_attached_refusal" cortex_command/lifecycle/tests/test_init_ensure.py` prints `0`. Grounding file: `cortex_command/lifecycle/tests/test_init_ensure.py:301,376`. **Phase**: Remove the attached-worktree refusal

9. **Docstrings stop claiming a worktree refusal.** The module docstring and the argparse `description` in `cortex_command/lifecycle/init_ensure.py` no longer describe an R11 worktree refusal. Acceptance: `grep -ci "worktree" cortex_command/lifecycle/init_ensure.py` prints `0`. Grounding file: `cortex_command/lifecycle/init_ensure.py:16,104`. **Phase**: Remove the attached-worktree refusal

10. **The supersede is recorded where a future contributor will look.** `cortex/requirements/project.md`'s `CORTEX_AUTO_ENSURE=0 opt-out` bullet records that the attached-worktree refusal was removed and why — #273 removed the bootstrap arm that made it load-bearing — so the guard is not re-added on the original F9 reasoning. Acceptance: `grep -c "attached worktree" cortex/requirements/project.md` prints `1` or more, and `grep -c '#273' cortex/requirements/project.md` prints `1` or more (it prints `0` on unmodified HEAD). Grounding file: `cortex/requirements/project.md:52`. **Phase**: Remove the attached-worktree refusal

## Non-Requirements

- **Reordering the opt-out ahead of the probe.** Moot once the probe is gone: `CORTEX_AUTO_ENSURE=0` reaches `handler.py:141` on both surfaces with no reorder, so the `spec.md:44`-vs-`plan.md:60` ordering conflict dissolves instead of being adjudicated.
- **Target-anchoring the probe to the resolved repo root**, and **main-repo-anchoring `--ensure`'s write target.** Both were investigated and rejected in research; see Technical Constraints.
- **Adding the primary-worktree path to case (iii)'s diagnostic.** This would preserve the deleted guard's one residual courtesy — telling a worktree user where to go — but only for the combination "repo with no `cortex/` at all, someone made a worktree of it, and ran a lifecycle phase inside it." No observed instance of that combination exists, and **Deletion bias** (`project.md:23`) puts the burden of proof on adding the machinery.
- **Symptom 3 — `cortex-load-requirements` reporting the primary checkout's state.** `cortex/requirements/lifecycle.md:119` documents the worktree/main-repo resolution divergence as intended, and `lifecycle.md`'s own Open Questions already defers the remedy ("whether the review phase's no-area-doc warning should also fire when a listed requirements path is reported absent"). It belongs to that question.
- **`enter`'s half-applied phase on a `blocked` outcome.** `enter.py:321-322` writes `index.md` and syncs the backlog before `:330` decides the state, so any `ensure_code != 0` leaves a partially applied phase. This survives the deletion — case (iii) and R19 still return 2 — but it is an ordering bug in `enter`, not in the guard. File separately.
- **Changing `skills/build/SKILL.md:40`'s `blocked` contract.** The state remains reachable and its documented handling stays correct; nothing to change, and leaving it alone keeps the dual-source mirror out of this commit.

## Edge Cases

- **Worktree of an initialized repo, marker absent (the normal case).** Selects case (iv) adoption (`handler.py:226-245`): additive scaffold with `overwrite=False` plus `write_marker(refresh=False)`. Measured in this repo's real worktree: 0 missing templates, both `.gitignore` targets already present, so the sole write is the gitignored `cortex/.cortex-init`. Expected: exit 0, marker written, nothing else touched; the marker's loss on `git worktree remove` costs nothing because the next `--ensure` in the primary checkout re-derives it.
- **Worktree of an uninitialized repo.** Case (iii) refuses with exit 2 before any write (Requirement 4). This is the scenario F9 was written for, and it is now guarded by the dispatch rather than by a CWD probe.
- **Worktree whose branch deleted some signature templates.** Case (iv) adoption writes the missing templates into the worktree, where they are git-tracked and will show as modifications. Expected: acceptable — the same additive behavior the primary checkout gets, and visible in `git status` rather than silent.
- **Foreign `cortex/` content in a worktree.** R19 still declines (`handler.py:250+`); the deletion does not widen R19's boundary.
- **`CORTEX_REPO_ROOT` pinned to the worktree by the overnight dispatcher** (`cortex_command/pipeline/dispatch.py:700`). Unaffected: with no probe, `--ensure` operates on the worktree as the dispatcher already intends, and writes only the gitignored marker there.
- **Concurrent worktree builders.** Each writes its own worktree's marker; no shared-root contention is introduced. (Had main-repo-anchoring shipped, N builders would have contended on one non-atomic `ensure_gitignore` read-modify-write.)

## Changes to Existing Behavior

- **REMOVED** — `_check_not_attached_worktree` in `cortex_command/lifecycle/init_ensure.py` and its call site.
- **REMOVED** — the duplicate `_check_not_attached_worktree` in `cortex_command/init/handler.py` and its call in `_run_ensure`.
- **REMOVED** — `test_r11a_worktree_attached_refusal` and `test_r11b_regular_checkout_baseline`.
- **MODIFIED** — `cortex-lifecycle-init-ensure` exit-2 causes: previously worktree-attached, foreign-content, marker-corruption, install-lock; now foreign-content, marker-corruption, install-lock, uninitialized-repo.
- **MODIFIED** — `cortex/requirements/project.md`'s opt-out bullet gains the supersede record.
- **ADDED** — a CWD-independence regression test.
- **Unchanged** — `enter`'s `KNOWN_STATES`, the `blocked` state and its `skills/build/SKILL.md:40` contract, R19, R6, and the five-case dispatch.

## Technical Constraints

- **Neither touched module is a dual-source mirror.** `plugins/` mirrors only `skills/`, `hooks/`, and `bin/cortex-*`; `.githooks/pre-commit`'s trigger lists never name `init_ensure.py` or `handler.py`. No mirror rebuild is involved.
- **Main-repo anchoring was rejected on four grounds**: inert in the overnight path (`dispatch.py:700` pins `CORTEX_REPO_ROOT` to the worktree and `interactive_lock.py:177-179` honors it verbatim); outside the sandbox allow-list (`overnight/sandbox_settings.py:66-73,163-171`); fails open to the worktree when its `cortex/`-existence guard trips (`interactive_lock.py:186,198` → `common.py:97`); and raises an uncaught `CortexProjectRootError` on the first-init case, since `handler.main` catches only `ScaffoldError`/`SettingsMergeError` (`handler.py:494`).
- **Target-anchoring by adding `cwd=` was rejected as a latent defect**: `git rev-parse --git-common-dir` returns a *relative* path when CWD is not the repo root while `--git-dir` returns absolute, and the existing `.resolve()` calls are anchored to the process CWD — adding `cwd=` produces a false worktree refusal in the primary checkout. Had any probe survived, it would have needed `git rev-parse --path-format=absolute` (git ≥ 2.31).
- **The `worktree_root = git_dir.parent.parent.parent` diagnostic is wrong in every layout**, not just unusual ones: `--git-dir` in a worktree points into the primary's `.git`, so the three-parent walk yields the primary root by construction. Both copies disappear with the probes.
- **`resolve_main_repo_root()` is not reusable for worktree detection** — it redirects a worktree CWD to the main root, the opposite of detection.
- **R11 is spec text, not drift.** `cortex/lifecycle/auto-apply-cortex-init-at-lifecycle/spec.md:44` mandates the helper check "Before any other check". This spec supersedes that requirement on the stated ground that #273 removed the bootstrap arm it protected; Requirement 10 records it.

## Open Decisions

None. The one live fork — delete the guard outright versus scope the refusal to case (iii) — is resolved in favour of deletion, because case (iii) *is* that scoped refusal and already runs before any write, so a second guard expressing the same condition would be redundant rather than defensive.

## Proposed ADR

None. The decision was assessed against `cortex/adr/README.md`'s three-criteria gate and fails criterion 1 (hard to reverse): it unwinds by restoring two functions in one PR. Criteria 2 and 3 are met, so the reasoning is recorded in `project.md` per Requirement 10 rather than lost.
