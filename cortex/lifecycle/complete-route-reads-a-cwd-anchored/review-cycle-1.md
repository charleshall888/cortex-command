# Review — complete-route-reads-a-cwd-anchored · cycle 1

Two-stage review, complex tier. Stage 1 produced no FAIL, so Stage 2 ran.

Method note: I consumed the orchestrator's test baseline rather than re-running `just test`. To rate
acceptance criteria I additionally ran the five directly-affected test files (82 passed) and six targeted
mutations in a throwaway git worktree under the scratchpad, removed afterwards. Every claim below about what
a test does or does not catch was measured, not read.

## Test baseline

I agree with the orchestrator's reading. The 6 failures in the `tests` recipe
(`tests/test_cli_background_install_hook.py` ×4, two `.venv`-symlink cases in
`tests/test_implement_option2_worktree_creation.py` and `tests/test_worktree.py`) touch none of the modules
under review and reproduce at `47797d42`. Baseline noise, not regressions.

## Mutations run (the evidence base)

| # | Mutation | Tests that failed |
|---|---|---|
| M1 | drop `and _find_slug_worktree(slug) is None` from the `on_main` gate | `test_on_main_does_not_fire_while_a_worktree_exists`, `test_accepted_edge_worktree_present_gh_absent_is_terminal_pr_unknown` |
| M2 | `artifact_root = root` (revert both artifact anchors) | `test_classify_uses_two_distinct_anchors_from_worktree_cwd`, `test_finalize_event_from_a_worktree_is_visible_to_the_complete_route` |
| M3 | revert `record_pr_opened` to `_resolve_user_project_root_from_cwd()` | `test_worktree_cwd_writes_both_artifacts_to_the_main_root`, `test_pr_opened_from_a_worktree_promotes_the_main_root_session_scan`, `test_project_root_error_returns_state_not_traceback` |
| M4 | anchor at raw `resolve_main_repo_root()` — i.e. **strip the Req-2a validation** | `test_env_root_without_this_lifecycle_is_ignored`, `test_branch2_stale_git_file_no_traceback` |
| M5 | revert all three production files to `47797d42` | 16 tests (list in Req 5 below) |
| M6 | revert **only** the `pr.json` read anchor, leave `events.log` anchored | **none — 602 passed** |

## Stage 1 — spec compliance

### Req 1 — the `events.log` verdict scan resolves through the pinned resolver — **PASS**

`classify` now derives `lifecycle_dir` from `resolve_verdict_root(slug)` (`complete_route.py:568-571`), so the
Branch-1/Branch-2 scan reads the validated root's log. Routed through Req 2a rather than calling
`resolve_events_log` directly, exactly as the requirement specifies.

The spec's acceptance test exists and discriminates with the stated signature:
`test_finalize_event_from_a_worktree_is_visible_to_the_complete_route`
(`cortex_command/lifecycle/tests/test_worktree_log_anchor.py`) writes `feature_complete` through
`lifecycle_event.log_event` (main root only), classifies from the worktree CWD, and asserts
`already_complete`; under M2 it fails with `pr_unknown` — the "today's behaviour" the spec predicted.

### Req 2 — `pr.json` resolves at the main root on both read and write — **PARTIAL**

Implementation is correct on all three legs. The read is `lifecycle_dir / "pr.json"` off the artifact root
(`:570`); `_reconstruct_pr_json` receives that same `lifecycle_dir` (`:698-700`), so the Branch-3 write moves
with it; `record_pr_opened.py:140-148` resolves once and hands the same root to both artifacts.

The **write** half's acceptance criterion is met and pinned (M3).

The **read** half is not pinned at all. M6 — reverting only `pr_json` to `root / "cortex" / "lifecycle" /
slug / "pr.json"` while leaving `events.log` anchored — leaves the entire suite green (602 passed). The
requirement's second acceptance clause, "a second asserts `classify` from the primary finds it", has no
corresponding test; nothing exercises `classify` reading a `pr.json` that sits outside the invoking
checkout's tree. I verified the behaviour is correct by inspection (from a worktree, `artifact_root` resolves
to the main root, `pr_json.is_file()` is true, Branch 4 runs and yields `pr_open`; from the primary the two
roots coincide) — so this is a coverage gap, not a defect. But it is a gap on the leg the spec's Problem
Statement leads with, and any future refactor can silently revert it.

