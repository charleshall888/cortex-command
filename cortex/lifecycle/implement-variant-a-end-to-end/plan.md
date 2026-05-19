# Plan: implement-variant-a-end-to-end

## Overview
Wire the orchestrator session's mid-lifecycle `cd` into the interactive worktree, refactor the orchestrator-session-reachable writer sites to accept an optional `worktree_root`, extend `cortex init` to register the worktree base in both `sandbox.filesystem.allowWrite` and `additionalDirectories`, and add cd-in-then-out around `/cortex-core:pr` in the Complete phase. The work lands as four PRs (Slice 7): Phase 1 (inventory + characterization tests, no behavior change), Phase 2 (`cortex init` extension), Phase 3 (new helper + per-callsite parameter), Phase 4 (lifecycle prose).

## Outline

### Phase 1: Writer-site inventory & characterization (tasks: 1, 2)
**Goal**: Lock in the call-graph-derived writer-site inventory and pin current behavior with characterization tests so Phase 3 can be verified non-regressive.
**Checkpoint**: `writer-sites.md` committed; baseline tests green on `main`.

### Phase 2: Sandbox infrastructure (tasks: 3, 4)
**Goal**: Extend `cortex init` to additively register the worktree base path in `allowWrite` and `additionalDirectories`.
**Checkpoint**: A fresh `cortex init` populates both arrays idempotently in an isolated test fixture; re-running does not duplicate.

### Phase 3: Path-resolution refactor (tasks: 5, 6, 7, 8)
**Goal**: Add `_resolve_user_project_root_from_cwd()` and per-callsite `worktree_root: Path | None = None` parameter additively. Existing env-first contract untouched.
**Checkpoint**: `just test` exits 0 with new helper + parameter behavior covered; existing tests at `cortex_command/tests/test_common.py:55-56` and `tests/test_common_utils.py:486` unchanged.

### Phase 4: Lifecycle integration (tasks: 9, 10, 11, 12, 13)
**Goal**: Wire the cd handoff into `implement.md` §1a and the cd-in-then-out pattern around `/cortex-core:pr` in `complete.md` Step 3, with advisory two-signal detection.
**Checkpoint**: `just test` exits 0 (including kept-pauses parity); `interactive_worktree_entered` event registered; four detection-outcome cases verified.

## Tasks

