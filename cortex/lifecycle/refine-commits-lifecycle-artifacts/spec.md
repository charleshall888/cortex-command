# Specification: refine-commits-lifecycle-artifacts

## Problem Statement

When `/cortex-core:lifecycle` delegates to `/cortex-core:refine`, refine produces `research.md` and `spec.md`, then returns. Refine SKILL.md §5 (line 169) explicitly delegates "commit-artifacts" to the caller (lifecycle), but lifecycle does not currently invoke any commit at the refine→plan boundary. Result: artifacts produced but never committed on the delegated path — they sit dirty in the working tree until the next phase's commit (`plan.md:306`) bundles them under a misnamed title, or until the user commits manually. This feature closes the gap: lifecycle invokes `/cortex-core:commit` after refine returns, honoring the existing §5 delegation rule and CLAUDE.md's "always commit via /cortex-core:commit" convention.

**Scope clarification**: Despite the slug `refine-commits-lifecycle-artifacts`, the actual commit responsibility lives in `/cortex-core:lifecycle`, not in `/cortex-core:refine`. This is a deliberate scope decision — refine SKILL.md §5 explicitly delegates commit-artifacts to the caller, so the fix lives at the caller layer. Standalone `/cortex-core:refine` invocations (not via lifecycle) remain uncommitted by this change; that path is a recognized residual exception to the CLAUDE.md "always commit via /cortex-core:commit" convention, deferred to a follow-up if a use case emerges. The slug is preserved for traceability with the user's original request phrasing.

Research also surfaced two adjacent cleanups in scope for this PR: (1) `specify.md:206`'s inline commit step is unreachable on the live invocation path (refine §5 overrides it; direct `/cortex-core:specify` is not a top-level entry point) — dead code worth deleting; (2) the `commit-artifacts` config flag is read by three LLM-prose-only consumers with no Python helper — adding a fourth consumer would multiply drift surface, so the helper gets extracted in the same PR.

## Phases

- **Phase 1: Helper consolidation** — Extract `read_commit_artifacts()` Python helper; route existing live consumers (`plan.md:306`, `complete.md:19`) through it; delete the dead `specify.md:206` inline commit step.
- **Phase 2: Post-refine commit wiring** — Add `skills/lifecycle/references/post-refine-commit.md` as the canonical commit site for the refine→plan boundary; wire `lifecycle/SKILL.md` Step 3 to invoke it after the `phase_transition specify→plan` row is logged (happy path) or after `lifecycle_cancelled` is logged (cancel path).

## Requirements

All 7 requirements below are **must-have** for this PR — the feature is tightly scoped and each requirement is load-bearing for either the user's original ask (R4-R6) or for one of the in-scope cleanups (R1-R3, R7). No should-have / nice-to-have layer exists at this scope; the won't-do items are explicit in the `## Non-Requirements` section.

1. **`read_commit_artifacts()` exists in `cortex_command/lifecycle_config.py`**: returns `True` when `cortex/lifecycle.config.md` is absent or its frontmatter omits the key (preserving the current default); returns the parsed boolean otherwise. Acceptance: `grep -c "def read_commit_artifacts" cortex_command/lifecycle_config.py` = 1, and a unit test in `tests/` asserts the three branches (absent file → True, key absent → True, key present with `false` → False). **Phase**: Helper consolidation.

2. **`plan.md:306` and `complete.md:19` read the flag via the helper**: their prose either invokes the helper directly via a `python3 -c` one-liner or invokes a `cortex-*` binstub wrapping the helper, replacing the existing prose-resident flag check. Acceptance: `grep -c 'read_commit_artifacts\|cortex-read-commit-artifacts' skills/lifecycle/references/plan.md skills/lifecycle/references/complete.md` ≥ 2, and the prior prose-resident `"If commit-artifacts is enabled in project config (default), stage cortex/lifecycle/{feature}/"` sentence is removed from both files. **Phase**: Helper consolidation.