Note on framing: the clause as written ("classify from the primary finds it") could not fail either, since
from the primary `root` and the verdict root are the same path. The case that discriminates is the
**reverse** one — `classify` from the *worktree* finding a main-root `pr.json` — which is what the fix
actually buys and what should be pinned.

### Req 2a — the resolved root is slug-validated before it is trusted — **PASS**

`log_resolver.resolve_verdict_root` (`:86-129`) implements the three-step order verbatim: env/walk root when
it holds `cortex/lifecycle/{slug}`; else the CWD walk when *it* holds the slug; else the step-1 result
stands. The CWD walk is wrapped in a bare `except` with a never-crash comment, so
`CortexProjectRootError` cannot escape from that branch. The check is slug-scoped, not a bare `cortex/`
test. Added to `__all__`.

**The brief's specific question — does the validation actually close the re-opened finalize arm?** Yes, and
it is pinned at the integration level, not only in unit tests. M4 replaces `resolve_verdict_root` with the
raw env-honouring `resolve_main_repo_root` in both verbs — the design fork the critical review warned about
— and two `complete_route` tests fail. Four unit tests in `test_log_resolver.py` additionally pin each
branch, including the honour case (a valid env root still wins from a worktree CWD, so validation only
rejects, never steers).

One observation about the spec, not the code: Req 2a's grounding sentence — "measured today:
`resolve_main_repo_root()` returns `/nonexistent/bogus` and the route is `on_main`/`step9`" — is **false** for
unmodified code. Unmodified `classify` never called `resolve_main_repo_root` at all; it used the
env-ignoring CWD root, so a bogus `CORTEX_REPO_ROOT` produced no `on_main` there. The requirement is still
correct and necessary (it guards the arm the *new* anchoring would otherwise open), but the erroneous
grounding is what made its stated acceptance unfalsifiable, and it propagated into Req 5 below.

### Req 3 — `record_pr_opened`'s `pr_opened` append lands in the pinned log — **PASS** (deliberate deviation)

The verb resolves one root and hangs both artifacts off it. The append still goes through the shared
`_append_event_atomic` primitive, so `tests/test_events_log_writer_census.py`'s allowlist entry stays a live
hit (verified: census passes).

Deviation from the requirement's letter: the path is `resolve_verdict_root(feature)` rather than
`log_resolver.resolve_events_log(feature)`. This is the right call and follows Req 1's own stated rationale —
using `resolve_events_log` here would have left this verb's `events.log` on the *unvalidated* root while its
`pr.json` sat on the validated one, reintroducing the two-tree split the requirement exists to close. The
acceptance criterion is met and pinned (M3).

Residual worth recording: when the env root is invalid, this verb's `events.log` path — and therefore its
flock domain (`{events_log}.lock`) — can diverge from `lifecycle_event.log_event`'s `resolve_events_log`.
That is a narrower window than the one just closed (it needs a `CORTEX_REPO_ROOT` that does not hold the
slug, in which case `log_event` is writing into a wrong tree regardless), but it is a new divergence the
requirements do not capture. Logged under Requirements Drift.

### Req 4 — the tree-sensitive git probes keep the CWD root — **PASS**

`_head_has_feature_complete(slug, root)` (`:645`), `_finalization_committable(slug, root)` (`:651`),
`read_commit_artifacts(root)` (`:650`) and `_drift_files_from_review` (via `root` at `:387`) all still take
the invoking checkout. `test_classify_uses_two_distinct_anchors_from_worktree_cwd` asserts the two anchors
differ inside one `classify` call by capturing `_git_out` arguments, exactly as specified, and fails under
M2. The named regression guard `test_branch2_nested_cortex_root_H_uses_show_prefix` still passes.

### Req 5 — Req 7's superseded half is retired explicitly — **PARTIAL**

