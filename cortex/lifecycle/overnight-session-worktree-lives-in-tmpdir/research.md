# Research: Make an overnight session survive its integration worktree disappearing

Rebuild the integration worktree from the surviving branch, and when work is committed but
unmergeable, report it as recoverable rather than as feature failure.

**Scope note.** Relocating the worktree off `$TMPDIR` and the ADR-0005
`resolve_worktree_root()` centralization are **out of scope**, deferred to a successor
ticket. The cause of the deletion is unknown after two incidents, so a placement fix cannot
be shown to work; this ticket makes the runner survive the loss whatever causes it.

## Incident evidence

Session `overnight-2026-08-07-0252` (wild-light). Reconstructed from
`cortex/lifecycle/sessions/overnight-2026-08-07-0252/` in the **wild-light** repo (the
ticket's Touch-points cite this path without a repo qualifier; it does not exist in
cortex-command).

| Time (EDT) | Event |
|---|---|
| Aug 6 22:52:14 | Bootstrap — `overnight-plan.md`, `session.json` written; `git worktree add` runs (`plan.py:409`) |
| Aug 7 01:52:03 | launchd starts the runner (`launchd-stdout.log`) |
| Aug 7 02:13:22 | `integration_worktree_missing` × 3 — already gone, *before* the first `feature_start` (02:13:25) |
| Aug 7 03:15:46 | `feature_failed` × 2, raw `FileNotFoundError`; `backlog_write_failed` × 2 |
| Aug 7 03:26:23 | `integration_worktree_missing` × 4 (round 2) |
| Aug 7 03:48:24 | `circuit_breaker` `reason: stall`, `stall_count: 2` → session ends |

Final state: 2 `failed`, 1 `deferred`, **3 never dispatched** (still `pending`).
`integration_degraded: False` — the session reported healthy integration while having lost it.

**The ticket's stated cause is not supported.** The Why reasons over a 01:52–03:48 window and
attributes the loss to macOS `$TMPDIR` purge. But exposure begins at **22:52** (bootstrap), a
3h21m window, and the directory was gone before the runner did any feature work. There has been
**no reboot since Jul 15**; `$TMPDIR/T/` still holds ~32,400 entries and
`$TMPDIR/overnight-worktrees/` itself survived — so no blanket purge occurred. One specific
directory vanished.

`cortex/debug/2026-04-01-wild-light-overnight-crash.md` records the **identical failure** four
months earlier in the same repo, with the same bootstrap→launch gap (12:50 → 13:37), and is
closed as *"Escalated — deletion cause unresolved"*, rating periodic purge *"unusual within 47
min"*. It also already named the fix: *"The runner has no guard for a missing worktree."* The
ticket does not cite it. **Cause remains unknown; the operator confirmed no knowledge of a
sweeper.**

**The harm is larger than the ticket states.** The misclassification cascaded: 0 merges in round
1 → 0 merges in round 2 → stall breaker → 3 features never attempted. A single infrastructure
fault consumed the whole session, not just two features' reporting.

## Codebase

### The fault's origin

`orchestrator.py:503-507` catches everything escaping `_run_one` via
`asyncio.gather(..., return_exceptions=True)` and keeps only `str(exc)` —
`error=f"unexpected exception: {exc}"`. **The traceback is discarded**, so "the merge is what
failed" was an inference from the path inside the error string, not evidence.

Most likely raiser: **`cortex_command/pipeline/merge.py:279-284`**,
`subprocess.run(["git","checkout",base_branch], cwd=repo, ...)` — Python raises
`FileNotFoundError` before git runs when `cwd` does not exist. Called unguarded (no
`try`/`except`) from `outcome_router.py:1904` inside `apply_feature_result()`, with
`repo_path=merge_target` from `_merge_target_repo_path(ctx, name)` (`:1881`).

Other `cwd=`-bearing candidates in the same worktree, reachable later:
`merge.py:296-301`, `:331-336`, `:350-355`; `outcome_router.py:605-615`, `:1490-1510`,
`:1804-1808`; `review_dispatch.py:493,545`; `merge_recovery.py:91,106,240`.
`_get_changed_files` (`outcome_router.py:286-304`) does **not** pass `cwd=` — it runs in the
process CWD and is therefore safe even with the worktree missing.

### The asymmetry (the actual gap)

```python
def _merge_target_repo_path(ctx, name):          # outcome_router.py:261-278
    if ctx.repo_path_map.get(name) is None:
        return ctx.home_worktree_path            # returned UNCHECKED
    return _effective_merge_repo_path(...)
```

