# Research: refine-commits-lifecycle-artifacts

When `/cortex-core:lifecycle` delegates to `/cortex-core:refine` and refine returns with `research.md` + `spec.md` produced and approved, the lifecycle orchestrator must commit the refine-produced artifacts plus any Context A backlog write-back in a single commit authored via `/cortex-core:commit`. Refine itself stays unchanged. Honors the existing §5 delegation rule placing commit-artifacts ownership with the caller, and CLAUDE.md's "always commit via /cortex-core:commit" convention. Context B (no backlog item) commits just the artifacts.

## Codebase Analysis

### Control-flow point — where refine returns to lifecycle

- `skills/lifecycle/SKILL.md:128-159` — the `/cortex-core:refine` delegation block (Step 3).
  - Lines 144-155: lifecycle owns `events.log` writes during delegation and emits `phase_transition` events at clarify→research, research→specify, specify→plan boundaries.
  - Line 154 specifically: lifecycle logs the `phase_transition from=specify to=plan` row after refine returns with spec_approved.
  - Line 159: after refine completes, lifecycle proceeds directly to the Plan phase.

### Existing commit pattern (precedent — but dead on the delegated refine path)

Three phases already implement a `commit-artifacts` step inline at their §5 (Transition) reference:

- `skills/lifecycle/references/specify.md:206` — `"If commit-artifacts is enabled in project config (default), stage cortex/lifecycle/{feature}/ and commit using /cortex-core:commit."`
- `skills/lifecycle/references/plan.md:306` — identical wording.
- `skills/lifecycle/references/complete.md:19` — `"Stage cortex/lifecycle/{slug}/ artifacts alongside any uncommitted source changes, then use /cortex-core:commit to create the commit. If cortex/lifecycle.config.md specifies commit-artifacts: false, exclude lifecycle artifacts from staging."`

