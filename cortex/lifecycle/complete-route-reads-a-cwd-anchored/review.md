# Review — complete-route-reads-a-cwd-anchored · cycle 2 (rework re-review, scoped)

Cycle 1 returned CHANGES_REQUESTED. This pass reads the rework range `4a78b8b9..HEAD` (`c0b27a20` +
`8f5bae06`) and answers the narrow question: did the five flagged items close, and did any fix break
something. Cycle 1's full review is preserved beside this file as `review-cycle-1.md`.

Method: I consumed the orchestrator's baseline rather than re-running `just test`. To rate the reworked
acceptance criteria I re-ran the four directly-affected test files and four mutations in a throwaway git
worktree under the scratchpad, removed afterwards (`git worktree list` verified clean, repo `cortex_command/`
and `tests/` untouched). Every claim below about what a test does or does not catch was measured.

## Test baseline

I agree with the orchestrator's reading. The 6 failures in the `tests` recipe are the same set confirmed at
`47797d42` in cycle 1 — `tests/test_cli_background_install_hook.py` ×4 and the two `.venv`-symlink cases
(`test_implement_option2_worktree_creation.py`, `test_worktree.py`) — confirmed by name in the log at
`:3508-3513`. None touches a module under review. Passing count 2623 → 2626 matches the three tests this
rework adds, so the rework adds no new failure and silences none.

## Mutations run this cycle

Baseline in the mutation worktree at `8f5bae06`: `tests/test_complete_route.py` +
`cortex_command/lifecycle/tests/` = **605 passed**.

| # | Mutation | Result |
|---|---|---|
| M6 | revert **only** the `pr.json` read anchor to `root / "cortex" / "lifecycle" / slug / "pr.json"` | **1 failed** — `test_main_root_pr_json_is_found_from_the_worktree_cwd` (`first_run` ≠ `pr_open`). Was 0 in cycle 1. |
| M1 | drop `and _find_slug_worktree(slug) is None` from the `on_main` gate | 3 failed — `test_on_main_does_not_fire_while_a_worktree_exists`, **`test_retryable_finalization_on_main_with_a_worktree_restarts_at_first_run`**, `test_accepted_edge_worktree_present_gh_absent_is_terminal_pr_unknown` |
| M7 | delete the new `try/except CortexProjectRootError` in `classify` | 1 failed — `test_classify_never_raises_when_the_verdict_root_cannot_resolve` (raises `CortexProjectRootError`) |
| M4 | strip Req 2a's slug validation (anchor at raw `resolve_main_repo_root`) | 4 failed — `test_env_root_without_this_lifecycle_is_ignored`, `test_branch2_stale_git_file_no_traceback`, and both `test_log_resolver.py` rejection cases |

## Prior-Cycle Checklist

### 1. Req 2 — the `pr.json` READ anchor is unpinned — **RESOLVED**

`test_main_root_pr_json_is_found_from_the_worktree_cwd` (`tests/test_complete_route.py:868-914`) pins exactly
the discriminating direction cycle 1 asked for: `pr.json` written at the main root via `_write_pr_json`, the
worktree asserted to hold none of its own, `classify` run from the worktree CWD, asserting `pr_open` /
`pr_state == "OPEN"` / the main-root URL / `terminal`. Measured: **M6 now costs exactly one failure** (was
zero across the whole suite in cycle 1), failing with `first_run` — the `pr.json`-absent arm — which is the
predicted signature.

The construction is careful in a way worth recording: `GH_STUB_PR_LIST_COUNT=0` closes the escape hatch by
which a CWD-anchored read could re-enter Branch 4 through the single-match `_reconstruct_pr_json`
reconstruction, so the mutation lands on `first_run` rather than accidentally recovering `pr_open`. The test
also asserts the reconstruction arm did **not** run (no `pr.json` materialises in the worktree), so it pins
the absence of a side effect as well as the route.

### 2. Req 5 — the rewritten test does not satisfy its own acceptance clause — **RESOLVED**

Cycle 1 asked for no code change: correct the spec's Req 2a measurement, restate Req 5's acceptance against
the unvalidated-anchor mutation, and carry the framing into the test docstring. All three landed.

- `spec.md:48-55` (Req 2a) now separates what was measured (`resolve_main_repo_root()` returns the bogus root
  verbatim) from what was wrongly attributed to HEAD, and labels it **"Orchestrator error, corrected in
  rework"** with the provenance (a post-fix emulation during research). It names the mutation that does
  discriminate.
- `spec.md:80-85` (Req 5) restates acceptance as "fails when `resolve_verdict_root` is replaced by the raw,
  unvalidated `resolve_main_repo_root`" and states explicitly that it deliberately does *not* fail against
  pre-change code, with the reason.
- `tests/test_complete_route.py:800-809` carries the same framing in the docstring, pointing back at the spec.