3. **`specify.md:206`'s dead inline commit is removed**: the sentence `"If commit-artifacts is enabled in project config (default), stage cortex/lifecycle/{feature}/ and commit using /cortex-core:commit."` is deleted from `skills/lifecycle/references/specify.md`. Acceptance: `grep -c "commit-artifacts" skills/lifecycle/references/specify.md` = 0. **Phase**: Helper consolidation.

4. **`skills/lifecycle/references/post-refine-commit.md` exists and documents the contract behaviorally**: encapsulates the post-refine commit step including (a) preconditions (refine has returned; either `phase_transition specify→plan` is the most recent event since the last commit, OR `lifecycle_cancelled` is the most recent event since the last commit); (b) the staging instruction (helper-driven flag check, then commit via `/cortex-core:commit`); (c) **the halt-before-Plan gate** — explicit prose stating that on commit failure the orchestrator MUST surface the error and NOT auto-advance to Plan, so that the stranded `phase_transition` row is resolved by the user's next invocation rather than re-introduced into a Plan-titled commit; (d) the cancel-path commit subject contract (see R6). Acceptance: `test -f skills/lifecycle/references/post-refine-commit.md` exits 0; the file references `read_commit_artifacts` (or the binstub) and `/cortex-core:commit`; `grep -ci "halt\|do not auto-advance\|do not advance" skills/lifecycle/references/post-refine-commit.md` ≥ 1 (the gate is documented); `grep -ci "precondition\|since the last commit" skills/lifecycle/references/post-refine-commit.md` ≥ 1 (the precondition rule is documented). **Phase**: Post-refine commit wiring.

5. **Lifecycle SKILL.md Step 3 invokes `post-refine-commit.md` on the happy path**: after the `phase_transition from=specify to=plan` row is logged (current line ~154), the trunk reads `references/post-refine-commit.md` and follows it. Acceptance: `grep -c "post-refine-commit" skills/lifecycle/SKILL.md` ≥ 1, AND a new integration-style test at `tests/test_post_refine_commit_wired.py` (or extension of an existing lifecycle test) asserts the trunk text references `post-refine-commit.md` in the Step 3 §4 region by reading the file and checking the substring appears after the `phase_transition` event-logging block; `just test` exits 0 with the new assertion included. End-to-end refine→commit behavior is "Interactive/session-dependent: a full refine invocation requires user input at the spec approval surface and is not amenable to a single-command check; the substring assertion plus the existing `/cortex-core:commit` skill's own tests are the binary-checkable surface." **Phase**: Post-refine commit wiring.

6. **Cancel path commits with a distinct subject; detection is "most recent event since last commit"**: `post-refine-commit.md` instructs the orchestrator to compose a commit subject distinguishing the cancel path from the approval path (e.g., `Refine {feature}: cancelled at spec approval` vs. `Refine {feature}: research and spec`). **The detection rule is unambiguous: the orchestrator inspects only the most recent significant event in `events.log` since the most recent commit on the current branch; if that event is `lifecycle_cancelled` the cancel subject fires, otherwise the approval subject fires.** The "since last commit" qualifier prevents historical `lifecycle_cancelled` rows from misclassifying later approval commits in multi-cycle cancel→resume→cancel flows. Acceptance: `grep -ci "since the last commit\|since last commit\|most recent" skills/lifecycle/references/post-refine-commit.md` ≥ 1 AND `grep -ci "cancelled\|cancel" skills/lifecycle/references/post-refine-commit.md` ≥ 1 — both grep targets must hit; the file documents both the subject distinction AND the detection rule. **Phase**: Post-refine commit wiring.

7. **Existing tests pass; new tests cover the helper**: `just test` exits 0 after the changes. A new `tests/test_lifecycle_config_commit_artifacts.py` (or extension of an existing test file) asserts `read_commit_artifacts()`'s three branches. Acceptance: `just test` exits 0; `grep -c "read_commit_artifacts" tests/` ≥ 1. **Phase**: Helper consolidation.

## Non-Requirements

