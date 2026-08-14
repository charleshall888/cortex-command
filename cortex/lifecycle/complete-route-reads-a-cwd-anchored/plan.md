# Plan: complete-route-reads-a-cwd-anchored

## Overview

Split `classify()`'s single root into two deliberate anchors — shared artifacts (`events.log`, `pr.json`)
at a slug-validated main root, tree-questions (`git show HEAD:`, `git status`) at the CWD root — then stop
the `on_main` finalize short-circuit from firing while a worktree for the slug exists. The validation step
is what keeps the new anchor from re-opening the same finalize arm under a stale `CORTEX_REPO_ROOT`.

**Architectural Pattern**: layered
<!-- One resolver layer beneath both verbs; neither verb re-derives a root. -->

## Outline

### Phase 1: Anchor reconciliation (tasks: 1, 2, 3)
**Goal**: every artifact a verdict reads resolves where its writer writes it, and a wrong root cannot steer
the verdict.
**Checkpoint**: `classify` run from a worktree and from the primary returns the same route for the same
lifecycle; a bogus `CORTEX_REPO_ROOT` no longer produces `on_main`.

### Phase 2: on_main guard (tasks: 4, 5)
**Goal**: the finalize leg stops firing while the work lives in a worktree.
**Checkpoint**: with no `pr.json`, `current_branch == main`, and a worktree present, the route is not
`on_main`; with no worktree it still is.

## Tasks

### Task 1: Add the slug-validated root resolver and correct the stale docstring
- **Files**: `cortex_command/lifecycle/log_resolver.py`,
  `cortex_command/lifecycle/tests/test_log_resolver.py`
- **What**: Add one public function resolving the root a verdict may trust: call `resolve_main_repo_root()`,
  and when `{root}/cortex/lifecycle/{slug}` is not a directory, fall back to the CWD walk; if that also
  yields no slug directory, the env result stands. Correct the module docstring's claim that
  `_resolve_user_project_root_from_cwd` is "what `log_event` uses for the *typed* subcommands" — false since
  #484 routed every typed subcommand through `log_event` -> `resolve_events_log`.
