---
name: build
description: Take a refined ticket from spec through plan, implement, review, and complete. Needs research.md and spec.md — run refine first if either is missing.
argument-hint: "<feature> [phase]"
---

# Build

The back half of the feature state machine: plan → implement → review → complete, file-based so it survives context loss. `cortex/lifecycle.config.md`, when present, overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Read the served state

```bash
cortex-lifecycle-next "$ARGUMENTS" --expect-file ${CLAUDE_SKILL_DIR}/references/protocol-expectation.txt
```

One read-only call serves the current state, its advance contract, and its pause spec; `--expect-file` hands it the plugin's protocol range so it can flag wheel/prose skew. Consume the served envelope, not the resolver's legacy `next` field. **Halt on skew or unavailability** — a `protocol-skew` state, a wrapper exit 2 (wheel absent), or a missing command each carry their own remediation; relay it and stop.

Invocation forms: `/cortex-core:build <feature>`, `<feature> <phase>`, reserved `complete <slug>` / `resume <feature>`.

**Not yet refined.** A served `state` of `research`, `specify`, or `new` means there is no spec to build from: say so and hand off to `/cortex-core:refine {feature}`. Never start a plan without both `research.md` and `spec.md` — `spec.md` alone is an inconsistent pair (overnight needs both), so warn and route to refine.

A **`resume`** state is served phase-keyed: `state` is the current phase, `advance_contract` threads into `cortex-lifecycle-advance` at each boundary, and `pause_spec` drives the kept pauses.

<!-- pause: empty-lifecycle-offer question -->
<!-- pause: ambiguous-backlog-pick question -->
**Passthrough routing states** carry a `next` directive — act on it: `derive-slug` (derive a 3–6 word kebab-case slug and re-run, no confirmation); `empty` (offer incomplete `cortex/lifecycle/*` lifecycles via `AskUserQuestion`, then re-run); `ambiguous-backlog` (present `candidates` via `AskUserQuestion`, then re-run); `wontfix` (run the named `cortex-lifecycle-wontfix` command and halt); `closed` / `parked` (the backlog item already records an outcome — relay `next` and do not build); `error` / `needs-feature` / `no-such-lifecycle` (report and stop).

## Step 2: Enter the resolved state

Run the envelope's `enter_command` **verbatim** — a `cortex-lifecycle-enter` invocation composing create-index, the lifecycle-start write-back, `cortex init --ensure`, and `.session`, with every discriminant pre-bound:

```bash
{envelope.enter_command}
```

Never rebuild it, and never substitute the user's typed token for its `--feature` value. Its bound backlog-file lets a resume repair an index that never received its backlog tags (`"index": "repaired"`); without it every requirements load silently narrows to project.md.

`ready` → proceed. `needs-decision` → the item is `already_complete` and the verb ran **no** side effect; apply the Backlog Status Check in [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md). `blocked` → a user-correctable gate refused and `.session` is unwritten; halt, fix, re-run (idempotent). `ensure-failed` / `error` → halt. Exit 2 → ambiguous slug; apply backlog-writeback.md's exit-2 rule. Mention any `ignored_tokens` in one line.

When resuming, report the served `state`/`criticality`/`tier`, offer continue-or-restart, and surface `staleness` tersely (non-blocking; default continue).

**Carry the served `criticality` and `tier` forward** — phase references consume them rather than re-reading state.

## Step 3: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the row for the served `state`.

**Reference-path propagation (load-bearing).** `${CLAUDE_SKILL_DIR}` resolves only in this body. Wherever a reference names a `${CLAUDE_SKILL_DIR}/…` path, substitute the absolute path resolved here — a bare `skills/…` or `../` path resolves against CWD and breaks off-repo.

## Advance-verb routing (shared)

Every phase boundary hands off to `cortex-lifecycle-advance`, which owns that arm's ordered emissions and their idempotent replay. Route on the returned `state` and relay the envelope's own `message` / `reason` / `preferred_remedy` — never re-derive the outcome, and never record an emission by hand. On `refused`, re-run `cortex-lifecycle-next` and re-invoke threading its `advance_contract.expected_from_state` via `--from-state`; if the mismatch survives that re-sync, escalate with both the detected phase and the expected from_state. If the verb is missing from `PATH`, halt and tell the operator to install or upgrade the cortex-command CLI.

## Phase transitions

Cross boundaries automatically — announce and continue; add no stop of your own unless a `<!-- pause: -->` marker or the arm's own routed outcome says otherwise. Each summary carries **Decisions**, **Scope delta**, **Blockers** (each "None" when empty), then **Next** last.

A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not user input; each phase reference owns its gate, and Plan additionally gates on a user-approval surface. A prior "report" or "summarize" instruction sets text cadence, not a boundary gate.

## Criticality

Override at any time with `cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new> --reason "{tag}: <one line>"`, which supersedes the monotonic-up-only Clarify reconciliation. Carry the reason — an override recorded as an outcome alone leaves the next reader re-deriving it from the artifacts — led by an optional `{tag}` from `reversibility:`, `exposure:`, `consequence:`, `other:`; an unknown tag is rejected and the whole row is discarded, so retag and re-run. `cortex-lifecycle-state --feature {feature}` (or `--field <x>`) reduces the event log to current values, omitting absent keys — apply the defaults `criticality=medium` / `tier=moderate` yourself. **`"corrupted": true`** means tier/criticality are unknowable: treat the feature as *requiring* review rather than applying the skip rule.

| Criticality | Review phase | Orchestrator review | Planning |
|-------------|-------------|--------------------|---------|
| low | tier-based (skip below complex) | skipped below complex, active for complex | tier-based |
| medium | tier-based (skip below complex) | active at phase boundaries | tier-based |
| high | forced at every tier; Stage 2 at complex only | active at all boundaries | single plan |
| critical | forced at every tier; Stage 2 at complex only | active at all boundaries | competing plans |

Either axis can force Review; only its Stage 2 is tier-gated. Forcing the full two-stage read at every tier was what kept a lighter tier from costing less, since criticality lands `high` for most non-trivial work.

Model choice is the dispatching agent's call at each site, never this table's. The implement→{review|complete} routing rule lives in its verb, not in prose.

## Situational references

- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided lifecycle termination

<!-- pause: resume-feature-pick question -->
Sessions bind to one feature each via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` file (never commit it). If multiple incomplete lifecycles exist and the user hasn't named one, list them and ask via `AskUserQuestion` which to resume; features with `feature_complete` in events.log or an APPROVED verdict in review.md are ignored.
