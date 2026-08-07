# Review: overnight-session-worktree-lives-in-tmpdir

**Criticality**: high · **Tier**: complex · **Baseline**: `just test` 8/8 suites, exit 0 (not re-run;
taken after the rework commit). Targeted: `test_report.py` 50 passed.

Cycle 1 rated 11 PASS / 1 PARTIAL / 0 FAIL and returned APPROVED with four issues; the operator
overrode to CHANGES_REQUESTED on issue 3 only. One rework commit (`b1f3c677`) fixed exactly that.
The full cycle-1 record is preserved below.

---

## Cycle 2 — Rework Verification (`b1f3c677`)

**Scope.** `git show --stat` confirms exactly two files: `cortex_command/overnight/report.py` (+4/-1)
and `cortex_command/overnight/tests/test_report.py` (+36). Nothing outside the two named files
changed, and the working tree carries no uncommitted source edits (`git status` shows only `cortex/`
documents).

**The fix is the narrow one requested.** `report.py:1690` changed from `sorted(deferrals)` to
`ordered = sorted(deferrals, key=lambda d: (d[0], d[1] or "", d[2]))` plus a two-line comment naming
why. No restructuring: the loop body, the `location` ternary, the `_suggest_next_step` call and the
trailing blank-line idiom are byte-identical.

**The crash is gone, and I reproduced it rather than reading for it.** I extracted
`b1f3c677~1:cortex_command/overnight/report.py` to a scratch module, loaded it, and called
`render_integration_worktree_loss` with the new test's exact `ReportData`:

```
PRE-FIX RAISES TypeError: '<' not supported between instances of 'NoneType' and 'str'
frame: report_prefix.py 1690  for feature, branch, error in sorted(deferrals):
```

Post-fix, `pytest -k worktree_loss` is 5 passed. So the new test is non-vacuous at the exact line the
operator named.

**Rendered output is unchanged for every previously-working input — verified exhaustively, not
argued.** I enumerated every 2- and 3-element multiset over the domain
`feature ∈ {a,b} × branch ∈ {None,"","x","y"} × error ∈ {e1,e2}` and compared pre-fix `sorted()`
against the post-fix keyed sort on every input where pre-fix did not raise:

```
pairs+triples: ok=2576  mismatch=0  pre-fix-crashed=1776
```

Zero reorderings. The reason it holds in general: pre-fix, tuple comparison only reaches element 2
when element 1 is equal, and it only survives that comparison when both branches are `None` (equal,
falls through to element 3) or both are `str`. `d[1] or ""` maps the both-`None` case to
`("", "")` — still equal, still falling through to `d[2]`, which the key also carries — and leaves
any non-empty `str` untouched. The only inputs the coercion could reorder are `None`-vs-`str` and
`""`-vs-`None` pairs, and both of those raised `TypeError` pre-fix, so no working render depended on
them. Stability is likewise preserved: a post-fix key collision implies pre-fix tuple equality except
in the `None`/`""` case, which pre-fix crashed on.

`d[2]` is not coerced, so a `None` error would still raise. That is not reachable from the producer:
`_defer_unresolved_worktree` (`outcome_router.py:674`) writes the literal
`"integration worktree unresolved"` into both the result dict and the event details, and the reader
uses `details.get("error", "")`. Worth naming, not worth widening the key for.

**The hand-built-events concession was reasonable.** The property under test is sort stability over
event *details*, and the producer cannot be driven into it: `data.events` comes from
`read_events(events_path)` where the default path is the per-session log symlink, so both deferrals
must land in one session; `worktree_branches.get(name)` returns the same value for a given feature
within a session, and `deferred` is excluded from `_count_pending` so the feature is not
re-dispatched. Reachability therefore remains narrow — it needs a resumed session whose
`worktree_branches` was repopulated between two deferrals of one feature — which is exactly why a
producer-driven fixture could not pin it. The four producer-driven fixtures immediately above it
(`test_report.py:1467, 1499, 1588, 1621`) still own the contract, and the new test's docstring says
so explicitly. Correct call; the rework brief's carve-out was used as intended and not widened.

**One test-quality note (not blocking).** `test_worktree_loss_sorts_mixed_branch_nullness` asserts
that both deferrals render; it does not assert their *order*, despite the docstring's "must still
order". Since the pre-fix failure is a raise rather than a mis-order, the test is non-vacuous as
written, and the exhaustive check above covers ordering better than an assertion would. No change
needed.

**No new drift from the rework.** A sort-key change with no observable output delta introduces no new
vocabulary, event, state field, or disposition.