`_effective_merge_repo_path()` (`outcome_router.py:128-258`) **already implements** the
recovery the ticket floats as "worth considering": `.exists()` check on the cached path, then
`git worktree add <path> <branch>`, with handlers for `"already exists"` and
`"already checked out at"` — the latter commented *"Stale git tracking — branch registered to a
now-deleted path after TMPDIR was cleared. Prune and retry once."* It is gated by
`if repo_path is None: return None` (`:169-170`), so **only cross-repo features reach it**.

wild-light's session had `integration_worktrees: {}` and every feature `repo_path: None` — all
six took the unchecked branch.

`_merge_target_repo_path` has 5 call sites (`:581, :715, :1465, :1881, :2291`), each already
paired with an `is None` guard, so fixing inside the function covers all five with **no
call-site changes**. This beats a per-site check, which would either duplicate the logic five
times or reproduce the same asymmetry.

**The branch name is already available for the home repo.** `plan.py:416` seeds
`integration_branches = {project_root: integration_branch_name}`, persisted at `:526` and
loaded at `orchestrator.py:273`. Verified on the incident state:
`{'/Users/charliehall/Workspaces/wild-light': 'overnight/overnight-2026-08-07-0252'}`. The
missing plumbing is only passing the home repo root as `repo_path` rather than short-circuiting
on `None`.

### Proving "the work exists"

No new state is needed — the same evidence the conflict path already uses:

- `ctx.worktree_branches.get(name)` — the suffix-correct branch (e.g. `pipeline/<name>-2`),
  populated from `create_worktree()`'s `info.branch` at `orchestrator.py:344-347`.
- `_get_changed_files(feature, base_branch, branch=actual_branch)`
  (`outcome_router.py:286-304`) — `git diff --name-only <base>...<branch>`, already called at
  `:685` and `:1869`, and **worktree-independent** (no `cwd=`).
- `OvernightFeatureStatus.recoverable_branch` (`state.py:113`) already exists.

### The recoverable disposition to mirror

`outcome_router.py:828-875` (`_apply_feature_result`, the `elif merge_result.conflict:` branch):

```python
recoverable_branch = actual_branch or None      # never a bare f"pipeline/{name}"
ctx.batch_result.features_deferred.append(
    {"name": name, "question_count": 0, "recoverable_branch": recoverable_branch})
overnight_log_event(FEATURE_DEFERRED, ..., details={..., "recoverable_branch": ...})
_write_back_to_backlog(name, "deferred", ..., recoverable_branch=recoverable_branch)
```

- **Circuit breaker excluded, confirmed in code**: never appends to `features_paused`, never
  increments `systemic_pauses_in_batch`. Both threshold sites (`:978-994`, `:2463-2479`) read
  only `features_paused`. Pinned by `test_merge_conflict_recoverable`.
- **Backlog write-back**: with `recoverable_branch` truthy, `_write_back_to_backlog`
  (`:488-554`) bypasses the `deferred → backlog` mapping and writes `status: in_progress` plus
  the branch (`:527-532`).
- **Persistence**: `map_results.py:_map_results_to_state` copies the dict key onto
  `OvernightFeatureStatus.recoverable_branch` — free for any new caller populating the same key.

**Load-bearing invariant a new caller breaks.** The branch's own comment (`:836-839`):

> *"Safe without a has-commits assertion **only while** this terminus stays gated on
> `conflict=True`: an empty `pipeline/<name>-N` branch merges cleanly (`conflict=False`) and
> never reaches here."*

A worktree-missing caller is **not** gated on `conflict=True`, so it **must** add an explicit
has-commits assertion — otherwise the report claims "your work is recoverable on this branch"
for an empty branch.

### Inert existing detection

`runner.py:869-887` already checks `worktree_path.is_dir()`, emits
`events.INTEGRATION_WORKTREE_MISSING`, and then **`continue`s**. Nothing consumes the event:
`grep` finds **no reference in `report.py` or `status.py`**. It fired 7 times during the
incident and reached no human surface.

### Test surface

- `cortex_command/overnight/tests/test_outcome_router.py` — `TestMergeConflictRecoverableRouting`
  (`:1321-1461`: `test_merge_conflict_recoverable`, `test_non_conflict_still_paused`,
  `test_recoverable_branch_suffix`, `test_recoverable_branch_absent`,
  `test_recoverable_not_redispatched`); `TestRecoverableWriteBack` (`:1271-1318`);
  `TestHomeMergeWorktreeCollision` (`:1463-1693`, real second-worktree fixture) — **only covers
  the worktree-exists case**. `TestSystemicThreshold` (`:493-673`).
- `tests/test_feature_executor.py` — `TestCrossRepoIntegrationBasePath` covers the cached-hit
  and `repo_path=None` branches, **not** the lazy-creation branches.
- **`render_built_merge_blocked` has zero test coverage anywhere in the repo.** The report
  section this fix depends on is untested today.