**Critical**: `skills/refine/SKILL.md:169` (refine's §5 adaptation):
> "Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; the caller (/cortex-core:lifecycle) owns phase-transition logging **and commit-artifacts**."

This sentence couples two skips: the `phase_transition` emission **and** the `commit-artifacts` step from specify.md §5. Because all top-level Spec invocations today flow through `/cortex-core:refine` (refine subsumed direct `/cortex-core:specify`), specify.md:206's commit step is dead on the live invocation path. The proposed feature is closing that gap on the orchestrator side, not adding new behavior — the dead inline commit is what's currently missing.

### Artifact set written during refine

- `cortex/lifecycle/{feature}/research.md` — written by `/cortex-core:research` during refine Step 4.
- `cortex/lifecycle/{feature}/spec.md` — written at refine Step 5 after user approval.
- `cortex/lifecycle/{feature}/index.md` — created at lifecycle start (`references/backlog-writeback.md:37-71`); refine appends `"research"` and `"spec"` to the `artifacts` array (refine SKILL.md:145-149, 174-178).
- `cortex/lifecycle/{feature}/events.log` — appended during the full refine flow.
- `cortex/backlog/{NNN}-{slug}.md` — **Context A only**: refine Step 3 writes complexity/criticality; refine Step 5 writes `status: refined`, `spec`, and `areas` via `cortex-update-item` (refine SKILL.md:184-196).

### Commit skill contract

- `skills/commit/SKILL.md` — invoked via Skill tool; uses `cortex-commit-preflight` to snapshot status/diff/recent commits; stages explicit files (no `-A`); commits with imperative-mood message ≤72 chars. PreToolUse hook validates messages.
- No machine-readable `--paths` argument — staging scope is conveyed via prose in the caller's context.

### Skill-to-skill invocation pattern

- Composition is orchestrator-driven via the Skill tool (no first-class skill-calls-skill API).
- Existing examples in this repo: refine SKILL.md:108-114 invokes `/cortex-core:research`; lifecycle SKILL.md:140 invokes `/cortex-core:refine`.

### Config: `commit-artifacts`

- `cortex/lifecycle.config.md:6` — `commit-artifacts: true` (default).
- **No Python reader exists** for this flag — `cortex_command/lifecycle_config.py` exposes only `read_branch_mode()`. The four prose-resident consumers (specify.md, plan.md, complete.md, and the proposed new reference) would each re-implement the flag check independently.

### Test scaffolding

- `tests/test_lifecycle_kept_pauses_parity.py` enforces that every `AskUserQuestion` call site has a matching inventory entry in `skills/lifecycle/SKILL.md` (±35-line tolerance). Adding a new `AskUserQuestion` site requires updating the inventory.
- No existing integration test asserts commit state at phase boundaries.

## Web Research

### Prior art for auto-commit at workflow phase transitions

- **Checkpoint-commit pattern** (git-checkpoint, Claude Code git-checkpoint skill, GitHub Actions auto-commit) — well-established for agent-emitted artifacts. Treats agent commits as save-points; small atomic scope; conventional messages.
- **GitHub Actions `stefanzweifel/git-auto-commit-action`** — explicitly scope what gets staged (`file_pattern`), tolerate no-op commits, avoid infinite-loop re-triggers.
- **Argo / Temporal artifact emission** — both engines treat artifact persistence as a *named state transition*, not a hidden side effect of the worker. Lesson: the commit should be a named transition of the lifecycle state machine, auditable in the event log.

### Skill composition

- Anthropic skills compose via orchestrator invocation. There is no first-class "skill calls skill" API; multi-step patterns are orchestrator-driven. The proposed design (lifecycle orchestrates refine and then commit) matches the canonical pattern.

### Failure semantics

- **Temporal failure-handling guide**: distinguish retryable (file lock, dirty index from race) from non-retryable (hook rejection, merge conflict). Exponential backoff for retryables; surface non-retryables immediately with a clear failure event in the workflow log. Don't auto-rollback partial multi-file state — leave artifacts on disk for human triage ("break, don't rollback").

### Patterns to adopt / avoid

- **Adopt**: explicit file manifest of what to stage (mirrors Argo's `outputs.artifacts`); events.log F-row on commit success/failure for auditability.
- **Avoid**: `git add -A`, silent no-op when nothing changed, auto-rollback on commit failure.

## Requirements & Constraints

- `CLAUDE.md:40` — "Always commit using the `/cortex-core:commit` skill -- never run `git commit` manually." Foundational constraint: commits flow through the commit skill.
- `skills/refine/SKILL.md:169` — refine explicitly delegates commit-artifacts to the caller. The proposed feature implements what this delegation requires.
- `skills/lifecycle/SKILL.md:144` — "lifecycle owns `cortex/lifecycle/{feature}/events.log`." Lifecycle is already the events-log writer; extending it to be the commit author is consistent.
- `skills/lifecycle/SKILL.md:170-181` — "A phase boundary is a mechanical transition, not a synchronization point." No new `AskUserQuestion` at the post-refine commit boundary.
- `cortex/lifecycle.config.md:6` — `commit-artifacts: true` default. The new commit step must honor `commit-artifacts: false`.
- `skills/lifecycle/SKILL.md:214-221` (Lifecycle Directory section) — "The `cortex/lifecycle/` directory handling is a per-project choice ... There is no global enforcement." This concerns whether `cortex/lifecycle/` is tracked in git, which is orthogonal to the runtime `commit-artifacts` flag.
- `cortex/requirements/project.md:50` — "Destructive operations preserve uncommitted state." The feature should not require a clean tree to operate; it should not destroy unrelated working-tree changes.
- `bin/.events-registry.md` — has no `commit_authored` / `artifacts_committed` / `commit_failed` row today. Any new event introduced by this feature must be registered (enforced by `bin/cortex-check-events-registry`).
- ADR-0004 (`cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md`) — precedent for multi-step lifecycle phases.

## Tradeoffs & Alternatives

Six alternatives evaluated:

- **Alt A — Inline in `lifecycle/SKILL.md` Step 3 trunk.** Low complexity (6–10 lines). Co-located with where lifecycle already owns `phase_transition` logging. Slight asymmetry vs. the existing `specify.md:206` / `plan.md:306` / `complete.md:19` pattern (which keeps commits in references, not the trunk).
- **Alt B — Refine §6 owns the commit.** **REJECTED by user.** Inverts refine SKILL.md:169's "caller owns commit-artifacts" contract; breaks standalone refine invocations.
- **Alt C — Dedicated reference `skills/lifecycle/references/post-refine-commit.md` ⟵ recommended.** Pattern-symmetric with existing references (backlog-writeback.md, discovery-bootstrap.md, complexity-escalation.md). Scales if post-refine handling grows (critical-review wiring for delegated path, future complexity-escalator hooks at this boundary). Lazy-loaded on demand. ~40–60 lines of reference content + a 1-line trunk pointer in `lifecycle/SKILL.md` Step 3.
- **Alt D — Stop hook / events.log watcher.** **Rejected.** Decouples cause from effect; no precedent (all four existing commit sites fire inline from skill prose); commit-on-transition is per-config-flag behavior, not an invariant, so hooks are wrong tool.
- **Alt E — Two commits (artifacts then backlog write-back).** Rejected — doubles latency, conflicts with user's explicit "bundle together" preference, no compensating benefit.
- **Alt F — Stage only, defer commit to user.** **REJECTED by user.** Diverges from all four existing inline-commit sites; breaks overnight (unattended runs cannot defer to a human commit step).

### Recommended approach: Alt C (dedicated reference)

Per-trunk pointer in `lifecycle/SKILL.md` Step 3 §4, after `phase_transition specify→plan` is logged: `"Follow [post-refine-commit.md](references/post-refine-commit.md)."`

Shape of `references/post-refine-commit.md`:
- Preconditions: refine has returned successfully; `spec_approved` event in events.log; `phase_transition from=specify to=plan` event already logged.
- Read `cortex/lifecycle.config.md`; if `commit-artifacts: false`, exit silently.
- Stage explicit paths: `cortex/lifecycle/{feature}/` + (Context A only) `cortex/backlog/{NNN}-{slug}.md`.
- Invoke `/cortex-core:commit` with a subject like `Refine {feature}: research and spec`.

## Adversarial Review

### Why refine §5 couples phase_transition and commit-artifacts (defending Alt C against the "just remove the override" alternative)

The "simpler" alternative would be to remove only the `commit-artifacts` portion of refine §5's override, letting `specify.md:206` fire on the delegated path. **This is structurally wrong** because of ordering: if refine committed before lifecycle's Step 3 §4 logs `phase_transition specify→plan`, the phase_transition row would be uncommitted at commit time, then would end up bundled with the next phase's commit (plan.md:306). The current §5 coupling exists precisely because lifecycle owns events.log AND must commit *after* writing the post-phase-transition row. The orchestrator-owned post-refine commit (Alt C) is the correct shape; the "remove override" alternative produces dangling phase_transition rows.

### Active failure modes the spec must address

1. **Resume creates phantom commits.** Re-invoking `/cortex-core:lifecycle <slug>` after a prior refine+commit: refine's Step 2 sees both artifacts exist and skips to its Step 6 (Completion). The orchestrator must NOT emit a phase_transition row and run the post-refine commit on the resume path. Mitigation: gate the commit on "did this session actually modify research.md / spec.md / index.md / backlog file" (e.g., compare SHAs before/after), not on file existence.

2. **Partial-state commits on refine failure.** Research succeeds, spec is cancelled (user picks "Cancel" at the spec approval surface). research.md is on disk; spec.md never gets written; events.log has clarify→research and research→specify phase_transition rows. Three options, all imperfect: (a) commit the partial state (creates a half-refined feature in git history); (b) don't commit (leaves events.log rows dirty in working tree); (c) block on user disposition (new `AskUserQuestion` site — would fail the parity test). The spec must pick one.

3. **Dirty working tree bundling.** `specify.md:206`'s phrasing "stage `cortex/lifecycle/{feature}/`" is a directory glob — it captures everything new in the dir, even unrelated transient files. The new reference must enumerate explicit paths (research.md, spec.md, index.md, events.log) plus the specific backlog file, NOT use the directory glob.

4. **`commit-artifacts` flag is prose-only.** No Python reader exists; the flag is read independently by each consumer. Adding a fourth prose consumer (post-refine-commit.md) compounds drift surface. **Recommend: extract `read_commit_artifacts() -> bool` into `cortex_command/lifecycle_config.py` and have all four consumers (specify, plan, complete, post-refine) read it via a shared helper or shell wrapper.** This is a precondition for adding the fourth site cleanly.

5. **Pre-commit hook rejection.** Repo's pre-commit hook rejects commits on `main` during active overnight sessions. If the post-refine commit fails on a hook rejection, the lifecycle has already emitted `phase_transition specify→plan` to events.log (uncommitted). The lifecycle then auto-advances to Plan. Plan writes plan.md. Plan-commit at plan.md:306 either succeeds (now bundling refine artifacts under the wrong commit title) or also fails. Mitigation: preflight the commit-hook condition before logging `phase_transition`. On rejection, halt with a user-actionable message and DO NOT auto-advance.

6. **Concurrent refine sessions in different worktrees.** Cross-worktree git index contention is bounded (each worktree has its own index), but `cortex-commit-preflight`'s snapshot+stage+commit is not transactional. A second commit between preflight snapshot and stage can invalidate the message author's premises. Mitigation: re-run preflight after staging, or hold an advisory lock for the preflight→commit critical section.

7. **`/cortex-core:commit` has no `--paths` argument.** Staging scope is conveyed via prose. The new reference should be explicit about exact paths to stage, and consider wrapping the commit with a shell helper that controls staging deterministically rather than relying on the commit-skill model's "stage relevant files" judgment.

### Commit count per feature (acknowledged, not problematic)

After this feature: refine-commit (research.md + spec.md + index.md + backlog + events.log up through specify→plan) → plan-write → plan-commit (plan.md + events.log plan→implement + index.md) → implement-commit(s) → review-commit → complete-commit. This matches existing intent at plan.md:306 / complete.md:19 — the proposal closes a gap, doesn't change the granularity model.

### Audit candidate

If specify.md:206 (and possibly plan.md:306) is reachable only via direct top-level invocation of `/cortex-core:specify` — and refine has subsumed all top-level Spec invocations — those inline commits are dead code. **Audit whether direct specify/plan invocation has any live entry point**; if not, delete the inline commit step in the same PR that adds post-refine-commit.md, so the commit logic exists in exactly one place.

## Open Questions

All six items below are explicitly deferred to the Spec phase per the Research Exit Gate. Each is a scope/policy/implementation decision that belongs in the structured spec interview rather than research-time investigation.

- **Q1 — Dead code audit.** Is `specify.md:206`'s inline commit (and `plan.md:306`'s, if also bypassed) reachable today via any live entry path? If not, should the inline commits be deleted in the same PR so commit logic exists in exactly one canonical site?
  **Deferred:** will be resolved in Spec by asking the user whether to bundle the cleanup. The audit itself is a one-grep verification that the spec interview can drive.

- **Q2 — `commit-artifacts` flag-read consolidation.** Should this PR extract `read_commit_artifacts()` into `cortex_command/lifecycle_config.py` and convert all four consumers to read via the helper before adding the fourth consumer, or accept the drift surface and add a fourth prose-only read?
  **Deferred:** will be resolved in Spec as a scope decision — this is the kind of "do we expand scope to remove fragility we discovered?" question the spec interview is designed to surface explicitly.

- **Q3 — Failure-path policy.** When refine is cancelled at the spec-approval surface (spec.md never gets written, but research.md and partial events.log entries exist), what should the orchestrator do? (a) commit the partial state with a "cancelled refine" marker, (b) leave the dirty tree for user disposition, (c) introduce a new user pause and update the kept-pauses inventory.
  **Deferred:** will be resolved in Spec by asking the user. This is a substantive policy decision that determines what behavior gets built.

- **Q4 — Resume idempotency mechanism.** Should commit-gating be SHA-based (compare artifact SHAs to pre-session state) or events-log-based (check for an `artifacts_committed` event after the last `lifecycle_start` row)? The latter requires registering a new event type.
  **Deferred:** will be resolved in Spec or Plan; both options work, the choice is a complexity tradeoff.

- **Q5 — Pre-commit hook preflight.** Should the post-refine flow preflight the hook (dry-run a commit, check overnight-active state) BEFORE writing `phase_transition` to events.log, to prevent stranded rows on hook rejection? Or accept that overnight-active+main is rare-enough that surfacing the hook rejection after the fact is sufficient?
  **Deferred:** will be resolved in Spec by asking the user. Determines whether the implementation needs a hook-preflight helper.

- **Q6 — Staging scope.** Reference enumerates explicit paths (`research.md`, `spec.md`, `index.md`, `events.log`, plus Context A backlog file), or matches the existing `specify.md:206` pattern of staging the lifecycle dir as a glob?
  **Deferred:** will be resolved in Spec. The adversarial review recommends explicit paths; the spec interview should confirm or override.