## Cycle 2 — Carried-Forward Issues

### Issue 1 — `integration_degraded` is unpinned (Req 9 PARTIAL): **still open, not blocking**

`grep -rn integration_degraded` across `cortex_command/` returns the producer
(`outcome_router.py:377`), the consumer (`runner.py:2277, 2362`), the dataclass, and nothing in any
test. `tests/test_runner_pr_gating.py` exercises the flag only *fixture-driven* (it copies
`state-nonzero-merge-degraded.json` and hand-writes the warning file), so it pins the consumer, not
this feature's producer. Cycle 1's rating stands.

What lowers the stakes, and is worth recording because cycle 1's drift finding overstated it: the
new producer is currently **inert at its only consumer**. `runner.py:2362` gates on
`integration_degraded and warning_file.exists()`, and `warning_file` has exactly one writer —
`runner.py:2346`, inside `if preserved_could_not_run:`, the same condition that independently sets
`integration_degraded` at `:2277`. So a purge-only session that sets the flag changes no PR body, no
title, and no draft state. The flag's value here is the recorded fact in `overnight-state.json`,
which is what spec Req 9 asks for, and which I confirmed by live probe in cycle 1.

So a silent regression in the `except Exception: pass` block would lose a state-file record, not a
behaviour. **Follow-up ticket, not a cycle-2 block**: add a producer-driven assertion that
`load_state(...).integration_degraded is True` after a purge, in the same test that already drives
the real resolver against a real purged worktree (`test_outcome_router.py:1804` is the natural host —
it already has the state file on disk).

### Issue 2 — false git wordings, and the dead literal: **comments still wrong; the dead literal is real and pre-existing**

I probed git 2.55.0 directly on a scratch repo, all four collision shapes:

| Shape | git 2.55 stderr |
|---|---|
| branch live in another worktree, ask for a different path | `fatal: 'feat' is already used by worktree at '<path>'` |
| branch checked out in the main repo, ask for a worktree | `fatal: 'master' is already used by worktree at '<path>'` |
| worktree dir deleted (stale), ask for a **different** path | `fatal: 'feat' is already used by worktree at '<dead path>'` |
| worktree dir deleted (stale), ask for the **same** path back | `fatal: '<path>' is a missing but already registered worktree; use 'add -f' …` |

Three findings:

1. **The two comments are still wrong** and were untouched by the rework.
   `test_outcome_router.py:1810`'s docstring and `outcome_router.py:198-200`'s comment both name
   `"already checked out at"`, which git 2.55 emits in none of the four shapes. Documentation-grade;
   the tests pass and the code is correct.
2. **`"already checked out at"` is dead on git 2.55** — provably, across every shape I could
   construct. It is **pre-existing**: `git show dac36ef8~1` shows the guard was
   `if "already checked out at" in stderr:` alone before this feature. This feature *added*
   `or "already registered" in stderr`, which is what makes the in-place case (Req 4) work at all.
   The feature strictly widened coverage; it did not create the dead literal.
3. **The different-path stale case matches neither literal**, so that arm does not fire.
   `"is already used by worktree at"` contains neither `"already checked out at"` nor
   `"already registered"`, so a cross-repo lazy re-creation whose branch is still registered to a
   deleted path falls through to the unknown-failure `RuntimeError` instead of prune-and-retry. This
   is also pre-existing (the old single literal missed it identically), and this feature's home path
   is unaffected because it asks for the same path back. Behaviour is unchanged from HEAD, so it is
   not a regression this cycle can charge — but it is a live gap a human should close.

**Follow-up ticket**, one line of work: replace both literals with the actually-emitted substrings
(`"already used by worktree at"` and `"already registered"`), fix the two comments, and pin the
widened guard with a real-git test. Not a ship blocker — the arm was equally dead before this
feature.

### Issue 4 — the `"already exists"` arm now writes `integration_worktrees`: **not-a-defect**

Reachability first. `outcome_router.py:305-306` writes only when `resolved == worktree_path`. Against
`dac36ef8~1`, the old code already wrote the cache on both success arms (`git show dac36ef8~1`, the
`returncode == 0` arm and the retry-after-prune arm), so the *only* new write is: `"already exists"`
**and** no cached entry **and** `worktree_path.exists()`. That requires the state map to have lost an
entry for a path git already has registered. The cached-entry sub-case still returns
`on_exists_fallback` (a different `Path`), so it still does not write — the old ordering is intact.

