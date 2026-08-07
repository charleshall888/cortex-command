# Plan: overnight-session-worktree-lives-in-tmpdir

## Overview

Fix the asymmetry at the one chokepoint: `_merge_target_repo_path()` stops handing home-repo
features an unchecked `Path`, and instead resolves → re-creates in place → or returns `None`.
Re-creation reuses `_effective_merge_repo_path()`'s existing `git worktree add` idiom, extracted
into a shared `_ensure_worktree()` helper so the cross-repo path stays byte-identical and the home
path does **not** inherit the `-lazy-<repo>` naming. When re-creation fails, the five existing
degraded-path guards route to `deferred` (no `recoverable_branch`) instead of `paused`, and a new
morning-report section names the branch to verify rather than advising a rebuild. The
conflict-gated `recoverable_branch` disposition at `outcome_router.py:828-875` is not touched.

## Outline

### Phase 1: Detect, recover, and preserve the evidence (tasks: 1)
**Goal**: `_merge_target_repo_path()` never returns a non-existent path for a home-repo feature —
it re-creates in place when it can and returns `None` when it cannot, emitting the loss signal
either way; and an exception escaping a feature coroutine no longer discards its traceback.
**Checkpoint**: a deleted home integration worktree is re-created at exactly
`state.worktree_path` (no `-lazy-` component) on the next resolver call, `integration_degraded`
is `True` in `overnight-state.json`, and the originating frame of an escaped exception is in the
events log.

### Phase 2: Route the unrecoverable case honestly (tasks: 2, 3)
**Goal**: an unresolvable worktree produces a `deferred` feature carrying
`error: "integration worktree unresolved"` and no `recoverable_branch` — not `paused`, not
`failed` — and that error reaches `overnight-state.json`.
**Checkpoint**: `features_paused` is empty, `systemic_pauses_in_batch == 0`, the feature is not
re-dispatched next round, and `state.features[f].error == "integration worktree unresolved"`.

### Phase 3: Report, document, and pin the recovery (tasks: 4, 5, 6, 7)
**Goal**: the morning report names the branch to verify instead of "retry or investigate" and
reports rebuilds with a count; the requirements doc covers mid-session loss; the PR gate and the
round-boundary backlog write-back are pinned against regression.
**Checkpoint**: `just test` green; a generated report for a deferred-on-unresolved-worktree
session contains the `pipeline/*` branch name and not the fallback advice.

## Tasks

### Task 1: Home integration worktree resolves, re-creates in place, or reports unresolvable

- **Files**:
  - `cortex_command/overnight/outcome_router.py`
  - `cortex_command/overnight/orchestrator.py`
  - `cortex_command/overnight/events.py`
  - `cortex_command/overnight/tests/test_outcome_router.py`
  - `cortex_command/overnight/tests/test_orchestrator.py`
  - `cortex_command/overnight/tests/test_lead_unit.py`
