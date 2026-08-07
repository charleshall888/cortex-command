# Specification: overnight-session-worktree-lives-in-tmpdir

## Problem Statement

When an overnight session's integration worktree disappears mid-run, the runner reports
features that finished and committed their work as **failed**, and the morning report tells the
operator to retry them. In session `overnight-2026-08-07-0252` (wild-light) this stranded three
features' output on unmerged branches, then cascaded: two rounds merged nothing, the
zero-progress stall breaker tripped, and three further features were never dispatched. The
operator recovered by hand-auditing branches. The runner already contains the machinery to
survive this — lazy worktree re-creation, a conflict-gated recoverable-work disposition, and
five guards written for the "TMPDIR wiped" case — but none of it engages, because
`_merge_target_repo_path()` hands home-repo features a `Path` that no longer exists instead of
signalling that it is unresolvable. This fixes the engagement, not the machinery.

**Design commitment.** The fix makes the worktree available and then lets the existing
conflict-gated logic run **unmodified**. It does not add a parallel has-commits assertion, a new
disposition, or a widened definition of the recoverable category. The comment at
`cortex_command/overnight/outcome_router.py:836-839` states that the recoverable terminus is
*"Safe without a has-commits assertion **only while** this terminus stays gated on
`conflict=True`"* — driving the home case through a real merge attempt preserves that invariant
rather than reopening it, and is why Requirements 7–9 are as small as they are.

## Phases

- **Phase 1: Make the loss detectable** — `_merge_target_repo_path()` stops returning a
  non-existent path, so the five existing degraded-path guards fire.
- **Phase 2: Recover automatically** — extend the existing lazy re-creation to home-repo
  features, and re-point every other consumer of the stale path.
- **Phase 3: Report honestly** — when recovery fails, stop advising a re-run; keep the
  underlying deletion visible.

## Requirements

1. **`_merge_target_repo_path()` returns `None` for a home-repo feature whose integration
   worktree does not exist on disk.** Today it returns `ctx.home_worktree_path` unchecked
   (`cortex_command/overnight/outcome_router.py:271-272`), so the five call-site guards at
   `:581, :715, :1465, :1881, :2291` — each already written for the *"degraded path: TMPDIR
   wiped / resumed session"* case and each testing `merge_target is None` — cannot fire.
   **Acceptance**: a new test in `cortex_command/overnight/tests/test_outcome_router.py`
   builds an `OutcomeContext` whose `home_worktree_path` points at a deleted directory and
   asserts `_merge_target_repo_path(ctx, name) is None`. Fails at HEAD (returns a `Path`).
   **Phase**: Make the loss detectable

2. **No feature reaches `status: "failed"` because its merge target was missing.** The
   catch-all at `cortex_command/overnight/orchestrator.py:503-507` must no longer be the
   terminus for this fault. **Acceptance**: a test drives a home-repo feature through
   `apply_feature_result` with a deleted integration worktree and asserts the resulting status
   is not `"failed"` and no error string contains `"unexpected exception"`. Fails at HEAD
   (produces `failed` + `"unexpected exception: [Errno 2]"`). **Phase**: Make the loss
   detectable

3. **The traceback is preserved for unexpected exceptions.** `orchestrator.py:507` builds
   `error=f"unexpected exception: {exc}"`, discarding the traceback — which is why this
   incident's origin had to be inferred rather than read. **Acceptance**: a test raises a
   known exception inside a feature coroutine and asserts the originating frame appears in the
   events log or captured stderr. Fails at HEAD (no traceback is recorded anywhere).
   **Phase**: Make the loss detectable

