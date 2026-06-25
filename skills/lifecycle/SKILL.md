---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/cortex-core:lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", "start a feature lifecycle", or wants to build a non-trivial feature with structured phases. Required before editing files in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/`. Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only.
when_to_use: "Use when starting a new feature (\"start a feature\", \"build this properly\") or any non-trivial change with structured phases. Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
argument-hint: "<feature> [phase]"
inputs:
  - "feature: string (required) — kebab-case slug of the feature to develop or resume"
  - "phase: string (optional) — explicit phase to enter: research|specify|plan|implement|review|complete"
outputs:
  - "cortex/lifecycle/{{feature}}/ — directory containing phase artifacts: research.md, spec.md, plan.md, review.md, events.log"
preconditions:
  - "Run from project root"
  - "cortex/lifecycle/ directory must exist or will be created"
precondition_checks:
  - "test -d cortex/lifecycle"
---

# Feature Lifecycle

A file-based state machine that survives context loss. Enforces research-before-code, prose-before-implementation, and spec-before-build discipline.

## Invocation

- `/cortex-core:lifecycle {{feature}}` — start new or resume existing feature
- `/cortex-core:lifecycle {{phase}}` — explicitly enter a phase for the active feature
- `/cortex-core:lifecycle resume {{feature}}` — resume a specific feature if multiple exist

## Project Configuration

If `cortex/lifecycle.config.md` exists at the project root, read it first. It contains project-specific overrides for complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Identify the Feature

Feature/phase from invocation: $ARGUMENTS. Parse: first word = feature name (strip a leading `#` first, so `#001` is treated as `001` and `#some-slug` as `some-slug` — the `#` is a no-op id sigil), second word (if present) = explicit phase override. If $ARGUMENTS is empty, fall through to the existing behavior (scan for incomplete lifecycle directories).

When `$ARGUMENTS` is non-empty but its first word is prose rather than a valid kebab-case slug (the valid-slug pattern is `^[a-z0-9]+(-[a-z0-9]+)*$`), derive a 3–6 word kebab-case slug that summarizes the prose's intent, announce the chosen slug as you create `cortex/lifecycle/{slug}/`, and use it as `{feature}` for the rest of Step 1 and Step 2. Do not ask the user to confirm the derived slug — proceed and let the user correct via re-invocation if needed. A derived slug that collides with an existing `cortex/lifecycle/{slug}/` directory is treated as a resume per Step 2's phase-detection routing, not silently disambiguated.

Determine the feature name from the invocation. Use lowercase-kebab-case for directory naming. When linked to a backlog item, use the canonical `slugify()` from `cortex_command.common`.

### Resolve the originating backlog file once

When `$ARGUMENTS` is non-empty, invoke `cortex-resolve-backlog-item` once to find the matching backlog file. The four sub-procedures (Backlog Status Check, Create index.md, Backlog Write-Back, Discovery Bootstrap) consume Step 1's resolver output — they do not re-scan the backlog directory.

```bash
cortex-resolve-backlog-item {feature}
```

Act on the result: a unique match resolves the printed file as `{backlog-file}` for the Step 2 sub-procedures; an ambiguous match prints candidates on stderr — present them via `AskUserQuestion` for the user to pick; no match means the feature has no backlog file, so proceed without one (the sub-procedures each handle that path). On any hard error, surface the resolver's message and halt.

