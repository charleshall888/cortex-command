# Review: overnight-session-worktree-lives-in-tmpdir (cycle 1)

**Criticality**: high · **Tier**: complex · **Baseline**: `just test` 8/8 suites, exit 0 (not re-run).

**Requirements-loading note.** `cortex-load-requirements` printed `no area docs matched for tags: []`
and loaded only `cortex/requirements/project.md` and `cortex/requirements/glossary.md`. The
governing area doc for this feature is **`cortex/requirements/pipeline.md`** — it owns the overnight
execution framework and Task 7 edited it. It was **not auto-loaded**; the lifecycle index carries
empty tags and the ticket's `areas: ['overnight-runner', 'report']` match no file under
`cortex/requirements/`. It was read manually and drift is assessed against it below.

## Stage 1 — Spec Compliance

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

### The deliberate deviation (Task 2 passes `"paused"` to `_write_back_to_backlog`)

Checked against the code, not the rationale. The claim holds:

- **Runtime disposition unchanged.** `features_deferred` append (`:684`), `FEATURE_DEFERRED` event (`:689`), no `recoverable_branch` key, `"integration worktree unresolved"` absent from `_SYSTEMIC_ERROR_TYPES`, `deferred` excluded from `_count_pending`. Verified at each site.
- **The `"paused"` argument reaches exactly one thing.** `_write_back_to_backlog` (`:615`) looks the string up in `_OVERNIGHT_TO_BACKLOG` (`:488-505`) and writes `{"status": "in_progress", "session_id": None}` into the **backlog markdown file**. It appends to no result list, emits no `FEATURE_PAUSED`, and touches no circuit-breaker counter. Its only failure event is `BACKLOG_WRITE_FAILED`.
- **Requirement 7 does not constrain the backlog file.** Read literally, Req 7 constrains the disposition (`deferred`), `_count_pending` exclusion, `features_paused` exclusion, and the absence of `recoverable_branch`. All four hold. The backlog `status:` field appears nowhere in it.

So this **satisfies** Requirement 7 rather than violating it, and it is the better choice on the merits: `deferred → backlog` would put a finished-but-unmerged item back in the from-scratch-rebuild pool while the morning report tells the operator to verify and merge its branch — two surfaces giving contradictory advice about the same item. Pinned by `test_outcome_router.py:2130 test_deferred_item_stays_out_of_the_rebuild_pool`, which drives a real on-disk backlog item and asserts `^status: in_progress$` present and `^status: backlog$` absent.

The one cost: the backlog item's `status: in_progress` is now reachable from two causes with different meanings (a genuine recoverable pause, and an infrastructure deferral). Nothing downstream distinguishes them. That is a documentation gap, logged under drift below, not a defect.

### Acceptance criteria that could not fail

Checked every criterion against the unmodified repo. One is a pass-at-HEAD criterion, and it is deliberate:

- **Req 5's `grep -c "recoverable_branch = " == 1`** passes on the unmodified repo (HEAD also has exactly one writer). It is an *absence* assertion — a regression pin that keeps a second writer from being added — which the repo's testing policy explicitly permits, and the spec framed it that way ("`grep` shows no new writer"). Req 5's other half (`test_recreated_worktree_still_merges`) does fail at HEAD, so the requirement as a whole is not vacuous.

Everything else genuinely fails or errors at HEAD: Req 1 (HEAD returns a `Path`), Req 2/5/7 (the `OSError` escapes), Req 3/4/6 (the code paths do not exist), Req 8/9-reader (no section, no `_suggest_next_step` branch), Req 10 (`grep -c "mid-session"` == 0), Req 11 (`grep -rl` returns nothing), Req 12 (no such test). No report-only greps, no unscoped globs, no pre-existing patterns being re-asserted.

### The five guard sites

All five converted, verified individually against the diff:

| Site | Function | Condition kept | `return` kept | Lock |
|---|---|---|---|---|
| `:741` | `_apply_feature_result` (checkout arm) | ✔ | ✔ | caller-held |
| `:859` | `_apply_feature_result` (merge arm) | ✔ | ✔ | caller-held |
| `:1595` | `_repair_completed_review_gate` | ✔ | ✔ | caller-held |
| `:1995` | `apply_feature_result` (async merge) | ✔ | ✔ | held from `apply_feature_result` |
| `:2391` | `apply_feature_result` (recovery precheck) | ✔ | ✔ | **`async with ctx.lock:` wrapper retained** around the helper call |

