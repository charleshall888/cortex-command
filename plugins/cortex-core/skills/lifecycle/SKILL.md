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

A file-based state machine that survives context loss: research before code, approved spec before build, coherence throughout.

## Project Configuration

If `cortex/lifecycle.config.md` exists at project root, read it first — it overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Resolve the Invocation

One read-only call classifies `$ARGUMENTS`, resolves the backlog file, detects phase, and reads staleness + criticality/tier:

```bash
cortex-lifecycle-resolve "$ARGUMENTS"
```

It emits one JSON object with a `state` discriminant and a `next` directive — act on `next`, don't re-derive it. `new` and `resume` proceed to Step 2 (`resume` carries `route`, `paused`, `checked`/`total`, `cycle`, `criticality`, `tier`, `staleness`, `backlog`; `new` carries `backlog`). Every other state is terminal; `next` says what to do: `derive-slug` (derive a 3–6 word kebab-case slug and re-run — no confirmation; user corrects via re-invocation), `empty` (offer incomplete `cortex/lifecycle/*` lifecycles via `AskUserQuestion`, then re-run), `ambiguous-backlog` (present `candidates` via `AskUserQuestion`, then re-run), `wontfix` (run the named `cortex-lifecycle-wontfix` command and halt), or `error` / `needs-feature` / `no-such-lifecycle` (report and stop — do not create a lifecycle).

The resolver never writes — Step 2's sub-procedures do.

## Step 2: Enter the Resolved State

`new` starts fresh (`phase = none`); `resume` follows the resolver's `next` directive for its `route` (Step 1 owns the mapping — don't re-derive it). When `paused`, route normally and note it.

One call composes the entry — create-index, the lifecycle-start write-back, `cortex init --ensure`, and `.session` — from the resolver's discriminants (resolve the backend once via `cortex-read-backlog-backend`; never re-derive it or new-vs-resume):

```bash
cortex-lifecycle-enter --feature {feature} --session-id $LIFECYCLE_SESSION_ID --backend {resolved-backend} --phase {none-or-current-phase} --backlog-file {backlog-filename-or-empty-string}
```

`{backlog-file}` is the resolver's `filename` basename (`""` on an exit-3 no-match). Exit 2 (ambiguous slug) → [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md)'s exit-2 rule. Else act on `state`: `ready` → proceed (`backlog_status` `open`/`no_match` is informational); `needs-decision` (the item is `already_complete` and the verb ran **no** side effect — no index, sync, or `.session`) → apply backlog-writeback.md's **Backlog Status Check** — **Continue** re-runs the call above with `--acknowledge-complete` appended (drives the full composition); **Close** on `phase = none` exits immediately, creating no artifacts and calling no finalize (there is no lifecycle dir), on any other phase runs backlog-writeback.md's finalize Close arm; `blocked` (`cortex init --ensure` refused a user-correctable gate, `.session` unwritten) → halt, fix, re-run (idempotent); `ensure-failed`/`error` → halt. When resuming, report `route`/`criticality`/`tier`, offer continue-or-restart, and surface `staleness` tersely (non-blocking drift hint; default continue).

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

Clarify, Research, and Spec are delegated to `/cortex-core:refine`.

- **`spec.md` AND `research.md` both exist** (prior refine run or resume): skip delegation, go to the phase table (Plan).
- **Otherwise** (spec.md missing, or present without research.md — warn this mixed state is inconsistent; overnight needs both): read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md), substituting the body-resolved paths below. Refine routes a missing research.md to research.

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the current phase's reference. Don't preload others.

### Reference-path propagation (load-bearing)

`${CLAUDE_SKILL_DIR}` resolves only in this body, not inside a reference you read. Wherever a reference contains a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path (a bare `skills/…` or `../` path resolves against CWD and breaks off-repo). Two targets sit outside this skill: `clarify-critic` → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`, refine's SKILL.md → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md`. `refine-delegation.md`'s `<REFINE_SKILL_MD>` placeholder resolves to `../refine/SKILL.md`.

## Phase Transition

Proceed automatically — no confirmation at phase boundaries; announce and continue. Each transition summary includes **Decisions**, **Scope delta**, **Blockers** (each "None" when empty), and **Next** (phase + what it does).

A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not user input. A prior "report"/"summarize" instruction sets text cadence only; it does not authorize `AskUserQuestion` (permitted at a boundary only by the Kept user pauses inventory).

### Per-phase completion rule

Auto-advance fires only on a phase's gate; each phase reference owns that gate and its transition statement — read the current phase's reference for the exact condition, don't re-derive it. Specify and Plan additionally gate on a §4 user-approval surface (see their references).

### Kept user pauses

Auto-proceed except where a phase reference defines a kept pause; the parity-tested inventory (tests-only, not runtime reading) lives in [kept-pauses.md](${CLAUDE_SKILL_DIR}/references/kept-pauses.md).

For criticality override syntax and the behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Situational references

No linear-flow trigger — consult only when the condition applies, don't preload:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` convention, multi-feature concurrency
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided lifecycle termination
