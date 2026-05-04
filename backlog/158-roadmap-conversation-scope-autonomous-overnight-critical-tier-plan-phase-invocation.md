---
schema_version: "1"
uuid: 23e7753d-b28a-4413-b5ab-34354f98568a
title: "Roadmap conversation: scope autonomous overnight critical-tier plan-phase invocation"
status: open
priority: high
type: spike
created: 2026-05-04
updated: 2026-05-04
blocked-by: []
tags: [competing-plan-synthesis, lifecycle, plan, overnight, scope]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

Discovery `competing-plan-synthesis` (research artifact: `research/competing-plan-synthesis/research.md`) was launched to design a synthesis system for the §1b critical-tier dual-plan flow at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:21-119`. The original framing assumed planning could happen overnight where the operator is unavailable, requiring autonomous synthesis.

The discovery surfaced that the autonomous overnight invocation path for `/cortex-interactive:lifecycle plan` does not exist today (`research/competing-plan-synthesis/research.md` Q4). The overnight orchestrator's plan-gen sub-agents are a different mechanism and have not fired in production (`research/overnight-plan-building/research.md:5-6, 89`). The §1b critical-tier flow has only ever fired in interactive sessions. Any synthesis-mechanism design presupposes an autonomous path that has not been scoped.

## What this ticket resolves

A roadmap-level question whose answer gates further synthesis design work. The discovery's DR-1 (revised after critical-review) explicitly defers all synthesis-mechanism commitments to this conversation:

- **Is unattended overnight critical-tier plan-phase invocation a roadmap goal?** Concrete shape would be a path like `cortex overnight start --include-unrefined` or equivalent that lets the overnight orchestrator pick up critical-tier features mid-stream and run plan-phase autonomously.
- **If yes**: scope a path-building epic as the zeroth-zeroth epic preceding any synthesis design. Instrumentation (DR-1's prerequisite F) follows the path. Synthesis design (DRs 2-7 in research.md) becomes a downstream follow-on conditional on observed `plan_comparison` events.
- **If no**: reduce scope. Drop synthesis-design tickets entirely. Keep DR-6 (async-notify-with-timeout) for the existing interactive `/cortex-interactive:lifecycle plan` flow when the operator is mid-session-but-away.
- **Synthesis-via-async-operator-decision**: a third shape surfaced in the conversation — build the synthesis-presentation layer (per DR-3 Option 4 + DR-4 + DR-5 in research.md) but keep the SELECTION step operator-driven via async push (notify.sh → operator picks remotely → defer-to-morning on timeout). Delivers synthesis output without requiring an autonomous selector or new path infrastructure.

## Why this is the right next step (Value)

Filing implementation tickets prematurely commits scope the team has not chosen. Path-building is an L-XL effort; synthesis design without a path is speculative; reducing to async-notify only forecloses a system the user originally requested. The conversation surfaces which of those is the actual goal so subsequent backlog tickets aim correctly.

The problem manifests at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:107-109` — the §1b user-selection step has no autonomous fallback, but no event in the corpus has ever needed one (`lifecycle/*/events.log` shows 4 `plan_comparison` events, all interactive). The decision lands in `requirements/pipeline.md` (where any roadmap commitment to overnight critical-tier path-building gets documented as a requirement) and conditionally in `claude/overnight/runner.sh` + `plugins/cortex-interactive/skills/lifecycle/references/plan.md` (where implementation lands if the answer is "build it").

## Inputs to bring to the conversation

- `research/competing-plan-synthesis/research.md` — full research artifact, DR-1 through DR-7
- `research/overnight-plan-building/research.md:5-6, 89, 203` — prior research documenting that overnight plan-gen has never fired in production and flagging the same intended-usage-pattern question as Open
- `lifecycle/*/events.log` — the four historical `plan_comparison` events (3 in archive, 1 active)
- `requirements/pipeline.md:87-95` — the existing deferral system that the "no, reduce scope" path would extend

## Out-of-scope

- Implementation of any of the four conversation outcomes — those become follow-on tickets
- Synthesis-mechanism design — gated on conversation outcome
- Path-building epic — gated on conversation outcome
- Re-running the underlying research — discovery already produced the framing

## Output

A short note (added to this ticket or filed as `requirements/pipeline.md` update) capturing the chosen direction. After that, follow-on backlog tickets get filed against the chosen shape and this ticket closes.