When `$ARGUMENTS` is empty, skip the resolver entirely — the existing incomplete-lifecycle-dirs scan path applies (see Step 2's empty-arguments fallback).

If a long session causes the parsed frontmatter to drop from working memory, a single targeted re-Read of `{backlog-file}` is permitted at a phase boundary.

## Step 2: Check for Existing State

Scan for `cortex/lifecycle/{feature}/` at the project root.

### Artifact-Based Phase Detection

If no `cortex/lifecycle/{feature}/` directory exists, `phase = none` — start from the beginning. Otherwise, invoke the canonical detector and route on the returned `phase` field:

```bash
cortex-common detect-phase cortex/lifecycle/{feature}
```

The command emits a single JSON object on stdout, e.g. `{"phase":"implement","checked":2,"total":5,"cycle":1}`. Parse the `phase` field and route accordingly. The `checked`/`total` fields report plan-task progress; `cycle` reports the review-cycle number.

Reference table (one line per `phase` value):

| `phase`            | Semantic meaning                                                                                  |
|--------------------|---------------------------------------------------------------------------------------------------|
| `research`         | No artifacts yet — start the Research phase.                                                      |
| `specify`          | `research.md` exists; advance to the Specify phase.                                               |
| `plan`             | `spec.md` exists; advance to the Plan phase.                                                      |
| `implement`        | `plan.md` exists with at least one task unchecked; run/resume the Implement phase.                |
| `implement-rework` | `review.md` verdict is `CHANGES_REQUESTED`; re-enter Implement to address review feedback.        |
| `review`           | `plan.md` exists with all tasks checked; run the Review phase.                                    |
| `complete`         | `events.log` has a `feature_complete` event, or `review.md` verdict is `APPROVED` — feature done. |
| `escalated`        | `review.md` verdict is `REJECTED`; present reviewer analysis and ask the user for direction.      |

**Paused suffix**: when the detected phase ends in `-paused` (e.g. `implement-paused:3/5`, `review-paused`), strip the `-paused` portion for routing-table lookup above; display the full label including ` — paused` to the user. The `-paused` marker is set when `events.log`'s most recent significant event among `{phase_transition, feature_complete, feature_wontfix, feature_paused}` is `feature_paused`. A later `phase_transition` event resumes the feature and clears the marker.

**Detect criticality and tier**: After determining the phase, run `cortex-lifecycle-state --feature {feature} --field criticality` (default: `medium`) and `cortex-lifecycle-state --feature {feature} --field tier` (default: `simple`). Report both alongside the detected phase when resuming. (Rules: [criticality-matrix.md §Reading lifecycle state](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).)

**Register session**: After identifying the feature (whether new or existing), register this session by writing the session file:

```
echo $LIFECYCLE_SESSION_ID > cortex/lifecycle/{feature}/.session
```

If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase. Before presenting the offer, surface two staleness signals so the user can decide whether the existing artifacts are still trustworthy:

1. **Artifact age**: relative age of `spec.md` (and `plan.md` if present) — e.g., "spec.md last modified 12 days ago".
2. **Commits since spec**: count of commits touching spec-named files since spec mtime; non-zero suggests research assumptions may have drifted.

Surface both as terse lines above the continue/restart prompt. Do not block — the offer defaults to "continue".

### Backlog Status, index.md, Write-Back, and Discovery Bootstrap

These four sub-procedures all read or update the originating backlog item and (for new lifecycles) seed `index.md` and epic context. Read the reference for the protocol:

- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — Backlog Status Check and Backlog Write-Back (Lifecycle Start)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — Create index.md (new lifecycle only), detect epic cortex/research/spec from backlog frontmatter, and record paths for refine context injection (do not copy epic content). Read only when `phase = none` (new lifecycle) or `phase = research`.

Run them in this order: Backlog Status Check → Create index.md → Backlog Write-Back → Discovery Bootstrap.

### Auto-apply init drift refresh

Run `cortex-lifecycle-init-ensure` before advancing to Step 3. If the command exits non-zero, halt and surface its diagnostic to the user — do not proceed to phase execution.

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

The Clarify, Research, and Spec phases are delegated to `/cortex-core:refine`.

**If `cortex/lifecycle/{feature}/spec.md` already exists AND `cortex/lifecycle/{feature}/research.md` also exists** (from a prior `/cortex-core:refine` run, or a resumed lifecycle): announce that early-phase delegation is skipped and proceed directly to the phase execution table below (Plan phase).

**If `cortex/lifecycle/{feature}/spec.md` exists but `cortex/lifecycle/{feature}/research.md` does not**: warn that the lifecycle is in an inconsistent state — spec exists without research, and overnight requires both. Delegate to `/cortex-core:refine` normally; `/cortex-core:refine`'s Step 2 will detect the missing research.md and route to the research phase.

**If `cortex/lifecycle/{feature}/spec.md` does not exist**: read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md) and follow it, substituting the body-resolved paths from the Reference-path propagation manifest below.