- **Depends on**: none
- **Complexity**: moderate
- **Context**: Existing members are `resolve_main_repo_root`, `resolve_events_log`, `resolve_flock_path`,
  `detect_split_log`; add to `__all__`. The env branch it wraps is `interactive_lock.py:177-179`
  (`return Path(env_root).resolve()`, unchecked); the CWD flavour to fall back to is
  `common._resolve_user_project_root_from_cwd`, which raises `CortexProjectRootError` — catch it, never let
  it escape (never-crash contract). Slug-scoped, not a bare `cortex/` test, so a *different* cortex project
  that lacks this lifecycle is also rejected. Stale docstring text is at `log_resolver.py:34-36`.
  `test_log_resolver.py` already builds a synthetic worktree fixture for this module — extend it.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_log_resolver.py -q` passes with new
  cases asserting (i) a bogus `CORTEX_REPO_ROOT` is rejected in favour of the CWD tree holding the slug, and
  (ii) a valid env root that *does* hold the slug is still honoured. Both fail before this task.
- **Status**: [x] done (eb62bbab 2026-08-13T20:10:39-04:00) — public name is `resolve_verdict_root`

### Task 2: Split `complete_route`'s single root into two deliberate anchors
- **Files**: `cortex_command/lifecycle/complete_route.py`, `tests/test_complete_route.py`
- **What**: Resolve `events.log` and `pr.json` beneath Task 1's validated root while
  `_head_has_feature_complete`, `_finalization_committable`, `_drift_files_from_review`, and
  `read_commit_artifacts` keep the CWD root. Update the module docstring, which currently states the CWD
  choice as deliberate. Rewrite the one existing test that pins the superseded behaviour.
- **Depends on**: [1]
- **Complexity**: moderate
- **Context**: `main()` resolves one root at `:684` and hands it to `classify(slug, root)`, which derives
  `lifecycle_dir` at `:528`; both `pr_json` (`:529`) and `events_log` (`:530`) descend from it, and
  `_reconstruct_pr_json` writes beneath it (`:267`). `classify`'s signature stays `(slug, root)` — `root`
  keeps meaning *the invoking checkout*; the artifact anchor is resolved inside. Precedent for the
  two-anchor shape and the comment style to match: `review_brief.py:706-713`. Docstring to update:
  `complete_route.py:26-30`. Do NOT re-anchor `root` wholesale — `_head_has_feature_complete` asks which
  commit *this tree's* HEAD points at (`git show HEAD:`, `cwd=root`, `:290,295`), and
  `tests/test_complete_route.py:1059-1099` pins that meaning and must keep passing. The test to rewrite is
  `tests/test_complete_route.py:753-796` (`test_worktree_cwd_resolution_ignores_env`, "Req 7" heading at
  `:741`); its `_setup_worktree` (`:745-750`) points a gitfile at a nonexistent path, which is why
  resolution falls through to the env value — replace it with `_worktree_fixture` from
  `cortex_command/lifecycle/tests/test_worktree_log_anchor.py:30-43`. Name the supersession in its
  docstring: Req 7 of `cortex/lifecycle/offload-completemd-pr-state-routing-and/spec.md:35` justified CWD
  resolution as matching "the `_resolve_user_project_root_from_cwd` contract `lifecycle_event` uses", and
  #484 moved that contract; Req 7's *env-ignoring* intent survives via Task 1's validation.
- **Verification**: `uv run pytest tests/test_complete_route.py -q` passes (baseline 36) with a new case
  asserting the two anchors *differ* within one `classify` call from a worktree CWD — capture `_git_out`
  arguments and compare the `cwd` handed to `_head_has_feature_complete` against the resolved artifact
  parent. That case fails on unmodified source, where both are the same path.
- **Status**: [x] done (a9cba2d4 2026-08-13T20:15:56-04:00) — a second test also pinned the superseded
  behaviour (`test_branch2_stale_git_file_no_traceback`) and was minimally re-fixtured; `_setup_worktree`
  was kept, not replaced, because the stale-marker degradation case needs it

### Task 3: Anchor `record_pr_opened`'s two artifacts to one tree
- **Files**: `cortex_command/lifecycle/record_pr_opened.py`,
  `cortex_command/lifecycle/tests/test_record_pr_opened.py`
- **What**: Resolve the `pr.json` write and the raw `pr_opened` append through Task 1's validated root so the
  verb stops writing its two artifacts to two different trees.
- **Depends on**: [1]
- **Complexity**: moderate
- **Context**: **Callers and pinning tests, enumerated**: the only production caller is the module's own
  `main` (`:224`); `test_record_pr_opened.py` holds ~15 cases, all but one passing `project_root=tmp_path`
  (which must keep winning over resolution, so they are unaffected) — the exception is `:233`,
  `project_root=None`, which exercises the resolution path and needs the worktree fixture. Two further tests
  reference this module, must be re-run, and should not need edits:
  `tests/test_events_log_writer_census.py:58` allowlists it as a sanctioned raw writer *because it uses the
  shared `_append_event_atomic` primitive* — keep that call and change only the path handed to it, or the
  allowlist entry becomes a stale hit and the census fails; `tests/test_complete_feature_complete_emission.py:274,310-315`
  pins its continued existence. `root = project_root or _resolve_user_project_root_from_cwd()` (`:143`) feeds
  `lifecycle_dir`, used by both `_atomic_write_json(lifecycle_dir / "pr.json", ...)` (`:161`) and
  `_append_event_atomic(lifecycle_dir / "events.log", ...)` (`:181`). The `project_root` parameter is a
  caller override and must keep winning when passed. This verb imports `_atomic_write_json`, `_gh_repo`,
  `_run` from `complete_route` (`:69`) — an import edge, not a write edge, so it does not serialize against
  Task 2. `pr_opened` is an ADR-0020 hand-written exempt row: preserve its exact key set and order; only the
  path changes.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_record_pr_opened.py tests/test_events_log_writer_census.py -q`
  passes with a new case asserting both `pr.json` and the `pr_opened` row land under the main root when the
  verb runs from a worktree CWD, with the worktree copies absent. Fails before this task.
- **Status**: [x] done (b747a53b 2026-08-13T20:13:58-04:00)

### Task 4: Extract a worktree-existence predicate and gate the `on_main` short-circuit on it
- **Files**: `cortex_command/lifecycle/complete_route.py`, `tests/test_complete_route.py`
- **What**: Extract the `interactive/{slug}` block-matching logic into a helper returning `Optional[str]`
  (the matched path, or `None`), have `_resolve_worktree_path` call it and apply its existing fallbacks
  unchanged, then add "and the predicate returns `None`" to the `on_main` short-circuit so a worktree-present
  lifecycle falls through to the existing Branch-3 orphan probe instead of the finalize leg. Pin the two
  edges the spec accepts with rationale.