The restated criterion is **falsifiable and verified**: under M4 the test fails. Per the standing rule that
every acceptance clause be run against the current tree before approval, I checked both halves — clause 1
(`tests/test_complete_route.py` green) holds in the baseline, clause 2 measured above.

### 3. Req 7's gate crossing Branch 2's retryable fall-through — **RESOLVED** (both remedies, not either)

Cycle 1 offered "a pinning test *or* an explicit accepted-edge line"; the rework did both.

- `spec.md:172-180` adds the Edge Case, naming the full precondition set, calling the cost real rather than
  neutral, and citing the Branch-2 comment's own "strictly worse than `already_complete`".
- `test_retryable_finalization_on_main_with_a_worktree_restarts_at_first_run`
  (`tests/test_complete_route.py:1614-1661`) builds the shape end-to-end (real repo, `merge_anchor: "merge"`
  working-tree row, no `pr.json`, live `interactive/{slug}` worktree, `main`) and asserts `first_run`/`step1`.

The test is not tautological: reaching `first_run` at all proves the Branch-2 retryable predicate evaluated
true and fell through, since a non-retryable evaluation returns `already_complete`/`step12` before the gate.
It discriminates — M1 flips it to `on_main`. The docstring frames it as characterization, not endorsement.

**On the builder's flagged residual** (a failed finalization commit on main with an un-cleaned worktree loses
its retry and restarts at step 1): I agree "accepted-with-cost" is the right disposition, on four grounds I
verified rather than assumed. (a) The restart arm is non-destructive — `first_run`/`step1` is `gh pr create`,
which the operator sees before anything happens; the destructive arm is `step8`, unreachable from here. (b)
The state is not stuck and the exit is cheap: removing the worktree — which is what this stage of the
lifecycle wants anyway — restores `on_main`/`step9` exactly (`complete_route.py:671`, pinned by
`test_on_main_still_fires_with_no_worktree`). (c) Reachability is narrower than the edge-case line implies:
the fall-through only *reaches* `first_run` when `_orphan_probe` succeeds and returns **zero** matches — a
`gh` failure yields the retryable `pr_unknown` (`:688-689`) and any match reconstructs into Branch 4
(`:704-708`) — and since the probe queries `--state all`, a merge-anchored lifecycle's own merged PR would be
found, so zero matches implies no PR for `interactive/{slug}` ever existed. (d) It is now documented and
pinned, so a future change to either branch has to face it.

One improvement I would take but do not require: neither the edge-case line nor the docstring names the
**exit** — that removing the worktree restores step 9. An operator who lands on this restart has the cost
documented and no stated recovery. That is a one-clause addition to `spec.md:172-180`, not a defect.

### 4. `_reconstruct_pr_json` can materialise a tree under a wholly bogus root — **RESOLVED as accepted** (recorded, no code change)

The builder's disposition — leave it as a recorded observation — is right, and the record survives: cycle 1's
review is preserved at `cortex/lifecycle/complete-route-reads-a-cwd-anchored/review-cycle-1.md:201-206`
rather than overwritten. I re-record the substance here so it does not depend on that file: under
`resolve_verdict_root`'s step-3 fallback the unvalidated root stands (`log_resolver.py`, step 3, documented
in its own docstring as the never-crash / fresh-lifecycle case), and `_atomic_write_json` does
`mkdir(parents=True)`, so a Branch-3 single-match reconstruction under a wrong `CORTEX_REPO_ROOT` creates
`{bogus}/cortex/lifecycle/{slug}/`. Needs a wrong env var *and* exactly one live orphan PR. Step 3 is the
spec's own accepted risk (`spec.md` Non-Requirements, and the plan's first Risk), so this is a consequence of
an approved decision, not an unexamined one.

### 5. `classify()` calls `resolve_verdict_root()` unguarded — **RESOLVED**

`complete_route.py:572-575` now wraps the call in `try/except CortexProjectRootError` falling back to
`root`, the invoking checkout, with a comment naming why the never-crash contract previously rested on an
accident of `main()`'s ordering. The guard is complete for the exception it names: `resolve_verdict_root`'s
CWD-walk branch is already caught internally, so step 1 is the only raise site, and step 1 is
`resolve_main_repo_root` → `interactive_lock._resolve_main_repo_root` arm (c) →
`_resolve_user_project_root()`, whose failure mode is exactly `CortexProjectRootError`. `CortexProjectRootError`
is imported at module scope (`:75`), so the test's `complete_route.CortexProjectRootError` reference is real
and not an attribute that happens to exist.

`test_classify_never_raises_when_the_verdict_root_cannot_resolve` (`:846-866`) pins it and discriminates —
M7 fails it with an escaping `CortexProjectRootError`. The fallback is behaviourally the pre-change anchor,
so it introduces no new routing on a path that previously worked.

## Requirement ratings