No site lost its `if ctx.repo_path_map.get(name) is None and <var> is None:` guard, its explanatory comment (each updated from "Pause and surface" to "Defer and surface"), or its `return`. The site running outside `ctx.lock` still acquires it. No unlocked fast path was added.

## Stage 2 — Code Quality

**`_ensure_worktree` extraction.** Cache-first ordering at the `"already exists"` arm is preserved correctly: the caller passes `on_exists_fallback=Path(integration_worktrees[key]) if integration_worktrees.get(key) else None` (`:299-304`), reproducing the original truthiness test, and the helper returns the fallback when set, else `worktree_path` if it exists, else raises — the same three-way order as the old `:210-219`. `_effective_merge_repo_path`'s signature is unchanged and its `None` short-circuit, cached hit, `integration_branches` `RuntimeError`, `-lazy-` construction, and both `logger.warning` calls all stay where they were.

One real behavioural difference the plan's "must not change" wording does not cover: the cache write moved from inside the helper to the caller as `if resolved == worktree_path: integration_worktrees[key] = str(worktree_path)` (`:305-306`). In the old code the `"already exists"` arm never wrote the cache; now, when there is no cached entry and `worktree_path` exists on disk, the caller records it. The recorded path is real and correct, and the effect is one fewer `git worktree add` subprocess on the next call — benign, arguably an improvement, but it *is* a cross-repo behaviour change and worth naming since the plan pinned that boundary explicitly.

**Task 1's added `"already registered"` handling is load-bearing, not a scope leak.** I probed real git (2.55.0) on a deleted-then-re-added worktree:

```
same path:      fatal: '<path>' is a missing but already registered worktree;
                use 'add -f' to override, or 'prune' or 'remove' to clear
different path: fatal: '<branch>' is already used by worktree at '<path>'
```

In-place re-creation — the whole point of Requirement 4 — hits the *first* message, which matches neither pre-existing literal. Without the added `or "already registered" in stderr` clause the resolver would fall through to the unknown-failure `RuntimeError` and Req 4 would not work at all. The implementer discovered a wrong premise in the spec's Edge Cases ("reports `already checked out at`") and fixed it. Correct call.

Two comments now make false statements about that same mechanism, and both should be corrected:

- `test_outcome_router.py:1804` docstring: *"`git worktree add`, which fails with 'already checked out at' against the stale tracking the deletion left behind"* — it fails with `missing but already registered`. The test passes, but its stated reason for passing is wrong.
- `outcome_router.py:186-190` comment: *"the branch is 'already checked out at' the dead path when we ask for a different path"* — on git 2.55 that case says `is already used by worktree at`. Both halves of the sentence name wordings git does not emit. This also implies the **pre-existing** `"already checked out at"` literal may be dead on current git; that is not this feature's regression, but a human should decide whether to widen or drop it.

**`sorted(deferrals)` can raise on a tie.** `report.py:1690` sorts `(feature, branch, error)` tuples where `branch` may be `None`. Two deferral events for the same feature across rounds with different branch-nullness (round 1 recorded a branch, round 2 never created a worktree) compare element 2 as `None < str` → `TypeError`, crashing `generate_report`. Identical tuples are safe (equality short-circuits). Low probability, cheap fix: `sorted(deferrals, key=lambda d: (d[0], d[1] or ""))`.

**Plan verification steps were executed.** Every one is present and matches what the plan named — including the two greps (`recoverable_branch = ` count, `ZERO PROGRESS` count ≥ 3), the producer-driven constraint on the Req 8/9 report tests (hand-written event dicts were explicitly forbidden and are not used for those two), and the ≥2-round shape for Req 6. The Task 6 test goes beyond the plan by defeating `conftest.py`'s `update_item` stub, without which the on-disk assertion would have been vacuous — a good catch by the implementer.

**Naming and pattern consistency.** `_defer_unresolved_worktree` mirrors the conflict terminus's shape; `render_integration_worktree_loss` follows `render_deferred_questions`' event-scan idiom (including its lack of session filtering, which is the established pattern here); the `try/except Exception: pass` around the loss event and the state write matches the existing best-effort idiom at `:2372-2376`; `map_results.py:124` sits alongside the adjacent `recoverable_branch` line with a parallel comment. The `_HOME_WORKTREE_STUB` fixture change in `test_lead_unit.py` / `test_outcome_router.py` is a necessary consequence of the resolver now stat-ing the path, and is documented at both sites.