4. **Home-repo features get lazy worktree re-creation, re-created IN PLACE at
   `state.worktree_path`.** `_effective_merge_repo_path()` (`outcome_router.py:128-258`)
   already performs `.exists()` → `git worktree add <path> <branch>` with `"already exists"`
   and `"already checked out at"` recovery, but is gated by `if repo_path is None: return None`
   (`:169-170`). The home repo's branch is already available — `plan.py:416` seeds
   `integration_branches = {project_root: integration_branch_name}`, persisted at `:526`,
   loaded at `orchestrator.py:273`; verified on the incident state as
   `{'…/wild-light': 'overnight/overnight-2026-08-07-0252'}`.

   **The home-repo path MUST NOT use the `-lazy-<repo_dir_name>` naming at
   `outcome_router.py:186-188`.** That builds
   `$TMPDIR/overnight-worktrees/<session_id>-lazy-<repo>`, which differs from the bootstrap
   path `$TMPDIR/overnight-worktrees/<session_id>` (`plan.py:380`) that
   `state.worktree_path` records. Re-creating at the divergent path would leave every other
   reader — `set_backlog_dir` (`orchestrator.py:276-277`),
   `runner._resolve_feature_integration_worktree` (`runner.py:806-830`) — still resolving the
   dead directory. Re-creating in place makes those readers correct with no re-pointing and
   nothing to persist.

   **Acceptance**: a test using a real git fixture deletes a home integration worktree, calls
   the resolver, and asserts (a) a worktree exists checked out on `overnight/<session_id>`,
   and (b) its path equals `state.worktree_path` exactly — no `-lazy-` component. Fails at
   HEAD (the resolver is never reached for home-repo features). **Phase**: Recover
   automatically

5. **After successful re-creation the merge proceeds through the unmodified existing path.**
   No new disposition branch. A clean feature reaches `status: "merged"`; a feature that then
   genuinely conflicts falls through to the existing `conflict=True` terminus at
   `outcome_router.py:828-875` unchanged. **Acceptance**: a test asserts a clean feature whose
   worktree was deleted and re-created reaches `"merged"`, and that the conflict terminus is
   entered only via `merge_result.conflict` — `grep` shows no new writer of
   `recoverable_branch` outside `:828-875`. Fails at HEAD (the feature reaches `failed`).
   **Phase**: Recover automatically

6. **Backlog write-back and plan-file mirroring survive the loss.** In-place re-creation
   (Requirement 4) is what makes this hold: `outcome_router._backlog_dir` is a module-level
   global (`:369`) re-set from `overnight_state.worktree_path` at the start of **every**
   `run_batch()` (`orchestrator.py:276-277`), so any re-pointing to a different path would be
   overwritten at each round boundary. `Path.glob` on a deleted directory returns empty
   **without raising**, so `_find_backlog_item_path` returns `None` and
   `_write_back_to_backlog` raises `FileNotFoundError("Backlog item not found for feature …")`
   (`:518-522`), logged as `BACKLOG_WRITE_FAILED` — exactly the incident's observed failure.
   `runner._resolve_feature_integration_worktree` (`runner.py:806-830`) reads
   `state.worktree_path` independently and is corrected by the same in-place property.
   **Acceptance**: a **multi-round** test (≥2 rounds, so the round-boundary re-set is
   exercised) asserts that after re-creation `_write_back_to_backlog` succeeds and no
   `BACKLOG_WRITE_FAILED` event is emitted in either round. A single-round fixture is
   insufficient — it cannot detect the reversion this requirement exists to prevent. Fails at
   HEAD. **Phase**: Recover automatically

7. **When re-creation fails, the feature is `deferred` — not `paused` and not `failed`.**
   `paused` is wrong: `_count_pending` (`runner.py:504-510`) counts `paused` alongside
   `pending`/`running`, so a paused feature is **re-dispatched next round**. For a feature
   whose work is already committed that re-runs finished work — the exact harm the ticket
   names (*"Following that advice would have meant re-running work that was already done"*),
   automated rather than merely advised. `deferred` is excluded from `_count_pending`, so it
   does not auto-retry, and it is not in `features_paused`, so it does not feed the systemic
   breaker. **No `recoverable_branch` is set** — without a completed merge attempt there is no
   `conflict=True` gate, and claiming recoverability unverified is the failure mode this spec
   exists to prevent; the deferral is honest that a human must decide whether to merge the
   branch or re-run. This changes the five guards' existing behaviour, which pause today.
   **Acceptance**: a test with re-creation forced to fail asserts the feature is `deferred`
   with error `"integration worktree unresolved"`, carries no `recoverable_branch`,
   `features_paused` is empty, `systemic_pauses_in_batch == 0`, and the feature is **not**
   re-dispatched in a following round. Fails at HEAD (the feature reaches `failed` with an
   `"unexpected exception"` error). **Phase**: Report honestly