### Alternatives weighed

- **(A) Existence check + lazy re-create inside `_merge_target_repo_path`** — reuses
  `_effective_merge_repo_path`'s established idiom, one chokepoint, covers all 5 call sites,
  produces a resolved `Path` directly. **Recommended.**
- **(B) Catch at the raise site** — wrap the `cwd=repo` calls in
  `except (FileNotFoundError, NotADirectoryError)` → `MergeResult(conflict=False,
  error="integration_worktree_missing")`. Purely reactive: never re-creates, and lands in the
  generic non-conflict `paused` branch (`:876-894`) which **does** feed the systemic breaker —
  the opposite of intent — unless special-cased. Must be applied at 6+ files' call sites.
- **(C) Session-level preflight at `run_batch()` start (`orchestrator.py:243`)** — cheap, one
  check plus one `git worktree add`, benefits the whole batch, uses state already loaded at
  `:271-277`. Does **not** cover mid-session deletion. **Complements (A), does not replace it.**

(A) is the durable choice; (C) is a cheap addition worth considering in the spec.

## Requirements & Constraints

**Feature status vocabulary** (`pipeline.md:37-40`): `pending → running → merged`;
`→ paused` (recoverable, auto-retries); `→ deferred` (awaiting human decision, no auto-retry);
`→ failed` (unrecoverable). The recoverable sub-case: *"A `deferred` feature with a
`recoverable_branch` field set is the built-but-merge-blocked recoverable sub-case: its work is
built and recoverable on that branch (**a genuine merge conflict exhausted repair**) ... surfaced
positively (not as failed/zero-progress)."*

**"Merge target vanished" does not fit the ratified definition as written.** Every instance
qualifies the sub-case as *a genuine merge conflict* that *exhausted repair* —
`pipeline.md:40`, `pipeline.md:70`, and three code docstrings (`report.py:1601`,
`report.py:1624`, `outcome_router.py:505`). `pipeline.md:70` routes the other case oppositely:
*"non-conflict / systemic merge failures remain `paused` and feed the systemic circuit
breaker."* Under current wording a vanished worktree reads as **`paused`**. Routing it to
recoverable therefore requires **widening a ratified definition** in the requirements doc and
the three docstrings — a definitional change, not only a code change.

**`pipeline.md:183` already covers the adjacent case**: *"TMPDIR cleared **between sessions**:
Stale integration worktree paths are re-created on next access; git tracking is pruned and
retried."* That is exactly `_effective_merge_repo_path`'s behavior, scoped to between-sessions.
**Mid-session loss is the uncovered gap** — and it is the incident.

**ADR gate** (`cortex/adr/README.md`, all three criteria required): (1) hard to reverse — weak
no; (2) surprising without context — yes; (3) result of a real trade-off — open, depends on
whether the spec records a genuinely rejected alternative. Verdict: **likely no ADR**, leaning
to a requirements-wording update plus code. If one is written, it cites **ADR-0015** as
precedent — 0015 split one failure class into two along the same *genuine fault vs.
infrastructure fault* axis, preserving work in the infra-fault branch and feeding the breaker
under a distinct cause class.

