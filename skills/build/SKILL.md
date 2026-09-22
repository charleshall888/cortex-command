---
name: build
description: Take a refined ticket from spec through plan, implement, review, and complete. Needs research.md and spec.md — run refine first if either is missing.
argument-hint: "<feature> [phase]"
---

# Build

Plan → implement → review → complete. State lives in files, so it survives context loss. `cortex/lifecycle.config.md`, when present, overrides complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Read the served state

```bash
cortex-lifecycle-next "$ARGUMENTS" --expect-file ${CLAUDE_SKILL_DIR}/references/protocol-expectation.txt
```

One read-only call returns the state, its advance contract, and its pause spec. `--expect-file` lets it detect a version mismatch between the installed CLI and this skill. Use the JSON result's fields, not the legacy `next` field. **Stop on `protocol-skew`, wrapper exit 2 (CLI not installed), or a missing command** — each gives its own fix; show it and stop.

Forms: `/cortex-core:build <feature>`, `<feature> <phase>`, reserved `complete <slug>` / `resume <feature>`.

**Not yet refined** — state `research`, `specify`, or `new`: hand off to `/cortex-core:refine {feature}`. Never plan without both `research.md` and `spec.md`; overnight needs both.

**`resume`** is served by phase: `state` is the current phase, `advance_contract` goes to `cortex-lifecycle-advance` at each boundary, and `pause_spec` drives the kept pauses. Write artifacts under `roots.artifacts.path` — never the log path, which always points at the main checkout.

<!-- pause: empty-lifecycle-offer question -->
<!-- pause: ambiguous-backlog-pick question -->
**Other states** carry a `next` instruction — act on it:

- `derive-slug` → make a 3–6 word kebab slug and re-run without asking.
- `empty` → offer the incomplete `cortex/lifecycle/*` lifecycles, then re-run.
- `ambiguous-backlog` → present `candidates`, then re-run.
- `wontfix` → run the named `cortex-lifecycle-wontfix` command and stop.
- `closed` / `parked` → already decided; show `next`, do not build.
- `error` / `needs-feature` / `no-such-lifecycle` → report and stop.

## Step 2: Enter the resolved state

Run the result's `enter_command` exactly as given — a `cortex-lifecycle-enter` call with every argument already filled in:

```bash
{envelope.enter_command}
```

Never rebuild it or swap the user's typed token in for `--feature`. Its backlog-file argument lets a resume repair an index that never got its backlog tags.

- `ready` → proceed.
- `needs-decision` → the item is `already_complete`; nothing ran. Apply the Backlog Status Check in [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md).
- `blocked` → a check the user can fix refused; `.session` is unwritten. Stop, fix, re-run.
- `ensure-failed` / `error` → stop.
- Exit 2 → ambiguous slug; follow backlog-writeback.md's exit-2 rule.

Mention any `ignored_tokens` in one line.

On resume, report the served `state`/`criticality`/`tier`, offer continue (default) or restart, and mention `staleness` briefly. **Carry `criticality` and `tier` forward** — the phase references use them instead of re-reading.

## Step 3: Execute the phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the row for the served `state`.

Invoking this skill authorises the sub-agents a phase reference calls for, even under a standing "no agents unless asked" rule. If you cannot start them, say what you did instead in the phase summary and label any review a self-review.

**Path propagation.** `${CLAUDE_SKILL_DIR}` resolves only in this body. Wherever a reference names a `${CLAUDE_SKILL_DIR}/…` path, use the absolute path resolved here.

## Advance-verb routing

Every phase boundary hands off to `cortex-lifecycle-advance`. It writes that boundary's events in order and is safe to run again. Route on the returned `state` and show its `message` / `reason` / `preferred_remedy`. Never work out an outcome or write an event by hand. On `refused`, re-run `cortex-lifecycle-next`, then re-invoke with `--from-state` set to `advance_contract.expected_from_state`; if still refused, escalate, naming both phases. Verb missing from `PATH` → stop; the operator installs or upgrades the cortex-command CLI.

## Phase transitions

Cross boundaries automatically: announce and continue. Add no stop unless a `<!-- pause: -->` marker or the routed outcome says so. Each summary carries **Decisions**, **Scope delta**, **Blockers** ("None" when empty), then **Next**. A boundary fires on its condition (e.g. `plan.md` all tasks `[x]`), not on user input; Plan also needs user approval.

## Criticality

Override anytime: `cortex-lifecycle-event criticality-override --feature <name> --from <old> --to <new> --reason "{tag}: <one line>"`. Tag: `reversibility:` / `exposure:` / `consequence:` / `other:`. The reason saves the next reader from working it out again.

`cortex-lifecycle-state --feature {feature}` (or `--field <x>`) returns the log's current values and omits absent keys — default `criticality=medium` / `tier=moderate` yourself. **`"corrupted": true`** → tier and criticality are unknown: treat the feature as *requiring* review.

- **Review** runs at every tier when criticality is `high`/`critical` (Stage 2 complex-only). Otherwise it runs for complex tier only.
- **Orchestrator review** runs at every phase boundary, except `low` criticality below complex.
- **Planning** uses competing plans at `critical`, a single plan otherwise.

You choose the model each time you start an agent. The implement→{review|complete} routing lives in its verb.

## Situational references

- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — parallel features via `Agent(isolation: "worktree")`
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — operator-decided termination

<!-- pause: resume-feature-pick question -->
A session binds to one feature through `cortex/lifecycle/{feature}/.session` — gitignored, cleaned at SessionEnd, never committed. Several incomplete lifecycles and none named → list them and ask. Ignore features with `feature_complete` in events.log or an APPROVED verdict in review.md.