8. **The morning report stops advising a re-run for this fault and names the branch to check.**
   `_suggest_next_step()` (`cortex_command/overnight/report.py:2206-2219`) falls through to
   `"Review learnings, retry or investigate"` for any unmatched error, which is what misled the
   operator. The new branch must not assert that work exists — it directs verification of the
   feature branch instead of a rebuild, because the alternative is the manual branch audit the
   ticket names as the incident's recovery cost. **Acceptance**: for a session with a feature
   deferred on `"integration worktree unresolved"`, `grep` the generated report and assert the
   string `"retry or investigate"` is absent for that feature and its `pipeline/*` branch name
   is present. Fails at HEAD (the fallback string is emitted). **Phase**: Report honestly

9. **A session that lost and rebuilt its worktree is distinguishable from a clean one.** The
   cause of the deletion is unknown across two incidents, so silent self-healing removes the
   last signal. `INTEGRATION_WORKTREE_MISSING` is emitted today (`runner.py:869-887`) and
   `grep` finds **no reader** in `report.py` or `status.py`; `integration_degraded`
   (`state.py:269`) was `False` on the incident despite total integration loss.
   **Acceptance**: for a session where the worktree was re-created, the morning report contains
   a line reporting the rebuild and a count, and `integration_degraded` is `True` in
   `overnight-state.json`. Fails at HEAD (no reader exists; `grep -c
   "INTEGRATION_WORKTREE_MISSING\|integration_worktree_missing" cortex_command/overnight/report.py`
   returns 0). **Phase**: Report honestly

10. **`cortex/requirements/pipeline.md` documents mid-session worktree loss.** Line 183 covers
    only *"TMPDIR cleared **between sessions**: Stale integration worktree paths are re-created
    on next access"*. Because this fix leaves the conflict-gated disposition unmodified, lines
    40 and 70 remain accurate and are **not** changed, and the three docstrings carrying
    "genuine merge conflict" (`report.py:1601`, `report.py:1624`, `outcome_router.py:505`) stay
    as they are. **Acceptance**: `grep -c "mid-session" cortex/requirements/pipeline.md`
    returns ≥1 (returns 0 at HEAD), and `grep -c "genuine merge conflict"
    cortex/requirements/pipeline.md` is unchanged from its HEAD value. **Phase**: Report
    honestly

11. **`render_built_merge_blocked()` gains test coverage.** It has zero coverage anywhere in
    the repo today (`grep -rl "render_built_merge_blocked" tests/ cortex_command/overnight/tests/`
    returns nothing), yet the reporting requirements depend on the section it renders. This is a
    coverage requirement: its criterion passes as soon as the test is written, because the
    function is already correct — the deliverable is the test's existence, not a behaviour
    change. **Acceptance**: `grep -rl "render_built_merge_blocked" cortex_command/overnight/tests/`
    returns a path (returns nothing at HEAD), and that test asserts the section names the branch
    when `recoverable_branch` is set and is omitted entirely when no feature carries one.
    **Phase**: Report honestly

12. **PR gating is verified against the deferred-and-recovered cases.** A zero-merge session
    opens a draft PR titled `[ZERO PROGRESS]` (`cortex/requirements/pipeline.md:26`). A session
    that recovered and merged is not zero-progress; a session deferred on unresolved worktrees
    is. **Acceptance**: a named test in
    `cortex_command/overnight/tests/test_runner_pr_gating.py` asserts the title prefix for both
    cases — present when every feature deferred on `"integration worktree unresolved"`, absent
    when re-creation succeeded and features merged.
    Fails at HEAD (no such test exists; the nearest, `test_recoverable_not_zero_progress:80`,
    covers only the merge-conflict case). **Phase**: Report honestly

## Non-Requirements

