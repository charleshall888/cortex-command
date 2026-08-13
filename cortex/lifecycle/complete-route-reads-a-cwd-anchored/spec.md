# Specification: complete-route reads a CWD-anchored events.log that #484 stopped writing to

## Problem Statement

`cortex-lifecycle-complete-route` decides a lifecycle's terminal routing by reading artifacts anchored to
the physical CWD, while the writers of those artifacts anchor elsewhere. The confirmed consequence: with a
PR open, the verb returns `pr_open` from the worktree but `on_main → step9` — the finalize leg — from the
primary, and nothing downstream of step9 re-checks PR state. A feature is marked complete, `feature_complete`
is emitted, artifacts are committed, and the worktree is orphaned, all silently, with the work unmerged.
The beneficiary is any operator running the Complete phase from the primary, which #475's worktree refusal
makes the sanctioned workaround. Not fixing it leaves a silent data-integrity failure on the one lifecycle
path whose whole job is deciding "is this actually done".

## Phases

- **Phase 1: Anchor reconciliation** — every artifact a verdict reads resolves where its writer writes it.
- **Phase 2: on_main guard** — the finalize short-circuit stops firing while the work lives in a worktree.

## Requirements

1. **The `events.log` verdict scan resolves through the pinned resolver.** `classify()`'s Branch-1/Branch-2
   scan reads `events.log` beneath the Req-2a slug-validated root — the same physical path
   `log_resolver.resolve_events_log(slug)` names whenever that root and `resolve_main_repo_root()` agree —
   not `root / "cortex" / "lifecycle" / slug / "events.log"`. Routing this read through Req 2a rather than
   calling `resolve_events_log` directly is what keeps the guard from being bypassed on the events.log leg.
   Acceptance: a test using `test_worktree_log_anchor.py`'s `_worktree_fixture` writes a
   `feature_complete` row to the **main-root** log only, runs `classify` from the worktree CWD, and asserts
   `route == "already_complete"`; the same test on unmodified code asserts today's `first_run`/`pr_unknown`.
   Grounding: `cortex_command/lifecycle/complete_route.py:530,538`. **Phase**: Anchor reconciliation

2. **`pr.json` resolves at the main root on both read and write.** `classify()`'s `pr_json` read
   (`complete_route.py:529,654`), the Branch-3 `_reconstruct_pr_json` write (`:267`), and
   `record_pr_opened.py`'s write (`:161`) all resolve against the Req-2a root rather than a CWD-anchored
   root. Acceptance: a test writes `pr.json` via `record_pr_opened` with CWD set to the worktree and asserts
   the file appears under the **main** root and not the worktree; a second asserts `classify` from the
   primary finds it. Grounding: `record_pr_opened.py:143,161`. **Phase**: Anchor reconciliation

2a. **The resolved root is slug-validated before it is trusted.** Both verbs resolve through one new
   `log_resolver` function that calls `resolve_main_repo_root()` and, when
   `{root}/cortex/lifecycle/{slug}` is not a directory, falls back to the CWD walk; if that also fails to
   produce a slug directory, the env result stands. This closes the case where an exported
   `CORTEX_REPO_ROOT` (which `docs/setup.md:66` instructs operators to set for exactly this shim family)
   points somewhere that does not hold this lifecycle — without which a nonexistent root returns verbatim
   (`interactive_lock.py:177-179`) and drives `on_main → step9`, the same finalize arm this spec exists to
   close. The check is slug-scoped, not a bare `cortex/` test, so a *different* cortex project is caught
   too. Acceptance: with `CORTEX_REPO_ROOT=/nonexistent/bogus` and a real lifecycle under the CWD tree,
   `classify` returns the CWD tree's verdict, not `on_main`; a second test points the env at a populated
   *other* project lacking this slug and asserts the same. Both fail on unmodified code — measured today:
   `resolve_main_repo_root()` returns `/nonexistent/bogus` and the route is `on_main`/`step9`.
   **Phase**: Anchor reconciliation