**Enforcement gate** (`project.md:41`, *"a pre-commit/CI gate survives only by naming the
specific, evidenced failure it prevents"*): both incidents are runtime/environmental, not source
patterns a static gate could detect. **No new gate is warranted**; regression tests are ordinary
coverage under *Quality bar*.

**Deletion bias / front-door bar** (`project.md:23`): *"a ticket adding harness machinery names
its specific evidence in its Why (measured cost or observed failure, not a hypothetical)."*
#465 clears it as filed — named session, quantified loss, exact file:line. The spec must carry
the same discipline, and should now also cite the stall cascade and the 2026-04-01 precedent.

**Backlog #002** (*morning report — surface failure root cause inline*): `status: complete`,
closed 2026-04-06, spec archived at
`cortex/lifecycle/archive/morning-report-surface-failure-root-cause-inline/spec.md`. **Overlap,
not conflict** — #002 built the inline-classification mechanism; this work adds a correctly
classified cause into it.

## Adversarial

*The dispatched adversarial agent did not deliver after two chases (a known failure mode in
this harness). This section was produced by the orchestrator against the same brief and is
narrower than a dedicated pass would be — see `## Open Questions` for what it could not settle.*

**Re-creation restores the checkout but not everything the worktree held.**
`orchestrator.py:277` sets `outcome_router.set_backlog_dir(Path(worktree_path) / "cortex" /
"backlog")` — the backlog directory the runner writes to lives **inside** the vanished worktree.
That is the source of the incident's `backlog_write_failed` events (*"Backlog item not found for
feature ... (backlog_uuid=...)"*). A lazy re-create that only returns a `Path` for the merge
leaves `set_backlog_dir` pointing at the dead directory, so backlog status write-backs keep
failing silently after merges are restored. **The spec must re-point it.**

**What is lost vs. preserved.** The branch ref survives, so everything *committed* to
`overnight/<session_id>` survives. Uncommitted worktree content does not. Per `pipeline.md:23`,
artifact commits (lifecycle files, backlog status updates, session data) land on the integration
branch — committed, therefore recoverable. The residual risk is content staged-but-uncommitted
at the moment of deletion, which the rebuild silently drops without reporting a gap.

**Fixing classification alone would not have saved the session.** The stall breaker
(`runner.py:3464-3476`) keys **only** on `merged_delta`:

```python
if merged_delta <= 0:
    stall_count += 1
    if stall_count >= 2:  ... break
```

A `deferred` + `recoverable_branch` feature is not progress. Correct classification alone still
yields 0 merges per round, still trips the breaker at 2, still strands the remaining features.
**This establishes the ordering: re-creation is the primary fix** (rebuild → merges succeed →
`merged_delta > 0` → no stall); honest classification is the **fallback for when re-creation
itself fails**. A spec that ships only the classification half fixes the reporting and leaves
the throughput loss intact.

**Widening `recoverable_branch` interacts with resume.** `test_recoverable_not_redispatched`
pins that a recoverable feature is not re-dispatched on session resume. For a vanished-worktree
feature that is *correct* (don't rebuild finished work) but incomplete — the work still needs a
merge, and nothing performs it. That is precisely what happened: recovery required a manual
branch audit and hand-merge (wild-light PR #30). Classification alone converts a misleading
report into an accurate report of manual work still owed.

**Self-healing risks hiding the cause.** The directory keeps vanishing and the cause is
unknown after two incidents. If the runner silently rebuilds, the operator loses the only signal
that something is deleting their worktrees. `INTEGRATION_WORKTREE_MISSING` already exists but
reaches no human surface. `OvernightState.integration_degraded` (`state.py:269`) is the existing
mechanism for flagging a degraded integration outcome, and was `False` on the incident. The spec
should surface successful recovery in the morning report — a recovered session must not look
identical to a clean one.

## Open Questions

- **What actually deletes the directory?** Unresolved across two incidents (2026-04-01 and
  2026-08-07); the operator confirms no known sweeper. *Deferred* — this ticket is deliberately
  cause-independent, and the placement successor ticket inherits the question. It must not block
  this spec.
- **Is `merge.py:279-284` confirmed as the raiser?** Reasoned from code paths, not from a
  traceback (`orchestrator.py:507` discards it). *Deferred to implementation* — the fix covers
  every `cwd=`-bearing site through the one chokepoint regardless of which raised first, so the
  answer does not change the design. Worth capturing the traceback as part of the fix.
- **Should the has-commits assertion compare against the base ref or against `HEAD` of the
  integration branch?** `_get_changed_files` uses `git diff --name-only <base>...<branch>`.
  The failure modes in each direction (false-positive "work is safe" on a branch sitting at
  base; false-negative on a branch whose commits were already partially merged) were not
  characterised. *Deferred to Spec* — this is an acceptance-criterion decision about what the
  report is allowed to claim, not a fact code-reading settles, and it is the highest-risk open
  item: answered wrong it produces a false "your work is safe".
- **Does a successful re-create fully restore the session, or do later steps still fail on the
  original worktree's absence?** Post-merge review dispatch (`review_dispatch.py:493,545`) and
  test recovery (`merge_recovery.py`) also `cwd` into the target; whether they receive the
  re-created path was not traced. *Deferred to Spec* — it sets the scope boundary (whether the
  fix is one chokepoint or also the review/recovery paths), which is a scoping decision rather
  than a research finding.
- **Does widening `recoverable_branch` break any reader that relies on merge-conflict
  semantics?** `report.py:414`, `:523`, `:1598`, `status.py`, and PR-gating
  (`test_runner_pr_gating.py`) were enumerated but not each individually audited. *Deferred to
  Spec* — enumeration is complete, so the audit is per-criterion verification work that belongs
  with the acceptance criteria. Priority reader: the PR-gating path, since a zero-merge session
  opens a draft PR titled `[ZERO PROGRESS]` (`pipeline.md:26`) and a recovered session must not.
- **Contradiction between angles, resolved:** the Codebase angle reported that the home repo has
  no entry in `integration_branches` and would need one synthesized. That is **wrong** —
  `plan.py:416` seeds it, and the incident state confirms
  `{'…/wild-light': 'overnight/overnight-2026-08-07-0252'}`. Recorded here because it would have
  inflated the spec's plumbing estimate.
