---
name: build
description: Build a refined feature through plan, implement, review, and complete. Use when user says "/cortex-core:build", "build this", "implement this ticket", "plan and build", or names a ticket that already has a spec. Requires research.md and spec.md — run /cortex-core:refine first if either is missing.
when_to_use: "Use once a ticket is refined (spec.md exists) and you want it built. Different from /cortex-core:refine — refine produces research and spec; build takes them through plan, implement, review, and complete. /cortex-core:dev routes to whichever the ticket's status calls for."
argument-hint: "<feature> [phase]"
---

# Build

The back half of the feature state machine: plan → implement → review → complete, file-based so it survives context loss.

Read `cortex/lifecycle.config.md` first if it exists — it overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Read the served state

One read-only call serves the current state, its advance contract, and its pause spec. Pass the plugin's expected protocol range (`min`/`max` from [protocol-expectation.txt](${CLAUDE_SKILL_DIR}/references/protocol-expectation.txt)) so it can flag wheel/prose skew:

```bash
cortex-lifecycle-next "$ARGUMENTS" --expect-min {min} --expect-max {max}
```

Consume the served envelope, not the resolver's legacy `next` field. **Halt on skew or unavailability** — a `protocol-skew` state, a wrapper exit 2 (wheel absent), or a missing command each carry their own remediation; relay it and stop.

Invocation forms: `/cortex-core:build <feature>`, `/cortex-core:build <feature> <phase>`, and the reserved `/cortex-core:build complete <slug>` / `/cortex-core:build resume <feature>`.

**Not yet refined.** A served `state` of `research` or `specify`, or a `new` state, means there is no spec to build from: say so and hand off to `/cortex-core:refine {feature}`. A `resume` state is served phase-keyed — `state` is the current phase, `advance_contract` threads into `cortex-lifecycle-advance` at each boundary, and `pause_spec` drives the kept pauses. Never start a plan without both `research.md` and `spec.md` — if `spec.md` exists without `research.md`, warn that the pair is inconsistent (overnight needs both) and route to refine.

<!-- pause: empty-lifecycle-offer question -->
<!-- pause: ambiguous-backlog-pick question -->
**Passthrough routing states** carry a `next` directive — act on it: `derive-slug` (derive a 3–6 word kebab-case slug and re-run, no confirmation); `empty` (offer incomplete `cortex/lifecycle/*` lifecycles via `AskUserQuestion`, then re-run); `ambiguous-backlog` (present `candidates` via `AskUserQuestion`, then re-run); `wontfix` (run the named `cortex-lifecycle-wontfix` command and halt); `error` / `needs-feature` / `no-such-lifecycle` (report and stop).

`cortex-lifecycle-next` never writes — Step 2's sub-procedures do.

## Step 2: Enter the resolved state

One call composes create-index, the lifecycle-start write-back, `cortex init --ensure`, and `.session`. The envelope serves it ready-to-run as `enter_command` with every discriminant pre-bound. **Run it verbatim** — never rebuild it, never substitute the user's typed token for its `--feature` value:

```bash
{envelope.enter_command}
```

The bound backlog-file also lets a resume repair an index that never received its backlog tags (`"index": "repaired"`) — without it, every requirements load silently narrows to project.md. Mention any `ignored_tokens` in one line.

`ready` → proceed. `needs-decision` → the item is `already_complete` and the verb ran **no** side effect; apply the Backlog Status Check in [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md). `blocked` → a user-correctable gate refused and `.session` is unwritten; halt, fix, re-run (idempotent). `ensure-failed` / `error` → halt. Exit 2 → ambiguous slug; apply backlog-writeback.md's exit-2 rule.

When resuming, report the served `state`/`criticality`/`tier`, offer continue-or-restart, and surface `staleness` tersely (non-blocking; default continue).

## Step 3: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the row for the served `state`.

**Reference-path propagation (load-bearing).** `${CLAUDE_SKILL_DIR}` resolves only in this body, not inside a reference you read. Wherever a reference names a `${CLAUDE_SKILL_DIR}/…` path, substitute the body-resolved absolute path — a bare `skills/…` or `../` path resolves against CWD and breaks off-repo.

## Advance-verb routing (shared)

Every phase boundary hands off to `cortex-lifecycle-advance`, which owns that arm's ordered emissions and their idempotent replay. Route on the returned `state` and relay the envelope's own `message` / `reason` / `preferred_remedy` — never re-derive the outcome, and never record an emission by hand. On `refused`, re-run `cortex-lifecycle-next` and re-invoke threading its `advance_contract.expected_from_state` via `--from-state`; if the mismatch survives that re-sync, escalate with both the detected phase and the expected from_state. If the verb is missing from `PATH`, halt and tell the operator to install or upgrade the cortex-command CLI.

## Phase transitions

Proceed automatically — announce and continue, no confirmation at boundaries. Each summary carries **Decisions**, **Scope delta**, **Blockers** (each "None" when empty), and **Next**. Entering Plan or Implement, append the served `session_split_hint` as one line — a suggestion, not a gate.

A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not user input; each phase reference owns its gate, and Plan additionally gates on a user-approval surface. A prior "report" or "summarize" instruction sets text cadence only — it does not authorize `AskUserQuestion`, permitted at a boundary only by the kept-pauses inventory ([kept-pauses.md](${CLAUDE_SKILL_DIR}/references/kept-pauses.md), tests-only).

## Criticality

Override at any time: `cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new>`. A user override always supersedes the automated Clarify reconciliation, which is monotonic-up-only.

Read state with `cortex-lifecycle-state --feature {feature}` (whole-state JSON) or `--field <x>`. It reduces the event log to current values; the CLI omits absent keys, so apply the defaults `criticality=medium` / `tier=simple` yourself. **`"corrupted": true`** means tier/criticality are unknowable — treat the feature as *requiring* review rather than applying the skip rule.

| Criticality | Review phase | Orchestrator review | Planning |
|-------------|-------------|--------------------|---------|
| low | tier-based (skip for simple) | skipped for simple, active for complex | tier-based |
| medium | tier-based (skip for simple) | active at phase boundaries | tier-based |
| high | forced regardless of tier | active at all boundaries | single plan |
| critical | forced regardless of tier | active at all boundaries | competing plans |

Model choice is the dispatching agent's call at each site, never this table's. The implement→{review|complete} routing rule lives in its verb, not in prose.

## Situational references

Consult only when the condition applies — don't preload:

- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided lifecycle termination

<!-- pause: resume-feature-pick question -->
Sessions bind to one feature each via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` file (never commit it). If multiple incomplete lifecycles exist and the user hasn't named one, list them and ask which to resume; features with `feature_complete` in events.log or an APPROVED verdict in review.md are ignored.