The Research and Spec phases are handled by the /cortex-core:refine delegation block above. The following phases run directly in the lifecycle context:

| Phase | Reference | Artifact Produced |
|-------|-----------|-------------------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `cortex/lifecycle/{feature}/plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source code + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `cortex/lifecycle/{feature}/review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the reference for the current phase. Do not preload other phases.

### Reference-path propagation (load-bearing)

Resolve `${CLAUDE_SKILL_DIR}` here in the body and carry the absolute paths into the phase — a bare `skills/…` or `../` path in a reference file resolves against CWD and breaks off-repo. When you read the current-phase reference, substitute these body-resolved absolute paths wherever it directs you to one of these targets:

- **clarify-critic** (consulted in Clarify §3a) → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`
- **overnight-check sidecar** (executed in Implement §1 Step A and §1a.ii) → `${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh`. The Implement reference invokes it as `cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "<message>" "<root>"` — preserve the `bash -s --` message and root arguments verbatim.
- **load-requirements protocol** (consulted in Specify §1, Review §1, and Clarify §2) → `${CLAUDE_SKILL_DIR}/references/load-requirements.md`
- **refine SKILL.md** (read verbatim in refine-delegation.md Step 1) → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md`. Substitute as `<REFINE_SKILL_MD>` in refine-delegation.md.
- **discovery-bootstrap** (read in refine-delegation.md Steps 2–3) → `${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md`. Substitute as `<DISCOVERY_BOOTSTRAP_MD>` in refine-delegation.md.
- **complexity-escalation** (run in refine-delegation.md Step 5) → `${CLAUDE_SKILL_DIR}/references/complexity-escalation.md`. Substitute as `<COMPLEXITY_ESCALATION_MD>` in refine-delegation.md.
- **post-refine-commit** (read in refine-delegation.md Step 6) → `${CLAUDE_SKILL_DIR}/references/post-refine-commit.md`. Substitute as `<POST_REFINE_COMMIT_MD>` in refine-delegation.md.
- **criticality-matrix** (§Reading lifecycle state rules cited by Detect criticality/tier in Step 2, and §Criticality Behavior Matrix cited at end of Phase Transition) → `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md`.
- **orchestrator-review** (read at Specify §3a and Plan §3a) → `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md`.
- **critical-review-gate** (read at Specify §3b and Plan §3b on the skip branch) → `${CLAUDE_SKILL_DIR}/references/critical-review-gate.md`.

## Phase Transition

Proceed automatically — do not ask the user for confirmation at phase boundaries. Announce the transition and continue to the next phase. Between phases, include these minimum fields in the transition summary:

- **Decisions**: Key decisions made during this phase (or "None")
- **Scope delta**: Changes to scope, approach, or plan since last phase (or "None")
- **Blockers**: Active blockers, escalations, or deferred questions (or "None")
- **Next**: Next phase name and what it will do

**A phase boundary is a mechanical transition, not a synchronization point.** The boundary fires when the gate condition above is satisfied (e.g., `plan.md` exists with all tasks `[x]`), not when the user gives input — so there is nothing to "wait for" once the gate has fired. If an earlier user instruction in the session asked you to "report" or "summarize" (at the end, between phases, between tasks), that modulates text-emission cadence — emit the transition summary as plain text and continue. It is not authorization to call `AskUserQuestion`, which is a syntactically different operation (yielding control to the user) rather than a text emission.

`AskUserQuestion` at a phase boundary is authorized only by the Kept user pauses inventory below; no test can catch runtime deviations — this paragraph is the runtime backstop.

### Per-phase completion rule

"Completing a phase artifact" is defined per-phase. A phase is complete (and auto-advance fires) only when its gate condition is satisfied:

- **Specify**: `spec.md` exists AND (`spec_approved` event in `events.log` OR a `phase_transition` event with `"from":"specify"` already exists as a migration sentinel).
- **Plan**: `plan.md` exists AND (`plan_approved` event in `events.log` OR a `phase_transition` event with `"from":"plan"` already exists as a migration sentinel).
- **Implement**: `plan.md` exists AND every task's `**Status**` line is `[x]` — no approval gate; the checkbox tally is the gate.
- **Review**: `review.md` exists AND a `review_verdict` event in `events.log` with `verdict: APPROVED` is present (auto-routes to Complete) OR the cycle-2 escalation condition is met (routes to `escalated`, which is a genuine user-blocking state).
- **Complete**: a `feature_complete` event is present in `events.log`.

Specify and Plan each retain a single user-facing approval surface at §4 of their respective references. Specify's is `Approve / Request changes / Cancel`. Plan's §4 is **merged with the Implement branch/dispatch selection**: the branch modes plus an "Approve plan but wait to implement" option are the surface (selecting a branch mode implies plan approval; Request changes / Cancel ride the "Other" free-text escape). The `plan_approved` event is emitted on any branch-mode or "wait" selection — a branch-mode selection records `dispatch_choice` and auto-advances to Implement; "wait" additionally emits `feature_paused` and halts (re-invocation resumes at Implement). The other transitions emit `phase_transition` events without a pause.

### Kept user pauses

The following user-facing pauses are deliberate and remain in scope.

- `skills/lifecycle/SKILL.md:60` — ambiguous backlog match needs operator disambiguation.
- `skills/lifecycle/references/clarify.md:57` — low-confidence clarify question batch surfaces unknowns the model cannot resolve alone.
- `skills/lifecycle/references/specify.md:36` — structured-interview gap-fill: model needs user input for unstated requirements.
- `skills/lifecycle/references/specify.md:67` — §2a cycle-2 confidence-check: user decides whether to loop back to research or proceed with gaps.
- `skills/lifecycle/references/specify.md:155` — spec approval surface (Approve / Request changes / Cancel). Substantive user decision.
- `skills/lifecycle/references/plan.md:281` — plan approval surface, merged with branch/dispatch selection (branch modes + "Approve plan but wait to implement" imply approval; Request changes / Cancel via the "Other" free-text escape). Substantive user decision.
- `skills/lifecycle/references/implement.md:50` — conditional pause: fallback branch-selection picker on main, used only when no plan-time `dispatch_choice` was recorded (trunk vs feature-branch-with-worktree vs feature branch). Suppressed when `lifecycle.config.md::branch-mode` is set AND the working tree is clean AND no concurrent live interactive worktree exists for the feature slug.
- `skills/lifecycle/references/backlog-writeback.md:11` — backlog write-back complete-lifecycle prompt on a backlog item already marked complete.
- `skills/lifecycle/references/complete.md:73` — phase-exit pause: merge-wait pause inside the multi-step Complete phase; user re-invokes /cortex-core:lifecycle complete <slug> after merging on GitHub.
- `skills/refine/SKILL.md:166` — refine §4 complexity-value gate pick-menu — renders only when the orchestrator's recommendation diverges from full scope or confidence is low; otherwise the announcement folds into the regular approval surface.

If the user invokes `/cortex-core:lifecycle <phase>` to jump to a specific phase, honor the request but warn if prerequisite artifacts are missing (e.g., entering Plan without research.md).

For criticality override syntax and the criticality behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Lifecycle Directory

Committing vs gitignoring `cortex/lifecycle/` is a per-project choice; there is no global enforcement.

## Reference Files

Beyond the per-phase references in the table above, these references cover cross-cutting concerns. Load on demand:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` file convention, multi-feature concurrency, listing incomplete features
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — running multiple features in parallel via `Agent(isolation: "worktree")`, worktree-inspection invariant
- [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md) — criticality override event, behavior matrix across review/orchestrator/dispatch/model dimensions
- [complexity-escalation.md](${CLAUDE_SKILL_DIR}/references/complexity-escalation.md) — `cortex-complexity-escalator` gates at phase transitions
- [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md) — delegation steps for the Clarify/Research/Specify phases (read when spec.md does not exist; uses body-resolved paths from the manifest above)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — index.md creation (new lifecycle only), epic-research detection from backlog frontmatter, epic-context injection during refine
- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — backlog status check and write-back to the originating backlog item
- [post-refine-commit.md](${CLAUDE_SKILL_DIR}/references/post-refine-commit.md) — canonical commit site for the refine→plan boundary
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — terminal-state workflow for operator-decided lifecycle termination
