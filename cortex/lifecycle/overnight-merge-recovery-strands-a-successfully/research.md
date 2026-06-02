# Research: Stop the overnight merge-recovery layer from stranding a successfully-built feature (#281)

> **Headline finding (verified against the real session logs):** The ticket's framing is
> factually wrong in one load-bearing way — **no revert ever ran**. The merge failed at its
> *first* step because it executed in the **wrong git tree**. Both bug "stages" (the dirty-base
> precheck pause and the round-2 worktree/branch collision) are **one upstream defect**:
> home-repo features resolve their merge target to the home working tree instead of the
> integration worktree. Fixing that single resolution bug makes feature 025 actually merge —
> which means the **reporting / status-surfacing half of the ticket is a separable fallback for
> *genuine* merge-blocks (real conflicts), not for the 025 scenario.** See Open Questions.

> **File:line caveat:** Sub-agents read a mix of the working tree and a worktree copy; **line
> numbers below are approximate and must be re-confirmed at implementation time.** Module
> *locations* are verified: `merge.py`, `merge_recovery.py`, `worktree.py`, `conflict.py` live in
> `cortex_command/pipeline/`; `outcome_router.py`, `runner.py`, `report.py`, `plan.py`,
> `state.py`, `feature_executor.py`, `orchestrator.py`, `map_results.py`, `events.py`,
> `backlog.py` live in `cortex_command/overnight/`. Note there are **two** `state.py`
> (`pipeline/` and `overnight/`), each with its own `FEATURE_STATUSES`.

## Codebase Analysis

**Naming correction:** the ticket calls the recovery entry point `attempt_merge_recovery`; the
real symbol is **`recover_test_failure`** in `cortex_command/pipeline/merge_recovery.py` (~L187).
Its return contract is the `MergeRecoveryResult` dataclass (`success, attempts, paused, flaky,
error`).

**The strand point — `merge_recovery.py` dirty-base precheck (~L226-260):**
- `git rev-parse --show-toplevel` (~L228) with `cwd=str(repo_path) if repo_path else None`
  resolves `repo_root`. With `repo_path=None` → `cwd=None` → resolves the **process cwd** (home
  checkout), not the integration worktree.
- `git status --porcelain --untracked-files=no` at `cwd=repo_root` (~L246). Non-empty stdout →
  `paused=True, attempts=0, flaky=False, error="dirty base branch after revert"` (~L253-260) —
  **returns before the flaky guard (~L262) or repair cycle (~L288) ever run.** The error string
  is a hardcoded misnomer; nothing verifies a revert occurred.

**The collision source — `merge.py`:**
- `merge_feature` (~L158): `repo = repo_path if repo_path is not None else _repo_root()` (~L198).
  `git checkout {base_branch}` at `cwd=repo` (~L244). For a home feature `base_branch` resolves to
  `overnight/<session_id>` and `repo` is the home checkout → **`fatal: '<branch>' is already used
  by worktree at <integration-worktree-path>`** → `MergeResult(success=False, error="Failed to
  checkout …")` (~L250-258).
- Test-failure revert (~L301-307): `git revert -m 1 --no-edit HEAD` at `cwd=repo`. Unreachable in
  the 025 trace (the checkout returned early), but a live strand path once the tree is correct.
- `revert_merge` (~L335) and `_repo_root()` (~L42-50, bare `--show-toplevel`, no cwd) corroborate
  the cwd-fallback pattern.

**The resolution chokepoint — `outcome_router.py` `_effective_merge_repo_path` (~L116-246):**
- **`if repo_path is None: return None` (~L157-158)** — the load-bearing early return. Home
  features hit this and never consult `integration_worktrees`, the cached-hit branch (~L163), the
  lazy-create branch (~L166), or the existing **`"already checked out at"` handler (~L214-241)**.
  That handler only guards *worktree creation* for cross-repo features, and never protects
  `merge_feature`'s downstream `git checkout`.