Observable effect, traced through every consumer of `integration_worktrees`
(`runner.py:825`, `runner.py:1552 → sandbox_settings.build_orchestrator_deny_paths`, `plan.py`,
`orchestrator.py:277`, `feature_executor.py:668`; no consumer deletes or prunes worktrees from this
map):

- `runner.py:825` now resolves the plan-commit worktree for that repo instead of returning `None`.
- `build_orchestrator_deny_paths` emits four more git-state-mutation **deny** paths for that repo key
  — strictly more restrictive, and identical to what the success arm would have produced.
- One fewer `git worktree add` subprocess on the next call.

The recorded path is real, exists on disk, and is session-namespaced (`{session_id}-lazy-{repo}`), so
it cannot name another session's worktree. Every effect is a correction of a state map that was blind
to a worktree the session was actively merging into. It is a behaviour *change* in the strict sense
the plan's "unchanged" wording pinned, so cycle 1 was right to name it — but it is not observable as
a different outcome for any feature. **Not a defect; nothing to do.**

## Cycle 1 Record (preserved)

**Requirements-loading note.** `cortex-load-requirements` printed `no area docs matched for tags: []`
and loaded only `cortex/requirements/project.md` and `cortex/requirements/glossary.md`. The
governing area doc for this feature is **`cortex/requirements/pipeline.md`** — it owns the overnight
execution framework and Task 7 edited it. It was **not auto-loaded**; the lifecycle index carries
empty tags and the ticket's `areas: ['overnight-runner', 'report']` match no file under
`cortex/requirements/`. It was read manually and drift is assessed against it below. (Cycle 2: still
true, and still out of scope for this ticket.)

### Stage 1 — Spec Compliance (cycle 1)