- **What**: Extract the `git worktree add` + `"already exists"` + `"already checked out at"`
  recovery core of `_effective_merge_repo_path()` into a shared helper, give
  `_merge_target_repo_path()`'s home-repo arm an existence check that calls it with the
  **in-place** path, and stop discarding the traceback of exceptions escaping a feature
  coroutine. Satisfies spec Requirements 1, 3, 4, and the producer half of 9.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - **Extraction.** `_effective_merge_repo_path()` is `outcome_router.py:128-258`. Extract
    `_ensure_worktree(repo_path: Path, worktree_path: Path, branch: str, *, on_exists_fallback:
    Path | None = None) -> Path` containing only `:192-258` (the `subprocess.run(["git",
    "worktree", "add", ...])` with its `GIT_DIR`-stripped env, the `"already exists"` arm, the
    `"already checked out at"` prune-and-retry arm, and the unknown-failure `RuntimeError`). The
    `"already exists"` arm returns `on_exists_fallback` when it is not `None`, else
    `worktree_path` when it exists, else raises — this preserves the current cache-first ordering
    at `:210-219` exactly. `_effective_merge_repo_path()` keeps its `None` short-circuit
    (`:169-170`), cached-hit check (`:173-175`), `integration_branches` lookup + `RuntimeError`
    (`:178-183`), `-lazy-<repo_dir_name>` path construction (`:185-188`),
    `integration_worktrees[key]` cache write, and both `logger.warning` calls; it passes
    `on_exists_fallback=Path(integration_worktrees[key]) if key in integration_worktrees else
    None`. **Its signature and cross-repo behaviour must not change** — callers:
    `_merge_target_repo_path` (`:273`) and `feature_executor.py:666`; existing pins:
    `TestEffectiveMergeRepoPath` (`tests/test_lead_unit.py:638-750`, 5 resolution cases),
    `test_outcome_router.py:1696-1745`, `tests/test_feature_executor.py`.
  - **Context field.** Add `home_repo_path: Path | None = None` to the `OutcomeContext` dataclass
    (`outcome_router.py:73-92`, after `home_worktree_path`). Populate it at **both**
    `OutcomeContext(...)` constructions in `orchestrator.py` (`:434` and `:527`) from
    `overnight_state.project_root` (`state.py:265`, an `Optional[str]`), captured alongside
    `home_worktree_path` at `orchestrator.py:271-277`, falling back to
    `_resolve_user_project_root()` (already imported at `orchestrator.py:26`) when the state field
    is absent. The field is defaulted, so the four test-side constructions
    (`test_outcome_router.py:54`, `:1563`, `test_lead_unit.py:69`,
    `tests/test_revert_merge_real_git.py:192`) stay valid unchanged.
  - **Home arm.** `_merge_target_repo_path()` (`:261-278`): return `ctx.home_worktree_path`
    unchanged when it is `None` or `.exists()`. Otherwise resolve the branch from
    `ctx.integration_branches` keyed by `_normalize_repo_key(str(ctx.home_repo_path))` (already
    imported at `:61`; `state._normalize_repo_key` applies `expanduser().resolve()`, which works
    on a non-existent path) with a raw-`str(ctx.home_repo_path)` fallback, mirroring
    `runner._resolve_feature_integration_worktree`'s un-normalized-key fallback
    (`runner.py:824-828`). Then call `_ensure_worktree(ctx.home_repo_path,
    ctx.home_worktree_path, branch)`. **Pass `ctx.home_worktree_path` itself as the worktree
    path** — do not construct a `-lazy-` path, and do not write the result into
    `ctx.integration_worktrees`, which holds cross-repo worktrees only (`runner.py:806-819`). On
    success return that path; on `RuntimeError`/`OSError`, or when `home_repo_path` or the branch
    is unavailable, return `None`.
  - **Loss signal** (spec Req 9 producer), emitted once per detected loss regardless of outcome:
    `overnight_log_event(INTEGRATION_WORKTREE_MISSING, ctx.config.batch_id, feature=name,
    details={"session_id": ctx.session_id, "feature": name, "worktree_path":
    str(ctx.home_worktree_path), "context": "merge_target", "recreated": <bool>},
    log_path=ctx.config.overnight_events_path)`. The constant is already in `events.EVENT_TYPES`
    (`events.py:71`) and already emitted with a `context` detail by `runner.py:869-887`. Then set
    `integration_degraded = True` via the best-effort `load_state`/`save_state` idiom already used
    at `outcome_router.py:2278-2285` — whole block inside `try:`/`except Exception: pass`, since a
    state-write failure must not block resolution.
  - **Traceback** (spec Req 3). Add `FEATURE_EXCEPTION = "feature_exception"` to `events.py`
    alongside the other constants (`:32-99`) **and** to the `EVENT_TYPES` tuple (`:101+`) —
    `log_event` raises on an unlisted event (`:230-233`). Check whether the vocabulary is mirrored
    elsewhere: `grep -rn "EVENT_TYPES" docs/ tests/ cortex_command/`. In the `for n, exc in
    zip(eligible, gather_results):` loop (`orchestrator.py:502-507`), before constructing
    `failed_result`, emit `overnight_log_event(FEATURE_EXCEPTION, config.batch_id, feature=n,
    details={"error": str(exc), "traceback": "".join(traceback.format_exception(type(exc), exc,
    exc.__traceback__))}, log_path=config.overnight_events_path)` inside `try:`/`except Exception:
    pass` so a logging failure cannot mask the original fault. Add `import traceback`
    (`orchestrator.py:16-24`) and `FEATURE_EXCEPTION` to the existing events import block
    (`:43-51`). Leave `error=f"unexpected exception: {exc}"` as-is — downstream matchers key off
    it.
  - **Inter-task contract** (Tasks 4 reads this): the loss event is
    `integration_worktree_missing` with `details.recreated: bool` and
    `details.context: "merge_target"`.
  - Re-creation runs inside `ctx.lock` at every call site (spec Edge Cases) — do not add an
    unlocked fast path.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_outcome_router.py
  cortex_command/overnight/tests/test_orchestrator.py cortex_command/overnight/tests/test_lead_unit.py -q`
  exits 0, with three new tests: (a) **Req 1** — an `OutcomeContext` whose `home_worktree_path`
  points at a deleted directory **and whose `integration_branches` has no entry for
  `home_repo_path`** (so re-creation is impossible) asserts `_merge_target_repo_path(ctx, name) is
  None`; (b) **Req 4** — a real git fixture in the `TestHomeMergeWorktreeCollision` idiom
  (`test_outcome_router.py:1463-1520`) deletes the home integration worktree, calls the resolver,
  and asserts `git -C <returned> rev-parse --abbrev-ref HEAD` == `overnight/<session_id>`, that
  the returned path `==` `ctx.home_worktree_path` exactly, and that `"-lazy-" not in
  str(returned)`; (c) **Req 3** — a feature coroutine raises a uniquely-named exception from a
  named helper, and the helper's function name appears in the `traceback` detail of a
  `feature_exception` entry in the events log written to `tmp_path`.
- **Status**: [x] done (dac36ef8 2026-08-07T11:31:06-04:00)

### Task 2: Unresolvable worktree defers the feature instead of pausing it

- **Files**:
  - `cortex_command/overnight/outcome_router.py`
  - `cortex_command/overnight/tests/test_outcome_router.py`
- **What**: Replace the five duplicated degraded-path guard bodies with one shared
  `_defer_unresolved_worktree()` that appends to `features_deferred` (carrying `error`, **no**
  `recoverable_branch`), emits `FEATURE_DEFERRED`, and writes back to the backlog — dropping the
  `features_paused` append and the `consecutive_pauses` increment. Satisfies spec Requirements 2,
  5, and 7.
- **Depends on**: [1] (write-serialization: cortex_command/overnight/outcome_router.py)
- **Complexity**: complex
- **Context**:
  - The five guard blocks are at `outcome_router.py:581-606`, `:715-737`, `:1465-1488`,
    `:1881-1904`, `:2291-2314`. Each is byte-similar: `features_paused.append` +
    `cb_state.consecutive_pauses += 1` + `FEATURE_PAUSED` + `_write_back_to_backlog(name,
    "paused", ...)` + `return`. Replace each body with a call to the new helper, keeping each
    site's surrounding `if ctx.repo_path_map.get(name) is None and <var> is None:` condition, its
    explanatory comment (updated from "Pause and surface" to the deferral wording), and its
    `return`. The `:2291` site runs **outside** `ctx.lock` and today wraps its body in `async with
    ctx.lock:` — keep that wrapper around the helper call.
  - `_defer_unresolved_worktree(ctx, name)` is **sync** (every site calls it from sync context or
    from inside an already-held lock) and mirrors the conflict terminus at `:828-875` minus the
    recoverable claim:
    `error = "integration worktree unresolved"`;
    `ctx.batch_result.features_deferred.append({"name": name, "question_count": 0, "error":
    error})`;
    `overnight_log_event(FEATURE_DEFERRED, ctx.config.batch_id, feature=name, details={"error":
    error, "conflict": False, "unresolved_worktree": True, "branch":
    ctx.worktree_branches.get(name)}, log_path=ctx.config.overnight_events_path)`;
    `_write_back_to_backlog(name, "paused", ctx.config.batch_id,
    ctx.config.overnight_events_path, backlog_id=ctx.backlog_ids.get(name),
    backlog_uuid=ctx.backlog_uuids.get(name))`.
    **Approval-time scope decision (2026-08-07): pass `"paused"`, not `"deferred"`**, so the
    `_OVERNIGHT_TO_BACKLOG` mapping writes `status: in_progress` rather than `status: backlog`.
    Writing `backlog` would return the item to the from-scratch-rebuild pool — the exact harm
    Requirement 7 names, displaced by one session — and would contradict the morning report's
    Task 4 advice to verify the named branch rather than re-run. This stays inside Requirement 7,
    which constrains `recoverable_branch` and the **runtime** disposition; the runtime disposition
    is still `deferred` (the `features_deferred` append and the `FEATURE_DEFERRED` event are
    unchanged), only the backlog mapping differs. See the first Risks entry.
    **Do not pass `recoverable_branch`** and do not include the key in the `features_deferred`
    dict — `map_results._map_results_to_state` reads it with `entry.get("recoverable_branch")`
    (`map_results.py:117`), so its absence leaves `fs.recoverable_branch` `None`, which is what
    keeps `_count_built_merge_blocked_home_repo` (`runner.py:2063-2075`) from counting the feature
    as progress.
  - `"integration worktree unresolved"` must **not** be added to `_SYSTEMIC_ERROR_TYPES`
    (`constants.py:35-41`) — spec Edge Cases.
  - `ctx.worktree_branches` is populated at `orchestrator.py:344-347` from `create_worktree()`'s
    `info.branch`; it is absent for a feature whose worktree was never created, so `.get()` may
    legitimately return `None`.
  - **Inter-task contract** (Tasks 3 and 4 read this): the deferral event is `feature_deferred`
    with `details.unresolved_worktree is True`, `details.error == "integration worktree
    unresolved"`, and `details.branch` = the suffixed feature branch or `None`; the
    `features_deferred` entry carries `"error"` and no `"recoverable_branch"` key.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_outcome_router.py -q` exits
  0, with new tests asserting, for a home-repo feature whose integration worktree is deleted **and
  unrecoverable**: (a) **Req 7** — `ctx.batch_result.features_deferred` contains an entry with
  `error == "integration worktree unresolved"` and no `recoverable_branch` key,
  `ctx.batch_result.features_paused == []`, `ctx.cb_state.systemic_pauses_in_batch == 0`, and
  `ctx.cb_state.consecutive_pauses == 0`; (b) **Req 2** — driving the same feature through
  `apply_feature_result` produces no `features_failed` entry and no error string containing
  `"unexpected exception"`; (c) **Req 5** — a clean feature whose worktree was deleted and
  successfully re-created (real git fixture) reaches `"merged"`, and `grep -c "recoverable_branch
  = " cortex_command/overnight/outcome_router.py` == 1, pinning `:841` as the sole writer;
  (d) **scope decision** — a real `cortex/backlog/` item on disk, driven through the same
  unresolvable-worktree path, ends at `status: in_progress` and **not** `status: backlog`, so the
  item is not returned to the from-scratch-rebuild pool.
