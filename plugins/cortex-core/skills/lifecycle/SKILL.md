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
- `/cortex-core:lifecycle {{feature}} {{phase}}` — enter a specific phase for that feature
- `/cortex-core:lifecycle resume {{feature}}` — resume a specific feature if multiple exist
- `/cortex-core:lifecycle complete {{slug}}` — finalize a feature (re-invoke the Complete phase)
- `/cortex-core:lifecycle wontfix {{slug}}` — abandon a feature via the terminal wontfix verb

## Project Configuration

If `cortex/lifecycle.config.md` exists at the project root, read it first. It contains project-specific overrides for complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Identify the Feature

Classify the invocation structurally — do not parse `$ARGUMENTS` in prose. Run the grammar helper and act on its `mode`:

```bash
cortex-lifecycle-parse-args "$ARGUMENTS"
```

It emits one JSON object `{"mode": "...", "feature": "...", "phase": "..."}`. Route on `mode` (the closed set the helper can emit):

| `mode` | Action |
|--------|--------|
| `wontfix` | Abandon the feature: invoke the wontfix verb with `feature` as the slug, report its outcome, and **halt** — this route is terminal/short-circuiting; do not fall through to Step 2. |
| `resume` | Resume `feature`: route into Step 2 phase-detection, but if `cortex/lifecycle/<feature>/` does not exist, report "no such lifecycle to resume" and stop — do not create it (that is bare `<feature>`'s behavior). |
| `complete` | Enter the Complete phase for `feature` via the explicit-phase-override route below (`phase` is `complete`). |
| `phase` | A bare phase token with no feature. Surface "specify a feature, e.g. `/cortex-core:lifecycle <feature> <phase>`" and stop — do not create a lifecycle. |
| `feature` | The normal path. Use `feature` as `{feature}`; if `phase` is non-empty, honor it via the explicit-phase-override route below. Proceed to the resolver and Step 2. |
| `needs-derivation` | `$ARGUMENTS`'s first word is prose, not a slug. Derive a 3–6 word kebab-case slug (valid-slug pattern `^[a-z0-9]+(-[a-z0-9]+)*$`) summarizing its intent, announce the chosen slug as you create `cortex/lifecycle/{slug}/`, and proceed as `feature`. Do not ask the user to confirm — let them correct via re-invocation. A derived slug colliding with an existing directory is treated as a resume per Step 2's routing. |
| `empty` | No arguments (or `resume` with no slug). Fall through to the incomplete-lifecycle-dirs scan (see Step 2's empty-arguments fallback). |
| `error` | A reserved word (`wontfix`/`resume`/`complete`) given with no slug. Report that the verb needs a target and stop. |

**Explicit-phase-override route**: when the helper returns a non-empty `phase` for a resolved `feature` (the `complete` mode, or a `feature` invocation whose word #2 is a phase token), enter that phase directly rather than deferring to Step 2's artifact detector (`cortex-common detect-phase` routes on artifacts and ignores an explicit phase). Warn if prerequisite artifacts are missing (e.g., entering Plan without research.md).

Use lowercase-kebab-case for directory naming. When linked to a backlog item, use the canonical `slugify()` from `cortex_command.common`.

### Resolve the originating backlog file once

When `$ARGUMENTS` is non-empty, invoke `cortex-resolve-backlog-item` once to find the matching backlog file. The four sub-procedures (Backlog Status Check, Create index.md, Backlog Write-Back, Discovery Bootstrap) consume Step 1's resolver output — they do not re-scan the backlog directory.

```bash
cortex-resolve-backlog-item {feature}
```

Act on the result: a unique match resolves the printed file as `{backlog-file}` for the Step 2 sub-procedures; an ambiguous match prints candidates on stderr — present them via `AskUserQuestion` for the user to pick; no match means the feature has no backlog file, so proceed without one (the sub-procedures each handle that path). On any hard error, surface the resolver's message and halt.

When `$ARGUMENTS` is empty, skip the resolver entirely — the existing incomplete-lifecycle-dirs scan path applies (see Step 2's empty-arguments fallback).

## Step 2: Check for Existing State

Scan for `cortex/lifecycle/{feature}/` at the project root.

### Artifact-Based Phase Detection

If no `cortex/lifecycle/{feature}/` directory exists, `phase = none` — start from the beginning. Otherwise, invoke the canonical detector and route on the returned `route` field:

```bash
cortex-common detect-phase cortex/lifecycle/{feature}
```

The command emits a single JSON object on stdout, e.g. `{"phase":"implement","route":"implement","paused":false,"checked":2,"total":5,"cycle":1}`. Route on the `route` field — the base phase, with any pause marker already stripped by the detector. The `checked`/`total` fields report plan-task progress; `cycle` reports the review-cycle number.

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

**Paused state**: the detector reports `paused` directly — when `true`, the feature was paused at the `route` phase; route normally and note the paused state when reporting to the user. How the marker is set and cleared is the detector's concern, not yours.

**Detect criticality and tier**: After determining the phase, run `cortex-lifecycle-state --feature {feature} --field criticality` (default: `medium`) and `cortex-lifecycle-state --feature {feature} --field tier` (default: `simple`). Report both alongside the detected phase when resuming. (Rules: [criticality-matrix.md §Reading lifecycle state](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).)

**Register session**: After identifying the feature (whether new or existing), register this session by writing the session file:

```
echo $LIFECYCLE_SESSION_ID > cortex/lifecycle/{feature}/.session
```

If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase. Before the offer, run `cortex-common staleness cortex/lifecycle/{feature}` and surface its `spec_age_days` / `plan_age_days` / `commits_since_spec` fields as terse lines above the prompt (high values or non-zero commits suggest the artifacts may have drifted). Do not block — the offer defaults to "continue".

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

**A phase boundary fires on its gate condition (e.g. `plan.md` with all tasks `[x]`), not on user input — there is nothing to wait for.** A prior session instruction to "report" or "summarize" between phases sets text-emission cadence only: emit the transition summary as plain text and continue. It does not authorize `AskUserQuestion` (yielding control to the user), which at a phase boundary is permitted only by the Kept user pauses inventory (`references/kept-pauses.md`).

### Per-phase completion rule

"Completing a phase artifact" is defined per-phase. A phase is complete (and auto-advance fires) only when its gate condition is satisfied:

- **Specify**: `spec.md` exists AND (`spec_approved` event in `events.log` OR a `phase_transition` event with `"from":"specify"` already exists as a migration sentinel).
- **Plan**: `plan.md` exists AND (`plan_approved` event in `events.log` OR a `phase_transition` event with `"from":"plan"` already exists as a migration sentinel).
- **Implement**: `plan.md` exists AND every task's `**Status**` line is `[x]` — no approval gate; the checkbox tally is the gate.
- **Review**: `review.md` exists AND a `review_verdict` event in `events.log` with `verdict: APPROVED` is present (auto-routes to Complete) OR the cycle-2 escalation condition is met (routes to `escalated`, which is a genuine user-blocking state).
- **Complete**: a `feature_complete` event is present in `events.log`.

Specify and Plan each retain a single user-facing approval surface at §4 of their respective references. Specify's is `Approve / Request changes / Cancel`. Plan's §4 is **merged with the Implement branch/dispatch selection**: the branch modes plus an "Approve plan but wait to implement" option are the surface (selecting a branch mode implies plan approval; Request changes / Cancel ride the "Other" free-text escape). The `plan_approved` event is emitted on any branch-mode or "wait" selection — a branch-mode selection records `dispatch_choice` and auto-advances to Implement; "wait" additionally emits `feature_paused` and halts (re-invocation resumes at Implement). The other transitions emit `phase_transition` events without a pause.

### Kept user pauses

Auto-proceed except where a phase reference defines a kept pause. The canonical, parity-tested inventory of those deliberate `AskUserQuestion` sites lives in [kept-pauses.md](${CLAUDE_SKILL_DIR}/references/kept-pauses.md) (enforced by `tests/test_lifecycle_kept_pauses_parity.py`).

To jump to a specific phase, name the feature — `/cortex-core:lifecycle <feature> <phase>` — and Step 1's explicit-phase-override route enters the requested phase, warning if prerequisite artifacts are missing (e.g., entering Plan without research.md). A bare phase token with no feature (`/cortex-core:lifecycle plan`) does not resolve to an active feature; Step 1 surfaces the feature-required message instead.

For criticality override syntax and the criticality behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Lifecycle Directory

Committing vs gitignoring `cortex/lifecycle/` is a per-project choice; there is no global enforcement.

## Situational references

The per-phase references (Step 3 table) and the cross-cutting references cited at their decision points above already load at point of use. These three have no point-of-use trigger in the linear flow — consult only when the named condition applies, and do not preload:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` convention, multi-feature concurrency, listing incomplete features
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — running multiple features in parallel via `Agent(isolation: "worktree")`, worktree-inspection invariant
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — terminal-state workflow for operator-decided lifecycle termination