3. **`record_pr_opened`'s `pr_opened` append lands in the pinned log.** The raw `_append_event_atomic` call
   at `record_pr_opened.py:181` targets `log_resolver.resolve_events_log(feature)`, so the verb's two
   artifacts no longer land in two different trees. Acceptance: a test runs `record_pr_opened` from a
   worktree CWD and asserts the `pr_opened` row appears in the main-root `events.log` and that the worktree
   copy is absent or unchanged. **Phase**: Anchor reconciliation

4. **The tree-sensitive git probes keep the CWD root.** `_head_has_feature_complete` (`:290,295`) and
   `_finalization_committable` (`:358-361`) continue to resolve `root` via
   `_resolve_user_project_root_from_cwd()`, because both ask a question *about the invoking checkout* (which
   commit its HEAD points at; what is pending in its index) rather than reading a shared artifact.
   Acceptance: a test invoking `classify` from a worktree CWD asserts the two anchors **differ** within one
   call — the resolved `events.log`/`pr.json` parent is the main root while the `cwd` handed to
   `_head_has_feature_complete` is the worktree (assert on captured `_git_out` call arguments). This fails on
   unmodified code, where both are the same path. `tests/test_complete_route.py:1059-1099`
   (`test_branch2_nested_cortex_root_H_uses_show_prefix`) must also still pass, as a regression guard.
   **Phase**: Anchor reconciliation

5. **Req 7's superseded half is retired explicitly, not silently.** `tests/test_complete_route.py:753-796`
   (`test_worktree_cwd_resolution_ignores_env`) is rewritten against a real worktree fixture to assert the
   new anchoring, and its docstring names the supersession — Req 7 of
   `cortex/lifecycle/offload-completemd-pr-state-routing-and/spec.md:35` justified CWD resolution as matching
   "the `_resolve_user_project_root_from_cwd` contract `lifecycle_event` uses", and #484 moved that contract.
   Acceptance: `uv run pytest tests/test_complete_route.py -q` is green and the rewritten test fails against
   unmodified `complete_route.py`. **Phase**: Anchor reconciliation

6. **A worktree-existence predicate exists, distinct from path resolution.** The `interactive/{slug}`
   block-matching logic inside `_resolve_worktree_path` (`:133-153`) is extracted into a helper returning
   `Optional[str]` — the matched worktree path, or `None` when no such worktree exists.
   `_resolve_worktree_path` calls it and applies its existing `--show-toplevel` → `root` fallbacks, so its
   own behavior is unchanged. Acceptance: a test asserts the helper returns `None` when `git worktree list
   --porcelain` reports no matching block, while `_resolve_worktree_path` still returns a non-empty path for
   the same input. **Phase**: on_main guard

7. **`on_main` does not fire while a worktree for the slug exists.** The short-circuit at
   `complete_route.py:622-628` takes the `on_main` route only when `pr.json` is absent **and**
   `current_branch in ("main","master")` **and** the Req-6 predicate returns `None`. When a worktree exists,
   control falls through to the existing Branch-3 orphan probe rather than to a new route. Acceptance: a test
   with no `pr.json`, `current_branch` stubbed to `main`, and a worktree present asserts the route is **not**
   `on_main`; with no worktree present, `on_main → step9` still fires. The fall-through route must be one of
   the 12 already listed in the module docstring (`:34-48`) — assert it equals `first_run` for the zero-match
   probe, not a newly-minted value. **Phase**: on_main guard

## Non-Requirements

- **Not changing `interactive_lock._resolve_main_repo_root` itself.** Its env branch (`:177-179`) returns the
  value verbatim while its CWD branch (`:186`) guards on `(candidate / "cortex").is_dir()` — the env path is
  strictly less validated than the CWD path inside one function. Correcting that asymmetry would change
  behavior for every pinned verb, so Req 2a guards verb-locally instead, which carries no shared blast
  radius. The shared-resolver asymmetry is filed separately.
- **Not fixing `finalize.py`'s internal split.** `finalize.py:185` reads its idempotency scan and counters
  from the CWD log while `log_event` writes `feature_complete` to the main-root log, so a worktree run
  re-emits `feature_complete` on every invocation. Same root cause, different verb, own blast radius — filed
  separately.