### Task 1: Phase 1 writer-site inventory artifact
- **Files**: `cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` (new)
- **What**: Enumerate orchestrator-session-reachable writer sites by tracing call graphs from `skills/lifecycle/references/implement.md` §1a–§4 and `skills/lifecycle/references/complete.md`. Each entry: `file:line` + reachability rationale (which step routes to it). Exclude sites in `cortex_command/overnight/daytime_pipeline.py` (slated for #246 removal).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R4. Start from the eight ticket-named sites enumerated in `research.md` § "The eight named writer sites — verified state" (`cortex_command/refine.py:117`; `cortex_command/critical_review.py:340-349,375-416,318-322`; `bin/cortex-complexity-escalator:265,296`; `cortex_command/discovery.py:189-197`; `cortex_command/backlog/update_item.py:445,169`; `claude/statusline.sh:244-247`; `cortex_command/overnight/report.py:52,125`). Add any additional sites surfaced by call-graph audit. Note in the artifact which sites are currently CWD-pinned versus env-pinned (per `research.md`'s classification).
- **Verification**: `test -f cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` — pass if exit 0; `wc -l < cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` > 20 — pass if count > 20.
- **Status**: [ ] pending

### Task 2: Characterization tests pinning current writer-site behavior
- **Files**: `tests/test_variant_a_writer_sites_baseline.py` (new), or per-module additions to existing test files where suitable.
- **What**: For each inventoried site, add a test that pins current pre-refactor behavior (resolved write target with default args / no `worktree_root` parameter). These tests pass on `main` and remain green after Phase 3 lands.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Spec R5. Pattern reference: env-var assertion structure in `cortex_command/tests/test_common.py:55-56`. For sites that resolve via `_resolve_user_project_root()`, pin the env-first behavior. For sites that resolve via bare relative paths, pin the CWD-relative behavior. Use `tmp_path` + `monkeypatch.chdir` or `monkeypatch.setenv` per case.
- **Verification**: `just test` — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Extend `cortex init` to register worktree base in `allowWrite` and `additionalDirectories`
- **Files**: `cortex_command/init/handler.py`
- **What**: Additively register the worktree base path (`$TMPDIR/cortex-worktrees/` by default, or the value of `CORTEX_WORKTREE_ROOT` if set) in both `sandbox.filesystem.allowWrite` and `additionalDirectories` of `~/.claude/settings.local.json`. Idempotent under the existing `fcntl.flock`-guarded merge (per ADR-0003).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R6. Pattern reference: existing umbrella registration at `cortex_command/init/handler.py:194-198` (Step 7) registers `<repo>/cortex/` in `allowWrite` only. Reuse the same merge helpers and `fcntl.flock` guarding. No removal of existing entries.
- **Verification**: `grep -c "additionalDirectories" cortex_command/init/handler.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 4: Tests for `cortex init` worktree-base registration
- **Files**: `cortex_command/init/tests/test_settings_merge.py` (additions) or new sibling test file under `cortex_command/init/tests/`.
- **What**: Verify that after `cortex init` runs in an isolated test fixture, `settings.local.json` contains the worktree base path in both `allowWrite` and `additionalDirectories`. Re-running `cortex init` does not duplicate either entry.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Spec R6 acceptance. Pattern reference: existing fixtures and the retired dual-registration scaffold at `cortex_command/init/tests/test_settings_merge.py:954`. Use `tmp_path` + `monkeypatch.setenv("HOME", ...)` to isolate the user settings path.
- **Verification**: `uv run python -m pytest cortex_command/init/tests/ -k "worktree_base"` — pass if exit 0 and at least one test in the selection passes.
- **Status**: [ ] pending

### Task 5: Add `_resolve_user_project_root_from_cwd()` helper
- **Files**: `cortex_command/common.py`
- **What**: New module-level function performing walk-up from `Path.cwd().resolve()` ignoring `CORTEX_REPO_ROOT`. Same stop conditions as the existing function: `.git` file (worktree) or `.git/` directory, or presence of a `cortex/` directory. Raises `CortexProjectRootError` when no ancestor matches. Signature: `def _resolve_user_project_root_from_cwd() -> Path:`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R1, R2. Existing function at `cortex_command/common.py:55-103` retains its env-first contract — do not modify. Reuse the existing walk-up loop body (extract into a shared private helper if natural, otherwise duplicate the loop).
- **Verification**: `grep -c "def _resolve_user_project_root_from_cwd" cortex_command/common.py` = 1 — pass if count = 1.
- **Status**: [ ] pending

### Task 6: Tests for `_resolve_user_project_root_from_cwd()`
- **Files**: `cortex_command/tests/test_common.py`
- **What**: Add tests verifying (a) the helper returns the worktree root when CWD is inside a worktree even with `CORTEX_REPO_ROOT` set to the main repo; (b) the helper raises `CortexProjectRootError` from a non-cortex directory. Existing tests at lines 55-56 unchanged.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Spec R2 acceptance. Pattern reference: existing env-var assertion at `cortex_command/tests/test_common.py:55-56`. Use `tmp_path` + a fake `.git` file (worktree-shaped) + `monkeypatch.setenv("CORTEX_REPO_ROOT", ...)`.
- **Verification**: `uv run python -m pytest cortex_command/tests/test_common.py -k "from_cwd"` — pass if exit 0 and at least one test in the selection passes.
- **Status**: [ ] pending

### Task 7: Add `worktree_root: Path | None = None` parameter to inventoried writer sites
- **Files**: `cortex_command/refine.py`, `cortex_command/critical_review.py`, `bin/cortex-complexity-escalator`, `cortex_command/discovery.py`, plus any additional Python modules surfaced by Task 1's `writer-sites.md` inventory.
- **What**: Add `worktree_root: Path | None = None` to each refactored function's signature. When present, resolve absolute lifecycle paths as `worktree_root / "cortex/lifecycle" / ...` (or analogous for `cortex/research`). When absent, retain existing behavior. For `bin/cortex-complexity-escalator`, expose via a new argparse flag `--worktree-root`.
- **Depends on**: [1, 5]
- **Complexity**: complex
- **Context**: Spec R3. Pattern reference: existing optional-base shape at `cortex_command/common.py:453,526` (`lifecycle_base: Path = Path("cortex/lifecycle")`) and the post-#130 `backlog_dir` parameter in `cortex_command/backlog/update_item.py`. Caller enumeration: before editing each refactored function, grep `cortex_command/` and `bin/` for every caller and confirm the default-None signature preserves the call-site contract (caller enumeration is required per the plan-reference Caller Enumeration rule).
- **Verification**: `just test` — pass if exit 0.
- **Status**: [ ] pending

### Task 8: Tests for `worktree_root` parameter behavior
- **Files**: `cortex_command/tests/test_refine.py`, `cortex_command/tests/test_critical_review.py`, `cortex_command/tests/test_discovery.py`, `tests/test_cortex_complexity_escalator.py` (extend existing test files where present, add per-module tests where absent).
- **What**: For each refactored site in Task 7, add at least one test passing a non-None `worktree_root` that lands the write in the parameter's directory rather than CWD or env-resolved root. Verify the write target is `worktree_root / "cortex/lifecycle" / {feature}` (or analogous).
- **Depends on**: [7]
- **Complexity**: complex
- **Context**: Spec R3 acceptance. Use `tmp_path` as the `worktree_root` value per test. For the `bin/cortex-complexity-escalator` test, invoke the CLI with `--worktree-root` and assert the events.log lands under the parameter directory.
- **Verification**: `just test` — pass if exit 0.
- **Status**: [ ] pending

### Task 9: Register `interactive_worktree_entered` event in events registry
- **Files**: `bin/.events-registry.md`
- **What**: Add a registry entry for `interactive_worktree_entered` with producer (`skills/lifecycle/references/implement.md` §1a), JSON schema (`{schema_version: 1, ts, event, feature, worktree_path}`), and one-line semantics.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R7 acceptance gates on `grep -c "interactive_worktree_entered" bin/.events-registry.md` = 1. Pattern reference: existing entries for `interactive_lock_acquired`, `pr_opened`, `feature_complete` in `bin/.events-registry.md`.
- **Verification**: `grep -c "interactive_worktree_entered" bin/.events-registry.md` = 1 — pass if count = 1.
- **Status**: [ ] pending

### Task 10: Wire cd handoff into `implement.md` §1a
- **Files**: `skills/lifecycle/references/implement.md`. Plugin mirror at `plugins/cortex-core/skills/lifecycle/references/implement.md` regenerates via the pre-commit hook — edit canonical source only.
- **What**: After worktree creation and lock acquisition in §1a, add prose directing the orchestrator to (a) capture `_origin_pwd=$(pwd)`, (b) issue `cd $(cortex-worktree-resolve interactive/{slug})` via Bash, (c) emit an `interactive_worktree_entered` event written to `cortex/lifecycle/{slug}/events.log` (path resolves to the worktree post-cd). Include a paragraph beginning "Variant A's cd affects only orchestrator-session Bash" whose final sentence cross-references §2(e) Worktree Integration (`implement.md:151-161`).
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Spec R7. Pattern reference: existing §1a prose (worktree-create + lock-acquire flow shipped via #239/#241). Kept-pauses parity: if line shifts cause the inventory anchor at `skills/lifecycle/SKILL.md:60` (backlog disambiguation) or `implement.md:22` (branch selection) to move >35 lines, update `skills/lifecycle/SKILL.md` "Kept user pauses" inventory in this task.
- **Verification**: `grep -c "interactive_worktree_entered" skills/lifecycle/references/implement.md` ≥ 1 — pass if count ≥ 1; `grep -c "Variant A's cd affects only orchestrator-session Bash" skills/lifecycle/references/implement.md` = 1 — pass if count = 1; `just test` — pass if exit 0 (kept-pauses parity included).
- **Status**: [ ] pending

### Task 11: Add advisory worktree-detection prose to `complete.md` Step 3
- **Files**: `skills/lifecycle/references/complete.md`. Plugin mirror regenerates via pre-commit hook.
- **What**: In Step 3, add prose for two-signal advisory detection: read `interactive.pid` via `cortex_command/interactive_lock.py:read_lock(feature_slug)` AND corroborate by comparing `git rev-parse --show-toplevel` against `pwd`. If either signal is absent or contradictory, treat as NOT in Variant A and skip the cd-in-then-out branch (proceed with `/cortex-core:pr` from current cwd).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R9. Public API reference: `cortex_command/interactive_lock.py` `read_lock`. Pattern reference: existing cd-out-or-bail guard at `complete.md:159-163` (Step 8).
- **Verification**: `grep -c "git rev-parse --show-toplevel" skills/lifecycle/references/complete.md` ≥ 1 — pass if count ≥ 1; `grep -c "interactive.pid" skills/lifecycle/references/complete.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 12: Wire cd-in-then-out around `/cortex-core:pr` in `complete.md` Step 3
- **Files**: `skills/lifecycle/references/complete.md`. Plugin mirror regenerates via pre-commit hook.
- **What**: Update Step 3 so that when the Task 11 detection reports positive, the lifecycle (a) saves `_origin_pwd=$(pwd)`, (b) `cd`s into the worktree if not already there, (c) invokes `/cortex-core:pr`, (d) restores `cd "$_origin_pwd"` after the PR skill returns. The Step 8 cd-out hard guard at `complete.md:159-163` composes correctly because of (d).
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Spec R8. Pattern reference: existing Step 3 prose. Kept-pauses parity: if line shifts cause `complete.md` inventory anchors to move >35 lines, update `skills/lifecycle/SKILL.md` "Kept user pauses" inventory in this task.
- **Verification**: `grep -c "_origin_pwd" skills/lifecycle/references/complete.md` ≥ 2 — pass if count ≥ 2; `just test` — pass if exit 0 (kept-pauses parity included).
- **Status**: [ ] pending

### Task 13: Add detection-case tests in `test_complete_pr_routing.py`
- **Files**: `tests/test_complete_pr_routing.py` (new)
- **What**: Verify the four detection-outcome cases for advisory worktree detection: (a) both signals positive → cd-in-then-out path is selected; (b) PID stale + pwd in worktree → cd-in-then-out path; (c) PID present + pwd NOT in worktree → non-worktree path; (d) both absent → non-worktree path.
- **Depends on**: [11, 12]
- **Complexity**: complex
- **Context**: Spec R9 acceptance. Mock `cortex_command.interactive_lock.read_lock` and `subprocess.run` for `git rev-parse --show-toplevel`. Use `tmp_path` + `monkeypatch.chdir` to control `pwd`. Pattern reference: existing test fixtures in `tests/` that mock subprocess and interactive_lock.
- **Verification**: `uv run python -m pytest tests/test_complete_pr_routing.py` — pass if exit 0 and at least one test in the file passes.
- **Status**: [ ] pending

## Risks

- **Phase 1 inventory may surface materially more writer sites than the eight ticket-named** (per spec Edge Cases). If audit reveals 30+ orchestrator-reachable sites, Phase 3 task count balloons and Task 7's complexity classification may need to split into sub-tasks. Mitigation: surface back at end of Task 1 before Phase 3 begins.
- **Slice 7 four-PR commit shape (R10, should-have)** is preferred for reviewability and bisect-ability but the work could land as a single bundled PR. If reviewer load on four sequential PRs proves heavy, fall back to a single bundled PR; the four-phase task structure remains intact.
- **Kept-pauses parity drift**: Tasks 10 and 12 modify `implement.md` and `complete.md` near existing parity anchors. If line-shift exceeds the 35-line tolerance in `tests/test_lifecycle_kept_pauses_parity.py`, the SKILL.md inventory must update in the same task (called out per-task).
- **Open Decision — `interactive.pid` session_id migration on `/clear`** (spec § Open Decisions): surface to user during plan approval; either fold into Task 11/12 scope or carve out as a follow-up ticket.
- **Phase 2 migration gap for users on unmigrated `settings.local.json`** (spec Edge Cases): users who installed before Phase 2 ships will hit sandbox-deny on first Write inside the worktree until they re-run `cortex init`. Spec explicitly leaves this unmitigated; release notes should call it out.

## Acceptance

After all four phases land: a Variant-A session that selects implement-phase preflight option 2 creates an `interactive/{slug}` worktree, the orchestrator session `cd`s into it after worktree creation, orchestrator-session events.log writes land in the worktree (and ship inside the PR), `cortex init` has registered the worktree base path in both `sandbox.filesystem.allowWrite` and `additionalDirectories` so Write tool calls inside the worktree succeed, and `/cortex-core:lifecycle complete <slug>` opens a worktree-aware PR via cd-in-then-out around `/cortex-core:pr`. `just test` exits 0; kept-pauses parity passes; existing env-first contract in `_resolve_user_project_root()` unchanged.
