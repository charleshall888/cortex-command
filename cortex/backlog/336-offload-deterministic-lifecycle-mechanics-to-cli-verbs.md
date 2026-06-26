---
schema_version: "1"
uuid: 8c587080-270b-4877-9f41-0f0aa6b230f6
title: Offload deterministic lifecycle mechanics to CLI verbs
status: backlog
priority: low
type: epic
created: 2026-06-26
updated: 2026-06-26
---
## Why

The lifecycle skill's reference files narrate large amounts of deterministic, consistent-outcome procedure — event emission, git/commit staging, PR-state routing, worktree path checks, requirements selection — for the agent to hand-execute. This is exactly the work the CLI exists to absorb: a deterministic outcome does not need an agent, and the narration pollutes runtime context every phase. The 2026-06-25 lifecycle reference-file audit surfaced these as the highest-leverage offloads. This epic groups the program so the shared discipline is consistent across children and the build order is explicit.

## Scope

Children, in build order:

- **#330** — extend `cortex-lifecycle-event` with `--field` and route the inline-emitted event sites through it. Foundation; land first.
- **#331** — `complete.md` PR-state routing + shared `stage-artifacts` verbs. Depends on #330.
- **#332** — `implement.md` branch/worktree dispatch consolidation + remove the inline Python heredoc. Depends on #330 for its event sites.
- **#333** — `cortex-load-requirements` selection verb.
- **#326** — Step-2 backlog write-back + index.md creation verbs (already filed; analog of #322).

Shared discipline every child carries: pin the byte-identical-output invariant (events.log rows, staged-path sets) so consolidation cannot silently change behavior — the way #326 pins its events.log rows — and reuse the resolve-once backend routing rather than re-deriving it per child.

## Out of scope

- The two correctness bugs (#329 wontfix routing, #335 config drift) and the reference-relocation cleanup (#334) are independent — not offloads, not gated on #330.
- Prose-only trims that need no verb (already shipped inline in the reference-list collapse + orchestrator-review dedup).

## Touch-points

- `cortex_command` CLI modules + console-script entries + tests (per child)
- `skills/lifecycle/references/` (+ mirrors)