- **Relocating the integration worktree off `$TMPDIR`.** Deferred to a successor ticket. The
  cause of the deletion is unknown after two incidents, so relocation cannot be shown to prevent
  recurrence; this ticket is deliberately cause-independent.
- **ADR-0005 `resolve_worktree_root()` centralization.** Four inline
  `Path(os.environ.get("TMPDIR"))` sites (`plan.py:380`, `plan.py:444`, `runner.py:2218`,
  `outcome_router.py:186`) bypass the chokepoint the ADR designates. Real, and it belongs with
  the placement ticket — ADR-0005 already anticipates it: *"Cross-repo overnight worktrees
  (branch d) remain TMPDIR-based pending a separate follow-up."*
- **Widening the ratified `recoverable_branch` definition.** Deliberately avoided; see the
  design commitment above. `pipeline.md:40` and `:70` are unchanged.
- **Persisting `ctx.integration_worktrees` to state.** `save_state` never writes it and
  `run_batch()` reloads from disk each round, so lazy-creation results are discarded at round
  boundaries. Requirement 4's in-place re-creation makes this moot for the home repo — the path
  never changes, so there is nothing to persist. It remains a live gap for the **cross-repo**
  `-lazy-` path, which self-heals only because that path is deterministic; closing it properly
  is a separate concern.
- **Diagnosing what deletes the directory.** Unresolved across 2026-04-01 and 2026-08-07;
  Requirement 9 preserves the signal rather than chasing the cause.
- **Moving worktree creation from bootstrap to runner start.** Would shrink the 3-hour
  unattended exposure window, but successful re-creation makes the window moot.
- **Changing where demo worktrees live.** `gc_demo_worktrees.py:152-162` filters on a
  `demo-overnight-` prefix and cannot match a session worktree.