The rewrite happened. `test_worktree_cwd_resolution_ignores_env` became
`test_env_root_without_this_lifecycle_is_ignored`, built on the real `_worktree_fixture`, and its docstring
names the supersession precisely (Req 7 of `offload-completemd-pr-state-routing-and/spec.md:35`, the moved
`_resolve_user_project_root_from_cwd` contract, and which half of Req 7 survives). `tests/test_complete_route.py`
is green.

The second acceptance clause — "the rewritten test fails against unmodified `complete_route.py`" — is
**unmet, measured**. Under M5 (all three production files at `47797d42`) sixteen tests fail:

```
test_complete_route.py: test_classify_uses_two_distinct_anchors_from_worktree_cwd,
  test_worktree_predicate_is_distinct_from_path_resolution,
  test_worktree_predicate_returns_the_matched_path,
  test_worktree_predicate_fails_open_when_git_fails,
  test_on_main_does_not_fire_while_a_worktree_exists,
  test_accepted_edge_worktree_present_gh_absent_is_terminal_pr_unknown
test_log_resolver.py: all four verdict-root cases
test_record_pr_opened.py: test_cli_emits_json, test_project_root_error_returns_state_not_traceback,
  test_cli_accepts_url_and_head_branch_flags, test_worktree_cwd_writes_both_artifacts_to_the_main_root
test_worktree_log_anchor.py: both new cross-verb cases
```

`test_env_root_without_this_lifecycle_is_ignored` is **not** in that list; I confirmed it passes standalone
against the reverted source. It could not have failed: unmodified `classify` never consulted the environment,
so no env-based assertion can discriminate against it. The clause inherited Req 2a's erroneous measurement.

Rated PARTIAL rather than FAIL because the test does discriminate against the mutation that actually matters
— M4, the unvalidated anchor — which is the fork the critical review raised and the one a future refactor
could plausibly take. The builder did not flag this the way Task 4's builder flagged its own two
non-discriminating cases; the honesty standard applied there should have been applied here.

### Req 6 — a worktree-existence predicate distinct from path resolution — **PASS**

`_find_slug_worktree(slug) -> Optional[str]` (`:133-171`) holds the block-matching loops verbatim;
`_resolve_worktree_path` calls it and layers its `--show-toplevel` → `root` fallbacks unchanged (`:184-186`).
Behaviour is identical to the old inline form — the matched `path` was already non-empty by construction
(`if path:` guard), so `if match:` cannot change any answer. Three tests pin the split: predicate `None` +
path `"/repos/main"` on a non-matching porcelain, the match case, and fail-open on `_git_out` returning
`None`. All three fail under M5 (the helper does not exist).

### Req 7 — `on_main` does not fire while a worktree for the slug exists — **PASS**

The conjunct is at `:664`, with the conditions in the specified order. The fall-through lands on `first_run`
— an existing route — asserted explicitly rather than accepting "not `on_main`" alone. The route enumeration
in the module docstring is unchanged at 12; no new value was minted.

The builder's self-correction is **honest and confirmed**: `test_on_main_still_fires_with_no_worktree` (the
negative control) and `test_accepted_edge_foreign_head_branch_cannot_reach_step8` (accepted edge ii) are both
absent from the M5 failure list, so neither discriminates against unmodified code. The plan checkpoint says
so in its own words. The remaining Req-7 cases do discriminate (M1 fails two; M5 fails all three predicate
tests plus two gate tests). Edge (ii) is a characterization pin the spec explicitly asked for — "pin it
rather than leave it accidental" — so its non-discrimination is the intended shape, not a miss.

Builder note 2 (`test_explicit_project_root_still_wins_over_resolution` passing under its own mutation) is
likewise honest: it pins the caller-override contract, which is unchanged by design.

Builder note 3 (`test_branch2_stale_git_file_no_traceback` re-fixtured) checks out. The test's primary
assertions — no traceback on a stale `.git` marker, and `already_complete`/`step12` from the W=True,
H=False, committable=False path — are byte-identical. What changed is the divergent `CORTEX_REPO_ROOT`
fixture: it now holds `lifecycle/other-feature` instead of `lifecycle/{SLUG}`. That was necessary (the old
fixture would have made the env root pass validation and win) and it did not weaken the test — it
*strengthened* its env role, which is now an active assertion rather than a passive one. Measured: this test
fails under M4, i.e. it is one of the two integration-level pins on the Req-2a validation.