| Req | Rating | Basis |
|-----|--------|-------|
| 1 — `events.log` scan through the pinned resolver | **PASS** — carried forward from cycle 1; holds while `classify`'s `events_log` stays derived from `artifact_root` (unchanged in this range) | |
| 2 — `pr.json` at the main root on read and write | **PASS** (was PARTIAL) | write leg pinned by cycle 1's M3, unchanged; read leg now pinned, M6 → 1 failure |
| 2a — the resolved root is slug-validated | **PASS** — re-verified, not carried: M4 fails 4 tests. Implementation unchanged; the spec's grounding text is corrected | |
| 3 — `pr_opened` append in the pinned log | **PASS** — carried forward from cycle 1; holds while `record_pr_opened` resolves one root for both artifacts (untouched by this range) | |
| 4 — tree-sensitive probes keep the CWD root | **PASS** — carried forward from cycle 1; holds while `_head_has_feature_complete` / `_finalization_committable` / `read_commit_artifacts` take `root` (untouched) | |
| 5 — Req 7's superseded half retired explicitly | **PASS** (was PARTIAL) | acceptance restated to a falsifiable criterion and measured against M4; supersession framing in spec and docstring |
| 6 — worktree-existence predicate | **PASS** — carried forward from cycle 1; holds while `_find_slug_worktree` returns `Optional[str]` and `_resolve_worktree_path` layers its fallbacks (untouched) | |
| 7 — `on_main` does not fire while a worktree exists | **PASS** — re-verified, not carried: M1 fails 3 tests including the new crossing pin; route enumeration still 12 | |

## Stage 2 — code quality of the rework

The production delta is four lines plus a comment. It is the smallest change that closes item 5, uses the
same exception and the same fallback shape as `record_pr_opened`, and the comment explains the asymmetry
rather than restating the code. The three new tests are well-constructed: each names the mutation it
discriminates against in its own docstring, two of them close an escape hatch explicitly
(`GH_STUB_PR_LIST_COUNT=0`; the `assert complete_route._find_slug_worktree(SLUG) is not None` precondition),
and the characterization test says in its docstring that it is characterization. That is the honesty standard
cycle 1 asked for, applied without being asked twice.

Two observations, neither blocking, neither new to this rework:

1. Carried from cycle 1 and still true: `_find_slug_worktree` runs `git worktree list` against the process
   CWD rather than `root`, so a direct `classify(slug, root)` call with `root` outside the process CWD
   consults the wrong repository for the gate. Unreachable via `main()`. Pre-existing pattern.
2. The spec's new Edge Case documents the crossing's cost but not its exit (item 3 above).

`plan.md` carries no task or checkpoint for the rework — the changes landed directly against the review
issues. That matches how a rework is scoped and is not a finding; noting it only so a reader of `plan.md`
alone does not conclude the tree matches its last checkpoint.

## Out-of-Scope Findings

None found outside the checklist. I read the full `4a78b8b9..HEAD` diff (4 files, 165 insertions), and the
production change is confined to `classify`'s resolver call. The rework touches no `skills/` or `plugins/`
path, so it carries no dual-source mirror obligation; the working tree holds no unstaged mirror drift.

## Requirements Drift

- **State**: detected
- **Findings**:
  - Assessed afresh against `cortex/requirements/lifecycle.md` as it stands after `8f5bae06`: the two bullets
    that commit added to `### Served verb class` correctly capture the validated wrapper, its flock-domain
    cost, and `complete-route`'s two anchors plus the `on_main` worktree gate. Those are **not** re-reported.
  - Not captured: the caller-side never-crash arm this rework adds. The wrapper bullet enumerates three
    outcomes (validated root / CWD walk / resolved root stands); there is now a fourth at the call site — a
    `CortexProjectRootError` escaping step 1 degrades to the invoking checkout. The general never-crash rule
    at `:93` covers "exits 0 with an envelope" but not where a verdict verb anchors when its resolver fails.
  - Not captured: the `on_main` gate's cost. The existing bullet frames the gate purely as pre-PR-window
    protection ("falls through to the orphan probe rather than completing unmerged work"); it is
    unconditional, so it also diverts Branch 2's retryable-finalization fall-through, which restarts at
    `first_run` instead of retrying at step 9. The spec now records this; the requirements read as if the gate
    had no cost.
- **Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `### Served verb class`
- **Content**:

```
- A verdict verb guards its own call to the slug-validated wrapper: a `CortexProjectRootError` escaping the wrapper's step-1 resolution degrades to the invoking checkout rather than a traceback, so the never-crash contract never rests on the caller's own root walk having already succeeded.
- That `on_main` worktree gate is unconditional, so it also diverts Branch 2's retryable-finalization fall-through: a failed finalization commit on `main` with the slug's worktree still present restarts at `first_run` rather than retrying at step 9. Accepted cost — removing the worktree restores the retry.
```

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "detected"}
```