- `_effective_base_branch(None, …)` (~L111-113) **correctly** returns `overnight/<session_id>`
  (via the default fallback). So home merges target the **right branch in the wrong tree** — the
  precise asymmetry that is the bug.
- Call sites: `merge_feature(…, repo_path=_effective_merge_repo_path(…))` at ~L565-572 and
  ~L845-854; review dispatch at ~L879-881; `recover_test_failure(…, repo_path=…)` at ~L1059-1074
  — **all four share the defect.** Recovery-result routing (~L1077-1178): flaky/success → merged;
  else → `features_paused` + backlog write-back.
- **Second unguarded checkout:** the `repair_completed` path does `git checkout
  ctx.config.base_branch` with `repo = Path.cwd()` (~L464-469) — hard-coded home cwd, same
  collision, bypasses the helper entirely.

**Where `overnight/<id>` is created — `plan.py`:** `integration_branch_name =
f"overnight/{session_id}"` (~L388); home integration worktree created once at
`$TMPDIR/overnight-worktrees/{session_id}` (~L406-410) and **owns the only checkout of that
branch for the whole session.** Critically, `integration_worktrees` is populated **only for
cross-repo** targets — the loop does `if repo_path == project_root: continue` (~L434-437); the
home worktree is stored solely in `state.worktree_path` (~L523). A "wild-light" rescue at
~L508-511 backfills `integration_worktrees[project_root]` **only** `if not has_home_features` —
which does not fire when every feature is a home feature (the failing case).

**The correct resolver already exists** at `runner.py` `_resolve_feature_integration_worktree`
(~L578-602): `if fs.repo_path is None: return Path(state.worktree_path)`. The merge path simply
does not use it.

**Status vocabulary is decentralized (no single enum):**
- `overnight/state.py` `FEATURE_STATUSES = ("pending","running","merged","paused","failed","deferred")`
  (~L28-30); `_TERMINAL_FEATURE_STATUSES = ("merged","failed","deferred")` (~L619) — **`paused`
  deliberately excluded** (it auto-retries). `OvernightFeatureStatus` fields (~L91-103): `status,
  round_assigned, started_at, completed_at, error, deferred_questions, spec_path, plan_path,
  backlog_id, recovery_attempts, recovery_depth, repo_path, intra_session_blocked_by` — **no
  `flaky`, no branch field, no `recoverable_branch`.**
- `pipeline/state.py` has a *separate* `FEATURE_STATUSES`
  (`pending, executing, reviewing, merging, merged, paused, failed`).
- `common.py` `TERMINAL_STATUSES` (~L162) and `plan.py` `_TERMINAL` (~L149) govern the **backlog**
  vocabulary — a different model from feature statuses.
- `_OVERNIGHT_TO_BACKLOG` (~L327-348) maps feature status → backlog write-back: `merged→complete`,
  `paused→in_progress`, `failed→refined`, `deferred→backlog`.

**Existing tests (package-local `*/tests/`):** `pipeline/tests/test_merge_recovery.py` (patches
`subprocess.run`; `test_dirty_base_check_*` assert the exact error string — **will need
updating**); `overnight/tests/test_outcome_router.py` (recovery path, `integration_worktrees={}`);
`tests/test_feature_executor.py::test_same_repo_uses_cwd` (**encodes the buggy `Path.cwd()`
expectation**, ~L186/216); `pipeline/tests/test_merge_ci.py` (only `merge_feature` coverage — no
checkout-collision test); `tests/test_runner_pr_gating.py` (`[ZERO PROGRESS]` gating + a
**byte-identical `tests/fixtures/dry_run_reference.txt` snapshot** that will need regenerating).
No test reproduces the round-2 collision end-to-end — a new test is needed.