- **Not reviving Branch 1.** `feature_wontfix`'s real producer (`wontfix_cli.py`) archives the directory
  before appending (`:194-196`) and refuses to run from a worktree at all, so `complete_route.py:566` is dead
  for its real producer irrespective of anchoring (corpus: 0 live rows, 19 archived). Not an anchoring defect
  — filed separately.
- **Not fixing `complete.md:23`'s escape hatch.** `cd $(git rev-parse --show-toplevel)` does not leave a
  worktree. Prose defect, filed separately.
- **Not introducing a `VerdictAnchors` object.** `log_resolver` already is the structural fix as a function;
  extending it to a second artifact is this change, not a new abstraction.
- **Not re-anchoring `review.md`, `plan.md`, or `register_artifact.py`.** Artifacts stay CWD-anchored per
  `b61c3abc`'s stated rule.
- **Not replacing the `on_main` short-circuit with an orphan probe.** Its exits make it a net regression:
  0 matches routes genuine direct-to-main work into `first_run` → `gh pr create`; an absent or offline `gh`
  yields `pr_unknown`, blocking offline completions; a stale same-name **merged** PR (`--state all`, `:637`)
  reconstructs `pr.json` and can reach `cleanup_worktree`, deleting a worktree and branch; and
  `orphan_ambiguous` becomes reachable with no correct answer. Req 6's predicate is local and offline.

## Edge Cases

- **A stale or nonexistent `CORTEX_REPO_ROOT` in an interactive session**: Req 2a catches it — the resolved
  root does not hold this slug's lifecycle directory, so resolution falls back to the CWD walk. The premise
  that this is rare does **not** hold and is not relied on: `docs/setup.md:66,158` instruct operators to
  export `CORTEX_REPO_ROOT` precisely to run the `cortex-*` shims from outside a project, and
  `cortex_command/cli.py:476` calls it "the unvalidated root funnel read by dozens of modules".
- **An exported `CORTEX_REPO_ROOT` pointing at a different project that *does* hold this slug**: not caught,
  and out of scope. This is the repo-wide property of the variable that ADR-0013 and `docs/dashboard.md:104`
  already govern; no lifecycle verb is immune to it, and making this one uniquely immune is what the CWD
  anchor did at the cost of the defect this spec fixes.
- **Overnight**: unaffected, because neither verb is reachable from any overnight process — `dispatch.py`'s
  closed `Skill` vocabulary (`:209-218`) has no `complete` arm, and no reference to `complete-route` or
  `record-pr-opened` exists under `cortex_command/overnight/` or `cortex_command/pipeline/`. The only
  invocation sites are `skills/build/references/complete.md:8` and `complete-first-run.md:28`, both
  interactive build-skill prose. (The env var carries three different values across the overnight tree —
  `runner.py:2902` and `:1964` pin the repo root, `dispatch.py:700` the worktree — which is why reachability,
  not the env pin, is the operative reason.)
- **A `pr.json` already sitting in a worktree from an earlier run**: it becomes invisible to the new read
  path. No migration — Branch 3's `_reconstruct_pr_json` regenerates it from `gh` at the new location, which
  is why warn-don't-heal is sufficient here and was not for `events.log`.
- **The pre-PR window** (`EnterWorktree` done, `gh pr create` not yet run) **with `gh` available**: no
  `pr.json` exists anywhere. Req 7 makes both trees fall through to the orphan probe, which returns 0 matches
  → `first_run` → step1, converging on "go create the PR" instead of diverging into finalize.
- **The pre-PR window with `gh` absent, unauthenticated, or offline**: `_orphan_probe` sets `error` and
  `classify` returns `_route_4a` — terminal `pr_unknown`, "retry later" (`complete_route.py:630-631`).
  Accepted: a terminal refusal the operator can retry is strictly better than today's silent finalize of
  unmerged work, and it fires only when a worktree for the slug exists. This is the one place Req 7 adds a
  network dependency; direct-to-main work without a worktree is untouched (the Req-6 predicate returns
  `None` before any probe).
