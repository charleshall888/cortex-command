---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/cortex-core:lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", "start a feature lifecycle", or wants to build a non-trivial feature with structured phases. Required before editing files in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/`. Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only.
when_to_use: "Use when starting a new feature (\"start a feature\") or any non-trivial change with structured phases. Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
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

A file-based state machine that survives context loss. Enforces research-before-code, and user-guided spec-before-build discipline, and enforced project coherence throughout the process.

## Project Configuration

If `cortex/lifecycle.config.md` exists at the project root, read it first. It contains project-specific overrides for complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Resolve the Invocation

One read-only call classifies `$ARGUMENTS`, resolves the originating backlog file, detects phase, and reads staleness + criticality/tier:

```bash
cortex-lifecycle-resolve "$ARGUMENTS"
```

It emits one JSON object with a `state` discriminant, a `next` directive, and the data that state carries. Act on `state`:

| `state` | Action |
|---------|--------|
| `wontfix` | Run the `cortex-lifecycle-wontfix` command in `next`, report its outcome, and **halt** — do not fall through. |
| `error` · `needs-feature` · `no-such-lifecycle` | Report `next` and stop — do not create a lifecycle. |
| `derive-slug` | Derive a 3–6 word kebab-case slug summarizing the prose, announce it as you create `cortex/lifecycle/<slug>/`, then re-run the resolver on the slug. Don't ask the user to confirm — they correct via re-invocation. |
| `empty` | No feature given — fall through to the incomplete-lifecycle-dirs scan (Step 2's empty-arguments fallback). |
| `ambiguous-backlog` | Present `candidates` via `AskUserQuestion`, then re-run the resolver on the chosen slug. |
| `new` · `resume` | Proceed to Step 2 with the struct. `resume` carries `route`, `paused`, `checked`/`total`, `cycle`, `criticality`, `tier`, `staleness`, and `backlog`; `new` carries `backlog` and starts fresh. |

The resolver is read-only: it honors an explicit phase override (word #2, returned as `route`) but never creates or writes — the mutating sub-procedures in Step 2 run afterward.

## Step 2: Enter the Resolved State

For `new`, start from the beginning (`phase = none`). For `resume`, enter the resolver's `route` — the base phase (pause marker already stripped); `checked`/`total` report plan-task progress, `cycle` the review-cycle number. The linear routes (`research`, `specify`, `plan`, `implement`, `review`) enter their same-named phase. Non-obvious routes: `implement-rework` (`review.md` is `CHANGES_REQUESTED` — re-enter Implement), `complete` (`feature_complete` logged or review `APPROVED` — feature done), `escalated` (`review.md` is `REJECTED` — present the reviewer analysis and ask the user for direction). When `paused` is true, route normally and note the paused state when reporting.

**Register session**: After identifying the feature (new or existing), write the session file:

```
echo $LIFECYCLE_SESSION_ID > cortex/lifecycle/{feature}/.session
```

If resuming, report `route`, `criticality`, and `tier`, and offer to continue or restart from an earlier phase. Surface the resolver's `staleness` (`spec_age_days` / `plan_age_days` / `commits_since_spec`) as terse lines above the prompt — high ages or non-zero commits suggest the artifacts may have drifted. Do not block — the offer defaults to "continue".

### Backlog Status, index.md, Write-Back, and Discovery Bootstrap

These four sub-procedures consume the resolver's `backlog` field (they do not re-scan the backlog directory) and, for new lifecycles, seed `index.md` and epic context. Read the reference for the protocol:

- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — Backlog Status Check and Backlog Write-Back (Lifecycle Start)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — Create index.md (new lifecycle only), detect epic cortex/research/spec from backlog frontmatter, and record paths for refine context injection (do not copy epic content). Read only when `phase = none` (new lifecycle) or `phase = research`.

Run them in this order: Backlog Status Check → Create index.md → Backlog Write-Back → Discovery Bootstrap.

### Auto-apply init drift refresh

Run `cortex-lifecycle-init-ensure` before advancing to Step 3. If the command exits non-zero, halt and surface its diagnostic to the user — do not proceed to phase execution.

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

The Clarify, Research, and Spec phases are delegated to `/cortex-core:refine`.

**If `cortex/lifecycle/{feature}/spec.md` already exists AND `cortex/lifecycle/{feature}/research.md` also exists** (from a prior `/cortex-core:refine` run, or a resumed lifecycle): announce that early-phase delegation is skipped and proceed directly to the phase execution table below (Plan phase).

**Otherwise** — spec.md is missing, or exists without research.md (warn that this mixed state is inconsistent; overnight requires both): read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md) and follow it, substituting the body-resolved paths from the Reference-path propagation manifest below. `/cortex-core:refine`'s Step 2 detects a missing research.md and routes to the research phase.

The Research and Spec phases are handled by the /cortex-core:refine delegation block above. The following phases run directly in the lifecycle context:

| Phase | Reference | Artifact Produced |
|-------|-----------|-------------------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `cortex/lifecycle/{feature}/plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source code + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `cortex/lifecycle/{feature}/review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the reference for the current phase. Do not preload other phases.

### Reference-path propagation (load-bearing)

`${CLAUDE_SKILL_DIR}` resolves only in this body, not inside a reference you read. So wherever a reference contains a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path (a bare `skills/…` or `../` path would resolve against CWD and break off-repo). Two targets sit outside this skill's `references/`: `clarify-critic` → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`, and refine's SKILL.md → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md`.

`refine-delegation.md` uses named placeholders — fill each with its `${CLAUDE_SKILL_DIR}`-resolved path: `<REFINE_SKILL_MD>`→`../refine/SKILL.md`, `<DISCOVERY_BOOTSTRAP_MD>`→`references/discovery-bootstrap.md`, `<COMPLEXITY_ESCALATION_MD>`→`references/complexity-escalation.md`, `<POST_REFINE_COMMIT_MD>`→`references/post-refine-commit.md`.

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

For criticality override syntax and the criticality behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Lifecycle Directory

Committing vs gitignoring `cortex/lifecycle/` is a per-project choice; there is no global enforcement.

## Situational references

The per-phase references (Step 3 table) and the cross-cutting references cited at their decision points above already load at point of use. These three have no point-of-use trigger in the linear flow — consult only when the named condition applies, and do not preload:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` convention, multi-feature concurrency, listing incomplete features
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — running multiple features in parallel via `Agent(isolation: "worktree")`, worktree-inspection invariant
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — terminal-state workflow for operator-decided lifecycle termination