**Full call chain into recovery:** `runner.run()` round loop → spawns `cortex-batch-runner` →
`orchestrator.run_batch` → `_run_one` → `outcome_router.apply_feature_result` →
`merge_feature(repo_path=_effective_merge_repo_path(…))` [checkout collision] → on failure routed
to test-failure branch → `recover_test_failure(repo_path=…)` [dirty-base strand] → `paused` →
`_write_back_to_backlog("paused")` → serialized to `batch-{round}-results.json` →
`map_results` → `OvernightState.features[*].status` → read by `report.py` / `runner._post_loop`.

## Web Research

**git worktree branch exclusivity** ([git-worktree](https://git-scm.com/docs/git-worktree),
[git-switch](https://git-scm.com/docs/git-switch)): a local branch may be checked out in at most
one worktree; `git checkout`/`switch`/`worktree add` raise `fatal: '<branch>' is already used by
worktree at '<path>'` as a deliberate safeguard (shared object store / ref db). Idiomatic safe
patterns, in order: (1) **detect ownership** with `git worktree list --porcelain`; (2) **operate
in the owning worktree** via `git -C <owning-path> …` rather than re-checking-out the branch
(the right pattern when a long-lived integration worktree owns it); (3) **detached checkout**
(`git worktree add --detach`/`git checkout --detach`) when you only need a commit's *contents*,
not to advance the branch; (4) `git worktree prune` for stale records. **Anti-pattern explicitly
discouraged:** `--ignore-other-worktrees` / `worktree add --force` (no warning on uncommitted
changes; index/ref clobbering).

**revert leaving a dirty tree** ([git-revert](https://git-scm.com/docs/git-revert),
[git-reset](https://git-scm.com/docs/git-reset)): a *successful* `git revert -m 1 --no-edit HEAD`
creates a commit and leaves the tree **clean** — so a successful revert does not by itself trip a
porcelain check. Dirtiness comes from the **conflict path** (unmerged paths, `.git/sequencer`,
dirty index) or from `-n/--no-commit`. `git rev-parse --show-toplevel` returns the **current
worktree's own root** when cwd is inside a linked worktree — so a cleanliness check that resolves
the root this way checks the wrong tree if cwd assumptions are off (cf. distinguishing main vs
linked worktree via `--git-dir` ≠ `--git-common-dir`). For "deterministically restore a known-
clean base," prefer `git reset --hard <captured SHA>` (+ `git clean -fd` for untracked) over
`revert`; pitfalls: discards uncommitted tracked work irrecoverably, doesn't remove untracked
files, destroys work silently if `<ref>` is wrong — must target an explicitly-captured SHA.

**recovery/retry state machines (prior art):** mature gating systems model "built but not yet
merged" as a **distinct, retryable state**, separate from test-failure:
- **Zuul** (closest prior art) separates `MERGER_FAILURE` (infra/merge-blocked, *retryable*) from
  a genuine job failure — devs note the name is "misleading… some infrastructure-related error"
  and deliberately retry it.
  ([gating](https://zuul-ci.org/docs/zuul/latest/gating.html),
  [retry commit](https://opendev.org/zuul/zuul/commit/c982bfed4d1ab2511464759e948a85c1b002d424))
- **Mergify** has an explicit lifecycle (… Validating → Merged); re-queue "resets to a neutral
  state" and re-enters at position, not from zero.
  ([lifecycle](https://docs.mergify.com/merge-queue/lifecycle/))
- **Idempotent partial-step retry**: checkpoint *which step to resume from* + per-step idempotency
  key; classify transient/infra failures apart from permanent ones and retry after backoff;
  preserve already-completed work so retry resumes from the integration step.

**The anti-pattern #281 exemplifies:** treating a *blocked-but-recoverable* condition as a
*terminal zero-progress failure*. The durable fix mirrors the prior art — detect worktree
ownership and `git -C` into the owner (or detached checkout) instead of contending for the
branch; restore the base deterministically; and tag the feature's true state so the recovery
layer retries integration rather than reporting total failure.

*(Unfetched: `devtoolbox.dedyn.io/blog/git-worktree-branch-locked-…` returned ECONNREFUSED;
summarized from search snippet.)*

## Requirements & Constraints

**In scope** per `project.md` ("Overnight execution: framework, sessions, … morning report";
"conflict resolution pipeline") — all three fix areas are squarely in scope.

**Fixed architectural constraints that must NOT be violated** (`pipeline.md`, labeled "fixed" /
"permanent"):
1. **Repair attempt cap** — max 2 attempts for test failures; single Sonnet→Opus escalation for
   conflicts. The fix must not become an unbounded retry loop to escape the stall.
2. **Integration branch persistence** — `overnight/{session_id}` is not auto-deleted; the
   collision fix must **not** resolve by deleting/reassigning the branch.
3. **Atomic state writes** — tempfile + `os.replace()`; any new field/marker must use it.
4. **`before_sha == after_sha` circuit breaker** — must remain the no-progress trip.

**Status-vocabulary multi-location constraint** (`project.md`): adding a **backlog terminal**
status requires updating `common.py:TERMINAL_STATUSES` + `plan.py:_TERMINAL` + a `normalize_status`
entry (with the `backlog.py` known-divergence). **Scope note:** "built but merge-blocked" is most
naturally a **feature** status (model B), *not* a backlog terminal status — so that specific
triple-update may not apply, but a new *feature* status touches `state.py:FEATURE_STATUSES` (both
copies) + ~13 consumer sites. **ADR-0004's R4 explicitly argued against** adding transient in-flight
statuses to backlog frontmatter ("widening the status schema for every downstream reader").

**Destructive-ops-preserve-uncommitted-state** (`project.md` Quality Attributes): directly governs
the ticket's `reset --hard` suggestion — "Cleanup scripts removing user-visible artifacts SKIP on
uncommitted state. Inline destructive sequences extract into named scripts." A `reset --hard` must
be scoped/guarded and extracted to a named script; the conservative path (scope the check to the
integration worktree) avoids the destructive remedy entirely.

**Resume contract** (`pipeline.md` Edge Cases): "`paused` features re-enter the execution queue" —
the documented behavior that produces the round-2 collision; changing re-dispatch must preserve it
for *genuinely* recoverable pauses. "Feature paused with no recovery attempts remaining: Status
transitions to `paused` permanently until human intervenes" — the documented stranded state.

**`[ZERO PROGRESS]` governance** (`pipeline.md` Session Orchestration): draft PR + `[ZERO
PROGRESS]` prefix on zero-merge home sessions; `integration_pr_flipped_once` gates the resume
state-flip — load-bearing, must be preserved. Changing the title logic requires regenerating the
`dry_run_reference.txt` snapshot.

**Events-registry obligation** (`bin/.events-registry.md`): new event constants must be added to
`EVENT_TYPES` in `overnight/events.py` (`append_event` raises otherwise) and a registry row added
(Python emission is `scan_coverage: manual` — not gate-blocked, but the convention requires the
row; reusable existing events: `feature_paused`, `feature_merged`, `circuit_breaker`,
`merge_recovery_{start,flaky,success,failed}`, `integration_recovery_{start,success,failed}`,
`integration_worktree_missing`). Any new event named in a `grep -c` acceptance check must resolve
(`tests/test_backlog_grep_targets_resolve.py`).

**Solution-horizon signal:** the ticket itself calls the collision "structural … audit all such
call sites" — under the project's durable-fix principle this favors a shared resolver fix at the
chokepoint over a point patch. **Sandbox:** `$TMPDIR` is already in `sandbox_settings.py` allowWrite
(~L68), so merging inside the `/tmp` integration worktree is sandbox-safe (ADR-0005: cross-repo
overnight worktrees remain TMPDIR-based).

## Dirty-Base Root Cause & Remedy

**Root cause = candidate (a), wrong-tree, verified against `overnight-2026-06-02-1312` logs.**
The real event chain (no `merge_complete`, no `merge_reverted`):
```
merge_start → ci_check_skipped → merge_error "Failed to checkout overnight/<id>:
  fatal: '…' is already used by worktree at /private/tmp/claude-503/overnight-worktrees/<id>"
→ merge_recovery_start → merge_recovery_failed attempts=0 "dirty base branch after revert"
```
The proof trace: feature `repo_path=None` (home feature; `orchestrator.py:280`) →
`_effective_merge_repo_path(None,…)` returns `None` (`outcome_router.py:157-158`; `integration_
worktrees={}` in state, so the cached-hit branch can't help) → `merge.py:198` falls back to
`_repo_root()` = home cwd → `git checkout overnight/<id>` collides. The dirty-base precheck then
runs `git status` against that same home tree, which was dirty **from the intentionally-
uncommitted round `plan.md` copies** the runner leaves in the home tree by design
(`runner.py` `_commit_round_plans_in_worktree` docstring ~L620: "The home-tree copy is
intentionally left in place (and uncommitted)"). So the "dirty base" is real but in the **wrong
tree**, and "after revert" is a lie.

**Why `integration_worktrees` is empty for home features:** `plan.py:434-437` skips
`project_root`; the wild-light rescue (`plan.py:508-511`) only fires `if not has_home_features`.

**Candidates (b)/(c) ruled out:** (b) no revert ran (the revert block at `merge.py:294` is
unreachable after the early checkout return); (c) `--untracked-files=no` excludes untracked, and
the dirtiness was real tracked modifications (the plan.md copies) in the home tree.

**Remedy evaluation:**
- **Remedy 1 — `reset --hard <pre-merge ref>` before the precheck (ticket A):** *Reject as
  primary.* The pre-merge ref isn't captured today; run against the wrong (home) tree it would
  **destroy the user's uncommitted work** (violates the destructive-ops constraint); even scoped,
  it masks that the merge never succeeded.
- **Remedy 2 — scope the cleanliness check to the integration worktree (ticket B):** correct
  direction but **incomplete** — it fixes the *check* but not the *merge*, which fails first.
- **Remedy 3 — fix upstream tree resolution (RECOMMENDED):** make the home merge target the
  integration worktree (`state.worktree_path`), mirroring `runner.py:578-602`. Fixes **both**
  `merge_feature` and `recover_test_failure` (they share the call) at the root; the checkout
  becomes a same-worktree no-op (as it already is cross-repo); the precheck then runs against the
  clean integration worktree. No destructive op; uncommitted-state constraint honored for free.
  This is the durable fix — the same wrong-tree fallback bites every home feature on merge /
  review-dispatch / recovery (`outcome_router.py:571, 851, 879, 1071`).

**Is `attempts=0` pause the wrong default? Yes, independently:** (1) the error string misreports
reality; (2) pausing a **built** feature because the *base tree* is dirty conflates an environment
problem with feature failure. Correct behavior: a correctly-scoped precheck that finds the
*integration* worktree dirty should clean-and-retry (the worktree is a throwaway `/tmp` tree, not
the user's), not pause-at-0 — reserve pause-at-0 for when the feature's own commits are the problem.

## Worktree/Branch Collision Audit & Re-dispatch Strategy

**Complete inventory of integration-branch checkout / worktree-add sites** (collision-risk):

| Site | Operation | Risk | Why |
|------|-----------|------|-----|
| `merge.py:244` `git checkout base_branch` (cwd=repo) | **YES — the bug** | home feature → repo=home cwd, base=`overnight/<id>` → collides. Cross-repo: same-worktree no-op (safe). |
| `merge.py:354` (`revert_merge`) checkout | **YES if reached** | same conditions; not currently on the overnight path (revert happens inside `merge_feature`). |
| `outcome_router.py:466` (`repair_completed`) `git checkout config.base_branch` (repo=`Path.cwd()`) | **YES** | hard-coded home cwd; ignores `_effective_merge_repo_path` entirely. |
| `orchestrator.py:340` / `worktree.py:261` / `conflict.py:137` `git worktree add -b … base` | **NO** | `overnight/<id>` used only as a *start-point* for a new `pipeline/…`/`repair/…` branch; round-2 re-entry returns early (worktree exists). |
| `plan.py:406-410` `git worktree add -b overnight/<id>` | **NO** | the *creator*, run once at bootstrap. |
| `integration_recovery.py`, `sync_rebase.py:238`, `conflict.py:599` | **NO** | operate inside a given worktree / file-level `--theirs`. |

**Does `outcome_router.py:214`'s "already checked out at" handler cover re-dispatch? NO** — it
lives inside `_effective_merge_repo_path`, reached only for cross-repo (`repo_path is not None`);
home features short-circuit at L157-158. And it guards `git worktree add`, not the downstream
`git checkout` in `merge_feature`. The collision is **not re-dispatch-specific** — it fires for
every home feature's *first* merge; round-2 is just where it becomes a visible stall.
**`tests/test_feature_executor.py:186` (`test_same_repo_uses_cwd`) asserts the buggy
`repo_path=None → Path.cwd()` resolution and must be updated.**

**Re-dispatch strategy — recommend (a) reuse the integration worktree, with (c) as a complementary
guard:**
- **(a) Reuse** — resolve home merges to the integration worktree (the Remedy-3 fix). Smallest,
  removes the home/cross-repo asymmetry, fixes sites #1/#2/#3 and the dirty-base strand at once,
  composes with the existing push/PR flow. **Cons:** must update `feature_executor.py:651-667` +
  the test, and reconcile with the `plan.py` wild-light conditional.
- **(b) Detached checkout** — *rejected*: a `--no-ff` merge must advance the branch ref; a detached
  HEAD merge produces commits no branch points to, and `git branch -f overnight/<id>` races the
  worktree that owns it. Works for read-only ops, not the merge itself.
- **(c) Skip re-dispatch of an already-built feature** — necessary for the *reporting* half (don't
  re-run the builder, don't burn budget, surface "recoverable on `pipeline/<feature>`"), but
  orthogonal to the collision — does **not** by itself fix the checkout target. Complement to (a).

## Status Model & Resume Queue

Two parallel models — **the bug lives in the feature-status model (B), not the backlog terminal
model (A).** Feature statuses (`overnight/state.py:28-30`): `merged` (terminal success),
`failed` (terminal, **cascades** to dependents), `deferred` (terminal-for-session, **no** auto-
retry, **no** cascade, surfaced for human), `paused` (**not** terminal, **auto-retries every
round** — the bug), `pending`/`running` (in-flight).

**Re-dispatch / auto-retry is enforced in two load-bearing places:** the orchestrator-round prompt
(`prompts/orchestrator-round.md`: "Paused features are always included … they are in recovery and
must be retried") and `runner.py:_count_pending` (~L352-358 counts `pending`+`running`+`paused`;
`deferred` excluded). So `paused` → re-dispatched into the collision; `deferred`/`failed`/`merged`
→ never re-dispatched.

**Whatever status represents "built but merge-blocked" must NOT be `failed`** (cascade would
wrongly fail siblings 026/027 — `sweep_blocker_failed_dependents`, `state.py:622-685`, fires only
on terminal `failed`) **and must NOT be `paused`** (re-dispatch loop). That leaves `deferred`-like
shape.

**Recommendation (status-model agent): reuse `deferred` + a new optional `recoverable_branch`
metadata field** on `OvernightFeatureStatus`, rather than minting a new status (which would touch
~13 consumers to re-implement behavior `deferred` already has — fails "complexity must earn its
place"). The existing `error`-string sub-distinction pattern (`outcome_router.py:160` already
routes `paused`→`deferred` by testing `"deferred" in error`) is the precedent. **But the
adversarial pass found three real problems with this (see below) — the status choice is
genuinely unresolved.**

## Reporting & Circuit-Breaker

**`[ZERO PROGRESS]` trigger** (`runner.py:_run_post_loop_sequence` ~L1689-1736): two gates against
the **integration branch** — (1) `_integration_commit_count()` = `git rev-list --count
main..overnight/<id>` == 0 → skip PR; (2) `_count_merged_home_repo()` (status=="merged" and
repo_path is None) == 0 → `--draft` + `[ZERO PROGRESS]`. Feature 025 hit gate (2): built but
`status=paused`, so 0 merges → `[ZERO PROGRESS]` draft PR (confirmed in `runner-stdout.log`:
`gh pr create --draft --title [ZERO PROGRESS]…`). **Gate (1) did NOT fire** because the integration
branch carries the round `plan.md` commits — so `main..overnight/<id>` ≠ 0 even with nothing
merged. **This means `_integration_commit_count` cannot be reused as-is to tell built-from-never-
built.**

**Morning report** (`report.py`): `render_executive_summary` (~L356-435) counts `merged` and
`failed = (failed|paused)` — a built-but-blocked feature reads as `failed`. The natural insertion
point is `render_failed_features` (~L1069-1201), which already has partial hooks: a `feature_merged`
warning path and a `Recovery branch: pipeline/{name}` line (~L1146) — **but that line is gated on
`conflict is not None`**, so a checkout-collision (no conflict event) renders no pointer.

**Circuit-breaker** (`runner.py:2711-2724`): "progress" = merge delta (`_count_merged`); two
consecutive zero-merge rounds → `circuit_breaker reason:"stall"`. **Reporting agent's claim: no
circuit-breaker code change needed** — the stall breaker is a correct budget backstop, and recovery
is already one-attempt-per-batch. *The adversarial pass qualifies this* (see Open Questions #4).

**Reporting signal — must use the persisted *actual* branch, not `pipeline/<name>`:** the feature's
branch may be suffixed (`pipeline/<name>-2`/`-N` on collision, `worktree.py:_resolve_branch_name`),
and `worktree_branches` is orchestrator-runtime-only — **not persisted** in `OvernightFeatureStatus`
or `ReportData`. So `git rev-list --count main..pipeline/<name>` on the bare name can read a stale
prior-session branch (false "built") or 0 (false "never built"). The signal must come from a
persisted field or by reading `merge_start.branch` from the event log.

## Adversarial Review

The adversarial pass verified every load-bearing claim against the code and the real logs
(confirming the root cause and the plan.md-copies dirtiness) and surfaced these corrections:

1. **The "just populate `integration_worktrees` at bootstrap" fix is a NO-OP.** The early return
   at `outcome_router.py:157-158` fires *before* the dict is consulted. The real change must be
   inside `_effective_merge_repo_path`: special-case `repo_path is None → state.worktree_path`.
   But the helper's signature `(repo_path, integration_worktrees, integration_branches,
   session_id)` has **no access to `state.worktree_path`** — a **signature change threaded through
   both call sites** is required. The naive patch would pass a shallow test and ship the bug.
2. **Reconcile with the wild-light conditional** at `plan.py:508-513` (already conditionally sets
   `integration_worktrees[project_root]`); an unconditional add changes that branch's behavior.
3. **Dispatch-allowlist leak risk:** `_effective_merge_repo_path` is *also* consumed at
   `feature_executor.py:656-667` to compute the worker's write-allowlist (today home features
   short-circuit to `Path.cwd()` there). The test-file header warns the pre-fix bug "admitted the
   home repo into cross-repo dispatch allowlists." Changing the helper's `None` return could shift
   the home worker's allowlist from home cwd to `/tmp` — **the dispatch site and merge site handle
   `None` independently and must be audited separately.** "Collapse onto one code path" is too
   optimistic.
4. **`deferred` does NOT yield a clean session for genuine blocks — it stalls.** A `deferred`
   feature's blocked siblings stay `pending` forever (orchestrator gate treats `!= "merged"` as
   blocking; `sweep_blocker_failed_dependents` cascades only on `failed`, not `deferred`). So
   `_count_pending` stays > 0, the loop churns the siblings, and the stall breaker fires. "No
   circuit-breaker change needed" is *technically* true (it stops) but the exit is **not graceful**
   — the deferred-blocker cascade must be addressed (treat the blocker as satisfiable/unsatisfiable
   explicitly, or sweep deferred-blocked dependents).
5. **`deferred` collides with the question-file machinery:** `report.py` (~L282-293, 964, 1867)
   renders a deferred feature as "Retry deferred … unanswered questions … see `deferred/{name}-
   q*.md`" — a file that won't exist for a merge-blocked (not question-blocked) feature → broken
   report text + misleading retry-from-scratch backlog item.
6. **The `backlog` write-back IS a latent rebuild-from-scratch bug** (`deferred → backlog`,
   `outcome_router.py:344-347`): a feature whose work is intact on `pipeline/<name>` becomes a
   candidate to be rebuilt from zero next session. `filter_ready`'s `_is_pipeline_branch_merged`
   guard does the *opposite* of what's needed (excludes *merged* branches). The write-back target
   must record "recover on branch X," not "redo."
7. **The recovery-branch hint must be ungated from `merge_conflict_classified`** (`report.py:1146`)
   or it won't render for this checkout-collision bug class.

## Open Questions

1. **Does the primary tree-resolution fix alone close #281 — making the status/reporting work a
   separable fallback?** Strong evidence: **yes for the observed 025 scenario** — once the home
   merge targets the integration worktree, the checkout no-ops, the dirty-base precheck reads the
   clean integration worktree, 025 merges, and siblings 026/027 unblock. The status/reporting/
   `deferred` work is then a fallback for **genuine** merge-blocks (real conflicts, repair
   exhaustion), *not* the 025 path. The user chose **full scope** (merge-path + reporting) at
   Clarify; this finding means the two halves are now revealed as **one tightly-scoped root-cause
   fix + one thornier, genuinely-separable fallback.** *Deferred: the Spec §4 complexity/value
   gate will surface whether the fallback ships in this lifecycle or splits to a follow-up, with
   a recommendation.*
2. **Status model for "built but merge-blocked": `deferred` + `recoverable_branch` metadata vs a
   new feature status vs explicit blocker-cascade handling.** The status-model agent recommends
   `deferred`+metadata; the adversarial pass shows that path needs (a) the deferred-blocker
   sibling cascade resolved, (b) the question-file rendering guarded, (c) a non-rebuild backlog
   write-back. *Deferred: resolved in Spec via the structured interview — this is a genuine design
   decision, and the fallback's existence depends on Q1.*
3. **Reporting signal source for built-vs-never-built:** a new persisted branch field on
   `OvernightFeatureStatus` vs reading `merge_start.branch` from the event log (the bare
   `pipeline/<name>` is unreliable due to branch suffixing; the integration-branch commit count is
   noisy from plan.md commits). *Deferred: resolved in Spec, dependent on Q2's status decision.*
4. **Does the `_effective_merge_repo_path` change need to also touch the dispatch-allowlist
   consumer (`feature_executor.py:656-667`)?** It must be **audited, not silently changed** — the
   merge site and dispatch site handle `repo_path is None` independently. *Deferred: resolved in
   Spec/Plan as an explicit audit step; the answer is "audit and keep the allowlist site's
   behavior unless deliberately changed."*
5. **The genuine test-failure-revert strand** (`merge.py:301-324`): once `repo` is correctly the
   integration worktree, the revert is correct — but if the integration worktree is *itself* dirty
   (prior aborted merge), the now-correctly-scoped dirty-base precheck genuinely fires. Should it
   clean-and-retry the throwaway worktree rather than pause-at-0? *Deferred: resolved in Spec
   (relates to Q1's "attempts=0 is the wrong default" finding).*
6. **`reset --hard` (if adopted at all):** only the integration worktree, only against a captured
   pre-merge SHA, extracted to a named script per the destructive-ops constraint. *Deferred:
   resolved in Spec — Remedy 3 likely makes it unnecessary.*