- **Status**: [x] done (01bef807 2026-08-07T11:37:57-04:00)

### Task 3: Carry the deferral error onto feature state

- **Files**:
  - `cortex_command/overnight/map_results.py`
  - `cortex_command/overnight/tests/test_map_results.py`
- **What**: `_map_results_to_state` sets `fs.error` for merged/paused/failed features but not for
  deferred ones, so Requirement 7's `"integration worktree unresolved"` would never reach
  `overnight-state.json` or the report. Read `error` off the deferred entry.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - `map_results.py:106-119` is the deferred loop. Add `fs.error = entry.get("error")` alongside
    the existing `fs.deferred_questions` / `fs.recoverable_branch` assignments. Question-deferral
    entries (`outcome_router.py:896-899`) carry no `error` key, so they get `None` — identical to
    today's default.
  - Behaviour note for the commit body: a feature that was `paused` with an error in an earlier
    round and is `deferred` in a later one now has its stale error cleared rather than retained.
    The `_TERMINAL_STATUSES` guard (`map_results.py:33`, `:112-113`) already prevents the reverse
    overwrite.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_map_results.py -q` exits 0,
  with a new test asserting that a `features_deferred` entry `{"name": "f", "question_count": 0,
  "error": "integration worktree unresolved"}` produces `state.features["f"].status ==
  "deferred"`, `.error == "integration worktree unresolved"`, and `.recoverable_branch is None`,
  while a question-deferral entry without an `error` key still yields `.error is None`.
- **Status**: [x] done (39d6c118 2026-08-07T11:41:44-04:00)

### Task 4: Morning report names the branch to verify instead of advising a re-run

- **Files**:
  - `cortex_command/overnight/report.py`
  - `cortex_command/overnight/tests/test_report.py`
- **What**: Add a `_suggest_next_step()` branch for the unresolved-worktree error, a new report
  section rendering both the rebuild count and the per-feature deferrals with their branch names,
  and first-ever coverage for the adjacent `render_built_merge_blocked` section. Satisfies spec
  Requirements 8, 11, and the reader half of 9.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - A feature deferred on an unresolved worktree reaches **no existing section**:
    `render_failed_features` (`report.py:1404-1410`) filters on `status in ("failed", "paused")`,
    `render_deferred_questions` (`:1232`) renders `data.deferrals` (question deferrals only), and
    `render_built_merge_blocked` (`:1598-1619`) filters on `recoverable_branch is not None`, which
    Task 2 deliberately leaves `None`. A new section is required.
  - `_suggest_next_step()` (`:2206-2219`): add, as the **first** branch, a case matching
    `"integration worktree unresolved"` returning text that directs verifying the named branch and
    explicitly does not advise a rebuild. It must not contain the substring `"retry or
    investigate"`. Its only pre-existing caller is `render_failed_features` (`report.py:1540`);
    the new branch is unreachable from there once Task 2 routes these features to `deferred`,
    which is why the new section below calls it too.
  - New `render_integration_worktree_loss(data: ReportData) -> str`, reading `data.events` in the
    idiom of `render_deferred_questions`' event scans (`:1249-1290`):
    - rebuilds — entries with `event == "integration_worktree_missing"` and
      `details.recreated is True` → one line naming the count;
    - deferrals — entries with `event == "feature_deferred"` and `details.unresolved_worktree is
      True` → one line per feature carrying `details.branch` (render an explicit "branch not
      recorded" when it is `None`) plus a suggestion line from `_suggest_next_step(details
      ["error"])`, so one function owns the advice text and the new `_suggest_next_step` branch is
      live rather than dead;
    - return `""` when both are empty.
  - Wire it into `generate_report()` (`:2711-2770`) with the conditional-append idiom used by the
    other omit-when-empty sections, placed immediately after `render_built_merge_blocked`.
  - `render_built_merge_blocked` coverage (spec Req 11) is a coverage requirement — the function
    is already correct and is **not** modified. Pin three behaviours: it names the branch when a
    feature carries `recoverable_branch`; it returns `""` (and its heading is absent from
    `generate_report`) when no feature carries one, with a Task-2-style unresolved-worktree
    deferral present so the two dispositions are pinned as distinct; and it returns `""` when
    `data.state is None` (`:1610-1611`).
  - The event-detail keys are the inter-task contracts declared in Tasks 1 and 2.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_report.py -q` exits 0 and
  `grep -rl "render_built_merge_blocked" cortex_command/overnight/tests/` returns a path (returns
  nothing at HEAD). The Req 8/9 tests must be **producer-driven** — build the events log by
  driving the real `outcome_router` paths from Tasks 1 and 2 (deleted worktree, recoverable and
  unrecoverable), then load that log into `ReportData` and call `generate_report`. Hand-written
  event dicts are not acceptable: they green the reader against a contract the producer may not
  emit. Assert (a) **Req 8** — the rendered section contains the feature's `pipeline/*` branch
  name and `"retry or investigate"` does not appear in that section; (b) **Req 9** — for a session
  whose worktree was re-created, the report contains the rebuild line with its count.