## Stage 2 — code quality

**Correct and consistent.** Naming (`resolve_verdict_root`, `_find_slug_worktree`) reads well and matches the
module conventions. The two-anchor comment in `classify` follows `review_brief.py:706-713`'s style as the
plan asked. Docstring corrections landed: `log_resolver.py:34-40` no longer claims
`_resolve_user_project_root_from_cwd` is what typed subcommands use, and `complete_route.py`'s module
docstring no longer states CWD anchoring as deliberate. Error handling is fail-open throughout
(`_find_slug_worktree` on `_git_out` `None`; `resolve_verdict_root` on the CWD walk raising). The plan's
verification commands were genuinely executed — I re-ran them and got the stated results.

Four observations, none blocking:

1. **An unanalyzed interaction between Req 7 and Branch 2's retryable fall-through.** When Branch 2 decides a
   finalization is retryable it deliberately does *not* return, expecting to land on `on_main` → step9. With
   the new gate, a retryable case on `main` with a live `interactive/{slug}` worktree and no `pr.json` now
   falls to the orphan probe instead, which on zero matches yields `first_run` → step1 — the outcome the
   Branch-2 comment itself calls "strictly worse than `already_complete`" because it restarts the lifecycle.
   This is exactly what Req 7 prescribes (the gate is unconditional), and reachability is narrow: it needs
   ¬H, a `merge_anchor: "merge"` working-tree row, `commit-artifacts: true`, a committable set, `main`, no
   `pr.json` at the verdict root, *and* a surviving worktree. But the spec's edge-case list analyses the
   Branch-2 retryable predicate and the Req-7 fall-through separately and never crosses them, and no test
   covers the crossing.

2. **`_reconstruct_pr_json` can materialise a directory tree under a wholly bogus root.** In
   `resolve_verdict_root`'s step-3 fallback the unvalidated root stands, and `_atomic_write_json` does
   `path.parent.mkdir(parents=True, exist_ok=True)`. So a Branch-3 single-match reconstruction under a wrong
   `CORTEX_REPO_ROOT` creates `{bogus}/cortex/lifecycle/{slug}/`. Pre-change it created the same tree under
   the real CWD root. Low severity (needs a wrong env var *and* exactly one live orphan PR), and step 3 is
   the spec's own accepted risk, but the side effect now lands somewhere the operator did not point at.

3. **`_find_slug_worktree` runs `git worktree list` against the process CWD, not `root`.** `_git_out` is
   called without `cwd`, matching `_current_branch`'s pre-existing style, and via `main()` the process CWD is
   always inside `root`'s tree — so production is fine. It does mean `classify(slug, root)` called directly
   with a `root` outside the process CWD consults the wrong repository for the gate. Pre-existing pattern;
   noting it because the gate is now a routing input rather than a message-formatting detail.

4. **`classify` can in principle raise where it previously could not.** `resolve_verdict_root` propagates
   `CortexProjectRootError` from its step-1 `resolve_main_repo_root()` call (only the CWD-walk branch is
   guarded), and `classify` does not catch it — unlike `record_pr_opened`, which does. Unreachable through
   `main()`: the preceding `_resolve_user_project_root_from_cwd()` must already have succeeded, and
   `_resolve_user_project_root`'s walk has identical termination semantics, so the never-crash contract
   holds. Recording it because the asymmetry between the two verbs is not obvious from the code.

Two minor items not worth changing: `_find_slug_worktree` runs a second `git worktree list` subprocess when a
gated fall-through later reaches `_resolve_worktree_path`, and `resolve_verdict_root` is re-derived on each
`classify` call. Both are one cheap local git call on a verb invoked once per Complete-phase step.

## Requirements Drift

- **State**: detected
- **Findings**:
  - `cortex/requirements/lifecycle.md:40` states that every machine verb resolves `events.log` through "the
    one pinned, worktree-aware resolver", with the flock-domain corollary following from that singularity.
    There are now two flavours: `resolve_events_log` (the appending verbs) and `resolve_verdict_root`
    (`complete-route`'s reads and both of `record-pr-opened`'s writes). They name the same physical path
    whenever the resolved root holds `cortex/lifecycle/{slug}`, and diverge — log path and flock domain
    together — when it does not.
  - `complete-route` now carries a second deliberate anchor (tree questions stay on the invoking checkout)
    and its `on_main` arm gained a worktree-absence precondition. Neither is captured; the closest existing
    statement, the worktree edge case at `:120`, describes only the typed-subcommand divergence.
