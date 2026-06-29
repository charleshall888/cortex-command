---
schema_version: "1"
uuid: 20938276-d6e5-4bf3-b7bd-1770084f37fa
title: Wire /cortex-core:lifecycle wontfix invocation and offload the workflow to an order-enforcing verb
status: complete
priority: medium
type: bug
created: 2026-06-25
updated: 2026-06-29
complexity: complex
criticality: high
spec: cortex/lifecycle/wire-cortex-corelifecycle-wontfix-invocation-and/spec.md
areas: ['lifecycle']
lifecycle_phase: plan
---
## Why

`complete.md:148` and the PR-closed branch route operators to `/cortex-core:lifecycle wontfix <slug>`, but SKILL.md has **no routing for a `wontfix` token** — Step 1 parses first-word-as-feature, so the advertised invocation resolves to `feature="wontfix", phase="<slug>"`, which is backwards. The workflow (`references/wontfix.md`), the terminal-state detection (`common.py` `feature_wontfix`), and the advertised entry point all exist, but nothing wires the entry to the workflow. Separately, the wontfix workflow's three steps (`git mv` archive → append `feature_wontfix` event → `cortex-update-item`) are **order-load-bearing** ("Step order is load-bearing" — `git mv` first so SessionStart enumeration drops the lifecycle even if a later step fails), enforced only by prose. Surfaced in the 2026-06-25 lifecycle reference-file audit; the buried "Reference Files" line was wontfix's only discoverability anchor (now removed in the list collapse).

## Role

Two coupled fixes:
- **Route the invocation**: recognize `wontfix` as a reserved sub-command in SKILL.md Step 1, document `/cortex-core:lifecycle wontfix <slug>` in the Invocation block, and route to the workflow instead of treating `wontfix` as a feature slug.
- **Offload the workflow to an order-enforcing verb**: `cortex-lifecycle-wontfix <slug>` performs archive-move → event-append → backlog-update in a structurally-fixed order, upgrading the prose-only ordering gate to a structural one (per CLAUDE.md "prefer structural over prose-only gates"). The skill issues one command; the verb owns the order and the byte-identical `feature_wontfix` row.

## Integration

Edits `skills/lifecycle/SKILL.md` (Step 1 parse + Invocation) and `references/wontfix.md` (+ mirrors) → lifecycle-gated. New `cortex_command` module + console-script entry. Depends on #330 for the event emission (the verb logs `feature_wontfix` via the extended `cortex-lifecycle-event`). The `feature_wontfix` row must stay byte-identical — consumed by `common.py` `detect_lifecycle_phase` + `claude/statusline.sh`.

## Edges

- `wontfix` collides with the slug-vs-phase parse — treat it as a reserved sub-command; rule out the degenerate case of a feature literally named `wontfix`.
- The verb must no-op safely if the lifecycle dir is already archived.
- The archive-internal detector patch in `common.py` stays.
- Keep the operator Close/Continue prompt as prose where a human decision is genuinely needed.

## Touch-points

- `skills/lifecycle/SKILL.md` (Step 1 + Invocation) (+ mirror)
- `skills/lifecycle/references/wontfix.md` (+ mirror)
- new `cortex_command` wontfix module + console-script entry
- tests for the routing + the verb's structural order enforcement