- **Status**: [x] done (4a6f3c23 2026-08-07T11:44:27-04:00)

### Task 5: PR gating pinned for the recovered and deferred session shapes

- **Files**: `cortex_command/overnight/tests/test_runner_pr_gating.py`
- **What**: Add two named tests asserting the `[ZERO PROGRESS]` title prefix is **absent** for a
  session that re-created its worktree and merged, and **present** for a session whose every
  feature deferred on `"integration worktree unresolved"`. Satisfies spec Requirement 12.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - The file is 99 lines and already carries the exact idiom: `_make_recoverable_state()` +
    `_run_post_loop(tmp_path, commit_count)` driving `runner._post_loop` in `dry_run` with
    `subprocess.run`, `ipc`, and `_integration_commit_count` patched, asserting on captured stdout
    (`:30-99`). Add a state builder per case rather than generalising the existing one.
  - The gate is `mc_merged_count = _count_merged_home_repo(state)` + `mc_recoverable_count =
    _count_built_merge_blocked_home_repo(state)` (`runner.py:2263-2265`). A deferred-on-unresolved
    feature carries `recoverable_branch=None`, so it counts as neither → `[ZERO PROGRESS]` is
    correct and intended. The recovered session has `status="merged"` features → prefix absent.
  - This is verification of existing behaviour, not a behaviour change: no `runner.py` edit.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_runner_pr_gating.py -q`
  exits 0 with the two new tests present, and `grep -c "ZERO PROGRESS"
  cortex_command/overnight/tests/test_runner_pr_gating.py` ≥ 3.
- **Status**: [x] done (927e41a1 2026-08-07T11:41:10-04:00)

### Task 6: Multi-round backlog write-back survives the loss

- **Files**: `cortex_command/overnight/tests/test_orchestrator.py`
- **What**: A ≥2-round test asserting that after in-place re-creation `_write_back_to_backlog`
  succeeds and no `BACKLOG_WRITE_FAILED` event is emitted in either round. Satisfies spec
  Requirement 6.
- **Depends on**: [2] (write-serialization: cortex_command/overnight/tests/test_orchestrator.py)
- **Complexity**: simple
- **Context**:
  - The reversion this test exists to prevent: `outcome_router._backlog_dir` is a module-level
    global (`outcome_router.py:369`) re-set from `overnight_state.worktree_path` at the **start of
    every** `run_batch()` (`orchestrator.py:275-277`). Any re-pointing to a path other than
    `state.worktree_path` would be silently overwritten at the round boundary — which a
    single-round fixture cannot detect. Task 1's in-place re-creation is what makes this hold.
  - `Path.glob` on a deleted directory returns empty without raising, so the failure mode is
    `_find_backlog_item_path` → `None` → `FileNotFoundError` inside `_write_back_to_backlog` → a
    swallowed `BACKLOG_WRITE_FAILED` event (`outcome_router.py:511-554`). Assert on the **absence
    of that event**, not on an exception.
  - `TestOrchestratorRunBatch` (`test_orchestrator.py:40-...`, patch helper at `:112`) already
    patches every `run_batch` dependency and awaits it; call `run_batch(self._config)` twice
    against the same state file, with a real on-disk home repo + integration worktree (the
    fixture builder at `test_outcome_router.py:1489-1520` is the reference) and a
    `cortex/backlog/` item inside the worktree. Delete the worktree before round 1.
  - Task 1 also edits this file; the declared edge is ordering-only.
- **Verification**: `uv run pytest cortex_command/overnight/tests/test_orchestrator.py -q` exits
  0; the new test asserts `[e for e in events if e["event"] == "backlog_write_failed"] == []`
  across both rounds and that the backlog item's `status` field was updated on disk.
- **Status**: [x] done (700a6c76 2026-08-07T11:47:53-04:00)

### Task 7: Document mid-session integration worktree loss

- **Files**: `cortex/requirements/pipeline.md`
- **What**: Add an `## Edge Cases` entry covering mid-session loss — the gap `pipeline.md:183`
  leaves open by scoping only to "TMPDIR cleared **between sessions**". Satisfies spec
  Requirement 10.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Insert immediately after the existing `- **TMPDIR cleared between sessions**: …` bullet
    (`cortex/requirements/pipeline.md:183`). The new bullet states: the home-repo integration
    worktree is re-created **in place** at `state.worktree_path` on next access; when re-creation
    fails the feature is `deferred` with `integration worktree unresolved` and **no**
    `recoverable_branch`, so it neither auto-retries nor feeds the systemic breaker; the morning
    report names the branch to verify rather than advising a re-run. Cite
    `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md` as the precedent for the
    genuine-fault vs infrastructure-fault split — the spec's Proposed ADR section says cite, do
    not duplicate into a new ADR.
  - **Do not touch** lines 40 or 70 (the ratified `recoverable_branch` definition) — the design
    commitment leaves them accurate.