- Does NOT modify `skills/refine/SKILL.md`. The §5 delegation rule stays as written.
- Does NOT add new event types to `bin/.events-registry.md` (no `commit_authored`, `artifacts_committed`, `commit_failed`).
- Does NOT add hook preflight, retry-on-failure, or SHA-based idempotency. The orchestrator + `/cortex-core:commit` are trusted to handle the commit sensibly in context — except for the explicit halt-before-Plan gate in R4, which IS documented in skill prose so the agent has a deterministic procedure on commit failure.
- Does NOT add new `AskUserQuestion` sites; the kept-pauses inventory at `skills/lifecycle/SKILL.md:195-209` and `tests/test_lifecycle_kept_pauses_parity.py` remain unchanged.
- Does NOT change `/cortex-core:refine`'s standalone (non-lifecycle) invocation behavior. Standalone refine still doesn't commit. The Problem Statement's scope clarification documents this residual exception.
- Does NOT extend auto-commit to lifecycle phase boundaries that don't already have one (Plan and Complete already commit; Implement and Review are out of scope here).
- Does NOT alter the `commit-artifacts` flag's semantics or default value (still `true`).
- Does NOT change the artifact-staging granularity at `plan.md:306` or `complete.md:19`; those continue to stage `cortex/lifecycle/{feature}/` as today, just via the new helper for the flag check.
- Does NOT define a slug-reuse, cancellation-cleanup, or lifecycle-directory archival policy. Cancel commits are durable git history; if the user wants to abandon a cancelled lifecycle and reuse the slug, that is currently handled by manual `git mv` to `archive/` (see existing `skills/lifecycle/references/wontfix.md` precedent) — formalizing the workflow is a follow-up.
- Does NOT reset the originating backlog item's `status: in_progress` on cancel. A cancelled refine is treated as a paused/resumable state (the user can re-invoke `/cortex-core:lifecycle` to continue), not as abandonment. If the user wants to mark the backlog item abandoned, they invoke `cortex-update-item --status wontfix` (or equivalent) explicitly.

## Edge Cases

- **Cancel at spec approval surface**: refine emits `lifecycle_cancelled` to `events.log` and halts. The lifecycle orchestrator then invokes `post-refine-commit.md`, which detects `lifecycle_cancelled` as the most recent event since the last commit and composes the distinct cancel subject from R6. Research.md, index.md (with `artifacts: ["research"]` — see edge case below), and the partial events.log (including `lifecycle_cancelled`) get committed. Spec.md is absent. The backlog item retains its pre-cancel `status: in_progress` per the non-requirement above. Lifecycle does NOT auto-advance to Plan.

- **Resume after a prior cancelled (and committed) refine**: refine's Step 2 sees `research.md` exists but `spec.md` does NOT — refine re-enters the spec phase, produces a new `spec.md`, and the user approves it (or cancels again). When `post-refine-commit.md` fires on the new approval, R6's "most recent event since last commit" detection rule correctly identifies the new `phase_transition specify→plan` event (not the older `lifecycle_cancelled`) and composes the approval subject. If the user cancels again, a new `lifecycle_cancelled` event becomes the most recent and triggers another cancel commit.

- **Resume after a prior approved (and committed) refine**: refine's Step 2 sees both `research.md` and `spec.md` exist; refine skips to its Step 6 (Completion) without re-emitting `phase_transition` rows. Lifecycle's Step 3 §4 detects no new phase_transitions need logging and post-refine-commit.md is no-op (nothing changed since the last commit, so the orchestrator silently proceeds to Plan).

- **index.md shape on cancel**: refine appends `"research"` to `index.md`'s `artifacts` array after research.md is written, but only appends `"spec"` after the user approves the spec (per refine SKILL.md §5). On the cancel path, `index.md` therefore commits with `artifacts: ["research"]` only — coherent with research.md being on disk and spec.md being absent. The orchestrator does not need to special-case index.md; refine's existing append-timing produces the correct shape.

- **Refine invoked inside `Agent(isolation: "worktree")`**: the commit fires in the worktree's index, not the parent. Lifecycle's existing worktree handling owns the merge-back to the parent (out of scope here).