- **Recovering session `overnight-2026-08-07-0252`.** Already hand-merged (wild-light PR #30).

## Edge Cases

- **Re-creation succeeds, merge then conflicts** → falls through to the existing
  `conflict=True` terminus unchanged, with `recoverable_branch` set from
  `ctx.worktree_branches` as today. No new path.
- **Re-creation fails after prune-and-retry** → `deferred` with `"integration worktree
  unresolved"`; report names the branch to check without asserting work exists.
- **`git worktree add` fails for an environmental reason** (parent directory gone, permissions
  changed, the same unknown agent that deleted the directory still active) → the outcome is
  Requirement 7's honest deferral, not a crash. Nothing in this spec assumes re-creation
  succeeds; recovery is the fast path, deferral is the correct floor.
- **The dead worktree is still registered to the branch** → `git worktree add` at the same path
  reports `"already checked out at"`; the existing handler prunes and retries once. In-place
  re-creation means only one path is ever registered for `overnight/<session_id>`, avoiding the
  two-worktrees-one-branch collision a divergent path would create.
- **Worktree vanishes again between re-creation and merge** → the guards are re-entrant; a
  second loss behaves identically rather than crashing.
- **Branch registered to the deleted path** (`"already checked out at"`) → prune and retry
  once, per the existing handler.
- **Concurrent features recover simultaneously** → all five call sites already run under
  `ctx.lock` (`outcome_router.py:75`; `apply_feature_result` acquires it before `:1881`, and
  the sync sites are invoked from within that block). Re-creation MUST stay inside the lock —
  an unlocked fast path added to avoid holding the lock across a slow `git worktree add` would
  reintroduce a real race on the shared `integration_worktrees` dict.
- **Wall-clock cost** — because the lock serializes outcome routing across the whole batch,
  re-creation stalls all features for the duration of one `git worktree add`. Acceptable, once
  per loss event, but not free.
- **Resumed session whose worktree was cleaned between runs** → already covered by
  `pipeline.md:183`; the new path must not regress it.
- **Re-creation failure is not a systemic error type** — `"integration worktree unresolved"` is
  absent from `_SYSTEMIC_ERROR_TYPES` (`constants.py:35-41`), so repeated failures feed the
  batch-level consecutive-pauses breaker (`orchestrator.py:364-369`), not the round-stall
  breaker that fired in the incident. The operator therefore sees a differently-shaped failure
  on recurrence; Requirement 9's report line is what makes it legible.
- **A recoverable feature is not re-dispatched on resume**
  (`test_outcome_router.py:1444 test_recoverable_not_redispatched`). Correct — the work exists —
  but the merge is still owed manually, and the report must say so rather than implying
  completion.

## Changes to Existing Behavior

- **MODIFIED** `_merge_target_repo_path()` — returns `None` (or a re-created path) instead of a
  non-existent one for home-repo features.
- **MODIFIED** `_effective_merge_repo_path()` — accepts a home-repo target.
- **MODIFIED** `orchestrator.py:503-507` — preserves the traceback.
- **MODIFIED** the five degraded-path guards — `deferred` instead of `paused`, so a feature
  whose work is committed is not re-dispatched.
- **MODIFIED** `_suggest_next_step()` — new branch for the unresolved-worktree case.
- **UNCHANGED** `set_backlog_dir` and `runner._resolve_feature_integration_worktree` — in-place
  re-creation keeps `state.worktree_path` correct, so neither needs re-pointing.
- **ADDED** a reader for `INTEGRATION_WORKTREE_MISSING` in the morning report.
- **ADDED** `integration_degraded` set on worktree loss.
- **ADDED** `cortex/requirements/pipeline.md` line covering mid-session loss.
- **UNCHANGED** the conflict-gated disposition at `outcome_router.py:828-875`, the ratified
  definition at `pipeline.md:40`/`:70`, and the three "genuine merge conflict" docstrings.

## Technical Constraints

- **The five degraded-path guards already exist** and pause with `"integration worktree
  unresolved"` today. Requirement 1 activates them; Requirement 4 makes recovery the usual
  outcome; Requirement 7 changes their terminal disposition from `paused` to `deferred`.
- **`conflict=True` remains the sole gate on `recoverable_branch`.** No parallel has-commits
  assertion — `outcome_router.py:836-839` documents why.
- **Circuit-breaker exclusion must be preserved.** Both threshold sites (`:978-994`,
  `:2463-2479`) read only `features_paused`.
- **The stall breaker counts only `merged_delta`** (`runner.py:3389`, `:3464-3476`;
  `_count_merged` at `:513-515` counts `status == "merged"` only). Recovery prevents the
  incident's cascade by restoring merges for clean features; it does not and should not make a
  genuinely-conflicted feature count as progress. A batch of only-conflicted features still
  stalls, correctly.
- **`_write_back_to_backlog` writes `status: in_progress`** (not `backlog`) when
  `recoverable_branch` is truthy (`:527-532`).
- **Fixing at the one chokepoint, not the five call sites** — per-site checks would duplicate
  the logic five times or reproduce the asymmetry being fixed.
- **`_apply_feature_result` is reached twice on a conflict** (async `:1904`, then the sync
  fall-through at `:2251-2254`). A pre-existing quirk the new path must not compound.

## Open Decisions

- **Do cross-repo per-feature build worktrees nest inside the home integration worktree?**
  `resolve_worktree_root` (`cortex_command/pipeline/worktree.py:150-159`) places them at
  `$TMPDIR/overnight-worktrees/<session_id>/<feature>` — a subdirectory of the home integration
  worktree path (`plan.py:380`), not of the cross-repo integration worktree (a sibling,
  `plan.py:443-447`). If real, the same deletion would also destroy in-flight cross-repo builds,
  a failure surfacing in `execute_feature` and outside this fix's scope. Deferred because
  confirming it requires observing a real cross-repo session's on-disk layout, which no fixture
  reproduces. The incident was home-repo-only (`integration_worktrees: {}`), so it does not
  block this work.

## Proposed ADR

None considered. Per `cortex/adr/README.md`'s three-criteria gate, all three are required and
this meets neither reversibility nor trade-off: it extends an existing pattern to a sibling
branch and deliberately leaves the ratified disposition and its definition unchanged. ADR-0015
remains the nearest precedent for splitting a failure class along a *genuine fault vs.
infrastructure fault* axis, and should be cited in the `pipeline.md` edit rather than
duplicated into a new ADR.