- **Depends on**: [2] (write-serialization: complete_route.py)
- **Complexity**: moderate
- **Context**: The matching loops are `complete_route.py:133-153`; `_resolve_worktree_path` has three call
  sites, all in this file (`:400`, `:468`, `:500`), and must keep returning non-empty (it falls back to
  `--show-toplevel`, then `root`) because the 4d/4f dirty/ancestor guards depend on a real path. The
  short-circuit is `:622-628`, currently conjunctive on `not pr_json.is_file()` and `current_branch in
  ("main","master")`. Add **no** new `route` value — the fall-through lands on the existing `first_run` /
  `orphan_ambiguous` / Branch-4 arms. `_git_out` returns `None` on failure; the predicate must fail open
  (return `None`, so `on_main` fires as today). Accepted edges to pin: (i) with a worktree present, no
  `pr.json`, and `shutil.which("gh")` stubbed to `None`, the route is terminal `pr_unknown` —
  `_orphan_probe` sets `error` and `classify` returns `_route_4a` (`:630-631`); this is the cost of the
  guard, not a defect, since a retryable refusal beats silent finalize. (ii) a `head_branch` absent from the
  local tree cannot reach `step8` — `merge-base --is-ancestor` returns non-zero and the route is
  `merged_not_ancestor`; that local probe is the only thing keeping an artifact-anchored authorization
  consistent with a CWD-anchored deletion target (`complete.md:27` deletes `f"interactive/{slug}"`, a name
  derived from the slug, never from the verified `head_branch`), so pin it rather than leave it accidental.
  This task also writes `tests/test_complete_route.py`, which Task 2 edits — hence the serialization edge.
- **Verification**: `uv run pytest tests/test_complete_route.py -q` passes with cases asserting (a) the
  predicate returns `None` for a `git worktree list` output with no matching block while
  `_resolve_worktree_path` still returns non-empty for the same input; (b) with no `pr.json`,
  `_current_branch` stubbed to `main`, and a worktree present, the route is not `on_main`; (c) with no
  worktree present, `on_main` / `step9` still fires; plus the two accepted edges above. Each fails before
  this task.
- **Status**: [x] done (d257db63 2026-08-13T20:20:24-04:00) — predicate is `_find_slug_worktree`. Correction
  to this task's own Verification: "each fails before" is false for case (c), a negative control, and for
  accepted edge (ii), a characterization pin of existing behaviour the spec asks to pin rather than change.
  Mutation check on the rest: 5 failed / 39 passed at HEAD.

### Task 5: Pin the cross-verb worktree behaviour in the #484 suite
- **Files**: `cortex_command/lifecycle/tests/test_worktree_log_anchor.py`
- **What**: Extend the suite #484 shipped with the two end-to-end cases that span both verbs — the reader
  now seeing what the writers wrote, and the relocated `pr_opened` row's downstream consumer.
- **Depends on**: [2, 3]
- **Complexity**: moderate
- **Context**: The fixture to reuse is `_worktree_fixture` (`:30-43`) with its `worktree` fixture (`:56-61`),
  which chdirs into the worktree and clears `CORTEX_REPO_ROOT`. Case (a): write `feature_complete` via
  `lifecycle_event.log_event` from the worktree CWD — the path `finalize.py:198` uses — then assert
  `complete_route.classify(...)["route"] == "already_complete"`; today it returns `pr_unknown`, which is the
  surviving events.log defect. Case (b): after `record_pr_opened` runs from the worktree, assert
  `hooks/scan_lifecycle.py` promotes the feature to `complete:awaiting-merge` for a main-root session —
  `:832` anchors `lifecycle_dir = cwd / "cortex" / "lifecycle"` (strictly CWD, no worktree awareness) and
  `:1017-1027` gates promotion on a `pr_opened` row with neither `feature_complete` nor `feature_wontfix`.
  Do **not** re-anchor `scan_lifecycle.py` — #494 owns that and is blocked on this landing; this pins the
  shift, it does not fix it.
- **Verification**: `uv run pytest cortex_command/lifecycle/tests/test_worktree_log_anchor.py -q` passes;
  case (a) fails when Task 2 is reverted and case (b) when Task 3 is reverted.
- **Status**: [x] done (41daa6b4 2026-08-13T20:21:51-04:00) — both reverts confirmed in a throwaway
  worktree; a self-sealing precondition in case (b) was found and closed with an explicit assertion

## Risks

- **Task 1's fallback ordering is a judgment call the spec fixed but the implementer will feel.** When both
  the env root and the CWD walk fail to produce a slug directory, the env result stands rather than raising.
  That keeps the never-crash contract and preserves today's behavior for a genuinely new lifecycle, but it
  means a wholly bogus env var still reaches the read — the read simply finds nothing, exactly as today.
- **Task 3 changes where 5 live lifecycles' `pr_opened` rows are written from here on.** Existing rows are
  not migrated; the spec's warn-don't-heal position (Branch 3 regenerates `pr.json` from `gh`) is what makes
  that safe. If migration turns out to be wanted, it is a separate ticket, not a scope expansion here.
- **The `scan_lifecycle` badge shift (Task 5b) is user-visible** and deliberately not fixed here — #494
  carries it and is blocked on this landing.

## Acceptance

Running `cortex-lifecycle-complete-route <slug>` from the primary and from the lifecycle's worktree returns
the same `route` for the same lifecycle, in each of: PR open, feature complete, and no PR yet. A bogus
`CORTEX_REPO_ROOT` no longer yields `on_main`. `uv run pytest tests/test_complete_route.py
cortex_command/lifecycle/tests/ -q` is green with the new cases, each failing when its production change is
reverted.