- **Direct-to-main work with no worktree**: the Req-6 predicate returns `None`, so `on_main → step9` fires
  exactly as today. No network call is added to this path.
- **`git worktree list` unavailable or failing**: `_git_out` returns `None`; the predicate returns `None` and
  `on_main` fires as today. Failing open preserves the never-crash contract.
- **The Branch-2 retryable predicate stays tree-dependent** (`complete_route.py:604-612`): `complete_seen` and
  `pr_json` become main-root, while `_h` (Req 4) and `current_branch` stay CWD-anchored. Expected behavior
  post-merge: the primary sees `_h` true → `already_complete → step12`, the worktree sees `_h` false, falls
  through, and Branch 4 routes it on real PR state. `pr.json`'s move does not narrow this — the
  valid-retry-target disjunct already held from both trees. Accepted: closing it means Option B, which Req 4
  rejects for silently reclassifying the worktree population.

- **The destructive arm's authorization and its target resolve in different trees**: `pr.json` supplies
  `head_branch` from the main root, while `_resolve_worktree_path`, `status --porcelain`, and `merge-base
  --is-ancestor` run in the CWD tree and Step 8 deletes `f"interactive/{slug}"` — a name derived from the
  slug, never from the verified `head_branch` (`complete.md:27`). What keeps them consistent is that the
  ancestor probe runs locally, so a `head_branch` absent from the local tree returns non-zero and falls to
  the safe `merged_not_ancestor` terminal. That is currently an accident rather than a designed invariant;
  Req 7's test suite pins it with a case asserting a foreign `head_branch` cannot reach `step8`.

## Changes to Existing Behavior

- **MODIFIED** — `complete_route.classify()` resolves `events.log` and `pr.json` at the main root while
  keeping `root` (CWD) for `_head_has_feature_complete`, `_finalization_committable`,
  `_drift_files_from_review`, and `read_commit_artifacts`. Two anchors, deliberately, matching
  `review_brief.py:706-713`.
- **MODIFIED** — `record_pr_opened` writes `pr.json` and appends `pr_opened` at the main root.
- **MODIFIED** — the `on_main` short-circuit gains a worktree-absence condition.
- **MODIFIED** — `tests/test_complete_route.py::test_worktree_cwd_resolution_ignores_env` is rewritten; the
  behavior it pinned is deliberately superseded.
- **MODIFIED** — `log_resolver.py:34-36`'s docstring claim that `_resolve_user_project_root_from_cwd` is
  "what `log_event` uses for the *typed* subcommands" is false post-#484 and is corrected.
- **MODIFIED** — a main-root `pr.json` becomes visible to the dashboard. `poller.py:356` calls
  `parse_feature_pr_artifact` (`data.py:2043`) with the dashboard's own project root, never a worktree
  (`poller.py:215,262-279`), so a worktree-local file renders no PR link today (`feature_cards.html:125`);
  interactive completions of a slug the overnight state lists now render one. Today's placement is decided by
  the CWD (`record_pr_opened.py:143` → `_resolve_user_project_root_from_cwd`, documented at
  `common.py:129-131` as ignoring the env var), not by any env pin.
- **MODIFIED** — relocating the `pr_opened` row (Req 3) changes what three consumers see. The corpus is
  **5 live `events.log` files, 0 archived**. (a) `advance`'s merge-consent gate becomes live for the overnight
  review→complete arm: `outcome_router.py:1341,1768,2069` pass `lifecycle_base=_resolve_lifecycle_base()`
  (`common.py:112-123`, env-honouring → the main root in the batch-runner child per `runner.py:1964`), and
  `review_dispatch.py:331` hands that log to `advance(verb="review-verdict")`, whose `_consent_cross_check`
  (`advance.py:664-707`) refuses `review.approved` on a non-MERGED PR. Today a worktree-written row is
  invisible to that reader, so the gate fails open for that population; afterwards it fires. This is the gate
  behaving as designed, but it is a behavior change on a path this spec otherwise leaves alone.
  (b) `hooks/scan_lifecycle.py:832` anchors `lifecycle_dir = cwd / "cortex" / "lifecycle"` — strictly CWD —
  and `:1017-1027` promotes a feature to `complete:awaiting-merge` only when that log carries `pr_opened`, so
  the badge moves from worktree sessions to main-root sessions. Acceptance: a test asserts the promotion
  fires for a main-root session after `record_pr_opened` runs from a worktree. (c) the dashboard, above.