- **Verification**: `grep -c "mid-session" cortex/requirements/pipeline.md` ≥ 1 (0 at HEAD) and
  `grep -c "genuine merge conflict" cortex/requirements/pipeline.md` == 2 (unchanged from HEAD).
- **Status**: [x] done (c79a37a5 2026-08-07T11:41:03-04:00)

## Risks

- **The `deferred → backlog` write-back re-queues the item for a future session.** Requirement 7
  forbids setting `recoverable_branch`, and `_write_back_to_backlog` bypasses the
  `_OVERNIGHT_TO_BACKLOG` mapping **only** when that field is truthy (`outcome_router.py:511-512`,
  `:527-532`). So an unresolved-worktree deferral writes the backlog item back to `status:
  backlog` — returning it to the from-scratch-rebuild pool. That is the exact harm Requirement 7
  names, displaced by one session rather than eliminated. The plan implements the spec literally.
  The alternative, entirely within Requirement 7's letter (it constrains `recoverable_branch` and
  the runtime disposition, not the backlog mapping), is to write `status: in_progress` — the
  `paused` mapping — which keeps the item out of the pool without claiming recoverability.
  **RESOLVED at approval (2026-08-07): take the alternative — Task 2 passes `"paused"` to
  `_write_back_to_backlog` so the item lands at `status: in_progress`.** Writing `backlog` would
  reproduce the harm this feature exists to fix and would contradict Task 4's report advice to
  verify the named branch. The runtime disposition remains `deferred`.
