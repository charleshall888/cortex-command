---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/cortex-core:lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", "start a feature lifecycle", or wants to build a non-trivial feature with structured phases.
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

A file-based state machine that survives context loss: research before code, user-approved spec before build, project coherence throughout.

## Project Configuration

If `cortex/lifecycle.config.md` exists at project root, read it first — it overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Resolve the Invocation

One read-only call classifies `$ARGUMENTS`, resolves the backlog file, detects phase, and reads staleness + criticality/tier:

```bash
cortex-lifecycle-resolve "$ARGUMENTS"
```

It emits one JSON object with a `state` discriminant, a `next` directive, and that state's data. Act on `state`:

| `state` | Action |
|---------|--------|
| `wontfix` | Run `next`'s `cortex-lifecycle-wontfix` command, report the outcome, **halt**. |
| `error` · `needs-feature` · `no-such-lifecycle` | Report `next` and stop — do not create a lifecycle. |
| `derive-slug` | Derive a 3–6 word kebab-case slug from the prose, announce it as you create `cortex/lifecycle/<slug>/`, then re-run the resolver on it. No confirmation — the user corrects via re-invocation. |
| `empty` | No feature given — act on `next`: scan `cortex/lifecycle/*` for incomplete lifecycles and offer them via `AskUserQuestion`, then re-run the resolver on the choice. |
| `ambiguous-backlog` | Present `candidates` via `AskUserQuestion`, then re-run the resolver on the choice. |
| `new` · `resume` | Proceed to Step 2. `resume` carries `route`, `paused`, `checked`/`total`, `cycle`, `criticality`, `tier`, `staleness`, `backlog`; `new` carries `backlog`. |

The resolver never writes — Step 2's sub-procedures do.

## Step 2: Enter the Resolved State

`new` starts fresh (`phase = none`). `resume` enters the resolver's `route` (base phase, pause marker stripped). Linear routes (`research`, `specify`, `plan`, `implement`, `review`) enter their same-named phase. Non-obvious: `implement-rework` (review `CHANGES_REQUESTED` → re-enter Implement), `complete` (`feature_complete` logged or review `APPROVED`), `escalated` (review `REJECTED` → present the analysis, ask for direction). When `paused`, route normally and note it.

**Register session:**

```
echo $LIFECYCLE_SESSION_ID > cortex/lifecycle/{feature}/.session
```

If resuming, report `route`, `criticality`, `tier`, and offer to continue or restart from an earlier phase. Surface `staleness` (`spec_age_days` / `plan_age_days` / `commits_since_spec`) as terse lines — high values suggest the artifacts drifted. Don't block; default to continue.

### Backlog + Discovery Bootstrap

These consume the resolver's `backlog` field (no re-scan) and, for new lifecycles, seed `index.md` and epic context. Run in order — Backlog Status → Create index.md → Backlog Write-Back → Discovery Bootstrap:

- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — Backlog Status Check and Write-Back
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — index.md creation + epic detection from backlog frontmatter. Read only when `phase = none` or `research`.

### Init drift refresh

Run `cortex-lifecycle-init-ensure` before Step 3. Non-zero exit → halt and surface its diagnostic.

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

Clarify, Research, and Spec are delegated to `/cortex-core:refine`.

- **`spec.md` AND `research.md` both exist** (prior refine run or resume): skip delegation, go to the phase table (Plan).
- **Otherwise** (spec.md missing, or present without research.md — warn this mixed state is inconsistent; overnight needs both): read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md), substituting the body-resolved paths below. Refine routes a missing research.md to the research phase.

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the current phase's reference. Do not preload others.

### Reference-path propagation (load-bearing)

`${CLAUDE_SKILL_DIR}` resolves only in this body, not inside a reference you read. Wherever a reference contains a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path (a bare `skills/…` or `../` path resolves against CWD and breaks off-repo). Two targets sit outside this skill: `clarify-critic` → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`, refine's SKILL.md → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md`. `refine-delegation.md`'s placeholders resolve to `<REFINE_SKILL_MD>`→`../refine/SKILL.md`, `<DISCOVERY_BOOTSTRAP_MD>`→`references/discovery-bootstrap.md`, `<COMPLEXITY_ESCALATION_MD>`→`references/complexity-escalation.md`, `<POST_REFINE_COMMIT_MD>`→`references/post-refine-commit.md`.

## Phase Transition

Proceed automatically — no confirmation at phase boundaries. Announce and continue. Each transition summary includes **Decisions**, **Scope delta**, **Blockers** (each "None" when empty), and **Next** (phase + what it does).

A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not on user input — nothing to wait for. A prior "report"/"summarize" instruction sets text cadence only — emit the summary as plain text and continue; it does not authorize `AskUserQuestion` (permitted at a boundary only by the Kept user pauses inventory).

### Per-phase completion rule

A phase completes (auto-advance fires) only on its gate:

- **Specify**: `spec.md` exists AND (`spec_approved` event OR a `phase_transition` with `"from":"specify"` as migration sentinel).
- **Plan**: `plan.md` exists AND (`plan_approved` event OR `phase_transition` `"from":"plan"`).
- **Implement**: `plan.md` exists AND every task `**Status**` is `[x]` — the checkbox tally is the gate, no approval.
- **Review**: `review.md` exists AND a `review_verdict` event with `verdict: APPROVED` (→ Complete), OR the cycle-2 escalation (→ `escalated`, user-blocking).
- **Complete**: `feature_complete` event present.

Specify and Plan each keep one approval surface at §4 of their reference. Specify's is `Approve / Request changes / Cancel`. Plan's §4 merges plan approval with the Implement branch/dispatch selection — see plan.md §4 for the branch-mode → `plan_approved` / `dispatch_choice` / `feature_paused` routing.

### Kept user pauses

Auto-proceed except where a phase reference defines a kept pause. The parity-tested inventory lives in [kept-pauses.md](${CLAUDE_SKILL_DIR}/references/kept-pauses.md).

For criticality override syntax and the behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Situational references

The per-phase and cross-cutting references above load at point of use. These three have no linear-flow trigger — consult only when their condition applies, don't preload:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` convention, multi-feature concurrency
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided lifecycle termination
