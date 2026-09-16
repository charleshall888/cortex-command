---
name: build
description: Take a refined ticket from spec through plan, implement, review, and complete. Needs research.md and spec.md — run refine first if either is missing.
argument-hint: "<feature> [phase]"
---

# Build

Plan → implement → review → complete, file-based so it survives context loss. `cortex/lifecycle.config.md`, when present, overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Read the served state

```bash
cortex-lifecycle-next "$ARGUMENTS" --expect-file ${CLAUDE_SKILL_DIR}/references/protocol-expectation.txt
```

One read-only call serves the state, its advance contract, and its pause spec; `--expect-file` lets it flag wheel/prose skew. Consume the served envelope, not the legacy `next` field. **Halt on skew or unavailability** — `protocol-skew`, wrapper exit 2 (wheel absent), or a missing command each carry their own remediation; relay it and stop.

Forms: `/cortex-core:build <feature>`, `<feature> <phase>`, reserved `complete <slug>` / `resume <feature>`.

**Not yet refined** — state `research`, `specify`, or `new`: hand off to `/cortex-core:refine {feature}`. Never plan without both `research.md` and `spec.md` (overnight needs both).

**`resume`** is served phase-keyed: `state` is the current phase, `advance_contract` threads into `cortex-lifecycle-advance` at each boundary, `pause_spec` drives the kept pauses. Artifacts go under `roots.artifacts.path` — never the log path, which is main-root pinned.

<!-- pause: empty-lifecycle-offer question -->
<!-- pause: ambiguous-backlog-pick question -->
**Passthrough states** carry a `next` directive — act on it: `derive-slug` (derive a 3–6 word kebab slug and re-run, no confirmation); `empty` (offer incomplete `cortex/lifecycle/*` lifecycles, then re-run); `ambiguous-backlog` (present `candidates`, then re-run); `wontfix` (run the named `cortex-lifecycle-wontfix` command and halt); `closed` / `parked` (an outcome is already recorded — relay `next`, do not build); `error` / `needs-feature` / `no-such-lifecycle` (report and stop).

## Step 2: Enter the resolved state

Run the envelope's `enter_command` **verbatim** — a `cortex-lifecycle-enter` invocation with every discriminant pre-bound:

```bash
{envelope.enter_command}
```

Never rebuild it or substitute the user's typed token for `--feature`; its bound backlog-file is what lets a resume repair an index that never received its backlog tags.

`ready` → proceed. `needs-decision` → the item is `already_complete` and nothing ran; apply the Backlog Status Check in [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md). `blocked` → a user-correctable gate refused, `.session` unwritten; halt, fix, re-run. `ensure-failed` / `error` → halt. Exit 2 → ambiguous slug; backlog-writeback.md's exit-2 rule. Mention any `ignored_tokens` in one line.

On resume, report the served `state`/`criticality`/`tier`, offer continue-or-restart, surface `staleness` tersely (default continue). **Carry `criticality` and `tier` forward** — phase references consume them rather than re-reading.

## Step 3: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the row for the served `state`.

Sub-agent dispatch is authorised by this invocation — a standing "no agents unless asked" rule does not reach the dispatches a phase reference prescribes. If dispatch is unavailable, name the substitution in the phase summary and label any review a self-review.

**Path propagation.** `${CLAUDE_SKILL_DIR}` resolves only in this body: wherever a reference names a `${CLAUDE_SKILL_DIR}/…` path, substitute the absolute path resolved here.

## Advance-verb routing

Every phase boundary hands off to `cortex-lifecycle-advance`, which owns that arm's ordered emissions and idempotent replay. Route on the returned `state` and relay its `message` / `reason` / `preferred_remedy`; never re-derive an outcome or record an emission by hand. On `refused`, re-run `cortex-lifecycle-next` and re-invoke threading `advance_contract.expected_from_state` via `--from-state`; if the mismatch survives, escalate with both phases. Verb missing from `PATH` → halt; the operator installs or upgrades the cortex-command CLI.

## Phase transitions

Cross boundaries automatically — announce and continue; add no stop of your own unless a `<!-- pause: -->` marker or the arm's routed outcome says so. Each summary carries **Decisions**, **Scope delta**, **Blockers** ("None" when empty), then **Next**. A boundary fires on its gate condition (e.g. `plan.md` all tasks `[x]`), not user input; Plan additionally gates on user approval.

## Criticality

Override anytime: `cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new> --reason "{tag}: <one line>"` (tag from `reversibility:` / `exposure:` / `consequence:` / `other:`; carry the reason so the next reader need not re-derive it). `cortex-lifecycle-state --feature {feature}` (or `--field <x>`) reduces the log to current values, omitting absent keys — default `criticality=medium` / `tier=moderate` yourself. **`"corrupted": true`** → tier/criticality unknowable: treat the feature as *requiring* review.

**Review** is forced at every tier when criticality is `high`/`critical` (Stage 2 complex-only); otherwise tier-based, complex only. **Orchestrator review** runs at every phase boundary except `low`-criticality below complex. **Planning** dispatches competing plans at `critical`, a single plan otherwise.

Model choice is the dispatching agent's call at each site. The implement→{review|complete} routing lives in its verb.

## Situational references

- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided termination

<!-- pause: resume-feature-pick question -->
Sessions bind to one feature via the gitignored, SessionEnd-cleaned `cortex/lifecycle/{feature}/.session` (never commit it). Several incomplete lifecycles and none named → list them and ask; features with `feature_complete` in events.log or an APPROVED verdict in review.md are ignored.