| # | Requirement | Rating | Justification |
|---|---|---|---|
| 1 | `_merge_target_repo_path()` returns `None` for a missing home worktree | **PASS** | `outcome_router.py:339-370` — returns `home_worktree` when it is `None` or `.exists()`, otherwise attempts re-creation and returns `resolved` (`None` on failure). Pinned by `test_outcome_router.py:1915 test_missing_home_worktree_without_branch_returns_none`, which pins the *no-`integration_branches`-entry* sub-case. That resolves the plan's "unstable criterion" flag coherently: with Req 4 in force, `is None` is only reachable when re-creation is impossible, and the test constructs exactly that. Fails at HEAD (HEAD returned `ctx.home_worktree_path` unchecked). |
| 2 | No feature reaches `failed` because its merge target was missing | **PASS** | All five guards route to `_defer_unresolved_worktree` (`outcome_router.py:741, 859, 1595, 1995, 2391`), so the resolver never hands `merge_feature` a dead `cwd` and `orchestrator.py:503-507` is no longer the terminus. `test_outcome_router.py:2055 test_unrecoverable_worktree_is_not_a_failure` asserts empty `features_failed` and no `"unexpected exception"` substring. Non-vacuous: at HEAD the `OSError` escapes `apply_feature_result`, so the test errors. |
| 3 | Traceback preserved for unexpected exceptions | **PASS** | `orchestrator.py:513-530` emits `FEATURE_EXCEPTION` with `"".join(traceback.format_exception(...))` inside `try/except Exception: pass` before building `failed_result`; `error=f"unexpected exception: {exc}"` left intact as the plan required. `events.py` adds the constant and the `EVENT_TYPES` member (both needed — `log_event` raises on an unlisted type). Pinned by `test_orchestrator.py:254 test_escaped_exception_logs_traceback`, asserting the named raising frame `_raise_unique_feature_fault` appears in the logged traceback. |
| 4 | Home-repo lazy re-creation, **in place** at `state.worktree_path` | **PASS** | `outcome_router.py:352` calls `_ensure_worktree(ctx.home_repo_path, home_worktree, branch)` with the recorded path verbatim — no `-lazy-` construction, and no write into `ctx.integration_worktrees`. Branch resolved via `_normalize_repo_key` with a raw-`str` fallback (`:346-348`), which matters: `plan.py:415-416` seeds `integration_branches` with an **un-normalized** `str(repo_root)` key. `home_repo_path` is populated at both `OutcomeContext(...)` sites (`orchestrator.py:458, 571`) from `overnight_state.project_root` with `_resolve_user_project_root()` fallback. Pinned by `test_outcome_router.py:1804`. **Independently verified**: I ran a standalone probe against a real git repo — the purged worktree came back at exactly `state.worktree_path`, `git rev-parse --abbrev-ref HEAD` == `overnight/<session_id>`, no `-lazy-` component. |
| 5 | Merge proceeds through the unmodified existing path | **PASS** | `test_outcome_router.py:1854 test_recreated_worktree_still_merges` drives the real merge after a purge and asserts `features_merged`, empty `features_deferred`/`features_paused`, and the observable git effect (the feature SHA is in the re-created worktree's `rev-list HEAD`). Fails at HEAD. The conflict terminus at `:828-875` is untouched; `grep -c "recoverable_branch = " outcome_router.py` == 1, pinned by `test_outcome_router.py:2088`. |
| 6 | Backlog write-back and plan mirroring survive the loss | **PASS** | `test_orchestrator.py:780 test_backlog_write_back_survives_purge_across_rounds` — two real `run_batch` calls against one on-disk state file, a real git home repo + integration worktree, a real committed backlog item, and the **genuine** `update_item` loaded from file to defeat `conftest.py`'s no-op stub (`_real_update_item`, `:721`). Asserts no `backlog_write_failed` across both rounds, that the degraded path actually ran (`len(missing) == 1`, `recreated is True`), that the re-created worktree is at `str(worktree)` on `base_branch`, both rounds merged, and `status: complete` landed on disk. This is the strongest test in the batch and it forecloses the round-boundary `set_backlog_dir` reversion the requirement exists to prevent. |
| 7 | Re-creation failure → `deferred`, not `paused`, not `failed` | **PASS** | `_defer_unresolved_worktree` (`outcome_router.py:660-703`): appends to `features_deferred` with `error` and **no** `recoverable_branch` key, emits `FEATURE_DEFERRED`, and does **not** append to `features_paused` or bump `cb_state.consecutive_pauses`. `"integration worktree unresolved"` is absent from `_SYSTEMIC_ERROR_TYPES` (`constants.py:35-41`, unmodified). `deferred` is excluded from `_count_pending` (`runner.py:504-510`, unmodified), so the feature is not re-dispatched. Pinned by `test_outcome_router.py:1981` (all five assertions: deferred entry, no `recoverable_branch` key, empty `features_paused`, `consecutive_pauses == 0`, `systemic_pauses_in_batch == 0`, no `feature_paused` event) and `:2029` for the sync `repair_completed` site. **The operator deviation is compliant — see below.** |
| 8 | Report stops advising a re-run and names the branch | **PASS** | `_suggest_next_step` gains a **first** branch matching `"integration worktree unresolved"` (`report.py:2278-2288`) returning verify-the-branch text with no `"retry or investigate"` substring; `render_integration_worktree_loss` (`report.py:1639-1706`) renders the per-feature deferral with `details.branch` and calls `_suggest_next_step` so the new branch is live rather than dead; wired into `generate_report` at `:2817` with the omit-when-empty idiom. Test at `test_report.py:1467` is **producer-driven** as the plan demanded — it drives the real `outcome_router` against a real purged git worktree and reads back the log the producer actually wrote, then asserts the `pipeline/*` branch is present and `"retry or investigate"` absent. |
| 9 | Lost-and-rebuilt session distinguishable from a clean one | **PARTIAL** | Both halves are implemented and both work. Reader: `render_integration_worktree_loss` counts `integration_worktree_missing` events with `details.recreated is True` and emits a rebuild line with a count — pinned producer-driven at `test_report.py:1499`. Producer: `integration_degraded = True` via the best-effort `load_state`/`save_state` idiom at `outcome_router.py:374-380`. **I verified by live probe that `integration_degraded` really lands as `True` in the state file.** But **no test asserts it** — the spec's criterion names it explicitly, and the write sits inside a bare `except Exception: pass`, so any future regression there is silent to the suite. Half the criterion is unpinned. |
| 10 | `pipeline.md` documents mid-session worktree loss | **PASS** | `cortex/requirements/pipeline.md:184` adds the mid-session bullet immediately after the between-sessions one, citing ADR-0015 as the precedent rather than duplicating it. `grep -c "mid-session"` == 1 (0 at HEAD); `grep -c "genuine merge conflict"` == 2 at both `dac36ef8~1` and HEAD (unchanged). Lines 40 and 70 untouched — the diff is a single added line. The three "genuine merge conflict" docstrings are unchanged (`report.py` still 2, `outcome_router.py` 0 — the spec's `outcome_router.py:505` citation was already stale at HEAD). |
| 11 | `render_built_merge_blocked()` gains test coverage | **PASS** | `grep -rl` now returns `cortex_command/overnight/tests/test_report.py`. Three behaviours pinned (`test_report.py:1571, 1588, 1621`): names the branch when `recoverable_branch` is set; returns `""` **and** its heading is absent from `generate_report` when an unresolved-worktree deferral is present instead (producer-driven, so the two dispositions are pinned as genuinely distinct); returns `""` when `data.state is None`. The function itself is not modified, as required. |
| 12 | PR gating verified for deferred and recovered cases | **PASS** | `test_runner_pr_gating.py:146` asserts `[ZERO PROGRESS]` **absent** for a recovered-and-merged session; `:156` asserts it **present** when every feature deferred on `"integration worktree unresolved"` with `recoverable_branch=None`. `_run_post_loop` was extended with an optional `state` parameter rather than the builder being generalised, matching the plan. `grep -c "ZERO PROGRESS"` == 8 (≥3). No `runner.py` edit, as the plan specified. |

**Tally: 11 PASS, 1 PARTIAL, 0 FAIL.**

#### The deliberate deviation (Task 2 passes `"paused"` to `_write_back_to_backlog`)

Checked against the code, not the rationale. The claim holds:

- **Runtime disposition unchanged.** `features_deferred` append (`:684`), `FEATURE_DEFERRED` event (`:689`), no `recoverable_branch` key, `"integration worktree unresolved"` absent from `_SYSTEMIC_ERROR_TYPES`, `deferred` excluded from `_count_pending`. Verified at each site.
- **The `"paused"` argument reaches exactly one thing.** `_write_back_to_backlog` (`:615`) looks the string up in `_OVERNIGHT_TO_BACKLOG` (`:488-505`) and writes `{"status": "in_progress", "session_id": None}` into the **backlog markdown file**. It appends to no result list, emits no `FEATURE_PAUSED`, and touches no circuit-breaker counter. Its only failure event is `BACKLOG_WRITE_FAILED`.
- **Requirement 7 does not constrain the backlog file.** Read literally, Req 7 constrains the disposition (`deferred`), `_count_pending` exclusion, `features_paused` exclusion, and the absence of `recoverable_branch`. All four hold. The backlog `status:` field appears nowhere in it.

So this **satisfies** Requirement 7 rather than violating it, and it is the better choice on the merits: `deferred → backlog` would put a finished-but-unmerged item back in the from-scratch-rebuild pool while the morning report tells the operator to verify and merge its branch — two surfaces giving contradictory advice about the same item. Pinned by `test_outcome_router.py:2130 test_deferred_item_stays_out_of_the_rebuild_pool`, which drives a real on-disk backlog item and asserts `^status: in_progress$` present and `^status: backlog$` absent.

The one cost: the backlog item's `status: in_progress` is now reachable from two causes with different meanings (a genuine recoverable pause, and an infrastructure deferral). Nothing downstream distinguishes them. That is a documentation gap, logged under drift below, not a defect.

#### Acceptance criteria that could not fail

Checked every criterion against the unmodified repo. One is a pass-at-HEAD criterion, and it is deliberate:

- **Req 5's `grep -c "recoverable_branch = " == 1`** passes on the unmodified repo (HEAD also has exactly one writer). It is an *absence* assertion — a regression pin that keeps a second writer from being added — which the repo's testing policy explicitly permits, and the spec framed it that way ("`grep` shows no new writer"). Req 5's other half (`test_recreated_worktree_still_merges`) does fail at HEAD, so the requirement as a whole is not vacuous.

Everything else genuinely fails or errors at HEAD: Req 1 (HEAD returns a `Path`), Req 2/5/7 (the `OSError` escapes), Req 3/4/6 (the code paths do not exist), Req 8/9-reader (no section, no `_suggest_next_step` branch), Req 10 (`grep -c "mid-session"` == 0), Req 11 (`grep -rl` returns nothing), Req 12 (no such test). No report-only greps, no unscoped globs, no pre-existing patterns being re-asserted.

#### The five guard sites

All five converted, verified individually against the diff:

| Site | Function | Condition kept | `return` kept | Lock |
|---|---|---|---|---|
| `:741` | `_apply_feature_result` (checkout arm) | ✔ | ✔ | caller-held |
| `:859` | `_apply_feature_result` (merge arm) | ✔ | ✔ | caller-held |
| `:1595` | `_repair_completed_review_gate` | ✔ | ✔ | caller-held |
| `:1995` | `apply_feature_result` (async merge) | ✔ | ✔ | held from `apply_feature_result` |
| `:2391` | `apply_feature_result` (recovery precheck) | ✔ | ✔ | **`async with ctx.lock:` wrapper retained** around the helper call |

No site lost its `if ctx.repo_path_map.get(name) is None and <var> is None:` guard, its explanatory comment (each updated from "Pause and surface" to "Defer and surface"), or its `return`. The site running outside `ctx.lock` still acquires it. No unlocked fast path was added.

### Stage 2 — Code Quality (cycle 1)

**`_ensure_worktree` extraction.** Cache-first ordering at the `"already exists"` arm is preserved correctly: the caller passes `on_exists_fallback=Path(integration_worktrees[key]) if integration_worktrees.get(key) else None` (`:299-304`), reproducing the original truthiness test, and the helper returns the fallback when set, else `worktree_path` if it exists, else raises — the same three-way order as the old `:210-219`. `_effective_merge_repo_path`'s signature is unchanged and its `None` short-circuit, cached hit, `integration_branches` `RuntimeError`, `-lazy-` construction, and both `logger.warning` calls all stay where they were.

One real behavioural difference the plan's "must not change" wording does not cover: the cache write moved from inside the helper to the caller as `if resolved == worktree_path: integration_worktrees[key] = str(worktree_path)` (`:305-306`). In the old code the `"already exists"` arm never wrote the cache; now, when there is no cached entry and `worktree_path` exists on disk, the caller records it. The recorded path is real and correct, and the effect is one fewer `git worktree add` subprocess on the next call — benign, arguably an improvement, but it *is* a cross-repo behaviour change and worth naming since the plan pinned that boundary explicitly. (Cycle 2 traced every consumer and rated this not-a-defect — see Issue 4 above.)

**Task 1's added `"already registered"` handling is load-bearing, not a scope leak.** I probed real git (2.55.0) on a deleted-then-re-added worktree:

```
same path:      fatal: '<path>' is a missing but already registered worktree;
                use 'add -f' to override, or 'prune' or 'remove' to clear
different path: fatal: '<branch>' is already used by worktree at '<path>'
```

In-place re-creation — the whole point of Requirement 4 — hits the *first* message, which matches neither pre-existing literal. Without the added `or "already registered" in stderr` clause the resolver would fall through to the unknown-failure `RuntimeError` and Req 4 would not work at all. The implementer discovered a wrong premise in the spec's Edge Cases ("reports `already checked out at`") and fixed it. Correct call.

Two comments now make false statements about that same mechanism, and both should be corrected:

- `test_outcome_router.py:1804` docstring: *"`git worktree add`, which fails with 'already checked out at' against the stale tracking the deletion left behind"* — it fails with `missing but already registered`. The test passes, but its stated reason for passing is wrong.
- `outcome_router.py:186-190` comment: *"the branch is 'already checked out at' the dead path when we ask for a different path"* — on git 2.55 that case says `is already used by worktree at`. Both halves of the sentence name wordings git does not emit. This also implies the **pre-existing** `"already checked out at"` literal may be dead on current git; that is not this feature's regression, but a human should decide whether to widen or drop it. (Cycle 2 confirmed the literal is dead and found the different-path arm unhandled — see Issue 2 above.)

**`sorted(deferrals)` can raise on a tie.** `report.py:1690` sorts `(feature, branch, error)` tuples where `branch` may be `None`. Two deferral events for the same feature across rounds with different branch-nullness (round 1 recorded a branch, round 2 never created a worktree) compare element 2 as `None < str` → `TypeError`, crashing `generate_report`. Identical tuples are safe (equality short-circuits). Low probability, cheap fix: `sorted(deferrals, key=lambda d: (d[0], d[1] or ""))`. **(Fixed in `b1f3c677`; verified cycle 2.)**

**Plan verification steps were executed.** Every one is present and matches what the plan named — including the two greps (`recoverable_branch = ` count, `ZERO PROGRESS` count ≥ 3), the producer-driven constraint on the Req 8/9 report tests (hand-written event dicts were explicitly forbidden and are not used for those two), and the ≥2-round shape for Req 6. The Task 6 test goes beyond the plan by defeating `conftest.py`'s `update_item` stub, without which the on-disk assertion would have been vacuous — a good catch by the implementer.

**Naming and pattern consistency.** `_defer_unresolved_worktree` mirrors the conflict terminus's shape; `render_integration_worktree_loss` follows `render_deferred_questions`' event-scan idiom (including its lack of session filtering, which is the established pattern here); the `try/except Exception: pass` around the loss event and the state write matches the existing best-effort idiom at `:2372-2376`; `map_results.py:124` sits alongside the adjacent `recoverable_branch` line with a parallel comment. The `_HOME_WORKTREE_STUB` fixture change in `test_lead_unit.py` / `test_outcome_router.py` is a necessary consequence of the resolver now stat-ing the path, and is documented at both sites.

### Requirements Drift (cycle 1 — applied in `1db892c3`)

State was `detected`. Findings, all three now applied to `cortex/requirements/pipeline.md`:

- **The backlog-file disposition for an infrastructure deferral is undocumented.** `pipeline.md`'s new bullet (`:184`) covers the runtime disposition but not that the *backlog item* is written `status: in_progress`. `### Feature Execution and Failure Handling` states `deferred` features "do not auto-retry" and enumerates three deferral sources, none of which is infrastructure loss; and `status: in_progress` is now reachable from two causes with different meanings (recoverable pause vs. infrastructure deferral) with nothing distinguishing them.
- **`integration_degraded` is now set at runtime from the merge-target resolver.** Previously it had exactly one producer (the preserved-could-not-run path). A second, unrelated producer now writes it, which changes what the flag means for the integration-PR warning that reads it. (Cycle 2 correction: it does **not** change the warning — see Issue 1.)
- **`FEATURE_EXCEPTION` / `feature_exception` is a new event type carrying formatted tracebacks.** New vocabulary in `EVENT_TYPES` with a new observability guarantee. Neither `pipeline.md` nor `glossary.md` recorded it.

Assessed against `project.md` and `glossary.md` as well: no drift there. The feature is squarely deletion-bias-compatible (it collapses five duplicated guard bodies into one helper and adds no new disposition), and the solution-horizon clause is satisfied — the chokepoint fix is the durable version, with relocation off `$TMPDIR` correctly deferred to a named successor.

### Operator Override (2026-08-07, cycle 1)

The reviewer's own verdict was **APPROVED**; its Stage 1 and Stage 2 findings above are unmodified.
The operator routed **CHANGES_REQUESTED** instead, on the reviewer's issue 3 — the
`sorted(deferrals)` `TypeError` in `render_integration_worktree_loss`. That crash was independently
reproduced by the orchestrator before the call:

```
TypeError: '<' not supported between instances of 'NoneType' and 'str'
```

Reachability is uncertain — `deferred` features are excluded from `_count_pending`, so it likely
needs two guard sites firing for one feature within a single round — but the failure mode is total
(`generate_report` raises, so the morning report this feature exists to improve produces nothing),
and the fix is one line. Cycle 1's rework arm was available, so it was used rather than deferring
the fix to a follow-up ticket.

Cycle 1's verdict of record was therefore **CHANGES_REQUESTED** with four issues (the
`integration_degraded` pin, the two false git wordings, the `sorted()` crash, and the
`integration_worktrees` write on the `"already exists"` arm) and `requirements_drift: detected`.
Issues 1, 2 and 4 were carried forward and are rated in the cycle-2 section above.

---

## Requirements Drift

**State**: `detected`

**Findings**:

The cycle-1 drift was applied in `1db892c3`. I verified all three bullets against the code:

- **Section placement is correct.** The infrastructure sub-case bullet is `pipeline.md:41`, inside
  `### Feature Execution and Failure Handling`'s `- **Acceptance criteria**:` list, immediately after
  the `recoverable_branch` sub-case bullet — exactly where cycle 1 asked. The two new Edge Cases
  bullets are `:186-187`, under `## Edge Cases` (heading at `:180`), immediately after the
  `**TMPDIR cleared mid-session**` bullet.
- **The infrastructure sub-case bullet (`:41`) is accurate.** No `recoverable_branch`: confirmed at
  `outcome_router.py:674-688` (the appended dict has `name`/`question_count`/`error` only). Excluded
  from the systemic breaker: `"integration worktree unresolved"` is absent from
  `_SYSTEMIC_ERROR_TYPES`. Backlog `status: in_progress`: confirmed via
  `_write_back_to_backlog(name, "paused", …)` → `_OVERNIGHT_TO_BACKLOG`.
- **The `integration_degraded` bullet (`:186`) is accurate but under-scoped.** "regardless of whether
  re-creation succeeded" is right — the `load_state`/`save_state` block at `outcome_router.py:374-380`
  sits outside the `if branch:` arm and runs whether `resolved` is a `Path` or `None`. What the
  sentence does not say is that only the **home** worktree path sets it; `_effective_merge_repo_path`
  (the cross-repo lazy path) never does. A reader of `## Edge Cases` would reasonably assume
  otherwise. Worth one clause.
- **The `feature_exception` bullet (`:187`) states something false.** It reads "…before recording the
  feature as `failed`, whose `error` field holds only `str(exc)`". The `FeatureResult` built at
  `orchestrator.py:533` sets `error=f"unexpected exception: {exc}"`, not bare `str(exc)`; it is the
  *event's* `details.error` that holds `str(exc)`. As written the relative clause attaches to the
  failed feature and misstates its error field. (The imprecision was inherited from the code comment
  at `orchestrator.py:511-512`, which says the same thing; that comment is a separate, cosmetic
  matter for the follow-up ticket.)

The rework commit `b1f3c677` introduces **no new drift**: a sort-key change with no output delta adds
no vocabulary, event, state field, or disposition. No drift against `project.md` or `glossary.md`.

**Update needed**: `cortex/requirements/pipeline.md` — two **corrections to lines applied in
`1db892c3`**, not appends.

## Suggested Requirements Update

**File**: `cortex/requirements/pipeline.md`
**Section**: `## Edge Cases`
**Content** — **replace** the existing line 186:

```
- **Mid-session worktree loss is recorded, not silent**: detection sets `integration_degraded: true` in `overnight-state.json` regardless of whether re-creation succeeded, and the morning report reports the rebuild count — so a session that self-healed is still distinguishable from a clean one
```

with:

```
- **Mid-session worktree loss is recorded, not silent**: detection on the *home* integration worktree sets `integration_degraded: true` in `overnight-state.json` regardless of whether re-creation succeeded (the cross-repo lazy path does not), and the morning report reports the rebuild count — so a session that self-healed is still distinguishable from a clean one
```

**File**: `cortex/requirements/pipeline.md`
**Section**: `## Edge Cases`
**Content** — **replace** the existing line 187:

```
- **An exception escaping a feature coroutine keeps its traceback**: the runner emits a `feature_exception` event carrying the formatted traceback before recording the feature as `failed`, whose `error` field holds only `str(exc)`
```

with:

```
- **An exception escaping a feature coroutine keeps its traceback**: the runner emits a `feature_exception` event carrying `str(exc)` and the formatted traceback, then records the feature as `failed` with `error: "unexpected exception: <exc>"` — the traceback lives on the event only, never on the feature result
```

## Verdict

Rework verified and correct; the three carried-forward issues are documentation- and
test-coverage-grade, with nothing that must not ship. At the cycle-2 cap, CHANGES_REQUESTED would
escalate rather than rework, and none of these warrants that. **All three belong in a follow-up
ticket**, which should cover: the `integration_degraded` producer assertion, the two false git
wordings plus the dead `"already checked out at"` literal and the unhandled
`"is already used by worktree at"` arm, and the two `pipeline.md` line corrections above.

```
{"verdict": "APPROVED", "cycle": 2, "issues": ["FOLLOW-UP: no test asserts the integration_degraded producer at outcome_router.py:377 (spec Req 9's producer half); the write sits in a bare `except Exception: pass`, so a regression is silent to the suite. Stakes are lower than cycle 1 judged: the flag is inert at its only consumer, since runner.py:2362 gates on `integration_degraded and warning_file.exists()` and the warning file's sole writer (runner.py:2346) runs only on the preserved-could-not-run path, which already sets the flag at :2277. A regression would lose a state-file record, not a behaviour", "FOLLOW-UP: `\"already checked out at\"` is dead on git 2.55 — probed all four collision shapes, none emit it. Pre-existing (the guard was that literal alone at dac36ef8~1); this feature widened it with `or \"already registered\"`, which is what makes in-place re-creation work. The residual gap: a stale registration asked for a *different* path emits `\"is already used by worktree at\"`, matching neither literal, so the prune-and-retry arm does not fire and the call falls to the unknown-failure RuntimeError. Same behaviour as HEAD, so not a regression. Fix alongside the two false-wording comments at test_outcome_router.py:1810 and outcome_router.py:198-200", "FOLLOW-UP: two lines applied to cortex/requirements/pipeline.md in 1db892c3 need correction — :187 states the failed feature's `error` field holds only `str(exc)` when orchestrator.py:533 writes `f\"unexpected exception: {exc}\"` (it is the event's details.error that holds str(exc)), and :186 does not say that only the home-worktree path sets integration_degraded. Exact replacement text is in this file's Suggested Requirements Update section", "NOT-A-DEFECT (closed): the `\"already exists\"` arm's new integration_worktrees write (outcome_router.py:305-306) changes no observable cross-repo outcome. Only reachable when the state map lost an entry for a path git already registered; the recorded path is real, on disk, and session-namespaced; traced through every consumer (runner.py:825 resolves instead of returning None, build_orchestrator_deny_paths emits four more *deny* paths, one fewer `git worktree add`) and no consumer deletes worktrees from this map"], "requirements_drift": "detected"}
```