- **Worktree contains a failed commit (dirty `events.log` + stranded `phase_transition` row)**: if the post-refine commit failed and the user did not resolve before the worktree handler runs, the handoff path inherits a dirty events.log with an uncommitted `phase_transition` row. Per the halt-before-Plan gate in R4, lifecycle should not have advanced to Plan in this state — so this scenario is reachable only if the user explicitly continues past the halt. The worktree handler's existing dirty-state semantics apply; resolving the orphan row is the user's responsibility per the halt-before-Plan contract.

- **Concurrent refine sessions in different worktrees**: each session commits its own touched files in its own worktree's index. Cross-worktree contention is bounded by git's per-worktree index — no special locking needed.

- **`commit-artifacts: false` in `cortex/lifecycle.config.md`**: post-refine-commit.md reads the flag via the helper and skips the commit silently. Same behavior as today's `plan.md:306` and `complete.md:19`.

- **Commit failure (index lock, hook rejection, working-tree conflict)**: `/cortex-core:commit` surfaces the error as it would in any other context. **Per the halt-before-Plan gate in R4, the orchestrator MUST surface the failure and NOT auto-advance to Plan.** The stranded `phase_transition` row sits in the uncommitted working tree until the user resolves the issue (resolve the conflict, re-run `/cortex-core:commit`, or revert) and re-invokes `/cortex-core:lifecycle`. On re-invocation, lifecycle's resume routing detects the working state and offers continuation. The halt gate is what prevents the failure path from re-creating the "misnamed bundling" defect the spec opens by condemning — without the halt, plan.md:306's later commit would bundle the stranded refine row under a "Plan {feature}" subject, recreating the dysfunction.

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/SKILL.md` Step 3 §4 — after the `phase_transition specify→plan` row is logged (or `lifecycle_cancelled` on the cancel path), reads `references/post-refine-commit.md` and follows it.
- **MODIFIED**: `skills/lifecycle/references/plan.md:306` and `skills/lifecycle/references/complete.md:19` — the prose-resident `commit-artifacts` flag check is replaced with a helper invocation (no user-visible behavioral change).
- **REMOVED**: `skills/lifecycle/references/specify.md:206` — the unreachable inline commit step.
- **ADDED**: `skills/lifecycle/references/post-refine-commit.md` — the canonical commit site for the refine→plan boundary, including the halt-before-Plan gate.
- **ADDED**: `cortex_command/lifecycle_config.py:read_commit_artifacts()` — Python helper for the `commit-artifacts` flag, callable from any consumer.
- **ADDED**: one new commit per refine completion on the previously-uncovered delegated path (or per refine cancellation, with a distinct subject). Total per-feature commit count rises from N-1 to N (one new commit), matching the intended granularity at `plan.md:306` and `complete.md:19`.

## Technical Constraints

- All commits must flow through `/cortex-core:commit` (`CLAUDE.md:40`).
- Lifecycle owns `cortex/lifecycle/{feature}/events.log`; the relevant event row (`phase_transition specify→plan` on approval, or `lifecycle_cancelled` on cancel) must be appended *before* the commit fires, so the commit captures it.
- The helper `read_commit_artifacts()` reads `cortex/lifecycle.config.md` frontmatter only — no other sources of truth. Defaults to `True` on absent file or absent key, matching the current prose-resident logic at `plan.md:306` and `complete.md:19`.
- Helper invocation pattern in skill prose: either `python3 -c "from cortex_command.lifecycle_config import read_commit_artifacts; ..."` or a dedicated `cortex-*` binstub. The binstub form is preferred for parity with other `cortex-*` helpers (see `cortex/requirements/project.md:33-35` skill-helper-module pattern); creating the binstub is permissible additional scope but the spec does not require it.
- The new reference must not introduce a `phase_transition` event of its own; lifecycle's Step 3 §4 owns that row, and `post-refine-commit.md` runs *after* it.
- The halt-before-Plan gate is encoded in skill prose (per R4 acceptance), not in a hook or programmatic interrupt. The gate is enforced by the orchestrator following the documented procedure on commit failure.
- No new `AskUserQuestion` calls. The kept-pauses parity test at `tests/test_lifecycle_kept_pauses_parity.py` must continue to pass without inventory updates.

## Open Decisions

None — all interview and critical-review questions resolved.

## Proposed ADR

None considered.