- **ADDED** — an `Optional`-returning worktree-existence helper, and the Req-2a slug-validated root resolver
  in `log_resolver`.

## Technical Constraints

- Never-crash contract (`lifecycle.md`, Non-Functional): every path exits 0 with a `{"state"/"route": …}`
  envelope; the new predicate must fail open rather than raise.
- **No new `route` value.** The enumeration stays at the 12 documented at `complete_route.py:34-48`; adding
  one would cost a new arm in `complete.md`'s closed if/elif dispatch. `project.md:61`'s "`route` may not be
  discriminated" rule is scoped to `common.py`'s resolvers and does not bind this field by the letter, but
  the cost it prices does apply.
- The verb has exactly one caller (`skills/build/references/complete.md:8` + plugin mirror), and
  `tests/test_complete_route.py:805-823` guards against new ones. No prose change is required by this spec —
  the route set is unchanged, so `complete.md`'s dispatch arms stay as they are.
- `pr.json` is never staged (`stage_artifacts.py:349-401`) and is not gitignored; it is runtime scratch, so
  moving it needs no migration and no `.gitignore` change.
- Editing `cortex_command/lifecycle/*` carries no dual-source mirror obligation; `skills/`-side files do.
  This spec touches no skill prose.

## Open Decisions

None.

## Proposed ADR

### Proposed ADR: 0038-pr-json-is-lifecycle-state-not-a-work-artifact

**Context.** `b61c3abc` (#484) established the rule that lifecycle *state* anchors at the main root while
work *artifacts* stay CWD-anchored ("the reviewer writes review.md where the work is"). It left `pr.json`
unclassified, and `complete_route` mixed a CWD-anchored `pr.json` into a verdict whose other input the same
commit had pinned. The two candidate readings are genuinely available: `pr.json` is produced during the
Complete phase in the worktree where the PR is opened (artifact-like), but it is consumed by a routing
decision, written once by a mechanical verb, and re-read by every later invocation from any tree
(state-like).

**Decision.** `pr.json` is lifecycle state and anchors at the main root, on both read and write, together
with the `pr_opened` event its writer emits. The classification test is *who must agree on it*: an artifact
is authored, read, and staged from one tree in one session; state is re-read by a later invocation that may
run from a different tree. `review.md` and `plan.md` remain artifacts under this test.

**Trade-off.** This supersedes the CWD half of Req 7 in
`cortex/lifecycle/offload-completemd-pr-state-routing-and/spec.md:35`, whose stated justification — matching
"the `_resolve_user_project_root_from_cwd` contract `lifecycle_event` uses" — was invalidated when #484 moved
that contract. Req 7's *env-ignoring* half is not superseded: Req 2a keeps a wrong `CORTEX_REPO_ROOT` from
steering a verdict by validating that the resolved root actually holds this slug's lifecycle.

Overnight is not a consideration either way — neither verb is reachable from any overnight process
(`dispatch.py:209-218` has no `complete` arm), so an env-ignoring resolver would have left overnight exactly
as untouched as this option does. The choice rests on the interactive population alone: one anchoring rule
shared with the writers, rather than a second resolver flavour that would diverge from `log_event` whenever
the operator has legitimately exported the variable per `docs/setup.md:66`.

The residual accepted is narrower than "a stale env var": an exported root pointing at a *different cortex
project that also holds this slug*. That is the repo-wide property of `CORTEX_REPO_ROOT` governed by
ADR-0013 and `docs/dashboard.md:104`, not something this verb should solve alone.