- **Requirement 1's acceptance criterion is unstable as literally written.** It asserts
  `_merge_target_repo_path(ctx, name) is None` for a deleted directory, but Requirement 4 makes
  the resolver *re-create* in that situation — so the criterion can only hold for the sub-case
  where re-creation is impossible. Task 1's verification pins it that way (no
  `integration_branches` entry). Flagging because read literally the criterion would pass after
  spec Phase 1 and then fail after spec Phase 2 — it measures the wrong thing rather than
  indicating a defect.
- **Task 1 is a five-file task.** It carries the resolver refactor, the context field, the loss
  signal, and the traceback fix. They are grouped because all four are spec Phase 1 and three of
  them edit the same two modules, so splitting them buys only serialization edges — but it is the
  largest single unit here and the most likely place for in-flight scope discovery.
- **Task 6 is the heaviest test in the plan.** A ≥2-round `run_batch` against a real on-disk repo
  and worktree is materially more fixture than the rest of the suite carries. It is the only shape
  that can detect the round-boundary `set_backlog_dir` reversion (the spec says so explicitly), so
  it stays — but expect it to be where in-flight time goes.
- **Not in scope, per the spec's Non-Requirements**: relocating the worktree off `$TMPDIR`, the
  ADR-0005 `resolve_worktree_root()` centralization, widening the ratified `recoverable_branch`
  definition, persisting `ctx.integration_worktrees`, and diagnosing what deletes the directory.

## Acceptance

An overnight session whose home integration worktree is deleted mid-run re-creates it in place at
`state.worktree_path`, merges its clean features (`status: "merged"`, so `merged_delta > 0` and
the stall breaker does not trip), writes back to the backlog across round boundaries without a
`BACKLOG_WRITE_FAILED`, and marks `integration_degraded: true`. When re-creation fails instead,
every affected feature is `deferred` with `"integration worktree unresolved"`, no feature is
`failed`, `features_paused` is empty, and the morning report names each feature's `pipeline/*`
branch to verify rather than advising a retry. `just test` exits 0.