## Requirements Drift

**State**: `detected`

**Findings**:
- **The backlog-file disposition for an infrastructure deferral is undocumented.** `pipeline.md`'s new bullet (`:184`) covers the runtime disposition but not that the *backlog item* is written `status: in_progress`. `### Feature Execution and Failure Handling` states `deferred` features "do not auto-retry" and enumerates three deferral sources, none of which is infrastructure loss; and `status: in_progress` is now reachable from two causes with different meanings (recoverable pause vs. infrastructure deferral) with nothing distinguishing them. This is the operator-visible half of the approval-time scope decision and the requirements capture none of it.
- **`integration_degraded` is now set at runtime from the merge-target resolver.** Previously it had exactly one producer (the preserved-could-not-run path). A second, unrelated producer now writes it, which changes what the flag means for the integration-PR warning that reads it. Not documented anywhere.
- **`FEATURE_EXCEPTION` / `feature_exception` is a new event type carrying formatted tracebacks.** New vocabulary in `EVENT_TYPES` with a new observability guarantee (an escaped feature-coroutine exception is now diagnosable from the log alone). Neither `pipeline.md` nor `glossary.md` records it.

Assessed against `project.md` and `glossary.md` as well: no drift there. The feature is squarely deletion-bias-compatible (it collapses five duplicated guard bodies into one helper and adds no new disposition), and the solution-horizon clause is satisfied — the chokepoint fix is the durable version, with relocation off `$TMPDIR` correctly deferred to a named successor.

**Update needed**: `cortex/requirements/pipeline.md`

## Suggested Requirements Update

**File**: `cortex/requirements/pipeline.md`
**Section**: `### Feature Execution and Failure Handling`
**Content** (append to the `- **Acceptance criteria**:` list, after the `recoverable_branch` sub-case bullet):

```
  - A `deferred` feature carrying `error: "integration worktree unresolved"` is the infrastructure sub-case: the integration worktree was lost mid-session and could not be re-created, so the merge never ran. It carries no `recoverable_branch` (nothing was verified mergeable) and is excluded from the systemic breaker. Its backlog item is written `status: in_progress`, not `status: backlog` — the work is finished on the feature branch, and returning the item to the rebuild pool would discard it
```

**File**: `cortex/requirements/pipeline.md`
**Section**: `## Edge Cases`
**Content** (append after the existing `- **TMPDIR cleared mid-session**: …` bullet):

```
- **Mid-session worktree loss is recorded, not silent**: detection sets `integration_degraded: true` in `overnight-state.json` regardless of whether re-creation succeeded, and the morning report reports the rebuild count — so a session that self-healed is still distinguishable from a clean one
- **An exception escaping a feature coroutine keeps its traceback**: the runner emits a `feature_exception` event carrying the formatted traceback before recording the feature as `failed`, whose `error` field holds only `str(exc)`
```

## Operator Override (2026-08-07)

The reviewer's own verdict was **APPROVED**; its Stage 1 and Stage 2 findings below are unmodified.
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

The verdict block below is set to the operator's routing so the file and `events.log` agree.
The reviewer's issues 1, 2 and 4 are carried forward unresolved for the cycle-2 read.

## Verdict

```
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Spec Req 9 is half-unpinned: integration_degraded is set at outcome_router.py:374-380 and verified working by live probe, but no test asserts it, and the write sits inside a bare `except Exception: pass` so a regression there would be silent to the suite", "Two comments state a git error wording that git 2.55 does not emit: test_outcome_router.py:1804's docstring claims 'already checked out at' for the in-place case (real wording: 'missing but already registered'), and outcome_router.py:186-190 claims 'already checked out at' for the different-path case (real wording: 'is already used by worktree at'). The tests pass; only the stated reasons are wrong. This also implies the pre-existing 'already checked out at' literal may be dead on current git", "report.py:1690 sorts (feature, branch, error) tuples where branch may be None; two deferrals for the same feature with differing branch-nullness raise TypeError and crash generate_report. Fix: key=lambda d: (d[0], d[1] or '')", "_ensure_worktree's caller now writes integration_worktrees on the 'already exists' arm where the original did not (outcome_router.py:305-306) — benign and arguably better, but the plan pinned cross-repo behaviour as unchanged"], "requirements_drift": "detected"}
```