- **Update needed**: `cortex/requirements/lifecycle.md`

## Suggested Requirements Update

- **File**: `cortex/requirements/lifecycle.md`
- **Section**: `### Served verb class`
- **Content**:

```
- A verb that reads shared lifecycle artifacts to reach a *verdict* resolves them through a slug-validated wrapper of the pinned resolver: the resolved root is trusted only when it holds `cortex/lifecycle/{slug}`, else the CWD walk wins, else the resolved root stands. This keeps a stale `CORTEX_REPO_ROOT` from making a live lifecycle read as fresh; the cost is that under an invalid root the wrapper's log path — and therefore its flock domain — can diverge from `resolve_events_log`'s.
- `complete-route` anchors twice on purpose: shared artifacts (`events.log`, `pr.json`) at the validated root, tree questions (`git show HEAD:`, `git status`, commit-artifacts config) at the invoking checkout. Its `on_main` finalize arm additionally requires that no `interactive/{slug}` worktree exists, so the pre-PR window falls through to the orphan probe rather than completing unmerged work.
```

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Req 2: the pr.json READ anchor is unpinned — reverting only `pr_json` to `root / \"cortex\" / \"lifecycle\" / slug / \"pr.json\"` while leaving events.log anchored leaves all 602 tests green (mutation M6). The requirement's second acceptance clause ('a second asserts classify from the primary finds it') has no test, and as written it could not fail anyway since from the primary the two roots coincide. Add one case that pins the discriminating direction: pr.json written at the main root, classify run from the worktree CWD, asserting Branch 4 is reached (e.g. pr_open) rather than the pr.json-absent arm — and confirm it fails under M6.", "Req 5: the rewritten test does not satisfy its own acceptance clause. `test_env_root_without_this_lifecycle_is_ignored` passes against all three production files reverted to 47797d42 (measured), so 'the rewritten test fails against unmodified complete_route.py' is unmet. It is unfalsifiable by construction — unmodified classify never read CORTEX_REPO_ROOT — because Req 2a's grounding claim ('measured today: resolve_main_repo_root() returns /nonexistent/bogus and the route is on_main/step9') is false for pre-change code. The test does discriminate against the mutation that matters (M4, the unvalidated anchor). No code change needed: correct the spec's Req 2a measurement and restate Req 5's acceptance against the unvalidated-anchor mutation, and add that framing to the test docstring so the next reader does not re-derive it.", "Stage 2, non-blocking: Req 7's gate crosses Branch 2's retryable fall-through in a case the spec analyses only separately. A retryable finalization on main with a live interactive/{slug} worktree and no pr.json now reaches the orphan probe and, on zero matches, first_run/step1 — restarting the lifecycle, which the Branch-2 comment itself calls strictly worse than already_complete. Pre-change it reached on_main/step9. Spec-conformant and narrow, but unanalysed and untested; worth either a pinning test or an explicit accepted-edge line.", "Stage 2, non-blocking: under resolve_verdict_root's step-3 fallback the unvalidated root stands, and _reconstruct_pr_json's _atomic_write_json does mkdir(parents=True), so a Branch-3 single-match reconstruction under a wrong CORTEX_REPO_ROOT materialises {bogus}/cortex/lifecycle/{slug}/. Low severity; noting because the side effect now lands somewhere the operator did not point at.", "Stage 2, non-blocking: classify() calls resolve_verdict_root() unguarded, which can propagate CortexProjectRootError from its step-1 resolve_main_repo_root() (only the CWD-walk branch is caught) — unlike record_pr_opened, which guards it. Unreachable via main() because the preceding _resolve_user_project_root_from_cwd() has identical walk semantics, so the never-crash contract holds today; the asymmetry is just not obvious from the code."], "requirements_drift": "detected"}
```
