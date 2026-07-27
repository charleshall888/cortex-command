---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/cortex-core:lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", "start a feature lifecycle", or wants to build a non-trivial feature with structured phases.
when_to_use: "Use when starting a new feature (\"start a feature\") or any non-trivial change with structured phases. Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
argument-hint: "<feature> [phase]"
---

# Feature Lifecycle

A file-based state machine that survives context loss: research before code, approved spec before build, coherence throughout.

Read `cortex/lifecycle.config.md` first if it exists — it overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Read the served state

One read-only call serves the current state, its advance contract, and its pause spec. Pass the plugin's expected protocol range (`min`/`max` from [protocol-expectation.txt](${CLAUDE_SKILL_DIR}/references/protocol-expectation.txt)) so it can flag wheel/prose skew:

```bash
cortex-lifecycle-next "$ARGUMENTS" --expect-min {min} --expect-max {max}
```

Consume the served envelope, not the resolver's legacy `next` field. **Halt on skew or unavailability** — a `protocol-skew` state, a wrapper exit 2 (wheel absent), or a missing command each carry their own remediation (envelope `remediation`, or stderr); relay it and stop.

<!-- pause: empty-lifecycle-offer question -->
<!-- pause: ambiguous-backlog-pick question -->
**Passthrough routing states** carry a `next` directive — act on it: `new` (carries `backlog`) → Step 2 fresh; `derive-slug` (derive a 3–6 word kebab-case slug and re-run — no confirmation; the user corrects by re-invoking); `empty` (offer incomplete `cortex/lifecycle/*` lifecycles via `AskUserQuestion`, then re-run); `ambiguous-backlog` (present `candidates` via `AskUserQuestion`, then re-run); `wontfix` (run the named `cortex-lifecycle-wontfix` command and halt); `error` / `needs-feature` / `no-such-lifecycle` (report and stop — do not create a lifecycle).

**A resumable feature** (state `resume`) is served phase-keyed: `state` is the current phase, `advance_contract` threads into `cortex-lifecycle-advance` at each boundary, `pause_spec` drives the kept pauses. Surface `staleness` tersely when present (non-blocking; default continue).

`cortex-lifecycle-next` never writes — Step 2's sub-procedures do.

## Step 2: Enter the resolved state

One call composes create-index, the lifecycle-start write-back, `cortex init --ensure`, and `.session`. The envelope serves it ready-to-run as `enter_command`, with every discriminant pre-bound (feature = the resolver's canonical slug, phase, backlog-file, backend; `$LIFECYCLE_SESSION_ID` expands in-shell). **Run it verbatim** — never rebuild it, never substitute the user's typed token for its `--feature` value:

```bash
{envelope.enter_command}
```

The bound backlog-file also lets a resume repair an index that never received its backlog tags (`"index": "repaired"`) — without it, every requirements load silently narrows to project.md. Mention any `ignored_tokens` in one line.

Act on `state`:

- **`ready`** → proceed (`backlog_status` `open`/`no_match` is informational).
- **`needs-decision`** → the item is `already_complete` and the verb ran **no** side effect. Apply the Backlog Status Check in [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md).
- **`blocked`** → `cortex init --ensure` refused a user-correctable gate and `.session` is unwritten; halt, fix, re-run (idempotent).
- **`ensure-failed`** / **`error`** → halt.
- **exit 2** → ambiguous slug; apply backlog-writeback.md's exit-2 rule.

When resuming, report the served `state`/`criticality`/`tier` and offer continue-or-restart.

## Step 3: Execute the phase

Clarify, Research, and Spec are delegated to `/cortex-core:refine`. **Both `spec.md` and `research.md` present** → skip delegation, go straight to Plan. **Otherwise** → read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md); warn if spec.md exists without research.md, since overnight needs both.

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the row for the served `state`. Don't preload others.

### Reference-path propagation (load-bearing)

`${CLAUDE_SKILL_DIR}` resolves only in this body, not inside a reference you read. Wherever a reference names a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path — a bare `skills/…` or `../` path resolves against CWD and breaks off-repo. Two targets sit outside this skill: `clarify-critic` → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md`, and refine's SKILL.md → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md` (`refine-delegation.md`'s `<REFINE_SKILL_MD>` placeholder).

## Advance-verb routing (shared)

Every phase boundary hands off to `cortex-lifecycle-advance`, which owns that arm's ordered emissions and their idempotent replay. Route on the returned `state`; never re-derive it. Three arms recur everywhere:

- **`error`** → surface the verb's `message` and halt without advancing.
- **`refused`** → a gate mismatch: relay `reason` and `preferred_remedy`, re-run `cortex-lifecycle-next`, and re-invoke threading its `advance_contract.expected_from_state` via `--from-state`. If it persists after re-sync, escalate with the detected phase and the expected from_state — never pass the detected phase.
- **command not found** → halt and instruct the operator to install/upgrade the cortex-command CLI, then re-invoke. Do NOT record anything by hand.

## Phase transitions

Proceed automatically — no confirmation at boundaries; announce and continue. Each summary carries **Decisions**, **Scope delta**, **Blockers** (each "None" when empty), and **Next** (phase + what it does). Entering Plan or Implement, append the served `session_split_hint` as one line — a suggestion to end the session and re-invoke fresh, not a gate.

A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not user input; each phase reference owns its own gate. Specify and Plan additionally gate on a user-approval surface. A prior "report" or "summarize" instruction sets text cadence only — it does not authorize `AskUserQuestion`, which is permitted at a boundary only by the kept-pauses inventory ([kept-pauses.md](${CLAUDE_SKILL_DIR}/references/kept-pauses.md), tests-only).

## Criticality

Override at any time: `cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new>`. A user override always supersedes the automated Clarify reconciliation, which is monotonic-up-only.

Read state with `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or `--field <x>`. It reduces the event log to current values; the CLI omits absent keys, so apply the defaults `criticality=medium` / `tier=simple` yourself. **`"corrupted": true`** means tier/criticality are unknowable — treat the feature as *requiring* review rather than applying the skip rule.

| Criticality | Review phase | Orchestrator review | Planning |
|-------------|-------------|--------------------|---------|
| low | tier-based (skip for simple) | skipped for simple, active for complex | tier-based |
| medium | tier-based (skip for simple) | active at phase boundaries | tier-based |
| high | forced regardless of tier | active at all boundaries | single plan |
| critical | forced regardless of tier | active at all boundaries | competing plans |

Research is always parallel at every criticality, sized by the fan-out matrix `/cortex-core:research` owns. Per-role model resolution belongs to `cortex-resolve-model` at each dispatch site, never to this table. The implement→{review|complete} and specify→{plan|implement} routing rules live in their verbs, not in prose.

## Situational references

Consult only when the condition applies — don't preload:

- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided lifecycle termination

<!-- pause: resume-feature-pick question -->
Sessions bind to one feature each via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` file (never commit it). If multiple incomplete lifecycles exist and the user hasn't named one, list them and ask which to resume; features with `feature_complete` in events.log or an APPROVED verdict in review.md are ignored.
